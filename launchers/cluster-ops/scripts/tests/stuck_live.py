"""Live check (Node 1) on set 2's stuck csv run on High, saved in tests/data/csv_high_case/. The goal
says "a line break at the very end doesn't start another record; an empty line elsewhere is a record
with no fields". The independent test read '\\n' as no records and '\\n\\n' as one; every candidate
returned [[]] and [[], []], as Python's csv module and the battery's reference do. The diagnosis
blamed the script nine times and the run ended FAILED with a file that scores 815/815.
  python stuck_live.py [N=3]  replays the attempt-10 diagnosis N times without and N times with the note
                              about the stuck failures, and prints each blame (2N thinking calls, about
                              2.5 minutes each). On 2026-10-31: script 3/3 without the note; with it,
                              script plus an interface correction 3/3 (the loop ends on the test's reading).
  python stuck_live.py follow a saved diagnosis that corrected the interface (stuck_diagnosis.txt) goes
                              through the real code; two engineer candidates are written from it and run
                              against the real acceptance test in the sandbox: do they now follow the
                              correction, so the loop ends (about 5 minutes)? On 2026-10-31 both dropped
                              the four old failures but overcorrected ('a\\n\\n' lost its empty record),
                              so a run would go on with new failures instead of repeating the old ones.
                              A fourth diagnosis with the note (fresh) blamed the test instead.
Run only when Node 1 is free. The goal is the battery's original wording, kept in goal.txt (the
battery's goal now spells out the "\\n" case)."""
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, r"Z:\workspace")
os.chdir(r"Z:\workspace")
import config  # noqa: E402
import run_langgraph_pipeline as p  # noqa: E402

FOLLOW = sys.argv[1:2] == ["follow"]
N = int(sys.argv[1]) if sys.argv[1:] and not FOLLOW else 3
CASE = os.path.join(HERE, "data", "csv_high_case")
WORK = os.path.join(config.RUNS_DIR, "stuck-live")         # not a run name, so pruning ignores it
REMOTE = "/mnt/blackboard/runs/stuck-live"


def read(name):
    with open(os.path.join(CASE, name), encoding="utf-8") as f:
        return f.read()


p.report = lambda *a, **k: None
p.connect_llm()
p.THINK_TOKENS = config.level_settings("high")["think_tokens"]
FAILS = ["FAIL: lone_lf_at_end expected [], got [[]]", "FAIL: lone_crlf_at_end expected [], got [[]]",
         "FAIL: empty_line_elsewhere_lf expected [[]], got [[], []]",
         "FAIL: empty_line_elsewhere_crlf expected [[]], got [[], []]"]
OUT = "\n".join(FAILS) + "\n"
label = p.TEST_LABELS["acceptance"]
ERROR = (f"The script's own --test passed, but {label} (written separately, from the goal and checks only, "
         "without seeing the code) failed.\n"
         + p.run_error(subprocess.CompletedProcess([], 1, OUT, ""), 1.0, label.capitalize()))
CHECKS = ["python3 csv_high.py --test exits with code 0",
          "stdout contains PASS quoting, PASS escaped_quotes, PASS line_breaks_inside_quotes, PASS crlf, "
          "PASS empty_fields, PASS empty_lines, PASS errors, and OK",
          "stdout does not contain FAIL or Traceback"]


def state(stuck):
    cands = [{"k": k, "rc": 0, "failed_test": "acceptance", "independent": False,
              "tests_out": {"acceptance": (1, OUT, "", 1.0)}} for k in (1, 2, 3, 4)]
    return {"run_id": "stuck-live", "task_key": "stuck-live", "attempt": 11, "max_attempts": 12,
            "target_file": "csv_high.py", "failed_test": "acceptance", "failure_kind": "indep",
            "goal": read("goal.txt").strip(), "spec": "", "checks": CHECKS, "interface": read("interface.txt").strip(),
            "code": read("csv_high.py"), "tests": {"acceptance": read("acceptance_test.py")},
            "test_feedback": {}, "retests_used": 0, "error": ERROR, "candidates": cands,
            "indep_last": {"role": "acceptance", "fails": FAILS, "blame": "script", "attempt": 9} if stuck else {}}


def sandbox_test(code):
    """Run the real acceptance test against one version of csv_high.py: its failure lines."""
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK)
    for name, text in (("csv_high.py", code), ("acceptance_test.py", read("acceptance_test.py"))):
        with open(os.path.join(WORK, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(text.rstrip() + "\n")
    docker = (f"docker run --rm --network none --memory 512m -v {REMOTE}:/work:ro -w /work "
              f"{config.SANDBOX_IMAGE} timeout 60 python3 acceptance_test.py")
    res = subprocess.run(["ssh", "-o", "BatchMode=yes", config.SSH_TARGET, docker],
                         capture_output=True, text=True, timeout=120)
    return res.returncode, p.failure_lines((res.stdout or "") + "\n" + (res.stderr or ""), 1500)


if FOLLOW:
    # A diagnosis that added a correction (trial 1 with the note, 2026-10-31), replayed through the real
    # code so the interface is corrected exactly as in a run; the engineer then writes for real.
    real_chat = p.llm_chat
    p.llm_chat = lambda *a, **k: (read("stuck_diagnosis.txt"), "stop")
    st = state(True)
    upd = p.diagnose_independent_failure(st)
    p.llm_chat = real_chat
    if "interface" not in upd:
        print("\nThe saved diagnosis didn't correct the interface; nothing to follow.")
        sys.exit(1)
    p.prewarm_containers = lambda *a, **k: None
    p.write_test = lambda s, role: ""
    p.write_probe = lambda s: ""
    lvl = config.level_settings("high")
    st.update(upd, run_id="stuck-live-eng", lvl=lvl, num_candidates=2, think_engineer=lvl["think_engineer"],
              diverse=False, tester=False, tests={}, plan="(see the interface)", test_checks={}, probe="",
              regression=[], attachments="", web_brief="", research_brief="", memory_context="",
              existing_code="", allow_network=False, started=time.time(), time_limit_s=3600, candidates=[])
    cands = p.engineer_node(st)["candidates"]
    rc0, before = sandbox_test(read("csv_high.py"))
    print(f"\nThe attempt-10 code against the test: exit {rc0}\n{before}")
    for c in cands:
        if c["status"] != "coded":
            print(f"Candidate {c['k']}: {c['status']}")
            continue
        rc, fails = sandbox_test(c["code"])
        print(f"Candidate {c['k']} against the test: exit {rc}" + (f"\n{fails}" if fails else ", no failures"))
    shutil.rmtree(WORK, ignore_errors=True)
    shutil.rmtree(os.path.join(config.RUNS_DIR, "stuck-live-eng"), ignore_errors=True)
    sys.exit(0)

results = []
for stuck in (False, True):
    for i in range(1, N + 1):
        t0 = time.time()
        upd = p.diagnose_independent_failure(state(stuck))
        diag = upd.get("error", "").split("RAW ERROR")[0]
        blame = ("test" if upd.get("retest") or "BLAME: test" in diag else
                 "both" if "BLAME: both" in diag else "script")
        row = {"note": stuck, "trial": i, "blame": blame, "correction": "interface" in upd,
               "seconds": round(time.time() - t0)}
        results.append(row)
        print(f"== {'with' if stuck else 'without'} the note, trial {i}: blame {blame}"
              f"{', interface corrected' if row['correction'] else ''} ({row['seconds']}s)")

summary = {s: [r["blame"] for r in results if r["note"] == s] for s in (False, True)}
print(f"\nWithout the note: {summary[False]}\nWith the note:    {summary[True]}")
print("(test = re-test the same code; script with an interface correction also ends the loop; "
      "script alone repeats it)")
with open(os.path.join(HERE, "stuck_live_results.json"), "w", encoding="utf-8") as f:
    json.dump(results, f, indent=1)
