"""Compare ways of ranking a failed run's candidates by its final independent tests, offline.

    python finalpick_metric.py set4_v2 set4_fb_high set4_v3_umax [--ratio R]

R defaults to the pipeline's FINAL_PICK_RATIO (0.8 since 2026-11-07; 0.7 before).

finalpick_sim.py saves, per failed run and candidate, (passes, fails, exit code) for each final test
(finalpick_<name>.json); score_candidates.py saves each candidate's reference score. The pipeline keeps
the candidate that got furthest and overrules it when its measure is under RATIO of the best one's.
  share  passes / (passes + fails), averaged over the tests: the pipeline's measure.
  reach  passes / the most checks that test printed for any candidate, averaged over the tests.
A test that stops early for one candidate prints fewer checks, so a broken candidate can show a large
share of very few: in set 4's third battery the evaluator on Ultra kept a candidate passing 68 of 85
checks (80%, 152 reference cases) over one passing 77 of 395 (19%, 946 cases). Reach fails the other
way when the test stops early for the right candidates (the second battery's struct on Ultra). On both
batteries' 11 failed runs: share 10,530, reach 10,642, of 11,716 (2026-11-05), so share stays.
Set 5's 4 failed runs (2026-11-06): share 3,519 at ratio 0.7 and 3,806 at 0.8, reach 3,643 and 3,930,
of 3,961; set 4 v3's picks are the same at 0.7-0.9. A run whose log has no 'Saving the candidate...'
line gets its furthest candidate replayed from the log (furthest_sim.replay). On 2026-11-07 the 9 failed
runs whose logs remain (set 4 v2 struct/max, v3, set 5) gave share 8,351 at 0.7 and 8,638 at 0.8 (only
set 5's fmtspec and inflate on Ultra switch), reach 9,136 and 9,423, best 9,613; the pipeline moved to 0.8."""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import furthest_sim  # noqa: E402  (also puts Z:\workspace on the path)

RUNS = r"Z:\runs"
FURTHEST = re.compile(r"Saving the candidate that got furthest as the final file \(attempt (\d+), candidate (\d+)")
ratio = (float(sys.argv[sys.argv.index("--ratio") + 1]) if "--ratio" in sys.argv
         else furthest_sim.p.FINAL_PICK_RATIO)
names = [a for a in sys.argv[1:] if not a.startswith("--") and not re.fullmatch(r"[\d.]+", a)]


def measures(per):
    """{name: {cand: value}} for each measure, from {cand: {test: (passes, fails, rc)}}."""
    tests = sorted({t for tv in per.values() for t in tv})
    reach = {t: max((sum(tv[t][:2]) for tv in per.values() if t in tv), default=0) for t in tests}
    out = {"share": {}, "reach": {}}
    for d, tv in per.items():
        out["share"][d] = sum(p / (p + f) if p + f else 0.0 for p, f, _rc in tv.values()) / len(tv)
        out["reach"][d] = sum(tv[t][0] / reach[t] if reach[t] else 0.0 for t in tv) / len(tv)
    return out


def order(d):
    return tuple(map(int, re.fullmatch(r"a(\d+)c(\d+)", d).groups()))


def replayed_furthest(log):
    """The furthest candidate by progress(), replayed from the log. The pipeline prints the 'Saving
    the candidate...' line only when that candidate isn't the last attempt's code, so set 5's fmtspec
    run on Ultra and inflate run on MAX have none."""
    best = None
    for attempt, k, cand in furthest_sim.replay(log):
        rank = furthest_sim.p.progress(cand)[0]
        if best is None or rank >= best[0]:          # a later candidate wins a tie, as in the pipeline
            best = (rank, f"a{attempt}c{k}")
    return best[1] if best else None


grand = {}
for name in names:
    per_run = json.load(open(os.path.join(HERE, f"finalpick_{name}.json"), encoding="utf-8"))
    scores = json.load(open(os.path.join(HERE, f"candidate_scores_{name}.json"), encoding="utf-8"))
    print(f"== {name}")
    for rid, per in per_run.items():
        sc = scores[rid]
        pts = {d: int(s.split("/")[0]) for d, s in sc["cands"].items() if re.fullmatch(r"\d+/\d+", s)}
        log = os.path.join(RUNS, rid, "pipeline.log")
        furthest = None
        if os.path.isfile(log):
            m = FURTHEST.search(open(log, encoding="utf-8", errors="replace").read())
            furthest = f"a{m.group(1)}c{m.group(2)}" if m else replayed_furthest(log)
        if furthest not in per:
            print(f"   {sc['task']:7}{sc['level']:6} furthest candidate unknown (log pruned or not saved); skipped")
            continue
        best = max(per, key=lambda d: pts.get(d, 0))
        row = [f"   {sc['task']:7}{sc['level']:6} furthest {furthest} {pts.get(furthest, 0):5}"]
        for mname, val in measures(per).items():
            top = max(per, key=lambda d: (val[d], order(d)))
            pick = furthest if val[furthest] >= ratio * val[top] else top
            grand.setdefault(mname, 0)
            grand[mname] += pts.get(pick, 0)
            row.append(f"{mname}: {pick} {pts.get(pick, 0):5}")
        grand.setdefault("furthest", 0)
        grand["furthest"] += pts.get(furthest, 0)
        grand.setdefault("best", 0)
        grand["best"] += pts.get(best, 0)
        print(" | ".join(row) + f" | best {best} {pts.get(best, 0)}")
print(f"totals at ratio {ratio}: " + ", ".join(f"{k} {v}" for k, v in grand.items()))
