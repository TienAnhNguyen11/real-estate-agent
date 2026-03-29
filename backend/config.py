from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import yaml


@dataclass(slots=True)
class AppConfig:

    default_filters: Dict[str, Any]
    scraper: Dict[str, Any]
    telegram: Dict[str, Any]
    scheduler: Dict[str, Any]
    database: Dict[str, Any]
    logging: Dict[str, Any]


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file config: {config_path}")

    with config_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    required_sections = [
        "default_filters",
        "scraper",
        "telegram",
        "scheduler",
        "database",
        "logging",
    ]
    for section in required_sections:
        if section not in raw:
            raise ValueError(f"Thiếu section '{section}' trong config.yaml")

    telegram = raw["telegram"]
    if not telegram.get("bot_token"):
        raise ValueError("Trường 'telegram.bot_token' đang trống trong config.yaml")
    if not telegram.get("admin_chat_id"):
        raise ValueError("Trường 'telegram.admin_chat_id' đang trống trong config.yaml")

    return AppConfig(
        default_filters=dict(raw["default_filters"]),
        scraper=dict(raw["scraper"]),
        telegram=dict(telegram),
        scheduler=dict(raw["scheduler"]),
        database=dict(raw["database"]),
        logging=dict(raw["logging"]),
    )
