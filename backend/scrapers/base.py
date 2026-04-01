from __future__ import annotations

import logging
import random
import time
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from urllib.parse import urlparse

import requests

from ..models import Listing

LOGGER = logging.getLogger(__name__)


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_2) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/16.3 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) "
    "Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 12.6; rv:121.0) "
    "Gecko/20100101 Firefox/121.0",
]


class BaseScraper(ABC):
    """Base class cho các scraper nguồn BĐS."""

    def __init__(self, config: Dict[str, object]):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(self._build_headers(""))

    @abstractmethod
    def build_search_url(self, filters: Dict[str, object], page: int = 1) -> str:
        """Xây URL tìm kiếm từ filters."""

    @abstractmethod
    def parse_listings(self, response_data: object) -> List[Listing]:
        """Parse HTML/JSON thành list Listing."""

    def scrape(self, filters: Dict[str, object]) -> List[Listing]:
        max_pages = int(self.config["scraper"]["max_pages"])
        results: List[Listing] = []
        for page in range(1, max_pages + 1):
            url = self.build_search_url(filters, page=page)
            LOGGER.info("[%s] Scraping trang %s: %s", self.__class__.__name__, page, url)
            text = self.fetch_page(url)
            if not text:
                LOGGER.info("[%s] Trang %s trả về rỗng, dừng.", self.__class__.__name__, page)
                break
            try:
                listings = self.parse_listings(text)
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("[%s] Lỗi parse trang %s: %s", self.__class__.__name__, page, exc)
                listings = []
            LOGGER.info("[%s] Trang %s: tìm thấy %s bản ghi", self.__class__.__name__, page, len(listings))
            if not listings:
                LOGGER.info("[%s] Không có listing ở trang %s, dừng.", self.__class__.__name__, page)
                break
            results.extend(listings)
            self._random_delay()
        LOGGER.info("[%s] Tổng cộng trước filter: %s bản ghi", self.__class__.__name__, len(results))
        return results

    def _random_delay(self) -> None:
        s_cfg = self.config["scraper"]
        delay = random.uniform(
            float(s_cfg["request_delay_min"]),
            float(s_cfg["request_delay_max"]),
        )
        time.sleep(delay)

    def fetch_page(self, url: str) -> Optional[str]:
        """GET với retry, backoff, xử lý 403/429."""
        s_cfg = self.config["scraper"]
        timeout = int(s_cfg["timeout"])
        max_retries = int(s_cfg["max_retries"])
        backoff = 2.0

        for attempt in range(1, max_retries + 1):
            try:
                self.session.headers.update(self._build_headers(url))
                resp = self.session.get(url, timeout=timeout)
                status = resp.status_code
                if status == 403:
                    self._warmup_session(url, timeout)
                    wait = random.uniform(10, 25)
                    LOGGER.warning("403 từ %s, đợi %.1fs rồi retry", url, wait)
                    time.sleep(wait)
                    continue
                if status == 429:
                    wait = 30
                    LOGGER.warning("429 từ %s, đợi %ss rồi retry", url, wait)
                    time.sleep(wait)
                    continue
                if not resp.ok:
                    LOGGER.warning("HTTP %s từ %s", status, url)
                    return None
                return resp.text
            except requests.Timeout:
                LOGGER.warning(
                    "Timeout khi fetch %s (attempt %s/%s)",
                    url,
                    attempt,
                    max_retries,
                )
            except requests.RequestException as exc:
                LOGGER.warning(
                    "Lỗi network khi fetch %s (attempt %s/%s): %s",
                    url,
                    attempt,
                    max_retries,
                    exc,
                )

            sleep_time = backoff**attempt
            time.sleep(sleep_time)

        LOGGER.error("Max retries exceeded cho %s", url)
        return None

    def _build_headers(self, url: str) -> Dict[str, str]:
        parsed = urlparse(url) if url else None
        referer = f"{parsed.scheme}://{parsed.netloc}/" if parsed and parsed.netloc else ""
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
            "image/webp,*/*;q=0.8",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Referer": referer,
        }

    def _warmup_session(self, url: str, timeout: int) -> None:
        """Thử gọi trang gốc để lấy cookie/session trước khi retry."""
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return
        home = f"{parsed.scheme}://{parsed.netloc}/"
        try:
            self.session.get(home, headers=self._build_headers(home), timeout=timeout)
            time.sleep(random.uniform(1.0, 2.5))
        except requests.RequestException:
            # Warmup chỉ là best effort, lỗi thì bỏ qua.
            return
