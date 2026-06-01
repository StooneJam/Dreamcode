"""FastAPI 服务器：前端 ↔ LangGraph 桥梁。

当前阶段（骨架）：
- POST /api/analyze   → 启动 job，返回 job_id
- GET  /api/stream/{job_id} → SSE：每 5 秒推 log 心跳，结束推 done
- GET  /api/report/pdf → 静态 PDF 文件服务
- POST /api/jobs/{job_id}/feedback  → stub（human gate 暂未接线）
- POST /api/jobs/{job_id}/question  → stub（Q&A 暂未实现）
"""
from __future__ import annotations

import asyncio
import contextvars
import json
import sys
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from cca.graph import build_graph, empty_state
from cca.llm.factory import LLMCredential, SLOT_DEFAULTS, use_credentials
from cca.schema import AgentFamily
from cca.tools.search import use_tavily_key

_APP_DIR = Path(__file__).parent
_UPLOAD_DIR = Path(__file__).parent.parent / "data" / "uploads"
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# job_id → {"status": str, "queue": asyncio.Queue, "result": dict | None}
_jobs: dict[str, dict] = {}


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


def _invoke_graph(
    target_product: str,
    user_query: str,
    user_files: list[str] | None,
    creds: dict[AgentFamily, LLMCredential] | None,
    tavily: str | None,
) -> dict:
    """同步调用 LangGraph，由 run_in_executor 在线程池里执行。"""
    graph = build_graph(checkpointer=None)
    state = empty_state(user_query, target_product, user_files)
    with use_credentials(creds):
        with use_tavily_key(tavily):
            return graph.invoke(state)


async def _heartbeat(queue: asyncio.Queue) -> None:
    while True:
        await asyncio.sleep(5)
        await queue.put({"type": "log", "agent": "System", "text": "分析进行中..."})


async def _run_job(
    job_id: str,
    target_product: str,
    user_query: str,
    user_files: list[str] | None,
    creds: dict[AgentFamily, LLMCredential] | None,
    tavily: str | None,
) -> None:
    queue: asyncio.Queue = _jobs[job_id]["queue"]
    _jobs[job_id]["status"] = "running"
    heartbeat = asyncio.create_task(_heartbeat(queue))
    try:
        loop = asyncio.get_event_loop()
        # copy_context 把当前 contextvars 快照传入线程，use_credentials/use_tavily_key
        # 在线程内再设值，不污染主线程 context。
        ctx = contextvars.copy_context()
        result = await loop.run_in_executor(
            None, ctx.run,
            _invoke_graph, target_product, user_query, user_files, creds, tavily,
        )
        heartbeat.cancel()
        pdf = result.get("report_pdf_path") or ""
        await queue.put({
            "type": "done",
            "pdf_path": pdf,
            "filename": Path(pdf).name if pdf else "",
        })
        _jobs[job_id]["status"] = "done"
        _jobs[job_id]["result"] = result
    except Exception as exc:
        heartbeat.cancel()
        await queue.put({"type": "error", "message": str(exc)})
        _jobs[job_id]["status"] = "error"
    finally:
        await queue.put(None)  # 终止 SSE 生成器


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
    _jobs[job_id] = {"status": "pending", "queue": asyncio.Queue(), "result": None}

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
async def get_pdf(path: str, download: int = 0) -> FileResponse:
    p = Path(path)
    if not p.exists():
        return FileResponse("/dev/null", status_code=404)
    disposition = "attachment" if download else "inline"
    return FileResponse(
        p, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{p.name}"'
                 if download else f'inline; filename="{p.name}"'},
    )


@app.post("/api/jobs/{job_id}/feedback")
async def feedback(job_id: str, body: dict) -> dict:
    # human gate resume — stub，等 checkpointer + interrupt 接线后补全
    return {"ok": True}


@app.post("/api/jobs/{job_id}/question")
async def question(job_id: str, body: dict) -> dict:
    # 报告 Q&A — stub，等对话记录存储模块完成后补全
    return {"answer": "Q&A 功能即将上线"}
