#!/usr/bin/env python3
"""log_level_stats.py - Count log levels and report top ERROR messages."""

import argparse
import re
import sys
import os
from collections import Counter

LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

# Regex to match log lines like:
# 2024-01-15 10:30:45 ERROR Some message here
# or: 2024-01-15T10:30:45Z ERROR Some message here
# or: [ERROR] Some message
# We'll use a flexible pattern.
LOG_LINE_RE = re.compile(
    r'^(?:\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?\s+)?'  # optional timestamp
    r'(?:\[)?'
    r'(DEBUG|INFO|WARNING|ERROR|CRITICAL)'
    r'(?:\])?'
    r'\s*:?\s*'
    r'(.*)$',
    re.IGNORECASE
)


def generate_sample_log(path: str) -> None:
    """Write a sample log file with known, fixed counts."""
    lines = []
    # 5 DEBUG lines
    for i in range(5):
        lines.append(f"2024-01-15 10:00:0{i} DEBUG Debug message {i}")
    # 10 INFO lines
    for i in range(10):
        lines.append(f"2024-01-15 10:01:0{i} INFO Info message {i}")
    # 3 WARNING lines
    for i in range(3):
        lines.append(f"2024-01-15 10:02:0{i} WARNING Warning message {i}")
    # 4 ERROR lines with specific repeated messages:
    # "Disk full" x2, "Connection refused" x1, "Timeout" x1
    lines.append("2024-01-15 10:03:00 ERROR Disk full")
    lines.append("2024-01-15 10:03:01 ERROR Connection refused")
    lines.append("2024-01-15 10:03:02 ERROR Disk full")
    lines.append("2024-01-15 10:03:03 ERROR Timeout")
    # 2 CRITICAL lines
    lines.append("2024-01-15 10:04:00 CRITICAL System failure")
    lines.append("2024-01-15 10:04:01 CRITICAL Kernel panic")

    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def analyze_log(path: str) -> tuple[dict[str, int], list[tuple[str, int]]]:
    """
    Read a log file and return:
      - counts: dict mapping each log level to its count
      - top_errors: list of (message, count) for the 3 most frequent ERROR messages
    """
    counts = {level: 0 for level in LOG_LEVELS}
    error_messages = Counter()

    with open(path, "r") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            match = LOG_LINE_RE.match(line)
            if match:
                level = match.group(1).upper()
                message = match.group(2).strip()
                if level in counts:
                    counts[level] += 1
                    if level == "ERROR":
                        error_messages[message] += 1
            # Lines that don't match are ignored

    # Get top 3 ERROR messages by frequency (most common first)
    top_errors = error_messages.most_common(3)

    return counts, top_errors


def print_results(counts: dict[str, int], top_errors: list[tuple[str, int]]) -> None:
    """Print level counts and top ERROR messages."""
    print("Log Level Counts:")
    for level in LOG_LEVELS:
        print(f"  {level}: {counts[level]}")
    print()
    print("Top 3 Most Frequent ERROR Messages:")
    if top_errors:
        for i, (msg, count) in enumerate(top_errors, 1):
            print(f"  {i}. [{count}x] {msg}")
    else:
        print("  (no ERROR messages found)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Count log levels and report top ERROR messages.")
    parser.add_argument("logfile", nargs="?", default=None, help="Path to the log file")
    parser.add_argument("--test", action="store_true", help="Run in test mode")
    args = parser.parse_args()

    if args.test:
        # Generate a sample log in /tmp
        test_log_path = "/tmp/test_sample_log.log"
        generate_sample_log(test_log_path)

        # Analyze it
        counts, top_errors = analyze_log(test_log_path)

        # Expected counts
        expected_counts = {
            "DEBUG": 5,
            "INFO": 10,
            "WARNING": 3,
            "ERROR": 4,
            "CRITICAL": 2,
        }

        # Check counts
        all_ok = True
        print("Test: Verifying log level counts...")
        for level in LOG_LEVELS:
            if counts[level] != expected_counts[level]:
                print(f"  FAIL: {level} expected {expected_counts[level]}, got {counts[level]}")
                all_ok = False
            else:
                print(f"  OK: {level} = {counts[level]}")

        # Check top errors
        # Expected top errors:
        #   "Disk full" x2
        #   "Connection refused" x1, "Timeout" x1 (tied, order may vary)
        print("Test: Verifying top ERROR messages...")
        if len(top_errors) != 3:
            print(f"  FAIL: Expected 3 top errors, got {len(top_errors)}")
            all_ok = False
        else:
            # Check that "Disk full" is first with count 2
            if top_errors[0][0] != "Disk full" or top_errors[0][1] != 2:
                print(f"  FAIL: Expected ('Disk full', 2) first, got {top_errors[0]}")
                all_ok = False
            else:
                print(f"  OK: Top error = {top_errors[0]}")

            # Check that the other two are "Connection refused" and "Timeout" (order may vary)
            remaining_msgs = {top_errors[1][0], top_errors[2][0]}
            expected_remaining = {"Connection refused", "Timeout"}
            if remaining_msgs != expected_remaining:
                print(f"  FAIL: Expected remaining errors {expected_remaining}, got {remaining_msgs}")
                all_ok = False
            else:
                print(f"  OK: Remaining errors = {remaining_msgs}")

            # Check counts for the remaining two
            for msg, cnt in top_errors[1:]:
                if cnt != 1:
                    print(f"  FAIL: Expected count 1 for '{msg}', got {cnt}")
                    all_ok = False
                else:
                    print(f"  OK: '{msg}' count = {cnt}")

        # Print the results as evidence
        print()
        print("Full output for sample log:")
        print_results(counts, top_errors)

        # Cleanup
        if os.path.exists(test_log_path):
            os.remove(test_log_path)

        if all_ok:
            print()
            print("TEST PASSED")
            sys.exit(0)
        else:
            print()
            print("TEST FAILED")
            sys.exit(1)

    else:
        # Normal mode
        if args.logfile is None:
            # Default to a common log path or prompt
            default_path = "/var/log/app.log"
            if os.path.exists(default_path):
                log_path = default_path
            else:
                print("No log file specified. Using default path or entering manually.")
                log_path = input("Enter log file path: ").strip()
                if not log_path:
                    print("No path provided. Exiting.")
                    sys.exit(1)
        else:
            log_path = args.logfile

        if not os.path.exists(log_path):
            print(f"Error: Log file '{log_path}' not found.", file=sys.stderr)
            sys.exit(1)

        counts, top_errors = analyze_log(log_path)
        print_results(counts, top_errors)


if __name__ == "__main__":
    main()
