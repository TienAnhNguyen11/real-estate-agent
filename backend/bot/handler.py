from __future__ import annotations

import logging
from typing import Any, Dict, List

from ..database import Database
from ..filters import FilterManager
from ..notifier import TelegramNotifier
from ..orchestrator import ScraperOrchestrator

LOGGER = logging.getLogger(__name__)


class CommandHandler:
    """Xử lý commands từ Telegram users."""

    def __init__(
        self,
        db: Database,
        filter_manager: FilterManager,
        orchestrator: ScraperOrchestrator,
        notifier: TelegramNotifier,
    ):
        self.db = db
        self.filter_manager = filter_manager
        self.orchestrator = orchestrator
        self.notifier = notifier

    # === Entry point ===

    def handle(self, update: Dict[str, Any]) -> None:
        message = update.get("message") or update.get("edited_message")
        if not message:
            return
        chat = message.get("chat", {})
        chat_id = str(chat.get("id"))
        text: str = message.get("text") or ""
        username = message.get("from", {}).get("username") or ""

        if text.startswith("/start"):
            self.handle_start(chat_id, username, "")
            return

        user = self.db.get_user(chat_id)
        if not user or not user.get("is_active"):
            self.notifier.send_to_user(chat_id, "Bạn chưa được cấp quyền.")
            return

        if not text.startswith("/"):
            return

        parts = text.split()
        cmd = parts[0].lower()
        args = parts[1:]

        COMMAND_MAP = {
            "/filter": self.cmd_filter,
            "/set_price": self.cmd_set_price,
            "/set_area": self.cmd_set_area,
            "/set_beds": self.cmd_set_beds,
            "/set_district": self.cmd_set_district,
            "/set_type": self.cmd_set_type,
            "/add_keyword": self.cmd_add_keyword,
            "/remove_keyword": self.cmd_remove_keyword,
            "/add_exclude": self.cmd_add_exclude,
            "/remove_exclude": self.cmd_remove_exclude,
            "/reset": self.cmd_reset,
            "/run": self.cmd_run,
            "/pause": self.cmd_pause,
            "/resume": self.cmd_resume,
            "/stats": self.cmd_stats,
            "/help": self.cmd_help,
            "/add_user": self.cmd_add_user,
            "/remove_user": self.cmd_remove_user,
            "/users": self.cmd_users,
        }

        handler = COMMAND_MAP.get(cmd)
        if not handler:
            self.notifier.send_to_user(chat_id, "Không hiểu lệnh. Gõ /help để xem danh sách.")
            return

        try:
            handler(chat_id, args)  # type: ignore[misc]
        except TypeError:
            handler(chat_id)  # type: ignore[misc]

    # === Filter commands ===

    def cmd_filter(self, chat_id: str, *_args: List[str]) -> None:
        f = self.filter_manager.get_all()
        lines = [
            "📋 *Tiêu chí hiện tại:*",
            f"Loại: {f.get('property_type')}",
            f"Khu vực: {f.get('location')}",
            f"Quận: {f.get('district') or '-'}",
            f"Giá: {f.get('price_min')} - {f.get('price_max')} triệu",
            f"Diện tích: {f.get('area_min')} - {f.get('area_max')} m²",
            f"Số PN tối thiểu: {f.get('bedrooms_min')}",
            f"Keywords: {', '.join(f.get('keywords') or [])}",
            f"Exclude: {', '.join(f.get('exclude_keywords') or [])}",
            f"Paused: {bool(f.get('is_paused'))}",
        ]
        self.notifier.send_to_user(chat_id, "\n".join(lines))

    def cmd_set_price(self, chat_id: str, args: List[str]) -> None:
        if len(args) != 2:
            self.notifier.send_to_user(chat_id, "Usage: /set_price 2000 4000")
            return
        try:
            min_v = int(args[0])
            max_v = int(args[1])
        except ValueError:
            self.notifier.send_to_user(chat_id, "Giá không hợp lệ.")
            return
        self.filter_manager.set("price_min", min_v)
        self.filter_manager.set("price_max", max_v)
        self.notifier.send_to_user(chat_id, f"Đã cập nhật giá: {min_v} - {max_v} triệu.")

    def cmd_set_area(self, chat_id: str, args: List[str]) -> None:
        if len(args) != 2:
            self.notifier.send_to_user(chat_id, "Usage: /set_area 60 100")
            return
        try:
            min_v = int(args[0])
            max_v = int(args[1])
        except ValueError:
            self.notifier.send_to_user(chat_id, "Diện tích không hợp lệ.")
            return
        self.filter_manager.set("area_min", min_v)
        self.filter_manager.set("area_max", max_v)
        self.notifier.send_to_user(chat_id, f"Đã cập nhật diện tích: {min_v}-{max_v} m².")

    def cmd_set_beds(self, chat_id: str, args: List[str]) -> None:
        if len(args) != 1:
            self.notifier.send_to_user(chat_id, "Usage: /set_beds 2")
            return
        try:
            beds = int(args[0])
        except ValueError:
            self.notifier.send_to_user(chat_id, "Số PN không hợp lệ.")
            return
        self.filter_manager.set("bedrooms_min", beds)
        self.notifier.send_to_user(chat_id, f"Đã cập nhật số PN tối thiểu: {beds}.")

    def cmd_set_district(self, chat_id: str, args: List[str]) -> None:
        if not args:
            self.notifier.send_to_user(chat_id, "Usage: /set_district quan-cau-giay")
            return
        district = args[0]
        self.filter_manager.set("district", district)
        self.notifier.send_to_user(chat_id, f"Đã cập nhật quận: {district}.")

    def cmd_set_type(self, chat_id: str, args: List[str]) -> None:
        if not args:
            self.notifier.send_to_user(chat_id, "Usage: /set_type ban-nha-rieng")
            return
        ptype = args[0]
        self.filter_manager.set("property_type", ptype)
        self.notifier.send_to_user(chat_id, f"Đã cập nhật loại BĐS: {ptype}.")

    def cmd_add_keyword(self, chat_id: str, args: List[str]) -> None:
        if not args:
            self.notifier.send_to_user(chat_id, "Usage: /add_keyword sổ hồng")
            return
        kw = " ".join(args).strip()
        curr = self.filter_manager.get("keywords") or []
        if kw not in curr:
            curr.append(kw)
            self.filter_manager.set("keywords", curr)
        self.notifier.send_to_user(chat_id, f"Đã thêm keyword: {kw}")

    def cmd_remove_keyword(self, chat_id: str, args: List[str]) -> None:
        if not args:
            self.notifier.send_to_user(chat_id, "Usage: /remove_keyword sổ hồng")
            return
        kw = " ".join(args).strip()
        curr = self.filter_manager.get("keywords") or []
        curr = [k for k in curr if k != kw]
        self.filter_manager.set("keywords", curr)
        self.notifier.send_to_user(chat_id, f"Đã xóa keyword: {kw}")

    def cmd_add_exclude(self, chat_id: str, args: List[str]) -> None:
        if not args:
            self.notifier.send_to_user(chat_id, "Usage: /add_exclude chưa có sổ")
            return
        kw = " ".join(args).strip()
        curr = self.filter_manager.get("exclude_keywords") or []
        if kw not in curr:
            curr.append(kw)
            self.filter_manager.set("exclude_keywords", curr)
        self.notifier.send_to_user(chat_id, f"Đã thêm exclude keyword: {kw}")

    def cmd_remove_exclude(self, chat_id: str, args: List[str]) -> None:
        if not args:
            self.notifier.send_to_user(chat_id, "Usage: /remove_exclude chưa có sổ")
            return
        kw = " ".join(args).strip()
        curr = self.filter_manager.get("exclude_keywords") or []
        curr = [k for k in curr if k != kw]
        self.filter_manager.set("exclude_keywords", curr)
        self.notifier.send_to_user(chat_id, f"Đã xóa exclude keyword: {kw}")

    def cmd_reset(self, chat_id: str, *_args: List[str]) -> None:
        self.filter_manager.reset()
        self.notifier.send_to_user(chat_id, "Đã reset filters về mặc định.")

    # === Actions ===

    def cmd_run(self, chat_id: str, *_args: List[str]) -> None:
        self.notifier.send_to_user(chat_id, "Đang tìm BĐS phù hợp...")
        self.orchestrator.run()
        self.notifier.send_to_user(chat_id, "Đã tìm xong BĐS phù hợp.")

    def cmd_pause(self, chat_id: str, *_args: List[str]) -> None:
        self.filter_manager.set("is_paused", True)
        self.notifier.send_to_user(chat_id, "Đã tạm dừng orchestrator.")

    def cmd_resume(self, chat_id: str, *_args: List[str]) -> None:
        self.filter_manager.set("is_paused", False)
        self.notifier.send_to_user(chat_id, "Đã bật lại orchestrator.")

    def cmd_stats(self, chat_id: str, *_args: List[str]) -> None:
        stats = self.db.get_stats()
        lines = [
            "📊 *Thống kê:*",
            f"Tổng tin: {stats['total']}",
            f"Đã gửi: {stats['sent']}",
        ]
        for src, c in stats["by_source"].items():
            lines.append(f"- {src}: {c}")
        self.notifier.send_to_user(chat_id, "\n".join(lines))

    def cmd_help(self, chat_id: str, *_args: List[str]) -> None:
        lines = [
            "*Danh sách lệnh:*",
            "/filter - Xem tiêu chí hiện tại",
            "/set_price min max",
            "/set_area min max",
            "/set_beds n",
            "/set_district slug-quan",
            "/set_type slug-loai",
            "/add_keyword text",
            "/remove_keyword text",
            "/add_exclude text",
            "/remove_exclude text",
            "/reset - Reset filters",
            "/run - Chạy crawl ngay",
            "/pause - Tạm dừng scheduler",
            "/resume - Bật lại scheduler",
            "/stats - Thống kê",
            "/add_user - (admin) thêm user",
            "/remove_user chat_id - (admin) xóa user",
            "/users - (admin) liệt kê users",
        ]
        self.notifier.send_to_user(chat_id, "\n".join(lines))

    # === Admin-only ===

    def _require_admin(self, chat_id: str) -> bool:
        user = self.db.get_user(chat_id)
        if not user or not user.get("is_admin"):
            self.notifier.send_to_user(chat_id, "Bạn không có quyền admin.")
            return False
        return True

    def cmd_add_user(self, chat_id: str, *_args: List[str]) -> None:
        if not self._require_admin(chat_id):
            return
        self.notifier.send_to_user(
            chat_id,
            "Tính năng /add_user dạng deep link chưa implement đầy đủ. Tạm thời hãy thêm user trực tiếp trong DB.",
        )

    def cmd_remove_user(self, chat_id: str, args: List[str]) -> None:
        if not self._require_admin(chat_id):
            return
        if not args:
            self.notifier.send_to_user(chat_id, "Usage: /remove_user chat_id")
            return
        target = args[0]
        self.db.set_user_active(target, False)
        self.notifier.send_to_user(chat_id, f"Đã deactivate user {target}.")

    def cmd_users(self, chat_id: str, *_args: List[str]) -> None:
        if not self._require_admin(chat_id):
            return
        users = self.db.get_active_users()
        if not users:
            self.notifier.send_to_user(chat_id, "Chưa có user nào.")
            return
        lines = ["*Users hiện tại:*"]
        for u in users:
            lines.append(
                f"- {u['chat_id']} ({u.get('name') or ''}) admin={bool(u['is_admin'])}"
            )
        self.notifier.send_to_user(chat_id, "\n".join(lines))

    # === User mới ===

    def handle_start(self, chat_id: str, username: str, _args: str) -> None:
        user = self.db.get_user(chat_id)
        if user:
            self.notifier.send_to_user(chat_id, "Chào mừng quay lại!")
            return
        # Tạm thời: auto-approve user mới để đơn giản.
        self.db.add_user(chat_id, username, is_admin=False)
        self.notifier.send_to_user(
            chat_id,
            "Bạn đã được thêm làm user. Bắt đầu nhận tin khi có BĐS phù hợp.",
        )

    def handle_callback(self, callback_query: Dict[str, Any]) -> None:
        LOGGER.info("Callback query nhận được (chưa implement): %s", callback_query)

