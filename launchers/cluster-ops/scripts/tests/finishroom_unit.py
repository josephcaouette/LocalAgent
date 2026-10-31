"""Finishing a cut-off candidate from its notes when room is tight (fake LLM, no sandbox). Set 2's
semver run on Medium stopped with "the prompt needs 8625 tokens plus at least 8192 for the answer":
the finishing call asked for the file plus half again, and the notes had taken that room. It now asks
for at least the file's own size, and a finish that still can't fit leaves just that candidate cut off."""
import os
import shutil
import sys

sys.path.insert(0, r"Z:\workspace")
os.chdir(r"Z:\workspace")
import config  # noqa: E402
import run_langgraph_pipeline as p  # noqa: E402

BODY = "".join(f"    total += {i}  # step {i} of the running sum, kept long on purpose\n" for i in range(45))
PREV = ("import sys\n\n\ndef bump(v):\n    total = 0\n" + BODY + "    return v + 2\n\n\nif __name__ == '__main__':\n"
        "    if sys.argv[1:] == ['--test']:\n        print('PASS' if bump(1) == 2 else 'FAIL: bump')\n")
GOOD = "```python\nimport sys\n\n\ndef bump(v):\n    return v + 1\n\n\nif __name__ == '__main__':\n    print('--test')\n```"
calls, mode = [], {"finish": "tight"}
FILE_MIN = max(1200, len(PREV) // 3 + 300)


def fake(label, system, blocks, want_out, min_out, temperature=None, think=False, n=1, answer_min=None,
         with_reasoning=False, **kw):
    calls.append((think, min_out))
    if think:                                           # candidate 1 runs out of room; candidate 2 is fine
        replies = [("```python\nimport sys\ndef bump(", "length", "my plan"), (GOOD, "stop", "notes")][:n]
    elif mode["finish"] == "never" or min_out > FILE_MIN:
        raise p.ContextTooSmall(f"the prompt needs 8625 tokens plus at least {min_out} for the answer")
    else:
        replies = [(GOOD, "stop", "")]
    return [r if with_reasoning else r[:2] for r in replies]


p.llm_complete = fake
p.report = lambda *a, **k: None
p.prewarm_containers = lambda *a, **k: None
p.write_test = lambda st, role: ""
p.write_probe = lambda st: ""
state = {"run_id": "unit-finishroom", "task_key": "t", "attempt": 2, "max_attempts": 3, "target_file": "f.py",
         "goal": "g", "plan": "p", "spec": "", "interface": "bump(v)", "checks": ["c"],
         "error": "DIAGNOSIS:\nbump adds 2\nBLAME: code", "failure_kind": "runtime", "code": PREV,
         "num_candidates": 2, "think_engineer": "retries", "diverse": False, "lvl": config.level_settings("medium"),
         "tests": {}, "test_checks": {}, "test_feedback": {}, "probe": "", "regression": [], "attachments": "",
         "web_brief": "", "research_brief": "", "memory_context": "", "existing_code": "", "tester": False,
         "candidates": [], "allow_network": False, "started": 0, "time_limit_s": 1}
checks = []

# 1. Tight room: the finish asks for the file's own size, which fits, so candidate 1 is finished.
cands = {c["k"]: c for c in p.engineer_node(state)["candidates"]}
finish_mins = [m for think, m in calls if not think]
checks += [("tight: one finishing call, asking for the file's own size", finish_mins == [FILE_MIN]),
           ("tight: both candidates have code", [cands[k]["status"] for k in (1, 2)] == ["coded", "coded"])]

# 2. No room at all: the run goes on; candidate 1 stays cut off and candidate 2 is kept.
mode["finish"] = "never"
calls.clear()
try:
    cands = {c["k"]: c for c in p.engineer_node(state)["candidates"]}
    checks += [("no room: the run goes on", True),
               ("no room: candidate 1 cut off, candidate 2 kept",
                [cands[k]["status"] for k in (1, 2)] == ["truncated", "coded"])]
except p.ContextTooSmall:
    checks += [("no room: the run goes on", False)]

ok = True
for name, good in checks:
    ok &= bool(good)
    print(("PASS " if good else "FAIL ") + name)
print("ALL PASS" if ok else "SOME FAILED")
shutil.rmtree(os.path.join(config.RUNS_DIR, "unit-finishroom"), ignore_errors=True)
