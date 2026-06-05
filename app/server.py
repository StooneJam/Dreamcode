"""FastAPI 服务器：前端 ↔ LangGraph 桥梁。

端点：
  POST /api/analyze                  → 启动 job，返回 {job_id}
  GET  /api/stream/{job_id}          → SSE：实时推 Agent 日志 + done/error
  GET  /api/report/pdf               → 内嵌预览或下载 PDF
  POST /api/jobs/{job_id}/feedback   → Phase 1 用户修订意见 → resume graph
  POST /api/jobs/{job_id}/question   → 报告多轮 Q&A（基于 report_md + qa_history）
"""
from __future__ import annotations

import asyncio
import contextvars
import json
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, Form, Header, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from cca.agents._streaming import set_sse_emitter
from cca.agents.qa_chat import answer_question
from cca.graph import build_graph, empty_state
from cca.llm.factory import SLOT_DEFAULTS, LLMCredential, get_report_llm, use_credentials
from cca.schema import AgentFamily
from cca.store import db
from cca.tools.search import use_tavily_key

_APP_DIR = Path(__file__).parent
_PROJECT_ROOT = Path(__file__).parent.parent
_UPLOAD_DIR = _PROJECT_ROOT / "data" / "uploads"
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# job_id → {status, queue, result, creds, checkpointer, thread_config, feedback_event, feedback_data, finished_at}
_jobs: dict[str, dict] = {}
# 按 (job_id, owner) 串行化同会话问答，避免历史交错与重复建会话
_qa_locks: dict[str, asyncio.Lock] = {}

_JOB_TTL = 3600  # 完成 1h 后清理内存（MemorySaver + queue 占用大）


def _evict_old_jobs() -> None:
    now = time.monotonic()
    dead = [jid for jid, j in _jobs.items()
            if j.get("finished_at") and now - j["finished_at"] > _JOB_TTL]
    for jid in dead:
        _jobs.pop(jid, None)
        _qa_locks.pop(f"{jid}:{_jobs.get(jid, {}).get('owner','')}", None)


# ── Owner 解析（从 session token） ────────────────────────────────────────


def _resolve_owner(authorization: str = Header("", alias="Authorization")) -> str:
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        return "anonymous"
    from cca.auth.session import resolve_session
    return resolve_session(token) or "anonymous"


# ── 凭证构建 ──────────────────────────────────────────────────────────────


def _build_creds(
    gpt5_key: str | None,
    deepseek_key: str | None,
    doubao_key: str | None,
) -> dict[AgentFamily, LLMCredential] | None:
    pairs: list[tuple[AgentFamily, str | None]] = [
        ("gpt-5",    gpt5_key),
        ("deepseek", deepseek_key),
        ("doubao",   doubao_key),
    ]
    creds = {
        family: LLMCredential(
            api_key=key,
            model=SLOT_DEFAULTS[family]["model"],
            base_url=SLOT_DEFAULTS[family]["base_url"],
        )
        for family, key in pairs if key
    }
    return creds or None


# ── 同步 graph 调用（在线程池执行） ─────────────────────────────────────


def _make_invoke(
    checkpointer: MemorySaver,
    creds: dict[AgentFamily, LLMCredential] | None,
    tavily: str | None,
    emit_fn,
    thread_config: dict,
):
    """返回一个可在线程池中安全调用的 graph.invoke 闭包。"""
    def _invoke(input_value):
        graph = build_graph(checkpointer=checkpointer)
        with use_credentials(creds):
            with use_tavily_key(tavily):
                with set_sse_emitter(emit_fn):
                    return graph.invoke(input_value, config=thread_config)
    return _invoke


def _get_graph_state(checkpointer: MemorySaver, thread_config: dict):
    graph = build_graph(checkpointer=checkpointer)
    return graph.get_state(thread_config)


# ── Job runner ────────────────────────────────────────────────────────────


async def _run_job(
    job_id: str,
    target_product: str,
    user_query: str,
    user_files: list[str] | None,
    creds: dict[AgentFamily, LLMCredential] | None,
    tavily: str | None,
    owner: str,
    report_language: str = "zh",
) -> None:
    queue: asyncio.Queue = _jobs[job_id]["queue"]
    loop = asyncio.get_event_loop()

    # emit_fn 把结构化 SSE 事件从线程安全地送入 asyncio 队列
    def emit_fn(event: dict) -> None:
        try:
            loop.call_soon_threadsafe(queue.put_nowait, event)
        except Exception:
            pass

    checkpointer = MemorySaver()
    thread_config = {"configurable": {"thread_id": job_id}}
    feedback_event = asyncio.Event()

    _jobs[job_id].update({
        "status": "running",
        "creds": creds,
        "checkpointer": checkpointer,
        "thread_config": thread_config,
        "feedback_event": feedback_event,
    })

    ctx = contextvars.copy_context()
    _invoke = _make_invoke(checkpointer, creds, tavily, emit_fn, thread_config)

    try:
        initial_state = empty_state(user_query, target_product, user_files)
        initial_state["report_language"] = report_language

        # ── Phase 1：跑到 human_gate interrupt ──────────────────────────
        result = await loop.run_in_executor(None, ctx.run, _invoke, initial_state)

        # 检查是否停在 interrupt 点
        snapshot = await loop.run_in_executor(
            None, _get_graph_state, checkpointer, thread_config
        )

        if snapshot.next:  # 图在等 human_gate resume
            profiles = result.get("profiles") or {}
            names = list(profiles.keys())
            target = result.get("target_product", target_product)
            n_comp = max(0, len(names) - 1)
            summary = (
                f"已完成 <b>{target}</b> 及 {n_comp} 个竞品的数据采集："
                f"{'、'.join(names)}。<br>如有修改意见请填写，也可直接继续生成报告。"
            )
            await queue.put({"type": "phase1_checkpoint", "summary": summary})

            # 等待用户反馈（最多 10 分钟，超时自动放行）
            try:
                await asyncio.wait_for(feedback_event.wait(), timeout=600)
            except asyncio.TimeoutError:
                _jobs[job_id]["feedback_data"] = {"raw_feedback": None, "approved": True}

            feedback_data = _jobs[job_id].get("feedback_data") or {"raw_feedback": None, "approved": True}

            # ── Phase 2：带 feedback resume ─────────────────────────────
            result = await loop.run_in_executor(
                None, ctx.run, _invoke, Command(resume=feedback_data)
            )

        pdf = result.get("report_pdf_path") or ""
        _jobs[job_id]["result"] = result
        _jobs[job_id]["status"] = "done"
        _jobs[job_id]["finished_at"] = time.monotonic()
        db.save_report(job_id, owner, target_product, result.get("report_md") or "", pdf)
        await queue.put({
            "type": "done",
            "pdf_path": pdf,
            "filename": Path(pdf).name if pdf else "",
        })

    except Exception as exc:
        _jobs[job_id]["status"] = "error"
        _jobs[job_id]["finished_at"] = time.monotonic()
        await queue.put({"type": "error", "message": str(exc)})
    finally:
        await queue.put(None)  # 终止 SSE 生成器
        _evict_old_jobs()


# ── FastAPI app ───────────────────────────────────────────────────────────


@asynccontextmanager
async def _lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(lifespan=_lifespan)
app.mount("/static", StaticFiles(directory=str(_APP_DIR / "static")), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(_APP_DIR / "index.html")


@app.post("/api/analyze")
async def analyze(
    target_product: str = Form(...),
    user_query: str = Form(""),
    file: UploadFile | None = File(None),
    gpt5_key: str | None = Form(None),
    deepseek_key: str | None = Form(None),
    doubao_key: str | None = Form(None),
    tavily_key: str | None = Form(None),
    report_language: str = Form("zh"),
    owner: str = Depends(_resolve_owner),
) -> dict:
    job_id = str(uuid.uuid4())

    user_files: list[str] | None = None
    if file and file.filename:
        dest = _UPLOAD_DIR / f"{job_id}_{file.filename}"
        dest.write_bytes(await file.read())
        user_files = [str(dest)]

    creds = _build_creds(gpt5_key, deepseek_key, doubao_key)
    _jobs[job_id] = {
        "status": "pending", "queue": asyncio.Queue(),
        "result": None, "creds": creds, "owner": owner,
    }

    asyncio.create_task(_run_job(
        job_id, target_product,
        user_query or target_product,
        user_files, creds, tavily_key, owner,
        report_language=report_language,
    ))
    return {"job_id": job_id}


@app.get("/api/stream/{job_id}")
async def stream(job_id: str) -> StreamingResponse:
    async def _generate():
        if job_id not in _jobs:
            yield f'data: {json.dumps({"type":"error","message":"job not found"})}\n\n'
            return
        queue: asyncio.Queue = _jobs[job_id]["queue"]
        while True:
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=20.0)
            except asyncio.TimeoutError:
                # 空闲心跳：阻止 Railway/Nginx 代理因无数据而断开连接
                yield ": keepalive\n\n"
                continue
            if msg is None:
                break
            yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/report/pdf")
async def get_pdf(path: str, download: int = 0):
    from urllib.parse import quote
    p = Path(path)
    if not p.is_absolute():
        p = _PROJECT_ROOT / p
    if not p.exists() or not p.is_file():
        return JSONResponse({"error": "file not found"}, status_code=404)
    disposition = "attachment" if download else "inline"
    # RFC 5987：filename* 支持任意 Unicode，兼容中文文件名
    encoded = quote(p.name, safe="")
    cd = f'{disposition}; filename="report.pdf"; filename*=UTF-8\'\'{encoded}'
    return FileResponse(p, media_type="application/pdf",
                        headers={"Content-Disposition": cd})


@app.post("/api/jobs/{job_id}/feedback")
async def feedback(job_id: str, body: dict) -> dict:
    job = _jobs.get(job_id)
    if not job:
        return {"ok": False, "error": "job not found"}
    job["feedback_data"] = {
        "raw_feedback": body.get("raw_feedback"),
        "approved": body.get("approved", True),
    }
    ev = job.get("feedback_event")
    if ev:
        ev.set()
    return {"ok": True}


@app.post("/api/jobs/{job_id}/question")
async def question(
    job_id: str, body: dict, owner: str = Depends(_resolve_owner)
) -> dict:
    q = (body.get("question") or "").strip()
    if not q:
        return {"answer": "无法回答：问题为空。"}

    # 报告优先从 DB 取（owner 隔离、跨重启可用）；同会话内存 job 兜底（须 owner 匹配）
    report = db.get_report(job_id, owner)
    report_md = report["report_md"] if report else ""
    job = _jobs.get(job_id)
    if not report_md and job and job.get("owner") == owner:
        report_md = (job.get("result") or {}).get("report_md") or ""
    if not report_md:
        return {"answer": "报告尚未生成或无权访问。"}

    key = f"{job_id}:{owner}"
    if key not in _qa_locks:
        _qa_locks[key] = asyncio.Lock()

    async with _qa_locks[key]:
        conv_id = db.get_or_create_conversation(job_id, owner)
        history = db.get_messages(conv_id)
        # 凭证优先级：请求体浏览器 key（重启后回看也能答）→ 内存 job → 项目 .env key。
        # 末级回退是有意的：付费按次模式下用户不传 key，由项目自有 key 兜底计费。
        creds = _build_creds(
            body.get("gpt5_key"), body.get("deepseek_key"), body.get("doubao_key")
        ) or (job.get("creds") if job else None)
        ctx = contextvars.copy_context()

        def _answer() -> str:
            with use_credentials(creds):
                return answer_question(report_md, history, q, get_report_llm())

        try:
            loop = asyncio.get_event_loop()
            answer = await loop.run_in_executor(None, ctx.run, _answer)
        except Exception as exc:
            return {"answer": f"回答失败：{exc}"}

        db.add_message(conv_id, "user", q)
        db.add_message(conv_id, "assistant", answer)

    return {"answer": answer}


@app.get("/api/reports")
async def reports_list(owner: str = Depends(_resolve_owner)) -> dict:
    """该 owner 的历史报告列表（不含正文）。"""
    return {"reports": db.list_reports(owner)}


@app.get("/api/reports/{report_id}")
async def report_detail(report_id: str, owner: str = Depends(_resolve_owner)):
    """回看单份报告：正文 + 历史对话。owner 不匹配返 404。"""
    report = db.get_report(report_id, owner)
    if not report:
        return JSONResponse({"error": "not found"}, status_code=404)
    return {"report": report, "messages": db.get_history(report_id, owner)}


# ── Auth endpoints ─────────────────────────────────────────────────────────


@app.post("/auth/register")
async def register(username: str = Form(...), password: str = Form(...)) -> dict:
    username = username.strip()
    if len(username) < 2:
        return JSONResponse({"error": "用户名至少 2 个字符"}, status_code=400)
    if len(password) < 6:
        return JSONResponse({"error": "密码至少 6 位"}, status_code=400)
    from cca.auth.password_auth import hash_password
    from cca.auth.session import create_session
    try:
        user_id, display_name = db.create_password_user(username, hash_password(password))
    except ValueError:
        return JSONResponse({"error": "用户名已被注册"}, status_code=409)
    token = create_session(user_id)
    return {"token": token, "display_name": display_name}


@app.post("/auth/password/login")
async def password_login(username: str = Form(...), password: str = Form(...)) -> dict:
    username = username.strip()
    from cca.auth.password_auth import verify_password
    from cca.auth.session import create_session
    row = db.get_password_user(username)
    if not row or not verify_password(password, row[2]):
        return JSONResponse({"error": "用户名或密码错误"}, status_code=401)
    user_id, display_name, _ = row
    token = create_session(user_id)
    return {"token": token, "display_name": display_name}


@app.get("/auth/google")
async def google_login(request: Request) -> RedirectResponse:
    from cca.auth.google_oauth import build_auth_url
    redirect_uri = str(request.url_for("google_callback"))
    return RedirectResponse(build_auth_url(redirect_uri))


@app.get("/auth/google/callback", name="google_callback")
async def google_callback(request: Request, code: str = "", error: str = "") -> RedirectResponse:
    if error or not code:
        return RedirectResponse("/?auth_error=google")
    try:
        from cca.auth.google_oauth import fetch_userinfo
        from cca.auth.session import create_session
        redirect_uri = str(request.url_for("google_callback"))
        userinfo = await fetch_userinfo(code, redirect_uri)
        user_id, display_name = db.get_or_create_user(
            "google", userinfo["sub"], userinfo.get("name") or userinfo.get("email", "用户")
        )
        token = create_session(user_id)
    except Exception:
        from loguru import logger
        logger.exception("Google OAuth callback failed")
        return RedirectResponse("/?auth_error=google")
    encoded_name = quote(display_name, safe="")
    return RedirectResponse(f"/?token={token}&display_name={encoded_name}")


@app.post("/auth/logout")
async def logout(authorization: str = Header("", alias="Authorization")) -> dict:
    token = authorization.removeprefix("Bearer ").strip()
    if token:
        from cca.auth.session import delete_session
        delete_session(token)
    return {"ok": True}
