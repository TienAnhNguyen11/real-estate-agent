from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List

import requests

LOGGER = logging.getLogger(__name__)


class TelegramPoller:
    """Long-polling loop nhận messages từ Telegram."""

    def __init__(self, bot_token: str, handler):
        self.bot_token = bot_token
        self.handler = handler
        self.offset = 0
        self.running = False
        self._thread: threading.Thread | None = None

    @property
    def api_base(self) -> str:
        return f"https://api.telegram.org/bot{self.bot_token}"

    def start(self) -> None:
        """Bắt đầu polling loop (blocking)."""
        self.running = True
        LOGGER.info("Bắt đầu Telegram long-polling.")
        while self.running:
            try:
                updates = self._get_updates()
                for upd in updates:
                    self.offset = max(self.offset, upd["update_id"] + 1)
                    self.handler.handle(upd)
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("Lỗi trong polling loop: %s", exc)

    def start_in_thread(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self.start, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Dừng polling loop (graceful shutdown)."""
        self.running = False

    def _get_updates(self) -> List[Dict[str, Any]]:
        try:
            resp = requests.get(
                f"{self.api_base}/getUpdates",
                params={"offset": self.offset, "timeout": 30},
                timeout=35,
            )
            if not resp.ok:
                LOGGER.warning("getUpdates fail %s: %s", resp.status_code, resp.text)
                return []
            data = resp.json()
            return data.get("result", [])
        except requests.RequestException as exc:
            LOGGER.warning("Lỗi gọi getUpdates: %s", exc)
            return []

