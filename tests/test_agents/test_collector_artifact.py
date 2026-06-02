"""端到端集成：finalize_profile 的 content_and_artifact 路径走真实 ReAct loop。

dry_run.py 把 collect_one_product 整个 mock 掉，覆盖不到这条路径；单测又只手搓
ToolMessage。这里用真 create_react_agent + 假模型，验证 ToolNode 确实把 profile
放进 .artifact、模型只看到停止串、collect 能从 artifact 抽回——不调真 API。
"""
from __future__ import annotations

import json

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.prebuilt import create_react_agent

from cca.agents.collector import _extract_finalized_profile
from cca.tools.collector_tools import finalize_profile


class _ToolFake(FakeMessagesListChatModel):
    """按序回放预设消息；bind_tools 返回自身（假模型忽略工具绑定）。"""

    def bind_tools(self, tools, **kwargs):  # noqa: ANN001, ARG002
        return self


def _agent_messages(profile_json: str) -> list:
    fake = _ToolFake(responses=[
        AIMessage(content="", tool_calls=[{
            "name": "finalize_profile",
            "args": {"product_name": "钉钉", "profile_json": profile_json},
            "id": "c1",
        }]),
        AIMessage(content="完成"),
    ])
    agent = create_react_agent(model=fake, tools=[finalize_profile])
    return agent.invoke({"messages": [HumanMessage(content="采集钉钉")]})["messages"]


def test_finalize_profile_artifact_flows_through_real_react_loop() -> None:
    pj = json.dumps({
        "product_name": "钉钉",
        "dimensions": [{
            "name": "视频", "category": "功能",
            "facts": [{"statement": "x", "evidence": [{"source_url": "https://a.com"}]}],
        }],
    }, ensure_ascii=False)
    msgs = _agent_messages(pj)

    tool_msg = next(m for m in msgs if isinstance(m, ToolMessage) and m.name == "finalize_profile")
    assert "提交成功" in tool_msg.content              # 模型只看到停止串，不回显 profile
    assert tool_msg.artifact["profile"]                # ToolNode 把 profile 放进了 artifact

    extracted = _extract_finalized_profile(msgs)
    assert extracted is not None
    profile, degraded = extracted
    assert profile["product_name"] == "钉钉"
    assert len(profile["dimensions"]) == 1             # 完整抽回
    assert degraded == []
