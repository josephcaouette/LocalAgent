"""Independent check of the agent's cron scripts against a brute-force minute-by-minute reference."""
import importlib.util
import sys
from datetime import datetime, timedelta

RANGES = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)]


def parse_field(text, lo, hi):
    values = set()
    for part in text.split(","):
        step = 1
        if "/" in part:
            part, step = part.split("/")
            step = int(step)
        if part == "*":
            a, b = lo, hi
        elif "-" in part:
            a, b = map(int, part.split("-"))
        else:
            a = b = int(part)
        values.update(range(a, b + 1, step))
    return values


def reference(expr, start, count=5):
    f = expr.split()
    mins, hours, doms, months, dows = (parse_field(x, *r) for x, r in zip(f, RANGES))
    dows = {d % 7 for d in dows}
    dom_star, dow_star = f[2].startswith("*"), f[4].startswith("*")   # Vixie cron's rule
    t = start.replace(second=0, microsecond=0) + timedelta(minutes=1)
    out = []
    while len(out) < count:
        dom_ok = t.day in doms
        dow_ok = (t.weekday() + 1) % 7 in dows
        if dom_star and dow_star:
            day_ok = True
        elif dom_star:
            day_ok = dow_ok
        elif dow_star:
            day_ok = dom_ok
        else:
            day_ok = dom_ok or dow_ok
        if t.minute in mins and t.hour in hours and t.month in months and day_ok:
            out.append(t)
        t += timedelta(minutes=1)
    return out


def load(path):
    spec = importlib.util.spec_from_file_location("cron_mod", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["cron_mod"] = mod
    spec.loader.exec_module(mod)
    return mod


EXPRS = ["*/15 8-10 * * 1-5", "0 0 1,15 * 1", "0 0 29 2 *", "30 4 1-7 * 0", "5 */6 * * *",
         "0 12 * 6-8 6,7", "59 23 31 * *", "0 0 * * *", "*/7 * * * *", "0 9-17/2 * * 1-5",
         "0 0 13 * 5", "15 14 1 * *", "0 22 * * 1-5", "23 0-20/2 * * *"]
STARTS = [datetime(2024, 1, 1, 0, 0, 0), datetime(2024, 2, 28, 23, 59, 30), datetime(2025, 12, 31, 23, 59, 0)]

for path in sys.argv[1:]:
    mod = load(path)
    fn = getattr(mod, "next_runs", None) or getattr(mod, "next_run_times", None)
    if fn is None:
        print(f"{path}: no next_runs(); skipping")
        continue
    good = bad = 0
    for expr in EXPRS:
        for start in STARTS:
            want = reference(expr, start)
            try:
                got = [g.replace(second=0, microsecond=0) for g in fn(expr, start, 5)]
            except TypeError:
                got = [g.replace(second=0, microsecond=0) for g in fn(expr, start)]
            except Exception as e:
                got = f"error: {e}"
            if got == want:
                good += 1
            else:
                bad += 1
                if bad <= 4:
                    print(f"  MISMATCH {expr!r} from {start}: got {got if isinstance(got, str) else [str(g) for g in got]}"
                          f"\n           want {[str(w) for w in want]}")
    print(f"{path}: {good} of {good + bad} cases match the reference")
