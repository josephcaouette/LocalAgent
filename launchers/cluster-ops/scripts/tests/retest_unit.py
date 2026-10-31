"""Unit test of the re-test path (multi-test version) against the real Node 2 sandbox."""
import os
import sys

sys.path.insert(0, r"Z:\workspace")
os.chdir(r"Z:\workspace")
import config  # noqa: E402
import run_langgraph_pipeline as p  # noqa: E402

run_id = p.new_run_id()
target = "add_two.py"
code = ("import sys\n\ndef add(a, b):\n    return a + b\n\nif __name__ == '__main__':\n"
        "    if '--test' in sys.argv:\n        assert add(2, 3) == 5\n        print('PASS: add')\n")
broken = code.replace("return a + b", "return a - b")
wrong_test = p.test_header(target) + "assert target.add(1, 1) == 3, 'wrong expectation'\n"
good_test = p.test_header(target) + "import target as t2\nassert t2.add(1, 1) == 2\nprint('PASS: 1 + 1')\n"
state = {"run_id": run_id, "task_key": "workflow:task:" + run_id, "attempt": 2, "max_attempts": 10,
         "target_file": target, "allow_network": False, "num_candidates": 3, "repeat_tests": 2,
         "lvl": config.level_settings("ultra"), "tester": True, "checks": ["add(2, 3) == 5"],
         "retests_used": 0, "interface": "add(a, b)", "spec": "", "tests": {"acceptance": wrong_test},
         "test_checks": {"acceptance": ["add(2, 3) == 5"]}, "test_feedback": {"acceptance": "the expectation was wrong"},
         "failed_test": "acceptance", "regression": [], "probe": "", "probe_verdicts": {},
         "candidates": [{"k": 1, "code": code, "status": "coded", "error": "", "failed_test": "acceptance"},
                        {"k": 2, "code": code, "status": "coded", "error": "", "failed_test": "acceptance"},
                        {"k": 3, "code": broken, "status": "coded", "error": "", "failed_test": "self"}]}
for k, c in ((1, code), (2, code), (3, broken)):                # attempt 1's staged files
    d = p.cand_dir(state, 1, k)
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, target), "w", newline="\n").write(c)
p.write_test = lambda st, role="acceptance": good_test          # the "corrected" test (uses `import target`)
p.report = lambda *a, **k: None
result = p.retest_node(state)
print("status:", result.get("status"), "| retest flag:", result.get("retest"), "| retests_used:",
      result.get("retests_used"), "| feedback cleared:", "acceptance" not in result.get("test_feedback", {}))
for c in result.get("candidates", []):
    print(f"  candidate {c['k']}: status={c['status']} exec_ok={c.get('exec_ok')} self rc={c.get('rc')} "
          f"tests={ {r: o[0] for r, o in c.get('tests_out', {}).items()} }")
print("route:", p.route_after_retest(dict(state, **result)))
p._cleanup_pool.shutdown(wait=True)
left = p.run_ssh(f"docker ps -a --filter name=agent-{run_id} --format '{{{{.Names}}}}'", 30).stdout.strip()
print("containers left:", left or "none")
