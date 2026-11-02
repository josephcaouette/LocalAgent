"""What each Ultra or MAX run did, side by side: the reference score, cost, and which of the extra
mechanisms fired and whether they changed anything (adversarial tests, critics' proven findings,
head-to-head, mutation testing, re-tests, the stuck note). Reads a battery results file, or run ids.
Usage: python umax_report.py battery_results_set3_umax.json | python umax_report.py RUN_ID ..."""
import json
import os
import re
import sys

sys.path.insert(0, r"Z:\workspace")
import config  # noqa: E402

PATTERNS = {
    "indep_fail": r"The independent acceptance test: FAILED",
    "adv_fail": r"The adversarial test: FAILED",
    "adv_pass": r"The adversarial test: passed",
    "blame_script": r"blame: (script|code)\)",
    "blame_test": r"blame: (test|expectation)\)",
    "blame_both": r"blame: both\)",
    "retest": r"\[Node: Retest|re-test(ing)? the same",
    "head_to_head": r"Head-to-head: candidate \d+ is more likely right",
    "critic_round": r"\[Node: Critic\]",
    "finding_real": r"Referee: finding \d+ is REAL",
    "finding_not": r"Referee: finding \d+ is not shown",
    "disputes": r"disagree on probe|DISPUTE|disputed probe",
    "stuck_note": r"asking for a decision that sticks",
    "interface_fix": r"Added to the interface for every later step",
    "finish_notes": r"finishing them from their own notes",
}


def run_ids(args):
    if len(args) == 1 and args[0].endswith(".json"):
        rows = json.load(open(args[0], encoding="utf-8"))
        return [(r["run_id"], r.get("task"), r.get("level"), (r.get("check") or "").splitlines()[0:1]) for r in rows]
    return [(a, None, None, []) for a in args]


def report(run_id, task, level, check):
    log = open(os.path.join(config.RUNS_DIR, run_id, "pipeline.log"), encoding="utf-8", errors="replace").read()
    rec = config.get_redis(decode_responses=True).hgetall(config.TASK_KEY_PREFIX + run_id)
    tokens = sum(v.get("out", 0) for v in json.loads(rec.get("tokens") or "{}").values())
    row = {k: len(re.findall(p, log)) for k, p in PATTERNS.items()}
    mut = re.findall(r"-> (\d+) of (\d+) planted bugs caught", log)
    row.update(run=run_id, task=task or "?", level=level or rec.get("profile", "?"), status=rec.get("status"),
               attempt=rec.get("attempt"), minutes=round(float(rec.get("elapsed_s") or 0) / 60),
               tokens=tokens, mutation=f"{mut[-1][0]}/{mut[-1][1]}" if mut else "-",
               score=(check[0].replace("SCORE ", "") if check else "?"))
    return row


def main():
    rows = [report(*r) for r in run_ids(sys.argv[1:])]
    cols = [("task", 7), ("level", 6), ("status", 7), ("score", 12), ("attempt", 4), ("minutes", 4),
            ("tokens", 7), ("indep_fail", 5), ("adv_fail", 4), ("blame_test", 4), ("blame_script", 4),
            ("head_to_head", 3), ("critic_round", 3), ("finding_real", 4), ("mutation", 6), ("stuck_note", 3)]
    head = {"attempt": "att", "minutes": "min", "indep_fail": "indF", "adv_fail": "advF", "blame_test": "bT",
            "blame_script": "bS", "head_to_head": "h2h", "critic_round": "crit", "finding_real": "real",
            "mutation": "mut", "stuck_note": "stk"}
    print(" ".join(f"{head.get(c, c):>{w}}" for c, w in cols))
    for r in rows:
        print(" ".join(f"{str(r[c]):>{w}}" for c, w in cols))
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "umax_report_last.json"), "w",
              encoding="utf-8") as f:
        json.dump(rows, f, indent=1)


if __name__ == "__main__":
    main()
