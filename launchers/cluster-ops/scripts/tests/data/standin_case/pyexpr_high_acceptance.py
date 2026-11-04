# --- added by the pipeline: load the script under test without running its main block ---
import importlib.util as _ilu
import subprocess as _sp
import sys as _sys

_spec = _ilu.spec_from_file_location("target_module", "/work/pyexpr_high_v2.py")
target = _ilu.module_from_spec(_spec)
_sys.modules["target_module"] = target
_sys.modules["target"] = target          # so `import target` works too
_spec.loader.exec_module(target)


def run_script(*args, input=None, timeout=15):
    """Run the script as a separate process. Returns subprocess.CompletedProcess (text mode)."""
    return _sp.run([_sys.executable, "/work/pyexpr_high_v2.py", *map(str, args)], input=input,
                   capture_output=True, text=True, timeout=timeout)

# --- independent acceptance test ---
import sys

failures = []

def check(name, cond, expected="true", got="false"):
    if cond:
        print(f"PASS: {name}")
    else:
        print(f"FAIL: {name} expected {expected}, got {got}")
        failures.append(name)

def value(expr, expected, typ=None):
    try:
        got = target.evaluate(expr)
    except Exception as e:
        check(f"value({expr!r})", False, repr(expected), f"{type(e).__name__}: {e}")
        return
    ok = got == expected
    if typ is not None:
        ok = ok and type(got) is typ
    check(f"value({expr!r})", ok, repr(expected), repr(got))

def value_error(expr):
    try:
        got = target.evaluate(expr)
    except ValueError:
        check(f"value_error({expr!r})", True)
    except Exception as e:
        check(f"value_error({expr!r})", False, "ValueError", f"{type(e).__name__}: {e}")
    else:
        check(f"value_error({expr!r})", False, "ValueError", repr(got))

def zero_error(expr):
    try:
        got = target.evaluate(expr)
    except ZeroDivisionError:
        check(f"zero_error({expr!r})", True)
    except Exception as e:
        check(f"zero_error({expr!r})", False, "ZeroDivisionError", f"{type(e).__name__}: {e}")
    else:
        check(f"zero_error({expr!r})", False, "ZeroDivisionError", repr(got))

# CLI acceptance checks
p = run_script("--test", timeout=15)
lines = p.stdout.strip().splitlines()
check("cli --test exit 0", p.returncode == 0, 0, p.returncode)
check("cli --test final PASS", bool(lines) and "PASS" in lines[-1], "PASS", lines[-1] if lines else "no output")

p = run_script("1 < x < 3", timeout=15)
check("cli name ValueError exit 1", p.returncode == 1 and any(l.startswith("ValueError") for l in p.stdout.splitlines()), "ValueError exit 1", f"rc={p.returncode} out={p.stdout!r}")

p = run_script("1//0 + )", timeout=15)
check("cli syntax before zero", p.returncode == 1 and any(l.startswith("ValueError") for l in p.stdout.splitlines()) and not any(l.startswith("ZeroDivisionError") for l in p.stdout.splitlines()), "ValueError not ZeroDivisionError", f"rc={p.returncode} out={p.stdout!r}")

p = run_script("9 ** 9 ** 9", timeout=10)
check("cli huge power ValueError", p.returncode == 1 and any(l.startswith("ValueError") for l in p.stdout.splitlines()), "ValueError", f"rc={p.returncode} out={p.stdout!r}")

p = run_script("1//0", timeout=15)
check("cli zero exit 2", p.returncode == 2 and any(l.startswith("ZeroDivisionError") for l in p.stdout.splitlines()), "ZeroDivisionError exit 2", f"rc={p.returncode} out={p.stdout!r}")

p = run_script("2 + 2", timeout=15)
check("cli simple print", p.returncode == 0 and p.stdout.strip() == "4", "4", p.stdout.strip())

# literals
value("0", 0, int)
value("00", 0, int)
value("0_0", 0, int)
value("1_000", 1000, int)
value("0x_ff", 255, int)
value("0XFF", 255, int)
value("0o7", 7, int)
value("0O7", 7, int)
value("0b1", 1, int)
value("0B1", 1, int)
value_error("007")
value_error("01")
value_error("1_")
value_error("_1")
value_error("1__1")
value_error("0x")
value_error("0b")
value_error("0o")
value_error("0x1_")
value_error("0xG")
value_error("1.5")
value_error("1e3")

# booleans, types, precedence
value("True", True, bool)
value("False", False, bool)
value("True + True", 2, int)
value("True & False", False, bool)
value("True | False", True, bool)
value("True ^ True", False, bool)
value("2 + 3 * 4", 14, int)
value("2 ** 3 ** 2", 512, int)
value("-2 ** 2", -4, int)
value("(-2) ** 2", 4, int)
value("1 << 2 + 3", 32, int)
value("1 & 2 | 3 ^ 4", 7, int)
value("not 1 < 2", False, bool)
value("-7 // 2", -4, int)
value("-7 % 2", 1, int)
value("2 % -3", -2, int)
value("7 // -2", -4, int)

# and/or short-circuit and operand return
value("0 or 5", 5, int)
value("3 and 0", 0, int)
value("0 and 1//0", 0, int)
value("1 or 1//0", 1, int)
value("True or 5", True, bool)
value("5 and 0", 0, int)
zero_error("0 or 1//0")
zero_error("1//0 and 0")

# chaining and short-circuit
value("1 < 2 < 3", True, bool)
value("1 < 3 < 2", False, bool)
value("1 < 1 < 1//0", False, bool)
zero_error("1 < 1//0 < 3")
value("1 <= 2 <= 3", True, bool)
value("1 == 2 == 3", False, bool)
value("1 != 2 != 3", True, bool)

# unsupported/invalid chars
value_error("x")
value_error("'a'")
value_error("1/2")
value_error("f()")
value_error("a[0]")
value_error("1 is 1")
value_error("1 in 1")
value_error("1 if 1 else 2")
value_error("1\n2")
value_error("1 # 2")
value_error("1 2")

# spaces/tabs
value(" 1 + 2 ", 3, int)
value("1\t+\t2", 3, int)

# negative exponent/shift
value_error("2 ** -3")
value_error("2 ** (1 - 3)")
value_error("1 << -1")
value_error("1 >> -1")
value_error("1 << (0 - 1)")

# size limits (safe ones)
value_error("2 ** 1000001")
value_error("1 << 1000000")
value("1 << 999999", 1 << 999999, int)

# big inputs
big_flat = "1+" * 499999 + "1"
try:
    r = target.evaluate(big_flat)
    check("big flat 1M chars", r == 500000 and type(r) is int, 500000, repr(r))
except Exception as e:
    check("big flat 1M chars", False, 500000, f"{type(e).__name__}: {e}")

big_digits = "1" * 100000
try:
    r = target.evaluate(big_digits)
    check("big 100k-digit literal", type(r) is int and r.bit_length() > 300000, ">300k bits", f"bits={getattr(r, 'bit_length', lambda: -1)()}")
except Exception as e:
    check("big 100k-digit literal", False, "int", f"{type(e).__name__}: {e}")

deep_parens = "(" * 100000 + "1" + ")" * 100000
try:
    r = target.evaluate(deep_parens)
    check("deep parentheses 100k", r == 1 and type(r) is int, 1, repr(r))
except Exception as e:
    check("deep parentheses 100k", False, 1, f"{type(e).__name__}: {e}")

deep_power = "1" + "**1" * 99999
try:
    r = target.evaluate(deep_power)
    check("deep ** chain 100k", r == 1 and type(r) is int, 1, repr(r))
except Exception as e:
    check("deep ** chain 100k", False, 1, f"{type(e).__name__}: {e}")

deep_unary = "-" * 100000 + "1"
try:
    r = target.evaluate(deep_unary)
    check("deep unary minus 100k", r == 1 and type(r) is int, 1, repr(r))
except Exception as e:
    check("deep unary minus 100k", False, 1, f"{type(e).__name__}: {e}")

sys.exit(1 if failures else 0)
