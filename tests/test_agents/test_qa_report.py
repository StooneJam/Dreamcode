"""Report Agent 测试。

覆盖：
- 工具单元测试（chart / pdf_renderer）
- report_node 输出结构校验
- forced 数据置信度标注
- 豆包 reviewer 集成开关
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cca.agents.qa_report import (
    _build_initial_message,
    _collect_forced_keys,
    _extract_final_md,
    _extract_pdf_path,
    _serialize_profiles,
)
from cca.schema import QAResult, ReportTask


# ---------------------------------------------------------------------------
# 辅助 fixtures / helpers
# ---------------------------------------------------------------------------

FAKE_REPORT_MD = """## 执行摘要
飞书竞品分析覆盖钉钉和企业微信。

## 核心功能对比
钉钉视频会议最大支持 300 人。

## 定价结构
钉钉 Pro 30 元/用户/月；企业微信 Pro 25 元/用户/月。（数据置信度低，仅供参考）

## 用户口碑
钉钉 AppStore 评分 4.2，企业微信 3.9。

## SWOT 分析
钉钉优势：定价低于竞品均值。

## 结论与建议
飞书在生态整合上仍有提升空间。
"""


def _make_tool_message(name: str, content: str):
    from langchain_core.messages import ToolMessage
    return ToolMessage(content=content, name=name, tool_call_id="fake-id")


def _make_ai_message_with_render_pdf(markdown_content: str) -> object:
    """构造带 render_pdf tool_call 的 AIMessage，匹配 _extract_final_md 的提取逻辑。"""
    from langchain_core.messages import AIMessage
    return AIMessage(
        content="",
        tool_calls=[{
            "id": "fake-tc-id",
            "name": "render_pdf",
            "args": {"markdown_content": markdown_content, "target_product": "飞书"},
        }],
    )


def _fake_agent_messages(include_pdf: bool = True, include_reviewer: bool = False):
    msgs = [_make_ai_message_with_render_pdf(FAKE_REPORT_MD)]
    if include_pdf:
        msgs.append(_make_tool_message("render_pdf", "output/report_飞书.pdf"))
    if include_reviewer:
        result = QAResult(product_name="__report__", passed=True, note="ok")
        msgs.append(_make_tool_message("call_reviewer", result.model_dump_json()))
    return msgs


# ---------------------------------------------------------------------------
# 工具单元测试
# ---------------------------------------------------------------------------

class TestRenderBarChart:
    def test_returns_markdown_embed(self, tmp_path):
        with patch("cca.tools.chart._CHART_DIR", tmp_path):
            from cca.tools.chart import render_bar_chart
            result = render_bar_chart.invoke({
                "title": "评分对比",
                "categories": '["钉钉", "企业微信"]',
                "values": "[4.2, 3.9]",
                "filename": "test_ratings",
            })
        assert result.startswith("![评分对比]")
        assert "test_ratings.png" in result

    def test_creates_png_file(self, tmp_path):
        with patch("cca.tools.chart._CHART_DIR", tmp_path):
            from cca.tools.chart import render_bar_chart
            render_bar_chart.invoke({
                "title": "定价对比",
                "categories": '["钉钉"]',
                "values": "[30.0]",
                "filename": "test_price",
            })
        assert (tmp_path / "test_price.png").exists()


class TestRenderChart:
    def test_bar_returns_markdown_embed(self, tmp_path):
        with patch("cca.tools.chart._CHART_DIR", tmp_path):
            from cca.tools.chart import render_chart
            result = render_chart.invoke({
                "chart_type": "bar",
                "title": "评分对比",
                "data_json": '{"labels": ["钉钉", "企业微信"], "values": [4.2, 3.9]}',
                "filename": "test_bar",
            })
        assert result.startswith("![评分对比]")
        assert "test_bar.png" in result

    def test_radar_creates_png(self, tmp_path):
        with patch("cca.tools.chart._CHART_DIR", tmp_path):
            from cca.tools.chart import render_chart
            render_chart.invoke({
                "chart_type": "radar",
                "title": "综合能力对比",
                "data_json": json.dumps({
                    "labels": ["功能", "生态", "定价", "易用"],
                    "series": {"钉钉": [4, 5, 3, 4], "企业微信": [3, 4, 5, 4]},
                    "max_value": 5,
                }),
                "filename": "test_radar",
            })
        assert (tmp_path / "test_radar.png").exists()

    def test_grouped_bar_creates_png(self, tmp_path):
        with patch("cca.tools.chart._CHART_DIR", tmp_path):
            from cca.tools.chart import render_chart
            render_chart.invoke({
                "chart_type": "grouped_bar",
                "title": "多维度对比",
                "data_json": json.dumps({
                    "labels": ["功能", "定价"],
                    "series": {"钉钉": [4, 3], "企业微信": [3, 5]},
                }),
                "filename": "test_grouped",
            })
        assert (tmp_path / "test_grouped.png").exists()

    def test_pie_creates_png(self, tmp_path):
        with patch("cca.tools.chart._CHART_DIR", tmp_path):
            from cca.tools.chart import render_chart
            render_chart.invoke({
                "chart_type": "pie",
                "title": "市场份额",
                "data_json": '{"labels": ["钉钉", "企业微信"], "values": [60, 40]}',
                "filename": "test_pie",
            })
        assert (tmp_path / "test_pie.png").exists()


class TestRenderPdf:
    def test_creates_output_file(self, tmp_path):
        with patch("cca.tools.pdf_renderer._OUTPUT_DIR", tmp_path):
            from cca.tools.pdf_renderer import render_pdf
            result = render_pdf.invoke({
                "markdown_content": "# Test\nHello",
                "target_product": "飞书",
            })
        assert "飞书" in result
        assert Path(result).exists()


# ---------------------------------------------------------------------------
# 内部函数单元测试
# ---------------------------------------------------------------------------

class TestCollectForcedKeys:
    def test_identifies_forced_units(self, mock_state):
        forced = _collect_forced_keys(mock_state["review_state"])
        assert "collector:企业微信" in forced
        assert "collector:钉钉" not in forced

    def test_empty_review_state(self):
        assert _collect_forced_keys([]) == set()


class TestSerializeProfiles:
    def test_forced_product_gets_annotation(self, mock_state):
        forced = _collect_forced_keys(mock_state["review_state"])
        serialized = _serialize_profiles(mock_state["profiles"], forced)
        data = json.loads(serialized)
        assert "_低置信度来源" in data["企业微信"]
        assert "_低置信度来源" not in data["钉钉"]


class TestBuildInitialMessage:
    def _call(self, mock_state, *, with_context: bool = False) -> str:
        report_task = ReportTask(**mock_state["report_task"])
        profiles_json = _serialize_profiles(mock_state["profiles"], set())
        return _build_initial_message(
            report_task,
            profiles_json,
            exploration_result=mock_state.get("exploration_result") if with_context else None,
            task_plan=mock_state.get("task_plan") if with_context else None,
            review_state=mock_state.get("review_state", []) if with_context else [],
        )

    def test_contains_task_fields(self, mock_state):
        msg = self._call(mock_state)
        assert "飞书" in msg
        assert "产品负责人" in msg
        assert "执行摘要" in msg

    def test_contains_profiles_json(self, mock_state):
        msg = self._call(mock_state)
        assert "钉钉" in msg
        assert "企业微信" in msg

    def test_task_plan_priority_dimensions_in_context(self, mock_state):
        """mock_state.task_plan 中的 priority_dimensions / product_type 应进 prompt 上下文。"""
        # 给 mock_state 的 task_plan 灌一个 priority_dimensions 验证
        mock_state["task_plan"]["collect_tasks"][0]["priority_dimensions"] = ["定价", "视频会议"]
        msg = self._call(mock_state, with_context=True)
        assert "PM 阶段二决策回顾" in msg
        assert "协作办公SaaS" in msg  # task_plan.product_type
        assert "定价" in msg

    def test_review_state_forced_in_context(self, mock_state):
        """review_state 全量进 prompt；forced 项的 qa_flags 应可见。"""
        msg = self._call(mock_state, with_context=True)
        assert "PM 评审台账" in msg
        assert "forced" in msg
        assert "定价来源 404" in msg  # 企业微信 collector forced 项的 qa_flags

    def test_no_context_block_when_empty(self, mock_state):
        """exploration_result=None / task_plan=None / review_state=[] 时不渲染对应段落。"""
        report_task = ReportTask(**mock_state["report_task"])
        profiles_json = _serialize_profiles(mock_state["profiles"], set())
        msg = _build_initial_message(
            report_task, profiles_json,
            exploration_result=None, task_plan=None, review_state=[],
        )
        assert "一轮探索回顾" not in msg
        assert "PM 阶段二决策回顾" not in msg
        assert "PM 评审台账" not in msg
        # 但 ReportTask 块与 profiles 块仍在
        assert "报告任务" in msg
        assert "产品档案数据" in msg


class TestExtractHelpers:
    def test_extract_final_md(self):
        msgs = _fake_agent_messages()
        assert _extract_final_md(msgs) == FAKE_REPORT_MD

    def test_extract_pdf_path(self):
        msgs = _fake_agent_messages(include_pdf=True)
        assert _extract_pdf_path(msgs) == "output/report_飞书.pdf"

    def test_extract_pdf_path_none_when_absent(self):
        msgs = _fake_agent_messages(include_pdf=False)
        assert _extract_pdf_path(msgs) is None


# ---------------------------------------------------------------------------
# report_node 集成测试（mock agent）
# ---------------------------------------------------------------------------

class TestReportNode:
    def _invoke_node(self, mock_state, extra_messages=None):
        msgs = _fake_agent_messages(include_pdf=True) + (extra_messages or [])
        mock_agent = MagicMock()
        mock_agent.invoke.return_value = {"messages": msgs}
        with patch("cca.agents.qa_report.create_react_agent", return_value=mock_agent):
            from cca.agents.qa_report import report_node
            return report_node(mock_state)

    def test_returns_required_keys(self, mock_state):
        result = self._invoke_node(mock_state)
        for key in ("report_md", "report_pdf_path", "report_status", "qa_results", "audit_log"):
            assert key in result

    def test_report_md_is_non_empty(self, mock_state):
        result = self._invoke_node(mock_state)
        assert isinstance(result["report_md"], str)
        assert len(result["report_md"]) > 0

    def test_report_status_passed_by_default(self, mock_state_with_reviewer):
        # reviewer 开启但 fake messages 里无 reviewer 消息 → _extract_reviewer_result 返回默认 passed=True
        result = self._invoke_node(mock_state_with_reviewer)
        assert result["report_status"] == "passed"

    def test_pdf_path_extracted(self, mock_state):
        result = self._invoke_node(mock_state)
        assert result["report_pdf_path"] == "output/report_飞书.pdf"

    def test_audit_log_appended(self, mock_state):
        result = self._invoke_node(mock_state)
        assert any(e["agent"] == "report" for e in result["audit_log"])

    def test_reviewer_result_captured(self, mock_state_with_reviewer):
        reviewer_msg = _make_tool_message(
            "call_reviewer",
            QAResult(product_name="__report__", passed=False,
                     failed_checks=["图文不一致"]).model_dump_json(),
        )
        result = self._invoke_node(mock_state_with_reviewer, extra_messages=[reviewer_msg])
        assert result["report_status"] == "failed"   # reviewer 开启且返回 passed=False → failed
        assert result["qa_results"][0]["passed"] is False
