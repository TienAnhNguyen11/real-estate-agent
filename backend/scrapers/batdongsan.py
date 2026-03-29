from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Dict, List
from urllib.parse import urlencode, urljoin

from .base import BaseScraper
from ..models import Listing

LOGGER = logging.getLogger(__name__)

class BatDongSanScraper(BaseScraper):
    BASE_URL = "https://batdongsan.com.vn"

    def build_search_url(self, filters: Dict[str, object], page: int = 1) -> str:  # type: ignore[override]
        property_type = str(filters.get("property_type") or "ban-can-ho-chung-cu")
        location = str(filters.get("location") or "ha-noi")

        slug = f"{property_type}-{location}"
        path = f"{self.BASE_URL}/{slug}/2pn"
        area_min = int(filters.get("area_min") or 0)
        area_max = int(filters.get("area_max") or 0)
        price_min = int(filters.get("price_min") or 0)
        price_max = int(filters.get("price_max") or 0)

        if page > 1:
            path += f"/p{page}"

        # Dùng dtnn/dtln theo URL bạn cung cấp.
        params: Dict[str, object] = {
            "gtn": self._price_to_slug(price_min) if price_min > 0 else None,
            "gcn": self._price_to_slug(price_max) if price_max > 0 else None,
            "dtnn": f"{area_min}m2" if area_min > 0 else None,
            "dtln": f"{area_max}m2" if area_max > 0 else None,
            "vrs": 1,
            "lgs": 1,
        }
        params = {k: v for k, v in params.items() if v is not None}

        return f"{path}?{urlencode(params)}"

    def parse_listings(self, response_data: object) -> List[Listing]:  # type: ignore[override]
        if not isinstance(response_data, list):
            return []

        results: List[Listing] = []
        now = datetime.now(timezone.utc).isoformat()
        for row in response_data:
            try:
                if not isinstance(row, dict):
                    continue
                raw_url = (row.get("url") or "").strip()
                if not raw_url:
                    continue
                url = urljoin(f"{self.BASE_URL}/", raw_url)
                title = (row.get("title") or "").strip()
                if not title:
                    continue
                price_text = (row.get("price_text") or "").strip() or None
                area_text = (row.get("area_text") or "").strip()
                bed_text = (row.get("bedrooms_text") or "").strip()
                listing = Listing(
                    url=url,
                    title=title,
                    price_text=price_text,
                    price_million=self._parse_price(price_text or ""),
                    area_m2=self._parse_area(area_text),
                    bedrooms=self._parse_bedrooms(bed_text),
                    location=(row.get("location") or "").strip() or None,
                    description=(row.get("description") or "").strip() or None,
                    posted_date=(row.get("posted_date") or "").strip() or None,
                    thumbnail_url=(row.get("thumbnail_url") or "").strip() or None,
                    source="batdongsan.com.vn",
                    scraped_at=now,
                )
                results.append(listing)
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("Lỗi parse 1 card BatDongSan: %s", exc)
        return results

    def scrape(self, filters: Dict[str, object]) -> List[Listing]:  # type: ignore[override]
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            LOGGER.warning("Playwright chưa cài; BatDongSan scraper bị skip.")
            return []

        max_pages = int(self.config["scraper"]["max_pages"])
        results: List[Listing] = []

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
            )
            context = browser.new_context(
                locale="vi-VN",
                timezone_id="Asia/Ho_Chi_Minh",
                viewport={"width": 1366, "height": 768},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
                ),
            )
            page = context.new_page()
            page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )
            page.goto(f"{self.BASE_URL}/", wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(1200)

            for page_num in range(1, max_pages + 1):
                candidate_urls = self._build_candidate_urls(filters, page=page_num)
                used = False
                for url in candidate_urls:
                    status, final_url = self._goto_with_retry(page, url)
                    if status is None or status >= 400:
                        LOGGER.warning("Playwright status=%s cho %s", status, url)
                        continue
                    if "/nha-dat-ban" in (final_url or ""):
                        LOGGER.warning(
                            "BatDongSan redirect về trang tổng, bỏ URL: %s -> %s",
                            url,
                            final_url,
                        )
                        continue
                    cards = self._extract_cards(page)
                    if not cards:
                        continue
                    parsed = self.parse_listings(cards)
                    results.extend(parsed)
                    used = True
                    break
                if not used:
                    break
                self._random_delay()

            context.close()
            browser.close()

        return results

    def _build_candidate_urls(self, filters: Dict[str, object], page: int = 1) -> List[str]:
        """Phiên bản đơn giản: URL chính + 1 fallback dtln rounded."""
        exact = self.build_search_url(filters, page=page)
        relaxed_filters = dict(filters)
        area_max = int(filters.get("area_max") or 0)
        if area_max > 0:
            relaxed_filters["area_max"] = ((area_max + 9) // 10) * 10
        relaxed = self.build_search_url(relaxed_filters, page=page)
        urls = [exact, relaxed]
        unique_urls: List[str] = []
        for u in urls:
            if u not in unique_urls:
                unique_urls.append(u)
        return unique_urls

    def _price_to_slug(self, price_million: int) -> str:
        if price_million >= 1000:
            return f"{price_million / 1000:g}-ty"
        return f"{price_million}-trieu"

    def _goto_with_retry(self, page, url: str) -> tuple[int | None, str | None]:
        for _ in range(3):
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(2500)
                status = resp.status if resp else None
                if status == 403:
                    page.wait_for_timeout(3000)
                    continue
                return status, page.url
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("Playwright goto lỗi cho %s: %s", url, exc)
                page.wait_for_timeout(2000)
        return None, None

    def _extract_cards(self, page) -> List[dict]:
        try:
            return page.evaluate(
                """
                () => {
                  const pick = (root, selectors) => {
                    for (const s of selectors) {
                      const el = root.querySelector(s);
                      if (el) return el;
                    }
                    return null;
                  };
                  const cards = Array.from(document.querySelectorAll(
                    "div.js__card, div.re__card-full, div[class*='card']"
                  ));
                  return cards.map((card) => {
                    const a = pick(card, [".js__card-title a", "a.js__card-title", "h3 a", "a[href*='/ban-']"]);
                    const price = pick(card, [".re__card-config-price", "span[class*='price']"]);
                    const area = pick(card, [".re__card-config-area", "span[class*='area']"]);
                    const bed = pick(card, [".re__card-config-bedroom", "[class*='bedroom']"]);
                    const loc = pick(card, [".re__card-location", "[class*='location']"]);
                    const desc = pick(card, ["p", "div.content"]);
                    const posted = pick(card, [".re__card-published-info", "[class*='publish']", "[class*='date']"]);
                    const img = card.querySelector("img");
                    return {
                      title: a ? (a.textContent || "").trim() : "",
                      url: a ? (a.getAttribute("href") || "") : "",
                      price_text: price ? (price.textContent || "").trim() : "",
                      area_text: area ? (area.textContent || "").trim() : "",
                      bedrooms_text: bed ? (bed.textContent || "").trim() : "",
                      location: loc ? (loc.textContent || "").trim() : "",
                      description: desc ? (desc.textContent || "").trim() : "",
                      posted_date: posted ? (posted.textContent || "").trim() : "",
                      thumbnail_url: img ? (img.getAttribute("data-src") || img.getAttribute("src") || "") : "",
                    };
                  }).filter((x) => x.url && x.title);
                }
                """
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Playwright extract lỗi: %s", exc)
            return []

    def _parse_price(self, text: str) -> float | None:
        if "/m" in text:
            return None
        t = text.lower().replace(",", ".")
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

