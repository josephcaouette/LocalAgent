# --- added by the pipeline: load the script under test without running its main block ---
import importlib.util as _ilu
import subprocess as _sp
import sys as _sys

_spec = _ilu.spec_from_file_location("target_module", "/work/struct_max_v3.py")
target = _ilu.module_from_spec(_spec)
_sys.modules["target_module"] = target
_sys.modules["target"] = target          # so `import target` works too
_spec.loader.exec_module(target)


def run_script(*args, input=None, timeout=15):
    """Run the script as a separate process. Returns subprocess.CompletedProcess (text mode)."""
    return _sp.run([_sys.executable, "/work/struct_max_v3.py", *map(str, args)], input=input,
                   capture_output=True, text=True, timeout=timeout)

# --- independent acceptance test ---
import sys, random, struct as S

fails = []

def check(name, cond, exp=None, got=None):
    if cond:
        print(f"PASS: {name}")
    else:
        print(f"FAIL: {name} expected {exp!r}, got {got!r}")
        fails.append(name)

def exc(fn, *a, **k):
    try:
        fn(*a, **k)
        return None
    except Exception as e:
        return e

def isV(e): return isinstance(e, ValueError)
def isO(e): return isinstance(e, OverflowError)

# Acceptance checks for --test
r = run_script("--test")
lines = [l.strip() for l in r.stdout.strip().splitlines()]
check("--test exit 0", r.returncode == 0, 0, r.returncode)
check("--test last line OK", bool(lines) and lines[-1] == "OK", "OK", lines[-1] if lines else None)
for s in ["PASS formats", "PASS byte orders", "PASS range limits",
          "PASS rounding overflow", "PASS errors"]:
    check(f"--test contains {s}", s in lines, s, lines)

# calcsize: valid formats compared with struct, invalid formats must raise ValueError
valid_fmts = ["<B", "<2B", "<3s", "<5p", "<0s", "<0c", "<0x", "<2x",
              "<e", "<f", "<d", "  <B  ", "< B", "< 1B", ">h", "!f", "=q"]
for fmt in valid_fmts:
    e1, e2 = exc(S.calcsize, fmt), exc(target.calcsize, fmt)
    if e1 is None:
        check(f"calcsize {fmt!r}", e2 is None and target.calcsize(fmt) == S.calcsize(fmt),
              S.calcsize(fmt), e2 if e2 is not None else target.calcsize(fmt))
    else:
        check(f"calcsize {fmt!r} invalid", isV(e2), "ValueError", repr(e2))

for fmt in ["B", "@B", "<z", "<1 B", "<0p", "<B1", "<1.5B", "<-1B", "< 1 B"]:
    check(f"calcsize invalid {fmt!r}", isV(exc(target.calcsize, fmt)), "ValueError",
          repr(exc(target.calcsize, fmt)))

def compare_pack(fmt, vals, name=None):
    name = name or f"pack {fmt!r} {vals!r}"
    e1 = exc(S.pack, fmt, *vals)
    e2 = exc(target.pack, fmt, *vals)
    if e1 is None:
        ok = e2 is None and target.pack(fmt, *vals) == S.pack(fmt, *vals)
        check(name, ok, S.pack(fmt, *vals), e2 if e2 is not None else target.pack(fmt, *vals))
    else:
        ok = isO(e2) if isinstance(e1, OverflowError) else isV(e2)
        check(name, ok, type(e1).__name__, repr(e2))

def compare_unpack(fmt, data, name=None):
    name = name or f"unpack {fmt!r} {data!r}"
    e1 = exc(S.unpack, fmt, data)
    e2 = exc(target.unpack, fmt, data)
    if e1 is None:
        ok = e2 is None and target.unpack(fmt, data) == S.unpack(fmt, data)
        check(name, ok, S.unpack(fmt, data), e2 if e2 is not None else target.unpack(fmt, data))
    else:
        check(name, isV(e2), "ValueError", repr(e2))

# Known / tricky cases, using struct as the exact reference where possible
compare_pack("<B", (65,))
compare_pack("<2B", (1, 2))
compare_pack("<b", (-1,))
compare_pack("<h", (1,))
compare_pack(">h", (1,))
compare_pack("!h", (1,))
compare_pack("=h", (1,))
compare_pack("<c", (b"a",))
compare_pack("<2c", (b"a", b"b"))
compare_pack("<3s", (b"ab",))
compare_pack("<0s", (b"abc",))
compare_pack("<5p", (b"ab",))
compare_pack("<1p", (b"abc",))
compare_pack("<0c", ())
compare_pack("<2x", ())
compare_pack("<e", (1.0,))
compare_pack("<f", (1.0,))
compare_pack("<d", (1.0,))
compare_pack("<e", (float("inf"),))
compare_pack("<e", (-float("inf"),))
compare_pack("<e", (float("nan"),))
compare_pack("<e", (-float("nan"),))
compare_pack("<e", (-0.0,))
compare_pack("<f", (float("inf"),))
compare_pack("<f", (-float("inf"),))
compare_pack("<f", (float("nan"),))
compare_pack("<f", (-float("nan"),))
compare_pack("<f", (-0.0,))
compare_pack("<e", (65504.0,))
compare_pack("<e", (65519.0,))
compare_pack("<e", (65520.0,))
compare_pack("<e", (5.960464477539063e-08,))
compare_pack("<e", (2.9802322387695312e-08,))
compare_pack("<f", (3.4028234663852886e+38,))
compare_pack("<f", (3.402823564422953e+38,))
compare_pack("<f", (1e39,))
compare_pack("<e", (1e30,))
compare_pack("<f", (10**400,))
compare_pack("<d", (10**400,))

# Type and range behavior
class Idx:
    def __init__(self, v): self.v = v
    def __index__(self): return self.v

check("__index__ accepted", target.pack("<B", Idx(5)) == b"\x05")
check("__index__ out of range", isV(exc(target.pack, "<B", Idx(256))))
check("bool accepted as int", target.pack("<b", True) == b"\x01" and target.pack("<b", False) == b"\x00")
check("float rejected for int", isV(exc(target.pack, "<B", 1.0)))
check("? truth packing", target.pack("<?", True) == b"\x01" and target.pack("<?", 0) == b"\x00" and target.pack("<?", []) == b"\x00")

for v in [b"", b"ab", bytearray(b"a"), "a", 97]:
    check(f"c rejects {v!r}", isV(exc(target.pack, "<c", v)))

check("s bytearray ok", target.pack("<3s", bytearray(b"ab")) == b"ab\x00")
check("s truncates", target.pack("<2s", b"abc") == b"ab")
check("s pads", target.pack("<2s", b"a") == b"a\x00")
check("s rejects str", isV(exc(target.pack, "<2s", "ab")))
check("p bytearray ok", target.pack("<5p", bytearray(b"ab")) == b"\x02ab\x00\x00")
check("p truncates", target.pack("<2p", b"abc") == b"\x01a")
check("p pads", target.pack("<6p", b"a") == b"\x01a\x00\x00\x00\x00")
check("p length byte max 255", target.pack("<300p", b"a" * 300) == b"\xff" + b"a" * 299)
check("p count 0 invalid", isV(exc(target.pack, "<0p", b"")))

ranges = {
    "b": (-128, 127), "B": (0, 255), "h": (-32768, 32767), "H": (0, 65535),
    "i": (-2147483648, 2147483647), "I": (0, 4294967295),
    "l": (-2147483648, 2147483647), "L": (0, 4294967295),
    "q": (-9223372036854775808, 9223372036854775807),
    "Q": (0, 18446744073709551615),
}
for ch, (lo, hi) in ranges.items():
    ok, err = True, None
    for v in (lo, hi):
        e = exc(target.pack, "<" + ch, v)
        if e is not None:
            ok, err = False, f"{v} should pack, got {e!r}"
    if ok:
        for v in (lo - 1, hi + 1):
            e = exc(target.pack, "<" + ch, v)
            if not isV(e):
                ok, err = False, f"{v} should raise ValueError, got {e!r}"
    check(f"range {ch}", ok, None, err)

# unpack: bytes and bytearray, wrong type/length
compare_unpack("<B", b"A")
compare_unpack("<2c", b"ab")
compare_unpack("<3s", b"abc")
compare_unpack("<0s", b"")
compare_unpack("<5p", b"\x02ab\x00\x00")
compare_unpack("<?", b"\x02")
compare_unpack("<?", b"\x00")
check("unpack bytearray", target.unpack("<B", bytearray(b"\x01")) == (1,))
for data in [b"", b"\x01\x01", [1], 1, "a"]:
    check(f"unpack bad data {data!r}", isV(exc(target.unpack, "<B", data)), "ValueError",
          repr(exc(target.unpack, "<B", data)))

# Random oracle against struct on safe finite values
rng = random.Random(1234)
ok, err = True, None
for i in range(120):
    prefix = rng.choice("<>!=")
    items = []
    for _ in range(rng.randrange(0, 4)):
        ch = rng.choice("x c b B ? h H i I l L q Q e f d s p".split())
        if ch == "p": n = rng.randrange(1, 6)
        elif ch == "s": n = rng.randrange(0, 5)
        elif ch == "x": n = rng.randrange(0, 4)
        elif ch == "c": n = rng.randrange(0, 4)
        else: n = rng.randrange(0, 3)
        items.append((n, ch))
    fmt = prefix + "".join((str(n) if n != 1 or ch in "sp" else "") + ch for n, ch in items)
    vals = []
    for n, ch in items:
        if ch == "x":
            continue
        if ch == "c":
            vals.extend(bytes([rng.randrange(256)]) for _ in range(n))
        elif ch in "sp":
            vals.append(bytes(rng.randrange(256) for _ in range(rng.randrange(0, 6))))
        elif ch == "?":
            vals.extend(rng.random() < 0.5 for _ in range(n))
        elif ch in ranges:
            lo, hi = ranges[ch]
            vals.extend(rng.randint(lo, hi) for _ in range(n))
        else:
            hi = 65500.0 if ch == "e" else 1e38 if ch == "f" else 1e300
            vals.extend(rng.uniform(-hi, hi) for _ in range(n))
    try:
        exp = S.pack(fmt, *vals)
        got = target.pack(fmt, *vals)
        if got != exp or target.unpack(fmt, got) != S.unpack(fmt, exp):
            ok, err = False, f"{fmt!r} {vals!r}"
            break
    except Exception as e:
        ok, err = False, repr(e)
        break
check("random struct oracle", ok, None, err)

# CLI success cases
cli_success = [
    (["<B", "65"], "41"),
    (["<2B", "1", "2"], "0102"),
    (["<b", "-1"], "ff"),
    (["<f", "1.5"], "0000c03f"),
    (["<f", "inf"], "0000807f"),
    (["<f", "nan"], "0000c07f"),
    (["<e", "1.0"], "003c"),
]
for args, exp in cli_success:
    r = run_script(*args)
    check(f"CLI {args}", r.returncode == 0 and r.stdout == exp + "\n",
          exp + "\n", (r.returncode, r.stdout))

cli_errors = [
    (["B", "1"], "FAIL: ValueError:"),
    (["<e", "1e30"], "FAIL: OverflowError:"),
    (["<2B", "1"], "FAIL: ValueError:"),
    (["<B", "abc"], "FAIL: ValueError:"),
    (["<B", "256"], "FAIL: ValueError:"),
]
for args, prefix in cli_errors:
    r = run_script(*args)
    out_lines = r.stdout.strip().splitlines()
    check(f"CLI error {args}",
          r.returncode == 2 and len(out_lines) == 1 and out_lines[0].startswith(prefix),
          prefix, (r.returncode, r.stdout))

sys.exit(1 if fails else 0)

# --- stand-in check (added by the pipeline) ---
# These results came out exactly the same against two stand-ins for the script that implement nothing and answer differently,
# so they don't depend on the script's answer (the test's input generator or reference may be wrong):
# (the test itself crashed: File "/work/acceptance_test.py", line 69, in <module> | struct.error: bad char in struct format)

# --- stand-in check (added by the pipeline) ---
# These results came out exactly the same against two stand-ins for the script that implement nothing and answer differently,
# so they don't depend on the script's answer (the test's input generator or reference may be wrong):
# FAIL: __index__ out of range expected None, got None
# FAIL: float rejected for int expected None, got None
# FAIL: c rejects b'' expected None, got None
# FAIL: c rejects b'ab' expected None, got None
# FAIL: c rejects bytearray(b'a') expected None, got None
# FAIL: c rejects 'a' expected None, got None
# FAIL: c rejects 97 expected None, got None
# FAIL: s rejects str expected None, got None
# FAIL: p count 0 invalid expected None, got None
# FAIL: range b expected None, got '128 should raise ValueError, got None'
# FAIL: range B expected None, got '256 should raise ValueError, got None'
# FAIL: range h expected None, got '32768 should raise ValueError, got None'
