"""A tester's typo gets one quick repair instead of costing an attempt (fake LLM)."""
import os
import sys

sys.path.insert(0, r"Z:\workspace")
os.chdir(r"Z:\workspace")
import config  # noqa: E402
import run_langgraph_pipeline as p  # noqa: E402

BAD = "```python\ntry:\n    target.f()\nexcept Exception:\n    print('FAIL:', ex)\nprint('PASS: f')\n```"
GOOD = BAD.replace("print('FAIL:', ex)", "print('FAIL: f raised')")
replies, seen = [BAD, GOOD], []


def fake_chat(label, system, blocks, want_out, min_out, temperature=None, think=False):
    seen.append((think, [b["text"] for b in blocks if b["title"] == "Problem:"]))
    return replies[len(seen) - 1], "stop"


p.llm_chat = fake_chat
state = {"target_file": "f.py", "goal": "g", "spec": "", "checks": ["c"], "interface": "f()", "tests": {},
         "test_feedback": {}, "test_checks": {}, "lvl": config.level_settings("high"), "allow_network": False}
full = p.write_test(state, "acceptance")
print("repaired test kept:", bool(full) and "FAIL: f raised" in full, "| calls:", len(seen),
      "| repair asked without thinking:", seen[1][0] is False, "|", seen[1][1][0][:80])
replies[1] = BAD
seen.clear()
print("still broken -> skipped:", p.write_test(state, "acceptance") == "")
