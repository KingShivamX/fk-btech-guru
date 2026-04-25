#!/usr/bin/env python3
"""
Launch Chrome with remote debugging (optional), attach via CDP, and save
the outer HTML of #div_mocktest to a file.

Waits until the element exists (e.g. after you log in and start the test),
polling all normal tabs on an interval.

Can also parse an exported HTML file into structured JSON (questions + options).

Install:
  pip install playwright beautifulsoup4
(No need for "playwright install" when only connecting to existing Chrome.)

Example:
  python other/export_div_mocktest.py
  python other/export_div_mocktest.py --no-launch
  python other/export_div_mocktest.py --from-html output/div_mocktest.html --limit 6
  (JSON is a list of {number, question, options: [{number, option}, ...]}.)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

_OTHER = Path(__file__).resolve().parent
PROJECT_ROOT = _OTHER.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
_DEFAULT_EXPORT_HTML = OUTPUT_DIR / "div_mocktest.html"
_DEFAULT_QUESTIONS_JSON = OUTPUT_DIR / "questions.json"

QN_DIV_ID = re.compile(r"^div_qn_(\d+)$")


def _strip_question_label(text: str, qnum: int) -> str:
    """Remove leading '53 :' / '53 :\\n' style prefix from scraped h3 text."""
    t = (text or "").strip()
    t = re.sub(rf"^{qnum}\s*:\s*\n?", "", t, count=1)
    return t.strip()

DEFAULT_CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DEFAULT_USER_DATA = r"C:\selenium\ChromeProfile"
CDP_URL = "http://127.0.0.1:9222"
DEFAULT_SELECTOR = "#div_mocktest"


def build_chrome_command(chrome_exe: Path, user_data_dir: Path) -> list[str]:
    return [
        str(chrome_exe),
        "--remote-debugging-port=9222",
        f"--user-data-dir={user_data_dir}",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--disable-features=CalculateNativeWinOcclusion",
    ]


def launch_chrome(cmd: list[str]) -> subprocess.Popen:
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )


def _cdp_connection_refused(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "econnrefused" in msg or "10061" in msg or "connection refused" in msg


def iter_normal_pages(browser):
    for context in browser.contexts:
        for page in context.pages:
            url = page.url or ""
            if url.startswith("devtools:") or url.startswith("chrome-extension:"):
                continue
            yield page


def poll_selector_and_export(
    browser,
    output: Path,
    selector: str,
    deadline: float,
    poll_interval: float,
    url_substring: str | None,
    require_visible: bool,
    status_every: float,
) -> None:
    last_status = 0.0
    while time.monotonic() < deadline:
        for page in iter_normal_pages(browser):
            if url_substring and url_substring not in (page.url or ""):
                continue
            try:
                handle = page.query_selector(selector)
            except Exception:
                continue
            if handle is None:
                continue
            if require_visible:
                try:
                    if not handle.is_visible():
                        continue
                except Exception:
                    continue
            html = handle.evaluate("el => el.outerHTML")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(html, encoding="utf-8")
            return

        now = time.monotonic()
        if now - last_status >= status_every:
            remaining = max(0, int(deadline - now))
            print(
                f"Waiting for {selector!r} ({remaining}s left). "
                "Log in and start the test in Chrome…",
                flush=True,
            )
            last_status = now
        time.sleep(poll_interval)

    raise TimeoutError(
        f"Timed out waiting for {selector!r}. "
        "Open the test page in a tab (or adjust --url-contains / timeout)."
    )


def parse_mocktest_html_to_json(html_path: Path, limit: int | None) -> list[dict]:
    """Parse #div_mocktest export → list of {number, question, options: [{number, option}]}."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print(
            "Missing beautifulsoup4. Run: pip install beautifulsoup4",
            file=sys.stderr,
        )
        sys.exit(1)

    raw = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(raw, "html.parser")
    root = soup.find(id="div_mocktest")
    if root is None:
        root = soup

    blocks = []
    for div in root.find_all("div", id=True):
        mid = div.get("id") or ""
        m = QN_DIV_ID.match(mid)
        if m:
            blocks.append((int(m.group(1)), div))

    blocks.sort(key=lambda x: x[0])
    if limit is not None and limit > 0:
        blocks = blocks[:limit]

    questions: list[dict] = []
    for num, div in blocks:
        h3 = div.select_one("h3.chapter_course")
        raw_q = h3.get_text(separator="\n", strip=True) if h3 else ""
        question = _strip_question_label(raw_q, num)

        opts: list[dict] = []
        strip = div.find("div", class_="strip_single_course")
        if strip:
            for ul in strip.find_all("ul"):
                inp = ul.find("input", attrs={"type": "radio"})
                choice = ul.find("div", class_="clsChoice")
                if inp is None and choice is None:
                    continue
                opt_text = (
                    choice.get_text(separator=" ", strip=True) if choice else ""
                )
                opts.append({"number": len(opts) + 1, "option": opt_text})

        questions.append(
            {
                "number": num,
                "question": question,
                "options": opts,
            }
        )

    return questions


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export #div_mocktest from Chrome (remote debugging), after it appears."
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=_DEFAULT_EXPORT_HTML,
        help=f"Output HTML (default: {_DEFAULT_EXPORT_HTML})",
    )
    parser.add_argument(
        "--selector",
        default=DEFAULT_SELECTOR,
        help=f"CSS selector to export (default: {DEFAULT_SELECTOR})",
    )
    parser.add_argument(
        "--chrome",
        type=Path,
        default=Path(DEFAULT_CHROME),
        help="Path to chrome.exe",
    )
    parser.add_argument(
        "--user-data-dir",
        type=Path,
        default=Path(DEFAULT_USER_DATA),
        help="Chrome user data directory",
    )
    parser.add_argument(
        "--no-launch",
        action="store_true",
        help="Do not start Chrome; attach to an already running instance on port 9222",
    )
    parser.add_argument(
        "--cdp-url",
        default=CDP_URL,
        help=f"CDP HTTP endpoint (default: {CDP_URL})",
    )
    parser.add_argument(
        "--start-wait",
        type=float,
        default=3.0,
        help="Seconds to wait before first CDP attach when using --no-launch (default: 3)",
    )
    parser.add_argument(
        "--connect-retries",
        type=int,
        default=15,
        help="Attempts to connect to CDP when launching Chrome (default: 15)",
    )
    parser.add_argument(
        "--connect-delay",
        type=float,
        default=1.0,
        help="Seconds between connect retries (default: 1)",
    )
    parser.add_argument(
        "--selector-timeout",
        type=float,
        default=3600.0,
        help="Max seconds to wait for the element after CDP is up (default: 3600 = 1 hour)",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="Seconds between checks across tabs (default: 2)",
    )
    parser.add_argument(
        "--status-every",
        type=float,
        default=30.0,
        help="Print waiting message at most this often in seconds (default: 30)",
    )
    parser.add_argument(
        "--url-contains",
        default=None,
        help="Only consider tabs whose URL contains this substring (optional)",
    )
    parser.add_argument(
        "--require-visible",
        action="store_true",
        help="Require the element to be visible, not only in the DOM",
    )
    parser.add_argument(
        "--from-html",
        type=Path,
        metavar="FILE",
        help="Parse exported mocktest HTML to JSON and exit (no browser)",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=_DEFAULT_QUESTIONS_JSON,
        help=f"Output JSON when using --from-html (default: {_DEFAULT_QUESTIONS_JSON})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="With --from-html: only include the first N questions by number (e.g. 6)",
    )
    args = parser.parse_args()

    if args.from_html is not None:
        if not args.from_html.is_file():
            print(f"Not found: {args.from_html}", file=sys.stderr)
            sys.exit(1)
        data = parse_mocktest_html_to_json(args.from_html, args.limit)
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"Wrote {args.json_out.resolve()} ({len(data)} questions)")
        return

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Missing dependency. Run: pip install playwright", file=sys.stderr)
        sys.exit(1)

    deadline = time.monotonic() + max(1.0, args.selector_timeout)

    with sync_playwright() as p:
        if not args.no_launch:
            if not args.chrome.is_file():
                print(f"Chrome not found: {args.chrome}", file=sys.stderr)
                sys.exit(1)
            launch_chrome(build_chrome_command(args.chrome, args.user_data_dir))
            browser = None
            last_err: Exception | None = None
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
        else:
            time.sleep(max(0.0, args.start_wait))
            browser = None
            last_err: Exception | None = None
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
                        and args.chrome.is_file()
                    ):
                        print(
                            "No Chrome on CDP port — starting Chrome with debugging…",
                            flush=True,
                        )
                        launch_chrome(
                            build_chrome_command(args.chrome, args.user_data_dir)
                        )
                        auto_launched = True
                        time.sleep(max(2.0, args.connect_delay))
            if browser is None:
                print(f"Could not attach to Chrome CDP: {last_err}", file=sys.stderr)
                sys.exit(1)

        try:
            print(
                f"Connected. Waiting up to {int(args.selector_timeout)}s for "
                f"{args.selector!r}…",
                flush=True,
            )
            poll_selector_and_export(
                browser,
                args.output,
                args.selector,
                deadline,
                args.poll_interval,
                args.url_contains,
                args.require_visible,
                args.status_every,
            )
            print(f"Wrote {args.output.resolve()}")
        except TimeoutError as e:
            print(e, file=sys.stderr)
            sys.exit(1)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
