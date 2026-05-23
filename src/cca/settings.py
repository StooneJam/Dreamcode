"""
集中加载 .env 与 config.yaml。
PM v0.1 是首个消费者；其他 agent 在此按需补充 helper 函数。

设计要点：
- `.env` 在 import 时一次性加载（override=True 避免被系统残留变量遮盖）。
- `config.yaml` 进程内单例缓存（lru_cache）。
- `domain_seeds/*.yaml` **不缓存**——D-021 约定用户可运行时上传新 yaml，每次现读。
"""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path
import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"

# 模块导入即加载 .env，下游所有 os.getenv 即刻可用
load_dotenv(override=True)


@lru_cache(maxsize=1)
def load_config() -> dict:
    """
    读取 config.yaml；单次进程内缓存。
    调用方按需读 section：
        cfg = load_config()
        n = cfg["task"]["n_competitors"]
    """
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_domain_seed(target_vertical: str) -> dict:
    """
    按 vertical 名读取领域 seed yaml；不存在则返空 dict。
    路径来自 config.paths.domain_seeds_dir；相对路径以项目根为基准。
    不做缓存：用户可运行时上传新 yaml，每次现读保新鲜。
    """
    seeds_dir_str = load_config().get("paths", {}).get(
        "domain_seeds_dir", "src/cca/domain_seeds"
    )
    seeds_dir = Path(seeds_dir_str)
    if not seeds_dir.is_absolute():
        seeds_dir = PROJECT_ROOT / seeds_dir

    seed_path = seeds_dir / f"{target_vertical}.yaml"
    if not seed_path.exists():
        return {}
    with open(seed_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
