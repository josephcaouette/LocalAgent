"""The day-of-month / day-of-week OR rule: 10 cases where a full-range field still counts as restricted."""
import sys
from datetime import datetime

sys.argv = sys.argv[:1] + []          # import the checker without running its main loop
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
paths = __import__("os").environ["CRON_PATHS"].split(";")
import cron_check as cc  # noqa: E402

EDGE = ["0 0 1-31 * 1", "0 0 15 * 0-6", "0 0 1-31 * *", "0 12 * * 0-7", "30 6 1,2,3 * 1-5"]
STARTS = [datetime(2024, 3, 9, 12, 0), datetime(2025, 6, 30, 23, 0)]
for path in paths:
    mod = cc.load(path)
    fn = getattr(mod, "next_runs", None) or getattr(mod, "next_run_times")
    ok = 0
    for expr in EDGE:
        for s in STARTS:
            want = cc.reference(expr, s)
            try:
                got = [g.replace(second=0, microsecond=0) for g in fn(expr, s, 5)]
            except Exception as e:
                got = f"error: {e}"
            if got == want:
                ok += 1
            else:
                print(f"  MISMATCH {expr!r} from {s}: got {got if isinstance(got, str) else [str(g) for g in got]}")
    print(f"{path}: {ok} of {len(EDGE) * len(STARTS)} restriction cases match")
