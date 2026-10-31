"""An independent test that keeps failing the same way after the diagnosis blamed the script (fake LLM,
no sandbox). Set 2's csv run on High blamed the script nine times while every candidate kept the same
reading of an ambiguous goal, which the reference agreed with, and the run ended FAILED with a correct
file. The diagnosis is now told the candidates won't change, and either blames the test or puts a
CORRECTION in the interface the engineer implements exactly."""
import os
import sys

sys.path.insert(0, r"Z:\workspace")
os.chdir(r"Z:\workspace")
import run_langgraph_pipeline as p  # noqa: E402

asks, reply = [], {"text": ""}


def fake_chat(label, system, blocks, want_out, min_out, temperature=None, think=False, think_tokens=None):
    asks.append(next(b["text"] for b in blocks if b["title"] == "Instructions:"))
    return reply["text"], "stop"


p.llm_chat = fake_chat
p.report = lambda *a, **k: None

OUT = ("PASS quoted_fields\nFAIL: lone_lf_at_end expected [], got [[]]\n"
       "FAIL: two_lf expected [[]], got [[], []]\nTraceback (most recent call last):\nFAILED (failures=2)\n")
OTHER = "FAIL: quoted_comma expected [['a', 'b']], got [['a,b']]\n"


def state(out=OUT, last=None, spec=""):
    cands = [{"k": k, "rc": 0, "failed_test": "acceptance", "independent": False,
              "tests_out": {"acceptance": (1, out, "", 0.4)}} for k in (1, 2)]
    return {"run_id": "unit-stuck", "task_key": "t", "attempt": 4, "max_attempts": 10, "failed_test": "acceptance",
            "target_file": "csv_high.py",
            "failure_kind": "indep", "goal": "parse csv", "spec": spec, "checks": ["c"],
            "interface": "parse_csv(text) -> list of lists", "code": "def parse_csv(t): ...",
            "tests": {"acceptance": "print('test')"}, "test_feedback": {}, "retests_used": 0,
            "error": "The independent acceptance test: exit code 1.\nLines in its output that report failures:\n" + out,
            "candidates": cands, "indep_last": last or {}}


def run(st, text):
    asks.clear()
    reply["text"] = text
    return p.diagnose_independent_failure(st), asks[-1]


checks = []
FAILS = ["FAIL: lone_lf_at_end expected [], got [[]]", "FAIL: two_lf expected [[]], got [[], []]"]
blamed_script = {"role": "acceptance", "fails": FAILS, "blame": "script", "attempt": 3}

# 1. The first failure: no note; the specific failure lines are remembered, without the generic ones.
upd, ask = run(state(), "The script is wrong.\nBLAME: script")
checks += [("first failure: no stuck note", "candidates written after it" not in ask),
           ("first failure: remembers the specific lines only", upd["indep_last"]["fails"] == FAILS),
           ("first failure: remembers the blame and attempt",
            (upd["indep_last"]["blame"], upd["indep_last"]["attempt"]) == ("script", 3))]

# 2. The same lines after a script blame: the note names them; blaming the test re-tests the same code.
upd, ask = run(state(last=blamed_script), "Both readings fit; the test is wrong.\nBLAME: test")
checks += [("stuck: the note is in the instructions",
            "candidates written after it" in ask and "attempt 3" in ask and FAILS[0] in ask),
           ("stuck, test blamed: re-test with feedback, interface unchanged",
            upd["retest"] and "acceptance" in upd["test_feedback"] and "interface" not in upd)]

# 3. Still the script, with a CORRECTION: it goes into the interface (and the spec, when there is one).
upd, _ = run(state(last=blamed_script, spec="Spec text."),
             "The goal rules it out.\nBLAME: script\nCORRECTION: a lone final line break gives no record.")
checks += [("stuck, script blamed: the correction is added to the interface",
            upd.get("interface", "").startswith("parse_csv(text)")
            and upd["interface"].endswith("a lone final line break gives no record.")),
           ("stuck, script blamed: and to the spec", upd.get("spec", "").endswith("gives no record.")),
           ("stuck, script blamed: no re-test", not upd["retest"])]

# 4. No note after a test blame, after different failures, or for a CORRECTION when not stuck.
_, ask = run(state(last=dict(blamed_script, blame="test")), "BLAME: script")
checks.append(("after a test blame: no note", "candidates written after it" not in ask))
_, ask = run(state(out=OTHER, last=blamed_script), "BLAME: script")
checks.append(("different failures: no note", "candidates written after it" not in ask))
upd, _ = run(state(), "BLAME: script\nCORRECTION: something")
checks.append(("not stuck: a CORRECTION changes nothing", "interface" not in upd and "spec" not in upd))

# 5. The lines come from the test's own output, not the pipeline's header ("report failures").
checks.append(("the pipeline's header isn't a failure line",
               not any("report failures" in ln for ln in p.indep_fail_lines(state(), "acceptance"))))

ok = True
for name, good in checks:
    ok &= bool(good)
    print(("PASS " if good else "FAIL ") + name)
print("ALL PASS" if ok else "SOME FAILED")
