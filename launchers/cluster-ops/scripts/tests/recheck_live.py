"""Node 1 (real, thinking) settles a dispute where the spec AND Node 3's script are both wrong."""
import os
import sys

sys.path.insert(0, r"Z:\workspace")
os.chdir(r"Z:\workspace")
import config  # noqa: E402
import run_langgraph_pipeline as p  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from examples_unit import GOAL, SPEC, CHECKS  # noqa: E402  (the module runs its own test on import)

p.report = lambda *a, **k: None
p.connect_llm()
p.THINK_TOKENS = config.level_settings("high")["think_tokens"]
state = {"run_id": "recheck", "goal": GOAL, "lvl": config.level_settings("high"), "task_key": "t"}
disputed = ["DISAGREE ex1: stated ['2024-01-08 00:00', '2024-01-15 00:00', '2024-01-22 00:00', '2024-01-29 00:00', "
            "'2024-02-05 00:00'], computed ['2024-01-15 00:00', '2024-04-01 00:00', '2024-04-15 00:00', "
            "'2024-07-01 00:00', '2024-07-15 00:00']"]
script = "# (Node 3's script applied AND instead of OR)\n"
spec, checks = p.recheck_examples(state, SPEC, list(CHECKS), "next_runs(expr, start, count)", disputed, script)
print("RESULT spec correction:", spec.split("CORRECTION", 1)[-1][:300] if "CORRECTION" in spec else "(none)")
print("RESULT check 1:", checks[0])
