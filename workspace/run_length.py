"""Strict run-length encoding CLI."""

import sys
from itertools import groupby

_ASCII_DIGITS = "0123456789"


def encode(s: str) -> str:
    """Encode a string using decimal counts followed by the repeated character."""
    if not isinstance(s, str):
        raise TypeError("encode() expects a str")
    if any(ch.isdigit() for ch in s):
        raise ValueError("input must not contain digits")
    return "".join(str(sum(1 for _ in group)) + ch for ch, group in groupby(s))


def decode(s: str) -> str:
    """Decode a strict run-length encoded string."""
    if not isinstance(s, str):
        raise TypeError("decode() expects a str")
    if s == "":
        return ""

    out = []
    i = 0
    n = len(s)

    while i < n:
        if s[i] not in _ASCII_DIGITS:
            raise ValueError("expected an ASCII digit at start of run")
        if s[i] == "0":
            raise ValueError("count must not have a leading zero")

        j = i + 1
        while j < n and s[j] in _ASCII_DIGITS:
            j += 1

        if j == n:
            raise ValueError("count must be followed by a repeated character")
        if s[j].isdigit():
            raise ValueError("repeated character must not be a digit")

        count = int(s[i:j])
        out.append(s[j] * count)
        i = j + 1

    return "".join(out)


def _usage() -> str:
    return "usage: run_length.py --test | run_length.py encode TEXT | run_length.py decode TEXT"


def _test_round_trip_aaabcc() -> None:
    assert encode("aaabcc") == "3a1b2c"
    assert decode("3a1b2c") == "aaabcc"


def _test_empty() -> None:
    assert encode("") == ""
    assert decode("") == ""


def _test_single_character() -> None:
    assert encode("a") == "1a"
    assert decode("1a") == "a"


def _test_long_run_over_9() -> None:
    assert encode("a" * 10) == "10a"
    assert decode("10a") == "a" * 10


def _test_encode_rejects_digit() -> None:
    try:
        encode("1")
    except ValueError:
        return
    raise AssertionError("encode('1') did not raise ValueError")


def _test_decode_rejects_a3() -> None:
    try:
        decode("a3")
    except ValueError:
        return
    raise AssertionError("decode('a3') did not raise ValueError")


def _test_decode_rejects_3() -> None:
    try:
        decode("3")
    except ValueError:
        return
    raise AssertionError("decode('3') did not raise ValueError")


def run_tests() -> int:
    tests = [
        ("round_trip_aaabcc", _test_round_trip_aaabcc),
        ("empty", _test_empty),
        ("single_character", _test_single_character),
        ("long_run_over_9", _test_long_run_over_9),
        ("encode_rejects_digit", _test_encode_rejects_digit),
        ("decode_rejects_a3", _test_decode_rejects_a3),
        ("decode_rejects_3", _test_decode_rejects_3),
    ]

    failures = 0
    for name, func in tests:
        try:
            func()
        except Exception:
            print(f"FAIL {name}")
            failures += 1
        else:
            print(f"PASS {name}")

    if failures:
        print("Tests failed")
        return 1

    print("All tests passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if len(argv) == 1 and argv[0] == "--test":
        return run_tests()

    if len(argv) == 2 and argv[0] in ("encode", "decode"):
        text = argv[1]
        try:
            if argv[0] == "encode":
                result = encode(text)
            else:
                result = decode(text)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

        print(result)
        return 0

    print(_usage(), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
