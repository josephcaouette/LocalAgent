"""The stand-in check on every saved independent test that a winning candidate passed: any finding
there is a false alarm, since the winner passed every check. Reads the passing attempt from each
run's pipeline.log ("PASSED on attempt N (candidate K)") under Z:\\runs.

    python standin_replay.py [PIPELINE_COPY.py] [-P 3]

Uses the sandbox on Node 2 (two containers per test, P tests at a time), not Node 1."""
import importlib.util
import os
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor

args = sys.argv[1:]
par = int(args[args.index("-P") + 1]) if "-P" in args else 3
copy = next((os.path.abspath(a) for a in args if a.endswith(".py")), None)    # before the chdir
sys.path.insert(0, r"Z:\workspace")
os.chdir(r"Z:\workspace")
if copy:
    spec = importlib.util.spec_from_file_location("run_langgraph_pipeline", copy)
    p = importlib.util.module_from_spec(spec)
    sys.modules["run_langgraph_pipeline"] = p
    spec.loader.exec_module(p)
else:
    import run_langgraph_pipeline as p  # noqa: E402
import config  # noqa: E402

PASSED = re.compile(r"PASSED on attempt (\d+) \(candidate (\d+)\)")
jobs = []
for run in sorted(os.listdir(config.RUNS_DIR)):
    log = os.path.join(config.RUNS_DIR, run, "pipeline.log")
    if run.startswith("unit") or not os.path.exists(log):
        continue
    text = open(log, encoding="utf-8", errors="replace").read()
    m = PASSED.search(text)
    level = re.search(r"--accuracy[= ](\w+)|accuracy: (\w+)|Level: (\w+)", text)
    if not m:
        continue
    folder = os.path.join(config.RUNS_DIR, run, f"a{m.group(1)}c{m.group(2)}")
    for role, fname in p.TEST_FILES.items():
        path = os.path.join(folder, fname)
        if os.path.exists(path):
            target = next((f for f in os.listdir(folder) if f.endswith(".py") and f not in
                           (p.TEST_FILES["acceptance"], p.TEST_FILES["adversarial"], p.PROBE_FILE,
                            p.REGRESSION_FILE)), "")
            if target:
                jobs.append((run, os.path.basename(folder), role, target, path))
print(f"{len(jobs)} tests that a winner passed", flush=True)


def check(i, job):
    run, cand, role, target, path = job
    test = open(path, encoding="utf-8").read().replace("\r\n", "\n")
    st = {"run_id": "unit-standin-replay", "attempt": 1000 + i, "target_file": target,
          "lvl": config.level_settings("max"), "allow_network": False}
    try:
        return job, p.standin_findings(*p.standin_runs(st, role, test), target)
    except Exception as e:
        return job, [f"(check failed: {e})"]


bad = 0
with ThreadPoolExecutor(max_workers=par) as pool:
    for (run, cand, role, target, _path), found in pool.map(lambda a: check(*a), enumerate(jobs)):
        bad += bool(found)
        print(f"{run} {cand} {role:11} {target:22} {len(found)} found" + (f": {found[0][:150]}" if found else ""),
              flush=True)
shutil.rmtree(os.path.join(config.RUNS_DIR, "unit-standin-replay"), ignore_errors=True)
print(f"false alarms: {bad} of {len(jobs)} tests")
