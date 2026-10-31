"""Any thinking call that gets cut off answers again from its notes; a non-script candidate is
rejected (fake LLM)."""
import os
import sys

sys.path.insert(0, r"Z:\workspace")
os.chdir(r"Z:\workspace")
import config  # noqa: E402
import run_langgraph_pipeline as p  # noqa: E402

calls = []


def fake_complete(label, system, blocks, want_out, min_out, temperature=None, think=False, n=1,
                  answer_min=None, with_reasoning=False, think_tokens=None):
    calls.append((think, [b["title"] for b in blocks]))
    if think:
        out = ('3. stdout contains no FAIL... Need 2-4 checks. Could add', "length", "thinking about the plan")
    else:
        out = ('{"steps": ["a"], "checks": ["c1", "c2"]}', "stop", "")
    return [out if with_reasoning else out[:2]] * n


p.llm_complete = fake_complete
p.THINK_TOKENS = 5000
blocks = [p.block("Goal:", "g"), p.block("Instructions:", "Return JSON")]
text, finish = p.llm_chat("Planner", "sys", blocks, want_out=1000, min_out=300, think=True)
print("answer after spill:", text, "| finish:", finish)
print("retry without thinking, notes before the instructions:",
      calls[1][0] is False and calls[1][1][-2].startswith("Your notes") and calls[1][1][-1] == "Instructions:")
calls.clear()
p.llm_complete = lambda *a, **k: [("ok", "stop", "") if k.get("with_reasoning") else ("ok", "stop")]
print("normal answers untouched:", p.llm_chat("Judge", "sys", blocks, 400, 150, think=True) == ("ok", "stop"))

# a candidate that is a plan, not a script
p.llm_complete = lambda *a, **k: [('```python\n{"steps": ["parse"], "checks": ["x"]}\n```', "stop", "")] * k.get("n", 1)
p.report = p.prewarm_containers = lambda *a, **k: None
p.write_test = lambda st, role: ""
p.write_probe = lambda st: ""
state = {"run_id": "unit-spill", "task_key": "t", "attempt": 1, "max_attempts": 3, "target_file": "f.py",
         "goal": "g", "plan": "p", "spec": "", "interface": "", "checks": ["c"], "error": "", "code": "",
         "num_candidates": 2, "think_engineer": "retries", "diverse": False, "lvl": config.level_settings("low"),
         "tests": {}, "test_checks": {}, "test_feedback": {}, "probe": "", "regression": [], "attachments": "",
         "web_brief": "", "research_brief": "", "memory_context": "", "existing_code": "", "tester": False,
         "candidates": [], "allow_network": False, "started": 0, "time_limit_s": 1}
upd = p.engineer_node(state)
print("plan-as-code rejected:", [c["status"] for c in upd.get("candidates", [])] or upd.get("status"),
      "|", (upd.get("error") or "")[:90])
import shutil  # noqa: E402
shutil.rmtree(os.path.join(config.RUNS_DIR, "unit-spill"), ignore_errors=True)
