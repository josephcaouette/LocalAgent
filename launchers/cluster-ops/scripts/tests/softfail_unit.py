"""A test that prints FAIL lines but exits 0 counts as failed (no sandbox, no LLM)."""
import os
import subprocess
import sys

sys.path.insert(0, r"Z:\workspace")
os.chdir(r"Z:\workspace")
import config  # noqa: E402
import run_langgraph_pipeline as p  # noqa: E402

for out in ["PASS: a\nPASS: b\n", "PASS: a\nFAIL: reference match for 0 9-17/2 * * * ref=[19:00]\n",
            "  FAILED test_x\n", "Summary\nFAILED: 0\nFAIL = 0\n", "PASS: handles FAIL input\nFAILURES: none\n",
            "fail: lower case is not our convention\n"]:
    print(repr(out[:45]).ljust(50), "->", "FAILED" if p.reported_failures(out, "The test") else "ok")

# run_all_tests: own --test passes, the acceptance test exits 0 with a FAIL line.
outputs = {"--test": (0, "PASS: own\n"), "acceptance_test.py": (0, "PASS: x\nFAIL: y expected 1, got 2\n")}
p.run_in_box = lambda st, box, args, *a, **k: subprocess.CompletedProcess(
    args, *outputs["--test" if "--test" in " ".join(args) else "acceptance_test.py"], "")
state = {"run_id": "t", "target_file": "x.py", "lvl": config.level_settings("ultra")}
err, role, _ = p.run_all_tests(state, "b", "x.py", [("acceptance", "acceptance_test.py")])
print("run_all_tests ->", role, "|", err.splitlines()[0][:110], "|", err.splitlines()[2][:60])
