"""
Tìm cách bypass 403 trên batdongsan.com.vn bằng Playwright — bao gồm pagination.
Chạy: python -m backend.test
"""
from __future__ import annotations

import sys
import time

TARGET_URL = (
    "https://batdongsan.com.vn/ban-can-ho-chung-cu-ha-noi/2pn"
    "?gtn=3-ty&gcn=6-ty&dtnn=60m2&dtln=100m2&vrs=1&tns=2&lgs=1&cIds=41,325,163,283"
)
WARMUP_URL  = "https://batdongsan.com.vn/ban-can-ho-chung-cu-ha-noi/2pn?vrs=1&tns=2&lgs=1&cIds=41,325,163,283"
BASE_URL    = "https://batdongsan.com.vn"

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver',  {get: () => undefined});
Object.defineProperty(navigator, 'languages',  {get: () => ['vi-VN','vi','en-US','en']});
Object.defineProperty(navigator, 'plugins',    {get: () => [1,2,3,4,5]});
window.chrome = {runtime: {}};
"""

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)

LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-dev-shm-usage",
    "--lang=vi-VN",
]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def nav(page, label: str, url: str, wait_ms: int = 2500) -> tuple[int | None, str]:
    """Navigate và in kết quả. Trả về (status, final_url)."""
    try:
        resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(wait_ms)
        status   = resp.status if resp else None
        final    = page.url
        cards    = _count_cards(page)
        print(f"  [{label}] status={status}  cards={cards}  url={final[:90]}")
        return status, final
    except Exception as exc:
        print(f"  [{label}] EXCEPTION: {exc}")
        return None, ""


def _count_cards(page) -> int:
    try:
        return page.evaluate("""
            () => (
                document.querySelectorAll('div.js__card, div.re__card-full').length
                || document.querySelectorAll("div[class*='card']").length
            )
        """)
    except Exception:
        return -1


def new_ctx(p, headless: bool = True, extra_headers: dict | None = None):
    browser = p.chromium.launch(headless=headless, args=LAUNCH_ARGS)
    ctx = browser.new_context(
        locale="vi-VN",
        timezone_id="Asia/Ho_Chi_Minh",
        viewport={"width": 1366, "height": 768},
        user_agent=USER_AGENT,
        extra_http_headers={
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            **(extra_headers or {}),
        },
    )
    pg = ctx.new_page()
    pg.add_init_script(STEALTH_JS)
    return browser, ctx, pg


def is_pass(status: int | None, page) -> bool:
    if not status or status >= 400:
        return False
    cards = _count_cards(page)
    return isinstance(cards, int) and cards > 0


# ---------------------------------------------------------------------------
# attempts
# ---------------------------------------------------------------------------

def attempt_1(p):
    """homepage → warmup (no filter) → target."""
    print("\n=== #1: homepage → warmup → target ===")
    browser, ctx, pg = new_ctx(p)
    try:
        nav(pg, "homepage", BASE_URL, 1500)
        nav(pg, "warmup",   WARMUP_URL, 2500)
        status, _ = nav(pg, "target", TARGET_URL, 3000)
        return is_pass(status, pg)
    finally:
        ctx.close(); browser.close()


def attempt_2(p):
    """homepage → target (bỏ warmup)."""
    print("\n=== #2: homepage → target (bỏ warmup) ===")
    browser, ctx, pg = new_ctx(p)
    try:
        nav(pg, "homepage", BASE_URL, 2500)
        status, _ = nav(pg, "target", TARGET_URL, 3000)
        return is_pass(status, pg)
    finally:
        ctx.close(); browser.close()


def attempt_3(p):
    """homepage + mouse move/scroll → warmup → target."""
    print("\n=== #3: homepage + mouse interaction → warmup → target ===")
    browser, ctx, pg = new_ctx(p)
    try:
        nav(pg, "homepage", BASE_URL, 1000)
        for x, y in [(300, 400), (600, 300), (900, 500), (400, 600)]:
            pg.mouse.move(x, y)
            pg.wait_for_timeout(250)
        pg.evaluate("window.scrollBy(0, 400)")
        pg.wait_for_timeout(600)
        pg.evaluate("window.scrollBy(0, -150)")
        pg.wait_for_timeout(500)
        nav(pg, "warmup",   WARMUP_URL, 2500)
        pg.evaluate("window.scrollBy(0, 300)")
        pg.wait_for_timeout(800)
        status, _ = nav(pg, "target", TARGET_URL, 3000)
        return is_pass(status, pg)
    finally:
        ctx.close(); browser.close()


def attempt_4(p):
    """Cold start thẳng target (không warmup gì cả)."""
    print("\n=== #4: cold start → target ===")
    browser, ctx, pg = new_ctx(p)
    try:
        status, _ = nav(pg, "target", TARGET_URL, 3000)
        return is_pass(status, pg)
    finally:
        ctx.close(); browser.close()


def attempt_5(p):
    """Headed (không headless) — xem có qua được không."""
    print("\n=== #5: headed browser → homepage → warmup → target ===")
    browser, ctx, pg = new_ctx(p, headless=False)
    try:
        nav(pg, "homepage", BASE_URL, 1500)
        nav(pg, "warmup",   WARMUP_URL, 2500)
        status, _ = nav(pg, "target", TARGET_URL, 3000)
        return is_pass(status, pg)
    finally:
        ctx.close(); browser.close()


def attempt_6(p):
    """Thử playwright-stealth nếu đã cài."""
    print("\n=== #6: playwright-stealth (nếu có) → homepage → target ===")
    try:
        from playwright_stealth import stealth_sync  # type: ignore
    except ImportError:
        print("  [skip] playwright-stealth chưa cài (pip install playwright-stealth)")
        return False
    browser, ctx, pg = new_ctx(p)
    try:
        stealth_sync(pg)
        nav(pg, "homepage", BASE_URL, 1500)
        nav(pg, "warmup",   WARMUP_URL, 2500)
        status, _ = nav(pg, "target", TARGET_URL, 3000)
        return is_pass(status, pg)
    finally:
        ctx.close(); browser.close()


def attempt_7(p):
    """homepage → đợi lâu hơn (5s) → warmup → đợi lâu hơn (5s) → target."""
    print("\n=== #7: long waits (5s each) ===")
    browser, ctx, pg = new_ctx(p)
    try:
        nav(pg, "homepage", BASE_URL, 5000)
        nav(pg, "warmup",   WARMUP_URL, 5000)
        status, _ = nav(pg, "target", TARGET_URL, 5000)
        return is_pass(status, pg)
    finally:
        ctx.close(); browser.close()


def attempt_8(p):
    """Thêm Referer header trỏ về warmup URL."""
    print("\n=== #8: Referer header = warmup URL ===")
    browser, ctx, pg = new_ctx(p, extra_headers={"Referer": WARMUP_URL})
    try:
        nav(pg, "homepage", BASE_URL, 1500)
        nav(pg, "warmup",   WARMUP_URL, 2500)
        pg.set_extra_http_headers({"Referer": WARMUP_URL})
        status, _ = nav(pg, "target", TARGET_URL, 3000)
        return is_pass(status, pg)
    finally:
        ctx.close(); browser.close()


# ---------------------------------------------------------------------------
# Pagination tests — chạy sau khi tìm được approach cho p1
# ---------------------------------------------------------------------------

TARGET_P2 = (
    "https://batdongsan.com.vn/ban-can-ho-chung-cu-ha-noi/2pn/p2"
    "?gtn=3-ty&gcn=6-ty&dtnn=60m2&dtln=100m2&vrs=1&tns=2&lgs=1&cIds=41,325,163,283"
)


def pagination_test_1(p):
    """p1 cold start → p2 same context (delay 3s)."""
    print("\n=== PAGINATION #1: cold start p1 → p2 same ctx, delay 3s ===")
    browser, ctx, pg = new_ctx(p)
    try:
        s1, _ = nav(pg, "p1", TARGET_URL, 3000)
        if not is_pass(s1, pg):
            print("  p1 fail — bỏ qua")
            return False
        s2, _ = nav(pg, "p2", TARGET_P2, 3000)
        return is_pass(s2, pg)
    finally:
        ctx.close(); browser.close()


def pagination_test_2(p):
    """p1 cold start → p2 NEW context trong cùng browser."""
    print("\n=== PAGINATION #2: cold start p1 → new ctx p2 (same browser) ===")
    browser = p.chromium.launch(headless=True, args=LAUNCH_ARGS)
    try:
        def make_page():
            ctx = browser.new_context(
                locale="vi-VN", timezone_id="Asia/Ho_Chi_Minh",
                viewport={"width": 1366, "height": 768},
                user_agent=USER_AGENT,
                extra_http_headers={"Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7"},
            )
            pg = ctx.new_page()
            pg.add_init_script(STEALTH_JS)
            return ctx, pg

        ctx1, pg1 = make_page()
        s1, _ = nav(pg1, "p1", TARGET_URL, 3000)
        p1_ok = is_pass(s1, pg1)  # check TRƯỚC khi close
        ctx1.close()
        if not p1_ok:
            print("  p1 fail — bỏ qua")
            return False

        time.sleep(2)
        ctx2, pg2 = make_page()
        s2, _ = nav(pg2, "p2", TARGET_P2, 3000)
        ok = is_pass(s2, pg2)
        ctx2.close()
        return ok
    finally:
        browser.close()


def pagination_test_5(p):
    """p1 và p2 mỗi trang dùng BROWSER hoàn toàn mới."""
    print("\n=== PAGINATION #5: new browser cho mỗi trang ===")
    def scrape_page(url: str, label: str) -> tuple[int | None, bool]:
        browser = p.chromium.launch(headless=True, args=LAUNCH_ARGS)
        try:
            ctx = browser.new_context(
                locale="vi-VN", timezone_id="Asia/Ho_Chi_Minh",
                viewport={"width": 1366, "height": 768},
                user_agent=USER_AGENT,
                extra_http_headers={"Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7"},
            )
            pg = ctx.new_page()
            pg.add_init_script(STEALTH_JS)
            status, _ = nav(pg, label, url, 3000)
            ok = is_pass(status, pg)
            ctx.close()
            return status, ok
        finally:
            browser.close()

    _, p1_ok = scrape_page(TARGET_URL, "p1")
    if not p1_ok:
        print("  p1 fail — bỏ qua")
        return False
    time.sleep(2)
    _, p2_ok = scrape_page(TARGET_P2, "p2")
    return p2_ok


def pagination_test_3(p):
    """p1 cold start → navigate about:blank → p2 same context."""
    print("\n=== PAGINATION #3: p1 → about:blank → p2 same ctx ===")
    browser, ctx, pg = new_ctx(p)
    try:
        s1, _ = nav(pg, "p1", TARGET_URL, 3000)
        if not is_pass(s1, pg):
            print("  p1 fail — bỏ qua")
            return False
        pg.goto("about:blank")
        pg.wait_for_timeout(1500)
        s2, _ = nav(pg, "p2", TARGET_P2, 3000)
        return is_pass(s2, pg)
    finally:
        ctx.close(); browser.close()


def pagination_test_4(p):
    """p1 cold start → delay dài 8s → p2 same context."""
    print("\n=== PAGINATION #4: p1 → delay 8s → p2 same ctx ===")
    browser, ctx, pg = new_ctx(p)
    try:
        s1, _ = nav(pg, "p1", TARGET_URL, 3000)
        if not is_pass(s1, pg):
            print("  p1 fail — bỏ qua")
            return False
        pg.wait_for_timeout(8000)
        s2, _ = nav(pg, "p2", TARGET_P2, 3000)
        return is_pass(s2, pg)
    finally:
        ctx.close(); browser.close()


# ---------------------------------------------------------------------------

def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    from playwright.sync_api import sync_playwright

    p1_attempts = [
        attempt_1, attempt_2, attempt_3, attempt_4,
        attempt_5, attempt_6, attempt_7, attempt_8,
    ]
    pagination_attempts = [
        pagination_test_1, pagination_test_2,
        pagination_test_3, pagination_test_4,
    ]
    passed = None

    with sync_playwright() as p:
        # Bước 1: tìm approach cho p1
        for fn in p1_attempts:
            try:
                ok = fn(p)
            except Exception as exc:
                print(f"  [FATAL] {fn.__name__}: {exc}")
                ok = False
            print(f"  -> {'PASS ✓' if ok else 'FAIL ✗'}")
            if ok:
                passed = fn.__name__
                break
            time.sleep(2)

        if not passed:
            print("\n>>> Tất cả p1 attempt đều fail.")
            return

        print(f"\n>>> P1 passed: {passed}")
        print("\n--- Bắt đầu test pagination ---")

        pagination_attempts.append(pagination_test_5)

        # Bước 2: tìm approach cho pagination
        for fn in pagination_attempts:
            try:
                ok = fn(p)
            except Exception as exc:
                print(f"  [FATAL] {fn.__name__}: {exc}")
                ok = False
            print(f"  -> {'PASS ✓' if ok else 'FAIL ✗'}")
            if ok:
                print(f"\n>>> PAGINATION passed: {fn.__name__}")
                break
            time.sleep(2)
        else:
            print("\n>>> Tất cả pagination approach đều fail.")

    print()
    if passed:
        print(f">>> PASSED: {passed} — apply approach này vào batdongsan.py")
    else:
        print(">>> Tất cả attempt đều fail — Cloudflare chặn headless, cần hướng khác.")
        print("    Gợi ý: pip install playwright-stealth  rồi chạy lại.")


if __name__ == "__main__":
    main()
