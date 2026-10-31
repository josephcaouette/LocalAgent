"""Example checker on a plan with one wrong example (real sandbox; Node 1 faked).
Part 1 fakes Node 3 (a crashing script, then a fixed one) so the repair path is tested
deterministically; part 2 asks the real Node 3 and reports what happened (its output varies)."""
import os
import sys

sys.path.insert(0, r"Z:\workspace")
os.chdir(r"Z:\workspace")
import config  # noqa: E402
import run_langgraph_pipeline as p  # noqa: E402

GOAL = ("Create next_runs.py with next_runs(expr, start, count) for standard 5-field cron expressions "
        "(minute hour day-of-month month day-of-week; *, lists, ranges, steps). When both day-of-month and "
        "day-of-week are restricted, a day matches if EITHER matches (Vixie cron).")
SPEC = ("Rules: standard cron; dow 0 or 7 = Sunday, 1 = Monday; results are strictly after start.\n"
        "Examples: next_runs('0 0 1,15 * 1', 2024-01-01 00:00, 5) -> 2024-01-08 00:00, 2024-01-15 00:00, "
        "2024-01-22 00:00, 2024-01-29 00:00, 2024-02-05 00:00.\n"      # wrong: the 5th is 2024-02-01
        "next_runs('30 9 * * *', 2024-03-10 10:00, 2) -> 2024-03-11 09:30, 2024-03-12 09:30.")  # right
CHECKS = ["--test prints PASS for '0 0 1,15 * 1' from 2024-01-01 00:00 with fifth run 2024-02-05 00:00",
          "--test prints PASS for '30 9 * * *' from 2024-03-10 10:00 -> 2024-03-11 09:30, 2024-03-12 09:30"]

GOOD_SCRIPT = """
from datetime import datetime, timedelta
def runs(start, n):
    t, out = start + timedelta(minutes=1), []
    while len(out) < n:
        if t.minute == 0 and t.hour == 0 and (t.day in (1, 15) or t.isoweekday() == 1):
            out.append(t.strftime('%Y-%m-%d %H:%M'))
        t += timedelta(minutes=1)
    return out
stated = ['2024-01-08 00:00', '2024-01-15 00:00', '2024-01-22 00:00', '2024-01-29 00:00', '2024-02-05 00:00']
got = runs(datetime(2024, 1, 1), 5)
print('AGREE ex1' if got == stated else f'DISAGREE ex1: stated {stated}, computed {got}')
print('AGREE ex2')
"""

if __name__ == "__main__":
    seen = {}

    def fake_chat(label, system, blocks, **kw):
        seen["disputed"] = next(b["text"] for b in blocks if b["title"].startswith("Disputed"))
        return ('{"verdicts": [{"example": "0 0 1,15 * 1 fifth run", "stated_is_right": false, '
                '"correct": "2024-02-01 00:00 (day-of-month 1 matches)", "reason": "OR rule"}], '
                '"checks": ["--test prints PASS for \'0 0 1,15 * 1\' from 2024-01-01 00:00 with fifth run 2024-02-01 00:00", '
                f'"{CHECKS[1]}"]}}'), "stop"

    real_chat = p.llm_chat
    replies = ["```python\nprint(int('*'))\n```", "```python" + GOOD_SCRIPT + "```"]
    asked = []

    def fake_chat2(label, system, blocks, **kw):
        if label == "Example checker":            # Node 1 writing the checking script
            asked.append(blocks[0]["text"])
            return replies[len(asked) - 1], "stop"
        return fake_chat(label, system, blocks, **kw)

    p.llm_chat = fake_chat2
    p.report = lambda *a, **k: None
    state = {"run_id": p.new_run_id(), "goal": GOAL, "allow_network": False,
             "lvl": config.level_settings("high"), "task_key": "t"}
    spec, checks = p.check_examples(state, SPEC, list(CHECKS), "next_runs(expr, start, count)")
    print("PART 1 repair asked with the traceback:", len(asked) == 2 and "ValueError" in asked[1],
          "| spec corrected:", "2024-02-01" in spec.split("CORRECTION")[-1] if "CORRECTION" in spec else False,
          "| check 1 fixed:", "2024-02-01" in checks[0], "| check 2 unchanged:", checks[1] == CHECKS[1])

    p.llm_chat = real_chat
    p.connect_llm()
    p.THINK_TOKENS = config.level_settings("high")["think_tokens"]
    seen.clear()
    state["run_id"] = p.new_run_id()
    spec, checks = p.check_examples(state, SPEC, list(CHECKS), "next_runs(expr, start, count)")
    outcome = ("corrected" if "CORRECTION" in spec else
               "disputed but confirmed" if seen.get("disputed") else "no dispute or skipped")
    print("PART 2 (live, Node 1 writes and decides):", outcome, "| disputed:", seen.get("disputed", "-")[:120])
    p._cleanup_pool.shutdown(wait=True)
    left = p.run_ssh(f"docker ps -a --filter name=agent-{state['run_id']} --format '{{{{.Names}}}}'", 30).stdout.strip()
    print("containers left:", left or "none")
