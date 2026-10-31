"""Safety net: a step that fails after a pass keeps the passing version (no LLM, no sandbox)."""
import os
import sys
import time
from typing import TypedDict

sys.path.insert(0, r"Z:\workspace")
os.chdir(r"Z:\workspace")
from langgraph.graph import StateGraph, END  # noqa: E402
import run_langgraph_pipeline as p  # noqa: E402

# 1. LangGraph: after a node raises, the loop variable holds the state from before that node.
class S(TypedDict):
    status: str
    n: int

def ok(s):
    return {"status": "PASSED", "n": s["n"] + 1}

def boom(s):
    raise p.InfraError("ssh timed out")

g = StateGraph(S)
g.add_node("ok", ok)
g.add_node("boom", boom)
g.set_entry_point("ok")
g.add_edge("ok", "boom")
g.add_edge("boom", END)
latest = {"status": "INIT", "n": 0}
try:
    for latest in g.compile().stream({"status": "INIT", "n": 0}, stream_mode="values"):
        pass
except p.InfraError as e:
    print("1. stream: caught", type(e).__name__, "| latest =", latest)

# 2. keep_passed_version with the saving steps stubbed out.
saved = []
p.promote = lambda st: (os.path.join("Z:/workspace", st["target_file"]), "")
p.save_result_file = lambda st: saved.append(st["code"]) or "result.py"
p.report = lambda st, **kw: saved.append(("report", kw.get("status"), kw.get("verdict", "")[-60:]))
p.NO_INGEST = True
base = {"run_id": "t", "task_key": "k", "target_file": "x.py", "goal": "g", "checks": [], "regression": [],
        "started": time.time(), "time_limit_s": 99, "max_attempts": 3, "error": "", "execution_stderr": "",
        "execution_output": "out", "winner": 2, "attempt": 3}
best = {"attempt": 1, "winner": 1, "code": "OLD", "verdict": "PASS v1", "execution_output": "o",
        "execution_stderr": ""}
cases = [("passed now", dict(base, status="PASSED", code="NEW", verdict="PASS v2", best_passed=best)),
         ("passed earlier", dict(base, status="CODED", code="BROKEN", verdict="", best_passed=best)),
         ("never passed", dict(base, status="FAILED", code="BAD", verdict="", best_passed={}))]
for name, st in cases:
    p._FINALIZE_STARTED.clear()
    saved.clear()
    kept = p.keep_passed_version(st, p.LLMError("timed out after 1200 s"))
    print(f"2. {name}: kept={kept} | saved={saved}")
p._FINALIZE_STARTED.set()          # a failure while saving must not try to save again
print("3. failure inside finalize: kept =", p.keep_passed_version(cases[0][1], RuntimeError("disk full")))
