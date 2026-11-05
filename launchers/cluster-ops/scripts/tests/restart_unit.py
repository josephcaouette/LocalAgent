"""A dead end gets a fresh start (fake LLM and sandbox). Fixes inherit their version's design: in set 4's
second battery the expression evaluator on MAX spent its last 10 attempts fixing one parser that
rejected every valid expression. After RESTART_AFTER attempts in a row whose best candidate got less
far than the best of their line of fixes, the next attempt writes fresh candidates from the goal and
spec, told what the dead end was, instead of fixing that version again (at most MAX_RESTARTS per run).
1. The count (dead_end). 2. Through the executor. 3. The engineer's fresh start."""
import os
import sys

sys.path.insert(0, r"Z:\workspace")
os.chdir(r"Z:\workspace")
import config  # noqa: E402
import run_langgraph_pipeline as p  # noqa: E402

p.report = lambda *a, **k: None
checks = []


def cand(k, rc, passes, fails, error="FAIL: x", code="code"):
    out = "".join(f"PASS c{i}\n" for i in range(passes)) + "".join(f"FAIL d{i}\n" for i in range(fails))
    return {"k": k, "rc": rc, "stdout": out, "stderr": "", "tests_out": {}, "code": code, "exec_ok": False,
            "exec_error": error, "failed_test": "", "indep_failed": False, "indep_stdout": "", "elapsed": 0.5}


# --- 1. The count -----------------------------------------------------------------------------------
st = {"attempt": 6, "line_best": [], "stall": 0, "restarts": 0}
seq = [("own test passed", [cand(1, 0, 9, 0)]),          # attempt 6: the best of the line so far
       ("worse", [cand(1, 1, 5, 5), cand(2, 1, 1, 9)]),  # 7
       ("worse", [cand(1, 1, 9, 1)]),                    # 8
       ("worse", [cand(1, 1, 2, 8, error="ValueError: invalid expression on 1 + 2 * 3")])]  # 9
seen = []
for i, (_what, results) in enumerate(seq):
    upd = p.dead_end(dict(st, attempt=6 + i), results, results[0])
    seen.append((upd.get("stall"), bool(upd.get("restart_note"))))
    st.update(upd)
checks += [
    ("three attempts in a row less far than the line's best: the next one starts over",
     seen == [(0, False), (1, False), (2, False), (0, True)]),
    ("  the note says why and shows the last failure", "dead end" in st["restart_note"]
     and "ValueError: invalid expression on 1 + 2 * 3" in st["restart_note"]),
    ("  one restart counted, and the line starts again", st["restarts"] == 1 and st["line_best"] == []),
]
st2 = {"attempt": 3, "line_best": [True, 0, 1.0], "stall": 2, "restarts": 0}
checks += [
    ("an attempt as far as the line's best is progress (the count starts over)",
     p.dead_end(st2, [cand(1, 0, 4, 0)], None) == {"stall": 0, "line_best": [True, 0, 1.0]}),
    ("an attempt further than it raises the line's best", p.dead_end(
        dict(st2, line_best=[False, 0, 0.5]), [cand(1, 0, 3, 0)], None)["line_best"] == [True, 0, 1.0]),
    ("after the last restart allowed, the count goes on but nothing restarts",
     p.dead_end(dict(st2, restarts=p.MAX_RESTARTS), [cand(1, 1, 0, 3)], cand(1, 1, 0, 3))
     == {"stall": 3, "line_best": [True, 0, 1.0]}),
]

# --- 2. Through the executor ------------------------------------------------------------------------
p.discard_containers = lambda *a, **k: None
runs = {}
p.run_candidate = lambda state, c: runs[c["k"]]
base = {"run_id": "unit-restart", "task_key": "t", "attempt": 9, "max_attempts": 16, "target_file": "t.py",
        "candidates": [{"k": 1, "status": "coded", "code": "a"}, {"k": 2, "status": "coded", "code": "b"}],
        "allow_network": False, "lvl": config.level_settings("max"), "tests": {}, "regression": [],
        "repeat_tests": 1, "probe": "", "probe_verdicts": {}, "furthest": {}, "tester": True,
        "line_best": [True, 0, 1.0], "stall": 2, "restarts": 0, "best_passed": {}}
runs.update({1: cand(1, 1, 1, 4, code="a"), 2: cand(2, 1, 3, 3, error="ValueError: invalid", code="b")})
upd = p.sandbox_executor_node(base)
checks.append(("executor: the third attempt without progress sets up a fresh start",
               upd["status"] == "FAILED" and upd["restarts"] == 1 and "ValueError: invalid" in upd["restart_note"]))
runs[2] = dict(cand(2, 0, 5, 0, code="b"), exec_ok=True)
upd = p.sandbox_executor_node(base)
checks.append(("executor: a candidate that passes ends the count", upd["status"] == "EXECUTED" and upd["stall"] == 0))

# --- 3. The engineer's fresh start ------------------------------------------------------------------
calls = []


def fake(label, system, blocks, want_out, min_out, temperature=None, think=False, n=1, answer_min=None,
         with_reasoning=False, **kw):
    calls.append({"label": label, "think": think, "titles": [b["title"] for b in blocks if b["text"].strip()],
                  "note": next((b["text"] for b in blocks if b["title"] == "Earlier attempts:"), "")})
    reply = mode["reply"]
    return [(reply, "stop", "") if with_reasoning else (reply, "stop")] * n


GOOD = "```python\nimport sys\n\n\ndef f():\n    return 1\n\n\nif __name__ == '__main__':\n    print('--test')\n```"
mode = {"reply": GOOD}
p.llm_complete = fake
p.prewarm_containers = lambda *a, **k: None
p.write_test = lambda st, role: ""
p.write_probe = lambda st: ""
eng = {"run_id": "unit-restart", "task_key": "t", "attempt": 10, "max_attempts": 16, "target_file": "t.py",
       "goal": "g", "plan": "p", "spec": "s", "interface": "f()", "checks": ["c"], "num_candidates": 3,
       "error": "FAIL: old line's failure\nBLAME: code", "failure_kind": "runtime", "code": "OLD = 1\n",
       "think_engineer": "retries", "diverse": True, "lvl": config.level_settings("medium"), "tests": {},
       "test_checks": {}, "test_feedback": {}, "probe": "", "regression": [], "attachments": "", "web_brief": "",
       "research_brief": "", "memory_context": "", "existing_code": "", "tester": False, "candidates": [],
       "allow_network": False, "started": 0, "time_limit_s": 1,
       "restart_note": "The code of the earlier attempts is set aside ... ValueError: invalid"}
out = p.engineer_node(eng)
first = calls[0]
checks += [
    ("engineer: a fresh start writes new files, with different approaches",
     out["status"] == "CODED" and len(calls) == 3 and all("Approach for this version:" in c["titles"] for c in calls)),
    ("  it isn't shown the old version or asked to fix it", "Previous version:" not in first["titles"]
     and not any(t.startswith("The previous attempt failed") for t in first["titles"])),
    ("  it is told why, and thinks first (on a level that thinks on retries)",
     "ValueError: invalid" in first["note"] and first["think"] is True),
    ("  the note is used once", out["restart_note"] == ""),
]
calls.clear()
mode["reply"] = "no code at all"
out = p.engineer_node(eng)
checks.append(("engineer: a fresh start with nothing testable keeps the note for the next attempt",
               out["status"] == "FAILED" and out["restart_note"] == eng["restart_note"]))
calls.clear()
mode["reply"] = GOOD
out = p.engineer_node(dict(eng, restart_note=""))
checks.append(("engineer: without a note, a failure is fixed as before",
               "Previous version:" in calls[0]["titles"] and not calls[0]["note"]))

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(("PASS " if ok else "FAIL ") + name)
print("ALL PASS" if not failed else f"{len(failed)} FAILED")
sys.exit(1 if failed else 0)
