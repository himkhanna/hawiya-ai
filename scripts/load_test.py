"""Async load test against /v1/health (default) or any GET endpoint.

Phase 1 target (BUILD_PLAN week 4): 50 RPS sustained for 30 minutes
without errors. This script doesn't drive a 30-minute soak — that's a
human task — but it validates the throughput shape against a running
service.

Usage:
    make benchmark                            # quick 30s smoke
    python -m scripts.load_test --rps 50 --duration 60 \\
        --url http://localhost:8000/v1/health

For ``/v1/documents/extract`` we'd need a stub OCR mode in the API
process; that's deferred — this script focuses on plumbing throughput.
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time
from dataclasses import dataclass, field

import httpx


@dataclass
class Result:
    latencies_ms: list[float] = field(default_factory=list)
    statuses: dict[int, int] = field(default_factory=dict)
    errors: int = 0


async def _one_request(client: httpx.AsyncClient, url: str, result: Result) -> None:
    start = time.perf_counter()
    try:
        resp = await client.get(url, timeout=10.0)
    except httpx.HTTPError:
        result.errors += 1
        return
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    result.latencies_ms.append(elapsed_ms)
    result.statuses[resp.status_code] = result.statuses.get(resp.status_code, 0) + 1


async def _run(url: str, rps: int, duration_s: int, concurrency: int) -> Result:
    result = Result()
    async with httpx.AsyncClient() as client:
        end_time = time.monotonic() + duration_s
        interval = 1.0 / rps
        sem = asyncio.Semaphore(concurrency)
        tasks: list[asyncio.Task[None]] = []

        async def _job() -> None:
            async with sem:
                await _one_request(client, url, result)

        next_tick = time.monotonic()
        while time.monotonic() < end_time:
            tasks.append(asyncio.create_task(_job()))
            next_tick += interval
            sleep_for = next_tick - time.monotonic()
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)

        await asyncio.gather(*tasks, return_exceptions=True)
    return result


def _percentile(samples: list[float], p: float) -> float:
    if not samples:
        return float("nan")
    s = sorted(samples)
    k = max(0, min(len(s) - 1, round(p / 100.0 * (len(s) - 1))))
    return s[k]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8000/v1/health")
    parser.add_argument("--rps", type=int, default=50)
    parser.add_argument("--duration", type=int, default=30, help="seconds")
    parser.add_argument("--concurrency", type=int, default=100)
    args = parser.parse_args()

    print(f"Load test: {args.rps} RPS for {args.duration}s against {args.url}")
    result = asyncio.run(_run(args.url, args.rps, args.duration, args.concurrency))

    total = len(result.latencies_ms) + result.errors
    if total == 0:
        print("No requests issued.")
        sys.exit(2)

    if result.latencies_ms:
        p50 = _percentile(result.latencies_ms, 50)
        p95 = _percentile(result.latencies_ms, 95)
        p99 = _percentile(result.latencies_ms, 99)
        mean = statistics.fmean(result.latencies_ms)
    else:
        p50 = p95 = p99 = mean = float("nan")

    print()
    print(f"Total requests : {total}")
    print(f"Errors         : {result.errors}")
    print(f"Status counts  : {dict(sorted(result.statuses.items()))}")
    print(f"Latency mean   : {mean:>7.1f} ms")
    print(f"Latency p50    : {p50:>7.1f} ms")
    print(f"Latency p95    : {p95:>7.1f} ms")
    print(f"Latency p99    : {p99:>7.1f} ms")

    error_rate = result.errors / total
    print()
    print("PASS" if error_rate == 0 else f"FAIL — {error_rate:.2%} error rate")
    sys.exit(0 if error_rate == 0 else 1)


if __name__ == "__main__":
    main()
