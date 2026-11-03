"""Score every candidate a battery's runs wrote, not only the file each run kept.

    python score_candidates.py set4 [-P 8] [--failed-only] [--results set4_fb_high]

Reads battery_results_<set>.json, finds each run's candidate files (Z:\\runs\\<run>\\a<N>c<M>\\<target>)
and its final file, and runs the set's checker on all of them in the sandbox on Node 2, P at a time,
each in its own container (the same command battery.py uses). Writes candidate_scores_<set>.json:
    {run_id: {"task", "level", "state", "kept": <battery's score line>,
              "cands": {"a3c1": "887/1234", ..., "final": "271/1037"}, "parts": {...}}}
"kept" is what the battery scored: the promoted file of a PASSED run, final_<target> otherwise.
Node 1 isn't used, so this can run beside other work, but it loads Node 2 with P checkers at once.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, "Z:/workspace")
import config  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CHECKS = {"set1": "battery_checks.py", "set2": "battery2_checks.py", "set3": "battery3_checks.py",
          "set4": "battery4_checks.py"}
LIMITS = {"set4": (900, "1g")}          # (timeout s, memory); the rest use battery.py's 300 s / 512m
SSH = ["ssh", "-o", "BatchMode=yes", config.SSH_TARGET]
SCORE = re.compile(r"SCORE (\d+)/(\d+)")
CAND = re.compile(r"a(\d+)c(\d+)")


def find_jobs(results, tag, failed_only):
    jobs, runs = [], {}
    for r in results:
        rid = r.get("run_id")
        if not rid or (failed_only and r["state"] == "PASSED"):
            continue
        target = f"{r['task']}_{r['level']}{tag}.py"
        run_dir = os.path.join(config.RUNS_DIR, rid)
        runs[rid] = {"task": r["task"], "level": r["level"], "state": r["state"],
                     "kept": (r.get("check") or "").splitlines()[0] if r.get("check") else "", "cands": {}, "parts": {}}
        names = sorted((d for d in os.listdir(run_dir) if CAND.fullmatch(d)),
                       key=lambda d: tuple(map(int, CAND.fullmatch(d).groups())))
        for d in names:
            if os.path.isfile(os.path.join(run_dir, d, target)):
                jobs.append((rid, d, r["task"], f"/bb/runs/{rid}/{d}/{target}"))
        if os.path.isfile(os.path.join(run_dir, "final_" + target)):
            jobs.append((rid, "final", r["task"], f"/bb/runs/{rid}/final_{target}"))
    return jobs, runs


def main():
    set_ = sys.argv[1]
    par = int(sys.argv[sys.argv.index("-P") + 1]) if "-P" in sys.argv else 8
    failed_only = "--failed-only" in sys.argv
    tag = os.environ.get("BATTERY_TAG", "")           # the suffix of the runs' target names
    # --results set4_fb_high reads battery_results_set4_fb_high.json (a `level` or tagged battery)
    name = sys.argv[sys.argv.index("--results") + 1] if "--results" in sys.argv else set_ + tag
    timeout, memory = LIMITS.get(set_, (300, "512m"))
    with open(os.path.join(HERE, f"battery_results_{name}.json"), encoding="utf-8") as f:
        results = json.load(f)
    jobs, runs = find_jobs(results, tag, failed_only)
    print(f"{len(jobs)} files in {len(runs)} runs; {par} at a time on Node 2", flush=True)

    remote = f"/tmp/score_{name}"
    subprocess.run(SSH + [f"rm -rf {remote} && mkdir -p {remote}/out"], check=True)
    subprocess.run(["scp", "-q", "-o", "BatchMode=yes", os.path.join(HERE, CHECKS[set_]),
                    f"{config.SSH_TARGET}:{remote}/checks.py"], check=True)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, newline="\n") as f:
        for i, (_rid, _cand, task, path) in enumerate(jobs):
            f.write(f"{i} {task} {path}\n")
        listing = f.name
    subprocess.run(["scp", "-q", "-o", "BatchMode=yes", listing, f"{config.SSH_TARGET}:{remote}/jobs.txt"], check=True)
    os.remove(listing)

    # Each line is "<index> <task> <path>": sh gets them as $0 $1 $2.
    run = (f"cd {remote} && xargs -P {par} -L 1 sh -c 'docker run --rm --network none --memory {memory} "
           f"-v /mnt/blackboard:/bb:ro -v {remote}:/c:ro {config.SANDBOX_IMAGE} timeout {timeout} "
           f"python3 /c/checks.py \"$1\" \"$2\" > out/$0.txt 2>&1' < jobs.txt")
    t0 = time.time()
    subprocess.run(SSH + [run], check=False)
    print(f"checked in {time.time() - t0:.0f}s", flush=True)

    dump = subprocess.run(SSH + [f"cd {remote}/out && for f in *.txt; do echo \"=== $f\"; head -2 \"$f\"; done"],
                          capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    outputs, cur = {}, None
    for line in dump.splitlines():
        if line.startswith("=== "):
            cur = int(line[4:].split(".")[0])
            outputs[cur] = []
        elif cur is not None:
            outputs[cur].append(line)
    for i, (rid, cand, _task, _path) in enumerate(jobs):
        lines = outputs.get(i, [])
        m = SCORE.search(lines[0]) if lines else None
        runs[rid]["cands"][cand] = f"{m.group(1)}/{m.group(2)}" if m else ("no output" if not lines else lines[0][:80])
        if len(lines) > 1 and lines[1].startswith("PARTS"):
            runs[rid]["parts"][cand] = lines[1][6:].strip()

    out_path = os.path.join(HERE, f"candidate_scores_{name}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(runs, f, indent=1)
    for rid, run in runs.items():
        scored = [(int(s.split("/")[0]), c) for c, s in run["cands"].items() if c != "final" and SCORE.match("SCORE " + s)]
        best = max(scored) if scored else (None, None)
        print(f"{run['task']:7} {run['level']:6} {run['state']:6} kept {run['kept'][6:] if run['kept'].startswith('SCORE') else run['kept']:>10}"
              f" | best {best[0]} ({best[1]}) of {len(scored)} candidates")
    print("wrote", out_path)


if __name__ == "__main__":
    main()
