"""Cut-off candidates are finished from their own notes without thinking (fake LLM, no sandbox)."""
import os
import shutil
import sys

sys.path.insert(0, r"Z:\workspace")
os.chdir(r"Z:\workspace")
import config  # noqa: E402
import run_langgraph_pipeline as p  # noqa: E402

GOOD = ("```python\nimport sys\n\n\ndef f():\n    return 1\n\n\nif __name__ == '__main__':\n"
        "    if sys.argv[1:] == ['--test']:\n        print('PASS: f')\n```")
calls = []


def fake(label, system, blocks, want_out, min_out, temperature=None, think=False, n=1, answer_min=None,
         with_reasoning=False):
    titles = [b["title"] for b in blocks]
    approach = next((b["text"] for b in blocks if b["title"].startswith("Approach")), "")
    k = p.APPROACHES.index(approach) + 1 if approach else 0
    calls.append((think, k, any(t.startswith("Your notes") for t in titles),
                  next((b["text"][-60:] for b in blocks if b["title"].startswith("Your notes")), "")))
    if think and k in (2, 4):
        out = ("Need ensure final answer is one block...\n```python\nx = (", "length", f"plan for approach {k}")
    else:
        out = (GOOD, "stop", "notes")
    return [out if with_reasoning else out[:2]] * n


p.llm_complete = fake
p.report = lambda *a, **k: None
p.prewarm_containers = lambda *a, **k: None
p.write_test = lambda st, role: ""
p.write_probe = lambda st: ""
p.THINK_TOKENS = 16000
p.CONTEXT_TOKENS = 32768
lvl = config.level_settings("max")
state = {"run_id": "unit-finish", "task_key": "t", "attempt": 1, "max_attempts": 16, "target_file": "f.py",
         "goal": "g", "plan": "p", "spec": "s", "interface": "f()", "checks": ["c"], "error": "", "code": "",
         "num_candidates": 5, "think_engineer": "always", "diverse": True, "lvl": lvl, "tests": {},
         "test_checks": {}, "test_feedback": {}, "probe": "x", "regression": [], "attachments": "",
         "web_brief": "", "research_brief": "", "memory_context": "", "existing_code": "", "tester": False,
         "candidates": [], "allow_network": False, "started": 0, "time_limit_s": 1}
upd = p.engineer_node(state)
print("candidates:", [(c["k"], c["status"]) for c in upd["candidates"]])
print("thinking calls:", sum(1 for c in calls if c[0]), "| finishing calls:",
      [(k, "notes" if has else "NO NOTES") for think, k, has, _ in calls if not think])
print("notes end with the cut-off answer:", all("x = (" in tail for think, _k, _h, tail in calls if not think))
shutil.rmtree(os.path.join(config.RUNS_DIR, "unit-finish"), ignore_errors=True)
