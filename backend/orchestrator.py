from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Dict, List, Set

from .database import Database
from .filters import FilterManager
from .models import Listing
from .notifier import TelegramNotifier
from .scrapers import AloNhaDatScraper, BatDongSanScraper, NhaTotScraper

LOGGER = logging.getLogger(__name__)


class ScraperOrchestrator:
    def __init__(
        self,
        config: Dict[str, object],
        db: Database,
        filter_manager: FilterManager,
        notifier: TelegramNotifier,
    ):
        self.config = config
        self.db = db
        self.filter_manager = filter_manager
        self.notifier = notifier
        self.scrapers = [
            BatDongSanScraper(config),
            NhaTotScraper(config),
            AloNhaDatScraper(config),
        ]

    def run(self) -> None:
        filters = self.filter_manager.get_all()
        if filters.get("is_paused"):
            LOGGER.info("Orchestrator đang ở trạng thái pause, bỏ qua vòng crawl.")
            return

        LOGGER.info("Bắt đầu crawl với filters: %s", filters)

        all_listings: List[Listing] = []
        errors = 0

        with ThreadPoolExecutor(max_workers=len(self.scrapers)) as executor:
            future_map = {
                executor.submit(scraper.scrape, filters): scraper
                for scraper in self.scrapers
            }
            for future in as_completed(future_map):
                scraper = future_map[future]
                try:
                    listings = future.result()
                    all_listings.extend(listings)
                    LOGGER.info(
                        "%s trả về %s listings",
                        scraper.__class__.__name__,
                        len(listings),
                    )
                except Exception as exc:  # noqa: BLE001
                    errors += 1
                    LOGGER.exception(
                        "Scraper %s lỗi: %s", scraper.__class__.__name__, exc
                    )

        deduped = self._deduplicate(all_listings)
        filtered = self._apply_filters(filters, deduped)

        now = datetime.now(timezone.utc).isoformat()
        new_listings = self.db.save_new_listings(filtered)

        sent_count = 0
        if new_listings:
            sent_count = self.notifier.send(new_listings)
            self.db.mark_notified([l.url for l in new_listings], now)

        LOGGER.info(
            "Tổng crawled: %s | Sau dedup: %s | Sau filter: %s | Mới (chưa lưu): %s | Đã gửi: %s | Lỗi scraper: %s",
            len(all_listings),
            len(deduped),
            len(filtered),
            len(new_listings),
            sent_count,
            errors,
        )

    def _deduplicate(self, listings: List[Listing]) -> List[Listing]:
        seen: Set[str] = set()
        result: List[Listing] = []
        for l in listings:
            url = l.url.strip()
            if url in seen:
                continue
            seen.add(url)
            result.append(l)
        return result

    def _apply_filters(self, filters: Dict[str, object], listings: List[Listing]) -> List[Listing]:
        price_min = float(filters.get("price_min") or 0)
        price_max = float(filters.get("price_max") or 0)
        area_min = float(filters.get("area_min") or 0)
        area_max = float(filters.get("area_max") or 0)
        bedrooms_min = int(filters.get("bedrooms_min") or 0)
        keywords = filters.get("keywords") or []
        exclude_keywords = filters.get("exclude_keywords") or []

        def match(l: Listing) -> bool:
            if l.price_million is not None:
                if price_min and l.price_million < price_min:
                    return False
                if price_max and l.price_million > price_max:
                    return False
            if l.area_m2 is not None:
                if area_min and l.area_m2 < area_min:
                    return False
                if area_max and l.area_m2 > area_max:
                    return False
            if l.bedrooms is not None and bedrooms_min:
                if l.bedrooms < bedrooms_min:
                    return False

            text = (l.description or "") + " " + (l.title or "")
            lower = text.lower()
            for kw in exclude_keywords:
                if kw and str(kw).lower() in lower:
                    return False
            if keywords:
                if not any(str(kw).lower() in lower for kw in keywords):
                    return False
            return True

        return [l for l in listings if match(l)]

