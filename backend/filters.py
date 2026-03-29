from __future__ import annotations

from typing import Any, Dict

from .database import Database


class FilterManager:
    """Quản lý tiêu chí lọc. Đọc/ghi từ DB, fallback config.yaml."""

    def __init__(self, db: Database, default_config: Dict[str, Any]):
        self.db = db
        self.defaults = default_config

    def initialize(self) -> None:
        """Seed default_filters từ config.yaml vào DB nếu đang trống."""
        existing = self.db.get_all_filters()
        if existing:
            return
        for key, value in self.defaults.items():
            self.set(key, value)

    def get_all(self) -> Dict[str, Any]:
        """Đọc toàn bộ filters từ DB → dict giống format config."""
        data = self.db.get_all_filters()
        result = dict(self.defaults)
        result.update(data)
        return result

    def get(self, key: str) -> Any:
        """Đọc 1 filter, fallback sang defaults."""
        value = self.db.get_filter(key)
        if value is None:
            return self.defaults.get(key)
        return value

    def set(self, key: str, value: Any) -> None:
        """Ghi 1 filter vào DB."""
        self.db.set_filter(key, value)

    def reset(self) -> None:
        """Xóa toàn bộ filters trong DB, seed lại từ defaults."""
        self.db.reset_filters()
        self.initialize()
