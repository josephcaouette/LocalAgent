"""Parse a small CSV subset without using the csv module.

Supported syntax:
- Fields are separated by commas.
- Records are separated by LF or CRLF.
- A field that starts with '"' is quoted.
- Inside a quoted field, '""' is one literal quote.
- Commas and line breaks inside a quoted field are literal.
- After a closing quote, only a comma, line break, or end of text may follow.
- An unquoted field is literal up to the next comma or line break.
"""

import sys


def parse_csv(text: str) -> list[list[str]]:
    """Parse CSV text and return a list of records, each a list of strings."""
    if not isinstance(text, str):
        raise TypeError("text must be str")

    records: list[list[str]] = []
    record: list[str] = []
    field: list[str] = []

    in_quotes = False
    field_started = False
    at_field_start = True

    i = 0
    n = len(text)

    while i < n:
        c = text[i]

        if in_quotes:
            if c == '"':
                if i + 1 < n and text[i + 1] == '"':
                    field.append('"')
                    i += 2
                else:
                    in_quotes = False
                    field_started = True
                    at_field_start = False
                    i += 1

                    if i < n:
                        nxt = text[i]
                        valid = (
                            nxt == ","
                            or nxt == "\n"
                            or (nxt == "\r" and i + 1 < n and text[i + 1] == "\n")
                        )
                        if not valid:
                            raise ValueError("invalid character after closing quote")
            else:
                field.append(c)
                i += 1

        elif c == ",":
            record.append("".join(field))
            field = []
            field_started = True
            at_field_start = True
            i += 1

        elif c == "\n" or (c == "\r" and i + 1 < n and text[i + 1] == "\n"):
            if field_started:
                record.append("".join(field))
            records.append(record)
            record = []
            field = []
            field_started = False
            at_field_start = True
            i += 2 if c == "\r" else 1

        elif c == '"' and at_field_start:
            in_quotes = True
            field_started = True
            at_field_start = False
            i += 1

        else:
            field.append(c)
            field_started = True
            at_field_start = False
            i += 1

    if in_quotes:
        raise ValueError("unterminated quoted field")

    if field_started:
        record.append("".join(field))

    if record:
        records.append(record)

    return records


def _expect_equal(case: str, actual: object, expected: object, failures: list[str]) -> bool:
    if actual == expected:
        return True
    failures.append(f"{case}: expected {expected!r}, got {actual!r}")
    return False


def _expect_value_error(case: str, text: str, failures: list[str]) -> bool:
    try:
        parse_csv(text)
    except ValueError:
        return True
    failures.append(f"{case}: expected ValueError for {text!r}")
    return False


def _run_case(case: str, func, failures: list[str]) -> bool:
    try:
        ok = func()
    except Exception as exc:
        failures.append(f"{case}: unexpected {type(exc).__name__}: {exc}")
        print(f"FAIL {case}")
        return False

    if ok:
        print(f"PASS {case}")
        return True

    print(f"FAIL {case}")
    return False


def _run_self_tests() -> int:
    failures: list[str] = []
    all_ok = True

    def quoting() -> bool:
        return (
            _expect_equal("quoting", parse_csv('"hello, world"'), [["hello, world"]], failures)
            and _expect_equal("quoting", parse_csv('"a",b'), [["a", "b"]], failures)
            and _expect_equal("quoting", parse_csv('a"b'), [["a\"b"]], failures)
            and _expect_equal("quoting", parse_csv('a,"b,c",d'), [["a", "b,c", "d"]], failures)
            and _expect_equal("quoting", parse_csv('"a","b"'), [["a", "b"]], failures)
        )

    def escaped_quotes() -> bool:
        return (
            _expect_equal("escaped_quotes", parse_csv('"a""b"'), [["a\"b"]], failures)
            and _expect_equal("escaped_quotes", parse_csv('"say ""hi"" now"'), [["say \"hi\" now"]], failures)
            and _expect_equal("escaped_quotes", parse_csv('""'), [[""]], failures)
            and _expect_equal("escaped_quotes", parse_csv('""""'), [["\""]], failures)
        )

    def line_breaks_inside_quotes() -> bool:
        return (
            _expect_equal("line_breaks_inside_quotes", parse_csv('"line1\nline2"'), [["line1\nline2"]], failures)
            and _expect_equal(
                "line_breaks_inside_quotes",
                parse_csv('"line1\r\nline2",x'),
                [["line1\r\nline2", "x"]],
                failures,
            )
            and _expect_equal(
                "line_breaks_inside_quotes",
                parse_csv('a,"x\ny",b'),
                [["a", "x\ny", "b"]],
                failures,
            )
        )

    def crlf() -> bool:
        return (
            _expect_equal("crlf", parse_csv("a,b\r\nc,d\r\n"), [["a", "b"], ["c", "d"]], failures)
            and _expect_equal("crlf", parse_csv('"a\r\nb"\r\n'), [["a\r\nb"]], failures)
            and _expect_equal("crlf", parse_csv("a\rb"), [["a\rb"]], failures)
            and _expect_equal("crlf", parse_csv("a\r\n"), [["a"]], failures)
        )

    def empty_fields() -> bool:
        return (
            _expect_equal("empty_fields", parse_csv("a,,b"), [["a", "", "b"]], failures)
            and _expect_equal("empty_fields", parse_csv(",a,"), [["", "a", ""]], failures)
            and _expect_equal("empty_fields", parse_csv("a,"), [["a", ""]], failures)
            and _expect_equal("empty_fields", parse_csv(","), [["", ""]], failures)
            and _expect_equal("empty_fields", parse_csv(""), [], failures)
        )

    def empty_lines() -> bool:
        return (
            _expect_equal("empty_lines", parse_csv("a\n\nb"), [["a"], [], ["b"]], failures)
            and _expect_equal("empty_lines", parse_csv("a\n"), [["a"]], failures)
            and _expect_equal("empty_lines", parse_csv("\n"), [[]], failures)
            and _expect_equal("empty_lines", parse_csv("a\r\n\r\nb"), [["a"], [], ["b"]], failures)
            and _expect_equal("empty_lines", parse_csv("a\n\n"), [["a"], []], failures)
        )

    def errors() -> bool:
        bad_cases = [
            '"abc',
            '"abc"def',
            '"abc" ',
            '"abc"\r',
            '"abc""def',
            '""x',
            '"a"b',
        ]
        ok = True
        for bad in bad_cases:
            ok = ok and _expect_value_error("errors", bad, failures)
        return ok

    all_ok = _run_case("quoting", quoting, failures) and all_ok
    all_ok = _run_case("escaped_quotes", escaped_quotes, failures) and all_ok
    all_ok = _run_case("line_breaks_inside_quotes", line_breaks_inside_quotes, failures) and all_ok
    all_ok = _run_case("crlf", crlf, failures) and all_ok
    all_ok = _run_case("empty_fields", empty_fields, failures) and all_ok
    all_ok = _run_case("empty_lines", empty_lines, failures) and all_ok
    all_ok = _run_case("errors", errors, failures) and all_ok

    if all_ok:
        print("OK")
        return 0

    for failure in failures:
        print(failure, file=sys.stderr)
    return 1


def _usage() -> None:
    print("usage: python3 csv_high.py FILE", file=sys.stderr)
    print("       python3 csv_high.py --test", file=sys.stderr)


def _run_file(path: str) -> int:
    try:
        with open(path, "r", encoding="utf-8", newline="") as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    try:
        records = parse_csv(text)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    for record in records:
        print(record)
    return 0


def main(argv: list) -> int:
    if len(argv) == 2:
        arg = argv[1]
        if arg == "--test":
            return _run_self_tests()
        if arg.startswith("-"):
            _usage()
            return 2
        return _run_file(arg)

    _usage()
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
