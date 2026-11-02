# --- added by the pipeline: load the script under test without running its main block ---
import importlib.util as _ilu
import subprocess as _sp
import sys as _sys

_spec = _ilu.spec_from_file_location("target_module", "/work/json_max.py")
target = _ilu.module_from_spec(_spec)
_sys.modules["target_module"] = target
_sys.modules["target"] = target          # so `import target` works too
_spec.loader.exec_module(target)


def run_script(*args, input=None, timeout=15):
    """Run the script as a separate process. Returns subprocess.CompletedProcess (text mode)."""
    return _sp.run([_sys.executable, "/work/json_max.py", *map(str, args)], input=input,
                   capture_output=True, text=True, timeout=timeout)

# --- independent acceptance test ---
import sys, os, math, tempfile, io, contextlib

fails = []
def check(name, ok, detail=""):
    print(("PASS: " if ok else f"FAIL: {name} ") + ("" if ok else detail))
    fails.append(not ok)

def val(name, text, expected):
    try:
        got = target.parse_json(text)
    except Exception as e:
        check(name, False, f"raised {type(e).__name__}: {e}")
        return
    ok = type(got) is type(expected) and got == expected
    check(name, ok, f"expected {expected!r}, got {got!r}")

def err(name, text, exc=ValueError):
    try:
        target.parse_json(text)
    except exc:
        check(name, True)
    except Exception as e:
        check(name, False, f"wrong exception {type(e).__name__}: {e}")
    else:
        check(name, False, "no exception")

# literals
val("null", "null", None)
val("true", "true", True)
val("false", "false", False)
for t in ["Null", "TRUE", "False", "nul", "tru", "nullx", "truex", "falsex"]:
    err(f"literal {t!r}", t)

# numbers
val("num 0", "0", 0)
val("num -0", "-0", 0)
val("num 1", "1", 1)
val("num -1", "-1", -1)
val("num big int", "9" * 1000, int("9" * 1000))
val("num 0.0", "0.0", 0.0)
val("num 1.0", "1.0", 1.0)
val("num 1e0", "1e0", 1.0)
val("num 1e1", "1e1", 10.0)
val("num 1E-2", "1E-2", 0.01)
val("num 0e1", "0e1", 0.0)
val("num 1e01", "1e01", 10.0)
val("num 1e+1", "1e+1", 10.0)
val("num 1.5e-3", "1.5e-3", 0.0015)
try:
    got = target.parse_json("-0.0")
    check("num -0.0 sign", type(got) is float and math.copysign(1, got) == -1.0, f"got {got!r}")
except Exception as e:
    check("num -0.0 sign", False, f"raised {type(e).__name__}: {e}")
try:
    got = target.parse_json("1e999")
    check("num overflow inf", type(got) is float and math.isinf(got) and got > 0, f"got {got!r}")
except Exception as e:
    check("num overflow inf", False, f"raised {type(e).__name__}: {e}")
try:
    got = target.parse_json("1e-999")
    check("num underflow zero", type(got) is float and got == 0.0, f"got {got!r}")
except Exception as e:
    check("num underflow zero", False, f"raised {type(e).__name__}: {e}")
for t in ["+1", "01", "1.", ".1", "1e", "1e+", "1e-", "NaN", "Infinity", "inf",
          "-Infinity", "1.e1", ".1e1", "0.", "0e", "1e1e1", "- 1", "1 2", "1a",
          "a1", "1\x0b", "\x0b1", "1\xa0", "\xa01", "1\x85", "1\x0c", "1\x1f",
          "-", "+", "1e01e", "1.0.0", "1..0", "1e+01e", "1e-01e"]:
    err(f"num invalid {t!r}", t)

# strings
val("str empty", '""', "")
val("str space", '"a b"', "a b")
val("str quote", '"\\""', '"')
val("str backslash", r'"\\"', "\\")
val("str slash", r'"\/"', "/")
val("str b", r'"\b"', "\x08")
val("str f", r'"\f"', "\x0c")
val("str n", r'"\n"', "\n")
val("str r", r'"\r"', "\r")
val("str t", r'"\t"', "\t")
val("str u00e9", r'"\u00e9"', "\u00e9")
val("str u0000", r'"\u0000"', "\x00")
val("str u upper", r'"\u00E9"', "\u00e9")
val("str pair", r'"\ud83d\ude00"', "\U0001F600")
val("str pair upper", r'"\uD83D\uDE00"', "\U0001F600")
val("str pair min", r'"\ud800\udc00"', "\U00010000")
val("str pair max", r'"\udbff\udfff"', "\U0010FFFF")
val("str lone high", r'"\ud800"', "\ud800")
val("str lone low", r'"\udc00"', "\udc00")
val("str low high", r'"\udc00\ud800"', "\udc00\ud800")
val("str high high", r'"\ud800\ud800"', "\ud800\ud800")
val("str high normal", r'"\ud800\u0041"', "\ud800A")
val("str normal high", r'"\u0041\ud800"', "A\ud800")
val("str pair separated", r'"\ud800 \udc00"', "\ud800 \udc00")
val("str escaped backslash then u", r'"\\u00e9"', "\\u00e9")
val("str raw nbsp", '"a\xa0b"', "a\xa0b")
val("str raw u0085", '"a\x85b"', "a\x85b")
val("str raw del", '"a\x7fb"', "a\x7fb")
val("str raw u0080", '"a\x80b"', "a\x80b")
for t in ['"abc', '"a\nb"', '"a\tb"', '"a\x00b"', '"a\x1fb"', '"\q"', r'"\u00e"', r'"\u00eG"']:
    err(f"str invalid {t!r}", t)

# objects
val("obj empty", "{}", {})
val("obj simple", '{"a":1}', {"a": 1})
val("obj nested", '{"a":[1,{"b":null}]}', {"a": [1, {"b": None}]})
val("obj dup keys", '{"b":1,"a":2,"b":3}', {"b": 3, "a": 2})
try:
    got = target.parse_json('{"b":1,"a":2,"b":3}')
    check("obj dup key order", list(got) == ["b", "a"], f"got {list(got)!r}")
except Exception as e:
    check("obj dup key order", False, f"raised {type(e).__name__}: {e}")
val("obj empty key", '{"":1}', {"": 1})
val("obj key escape", r'{"a\nb":1}', {"a\nb": 1})
val("obj key pair", r'{"\ud83d\ude00":1}', {"\U0001F600": 1})
for t in ['{"a":1,}', '{,"a":1}', '{"a":1,,}', '{"a":1 "b":2}', '{"a" 1}',
          '{a:1}', '{"a":1}x', '{"a":}', '{:1}', '{"a",1}', '{"a":1', '{"a":1}2']:
    err(f"obj invalid {t!r}", t)

# arrays
val("arr empty", "[]", [])
val("arr simple", '[1,"a",true,null]', [1, "a", True, None])
val("arr nested", '[[1],{"b":2}]', [[1], {"b": 2}])
for t in ['[1,]', '[,1]', '[1,,2]', '[1 2]', '[1', '[1]2', '[x]']:
    err(f"arr invalid {t!r}", t)

# whitespace and top-level
val("ws around", " \t\n\r 1 \t\n\r ", 1)
val("ws object", '{\t"a"\n:\r 1\r}', {"a": 1})
val("ws array", '[\t1\n,\r 2\r]', [1, 2])
for t in ["", " \t\n\r ", "1\xa0", "\xa01", "1\xa02", "1\x85", "1\x0b", "1\x0c",
          "1\x1f", "1\x852", "1 2", "{}x", "[]x", '"a"x', "nullx"]:
    err(f"ws/top invalid {t!r}", t)

# non-str
for x in [1, b"1", None, ["1"]]:
    err(f"non-str {type(x).__name__}", x, TypeError)

# CLI
with tempfile.TemporaryDirectory(dir="/tmp") as td:
    def w(name, data, binary=False):
        p = os.path.join(td, name)
        mode = "wb" if binary else "w"
        with open(p, mode, encoding=None if binary else "utf-8") as f:
            f.write(data)
        return p

    cases = [
        ("cli int", "1", "1\n"),
        ("cli null", "null", "None\n"),
        ("cli true", "true", "True\n"),
        ("cli false", "false", "False\n"),
        ("cli -0.0", "-0.0", "-0.0\n"),
        ("cli dict", '{"a":[1,{"b":null}]}', repr({"a": [1, {"b": None}]}) + "\n"),
        ("cli emoji", r'"\ud83d\ude00"', repr("\U0001F600") + "\n"),
        ("cli nbsp string", '"a\xa0b"', repr("a\xa0b") + "\n"),
        ("cli ws", " \t\n\r 42 \t\n\r ", "42\n"),
    ]
    for name, text, expected in cases:
        p = w(name + ".json", text)
        r = run_script(p)
        check(name, r.returncode == 0 and r.stdout == expected,
              f"rc={r.returncode} out={r.stdout!r} err={r.stderr!r}")

    for name, text in [("cli empty", ""), ("cli ws only", "   "), ("cli bad", "nul"),
                       ("cli trailing", "1 2"), ("cli nbsp ws", "1\xa0")]:
        p = w(name + ".json", text)
        r = run_script(p)
        check(name + " invalid", r.returncode == 1 and r.stderr.strip() != "",
              f"rc={r.returncode} out={r.stdout!r} err={r.stderr!r}")

    p = w("badutf.json", b"\xff\xfe", binary=True)
    r = run_script(p)
    check("cli invalid utf8", r.returncode == 1 and r.stderr.strip() != "",
          f"rc={r.returncode} err={r.stderr!r}")

    r = run_script(os.path.join(td, "missing.json"))
    check("cli missing", r.returncode == 1 and r.stderr.strip() != "",
          f"rc={r.returncode} err={r.stderr!r}")

    r = run_script()
    check("cli no args usage", r.returncode == 2 and "usage" in r.stderr,
          f"rc={r.returncode} err={r.stderr!r}")

    r = run_script("--test", "extra")
    check("cli extra args usage", r.returncode == 2 and "usage" in r.stderr,
          f"rc={r.returncode} err={r.stderr!r}")

    expected_lines = ["PASS literals", "PASS numbers", "PASS strings", "PASS objects",
                      "PASS arrays", "PASS whitespace", "PASS malformed", "ALL TESTS PASSED"]
    r = run_script("--test")
    check("cli --test exact", r.returncode == 0 and r.stdout.splitlines() == expected_lines,
          f"rc={r.returncode} out={r.stdout!r}")

# main()
try:
    out = io.StringIO(); errbuf = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(errbuf):
        rc = target.main([])
    check("main no args returns 2", rc == 2 and "usage" in errbuf.getvalue(),
          f"rc={rc!r} err={errbuf.getvalue()!r}")
except Exception as e:
    check("main no args returns 2", False, f"raised {type(e).__name__}: {e}")

sys.exit(1 if fails else 0)
