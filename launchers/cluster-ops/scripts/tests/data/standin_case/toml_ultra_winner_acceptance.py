# --- added by the pipeline: load the script under test without running its main block ---
import importlib.util as _ilu
import subprocess as _sp
import sys as _sys

_spec = _ilu.spec_from_file_location("target_module", "/work/toml_ultra_v2.py")
target = _ilu.module_from_spec(_spec)
_sys.modules["target_module"] = target
_sys.modules["target"] = target          # so `import target` works too
_spec.loader.exec_module(target)


def run_script(*args, input=None, timeout=15):
    """Run the script as a separate process. Returns subprocess.CompletedProcess (text mode)."""
    return _sp.run([_sys.executable, "/work/toml_ultra_v2.py", *map(str, args)], input=input,
                   capture_output=True, text=True, timeout=timeout)

# --- independent acceptance test ---
import sys, random, math, os

failed = False

def check(name, cond, extra=""):
    global failed
    if cond:
        print(f"PASS: {name}")
    else:
        failed = True
        print(f"FAIL: {name} expected {extra}" if extra else f"FAIL: {name}")

def eq(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(eq(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(eq(x, y) for x, y in zip(a, b))
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, float) or isinstance(b, float):
        if isinstance(a, float) and isinstance(b, float):
            return (math.isnan(a) and math.isnan(b)) or a == b
        return False
    if isinstance(a, int) and isinstance(b, int):
        return a == b
    if isinstance(a, str) and isinstance(b, str):
        return a == b
    return False

def ok(doc, expected, name=None):
    try:
        got = target.loads(doc)
    except ValueError as e:
        check(name or "ok", False, f"no error, got {e!r}")
        return
    except Exception as e:
        check(name or "ok", False, f"exception {e!r}")
        return
    check(name or "ok", eq(got, expected), f"{expected!r}, got {got!r}")

def err(doc, name=None):
    try:
        target.loads(doc)
        check(name or "err", False, "expected ValueError")
    except ValueError:
        check(name or "err", True)
    except Exception as e:
        check(name or "err", False, f"wrong exception {e!r}")

# scalars
ok("a=true", {"a": True}, "bool true")
ok("a=false", {"a": False}, "bool false")
ok("a=999999999999999999999999999999999999999999", {"a": 999999999999999999999999999999999999999999}, "big int")
ok("a=0x1_f", {"a": 31}, "hex underscore")
ok("a=1.0_0", {"a": 1.0}, "float underscore")
ok("a=1e999", {"a": math.inf}, "float overflow")
ok("a=-1e999", {"a": -math.inf}, "negative float overflow")
ok(r'a="\u00d7"', {"a": "×"}, "unicode escape")
err('a="abc\\\n  def"', "single line continuation")
ok('a="""abc""""', {"a": "abc\""}, "ml basic one quote")
ok('a="""abc"""""', {"a": "abc\"\""}, "ml basic two quotes")
err('a="""abc""""""', "ml basic three quotes")
err('a="\\uD800"', "surrogate escape")
err("a=1979-05-27", "date value")
err("a=12:34:56", "time value")
err("a=1979-05-27T12:34:56Z", "datetime value")

# keys
ok('""=1', {"": 1}, "empty key")
ok('a.""=1', {"a": {"": 1}}, "dotted empty key")
ok('a . b = 1', {"a": {"b": 1}}, "dotted whitespace")
ok("1979-05-27=1", {"1979-05-27": 1}, "date-like key")
err("a=1\na=2", "duplicate key")
err("a.b=1\na.b=2", "duplicate dotted key")
err("a=1\na.b=2", "dotted through scalar")

# tables
ok("[a.b]\nc=1", {"a": {"b": {"c": 1}}}, "table header")
ok("[a.b]\n[a.b.c]\nd=1", {"a": {"b": {"c": {"d": 1}}}}, "nested header")
err("[a.b]\n[a.b]", "duplicate table header")
err("[a.b]\nc=1\n[a]", "redefine implicit table")
err("a.b=1\n[a]", "redefine dotted table")
ok("[[a]]\n[a.b]\nc=1\n[[a]]\n[a.b]\nd=2", {"a": [{"b": {"c": 1}}, {"b": {"d": 2}}]}, "aot last element")
err("[[a]]\n[a]", "header on aot")
err("a={b=1}\na.c=2", "extend inline table")
err("a={b=1}\n[a.b]", "header into inline table")

# arrays
ok("a=[1,2,]", {"a": [1, 2]}, "trailing comma")
ok("a=[\n1,\n# c\n2\n]", {"a": [1, 2]}, "array comments/newlines")
ok("a=[{b=1},{c=2}]", {"a": [{"b": 1}, {"c": 2}]}, "array inline tables")
err("a={b=1,}", "inline trailing comma")
err("a={b=1\n}", "inline newline")
err("a=[1]\na.b=2", "extend static array")
err("a=[1]\n[[a]]", "aot on static array")

# invalid / line endings / controls
err("a=1\r", "lone CR")
ok("a=1\r\n", {"a": 1}, "CRLF")
err("# comment\r", "lone CR comment")
ok("# tab\t\na=1", {"a": 1}, "tab comment")
err("a=\"abc\x01def\"", "control in string")
err("a=0x_1", "hex underscore invalid")
err("a=1e01", "exponent leading zero")
err("a=1.", "float missing frac digits")
err("a=.1", "float missing int digits")
err("a={b=1 # c}", "comment in inline table")

# random property over a simple valid subset
rng = random.Random(1234)
for _ in range(12):
    keys, doc, expected = set(), [], {}
    for _ in range(8):
        k = "".join(rng.choice("abcXYZ019_-") for _ in range(rng.randint(1, 4)))
        if k in keys:
            continue
        t = rng.randrange(5)
        if t == 0:
            v = str(rng.randint(-10**25, 10**25))
        elif t == 1:
            v = f"{rng.randint(-100, 100)}.5"
        elif t == 2:
            v = rng.choice(["true", "false"])
        elif t == 3:
            v = '"abc"'
        else:
            v = "[1,2,]"
        keys.add(k)
        doc.append(f"{k}={v}")
        expected[k] = eval(v) if v not in ("true", "false") else (v == "true")
    doc = "\n".join(doc)
    ok(doc, expected, "random subset")

# CLI
p = run_script("--test")
exp_lines = ["PASS scalars", "PASS keys", "PASS tables", "PASS arrays", "PASS invalid", "OK: all tests passed"]
check("--test exit 0", p.returncode == 0, f"rc={p.returncode}")
check("--test exact output", p.stdout.strip().splitlines() == exp_lines, f"got {p.stdout.strip().splitlines()!r}")
check("--test no failure markers", "FAIL" not in p.stdout and "Traceback" not in p.stdout)

path = "/tmp/toml_ultra_acceptance.toml"
with open(path, "w", encoding="utf-8") as f:
    f.write("a=1\nb=\"x\"\n")
p = run_script(path)
check("cli valid exit 0", p.returncode == 0, f"rc={p.returncode}")
check("cli valid repr", p.stdout.strip() == repr({"a": 1, "b": "x"}), f"got {p.stdout.strip()!r}")

with open(path, "w", encoding="utf-8") as f:
    f.write("a=1\na=2\n")
p = run_script(path)
check("cli invalid exit 2", p.returncode == 2, f"rc={p.returncode}")
check("cli invalid stderr", p.stderr.startswith("ERROR:"), f"got {p.stderr!r}")

p = run_script("/tmp/toml_ultra_missing_file.toml")
check("cli missing exit 2", p.returncode == 2, f"rc={p.returncode}")
check("cli missing stderr", p.stderr.startswith("ERROR:"), f"got {p.stderr!r}")

bad = "/tmp/toml_ultra_bad_utf8.toml"
with open(bad, "wb") as f:
    f.write(b"\xff\xfe")
p = run_script(bad)
check("cli undecodable exit 2", p.returncode == 2, f"rc={p.returncode}")
check("cli undecodable stderr", p.stderr.startswith("ERROR:"), f"got {p.stderr!r}")

p = run_script()
check("cli no args exit 2", p.returncode == 2, f"rc={p.returncode}")
p = run_script("--bogus")
check("cli unknown arg exit 2", p.returncode == 2, f"rc={p.returncode}")

sys.exit(1 if failed else 0)
