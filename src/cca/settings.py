"""
Centralized loader for .env and config.yaml.
PM v0.1 is the first consumer; other agents can add helper functions here as needed.

Design notes:
- `.env` loads once at import time (override=True so it isn't shadowed by stale
  system env vars).
- `config.yaml` is cached as a process-wide singleton (lru_cache).
"""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path
import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"

# .env loads as soon as this module is imported, so all downstream os.getenv calls work immediately
load_dotenv(override=True)


@lru_cache(maxsize=1)
def load_config() -> dict:
    """
    Read config.yaml; cached once per process.
    Callers read sections as needed:
        cfg = load_config()
        n = cfg["task"]["n_competitors"]
    """
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)
