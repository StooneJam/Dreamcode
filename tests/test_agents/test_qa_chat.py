"""测试报告多轮 Q&A 逻辑 —— 用贴合 ChatModel 接口的本地 fake，不调真 API。"""
from __future__ import annotations

from types import SimpleNamespace

from langchain_core.messages import HumanMessage, SystemMessage

from cca.agents.qa_chat import answer_question, build_qa_messages, trim_history


class _FakeChat:
    """最简假 ChatModel：记下收到的 messages，返回带 .content 的对象。"""

    def __init__(self, reply: str = "这是回答"):
        self.reply = reply
        self.seen: list | None = None

    def invoke(self, messages):
        self.seen = messages
        return SimpleNamespace(content=self.reply)


def test_build_messages_grounds_on_full_report_not_truncated() -> None:
    """报告全文进 System，不再像旧 stub 那样截到 6000 字。"""
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
    assert len(trimmed) == 6  # 3 轮 × 2 条
    assert trimmed[-1]["content"] == "39"


def test_answer_question_strips_reply_and_passes_history_and_report() -> None:
    llm = _FakeChat("  ¥12/月  ")
    history = [
        {"role": "user", "content": "飞书定价？"},
        {"role": "assistant", "content": "¥15/月"},
    ]
    ans = answer_question("报告全文ABC", history, "钉钉呢？", llm)
    assert ans == "¥12/月"  # 已 strip
    contents = [m.content for m in llm.seen]
    assert "钉钉呢？" in contents              # 本轮问题
    assert "飞书定价？" in contents            # 多轮：历史进了上下文
    assert any("报告全文ABC" in c for c in contents)  # 报告 grounding
