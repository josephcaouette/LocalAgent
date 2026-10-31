# --- added by the pipeline: load the script under test without running its main block ---
import importlib.util as _ilu
import subprocess as _sp
import sys as _sys

_spec = _ilu.spec_from_file_location("target_module", "/work/calc_max.py")
target = _ilu.module_from_spec(_spec)
_sys.modules["target_module"] = target
_sys.modules["target"] = target          # so `import target` works too
_spec.loader.exec_module(target)


def run_script(*args, input=None, timeout=15):
    """Run the script as a separate process. Returns subprocess.CompletedProcess (text mode)."""
    return _sp.run([_sys.executable, "/work/calc_max.py", *map(str, args)], input=input,
                   capture_output=True, text=True, timeout=timeout)

# --- independent acceptance test ---
import sys

failures = []

def check(desc, cond, expected=None, got=None):
    if cond:
        print(f"PASS: {desc}")
    else:
        if expected is None and got is None:
            print(f"FAIL: {desc}")
        else:
            print(f"FAIL: {desc} expected {expected!r}, got {got!r}")
        failures.append(desc)

def ev(expr, expected, desc):
    try:
        got = target.evaluate(expr)
        check(desc, type(got) is int and got == expected, expected, got)
    except Exception as e:
        check(desc, False, expected, f"{type(e).__name__}: {e}")

def err(expr, exc, desc):
    try:
        got = target.evaluate(expr)
        check(desc, False, exc.__name__, f"returned {got!r}")
    except exc:
        check(desc, True)
    except Exception as e:
        check(desc, False, exc.__name__, f"{type(e).__name__}: {e}")

valid_cases = [
    ("0", 0),
    ("1", 1),
    ("007", 7),
    ("000", 0),
    ("01+2", 3),
    ("2+3*4", 14),
    ("(2+3)*4", 20),
    ("10-2-3", 5),
    ("10/2/2", 2),
    ("100/10/2", 5),
    ("100/10*2", 20),
    ("100/10/2*5", 25),
    ("100/10*2/5", 4),
    ("10*2/3", 6),
    ("10/3*2", 6),
    ("10/3/2", 1),
    ("10/2/3", 1),
    ("10-2*3+4*5-6", 9),
    ("(1-2)*(3-4)", 1),
    ("(1+2)*(3+4)", 21),
    ("10/(2/2)", 10),
    ("1/(3/2)", 1),
    ("10/(4/2)", 5),
    ("10/(4/3)", 10),
    ("--3", 3),
    ("---3", -3),
    ("----3", 3),
    ("2*-3", -6),
    ("-(1+2)", -3),
    ("2--3", 5),
    ("2 - -3", 5),
    ("2 - --3", -1),
    ("2 - ---3", 5),
    ("2 * --3", 6),
    ("2 / --3", 0),
    ("2 / ---3", 0),
    ("2 + -3 * 4", -10),
    ("-2+3", 1),
    ("-2*3", -6),
    ("-2/3", 0),
    ("-2/-3", 0),
    ("-2*3/2", -3),
    ("2*-3/2", -3),
    ("2/-3", 0),
    ("2/-2", -1),
    ("2/-2/2", 0),
    ("2/-2*2", -2),
    ("-7/2", -3),
    ("7/-2", -3),
    ("-7/-2", 3),
    ("1/-2", 0),
    ("-1/2", 0),
    ("-1/-2", 0),
    ("7/2", 3),
    ("0/5", 0),
    ("0/-5", 0),
    ("-0/5", 0),
    ("-(1)", -1),
    ("--(1+2)", 3),
    ("(-1)", -1),
    ("(- 1)", -1),
    ("( -1 )", -1),
    (" 1 + 2 ", 3),
    ("1 +  2", 3),
    ("1+ 2", 3),
    ("1 +2", 3),
    ("1  +2", 3),
    ("1 +  2 ", 3),
    ("(1)", 1),
    ("((1))", 1),
    ("(((1)))", 1),
]
for expr, val in valid_cases:
    ev(expr, val, f"evaluate {expr!r}")

big = 5000
ev("9" * big, 10 ** big - 1, "evaluate 5000-digit 9s")
ev("0" * big + "1", 1, "evaluate 5000 leading zeros")
ev("1" + "0" * big, 10 ** big, "evaluate 1 followed by 5000 zeros")
ev("1+" * 9999 + "1", 10000, "evaluate 10000 additions")
ev("(" * 200 + "1" + ")" * 200, 1, "evaluate 200 nested parentheses")

error_cases = [
    "", "   ", "1.", "1.0", ".1", "(1", "1)", "()", "(-)", "( - )",
    "2+", "2*", "2/", "*2", "+2", "+ 2", "2 + +3", "2 * *3", "2 / /3",
    "2 + + 3", "3 4", "3  4", "2(3)", "2 (3)", "(1)2", "(1)(2)", "3(4)",
    "1\t2", "1\n2", "1\r2", "1 +\u00a02", "1+a", "a", "1;2", "1&2",
    "1|2", "1^2", "1%2", "1**2", "1 - - +3",
]
for expr in error_cases:
    err(expr, ValueError, f"ValueError for {expr!r}")

zero_cases = [
    "1/0", "1/-0", "1/(0)", "1/(2/3)", "10/(2/3)", "0/0", "5/(1-1)",
    "5/(-0)", "5/(0+0)", "5/(0*5)", "1/(0-0)", "1/(0/1)", "1/(1-1)",
    "1 / -0", "1 / (2/3)", "10/(0)", "10/( 0)", "10/(0 )",
]
for expr in zero_cases:
    err(expr, ZeroDivisionError, f"ZeroDivisionError for {expr!r}")

proc = run_script("--test")
expected_test_out = "PASS precedence\nPASS unary_minus\nPASS truncation\nPASS errors\n"
check("CLI --test exit code", proc.returncode == 0, 0, proc.returncode)
check("CLI --test stdout exact", proc.stdout == expected_test_out, expected_test_out, proc.stdout)
check("CLI --test stderr empty", proc.stderr == "", "", proc.stderr)

for expr, out in [
    ("1+2", "3\n"),
    ("-3", "-3\n"),
    ("7/2", "3\n"),
    (" 1 + 2 ", "3\n"),
    ("100/10*2", "20\n"),
]:
    proc = run_script(expr)
    check(f"CLI {expr!r}", proc.returncode == 0 and proc.stdout == out and proc.stderr == "",
          (0, out, ""), (proc.returncode, proc.stdout, proc.stderr))

for expr, prefix in [
    ("1/0", "ZeroDivisionError:"),
    ("", "ValueError:"),
    ("1.", "ValueError:"),
    ("2+", "ValueError:"),
    ("3 4", "ValueError:"),
]:
    proc = run_script(expr)
    check(f"CLI error {expr!r}", proc.returncode == 1 and proc.stderr.startswith(prefix),
          (1, prefix), (proc.returncode, proc.stderr))

proc = run_script()
check("CLI no args", proc.returncode == 2 and proc.stderr != "", (2, "nonempty stderr"),
      (proc.returncode, proc.stderr))
proc = run_script("1", "2")
check("CLI too many args", proc.returncode == 2 and proc.stderr != "", (2, "nonempty stderr"),
      (proc.returncode, proc.stderr))
proc = run_script("--test", "1")
check("CLI --test plus arg", proc.returncode == 2 and proc.stderr != "", (2, "nonempty stderr"),
      (proc.returncode, proc.stderr))

sys.exit(1 if failures else 0)
