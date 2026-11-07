"""Fifth test battery: three fresh tasks with exact standard-library references, to test the pipeline's v3
changes (restarts, per-test re-tests, final pick, stand-in checks) on goals they were not tuned on (set 4).
Each goal is long and dense with rules taken from the reference's real behaviour (checked in the sandbox's
Python 3.11.18 and zlib 1.3.1). Run inside the sandbox (the module under test is pipeline-written code):
    python3 battery5_checks.py TASK /work/<file>.py        (TASK: fmtspec, strptime or inflate)
Prints `SCORE passed/total`, a `PARTS` line with the score per kind of case, and up to 6 mismatches.
The cases are the same on every run (fixed seeds), so the levels are compared on identical inputs.

References: fmtspec - format(); strptime - datetime.strptime; inflate - zlib.decompress with zlib.error
mapped to ValueError. All are computed before the candidate is imported. Every call to the candidate runs
in a forked child with a time and memory limit, so a crash, a hang or a runaway allocation costs only that
case. Validate changes with `python3 battery5_checks.py selfcheck` and the stubs in tests/stubs5/: every
`*_ok.py` must score in full and every `*_bad_*.py` must not (mkvariants5.py writes the bad ones). The ok
stubs are written from the goals alone, without the reference modules, so a full score also shows that
each goal states every rule its cases depend on."""
import datetime
import importlib.util
import os
import pickle
import random
import select
import signal
import string
import struct
import sys
import time
import warnings
import zlib

try:                                   # Linux only; battery.py imports this module on Windows for GOALS
    import resource
except ImportError:
    resource = None

GOALS = {
    "fmtspec": (
        "Create a Python module with fmt(value, spec) -> str that returns exactly what Python 3.11's built-in "
        "format(value, spec) returns, where value is an int, float or str (never a bool) and spec is a format "
        "specification (the part after ':' in a replacement field), without using format(), str.format, "
        "format_map, f-strings with a format spec, % formatting, __format__, or the string, decimal or locale "
        "modules (str(), repr(), int(), hex(), oct(), bin(), float.as_integer_ratio(), fractions and math are "
        "allowed). Grammar: [[fill]align][sign][z][#][0][width][grouping][.precision][type]; fill is any one "
        "character and only counts as a fill when an align character < > = ^ follows it; sign is + - or space; "
        "grouping is , or _. Types: for an int b c d o x X, none (like d) and the float types e E f F g G % (the "
        "int is converted to float first, and one too large for a float raises OverflowError); for a float e E "
        "f F g G % and none; for a str s and none. Numbers align right by default, strings left; ^ puts the "
        "extra fill character on the right. The 0 flag, when no fill is given, makes the fill 0 and, for a "
        "number with no align character, the alignment = (padding goes after the sign and any prefix); a string "
        "keeps its alignment (format('ab', '05') == 'ab000', format('ab', '>05') == '000ab'). When the fill is "
        "0 and the alignment = (from the 0 flag or written as 0=) and a grouping is given, the padding zeros "
        "count as digits and are grouped too, and if the width would be reached right at a separator one more "
        "0 is added, so the result never starts with a separator (format(1234, '010,') == '00,001,234', "
        "format(1234, '08,') == '0,001,234', format(255, '#010_x') == '0x000_00ff'). Grouping separates the "
        "integer part's digits in threes, or in fours for _ with b o x X. # adds the prefix 0b 0o 0x or 0X to "
        "b o x X (inside the width, before the zero padding). c gives chr(value) and raises OverflowError for "
        "values outside range(0x110000). Floats: f F e E % are rounded exactly from the float's binary value, "
        "half to even (format(2.675, '.2f') == '2.67', format(0.125, '.2f') == '0.12', format(2.5, '.0f') == "
        "'2'); the default precision is 6; exponents have a sign and at least two digits (1e+05, 1e-300). g G "
        "with precision p (0 counts as 1; default 6) round to p significant digits, then use scientific "
        "notation if the rounded value's exponent x is < -4 or >= p, else fixed; trailing zeros, and a point "
        "left at the end, are removed unless # is given. With no type and no precision a float prints the "
        "digits of repr() (scientific when x < -4 or x >= 16); with no type and a precision p it works like g "
        "but uses scientific notation when x >= p - 1 and always keeps at least one digit after the point in "
        "fixed notation (format(100.0, '.3') == '1e+02', format(1.0, '.3') == '1.0', format(1e16, '.17') == "
        "'1e+16'). % multiplies by 100 as a float multiplication (value * 100 rounded to the nearest float, as "
        "Python's * does), formats that like f and appends %. # keeps the decimal point even with no digits "
        "after it (format(1.0, '#.0f') == '1.', format(1.0, '#.0e') == '1.e+00', format(1e16, '#') == "
        "'1.e+16'). inf and nan print as inf and nan (INF and NAN for E F G), a nan's sign is ignored, and they "
        "are padded like other numbers, zeros included (format(float('-inf'), '010') == '-000000inf'). z turns "
        "a result that is negative zero after rounding into positive zero (format(-0.001, 'z.1f') == '0.0'). "
        "For a str, the precision is the maximum number of characters kept. Errors, all ValueError: a precision "
        "with an int type (b c d o x X or none); z with an int type or a str; a sign, #, = alignment or "
        "grouping with a str; a sign or # with c; grouping with c, or , with b o x X; both , and _; a . with no "
        "digits after it; a type the value's type doesn't support; anything else that doesn't fit the grammar. "
        "These ValueErrors take precedence over the OverflowErrors (format(-1, '+c') raises ValueError). The "
        "type n never appears, and ints formatted in decimal have at most 4,300 digits (the most str() converts in "
        "Python 3.11), while b o x X may get much longer ones. Command line: python <script> VALUE SPEC (VALUE read as an int if it can be, "
        "else a float, else a str) prints the result. In --test mode check every type, alignment and flag, "
        "rounding ties, grouping with zero padding, and the error cases."),
    "strptime": (
        "Create a Python module with strptime(text, fmt) -> datetime.datetime that returns exactly what Python "
        "3.11's datetime.datetime.strptime(text, fmt) returns in the C locale (English names), without using "
        "datetime.strptime, time.strptime, the _strptime module or any date-parsing library (the datetime "
        "classes, calendar and re are allowed). Directives, each with the forms it accepts as regular "
        "expressions tried in this order: %d 3[01]|[12]\\d|0[1-9]|[1-9]| [1-9]; %m 1[0-2]|0[1-9]|[1-9]; %y \\d\\d "
        "(00-68 mean 2000-2068, 69-99 mean 1969-1999); %Y \\d\\d\\d\\d; %H 2[0-3]|[01]\\d|\\d; %I 1[0-2]|0[1-9]|[1-9]; "
        "%M [0-5]\\d|\\d; %S 6[01]|[0-5]\\d|\\d; %f [0-9]{1,6} (padded with zeros on the right to microseconds); %j "
        "36[0-6]|3[0-5]\\d|[12]\\d\\d|0[1-9]\\d|00[1-9]|[1-9]\\d|0[1-9]|[1-9]; %U and %W 5[0-3]|[0-4]\\d|\\d; %V "
        "5[0-3]|0[1-9]|[1-4]\\d|\\d; %G \\d\\d\\d\\d; %w [0-6] (0 is Sunday); %u [1-7] (1 is Monday); %a and %A the "
        "abbreviated and full weekday names, %b and %B the abbreviated and full month names (Mon, Monday, Jan, "
        "January, ...; longer names are tried first); %p AM or PM; %z an offset: Z (uppercase only), or + or - "
        "then two digits of hours, an optional colon, minutes [0-5]\\d, and optionally seconds (an optional "
        "colon and [0-5]\\d) followed by an optional fraction of 1 to 6 digits after a point; %% a literal %. "
        "Matching works like CPython's: the format becomes one regular expression, matched case-insensitively "
        "from the start of the text with backtracking (as re.match does), so ambiguous digit runs resolve by "
        "the order above ('112' with '%m%d' is November 2, '13' is January 3); the first match must end at the "
        "end of the text, else ValueError. A run of whitespace in the format matches one or more whitespace "
        "characters; any other character matches itself, letters in either case (names too). A % followed by "
        "a character not listed above, or a % at the end of the format, raises ValueError; formats never repeat "
        "a directive. Fields: when several directives set the same field (%Y and %y; %m %b and %B; %H and %I; "
        "%a %A %w and %u; %U and %W) the one that comes last in the format wins. %I with PM adds 12 except to "
        "12; %I with AM or with no %p turns 12 into 0; %p without %I is ignored. Missing fields default to "
        "year 1900, month 1, day 1, time 00:00:00.000000 and no tzinfo; February 29 with no year directive "
        "raises ValueError. The date: %j, if present, wins over month and day (day j of the year, counting on "
        "into the next year: 366 in a common year is January 1 of the next). Else %U or %W together with a "
        "weekday directive give it: with weeks starting on Sunday for %U and Monday for %W, let f be January "
        "1's weekday and d the given weekday, both counted 0-6 from the week's first day; week 0 is day "
        "1 + d - f of the year and week n >= 1 is day 1 + (7 - f) % 7 + 7 * (n - 1) + d, counting back into "
        "the previous year for days <= 0 and on into the next past the year's end. %U or %W without a weekday "
        "directive is ignored, and a weekday that doesn't match the resulting date is ignored. %G (ISO year) "
        "needs %V (ISO week) and a weekday directive and gives the ISO date, rolling into the next or previous "
        "year when the week is past the last ISO week or is 0 ('2023 53 1' with '%G %V %u' is 2024-01-01); %G "
        "without %V or without a weekday, %G with %j, and %V without %G raise ValueError (tests never combine "
        "%G or %V with %Y %y %U %W %m %d %b or %B). %z sets tzinfo to datetime.timezone(offset) (an offset of "
        "zero gives timezone.utc); its colons must be used consistently (+05:3015 and +0530:15 raise "
        "ValueError); the sign applies to every part, fraction included. A value out of range (February 30, "
        "second 60 or 61, year 0, a date past year 9999, an offset of 24 hours or more) raises ValueError. "
        "Command line: python <script> TEXT FORMAT prints repr() of the result. In --test mode check every "
        "directive, the ambiguous and case-insensitive matching, the week and ISO rules, %z, and the errors."),
    "inflate": (
        "Create a Python module with decompress(data, wbits=15) -> bytes that returns exactly what Python's "
        "zlib.decompress(data, wbits) returns (zlib 1.3.1) for wbits 15 (zlib format, RFC 1950), -15 (raw "
        "deflate, RFC 1951) and 31 (gzip format, RFC 1952), and raises ValueError wherever zlib.decompress "
        "raises zlib.error, without using the zlib, gzip, zipfile, binascii, bz2 or lzma modules or any "
        "compression library. Only the first stream is decoded: bytes after its end are ignored, a second gzip "
        "member included. zlib format: a 2-byte header CMF FLG with (CMF * 256 + FLG) % 31 == 0, compression "
        "method 8 in CMF's low 4 bits and a window size CINFO (the high 4 bits) of at most 7 (smaller values "
        "are fine), FDICT (FLG bit 5) not set (a preset dictionary is an error), FLEVEL ignored; then the "
        "deflate data and the Adler-32 of the output, 4 bytes big-endian. gzip format: bytes 1f 8b, method 8, "
        "a flag byte whose reserved bits 0xe0 must be zero, MTIME XFL and OS ignored, then the optional parts "
        "in this order: FEXTRA (flag 4: a 2-byte little-endian length and that many bytes), FNAME (8) and "
        "FCOMMENT (16) (each zero-terminated), FHCRC (2: two bytes that must equal the low 16 bits of the "
        "CRC-32 of all the header bytes before them; FTEXT, flag 1, is ignored); then the deflate data, the "
        "CRC-32 of the output and its length mod 2**32, 4 bytes little-endian each. Deflate: stored blocks (the "
        "rest of the byte after the block header is skipped; LEN and NLEN must be one's complements), fixed "
        "Huffman and dynamic Huffman blocks; block type 3 is an error. Dynamic block headers: HLIT > 286 or "
        "HDIST > 30 is an error; the code-length code must be a complete prefix code; the literal/length and "
        "distance code lengths form one sequence (the repeat codes 16, 17 and 18 may run from one into the "
        "other; a 16 with no previous length, or a repeat past the end, is an error); the end-of-block symbol "
        "256 must have a nonzero length; a literal/length or distance code that is over-subscribed is an "
        "error, and an incomplete one is an error too unless it has exactly one code and that code has length "
        "1 (reading the unused bit pattern is then an error); the distance code lengths may all be zero (reading "
        "a distance is then an error). Decoding errors: literal/length symbols 286 and 287 and distance "
        "symbols 30 and 31 (possible in fixed blocks), a distance reaching back before the start of the "
        "output, and input that ends before the stream does (a truncated header, block or trailer, or empty "
        "input). Big inputs must work: outputs of several megabytes in a few seconds. Command line: python "
        "<script> FILE [WBITS] writes the decompressed bytes to stdout. In --test mode check all three formats, "
        "all block types, the header options, and corrupt and truncated streams."),
}


# ------------------------------------------------------------------------------------------- harness
class Hang(BaseException):
    """Raised by the alarm when a reference call runs past its limit."""


def _on_alarm(signum, frame):
    raise Hang()


def mro(e):
    return [c.__name__ for c in type(e).__mro__]


def _disarm():
    while True:
        try:
            signal.setitimer(signal.ITIMER_REAL, 0)
            return
        except Hang:
            continue


def call(fn, args, limit):
    """fn(*args) in this process under an alarm: ('ok', value), ('err', [exception class names]) or
    ('hang', None). Only for trusted code (the references) and the import."""
    res = ("hang", None)
    try:
        signal.setitimer(signal.ITIMER_REAL, limit, 0.05)
        try:
            res = ("ok", fn(*args))
        except Hang:
            res = ("hang", None)
        except BaseException as e:  # noqa: B902 - SystemExit and RecursionError count as raised
            res = ("err", mro(e))
        _disarm()
    except Hang:
        _disarm()
    return res


def isolated(fn, args, limit, mem=1536 << 20):
    """fn(*args) in a forked child with a time and address-space limit."""
    rfd, wfd = os.pipe()
    pid = os.fork()
    if pid == 0:
        try:
            os.close(rfd)
            signal.setitimer(signal.ITIMER_REAL, 0)
            try:
                resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
            except (ValueError, OSError):
                pass
            try:
                res = ("ok", fn(*args))
            except BaseException as e:  # noqa: B902
                res = ("err", mro(e))
            try:
                data = pickle.dumps(res, protocol=pickle.HIGHEST_PROTOCOL)
            except BaseException:  # noqa: B902
                data = pickle.dumps(("ok", f"<unpicklable {type(res[1]).__name__}>"))
            view = memoryview(data)
            while view:
                view = view[os.write(wfd, view):]
        finally:
            os._exit(0)
    os.close(wfd)
    chunks, deadline = [], time.monotonic() + limit
    try:
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)
                return ("hang", None)
            if select.select([rfd], [], [], left)[0]:
                chunk = os.read(rfd, 1 << 20)
                if not chunk:
                    break
                chunks.append(chunk)
    finally:
        os.close(rfd)
    _, status = os.waitpid(pid, 0)
    if not chunks:
        return ("crash", f"exit status {status}")
    try:
        return pickle.loads(b"".join(chunks))
    except Exception:  # noqa: BLE001
        return ("crash", "unreadable result")


def expect(ref, args, kinds):
    """The reference's outcome: ('ok', v), ('err', the first of kinds the exception is), or None when the
    case is unusable (a TypeError, or a reference failure the goal doesn't cover)."""
    res = call(ref, args, 30.0)
    if res[0] == "ok":
        return res
    if res[0] == "err":
        for k in kinds:
            if k in res[1]:
                return ("err", k)
    return None


def short(v, n=110):
    if isinstance(v, int) and not isinstance(v, bool) and v.bit_length() > 300:
        return f"<int of {v.bit_length()} bits>"
    try:
        s = repr(v)
    except Exception:  # noqa: BLE001
        s = f"<unprintable {type(v).__name__}>"
    return s if len(s) <= n else s[:n] + "..."


def show(res):
    kind, v = res
    if kind == "err":
        return f"raised {v if isinstance(v, str) else v[0]}"
    if kind == "hang":
        return "no answer in time"
    if kind == "crash":
        return f"crashed ({v})"
    return short(v)




# ------------------------------------------------------------------------------------------- fmtspec
FMT_KINDS = ("ValueError", "OverflowError")
NAN, INF = float("nan"), float("inf")
FMT_FIXED = [
    (5, '<05'), ('ab', '05'), ('ab', '>05'), ('ab', 'x<05'), (0xffffff, '_x'), (1234567, '_d'), (65, 'c'),
    (65, '>3c'), (-0.0, 'z'), (-0.001, 'z.1f'), (-0.0, 'z.0e'), (1e16, ''), (1e16, '>8'), (123.0, '.3'),
    (1.0, '.3'), (100.0, '.3'), (1e15, ''), (1.5e-5, ''), (0.0001, ''), (NAN, '010'), (-INF, '010'), (INF, '+'),
    (NAN, 'F'), (NAN, '+.2e'), (0.5, '%'), (0.5, '.0%'), (1, '%'), (0.125, '.1%'), (1.0, '#g'), (1.0, '#.0f'),
    (1.0, '#'), (1.0, '#.0e'), (0.0001, 'g'), (1e-5, 'g'), (1234.5, ',e'), (1234567.891, ',.2f'), (1234567.0, ',g'),
    (123456.0, ',g'), (1234, '010,'), (1234, '09,'), (1234, '08,'), (255, '#010_x'), (-1234, '010,'),
    (1234.5, '012,.1f'), (2.675, '.2f'), (0.125, '.2f'), (2.5, '.0f'), (3.5, '.0f'), ('hello', '.2'),
    ('hello', '>8.2'), ('hi', '^5'), (5, '^4'), (5, '{>3'), (-42, '=6'), (255, '=#8x'), (-255, '#x'), (10, '.2f'),
    (10, 'g'), (10, 'e'), (-10, '+'), (10, ' '), (1.5, '_f'), (1, '_e'), (12345.678, '_.1f'), (1, '0'), (1, '00'),
    (1, '='), (123, '=+08_'), (-0.0, '+'), (-0.0, ' z'), (5, '-^7'), (-5.5, '^+9.2f'), (1e22, 'f'), (1e-7, '.3'),
    (5e-324, ''), (1.0, '.0'), (1.0, '#.0'), (15.0, '.1'), (9.5, '.0e'), (0.0, 'e'), (1, '+#x'), (1e16, '.17'),
    (123.456, '.5'), (1, '#'), (0, '#b'), (5, '#_b'), (255, '_X'), (12345, ',.2f'), ('x', '0'), ('x', '<0'),
    (1.5, ''), (-1.5, '010'), (1e100, ',.0f'), (1e16, '#'), (-NAN, '+'), (-NAN, ''), (0.07, '%'), (0.07, '.17%'),
    (1.005, '.2f'), (0.5, '.0f'), (1.5, '.0f'), (-0.5, '.0f'), (-0.5, 'z.0f'), (123.456, '#.3g'), (0.0, '#'),
    (0.0, '.0'), (1234567, ','), (12345678, '_b'), (-12345678, '#_o'), (255, '#X'), (0, '#o'), (65, '^5c'),
    (0x1F600, 'c'), (10, '^7'), (-10, '^8'), (-10, '=8'), (-10, '08'), (-10, '+08'), (10, ' 08'), (10, '=+8'),
    (3.14159, '=+12.3f'), (3.14159, '012,.3f'), (1234.5678, '_.2f'), (1e6, ',.0f'), (1e6, ','), (1e6, '_g'),
    (12345.0, ',.2%'), (INF, ',.2f'), (NAN, '=+08'), (INF, 'E'), (NAN, 'G'), (-0.0, '+z.2f'), (-1e-10, 'z.3f'),
    (-1e-10, 'z.3e'), ('', '5'), ('', '.0'), ('héllo', '^9.3'), ('x', '*^4'), ('abc', '0^7'), ('abc', '<07'),
    (5, 'x>05'), (5, '0>05'), (5, '0<5'), (5, '1>3'), (1234, '0>10,'), (1234, '0=10,'), (1234, '0<10,'),
    (-1234, '0=10,'), (1234, '+010,'), (1234.5, '+012,.1f'), (999999.5, 'g'), (9.9995, '.4'), (0.00009999995, 'g'),
    (2.0 ** 60, ''), (2.0 ** 60, 'f'), (1e-300, '.3g'), (99.95, '.1f'), (0.95, '.0%'), (1e16, ',g'),
    (7, '#010b'), (-7, '#010b'), (7, '+#o'), (300, '=^9'), (1.25, '^+10.1f'), (-1.25, 'z^10.1f'),
    # errors
    (12, '.2'), (12, '.2d'), (-1, 'c'), (0x110000, 'c'), (65, '+c'), (65, '#c'), (65, ',c'), (65, '_c'),
    (10 ** 400, 'e'), (5, 'z'), ('a', 'z'), ('ab', '=5'), (255, ',x'), (1, ',_'), (1, '_,'), ('a', '+'), ('a', '#'),
    ('a', ','), ('a', 'd'), (1.5, 'd'), (1.5, 's'), (1, 's'), (1.5, '#x'), (5, '10.'), (5.0, '.f'), (5, 'abc'),
    (-1, '+c'), (2 ** 70, 'c'), (2 ** 70, '.1c'), (10 ** 400, ',_f'), (10 ** 400, '.2f'), (5, '<<<5'), (5, 'x5'),
    (5.0, '5.2.1f'), (5.5, '%%'), ('a', ' '), (-10 ** 400, '%'), (5, '.2x'), (5.0, 'c'), ('a', 's5'), (5, '0=c'),
]
INT_TYPES = ["d", "", "", "b", "o", "x", "X", "c", "e", "E", "f", "F", "g", "G", "%"]
FLOAT_TYPES = ["e", "E", "f", "F", "g", "G", "%", "", "", ""]
FILLS = ['', '', '', ' ', '*', '0', '0', 'x', '{', '}', '_', ',', '.', '#', 'é', '1', '<', '=']
SPECIAL_FLOATS = [0.0, -0.0, INF, -INF, NAN, -NAN, 5e-324, 2.2250738585072014e-308, 1.7976931348623157e308,
                  1e16, 9999999999999998.0, 1e15, 0.0001, 0.00001, 9.5, 0.5, 1.5, 2.5, 99.95, 0.95, 1e-7,
                  123456789.0, 1e22, 1e23, 0.1, 0.2, 0.3, 1 / 3, 2 / 3, 2.675, 1.005]


def ref_fmt(value, spec):
    return format(value, spec)


def f_spec_num(rng, t):
    """A spec for a number with type t, built to be valid most of the time."""
    s = ""
    if rng.random() < 0.45:
        s += rng.choice(FILLS) + rng.choice("<>=^")
    if t != "c" and rng.random() < 0.4:
        s += rng.choice("+- ")
    if t in "eEfFgG%" and rng.random() < 0.2:
        s += "z"
    if t != "c" and rng.random() < 0.3:
        s += "#"
    if rng.random() < 0.3:
        s += "0"
    if rng.random() < 0.6:
        s += str(rng.randint(0, 30))
    if t != "c" and rng.random() < 0.35:
        s += "_" if t in "boxX" else rng.choice(",_")
    if t in "eEfFgG%" and rng.random() < 0.65:
        s += "." + str(rng.choice([0, 0, 1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 17, 20, 25]))
    return s + t


def f_spec_str(rng):
    s = ""
    if rng.random() < 0.5:
        s += rng.choice(FILLS) + rng.choice("<>^")
    if rng.random() < 0.25:
        s += "0"
    if rng.random() < 0.7:
        s += str(rng.randint(0, 20))
    if rng.random() < 0.4:
        s += "." + str(rng.randint(0, 8))
    return s + rng.choice(["", "s"])


def f_int(rng, t):
    if t == "c":
        v = rng.choice([65, 97, 48, 32, 10, 0, 0x263A, 0x1F600, 0x10FFFF, rng.randint(32, 0xD7FF),
                        rng.randint(0xE000, 0x2FFFF)])
        return v
    r = rng.random()
    if r < 0.1:
        return rng.choice([0, 1, -1, 7, -7, 10, 255, -255, 1000, -1000, 65535, 2 ** 31, -2 ** 63, 10 ** 18])
    if r < 0.5:
        return rng.randint(-10 ** 6, 10 ** 6)
    if r < 0.8:
        return rng.choice([-1, 1]) * rng.getrandbits(rng.randint(1, 100))
    return rng.choice([-1, 1]) * (10 ** rng.randint(1, 40) + rng.randint(-5, 5))


def f_float(rng):
    r = rng.random()
    if r < 0.15:
        return rng.choice(SPECIAL_FLOATS)
    if r < 0.35:                                       # exact ties at some decimal position
        return rng.choice([-1, 1]) * rng.randrange(1, 2000, 2) / 2 ** rng.randint(1, 12)
    if r < 0.6:
        return round(rng.uniform(-1e5, 1e5), rng.randint(0, 6))
    if r < 0.85:
        return rng.choice([-1, 1]) * rng.random() * 10.0 ** rng.randint(-25, 25)
    return struct.unpack("<d", struct.pack("<Q", rng.getrandbits(64)))[0]


def f_text(rng):
    pool = string.ascii_letters + string.digits + " .,-_*{}<>=^%#éß漢☃"
    return "".join(rng.choice(pool) for _ in range(rng.choice([0, 1, 2, 3, 5, 8, 12])))


def f_bad_spec(rng):
    """A spec with one deliberate error, and a value for it."""
    k = rng.randrange(12)
    if k == 0:
        return f_int(rng, "d"), rng.choice(["", ">", "+", "#"]) + str(rng.randint(0, 9)) + "." + str(rng.randint(0, 9)) + rng.choice(["", "d", "x", "b", "o", "X", "c"])
    if k == 1:
        return rng.choice([f_int(rng, "d"), f_text(rng)]), rng.choice(["z", "z5", "+z", "z#x", "zd", "zs"])
    if k == 2:
        return f_text(rng), rng.choice(["+", "-", " ", "#", "=", "0=", ",", "_", "+5", "#8", "=9", ",s", "_5s"])
    if k == 3:
        return f_int(rng, "c"), rng.choice(["+c", "-c", " c", "#c", ",c", "_c", ".2c", "z c", "0+5c"])
    if k == 4:
        return f_int(rng, "d"), rng.choice([",x", ",b", ",o", ",X", "#,x", "08,b"])
    if k == 5:
        return rng.choice([f_int(rng, "d"), f_float(rng)]), rng.choice([",_", "_,", "10,_d", ",_f", "_,g"])
    if k == 6:
        return rng.choice([f_int(rng, "d"), f_float(rng), f_text(rng)]), rng.choice([".", "10.", ".f", ".e", ">5.", ".%"])
    if k == 7:
        return f_float(rng), rng.choice(["d", "x", "b", "o", "X", "c", "s", "5d", "#x"])
    if k == 8:
        return f_text(rng), rng.choice(["d", "f", "e", "x", "%", "c", "g", "5d"])
    if k == 9:
        return rng.choice([f_int(rng, "d"), f_float(rng)]), rng.choice(["x5", "5.2.1f", "<<<5", "abc", "==5", "+-5", "5 ", " +5", "%%", "1e", "q", "0x"])
    if k == 10:
        return rng.choice([-1, -65, 0x110000, 2 ** 40, -2 ** 70]), rng.choice(["c", ">3c", "0=5c", "^c", "+c"])
    return rng.choice([10 ** 309, -10 ** 400, 2 ** 1024]), rng.choice(["e", "f", "g", "%", ".3E", "+012,.2f", ",_f", ".2d"])


def fmt_cases():
    rng = random.Random(5)
    cases = []

    def add(part, value, spec, mode="iso", limit=2.0):
        exp = expect(ref_fmt, (value, spec), FMT_KINDS)
        if exp is None:
            return
        if part in ("int", "float", "str") and exp[0] == "err":
            part = "invalid"
        cases.append((part, "fmt", (value, spec), exp, mode, limit))

    for value, spec in FMT_FIXED:
        add("fixed", value, spec)
    for _ in range(320):
        t = rng.choice(INT_TYPES)
        add("int", f_int(rng, t), f_spec_num(rng, t))
    for _ in range(420):
        add("float", f_float(rng), f_spec_num(rng, rng.choice(FLOAT_TYPES)))
    for _ in range(160):
        add("str", f_text(rng), f_spec_str(rng))
    for _ in range(220):
        add("invalid", *f_bad_spec(rng))
    for value, spec in [(10 ** 4000 + 12345, ','), (-(10 ** 4200) + 7, '_d'), (10 ** 5000, 'x'), (-(10 ** 5000), '#_X'),
                        (7 ** 3000, '060000,'), (5e-324, '.1100f'), (1.7976931348623157e308, ',.2f'),
                        (2.0 ** -1074, '.760e'), (0.1, '.1000f'), (1 / 3, '.500g'), ('x' * 100000, '^200001'),
                        (1e300, '#,.3f'), (12345.678, '0=100000,.2f'), (-2.5, '0=60000_.1f'), (10 ** 300, ',.5e'),
                        (2.0 ** 1023, '.400g'), (10 ** 4299, ''), (-(10 ** 4299), '+,'), ('ab' * 50000, '.99999'),
                        (2 ** 20000 - 1, '#_b')]:
        add("big", value, spec, "big", 10.0)
    return cases


def canon_fmt(v):
    return (type(v).__name__, v if isinstance(v, str) else repr(v)[:200])


# ------------------------------------------------------------------------------------------- strptime
WDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]
ST_FIXED = [
    ('68', '%y'), ('69', '%y'), ('Feb 29', '%b %d'), ('2024 060 03 05', '%Y %j %m %d'), ('2023 366', '%Y %j'),
    ('12', '%I'), ('12 PM', '%I %p'), ('12 AM', '%I %p'), ('5 pm', '%I %p'), ('pm', '%p'), ('13 PM', '%H %p'),
    ('2024 0 0', '%Y %U %w'), ('2023 0 1', '%Y %U %w'), ('2024 0 1', '%Y %W %u'), ('2023 0 1', '%Y %W %u'),
    ('2024', '%G'), ('2024 01', '%G %V'), ('01 1', '%V %u'), ('01', '%V'), ('2024 01 1', '%G %V %u'),
    ('2024 01 1 010', '%G %V %u %j'), ('2023 53 1', '%G %V %u'), ('Z', '%z'), ('z', '%z'), ('+05:30', '%z'),
    ('+0530', '%z'), ('+05:30:15', '%z'), ('+05:30:15.5', '%z'), ('+053015', '%z'), ('+05:3015', '%z'),
    ('+0530:15', '%z'), ('+99:00', '%z'), ('-00:00', '%z'), ('2024  01', '%Y %m'), ('2024\t\n01', '%Y %m'),
    ('202401', '%Y %m'), ('2024 01', '%Y%m'), ('2024-01- 5', '%Y-%m-%d'), ('2024t05', '%YT%m'), ('5', '%f'),
    ('1234567', '%f'), ('60', '%S'), ('61', '%S'), ('1', '%d%'), ('1', '%q'), ('1', '%e'), ('1', '%E'),
    ('x', '%Ex'), ('January', '%b'), ('jan', '%B'), ('JANUARY', '%B'), ('a.b', 'a.b'), ('axb', 'a.b'),
    ('Mon 2024-01-02', '%a %Y-%m-%d'), ('2024 10', '%Y %U'), ('2024 1 0', '%Y %W %w'), ('0', '%d'), ('000', '%j'),
    ('2024 1', '%Y %j'), ('2024 366', '%Y %j'), ('0000', '%Y'), ('', ''), ('9999 366', '%Y %j'), ('%5', '%%%d'),
    ('2024 99', '%Y %y'), ('112', '%m%d'), ('13', '%m%d'), ('1112', '%d%m'), ('2024 1 1', '%Y %m %d '),
    (' 2024', '%Y'), ('2024 ', '%Y'), ('9 1', '%m %H'), ('2024 53 6', '%Y %U %w'), ('1999 52 0', '%Y %W %w'),
    ('Tue', '%a'), ('tuesday', '%A'), ('2024 xx', '%Y xx'), ('2024 XX', '%Y xx'), ('2021 1 Sun', '%G %V %a'),
    ('2020 53 7', '%G %V %u'), ('2024 0 3', '%G %V %u'), ('1 1 2024', '%u %V %G'), ('12:30', '%H:%M'),
    ('2024-1-1', '%Y-%m-%d'), ('2024 0 Sun', '%Y %U %a'), ('Sunday 2024 00', '%A %Y %U'), ('1900 0 0', '%Y %U %w'),
    ('0001 0 0', '%Y %U %w'), ('11:59:59 pm', '%I:%M:%S %p'), ('12:00:00 AM', '%I:%M:%S %p'), ('7', '%I'),
    ('7 PM 19', '%I %p %H'), ('19 7 PM', '%H %I %p'), ('99 2024', '%y %Y'), ('Jan 3 2024', '%b %m %Y'),
    ('Mon 0 2024', '%a %w %Y'), ('2024 10 Mon 0', '%Y %W %a %w'), ('2024 10 3 10', '%Y %U %w %W'),
    ('-05:30:15.25', '%z'), ('+23:59:59.999999', '%z'), ('+24:00', '%z'), ('+0000', '%z'), ('-0000', '%z'),
    ('+05', '%z'), ('+05:30:1', '%z'), ('2024-02-29', '%Y-%m-%d'), ('2023-02-29', '%Y-%m-%d'),
    ('1900-02-29', '%Y-%m-%d'), ('2000-02-29', '%Y-%m-%d'), ('02/29', '%m/%d'),
    ('9999-12-31 23:59:59.999999', '%Y-%m-%d %H:%M:%S.%f'), ('0001-01-01', '%Y-%m-%d'), ('12/31/68', '%m/%d/%y'),
    ('1/1/69', '%m/%d/%y'), ('   2024', '%Y'), ('2024', ' %Y'), (' 5', '%d'), ('  5', '%d'), ('5 ', '%d '),
    ('march 5', '%B %d'), ('MAR 5', '%b %d'), ('Sept 5', '%b %d'), ('mAy', '%B'), ('may', '%b'), ('pM', '%p'),
    ('2024-01-01T10:00:00Z', '%Y-%m-%dT%H:%M:%S%z'), ('20240101', '%Y%m%d'), ('2024111', '%Y%m%d'),
    ('202412', '%Y%m%d'), ('1230', '%H%M'), ('130', '%H%M'), ('960', '%H%M'), ('1012', '%I%M'), ('366', '%j'),
    ('367', '%j'), ('2024 060', '%Y %j'), ('060', '%j'), ('2023 365 23', '%Y %j %H'), ('5.123', '%S.%f'),
    ('2024 53 0', '%Y %W %w'), ('2026 0 6', '%Y %W %u'), ('9999 52 5', '%Y %U %w'), ('9999 53 6', '%Y %U %w'),
    ('2025 52 7', '%G %V %u'), ('2026 53 4', '%G %V %u'), ('2015 53 Sun', '%G %V %a'), ('1 52 4', '%G %V %u'),
    ('0001 01 1', '%G %V %u'), ('2024 01', '%G %u'), ('12:30', '%I:%M'), ('2024-01-05 12 07', '%Y-%m-%d %I %M'), ('2024 1 Monday', '%G %V %A'), ('Thu 2024 7', '%a %G %V'),
]
ST_WS = " \t\n \t \x0b\x0c\r "
ST_SEPS = ["-", "-", "/", " ", " ", " ", "  ", "\t", ":", "T", ",", ", ", ".", "", " at ", "_", " / "]


def ref_strptime(text, fmt):
    return datetime.datetime.strptime(text, fmt)


def s_lit(rng, sep):
    """Text matching a literal piece of a format: whitespace runs vary, letters change case."""
    out, i = "", 0
    while i < len(sep):
        if sep[i].isspace():
            while i < len(sep) and sep[i].isspace():
                i += 1
            out += "".join(rng.choice(ST_WS) for _ in range(rng.choice([1, 1, 1, 2, 3])))
        else:
            out += sep[i].swapcase() if sep[i].isalpha() and rng.random() < 0.5 else sep[i]
            i += 1
    return out


def s_offset(rng):
    if rng.random() < 0.1:
        return "Z"
    colon = rng.random() < 0.5
    s = rng.choice("+-") + f"{rng.randint(0, 23):02d}" + (":" if colon else "") + f"{rng.randint(0, 59):02d}"
    if rng.random() < 0.3:
        s += (":" if colon else "") + f"{rng.randint(0, 59):02d}"
        if rng.random() < 0.4:
            s += "." + f"{rng.randint(0, 999999):06d}"[:rng.randint(1, 6)]
    return s


def s_case(rng):
    """A random (text, format) pair built from a random date and time; the reference decides what it means."""
    y = rng.randint(1900, 2100) if rng.random() < 0.8 else rng.randint(1, 9999)
    m = rng.randint(1, 12)
    leap = y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)
    d = rng.randint(1, [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
    mode = rng.choice(["ymd"] * 4 + ["yj", "uw", "uw", "iso", "iso", "md", "none"])
    if mode == "md" and m == 2 and d == 29:
        d = 28
    dt = datetime.datetime(y, m, d, rng.randint(0, 23), rng.randint(0, 59), rng.randint(0, 59),
                           rng.choice([0, rng.randint(0, 999999)]))
    wd = dt.weekday()

    def num(v, w, space=False):
        r = rng.random()
        if space and v < 10 and r < 0.15:
            return " " + str(v)
        return str(v).zfill(w) if r < 0.6 else str(v)

    def name(s):
        return rng.choice([s, s.lower(), s.upper(), "".join(c.upper() if rng.random() < 0.5 else c.lower() for c in s)])

    def weekday():
        w = wd if rng.random() < 0.85 else rng.randrange(7)
        return rng.choice([("%a", name(WDAYS[w][:3])), ("%A", name(WDAYS[w])), ("%w", str((w + 1) % 7)),
                           ("%u", str(w + 1))])

    items = []
    if mode in ("ymd", "md"):
        mi = rng.choice([("%m", num(m, 2)), ("%b", name(MONTHS[m - 1][:3])), ("%B", name(MONTHS[m - 1]))])
        di = ("%d", num(d, 2, True))
        items = [mi, di]
        if mode == "ymd":
            yi = ("%y", f"{y % 100:02d}") if 1969 <= y <= 2068 and rng.random() < 0.3 else ("%Y", f"{y:04d}")
            items = (rng.choice([[yi, mi, di], [di, mi, yi], [mi, di, yi]]) if rng.random() < 0.7
                     else rng.sample([yi, mi, di], 3))
        if rng.random() < 0.25:
            items.insert(rng.randrange(len(items) + 1), weekday())
    elif mode == "yj":
        j = dt.timetuple().tm_yday
        items = [("%Y", f"{y:04d}"), ("%j", str(j).zfill(3) if rng.random() < 0.6 else str(j))]
        if rng.random() < 0.2:
            items.append(weekday())
    elif mode == "uw":
        yday = dt.timetuple().tm_yday - 1
        wi = (("%U", num((yday + 7 - (wd + 1) % 7) // 7, 2)) if rng.random() < 0.5
              else ("%W", num((yday + 7 - wd) // 7, 2)))
        items = rng.sample([("%Y", f"{y:04d}"), wi, weekday()], 3)
    elif mode == "iso":
        iy, iw, _ = dt.isocalendar()
        items = rng.sample([("%G", f"{iy:04d}"), ("%V", num(iw, 2)), weekday()], 3)
    if rng.random() < 0.75 or not items:
        h = dt.hour
        if rng.random() < 0.3:
            t = [("%I", num(h % 12 or 12, 2)), ("%M", num(dt.minute, 2))]
            if rng.random() < 0.85:
                t.append(("%p", name("AM" if h < 12 else "PM")))
        else:
            t = [("%H", num(h, 2)), ("%M", num(dt.minute, 2))]
        if rng.random() < 0.7:
            t.append(("%S", num(dt.second, 2)))
        if rng.random() < 0.4:
            t.append(("%f", f"{dt.microsecond:06d}"[:rng.randint(1, 6)]))
        if rng.random() < 0.3:
            t.append(("%z", s_offset(rng)))
        items += t
    if rng.random() < 0.08:
        items.insert(rng.randrange(len(items) + 1), ("%%", "%"))
    fmt = text = ""
    if rng.random() < 0.1:
        fmt, text = "on ", s_lit(rng, "on ")
    for i, (dv, tv) in enumerate(items):
        if i:
            sep = rng.choice(ST_SEPS) if rng.random() < 0.9 else ""
            fmt += sep
            text += s_lit(rng, sep)
        fmt += dv
        text += tv
    return text, fmt


def s_bad(rng):
    """A (text, format) pair that is probably invalid: a template error or a mutated random case."""
    k = rng.randrange(12)
    y, m = rng.randint(1900, 2100), rng.randint(1, 12)
    if k == 0:
        last = [31, 29 if y % 4 == 0 and (y % 100 or y % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
        return f"{y}-{m:02d}-{rng.randint(last + 1, 31) if last < 31 else 32}", "%Y-%m-%d"
    if k == 1:
        return f"{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:6{rng.choice('01')}", "%H:%M:%S"
    if k == 2:
        return rng.choice(["+24:00", "-99:59", "+05:3015", "+0530:15", "z", "+5:30", "+05:60", "+05:30:", "+0530.5",
                           "-23:59:60", "++05:00", "+05:30:15.1234567", "UTC"]), rng.choice(["%z", "%z"])
    if k == 3:
        text, fmt = s_case(rng)
        cut = rng.randrange(len(fmt) + 1)
        return text, fmt[:cut] + "%" + rng.choice("eEOqikKlLnNoPrRstTvJQC1-#!") + fmt[cut:]
    if k == 4:
        text, fmt = s_case(rng)
        return text, fmt + "%"
    if k == 5:
        return rng.choice([("2024 01", "%G %V"), ("2024 1", "%G %u"), ("01 1", "%V %u"), ("2024 01 1 010", "%G %V %u %j"),
                           ("Mon 05", "%a %V"), ("2024", "%G"), ("2024 07 3 100", "%G %V %w %j")])
    if k == 6:
        return rng.choice([f"{m:02d}/29", "Feb 29", "february 29", "29 2"]), rng.choice(["%m/%d", "%b %d", "%B %d", "%d %m"])
    if k == 7:
        return rng.choice([("0000-01-01", "%Y-%m-%d"), ("9999 366", "%Y %j"), ("9999 53 6", "%Y %U %w"),
                           ("9999 53 Sun", "%Y %W %a"), ("0001 00 1", "%Y %W %u")])
    if k == 8:
        return rng.choice([("Janu 5", "%b %d"), ("January 5", "%b %d"), ("Mo", "%a"), ("Mond", "%A"), ("Sept", "%b"),
                           ("Juni", "%B"), ("noon", "%p"), ("A.M.", "%p")])
    if k == 9:
        return rng.choice([("2024-01-01", "%Y %m %d"), ("2024/01/01", "%Y-%m-%d"), ("2024 01 01", "%Y %m %d "),
                           ("2024-01-01 ", "%Y-%m-%d"), (" 2024-01-01", "%Y-%m-%d"), ("2024-01-01", " %Y-%m-%d")])
    text, fmt = s_case(rng)
    if not text:
        return "x", fmt
    i = rng.randrange(len(text))
    op = rng.randrange(4)
    if op == 0:
        return text[:i] + text[i + 1:], fmt
    if op == 1:
        return text[:i] + rng.choice("0123456789x :-") + text[i:], fmt
    if op == 2 and text[i].isdigit():
        return text[:i] + rng.choice("0123456789".replace(text[i], "")) + text[i + 1:], fmt
    return text + rng.choice(["0", "1", "x", " ", "Z", "+0"]), fmt


def strptime_cases():
    rng = random.Random(55)
    cases, seen = [], set()

    def add(part, text, fmt):
        if (text, fmt) in seen:
            return
        seen.add((text, fmt))
        exp = expect(ref_strptime, (text, fmt), ("ValueError",))
        if exp is None:
            return
        if part == "valid" and exp[0] == "err":
            part = "invalid"
        cases.append((part, "strptime", (text, fmt), exp, "iso", 2.0))

    for text, fmt in ST_FIXED:
        add("fixed", text, fmt)
    for _ in range(760):
        add("valid", *s_case(rng))
    for _ in range(520):
        add("invalid", *s_bad(rng))
    return cases


def canon_strptime(v):
    if not isinstance(v, datetime.datetime):
        return ("other", type(v).__name__)
    off = v.utcoffset()
    return ("datetime", v.year, v.month, v.day, v.hour, v.minute, v.second, v.microsecond,
            None if off is None else (off.days, off.seconds, off.microseconds))


# ------------------------------------------------------------------------------------------- inflate
LBASE = [3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 19, 23, 27, 31, 35, 43, 51, 59, 67, 83, 99, 115, 131, 163, 195,
         227, 258]
LEXT = [0] * 8 + [1] * 4 + [2] * 4 + [3] * 4 + [4] * 4 + [5] * 4 + [0]
DBASE = [1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 33, 49, 65, 97, 129, 193, 257, 385, 513, 769, 1025, 1537, 2049, 3073,
         4097, 6145, 8193, 12289, 16385, 24577]
DEXT = [0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10, 10, 11, 11, 12, 12, 13, 13]
CL_ORDER = [16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15]
FIXED_LIT = [8] * 144 + [9] * 112 + [7] * 24 + [8] * 8
WORDS = ("the of and to in is was for on that with as by at from his it an were are which this be or has had "
         "not but first one their its new after who they have her she two been other when there all during into "
         "school time may years more most only over city some world would where later up such used many can "
         "state about national out known university united then made 1999 2024 3.14 x_y {} [] == != <=").split()


def ref_inflate(data, wbits=15):
    try:
        return zlib.decompress(data, wbits)
    except zlib.error as e:
        raise ValueError(str(e)) from None


class BitW:
    """Deflate bit writer: fields go least significant bit first, Huffman codes most significant first."""
    def __init__(self):
        self.acc = self.n = 0
        self.out = bytearray()

    def put(self, v, k):
        self.acc |= (v & ((1 << k) - 1)) << self.n
        self.n += k
        while self.n >= 8:
            self.out.append(self.acc & 255)
            self.acc >>= 8
            self.n -= 8

    def code(self, c, k):
        self.put(int(bin(c & ((1 << k) - 1))[2:].zfill(k)[::-1], 2), k)

    def align(self):
        if self.n:
            self.put(0, 8 - self.n)

    def done(self):
        self.align()
        return bytes(self.out)


def canon_codes(lengths):
    """Canonical Huffman codes (RFC 1951 3.2.2): {symbol: (code, length)}."""
    count = [0] * 17
    for n in lengths:
        if n:
            count[n] += 1
    code, nxt = 0, [0] * 17
    for b in range(1, 17):
        code = (code + count[b - 1]) << 1
        nxt[b] = code
    out = {}
    for s, n in enumerate(lengths):
        if n:
            out[s] = (nxt[n], n)
            nxt[n] += 1
    return out


def complete_lengths(symbols, n):
    """n code lengths giving the listed symbols (at least two after padding) a complete prefix code."""
    syms = sorted(set(symbols))
    if len(syms) == 1:
        syms.append(0 if syms[0] else 1)
    k = (len(syms) - 1).bit_length()
    short = 2 ** k - len(syms)
    lens = [0] * n
    for i, s in enumerate(syms):
        lens[s] = k - 1 if i < short else k
    return lens


def rle(seq):
    """Code-length symbols (sym, extra, extra bits) for a sequence of lengths, runs crossing any boundary."""
    out, i = [], 0
    while i < len(seq):
        v, j = seq[i], i
        while j < len(seq) and seq[j] == v:
            j += 1
        run = j - i
        if v == 0:
            while run >= 11:
                r = min(run, 138)
                out.append((18, r - 11, 7))
                run -= r
            if run >= 3:
                out.append((17, run - 3, 3))
                run = 0
            out += [(0, 0, 0)] * run
        else:
            out.append((v, 0, 0))
            run -= 1
            while run >= 3:
                r = min(run, 6)
                out.append((16, r - 3, 2))
                run -= r
            out += [(v, 0, 0)] * run
        i = j
    return out


def emit(w, items, lc, dc):
    """Symbols: an int is a literal byte, ('m', length, distance) a match, ('sym', lsym, lextra, dsym,
    dextra) explicit symbols (dsym None: no distance), ('bits', v, k) raw bits, 'eob' the end of block."""
    for it in items:
        if isinstance(it, int):
            w.code(*lc[it])
        elif it == "eob":
            w.code(*lc[256])
        elif it[0] == "m":
            _, length, dist = it
            i = max(k for k in range(29) if LBASE[k] <= length)
            w.code(*lc[257 + i])
            w.put(length - LBASE[i], LEXT[i])
            j = max(k for k in range(30) if DBASE[k] <= dist)
            w.code(*dc[j])
            w.put(dist - DBASE[j], DEXT[j])
        elif it[0] == "sym":
            _, ls, le, ds, de = it
            w.code(*lc[ls])
            w.put(le, LEXT[ls - 257] if 257 <= ls < 286 else 0)
            if ds is not None:
                w.code(*dc[ds])
                w.put(de, DEXT[ds] if ds < 30 else 0)
        else:
            w.put(it[1], it[2])


def dyn_block(w, final, lit, dist, items, cl_items=None, cl_lens=None, hlit=None, hdist=None):
    w.put(final, 1)
    w.put(2, 2)
    cl_items = rle(lit + dist) if cl_items is None else cl_items
    if cl_lens is None:
        cl_lens = complete_lengths([s for s, _, _ in cl_items], 19)
    nclen = max([4] + [i + 1 for i, s in enumerate(CL_ORDER) if cl_lens[s]])
    w.put((len(lit) if hlit is None else hlit) - 257, 5)
    w.put((len(dist) if hdist is None else hdist) - 1, 5)
    w.put(nclen - 4, 4)
    for s in CL_ORDER[:nclen]:
        w.put(cl_lens[s], 3)
    clc = canon_codes(cl_lens)
    for s, e, k in cl_items:
        w.code(*clc[s])
        w.put(e, k)
    emit(w, items, canon_codes(lit), canon_codes(dist))


def fixed_block(w, final, items):
    w.put(final, 1)
    w.put(1, 2)
    emit(w, items, canon_codes(FIXED_LIT), canon_codes([5] * 32))


def stored_block(w, final, data, nlen=None):
    w.put(final, 1)
    w.put(0, 2)
    w.align()
    w.put(len(data), 16)
    w.put(~len(data) & 0xffff if nlen is None else nlen, 16)
    for b in data:
        w.put(b, 8)


def deflate_raw(data, level=6, strategy=0):
    c = zlib.compressobj(level, zlib.DEFLATED, -15, 8, strategy)
    return c.compress(data) + c.flush()


def zhdr(cinfo=7, flevel=2, fdict=0, method=8):
    cmf, flg = (cinfo << 4) | method, (flevel << 6) | (fdict << 5)
    return bytes([cmf, flg + (31 - (cmf * 256 + flg) % 31) % 31])


def wrap_zlib(raw, data, hdr=b"\x78\x9c"):
    return hdr + raw + struct.pack(">I", zlib.adler32(data))


def wrap_gzip(raw, data, flags=0, extra=b"", name=b"", comment=b"", hcrc=None, mtime=0, xfl=0, os_=255):
    h = bytearray(b"\x1f\x8b\x08" + bytes([flags]) + struct.pack("<I", mtime) + bytes([xfl, os_]))
    if flags & 4:
        h += struct.pack("<H", len(extra)) + extra
    if flags & 8:
        h += name + b"\x00"
    if flags & 16:
        h += comment + b"\x00"
    if flags & 2:
        h += struct.pack("<H", zlib.crc32(bytes(h)) & 0xffff if hcrc is None else hcrc)
    return bytes(h) + raw + struct.pack("<II", zlib.crc32(data), len(data) & 0xffffffff)


def raw_of(build):
    w = BitW()
    build(w)
    return w.done()


def inflate_crafted():
    """(label, data, wbits, outcome zlib must give: 'ok', 'err' or None) for the fixed part."""
    c = zlib.compress(b"abc")
    raw = deflate_raw(b"hello hello hello")
    g = zlib.compressobj(9, zlib.DEFLATED, 31)
    gz = g.compress(b"gzip data") + g.flush()
    body = gz[10:]
    hdr = bytearray(gz[:10])
    hdr[3] |= 2
    text = b"The quick brown fox jumps over the lazy dog. " * 20
    traw = deflate_raw(text)
    out = [("empty 15", b"", 15, "err"), ("empty -15", b"", -15, "err"), ("empty 31", b"", 31, "err"),
           ("zlib trailing", c + b"xyz", 15, "ok"), ("raw trailing", raw + b"\xff\x00junk", -15, "ok"),
           ("two gzip members", gz + gz, 31, "ok"), ("gzip as 15", gz, 15, "err"), ("zlib as 31", c, 31, "err"),
           ("zlib as -15", c, -15, None), ("raw as 15", raw, 15, "err"), ("raw as 31", raw, 31, "err"),
           ("fdict", bytes([0x78, 0xbb]) + b"\x00\x00\x00\x01" + c[2:], 15, "err"),
           ("cinfo 8", bytes([0x88, 0x1c]) + c[2:], 15, "err"), ("bad fcheck", bytes([0x78, 0x9d]) + c[2:], 15, "err"),
           ("method 7", bytes([0x77, 0x09]) + c[2:], 15, "err"), ("bad adler", c[:-1] + bytes([c[-1] ^ 1]), 15, "err"),
           ("truncated adler", c[:-2], 15, "err"), ("no adler", c[:-4], 15, "err"), ("header only", c[:2], 15, "err"),
           ("gzip fhcrc wrong", bytes(hdr) + b"\x00\x00" + body, 31, "err"),
           ("gzip fhcrc right", bytes(hdr) + struct.pack("<H", zlib.crc32(bytes(hdr)) & 0xffff) + body, 31, "ok"),
           ("gzip bad isize", gz[:-1] + bytes([gz[-1] ^ 1]), 31, "err"),
           ("gzip bad crc", gz[:-5] + bytes([gz[-5] ^ 1]) + gz[-4:], 31, "err"), ("gzip no isize", gz[:-1], 31, "err"),
           ("stored nlen bad", b"\x01\x03\x00\xfc\xfe" + b"abc", -15, "err"),
           ("stored ok", b"\x01\x03\x00\xfc\xff" + b"abc", -15, "ok"), ("btype 3", b"\x07\x00", -15, "err"),
           ("cinfo 0", wrap_zlib(traw, text, zhdr(0, 0)), 15, "ok"), ("flevel 3", wrap_zlib(traw, text, zhdr(7, 3)), 15, "ok"),
           ("cinfo 7 method 15", wrap_zlib(traw, text, zhdr(7, 2, 0, 15)), 15, "err"),
           ("gzip all options", wrap_gzip(traw, text, 31, b"ab\x00cd" * 3, b"name.txt", b"a comment", None, 1700000000, 2, 3), 31, "ok"),
           ("gzip extra only", wrap_gzip(traw, text, 4, b"\x00" * 300), 31, "ok"),
           ("gzip extra truncated", wrap_gzip(b"", b"", 4, b"")[:10] + b"\x64\x00" + b"x" * 10, 31, "err"),
           ("gzip name unterminated", b"\x1f\x8b\x08\x08" + b"\x00" * 6 + b"name", 31, "err"),
           ("gzip wrong id", b"\x1f\x8c" + wrap_gzip(traw, text)[2:], 31, "err"),
           ("gzip method 7", b"\x1f\x8b\x07" + wrap_gzip(traw, text)[3:], 31, "err"),
           ("gzip ftext", wrap_gzip(traw, text, 1), 31, "ok"), ("gzip header only", wrap_gzip(traw, text)[:10], 31, "err")]
    for bit in (0x20, 0x40, 0x80):
        out.append((f"gzip reserved flag {bit:#x}", wrap_gzip(traw, text, bit), 31, "err"))
    lit_ab = complete_lengths([97, 98, 256, 257, 258], 259)
    # dynamic blocks for each code rule
    out += [
        ("dist one code length 1", raw_of(lambda w: dyn_block(w, 1, lit_ab, [1] + [0] * 3, [97, ("m", 3, 1), 98, "eob"])), -15, "ok"),
        ("dist two codes length 2", raw_of(lambda w: dyn_block(w, 1, lit_ab, [2, 2], [97, ("m", 3, 1), "eob"])), -15, "err"),
        ("dist all zero, literals", raw_of(lambda w: dyn_block(w, 1, complete_lengths([97, 98, 256], 257), [0], [97, 98, 97, "eob"])), -15, "ok"),
        ("dist all zero, a match", raw_of(lambda w: dyn_block(w, 1, lit_ab, [0, 0], [97, ("sym", 257, 0, None, None), ("bits", 0, 8), "eob"])), -15, "err"),
        ("missing end of block", raw_of(lambda w: dyn_block(w, 1, complete_lengths([97, 98, 257], 258), [1, 1], [97, 98])), -15, "err"),
        ("hlit 287", raw_of(lambda w: dyn_block(w, 1, lit_ab, [1, 1], [97, "eob"], hlit=287)), -15, "err"),
        ("hdist 31", raw_of(lambda w: dyn_block(w, 1, lit_ab, [1, 1], [97, "eob"], hdist=31)), -15, "err"),
        ("hlit 286", raw_of(lambda w: dyn_block(w, 1, complete_lengths([97, 256, 285], 286), [1, 1], [97, ("m", 258, 1), "eob"])), -15, "ok"),
        ("repeat 16 first", raw_of(lambda w: dyn_block(w, 1, lit_ab, [1, 1], [97, "eob"], cl_items=[(16, 0, 2)] + rle(lit_ab + [1, 1]))), -15, "err"),
        ("repeat past the end", raw_of(lambda w: dyn_block(w, 1, lit_ab, [1, 1], [97, "eob"], cl_items=rle(lit_ab + [1]) + [(16, 3, 2)])), -15, "err"),
        ("over-subscribed lit/len", raw_of(lambda w: dyn_block(w, 1, [1] * 3 + [0] * 253 + [1, 1], [1, 1], [0, "eob"])), -15, "err"),
        ("over-subscribed dist", raw_of(lambda w: dyn_block(w, 1, lit_ab, [1, 1, 1], [97, "eob"])), -15, "err"),
        ("incomplete code-length code", raw_of(lambda w: dyn_block(w, 1, lit_ab, [1, 1], [97, "eob"],
                                                                  cl_lens=[3 if s else 0 for s in complete_lengths([s for s, _, _ in rle(lit_ab + [1, 1])], 19)])), -15, "err"),
        ("lit/len only end of block", raw_of(lambda w: dyn_block(w, 1, [0] * 256 + [1], [0], ["eob"])), -15, "ok"),
        ("lit/len unused pattern", raw_of(lambda w: dyn_block(w, 1, [0] * 256 + [1], [0], [("bits", 1, 1), "eob"])), -15, "err"),
        ("dist unused pattern", raw_of(lambda w: dyn_block(w, 1, lit_ab, [1], [97, ("sym", 257, 0, None, None), ("bits", 1, 1), "eob"])), -15, "err"),
    ]
    # runs of code lengths that cross from the literal/length lengths into the distance lengths
    lit0 = complete_lengths([97, 98, 256, 257], 260)
    out.append(("zero run crosses into distances", raw_of(lambda w: dyn_block(w, 1, lit0, [0, 0, 1], [97, 98, 97, ("m", 3, 3), "eob"])), -15, "ok"))
    lit3 = complete_lengths([97, 256, 259, 260, 261], 262)
    out.append(("repeat 16 crosses into distances", raw_of(lambda w: dyn_block(w, 1, lit3, [3] * 8, [97, ("m", 5, 1), "eob"])), -15, "ok"))
    out.append(("crossing runs in zlib", wrap_zlib(raw_of(lambda w: dyn_block(w, 1, lit3, [3] * 8, [97, ("m", 5, 1), "eob"])), b"a" * 6), 15, "ok"))
    # fixed blocks
    out += [
        ("fixed symbol 286", raw_of(lambda w: fixed_block(w, 1, [97, ("sym", 286, 0, None, None), "eob"])), -15, "err"),
        ("fixed symbol 287", raw_of(lambda w: fixed_block(w, 1, [97, ("sym", 287, 0, None, None), "eob"])), -15, "err"),
        ("fixed distance 30", raw_of(lambda w: fixed_block(w, 1, [97] * 40 + [("sym", 257, 0, 30, 0), "eob"])), -15, "err"),
        ("fixed distance 31", raw_of(lambda w: fixed_block(w, 1, [97] * 40 + [("sym", 257, 0, 31, 0), "eob"])), -15, "err"),
        ("distance too far back", raw_of(lambda w: fixed_block(w, 1, [97, 98, ("m", 3, 3), "eob"])), -15, "err"),
        ("distance to the first byte", raw_of(lambda w: fixed_block(w, 1, [97, 98, ("m", 3, 2), "eob"])), -15, "ok"),
        ("length 258 from code 284", raw_of(lambda w: fixed_block(w, 1, [97, ("sym", 284, 31, 0, 0), "eob"])), -15, "ok"),
        ("distance 32768", raw_of(lambda w: (stored_block(w, 0, bytes(range(256)) * 128), fixed_block(w, 1, [("m", 258, 32768), "eob"]))), -15, "ok"),
        ("distance 32768 too far", raw_of(lambda w: (stored_block(w, 0, bytes(range(256)) * 127 + bytes(255)), fixed_block(w, 1, [("m", 258, 32768), "eob"]))), -15, "err"),
        ("stored empty final", raw_of(lambda w: stored_block(w, 1, b"")), -15, "ok"),
        ("empty fixed then stored", raw_of(lambda w: (fixed_block(w, 0, ["eob"]), stored_block(w, 1, b"xyz"))), -15, "ok"),
        ("no final block", raw_of(lambda w: (fixed_block(w, 0, [97, "eob"]), stored_block(w, 0, b"xyz"))), -15, "err"),
        ("stored then btype 3", raw_of(lambda w: (stored_block(w, 0, b"ab"), w.put(1, 1), w.put(3, 2))), -15, "err"),
        ("fixed error in gzip", wrap_gzip(raw_of(lambda w: fixed_block(w, 1, [97, 98, ("m", 3, 3), "eob"])), b"ababa"), 31, "err"),
    ]
    return out


def i_data(rng):
    n = rng.choice([0, 1, 2, 10, 100, 1000, 5000, 20000, rng.randint(0, 3000), rng.randint(0, 3000)])
    k = rng.randrange(7)
    if k == 0:
        return rng.getrandbits(8 * n).to_bytes(n, "little") if n else b""
    if k == 1:
        return "".join(rng.choice("ab") for _ in range(n)).encode()
    if k == 2:
        return " ".join(rng.choice(WORDS) for _ in range(n // 5 + 1)).encode()[:n]
    if k == 3:
        return bytes([rng.randrange(256)]) * n
    if k == 4:
        m = rng.randint(1, 300)
        pat = rng.getrandbits(8 * m).to_bytes(m, "little")
        return (pat * (n // m + 1))[:n]
    if k == 5:
        block = rng.getrandbits(8000).to_bytes(1000, "little")
        return block + rng.getrandbits(8 * 31000).to_bytes(31000, "little") + block
    return "".join(f"{rng.choice(WORDS)} {rng.randint(0, 99999)}\n" for _ in range(n // 10 + 1)).encode()


def i_stream(rng, data, kind):
    """data compressed by zlib with random settings and flushes; sometimes a hand-made zlib or gzip header."""
    level = rng.choice([0, 1, 2, 3, 4, 5, 6, 6, 7, 8, 9])
    strategy = rng.choice([zlib.Z_DEFAULT_STRATEGY] * 3 + [zlib.Z_FILTERED, zlib.Z_HUFFMAN_ONLY, zlib.Z_RLE, zlib.Z_FIXED])
    bits = rng.randint(9, 15)
    custom = kind != "raw" and rng.random() < 0.3
    wb = -bits if custom or kind == "raw" else {"zlib": bits, "gzip": 16 + bits}[kind]
    c = zlib.compressobj(level, zlib.DEFLATED, wb, rng.randint(1, 9), strategy)
    parts, i = [], 0
    while i < len(data):
        j = i + rng.choice([len(data), rng.randint(1, 4000)])
        parts.append(c.compress(data[i:j]))
        if rng.random() < 0.3:
            parts.append(c.flush(rng.choice([zlib.Z_SYNC_FLUSH, zlib.Z_FULL_FLUSH, zlib.Z_PARTIAL_FLUSH, zlib.Z_BLOCK])))
        i = j
    parts.append(c.flush())
    blob = b"".join(parts)
    if custom and kind == "zlib":
        blob = wrap_zlib(blob, data, zhdr(rng.randint(0, 7), rng.randint(0, 3)))
    elif custom:
        flags = rng.choice([0, 1, 2, 4, 8, 16]) | rng.choice([0, 2, 4, 8, 16, 30, 31])
        blob = wrap_gzip(blob, data, flags, bytes(rng.randrange(256) for _ in range(rng.randint(0, 40))),
                         bytes(rng.randint(1, 255) for _ in range(rng.randint(0, 20))),
                         bytes(rng.randint(1, 255) for _ in range(rng.randint(0, 20))), None,
                         rng.getrandbits(32), rng.randrange(256), rng.randrange(256))
    if rng.random() < 0.15:
        blob += rng.getrandbits(8 * 7).to_bytes(7, "little")[:rng.randint(1, 7)]
    return blob


def i_corrupt(rng, blob):
    b = bytearray(blob)
    k = rng.randrange(6)
    if k == 0:
        return bytes(b[:rng.randrange(len(b))])

    def pos(extra=0):
        return rng.randrange(min(len(b) + extra, 60)) if rng.random() < 0.5 else rng.randrange(len(b) + extra)
    if k in (1, 2):
        for _ in range(rng.randint(1, 3)):
            i = pos()
            b[i] ^= 1 << rng.randrange(8)
    elif k == 3:
        b[pos()] = rng.randrange(256)
    elif k == 4:
        del b[pos()]
    else:
        b.insert(pos(1), rng.randrange(256))
    return bytes(b)


def inflate_cases():
    rng = random.Random(555)
    cases = []

    def add(part, data, wbits, mode="iso", limit=5.0):
        exp = expect(ref_inflate, (data, wbits), ("ValueError",))
        if exp is not None:
            cases.append((part, "decompress", (data, wbits), exp, mode, limit))

    for _label, data, wbits, _want in inflate_crafted():
        add("fixed", data, wbits)
    for _ in range(300):
        kind = rng.choice(["zlib", "raw", "gzip"])
        add("valid", i_stream(rng, i_data(rng), kind), {"zlib": 15, "raw": -15, "gzip": 31}[kind])
    for _ in range(520):
        kind = rng.choice(["zlib", "raw", "raw", "gzip"])
        data = i_data(rng)[:6000] or b"x"
        add("corrupt", i_corrupt(rng, i_stream(rng, data, kind)), {"zlib": 15, "raw": -15, "gzip": 31}[kind])
    text = " ".join(rng.choice(WORDS) for _ in range(250000)).encode()
    for data, kind, level, strategy, flush in [(text * 3, "zlib", 6, 0, 0), (rng.getrandbits(8 << 20).to_bytes(1 << 20, "little"), "gzip", 1, 0, 0),
                                               (bytes(4 << 20), "raw", 9, 0, 0), (text * 2, "raw", 6, zlib.Z_HUFFMAN_ONLY, 0),
                                               (text, "zlib", 6, zlib.Z_FIXED, 0), (text[:500000], "gzip", 6, 0, 100)]:
        c = zlib.compressobj(level, zlib.DEFLATED, {"zlib": 15, "raw": -15, "gzip": 31}[kind], 8, strategy)
        if flush:
            blob = b"".join(c.compress(data[i:i + flush]) + c.flush(zlib.Z_FULL_FLUSH) for i in range(0, len(data), flush))
        else:
            blob = c.compress(data)
        add("big", blob + c.flush(), {"zlib": 15, "raw": -15, "gzip": 31}[kind], "big", 30.0)
    return cases


def canon_inflate(v):
    if isinstance(v, (bytes, bytearray)):
        return ("bytes", bytes(v))
    return ("other", type(v).__name__)


# ------------------------------------------------------------------------------------------- driver
TASKS = {"fmtspec": (fmt_cases, canon_fmt, ["fixed", "int", "float", "str", "invalid", "big"]),
         "strptime": (strptime_cases, canon_strptime, ["fixed", "valid", "invalid"]),
         "inflate": (inflate_cases, canon_inflate, ["fixed", "valid", "corrupt", "big"])}
HANG_BUDGET = {"iso": 8, "big": 4}


def same(got, exp, canon):
    if exp[0] == "err":
        return got[0] == "err" and exp[1] in got[1]
    if got[0] != "ok":
        return False
    try:
        return canon(got[1]) == canon(exp[1])
    except Exception:  # noqa: BLE001
        return False


def label(name, args):
    if name == "fmt":
        return f"fmt({short(args[0], 50)}, {short(args[1], 40)})"
    if name == "strptime":
        return f"strptime({short(args[0], 60)}, {short(args[1], 50)})"
    data, wbits = args
    return f"decompress(<{len(data)} bytes: {data[:24].hex()}{'...' if len(data) > 24 else ''}>, {wbits})"


def check(task, path):
    warnings.simplefilter("ignore")
    build, canon, parts = TASKS[task]
    signal.signal(signal.SIGALRM, _on_alarm)
    cases = build()                                     # every reference value is computed before the import
    sink = open(os.devnull, "w")
    sys.stdout = sys.stderr = sink                      # the candidate's prints can't reach the score line
    spec = importlib.util.spec_from_file_location("candidate", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["candidate"] = mod
    loaded = call(spec.loader.exec_module, (mod,), 30.0)
    signal.signal(signal.SIGALRM, _on_alarm)            # in case the import replaced the handler
    results, hangs = [], {"iso": 0, "big": 0}
    for part, name, args, exp, mode, limit in cases:
        fn = getattr(mod, name, None)
        if loaded[0] != "ok" or fn is None:
            got = ("err", ["ImportError" if loaded[0] != "ok" else "AttributeError"])
        elif hangs[mode] >= HANG_BUDGET[mode]:
            got = ("hang", None)
        else:
            got = isolated(fn, args, limit)
            if got[0] == "hang":
                hangs[mode] += 1
        results.append((part, name, args, got, exp, same(got, exp, canon)))
    lines = [f"SCORE {sum(r[5] for r in results)}/{len(results)}",
             "PARTS " + " ".join(f"{p}={sum(r[5] for r in results if r[0] == p)}/{sum(1 for r in results if r[0] == p)}"
                                 for p in parts)]
    if loaded[0] != "ok":
        lines.append(f"the module didn't load: {show(loaded)}")
    for part, name, args, got, exp, good in results:
        if not good and len(lines) < 8:
            lines.append(f"{part}: {label(name, args)} -> got {show(got)}, expected {show(exp)}")
    os.write(1, ("\n".join(lines) + "\n").encode("utf-8", "replace"))


def selfcheck():
    warnings.simplefilter("ignore")
    signal.signal(signal.SIGALRM, _on_alarm)
    problems = []
    for lbl, data, wbits, want in inflate_crafted():    # each hand-built stream tests what its label says
        got = call(ref_inflate, (data, wbits), 10)
        if want and (got[0] == "ok") != (want == "ok"):
            problems.append(f"inflate crafted '{lbl}': zlib gives {show(got)}, built to be {want}")
    for task, (build, _canon, parts) in TASKS.items():
        t0 = time.time()
        cases = build()
        kinds = {}
        for c in cases:
            kinds.setdefault(c[0], [0, 0])[0 if c[3][0] == "ok" else 1] += 1
        print(task, len(cases), f"cases ({time.time() - t0:.1f} s):",
              ", ".join(f"{p} {kinds.get(p, [0, 0])[0]} ok + {kinds.get(p, [0, 0])[1]} errors" for p in parts))
        if len({tuple(short(a, 300) for a in c[2]) for c in cases}) < len(cases) * 0.95:
            problems.append(f"{task}: many repeated cases")
    print("\n".join(problems) if problems else "selfcheck OK")


if __name__ == "__main__":
    if sys.argv[1:] == ["selfcheck"]:
        selfcheck()
    else:
        check(sys.argv[1], sys.argv[2])
