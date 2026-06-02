"""报告 Q&A：基于已生成报告的多轮答疑。纯函数，便于单测与 Phase 2 持久化复用。"""
from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

# 保留最近 N 轮（每轮 user+assistant 两条）历史，超出丢最旧以控 token
_MAX_HISTORY_TURNS = 8

_SYSTEM = (
    "你是竞品分析助手，基于下面这份已生成的竞品分析报告回答用户的追问。\n"
    "规则：只引用报告中已有的信息，不编造数据；报告里没有就直说没有。\n"
    "可结合上文对话理解指代（如“它”“第二名”）。回答简洁、用中文。\n\n"
    "===== 竞品分析报告全文 =====\n{report}\n===== 报告结束 ====="
)


def trim_history(history: list[dict], max_turns: int = _MAX_HISTORY_TURNS) -> list[dict]:
    """只保留最近 max_turns 轮对话（每轮含 user+assistant 两条）。"""
    if max_turns <= 0:
        return []
    return history[-max_turns * 2:]


def build_qa_messages(report_md: str, history: list[dict], question: str) -> list[BaseMessage]:
    """组装答疑 messages：System(报告全文) + 最近若干轮历史 + 本轮问题。"""
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
    """基于报告多轮答疑，返回助手回答文本。llm 由调用方按凭证构造后传入。"""
    reply = llm.invoke(build_qa_messages(report_md, history, question))
    return (reply.content or "").strip()
