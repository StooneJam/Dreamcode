"""FastAPI 服务器：前端 ↔ LangGraph 桥梁。

端点：
  POST /api/analyze                  → 启动 job，返回 {job_id}
  GET  /api/stream/{job_id}          → SSE：实时推 Agent 日志 + done/error
  GET  /api/report/pdf               → 内嵌预览或下载 PDF
  POST /api/jobs/{job_id}/feedback   → Phase 1 用户修订意见 → resume graph
  POST /api/jobs/{job_id}/question   → 报告 Q&A（基于 report_md 用 LLM 回答）
"""
from __future__ import annotations

import asyncio
import contextvars
import json
import sys
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from cca.agents._streaming import set_sse_emitter
from cca.graph import build_graph, empty_state
from cca.llm.factory import LLMCredential, SLOT_DEFAULTS, get_report_llm, use_credentials
from cca.schema import AgentFamily
from cca.tools.search import use_tavily_key

_APP_DIR = Path(__file__).parent
_PROJECT_ROOT = Path(__file__).parent.parent
_UPLOAD_DIR = _PROJECT_ROOT / "data" / "uploads"
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# job_id → {status, queue, result, creds, checkpointer, thread_config, feedback_event, feedback_data}
_jobs: dict[str, dict] = {}


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
        await queue.put({
            "type": "done",
            "pdf_path": pdf,
            "filename": Path(pdf).name if pdf else "",
        })

    except Exception as exc:
        _jobs[job_id]["status"] = "error"
        await queue.put({"type": "error", "message": str(exc)})
    finally:
        await queue.put(None)  # 终止 SSE 生成器


# ── FastAPI app ───────────────────────────────────────────────────────────


app = FastAPI()
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
        "result": None, "creds": creds,
    }

    asyncio.create_task(_run_job(
        job_id, target_product,
        user_query or target_product,
        user_files, creds, tavily_key,
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
            msg = await queue.get()
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
    p = Path(path)
    if not p.is_absolute():
        p = _PROJECT_ROOT / p
    if not p.exists() or not p.is_file():
        return JSONResponse({"error": "file not found"}, status_code=404)
    disposition = "attachment" if download else "inline"
    return FileResponse(
        p, media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{p.name}"'},
    )


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
async def question(job_id: str, body: dict) -> dict:
    job = _jobs.get(job_id)
    if not job or job.get("status") != "done":
        return {"answer": "报告尚未生成，请稍后再试。"}

    report_md = (job.get("result") or {}).get("report_md") or ""
    q = body.get("question", "").strip()
    if not q or not report_md:
        return {"answer": "无法回答：报告内容不可用。"}

    creds = job.get("creds")
    loop = asyncio.get_event_loop()
    ctx = contextvars.copy_context()

    def _answer():
        from langchain_core.messages import HumanMessage, SystemMessage
        with use_credentials(creds):
            llm = get_report_llm()
            return llm.invoke([
                SystemMessage(content=(
                    "你是竞品分析助手。基于以下报告内容简洁地回答用户问题，"
                    "只引用报告中有的信息，不要编造数据。"
                )),
                HumanMessage(content=f"报告内容：\n{report_md[:6000]}\n\n问题：{q}"),
            ]).content

    try:
        answer = await loop.run_in_executor(None, ctx.run, _answer)
        return {"answer": answer}
    except Exception as exc:
        return {"answer": f"回答失败：{exc}"}
