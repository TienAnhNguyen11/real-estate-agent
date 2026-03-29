from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Iterable, List

from .models import Listing

LOGGER = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = Lock()
        self._init_schema()

    @contextmanager
    def _cursor(self):
        with self._lock:
            cur = self._conn.cursor()
            try:
                yield cur
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
            finally:
                cur.close()

    def _init_schema(self) -> None:
        with self._cursor() as cur:
            cur.executescript(
                """
                CREATE TABLE IF NOT EXISTS listings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE NOT NULL,
                    title TEXT,
                    price_text TEXT,
                    price_million REAL,
                    area_m2 REAL,
                    bedrooms INTEGER,
                    location TEXT,
                    description TEXT,
                    posted_date TEXT,
                    thumbnail_url TEXT,
                    source TEXT,
                    scraped_at TEXT,
                    notified_at TEXT,
                    is_favorite INTEGER DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_listings_url ON listings(url);
                CREATE INDEX IF NOT EXISTS idx_listings_notified ON listings(notified_at);

                CREATE TABLE IF NOT EXISTS search_filters (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS users (
                    chat_id TEXT PRIMARY KEY,
                    name TEXT,
                    is_admin INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    added_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    # === Listings ===

    def save_new_listings(self, listings: Iterable[Listing]) -> List[Listing]:
        """Lưu danh sách listings, trả về chỉ những listing mới (chưa tồn tại)."""
        new_listings: List[Listing] = []
        with self._cursor() as cur:
            for listing in listings:
                data = asdict(listing)
                url = data.pop("url")
                columns = [
                    "url",
                    "title",
                    "price_text",
                    "price_million",
                    "area_m2",
                    "bedrooms",
                    "location",
                    "description",
                    "posted_date",
                    "thumbnail_url",
                    "source",
                    "scraped_at",
                ]
                values = [url] + [data.get(col) for col in columns[1:]]
                try:
                    cur.execute(
                        f"""
                        INSERT OR IGNORE INTO listings
                        ({", ".join(columns)})
                        VALUES ({", ".join("?" for _ in columns)})
                        """,
                        values,
                    )
                    if cur.rowcount > 0:
                        new_listings.append(listing)
                except sqlite3.Error as exc:
                    LOGGER.warning("Lỗi khi lưu listing %s: %s", url, exc)
        return new_listings

    def mark_notified(self, urls: Iterable[str], timestamp: str) -> None:
        """Đánh dấu các listing đã gửi thông báo."""
        url_list = list(urls)
        if not url_list:
            return
        with self._cursor() as cur:
            cur.executemany(
                "UPDATE listings SET notified_at = ? WHERE url = ?",
                [(timestamp, url) for url in url_list],
            )

    # === Users ===

    def get_active_users(self) -> List[Dict[str, Any]]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT chat_id, name, is_admin, is_active, added_at "
                "FROM users WHERE is_active = 1"
            )
            rows = cur.fetchall()
        return [dict(row) for row in rows]

    def add_user(self, chat_id: str, name: str, is_admin: bool = False) -> None:
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT OR REPLACE INTO users (chat_id, name, is_admin, is_active)
                VALUES (?, ?, ?, 1)
                """,
                (chat_id, name, 1 if is_admin else 0),
            )

    def set_user_active(self, chat_id: str, active: bool) -> None:
        with self._cursor() as cur:
            cur.execute(
                "UPDATE users SET is_active = ? WHERE chat_id = ?",
                (1 if active else 0, chat_id),
            )

    def get_user(self, chat_id: str) -> Dict[str, Any] | None:
        with self._cursor() as cur:
            cur.execute(
                "SELECT chat_id, name, is_admin, is_active, added_at "
                "FROM users WHERE chat_id = ?",
                (chat_id,),
            )
            row = cur.fetchone()
        return dict(row) if row else None

    def get_stats(self) -> Dict[str, Any]:
        """Thống kê cơ bản từ DB."""
        with self._cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM listings")
            total = cur.fetchone()[0]

            cur.execute(
                "SELECT COUNT(*) FROM listings WHERE notified_at IS NOT NULL"
            )
            sent = cur.fetchone()[0]

            cur.execute(
                "SELECT source, COUNT(*) as c FROM listings GROUP BY source"
            )
            by_source = {row["source"]: row["c"] for row in cur.fetchall()}

        return {"total": total, "sent": sent, "by_source": by_source}

    # === Filters ===

    def get_all_filters(self) -> Dict[str, Any]:
        with self._cursor() as cur:
            cur.execute("SELECT key, value FROM search_filters")
            rows = cur.fetchall()
        result: Dict[str, Any] = {}
        for row in rows:
            key = row["key"]
            value = row["value"]
            try:
                result[key] = json.loads(value)
            except json.JSONDecodeError:
                result[key] = value
        return result

    def get_filter(self, key: str) -> Any | None:
        with self._cursor() as cur:
            cur.execute(
                "SELECT value FROM search_filters WHERE key = ?",
                (key,),
            )
            row = cur.fetchone()
        if not row:
            return None
        value = row["value"]
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value

    def set_filter(self, key: str, value: Any) -> None:
        if isinstance(value, (list, dict)):
            stored = json.dumps(value, ensure_ascii=False)
        else:
            stored = str(value)
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO search_filters (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (key, stored),
            )

    def reset_filters(self) -> None:
        with self._cursor() as cur:
            cur.execute("DELETE FROM search_filters")
