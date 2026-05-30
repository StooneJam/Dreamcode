"""
集中加载 .env 与 config.yaml。
PM v0.1 是首个消费者；其他 agent 在此按需补充 helper 函数。

设计要点：
- `.env` 在 import 时一次性加载（override=True 避免被系统残留变量遮盖）。
- `config.yaml` 进程内单例缓存（lru_cache）。
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
