# --- added by the pipeline: load the script under test without running its main block ---
import importlib.util as _ilu
import subprocess as _sp
import sys as _sys

_spec = _ilu.spec_from_file_location("target_module", "/work/pyexpr_max_v2.py")
target = _ilu.module_from_spec(_spec)
_sys.modules["target_module"] = target
_sys.modules["target"] = target          # so `import target` works too
_spec.loader.exec_module(target)


def run_script(*args, input=None, timeout=15):
    """Run the script as a separate process. Returns subprocess.CompletedProcess (text mode)."""
    return _sp.run([_sys.executable, "/work/pyexpr_max_v2.py", *map(str, args)], input=input,
                   capture_output=True, text=True, timeout=timeout)

# --- independent acceptance test ---
import sys, random, subprocess

failed = False

def check(name, cond, extra=""):
    global failed
    if cond:
        print(f"PASS: {name}")
    else:
        failed = True
        print(f"FAIL: {name} {extra}")

def safe_run(args, timeout=15):
    try:
        return run_script(*args, timeout=timeout)
    except Exception as e:
        p = type("P", (), {})()
        p.returncode = -1
        p.stdout = ""
        p.stderr = str(e)
        return p

def val(expr, expected, name=None):
    name = name or expr
    try:
        res = target.evaluate(expr)
    except Exception as e:
        check(name, False, f"raised {type(e).__name__}: {e}")
        return
    if type(res) is not type(expected):
        check(name, False, f"expected type {type(expected).__name__}, got {type(res).__name__}")
        return
    if res != expected:
        check(name, False, f"expected {expected!r}, got {res!r}")
        return
    check(name, True)

def err(expr, exc, via_cli=False, timeout=10, name=None):
    name = name or expr
    if via_cli:
        proc = safe_run([expr], timeout=timeout)
        if proc.returncode != 1:
            check(name, False, f"expected exit 1, got {proc.returncode}")
        elif proc.stdout.strip() != exc.__name__:
            check(name, False, f"expected stdout {exc.__name__!r}, got {proc.stdout.strip()!r}")
        else:
            check(name, True)
    else:
        try:
            target.evaluate(expr)
        except exc:
            check(name, True)
        except Exception as e:
            check(name, False, f"expected {exc.__name__}, got {type(e).__name__}: {e}")
        else:
            check(name, False, "expected error, got no error")

# 1. CLI --test
proc = safe_run(["--test"], timeout=30)
check("--test exit 0", proc.returncode == 0, f"rc={proc.returncode} out={proc.stdout[:200]!r}")
lines = proc.stdout.splitlines()
for cat in ["precedence", "chaining", "short-circuit", "types", "errors", "big"]:
    check(f"--test has PASS {cat}", f"PASS {cat}" in lines)

# 2. CLI basic
proc = safe_run(["1 + 2"], timeout=10)
check("cli 1+2", proc.returncode == 0 and proc.stdout.strip() == "3", f"rc={proc.returncode} out={proc.stdout!r}")
proc = safe_run(["True"], timeout=10)
check("cli True", proc.returncode == 0 and proc.stdout.strip() == "True", f"rc={proc.returncode} out={proc.stdout!r}")
proc = safe_run(["1//0"], timeout=10)
check("cli 1//0", proc.returncode == 1 and proc.stdout.strip() == "ZeroDivisionError", f"rc={proc.returncode} out={proc.stdout!r}")
proc = safe_run(["bad"], timeout=10)
check("cli bad", proc.returncode == 1 and proc.stdout.strip() == "ValueError", f"rc={proc.returncode} out={proc.stdout!r}")

# 3. Known values
val_cases = [
    ("1 + 2 * 3", 7), ("2 ** 3 ** 2", 512), ("-2 ** 2", -4), ("~2 ** 2", -5),
    ("2 ** +3", 8), ("1 + 2 << 3", 24), ("1 << 2 + 3", 32), ("1 | 2 << 3", 17),
    ("1 << 2 | 3", 7), ("1 ^ 2 & 3", 3), ("not 0 == 1", True), ("not 0 or 1", True),
    ("1 < 2 and 3", 3), ("0 or 1 < 2", True), ("1 < 2 < 3", True), ("1 < 2 < 2", False),
    ("1 == 2 == 2", False), ("1 < 0 < 1//0", False), ("1 < 2 == 2", True),
    ("1 < 2 > 1", True), ("1 < 2 > 2", False), ("0 and 1//0", 0), ("1 or 1//0", 1),
    ("0 or 5", 5), ("3 and 0", 0), ("True or 5", True), ("True and 5", 5),
    ("False and 5", False), ("False or 5", 5), ("True", True), ("False", False),
    ("1 < 2", True), ("not 0", True), ("True & False", False), ("True | 1", 1),
    ("True ^ 1", 0), ("True + True", 2), ("-True", -1), ("~True", -2),
    ("True << 1", 2), ("True >> 1", 0), ("True // 2", 0), ("True % 2", 1),
    ("False // 2", 0), ("False % 2", 0), ("True & True", True), ("False | False", False),
    ("True ^ False", True), ("-7 // 2", -4), ("-7 % 2", 1), ("7 // -2", -4),
    ("7 % -2", -1), ("-7 // -2", 3), ("-7 % -2", -1), ("0", 0), ("00", 0),
    ("0_0", 0), ("000", 0), ("0_0_0", 0), ("1_000", 1000), ("0x_ff", 255),
    ("0X_FF", 255), ("0o_7", 7), ("0b_1", 1), ("0x1_2", 18), ("0o1_2", 10),
    ("0b1_0", 2), ("1\t+2", 3), (" 1 + 2 ", 3), ("not 0 and 1", 1),
    ("not 1 or 2", 2), ("not not 1", True), ("--5", 5), ("+5", 5),
]
for expr, expected in val_cases:
    val(expr, expected)

# 4. Expected errors
err_cases = [
    ("1//0", ZeroDivisionError), ("1%0", ZeroDivisionError), ("1//0 + 2", ZeroDivisionError),
    ("1 + 1//0", ZeroDivisionError), ("1 << -1", ValueError), ("1 >> -1", ValueError),
    ("1 << (1-2)", ValueError), ("2 ** -1", ValueError), ("0 ** -1", ValueError),
    ("2 ** (1-2)", ValueError), ("-2 ** -1", ValueError), ("2 ** ~2", ValueError),
    ("1//0 + )", ValueError), ("x", ValueError), ("1.5", ValueError), ("1e3", ValueError),
    ("1 / 2", ValueError), ("f()", ValueError), ("a[0]", ValueError), ("1 is 1", ValueError),
    ("1 in 1", ValueError), ("1 if 1 else 2", ValueError), ("1 +", ValueError),
    ("1 + * 2", ValueError), ("()", ValueError), ("(1)", ValueError), ("1))", ValueError),
    ("((1)", ValueError), ("1\n2", ValueError), ("1 # 2", ValueError), ("1\n", ValueError),
    ("1\t2", ValueError), ("1 2", ValueError), ("01", ValueError), ("007", ValueError),
    ("0_7", ValueError), ("0__0", ValueError), ("0_", ValueError), ("_0", ValueError),
    ("1_", ValueError), ("_1", ValueError), ("1__2", ValueError), ("0x", ValueError),
    ("0x_", ValueError), ("0x__f", ValueError), ("0x1_", ValueError), ("0b2", ValueError),
    ("0o8", ValueError), ("0xG", ValueError), ("0x1__2", ValueError), ("0o1_", ValueError),
    ("0b1_", ValueError), ("1\r2", ValueError),
]
for expr, exc in err_cases:
    err(expr, exc)

# 5. CLI errors involving huge expressions
proc = safe_run(["0 and 9**9**9"], timeout=10)
check("cli 0 and 9**9**9", proc.returncode == 0 and proc.stdout.strip() == "0", f"rc={proc.returncode} out={proc.stdout!r}")
proc = safe_run(["1 or 9**9**9"], timeout=10)
check("cli 1 or 9**9**9", proc.returncode == 0 and proc.stdout.strip() == "1", f"rc={proc.returncode} out={proc.stdout!r}")

cli_err_cases = [
    ("9 ** 9 ** 9", ValueError),
    ("1//0 + 9**9**9", ZeroDivisionError),
    ("9**9**9 + 1//0", ValueError),
]
for expr, exc in cli_err_cases:
    err(expr, exc, via_cli=True, timeout=10)

# 6. Size limit edge cases
val("2 ** 999999", 2 ** 999999, "2**999999")
err("2 ** 1000000", ValueError)

# 7. Random reference using eval
rng = random.Random(1234)
leaves = ["0", "1", "2", "3", "True", "False"]
binops = ["+", "-", "*", "//", "%", "&", "|", "^", "<<", ">>", "**", "<", "<=", ">", ">=", "==", "!=", "and", "or"]

def gen(d):
    if d == 0 or rng.random() < 0.25:
        return rng.choice(leaves)
    if rng.random() < 0.1:
        return f"not ({gen(d-1)})"
    op = rng.choice(binops)
    left = gen(d-1)
    right = gen(d-1)
    if op in ("//", "%", "<<", ">>"):
        right = rng.choice(["1", "2", "3"])
    elif op == "**":
        right = rng.choice(["1", "2"])
    return f"({left} {op} {right})"

random_fail = None
for i in range(100):
    expr = gen(3)
    try:
        ref = eval(expr, {}, {})
        res = target.evaluate(expr)
        if type(res) is not type(ref) or res != ref:
            random_fail = f"{expr!r}: expected {ref!r} ({type(ref).__name__}), got {res!r} ({type(res).__name__})"
            break
    except Exception as e:
        random_fail = f"{expr!r}: raised {type(e).__name__}: {e}"
        break
check("random reference", random_fail is None, random_fail or "")

# 8. Big inputs
val("0" * 100000, 0, "100k zeros")
val("1" + "0" * 99999, 10 ** 99999, "100k digit literal")
expr_1m = " " * 100000 + "0" * 100000 + " " * 800000
val(expr_1m, 0, "1M char whitespace")
val("(" * 100000 + "1" + ")" * 100000, 1, "100k parens")
val("not " * 100000 + "True", True, "100k not chain")
val("1" + " ** 1" * 99999, 1, "100k ** chain")

sys.exit(1 if failed else 0)
