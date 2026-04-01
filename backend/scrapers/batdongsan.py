from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Dict, List
from urllib.parse import urljoin

from .base import BaseScraper
from ..models import Listing

LOGGER = logging.getLogger(__name__)

# URL ổn định — không bị canonical redirect khi thay gtn/gcn/dtnn/dtln.
# Các param còn lại (vrs, tns, lgs, cIds) giữ cố định.
_SEARCH_BASE = "https://batdongsan.com.vn/ban-can-ho-chung-cu-ha-noi/2pn"
_FIXED_PARAMS = "vrs=1&tns=2&lgs=1&cIds=41,325,163,283"


class BatDongSanScraper(BaseScraper):
    BASE_URL = "https://batdongsan.com.vn"

    def build_search_url(self, filters: Dict[str, object], page: int = 1) -> str:  # type: ignore[override]
        price_min = int(filters.get("price_min") or 0)
        price_max = int(filters.get("price_max") or 0)
        area_min  = int(filters.get("area_min")  or 0)
        area_max  = int(filters.get("area_max")  or 0)

        path = _SEARCH_BASE if page <= 1 else f"{_SEARCH_BASE}/p{page}"

        variable: list[str] = []
        if price_min > 0:
            variable.append(f"gtn={self._price_to_slug(price_min)}")
        if price_max > 0:
            variable.append(f"gcn={self._price_to_slug(price_max)}")
        if area_min > 0:
            variable.append(f"dtnn={area_min}m2")
        if area_max > 0:
            variable.append(f"dtln={area_max}m2")

        qs = "&".join(variable + [_FIXED_PARAMS])
        return f"{path}?{qs}"

    def scrape(self, filters: Dict[str, object]) -> List[Listing]:  # type: ignore[override]
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            LOGGER.warning("[BatDongSanScraper] Playwright chưa cài, scraper bị skip.")
            return []

        max_pages = int(self.config["scraper"]["max_pages"])
        results: List[Listing] = []

        with sync_playwright() as p:
            # Mỗi trang dùng context riêng — tránh bị 403 khi chuyển trang
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
            )
            try:
                for page_num in range(1, max_pages + 1):
                    url = self.build_search_url(filters, page=page_num)
                    LOGGER.info("[BatDongSanScraper] Scraping trang %s: %s", page_num, url)
                    context = browser.new_context(
                        locale="vi-VN",
                        timezone_id="Asia/Ho_Chi_Minh",
                        viewport={"width": 1366, "height": 768},
                        user_agent=(
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
                        ),
                        extra_http_headers={
                            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
                        },
                    )
                    try:
                        page = context.new_page()
                        page.add_init_script(
                            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
                        )
                        status, final_url = self._goto_with_retry(page, url)
                        if status is None or status >= 400:
                            LOGGER.warning(
                                "[BatDongSanScraper] HTTP status=%s (final_url=%s), dừng.",
                                status,
                                final_url,
                            )
                            break
                        cards = self._extract_cards(page)
                        LOGGER.info(
                            "[BatDongSanScraper] Trang %s: tìm thấy %s bản ghi",
                            page_num,
                            len(cards),
                        )
                        if not cards:
                            break
                        results.extend(self.parse_listings(cards))
                    finally:
                        context.close()
                    self._random_delay()

                LOGGER.info(
                    "[BatDongSanScraper] Tổng cộng trước filter: %s bản ghi", len(results)
                )
            finally:
                browser.close()

        return results

    @staticmethod
    def _clean(text: str | None, max_len: int = 300) -> str | None:
        """Strip non-printable bytes and limit length. Returns None if empty."""
        if not text:
            return None
        cleaned = "".join(c for c in text if c.isprintable() or c in " \t").strip()
        result = cleaned[:max_len]
        return result or None

    @staticmethod
    def _clean_date(text: str | None) -> str | None:
        """Validate and clean a posted-date string.
        Real dates are short and contain at least one digit.
        Rejects binary-data artifacts that slip through _clean().
        """
        if not text:
            return None
        cleaned = "".join(c for c in text if c.isprintable() or c in " \t").strip()[:80]
        if not cleaned:
            return None
        # Must contain at least one digit (all valid date/time strings do)
        if not any(c.isdigit() for c in cleaned):
            return None
        return cleaned

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
                title = self._clean(row.get("title"), 300)
                if not title:
                    continue
                price_text = self._clean(row.get("price_text"), 100)
                area_text  = (row.get("area_text")   or "").strip()
                bed_text   = (row.get("bedrooms_text") or "").strip()
                raw_thumb  = (row.get("thumbnail_url") or "").strip()
                # Reject inline data URLs — Telegram can't use them
                thumbnail  = raw_thumb if raw_thumb and not raw_thumb.startswith("data:") else None
                results.append(Listing(
                    url=url,
                    title=title,
                    price_text=price_text,
                    price_million=self._parse_price(price_text or ""),
                    area_m2=self._parse_area(area_text),
                    bedrooms=self._parse_bedrooms(bed_text),
                    location=self._clean(row.get("location"), 200),
                    description=None,
                    posted_date=self._clean_date(row.get("posted_date")),
                    thumbnail_url=thumbnail,
                    source="batdongsan.com.vn",
                    scraped_at=now,
                ))
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("[BatDongSanScraper] Lỗi parse 1 card: %s", exc)
        return results

    # ------------------------------------------------------------------ helpers

    def _price_to_slug(self, price_million: int) -> str:
        if price_million >= 1000:
            return f"{price_million / 1000:g}-ty"
        return f"{price_million}-trieu"

    def _goto_with_retry(self, page, url: str) -> tuple[int | None, str | None]:
        for attempt in range(1, 4):
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(2500)
                if resp is None:
                    LOGGER.warning(
                        "[BatDongSanScraper] page.goto() trả về None (attempt %s/3), "
                        "page.url=%s — có thể bị JS redirect/challenge, thử lại.",
                        attempt,
                        page.url,
                    )
                    page.wait_for_timeout(3000)
                    continue
                if resp.status == 403:
                    LOGGER.warning(
                        "[BatDongSanScraper] HTTP 403 (attempt %s/3): %s", attempt, url
                    )
                    page.wait_for_timeout(3000)
                    continue
                return resp.status, page.url
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning(
                    "[BatDongSanScraper] Playwright goto lỗi (attempt %s/3) cho %s: %s",
                    attempt,
                    url,
                    exc,
                )
                page.wait_for_timeout(2000)
        return None, None

    def _extract_cards(self, page) -> List[dict]:
        try:
            return page.evaluate(
                """
                () => {
                  const cards = Array.from(document.querySelectorAll(
                    "div.js__card, div.re__card-full"
                  ));
                  return cards.map((card) => {
                    const link    = card.querySelector("a.js__product-link-for-product-id");
                    const titleEl = card.querySelector("h3.re__card-title") || card.querySelector("span.pr-title");
                    const price = card.querySelector("span.re__card-config-price");
                    const area  = card.querySelector("span.re__card-config-area");
                    const bed   = card.querySelector("span.re__card-config-bedroom");
                    const loc   = card.querySelector(".re__card-location");
                    const posted = card.querySelector(".re__card-published-info");
                    const img = card.querySelector("img");
                    return {
                      title:         titleEl ? (titleEl.textContent || "").trim() : "",
                      url:           link    ? (link.getAttribute("href") || "")  : "",
                      price_text:    price   ? (price.textContent  || "").trim()  : "",
                      area_text:     area    ? (area.textContent   || "").trim()  : "",
                      bedrooms_text: bed     ? (bed.textContent    || "").trim()  : "",
                      location:      loc     ? (loc.textContent    || "").trim()  : "",
                      posted_date:   (() => {
                        if (!posted) return "";
                        const t = (posted.textContent || "").trim().slice(0, 100);
                        // Only keep if it looks like a date (contains digit + time/date keyword)
                        return /\d/.test(t) && /(giờ|phút|ngày|tuần|tháng|năm|trước|nay|hôm)/i.test(t) ? t : "";
                      })(),
                      thumbnail_url: img     ? (img.getAttribute("data-src") || img.getAttribute("src") || "") : "",
                    };
                  }).filter((x) => x.url && x.title);
                }
                """
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("[BatDongSanScraper] Playwright extract lỗi: %s", exc)
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
