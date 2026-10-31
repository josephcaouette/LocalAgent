"""Deep diagnosis: identical failures across independent candidates can correct the spec (fake LLM)."""
import os
import sys

sys.path.insert(0, r"Z:\workspace")
os.chdir(r"Z:\workspace")
import config  # noqa: E402
import run_langgraph_pipeline as p  # noqa: E402

out = ("PASS minute-star\nFAIL dom-dow-or expected=2024-01-08 ... 2024-02-05 actual=2024-01-08 ... 2024-02-01\n"
       "FAILED 1/5\n")
seen = {}


def fake_chat(label, system, blocks, **kw):
    seen["blocks"] = "\n".join(str(b) for b in blocks)
    seen["think"] = kw.get("think")
    return ("1. dom-dow-or failed. 2. Feb 1 matches day-of-month 1 and both fields are restricted, so "
            "it's a run; the expected list is wrong.\nBLAME: expectation\n"
            "CORRECTION: for `0 0 1,15 * 1` from 2024-01-01 the fifth run is 2024-02-01T00:00:00, not 2024-02-05."), "stop"


p.llm_chat = fake_chat
p.report = lambda *a, **k: None


def state(independent, n=5, same=True):
    cands = [{"k": k, "rc": 1, "failed_test": "self", "independent": independent,
              "stdout": out if same or k == 1 else out.replace("02-01", f"03-0{k}")} for k in range(1, n + 1)]
    return {"attempt": 2, "max_attempts": 16, "judges": 5, "failure_kind": "runtime", "goal": "cron",
            "spec": "SPEC with example ... 2024-02-05", "checks": ["c1"], "code": "x = 1", "tests": {},
            "failed_test": "self", "error": "self-test failed\n" + out, "candidates": cands, "task_key": "t",
            "run_id": "t", "lvl": config.level_settings("max")}


for name, st in [("independent, all agree", state(True)), ("same base code, all agree", state(False)),
                 ("independent, all differ", state(True, same=False))]:
    upd = p.error_condenser_node(st)
    print(f"{name}: thinking={seen['think']} | note in prompt={'failed with exactly the same result' in seen['blocks']}"
          f" | spec corrected={'CORRECTION (found while testing attempt 1' in upd.get('spec', '')}"
          f" | note for engineer={'NOTE:' in upd['error']}")
low = dict(state(True), judges=1)
p.llm_chat = lambda *a, **k: ("diagnosis", "stop")
print("Low/Medium keep the quick diagnosis:", "spec" not in p.error_condenser_node(low))

# Low and Medium: a failed check without a crash gets a short thinking diagnosis; a crash doesn't.
config.HELPER_BACKEND = "node1"
calls = []
p.llm_chat = lambda label, system, blocks, **kw: (calls.append(kw), fake_chat(label, system, blocks, **kw))[1]
low = dict(state(False, n=2), judges=1, lvl=config.level_settings("low"),
           error="Self-test: exit code 1.\nLines in its output that report failures:\n"
                 "FAIL a*b*c abcc expected=False got=True\nSTDERR:\n\nSTDOUT (tail):\nFAIL 1 case(s) failed")
p.error_condenser_node(low)
crash = dict(low, error="Self-test: exit code 1.\nSTDERR:\nTraceback (most recent call last):\nKeyError: 'x'\n")
p.error_condenser_node(crash)
print("Low, failed check -> thinking diagnosis:", calls[0].get("think") is True,
      "| budget", calls[0].get("think_tokens"), "| crash -> quick diagnosis:", not calls[1].get("think"))
