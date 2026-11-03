"""Set 4's big files (800-900 lines) on the 16k levels (fake LLM, no sandbox):
1. A failed run saves the tested candidate that got furthest, not the last attempt's code (toml on Low
   saved a version the static check had rejected: 271/1037, while attempt 1's scored 718/1037).
2. A standard-library module used as `name.attr` but never imported gets its import added (the same
   run lost both attempt-3 candidates to `re.` calls without `import re`).
3. Module-level functions that only raise NotImplementedError are rejected as placeholders (pyexpr
   on High tested a 767-line file whose `evaluate` and `_main` were placeholders, nine times).
4. Edits keep 4,000 tokens for the answer when thinking (with 1,500, pyexpr on High thought 5-7k
   tokens of an 8.3k room and 28 of 36 edit replies were cut off before one complete edit)."""
import os
import shutil
import sys

sys.path.insert(0, r"Z:\workspace")
os.chdir(r"Z:\workspace")
import config  # noqa: E402
import run_langgraph_pipeline as p  # noqa: E402

checks = []

# --- 2. Missing standard-library imports -------------------------------------------------------
DOC = '"""Parser."""\n\n\ndef split(s):\n    return re.split(r",", s)\n\n\nif __name__ == "__main__":\n    print(split("a,b"))\n'
fixed, added = p.add_missing_imports(DOC, "t.py")
checks += [
    ("import: re added", added == ["re"]),
    ("import: placed right after the docstring", fixed.startswith('"""Parser."""\nimport re\n')),
    ("import: the result passes the static check", p.static_problems(fixed, "t.py") == []),
]
fixed, added = p.add_missing_imports("import sys\n\n\ndef f(tok):\n    return token.type + sys.maxsize\n", "t.py")
checks.append(("import: a misspelt variable named like a module (token.type) is left for the static check",
               added == [] and p.static_problems(fixed, "t.py")))
fixed, added = p.add_missing_imports("def f():\n    return numpy.array([1])\n", "t.py")
checks.append(("import: not a standard-library module, nothing added", added == []))
fixed, added = p.add_missing_imports("#!/usr/bin/env python3\n# a tool\ndef f():\n    return math.pi\n", "t.py")
checks.append(("import: after a shebang and leading comments",
               added == ["math"] and fixed.splitlines()[:3] == ["#!/usr/bin/env python3", "# a tool", "import math"]))
fixed, added = p.add_missing_imports('"""D."""\nfrom __future__ import annotations\n\n\ndef f():\n'
                                     '    return json.dumps({}) + string.digits\n', "t.py")
checks.append(("import: after `from __future__`, several at once",
               added == ["json", "string"] and fixed.splitlines()[1:4]
               == ["from __future__ import annotations", "import json", "import string"]))
same = "import re\n\n\ndef f(s):\n    return re.escape(s)\n"
checks.append(("import: nothing missing, code unchanged", p.add_missing_imports(same, "t.py") == (same, [])))

# --- 3. Placeholder functions -------------------------------------------------------------------
STUB = ('"""Evaluator."""\nimport sys\n\n\ndef _tokens(s):\n    return s.split()\n\n\ndef evaluate(expr):\n'
        '    """Evaluate."""\n    raise NotImplementedError("internal error")\n\n\ndef _main():\n'
        '    raise NotImplementedError\n\n\nif __name__ == "__main__":\n    sys.exit(_main())\n')
ABSTRACT = ('class Node:\n    def ev(self):\n        raise NotImplementedError\n\n\nclass Num(Node):\n'
            '    def __init__(self, v):\n        self.v = v\n\n    def ev(self):\n        return self.v\n')
PARTIAL = 'def compile_expr(s):\n    if not s:\n        return None\n    raise NotImplementedError("too hard")\n'
checks += [
    ("placeholder: module-level stubs found", p.placeholder_functions(STUB) == ["evaluate", "_main"]),
    ("placeholder: an abstract method is a normal design", p.placeholder_functions(ABSTRACT) == []),
    ("placeholder: a function with real code before the raise is not a placeholder",
     p.placeholder_functions(PARTIAL) == []),
]

# --- engineer_node with a fake model ------------------------------------------------------------
calls, replies = [], {"Engineer": [], "Engineer, edits": []}


def fake(label, system, blocks, want_out, min_out, temperature=None, think=False, n=1, answer_min=None,
         with_reasoning=False, **kw):
    calls.append({"label": label, "think": think, "answer_min": answer_min, "want_out": want_out})
    if label == "Engineer, edits" and replies.get("edits_too_small"):
        raise p.ContextTooSmall("tiny")
    out = (replies[label] * n)[:n]
    return [r if with_reasoning else r[:2] for r in out]


p.llm_complete = fake
p.report = lambda *a, **k: None
p.prewarm_containers = lambda *a, **k: None
p.discard_containers = lambda *a, **k: None
p.write_test = lambda st, role: ""
p.write_probe = lambda st: ""
RUN = "unit-bigfile"
run_dir = os.path.join(config.RUNS_DIR, RUN)
shutil.rmtree(run_dir, ignore_errors=True)
state = {"run_id": RUN, "task_key": "t", "attempt": 1, "max_attempts": 3, "target_file": "f.py",
         "goal": "g", "plan": "p", "spec": "s", "interface": "split(s)", "checks": ["c"],
         "error": "", "failure_kind": "", "code": "", "num_candidates": 2,
         "think_engineer": "retries", "diverse": False, "lvl": config.level_settings("low"), "tests": {},
         "test_checks": {}, "test_feedback": {}, "probe": "", "regression": [], "attachments": "",
         "web_brief": "", "research_brief": "", "memory_context": "", "existing_code": "", "tester": False,
         "candidates": [], "allow_network": False, "started": 0, "time_limit_s": 1, "repeat_tests": 1,
         "probe_verdicts": {}, "best_passed": {}, "furthest": {}, "status": "", "verdict": "",
         "execution_stderr": ""}
NEEDS_RE = ("```python\nimport sys\n\n\ndef split(s):\n    return re.split(',', s)\n\n\nif __name__ == '__main__':\n"
            "    if sys.argv[1:] == ['--test']:\n        print('PASS' if split('a,b') == ['a', 'b'] else 'FAIL')\n```")
STUB_REPLY = "```python\n" + STUB.replace('sys.exit(_main())', "sys.exit(_main()) if '--test' else 0") + "```"
replies["Engineer"] = [(NEEDS_RE, "stop", "notes"), (STUB_REPLY, "stop", "notes")]
cands = {c["k"]: c for c in p.engineer_node(state)["candidates"]}
checks += [
    ("engineer: the candidate missing `import re` is coded, with the import added",
     cands[1]["status"] == "coded" and "\nimport re\n" in "\n" + cands[1]["code"]),
    ("engineer: the staged file has the import too",
     "import re" in open(os.path.join(run_dir, "a1c1", "f.py"), encoding="utf-8").read()),
    ("engineer: the placeholder candidate is rejected with the names",
     cands[2]["status"] == "static" and "evaluate, _main" in cands[2]["error"]
     and "NotImplementedError" in cands[2]["error"]),
]

# --- 4. Room for the edits ----------------------------------------------------------------------
GOOD_EDIT = "<<<<<<< SEARCH\n    return v + 2\n=======\n    return v + 1\n>>>>>>> REPLACE"
replies["Engineer, edits"] = [(GOOD_EDIT, "stop", "notes")]
prev = "import sys\n\n\ndef bump(v):\n    return v + 2\n\n\nif __name__ == '__main__':\n    print('--test')\n"
calls.clear()
p.engineer_edits(dict(state, code=prev, attempt=2), "sys", [p.block("Goal:", "g"), p.block("Instructions:", "x")], True, 1)
p.engineer_edits(dict(state, code=prev, attempt=2), "sys", [p.block("Goal:", "g"), p.block("Instructions:", "x")], False, 1)
checks += [
    ("edits: thinking keeps 4,000 tokens for the answer", calls[0]["think"] and calls[0]["answer_min"] == 4000),
    ("edits: without thinking, the answer floor stays 1,500", not calls[1]["think"] and calls[1]["answer_min"] == 1500),
]

# --- 1. The furthest candidate becomes the final file of a failed run ---------------------------
def ran(k, code, rc, out, tests_out=None):
    return {"k": k, "code": code, "rc": rc, "stdout": out, "tests_out": tests_out or {}}


a1 = ran(1, "A1", 1, "PASS a\n" * 13 + "FAIL b: got 1, expected 2\n")      # 13 of 14 own checks
a2 = ran(1, "A2", 1, "PASS a\nFAIL b\nFAIL c\nFAIL d\n")                  # 1 of 4
rank_a1, rank_a2 = p.progress(a1)[0], p.progress(a2)[0]
own_ok = ran(2, "B", 0, "PASS a\n", {"acceptance": (1, "FAIL x", "", 1.0)})
both_ok = ran(3, "C", 0, "PASS a\n", {"acceptance": (0, "PASS x", "", 1.0)})
checks += [
    ("progress: a higher share of own checks ranks higher", rank_a1 > rank_a2),
    ("progress: passing its own test beats any share", p.progress(own_ok)[0] > rank_a1),
    ("progress: then the independent tests it passed", p.progress(both_ok)[0] > p.progress(own_ok)[0]),
]
crash = dict(ran(1, "CR", 1, "PASS a\n"), stderr="Traceback (most recent call last):\n  ...\nTypeError: x\n")
two_of_three = ran(2, "TT", 1, "PASS a\nPASS b\nFAIL c: got 4, want -4\n")
silent = ran(3, "SI", 1, "PASS a\nPASS b\n")
timeout = ran(4, "TI", 124, "PASS a\nPASS b\nFAIL c\n")
checks += [
    ("progress: one PASS then a crash ranks below 2 of 3 (pyexpr on Low)",
     p.progress(two_of_three)[0] > p.progress(crash)[0] and p.progress(crash)[1:] == (1, 1)),
    ("progress: an error exit with only PASS lines counts one failure", p.progress(silent)[1:] == (2, 1)),
    ("progress: a timeout counts one more failure", p.progress(timeout)[1:] == (2, 2)),
]
far = p.furthest_so_far(dict(state, attempt=1), [a1])
far = p.furthest_so_far(dict(state, attempt=2, furthest=far), [a2])
checks.append(("furthest: a worse later attempt keeps attempt 1's", far["attempt"] == 1 and far["code"] == "A1"
               and (far["passes"], far["fails"]) == (13, 1)))
tie = p.furthest_so_far(dict(state, attempt=3, furthest=far), [dict(a1, code="A3")])
checks.append(("furthest: a tie goes to the later attempt", tie["attempt"] == 3 and tie["code"] == "A3"))
untested = p.furthest_so_far(dict(state, attempt=4, furthest=far), [dict(both_ok, code="")])
checks.append(("furthest: a candidate without code is never kept", untested["code"] == "A1"))

# The executor passes it on.
p.run_candidate = lambda st, c: dict(c, rc=1, stdout="PASS a\nFAIL b\nFAIL c\n", stderr="", tests_out={},
                                     exec_ok=False, exec_error="FAIL b", failed_test="", indep_failed=False,
                                     indep_stdout="", elapsed=1.0)
ex_state = dict(state, attempt=2, furthest=far, candidates=[{"k": 1, "code": "WORSE", "status": "coded"}])
upd = p.sandbox_executor_node(ex_state)
checks.append(("executor: a worse attempt fails but keeps the furthest candidate",
               upd["status"] == "FAILED" and upd["code"] == "WORSE" and upd["furthest"]["code"] == "A1"))

# finalize_node writes it.
p.run_stats = lambda st: {}
os.makedirs(run_dir, exist_ok=True)
p.finalize_node(dict(state, status="FAILED", code="WORSE", attempt=4, error="FAIL b", verdict="v", furthest=far))
final = open(os.path.join(run_dir, "final_f.py"), encoding="utf-8").read()
checks.append(("finalize: a failed run saves the furthest candidate", final.strip() == "A1"))
p.finalize_node(dict(state, status="FAILED", code="A1", attempt=4, error="FAIL b", verdict="v", furthest=far))
checks.append(("finalize: the same code, nothing to say", open(os.path.join(run_dir, "final_f.py"),
                                                                encoding="utf-8").read().strip() == "A1"))
p.finalize_node(dict(state, status="FAILED", code="LAST", attempt=4, error="", verdict="v", furthest={}))
checks.append(("finalize: nothing tested, the last code as before",
               open(os.path.join(run_dir, "final_f.py"), encoding="utf-8").read().strip() == "LAST"))
shutil.rmtree(run_dir, ignore_errors=True)

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(("PASS " if ok else "FAIL ") + name)
print("ALL PASS" if not failed else f"{len(failed)} FAILED")
sys.exit(1 if failed else 0)
