# --- added by the pipeline: load the script under test without running its main block ---
import importlib.util as _ilu
import subprocess as _sp
import sys as _sys

_spec = _ilu.spec_from_file_location("target_module", "/work/struct_high_v2.py")
target = _ilu.module_from_spec(_spec)
_sys.modules["target_module"] = target
_sys.modules["target"] = target          # so `import target` works too
_spec.loader.exec_module(target)


def run_script(*args, input=None, timeout=15):
    """Run the script as a separate process. Returns subprocess.CompletedProcess (text mode)."""
    return _sp.run([_sys.executable, "/work/struct_high_v2.py", *map(str, args)], input=input,
                   capture_output=True, text=True, timeout=timeout)

# --- independent acceptance test ---
import sys, math, struct as _s

failed = []

def check(name, cond, expected=None, got=None):
    if cond:
        print(f"PASS: {name}")
    else:
        print(f"FAIL: {name} expected {expected!r}, got {got!r}")
        failed.append(name)

def eq(a, b):
    if isinstance(a, float) and isinstance(b, float):
        return math.isnan(a) and math.isnan(b) or a == b
    return a == b

def seq_eq(a, b):
    if len(a) != len(b):
        return False
    return all(eq(x, y) for x, y in zip(a, b))

def try_pack(fmt, *vals):
    try:
        return target.pack(fmt, *vals)
    except (ValueError, OverflowError) as e:
        return type(e)

def try_spack(fmt, *vals):
    try:
        return _s.pack(fmt, *vals)
    except (ValueError, OverflowError) as e:
        return type(e)

def try_unpack(fmt, data):
    try:
        return target.unpack(fmt, data)
    except (ValueError, OverflowError) as e:
        return type(e)

def try_sunpack(fmt, data):
    try:
        return _s.unpack(fmt, data)
    except (ValueError, OverflowError) as e:
        return type(e)

def try_calcsize(fmt):
    try:
        return target.calcsize(fmt)
    except (ValueError, OverflowError) as e:
        return type(e)

def try_scalcsize(fmt):
    try:
        return _s.calcsize(fmt)
    except (ValueError, OverflowError) as e:
        return type(e)

# --- Acceptance checks ---
r = run_script("--test")
check("--test prints OK and exits 0", r.returncode == 0 and r.stdout.strip() == "OK", "OK", r.stdout.strip())

r = run_script("<", "1i", "42")
check("CLI < 1i 42", r.returncode == 0 and r.stdout.strip() == "2a000000", "2a000000", r.stdout.strip())

r = run_script(">", "1i", "42")
check("CLI > 1i 42", r.returncode == 0 and r.stdout.strip() == "0000002a", "0000002a", r.stdout.strip())

r = run_script("@", "1i", "42")
check("CLI @ 1i 42 exits 1 with ValueError", r.returncode == 1 and "ValueError" in r.stderr, "ValueError in stderr", r.stderr.strip())

# --- calcsize ---
for p in ['<', '>', '!', '=']:
    for f in ['b','B','h','H','i','I','l','L','q','Q','?','c','e','f','d','x']:
        check(f"calcsize {p}{f}", try_calcsize(p+f) == try_scalcsize(p+f), try_scalcsize(p+f), try_calcsize(p+f))
    check(f"calcsize {p}s2", try_calcsize(p+"s2") == try_scalcsize(p+"s2"), try_scalcsize(p+"s2"), try_calcsize(p+"s2"))
    check(f"calcsize {p}p3", try_calcsize(p+"p3") == try_scalcsize(p+"p3"), try_scalcsize(p+"p3"), try_calcsize(p+"p3"))
    check(f"calcsize {p}2b", try_calcsize(p+"2b") == try_scalcsize(p+"2b"), try_scalcsize(p+"2b"), try_calcsize(p+"2b"))

# No byte order or @ raises ValueError
for f in ['i', '@i', '  i']:
    check(f"calcsize {f!r} raises ValueError", try_calcsize(f) is ValueError, "ValueError", try_calcsize(f))

# --- pack/unpack roundtrip and byte comparison with struct ---
int_vals = {
    'b': [0, 1, -1, 127, -128, 100],
    'B': [0, 1, 255, 100],
    'h': [0, 1, -1, 32767, -32768],
    'H': [0, 1, 65535, 1000],
    'i': [0, 1, -1, 2147483647, -2147483648],
    'I': [0, 1, 2**32-1, 100000],
    'l': [0, 1, -1, 2147483647, -2147483648],
    'L': [0, 1, 2**32-1, 100000],
    'q': [0, 1, -1, 2**63-1, -2**63],
    'Q': [0, 1, 2**64-1, 100000],
}
float_vals = [0.0, 1.0, -1.0, 1.5, -1.5, 0.5, 2.0, 65504.0, 1e-20, 1e30, math.inf, -math.inf]
float_vals_f = [0.0, 1.0, -1.0, 1.5, 1e38, 1e-30, math.inf, -math.inf]
float_vals_d = [0.0, 1.0, -1.0, 1.5, 1e308, 1e-300, math.inf, -math.inf]

for p in ['<', '>', '!', '=']:
    for f, vals in int_vals.items():
        for v in vals:
            fmt = p + f
            exp = try_spack(fmt, v)
            got = try_pack(fmt, v)
            check(f"pack {fmt} {v}", got == exp, exp, got)
            if isinstance(exp, bytes):
                check(f"unpack {fmt} {v}", seq_eq(try_unpack(fmt, exp), try_sunpack(fmt, exp)), try_sunpack(fmt, exp), try_unpack(fmt, exp))
    # ? bool
    for v in [True, False]:
        fmt = p + '?'
        check(f"pack {fmt} {v}", try_pack(fmt, v) == try_spack(fmt, v), try_spack(fmt, v), try_pack(fmt, v))
    # c
    check(f"pack {p}c b'A'", try_pack(p+'c', b'A') == try_spack(p+'c', b'A'), try_spack(p+'c', b'A'), try_pack(p+'c', b'A'))
    check(f"unpack {p}c", seq_eq(try_unpack(p+'c', b'A'), try_sunpack(p+'c', b'A')), try_sunpack(p+'c', b'A'), try_unpack(p+'c', b'A'))
    # x
    check(f"pack {p}x", try_pack(p+'x') == try_spack(p+'x'), try_spack(p+'x'), try_pack(p+'x'))
    # e
    for v in float_vals:
        fmt = p + 'e'
        exp = try_spack(fmt, v)
        got = try_pack(fmt, v)
        check(f"pack {fmt} {v}", got == exp, exp, got)
        if isinstance(exp, bytes) and not (isinstance(v, float) and math.isnan(v)):
            check(f"unpack {fmt} {v}", seq_eq(try_unpack(fmt, exp), try_sunpack(fmt, exp)), try_sunpack(fmt, exp), try_unpack(fmt, exp))
    # f
    for v in float_vals_f:
        fmt = p + 'f'
        exp = try_spack(fmt, v)
        got = try_pack(fmt, v)
        check(f"pack {fmt} {v}", got == exp, exp, got)
        if isinstance(exp, bytes) and not (isinstance(v, float) and math.isnan(v)):
            check(f"unpack {fmt} {v}", seq_eq(try_unpack(fmt, exp), try_sunpack(fmt, exp)), try_sunpack(fmt, exp), try_unpack(fmt, exp))
    # d
    for v in float_vals_d:
        fmt = p + 'd'
        exp = try_spack(fmt, v)
        got = try_pack(fmt, v)
        check(f"pack {fmt} {v}", got == exp, exp, got)
        if isinstance(exp, bytes) and not (isinstance(v, float) and math.isnan(v)):
            check(f"unpack {fmt} {v}", seq_eq(try_unpack(fmt, exp), try_sunpack(fmt, exp)), try_sunpack(fmt, exp), try_unpack(fmt, exp))
    # s2
    for v in [b'ab', b'a', b'abc']:
        fmt = p + 's2'
        exp = try_spack(fmt, v)
        got = try_pack(fmt, v)
        check(f"pack {fmt} {v!r}", got == exp, exp, got)
        if isinstance(exp, bytes):
            check(f"unpack {fmt} {v!r}", seq_eq(try_unpack(fmt, exp), try_sunpack(fmt, exp)), try_sunpack(fmt, exp), try_unpack(fmt, exp))
    # p3
    for v in [b'ab', b'a', b'abc', b'abcd']:
        fmt = p + 'p3'
        exp = try_spack(fmt, v)
        got = try_pack(fmt, v)
        check(f"pack {fmt} {v!r}", got == exp, exp, got)
        if isinstance(exp, bytes):
            check(f"unpack {fmt} {v!r}", seq_eq(try_unpack(fmt, exp), try_sunpack(fmt, exp)), try_sunpack(fmt, exp), try_unpack(fmt, exp))
    # 2b
    check(f"pack {p}2b 1,2", try_pack(p+'2b', 1, 2) == try_spack(p+'2b', 1, 2), try_spack(p+'2b', 1, 2), try_pack(p+'2b', 1, 2))

# --- Range limits (out of range) ---
int_ranges = {
    'b': (-128, 127), 'B': (0, 255), 'h': (-32768, 32767), 'H': (0, 65535),
    'i': (-2147483648, 2147483647), 'I': (0, 2**32-1),
    'l': (-2147483648, 2147483647), 'L': (0, 2**32-1),
    'q': (-2**63, 2**63-1), 'Q': (0, 2**64-1),
}
for p in ['<', '>', '!', '=']:
    for f, (lo, hi) in int_ranges.items():
        fmt = p + f
        check(f"pack {fmt} {lo-1} raises", try_pack(fmt, lo-1) is ValueError, "ValueError", try_pack(fmt, lo-1))
        check(f"pack {fmt} {hi+1} raises", try_pack(fmt, hi+1) is ValueError, "ValueError", try_pack(fmt, hi+1))

# --- e/f overflow ---
for p in ['<', '>', '!', '=']:
    check(f"pack {p}e 1e30 raises OverflowError", try_pack(p+'e', 1e30) is OverflowError, "OverflowError", try_pack(p+'e', 1e30))
    check(f"pack {p}f 1e39 raises OverflowError", try_pack(p+'f', 1e39) is OverflowError, "OverflowError", try_pack(p+'f', 1e39))

# --- e NaN known value ---
for p in ['<', '>', '!', '=']:
    check(f"pack {p}e nan == 0x7e00", try_pack(p+'e', math.nan) == _s.pack(p+'e', math.nan), _s.pack(p+'e', math.nan), try_pack(p+'e', math.nan))
    neg_nan = -math.nan
    check(f"pack {p}e -nan sign", try_pack(p+'e', neg_nan) == _s.pack(p+'e', neg_nan), _s.pack(p+'e', neg_nan), try_pack(p+'e', neg_nan))

# --- Custom __index__ ---
class Idx:
    def __init__(self, v): self.v = v
    def __index__(self): return self.v

check("pack <i Idx(42)", try_pack('<i', Idx(42)) == try_pack('<i', 42), try_pack('<i', 42), try_pack('<i', Idx(42)))
check("pack <b Idx(5)", try_pack('<b', Idx(5)) == try_pack('<b', 5), try_pack('<b', 5), try_pack('<b', Idx(5)))

# --- ? custom truth ---
class T:
    def __bool__(self): return True
class F:
    def __bool__(self): return False

check("pack <? T()", try_pack('<?', T()) == b'\x01', b'\x01', try_pack('<?', T()))
check("pack <? F()", try_pack('<?', F()) == b'\x00', b'\x00', try_pack('<?', F()))
check("unpack <? b'\\x01'", try_unpack('<?', b'\x01') == (True,), (True,), try_unpack('<?', b'\x01'))
check("unpack <? b'\\x02'", try_unpack('<?', b'\x02') == (True,), (True,), try_unpack('<?', b'\x02'))
check("unpack <? b'\\x00'", try_unpack('<?', b'\x00') == (False,), (False,), try_unpack('<?', b'\x00'))

# --- Float custom __float__ ---
class Fl:
    def __init__(self, v): self.v = v
    def __float__(self): return self.v

check("pack <f Fl(1.5)", try_pack('<f', Fl(1.5)) == try_pack('<f', 1.5), try_pack('<f', 1.5), try_pack('<f', Fl(1.5)))
check("pack <e Fl(1.5)", try_pack('<e', Fl(1.5)) == try_pack('<e', 1.5), try_pack('<e', 1.5), try_pack('<e', Fl(1.5)))
check("pack <d Fl(1.5)", try_pack('<d', Fl(1.5)) == try_pack('<d', 1.5), try_pack('<d', 1.5), try_pack('<d', Fl(1.5)))

# --- Float from int ---
check("pack <f 2 (int)", try_pack('<f', 2) == try_pack('<f', 2.0), try_pack('<f', 2.0), try_pack('<f', 2))
check("pack <e 1 (int)", try_pack('<e', 1) == try_pack('<e', 1.0), try_pack('<e', 1.0), try_pack('<e', 1))

# --- unpack wrong size ---
check("unpack <i wrong size raises", try_unpack('<i', b'\x01\x02\x03') is ValueError, "ValueError", try_unpack('<i', b'\x01\x02\x03'))
check("unpack <i wrong size raises (long)", try_unpack('<i', b'\x01\x02\x03\x04\x05') is ValueError, "ValueError", try_unpack('<i', b'\x01\x02\x03\x04\x05'))

# --- unpack wrong type ---
check("unpack <i str raises", try_unpack('<i', 'abcd') is ValueError, "ValueError", try_unpack('<i', 'abcd'))

# --- s/p return bytes ---
r = try_unpack('<s2', b'ab')
check("unpack <s2 returns bytes", isinstance(r[0], bytes), "bytes", type(r[0]))
r = try_unpack('<p3', b'\x02ab')
check("unpack <p3 returns bytes", isinstance(r[0], bytes), "bytes", type(r[0]))

# --- c returns bytes ---
r = try_unpack('<c', b'A')
check("unpack <c returns bytes", isinstance(r[0], bytes), "bytes", type(r[0]))

# --- s/p accept bytearray ---
check("pack <s2 bytearray", try_pack('<s2', bytearray(b'ab')) == try_pack('<s2', b'ab'), try_pack('<s2', b'ab'), try_pack('<s2', bytearray(b'ab')))
check("pack <p3 bytearray", try_pack('<p3', bytearray(b'ab')) == try_pack('<p3', b'ab'), try_pack('<p3', b'ab'), try_pack('<p3', bytearray(b'ab')))

# --- unpack accepts bytearray ---
check("unpack <i bytearray", try_unpack('<i', bytearray(b'\x01\x02\x03\x04')) == try_unpack('<i', b'\x01\x02\x03\x04'), try_unpack('<i', b'\x01\x02\x03\x04'), try_unpack('<i', bytearray(b'\x01\x02\x03\x04')))

# --- CLI with float ---
r = run_script("<", "f", "1.5")
exp_hex = _s.pack('<f', 1.5).hex()
check(f"CLI < f 1.5", r.returncode == 0 and r.stdout.strip() == exp_hex, exp_hex, r.stdout.strip())

# --- CLI with multiple values ---
r = run_script("<", "2b", "1", "2")
check("CLI < 2b 1 2", r.returncode == 0 and r.stdout.strip() == "0102", "0102", r.stdout.strip())

# --- CLI error: out of range ---
r = run_script("<", "b", "256")
check("CLI < b 256 exits 1", r.returncode == 1, 1, r.returncode)

# --- Whitespace in format ---
check("pack < 1i 42 (whitespace)", try_pack('< 1i', 42) == try_pack('<1i', 42), try_pack('<1i', 42), try_pack('< 1i', 42))
check("calcsize < 1i", try_calcsize('< 1i') == try_scalcsize('< 1i'), try_scalcsize('< 1i'), try_calcsize('< 1i'))

# --- Whitespace between count and char should raise ---
check("pack <2 b raises", try_pack('<2 b', 1, 2) is ValueError, "ValueError", try_pack('<2 b', 1, 2))

# --- 0 repeat count ---
check("pack <0i", try_pack('<0i') == b'', b'', try_pack('<0i'))
check("calcsize <0i", try_calcsize('<0i') == 0, 0, try_calcsize('<0i'))

# --- Final ---
if failed:
    print(f"\n{len(failed)} check(s) failed")
    sys.exit(1)
else:
    print("\nAll checks passed")
    sys.exit(0)
