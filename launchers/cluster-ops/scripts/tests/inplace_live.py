"""Live checks (Node 1) on two real failures from battery set 1, saved in tests/data/:
1. calc/max: the first adversarial test expected 9 for 10-2*3+4*5-6, and all 5 independent candidates
   returned 18. The in-place fix must change only that check, and the fixed test must pass on the
   winning code in the sandbox (the original must fail there).
2. glob/low: the self-test expected a*b*c not to match abcc (it does). Low's thinking diagnosis must
   blame the expectation (run 3 times; the quick no-thinking diagnosis blamed the code).
Run only when Node 1 is free: about 4 model calls, 3-4 minutes. Usage: python inplace_live.py [1|2]"""
import difflib
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

p.report = lambda *a, **k: None
WORK = os.path.join(config.RUNS_DIR, "inplace-live")       # not a run name, so pruning ignores it
REMOTE = "/mnt/blackboard/runs/inplace-live"
PARTS = sys.argv[1:] or ["1", "2"]


def sandbox(files, cmd):
    """Put files in the scratch folder and run cmd there in the sandbox: CompletedProcess."""
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK)
    for name, text in files.items():
        with open(os.path.join(WORK, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    docker = (f"docker run --rm --network none --memory 512m -v {REMOTE}:/work:ro -w /work "
              f"{config.SANDBOX_IMAGE} timeout 60 {cmd}")
    return subprocess.run(["ssh", "-o", "BatchMode=yes", config.SSH_TARGET, docker],
                          capture_output=True, text=True, timeout=120)


def case(name):
    folder = os.path.join(HERE, "data", name)
    rec = json.load(open(os.path.join(folder, "record.json"), encoding="utf-8"))
    return folder, rec


if "1" in PARTS:
    folder, rec = case("calc_max_case")
    target = rec["target_file"]
    old_full = open(os.path.join(folder, "adversarial_test.py"), encoding="utf-8").read()
    winner = open(os.path.join(folder, "final_calc_max.py"), encoding="utf-8").read()
    state = {"target_file": target, "goal": rec["goal"], "spec": rec["spec"],
             "checks": json.loads(rec["checks"] or "[]"), "interface": rec["interface"],
             "tests": {"adversarial": old_full}, "test_feedback": {"adversarial": rec["diagnosis"]},
             "test_checks": {}, "lvl": config.level_settings("max"), "allow_network": False,
             "error": f"DIAGNOSIS:\n{rec['diagnosis']}\n\nRAW ERROR (tail):\n"
                      "FAIL: evaluate '10-2*3+4*5-6' expected 9, got 18"}
    p.THINK_TOKENS = 16000
    calls, real = [], p.llm_chat
    p.llm_chat = lambda *a, **k: (calls.append(bool(k.get("think", False))), real(*a, **k))[1]  # llm_chat's default
    t0 = time.time()
    new_full = p.write_test(state, "adversarial")
    p.llm_chat = real
    secs = time.time() - t0
    head = len(p.test_header(target))
    diff = [ln for ln in difflib.unified_diff(old_full[head:].splitlines(), new_full[head:].splitlines(),
                                              lineterm="", n=0) if ln[:1] in "+-" and ln[:3] not in ("+++", "---")]
    before = sandbox({target: winner, "adversarial_test.py": old_full}, "python3 /work/adversarial_test.py")
    after = sandbox({target: winner, "adversarial_test.py": new_full}, "python3 /work/adversarial_test.py")
    fails_after = p.failure_lines(after.stdout or "")
    print(f"PART 1: model calls {len(calls)} (thinking: {calls}) in {secs:.0f}s | in place: {calls == [False]}")
    print(f"    changed lines: {len(diff)}")
    for ln in diff[:8]:
        print("     ", ln[:160])
    print(f"    original on the winning code: rc={before.returncode} (should fail) | "
          f"fixed: rc={after.returncode}, FAIL lines: {fails_after or 'none'}")
    print("PART 1", "PASS" if calls == [False] and before.returncode != 0 and after.returncode == 0
          and not fails_after and len(diff) <= 6 else "FAIL")

if "2" in PARTS:
    folder, rec = case("glob_low_case")
    code = open(os.path.join(folder, "glob_low.py"), encoding="utf-8").read()
    res = sandbox({"glob_low.py": code}, "python3 /work/glob_low.py --test")
    err = p.run_error(res, 0.5, "Its own test (python3 glob_low.py --test)")
    state = {"attempt": 3, "max_attempts": 3, "judges": 1, "failure_kind": "runtime", "goal": rec["goal"],
             "spec": "", "checks": [], "code": code, "tests": {}, "failed_test": "self", "error": err,
             "candidates": [{"k": 1, "rc": 1, "failed_test": "self", "independent": False, "stdout": res.stdout}],
             "lvl": config.level_settings("low"), "run_id": "inplace-live", "task_key": "inplace-live"}
    config.HELPER_BACKEND = "node1"
    p.THINK_TOKENS = config.THINK_TOKENS
    print("PART 2: the failing line:", p.failure_lines(res.stdout or "").splitlines()[:1])
    blames = []
    for i in range(3):
        t0 = time.time()
        upd = p.error_condenser_node(state)
        text = upd.get("error", "")
        blame = (text.split("BLAME:", 1)[1].split()[0].lower() if "BLAME:" in text else "none")
        blames.append(blame)
        print(f"    try {i + 1}: blame={blame} ({time.time() - t0:.0f}s)")
    print("PART 2", "PASS" if blames.count("expectation") >= 2 else "FAIL", "| blames:", blames)
shutil.rmtree(WORK, ignore_errors=True)
