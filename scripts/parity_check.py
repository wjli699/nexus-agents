#!/usr/bin/env python3
"""Parity check: Python stock backend vs the original n8n-only behaviour.

Sends the Milestone 1 test messages straight to /agents/stock/handle and
checks each reply. Assumes the watchlist is EMPTY at the start
(`--reset` will TRUNCATE it via docker compose).

    python scripts/parity_check.py --url http://localhost:8000
    python scripts/parity_check.py --reset          # from the repo root

Exit code is non-zero if any case fails.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.request

# (label, message, kind, expected)  — kind is "exact" or "regex"
CASES: list[tuple[str, str, str, str]] = [
    ("empty list",            "list",                     "exact", "Your watchlist is empty."),
    ("add AAPL",              "add AAPL",                  "exact", "Added AAPL to your watchlist."),
    ("add dup / lowercase",   "add aapl",                  "exact", "Added AAPL to your watchlist."),
    ("add TSLA",              "add TSLA",                  "exact", "Added TSLA to your watchlist."),
    ("list (two, sorted)",    "list",                      "exact", "Your watchlist:\nAAPL\nTSLA"),
    ("remove TSLA",           "remove TSLA",               "exact", "Removed TSLA from your watchlist."),
    ("remove TSLA again",     "remove TSLA",               "exact", "TSLA wasn't on your watchlist."),
    ("check AAPL (format)",   "check AAPL",                "regex", r"^AAPL: \$[0-9.]+ \(-?[0-9.]+%\)$"),
    ("check bad ticker",      "check ZZZZ",                "exact", "Couldn't find data for that ticker."),
    ("natural-language check", "what is NVDA trading at",   "regex", r"^NVDA: \$[0-9.]+ \(-?[0-9.]+%\)$"),
    # Deviation from n8n (documented): the old Switch defaulted unknown -> check
    # and then threw on a null ticker. The backend returns usage text instead.
    ("unknown -> usage text", "hello there",               "regex", r"check AAPL"),
]


def send(base_url: str, message: str) -> str:
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/agents/stock/handle",
        data=json.dumps({"message": message}).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.load(resp)["text"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--reset", action="store_true",
                    help="TRUNCATE watchlist via `docker compose exec postgres` first")
    args = ap.parse_args()

    if args.reset:
        subprocess.run(
            ["docker", "compose", "exec", "-T", "postgres",
             "psql", "-U", "nexus", "-d", "nexus", "-c", "TRUNCATE watchlist;"],
            cwd="docker", check=True,
        )
        print("watchlist reset\n")

    passed = failed = 0
    for label, message, kind, expected in CASES:
        try:
            got = send(args.url, message)
        except Exception as exc:  # noqa: BLE001 - report and keep going
            print(f"FAIL  {label}\n        sent:  {message!r}\n        error: {exc}")
            failed += 1
            continue

        ok = got == expected if kind == "exact" else re.search(expected, got) is not None
        if ok:
            print(f"PASS  {label}")
            passed += 1
        else:
            print(f"FAIL  {label}")
            print(f"        sent:     {message!r}")
            print(f"        expected ({kind}): {expected!r}")
            print(f"        got:      {got!r}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
