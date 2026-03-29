from __future__ import annotations

import logging
from typing import List

import requests

from ..database import Database
from ..models import Listing
from .base import BaseNotifier

LOGGER = logging.getLogger(__name__)


class TelegramNotifier(BaseNotifier):
    API_BASE = "https://api.telegram.org/bot{token}"

    def __init__(self, bot_token: str, db: Database, max_per_run: int = 20):
        self.bot_token = bot_token
        self.db = db
        self.max_per_run = max_per_run

    def _api_url(self, method: str) -> str:
        return f"{self.API_BASE.format(token=self.bot_token)}/{method}"

    def send(self, listings: List[Listing]) -> int:  # type: ignore[override]
        users = self.db.get_active_users()
        if not users or not listings:
            return 0

        sent = 0
        for listing in listings[: self.max_per_run]:
            text = self._format_listing(listing)
            for user in users:
                chat_id = user["chat_id"]
                ok = False
                if listing.thumbnail_url:
                    ok = self._send_photo(chat_id, listing.thumbnail_url, text)
                if not ok:
                    ok = self._send_message(chat_id, text)
                if ok:
                    sent += 1
        return sent

    def _format_listing(self, listing: Listing) -> str:
        price_line = ""
        if listing.price_million:
            price_line = f"{listing.price_million:,.0f} triệu"
            if listing.area_m2 and listing.area_m2 > 0:
                per_m2 = listing.price_million * 1_000_000 / listing.area_m2
                price_line += f" (~{per_m2:,.0f} đ/m²)"

        area_bed = []
        if listing.bedrooms is not None:
            area_bed.append(f"🛏 {listing.bedrooms} PN")
        if listing.area_m2 is not None:
            area_bed.append(f"📐 {listing.area_m2:g} m²")

        lines = [
            f"🏠 *{listing.title.strip()}*",
        ]
        if listing.location:
            lines.append(f"📍 {listing.location}")
        if price_line:
            lines.append(f"💰 {price_line}")
        if area_bed:
            lines.append(" | ".join(area_bed))
        if listing.posted_date:
            lines.append(f"📅 Đăng: {listing.posted_date}")
        lines.append(f"👉 [Xem chi tiết]({listing.url})")
        lines.append(f"_Nguồn: {listing.source}_")
        return "\n".join(lines)

    def _send_message(self, chat_id: str, text: str) -> bool:
        try:
            resp = requests.post(
                self._api_url("sendMessage"),
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": False,
                },
                timeout=15,
            )
            if not resp.ok:
                LOGGER.warning("Telegram sendMessage fail %s: %s", resp.status_code, resp.text)
                return False
            return True
        except requests.RequestException as exc:
            LOGGER.warning("Lỗi gọi Telegram sendMessage: %s", exc)
            return False

    def _send_photo(self, chat_id: str, photo_url: str, caption: str) -> bool:
        try:
            resp = requests.post(
                self._api_url("sendPhoto"),
                json={
                    "chat_id": chat_id,
                    "photo": photo_url,
                    "caption": caption,
                    "parse_mode": "Markdown",
                },
                timeout=20,
            )
            if not resp.ok:
                LOGGER.warning("Telegram sendPhoto fail %s: %s", resp.status_code, resp.text)
                return False
            return True
        except requests.RequestException as exc:
            LOGGER.warning("Lỗi gọi Telegram sendPhoto: %s", exc)
            return False

    def send_to_user(self, chat_id: str, text: str) -> bool:
        """Gửi tin nhắn tới 1 user cụ thể (dùng cho bot responses)."""
        return self._send_message(chat_id, text)

