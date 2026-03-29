from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Dict, List

from .base import BaseScraper
from ..models import Listing

LOGGER = logging.getLogger(__name__)


class NhaTotScraper(BaseScraper):
    """Scraper sử dụng JSON API của nhatot.com."""

    API_URL = "https://gateway.chotot.com/v1/public/ad-listing"

    def build_search_url(self, filters: Dict[str, object], page: int = 1) -> str:  # type: ignore[override]
        # Không dùng URL trực tiếp, chỉ để log/debug.
        return self.API_URL

    def _build_params(self, filters: Dict[str, object], offset: int) -> Dict[str, object]:
        price_min = int(filters.get("price_min", 0)) * 1_000_000
        price_max = int(filters.get("price_max", 0)) * 1_000_000
        area_min = int(filters.get("area_min", 0))
        area_max = int(filters.get("area_max", 0))

        params: Dict[str, object] = {
            "cg": 1010,  # căn hộ
            "region_v2": 12000,  # Hà Nội
            "price_min": price_min,
            "price_max": price_max,
            "area_min": area_min,
            "area_max": area_max,
            "limit": 20,
            "o": offset,
            "st": "s,k",
            "w": 1,
        }
        return params

    def scrape(self, filters: Dict[str, object]) -> List[Listing]:  # type: ignore[override]
        """Override để gọi JSON API thay vì HTML."""
        s_cfg = self.config["scraper"]
        max_pages = int(s_cfg["max_pages"])
        results: List[Listing] = []
        for page in range(max_pages):
            offset = page * 20
            params = self._build_params(filters, offset)
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=int(s_cfg["timeout"]))
                if not resp.ok:
                    LOGGER.warning("NhaTot HTTP %s", resp.status_code)
                    break
                data = resp.json()
            except json.JSONDecodeError as exc:
                LOGGER.warning("Không parse được JSON từ NhaTot: %s", exc)
                break
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("Lỗi gọi API NhaTot: %s", exc)
                break

            listings = self.parse_listings(data)
            if not listings:
                break
            results.extend(listings)
            self._random_delay()
        return results

    def parse_listings(self, response_data: object) -> List[Listing]:  # type: ignore[override]
        ads = []
        if isinstance(response_data, dict):
            ads = response_data.get("ads") or []
        results: List[Listing] = []
        now = datetime.now(timezone.utc).isoformat()
        for ad in ads:
            try:
                title = ad.get("subject") or ""
                if not title:
                    continue
                price = ad.get("price")
                price_million = price / 1_000_000 if isinstance(price, (int, float)) else None
                area_m2 = ad.get("size")
                bedrooms = ad.get("rooms")
                location_parts = [ad.get("area_name"), ad.get("region_name")]
                location = ", ".join([p for p in location_parts if p])
                description = ad.get("body")
                url = f"https://www.nhatot.com/{ad.get('list_id')}.htm"
                thumbnail = ad.get("image")
                listing = Listing(
                    url=url,
                    title=title,
                    price_text=None,
                    price_million=price_million,
                    area_m2=area_m2,
                    bedrooms=bedrooms,
                    location=location or None,
                    description=description,
                    posted_date=None,
                    thumbnail_url=thumbnail,
                    source="nhatot.com",
                    scraped_at=now,
                )
                results.append(listing)
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("Lỗi parse 1 tin NhaTot: %s", exc)
        return results

