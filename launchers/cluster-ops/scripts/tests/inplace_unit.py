"""A blamed independent test is fixed with small SEARCH/REPLACE edits, so the checks that already
passed can't change; a fix that doesn't apply falls back to a full rewrite (fake LLM)."""
import os
import sys

sys.path.insert(0, r"Z:\workspace")
os.chdir(r"Z:\workspace")
import config  # noqa: E402
import run_langgraph_pipeline as p  # noqa: E402

ok = True


def check(name, cond):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name)


# --- apply_edits on its own ---
TEXT = "a = 1\nb = 2   \nc = 3\n"
new, n, prob = p.apply_edits(TEXT, "<<<<<<< SEARCH\na = 1\n=======\na = 10\n>>>>>>> REPLACE")
check("exact edit applies", (new, n, prob) == ("a = 10\nb = 2   \nc = 3\n", 1, ""))
new, n, prob = p.apply_edits(TEXT, "```\n<<<<<<< SEARCH\nb = 2\nc = 3\n=======\nb = 20\nc = 3\n>>>>>>> REPLACE\n```")
check("edit ignoring trailing spaces applies", new == "a = 1\nb = 20\nc = 3\n" and not prob)
new, n, prob = p.apply_edits(TEXT, "<<<<<<< SEARCH\nb = 2\n=======\n>>>>>>> REPLACE")
check("empty replacement deletes the lines", new == "a = 1\nc = 3\n" and not prob)
_, _, prob = p.apply_edits("x\nx\n", "<<<<<<< SEARCH\nx\n=======\ny\n>>>>>>> REPLACE")
check("ambiguous edit is refused", "2 places" in prob)
_, _, prob = p.apply_edits(TEXT, "Here is the whole test again: ...")
check("reply without edits is refused", "without any edit" in prob)

# --- write_test with a diagnosis: one in-place call, the other checks untouched ---
OLD = ("CASES = [('1+2', 3), ('10-2*3+4*5-6', 9), ('7/2', 3)]\n"
       "bad = 0\nfor e, want in CASES:\n    got = target_eval(e)\n"
       "    print('PASS:' if got == want else 'FAIL:', e, 'expected', want, 'got', got)\n"
       "    bad += got != want\nsys.exit(1 if bad else 0)\n")
EDIT = ("<<<<<<< SEARCH\nCASES = [('1+2', 3), ('10-2*3+4*5-6', 9), ('7/2', 3)]\n=======\n"
        "CASES = [('1+2', 3), ('10-2*3+4*5-6', 18), ('7/2', 3)]\n>>>>>>> REPLACE")
REWRITE = "```python\nimport sys\nprint('PASS: rewritten')\nsys.exit(0)\n```"
replies, seen = [], []


def fake_chat(label, system, blocks, want_out, min_out, temperature=None, think=False, think_tokens=None):
    seen.append({"think": think, "titles": [b["title"] for b in blocks]})
    return replies[len(seen) - 1], "stop"


p.llm_chat = fake_chat
target = "calc.py"
state = {"target_file": target, "goal": "g", "spec": "", "checks": ["c"], "interface": "evaluate(expr)",
         "tests": {"adversarial": p.test_header(target) + "import sys\ntarget_eval = lambda e: 0\n" + OLD},
         "test_feedback": {"adversarial": "The test expected 9 for 10-2*3+4*5-6; the right value is 18. BLAME: test"},
         "test_checks": {}, "lvl": config.level_settings("max"), "allow_network": False,
         "error": "FAIL: 10-2*3+4*5-6 expected 9 got 18"}
replies[:] = [EDIT]
full = p.write_test(state, "adversarial")
body = full[len(p.test_header(target)):]
check("in-place fix used one call, without thinking", len(seen) == 1 and seen[0]["think"] is False)
check("fixed value is in the test", "('10-2*3+4*5-6', 18)" in body)
check("everything else is byte-for-byte the same",
      body.replace("18)", "9)", 1) == state["tests"]["adversarial"][len(p.test_header(target)):])

# --- an edit that doesn't match falls back to the full rewrite ---
seen.clear()
replies[:] = ["<<<<<<< SEARCH\nnot in the test\n=======\nx\n>>>>>>> REPLACE", REWRITE]
full = p.write_test(state, "adversarial")
check("unmatched edit falls back to a rewrite", len(seen) == 2 and "rewritten" in full and seen[1]["think"])

# --- without a diagnosis there's no in-place attempt ---
seen.clear()
replies[:] = [REWRITE]
p.write_test(dict(state, test_feedback={}), "adversarial")
check("no diagnosis -> straight to the normal update", len(seen) == 1 and seen[0]["think"])
print("ALL PASS" if ok else "SOME FAILED")
