"""Each new or revised independent test first runs against two stand-ins for the script that implement
nothing and answer differently (A: truthy, equal to everything; B: falsy, equal to nothing). What it
reports the same way against both can't come from the script's answer, so it goes back to the test's
writer before any candidate is blamed. Set 4's MAX acceptance test for the expression evaluator had
two such bugs, found one attempt at a time: its generator recursed without end (attempt 15), then
fed Python's eval expressions it rejects (attempt 16, the last).
Part 1: the comparison on made-up outputs. Part 2: the repair flow (fake model). Part 3: the saved
tests in the sandbox (Node 2): both broken MAX tests are caught, and tests that winning candidates
passed come out clean."""
import os
import shutil
import sys

sys.path.insert(0, r"Z:\workspace")
os.chdir(r"Z:\workspace")
import config  # noqa: E402
import run_langgraph_pipeline as p  # noqa: E402

p.report = lambda *a, **k: None
checks = []

# --- 1. The comparison --------------------------------------------------------------------------
EVAL = "FAIL: random 28 ((4 - not 4) ^ True) expected 'eval no exception', got 'SyntaxError: invalid syntax'"
out_a = "\n".join(["PASS: cli", EVAL, "FAIL: value 1+2 expected 3, got <stand-in A value>",
                   "FAIL: rejects 1+ expected 'ValueError', got 'no exception'", "FAIL: bare label",
                   "FAIL: count expected 5, got 17"])
out_b = "\n".join(["FAIL: cli expected 0, got 3", EVAL, "FAIL: value 1+2 expected 3, got <stand-in B value>",
                   "FAIL: rejects 1+ expected 'ValueError', got 'no exception'", "FAIL: bare label",
                   "FAIL: count expected 5, got 42"])
found = p.standin_findings(out_a, out_b, "pyexpr_max.py")
checks += [
    ("the same FAIL line with a got-value against both is found", found == [EVAL]),
    ("a line that names a stand-in value is left alone", not any("stand-in" in f for f in found)),
    ("an exception check (neither stand-in raises) is left alone", not any("ValueError" in f for f in found)),
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

# --- 3. The saved tests, in the sandbox -----------------------------------------------------------
RUNS = config.RUNS_DIR
# The two MAX tests first crash in their own code when the big-number check fails: building the FAIL
# message takes repr() of a 100,000-digit int, past Python's 4,300-digit limit (no candidate failed
# that check, so no run saw it). "+digits" copies them with that limit lifted, as a writer's fix would,
# which uncovers the bugs the run met: invalid expressions for eval (a16) and endless recursion (a15).
SAVED = [  # (run, folder, test file, target, expected)
    ("20261102-100936", "a16c1", "acceptance_test.py", "pyexpr_max.py", "digits"),
    ("20261102-100936", "a15c1", "acceptance_test.py", "pyexpr_max.py", "digits"),
    ("20261102-100936", "a16c1", "acceptance_test.py+digits", "pyexpr_max.py", "eval"),
    ("20261102-100936", "a15c1", "acceptance_test.py+digits", "pyexpr_max.py", "recursion"),
    ("20261102-161028", "a10c3", "acceptance_test.py", "toml_max.py", "clean"),     # passed runs: a winner
    ("20261102-161028", "a10c3", "adversarial_test.py", "toml_max.py", "clean"),    # passed these tests
    ("20261102-143412", "a8c3", "acceptance_test.py", "toml_ultra.py", "clean"),
    ("20261102-202246", "a8c4", "acceptance_test.py", "struct_max.py", "clean"),
    ("20261102-202246", "a8c4", "adversarial_test.py", "struct_max.py", "clean"),
    ("20261102-183130", "a7c4", "acceptance_test.py", "struct_ultra.py", "clean"),
]
shutil.rmtree(os.path.join(RUNS, "unit-standin"), ignore_errors=True)
for k, (run, cand, fname, target, want) in enumerate(SAVED, 1):
    path = os.path.join(RUNS, run, cand, fname.split("+")[0])
    if not os.path.exists(path):
        checks.append((f"saved {run}/{cand}/{fname}: file missing (runs older than the newest 30 are deleted)", True))
        continue
    test = open(path, encoding="utf-8").read().replace("\r\n", "\n")
    if fname.endswith("+digits"):
        marker = "# --- independent acceptance test ---\n"
        test = test.replace(marker, marker + "import sys as _s4300\n_s4300.set_int_max_str_digits(0)\n", 1)
    role = "adversarial" if fname.startswith("adversarial") else "acceptance"
    st = dict(state, target_file=target, attempt=100 + k)
    found = p.standin_findings(*p.standin_runs(st, role, test), target)
    shown = "; ".join(f[:90] for f in found[:2])
    if want == "digits":
        ok = len(found) == 1 and "Exceeds the limit (4300 digits)" in found[0]
    elif want == "eval":
        ok = found and all("eval no exception" in f for f in found)
    elif want == "recursion":
        ok = found and any("RecursionError" in f for f in found)
    else:
        ok = found == []
    checks.append((f"saved {run[-6:]}/{cand}/{fname} ({target}): {want} -> {len(found)} found {shown}", bool(ok)))
shutil.rmtree(os.path.join(RUNS, "unit-standin"), ignore_errors=True)

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(("PASS " if ok else "FAIL ") + name)
print("ALL PASS" if not failed else f"{len(failed)} FAILED")
sys.exit(1 if failed else 0)
