"""After the last attempt, one more chance for a wrong test (fake LLM, no sandbox). When the attempts
are used up but time is left and only an independent test failed (the candidates passed their own
tests), the failure still gets a diagnosis; if it blames the test alone, the test is fixed and the
same code re-tested once. Set 4's expression evaluator on MAX ended on its 16th attempt with four
candidates that had passed their own tests failing only an acceptance test whose generator wrote
expressions Python itself rejects."""
import os
import sys
import time

sys.path.insert(0, r"Z:\workspace")
os.chdir(r"Z:\workspace")
import run_langgraph_pipeline as p  # noqa: E402

p.report = lambda *a, **k: None
calls, reply = [], {"text": ""}


def fake_chat(label, system, blocks, want_out, min_out, **kw):
    calls.append(label)
    return reply["text"], "stop"


p.llm_chat = fake_chat
FAIL = "FAIL: random 28 ((4 - not 4) ^ True) expected 'eval no exception', got 'SyntaxError: invalid syntax'"


def state(**kw):
    cands = [{"k": k, "rc": 0, "status": "coded", "failed_test": "acceptance", "independent": False,
              "tests_out": {"acceptance": (1, f"PASS: a\n{FAIL}\n", "", 0.5)}} for k in (1, 2)]
    st = {"run_id": "unit-lastchance", "task_key": "t", "attempt": 17, "max_attempts": 16,
          "started": time.time(), "time_limit_s": 3600, "status": "FAILED", "failure_kind": "indep",
          "failed_test": "acceptance", "last_chance_used": False, "retests_used": 0, "retest": False,
          "target_file": "pyexpr_max.py", "goal": "evaluate expressions", "spec": "", "checks": ["c"],
          "interface": "evaluate(expr)", "code": "def evaluate(e): ...", "judges": 3,
          "tests": {"acceptance": "print('test')"}, "test_feedback": {}, "candidates": cands,
          "indep_last": {}, "error": "The independent acceptance test failed:\n" + FAIL}
    st.update(kw)
    return st


checks = []
# Routing after the executor.
checks += [
    ("last attempt, only the acceptance test failed: diagnose once more",
     p.route_after_executor(state()) == "condenser"),
    ("attempts left: diagnose as always", p.route_after_executor(state(attempt=5)) == "condenser"),
    ("time is up: finish", p.route_after_executor(state(started=time.time() - 7200)) == "finalize"),
    ("the candidates' own test failed: finish", p.route_after_executor(state(failure_kind="runtime")) == "finalize"),
    ("the last chance was used: finish", p.route_after_executor(state(last_chance_used=True)) == "finalize"),
    ("no re-tests left: finish", p.route_after_executor(state(retests_used=p.MAX_RETESTS)) == "finalize"),
    ("a pass still goes to the verifier", p.route_after_executor(state(status="EXECUTED")) == "verifier"),
]

# The diagnosis blames the test: it is fixed and the same code re-tested.
reply["text"] = "The test's generator makes expressions Python rejects; the script is fine.\nBLAME: test"
st = state()
upd = p.error_condenser_node(st)
st.update(upd)
checks += [
    ("blamed on the test: one model call", calls == ["Condenser"]),
    ("  the last chance is spent", upd.get("last_chance_used") is True),
    ("  re-test the same code", upd.get("retest") is True and p.route_after_condenser(st) == "retest"),
    ("  a failed re-test then finishes", p.route_after_retest(dict(st, status="FAILED", attempt=18)) == "finalize"),
    ("  and no further last chance", p.route_after_executor(dict(st, status="FAILED", attempt=18)) == "finalize"),
]

# The diagnosis blames the script (or both): no attempts left for new code, so finish.
for text, label in (("The script accepts 4 - not 4.\nBLAME: script", "on the script"),
                    ("Both are wrong.\nBLAME: both", "on both")):
    calls.clear()
    reply["text"] = text
    st = state()
    upd = p.error_condenser_node(st)
    st.update(upd)
    checks.append((f"blamed {label}: finish without a new attempt",
                   upd.get("last_chance_used") is True and not upd.get("retest")
                   and p.route_after_condenser(st) == "finalize"))

# With attempts left, the condenser behaves as before.
calls.clear()
reply["text"] = "The script is wrong.\nBLAME: script"
st = state(attempt=5)
upd = p.error_condenser_node(st)
st.update(upd)
checks.append(("attempts left: no last-chance mark, on to the engineer",
               "last_chance_used" not in upd and p.route_after_condenser(st) == "engineer"))
checks.append(("the graph builds with the new edge", p.build_graph() is not None))

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(("PASS " if ok else "FAIL ") + name)
print("ALL PASS" if not failed else f"{len(failed)} FAILED")
sys.exit(1 if failed else 0)
