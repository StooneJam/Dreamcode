"""测试 settings.py 的 config 加载行为。"""
from __future__ import annotations

import pytest

from cca import settings


@pytest.fixture(autouse=True)
def reset_config_cache() -> None:
    """每个测试前清 lru_cache，避免 monkeypatch 受历史污染。"""
    settings.load_config.cache_clear()


def test_load_config_returns_dict_with_task_section() -> None:
    config = settings.load_config()
    assert isinstance(config, dict)
    assert "task" in config
    assert "paths" in config


def test_config_task_section_has_pm_required_fields() -> None:
    """PM 启动依赖的 task 字段必须全部存在；缺失即 config 被改坏。"""
    task = settings.load_config()["task"]
    for field in ("primary_competitor", "n_competitors", "user_query"):
        assert field in task, f"PM 需要的 task.{field} 缺失"


def test_load_config_is_cached() -> None:
    """连续两次调用应返回同一对象（lru_cache 生效）。"""
    a = settings.load_config()
    b = settings.load_config()
    assert a is b
