import operator
import re
import sys

_INTERVAL_RE = re.compile(r"^(-?\d+)-(-?\d+)$")


def _coerce_int(value, name):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer, not a boolean")
    try:
        return operator.index(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _validate_interval(interval):
    if isinstance(interval, (str, bytes, bytearray)):
        raise ValueError("interval must be a 2-item sequence of integers")

    try:
        start, end = interval
    except (TypeError, ValueError) as exc:
        raise ValueError("interval must be a 2-item sequence") from exc

    start = _coerce_int(start, "start")
    end = _coerce_int(end, "end")

    if start > end:
        raise ValueError("interval start must be <= end")

    return (start, end)


def merge_intervals(intervals):
    validated = [_validate_interval(interval) for interval in intervals]
    validated.sort()

    if not validated:
        return []

    merged = []
    current_start, current_end = validated[0]

    for start, end in validated[1:]:
        if start <= current_end:
            if end > current_end:
                current_end = end
        else:
            merged.append((current_start, current_end))
            current_start, current_end = start, end

    merged.append((current_start, current_end))
    return merged


def parse_interval(text):
    match = _INTERVAL_RE.match(text)
    if match is None:
        raise ValueError(f"malformed interval argument: {text!r}")
    return int(match.group(1)), int(match.group(2))


def run_self_tests():
    assert merge_intervals([]) == []
    print("PASS: empty input")

    assert merge_intervals([(1, 10), (2, 3), (4, 5)]) == [(1, 10)]
    assert merge_intervals([(2, 3), (1, 10)]) == [(1, 10)]
    print("PASS: nested intervals")

    assert merge_intervals([(8, 10), (1, 3), (2, 6)]) == [(1, 6), (8, 10)]
    print("PASS: unsorted input")

    assert merge_intervals([(1, 3), (3, 5), (5, 7)]) == [(1, 7)]
    assert merge_intervals([(1, 3), (4, 6)]) == [(1, 3), (4, 6)]
    print("PASS: touching intervals")

    try:
        merge_intervals([(3, 1)])
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for start > end")
    print("PASS: ValueError for start > end")

    print("ALL TESTS PASSED")


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    if any(arg == "--test" for arg in argv):
        try:
            run_self_tests()
        except AssertionError as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 1
        return 0

    try:
        parsed = [parse_interval(arg) for arg in argv]
        merged = merge_intervals(parsed)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(" ".join(f"{start}-{end}" for start, end in merged))
    return 0


if __name__ == "__main__":
    sys.exit(main())
