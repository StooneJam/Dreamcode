"""FastAPI server: the frontend <-> LangGraph bridge.

Endpoints:
  POST /api/analyze                  -> start a job, returns {job_id}
  GET  /api/stream/{job_id}          -> SSE: streams agent logs + done/error
  GET  /api/report/pdf               -> inline preview or download the PDF
  POST /api/jobs/{job_id}/feedback   -> phase-1 user revision feedback -> resume the graph
  POST /api/jobs/{job_id}/question   -> multi-turn report Q&A (grounded in report_md + qa_history)
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

# job_id -> {status, queue, result, creds, checkpointer, thread_config, feedback_event, feedback_data, finished_at}
_jobs: dict[str, dict] = {}
# serializes Q&A per (job_id, owner) to avoid interleaved history or duplicate conversation creation
_qa_locks: dict[str, asyncio.Lock] = {}

_JOB_TTL = 3600  # clean up memory 1h after completion (MemorySaver + queue take significant space)
_MAX_RUN_EVENTS = 4000  # cap on persisted process events per run, to keep an oversized job from blowing up the events blob


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


# ── Owner resolution (from the session token) ──────────────────────────


def _resolve_owner(authorization: str = Header("", alias="Authorization")) -> str:
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        return "anonymous"
    from cca.auth.session import resolve_session
    return resolve_session(token) or "anonymous"


# ── Credential building ──────────────────────────────────────────────────


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


# ── Synchronous graph invocation (runs in a thread pool) ────────────────


def _make_invoke(
    checkpointer: MemorySaver,
    creds: dict[AgentFamily, LLMCredential] | None,
    tavily: str | None,
    emit_fn,
    thread_config: dict,
    on_run_id,
):
    """Return a graph.invoke closure that's safe to call from a thread pool.

    Each invoke is wrapped with track_pipeline_tokens to get this trace's root run id
    and pass it to on_run_id (for the frontend's "view full trace" deep link). In the
    HITL scenario, phase1/phase2 each invoke once; the last one wins.

    on_run_id is called in a finally block: when graph.invoke raises, box still gets
    filled by track_pipeline_tokens (see logger.py's try/finally), so this must
    likewise not lose the run_id just because of an early exit from the exception --
    a failed run is exactly the scenario where looking up the trace matters most.
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


# ── Job runner ────────────────────────────────────────────────────────


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
    events: list[dict] = []  # for persisted replay: the same events are both pushed to SSE and stored

    # emit_fn thread-safely pushes a structured SSE event into the asyncio queue;
    # if the job was cancelled (client disconnected), raises JobCancelled to abort graph execution.
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
        """For logged-in users, persist the process event stream + push a live LangSmith trace link.

        Called on both success and failure -- on failure it likewise persists and
        tries to push trace_url, since a failed call is exactly the scenario where
        clicking into LangSmith for details matters most, not just on the done path.
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

        # ── Phase 1: run until human_gate's interrupt ───────────────────
        result = await loop.run_in_executor(None, ctx.run, _invoke, initial_state)

        # check whether it's paused at the interrupt point
        snapshot = await loop.run_in_executor(
            None, _get_graph_state, checkpointer, thread_config
        )

        if snapshot.next:  # the graph is waiting on human_gate's resume
            profiles = result.get("profiles") or {}
            names = list(profiles.keys())
            target = result.get("target_product", target_product)
            n_comp = max(0, len(names) - 1)
            summary = (
                f"已完成 <b>{target}</b> 及 {n_comp} 个竞品的数据采集："
                f"{'、'.join(names)}。<br>如有修改意见请填写，也可直接继续生成报告。"
            )
            await queue.put({"type": "phase1_checkpoint", "summary": summary})

            # wait for user feedback (up to 10 minutes, auto-passes through on timeout)
            try:
                await asyncio.wait_for(feedback_event.wait(), timeout=600)
            except asyncio.TimeoutError:
                _jobs[job_id]["feedback_data"] = {"raw_feedback": None, "approved": True}

            feedback_data = _jobs[job_id].get("feedback_data") or {"raw_feedback": None, "approved": True}

            # ── Phase 2: resume with feedback ────────────────────────────
            result = await loop.run_in_executor(
                None, ctx.run, _invoke, Command(resume=feedback_data)
            )

        pdf = result.get("report_pdf_path") or ""
        _jobs[job_id]["result"] = result
        _jobs[job_id]["status"] = "done"
        _jobs[job_id]["finished_at"] = time.monotonic()
        # anonymous (not logged in) users aren't persisted: the report stays in the in-memory job; only logged-in users get stored history
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
        await queue.put(None)  # terminate the SSE generator
        _evict_old_jobs()


# ── FastAPI app ─────────────────────────────────────────────────────────


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
        # if the job already finished by the time of a reconnect: send the done event directly, don't wait on the queue
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
                # idle heartbeat: send a real data frame so a proxy doesn't close the connection for lack of data
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
    """The PDF path for the caller's own report: DB first, falling back to the
    in-memory job (anonymous/unpersisted case). Both paths check owner."""
    report = db.get_report(report_id, owner)
    if report:
        return report.get("pdf_path") or ""
    job = _jobs.get(report_id)
    if job and job.get("owner") == owner:
        return (job.get("result") or {}).get("report_pdf_path") or ""
    return ""


@app.get("/api/report/pdf")
async def get_pdf(report_id: str, owner: str = Depends(_resolve_owner)):
    """Get the caller's own report PDF by report_id; the path always comes from the
    server's own record, never accepted from the client."""
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

    # prefer the report from the DB (owner-isolated, survives restarts); fall back to the same-session in-memory job (owner must match)
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
        # credential priority: request body's browser key (works even after a
        # restart) -> in-memory job -> the project's own .env key.
        # The last fallback is deliberate: in a pay-per-use model the user doesn't
        # pass a key, and the project's own key covers billing.
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
    """This owner's historical report list (excludes body text)."""
    return {"reports": db.list_reports(owner)}


@app.get("/api/reports/{report_id}")
async def report_detail(report_id: str, owner: str = Depends(_resolve_owner)):
    """Look back at a single report: body + conversation history. Returns 404 if owner doesn't match."""
    report = db.get_report(report_id, owner)
    if not report:
        return JSONResponse({"error": "not found"}, status_code=404)
    return {"report": report, "messages": db.get_history(report_id, owner)}


@app.get("/api/reports/{report_id}/trace")
async def report_trace(report_id: str, owner: str = Depends(_resolve_owner)):
    """Replay a run's agent process event stream + a LangSmith deep link. Returns 404
    if owner doesn't match.

    The LangSmith URL is resolved on demand here (one network round trip), to avoid slowing down the job's completion.
    """
    trace = db.get_run_trace(report_id, owner)
    if not trace:
        return JSONResponse({"error": "not found"}, status_code=404)
    loop = asyncio.get_event_loop()
    trace_url = await loop.run_in_executor(
        None, resolve_trace_url, trace.get("langsmith_run_id")
    )
    return {"events": json.loads(trace["events_json"] or "[]"), "trace_url": trace_url}


# ── Auth endpoints ──────────────────────────────────────────────────────


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
    """Railway's proxy terminates SSL, so url_for may generate http://. Prefer the explicitly configured env var."""
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
