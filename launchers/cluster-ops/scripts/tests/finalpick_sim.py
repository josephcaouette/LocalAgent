"""Would a failed run keep a better file if it judged its candidates by its final independent tests?

    python finalpick_sim.py set4_v2 [-P 8]        (BATTERY_TAG=_v2 for the runs' target names)

A failed run keeps the candidate that got furthest (progress(): own test passed, then independent
tests passed, then the share of its own checks). In set 4's second battery that kept 11,862 of the
14,068 points its best candidates reach: a candidate whose weak self-test passed (6/1234) beat ones
that failed theirs, and own-check shares were compared across self-tests that change every attempt.
This runs the last version of each independent test (acceptance, adversarial) on every candidate of
every failed High/Ultra/MAX run, in the sandbox on Node 2 (P containers at once; Node 1 isn't used),
and compares picks by those tests with the kept file and the best candidate (candidate_scores_<name>.json).
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "Z:/workspace")
import config  # noqa: E402
import run_langgraph_pipeline as p  # noqa: E402

name = sys.argv[1]
par = int(sys.argv[sys.argv.index("-P") + 1]) if "-P" in sys.argv else 8
tag = os.environ.get("BATTERY_TAG", "")
CAND = re.compile(r"a(\d+)c(\d+)")
SSH = ["ssh", "-o", "BatchMode=yes", config.SSH_TARGET]
results = json.load(open(os.path.join(HERE, f"battery_results_{name}.json"), encoding="utf-8"))
scores = json.load(open(os.path.join(HERE, f"candidate_scores_{name}.json"), encoding="utf-8"))

remote = f"/tmp/finalpick_{name}"
subprocess.run(SSH + [f"rm -rf {remote} && mkdir -p {remote}/out"], check=True)
jobs, runs = [], {}
for r in results:
    if r["state"] == "PASSED" or r["level"] not in ("high", "ultra", "max"):
        continue
    rid, target = r["run_id"], f"{r['task']}_{r['level']}{tag}.py"
    run_dir = os.path.join(config.RUNS_DIR, rid)
    cands = sorted((d for d in os.listdir(run_dir) if CAND.fullmatch(d) and os.path.isfile(os.path.join(run_dir, d, target))),
                   key=lambda d: tuple(map(int, CAND.fullmatch(d).groups())))
    tests = {}
    for d in cands:                                   # the last version of each test wins
        for fname in p.TEST_FILES.values():
            if os.path.isfile(os.path.join(run_dir, d, fname)):
                tests[fname] = os.path.join(run_dir, d, fname)
    if not tests:
        continue
    subprocess.run(SSH + [f"mkdir -p {remote}/{rid}"], check=True)
    for fname, path in tests.items():
        subprocess.run(["scp", "-q", "-o", "BatchMode=yes", path, f"{config.SSH_TARGET}:{remote}/{rid}/{fname}"], check=True)
    runs[rid] = {"task": r["task"], "level": r["level"], "target": target, "cands": cands, "tests": sorted(tests)}
    for d in cands:
        for fname in tests:
            jobs.append((rid, d, fname, target))
print(f"{len(jobs)} test runs on {sum(len(v['cands']) for v in runs.values())} candidates in {len(runs)} runs; "
      f"{par} at a time on Node 2", flush=True)

with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, newline="\n") as f:
    for i, (rid, d, fname, target) in enumerate(jobs):
        f.write(f"{i} {rid} {d} {fname} {target}\n")
    listing = f.name
subprocess.run(["scp", "-q", "-o", "BatchMode=yes", listing, f"{config.SSH_TARGET}:{remote}/jobs.txt"], check=True)
os.remove(listing)
# "<i> <run> <cand> <test> <target>" -> $0..$4. Each candidate gets a fresh writable /work, as in a run.
cmd = (f"cd {remote} && xargs -P {par} -L 1 sh -c 'docker run --rm --network none --memory 1g "
       f"--tmpfs /work:exec,mode=1777 -v /mnt/blackboard:/bb:ro -v {remote}:/fp:ro {config.SANDBOX_IMAGE} "
       f"sh -c \"cp /bb/runs/$1/$2/$4 /fp/$1/$3 /work/ && cd /work && timeout 60 python3 -u $3; echo @@rc=\\$?\" "
       f"> out/$0.txt 2>&1' < jobs.txt")
t0 = time.time()
subprocess.run(SSH + [cmd], check=False)
print(f"ran in {time.time() - t0:.0f}s", flush=True)
dump = subprocess.run(SSH + [f"cd {remote}/out && for f in *.txt; do echo \"=== $f\"; cat \"$f\"; done"],
                      capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
outputs, cur = {}, None
for line in dump.splitlines():
    if line.startswith("=== ") and line.endswith(".txt"):
        cur = int(line[4:-4])
        outputs[cur] = []
    elif cur is not None:
        outputs[cur].append(line)


def tally(lines):
    """(passes, fails) the way progress() counts: a crash or timeout without a FAIL line is one more."""
    rc = next((int(ln[5:]) for ln in reversed(lines) if ln.startswith("@@rc=")), None)
    passes = sum(1 for ln in lines if p._PASS_LINE.match(ln))
    fails = sum(1 for ln in lines if re.match(r"\s*FAIL", ln, re.IGNORECASE))
    if rc != 0 and (not fails or rc in (124, 137) or any("Traceback (most recent call last)" in ln for ln in lines)):
        fails += 1
    return passes, fails, rc


per = {}
for i, (rid, d, fname, _t) in enumerate(jobs):
    per.setdefault(rid, {}).setdefault(d, {})[fname] = tally(outputs.get(i, []))


def pts(rid, d):
    s = scores[rid]["cands"].get(d, "")
    return int(s.split("/")[0]) if re.match(r"\d+/\d+$", s) else 0


rows, tot = [], {"kept": 0, "share": 0, "passed": 0, "best": 0}
for rid, run in runs.items():
    cands = run["cands"]

    def share(d):
        t = per[rid][d]
        return sum(ps / (ps + fs) if ps + fs else 0.0 for ps, fs, _rc in t.values()) / len(t)

    def passed(d):
        return sum(1 for _ps, _fs, rc in per[rid][d].values() if rc == 0)
    by_share = max(cands, key=lambda d: (share(d), tuple(map(int, CAND.fullmatch(d).groups()))))
    by_passed = max(cands, key=lambda d: (passed(d), share(d), tuple(map(int, CAND.fullmatch(d).groups()))))
    best = max(cands, key=lambda d: pts(rid, d))
    kept = scores[rid]["kept"]
    kept_pts = int(re.search(r"(\d+)/", kept).group(1)) if re.search(r"(\d+)/", kept) else 0
    total = re.search(r"/(\d+)", kept).group(1) if re.search(r"/(\d+)", kept) else "?"
    rows.append(f"{run['task']:7}{run['level']:6} kept {kept_pts:5} | by share {pts(rid, by_share):5} ({by_share}, "
                f"{share(by_share):.2f}) | by tests passed {pts(rid, by_passed):5} ({by_passed}) | best "
                f"{pts(rid, best):5} ({best}, share {share(best):.2f}) of {total}; tests {', '.join(run['tests'])}")
    for k, v in (("kept", kept_pts), ("share", pts(rid, by_share)), ("passed", pts(rid, by_passed)),
                 ("best", pts(rid, best))):
        tot[k] += v
print("\n".join(rows))
print(f"totals: kept {tot['kept']}, by share {tot['share']}, by tests passed {tot['passed']}, best {tot['best']}")
json.dump({rid: {d: {t: list(v) for t, v in tv.items()} for d, tv in cs.items()} for rid, cs in per.items()},
          open(os.path.join(HERE, f"finalpick_{name}.json"), "w", encoding="utf-8", newline="\n"), indent=1)
