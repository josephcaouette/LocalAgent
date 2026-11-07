"""The engineer's SEARCH/REPLACE edits to the previous version (fake LLM, no sandbox):
1. A fix whose whole file doesn't fit the context window falls back to edits instead of stopping the
   run (set 2's semver run on Low stopped with "the prompt needs 9969 tokens plus at least 10288").
2. When the diagnosis blamed only the self-test's expected values, candidate 1 corrects them in place
   and the others rewrite the file (set 2's life run on Low: each rewrite brought new wrong grids).
3. When it blamed the code and some expected values ("both"), one edits call corrects the values first
   and every candidate fixes the code from that version (set 5's fmtspec runs: every rewrite kept the
   wrong values, through the same correction 5 and 13 times)."""
import os
import shutil
import sys

sys.path.insert(0, r"Z:\workspace")
os.chdir(r"Z:\workspace")
import config  # noqa: E402
import run_langgraph_pipeline as p  # noqa: E402

PREV = ("import sys\n\n\ndef bump(v):\n    return v + 2\n\n\nif __name__ == '__main__':\n"
        "    if sys.argv[1:] == ['--test']:\n        print('PASS' if bump(1) == 2 else 'FAIL: bump')\n")
REWRITE = "```python\nimport sys\n# rewritten\n\n\ndef bump(v):\n    return v + 1\n\n\nif __name__ == '__main__':\n    print('--test')\n```"
GOOD_EDIT = "<<<<<<< SEARCH\n    return v + 2\n=======\n    return v + 1\n>>>>>>> REPLACE"
BAD_EDIT = "<<<<<<< SEARCH\n    return v + 3\n=======\n    return v + 1\n>>>>>>> REPLACE"
calls, mode = [], {"too_small": True}


def fake(label, system, blocks, want_out, min_out, temperature=None, think=False, n=1, answer_min=None,
         with_reasoning=False, **kw):
    texts = {b["title"]: b["text"] for b in blocks}
    calls.append((label, think, n, texts.get("Instructions:", "")[:40], texts.get("Previous version:", ""),
                  texts.get("Note:", "")))
    if label == "Engineer":
        if mode["too_small"]:
            raise p.ContextTooSmall("the prompt needs 9969 tokens plus at least 10288 for the answer, but the "
                                    "model's context window is 16384 tokens")
        replies = [(REWRITE, "stop", "notes")] * n
    elif mode.get("bad_edit"):
        replies = [(BAD_EDIT, "stop", "notes")] * n
    else:
        replies = [(GOOD_EDIT, "stop", "notes"), (BAD_EDIT, "stop", "notes")][:n]
    return [r if with_reasoning else r[:2] for r in replies]


p.llm_complete = fake
p.report = lambda *a, **k: None
p.prewarm_containers = lambda *a, **k: None
p.write_test = lambda st, role: ""
p.write_probe = lambda st: ""
state = {"run_id": "unit-edits", "task_key": "t", "attempt": 2, "max_attempts": 3, "target_file": "f.py",
         "goal": "g", "plan": "p", "spec": "s", "interface": "bump(v)", "checks": ["c"],
         "error": "FAIL: bump", "failure_kind": "runtime", "code": PREV, "num_candidates": 2,
         "think_engineer": "retries", "diverse": False, "lvl": config.level_settings("low"), "tests": {},
         "test_checks": {}, "test_feedback": {}, "probe": "", "regression": [], "attachments": "",
         "web_brief": "", "research_brief": "", "memory_context": "", "existing_code": "", "tester": False,
         "candidates": [], "allow_network": False, "started": 0, "time_limit_s": 1}
checks = []

# 1. The whole file doesn't fit: every candidate sends edits.
cands = {c["k"]: c for c in p.engineer_node(state)["candidates"]}
checks += [
    ("too long: whole file first, then edits (both thinking)",
     [(c[0], c[1]) for c in calls] == [("Engineer", True), ("Engineer, edits", True)]),
    ("too long: the edits call says why", calls[-1][3].startswith("The file is too long")),
    ("too long: candidate 1 has the edited file", cands[1]["status"] == "coded"
     and "return v + 1" in cands[1]["code"] and "return v + 2" not in cands[1]["code"]),
    ("too long: candidate 2's unmatched edit is reported", cands[2]["status"] == "no_code"
     and "couldn't be applied" in cands[2]["error"] and "matches 0 places" in cands[2]["error"]),
]
calls.clear()
try:                                   # a first attempt (nothing to edit) still stops as before
    p.engineer_node(dict(state, attempt=1, error="", code=""))
    checks.append(("too long, no previous version: the error is raised", False))
except p.ContextTooSmall:
    checks.append(("too long, no previous version: the error is raised", True))

# 2. Only the expected values were blamed: candidate 1 edits in place, the others rewrite.
mode["too_small"] = False
calls.clear()
diag = "DIAGNOSIS:\n1. The blinker check expects the wrong grid.\nBLAME: expectation\nCORRECTION: ...\n\nRAW ERROR (tail):\nFAIL blinker"
cands = {c["k"]: c for c in p.engineer_node(dict(state, num_candidates=3, error=diag))["candidates"]}
by_label = {c[0]: c for c in calls}
checks += [
    ("expectation: one edits call for one candidate, one rewrite call for two",
     sorted((c[0], c[2]) for c in calls) == [("Engineer", 2), ("Engineer, edits", 1)]),
    ("expectation: the edits call names the expected values",
     by_label["Engineer, edits"][3].startswith("The diagnosis says the code is")),
    ("expectation: candidate 1 is the previous version with one change",
     cands[1]["code"].strip() == PREV.replace("v + 2", "v + 1").strip()),
    ("expectation: candidates 2 and 3 are rewrites", all("# rewritten" in cands[k]["code"] for k in (2, 3))),
]

# 3. The code and some expected values were both blamed: the values are corrected in place first, and
#    every candidate fixes the code from the corrected version.
calls.clear()
both = diag.replace("BLAME: expectation", "BLAME: both")
cands = {c["k"]: c for c in p.engineer_node(dict(state, num_candidates=3, error=both))["candidates"]}
checks += [
    ("both: the edits call first, then one call for all three",
     [(c[0], c[2]) for c in calls] == [("Engineer, edits", 1), ("Engineer", 3)]),
    ("both: the edits call corrects only the expected values", calls[0][3].startswith("The diagnosis blames")),
    ("both: the candidates start from the corrected version",
     "return v + 1" in calls[1][4] and "return v + 2" not in calls[1][4]),
    ("both: the note says the values are already corrected", "already corrected" in calls[1][5]),
    ("both: all three candidates are written by the engineer",
     all("# rewritten" in cands[k]["code"] for k in (1, 2, 3))),
]
calls.clear()
mode["bad_edit"] = True
p.engineer_node(dict(state, num_candidates=3, error=both))
mode["bad_edit"] = False
checks.append(("both, the correction doesn't apply: the candidates fix the previous version as it was",
               [(c[0], c[2]) for c in calls] == [("Engineer, edits", 1), ("Engineer", 3)]
               and "return v + 2" in calls[1][4] and "already corrected" not in calls[1][5]))
calls.clear()
p.engineer_node(dict(state, num_candidates=3, error=both, failure_kind="indep"))
checks.append(("both, from an independent test: no edits call (the test's writer fixes the test)",
               [(c[0], c[2]) for c in calls] == [("Engineer", 3)]))

ok = True
for name, good in checks:
    ok &= good
    print(("PASS " if good else "FAIL ") + name)
print("ALL PASS" if ok else "SOME FAILED")
shutil.rmtree(os.path.join(config.RUNS_DIR, "unit-edits"), ignore_errors=True)
