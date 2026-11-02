"""Third test battery: three hard tasks meant to tell Ultra and MAX apart (in sets 1 and 2 both levels
were always right). Goals and reference checkers. Run inside the sandbox (the module under test is
pipeline-written code):  python3 battery3_checks.py TASK /work/<file>.py
Prints `SCORE passed/total` and up to 6 mismatches. TASK is json, ipv6 or regex.

Every reference is the standard library (json, ipaddress, re) behind a thin layer for the goal's own
rules. Validate changes with tests/stubs3/: `python3 battery3_checks.py selfcheck` compares the IPv6
formatter with ipaddress, and every <task>_ok stub must score in full while every <task>_bad_* stub must not.
Each call to the module gets 1 s (a regex that loops on (a*)* is a wrong answer, not a hung checker);
after 8 timeouts the remaining cases count as failed without calling it."""
import importlib.util
import ipaddress
import json
import random
import re
import signal
import sys

GOALS = {
    "json": (
        "Create a Python module with parse_json(text) that parses a JSON document into Python values, "
        "without using the json module. Objects become dict, arrays list, strings str, true and false bool "
        "and null None. A number is an optional minus sign, then 0 or a digit 1-9 followed by more digits, "
        "then an optional fraction (a dot and one or more digits), then an optional exponent (e or E, an "
        "optional + or -, one or more digits). It becomes an int when it has neither fraction nor exponent "
        "and a float otherwise; nothing else is a number (no plus sign in front, no leading zeros, no NaN "
        "or Infinity). A string is enclosed in double quotes and may not contain an unescaped character "
        "below U+0020; its escapes are \\\" \\\\ \\/ \\b \\f \\n \\r \\t and \\uXXXX with four hex digits "
        "in either case. A \\u escape for a high surrogate (D800-DBFF) immediately followed by a \\u escape "
        "for a low surrogate (DC00-DFFF) is one character; any other surrogate escape stands for that code "
        "point alone. Object keys are strings, and when a key repeats, the last value wins. Whitespace "
        "between tokens is any mix of space, tab, newline and carriage return, and the whole text must be "
        "exactly one value with optional whitespace around it. Anything else raises ValueError. Command "
        "line: python <script> FILE prints repr() of the parsed value. In --test mode check every kind of "
        "value, nesting, the number forms, every escape including surrogate pairs, repeated keys and "
        "malformed input."),
    "ipv6": (
        "Create a Python module with normalize_ipv6(text) -> str that checks an IPv6 address written in "
        "the text form of RFC 4291 and returns it in the canonical form described below, without using the "
        "ipaddress or socket modules. Input: eight groups of one to four hex digits (either case) separated "
        "by colons; or fewer groups with exactly one :: standing for one or more groups of zeros (:: alone "
        "is all zeros, and :: may come at the start or the end). The last two groups may instead be written "
        "as a dotted IPv4 address: four decimal numbers 0-255 separated by dots, without leading zeros (0 "
        "is fine, 01 is not). Output: the eight groups in lowercase hex without leading zeros, separated by "
        "colons, with the longest run of two or more consecutive zero groups replaced by :: (the leftmost "
        "such run when two are equally long). A lone zero group stays 0, and the output never uses the "
        "dotted form, not even for IPv4-mapped addresses (::ffff:1.2.3.4 becomes ::ffff:102:304). Anything "
        "else raises ValueError, including spaces, a zone index such as %eth0, a "
        "second ::, a group of five or more digits, and too many or too few groups. Command line: python "
        "<script> ADDRESS prints the canonical form. In --test mode check the compression rules including "
        "ties, :: at either end, embedded IPv4, mixed case and malformed input."),
    "regex": (
        "Create a Python module with full_match(pattern, text) -> bool that reports whether the whole of "
        "text matches the regular expression pattern, without using the re module. In a pattern, . matches "
        "any one character except a newline. [...] is a character class: it matches one character that is "
        "listed, on its own or in a range such as a-z (both ends included), and [^...] matches one character "
        "that is not listed, a newline included. A ] right after [ or [^ is listed rather than closing the "
        "class, and a - that is first or last in the class is listed rather than making a range. A "
        "backslash followed by a character that is not a letter or digit (Unicode letters and digits count, as str.isalnum() decides) stands for that character itself, "
        "inside a class or outside (so \\. matches a dot). *, + and ? after an item repeat it zero or more "
        "times, one or more times, or zero or one time; an item is a character, ., a class, an escape or a "
        "group. Parentheses group a sub-pattern, and | separates alternatives at the top level or inside a "
        "group; an alternative may be empty and then matches the empty string. Every other character, "
        "including ^ $ { } and spaces, matches itself. Matching must consider every way the pattern can "
        "match: full_match('(a|ab)c', 'abc') and full_match('(a*)*b', 'aab') are True, and patterns such as "
        "(a*)* must not loop forever. These raise ValueError: an unmatched ( or ), a *, + or ? with no item "
        "before it (at the start, right after ( or |, or right after another *, + or ?), a class with no "
        "closing ], a range whose second character comes before its first (such as z-a), and a backslash "
        "at the end of the pattern or before a letter or digit (so \\\u00e9 is an error too). Command line: python <script> PATTERN TEXT "
        "prints True or False. In --test mode check literals, ., classes, ranges, negated classes, escapes, "
        "each quantifier, groups, alternation including empty alternatives, nested repetition and every "
        "error."),
}


# ----------------------------------------------------------------------------- harness
class Hang(BaseException):
    """A call ran past its time. BaseException, so the module's own `except Exception` can't swallow it."""


def _alarm(signum, frame):
    raise Hang()


HANGS = [0]
MAX_HANGS = 8


def load(path):
    spec = importlib.util.spec_from_file_location("under_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def outcome(fn, *args, limit=1.0):
    """("ok", value) or ("raise", name, exception); a call past `limit` seconds is ("raise", "Hang", ...)."""
    if HANGS[0] >= MAX_HANGS:
        return ("raise", "Hang", Hang())             # don't wait on a module that keeps hanging
    signal.signal(signal.SIGALRM, _alarm)
    signal.setitimer(signal.ITIMER_REAL, limit)
    try:
        return ("ok", fn(*args))
    except Hang:
        HANGS[0] += 1
        return ("raise", "Hang", Hang())
    except Exception as e:          # noqa: BLE001 - every exception is a result here
        return ("raise", type(e).__name__, e)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


def compare(results, want, got, label, same=lambda a, b: a == b):
    if want[0] == "ok":
        ok = got[0] == "ok" and same(got[1], want[1])
        results.append((ok, f"{label} -> {got[0]} {got[1]!r:.120}, expected {want[1]!r:.120}"))
    else:
        ok = got[0] == "raise" and isinstance(got[2], ValueError)
        results.append((ok, f"{label} -> {got[0]} {got[1]!r:.120}, expected ValueError"))


# ----------------------------------------------------------------------------- json
def _no_constant(name):
    raise ValueError(f"{name} is not a JSON number")


def ref_json(text):
    return json.loads(text, parse_constant=_no_constant)


def canon(v):
    """Type-exact form for comparing (True == 1 and 1 == 1.0 in Python, but not in JSON)."""
    if v is None or isinstance(v, bool):
        return (type(v).__name__, v)
    if isinstance(v, int):
        return ("int", v)
    if isinstance(v, float):
        return ("float", repr(v))
    if isinstance(v, str):
        return ("str", v)
    if isinstance(v, list):
        return ("list", [canon(x) for x in v])
    if isinstance(v, dict):
        return ("dict", sorted(((repr(k), canon(x)) for k, x in v.items()), key=lambda kv: kv[0]))
    return ("other", repr(v))


JSON_CHARS = ["a", "b", "Z", " ", '"', "\\", "/", "\n", "\t", "\x00", "\x1f", "\x7f", "é", " ",
              "\U0001F600", "\ud800", "\udfff", "A"]


def json_value(rng, depth=0):
    r = rng.random()
    if depth > 3 or r < 0.45:
        kind = rng.choice(("int", "float", "str", "lit"))
        if kind == "int":
            return rng.choice((0, 1, -1, rng.randint(-10 ** 6, 10 ** 6), rng.randint(-10 ** 20, 10 ** 20)))
        if kind == "float":
            return rng.choice((0.5, -0.0, 1e-07, 2.5e10, rng.uniform(-1e6, 1e6), rng.randint(1, 99) / 8))
        if kind == "str":
            return "".join(rng.choice(JSON_CHARS) for _ in range(rng.randint(0, 6)))
        return rng.choice((True, False, None))
    if r < 0.75:
        return [json_value(rng, depth + 1) for _ in range(rng.randint(0, 4))]
    return {"".join(rng.choice('abk"\\é') for _ in range(rng.randint(0, 3))): json_value(rng, depth + 1)
            for _ in range(rng.randint(0, 4))}


def json_text(rng, value):
    indent = rng.choice((None, None, 0, 2, "\t"))
    seps = rng.choice(((",", ":"), (", ", ": "), (" ,", " : "), (",\r\n", ":\t")))
    text = json.dumps(value, ensure_ascii=rng.random() < 0.5, indent=indent, separators=seps)
    pad = lambda: "".join(rng.choice(" \t\r\n") for _ in range(rng.choice((0, 0, 1, 3))))  # noqa: E731
    return pad() + text + pad()


def json_mutate(rng, text):
    i = rng.randrange(len(text) + 1)
    piece = rng.choice(list('{}[]:,"\\0123456789-+.eEtfnul \t\n\x0b/') + ["\\u", "\\ud800", "00", "NaN", "\x01"])
    op = rng.choice(("del", "ins", "rep"))
    if op == "del" and text:
        return text[:i] + text[i + 1:]
    if op == "ins":
        return text[:i] + piece + text[i:]
    return text[:i] + piece + text[i + 1:]


def json_number_text(rng):
    return (rng.choice(("", "", "-", "+", "--")) + rng.choice(("0", "1", "12", "01", "00", "", "9" * 25))
            + rng.choice(("", "", ".5", ".", ".05", "..5")) + rng.choice(("", "", "e5", "E-3", "e+0", "e", "e+", "E07")))


JSON_FIXED = [
    "0", "-0", "1", "-1", "123", "1.5", "-0.0", "1e5", "1E+5", "1e-5", "2.5E-3", "0.0", "10", "1.0e2",
    "01", "+1", ".5", "1.", "1e", "1e+", "-", "--1", "0x10", "1_000", "NaN", "Infinity", "-Infinity",
    "nan", "inf", "1.5.2", "00", "true", "false", "null", "True", "nul", "truex", '""', '"abc"',
    '"a\\"b"', '"\\\\"', '"\\/"', '"\\b\\f\\n\\r\\t"', '"\\u0041"', '"\\u00e9"', '"\\u00E9"',
    '"\\ud83d\\ude00"', '"\\ud83d"', '"\\ude00"', '"\\ud83dx"', '"\\ud83d\\u0041"', '"\\ude00\\ud83d"',
    '"\\ud83d\\ud83d\\ude00"', '"\\u12"', '"\\u12g4"', '"\\x41"', '"\\a"', '"a\nb"', '"a\tb"', '"a\x7fb"',
    '"unterminated', '"a"b"', "'a'", '"é"', "[]", "[1,2,3]", "[ 1 , 2 ]", "[1,]", "[,1]", "[1 2]",
    "{}", '{"a":1}', '{"a":1,"a":2}', '{"a":1,}', "{a:1}", '{"a" 1}', '{"a":}', "{1:2}", "[[[]]]",
    '{"a":[{"b":null}]}', " \t\n\r[1]\r\n ", "[1]\x0b", "﻿[1]", "", "   ", "[1] [2]", "[1]x",
    "[" * 40 + "]" * 40, '{"":0}', '["\\u0000"]', '{"a":{"a":{"a":[]}}}', "[-0, 0.5e-1, 1E2]",
]


def check_json(mod, rng):
    texts = list(JSON_FIXED)
    for _ in range(500):
        texts.append(json_text(rng, json_value(rng)))
    for _ in range(500):
        texts.append(json_mutate(rng, json_text(rng, json_value(rng))))
    for _ in range(150):
        num = json_number_text(rng)
        texts.append(num if rng.random() < 0.5 else f"[{num}]")
    results = []
    for t in texts:
        compare(results, outcome(ref_json, t), outcome(mod.parse_json, t), f"parse_json({t!r:.80})",
                same=lambda a, b: canon(a) == canon(b))
    return results


# ----------------------------------------------------------------------------- ipv6
def rfc5952(groups):
    """Canonical text for eight 16-bit groups: lowercase, no leading zeros, the longest run (leftmost on
    a tie) of two or more zero groups as ::."""
    best_start, best_len, i = -1, 0, 0
    while i < 8:
        if groups[i] == 0:
            j = i
            while j < 8 and groups[j] == 0:
                j += 1
            if j - i > best_len:
                best_start, best_len = i, j - i
            i = j
        else:
            i += 1
    parts = [format(g, "x") for g in groups]
    if best_len >= 2:
        return ":".join(parts[:best_start]) + "::" + ":".join(parts[best_start + best_len:])
    return ":".join(parts)


def ref_ipv6(text):
    if "%" in text:
        raise ValueError("zone index")
    packed = ipaddress.IPv6Address(text).packed      # AddressValueError is a ValueError
    return rfc5952([int.from_bytes(packed[i:i + 2], "big") for i in range(0, 16, 2)])


def ipv6_text(rng, groups):
    """One random valid way of writing the eight groups."""
    parts = [format(g, rng.choice(("x", "x", "X", "04x", "02x"))) for g in groups]
    hexes = 8
    if rng.random() < 0.25:
        hi, lo = groups[6], groups[7]
        parts = parts[:6] + [".".join(str(b) for b in (hi >> 8, hi & 255, lo >> 8, lo & 255))]
        hexes = 6
    runs, i = [], 0
    while i < hexes:
        if groups[i] == 0:
            j = i
            while j < hexes and groups[j] == 0:
                j += 1
            runs.append((i, j))
            i = j
        else:
            i += 1
    if runs and rng.random() < 0.75:
        s, e = rng.choice(runs)
        s2 = rng.randint(s, e - 1)
        e2 = rng.randint(s2 + 1, e)
        return ":".join(parts[:s2]) + "::" + ":".join(parts[e2:])
    return ":".join(parts)


def ipv6_groups(rng):
    return [rng.choice((0, 0, 0, 1, 0xffff, 0xabc, rng.randrange(65536))) for _ in range(8)]


def ipv6_mutate(rng, text):
    i = rng.randrange(len(text) + 1)
    piece = rng.choice(list(":.0123456789abcdefABCDEFg %") + ["::", "00000", "01", "256"])
    op = rng.choice(("del", "ins", "rep"))
    if op == "del" and text:
        return text[:i] + text[i + 1:]
    if op == "ins":
        return text[:i] + piece + text[i:]
    return text[:i] + piece + text[i + 1:]


IPV6_FIXED = [
    "::", "::1", "1::", "1:2:3:4:5:6:7:8", "1:0:0:2:0:0:0:3", "1:0:0:2:0:0:3:4", "0:0:1:0:0:0:0:2",
    "2001:DB8::1", "2001:0db8:0000:0000:0000:ff00:0042:8329", "::ffff:192.0.2.1", "::192.0.2.1",
    "1:2:3:4:5:6:1.2.3.4", "1:2:3:4:5:6:7:1.2.3.4", "::01.2.3.4", "::1.2.3.256", "::1.2.3", "1::2::3",
    ":1:2:3:4:5:6:7", "1:2:3:4:5:6:7:", "1:2:3:4:5:6:7:8:9", "12345::", "fe80::1%eth0", " ::1", "::1 ",
    "", ":", ":::", "1:2:3:4:5:6:7::", "::2:3:4:5:6:7:8", "0:0:0:0:0:0:0:1", "1:0:2:0:3:0:4:0", "g::",
    "::1.2.3.4.5", "1.2.3.4", "::ffff:1.2.3.4", "1:2:3:4:5:6:7:8::", "::1:2:3:4:5:6:7:8", "0::0",
    "1:2:3:4::5:6:7", "1:2:3:4:5::6:7:8", "abcd:ef01:2345:6789:ABCD:EF01:2345:6789", "::0:0:1",
    "1:2::3:4:0:0:0", "0:0:0:1:0:0:0:0", "::1.2.3.04", "::0.0.0.0", "::255.255.255.255",
]


def check_ipv6(mod, rng):
    texts = list(IPV6_FIXED)
    for _ in range(500):
        texts.append(ipv6_text(rng, ipv6_groups(rng)))
    for _ in range(400):
        texts.append(ipv6_mutate(rng, ipv6_text(rng, ipv6_groups(rng))))
    results = []
    for t in texts:
        compare(results, outcome(ref_ipv6, t), outcome(mod.normalize_ipv6, t), f"normalize_ipv6({t!r})")
    return results


# ----------------------------------------------------------------------------- regex
def _rx_char(p, j):
    """The character at p[j], or the one it escapes: (char, next index)."""
    if p[j] != "\\":
        return p[j], j + 1
    if j + 1 >= len(p):
        raise ValueError("backslash at the end")
    if p[j + 1].isalnum():
        raise ValueError("backslash before a letter or digit")
    return p[j + 1], j + 2


def ref_regex_translate(p):
    """Check the goal's syntax here and return an equivalent pattern for Python's re, which matches."""
    out, depth, prev, i, n = [], 0, "start", 0, len(p)
    while i < n:
        c = p[i]
        if c in "*+?":
            if prev in ("start", "open", "bar", "quant"):
                raise ValueError(f"nothing to repeat at {i}")
            out.append(c)
            prev, i = "quant", i + 1
        elif c == "(":
            out.append("(?:")
            depth, prev, i = depth + 1, "open", i + 1
        elif c == ")":
            if depth == 0:
                raise ValueError("unmatched )")
            out.append(")")
            depth, prev, i = depth - 1, "item", i + 1
        elif c == "|":
            out.append("|")
            prev, i = "bar", i + 1
        elif c == ".":
            out.append(".")
            prev, i = "item", i + 1
        elif c == "[":
            j, neg, parts, first = i + 1, False, [], True
            if j < n and p[j] == "^":
                neg, j = True, j + 1
            while True:
                if j >= n:
                    raise ValueError("class with no closing ]")
                if p[j] == "]" and not first:
                    j += 1
                    break
                lo, j = _rx_char(p, j)
                first = False
                if j + 1 < n and p[j] == "-" and p[j + 1] != "]":
                    hi, j = _rx_char(p, j + 1)
                    if hi < lo:
                        raise ValueError(f"range {lo}-{hi} goes backwards")
                    parts.append(re.escape(lo) + "-" + re.escape(hi))
                else:
                    parts.append(re.escape(lo))
            out.append("[" + ("^" if neg else "") + "".join(parts) + "]")
            prev, i = "item", j
        else:
            ch, i = _rx_char(p, i)
            out.append(re.escape(ch))
            prev = "item"
    if depth:
        raise ValueError("unmatched (")
    return "".join(out)


def ref_regex(pattern, text):
    py = ref_regex_translate(pattern)
    try:
        return re.fullmatch(py, text) is not None
    except re.error as e:            # not expected: the translation has checked the syntax
        raise ValueError(str(e)) from None


def rx_gen(rng, depth=0):
    """A random valid pattern and a sampler that returns a text it matches."""
    alts = [rx_seq(rng, depth) for _ in range(rng.choice((1, 1, 1, 2, 3)))]
    return "|".join(a for a, _ in alts), (lambda r: r.choice(alts)[1](r))


def rx_seq(rng, depth):
    parts = []
    for _ in range(rng.randint(0, 3)):
        item, sample = rx_item(rng, depth)
        q = rng.choice(("", "", "", "*", "+", "?"))
        parts.append((item + q, rx_repeat(sample, q)))
    return "".join(p for p, _ in parts), (lambda r: "".join(s(r) for _, s in parts))


def rx_repeat(sample, q):
    lo, hi = {"": (1, 1), "*": (0, 3), "+": (1, 3), "?": (0, 1)}[q]
    return lambda r: "".join(sample(r) for _ in range(r.randint(lo, hi)))


def rx_item(rng, depth):
    kind = rng.choice(("chr", "chr", "chr", "any", "cls", "esc") + (("grp",) if depth < 2 else ()))
    if kind == "chr":
        ch = rng.choice("abc")
        return ch, (lambda r: ch)
    if kind == "any":
        return ".", (lambda r: r.choice("abc.-*"))
    if kind == "esc":
        ch = rng.choice(".*+?()[]|\\-")
        return "\\" + ch, (lambda r: ch)
    if kind == "grp":
        pat, sample = rx_gen(rng, depth + 1)
        return f"({pat})", sample
    members = rng.sample(["a", "b", "c", ".", "*", "(", "|", "x"], rng.randint(1, 3))
    listed = list(members)
    body = "".join(members)
    if rng.random() < 0.4:
        rg = rng.choice(("a-c", "b-c", "a-b", "x-z"))
        body += rg
        listed += [chr(c) for c in range(ord(rg[0]), ord(rg[2]) + 1)]
    if rng.random() < 0.15:
        body, listed = "]" + body, listed + ["]"]
    if rng.random() < 0.15:
        body, listed = body + "-", listed + ["-"]
    if rng.random() < 0.3:
        outside = [c for c in "abcxyz.*-]\n#" if c not in listed]
        return "[^" + body + "]", (lambda r: r.choice(outside))
    return "[" + body + "]", (lambda r: r.choice(listed))


RX_TEXT = "abc.-*]\n"
RX_FIXED = [
    ("", ["", "a"]), ("a", ["a", "", "aa", "b"]), ("abc", ["abc", "ab"]), ("a.c", ["abc", "a\nc", "ac"]),
    (".", ["\n", "a", ""]), ("[abc]", ["b", "d", ""]), ("[a-c]", ["b", "d"]), ("[^a-c]", ["d", "b", "\n"]),
    ("[]a]", ["]", "a", "b"]), ("[^]a]", ["]", "b"]), ("[a-]", ["-", "a", "b"]), ("[-a]", ["-", "a"]),
    ("\\.", [".", "a"]), ("[\\]]", ["]", "\\"]), ("[\\\\]", ["\\", "]"]), ("a*", ["", "aaa", "ab"]),
    ("a+", ["", "a", "aa"]), ("a?", ["", "a", "aa"]), ("(ab)*", ["", "abab", "aba"]),
    ("(a|b)+c", ["abac", "c"]), ("(a|ab)c", ["abc", "ac"]), ("(a*)*", ["", "aaa", "b"]),
    ("(a*)*b", ["aab", "b", "aaa"]), ("(a|)+", ["", "aa"]), ("a||b", ["", "a", "b", "ab"]),
    ("(|a)", ["", "a"]), ("()", ["", "a"]), ("(()*)*", ["", "a"]), ("a**", ["a"]), ("*a", ["a"]),
    ("(*a)", ["a"]), ("a|*b", ["b"]), ("(a", ["a"]), ("a)", ["a"]), ("[abc", ["a"]), ("[]", [""]),
    ("[^]", [""]), ("[z-a]", ["b"]), ("a\\", ["a"]), ("\\d", ["d"]), ("\\1", ["1"]), ("^a$", ["^a$", "a"]),
    ("a{2}", ["a{2}", "aa"]), (" a b", [" a b"]), ("[.]", [".", "a"]), ("[*]", ["*"]), ("a*?", ["a"]),
    ("a+?", ["a"]), ("a??", ["a"]), ("a*+", ["a"]), ("(a)(b)", ["ab"]), ("((a|b)c)*", ["acbc", "ab"]),
    ("x\ny", ["x\ny", "xy"]), ("[a-c-]", ["-", "b"]), ("[]-a]", ["^", "b"]), ("\\(\\)", ["()"]),
    ("a|b|", ["", "c"]), ("((a))+", ["aa"]), ("(a|b)*a(a|b)", ["ab", "bab", "a"]), ("[\\-a]", ["-", "b"]),
    ("(a+)+b", ["aaab", "aaa"]), ("(?:a)", ["a"]), ("\\é", ["é"]),
]


def check_regex(mod, rng):
    cases = [(p, t) for p, texts in RX_FIXED for t in texts]
    for _ in range(300):
        pat, sample = rx_gen(rng)
        for _ in range(3):
            t = sample(rng)
            if rng.random() < 0.3 and t:                     # a near miss
                i = rng.randrange(len(t))
                t = t[:i] + rng.choice(RX_TEXT) + t[i + 1:]
            cases.append((pat, t))
        for _ in range(2):
            cases.append((pat, "".join(rng.choice(RX_TEXT) for _ in range(rng.randint(0, 6)))))
    for _ in range(150):
        pat = "".join(rng.choice("ab.*+?()[]|\\-^") for _ in range(rng.randint(1, 7)))
        for _ in range(2):
            cases.append((pat, "".join(rng.choice("ab.-*]") for _ in range(rng.randint(0, 5)))))
    results = []
    for p, t in cases:
        compare(results, outcome(ref_regex, p, t), outcome(mod.full_match, p, t), f"full_match({p!r}, {t!r})",
                same=lambda a, b: a is b)
    return results


CHECKS = {"json": check_json, "ipv6": check_ipv6, "regex": check_regex}


def selfcheck():
    """The parts of the references that aren't the standard library, checked against it."""
    rng = random.Random(1)
    bad = 0
    for _ in range(3000):
        text = ipv6_text(rng, ipv6_groups(rng))
        if ipaddress.IPv6Address(text).ipv4_mapped:      # Python prints those dotted; the goal says never
            continue
        if ref_ipv6(text) != ipaddress.IPv6Address(text).compressed:
            bad += 1
            print("IPV6 FORMAT MISMATCH", text, ref_ipv6(text), ipaddress.IPv6Address(text).compressed)
    for _ in range(3000):                                  # generated patterns must be valid and sampled right
        pat, sample = rx_gen(rng)
        t = sample(rng)
        if not ref_regex(pat, t):
            bad += 1
            print("REGEX SAMPLE NOT MATCHED", repr(pat), repr(t))
    print("SELFCHECK", "OK" if not bad else f"{bad} problems")


if __name__ == "__main__":
    if sys.argv[1:] == ["selfcheck"]:
        selfcheck()
        sys.exit(0)
    task, path = sys.argv[1], sys.argv[2]
    try:
        mod = load(path)
        results = CHECKS[task](mod, random.Random(20261101))
    except Exception as e:          # noqa: BLE001
        print(f"SCORE 0/1 (could not run: {type(e).__name__}: {e})")
        sys.exit(0)
    bad = [msg for ok, msg in results if not ok]
    print(f"SCORE {len(results) - len(bad)}/{len(results)}" + (f" ({HANGS[0]} timeouts)" if HANGS[0] else ""))
    for msg in bad[:6]:
        print("  MISMATCH", msg[:300])
