"""Test battery: five non-cron tasks queued through a hidden Agent Cluster window at several
accuracy levels, then each result is checked against a reference in the sandbox.

Usage: python battery.py [full|quick] [set1|set2]   (quick = Low only; set2 = the second task set)
Results: battery_results_<set>.json next to this file, and a table at the end of the output.
The produced files land in Z:\\workspace as <task>_<level>.py: delete them afterwards.
"""
import json
import os
import subprocess
import sys
import time
import tkinter as tk
from tkinter import messagebox

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, r"C:\AI\cluster_launcher")
import cluster_launcher as cl  # noqa: E402

MODE = sys.argv[1] if len(sys.argv) > 1 else "full"
T0 = time.time()
messagebox.askyesno = lambda *a, **k: True

GOALS = {
    "glob": (
        "Create a Python module with match(pattern, text) -> bool for shell-style wildcard matching, without "
        "using the fnmatch, glob or re modules. Rules: * matches any sequence of characters (including none); "
        "? matches exactly one character; [abc] matches one of the listed characters and [a-c] a range; "
        "[!abc] matches one character that is NOT listed; inside brackets every character is literal (so [*] "
        "matches '*'), and a ']' right after '[' or '[!' is a literal member of the set; a '[' with no closing "
        "']' matches a literal '['. The whole text must match, case-sensitively. Command line: python <script> "
        "PATTERN TEXT prints True or False. In --test mode check typical and tricky patterns."),
    "bowling": (
        "Create a Python module with score(rolls) -> int for a complete game of ten-pin bowling, where rolls "
        "is the list of pins knocked down by each roll in order. Standard scoring: a strike (all 10 pins on the "
        "first roll of a frame) scores 10 plus the next two rolls; a spare (all 10 pins in two rolls) scores 10 "
        "plus the next roll; the tenth frame has one bonus roll after a spare or two after a strike (so 2 or 3 "
        "rolls). Raise ValueError for an invalid game: a roll below 0 or above 10; two rolls in a frame "
        "totalling more than 10 (in the tenth frame, the two bonus rolls after a strike may total more than 10 "
        "only when the first of them is a strike); an incomplete game; or extra rolls after the game is over. "
        "Command line: python <script> ROLL ROLL ... prints the score. In --test mode check a perfect game "
        "(300), all spares, a gutter game and the error cases."),
    "calc": (
        "Create a Python module with evaluate(expr) -> int that evaluates integer arithmetic, without eval, "
        "exec, ast or compile. Supported: non-negative integer literals, + - * /, parentheses and unary minus, "
        "with the usual precedence (* and / before + and -, left to right). Unary minus binds tighter than * "
        "and / and may repeat (--3 is 3, 2*-3 is -6, -(1+2) is -3); there is no unary plus. / is integer "
        "division that truncates toward zero (7/2 is 3, -7/2 is -3). Spaces are allowed between tokens. Raise "
        "ZeroDivisionError for division by zero and ValueError for anything malformed: empty input, unknown "
        "characters (including '.'), unbalanced parentheses, missing operands such as '2+' or '*2', and two "
        "numbers or a number and '(' next to each other ('3 4', '2(3)'). Command line: python <script> \"EXPR\" "
        "prints the result. In --test mode check precedence, unary minus, truncation and the error cases."),
    "topo": (
        "Create a Python module with order(deps) -> list. deps is a dict mapping each task name (a string) to "
        "the list of tasks it depends on; a task that appears only in someone's dependency list is a task with "
        "no dependencies. Return every task exactly once, each after all of its dependencies; whenever several "
        "tasks are ready, take the alphabetically smallest first, so the result is unique. If the dependencies "
        "contain a cycle, raise CycleError, a ValueError subclass defined in the module, whose .cycle attribute "
        "is a list of task names [t0, t1, ..., t0] where each task depends on the next one (for {'a': ['a']} "
        "that is ['a', 'a']). Command line: python <script> FILE reads lines like 'task: dep1 dep2' and prints "
        "the order, one task per line. In --test mode check ordering, ties and cycles."),
    "slots": (
        "Create a Python module with free_slots(busy, day_start, day_end, min_length) -> list. busy is a list "
        "of (start, end) pairs of 'HH:MM' strings (24-hour, two-digit hours 00-23 and minutes 00-59) giving "
        "everyone's busy periods together; they can overlap, touch or extend outside the day, and aren't "
        "sorted. A period covers start up to but not including end. Return, sorted, the (start, end) 'HH:MM' "
        "pairs of free time inside day_start..day_end that last at least min_length minutes (a positive "
        "integer); periods that touch leave no gap between them. Raise ValueError for a malformed time, a busy "
        "period whose start isn't before its end, or day_start not before day_end. Command line: python "
        "<script> DAY_START DAY_END MIN_LENGTH START-END ... prints one free slot per line. In --test mode "
        "check overlaps, touching periods, clipping to the day and the error cases."),
}
SET = sys.argv[2] if len(sys.argv) > 2 else "set1"
CHECKS_FILE = "battery_checks.py"
TOP = [("bowling", "ultra"), ("glob", "ultra"), ("calc", "max")]
if SET == "set2":                      # the second task set: goals live with their checkers
    sys.path.insert(0, HERE)
    import battery2_checks  # noqa: E402
    GOALS, CHECKS_FILE = battery2_checks.GOALS, "battery2_checks.py"
    TOP = [("semver", "ultra"), ("csv", "ultra"), ("justify", "max")]
TASKS = list(GOALS)
TAG = os.environ.get("BATTERY_TAG", "")                 # suffix for target names (one-off runs)
EXTRA = os.environ.get("BATTERY_EXTRA", "").split()    # extra pipeline flags, e.g. --helper-think 8000
if MODE == "quick":
    MATRIX = [(t, "low") for t in TASKS]
elif MODE == "one":                    # battery.py one set1 TASK LEVEL
    MATRIX = [(sys.argv[3], sys.argv[4])]
else:
    MATRIX = [(t, lvl) for lvl in ("low", "medium", "high") for t in TASKS] + TOP


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
_orig_launch = ag._launch


def launch_with_flags(job):
    job["args"] = job["args"] + [a for a in ("--no-memory", "--no-ingest") if a not in job["args"]] + EXTRA
    return _orig_launch(job)


ag._launch = launch_with_flags


def pump(sec):
    end = time.time() + sec
    while time.time() < end:
        root.update()
        time.sleep(0.05)


def dispatch(task, level):
    ag.goal_entry.delete("1.0", "end")
    ag.goal_entry.insert("1.0", GOALS[task])
    ag.target_entry.delete(0, "end")
    ag.target_entry.insert(0, f"{task}_{level}{TAG}.py")
    ag.allow_network.set(False)
    ag.level.set(level)
    ag._on_level_change()
    ag.task_research.set(False)
    ag.start_pipeline()
    job = ag.jobs[-1]
    job["task"] = task
    return job


def check(job):
    """Run the reference checker in the sandbox on the promoted file (or the best failed attempt)."""
    target = f"{job['task']}_{job['level']}{TAG}.py"
    if job["state"] == "PASSED":
        remote = f"/bb/workspace/{target}"
    elif job["run_id"]:
        remote = f"/bb/runs/{job['run_id']}/final_{target}"
    else:
        return "no file"
    cmd = (f"docker run --rm -i --network none --memory 512m -v /mnt/blackboard:/bb:ro {config.SANDBOX_IMAGE} "
           f"timeout 300 python3 - {job['task']} {remote}")
    with open(os.path.join(HERE, CHECKS_FILE), "rb") as f:
        res = subprocess.run(["ssh", "-o", "BatchMode=yes", config.SSH_TARGET, cmd], stdin=f,
                             capture_output=True, timeout=400)
    out = res.stdout.decode("utf-8", "replace").strip()
    return out or f"checker failed: {res.stderr.decode('utf-8', 'replace')[-300:]}"


pump(4)
jobs = [dispatch(t, lvl) for t, lvl in MATRIX]
say("queued:", [(j["id"], j["task"], j["level"]) for j in jobs])
last = None
end = time.time() + 10 * 3600
while time.time() < end and (any(j["state"] in ("QUEUED", "RUNNING") for j in jobs) or ag._switching):
    pump(5)
    snap = [(j["id"], j["task"], j["level"], j["state"]) for j in jobs] + [("mode", ag._server_mode, ag._switching)]
    if snap != last:
        say(" ".join(f"#{i} {t}/{lvl} {st}" for i, t, lvl, st in snap[:-1]), "| mode", ag._server_mode,
            "switching" if ag._switching else "")
        last = snap
say("all runs finished; waiting for the idle-time digests...")
t0 = time.time()
pump(30)
while time.time() - t0 < 900 and ag._digest_proc is not None and ag._digest_proc.poll() is None:
    pump(5)

results = []
for j in jobs:
    rec = R.hgetall(config.TASK_KEY_PREFIX + j["run_id"]) if j["run_id"] else {}
    tok = sum(v.get("out", 0) for v in json.loads(rec.get("tokens") or "{}").values())
    score = check(j)
    results.append({"task": j["task"], "level": j["level"], "state": j["state"], "run_id": j["run_id"],
                    "attempt": rec.get("attempt"), "elapsed_s": rec.get("elapsed_s"), "tokens_out": tok,
                    "digest": bool(rec.get("digest")), "check": score})
    say(f"{j['task']:8} {j['level']:7} {j['state']:7} attempt {rec.get('attempt')} {rec.get('elapsed_s')}s "
        f"{tok} tok | digest {'yes' if rec.get('digest') else 'NO'} | {score.splitlines()[0] if score else '?'}")
    for line in score.splitlines()[1:4]:
        say("      ", line[:250])
with open(os.path.join(HERE, f"battery_results_{SET}.json"), "w", encoding="utf-8") as f:
    json.dump(results, f, indent=1)
say("BATTERY DONE")
app._remove_pid_file()
if OLD_PID:
    with open(cl.GUI_PID_FILE, "w") as f:
        f.write(OLD_PID)
root.destroy()
