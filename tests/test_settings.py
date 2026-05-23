"""测试 settings.py 的 config / domain_seed 加载行为。"""
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
    for field in ("target_vertical", "primary_competitor", "n_competitors", "user_query"):
        assert field in task, f"PM 需要的 task.{field} 缺失"


def test_load_config_is_cached() -> None:
    """连续两次调用应返回同一对象（lru_cache 生效）。"""
    a = settings.load_config()
    b = settings.load_config()
    assert a is b


def test_load_domain_seed_returns_empty_for_unknown_vertical() -> None:
    result = settings.load_domain_seed("vertical_that_does_not_exist_xyz123")
    assert result == {}


def test_load_domain_seed_reads_yaml_when_exists(
    tmp_path: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """模拟用户上传一份 yaml 后能被读到。"""
    seeds_dir = tmp_path / "seeds"
    seeds_dir.mkdir()
    (seeds_dir / "gaming.yaml").write_text(
        "priority_dimensions:\n  - 帧率\n  - 联机延迟\n",
        encoding="utf-8",
    )

    # 用 monkeypatch 强制 load_config 返回指向 tmp 的 paths
    monkeypatch.setattr(
        settings,
        "load_config",
        lambda: {"paths": {"domain_seeds_dir": str(seeds_dir)}},
    )

    seed = settings.load_domain_seed("gaming")

    assert seed == {"priority_dimensions": ["帧率", "联机延迟"]}


def test_load_domain_seed_does_not_cache_between_calls(
    tmp_path: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-021：用户运行时上传新 yaml，下次调用应读到新内容。"""
    seeds_dir = tmp_path / "seeds"
    seeds_dir.mkdir()
    monkeypatch.setattr(
        settings,
        "load_config",
        lambda: {"paths": {"domain_seeds_dir": str(seeds_dir)}},
    )

    # 第一次调：文件不存在
    assert settings.load_domain_seed("fresh_upload") == {}

    # 模拟用户上传
    (seeds_dir / "fresh_upload.yaml").write_text("foo: bar\n", encoding="utf-8")

    # 第二次调：应能读到新内容（无缓存）
    assert settings.load_domain_seed("fresh_upload") == {"foo": "bar"}
