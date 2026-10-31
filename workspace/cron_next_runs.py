#!/usr/bin/env python3
"""
cron_next_runs.py

Parses standard 5-field cron expressions and prints the next 5 run times.
Supports *, lists, ranges, and step values.
Follows standard cron rules for day-of-month and day-of-week combination.
"""

import argparse
import sys
from datetime import datetime, timedelta


def parse_field(field, min_value, max_value):
    """
    Parse a single cron field and return a sorted set of integers.
    
    Supports:
    - '*' (all values)
    - Single values (e.g., '5')
    - Ranges (e.g., '1-5')
    - Steps (e.g., '*/15', '1-30/5')
    - Lists (e.g., '1,5,10')
    - Combinations (e.g., '1-5,10,20-30/2')
    """
    values = set()
    
    for term in field.split(','):
        term = term.strip()
        if not term:
            raise ValueError(f"Empty term in field: '{field}'")
        
        # Check for step value
        if '/' in term:
            base, step_str = term.split('/', 1)
            try:
                step = int(step_str)
            except ValueError:
                raise ValueError(f"Invalid step value: '{step_str}'")
            if step <= 0:
                raise ValueError(f"Step must be positive: {step}")
            
            if base == '*':
                start_val = min_value
                end_val = max_value
            elif '-' in base:
                start_str, end_str = base.split('-', 1)
                try:
                    start_val = int(start_str)
                    end_val = int(end_str)
                except ValueError:
                    raise ValueError(f"Invalid range in step term: '{base}'")
                if start_val > end_val:
                    raise ValueError(f"Invalid range: {start_val}-{end_val}")
            else:
                try:
                    start_val = int(base)
                except ValueError:
                    raise ValueError(f"Invalid base value: '{base}'")
                end_val = max_value
            
            if start_val < min_value or end_val > max_value:
                raise ValueError(f"Value out of range [{min_value}, {max_value}]: {start_val}-{end_val}")
            
            values.update(range(start_val, end_val + 1, step))
        
        elif '-' in term:
            start_str, end_str = term.split('-', 1)
            try:
                start_val = int(start_str)
                end_val = int(end_str)
            except ValueError:
                raise ValueError(f"Invalid range: '{term}'")
            if start_val > end_val:
                raise ValueError(f"Invalid range: {start_val}-{end_val}")
            if start_val < min_value or end_val > max_value:
                raise ValueError(f"Value out of range [{min_value}, {max_value}]: {start_val}-{end_val}")
            values.update(range(start_val, end_val + 1))
        
        elif term == '*':
            values.update(range(min_value, max_value + 1))
        
        else:
            try:
                val = int(term)
            except ValueError:
                raise ValueError(f"Invalid value: '{term}'")
            if val < min_value or val > max_value:
                raise ValueError(f"Value out of range [{min_value}, {max_value}]: {val}")
            values.add(val)
    
    return sorted(values)


def parse_cron(expr):
    """
    Parse a 5-field cron expression.
    Returns a tuple of (minutes, hours, doms, months, dows, dom_raw, dow_raw)
    where dows has 7 normalized to 0.
    """
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError(f"Cron expression must have exactly 5 fields, got {len(fields)}: '{expr}'")
    
    minute_field, hour_field, dom_field, month_field, dow_field = fields
    
    minutes = parse_field(minute_field, 0, 59)
    hours = parse_field(hour_field, 0, 23)
    doms = parse_field(dom_field, 1, 31)
    months = parse_field(month_field, 1, 12)
    dows = parse_field(dow_field, 0, 7)
    
    # Normalize day-of-week: 7 -> 0 (both mean Sunday)
    dows = sorted(set(0 if d == 7 else d for d in dows))
    
    dom_raw = dom_field
    dow_raw = dow_field
    
    return minutes, hours, doms, months, dows, dom_raw, dow_raw


def day_matches(date, doms, dows, dom_raw, dow_raw):
    """
    Check if a date matches the day constraints using standard cron rules.
    
    Standard cron rule:
    - If both day-of-month and day-of-week are restricted (not '*'),
      the date matches if EITHER day-of-month OR day-of-week matches.
    - If only one is restricted, only that field must match.
    - If neither is restricted, all days match.
    """
    dom_restricted = dom_raw != '*'
    dow_restricted = dow_raw != '*'
    
    day_of_month = date.day
    # Python: Monday=0, Sunday=6. Cron: Sunday=0, Monday=1, ..., Saturday=6
    day_of_week = (date.weekday() + 1) % 7  # Convert to cron convention
    
    if dom_restricted and dow_restricted:
        # Both restricted: match if either matches
        return day_of_month in doms or day_of_week in dows
    elif dom_restricted:
        return day_of_month in doms
    elif dow_restricted:
        return day_of_week in dows
    else:
        return True


def next_runs(expr, start, count=5):
    """
    Find the next 'count' run times strictly after 'start'.
    Returns a list of datetime objects.
    """
    minutes, hours, doms, months, dows, dom_raw, dow_raw = parse_cron(expr)
    
    # Truncate start to the minute
    start_truncated = start.replace(second=0, microsecond=0)
    
    # Start scanning from the next minute
    current = start_truncated + timedelta(minutes=1)
    
    results = []
    # Limit search to avoid infinite loops (e.g., invalid expressions)
    max_iterations = 100000
    iterations = 0
    
    while len(results) < count and iterations < max_iterations:
        iterations += 1
        
        # Check month
        if current.month not in months:
            # Advance to the first day of the next month
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1, day=1, hour=0, minute=0)
            else:
                current = current.replace(month=current.month + 1, day=1, hour=0, minute=0)
            continue
        
        # Check day (using standard cron rules)
        if not day_matches(current, doms, dows, dom_raw, dow_raw):
            current += timedelta(days=1)
            current = current.replace(hour=0, minute=0)
            continue
        
        # Check hour
        if current.hour not in hours:
            current += timedelta(hours=1)
            current = current.replace(minute=0)
            continue
        
        # Check minute
        if current.minute not in minutes:
            current += timedelta(minutes=1)
            continue
        
        # All fields match
        results.append(current)
        current += timedelta(minutes=1)
    
    if len(results) < count:
        raise RuntimeError(f"Could not find {count} run times within search limit")
    
    return results


def format_datetime(dt):
    """Format a datetime as 'YYYY-MM-DD HH:MM'."""
    return dt.strftime('%Y-%m-%d %H:%M')


def run_test():
    """Run test cases and print PASS/FAIL lines."""
    test_cases = [
        # (expression, start_time, expected_next_5)
        (
            '0 0 1 * 1',
            '2024-01-01T00:00:00',
            ['2024-01-08 00:00', '2024-01-15 00:00', '2024-01-22 00:00', '2024-01-29 00:00', '2024-02-01 00:00']
        ),
        (
            '*/15 * * * *',
            '2024-01-01T00:00:00',
            ['2024-01-01 00:15', '2024-01-01 00:30', '2024-01-01 00:45', '2024-01-01 01:00', '2024-01-01 01:15']
        ),
        (
            '0 0 1 1 *',
            '2024-01-01T00:00:00',
            ['2025-01-01 00:00', '2026-01-01 00:00', '2027-01-01 00:00', '2028-01-01 00:00', '2029-01-01 00:00']
        ),
        (
            '30 2 * * 0',
            '2024-01-01T00:00:00',
            ['2024-01-07 02:30', '2024-01-14 02:30', '2024-01-21 02:30', '2024-01-28 02:30', '2024-02-04 02:30']
        ),
        (
            '0 12 1,15 * 3',
            '2024-01-01T00:00:00',
            ['2024-01-01 12:00', '2024-01-03 12:00', '2024-01-10 12:00', '2024-01-15 12:00', '2024-01-17 12:00']
        ),
    ]
    
    all_passed = True
    for expr, start_str, expected in test_cases:
        start_dt = datetime.fromisoformat(start_str)
        try:
            actual = next_runs(expr, start_dt, count=5)
            actual_formatted = [format_datetime(dt) for dt in actual]
            if actual_formatted == expected:
                print(f"PASS {expr} {start_str} -> {', '.join(actual_formatted)}")
            else:
                print(f"FAIL {expr} {start_str} -> expected {', '.join(expected)}, got {', '.join(actual_formatted)}")
                all_passed = False
        except Exception as e:
            print(f"FAIL {expr} {start_str} -> error: {e}")
            all_passed = False
    
    return all_passed


def main():
    parser = argparse.ArgumentParser(description='Cron next run times calculator')
    parser.add_argument('--test', action='store_true', help='Run test cases')
    parser.add_argument('expr', nargs='?', help='Cron expression')
    parser.add_argument('start', nargs='?', help='Start time (ISO format)')
    
    args = parser.parse_args()
    
    if args.test:
        success = run_test()
        sys.exit(0 if success else 1)
    else:
        if not args.expr or not args.start:
            parser.error("Both expression and start time are required (or use --test)")
        
        start_dt = datetime.fromisoformat(args.start)
        try:
            results = next_runs(args.expr, start_dt, count=5)
            for dt in results:
                print(format_datetime(dt))
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == '__main__':
    main()
