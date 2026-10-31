import argparse
import csv
import math
import sys
from pathlib import Path

SAMPLE_CSV_TEXT = """name,age,city,score
Alice,20,Paris,80
Bob,,London,91
Cara,25,,
Dan,30,Osaka,
"""


def is_blank(value):
    return value is None or value.strip() == ""


def to_finite_float(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def compute_stats(csv_path):
    csv_path = Path(csv_path)
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    numeric_stats = {}
    non_numeric_columns = []

    for column in fieldnames:
        numbers = []
        invalid = False

        for row in rows:
            raw = row.get(column)
            if is_blank(raw):
                continue

            number = to_finite_float(raw)
            if number is None:
                invalid = True
                break

            numbers.append(number)

        if numbers and not invalid:
            numeric_stats[column] = {
                "count": len(numbers),
                "mean": sum(numbers) / len(numbers),
                "min": min(numbers),
                "max": max(numbers),
            }
        else:
            non_numeric_columns.append(column)

    return numeric_stats, non_numeric_columns


def format_report(numeric_stats, non_numeric_columns):
    lines = ["Numeric columns:"]

    if numeric_stats:
        for column, stats in numeric_stats.items():
            lines.append(
                f"{column}: count={stats['count']} "
                f"mean={stats['mean']:.2f} "
                f"min={stats['min']:.2f} "
                f"max={stats['max']:.2f}"
            )
    else:
        lines.append("(none)")

    lines.append("Non-numeric columns:")
    if non_numeric_columns:
        lines.append(", ".join(non_numeric_columns))
    else:
        lines.append("(none)")

    return "\n".join(lines)


def run_test():
    sample_path = Path("sample.csv")
    sample_path.write_text(SAMPLE_CSV_TEXT, encoding="utf-8")
    print("sample.csv written")

    numeric_stats, non_numeric_columns = compute_stats(sample_path)
    print(format_report(numeric_stats, non_numeric_columns))

    failures = []

    expected_numeric = {
        "age": {"count": 3, "mean": 25.00, "min": 20.00, "max": 30.00},
        "score": {"count": 2, "mean": 85.50, "min": 80.00, "max": 91.00},
    }

    if set(numeric_stats) != set(expected_numeric):
        failures.append(
            f"numeric columns mismatch: {sorted(numeric_stats)} != {sorted(expected_numeric)}"
        )

    for column, expected in expected_numeric.items():
        actual = numeric_stats.get(column)
        if actual is None:
            failures.append(f"missing numeric column: {column}")
            continue

        if actual["count"] != expected["count"]:
            failures.append(f"{column}: count {actual['count']} != {expected['count']}")

        for key in ("mean", "min", "max"):
            if not math.isclose(actual[key], expected[key], rel_tol=1e-12, abs_tol=1e-12):
                failures.append(f"{column}: {key} {actual[key]} != {expected[key]}")

    if non_numeric_columns != ["name", "city"]:
        failures.append(
            f"non-numeric columns mismatch: {non_numeric_columns} != ['name', 'city']"
        )

    if failures:
        print("FAIL: expected statistics mismatch")
        for failure in failures:
            print(f" - {failure}")
        sys.exit(1)

    print("PASS: all expected statistics matched")
    sys.exit(0)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Compute statistics for numeric CSV columns.")
    parser.add_argument("csv_path", nargs="?", help="Path to a CSV file to analyze.")
    parser.add_argument("--test", action="store_true", help="Run a built-in self-test.")
    args = parser.parse_args(argv)

    if args.test:
        run_test()
        return 0

    if not args.csv_path:
        parser.print_usage(sys.stderr)
        print("error: a CSV path is required unless --test is used", file=sys.stderr)
        return 2

    numeric_stats, non_numeric_columns = compute_stats(args.csv_path)
    print(format_report(numeric_stats, non_numeric_columns))
    return 0


if __name__ == "__main__":
    sys.exit(main())
