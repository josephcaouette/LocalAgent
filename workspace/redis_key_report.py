#!/usr/bin/env python3
"""Report Redis key counts grouped by key prefix.

The prefix is the part of the key before the first ':'.  The script uses
SCAN only; it never uses KEYS.
"""

import argparse
import os
import sys
from collections import Counter

import redis
from redis import exceptions as redis_exceptions

# Make config.py importable whether the script is run from /work, /workspace,
# or another location on the cluster.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
for _path in (_SCRIPT_DIR, os.getcwd(), "/work", "/workspace"):
    if _path and _path not in sys.path:
        sys.path.insert(0, _path)

try:
    import config
except ImportError:
    # Fallback matching the attached config.py defaults.  This is only used if
    # config.py cannot be imported at all.
    config = None
    REDIS_HOST = "192.168.254.25"
    REDIS_PORT = 6379
else:
    REDIS_HOST = getattr(config, "REDIS_HOST", "192.168.254.25")
    REDIS_PORT = int(getattr(config, "REDIS_PORT", 6379))


def make_client():
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=None,
        db=0,
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=3,
    )


def count_by_prefix(client):
    """Count keys by prefix using SCAN only."""
    counts = Counter()
    total = 0

    # scan_iter uses SCAN internally.  It is the only key-enumeration call.
    for key in client.scan_iter(count=1000):
        prefix = key.split(":", 1)[0]
        counts[prefix] += 1
        total += 1

    return counts, total


def print_report(counts, total):
    """Print prefix:count lines sorted by count desc, then prefix asc."""
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    for prefix, count in ordered:
        print(f"{prefix}:{count}")
    print(f"total:{total}")


def main():
    parser = argparse.ArgumentParser(description="Report Redis keys by prefix.")
    parser.add_argument("--test", action="store_true", help="Run self-checks.")
    args = parser.parse_args()

    client = make_client()

    try:
        client.ping()
        counts, total = count_by_prefix(client)
    except (redis_exceptions.ConnectionError, redis_exceptions.TimeoutError, OSError) as exc:
        print(f"ERROR: cannot reach Redis at {REDIS_HOST}:{REDIS_PORT}: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.test:
        if total == 0:
            print("total:0")
            print("FAIL: no keys found")
            sys.exit(1)

        computed_sum = sum(counts.values())
        if computed_sum != total or total < 1:
            print("FAIL: per-prefix counts do not add up to total or total is zero")
            sys.exit(1)

        print("TEST: connected to Redis")
        print(f"TEST: prefix_count_sum={computed_sum}")
        print("TEST: PASS: per-prefix counts add up to total and at least one key exists")

    print_report(counts, total)

    sys.exit(0)


if __name__ == "__main__":
    main()
