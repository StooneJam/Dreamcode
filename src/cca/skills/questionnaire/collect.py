"""问卷回收 —— 支持 LLM 自动填写或真实分发；问卷按产品名缓存到 SQLite。"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from cca.llm.factory import get_llm
from cca.llm.structured import invoke_structured
from cca.settings import load_config
from cca.skills.questionnaire.design import Questionnaire, design_questionnaire

# 模拟用户画像，让 LLM 填写时有角色背景
_PERSONAS = [
    "中型互联网公司产品经理，每天高频使用协同办公工具",
    "创业公司 CEO，10 人小团队，关注性价比和上手速度",
    "大厂技术研发，关注 API 生态与开发者文档",
    "教育行业运营，团队 20 人，注重稳定性",
    "自由职业者，轻度协作需求，关注免费额度",
]


class QuestionResponse(BaseModel):
    question_id: str
    answer: str


class SurveyResponse(BaseModel):
    respondent_id: str
    product_name: str
    answers: list[QuestionResponse]


def _db_path() -> Path:
    raw = load_config().get("paths", {}).get("store_db", "data/memory/store.db")
    path = Path(raw)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS questionnaire_cache (
            product_name          TEXT PRIMARY KEY,
            questions_json        TEXT NOT NULL,
            competitor_names_json TEXT NOT NULL,
            created_at            TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS survey_responses (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name  TEXT NOT NULL,
            respondent_id TEXT NOT NULL,
            question_id   TEXT NOT NULL,
            answer        TEXT NOT NULL,
            collected_at  TEXT NOT NULL
        )
    """)
    conn.commit()


def _load_cached_questionnaire(conn: sqlite3.Connection, product_name: str) -> Questionnaire | None:
    row = conn.execute(
        "SELECT questions_json, competitor_names_json FROM questionnaire_cache WHERE product_name = ?",
        (product_name,),
    ).fetchone()
    if not row:
        return None
    return Questionnaire(
        product_name=product_name,
        competitor_names=json.loads(row[1]),
        questions=json.loads(row[0]),
    )


def _save_questionnaire(conn: sqlite3.Connection, q: Questionnaire) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO questionnaire_cache "
        "(product_name, questions_json, competitor_names_json, created_at) VALUES (?,?,?,?)",
        (
            q.product_name,
            json.dumps([question.model_dump() for question in q.questions], ensure_ascii=False),
            json.dumps(q.competitor_names, ensure_ascii=False),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()


def get_or_create_questionnaire(
    product_name: str,
    competitor_names: list[str],
    dimensions: list[str],
) -> Questionnaire:
    """从缓存读取该产品问卷；不存在则设计新问卷并写入缓存。"""
    with sqlite3.connect(_db_path()) as conn:
        _ensure_tables(conn)
        cached = _load_cached_questionnaire(conn, product_name)
        if cached:
            return cached
        q = design_questionnaire(product_name, competitor_names, dimensions)
        _save_questionnaire(conn, q)
        return q


def _persist_responses(conn: sqlite3.Connection, resp: SurveyResponse) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    conn.executemany(
        "INSERT INTO survey_responses "
        "(product_name, respondent_id, question_id, answer, collected_at) VALUES (?,?,?,?,?)",
        [(resp.product_name, resp.respondent_id, a.question_id, a.answer, ts)
         for a in resp.answers],
    )
    conn.commit()


def _autofill(q: Questionnaire, persona: str) -> SurveyResponse:
    """让 LLM 以指定用户角色填写问卷，返回结构化回答。"""
    sys = (
        f"你是 {q.product_name} 的真实用户，背景：{persona}。"
        "请根据使用体验如实填写问卷。"
        "rating_5 填 1-5 的数字字符串；multiple_choice 填选项原文；"
        "open_text 填 20-60 字的真实感受，包含具体场景。"
    )
    user = json.dumps(q.model_dump(), ensure_ascii=False)
    return invoke_structured(
        get_llm("deepseek"),
        [SystemMessage(content=sys), HumanMessage(content=user)],
        SurveyResponse,
    )


def collect_responses(
    q: Questionnaire,
    n: int = 5,
    fill_mode: Literal["llm", "real"] = "llm",
) -> list[SurveyResponse]:
    """自动填写 n 份问卷或准备真实分发。

    fill_mode="llm"  — LLM 模拟 n 位用户填写，持久化到 SQLite。
    fill_mode="real" — 真实分发模式，返回空列表（问卷文本已由 subgraph 格式化）。
    """
    if fill_mode == "real":
        return []
    responses = [
        _autofill(q, _PERSONAS[i % len(_PERSONAS)])
        for i in range(n)
    ]
    with sqlite3.connect(_db_path()) as conn:
        _ensure_tables(conn)
        for resp in responses:
            _persist_responses(conn, resp)
    return responses
