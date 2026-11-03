"""Live replay (Node 1, 16k server) of an edit request whose replies didn't apply. In the High re-run of
set 4's struct task (run 20261103-011823), 21 of the fix replies had an edit that "matches 0 places".
The pipeline didn't keep those replies, so this sends the same kind of request again (the run's goal,
plan, checks and interface, the candidate it fixed and its failure) and shows, for every SEARCH part
that doesn't match, the closest place in the file and how the two differ.

    python edits_live.py [RUN] [CAND] [N]      (defaults: 20261103-011823 a4c4 4)

About 2-4 minutes with Node 1 free. Replies are saved under %TEMP%\\agent_tests\\edits_live\\."""
import difflib
import json
import os
import re
import sys

sys.path.insert(0, r"Z:\workspace")
os.chdir(r"Z:\workspace")
import config  # noqa: E402
import run_langgraph_pipeline as p  # noqa: E402

p.report = lambda *a, **k: None
args = sys.argv[1:]
RUN = args[0] if args else "20261103-011823"
CAND = args[1] if len(args) > 1 else "a4c4"
N = int(args[2]) if len(args) > 2 else 4
OUT = os.path.join(os.environ.get("TEMP", "."), "agent_tests", "edits_live")
os.makedirs(OUT, exist_ok=True)

rec = config.get_redis(decode_responses=True).hgetall(f"workflow:task:{RUN}")
target = rec["target_file"]
code = open(os.path.join(config.RUNS_DIR, RUN, CAND, target), encoding="utf-8").read().replace("\r\n", "\n")
code = code.rstrip("\n")
log = open(os.path.join(config.RUNS_DIR, RUN, "pipeline.log"), encoding="utf-8", errors="replace").read()
# The failure the fix was for: this candidate's test output and the diagnosis after it.
att, k = re.match(r"a(\d+)c(\d+)", CAND).groups()
start = log.find("Testing", log.find(f"(attempt {att}/"))
start = log.find(f"--- Candidate {k}:", start)
end = log.find("[Node: Engineer Coder]", start)
error = log[start:end].strip()

p.connect_llm()
p.THINK_TOKENS = config.level_settings(rec.get("profile") or "high")["think_tokens"]
state = {"target_file": target, "allow_network": False, "lvl": config.level_settings(rec.get("profile") or "high"),
         "code": code}
checks = p.numbered(json.loads(rec.get("checks") or "[]"))
blocks = [
    p.block("Goal:", rec["goal"]),
    p.block("Target file:", target),
    p.block("Acceptance checks (the --test run must demonstrate each one):", checks),
    p.block("Plan:", rec.get("plan", "")),
    p.block("Spec (reviewed; if it disagrees with the goal, the goal wins):", rec.get("spec", ""), trim=3),
    p.block("Interface (independent tests call the script this way; implement it exactly):", rec.get("interface", "")),
    p.block(f"The previous attempt failed (attempt {att}):", error, trim=2, keep="tail", min_chars=1500),
    p.block("Previous version:", code, code=True),
    p.block("Instructions:", "(replaced)"),
]
system = p.engineer_system(state)
print(f"{RUN}/{CAND}: {target}, {len(code.splitlines())} lines; context {p.CONTEXT_TOKENS}, thinking budget "
      f"{p.THINK_TOKENS}; asking for {N} replies...", flush=True)
calls, real_complete = [], p.llm_complete


def recording(*a, **k):
    replies = real_complete(*a, **k)
    calls.append((bool(k.get("think")), replies))
    return replies


p.llm_complete = recording
out, problems = p.engineer_edits(state, system, blocks, True, N)       # the pipeline's own edit step
first = calls[0][1]                                                     # the replies before any rescue


def exact_only(raw):
    """The rule before 2026-11-03: every SEARCH part matches one place exactly."""
    edits = p.EDIT_BLOCK.findall(raw)
    for search, _r in edits:
        search = search[:-1] if search.endswith("\n") else search
        want = [ln.rstrip() for ln in search.split("\n")]
        hits = sum(1 for s in range(len(lines) - len(want) + 1)
                   if [ln.rstrip() for ln in lines[s:s + len(want)]] == want) or code.count(search)
        if hits != 1:
            return False
    return bool(edits)


lines = code.split("\n")
stripped = [ln.strip() for ln in lines]


def why(search):
    """How a SEARCH part that matches nowhere differs from the closest place in the file."""
    want = search.split("\n")
    w_strip = [ln.strip() for ln in want]
    n = len(want)
    if any(stripped[i:i + n] == w_strip for i in range(len(lines) - n + 1)):
        return "indentation only (the lines match once leading spaces are ignored)"
    ws = [re.sub(r"\s+", " ", ln) for ln in w_strip]
    if any([re.sub(r"\s+", " ", ln) for ln in stripped[i:i + n]] == ws for i in range(len(lines) - n + 1)):
        return "spacing inside lines only"
    nonblank = [ln for ln in w_strip if ln]
    if nonblank != w_strip:
        body = "\n".join(stripped)
        if "\n".join(nonblank) in "\n".join(ln for ln in stripped if ln) and "\n".join(nonblank) not in body:
            return "blank lines differ only"
    best, at = 0.0, 0
    for i in range(0, max(1, len(lines) - n + 1)):
        r = difflib.SequenceMatcher(None, "\n".join(w_strip), "\n".join(stripped[i:i + n])).ratio()
        if r > best:
            best, at = r, i
    diff = list(difflib.unified_diff(lines[at:at + n], want, "file", "search", lineterm="", n=0))[2:14]
    missing = sum(1 for ln in w_strip if ln and ln not in stripped)
    return (f"closest place is line {at + 1} (similarity {best:.2f}); {missing} of {len(nonblank)} SEARCH lines "
            f"appear nowhere in the file:\n        " + "\n        ".join(diff))


for i, (raw, finish, notes) in enumerate(first, 1):
    with open(os.path.join(OUT, f"{RUN}_{CAND}_reply{i}.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write(f"=== finish: {finish}\n=== reasoning ({len(notes)} chars)\n{notes}\n=== answer\n{raw}")
for i, (raw, _f, _n) in enumerate(out, 1):
    if i not in problems:
        print(f"Reply {i}: applied")
        continue
    edits = p.EDIT_BLOCK.findall(raw)
    print(f"Reply {i}: {problems[i]} ({len(edits)} complete edit block(s), answer {len(raw)} chars)")
    for j, (search, _replace) in enumerate(edits, 1):
        search = search[:-1] if search.endswith("\n") else search
        if p.apply_edits(code, f"<<<<<<< SEARCH\n{search}\n=======\nx\n>>>>>>> REPLACE")[2]:
            print(f"    block {j} ({len(search.splitlines())} lines): " + why(search))
    if not edits:
        print("    answer starts: " + raw[:300].replace("\n", "\n    "))
rescued = sum(1 for think, _r in calls[1:] if not think)
print(f"\nBefore 2026-11-03 (exact matching, no rescue): {sum(exact_only(r) for r, _f, _n in first)} of {N} "
      f"replies applied. Now: {N - len(problems)} of {N} ({rescued} finished from their notes).")
print(f"Replies saved in {OUT}")
