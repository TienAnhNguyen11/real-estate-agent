from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(slots=True)
class Listing:
    """Đại diện 1 tin đăng BĐS đã được chuẩn hóa."""

    url: str
    title: str
    price_text: Optional[str] = None
    price_million: Optional[float] = None
    area_m2: Optional[float] = None
    bedrooms: Optional[int] = None
    location: Optional[str] = None
    description: Optional[str] = None
    posted_date: Optional[str] = None
    thumbnail_url: Optional[str] = None
    source: str | None = None
    scraped_at: str | None = None
