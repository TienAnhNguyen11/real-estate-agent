from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Dict, List

from bs4 import BeautifulSoup

from .base import BaseScraper
from ..models import Listing

LOGGER = logging.getLogger(__name__)


class AloNhaDatScraper(BaseScraper):
    BASE_URL = "https://alonhadat.com.vn"

    def build_search_url(self, filters: Dict[str, object], page: int = 1) -> str:  # type: ignore[override]
        path = "nha-dat/can-ban/can-ho-chung-cu/1/ha-noi.html"
        if page > 1:
            return f"{self.BASE_URL}/{path.replace('.html', f'/trang-{page}.html')}"
        return f"{self.BASE_URL}/{path}"

    def parse_listings(self, response_data: object) -> List[Listing]:  # type: ignore[override]
        html = str(response_data)
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("article")
        results: List[Listing] = []
        now = datetime.now(timezone.utc).isoformat()

        for card in cards:
            try:
                title_el = card.select_one("h3.property-title a, a.link")
                if not title_el or not title_el.get("href"):
                    continue
                title = title_el.get_text(strip=True)
                url = title_el["href"]
                if url.startswith("/"):
                    url = f"{self.BASE_URL}{url}"

                price_el = card.select_one("span.price")
                price_text = price_el.get_text(strip=True) if price_el else None
                price_million = self._parse_price(price_text) if price_text else None

                area_el = card.select_one("span.area")
                area_text = area_el.get_text(strip=True) if area_el else ""
                area_m2 = self._parse_area(area_text)

                location_el = card.select_one("p.new-address, .property-address")
                location = location_el.get_text(strip=True) if location_el else None

                desc_el = card.select_one("p.brief")
                description = desc_el.get_text(strip=True) if desc_el else None

                bed_el = card.select_one("span.bedroom")
                bedrooms = self._parse_bedrooms(bed_el.get_text(strip=True) if bed_el else "")

                listing = Listing(
                    url=url,
                    title=title,
                    price_text=price_text,
                    price_million=price_million,
                    area_m2=area_m2,
                    bedrooms=bedrooms,
                    location=location,
                    description=description,
                    posted_date=None,
                    thumbnail_url=None,
                    source="alonhadat.com.vn",
                    scraped_at=now,
                )
                results.append(listing)
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("Lỗi parse 1 card AloNhaDat: %s", exc)
        return results

    def _parse_price(self, text: str) -> float | None:
        t = text.lower().replace(",", ".")
        if "/m" in t:
            return None
        m = re.search(r"([\d\.]+)\s*tỷ", t)
        if m:
            return float(m.group(1)) * 1000
        m = re.search(r"([\d\.]+)\s*triệu", t)
        if m:
            return float(m.group(1))
        return None

    def _parse_area(self, text: str) -> float | None:
        m = re.search(r"([\d\.]+)\s*m", text.replace(",", "."))
        if not m:
            return None
        try:
            return float(m.group(1))
        except ValueError:
            return None

    def _parse_bedrooms(self, text: str) -> int | None:
        m = re.search(r"(\d+)", text)
        if not m:
            return None
        try:
            return int(m.group(1))
        except ValueError:
            return None

