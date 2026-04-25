#!/usr/bin/env python3
"""
Scrape #div_mocktest from Chrome -> output/div_mocktest.html, then parse it
into output/questions.json.

Usage:
  python mocktest_pipeline.py
  python mocktest_pipeline.py --launch-chrome
  python mocktest_pipeline.py --skip-export    # parse existing HTML only
  python mocktest_pipeline.py --skip-parse     # export HTML only

Requires: Chrome on :9222 (or --launch-chrome), pip install playwright beautifulsoup4
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OTHER = ROOT / "other"
OUT = ROOT / "output"


def run_phase(name: str, script: str, argv: list[str]) -> None:
    script_path = OTHER / script
    if not script_path.is_file():
        print(f"Missing script: {script_path}", file=sys.stderr)
        sys.exit(1)
    cmd = [sys.executable, str(script_path)] + argv
    print(f"\n{'=' * 60}\n  {name}\n  {' '.join(cmd)}\n{'=' * 60}\n", flush=True)
    r = subprocess.run(cmd, cwd=ROOT)
    if r.returncode != 0:
        print(f"\nStopped: {name} exited with {r.returncode}", file=sys.stderr)
        sys.exit(r.returncode)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Export #div_mocktest from Chrome and parse it into questions.json."
    )
    ap.add_argument(
        "--launch-chrome",
        action="store_true",
        help="Start Chrome with CDP; default attaches to existing :9222",
    )
    ap.add_argument("--html", type=Path, default=OUT / "div_mocktest.html")
    ap.add_argument("--questions", type=Path, default=OUT / "questions.json")
    ap.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Parse only the first N questions (by order in HTML)",
    )
    ap.add_argument(
        "--selector-timeout",
        type=float,
        default=3600.0,
        help="Seconds to wait for #div_mocktest in export",
    )
    ap.add_argument("--skip-export", action="store_true")
    ap.add_argument("--skip-parse", action="store_true")
    ap.add_argument("--url-contains", default=None)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    export_attach_only = not args.launch_chrome

    if not args.skip_export:
        ex = ["-o", str(args.html), "--selector-timeout", str(args.selector_timeout)]
        if export_attach_only:
            ex.append("--no-launch")
        if args.url_contains:
            ex.extend(["--url-contains", args.url_contains])
        run_phase("1 - Export #div_mocktest", "export_div_mocktest.py", ex)
    elif not args.html.is_file():
        print(f"Missing {args.html}", file=sys.stderr)
        sys.exit(1)

    if not args.skip_parse:
        pr = ["--from-html", str(args.html), "--json-out", str(args.questions)]
        if args.limit is not None:
            pr.extend(["--limit", str(args.limit)])
        run_phase("2 - Parse questions.json", "export_div_mocktest.py", pr)
    elif not args.questions.is_file():
        print(f"Missing {args.questions}", file=sys.stderr)
        sys.exit(1)

    print("\nDone.\n", flush=True)


if __name__ == "__main__":
    main()
