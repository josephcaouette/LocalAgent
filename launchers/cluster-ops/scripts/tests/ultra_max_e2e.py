"""Combined window, end to end: queue Ultra -> MAX -> Low and check the 32k switching and every
new feature. Usage: python ultra_max_e2e.py smoke|bench"""
import re
import sys
import time
import tkinter as tk
from tkinter import messagebox

sys.path.insert(0, r"C:\AI\cluster_launcher")
import cluster_launcher as cl  # noqa: E402

MODE = sys.argv[1] if len(sys.argv) > 1 else "smoke"
T0 = time.time()
messagebox.askyesno = lambda *a, **k: True


def say(*a):
    print(f"[{time.time() - T0:6.0f}s]", *a, flush=True)


try:                                   # the user's own window owns this file; put it back at the end
    OLD_PID = open(cl.GUI_PID_FILE).read().strip()
except OSError:
    OLD_PID = ""
root = tk.Tk()
root.withdraw()
app = cl.ClusterWindow(root)
ag = app.agent
import config  # noqa: E402
R = config.get_redis(decode_responses=True)
EXTRA = ["--no-ingest"] + (["--no-memory"] if MODE.startswith("bench") else [])
_orig_launch = ag._launch


def launch_with_flags(job):
    job["args"] = job["args"] + [a for a in EXTRA if a not in job["args"]]
    return _orig_launch(job)


ag._launch = launch_with_flags


def pump(sec):
    end = time.time() + sec
    while time.time() < end:
        root.update()
        time.sleep(0.05)


def server_ctx():
    card = cl.vllm_card()
    return card.get("max_model_len") if card else None


def dispatch(goal, target, level):
    ag.goal_entry.delete("1.0", "end")
    ag.goal_entry.insert("1.0", goal)
    ag.target_entry.delete(0, "end")
    ag.target_entry.insert(0, target)
    ag.allow_network.set(False)
    ag.level.set(level)
    ag._on_level_change()
    ag.task_research.set(False)       # keep the comparison about the pipeline itself
    ag.start_pipeline()
    return ag.jobs[-1]


pump(4)
say("start: server context", server_ctx(), "| agent mode", ag._server_mode)
CRON = ("that parses a standard 5-field cron expression (minute, hour, day of month, month, day of week) "
        "supporting *, lists, ranges and step values, and prints the next 5 run times after a given start "
        "time. Follow standard cron rules, including how day-of-month and day-of-week combine when both "
        "are restricted. In --test mode, check several expressions against hand-computed expected times.")
if MODE == "bench":
    jobs = [dispatch("Create cron_bench_ultra.py " + CRON, "cron_bench_ultra.py", "ultra"),
            dispatch("Create cron_bench_max.py " + CRON, "cron_bench_max.py", "max")]
elif MODE == "bench-max":                  # MAX alone, e.g. after a fix
    jobs = [dispatch("Create cron_bench_max2.py " + CRON, "cron_bench_max2.py", "max")]
else:
    jobs = [dispatch("Create run_length.py with encode(s) and decode(s) for run-length encoding, e.g. 'aaabcc' "
                     "<-> '3a1b2c'. encode rejects input containing digits with ValueError; decode rejects "
                     "malformed input (such as 'a3' or '3') with ValueError. Command line: python run_length.py "
                     "encode TEXT or decode TEXT prints the result. In --test mode check round trips, empty "
                     "input, single characters, long runs (over 9) and the error cases.", "run_length.py", "ultra"),
            dispatch("Create base_convert.py with to_base(n, base) and from_base(text, base) for integer bases "
                     "2 to 36 (digits 0-9 then a-z, lowercase output, '-' for negative numbers). Invalid bases "
                     "or digits raise ValueError. Command line: python base_convert.py NUMBER FROM_BASE TO_BASE "
                     "prints the converted number. In --test mode check round trips, 0, negatives, base 36 and "
                     "the error cases.", "base_convert.py", "max"),
            dispatch("Create count_lines.py that counts non-empty lines in a text file given on the command "
                     "line. In --test mode write a small sample file to /tmp and check the count.",
                     "count_lines.py", "low")]
say("dispatched:", [(j["id"], j["level"], j["state"], j["phase"][:50]) for j in jobs])

seen_ctx, last = [], None
end = time.time() + (6 if MODE.startswith("bench") else 3) * 3600
while time.time() < end and any(j["state"] in ("QUEUED", "RUNNING") for j in jobs) or ag._switching:
    pump(5)
    snap = [(j["id"], j["level"], j["state"], j["phase"][:60]) for j in jobs] + [("mode", ag._server_mode, ag._switching)]
    if snap != last:
        ctx = server_ctx()
        say(snap, "| server ctx", ctx)
        last = snap
        for j in jobs:
            if j["state"] == "RUNNING" and not any(r == j["id"] for r, _ in seen_ctx):
                seen_ctx.append((j["id"], ctx))
    if time.time() > end:
        break
pump(10)
say("server context while each run started:", seen_ctx, "| final server ctx", server_ctx(), "| mode", ag._server_mode)
for j in jobs:
    rec = R.hgetall(config.TASK_KEY_PREFIX + j["run_id"]) if j["run_id"] else {}
    say(f"#{j['id']} {j['level']}: {j['state']} | elapsed {rec.get('elapsed_s')}s | attempt {rec.get('attempt')} | "
        f"mutation: {rec.get('mutation_score')} | regression checks: {rec.get('regression_checks')}")
    say("    timings", rec.get("timings"))
    say("    tokens ", rec.get("tokens"))
    say("    verdict", (rec.get("verdict") or "")[:250])
    for ln in j["lines"]:
        s = ln.strip()
        if re.match(r"(\[Node: (Spec|Critic|Mutation|Re-test)|-> |Candidate \d: (truncated|static|PASS|FAIL)|"
                    r"Comparing candidates|Referee|Head-to-head|Panel for|Winner|Not caught|Not proven|Not shown|"
                    r"Independent test|.*test ready|Prober|MAJOR|MINOR|\[i\]|\[!\]|\[x\]|\[\+\] PASSED)", s):
            say("      ", s[:200])
say("E2E DONE")
app._remove_pid_file()
if OLD_PID:
    with open(cl.GUI_PID_FILE, "w") as f:
        f.write(OLD_PID)
root.destroy()
