"""Tests for settings.py's config-loading behavior."""
from __future__ import annotations

import pytest

from cca import settings


@pytest.fixture(autouse=True)
def reset_config_cache() -> None:
    """Clear the lru_cache before every test, so monkeypatches aren't polluted by earlier state."""
    settings.load_config.cache_clear()


def test_load_config_returns_dict_with_task_section() -> None:
    config = settings.load_config()
    assert isinstance(config, dict)
    assert "task" in config
    assert "paths" in config


def test_config_task_section_has_pm_required_fields() -> None:
    """Every task field PM's startup depends on must be present; a missing one means config got broken."""
    task = settings.load_config()["task"]
    for field in ("primary_competitor", "n_competitors", "user_query"):
        assert field in task, f"PM 需要的 task.{field} 缺失"


def test_load_config_is_cached() -> None:
    """Two consecutive calls should return the same object (lru_cache in effect)."""
    a = settings.load_config()
    b = settings.load_config()
    assert a is b
