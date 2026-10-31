"""A/B of the acceptance test writer's reference guidance (STDLIB_REFERENCE, OWN_REFERENCE_LIMIT) on
the csv task: set 2's Ultra run 20261031-134126 (its spec, checks and interface; the battery's current
goal). Each arm writes N acceptance tests through the pipeline's own write_test on Node 1, "old" with
the two sentences blanked and "new" with them. Every test then runs in the sandbox on:
- correct implementations: the run's final file and its candidates that the reference checker passes
  in full. A test that fails one is a false failure (in a real run: a diagnosis, then a re-test);
- mutants of the final file (one small change each, from probe_trial.py) that the reference checker
  tells apart. A test catches a mutant when it fails on it; counted only for tests that pass the final
  file (a test that fails everything catches nothing useful).
It also records whether each test uses the csv module. Usage: python testwriter_ab.py [N=3] [ARMS]
Uses Node 1 (2N thinking calls, the arms one after the other) and the sandbox, about 25 minutes.

Result (2026-10-31, 16k server, 3 tests per arm; testwriter_ab_results.json): the guidance didn't help,
so it was taken out again. Usable tests (pass the correct file): old 1/3, new 1/3, new2 (a second
STDLIB wording: "a module the goal forbids the script usually implements the rules") 0/3. No test in
any arm used the csv module. The limit did change the style (no new test wrote a full second parser,
against 3/3 old) but not the error rate: the broken tests all tripped over empty lines ([''] for []).
Each usable test caught 39 of 40 mutants. To A/B another wording, put it in module constants in the
pipeline again: "old" blanks them, any other arm uses them."""
import glob
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, r"Z:\workspace")
os.chdir(r"Z:\workspace")
import config  # noqa: E402
import run_langgraph_pipeline as p  # noqa: E402

sys.path.insert(0, HERE)
import battery2_checks  # noqa: E402
from probe_trial import mutants, sections, write  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 3
ARMS = sys.argv[2].split(",") if len(sys.argv) > 2 else ["old", "new"]   # e.g. "new" to rerun one arm
RUN, TARGET = "20261031-134126", "csv_ultra.py"
WORK = os.path.join(config.RUNS_DIR, "testwriter-ab")    # not a run name, so pruning ignores it
REMOTE = "/mnt/blackboard/runs/testwriter-ab"
KEEP_CORRECT, KEEP_MUTANTS = 6, 40
USES_CSV = re.compile(r"^\s*(import csv\b|from csv import)", re.M)


def sandbox(script, limit=2400):
    """Run a shell script in one sandbox container with the trial folder at /trial (read-only)."""
    docker = (f"docker run --rm --network none --memory 1g -e PYTHONDONTWRITEBYTECODE=1 "
              f"-v {REMOTE}:/trial:ro {config.SANDBOX_IMAGE} sh -c {shlex.quote(script)}")
    res = subprocess.run(["ssh", "-o", "BatchMode=yes", config.SSH_TARGET, docker],
                         capture_output=True, text=True, timeout=limit + 120)
    return res.stdout


def main():
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK)
    shutil.copy(os.path.join(HERE, "battery2_checks.py"), WORK)
    run_dir = os.path.join(config.RUNS_DIR, RUN)
    final = open(os.path.join(run_dir, f"final_{TARGET}"), encoding="utf-8").read()
    impls = {"final": final}
    for path in sorted(glob.glob(os.path.join(run_dir, "a*c*", TARGET))):
        impls["c_" + os.path.basename(os.path.dirname(path))] = open(path, encoding="utf-8").read()
    impls.update(mutants(final))
    for name, code in impls.items():
        write(os.path.join(WORK, "impls", f"{name}.py"), code)

    # 1. Which implementations the reference checker passes in full, and which mutants it tells apart.
    out = sandbox('for f in /trial/impls/*.py; do echo "== $f"; timeout 30 python3 /trial/battery2_checks.py '
                  'csv "$f" 2>/dev/null | head -1; done')
    score = {}
    for path, line in sections(out, "SCORE").items():
        try:
            a, b = line.split()[1].split("/")
            score[os.path.basename(path)[:-3]] = (int(a), int(b))
        except (AttributeError, IndexError, ValueError):
            score[os.path.basename(path)[:-3]] = (0, 1)
    full = lambda n: n in score and score[n][0] == score[n][1]   # noqa: E731
    assert full("final"), f"the final file doesn't pass the reference checker: {score.get('final')}"
    correct = ["final"] + [n for n in impls if n.startswith("c_") and full(n)][:KEEP_CORRECT]
    told_apart = [n for n in impls if n.startswith("m") and not full(n)][:KEEP_MUTANTS]
    equivalent = sum(1 for n in impls if n.startswith("m") and full(n))
    print(f"{len(correct)} correct implementations, {len(told_apart)} mutants told apart "
          f"({equivalent} equivalent)", flush=True)

    # 2. The tests: N per arm, written concurrently within an arm (the sentences are module globals).
    rec = config.get_redis(decode_responses=True).hgetall(config.TASK_KEY_PREFIX + RUN)
    p.connect_llm()
    p.THINK_TOKENS = config.level_settings("ultra")["think_tokens"]
    p.report = lambda *a, **k: None
    state = {"target_file": TARGET, "goal": battery2_checks.GOALS["csv"], "spec": rec["spec"],
             "checks": json.loads(rec["checks"]), "interface": rec["interface"], "allow_network": False,
             "lvl": config.level_settings("ultra"), "tests": {}, "test_feedback": {}}
    names = [n for n in ("STDLIB_REFERENCE", "OWN_REFERENCE_LIMIT") if hasattr(p, n)]   # gone since the test
    saved = {n: getattr(p, n) for n in names}
    tests, gen = {}, []
    for arm in ARMS:
        # "old" blanks the guidance; any other arm uses it as the pipeline has it now
        for n in names:
            setattr(p, n, "" if arm == "old" else saved[n])
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=N) as pool:
            texts = list(pool.map(lambda _: p.write_test(dict(state), "acceptance"), range(N)))
        gen.append({"arm": arm, "secs": round(time.time() - t0), "usable": sum(1 for t in texts if t)})
        print(f"{arm}: {sum(1 for t in texts if t)} of {N} tests written in {time.time() - t0:.0f}s", flush=True)
        for s, text in enumerate(texts, 1):
            if text:
                tests[f"{arm}_{s}"] = text
    for n in names:
        setattr(p, n, saved[n])
    keep =os.path.join(os.environ.get("TEMP", "."), "agent_tests", "testwriter_ab_files")
    for name, text in tests.items():
        write(os.path.join(keep, f"{name}.py"), text)
        write(os.path.join(WORK, "tests", f"{name}.py"), text.replace("/work/", "/tmp/w/"))

    # 3. Every test on every correct implementation and told-apart mutant, each at the path tests load
    #    (four containers in parallel, each taking every fourth implementation).
    def run_group(names):
        return sandbox(
            f'W=/tmp/w; mkdir -p $W; for n in {" ".join(names)}; do cp /trial/impls/$n.py $W/{TARGET}; '
            f'for t in /trial/tests/*.py; do cp $t $W/test.py; (cd $W && timeout -k 3 20 python3 $W/test.py '
            f'> /tmp/out 2>&1); rc=$?; echo "== $n $(basename $t .py) $rc"; '
            f'if [ $n = final ] && [ $rc != 0 ]; then grep -E "FAIL|Error" /tmp/out | head -6; fi; done; done')
    every = correct + told_apart
    with ThreadPoolExecutor(max_workers=4) as pool:
        out = "\n".join(pool.map(run_group, [every[i::4] for i in range(4)]))
    rc, fails_on_final, last = {}, {}, None
    for line in out.splitlines():
        if line.startswith("== "):
            _, impl, test, code = line.split()
            rc[(impl, test)] = int(code)
            last = test if impl == "final" else None
        elif last:
            fails_on_final.setdefault(last, []).append(line.strip()[:200])
    rows = {}
    for test, text in tests.items():
        passes_final = rc.get(("final", test)) == 0
        rows[test] = {"uses_csv": bool(USES_CSV.search(text)), "lines": len(text.splitlines()),
                      "passes_final": passes_final,
                      "false_failures": sum(1 for c in correct if rc.get((c, test), 1) != 0),
                      "mutants_caught": sum(1 for m in told_apart if rc.get((m, test), 0) != 0) if passes_final else 0,
                      "fails_on_final": fails_on_final.get(test, [])}
    result = {"run": RUN, "correct": len(correct), "mutants": len(told_apart), "equivalent": equivalent,
              "context": p.CONTEXT_TOKENS, "generation": gen, "rows": rows}
    out_file = os.path.join(HERE, "testwriter_ab_results.json")
    try:                                         # keep earlier arms' rows when only some arms ran
        old = json.load(open(out_file, encoding="utf-8"))
        result["rows"] = {**{k: v for k, v in old.get("rows", {}).items() if k.split("_")[0] not in ARMS},
                          **result["rows"]}
        result["generation"] = [g for g in old.get("generation", []) if g["arm"] not in ARMS] + gen
    except (OSError, ValueError):
        pass
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1)
    print(f"\n{'test':7} csv  lines  final  false-fail  caught/{len(told_apart)}")
    for test, r in rows.items():
        print(f"{test:7} {'yes' if r['uses_csv'] else 'no ':3} {r['lines']:5}  {'pass' if r['passes_final'] else 'FAIL':5}"
              f"  {r['false_failures']:>4}/{len(correct)}     {r['mutants_caught']:>3}")
        for line in r["fails_on_final"][:3]:
            print(f"        {line}")
    shutil.rmtree(WORK, ignore_errors=True)


if __name__ == "__main__":
    main()
