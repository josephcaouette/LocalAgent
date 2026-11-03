"""Which version the next fix starts from after an attempt fails (fake sandbox, no model):
--fix-base latest (the default): this attempt's best candidate, as before.
--fix-base furthest: the candidate that got furthest in the whole run (own test passed, then
independent tests passed, then the share of its own checks), with a note on what the worse attempt
tried; going back to the same version is allowed twice. Set 4's pyexpr run on Ultra peaked on
attempt 4 (972 of 1,234 reference cases), and its later fixes, each built on the attempt before,
ended at 757."""
import os
import sys

sys.path.insert(0, r"Z:\workspace")
os.chdir(r"Z:\workspace")
import config  # noqa: E402
import run_langgraph_pipeline as p  # noqa: E402

p.report = lambda *a, **k: None
p.discard_containers = lambda *a, **k: None
checks = []
OUTPUTS = {}          # code -> (rc, stdout, stderr)


def fake_run(state, c):
    rc, out, err = OUTPUTS[c["code"]]
    return dict(c, rc=rc, stdout=out, stderr=err, tests_out={}, exec_ok=False,
                exec_error=f"error of {c['code']}", failed_test="", indep_failed=False, indep_stdout="",
                elapsed=1.0)


p.run_candidate = fake_run
state = {"run_id": "unit-fixbase", "attempt": 1, "max_attempts": 9, "target_file": "f.py", "tests": {},
         "regression": [], "repeat_tests": 1, "lvl": config.level_settings("low"), "probe": "",
         "probe_verdicts": {}, "allow_network": False, "tester": False, "furthest": {}, "candidates": []}


def attempt(st, codes):
    st = dict(st, candidates=[{"k": k, "code": c, "status": "coded"} for k, c in enumerate(codes, 1)])
    upd = p.sandbox_executor_node(st)
    return dict(st, **{k: v for k, v in upd.items() if k != "candidates"}), upd     # fail() moves attempt on


OUTPUTS.update({
    "GOOD": (1, "PASS a\n" * 9 + "FAIL j: got 1, want 2\n", ""),           # 9 of 10
    "WORSE": (1, "PASS a\nFAIL b\nFAIL c\n", ""),                           # 1 of 3
    "WORSE2": (1, "PASS a\nFAIL b\nFAIL c\nFAIL d\n", ""),
    "WORSE3": (1, "FAIL a\n", ""),
    "LONG": (1, "FAIL x\n" * 30, ""),                                       # longest output, 0 of 30
    "SHORT": (1, "PASS a\nPASS b\nFAIL c\n", ""),                           # 2 of 3
})

# --fix-base latest: unchanged behaviour.
p.FIX_BASE = "latest"
st, _ = attempt(state, ["GOOD"])
st, upd = attempt(st, ["WORSE"])
checks += [
    ("latest: the next fix starts from this attempt's best", upd["code"] == "WORSE"
     and upd["error"] == "error of WORSE"),
    ("latest: the furthest is still tracked for the final file", upd["furthest"]["code"] == "GOOD"),
]

# --fix-base furthest: back to attempt 1's version, with a note on what attempt 2 tried.
p.FIX_BASE = "furthest"
st, _ = attempt(state, ["GOOD"])
st, upd = attempt(st, ["WORSE"])
checks += [
    ("furthest: a worse attempt sends the next fix back to attempt 1's version", upd["code"] == "GOOD"),
    ("furthest: its own failure report goes with it", upd["error"].endswith("error of GOOD")
     and upd["execution_output"].startswith("PASS a")),
    ("furthest: the note says what the worse attempt's best got", "error of WORSE" in upd["error"]
     and upd["error"].startswith("(This fix starts again from attempt 1's version")),
    ("furthest: one return counted", upd["furthest"]["returns"] == 1),
]
st, upd = attempt(st, ["WORSE2"])
checks.append(("furthest: a second return is allowed", upd["code"] == "GOOD" and upd["furthest"]["returns"] == 2))
st, upd = attempt(st, ["WORSE3"])
checks.append(("furthest: after two returns, the run carries on from its latest code",
               upd["code"] == "WORSE3" and upd["error"] == "error of WORSE3"))

# A better attempt replaces the furthest and resets the count.
OUTPUTS["BEST"] = (1, "PASS a\n" * 19 + "FAIL t\n", "")
st2, _ = attempt(state, ["GOOD"])
st2, upd = attempt(st2, ["WORSE"])
st2, upd = attempt(st2, ["BEST"])
checks.append(("furthest: a better candidate is fixed next, no note", upd["code"] == "BEST"
               and upd["error"] == "error of BEST" and upd["furthest"]["returns"] == 0))

# Within one attempt the ranking picks, not the length of the output.
st3, upd = attempt(state, ["LONG", "SHORT"])
p.FIX_BASE = "latest"
_, upd_latest = attempt(state, ["LONG", "SHORT"])
checks += [
    ("furthest: within an attempt, the higher share of passing checks is fixed", upd["code"] == "SHORT"
     and "This fix starts again" not in upd["error"]),
    ("latest: within an attempt, the longest output as before", upd_latest["code"] == "LONG"),
]

# The same code coming back (a re-test) is not a step back.
p.FIX_BASE = "furthest"
st4, _ = attempt(state, ["GOOD"])
OUTPUTS["GOOD"] = (1, "PASS a\nFAIL b\nFAIL c\n", "")          # the same code does worse under a new test
st4, upd = attempt(st4, ["GOOD"])
checks.append(("furthest: the same code re-tested keeps its new failure", upd["code"] == "GOOD"
               and upd["error"] == "error of GOOD"))

# The command line.
checks += [
    ("flag: latest by default", p.parse_args(["--goal", "g"]).fix_base == "latest"),
    ("flag: furthest when asked", p.parse_args(["--goal", "g", "--fix-base", "furthest"]).fix_base == "furthest"),
]

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(("PASS " if ok else "FAIL ") + name)
print("ALL PASS" if not failed else f"{len(failed)} FAILED")
sys.exit(1 if failed else 0)
