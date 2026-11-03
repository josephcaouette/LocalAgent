"""Fix replies made of SEARCH/REPLACE edits that didn't apply (fake LLM, no sandbox). In set 4's High
re-run (16k server, 680-900-line files) most fixes failed this way. A live replay of four fix replies
for the struct candidate a4c4 (edits_live.py) showed both kinds: two replies thought past their small
budget (about 1,300 tokens) and used the whole answer without one edit block, and two replaced a whole
100-line function whose copy in SEARCH differed from the file in two comment lines. An attempt where
nothing applied then passed on only "your edits couldn't be applied", not the failure being fixed.
1. Loose matching (made-up file). 2. The two saved replies (tests/data/edits_case). 3. A reply cut off
while thinking is finished from its notes. 4. An attempt where nothing applied keeps its problem."""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, r"Z:\workspace")
os.chdir(r"Z:\workspace")
import config  # noqa: E402
import run_langgraph_pipeline as p  # noqa: E402

p.report = lambda *a, **k: None
checks = []


def edit(search, replace):
    return f"<<<<<<< SEARCH\n{search}\n=======\n{replace}\n>>>>>>> REPLACE"


# --- 1. Loose matching ------------------------------------------------------------------------------
BODY = ["    # scale (p-1) times, i.e. once per step", "    y = x * 2", "    z = y + 1", "    w = z - 3",
        "    v = w * w", "    u = v + y", "    t = u - z", "    s = t * 2", "    r = s + t", "    q = r - u",
        "    return q"]
FILE = "\n".join(["import sys", "", "", "class Packer:", "    def size(self, fmt):",
                  "        # count the bytes", "        total = 0", "        for ch in fmt:",
                  "            total += SIZES[ch]", "        return total", "", "",
                  "def helper_a(x):"] + BODY + ["", "", "def helper_b(x):"] + BODY + ["", "", "def last(x):",
                  "    return x"])


def run(reply):
    return p.apply_edits(FILE, reply)


new, n, problem = run(edit("        total = 0", "        total = 1"))
checks.append(("an exact SEARCH still applies as before", not problem and "        total = 1" in new))
# The model quoted a method as if it were at the top level, and wrote its replacement the same way.
new, n, problem = run(edit("def size(self, fmt):\n    # count the bytes\n    total = 0",
                           "def size(self, fmt):\n    # bytes\n    total = len(fmt)"))
checks.append(("a SEARCH with the wrong indentation applies, re-indented to fit",
               not problem and "    def size(self, fmt):\n        # bytes\n        total = len(fmt)\n        for ch" in new))
new, n, problem = run(edit("            total  +=  SIZES[ch]", "            total += SIZES.get(ch, 0)"))
checks.append(("extra spaces inside a line still find the line", not problem and "SIZES.get(ch, 0)" in new))
# A 13-line function copied with its comment retyped (as in the saved struct replies).
copied = ["def helper_a(x):", "    # scale (p - 1) times, i.e., once per step"] + BODY[1:]
new, n, problem = run(edit("\n".join(copied), "def helper_a(x):\n    return x * 4"))
checks.append(("a long SEARCH with one retyped comment line replaces exactly that function",
               not problem and "def helper_a(x):\n    return x * 4\n\n\ndef helper_b(x):\n" + BODY[0] in new
               and new.count("    return q") == 1))
new, n, problem = run(edit("\n".join(["def helper_a(x):"] + BODY[:4] + BODY[5:]), "def helper_a(x):\n    return 0"))
checks.append(("a long SEARCH with a line left out still finds its function",
               not problem and "def helper_a(x):\n    return 0\n\n\ndef helper_b" in new))
new, n, problem = run(edit("\n".join(["    # scale (p - 1) times, i.e., once per step"] + BODY[1:]), "    return 0"))
checks.append(("a near copy that fits two places equally is refused",
               problem == "has an edit that matches 0 places" and new == FILE))
new, n, problem = run(edit("def last(x):\n    return  x + 0\n", "def last(x):\n    return 1"))
checks.append(("a short SEARCH (under 3 lines) with a changed line is refused", bool(problem)))
new, n, problem = run(edit("        # count the bytes\n        totals = 0\n        for ch in fmt:",
                           "        total = 9"))
checks.append(("a 3-line SEARCH with one changed line is refused (too short to be sure)", bool(problem)))
new, n, problem = run(edit("    return q", "    return 0"))
checks.append(("a SEARCH found in two places is still refused", problem == "has an edit that matches 2 places"))
new, n, problem = run(edit("        total = 0", "        total = 1") + "\n" +
                      edit("\n".join(copied), "def helper_a(x):\n    return 5"))
checks.append(("an exact and a near edit in one reply both apply", not problem and n == 2
               and "total = 1" in new and "def helper_a(x):\n    return 5" in new))

# --- 2. The saved replies ---------------------------------------------------------------------------
case = os.path.join(HERE, "data", "edits_case")
code = open(os.path.join(case, "struct_high_fb.py"), encoding="utf-8").read().rstrip("\n")
lines = code.split("\n")
for i, start in ((3, 169), (4, 177)):              # where the closest place was (edits_live.py)
    reply = open(os.path.join(case, f"reply{i}.txt"), encoding="utf-8").read()
    (search, replace), = p.EDIT_BLOCK.findall(reply)
    exact = code.count(search.rstrip("\n"))
    new, n, problem = p.apply_edits(code, reply)
    try:
        compile(new, "struct_high_fb.py", "exec")
        compiles = True
    except SyntaxError:
        compiles = False
    checks += [
        (f"saved reply {i}: its SEARCH matches nowhere exactly", exact == 0),
        (f"  now applies ({len(search.splitlines())}-line SEARCH)", not problem and n == 1),
        ("  the lines before the function are unchanged", new.split("\n")[:start] == lines[:start]),
        ("  the replacement is in the file and it compiles", replace.strip().split("\n")[-1].strip() in new
         and compiles),
    ]

# --- 3. A reply cut off while still thinking ----------------------------------------------------------
PREV = "def bump(v):\n    return v + 2\n"
GOOD = edit("    return v + 2", "    return v + 1")
BAD = edit("    return v + 3", "    return v + 1")
calls, mode = [], {"first": [], "second": [(GOOD, "stop", "")]}


def fake(label, system, blocks, want_out, min_out, temperature=None, think=False, n=1, answer_min=None,
         with_reasoning=False, **kw):
    calls.append({"label": label, "think": think, "n": n, "titles": [b["title"] for b in blocks],
                  "notes": next((b["text"] for b in blocks if b["title"].startswith("Your notes")), "")})
    replies = mode["first"][:n] if len(calls) == 1 else mode["second"]
    return [r if with_reasoning else r[:2] for r in replies]


real_complete = p.llm_complete
p.llm_complete = fake
p.THINK_TOKENS = 10000
st = {"code": PREV}
mode["first"] = [("Need provide edits only. Let's deeply analyze the code...", "length", "thinking about bump"),
                 (GOOD, "stop", "notes"), ("Some reasoning\n" + GOOD + "\nmore reasoning, then cut", "length", "n")]
out, problems = p.engineer_edits(st, "sys", [p.block("Goal:", "g"), p.block("Instructions:", "x")], True, 3)
checks += [
    ("cut off while thinking: one more call, without thinking", len(calls) == 2 and calls[1]["think"] is False),
    ("  it gets the notes and the cut-off answer", "thinking about bump" in calls[1]["notes"]
     and "which was cut off" in calls[1]["notes"] and "deeply analyze" in calls[1]["notes"]),
    ("  and ends with the edit instructions", calls[1]["titles"][-1] == "Instructions:"),
    ("  a cut-off reply that has a complete edit keeps it (not redone)", problems == {} and len(out) == 3
     and all("return v + 1" in o[0] for o in out)),
]
calls.clear()
mode["first"] = [("Still thinking...", "length", "notes")]
out, problems = p.engineer_edits(st, "sys", [p.block("Instructions:", "x")], False, 1)
checks.append(("without thinking nothing is redone", len(calls) == 1 and 1 in problems))
calls.clear()
mode["first"] = [(BAD, "stop", "notes")]
out, problems = p.engineer_edits(st, "sys", [p.block("Instructions:", "x")], True, 1)
checks.append(("a reply whose edits failed is kept for model_reply.txt", out[0][0] == BAD and 1 in problems))

# --- 4. An attempt where nothing applied keeps the problem it was fixing ------------------------------
def fake_node(label, system, blocks, want_out, min_out, think=False, n=1, with_reasoning=False, **kw):
    if label == "Engineer":
        raise p.ContextTooSmall("the prompt needs 10921 tokens plus at least 10395 for the answer, but the "
                                "model's context window is 16384 tokens")
    return [(BAD, "stop", "notes")] * n


p.llm_complete = fake_node
p.prewarm_containers = lambda *a, **k: None
p.discard_containers = lambda *a, **k: None
p.write_test = lambda st, role: ""
p.write_probe = lambda st: ""
state = {"run_id": "unit-editmatch", "task_key": "t", "attempt": 6, "max_attempts": 10, "target_file": "f.py",
         "goal": "g", "plan": "p", "spec": "s", "interface": "bump(v)", "checks": ["c"],
         "error": "FAIL: bump(1) expected 2, got 3\nBLAME: code", "failure_kind": "runtime", "code": PREV,
         "num_candidates": 2, "think_engineer": "always", "diverse": False, "lvl": config.level_settings("high"),
         "tests": {}, "test_checks": {}, "test_feedback": {}, "probe": "", "regression": [], "attachments": "",
         "web_brief": "", "research_brief": "", "memory_context": "", "existing_code": "", "tester": False,
         "candidates": [], "allow_network": False, "started": 0, "time_limit_s": 1}
shutil.rmtree(os.path.join(config.RUNS_DIR, "unit-editmatch"), ignore_errors=True)
upd = p.engineer_node(state)
again = p.engineer_node(dict(state, attempt=7, error=upd["error"]))
saved = os.path.join(config.RUNS_DIR, "unit-editmatch", "a6c1", "model_reply.txt")
checks += [
    ("nothing applied: the next attempt still sees the failure it was fixing",
     upd["status"] == "FAILED" and "couldn't be applied" in upd["error"]
     and "The problem you were fixing:\nFAIL: bump(1) expected 2, got 3" in upd["error"]),
    ("  twice in a row: the problem is carried once, not nested",
     again["error"].count("The problem you were fixing") == 1 and "expected 2, got 3" in again["error"]),
    ("  the code to fix is still the previous version", upd["code"] == PREV),
    ("  the failed reply is saved for inspection", os.path.exists(saved) and BAD in open(saved, encoding="utf-8").read()),
]
shutil.rmtree(os.path.join(config.RUNS_DIR, "unit-editmatch"), ignore_errors=True)
p.llm_complete = real_complete

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(("PASS " if ok else "FAIL ") + name)
print("ALL PASS" if not failed else f"{len(failed)} FAILED")
sys.exit(1 if failed else 0)
