from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from ..models import Listing


class BaseNotifier(ABC):
    """Interface chung cho các notifier (Telegram, email, ...)."""

    @abstractmethod
    def send(self, listings: List[Listing]) -> int:
        """Gửi danh sách listings tới các subscriber. Trả về số tin gửi thành công."""

