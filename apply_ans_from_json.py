#!/usr/bin/env python3
"""
Apply MCQ answers from a JSON file by clicking options in Chrome (CDP).

Expected JSON: a list of { "number": <question 1..N>, "option": <1..5> }.
Example: ans.json

Requires: Chrome with remote debugging on port 9222 (or --launch-chrome),
          pip install playwright

  python apply_ans_from_json.py --answers ans.json

Use only if the site and your institution allow automation.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_OTHER = ROOT / "other"
if str(_OTHER) not in sys.path:
    sys.path.insert(0, str(_OTHER))

from export_div_mocktest import (  # noqa: E402
    CDP_URL,
    DEFAULT_CHROME,
    DEFAULT_USER_DATA,
    _cdp_connection_refused,
    build_chrome_command,
    iter_normal_pages,
    launch_chrome,
)


def load_answers(path: Path) -> list[dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Root must be a JSON array")
    out: list[dict] = []
    for i, row in enumerate(raw):
        if not isinstance(row, dict):
            raise ValueError(f"Row {i}: expected object")
        n = row.get("number")
        o = row.get("option")
        if o is None and "answer_option_number" in row:
            o = row["answer_option_number"]
        if not isinstance(n, int) or not isinstance(o, int):
            raise ValueError(f"Row {i}: need integer number and option")
        if n < 1 or o < 1:
            raise ValueError(f"Row {i}: number and option must be >= 1")
        out.append({"number": n, "option": o})
    out.sort(key=lambda r: r["number"])
    return out


def get_visible_question_number(page) -> int | None:
    """Prefer #div_mocktest only; if several blocks look visible during transitions, use the lowest qn."""
    return page.evaluate(
        """() => {
            const root = document.querySelector("#div_mocktest");
            const scope = root || document;
            const nodes = scope.querySelectorAll('[id^="div_qn_"]');
            const visible = [];
            for (const el of nodes) {
                const st = window.getComputedStyle(el);
                if (st.display === "none") continue;
                const r = el.getBoundingClientRect();
                if (r.width < 2 && r.height < 2) continue;
                const m = /^div_qn_(\\d+)$/.exec(el.id);
                if (m) visible.push(parseInt(m[1], 10));
            }
            if (visible.length === 0) return null;
            return Math.min(...visible);
        }"""
    )


def wait_until_visible_is(
    page,
    target: int,
    timeout_sec: float,
    poll_sec: float = 0.08,
    consecutive_hits: int = 3,
) -> None:
    """Poll until we see `target` as the visible question several times in a row (post-NEXT / load)."""
    deadline = time.monotonic() + timeout_sec
    hits = 0
    last_seen: int | None = None
    while time.monotonic() < deadline:
        cur = get_visible_question_number(page)
        if cur == target:
            hits += 1
            if hits >= consecutive_hits:
                return
        else:
            hits = 0
        last_seen = cur
        time.sleep(poll_sec)
    raise TimeoutError(
        f"Timed out waiting for question {target} to show (last visible was {last_seen!r}, "
        f"after {timeout_sec}s). Try --after-option-ms / --after-next-ms or a slower --delay-ms."
    )


def wait_for_option_strip_ready(page, qn: int, timeout_ms: float) -> None:
    """Ensure the MCQ strip for this question is actually visible before clicking."""
    page.locator(f"#div_qn_{qn} .strip_single_course").first.wait_for(
        state="visible", timeout=timeout_ms
    )


def find_mock_page(browser, url_contains: str | None):
    for page in iter_normal_pages(browser):
        if url_contains and url_contains not in (page.url or ""):
            continue
        try:
            if page.query_selector("#div_mocktest"):
                return page
        except Exception:
            continue
    return None


def click_next(page, css_override: str | None, timeout_ms: float) -> None:
    if css_override:
        page.locator(css_override).first.click(timeout=timeout_ms)
        return
    tried = False
    for role in ("link", "button"):
        loc = page.get_by_role(role, name=re.compile(r"next", re.I))
        try:
            if loc.count() > 0:
                loc.first.click(timeout=timeout_ms)
                tried = True
                break
        except Exception:
            continue
    if tried:
        return
    for sel in (
        "a:has-text('NEXT')",
        "button:has-text('NEXT')",
        '[onclick*="next"]',
        '[onclick*="Next"]',
        "#lnkNext",
        ".lnkNext",
    ):
        loc = page.locator(sel)
        try:
            if loc.count() > 0:
                loc.first.click(timeout=timeout_ms)
                return
        except Exception:
            continue
    raise RuntimeError(
        "Could not find a NEXT control. Open the mock test tab, or pass "
        "--next-selector with a CSS selector that matches your site's NEXT button."
    )


def sync_to_question(
    page,
    qn: int,
    css_next: str | None,
    timeout_ms: float,
    max_steps: int,
    nav_timeout_sec: float,
) -> None:
    for _ in range(max_steps):
        cur = get_visible_question_number(page)
        if cur == qn:
            wait_until_visible_is(page, qn, timeout_sec=nav_timeout_sec)
            return
        if cur is None:
            time.sleep(0.05)
            continue
        if cur > qn:
            raise RuntimeError(
                f"Visible question is {cur} but need {qn}. Cannot go backward; "
                "restart the test or align the tab to the first row in your JSON."
            )
        prev = cur
        click_next(page, css_next, timeout_ms)
        # Wait until the page actually leaves the previous question (avoid stacked NEXTs).
        t0 = time.monotonic()
        while time.monotonic() - t0 < nav_timeout_sec:
            nxt = get_visible_question_number(page)
            if nxt is not None and nxt != prev:
                break
            time.sleep(0.05)
        else:
            raise TimeoutError(f"No navigation after NEXT while syncing to Q{qn} (stuck on {prev})")
    raise TimeoutError(f"Timed out syncing to question {qn}")


def click_option(page, qn: int, opt_1based: int, timeout_ms: float) -> None:
    strip = page.locator(f"#div_qn_{qn} .strip_single_course")
    uls = strip.locator("ul")
    n = uls.count()
    if n == 0:
        raise RuntimeError(f"Q{qn}: no options found under .strip_single_course")
    if opt_1based < 1 or opt_1based > n:
        raise RuntimeError(f"Q{qn}: option {opt_1based} invalid (this question has {n} options)")
    row = uls.nth(opt_1based - 1)
    radio = row.locator("input[type='radio']").first
    try:
        radio.click(timeout=timeout_ms)
    except Exception:
        row.locator(".clsChoice").first.click(timeout=timeout_ms)


def connect_browser(args, p):
    if args.launch_chrome:
        chrome = Path(args.chrome)
        if not chrome.is_file():
            print(f"Chrome not found: {chrome}", file=sys.stderr)
            sys.exit(1)
        launch_chrome(build_chrome_command(chrome, Path(args.user_data_dir)))
        browser = None
        last_err: BaseException | None = None
        for _ in range(max(1, args.connect_retries)):
            time.sleep(args.connect_delay)
            try:
                browser = p.chromium.connect_over_cdp(args.cdp_url)
                break
            except Exception as e:
                last_err = e
        if browser is None:
            print(f"Could not attach to Chrome CDP: {last_err}", file=sys.stderr)
            sys.exit(1)
        return browser

    time.sleep(max(0.0, args.start_wait))
    browser = None
    last_err: BaseException | None = None
    auto_launched = False
    for attempt in range(max(1, args.connect_retries)):
        if attempt > 0:
            time.sleep(args.connect_delay)
        try:
            browser = p.chromium.connect_over_cdp(args.cdp_url)
            break
        except Exception as e:
            last_err = e
            if (
                not auto_launched
                and _cdp_connection_refused(e)
                and Path(args.chrome).is_file()
            ):
                print("No Chrome on CDP port — starting Chrome with debugging…", flush=True)
                launch_chrome(
                    build_chrome_command(Path(args.chrome), Path(args.user_data_dir))
                )
                auto_launched = True
                time.sleep(max(2.0, args.connect_delay))
    if browser is None:
        print(f"Could not attach to Chrome CDP: {last_err}", file=sys.stderr)
        sys.exit(1)
    return browser


def main() -> None:
    ap = argparse.ArgumentParser(description="Click answers from JSON on the mock test page.")
    ap.add_argument("--answers", type=Path, default=ROOT / "ans.json", help="Path to answers JSON")
    ap.add_argument(
        "--launch-chrome",
        action="store_true",
        help="Start Chrome with CDP 9222 (default: attach to existing Chrome)",
    )
    ap.add_argument("--cdp-url", default=CDP_URL)
    ap.add_argument("--chrome", type=Path, default=Path(DEFAULT_CHROME))
    ap.add_argument("--user-data-dir", type=Path, default=Path(DEFAULT_USER_DATA))
    ap.add_argument("--connect-retries", type=int, default=15)
    ap.add_argument("--connect-delay", type=float, default=1.0)
    ap.add_argument("--start-wait", type=float, default=3.0)
    ap.add_argument("--url-contains", default=None)
    ap.add_argument(
        "--next-selector",
        default=None,
        help="CSS selector for the NEXT control if auto-detection fails",
    )
    ap.add_argument("--timeout", type=float, default=8.0, help="Per-action timeout (seconds)")
    ap.add_argument(
        "--delay-ms",
        type=float,
        default=80.0,
        help="Extra pause after settle waits (ms). Higher = safer on slow pages.",
    )
    ap.add_argument(
        "--after-option-ms",
        type=float,
        default=120.0,
        help="Wait after selecting an option before clicking NEXT (lets the site save the answer).",
    )
    ap.add_argument(
        "--after-next-ms",
        type=float,
        default=80.0,
        help="Extra wait after NEXT, before we poll for the following question.",
    )
    ap.add_argument(
        "--nav-timeout",
        type=float,
        default=25.0,
        help="Max seconds to wait for the next question to appear after NEXT",
    )
    ap.add_argument("--dry-run", action="store_true", help="Print actions only, no clicks")
    ap.add_argument("--limit", type=int, default=None, metavar="N", help="Apply only first N rows")
    args = ap.parse_args()

    timeout_ms = max(500.0, args.timeout * 1000.0)

    if not args.answers.is_file():
        print(f"Not found: {args.answers}", file=sys.stderr)
        sys.exit(1)

    rows = load_answers(args.answers)
    if args.limit is not None:
        rows = rows[: max(0, args.limit)]

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Missing playwright. Run: pip install playwright", file=sys.stderr)
        sys.exit(1)

    with sync_playwright() as p:
        browser = connect_browser(args, p)
        try:
            page = find_mock_page(browser, args.url_contains)
            if page is None:
                print(
                    "No tab with #div_mocktest found. Open the test in Chrome "
                    "or use --url-contains.",
                    file=sys.stderr,
                )
                sys.exit(1)

            page.bring_to_front()
            v0 = get_visible_question_number(page)
            if v0 is None:
                print("Could not detect a visible question (#div_qn_*).", file=sys.stderr)
                sys.exit(1)
            if v0 != rows[0]["number"]:
                print(
                    f"Visible question is {v0} but JSON starts at {rows[0]['number']}. "
                    f"Syncing forward…",
                    flush=True,
                )

            nav_to = args.nav_timeout
            after_opt = args.after_option_ms / 1000.0
            after_next = args.after_next_ms / 1000.0
            d = args.delay_ms / 1000.0

            for i, row in enumerate(rows):
                qn = row["number"]
                opt = row["option"]
                if args.dry_run:
                    print(f"[dry-run] sync Q{qn}, click option {opt}", flush=True)
                else:
                    sync_to_question(
                        page,
                        qn,
                        args.next_selector,
                        timeout_ms,
                        max_steps=500,
                        nav_timeout_sec=nav_to,
                    )
                    wait_for_option_strip_ready(page, qn, timeout_ms)
                    click_option(page, qn, opt, timeout_ms)
                    if after_opt > 0:
                        time.sleep(after_opt)
                    print(f"Q{qn}: option {opt}", flush=True)
                if d > 0:
                    time.sleep(d)
                last = i == len(rows) - 1
                if not last:
                    next_qn = rows[i + 1]["number"]
                    if args.dry_run:
                        print(f"[dry-run] NEXT (expect Q{next_qn})", flush=True)
                    else:
                        click_next(page, args.next_selector, timeout_ms)
                        if after_next > 0:
                            time.sleep(after_next)
                        wait_until_visible_is(
                            page,
                            next_qn,
                            timeout_sec=nav_to,
                            poll_sec=0.08,
                            consecutive_hits=3,
                        )
                    if d > 0:
                        time.sleep(d)

            print("\nDone.\n", flush=True)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
