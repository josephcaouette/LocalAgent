"""Where the dead-end restart would first fire, replayed on a battery's logs.

    python restart_sim.py set4_v2 [AFTER]       (AFTER: attempts without progress, default 3)

The pipeline counts the attempts in a row whose best candidate gets less far (progress()) than the
best of the current line of fixes, and after AFTER of them writes fresh candidates instead of fixing
that line again. This replays each run's pipeline.log (furthest_sim.replay) and prints the attempt
where the first restart would start, the run's outcome, and the best candidate score before that point
against the whole run's (candidate_scores_<name>.json). After a restart the run would differ, so only
the first point is meaningful."""
import json
import os
import re
import sys

from furthest_sim import HERE, config, p, replay

name = sys.argv[1]
after = int(sys.argv[2]) if len(sys.argv) > 2 else 3
runs = json.load(open(os.path.join(HERE, f"candidate_scores_{name}.json"), encoding="utf-8"))
print(f"{'task':7} {'level':6} {'state':6} {'attempts':>8}  first restart       best before / in all")
for rid, run in runs.items():
    by_attempt = {}
    for attempt, k, cand in replay(os.path.join(config.RUNS_DIR, rid, "pipeline.log")):
        by_attempt.setdefault(attempt, []).append((k, list(p.progress(cand)[0])))
    line_best, stall, fire = None, 0, None
    for attempt in sorted(by_attempt):
        top = max(rank for _k, rank in by_attempt[attempt])
        if line_best is not None and top < line_best:
            stall += 1
        else:
            stall, line_best = 0, top if line_best is None else max(line_best, top)
        if stall >= after:
            fire = attempt + 1
            break
    scores = {c: int(s.split("/")[0]) for c, s in run["cands"].items() if re.fullmatch(r"\d+/\d+", s) and c != "final"}
    before = max((v for c, v in scores.items() if fire and int(re.match(r"a(\d+)", c).group(1)) < fire), default=None)
    last = max(by_attempt) if by_attempt else 0
    where = f"attempt {fire}" if fire else "never"
    print(f"{run['task']:7} {run['level']:6} {run['state']:6} {last:>8}  {where:18}  "
          f"{before if before is not None else '-':>6} / {max(scores.values(), default='-')}")
