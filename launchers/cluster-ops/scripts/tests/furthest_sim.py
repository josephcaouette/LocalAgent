"""What a failed run would have saved under the "furthest candidate" rule, against the reference score.

    python furthest_sim.py set4

Replays each run's pipeline.log (own-test exit code, which independent tests passed, PASS and FAIL
lines in the printed output) through run_langgraph_pipeline.progress(), the same ranking the pipeline
now uses, and looks the chosen candidate up in candidate_scores_<set>.json (score_candidates.py).
Prints, per run: the file it kept, the furthest candidate's score, and the best candidate's score.
The printed output is a tail (1,500 characters), so PASS/FAIL shares are approximate."""
import json
import os
import re
import sys

sys.path.insert(0, r"Z:\workspace")
os.chdir(r"Z:\workspace")
import config  # noqa: E402
import run_langgraph_pipeline as p  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ATTEMPT = re.compile(r"\(attempt (\d+)/\d+\)")
RESULT = re.compile(r"^\s*--- Candidate (\d+): exit code (-?\d+|-) after")
TEST = re.compile(r"^\s*The (.+?): (passed|FAILED)\s*$")


def replay(log_path):
    """[(attempt, k, candidate dict as progress() reads it)] in log order."""
    out, attempt, cur, section = [], 0, None, "own"
    for line in open(log_path, encoding="utf-8", errors="replace"):
        line = line.rstrip("\n")
        m = ATTEMPT.search(line)
        if m and line.startswith("[Node:"):
            attempt = int(m.group(1))
        m = RESULT.match(line)
        if m:
            rc = None if m.group(2) == "-" else int(m.group(2))
            cur = {"k": int(m.group(1)), "rc": rc, "stdout": "", "stderr": "", "tests_out": {}, "code": "x"}
            out.append((attempt, cur["k"], cur))
            section = "own"
            continue
        if cur is None:
            continue
        if line.startswith("[Node:"):
            cur = None
            continue
        m = TEST.match(line)
        if m:
            cur["tests_out"][m.group(1)] = (0 if m.group(2) == "passed" else 1, "", "", 0.0)
            section = "test"
        elif line.strip() == "stderr:":
            section = "stderr"
        elif section == "own":
            cur["stdout"] += line + "\n"
        elif section == "stderr":
            cur["stderr"] += line + "\n"
    return out


def main():
    set_ = sys.argv[1]
    with open(os.path.join(HERE, f"candidate_scores_{set_}.json"), encoding="utf-8") as f:
        runs = json.load(f)
    print(f"{'task':7} {'level':6} {'state':6} {'kept':>10} {'furthest':>18} {'best':>18}")
    for rid, run in runs.items():
        best = None
        for attempt, k, cand in replay(os.path.join(config.RUNS_DIR, rid, "pipeline.log")):
            rank = list(p.progress(cand)[0])
            if best is None or rank >= best[0]:
                best = (rank, f"a{attempt}c{k}")
        scores = {c: s for c, s in run["cands"].items() if re.fullmatch(r"\d+/\d+", s)}
        top = max(((int(s.split("/")[0]), c) for c, s in scores.items() if c != "final"), default=(None, "-"))
        far = f"{scores.get(best[1], '?')} ({best[1]})" if best else "-"
        kept = run["kept"][6:] if run["kept"].startswith("SCORE ") else run["kept"]
        total = next(iter(scores.values())).split("/")[1] if scores else "?"
        print(f"{run['task']:7} {run['level']:6} {run['state']:6} {kept:>10} {far:>18} "
              f"{str(top[0]) + '/' + total + ' (' + top[1] + ')':>18}")


if __name__ == "__main__":
    main()
