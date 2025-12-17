"""
flag_watcher.py – fetches the current flag for a given access token
and writes it to ./flag.txt every minute.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import requests

TOKEN = "bcdb3f85e9b80840dcbae34f6c849c86"
BASE_URL = "http://localhost:5000"


def fetch_flag(base_url: str, token: str, timeout: float = 10.0) -> str:
    url = f"{base_url.rstrip('/')}/service/flag/{token}"
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    return payload["flag"]


def compute_next_poll(interval: int, offset: float) -> float:
    interval = max(1, interval)
    offset = max(0.0, offset)
    now = time.time()
    next_tick = (int(now // interval) + 1) * interval + offset
    return next_tick


def main() -> int:
    parser = argparse.ArgumentParser(description="Keep flag.txt updated from the control plane.")
    parser.add_argument("--token", default=TOKEN, help="Flag access token (default: env constant)")
    parser.add_argument("--base-url", default=BASE_URL, help="Control plane base URL (default: http://localhost:5000)")
    parser.add_argument(
        "--output",
        default="flag.txt",
        help="File to write the flag into (default: ./flag.txt)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Polling interval in seconds (default: 60)",
    )
    parser.add_argument(
        "--offset",
        type=float,
        default=0.5,
        help="Extra seconds to wait after each server tick before polling (default: 0.5)",
    )
    args = parser.parse_args()

    output_path = Path(args.output).resolve()
    print(
        f"[flag_watcher] writing to {output_path}, polling every {args.interval}s "
        f"(offset {args.offset}s after server tick)"
    )

    next_poll = compute_next_poll(args.interval, args.offset)

    while True:
        delay = next_poll - time.time()
        if delay > 0:
            print(f"[flag_watcher] sleeping {delay:.2f}s to sync with server tick")
            time.sleep(delay)
        next_poll += args.interval
        try:
            print(f"[flag_watcher] fetching flag from {args.base_url}/service/flag/{args.token}")
            flag_value = fetch_flag(args.base_url, args.token)
            print(f"[flag_watcher] server responded with flag: {flag_value}")
            output_path.write_text(flag_value + "\n", encoding="utf-8")
            print(f"[flag_watcher] wrote flag to {output_path} at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        except Exception as exc:
            print(f"[flag_watcher] failed to update flag: {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
