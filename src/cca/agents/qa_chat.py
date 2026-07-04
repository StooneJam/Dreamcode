"""Report Q&A: multi-turn Q&A grounded in an already-generated report. Pure functions,
easy to unit test and reuse for phase-2 persistence."""
from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

# keep the last N turns (2 messages per turn: user+assistant); drop oldest to bound tokens
_MAX_HISTORY_TURNS = 8

_SYSTEM = (
    "你是竞品分析助手，基于下面这份已生成的竞品分析报告回答用户的追问。\n"
    "规则：只引用报告中已有的信息，不编造数据；报告里没有就直说没有。\n"
    "可结合上文对话理解指代（如“它”“第二名”）。回答简洁、用中文。\n\n"
    "===== 竞品分析报告全文 =====\n{report}\n===== 报告结束 ====="
)


def trim_history(history: list[dict], max_turns: int = _MAX_HISTORY_TURNS) -> list[dict]:
    """Keep only the last max_turns turns (2 messages per turn: user+assistant)."""
    if max_turns <= 0:
        return []
    return history[-max_turns * 2:]


def build_qa_messages(report_md: str, history: list[dict], question: str) -> list[BaseMessage]:
    """Assemble the Q&A messages: System(full report) + recent history + this question."""
    messages: list[BaseMessage] = [SystemMessage(content=_SYSTEM.format(report=report_md))]
    for turn in trim_history(history):
        content = turn.get("content", "")
        if turn.get("role") == "user":
            messages.append(HumanMessage(content=content))
        elif turn.get("role") == "assistant":
            messages.append(AIMessage(content=content))
    messages.append(HumanMessage(content=question))
    return messages


def answer_question(
    report_md: str, history: list[dict], question: str, llm: BaseChatModel
) -> str:
    """Answer a question grounded in the report; returns the assistant's reply text.
    llm is built by the caller from its own credentials."""
    reply = llm.invoke(build_qa_messages(report_md, history, question))
    return (reply.content or "").strip()
