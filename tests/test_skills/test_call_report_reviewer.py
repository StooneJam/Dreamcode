"""测试 call_report_reviewer skill 占位返回签名正确。"""
from __future__ import annotations

from cca.schema import QAResult
from cca.skills.call_report_reviewer import call_report_reviewer


def test_placeholder_returns_qa_result() -> None:
    result = call_report_reviewer(report_md="# 报告", profiles={})
    assert isinstance(result, QAResult)
    assert result.passed is True
    assert "占位" in (result.note or "")


def test_placeholder_signals_v1_not_real() -> None:
    """占位实现不应被误用为真审查 — note 必须明示。"""
    result = call_report_reviewer("any md", {"飞书": {}})
    assert result.note is not None
    assert "未真接入" in result.note or "占位" in result.note
