"""Latency measurement CLI for TalentRank's `/match` and `/retrieve` endpoints.
See .claude/enhancements/08.

Fires real HTTP requests against a running API, reports p50/p95/p99 for a batch of
uncached (distinct-text) requests plus a separate cached-repeat-query measurement,
and prints a markdown row ready to paste into `measured-facts.md`.

Defaults to `http://127.0.0.1:8000`, not `http://localhost:8000`: on this project's
Windows dev machine, resolving `localhost` attempted an IPv6 connection first and
fell back to IPv4 only after a multi-second delay, silently inflating every
measurement by roughly two seconds versus the server's own reported `took_ms`. Using
the literal loopback address skips that resolution step entirely. See
`.claude/reference/engineering-challenges.md`.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import time
import urllib.error
import urllib.request
import uuid

import numpy as np

_BASE_RESUME_TEXT = (
    "Latency measurement resume: backend engineer with experience in Python, "
    "machine learning services, and semantic search, padded to satisfy the API's "
    "minimum resume length requirement for this synthetic benchmarking request."
)

# A fresh nonce per process run. Without this, "uncached variant {i}" text is
# deterministic across separate invocations of this script against the same
# long-lived server, so a second run can silently hit the *first* run's cache
# entries -- measured directly: a second run reusing an overlapping index range
# reported a p50 an order of magnitude too low, with the underlying response
# already carrying `cached: true`. See enhancements/08 and engineering-challenges.md.
_RUN_NONCE = uuid.uuid4().hex[:12]


def _fire(url: str, endpoint: str, resume_text: str, top_k: int, top_n: int) -> tuple[float, bool]:
    """Send one request; return (wall_clock_ms, cached)."""

    body = json.dumps({"resume_text": resume_text, "top_k": top_k, "top_n": top_n}).encode("utf-8")
    request = urllib.request.Request(f"{url}{endpoint}", data=body, headers={"Content-Type": "application/json"})
    start = time.perf_counter()
    with urllib.request.urlopen(request) as response:
        payload = json.loads(response.read())
    elapsed_ms = (time.perf_counter() - start) * 1000
    return elapsed_ms, bool(payload.get("cached", False))


def _percentiles(values: list[float]) -> dict[str, float]:
    if not values:
        return {"p50": float("nan"), "p95": float("nan"), "p99": float("nan")}
    array = np.asarray(values)
    return {
        "p50": float(np.percentile(array, 50)),
        "p95": float(np.percentile(array, 95)),
        "p99": float(np.percentile(array, 99)),
    }


def measure(args: argparse.Namespace) -> None:
    url = args.url.rstrip("/")
    endpoint = f"/{args.endpoint}"

    print(f"Warm-up request to {url}{endpoint} (excluded from the sample) ...")
    try:
        _fire(url, endpoint, f"{_BASE_RESUME_TEXT} warmup", args.top_k, args.top_n)
    except urllib.error.URLError as exc:
        print(f"Could not reach {url}{endpoint}: {exc}")
        return

    def _uncached_call(i: int) -> float:
        text = f"{_BASE_RESUME_TEXT} uncached variant {_RUN_NONCE}-{i}"
        elapsed_ms, cached = _fire(url, endpoint, text, args.top_k, args.top_n)
        if cached:
            # Should be unreachable given the per-run nonce; if it isn't, the
            # "uncached" p50/p95/p99 below are not trustworthy -- fail loud rather
            # than silently report a contaminated number.
            raise RuntimeError(
                f"Expected an uncached response for variant {i} but got cached=True. "
                "The 'uncached' latency figures below would be invalid; aborting."
            )
        return elapsed_ms

    print(f"Firing {args.requests} uncached requests (concurrency={args.concurrency}) ...")
    if args.concurrency > 1:
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            uncached_ms = list(pool.map(_uncached_call, range(args.requests)))
    else:
        uncached_ms = [_uncached_call(i) for i in range(args.requests)]

    print("Measuring a cached repeat query (same resume text sent twice) ...")
    repeat_text = f"{_BASE_RESUME_TEXT} cached repeat query {_RUN_NONCE}"
    first_ms, first_cached = _fire(url, endpoint, repeat_text, args.top_k, args.top_n)
    second_ms, second_cached = _fire(url, endpoint, repeat_text, args.top_k, args.top_n)

    stats = _percentiles(uncached_ms)

    print()
    print(f"=== {args.label} ===")
    print(f"endpoint={endpoint} top_k={args.top_k} top_n={args.top_n} n={args.requests} concurrency={args.concurrency}")
    print(f"uncached: p50={stats['p50']:.1f}ms  p95={stats['p95']:.1f}ms  p99={stats['p99']:.1f}ms")
    print(
        f"cached repeat query: first={first_ms:.1f}ms (cached={first_cached})  second={second_ms:.1f}ms (cached={second_cached})"
    )
    print()
    print("Markdown row (paste into measured-facts.md; add NDCG@10 from scripts/run_eval.py separately):")
    print(f"| {args.label} | {stats['p50']:.1f} ms | {stats['p95']:.1f} ms | |")


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure TalentRank API latency against a running server.")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="API base URL (default: http://127.0.0.1:8000)")
    parser.add_argument("--top-k", type=int, default=100)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--requests", type=int, default=30, help="Number of uncached requests to sample")
    parser.add_argument("--concurrency", type=int, default=1, help="Concurrent workers firing uncached requests")
    parser.add_argument("--endpoint", choices=["match", "retrieve"], default="match")
    parser.add_argument("--label", default="unlabeled", help="Label for the printed markdown row")
    args = parser.parse_args()
    measure(args)


if __name__ == "__main__":
    main()
