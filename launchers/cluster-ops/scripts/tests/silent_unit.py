"""An independent test that exits with an error although every check it printed passed (fake LLM, no
sandbox). Set 3's json run on MAX lost four attempts to one: its adversarial test ended with
sys.exit(1 if fails else 0) where fails held one False per passing check, so it always exited 1 and
printed nothing but PASS lines. Two diagnoses invented a failure and blamed the script, and the
engineer broke working code to satisfy them. Now, when every candidate that ran the test got the same
exit code from it with nothing failing in sight, the test is blamed without a model call and the same
code is re-tested; with one such run, the diagnosis is told plainly that no check failed.
tests/data/silent_test_case/ holds the real outputs (the broken test rerun on attempt 3's candidates)."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, r"Z:\workspace")
os.chdir(r"Z:\workspace")
import run_langgraph_pipeline as p  # noqa: E402

calls = []


def fake_chat(label, system, blocks, want_out, min_out, **kw):
    calls.append({b["title"]: b["text"] for b in blocks})
    return "The script is wrong.\nBLAME: script", "stop"


p.llm_chat = fake_chat
p.report = lambda *a, **k: None

DATA = os.path.join(HERE, "data", "silent_test_case")
REAL = [open(os.path.join(DATA, f"c{k}.out"), encoding="utf-8").read() for k in (1, 2, 3, 5)]


def error_for(rc, out, err, role="adversarial"):
    res = subprocess.CompletedProcess([], rc, out, err)
    return (f"The script's own --test passed, but {p.TEST_LABELS[role]} (written separately) failed.\n"
            + p.run_error(res, 0.5, p.TEST_LABELS[role].capitalize(), 60))


def state(runs, role="adversarial", retests_used=0):
    """runs: one (rc, stdout, stderr) per candidate that failed the test."""
    cands = [{"k": k, "rc": 0, "status": "coded", "failed_test": role, "independent": True,
              "tests_out": {"acceptance": (0, "PASS a\nALL PASSED\n", "", 0.3), role: (rc, out, err, 0.5)}}
             for k, (rc, out, err) in enumerate(runs, 1)]
    return {"run_id": "unit-silent", "task_key": "t", "attempt": 4, "max_attempts": 16, "failed_test": role,
            "target_file": "json_max.py", "failure_kind": "indep", "goal": "parse json", "spec": "",
            "checks": ["c"], "interface": "parse_json(text) -> value", "code": "def parse_json(t): ...",
            "tests": {role: "print('test')"}, "test_feedback": {}, "retests_used": retests_used,
            "error": error_for(*runs[0], role=role), "candidates": cands, "indep_last": {}}


def diagnose(st):
    calls.clear()
    return p.diagnose_independent_failure(st)


checks = []
real = [(1, out, "") for out in REAL]

# 1. The real case: four candidates, exit code 1, 171 PASS lines each, nothing else.
checks.append(("real outputs: recognised (exit 1, 171 PASS lines, 4 candidates)",
               p.silent_test_failure(state(real), "adversarial") == (1, 171, 4)))
upd = diagnose(state(real))
fb = upd["test_feedback"].get("adversarial", "")
checks += [("real outputs: decided without a model call", calls == []),
           ("  the test is blamed and the same code re-tested", upd["retest"] and upd["indep_last"]["blame"] == "test"),
           ("  the test's writer is told what to fix", "exit 0 exactly when every check passed" in fb and "code 1" in fb)]
upd = diagnose(state(real, retests_used=p.MAX_RETESTS))
checks.append(("no re-tests left: still blamed on the test, not re-tested",
               calls == [] and not upd["retest"] and "adversarial" in upd["test_feedback"]))
checks.append(("the acceptance test is handled the same way",
               p.silent_test_failure(state(real[:2], role="acceptance"), "acceptance") == (1, 171, 2)))
summary = "PASS: a\nPASS: b\nResults: 2 passed, 0 failed\n"
checks.append(("a summary saying nothing failed doesn't count as a failure",
               p.silent_test_failure(state([(1, summary, "")] * 2), "adversarial") == (1, 2, 2)))

# 2. Anything that could be the script's fault goes to the diagnosis as before.
cases = {
    "only one candidate ran it": [real[0]],
    "a FAIL line in one run": [real[0], (1, REAL[1] + "FAIL: cli emoji expected x, got y\n", "")],
    "a traceback on stderr": [real[0], (1, REAL[1], "Traceback (most recent call last):\nValueError: x\n")],
    "a timeout": [real[0], (124, REAL[1], "")],
    "different exit codes": [real[0], (2, REAL[1], "")],
    "no PASS lines at all": [(1, "", ""), (1, "", "")],
}
for name, runs in cases.items():
    upd = diagnose(state(runs))
    checks.append((f"{name}: the model diagnoses it", len(calls) == 1 and upd["indep_last"]["blame"] == "script"))

# 3. The failure report says so plainly, for the diagnosis to read (one run, or the script's own --test).
err = error_for(*real[0])
checks += [("the report says nothing failed", "171 checks it printed passed" in err and "exit code 1" in err),
           ("  and the diagnosis sees it", "171 checks it printed passed" in (diagnose(state([real[0]])) and
                                                                             calls[0]["What happened:"]))]
checks.append(("a report with a FAIL line doesn't say it",
               "checks it printed passed" not in error_for(1, "PASS: a\nFAIL: b expected 1, got 2\n", "")))

ok = True
for name, good in checks:
    ok &= bool(good)
    print(("PASS " if good else "FAIL ") + name)
print("ALL PASS" if ok else "SOME FAILED")
