"""Engineer replies that aren't scripts are rejected before they reach the sandbox: no --test mode,
or only bare values (a JSON plan that mentions --test compiles as Python and runs silently)."""
import os
import sys

sys.path.insert(0, r"Z:\workspace")
os.chdir(r"Z:\workspace")
import run_langgraph_pipeline as p  # noqa: E402

PLAN = ('{\n  "steps": ["Write glob.py with match(pattern, text).", "Support --test for a self-check."],\n'
        '  "checks": ["python3 glob.py --test exits 0"]\n}')
SCRIPT = ("import sys\n\ndef match(p, t):\n    return p == t\n\nif __name__ == '__main__':\n"
          "    if sys.argv[1:] == ['--test']:\n        print('PASS')\n")
cases = [("JSON plan mentioning --test", PLAN, True), ("docstring only", '"""--test: notes"""', True),
         ("real script", SCRIPT, False), ("print-only script", "print('--test')", False),
         ("syntax error is left to the syntax check", "def f(:\n  '--test'", False)]
ok = True
for name, code, want in cases:
    got = p.only_expressions(code)
    ok &= got == want
    print(("PASS " if got == want else "FAIL ") + f"{name}: flagged={got}")
print("ALL PASS" if ok else "SOME FAILED")
