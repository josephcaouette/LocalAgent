# --- added by the pipeline: load the script under test without running its main block ---
import importlib.util as _ilu
import subprocess as _sp
import sys as _sys

_spec = _ilu.spec_from_file_location("target_module", "/work/toml_max_v2.py")
target = _ilu.module_from_spec(_spec)
_sys.modules["target_module"] = target
_sys.modules["target"] = target          # so `import target` works too
_spec.loader.exec_module(target)


def run_script(*args, input=None, timeout=15):
    """Run the script as a separate process. Returns subprocess.CompletedProcess (text mode)."""
    return _sp.run([_sys.executable, "/work/toml_max_v2.py", *map(str, args)], input=input,
                   capture_output=True, text=True, timeout=timeout)

# --- independent acceptance test ---
import math, os, sys, tempfile

def same(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if type(a) is not type(b):
            return False
        if isinstance(a, float) and math.isnan(a) and math.isnan(b):
            return True
        return a == b
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return a == b

fails = []
def rec(name, cond, got=''):
    if cond:
        print(f"PASS: {name}")
    else:
        print(f"FAIL: {name} expected ok, got {got}")
        fails.append(name)

def eq(name, doc, exp):
    try:
        got = target.loads(doc)
    except Exception as e:
        rec(name, False, f"raised {type(e).__name__}: {e}")
        return
    rec(name, same(exp, got), repr(got))

def err(name, doc):
    try:
        target.loads(doc)
    except ValueError:
        rec(name, True)
    except Exception as e:
        rec(name, False, f"raised {type(e).__name__}: {e}")
    else:
        rec(name, False, "no exception")

def ok_cli(name, args, rc, out_contains=None, err_prefix=None, last_line=None):
    try:
        p = run_script(args, timeout=20)
    except Exception as e:
        rec(name, False, f"run_script raised {e}")
        return
    good = p.returncode == rc
    if out_contains is not None:
        good &= out_contains in p.stdout
    if err_prefix is not None:
        good &= p.stderr.startswith(err_prefix)
    if last_line is not None:
        lines = [x for x in p.stdout.splitlines() if x.strip()]
        good &= bool(lines) and lines[-1] == last_line
    rec(name, good, f"rc={p.returncode} out={p.stdout!r} err={p.stderr!r}")

# valid values
eq("empty-doc", "", {})
eq("comment-only", "# c\n", {})
eq("comment-eof", "a = 1 # c", {"a": 1})
eq("crlf", "a = 1\r\n", {"a": 1})
eq("ff-whitespace", "a = 1\x0c\n", {"a": 1})
eq("del-in-string", 'a = "\x7f"', {"a": "\x7f"})
eq("c1-in-string", 'a = "\u0080"', {"a": "\u0080"})
eq("raw-tab-string", 'a = "\t"', {"a": "\t"})
eq("basic-escapes", 'a = "\\b\\t\\n\\f\\r\\\"\\\\\\u0041\\U00000042"', {"a": "\b\t\n\f\r\"\AB"})
eq("literal-string", "a = 'abc'", {"a": "abc"})
eq("literal-double-quote", "a = 'a\"b'", {"a": "a\"b"})
eq("ml-basic-trim", 'a = """\nabc"""', {"a": "abc"})
eq("ml-basic-no-trim", 'a = """abc"""', {"a": "abc"})
eq("ml-basic-continuation", 'a = """abc\\\n  def"""', {"a": "abcdef"})
eq("ml-basic-one-quote", 'a = """x""""', {"a": "x\""})
eq("ml-basic-two-quotes", 'a = """x"""""', {"a": "x\"\""})
eq("ml-literal-trim", "a = '''\nabc'''", {"a": "abc"})
eq("ml-literal-one-apostrophe", "a = '''x''''", {"a": "x'"})
eq("ml-literal-two-apostrophes", "a = '''x'''''", {"a": "x''"})
eq("integer-dec", "a = 1_000", {"a": 1000})
eq("integer-neg-zero", "a = -0", {"a": 0})
eq("integer-plus", "a = +1", {"a": 1})
eq("integer-hex", "a = 0xF0_F0", {"a": 0xF0F0})
eq("integer-oct", "a = 0o1_2", {"a": 10})
eq("integer-bin", "a = 0b1_0", {"a": 2})
eq("integer-large", "a = " + "1" + "0"*4000, {"a": int("1" + "0"*4000)})
eq("float-dec", "a = 1.5", {"a": 1.5})
eq("float-exp", "a = 1e3", {"a": 1000.0})
eq("float-underscore", "a = 1_000.5", {"a": 1000.5})
eq("float-inf", "a = inf", {"a": float("inf")})
eq("float-neg-inf", "a = -inf", {"a": float("-inf")})
eq("float-nan", "a = nan", {"a": float("nan")})
eq("float-overflow", "a = 1e999", {"a": float("inf")})
eq("float-underflow", "a = 1e-999", {"a": 0.0})
eq("bool-true", "a = true", {"a": True})
eq("bool-false", "a = false", {"a": False})
eq("array-empty", "a = []", {"a": []})
eq("array-trailing-comma", "a = [1, 2, ]", {"a": [1, 2]})
eq("array-comments-newlines", "a = [1, # c\n2]", {"a": [1, 2]})
eq("array-crlf", "a = [\r\n1\r\n]", {"a": [1]})
eq("array-mixed", "a = [1, \"s\", true, [2]]", {"a": [1, "s", True, [2]]})
eq("array-large", "a = [" + ",".join(["1"]*10000) + "]", {"a": [1]*10000})
eq("inline-empty", "a = {}", {"a": {}})
eq("inline-dotted", "a = {b.c = 1}", {"a": {"b": {"c": 1}}})
eq("inline-empty-key", 'a = { "" = 1 }', {"a": {"": 1}})
eq("table", "[a]\nb = 1", {"a": {"b": 1}})
eq("table-implicit-explicit", "a.b = 1\n[a]", {"a": {"b": 1}})
eq("table-extend-dotted", "[a]\nb = 1\na.c = 2", {"a": {"b": 1, "c": 2}})
eq("aot", "[[a]]\nb = 1", {"a": [{"b": 1}]})
eq("aot-append", "[[a]]\n[[a]]", {"a": [{}, {}]})
eq("aot-dotted-header", "[[a.b]]\nc = 1", {"a": {"b": [{"c": 1}]}})
eq("aot-intermediate", "[[a]]\n[[a.b]]\nc = 1", {"a": [{"b": [{"c": 1}]}]})
eq("dotted-key", "a.b.c = 1", {"a": {"b": {"c": 1}}})
eq("dotted-key-spaces", "a . b = 1", {"a": {"b": 1}})
eq("quoted-key", '"a b" = 1', {"a b": 1})
eq("literal-quoted-key", "'a-b' = 1", {"a-b": 1})
eq("empty-key", '"" = 1', {"": 1})
eq("empty-key-component", 'a."" = 1', {"a": {"": 1}})
eq("key-escape", '"a\\nb" = 1', {"a\nb": 1})
eq("table-empty-key", '[""]\nb = 1', {"": {"b": 1}})
eq("aot-empty-key", '[[""]]\nb = 1', {"": [{"b": 1}]})
eq("aot-dotted-key", "[[a]]\na.b = 1", {"a": [{"b": 1}]})
eq("aot-table-header", "[[a]]\n[a.b]\nc = 1", {"a": [{"b": {"c": 1}}]})
eq("aot-aot-header", "[[a]]\n[[a.b]]", {"a": [{"b": []}]})

# invalid values/controls
err("invalid-lone-cr", "a = 1\r")
err("invalid-vtab-outside", "a = 1\x0b\n")
err("invalid-nul-outside", "a = 1\x00\n")
err("invalid-del-outside", "a = 1\x7f\n")
err("invalid-c1-outside", "a = 1\u0080\n")
err("invalid-ff-comment", "a = 1 # c\x0c\n")
err("invalid-ff-string", 'a = "\x0c"')
err("invalid-ff-literal", "a = '\x0c'")
err("invalid-raw-newline-basic", 'a = "abc\ndef"')
err("invalid-raw-newline-literal", "a = 'abc\ndef'")
err("invalid-lone-cr-string", 'a = "abc\rdef"')
err("invalid-crlf-string", 'a = "abc\r\ndef"')
err("invalid-surrogate-escape", 'a = "\\uD800"')
err("invalid-escape-bad", 'a = "\\q"')
err("invalid-escape-x", 'a = "\\x41"')
err("invalid-escape-short-u", 'a = "\\u12G4"')
err("invalid-escape-short-U", 'a = "\\U12G45678"')

# invalid numbers
err("invalid-leading-zero", "a = 01")
err("invalid-leading-zero-neg", "a = -01")
err("invalid-underscore-start", "a = _1")
err("invalid-underscore-end", "a = 1_")
err("invalid-underscore-double", "a = 1__0")
err("invalid-hex-underscore", "a = 0x_1")
err("invalid-hex-no-digit", "a = 0x")
err("invalid-hex-sign", "a = -0x1")
err("invalid-hex-upper-prefix", "a = 0X1")
err("invalid-oct-digit", "a = 0o8")
err("invalid-bin-digit", "a = 0b2")
err("invalid-float-dot-only", "a = .5")
err("invalid-float-trailing-dot", "a = 5.")
err("invalid-float-underscore-before-dot", "a = 1_.5")
err("invalid-float-underscore-after-dot", "a = 1._5")
err("invalid-float-exp-no-digit", "a = 1e")
err("invalid-float-exp-sign-no-digit", "a = 1e+")
err("invalid-float-underscore-exp", "a = 1_e3")
err("invalid-float-underscore-after-exp", "a = 1e3_")
err("invalid-float-lead-zero", "a = 01.5")
err("invalid-float-nan-upper", "a = NaN")
err("invalid-float-infinity", "a = infinity")
err("invalid-bool-upper", "a = True")

# invalid dates/times
err("invalid-date", "a = 1979-05-27")
err("invalid-time", "a = 07:32:00")
err("invalid-datetime", "a = 1979-05-27T07:32:00")
err("invalid-offset-datetime", "a = 1979-05-27T07:32:00Z")
err("invalid-date-like", "a = 1979-05")

# invalid arrays/inline
err("invalid-array-comma", "a = [,]")
err("invalid-array-double-comma", "a = [1,,2]")
err("invalid-array-no-comma", "a = [1 2]")
err("invalid-inline-trailing-comma", "a = {b=1,}")
err("invalid-inline-comment", "a = {b=1, # c\n}")
err("invalid-inline-newline", "a = {b=1\n}")
err("invalid-inline-crlf", "a = {b=1\r\n}")

# invalid keys/structure
err("invalid-duplicate-key", "a=1\na=2")
err("invalid-duplicate-dotted", "a.b=1\na.b=2")
err("invalid-dotted-over-scalar", "a.b=1\na.b.c=2")
err("invalid-table-over-key", "a=1\n[a]")
err("implicit-table-over-scalar", "a.b=1\n[a.b]")
err("table-defined-twice", "[a]\n[a]")
err("aot-over-array", "a=[]\n[[a]]")
err("aot-over-table", "[a]\n[[a]]")
err("inline-closed-dot", "a={b=1}\na.c=2")
err("inline-closed-header", "a={b=1}\n[a.c]")
err("static-array-extend", "a=[1]\na.b=2")
err("aot-final-key", "[[a]]\na=1")
err("table-header-over-aot", "[[a]]\n[a]")
err("aot-header-over-scalar", "a=1\n[[a]]")
err("aot-header-over-table", "a.b.c=1\n[[a.b]]")
err("ml-basic-six-quotes", 'a = """x""""""')
err("ml-literal-six-quotes", "a = '''x''''''")
err("invalid-key-double-dot", "a..b=1")
err("invalid-key-trailing-dot", "a.b.=1")
err("invalid-key-leading-dot", ".a=1")
err("invalid-newline-before-eq", "a\n=1")
err("invalid-newline-after-eq", "a =\n1")
err("invalid-comment-before-value", "a = # c\n1")
err("invalid-lone-cr-eq", "a\r=1")

# CLI
fd, f1 = tempfile.mkstemp(dir="/tmp", suffix=".toml")
os.write(fd, b"a = 1\n"); os.close(fd)
ok_cli("cli-valid", [f1], 0, out_contains="{'a': 1}")
fd, f2 = tempfile.mkstemp(dir="/tmp", suffix=".toml")
os.write(fd, b"a = 01\n"); os.close(fd)
ok_cli("cli-invalid", [f2], 1, err_prefix="ValueError:")
ok_cli("cli-missing", ["/tmp/definitely_missing_toml_test_file_xyz"], 2, err_prefix="OSError:")
ok_cli("cli-unknown", ["--bogus"], 2)
ok_cli("cli-test", ["--test"], 0, last_line="ALL TESTS PASSED")
p = run_script(["--test"], timeout=20)
pass_lines = [l for l in p.stdout.splitlines() if l.startswith("PASS: ")]
required = {"basic-string","literal-string","multi-line-basic-string","multi-line-literal-string","integer","float","boolean","array","inline-table","table","array-of-tables","dotted-key","quoted-key","empty-key","invalid-date","invalid-duplicate-key","invalid-lone-cr","invalid-leading-zero","invalid-underscore"}
names = {l[6:] for l in pass_lines}
rec("cli-test-count", len(pass_lines) >= 25, f"{len(pass_lines)} PASS lines")
rec("cli-test-required", required.issubset(names), f"missing {required - names}")
rec("cli-test-no-fail", not any(l.startswith("FAILED: ") for l in p.stdout.splitlines()), p.stdout)

sys.exit(1 if fails else 0)
