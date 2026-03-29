from __future__ import annotations

import argparse
import random
import sys
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

URL_BASE = "https://batdongsan.com.vn/ban-can-ho-chung-cu-ha-noi"
URL_FULL = (
    "https://batdongsan.com.vn/ban-can-ho-chung-cu-ha-noi/"
    "gia-tu-3-ty-den-5-ty-2pn?dtnn=50m2&dtln=75m2&vrs=1&tns=2&lgs=1"
)
ALONHADAT_URL = "https://alonhadat.com.vn/nha-dat/can-ban/can-ho-chung-cu/1/ha-noi.html"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_2) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/16.3 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) "
    "Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 12.6; rv:124.0) "
    "Gecko/20100101 Firefox/124.0",
]


@dataclass
class TestResult:
    name: str
    ok: bool
    status_code: Optional[int]
    cards: int
    note: str


def _headers(referer: str = "https://batdongsan.com.vn/") -> dict[str, str]:
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


def _count_cards(html: str) -> int:
    soup = BeautifulSoup(html, "html.parser")
    cards = (
        soup.select("div.js__card")
        or soup.select("div.re__card-full")
        or soup.select("div[class*='card']")
    )
    return len(cards)


def _count_alonhadat_cards(html: str) -> int:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("article")
    return len(cards)


def test_requests_strategy() -> TestResult:
    session = requests.Session()
    target_urls = [
        URL_FULL,
        f"{URL_BASE}?{urlencode({'gia-tu': 3000, 'gia-den': 5000, 'dt-tu': 60, 'dt-den': 100})}",
        URL_BASE,
    ]

    for i, url in enumerate(target_urls, start=1):
        try:
            # Warmup trang chủ để lấy cookie trước khi vào trang search.
            session.get("https://batdongsan.com.vn/", headers=_headers(), timeout=25)
            time.sleep(random.uniform(1.0, 2.5))
            resp = session.get(url, headers=_headers("https://batdongsan.com.vn/"), timeout=30)
            cards = _count_cards(resp.text) if resp.ok else 0
            if resp.ok and cards > 0:
                return TestResult(
                    name="requests+warmup+fallback",
                    ok=True,
                    status_code=resp.status_code,
                    cards=cards,
                    note=f"Thành công ở biến thể URL #{i}",
                )
            if resp.status_code == 403:
                time.sleep(random.uniform(8, 15))
        except Exception as exc:  # noqa: BLE001
            return TestResult(
                name="requests+warmup+fallback",
                ok=False,
                status_code=None,
                cards=0,
                note=f"Lỗi network/parse: {exc}",
            )

    return TestResult(
        name="requests+warmup+fallback",
        ok=False,
        status_code=403,
        cards=0,
        note="Tất cả URL biến thể đều không lấy được cards",
    )


def test_playwright_strategy() -> TestResult:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001
        return TestResult(
            name="playwright",
            ok=False,
            status_code=None,
            cards=0,
            note=f"Chưa cài playwright: {exc}",
        )

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(locale="vi-VN", user_agent=random.choice(USER_AGENTS))
            page = context.new_page()
            response = page.goto(URL_FULL, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(3000)
            html = page.content()
            cards = _count_cards(html)
            status = response.status if response else None
            browser.close()
            ok = bool(status and status < 400 and cards > 0)
            note = "Render thành công" if ok else "Không lấy được cards hoặc status không hợp lệ"
            return TestResult(
                name="playwright",
                ok=ok,
                status_code=status,
                cards=cards,
                note=note,
            )
    except Exception as exc:  # noqa: BLE001
        return TestResult(
            name="playwright",
            ok=False,
            status_code=None,
            cards=0,
            note=f"Lỗi khi chạy browser: {exc}",
        )


def test_batdongsan_url_patterns() -> TestResult:
    """Bruteforce vài pattern URL để tìm dạng không redirect."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001
        return TestResult(
            name="batdongsan-patterns",
            ok=False,
            status_code=None,
            cards=0,
            note=f"Chưa cài playwright: {exc}",
        )

    urls = [
        "https://batdongsan.com.vn/ban-can-ho-chung-cu-ha-noi/gia-tu-3-ty-den-5-ty-2pn?dtnn=50m2&dtln=75m2&vrs=1&tns=2&lgs=1",
        "https://batdongsan.com.vn/ban-can-ho-chung-cu-ha-noi/gia-tu-3-ty-den-5-ty-2pn?dtnn=50m2&dtln=70m2&vrs=1&tns=2&lgs=1",
        "https://batdongsan.com.vn/ban-can-ho-chung-cu-ha-noi/gia-tu-3-ty-den-5-ty-2pn?dtnn=50m2&dtln=100m2&vrs=1&tns=2&lgs=1",
        "https://batdongsan.com.vn/ban-can-ho-chung-cu-ha-noi?vrs=1&tns=2&lgs=1&gtn=3-ty&gcn=5-ty",
        "https://batdongsan.com.vn/ban-can-ho-chung-cu-ha-noi?gtn=3-ty&gcn=5-ty&lgs=1",
        "https://batdongsan.com.vn/ban-can-ho-chung-cu-ha-noi?lgs=1",
        "https://batdongsan.com.vn/ban-can-ho-chung-cu-ha-noi",
    ]

    details: list[str] = []
    best_cards = 0
    best_note = "Không có pattern hợp lệ"
    best_status: Optional[int] = None
    ok = False

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(locale="vi-VN", user_agent=random.choice(USER_AGENTS))
        page = context.new_page()
        for u in urls:
            try:
                resp = page.goto(u, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(2500)
                final_url = page.url
                status = resp.status if resp else None
                html = page.content()
                cards = _count_cards(html)
                redirected_home = "/nha-dat-ban" in final_url
                details.append(
                    f"url={u} status={status} cards={cards} final={final_url} redirected_home={redirected_home}"
                )
                if status and status < 400 and not redirected_home and cards > best_cards:
                    best_cards = cards
                    best_status = status
                    best_note = f"Best URL: {u}"
                    ok = True
            except Exception as exc:  # noqa: BLE001
                details.append(f"url={u} error={exc}")
        browser.close()

    print("=== BATDONGSAN URL PATTERN DETAILS ===")
    for d in details:
        print(d)

    return TestResult(
        name="batdongsan-patterns",
        ok=ok,
        status_code=best_status,
        cards=best_cards,
        note=best_note,
    )


def test_alonhadat_strategy() -> TestResult:
    try:
        resp = requests.get(
            ALONHADAT_URL,
            headers=_headers("https://alonhadat.com.vn/"),
            timeout=30,
        )
        cards = _count_alonhadat_cards(resp.text) if resp.ok else 0
        return TestResult(
            name="alonhadat-requests",
            ok=bool(resp.ok and cards > 0),
            status_code=resp.status_code,
            cards=cards,
            note="OK" if resp.ok and cards > 0 else "Không tìm thấy card article",
        )
    except Exception as exc:  # noqa: BLE001
        return TestResult(
            name="alonhadat-requests",
            ok=False,
            status_code=None,
            cards=0,
            note=f"Lỗi khi gọi AloNhaDat: {exc}",
        )


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--only",
        choices=["requests", "playwright", "alonhadat", "all"],
        default="all",
    )
    args = parser.parse_args()

    results: list[TestResult] = []
    if args.only in ("requests", "all"):
        results.append(test_requests_strategy())
    if args.only in ("playwright", "all"):
        results.append(test_playwright_strategy())
    if args.only in ("alonhadat", "all"):
        results.append(test_alonhadat_strategy())
    if args.only == "all":
        results.append(test_batdongsan_url_patterns())

    print("=== SOURCE ACCESS TEST ===")
    for r in results:
        print(
            f"[{r.name}] ok={r.ok} status={r.status_code} cards={r.cards} note={r.note}"
        )

    any_ok = any(r.ok for r in results)
    print(f"RESULT={'PASS' if any_ok else 'FAIL'}")


if __name__ == "__main__":
    main()
