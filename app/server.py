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
import os
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

from cca.agents._streaming import JobCancelled, set_sse_emitter
from cca.agents.qa_chat import answer_question
from cca.graph import build_graph, empty_state
from cca.llm.factory import SLOT_DEFAULTS, LLMCredential, get_report_llm, use_credentials
from cca.observability.logger import resolve_trace_url, track_pipeline_tokens
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
_MAX_RUN_EVENTS = 4000  # 单次运行落库的过程事件上限，防超长 job 撑爆 events blob


def _cancel_job(job_id: str) -> None:
    job = _jobs.get(job_id)
    if job and job.get("status") in ("pending", "running"):
        job["cancelled"] = True


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
    on_run_id,
):
    """返回一个可在线程池中安全调用的 graph.invoke 闭包。

    每次 invoke 用 track_pipeline_tokens 包住，拿到本次 trace 的 root run id 回传 on_run_id
    （供前端「查看完整 Trace」深链）。HITL 场景 phase1/phase2 各一次 invoke，取最后一次。

    on_run_id 放在 finally 里调用：graph.invoke 抛异常时 box 仍会被 track_pipeline_tokens
    填充（见 logger.py 的 try/finally），这里必须同样不因异常提前退出而丢了 run_id——
    失败的运行恰恰是最需要回查 trace 的场景。
    """
    def _invoke(input_value):
        graph = build_graph(checkpointer=checkpointer)
        box: dict = {}
        try:
            with use_credentials(creds):
                with use_tavily_key(tavily):
                    with set_sse_emitter(emit_fn):
                        with track_pipeline_tokens() as box:
                            return graph.invoke(input_value, config=thread_config)
        finally:
            if box.get("run_id"):
                on_run_id(box["run_id"])
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
    events: list[dict] = []  # 落库回放用：同一份事件既推 SSE 也存下来

    # emit_fn 把结构化 SSE 事件从线程安全地送入 asyncio 队列；
    # 若 job 已被取消（客户端断开），抛 JobCancelled 中止图执行。
    def emit_fn(event: dict) -> None:
        if _jobs.get(job_id, {}).get("cancelled"):
            raise JobCancelled(job_id)
        if len(events) < _MAX_RUN_EVENTS:
            events.append(event)
        try:
            loop.call_soon_threadsafe(queue.put_nowait, event)
        except Exception:
            pass

    def _capture_run_id(run_id: str) -> None:
        _jobs[job_id]["langsmith_run_id"] = run_id

    async def _persist_and_emit_trace() -> None:
        """登录用户落库过程事件流 + 实时推一条 LangSmith trace 链接。

        成功/失败都调用——失败时同样落库，且同样尝试推 trace_url，因为调用失败
        恰恰是最需要点进 LangSmith 看细节的场景，不能只在 done 路径才做。
        """
        if owner == "anonymous":
            return
        langsmith_run_id = _jobs[job_id].get("langsmith_run_id")
        db.save_run_trace(job_id, owner, langsmith_run_id, json.dumps(events, ensure_ascii=False))
        trace_url = await loop.run_in_executor(None, resolve_trace_url, langsmith_run_id)
        if trace_url:
            await queue.put({"type": "trace_url", "url": trace_url})

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
    _invoke = _make_invoke(checkpointer, creds, tavily, emit_fn, thread_config, _capture_run_id)

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
        # 匿名（未登录）不持久化：报告留在内存 job，登录才入库存历史
        if owner != "anonymous":
            db.save_report(job_id, owner, target_product, result.get("report_md") or "", pdf)
        await _persist_and_emit_trace()
        await queue.put({"type": "done", "has_pdf": bool(pdf)})

    except Exception as exc:
        _jobs[job_id]["status"] = "error"
        _jobs[job_id]["finished_at"] = time.monotonic()
        await _persist_and_emit_trace()
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
        "cancelled": False,
    }

    asyncio.create_task(_run_job(
        job_id, target_product,
        user_query or target_product,
        user_files, creds, tavily_key, owner,
        report_language=report_language,
    ))
    return {"job_id": job_id}


@app.get("/api/stream/{job_id}")
async def stream(job_id: str, request: Request) -> StreamingResponse:
    async def _generate():
        if job_id not in _jobs:
            yield f'data: {json.dumps({"type":"error","message":"job not found"})}\n\n'
            return
        job = _jobs[job_id]
        # 重连时 job 已完成：直接补发 done 事件，不等 queue
        if job.get("status") == "done":
            result = job.get("result") or {}
            yield f'data: {json.dumps({"type":"done","has_pdf":bool(result.get("report_pdf_path"))})}\n\n'
            return
        if job.get("status") == "error":
            yield f'data: {json.dumps({"type":"error","message":"job failed"})}\n\n'
            return
        queue: asyncio.Queue = job["queue"]
        while True:
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=20.0)
            except asyncio.TimeoutError:
                if await request.is_disconnected():
                    _cancel_job(job_id)
                    return
                # 空闲心跳：发真实 data 帧，防止代理因无数据关闭连接
                yield 'data: {"type":"heartbeat"}\n\n'
                continue
            if msg is None:
                break
            yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _resolve_owned_pdf(report_id: str, owner: str) -> str:
    """本人报告的 PDF 路径：DB 优先，内存 job 兜底（匿名/未持久化场景）。均按 owner 校验。"""
    report = db.get_report(report_id, owner)
    if report:
        return report.get("pdf_path") or ""
    job = _jobs.get(report_id)
    if job and job.get("owner") == owner:
        return (job.get("result") or {}).get("report_pdf_path") or ""
    return ""


@app.get("/api/report/pdf")
async def get_pdf(report_id: str, owner: str = Depends(_resolve_owner)):
    """按 report_id 取本人报告 PDF；路径只来自服务端记录，不收客户端文件路径。"""
    pdf_path = _resolve_owned_pdf(report_id, owner)
    if not pdf_path:
        return JSONResponse({"error": "not found"}, status_code=404)
    p = Path(pdf_path)
    if not p.is_absolute():
        p = _PROJECT_ROOT / p
    if not p.is_file():
        return JSONResponse({"error": "file not found"}, status_code=404)
    return FileResponse(p, media_type="application/pdf",
                        content_disposition_type="inline")


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


@app.get("/api/reports/{report_id}/trace")
async def report_trace(report_id: str, owner: str = Depends(_resolve_owner)):
    """回放一次运行的 Agent 过程事件流 + LangSmith 深链。owner 不匹配返 404。

    LangSmith URL 在此按需解析（一次网络往返），避免拖慢 job 收尾。
    """
    trace = db.get_run_trace(report_id, owner)
    if not trace:
        return JSONResponse({"error": "not found"}, status_code=404)
    loop = asyncio.get_event_loop()
    trace_url = await loop.run_in_executor(
        None, resolve_trace_url, trace.get("langsmith_run_id")
    )
    return {"events": json.loads(trace["events_json"] or "[]"), "trace_url": trace_url}


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


def _google_redirect_uri(request: Request) -> str:
    """Railway 代理做 SSL 终止，url_for 可能生成 http://。优先用显式配置的环境变量。"""
    return os.getenv("GOOGLE_REDIRECT_URI") or str(request.url_for("google_callback"))


@app.get("/auth/google")
async def google_login(request: Request) -> RedirectResponse:
    from cca.auth.google_oauth import build_auth_url
    return RedirectResponse(build_auth_url(_google_redirect_uri(request)))


@app.get("/auth/google/callback", name="google_callback")
async def google_callback(request: Request, code: str = "", error: str = "") -> RedirectResponse:
    if error or not code:
        return RedirectResponse("/?auth_error=google")
    try:
        from cca.auth.google_oauth import fetch_userinfo
        from cca.auth.session import create_session
        redirect_uri = _google_redirect_uri(request)
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
