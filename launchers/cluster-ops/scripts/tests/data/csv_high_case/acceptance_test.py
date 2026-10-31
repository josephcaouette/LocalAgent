# --- added by the pipeline: load the script under test without running its main block ---
import importlib.util as _ilu
import subprocess as _sp
import sys as _sys

_spec = _ilu.spec_from_file_location("target_module", "/work/csv_high.py")
target = _ilu.module_from_spec(_spec)
_sys.modules["target_module"] = target
_sys.modules["target"] = target          # so `import target` works too
_spec.loader.exec_module(target)


def run_script(*args, input=None, timeout=15):
    """Run the script as a separate process. Returns subprocess.CompletedProcess (text mode)."""
    return _sp.run([_sys.executable, "/work/csv_high.py", *map(str, args)], input=input,
                   capture_output=True, text=True, timeout=timeout)

# --- independent acceptance test ---
import os
import sys

failures = []

def check(name, ok, expected=None, got=None):
    if ok:
        print(f"PASS: {name}")
    else:
        if expected is None and got is None:
            print(f"FAIL: {name}")
        else:
            print(f"FAIL: {name} expected {expected!r}, got {got!r}")
        failures.append(name)

def expect_value(name, text, expected):
    try:
        got = target.parse_csv(text)
    except Exception as exc:
        check(name, False, expected, f"raised {type(exc).__name__}: {exc}")
        return
    check(name, got == expected, expected, got)

def expect_value_error(name, text):
    try:
        got = target.parse_csv(text)
    except ValueError:
        check(name, True)
    except Exception as exc:
        check(name, False, "ValueError", f"raised {type(exc).__name__}: {exc}")
    else:
        check(name, False, "ValueError", f"parsed {got!r}")

value_cases = [
    ("empty_text", "", []),
    ("single_record", "a,b,c", [["a", "b", "c"]]),
    ("trailing_lf", "a,b\n", [["a", "b"]]),
    ("trailing_crlf", "a,b\r\n", [["a", "b"]]),
    ("lone_cr_is_ordinary", "a\rb", [["a\rb"]]),
    ("lone_lf_at_end", "\n", []),
    ("lone_crlf_at_end", "\r\n", []),
    ("empty_line_elsewhere_lf", "\n\n", [[]]),
    ("empty_line_elsewhere_crlf", "\r\n\r\n", [[]]),
    ("empty_fields", "a,,b", [["a", "", "b"]]),
    ("leading_trailing_commas", ",a,b,", [["", "a", "b", ""]]),
    ("single_comma", ",", [["", ""]]),
    ("quoted_empty", '""', [[""]]),
    ("quoted_simple", '"a"', [["a"]]),
    ("quoted_comma", '"a,b"', [["a,b"]]),
    ("quoted_escaped_quote", '"a""b"', [["a\"b"]]),
    ("quoted_escaped_quotes_end", '"a""b"""', [["a\"b\""]]),
    ("quoted_lf", '"a\nb"', [["a\nb"]]),
    ("quoted_crlf", '"a\r\nb"', [["a\r\nb"]]),
    ("quoted_lone_cr", '"a\rb"', [["a\rb"]]),
    ("unquoted_quote", 'a"b', [["a\"b"]]),
    ("unquoted_quote_with_comma", 'a"b,c', [["a\"b", "c"]]),
    ("mixed_fields", 'a,"b,c",d', [["a", "b,c", "d"]]),
    ("multiple_quoted_fields", '"a,b","c""d"', [["a,b", "c\"d"]]),
    ("lf_records", "a,b\nc,d", [["a", "b"], ["c", "d"]]),
    ("crlf_records", "a,b\r\nc,d", [["a", "b"], ["c", "d"]]),
    ("empty_line_between_lf", "a\n\nb", [["a"], [], ["b"]]),
    ("empty_line_between_crlf", "a\r\n\r\nb", [["a"], [], ["b"]]),
    ("trailing_empty_line_lf", "a\n\n", [["a"], []]),
    ("trailing_empty_line_crlf", "a\r\n\r\n", [["a"], []]),
    ("after_quote_comma", '"a",b', [["a", "b"]]),
    ("after_quote_comma_end", '"a",', [["a", ""]]),
    ("after_quote_lf_end", '"a"\n', [["a"]]),
    ("after_quote_crlf_end", '"a"\r\n', [["a"]]),
    ("after_quote_lf_record", '"a"\nb', [["a"], ["b"]]),
    ("after_quote_crlf_record", '"a"\r\nb', [["a"], ["b"]]),
    ("after_quote_comma_quoted", '"a","b"', [["a", "b"]]),
]

for name, text, expected in value_cases:
    expect_value(name, text, expected)

error_cases = [
    ("unterminated_quoted", '"abc'),
    ("unterminated_quoted_lf", '"abc\n'),
    ("unterminated_quoted_crlf", '"abc\r\n'),
    ("unterminated_after_escape", '"a""'),
    ("char_after_closing_quote", '"a"b'),
    ("space_after_closing_quote", '"a" '),
    ("lone_cr_after_closing_quote", '"a"\r'),
]

for name, text in error_cases:
    expect_value_error(name, text)

def write_tmp(name, data):
    path = os.path.join("/tmp", name)
    with open(path, "wb") as f:
        f.write(data)
    return path

normal_path = write_tmp("csv_high_accept_normal.csv", b"a,b\nc,d\r\n")
p = run_script(normal_path)
check("cli_normal_exit", p.returncode == 0, 0, p.returncode)
check(
    "cli_normal_output",
    p.stdout.splitlines() == [repr(["a", "b"]), repr(["c", "d"])],
    [repr(["a", "b"]), repr(["c", "d"])],
    p.stdout.splitlines(),
)

quoted_path = write_tmp("csv_high_accept_quoted.csv", b'"a,b"\n"x""y"\n')
p = run_script(quoted_path)
check("cli_quoted_exit", p.returncode == 0, 0, p.returncode)
check(
    "cli_quoted_output",
    p.stdout.splitlines() == [repr(["a,b"]), repr(["x\"y"])],
    [repr(["a,b"]), repr(["x\"y"])],
    p.stdout.splitlines(),
)

empty_path = write_tmp("csv_high_accept_empty.csv", b"")
p = run_script(empty_path)
check("cli_empty_exit", p.returncode == 0, 0, p.returncode)
check("cli_empty_output", p.stdout.strip() == "", "", p.stdout.strip())

empty_line_path = write_tmp("csv_high_accept_empty_line.csv", b"a\n\nb")
p = run_script(empty_line_path)
check("cli_empty_line_exit", p.returncode == 0, 0, p.returncode)
check(
    "cli_empty_line_output",
    p.stdout.splitlines() == [repr(["a"]), repr([]), repr(["b"])],
    [repr(["a"]), repr([]), repr(["b"])],
    p.stdout.splitlines(),
)

error_path = write_tmp("csv_high_accept_error.csv", b'"a"b')
p = run_script(error_path)
check("cli_parse_error_exit", p.returncode == 1, 1, p.returncode)
check("cli_parse_error_stderr", p.stderr.strip() != "", "non-empty", p.stderr.strip())

missing_path = "/tmp/csv_high_accept_missing.csv"
if os.path.exists(missing_path):
    os.remove(missing_path)
p = run_script(missing_path)
check("cli_missing_file_exit", p.returncode == 1, 1, p.returncode)
check("cli_missing_file_stderr", p.stderr.strip() != "", "non-empty", p.stderr.strip())

p = run_script()
check("cli_no_args_exit", p.returncode == 2, 2, p.returncode)
check("cli_no_args_stderr", p.stderr.strip() != "", "non-empty", p.stderr.strip())

p = run_script("--bogus")
check("cli_unknown_args_exit", p.returncode == 2, 2, p.returncode)
check("cli_unknown_args_stderr", p.stderr.strip() != "", "non-empty", p.stderr.strip())

p = run_script("--test")
check("selftest_exit", p.returncode == 0, 0, p.returncode)
for case in [
    "quoting",
    "escaped_quotes",
    "line_breaks_inside_quotes",
    "crlf",
    "empty_fields",
    "empty_lines",
    "errors",
]:
    check(f"selftest_{case}", f"PASS {case}" in p.stdout, f"PASS {case}", p.stdout)
check("selftest_ok", "OK" in p.stdout, "OK", p.stdout)
check(
    "selftest_no_fail_or_traceback",
    "FAIL" not in p.stdout and "Traceback" not in p.stdout,
    "no FAIL/Traceback",
    p.stdout,
)

sys.exit(1 if failures else 0)
