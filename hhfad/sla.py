#!/usr/bin/env python3
"""Lightweight SLA checker that verifies core endpoints are reachable."""

import sys
from urllib.parse import urljoin

import requests

PORT = 8001
TIMEOUT = 5


def check_health(base: str) -> None:
    resp = requests.get(urljoin(base, "/health"), timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError("health endpoint did not return ok=true")


def check_designer(base: str) -> None:
    resp = requests.get(urljoin(base, "/designer"), timeout=TIMEOUT)
    resp.raise_for_status()
    if "Preview Studio" not in resp.text:
        raise RuntimeError("designer page missing expected marker text")


def check_logs(base: str) -> None:
    resp = requests.get(urljoin(base, "/logs"), params={"name": "designer.log"}, timeout=TIMEOUT)
    resp.raise_for_status()
    if "[boot] welcome to the helper log" not in resp.text:
        raise RuntimeError("log endpoint did not return baseline content")


def main() -> int:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <ip-address>", file=sys.stderr)
        return 1

    ip = sys.argv[1].strip()
    base = f"http://{ip}:{PORT}"

    try:
        print(f"[*] Checking {base} ...")
        check_health(base)
        check_designer(base)
        check_logs(base)
    except (requests.RequestException, RuntimeError, ValueError) as exc:
        print(f"[-] SLA failed: {exc}", file=sys.stderr)
        return 1

    print("[+] SLA OK (core endpoints reachable)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
