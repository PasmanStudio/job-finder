"""Load and expose search_config.yaml settings."""
from __future__ import annotations

import os
from pathlib import Path

import yaml

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "search_config.yaml"


def load() -> dict:
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # Allow email_to override from env
    env_to = os.environ.get("EMAIL_TO", "")
    if env_to:
        cfg.setdefault("email", {})["to"] = env_to

    return cfg
