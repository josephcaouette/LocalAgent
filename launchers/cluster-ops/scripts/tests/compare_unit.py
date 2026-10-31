import json, subprocess, sys
sys.path.insert(0, r"Z:\workspace")
import config, run_langgraph_pipeline as p
cases = ["('ok',)", "('bad msg',)", "('real bug',)"]
answers = {1: [1, "Error: invalid digit", 4], 2: [1, "error - digit not allowed", 5], 3: [1, "Error: bad", 4]}
def fake_run(state, attempt, k, args, env=None, workdir=None):
    out = "PROBE-CASES:" + json.dumps(cases) + "\nPROBE-RESULTS:" + json.dumps(answers[k]) + "\n"
    return subprocess.CompletedProcess(args, 0, out, "")
p.run_in_container = fake_run
calls = []
def fake_chat(label, system, blocks, **kw):
    calls.append(label)
    return json.dumps({"verdicts": [{"case": 1, "correct": "all", "reason": "message wording is not specified"},
                                    {"case": 2, "correct": "A", "reason": "4 is right"}]}), "stop"
p.llm_chat = fake_chat
state = {"attempt": 1, "goal": "g", "spec": "", "interface": "", "probe": p.test_header("t.py") + "CASES=[]\n",
         "target_file": "t.py", "probe_verdicts": {}, "lvl": config.level_settings("ultra")}
passed = [{"k": 1}, {"k": 2}, {"k": 3}]
errors, updates = p.compare_candidates(state, passed)
print("errors:", {k: v.splitlines()[1][:90] for k, v in errors.items()})
print("referee calls:", calls)
# A later attempt with the same answers: decided from the cache, no new referee call.
calls.clear()
errors2, _ = p.compare_candidates(dict(state, probe_verdicts=updates), passed)
print("from cache -> errors:", sorted(errors2), "| referee calls:", calls)
