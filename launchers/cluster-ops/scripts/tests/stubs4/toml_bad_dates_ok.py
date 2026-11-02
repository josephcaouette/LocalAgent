"""A correct solution of battery 4's toml task for validating the checker: tomllib (the reference
itself) plus the goal's no-dates rule. BUG picks a deliberate defect for the bad variants
(mkvariants4.py); "" is the correct version."""
import datetime
import re
import tomllib

BUG = "dates_ok"


def _check(v):
    if isinstance(v, (datetime.date, datetime.time)):
        raise ValueError("date and time values are not supported")
    for x in (v.values() if isinstance(v, dict) else v if isinstance(v, list) else ()):
        _check(x)


def _floats(v):
    if isinstance(v, dict):
        return {k: _floats(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_floats(x) for x in v]
    return float(v) if type(v) is int else v


def loads(text):
    if BUG == "crlf_strict" and "\r" in text:
        raise ValueError("CR")
    if BUG == "inline_comma":
        text = re.sub(r",\s*\}", "}", text)
    if BUG == "leading_zero":
        text = re.sub(r"(=\s*[+-]?)0+(\d)", r"\1\2", text)
    if BUG == "empty_key" and re.search(r"(?m)^\s*(\"\"|'')\s*=", text):
        raise ValueError("empty key")
    v = tomllib.loads(text)
    if BUG != "dates_ok":
        _check(v)
    return _floats(v) if BUG == "ints_as_floats" else v
