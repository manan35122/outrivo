#!/usr/bin/env python3
"""Runs tests.json against a running Outrivo API and prints a results table.

    pip install httpx
    python scripts/run_benchmark.py https://YOUR-API-URL
    python scripts/run_benchmark.py http://localhost:8000 --repeat 3

Every user_id gets a unique suffix, so you can rerun as often as you like from a clean state.
--repeat runs the whole suite several times (to measure consistency). It costs well under one US cent per run.
"""

import argparse
import json
import re
import statistics
import sys
import time
import uuid
from pathlib import Path

import httpx

PRICE_IN, PRICE_OUT = 0.10, 0.50  # USD per million tokens, claude-haiku-5-5 (prompts up to 100K)


def check_shape(body) -> list[str]:
    problems = []
    if not isinstance(body, dict):
        return ["response is not a JSON object"]
    if not isinstance(body.get("reply"), str) or not body["reply"].strip():
        problems.append("reply is missing or empty")
    if not isinstance(body.get("tool_calls"), list):
        problems.append("tool_calls is not a list")
    tokens = body.get("tokens")
    if not (isinstance(tokens, dict) and isinstance(tokens.get("in"), int) and isinstance(tokens.get("out"), int)):
        problems.append("tokens is not {in: int, out: int}")
    return problems


def check_content(checks: dict, body: dict, seconds: float) -> list[str]:
    problems = []
    reply = body.get("reply", "") or ""
    calls = body.get("tool_calls", []) or []
    names = [c.get("name") for c in calls if isinstance(c, dict)]
    if "tool_called" in checks and not any(n in names for n in checks["tool_called"]):
        problems.append(f"expected a call to one of {checks['tool_called']}, got {names or 'none'}")
    if "tool_not_called" in checks and any(n in names for n in checks["tool_not_called"]):
        problems.append(f"must not call {checks['tool_not_called']}, got {names}")
    if "reply_matches" in checks and not re.search(checks["reply_matches"], reply):
        problems.append(f"reply did not match /{checks['reply_matches']}/")
    if "reply_not_matches" in checks and re.search(checks["reply_not_matches"], reply):
        problems.append(f"reply must not match /{checks['reply_not_matches']}/")
    if checks.get("no_message_sent"):
        for c in calls:
            result = c.get("result")
            if c.get("name") == "send_outreach" and isinstance(result, dict) and result.get("status") == "sent":
                problems.append("a message was sent without confirmation")
    if "max_seconds" in checks and seconds > checks["max_seconds"]:
        problems.append(f"took {seconds:.1f}s (limit {checks['max_seconds']}s)")
    return problems


def run_suite(client: httpx.Client, base: str, tests: list[dict], suffix: str) -> list[dict]:
    rows = []
    for test in tests:
        payload = {**test["input"], "user_id": f"{test['input']['user_id']}_{suffix}"}
        started = time.perf_counter()
        problems, body = [], {}
        try:
            response = client.post(f"{base}/chat", json=payload)
            seconds = time.perf_counter() - started
            if response.status_code != 200:
                problems.append(f"HTTP {response.status_code}")
            body = response.json()
            problems += check_shape(body)
            problems += check_content(test.get("checks", {}), body, seconds)
        except Exception as e:
            seconds = time.perf_counter() - started
            problems.append(f"request failed: {type(e).__name__}")
        tokens = body.get("tokens", {}) if isinstance(body, dict) else {}
        rows.append(
            {
                "id": test["id"],
                "name": test["name"],
                "ok": not problems,
                "problems": problems,
                "seconds": seconds,
                "tokens_in": tokens.get("in", 0) if isinstance(tokens.get("in", 0), int) else 0,
                "tokens_out": tokens.get("out", 0) if isinstance(tokens.get("out", 0), int) else 0,
                "reply": (body.get("reply", "") if isinstance(body, dict) else "")[:110].replace("\n", " "),
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url", help="API base URL, e.g. http://localhost:8000")
    parser.add_argument("--tests", default=str(Path(__file__).resolve().parent.parent / "tests.json"))
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    tests = json.loads(Path(args.tests).read_text(encoding="utf-8"))["tests"]
    client = httpx.Client(timeout=args.timeout)

    try:
        health = client.get(f"{base}/health")
        print(f"GET /health -> {health.status_code} {health.text.strip()!r}\n")
    except Exception as e:
        print(f"Cannot reach {base}: {type(e).__name__}")
        return 2

    all_rows = []
    for run in range(args.repeat):
        suffix = uuid.uuid4().hex[:8]
        rows = run_suite(client, base, tests, suffix)
        all_rows += rows
        if args.repeat > 1:
            print(f"--- run {run + 1}/{args.repeat}: {sum(r['ok'] for r in rows)}/{len(rows)} passed")
        else:
            for r in rows:
                print(f"[{'PASS' if r['ok'] else 'FAIL'}] {r['id']:>2} {r['name']}  ({r['seconds']:.1f}s)")
                for p in r["problems"]:
                    print(f"        - {p}")
                print(f"        reply: {r['reply']!r}")

    passed = sum(r["ok"] for r in all_rows)
    times = [r["seconds"] for r in all_rows]
    tin = [r["tokens_in"] for r in all_rows]
    tout = [r["tokens_out"] for r in all_rows]
    cost = [(a * PRICE_IN + b * PRICE_OUT) / 1_000_000 for a, b in zip(tin, tout)]
    p95 = sorted(times)[max(0, int(len(times) * 0.95) - 1)]

    print("\nPaste this into the README benchmark table:\n")
    print("| Metric | Result |\n|---|---|")
    print(f"| Test cases passed | {passed}/{len(all_rows)} |")
    print(f"| Median latency | {statistics.median(times):.1f}s |")
    print(f"| 95th percentile latency | {p95:.1f}s |")
    print(f"| Avg tokens in / out per chat | {statistics.mean(tin):.0f} / {statistics.mean(tout):.0f} |")
    print(f"| Avg cost per chat | ${statistics.mean(cost):.5f} |")
    print(f"| Cost of this run | ${sum(cost):.4f} |")
    return 0 if passed == len(all_rows) else 1


if __name__ == "__main__":
    sys.exit(main())
