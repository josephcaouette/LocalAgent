"""Fourth test battery: three big tasks with exact standard-library references, built to push Ultra and
MAX apart (in sets 1-3 every file from both levels was correct). Each task is long and dense with rules,
with traps aimed at MAX's extra steps: inputs at extreme sizes and depths for the adversarial tester and
the robustness critic, and many error rules and boundary values for mutation testing. Run inside the
sandbox (the module under test is pipeline-written code):
    python3 battery4_checks.py TASK /work/<file>.py        (TASK: pyexpr, toml or struct)
Prints `SCORE passed/total`, a `PARTS` line with the score per kind of case, and up to 6 mismatches.
The cases are the same on every run (fixed seeds), so the levels are compared on identical inputs.

References: pyexpr - Python's own parser (ast.parse) plus a small evaluator that applies the goal's size
rule, and closed forms for inputs too deep or long for ast.parse; toml - tomllib, with date and time
values turned into the goal's ValueError; struct - struct, behind the goal's byte-order rule and with
struct.error mapped to ValueError. Every call to the candidate runs in a forked child with a time and
memory limit (an alarm can't interrupt a long computation inside C, such as 9**9**9 or a regex that
backtracks), so a crash, a hang or a runaway allocation costs only that case.
Validate changes with `python3 battery4_checks.py selfcheck` and the stubs in tests/stubs4/: every
`*_ok.py` must score in full and every `*_bad_*.py` must not (mkvariants4.py writes the bad ones)."""
import ast
import importlib.util
import math
import operator
import os
import pickle
import random
import re
import select
import signal
import struct
import sys
import time
import warnings

try:                                   # Linux only; battery.py imports this module on Windows for GOALS
    import resource
except ImportError:
    resource = None
try:
    import tomllib
except ImportError:
    tomllib = None

GOALS = {
    "pyexpr": (
        "Create a Python module with evaluate(expr) -> int or bool that evaluates an integer expression "
        "written in a subset of Python 3's syntax, with exactly Python 3's semantics, without using eval, exec, "
        "compile, the ast or tokenize modules or any parsing library. The subset: integer literals as Python "
        "writes them (decimal with no leading zeros except in zero itself, so 007 is invalid but 00 and 0_0 are "
        "0; 0x, 0o and 0b prefixes in either case; underscores only between digits or right after a base prefix, "
        "as in 1_000 and 0x_ff), True and False, parentheses, and these operators from lowest to highest "
        "precedence: or; and; not; the comparisons < <= > >= == !=, which chain as in Python (1 < x < 3 means "
        "1 < x and x < 3, with x evaluated once and the rest skipped once a comparison is false); |; ^; &; << and "
        ">>; + and -; * // and %; unary - + and ~; and ** (right-associative, binding tighter than a unary "
        "operator on its left but looser than one on its right: -2**2 is -4). Results follow Python exactly, "
        "types included: comparisons and not give bool; and/or return one of their operands and short-circuit "
        "(0 or 5 is 5, 3 and 0 is 0, 0 and 1//0 is 0); bool & | ^ bool stays bool; arithmetic on bools gives int "
        "(True + True is 2); // and % floor (-7 // 2 is -4, -7 % 2 is 1). Spaces and tabs may appear between "
        "tokens and at either end; any other character outside tokens (a newline, #, ...) is invalid. Errors: "
        "ZeroDivisionError for // or % by zero; ValueError for an invalid or unsupported expression (anything "
        "Python would reject, and anything outside the subset such as names, floats like 1.5 or 1e3, strings, /, "
        "calls, subscripts, is, in, if-else), for a negative exponent (Python would give a float) or a negative "
        "shift count, and for any operation whose exact result would need more than 1,000,000 bits "
        "(abs(result).bit_length() > 1000000). The size check must not compute the huge result first: "
        "9 ** 9 ** 9 raises ValueError at once. The whole expression is checked before anything is evaluated, "
        "so 1//0 + ) raises ValueError, not ZeroDivisionError. Big inputs must work: expressions up to 1,000,000 "
        "characters (time roughly proportional to the length), nesting up to 100,000 levels deep (parentheses, "
        "chains of unary operators or not, or ** chains), and integer literals of up to 100,000 digits (Python "
        "3.11's int() refuses decimal strings over 4,300 digits by default). Command line: python <script> "
        "\"EXPR\" prints the result. In --test mode check precedence, chaining, short-circuiting, result types, "
        "the error cases and the big inputs."),
    "toml": (
        "Create a Python module with loads(text) -> dict that parses a TOML v1.0.0 document given as a str, "
        "without using tomllib, tomli, toml or any other TOML library. Follow the TOML v1.0.0 specification "
        "exactly, with two exceptions: date and time values (offset date-time, local date-time, local date and "
        "local time) are not supported, so a document containing one raises ValueError; and integers may be of "
        "any size (no 64-bit limit). Everything else in the spec is supported: comments; bare keys "
        "(A-Za-z0-9_-), quoted keys (basic and literal, including the empty key \"\") and dotted keys; basic "
        "strings with all escapes (\\b \\t \\n \\f \\r \\\" \\\\ \\uXXXX \\UXXXXXXXX, which must be Unicode "
        "scalar values), literal strings, and multi-line basic and literal strings (a newline right after the "
        "opening delimiter is trimmed; in multi-line basic strings a backslash at the end of a line removes it "
        "together with the whitespace and newlines that follow; up to two quotes may sit right before the "
        "closing delimiter); integers (decimal with an optional sign and no leading zeros, 0x 0o 0b prefixes "
        "without a sign, underscores only between digits); floats (a fractional part and/or an exponent, digits "
        "required on both sides of the point, underscores between digits; inf and nan with an optional sign; a "
        "float too large for Python becomes inf, as float() does); true and false; arrays (any mix of types; "
        "newlines, comments and a trailing comma allowed inside); inline tables (on one line, no trailing comma, "
        "closed for good: nothing can be added to them later); tables [a.b] and arrays of tables [[a.b]], with "
        "the spec's rules for defining tables and keys only once (dotted keys and headers create the tables "
        "they pass through; a table can't be defined twice with headers, nor a key or table redefined; static "
        "arrays and inline tables can't be extended). Control characters other than tab are not allowed in "
        "strings or comments; lines end with LF or CRLF (a lone CR is invalid). Results: tables are dicts, "
        "arrays lists, and the scalars str, int, float and bool. Raise ValueError (or a subclass) for any "
        "invalid document. Command line: python <script> FILE prints repr() of the result. In --test mode check "
        "every kind of value and key, tables and arrays of tables, and many invalid documents."),
    "struct": (
        "Create a Python module with pack(fmt, *values) -> bytes, unpack(fmt, data) -> tuple and "
        "calcsize(fmt) -> int that behave exactly like Python's struct module for format strings that start "
        "with a byte-order character < > ! or = (standard sizes, no alignment; = is the machine's own byte "
        "order), without using the struct, array, ctypes or numpy modules (int.to_bytes, int.from_bytes and math "
        "are allowed). A format with no byte-order character, or starting with @, raises ValueError. Format "
        "characters: x (pad byte), c (char: a bytes object of length 1), b B (1 byte), ? (bool), h H (2), i I "
        "l L (4), q Q (8), e (IEEE 754 half precision), f (single), d (double), s (bytes; the count is the "
        "length: shorter values are padded with zero bytes, longer ones cut), p (Pascal string: one length byte "
        "holding min(len, count-1, 255), then the bytes padded or cut to count-1). Each may have a decimal "
        "repeat count before it (0 allowed); whitespace may separate items but not a count from its character. "
        "As in struct: integer formats take ints, bools or objects with __index__, range-checked; ? packs any "
        "object by its truth value and unpacks a nonzero byte as True; float formats take ints, floats and "
        "objects with __float__, round to nearest with ties to even, and raise OverflowError when the rounded "
        "value is out of range (inf itself packs as inf); a nan packs as the quiet nan with its sign and an "
        "all-zero payload (e: 0x7e00); c takes bytes only, s and p take bytes or bytearray; unpack takes bytes "
        "or bytearray of exactly calcsize(fmt) bytes and returns s and p fields as bytes. Raise ValueError (or a "
        "subclass) wherever struct raises struct.error, and OverflowError wherever struct raises OverflowError. "
        "Command line: python <script> FMT VALUE... packs ints and floats and prints the bytes as hex. In --test "
        "mode check every format character, the byte orders, range limits, rounding and overflow of e and f, "
        "and the error cases."),
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


# ------------------------------------------------------------------------------------------- pyexpr
LIMIT_BITS = 1_000_000
EXPR_CHARS = set("0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_()+-*/%<>=!&|^~ \t")
BIN_OPS = {ast.BitOr: operator.or_, ast.BitXor: operator.xor, ast.BitAnd: operator.and_, ast.LShift: None,
           ast.RShift: None, ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
           ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: None}
CMP_OPS = {ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge,
           ast.Eq: operator.eq, ast.NotEq: operator.ne}
UN_OPS = {ast.USub: operator.neg, ast.UAdd: operator.pos, ast.Invert: operator.invert, ast.Not: operator.not_}


def _sized(v):
    if abs(v).bit_length() > LIMIT_BITS:
        raise ValueError("result over 1,000,000 bits")
    return v


def _valid(node):
    if isinstance(node, ast.Constant):
        if type(node.value) not in (int, bool):
            raise ValueError("outside the subset")
    elif isinstance(node, ast.BoolOp):
        for v in node.values:
            _valid(v)
    elif isinstance(node, ast.UnaryOp) and type(node.op) in UN_OPS:
        _valid(node.operand)
    elif isinstance(node, ast.BinOp) and type(node.op) in BIN_OPS:
        _valid(node.left)
        _valid(node.right)
    elif isinstance(node, ast.Compare) and all(type(o) in CMP_OPS for o in node.ops):
        _valid(node.left)
        for c in node.comparators:
            _valid(c)
    else:
        raise ValueError("outside the subset")


def _ev(node):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.BoolOp):
        v = None
        for sub in node.values:
            v = _ev(sub)
            if (not v) if isinstance(node.op, ast.And) else v:
                return v
        return v
    if isinstance(node, ast.UnaryOp):
        return _sized(UN_OPS[type(node.op)](_ev(node.operand)))
    if isinstance(node, ast.BinOp):
        a, b, op = _ev(node.left), _ev(node.right), type(node.op)
        if op is ast.Pow:
            if b < 0:
                raise ValueError("negative exponent")
            if abs(a) >= 2 and (abs(a).bit_length() - 1) * b >= LIMIT_BITS:
                raise ValueError("result over 1,000,000 bits")
            return _sized(a ** b)
        if op in (ast.LShift, ast.RShift):
            if b < 0:
                raise ValueError("negative shift count")
            if op is ast.RShift:
                return a >> b
            if a and abs(a).bit_length() + b > LIMIT_BITS:
                raise ValueError("result over 1,000,000 bits")
            return _sized(a << b)
        return _sized(BIN_OPS[op](a, b))
    left = _ev(node.left)
    for op, comp in zip(node.ops, node.comparators):
        right = _ev(comp)
        if not CMP_OPS[type(op)](left, right):
            return False
        left = right
    return True


def ref_pyexpr(expr):
    if any(c not in EXPR_CHARS for c in expr):
        raise ValueError("character outside the subset")
    old = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(0)
    try:
        tree = ast.parse(expr.strip(" \t"), mode="eval")
    except SyntaxError as e:
        raise ValueError(f"syntax: {e}") from None
    finally:
        sys.set_int_max_str_digits(old)
    _valid(tree.body)
    return _ev(tree.body)


def rx_literal(rng):
    r = rng.random()
    if r < 0.1:
        return rng.choice(["True", "False"])
    v = rng.choice([0, 1, 2, 3, 5, 7, 10, 12, 100, 255, rng.randint(0, 50), rng.randint(0, 10 ** 6),
                    rng.randint(0, 10 ** 20)])
    if r < 0.62:
        return _us(rng, str(v))
    if r < 0.95:
        base, pre = rng.choice([(16, "x"), (8, "o"), (2, "b")])
        digits = format(v, {16: "x", 8: "o", 2: "b"}[base])
        if base == 16 and rng.random() < 0.3:
            digits = digits.upper()
        return "0" + (pre.upper() if rng.random() < 0.3 else pre) + ("_" if rng.random() < 0.15 else "") + _us(rng, digits)
    return rng.choice(["00", "0_0", "000"])


def _us(rng, digits):
    if len(digits) < 2 or rng.random() < 0.75:
        return digits
    out = [digits[0]]
    for ch in digits[1:]:
        if rng.random() < 0.3:
            out.append("_")
        out.append(ch)
    return "".join(out)


RX_BINARY = ["or", "and", "<", "<=", ">", ">=", "==", "!=", "|", "^", "&", "<<", ">>", "+", "-", "*", "//", "%", "**"]


def rx_expr(rng, depth):
    """A random expression as a token list (keywords are tokens of their own)."""
    if depth <= 0 or rng.random() < 0.22:
        return [rx_literal(rng)]
    r = rng.random()
    if r < 0.14:
        op = rng.choice(["-", "+", "~", "not"])
        return [op] + _paren(rng, rx_expr(rng, depth - 1), 0.4)
    if r < 0.22:
        toks = _paren(rng, rx_expr(rng, depth - 1), 0.5)
        for _ in range(rng.randint(2, 3)):
            toks += [rng.choice(["<", "<=", ">", ">=", "==", "!="])] + _paren(rng, rx_expr(rng, depth - 2), 0.5)
        return toks
    op = rng.choice(RX_BINARY)
    left = _paren(rng, rx_expr(rng, depth - 1), 0.5)
    if op == "**":
        right = [str(rng.randint(0, 6))] if rng.random() < 0.8 else _paren(rng, rx_expr(rng, 1), 0.7)
    elif op in ("<<", ">>"):
        right = [str(rng.randint(0, 70))] if rng.random() < 0.85 else ["-", "1"]
    elif op in ("//", "%") and rng.random() < 0.15:
        right = ["0"]
    else:
        right = _paren(rng, rx_expr(rng, depth - 1), 0.5)
    return left + [op] + right


def _paren(rng, toks, p):
    return ["("] + toks + [")"] if len(toks) > 1 and rng.random() < p else toks


def rx_render(rng, toks):
    """Join tokens with random spacing; keywords always get a space or bracket next to them."""
    out = []
    for i, t in enumerate(toks):
        if i:
            word = t in ("and", "or", "not") or toks[i - 1] in ("and", "or", "not")
            out.append(rng.choice([" ", "  ", "\t"]) if word else rng.choice(["", "", " ", " ", "  "]))
        out.append(t)
    lead = rng.choice(["", "", "", " ", "\t"])
    return lead + "".join(out) + rng.choice(["", "", "", " "])


RX_BAD_TOKENS = ["(", ")", "+", "*", "/", "//", ".", "1.5", "1e3", "x", "None", "is", "in", "if", "=", "!", "#",
                 ",", "[0]", "'a'", "lambda", "0j", "**", "<", "not", "and", "<>", "===", ":="]
RX_BAD_LITERALS = ["01", "007", "1__0", "1_", "_1", "0x", "0b2", "0o8", "0x_", "0_1", "1_000_", "0b_", "0xg", "0X__1",
                   "1e5", "0.5", "1j", "00_1", "0xFF_"]


def rx_mutate(rng, toks):
    toks = list(toks)
    m = rng.randrange(6)
    i = rng.randrange(len(toks) + 1)
    if m == 0:
        toks.insert(i, rng.choice(RX_BAD_TOKENS))
    elif m == 1 and len(toks) > 1:
        del toks[min(i, len(toks) - 1)]
    elif m == 2:
        lits = [j for j, t in enumerate(toks) if t[0].isdigit()]
        if lits:
            toks[rng.choice(lits)] = rng.choice(RX_BAD_LITERALS)
        else:
            toks.insert(i, rng.choice(RX_BAD_LITERALS))
    elif m == 3:
        bools = [j for j, t in enumerate(toks) if t in ("True", "False")]
        if bools:
            toks[rng.choice(bools)] = rng.choice(["true", "TRUE", "false", "Truth"])
        else:
            toks.insert(i, "true")
    elif m == 4:
        toks.insert(i, rng.choice(["\n", "\x0c", "#c", "\\", ";"]))
    else:
        ops = [j for j, t in enumerate(toks) if t in RX_BINARY]
        if ops:
            j = rng.choice(ops)
            toks.insert(j, toks[j])
        else:
            toks.append(rng.choice(["+", "*", "**"]))
    return toks


PYEXPR_FIXED = [
    "1 + 2 * 3", "(1 + 2) * 3", "2 ** 3 ** 2", "-2 ** 2", "(-2) ** 2", "2 ** -1", "2 * -3 ** 2", "-3 // 2", "-3 % 2",
    "3 // -2", "3 % -2", "7 // 0", "7 % 0", "0 // 0", "1 < 2 < 3", "3 > 2 > 1", "1 < 3 > 2", "1 == 1 == 1",
    "1 == 1 != 2", "(1 < 2) < 3", "1 < (2 < 3)", "not 1 == 2", "not (1 == 2)", "not 0", "not 5", "not not 7",
    "0 or 5", "3 and 0", "0 and 1 // 0", "1 or 1 // 0", "1 < 0 < 1 // 0", "1 < 2 < 1 // 0", "True + True",
    "True & True", "True | False", "True ^ True", "~True", "-True", "+True", "True * 3", "True ** 2",
    "True // True", "True << 1", "1 & 3 == 1", "1 | 2 ^ 3 & 4", "1 << 2 + 1", "8 >> 1 + 1", "2 + 3 << 1",
    "1 << -1", "1 >> -1", "2 ** -0", "0 ** 0", "(-1) ** 1000001", "0 or False", "False or 0", "0 and False",
    "1 and True", "True and 5", "5 and True", "'a'", "1.5", "1e3", "1 / 2", "x", "1 is 1", "1 in 1",
    "1 if 1 else 2", "(1, 2)", "[1]", "f(1)", "1()", "(1)(2)", "1 +", "+ 1", "* 1", "1 2", "()", "(1", "1)", "",
    "   ", "\t1\t", " 1 + 2 ", "1\n+2", "1 # c", "1\x0c+ 2", "01", "00", "0_0", "0_1", "1__0", "1_", "_1", "0x",
    "0xFF", "0X_ff", "0o17", "0O7", "0b101", "0B_1", "0b2", "0o8", "0x_", "1_000_000", "not", "not not",
    "1 not 2", "1 == not 2", "1 + not 2", "not -1", "- not 1", "1//0 + )", "1 // 0 + x", "(1 // 0) and",
    "1 <> 2", "1 === 1", "1 != = 1", "1 => 2", "1 =< 2", "!1", "1 !", "~~5", "- - 1", "-~-~1", "2 ** 2 ** -1",
    "(2 ** 2) ** -1", "True < 2", "False == 0", "1 == True", "2 > True > False", "None", "true", "TRUE",
    "and", "1 and", "or 1", "1 or or 2", "1 ** 2 ** 3 ** 2", "4 // 2 // 2", "64 % 10 % 4", "2 - 3 - 4",
    "100 - 2 * 3 ** 2 // 4 % 5", "-(-(-(1)))", "not (0 or 0) and 1", "1 if", "lambda: 1", "0 < 1 is True",
    "(not 1) + 1", "not 1 + 1", "~0 == -1 == ~0", "5 % -3 * -1", "-5 // 2 ** 1", "2 ** 2 ** 2 ** 2",
    "(1 << 64) - 1 & 0xFF_FF", "0b1010 ^ 0o17 | 0x1F", "True + (1 < 2)", "(1 < 2) & (2 < 3)",
    "(1 < 2) | 5", "~(1 == 1)", "-(1 == 1)", "0 or 0 or 0", "1 and 2 and 3", "0 or 1 and 0", "(0 or 1) and 0",
    "1 == 1.0", "1 < 2 <", "< 1", "1 << 2 << 3", "256 >> 2 >> 1", "3 ** 0 ** 0", "(3 ** 0) ** 0"]
PYEXPR_FIXED_BIG = [
    "9 ** 9 ** 9", "2 ** 999999 > 0", "2 ** 1000000 > 0", "1 << 999999 > 0", "1 << 1000000", "10 ** 300000 > 0",
    "(10 ** 300000) * (10 ** 10) % 1000003", "-(2 ** 999999) * 2", "(-2) ** 999999 < 0", "7 ** 356000 % 1000",
    "7 ** 357000 % 1000", "0 ** (10 ** 100)", "1 ** (10 ** 100)", "(-1) ** (10 ** 100 + 1)", "2 ** (10 ** 100)",
    "1 << (10 ** 100)", "(1 << 999999) - 1 + (1 << 999999) > 0", "~((1 << 999999) - 1 + (1 << 999999))",
    "0 and 9 ** 9 ** 9", "1 or 9 ** 9 ** 9", "1 < 0 < 9 ** 9 ** 9", "9 ** 9 ** 9 + 1 // 0", "1 // 0 + 9 ** 9 ** 9"]


def pyexpr_big():
    """Inputs too deep or long for ast.parse, with expected values from closed forms (checked at a small
    scale against the reference by the selfcheck)."""
    d, out = 100_000, []
    unit = "(7*3-2//5%4<<1>>1|8&12^5)"
    v_unit = ref_pyexpr(unit)
    out += [("(" * d + "7" + ")" * d, ("ok", 7)), ("-" * d + "5", ("ok", 5)), ("-" * (d - 1) + "5", ("ok", -5)),
            ("~" * (d - 1) + "5", ("ok", -6)), ("not " * 50_000 + "0", ("ok", False)),
            ("not " * 50_001 + "0", ("ok", True)), ("(1+" * d + "1" + ")" * d, ("ok", d + 1)),
            ("1**" * d + "1", ("ok", 1)), ("2**" * d + "1", ("err", "ValueError")),
            ("1+" * 400_000 + "1", ("ok", 400_001)), ("1-" * 300_000 + "1", ("ok", 1 - 300_000)),
            ("-(" * d + "3" + ")" * d, ("ok", 3)), (" + ".join([unit] * 30_000), ("ok", 30_000 * v_unit)),
            ("9" * 100_000, ("ok", 10 ** 100_000 - 1)), ("1" + "0" * 99_999 + " // 1" + "0" * 99_997, ("ok", 100)),
            ("1_" * 50_000 + "1", ("ok", (10 ** 50_001 - 1) // 9)), ("0x" + "f" * 100_000, ("ok", 16 ** 100_000 - 1)),
            ("1 < 2 < " + " < ".join(str(i) for i in range(3, 100_003)), ("ok", True)),
            ("0 and (" + "1+" * 300_000 + "1//0)", ("ok", 0)),
            ("(" * 50_000 + "1 < 2" + ")" * 50_000 + " == 1", ("ok", True))]
    return out


def pyexpr_cases():
    rng, cases = random.Random(4001), []

    def add(part, expr, mode, limit, exp=None):
        e = exp if exp is not None else expect(ref_pyexpr, (expr,), ("ZeroDivisionError", "ValueError"))
        if e is not None:
            cases.append((part, "evaluate", (expr,), e, mode, limit))

    for expr in PYEXPR_FIXED:
        add("fixed", expr, "iso", 3.0)
    for expr in PYEXPR_FIXED_BIG:
        add("big", expr, "big", 10.0)
    for _ in range(700):
        add("random", rx_render(rng, rx_expr(rng, rng.randint(1, 6))), "iso", 3.0)
    for _ in range(320):
        add("invalid", rx_render(rng, rx_mutate(rng, rx_expr(rng, rng.randint(1, 4)))), "iso", 3.0)
    for expr, exp in pyexpr_big():
        add("big", expr, "big", 30.0, exp)
    return cases


def canon_pyexpr(v):
    return (type(v).__name__, v) if type(v) in (int, bool) else ("other", type(v).__name__)


# ------------------------------------------------------------------------------------------- toml
def _has_datetime(v):
    import datetime
    if isinstance(v, (datetime.date, datetime.time)):
        return True
    if isinstance(v, dict):
        return any(_has_datetime(x) for x in v.values())
    if isinstance(v, list):
        return any(_has_datetime(x) for x in v)
    return False


def ref_toml(text):
    v = tomllib.loads(text)
    if _has_datetime(v):
        raise ValueError("date and time values are not supported")
    return v


def canon_toml(v):
    if isinstance(v, bool):
        return ("bool", v)
    if isinstance(v, int):
        return ("int", v)
    if isinstance(v, float):
        return ("float", "nan") if v != v else ("float", v, math.copysign(1.0, v))
    if isinstance(v, str):
        return ("str", v)
    if isinstance(v, list):
        return ("list", tuple(canon_toml(x) for x in v))
    if isinstance(v, dict):
        return ("dict", frozenset((k if isinstance(k, str) else ("key", repr(k)), canon_toml(x)) for k, x in v.items()))
    return ("other", type(v).__name__)


T_BARE = ["a", "b", "c", "key", "name", "x1", "_", "-", "a-b", "a_b", "123", "true", "inf", "nan", "Z", "k-9_", "0"]
T_QUOTED = ["a b", "", "a.b", "\u00e9", "#", "=", "\u4e2d", 'q"', "tab\t", "x'y", "[k]"]
T_STR = ["", "hello", "a b", 'q"uote', "back\\slash", "tab\there", "new\nline", "\u00e9t\u00e9", "\u4e2d\u6587",
         "\U0001F600", "\x01ctrl", "'single'", "#not a comment", "= sign", "[brackets]", "trailing ", " leading",
         "\\n literal", "\x7f del", "cr\rhere", "form\x0cfeed", "bell\x08", 'two "" quotes', "three ''' singles",
         "ends with quote'", 'ends with dq"', "\nstarts with newline"]


def t_key(rng, used):
    for _ in range(30):
        if rng.random() < 0.8:
            k = rng.choice(T_BARE + T_QUOTED)
        else:
            k = "".join(rng.choice("abcxyz_-019") for _ in range(rng.randint(1, 6)))
        if k not in used:
            return k
    return f"k{len(used)}_{rng.randrange(10 ** 6)}"


def t_scalar(rng):
    r = rng.random()
    if r < 0.3:
        return rng.choice([0, 1, -1, 7, 42, -17, 1000, 2 ** 31, -2 ** 31, 2 ** 63 - 1, -2 ** 63, 2 ** 64, -(2 ** 70),
                           rng.randint(-10 ** 6, 10 ** 6), rng.randint(0, 2 ** 40)])
    if r < 0.5:
        return rng.choice([0.0, -0.0, 1.5, -2.25, 3.14159, 1e10, 6.02e23, 1e-7, 5e-324, 1.7976931348623157e308,
                           math.inf, -math.inf, math.nan, rng.uniform(-1e6, 1e6), rng.uniform(0, 1)])
    if r < 0.6:
        return rng.choice([True, False])
    if rng.random() < 0.7:
        return rng.choice(T_STR)
    return "".join(rng.choice("abc \u00e9\u4e2d\"\\\t\n'#") for _ in range(rng.randint(0, 10)))


def t_value(rng, depth):
    r = rng.random()
    if depth < 3 and r < 0.12:
        return [t_value(rng, depth + 1) for _ in range(rng.randint(0, 4))]
    if depth < 3 and r < 0.17:
        d = {}
        for _ in range(rng.randint(0, 3)):
            d[t_key(rng, d)] = t_value(rng, depth + 1)
        return d
    return t_scalar(rng)


def t_table(rng, depth):
    tbl = {}
    for _ in range(rng.randint(1 if depth == 0 else 0, 6 if depth == 0 else 3)):
        k, r = t_key(rng, tbl), rng.random()
        if depth < 2 and r < 0.2:
            tbl[k] = t_table(rng, depth + 1)
        elif depth < 2 and r < 0.28:
            tbl[k] = [t_table(rng, depth + 1) for _ in range(rng.randint(1, 3))]
        else:
            tbl[k] = t_value(rng, depth + 1)
    return tbl


def t_plain(c):
    return c == "\t" or (ord(c) >= 32 and ord(c) != 127)


def t_basic(rng, s):
    out = ['"']
    for c in s:
        if c == '"':
            out.append('\\"')
        elif c == "\\":
            out.append("\\\\")
        elif c in "\n\r\x08\x0c":
            out.append({"\n": "\\n", "\r": "\\r", "\x08": "\\b", "\x0c": "\\f"}[c])
        elif c == "\t":
            out.append(rng.choice(["\\t", "\t"]))
        elif not t_plain(c):
            out.append("\\u%04x" % ord(c))
        elif ord(c) > 127 and rng.random() < 0.3:
            out.append(("\\u%04X" % ord(c)) if ord(c) < 0x10000 else ("\\U%08x" % ord(c)))
        else:
            out.append(c)
    out.append('"')
    return "".join(out)


def t_ml_basic(rng, s):
    parts = []
    for c in s:
        if c == '"':
            parts.append('\\"')
        elif c == "\\":
            parts.append("\\\\")
        elif c in "\n\t":
            parts.append(c)
        elif not t_plain(c):
            parts.append("\\u%04x" % ord(c))
        else:
            parts.append(c)
    plain = [j for j in range(1, len(parts)) if len(parts[j]) == 1 and not parts[j].isspace()
             and len(parts[j - 1]) == 1 and parts[j - 1] not in "\n\t "]
    if plain and rng.random() < 0.4:
        j = rng.choice(plain)
        parts.insert(j, "\\" + rng.choice(["\n", "  \n", "\n\n"]) + rng.choice(["", "  ", "\t"]))
    lead = "\n" if s.startswith("\n") or rng.random() < 0.5 else ""
    return '"""' + lead + "".join(parts) + '"""'


def t_string(rng, s, inline):
    r = rng.random()
    if not inline and r < 0.12 and "\r" not in s:
        return t_ml_basic(rng, s)
    if (not inline and r < 0.2 and "'''" not in s and "\r" not in s
            and all(t_plain(c) or c == "\n" for c in s)):
        lead = "\n" if s.startswith("\n") or rng.random() < 0.5 else ""
        return "'''" + lead + s + "'''"
    if r < 0.4 and "'" not in s and all(t_plain(c) for c in s):
        return "'" + s + "'"
    return t_basic(rng, s)


def t_render_key(rng, k):
    if k and re.fullmatch(r"[A-Za-z0-9_-]+", k) and rng.random() < 0.85:
        return k
    if k and "'" not in k and all(t_plain(c) for c in k) and rng.random() < 0.4:
        return "'" + k + "'"
    return t_basic(rng, k)


def t_us(rng, digits):
    if len(digits) < 2 or rng.random() < 0.7:
        return digits
    out = [digits[0]]
    for ch in digits[1:]:
        if rng.random() < 0.25:
            out.append("_")
        out.append(ch)
    return "".join(out)


def t_int(rng, v):
    r = rng.random()
    if v >= 0 and r < 0.1:
        digits = format(v, "x")
        return "0x" + t_us(rng, "0" * rng.randint(0, 2) + (digits.upper() if rng.random() < 0.3 else digits))
    if v >= 0 and r < 0.16:
        return "0o" + t_us(rng, format(v, "o"))
    if v >= 0 and r < 0.22:
        return "0b" + t_us(rng, format(v, "b"))
    return ("-" if v < 0 else rng.choice(["", "", "", "+"])) + t_us(rng, str(abs(v)))


def t_float(rng, v):
    if v != v:
        return rng.choice(["nan", "+nan", "-nan"])
    if math.isinf(v):
        return "-inf" if v < 0 else rng.choice(["inf", "+inf"])
    s, sign = repr(v), ""
    if s[0] == "-":
        sign, s = "-", s[1:]
    elif rng.random() < 0.2:
        sign = "+"
    m = re.fullmatch(r"(\d+)(\.\d+)?(e[+-]?\d+)?", s)
    ip, fp, ex = m.group(1), m.group(2) or "", m.group(3) or ""
    if fp and rng.random() < 0.2:
        fp = "." + t_us(rng, fp[1:])
    if ex and rng.random() < 0.3:
        ex = "E" + ex[1:]
    return sign + t_us(rng, ip) + fp + ex


def t_render_value(rng, v, inline, crlf):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return t_int(rng, v)
    if isinstance(v, float):
        return t_float(rng, v)
    if isinstance(v, str):
        return t_string(rng, v, inline or crlf)
    if isinstance(v, list):
        parts = [t_render_value(rng, x, inline, crlf) for x in v]
        if inline or not parts or rng.random() < 0.6:
            sp = rng.choice(["", " "])
            return "[" + sp + ("," + rng.choice([" ", ""])).join(parts) + ("," if parts and rng.random() < 0.15 else "") + sp + "]"
        return "[\n" + "".join("  " + p + "," + (" # note" if rng.random() < 0.2 else "") + "\n" for p in parts) + "]"
    if not v:
        return rng.choice(["{}", "{ }"])
    items = [f"{t_render_key(rng, k)} = {t_render_value(rng, x, True, crlf)}" for k, x in v.items()]
    return "{ " + ", ".join(items) + " }" if rng.random() < 0.7 else "{" + ",".join(items) + "}"


def t_is_aot(v):
    return isinstance(v, list) and bool(v) and all(isinstance(x, dict) for x in v)


def t_emit(rng, tbl, path, out, crlf):
    later = []
    for k, v in tbl.items():
        key = t_render_key(rng, k)
        if isinstance(v, dict):
            style = rng.random()
            if style < 0.3:
                out.append(f"{key} = {t_render_value(rng, v, True, crlf)}")
            elif style < 0.5 and v and all(not isinstance(x, dict) and not t_is_aot(x) for x in v.values()):
                for kk, vv in v.items():
                    out.append(f"{key}.{t_render_key(rng, kk)} = {t_render_value(rng, vv, False, crlf)}")
            else:
                later.append(("table", k, v))
        elif t_is_aot(v) and rng.random() < 0.7:
            later.append(("aot", k, v))
        else:
            eq = rng.choice([" = ", "=", " =", "= ", "\t=\t"])
            out.append(rng.choice(["", "", "", "  "]) + key + eq + t_render_value(rng, v, False, crlf)
                       + rng.choice(["", "", "", "  # comment", " #c", " # \u00e9"]))
    for kind, k, v in later:
        hdr = ".".join(t_render_key(rng, x) for x in path + [k])
        if kind == "table":
            out.append(rng.choice(["", "\n# section"]))
            out.append(f"[{hdr}]" + rng.choice(["", "", " # c"]))
            t_emit(rng, v, path + [k], out, crlf)
        else:
            for item in v:
                out.append(f"[[{hdr}]]")
                t_emit(rng, item, path + [k], out, crlf)


def t_document(rng):
    """(text, structure): a random valid document and what it must parse to."""
    tbl, crlf, out = t_table(rng, 0), rng.random() < 0.15, []
    if rng.random() < 0.3:
        out.append("# generated document")
    t_emit(rng, tbl, [], out, crlf)
    text = "\n".join(out) + rng.choice(["", "\n"])
    return (text.replace("\n", "\r\n") if crlf else text), tbl


TOML_BAD_LINES = ["k = 1 2", "k = [1 2]", "k = {a = 1 b = 2}", "[a]]", "[[a]", "[ [a] ]", "[]", "[a.]", 'k = """',
                  "k = '''x", "k = 0x", "k = +0x1", "k = 1.", "k = .1", "k = 1e", "k = nan1", "k = infinity", "k = 0b2",
                  "k = 0o8", "k = 1__0", "k = 1_", "k = -0x1", "k = 00", "k = 01.5", "k = 1e1.5", "k = truee",
                  "x y = 1", "\u00e9 = 1", "a..b = 1", ".a = 1", "a. = 1", "= 1", "k = ", "k == 1", "k = 'a' 'b'",
                  "k = \"\\q\"", "k = \"\\u12\"", "k = \"\\UFFFFFFFF\"", "k = {a = 1,}", "k = [,]", "k = 1979-05-27"]


def t_mutate(rng, doc):
    text = doc[0]
    lines = text.split("\n")
    kv = [i for i, ln in enumerate(lines) if re.match(r"\s*[A-Za-z0-9_\"'-][^=\[]*=", ln)]
    hdr = [i for i, ln in enumerate(lines) if re.match(r"\s*\[[^\[]", ln)]
    root = [m.group(1) for m in re.finditer(r"(?m)^([A-Za-z0-9_-]+) = ([\[{])", text.split("\n[")[0])]
    m = rng.randrange(19)
    if m == 0 and kv:
        i = rng.choice(kv)
        lines.insert(i + 1, lines[i].split("=")[0] + "= 1")
    elif m == 1 and hdr:
        lines.append(lines[rng.choice(hdr)].split("#")[0].strip())
    elif m == 2 and "}" in text:
        return text.replace("}", ",}", 1)
    elif m == 3:
        return re.sub(r"= ?(\d)", r"= 0\1", text, count=1)
    elif m == 4:
        return re.sub(r"= ?(\d+)", lambda mo: "= " + rng.choice(["_", ""]) + mo.group(1) + rng.choice(["_", "__0"]), text, count=1)
    elif m == 5 and '"' in text:
        return text.replace('"', '"\\x41', 1)
    elif m == 6 and kv:
        i = rng.choice(kv)
        lines[i] = lines[i][::-1].replace('"', "", 1)[::-1]
    elif m == 7 and '= "' in text:
        return text.replace('= "', '= "a\nb', 1)
    elif m == 8 and root:
        k = rng.choice(root)
        lines.append(rng.choice([f"{k}.zz = 1", f"[{k}.zz]", f"[[{k}]]", f"[{k}]"]))
    elif m == 9:
        lines.insert(rng.randrange(len(lines) + 1), "d = " + rng.choice(
            ["1979-05-27", "07:32:00", "1979-05-27T07:32:00Z", "1979-05-27 07:32:00", "1979-05-27T00:32:00.999-07:00"]))
    elif m == 10 and "true" in text:
        return text.replace("true", "True", 1)
    elif m == 11 and "\n" in text:
        i = rng.choice([j for j, c in enumerate(text) if c == "\n"])
        return text[:i] + "\r" + text[i + 1:]
    elif m == 12 and '"' in text:
        return text.replace('"', '"\x01', 1)
    elif m == 13 and "{ " in text:
        return text.replace("{ ", "{\n", 1)
    elif m == 14:
        lines.append(rng.choice(["# bad \x01 char", "# del \x7f", "a = 1 # \x00"]))
    elif m == 15 and len(text) > 1:
        i = rng.randrange(len(text))
        return text[:i] + text[i + 1:]
    elif m == 16 and len(text) > 1:
        i = rng.randrange(len(text))
        return text[:i] + rng.choice("=[]{}\"',.#\\ ") + text[i:]
    else:
        lines.insert(rng.randrange(len(lines) + 1), rng.choice(TOML_BAD_LINES))
    return "\n".join(lines)


TOML_FIXED = [
    "a = 9223372036854775808", "a = -9223372036854775809", "a = 01", "a = +0x1", "a = 0x", "a = 1__2", "a = 1_",
    "a = .5", "a = 5.", "a = 1_0.0_1", "a = 0.0_1", "a = 1e+05", "a = -nan", "a = -0.0", "a = {b = 1,}",
    "a = {\nb = 1}", "a.b = 1\n[a]", "[a.b]\n[a]", "[a]\nb.c = 1\n[a.b]", "[a]\n[a]", "a = [1]\n[[a]]",
    "a = {b=1}\n[a.c]", "a = {b=1}\na.c = 2", "[[a]]\n[a]", "[a]\n[[a]]", 'a = "\\x41"', 'a = "\\ud800"',
    'a = "\\U00110000"', 'a = """\nx"""', 'a = """x\\\n   y"""', "a = '''\nx'''", 'a = "t\tb"', 'a = "c\x01"',
    'a = "d\x7f"', "a = 1979-05-27", "a = 07:32:00", '"" = 1', "a b = 1", 'a."b.c" = 1', "3.14159 = 'pi'",
    "\u00fc = 1", "a = 1\rb = 2", "a = 1\r\nb = 2", "a = [,]", "a = [1,,2]", "a = True", "[ a . b ]\nc=1",
    "[[ a ]]", "[ [a] ]", "a = 0", "a = -0", "a = +1", "a = 0o17", "a = 0b_1", "a = 0x_1", "a = 1e1_0", "a = 1.e5",
    "a = inf\nb = -inf\nc = +nan", "a = 9_223_372_036_854_775_807", "a.b.c = 1\na.b.d = 2", "a = {b.c = 1}",
    "a = {b = 1, b = 2}", "[a]\nb = 1\n[a]\nc = 2", "a = []\n[[a]]", "[[a]]\nb = 1\n[[a]]\nb = 2",
    "[[a.b]]\n[a]\nc = 1", "x = 'a'\"b\"", "a = 1 # c\n# d", 'a = """a"""""', "a = '''''''", 'a = """"""',
    "a = 1979-05-27T07:32:00Z", 'a = "\\e"', 'a = "\\u00e9"', "a = 'x' # \x01", "a = 0xDEADbeef", "a = 0xG",
    "a = 1e400", "a = 2_.0", "a = 1._2", "[a]\n[a.b]\n[a]", "a = 1 b = 2", 'a = "x" \n', "a=1#c", "[a] # c\n",
    "[a]x", "a = [1 2]", "a = { }", "a = {b = {c = 1}}\n[a.b.d]", "a.b = 1\na = 2", "a = 1\na.b = 2",
    "[a]\n[b]\n[a.c]", "a = '''a''''", "a = 1_000_000", "", "\n\n# only comments\n", "x = 1 # c\n# full\n\n",
    "[a]\nb = 1\n[a.c]\nd = 2\n[e]\n", "[x.y.z]\n[x]\nw = 1",
    "[[fruit]]\nname = 'apple'\n[fruit.physical]\ncolor = 'red'\n[[fruit.variety]]\nname = 'red delicious'\n"
    "[[fruit]]\nname = 'banana'\n[[fruit.variety]]\nname = 'plantain'",
    "a = [[1, 2], ['a', 'b'], [1.5, true]]", "a = [ { x = 1 }, { y = [1, 2] } ]", 'k = """\\\n  hello \\\n  world"""',
    "k = '''\nline1\nline2'''", 'k = """a\\tb\\u00e9\\U0001F600"""', 'site."google.com" = true',
    "a.b.c = 1\na.d = 2\n[a.e]\nf = 3", "a = [\n  1,\n  2, # two\n]", "a = [\n]\nb = [ # c\n 1 ]",
    "'' = 1", "a = \"\"\"\\\n\n\n  x\"\"\"", "a = 'it''s'", "a = '\\\\'", 'a = "\\\\\\""', "a = 1.0e-3",
    "a = -1E+3", "a = 6.626e-34", "a = 0e0", "a = +0.0", "a = 1_000.000_1", "a = 0x0", "a = 0o0", "a = 0b0",
    "a = 0x_0", "a = -0x0", "a = 0b11_01", "a = 0o7_7", "a = 99999999999999999999999999", "[a.b.c]\n[a.b]\n[a]",
    "[a]\nb = {}\n[a.b.c]", "[a]\n\"b\" = 1\nb = 2", "a.'b' = 1\na.\"b\" = 2", "[[a]]\n[[a.b]]\n[a.b.c]\nd = 1",
    "[ a ]\n[ a.b ]", "a = [1,]", "a = [1, [2, [3, [4]]]]", "a = { b = [1, 2], c = { d = 'e' } }",
    "a = \"\"\"\n\"\"\"", "a = '''\n'''", "a = '''x\r\ny'''", "a = \"\"\"x\r\ny\"\"\"", "key = \"value\"\r\n[t]\r\nx = 1\r\n",
    "a = \"\\U0001F600\"", "a = \"\\uD83D\\uDE00\"", "\t[a]\n\tb = 1", "a = 1 \t# tab before comment",
    "[a]\nb = 1\n\n[[c]]\nd = 2\n\n[[c]]\n\n[a.e]", "a = [{}, {}]\n", "a = 1\n[[a]]", "[[a]]\na = 1\n[[a]]\n[a.x]",
    "a = inf\nb = nan\nc = -inf\nd = +inf", "a = 1e-400", "a = 1.7976931348623159e308", "a = 0.1e1_0"]
TOML_BIG = [
    "\n".join(f"k{i} = {i}" for i in range(20_000)),
    "a = [" + ", ".join(str(i) for i in range(60_000)) + "]\n" + "".join(f"[t{i}]\nv = '{i}'\n" for i in range(3_000)),
    "[[items]]\nn = 0\n" + "".join(f"[[items]]\nn = {i}\ns = \"line {i}\\n\"\n" for i in range(1, 8_000))]


def toml_cases():
    rng, cases = random.Random(4002), []

    def add(part, text, limit=3.0):
        e = expect(ref_toml, (text,), ("ValueError",))
        if e is not None:
            cases.append((part, "loads", (text,), e, "iso", limit))

    for doc in TOML_FIXED:
        add("fixed", doc)
    for _ in range(420):
        add("valid", t_document(rng)[0])
    for doc in TOML_BIG:
        add("valid", doc, 20.0)
    for _ in range(460):
        add("invalid", t_mutate(rng, t_document(rng)))
    return cases


# ------------------------------------------------------------------------------------------- struct
class FormatError(ValueError):
    pass


class Idx:
    def __init__(self, v):
        self.v = v

    def __index__(self):
        return self.v

    def __repr__(self):
        return f"Idx({self.v})"


class Flt:
    def __init__(self, v):
        self.v = v

    def __float__(self):
        return self.v

    def __repr__(self):
        return f"Flt({self.v!r})"


def _prefix(fmt):
    if not isinstance(fmt, str) or not fmt or fmt[0] not in "<>!=":
        raise FormatError("a format must start with <, >, ! or =")


def ref_pack(fmt, *values):
    _prefix(fmt)
    try:
        return struct.pack(fmt, *values)
    except struct.error as e:
        raise FormatError(str(e)) from None


def ref_unpack(fmt, data):
    _prefix(fmt)
    try:
        return struct.unpack(fmt, data)
    except struct.error as e:
        raise FormatError(str(e)) from None


def ref_calcsize(fmt):
    _prefix(fmt)
    try:
        return struct.calcsize(fmt)
    except struct.error as e:
        raise FormatError(str(e)) from None


S_INT = {"b": (-128, 127), "B": (0, 255), "h": (-2 ** 15, 2 ** 15 - 1), "H": (0, 2 ** 16 - 1),
         "i": (-2 ** 31, 2 ** 31 - 1), "I": (0, 2 ** 32 - 1), "l": (-2 ** 31, 2 ** 31 - 1), "L": (0, 2 ** 32 - 1),
         "q": (-2 ** 63, 2 ** 63 - 1), "Q": (0, 2 ** 64 - 1)}
S_CHARS = "xcbB?hHiIlLqQefdsp"
S_EXP = {"e": (-27, 17), "f": (-152, 130), "d": (-1074, 1023)}


def s_near(rng, ch):
    """A value of format e or f, the midpoint to its neighbour (a tie), or just either side of it."""
    if ch == "d":
        x = struct.unpack("<d", rng.getrandbits(64).to_bytes(8, "little"))[0]
        return 1.0 if x != x else x
    width = 2 if ch == "e" else 4
    bits = rng.getrandbits(8 * width - 1)
    a = struct.unpack("<" + ch, bits.to_bytes(width, "little"))[0]
    b = struct.unpack("<" + ch, (bits + 1).to_bytes(width, "little"))[0]
    if not (math.isfinite(a) and math.isfinite(b)):
        return a
    mid = (a + b) / 2
    x = rng.choice([a, mid, mid, math.nextafter(mid, math.inf), math.nextafter(mid, -math.inf)])
    return -x if rng.random() < 0.3 else x


def s_value(rng, ch):
    r = rng.random()
    if ch in S_INT:
        lo, hi = S_INT[ch]
        if r < 0.25:
            return rng.choice([lo, hi, 0, 1, -1 if lo < 0 else 2])
        if r < 0.32:
            return rng.choice([lo - 1, hi + 1])
        if r < 0.38:
            return rng.choice([True, False])
        if r < 0.44:
            return Idx(rng.randint(lo, hi))
        if r < 0.48:
            return rng.choice([1.0, "1", None, b"1", 2.5])
        return rng.randint(lo, hi)
    if ch == "?":
        return rng.choice([0, 1, 2, -1, "", "x", [], [0], None, 0.0, 1.5, True, False])
    if ch == "c":
        return rng.choice([b"a", b"\x00", b"\xff", b"Z", b"a", b"", b"ab", bytearray(b"a"), "a"])
    if r < 0.15:
        return rng.choice([0.0, -0.0, math.inf, -math.inf, math.nan, -math.nan, 1.0, -1.0])
    if r < 0.22:
        return rng.choice([1, 0, -3, True, Flt(0.25), 3])
    if r < 0.25:
        return rng.choice(["1.0", None, b"x"])
    if r < 0.55:
        lo, hi = S_EXP[ch]
        return rng.choice([1, -1]) * rng.uniform(1, 2) * 2.0 ** rng.randint(lo, hi)
    return s_near(rng, ch)


def s_bytes(rng, n):
    r = rng.random()
    if r < 0.06:
        return rng.choice(["str", None, 5])
    v = bytes(rng.randrange(256) for _ in range(rng.choice([0, 1, max(0, n - 1), n, n, n + 1, n + 3, 260])))
    return bytearray(v) if r < 0.2 else v


def s_format(rng):
    prefix, items, values = rng.choice("<>!="), [], []
    for _ in range(rng.randint(1, 5)):
        ch, r = rng.choice(S_CHARS), rng.random()
        if r < 0.6:
            count = None
        elif ch in "spx":
            count = rng.choice([0, 1, 2, 3, 5, 8, 16, 255, 256, 257, 300])
        else:
            count = rng.randint(0, 4)
        cs = "" if count is None else (("0" if rng.random() < 0.05 else "") + str(count))
        items.append(rng.choice(["", "", "", " ", "\t", "\n "]) + cs + ch)
        n = 1 if count is None else count
        if ch in "sp":
            values.append(s_bytes(rng, n))
        elif ch != "x":
            values.extend(s_value(rng, ch) for _ in range(n))
    return prefix + "".join(items) + rng.choice(["", "", " "]), values


def s_break(rng, fmt, values):
    m = rng.randrange(8)
    if m == 0:
        return fmt[1:], values
    if m == 1:
        return "@" + fmt[1:], values
    if m == 2:
        return re.sub(r"(\d)([a-zA-Z?])", r"\1 \2", fmt, count=1) if re.search(r"\d[a-zA-Z?]", fmt) else fmt + "3 i", values
    if m == 3:
        i = rng.randrange(1, len(fmt) + 1)
        return fmt[:i] + rng.choice("znNPZg@<") + fmt[i:], values
    if m == 4:
        return fmt + rng.choice(["3", "12"]), values
    if m == 5:
        return fmt, values[:-1]
    if m == 6:
        return fmt, values + [rng.choice([0, b"x", 1.5])]
    return fmt + rng.choice(["<h", "!"]), values + [1]


def struct_cases():
    rng, cases = random.Random(4003), []

    def add(part, name, args, limit=3.0):
        ref = {"pack": ref_pack, "unpack": ref_unpack, "calcsize": ref_calcsize}[name]
        e = expect(ref, args, ("OverflowError", "ValueError"))
        if e is not None:
            cases.append((part, name, args, e, "iso", limit))

    for name, args in STRUCT_FIXED:
        add("fixed", name, args)
    for _ in range(420):
        fmt, values = s_format(rng)
        if rng.random() < 0.25:
            fmt, values = s_break(rng, fmt, values)
        add("pack", "pack", (fmt, *values))
    for _ in range(240):
        fmt, _ = s_format(rng)
        try:
            size = struct.calcsize(fmt)
        except struct.error:
            continue
        r = rng.random()
        n = size + (rng.choice([-1, 1, 5]) if r < 0.12 else 0)
        data = bytes(rng.randrange(256) for _ in range(max(0, n)))
        if r > 0.85:
            data = bytearray(data)
        if r < 0.05:
            fmt = fmt[1:]
        add("unpack", "unpack", (fmt, data))
    for _ in range(120):
        fmt, values = s_format(rng)
        if rng.random() < 0.35:
            fmt = s_break(rng, fmt, values)[0]
        add("calcsize", "calcsize", (fmt,))
    for _ in range(320):
        ch = rng.choice("eeeffd")
        add("floats", "pack", (rng.choice("<>!=") + ch, s_near(rng, ch) if rng.random() < 0.8 else s_value(rng, ch)))
    all_halves = b"".join(i.to_bytes(2, "little") for i in range(65536))
    for k in range(64):
        add("floats", "unpack", ("<1024e", all_halves[k * 2048:(k + 1) * 2048]))
    for k in range(20):
        add("floats", "unpack", (">100f", bytes(rng.randrange(256) for _ in range(400))))
    return cases


STRUCT_FIXED = [
    ("pack", ("<e", 65504.0)), ("pack", ("<e", 65519.99)), ("pack", ("<e", 65520.0)), ("pack", ("<e", 65536.0)),
    ("pack", ("<e", -65520.0)), ("pack", ("<e", 2.0 ** -24)), ("pack", ("<e", 2.0 ** -25)),
    ("pack", ("<e", math.nextafter(2.0 ** -25, 1))), ("pack", ("<e", 3 * 2.0 ** -26)), ("pack", ("<e", 2.0 ** -14)),
    ("pack", ("<e", 2049.0)), ("pack", ("<e", 2051.0)), ("pack", ("<e", 0.1)), ("pack", ("<e", -0.0)),
    ("pack", ("<e", math.inf)), ("pack", ("<e", -math.inf)), ("pack", ("<e", math.nan)), ("pack", ("<e", -math.nan)),
    ("pack", (">e", 1e10)), ("pack", ("<e", 1e-8)), ("pack", ("<e", 3)), ("pack", ("<e", True)),
    ("pack", ("<f", 3.4028234663852886e38)), ("pack", ("<f", 3.4028235677973366e38)),
    ("pack", ("<f", math.nextafter(3.4028235677973366e38, 0))), ("pack", ("<f", 1e39)), ("pack", ("<f", 2.0 ** -149)),
    ("pack", ("<f", 2.0 ** -150)), ("pack", ("<f", math.nextafter(2.0 ** -150, 1))), ("pack", ("<f", 1e-50)),
    ("pack", (">f", -0.0)), ("pack", ("<f", 16777217.0)), ("pack", ("<f", 16777219.0)), ("pack", ("<f", 0.1)),
    ("pack", ("<f", math.nan)), ("pack", ("<f", -math.nan)), ("pack", ("<f", -1e300)), ("pack", ("<d", 5e-324)),
    ("pack", ("<d", -math.nan)), ("pack", ("<d", 1.7976931348623157e308)), ("pack", ("!d", math.pi)),
    ("pack", ("<0p", b"x")), ("pack", ("<1p", b"abc")), ("pack", ("<300p", b"x" * 300)), ("pack", ("<5p", b"hi")),
    ("pack", ("<5p", b"hello world")), ("pack", ("<256p", b"y" * 256)), ("pack", ("<257p", b"y" * 300)),
    ("pack", ("<3p", bytearray(b"ab"))), ("pack", (" <i", 1)), ("pack", ("< i", 1)), ("pack", ("<3 i", 1, 2, 3)),
    ("pack", ("<i ", 1)), ("pack", ("<\ti\n", 1)), ("pack", ("<i", True)), ("pack", ("<i", 1.0)),
    ("pack", ("<c", bytearray(b"a"))), ("pack", ("<2s", bytearray(b"ab"))), ("pack", ("<s", "x")),
    ("pack", ("<?", "x")), ("pack", ("<?", [])), ("pack", ("<?", 0.0)), ("pack", ("<q", 2 ** 63)),
    ("pack", ("<Q", -1)), ("pack", ("<Q", 2 ** 64 - 1)), ("pack", ("<b", -129)), ("pack", ("<B", 256)),
    ("pack", ("<h", Idx(7))), ("pack", ("<h", Idx(40000))), ("pack", ("<d", Flt(1.5))), ("pack", ("<d", "1.0")),
    ("pack", ("<d", None)), ("pack", ("i", 1)), ("pack", ("@h", 1)), ("pack", ("<3", 1)), ("pack", ("<z", 1)),
    ("pack", ("<i<", 1)), ("pack", ("<",)), ("pack", ("<0c",)), ("pack", ("<0s", b"abc")), ("pack", ("<2s", b"a")),
    ("pack", ("<ii", 1)), ("pack", ("<i", 1, 2)), ("pack", ("<02h", 1, 2)), ("pack", ("<xh", 1)), ("pack", ("!h", 1)),
    ("pack", ("=h", 1)), ("pack", (">Q", 2 ** 64 - 1)), ("pack", ("<n", 1)), ("pack", ("<P", 1)), ("pack", ("<c", b"")),
    ("pack", ("<c", b"ab")), ("pack", ("<c", "a")), ("pack", ("<3c", b"a", b"b", b"c")), ("pack", ("<2?", 5, "")),
    ("pack", ("<4x",)), ("pack", ("<hxxh", 1, 2)), ("pack", (">bhiq", -1, -1, -1, -1)), ("pack", ("<10s", b"short")),
    ("unpack", ("<i", b"\x00" * 5)), ("unpack", ("<e", b"\x00\xfe")), ("unpack", ("<?", b"\x02")),
    ("unpack", ("<0s", b"")), ("unpack", ("<5p", b"\x09abcd")), ("unpack", ("<5p", b"\x02abcd")),
    ("unpack", ("<2c", b"ab")), ("unpack", ("<h", bytearray(b"\x01\x00"))), ("unpack", (">h", b"\xff\xfe")),
    ("unpack", ("<e", b"\x01\x00")), ("unpack", ("<e", b"\xff\x7b")), ("unpack", ("<f", b"\x01\x00\x80\x7f")),
    ("unpack", ("<3x", b"abc")), ("unpack", ("i", b"\x00" * 4)), ("unpack", ("<i", b"")), ("unpack", ("<3?", b"\x00\x01\xff")),
    ("unpack", (">Q", b"\xff" * 8)), ("unpack", ("<q", b"\x00" * 7 + b"\x80")), ("unpack", ("!d", b"\x7f\xf0" + b"\x00" * 6)),
    ("unpack", ("<4s", b"ab\x00\x00")), ("unpack", ("<1p", b"\x05")),
    ("calcsize", ("<5x",)), ("calcsize", ("<",)), ("calcsize", ("<0p",)), ("calcsize", ("<2e3f4d",)),
    ("calcsize", ("<qQiIlLhHbB?cxe",)), ("calcsize", ("i",)), ("calcsize", ("@i",)), ("calcsize", ("<3",)),
    ("calcsize", ("< 10s 2p",)), ("calcsize", ("<10 s",)), ("calcsize", ("!300p",)), ("calcsize", ("=0q0s",))]


def canon_struct(v):
    if isinstance(v, tuple):
        return ("tuple", tuple(canon_struct(x) for x in v))
    if isinstance(v, float):
        return ("float", "nan") if v != v else ("float", v, math.copysign(1.0, v))
    if isinstance(v, bool):
        return ("bool", v)
    if isinstance(v, int):
        return ("int", v)
    if isinstance(v, (bytes, bytearray)):
        return (type(v).__name__, bytes(v))
    return ("other", type(v).__name__)


# ------------------------------------------------------------------------------------------- driver
TASKS = {"pyexpr": (pyexpr_cases, canon_pyexpr, ["fixed", "random", "invalid", "big"]),
         "toml": (toml_cases, canon_toml, ["fixed", "valid", "invalid"]),
         "struct": (struct_cases, canon_struct, ["fixed", "pack", "unpack", "calcsize", "floats"])}
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
    if name in ("evaluate", "loads"):
        text = args[0]
        return (repr(text[:70]) + (f"... ({len(text)} chars)" if len(text) > 70 else ""))
    return f"{name}{short(args, 90)}"


def check(task, path):
    warnings.simplefilter("ignore")
    build, canon, parts = TASKS[task]
    signal.signal(signal.SIGALRM, _on_alarm)
    cases = build()
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
    small = [("(" * 50 + "7" + ")" * 50, 7), ("-" * 50 + "5", 5), ("-" * 49 + "5", -5), ("~" * 49 + "5", -6),
             ("not " * 50 + "0", False), ("not " * 51 + "0", True), ("(1+" * 50 + "1" + ")" * 50, 51),
             ("1**" * 50 + "1", 1), ("1+" * 400 + "1", 401), ("1-" * 300 + "1", -299), ("-(" * 50 + "3" + ")" * 50, 3),
             ("1_" * 50 + "1", int("1" * 51)), ("2**2**2**2**1", 65536), ("0 and (" + "1+" * 50 + "1//0)", 0),
             ("(" * 50 + "1 < 2" + ")" * 50 + " == 1", True), ("1 < 2 < " + " < ".join(str(i) for i in range(3, 60)), True)]
    for expr, want in small:
        got = call(ref_pyexpr, (expr,), 10)
        if got != ("ok", want) or type(got[1]) is not type(want):
            problems.append(f"pyexpr closed form {expr[:30]!r}: {got}")
    if expect(ref_pyexpr, ("2**" * 6 + "1",), ("ValueError",)) != ("err", "ValueError"):
        problems.append("pyexpr: 2**...**1 six deep should be too large")
    rng = random.Random(1)
    for i in range(300):
        text, tbl = t_document(rng)
        try:
            if canon_toml(tomllib.loads(text)) != canon_toml(tbl):
                problems.append(f"toml serializer, document {i}: parses to something else:\n{text[:300]}")
        except tomllib.TOMLDecodeError as e:
            problems.append(f"toml serializer, document {i}: invalid ({e}):\n{text[:300]}")
    for want, fmt, v in [(b"\x00\x7e", "<e", math.nan), (b"\x00\xfe", "<e", -math.nan),
                         (b"\x00\x00\xc0\x7f", "<f", math.nan), (b"\x00\x00\xc0\xff", "<f", -math.nan),
                         (b"\x00" * 6 + b"\xf8\x7f", "<d", math.nan), (b"\x00" * 6 + b"\xf8\xff", "<d", -math.nan)]:
        if struct.pack(fmt, v) != want:
            problems.append(f"struct nan pattern for {fmt} {v}: {struct.pack(fmt, v)!r}")
    for task, (build, _canon, parts) in TASKS.items():
        cases = build()
        kinds = {}
        for c in cases:
            kinds.setdefault(c[0], [0, 0])[0 if c[3][0] == "ok" else 1] += 1
        print(task, len(cases), "cases:", ", ".join(f"{p} {kinds.get(p, [0, 0])[0]} ok + {kinds.get(p, [0, 0])[1]} errors" for p in parts))
    print("\n".join(problems) if problems else "selfcheck OK")


if __name__ == "__main__":
    if sys.argv[1:] == ["selfcheck"]:
        selfcheck()
    else:
        check(sys.argv[1], sys.argv[2])
