"""Tests for the report's multi-turn Q&A logic -- uses a local fake matching the ChatModel interface, no real API calls."""
from __future__ import annotations

from types import SimpleNamespace

from langchain_core.messages import HumanMessage, SystemMessage

from cca.agents.qa_chat import answer_question, build_qa_messages, trim_history


class _FakeChat:
    """The simplest fake ChatModel: records the messages it receives, returns an object with .content."""

    def __init__(self, reply: str = "这是回答"):
        self.reply = reply
        self.seen: list | None = None

    def invoke(self, messages):
        self.seen = messages
        return SimpleNamespace(content=self.reply)


def test_build_messages_grounds_on_full_report_not_truncated() -> None:
    """The full report goes into System, no longer truncated to 6000 chars like the old stub did."""
    report = "报告正文" + "x" * 8000
    msgs = build_qa_messages(report, [], "定价多少？")
    assert isinstance(msgs[0], SystemMessage)
    assert report in msgs[0].content
    assert isinstance(msgs[-1], HumanMessage)
    assert msgs[-1].content == "定价多少？"


def test_build_messages_includes_history_in_order() -> None:
    history = [
        {"role": "user", "content": "飞书定价？"},
        {"role": "assistant", "content": "¥15/月"},
    ]
    msgs = build_qa_messages("报告", history, "那钉钉呢？")
    assert [type(m).__name__ for m in msgs] == [
        "SystemMessage", "HumanMessage", "AIMessage", "HumanMessage",
    ]
    assert msgs[1].content == "飞书定价？"
    assert msgs[2].content == "¥15/月"
    assert msgs[3].content == "那钉钉呢？"


def test_trim_history_keeps_last_n_turns() -> None:
    history = [{"role": "user", "content": str(i)} for i in range(40)]
    trimmed = trim_history(history, max_turns=3)
    assert len(trimmed) == 6  # 3 turns x 2 messages
    assert trimmed[-1]["content"] == "39"


def test_answer_question_strips_reply_and_passes_history_and_report() -> None:
    llm = _FakeChat("  ¥12/月  ")
    history = [
        {"role": "user", "content": "飞书定价？"},
        {"role": "assistant", "content": "¥15/月"},
    ]
    ans = answer_question("报告全文ABC", history, "钉钉呢？", llm)
    assert ans == "¥12/月"  # already stripped
    contents = [m.content for m in llm.seen]
    assert "钉钉呢？" in contents              # this round's question
    assert "飞书定价？" in contents            # multi-turn: history made it into context
    assert any("报告全文ABC" in c for c in contents)  # report grounding
