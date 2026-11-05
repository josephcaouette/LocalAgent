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
import sys

P = target.pack
U = target.unpack
C = target.calcsize

fails = []

def report(name, cond, detail=""):
    if cond:
        print("PASS: " + name)
    else:
        print("FAIL: " + name + " " + detail)
        fails.append(name)

def eq(name, fn, expected):
    try:
        got = fn()
    except Exception as e:
        report(name, False, f"expected {expected!r}, got {type(e).__name__}: {e}")
        return
    report(name, got == expected, f"expected {expected!r}, got {got!r}")

def raises(name, fn, exc):
    try:
        got = fn()
    except exc:
        report(name, True)
    except Exception as e:
        report(name, False, f"expected {exc.__name__}, got {type(e).__name__}: {e}")
    else:
        report(name, False, f"expected {exc.__name__}, got value {got!r}")

# --- calcsize / format validation ---
eq("calcsize <B", lambda: C('<B'), 1)
eq("calcsize ws", lambda: C('  <2B  '), 2)
eq("calcsize 1p", lambda: C('<1p'), 1)
eq("calcsize 5p", lambda: C('<5p'), 5)
eq("calcsize 0s", lambda: C('<0s'), 0)
eq("calcsize 3s", lambda: C('<3s'), 3)
eq("calcsize 2c", lambda: C('<2c'), 2)
eq("calcsize e", lambda: C('<e'), 2)
eq("calcsize q", lambda: C('<q'), 8)
eq("calcsize big", lambda: C('<1000000B'), 1000000)
eq("calcsize <s", lambda: C('<s'), 1)
raises("calcsize no prefix", lambda: C('B'), ValueError)
raises("calcsize @", lambda: C('@B'), ValueError)
raises("calcsize ws count", lambda: C('<2 B'), ValueError)
raises("calcsize unknown", lambda: C('<z'), ValueError)
raises("calcsize 0p", lambda: C('<0p'), ValueError)
raises("calcsize neg count", lambda: C('<-1B'), ValueError)
raises("calcsize float count", lambda: C('<1.5B'), ValueError)

# --- endianness ---
eq("LE H", lambda: P('<H', 0x1234), b'\x34\x12')
eq("BE H", lambda: P('>H', 0x1234), b'\x12\x34')
eq("! H", lambda: P('!H', 0x1234), b'\x12\x34')
eq("= H", lambda: P('=H', 0x1234), b'\x34\x12' if sys.byteorder == 'little' else b'\x12\x34')
eq("LE Q", lambda: P('<Q', 0x0102030405060708), b'\x08\x07\x06\x05\x04\x03\x02\x01')
eq("BE Q", lambda: P('>Q', 0x0102030405060708), b'\x01\x02\x03\x04\x05\x06\x07\x08')
eq("LE f", lambda: P('<f', 1.0), b'\x00\x00\x80\x3f')
eq("BE f", lambda: P('>f', 1.0), b'\x3f\x80\x00\x00')
eq("LE e", lambda: P('<e', 1.0), b'\x00\x3c')
eq("BE e", lambda: P('>e', 1.0), b'\x3c\x00')
eq("LE d", lambda: P('<d', 1.0), b'\x00\x00\x00\x00\x00\x00\xf0\x3f')

# --- integers ---
eq("b min", lambda: P('<b', -128), b'\x80')
eq("b max", lambda: P('<b', 127), b'\x7f')
raises("b over", lambda: P('<b', 128), ValueError)
raises("b under", lambda: P('<b', -129), ValueError)
eq("B max", lambda: P('<B', 255), b'\xff')
raises("B over", lambda: P('<B', 256), ValueError)
raises("B neg", lambda: P('<B', -1), ValueError)
eq("H max", lambda: P('<H', 65535), b'\xff\xff')
raises("H over", lambda: P('<H', 65536), ValueError)
eq("i min", lambda: P('<i', -2**31), b'\x00\x00\x00\x80')
raises("i over", lambda: P('<i', 2**31), ValueError)
eq("I max", lambda: P('<I', 2**32 - 1), b'\xff\xff\xff\xff')
raises("I over", lambda: P('<I', 2**32), ValueError)
eq("L max", lambda: P('<L', 2**32 - 1), b'\xff\xff\xff\xff')
eq("q min", lambda: P('<q', -2**63), b'\x80' + b'\x00' * 7)
raises("q over", lambda: P('<q', 2**63), ValueError)
eq("Q max", lambda: P('<Q', 2**64 - 1), b'\xff' * 8)
raises("Q over", lambda: P('<Q', 2**64), ValueError)
eq("bool as int", lambda: P('<i', True), b'\x01\x00\x00\x00')
raises("float as int", lambda: P('<B', 1.5), ValueError)

class Idx:
    def __index__(self):
        return 7
eq("__index__", lambda: P('<B', Idx()), b'\x07')
eq("unpack b", lambda: U('<b', b'\x80'), (-128,))
eq("unpack i neg", lambda: U('<i', b'\xff\xff\xff\xff'), (-1,))
eq("unpack Q max", lambda: U('<Q', b'\xff' * 8), (2**64 - 1,))

# --- ? ---
eq("? true", lambda: P('<?', True), b'\x01')
eq("? zero", lambda: P('<?', 0), b'\x00')
eq("? truthy obj", lambda: P('<?', 'x'), b'\x01')
eq("unpack ? nonzero", lambda: U('<?', b'\x02'), (True,))
eq("unpack ? zero", lambda: U('<?', b'\x00'), (False,))

# --- c ---
eq("c basic", lambda: P('<c', b'a'), b'a')
raises("c len2", lambda: P('<c', b'ab'), ValueError)
raises("c int", lambda: P('<c', 97), ValueError)
raises("c bytearray", lambda: P('<c', bytearray(b'a')), ValueError)
eq("2c", lambda: P('<2c', b'a', b'b'), b'ab')
eq("unpack 2c", lambda: U('<2c', b'ab'), (b'a', b'b'))
eq("0c", lambda: P('<0c'), b'')

# --- s ---
eq("3s pad", lambda: P('<3s', b'ab'), b'ab\x00')
eq("3s cut", lambda: P('<3s', b'abcd'), b'abc')
eq("0s", lambda: P('<0s', b'abc'), b'')
raises("0s noarg", lambda: P('<0s'), ValueError)
eq("3s bytearray", lambda: P('<3s', bytearray(b'ab')), b'ab\x00')
eq("unpack 3s", lambda: U('<3s', b'ab\x00'), (b'ab\x00',))
eq("s default", lambda: P('<s', b'ab'), b'a')

# --- p ---
eq("5p", lambda: P('<5p', b'ab'), b'\x02ab\x00\x00')
eq("1p", lambda: P('<1p', b'abc'), b'\x00')
eq("2p", lambda: P('<2p', b'ab'), b'\x01a')
eq("256p", lambda: P('<256p', b'ab'), b'\x02ab' + b'\x00' * 253)
eq("257p", lambda: P('<257p', b'x' * 300), b'\xff' + b'x' * 256)
eq("unpack 5p", lambda: U('<5p', b'\x02ab\x00\x00'), (b'\x02ab\x00\x00',))
raises("0p", lambda: P('<0p', b''), ValueError)
eq("p default", lambda: P('<p', b'abc'), b'\x00')

# --- x / arg count ---
eq("2x", lambda: P('<2x'), b'\x00\x00')
raises("2x arg", lambda: P('<2x', 1), ValueError)
raises("missing arg", lambda: P('<B'), ValueError)
raises("extra arg", lambda: P('<B', 1, 2), ValueError)
eq("mixed", lambda: P('<BH', 1, 2), b'\x01\x02\x00')
eq("ws items", lambda: P('< 2B ', 1, 2), b'\x01\x02')

# --- floats ---
eq("f int", lambda: P('<f', 1), b'\x00\x00\x80\x3f')
eq("f neg zero", lambda: P('<f', -0.0), b'\x00\x00\x00\x80')
eq("f inf", lambda: P('<f', float('inf')), b'\x00\x00\x80\x7f')
eq("f -inf", lambda: P('<f', float('-inf')), b'\x00\x00\x80\xff')
eq("f nan", lambda: P('<f', float('nan')), b'\x00\x00\xc0\x7f')
eq("f -nan", lambda: P('<f', -float('nan')), b'\x00\x00\xc0\xff')
eq("e nan", lambda: P('<e', float('nan')), b'\x00\x7e')
eq("e -nan", lambda: P('<e', -float('nan')), b'\x00\xfe')
eq("e inf", lambda: P('<e', float('inf')), b'\x00\x7c')
eq("e -inf", lambda: P('<e', float('-inf')), b'\x00\xfc')
eq("e neg zero", lambda: P('<e', -0.0), b'\x00\xfc')
eq("d nan", lambda: P('<d', float('nan')), b'\x00' * 6 + b'\xf0\x7f')
eq("e max", lambda: P('<e', 65504.0), b'\xff\x7b')
eq("e 65519", lambda: P('<e', 65519.0), b'\xff\x7b')
raises("e tie inf", lambda: P('<e', 65520.0), OverflowError)
raises("e 65521", lambda: P('<e', 65521.0), OverflowError)
raises("e 65536", lambda: P('<e', 65536.0), OverflowError)
raises("e 1e30", lambda: P('<e', 1e30), OverflowError)
eq("e sub exact", lambda: P('<e', 5.960464477539063e-08), b'\x01\x00')
eq("e sub tie down", lambda: P('<e', 2.9802322387695312e-08), b'\x00\x00')
eq("e sub tie even", lambda: P('<e', 3 * 2**-25), b'\x02\x00')
eq("f max", lambda: P('<f', 3.4028234663852886e+38), b'\xff\xff\x7f\x7f')
raises("f tie inf", lambda: P('<f', 3.402823564422953e+38), OverflowError)
eq("f tie even", lambda: P('<f', 1 + 2**-24), b'\x00\x00\x80\x3f')
eq("f round up", lambda: P('<f', 1 + 3 * 2**-24), b'\x01\x00\x80\x3f')
raises("f bad str", lambda: P('<f', 'abc'), ValueError)
raises("f big int", lambda: P('<f', 10**400), OverflowError)

class Flt:
    def __float__(self):
        return 1.5
eq("__float__", lambda: P('<f', Flt()), b'\x00\x00\xc0\x3f')

# --- unpack validation ---
eq("unpack B", lambda: U('<B', b'\x01'), (1,))
eq("unpack bytearray", lambda: U('<B', bytearray(b'\x01')), (1,))
raises("unpack str", lambda: U('<B', 'a'), ValueError)
raises("unpack short", lambda: U('<B', b''), ValueError)
raises("unpack long", lambda: U('<B', b'ab'), ValueError)
raises("unpack int", lambda: U('<B', 1), ValueError)
eq("unpack tuple", lambda: isinstance(U('<2B', b'\x01\x02'), tuple), True)

# --- CLI ---
r = run_script('--test')
t = r.stdout
report("--test exit", r.returncode == 0, f"got {r.returncode}")
for s in ("PASS formats", "PASS byte orders", "PASS range limits", "PASS rounding overflow", "PASS errors"):
    report(f"--test has {s}", s in t)
lines = [l for l in t.splitlines() if l.strip()]
report("--test ends OK", bool(lines) and "OK" in lines[-1], f"last={lines[-1] if lines else ''!r}")

r = run_script('<B', '255')
report("cli B 255", r.returncode == 0 and r.stdout.strip() == 'ff' and r.stdout.endswith('\n'), f"rc={r.returncode} out={r.stdout!r}")
r = run_script('<f', '1.5')
report("cli f 1.5", r.returncode == 0 and r.stdout.strip() == '0000c03f', f"rc={r.returncode} out={r.stdout!r}")
r = run_script('<2B', '1', '2')
report("cli 2B", r.returncode == 0 and r.stdout.strip() == '0102', f"rc={r.returncode} out={r.stdout!r}")

def cli_err(args, excname):
    r = run_script(*args)
    ls = r.stdout.splitlines()
    cond = r.returncode == 2 and len(ls) == 1 and ls[0].startswith("FAIL: " + excname)
    report(f"cli err {args}", cond, f"rc={r.returncode} out={r.stdout!r}")

cli_err(('<B', '256'), 'ValueError')
cli_err(('<e', '1e30'), 'OverflowError')
cli_err(('B', '1'), 'ValueError')
cli_err(('<B',), 'ValueError')

sys.exit(1 if fails else 0)

# --- stand-in check (added by the pipeline) ---
# These results came out exactly the same against two stand-ins for the script that implement nothing and answer differently,
# so they don't depend on the script's answer (the test's input generator or reference may be wrong):
# FAIL: unpack tuple expected True, got False
