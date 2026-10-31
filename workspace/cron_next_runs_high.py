#!/usr/bin/env python3
"""Compute the next run times for a standard 5-field cron expression."""

from __future__ import annotations

import os
import subprocess
import sys
from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class CronSpec:
    """Parsed representation of a 5-field cron expression."""

    minutes: tuple[int, ...]
    hours: tuple[int, ...]
    days: frozenset[int]
    months: frozenset[int]
    weekdays: frozenset[int]
    dom_restricted: bool
    dow_restricted: bool


def _parse_field(raw: str, low: int, high: int) -> frozenset[int]:
    """Parse one cron field into a frozenset of valid integer values."""
    if not raw:
        raise ValueError("empty cron field")

    values: set[int] = set()

    for part in raw.split(","):
        if not part:
            raise ValueError("empty cron field item")

        if "/" in part:
            base, _, step_raw = part.partition("/")
            if not step_raw.isdigit():
                raise ValueError(f"invalid step value: {step_raw!r}")
            step = int(step_raw)
            if step <= 0:
                raise ValueError(f"step value must be positive: {step}")

            if base == "*":
                start, end = low, high
            elif "-" in base:
                range_start_raw, _, range_end_raw = base.partition("-")
                if not range_start_raw.isdigit() or not range_end_raw.isdigit():
                    raise ValueError(f"invalid range: {base!r}")
                start = int(range_start_raw)
                end = int(range_end_raw)
                if start < low or start > high or end < low or end > high:
                    raise ValueError(f"range out of bounds: {base!r}")
                if start > end:
                    raise ValueError(f"reversed range: {base!r}")
            else:
                if not base.isdigit():
                    raise ValueError(f"invalid value: {base!r}")
                start = int(base)
                if start < low or start > high:
                    raise ValueError(f"value out of bounds: {base!r}")
                end = high

            values.update(range(start, end + 1, step))
        else:
            if part == "*":
                values.update(range(low, high + 1))
            elif "-" in part:
                range_start_raw, _, range_end_raw = part.partition("-")
                if not range_start_raw.isdigit() or not range_end_raw.isdigit():
                    raise ValueError(f"invalid range: {part!r}")
                start = int(range_start_raw)
                end = int(range_end_raw)
                if start < low or start > high or end < low or end > high:
                    raise ValueError(f"range out of bounds: {part!r}")
                if start > end:
                    raise ValueError(f"reversed range: {part!r}")
                values.update(range(start, end + 1))
            else:
                if not part.isdigit():
                    raise ValueError(f"invalid value: {part!r}")
                value = int(part)
                if value < low or value > high:
                    raise ValueError(f"value out of bounds: {part!r}")
                values.add(value)

    if not values:
        raise ValueError("cron field produced no values")

    return frozenset(values)


def parse_cron(expr: str) -> CronSpec:
    """Parse and validate a standard 5-field cron expression."""
    if not isinstance(expr, str):
        raise ValueError("cron expression must be a string")

    fields = expr.split()
    if len(fields) != 5:
        raise ValueError(f"expected 5 cron fields, got {len(fields)}")

    minute_raw, hour_raw, dom_raw, month_raw, dow_raw = fields

    minutes = _parse_field(minute_raw, 0, 59)
    hours = _parse_field(hour_raw, 0, 23)
    days = _parse_field(dom_raw, 1, 31)
    months = _parse_field(month_raw, 1, 12)
    weekdays = _parse_field(dow_raw, 0, 7)

    # Cron allows 7 as Sunday; normalize to 0.
    weekdays = frozenset(0 if day == 7 else day for day in weekdays)

    return CronSpec(
        minutes=tuple(sorted(minutes)),
        hours=tuple(sorted(hours)),
        days=days,
        months=months,
        weekdays=weekdays,
        dom_restricted=dom_raw != "*",
        dow_restricted=dow_raw != "*",
    )


def _cron_weekday(dt: datetime) -> int:
    """Convert Python weekday (Monday=0) to cron weekday (Sunday=0)."""
    return (dt.weekday() + 1) % 7


def _day_matches(spec: CronSpec, dt: datetime) -> bool:
    """Apply standard cron day-of-month / day-of-week semantics."""
    if dt.month not in spec.months:
        return False

    dom_ok = dt.day in spec.days
    dow_ok = _cron_weekday(dt) in spec.weekdays

    if spec.dom_restricted and spec.dow_restricted:
        return dom_ok or dow_ok
    if spec.dom_restricted:
        return dom_ok
    if spec.dow_restricted:
        return dow_ok
    return True


def _add_years(dt: datetime, years: int) -> datetime:
    """Best-effort year addition for the 100-year search limit."""
    new_year = dt.year + years
    if new_year > 9999:
        return datetime.max

    try:
        return dt.replace(year=new_year)
    except (OverflowError, ValueError):
        if dt.month == 2 and dt.day == 29:
            try:
                return dt.replace(year=new_year, day=28)
            except (OverflowError, ValueError):
                return datetime.max
        return datetime.max


def next_runs(expr: str, start: datetime, count: int = 5) -> list[datetime]:
    """
    Return the next `count` run times strictly after `start`.

    The returned datetimes are naive, with seconds and microseconds zero.
    """
    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        raise ValueError("count must be an integer >= 1")

    spec = parse_cron(expr)

    if not isinstance(start, datetime):
        raise ValueError("start must be a datetime")

    # Work with naive local time and move to the next minute boundary.
    start = start.replace(tzinfo=None, second=0, microsecond=0)
    try:
        current = start + timedelta(minutes=1)
    except OverflowError:
        raise RuntimeError("no matching run found within 100 years") from None

    limit = _add_years(start, 100)
    results: list[datetime] = []

    while len(results) < count and current < limit:
        if current.month not in spec.months:
            if current.month == 12:
                current = datetime(current.year + 1, 1, 1)
            else:
                current = datetime(current.year, current.month + 1, 1)
            continue

        if not _day_matches(spec, current):
            current = (current + timedelta(days=1)).replace(hour=0, minute=0)
            continue

        found = None
        for hour in spec.hours:
            if hour < current.hour:
                continue

            if hour == current.hour:
                minute_index = bisect_left(spec.minutes, current.minute)
            else:
                minute_index = 0

            if minute_index < len(spec.minutes):
                found = datetime(
                    current.year,
                    current.month,
                    current.day,
                    hour,
                    spec.minutes[minute_index],
                )
                break

        if found is None:
            current = (current + timedelta(days=1)).replace(hour=0, minute=0)
        else:
            results.append(found)
            current = found + timedelta(minutes=1)

    if len(results) < count:
        raise RuntimeError("no matching run found within 100 years")

    return results


def _format_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def _parse_cli_start(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def _run_tests() -> int:
    cases = [
        (
            "* * * * *",
            "2024-01-01 00:00:00",
            [
                "2024-01-01T00:01:00",
                "2024-01-01T00:02:00",
                "2024-01-01T00:03:00",
                "2024-01-01T00:04:00",
                "2024-01-01T00:05:00",
            ],
        ),
        (
            "0 9 * * *",
            "2024-01-01 09:00:00",
            [
                "2024-01-02T09:00:00",
                "2024-01-03T09:00:00",
                "2024-01-04T09:00:00",
                "2024-01-05T09:00:00",
                "2024-01-06T09:00:00",
            ],
        ),
        (
            "0 0 1 * 1",
            "2024-01-01 00:00:00",
            [
                "2024-01-08T00:00:00",
                "2024-01-15T00:00:00",
                "2024-01-22T00:00:00",
                "2024-01-29T00:00:00",
                "2024-02-01T00:00:00",
            ],
        ),
        (
            "*/15 8 * * *",
            "2024-01-01 08:10:00",
            [
                "2024-01-01T08:15:00",
                "2024-01-01T08:30:00",
                "2024-01-01T08:45:00",
                "2024-01-02T08:00:00",
                "2024-01-02T08:15:00",
            ],
        ),
        (
            "0 9-17 * * 1-5",
            "2024-01-05 18:00:00",
            [
                "2024-01-08T09:00:00",
                "2024-01-08T10:00:00",
                "2024-01-08T11:00:00",
                "2024-01-08T12:00:00",
                "2024-01-08T13:00:00",
            ],
        ),
        (
            "0 0 29 2 *",
            "2024-03-01 00:00:00",
            [
                "2028-02-29T00:00:00",
                "2032-02-29T00:00:00",
                "2036-02-29T00:00:00",
                "2040-02-29T00:00:00",
                "2044-02-29T00:00:00",
            ],
        ),
        (
            "0 0 * * 7",
            "2024-01-01 00:00:00",
            [
                "2024-01-07T00:00:00",
                "2024-01-14T00:00:00",
                "2024-01-21T00:00:00",
                "2024-01-28T00:00:00",
                "2024-02-04T00:00:00",
            ],
        ),
        (
            "30 4 1,15 * *",
            "2024-01-15 04:30:00",
            [
                "2024-02-01T04:30:00",
                "2024-02-15T04:30:00",
                "2024-03-01T04:30:00",
                "2024-03-15T04:30:00",
                "2024-04-01T04:30:00",
            ],
        ),
    ]

    all_passed = True

    for expr, start_str, expected in cases:
        try:
            start = _parse_cli_start(start_str)
            got = next_runs(expr, start, 5)
            got_formatted = [_format_dt(dt) for dt in got]
            passed = got_formatted == expected
        except (ValueError, RuntimeError):
            passed = False

        if passed:
            print(f"PASS {expr} {start_str}")
        else:
            print(f"FAIL {expr} {start_str}")
            all_passed = False

    # Demonstrate the exact CLI acceptance checks by invoking this file.
    script = os.path.abspath(__file__)
    cli_cases = [
        (
            ["0 9 * * *", "2024-01-01 09:00:00"],
            [
                "2024-01-02T09:00:00",
                "2024-01-03T09:00:00",
                "2024-01-04T09:00:00",
                "2024-01-05T09:00:00",
                "2024-01-06T09:00:00",
            ],
            0,
        ),
        (
            ["bad * * * *", "2024-01-01 00:00:00"],
            None,
            2,
        ),
    ]

    for args, expected_stdout, expected_rc in cli_cases:
        label = " ".join(args)
        try:
            proc = subprocess.run(
                [sys.executable, script, *args],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if expected_stdout is None:
                passed = (
                    proc.returncode == expected_rc
                    and proc.stderr.strip() != ""
                    and proc.stdout.strip() == ""
                )
            else:
                passed = (
                    proc.returncode == expected_rc
                    and proc.stdout.splitlines() == expected_stdout
                    and proc.stderr.strip() == ""
                )
        except Exception:
            passed = False

        if passed:
            print(f"PASS {label}")
        else:
            print(f"FAIL {label}")
            all_passed = False

    if all_passed:
        print("OK")
        return 0

    print("FAILED")
    return 1


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: cron_next_runs_high.py --test", file=sys.stderr)
        return 2

    if argv[0] == "--test":
        return _run_tests()

    if len(argv) != 2:
        print(
            "usage: cron_next_runs_high.py <cron> <YYYY-MM-DD HH:MM:SS>",
            file=sys.stderr,
        )
        return 2

    expr, start_raw = argv

    try:
        start = _parse_cli_start(start_raw)
    except ValueError as exc:
        print(f"error: invalid start time: {exc}", file=sys.stderr)
        return 2

    try:
        runs = next_runs(expr, start, 5)
    except ValueError as exc:
        print(f"error: invalid cron expression: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3

    for run in runs:
        print(_format_dt(run))

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
