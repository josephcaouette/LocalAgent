"""Each new or revised independent test first runs against two stand-ins for the script that implement
nothing and answer differently (A: truthy, equal to everything; B: falsy, equal to nothing). What it
reports the same way against both can't come from the script's answer, so it goes back to the test's
writer before any candidate is blamed. Set 4's MAX acceptance test for the expression evaluator had
two such bugs, found one attempt at a time: its generator recursed without end (attempt 15), then
fed Python's eval expressions it rejects (attempt 16, the last).
Part 1: the comparison on made-up outputs. Part 2: the repair flow (fake model). Part 3: saved tests
from set 4's second and third batteries in the sandbox (Node 2), from tests/data/standin_case/cases.json."""
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, r"Z:\workspace")
os.chdir(r"Z:\workspace")
import config  # noqa: E402
import run_langgraph_pipeline as p  # noqa: E402

p.report = lambda *a, **k: None
checks = []

# --- 1. The comparison --------------------------------------------------------------------------
EVAL = "FAIL: random 28 ((4 - not 4) ^ True) expected 'eval no exception', got 'SyntaxError: invalid syntax'"
TOTAL = "FAIL: total of 2 and 3 expected 6, got 5"     # worked out by the test itself, the same for any script
# Exception checks as set 4's second and third batteries worded them (51 and 76 such lines were sent back
# to the MAX testers as findings in the second; "should raise" came up in the third).
EXC = ["FAIL: rejects 1+ expected 'ValueError', got 'no exception'", "FAIL: 1//0 expected error, got no error",
       "FAIL: invalid-lone-cr expected ok, got no exception", "FAIL: 2 ** -1 did not raise ValueError",
       "FAIL: range b expected None, got '128 should raise ValueError, got None'",
       "FAIL: range b expected None, got '-129 should raise, got None'"]
# Verdicts the test worked out about the answer, as the third battery's struct tests printed them:
# isinstance(U(...), tuple), and isinstance(exc(...), ValueError) with the check's default values.
VERDICT = ["FAIL: unpack tuple expected True, got False", "FAIL: __index__ out of range expected None, got None"]
out_a = "\n".join(["PASS: cli", EVAL, TOTAL, "FAIL: value 1+2 expected 3, got <stand-in A value>"] + EXC + VERDICT
                  + ["FAIL: bare label", "FAIL: count expected 5, got 17"])
out_b = "\n".join(["FAIL: cli expected 0, got 3", EVAL, TOTAL, "FAIL: value 1+2 expected 3, got <stand-in B value>"]
                  + EXC + VERDICT + ["FAIL: bare label", "FAIL: count expected 5, got 42"])
found = p.standin_findings(out_a, out_b, "pyexpr_max.py")
checks += [
    ("the same FAIL line with a got-value against both is found", found == [EVAL, TOTAL]),
    ("a line that names a stand-in value is left alone", not any("stand-in" in f for f in found)),
    ("exception checks, however worded, are left alone (neither stand-in raises)", not any(f in EXC for f in found)),
    ("a bare None/True/False the test worked out is left alone (the same for both stand-ins)",
     not any(f in VERDICT for f in found)),
    ("a FAIL line without a value is left alone", "FAIL: bare label" not in found),
]
crash = ('Traceback (most recent call last):\n  File "/work/acceptance_test.py", line 170, in <module>\n'
         '    expr = gen(4)\n  File "/work/acceptance_test.py", line 166, in gen\n'
         '    return f"({gen(d-1)} {rng.choice(bins)} {gen(d-2)})"\nRecursionError: maximum recursion depth exceeded\n')
found = p.standin_findings("PASS: a\n" + crash, "FAIL: a expected 1, got 2\n" + crash, "pyexpr_max.py")
checks.append(("the same crash in the test's own code is found",
               len(found) == 1 and "RecursionError" in found[0] and "line 166" in found[0]))
in_standin = crash.replace('"/work/acceptance_test.py", line 166', '"/work/pyexpr_max.py", line 12')
checks += [
    ("a crash inside the stand-in is left alone", p.standin_findings(in_standin, in_standin, "pyexpr_max.py") == []),
    ("crashes that differ are left alone",
     p.standin_findings(crash, crash.replace("line 166", "line 99"), "pyexpr_max.py") == []),
    ("an assertion is a check, not a crash", p.standin_findings(
        crash.replace("RecursionError: maximum recursion depth exceeded", "AssertionError: 3 != 4"),
        crash.replace("RecursionError: maximum recursion depth exceeded", "AssertionError: 3 != 4"),
        "pyexpr_max.py") == []),
]

# --- 2. The repair flow -------------------------------------------------------------------------
TEST = 'print("PASS: a")\nprint("FAIL: random 1 expected \'eval no exception\', got \'SyntaxError\'")\n'
FIXED = 'print("PASS: a")\nprint("PASS: random 1 rejected as invalid")\n'
state = {"run_id": "unit-standin", "attempt": 2, "target_file": "pyexpr_max.py",
         "lvl": config.level_settings("max"), "allow_network": False}
full = p.test_header("pyexpr_max.py") + TEST
runs, chats = [], []


def fake_runs(st, role, test):
    runs.append(test)
    out = ("PASS: a\nFAIL: random 1 expected 'eval no exception', got 'SyntaxError'\n" if "eval no exception" in test
           else "PASS: a\nPASS: random 1 rejected as invalid\n")
    return out, out


def fake_chat(label, system, blocks, want_out, min_out, **kw):
    chats.append({b["title"]: b["text"] for b in blocks})
    edit = ("<<<<<<< SEARCH\nprint(\"FAIL: random 1 expected 'eval no exception', got 'SyntaxError'\")\n=======\n"
            "print(\"PASS: random 1 rejected as invalid\")\n>>>>>>> REPLACE")
    return (edit if reply["mode"] == "fix" else "no edits"), "stop"


reply = {"mode": "fix"}
real_runs, real_chat = p.standin_runs, p.llm_chat
p.standin_runs, p.llm_chat = fake_runs, fake_chat
src = "FAIL: random 1 expected 'eval no exception', got 'SyntaxError'"
out = p.standin_review(state, "acceptance", "sys", [p.block("Goal:", "g")], full)
checks += [
    ("review: the finding goes back to the writer once", len(chats) == 1 and src in chats[0]["Task:"]),
    ("review: the fixed test is checked again and used", out.endswith(FIXED) and len(runs) == 2),
]
runs.clear(), chats.clear()
reply["mode"] = "refuse"
out = p.standin_review(state, "acceptance", "sys", [p.block("Goal:", "g")], full)
checks.append(("review: no fix, the test is kept with a note for the diagnosis",
               out.startswith(full.rstrip()) and "# --- stand-in check" in out and "eval no exception" in out.split(
                   "stand-in check")[1] and len(chats) == 1))
runs.clear(), chats.clear()
checks.append(("review: a clean test goes through untouched, no model call",
               p.standin_review(state, "acceptance", "sys", [], p.test_header("pyexpr_max.py") + FIXED)
               == p.test_header("pyexpr_max.py") + FIXED and chats == []))
p.STANDIN_CHECK = False
checks.append(("review: switched off, nothing runs", p.standin_review(state, "acceptance", "sys", [], full) == full
               and len(runs) == 1))
p.STANDIN_CHECK = True
p.standin_runs, p.llm_chat = real_runs, real_chat

# --- 3. Saved tests, in the sandbox ---------------------------------------------------------------
# From set 4's second battery: the two MAX tests whose exception checks were taken for findings (they
# must come out clean); two High tests with a real bug each, found in the run but not repaired (a
# FAIL message built with repr() of a 100,000-digit int, past Python's 4,300-digit limit; a reference
# call to struct.calcsize that raises for every candidate); and the test TOML's Ultra winner passed.
# From the third: struct on MAX's acceptance test (19 exception checks printed "expected None, got None"
# or "should raise") and adversarial test (an isinstance check), all false findings: clean.
# The first battery's MAX tests, where the check found its first bugs (invalid expressions for eval,
# endless recursion), were pruned with their runs before they were saved here.
RUNS = config.RUNS_DIR
case = os.path.join(HERE, "data", "standin_case")
shutil.rmtree(os.path.join(RUNS, "unit-standin"), ignore_errors=True)
for k, c in enumerate(json.load(open(os.path.join(case, "cases.json"), encoding="utf-8")), 1):
    test = open(os.path.join(case, c["file"]), encoding="utf-8").read()
    st = dict(state, target_file=c["target"], attempt=100 + k)
    found = p.standin_findings(*p.standin_runs(st, c["role"], test), c["target"])
    shown = "; ".join(f[:90] for f in found[:2])
    ok = found == [] if c["expect"] == "clean" else len(found) == 1 and c["expect"] in found[0]
    checks.append((f"saved {c['file']} ({c['from']}): {c['expect']} -> {len(found)} found {shown}", ok))
shutil.rmtree(os.path.join(RUNS, "unit-standin"), ignore_errors=True)

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(("PASS " if ok else "FAIL ") + name)
print("ALL PASS" if not failed else f"{len(failed)} FAILED")
sys.exit(1 if failed else 0)
