"""Reference checkers for the test battery. Run inside the sandbox (the module under test is
pipeline-written code):  python3 battery_checks.py TASK /work/<file>.py
Prints `SCORE passed/total` and up to 6 mismatches. TASK is glob, bowling, calc, topo or slots."""
import fnmatch
import heapq
import importlib.util
import random
import sys


def load(path):
    spec = importlib.util.spec_from_file_location("under_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def outcome(fn, *args):
    """('ok', value) or ('raise', exception class name, exception)."""
    try:
        return ("ok", fn(*args))
    except Exception as e:          # noqa: BLE001 - every exception is a result here
        return ("raise", type(e).__name__, e)


# ----------------------------------------------------------------------------- glob
def glob_cases(rng):
    cases = [("", ""), ("*", ""), ("?", ""), ("a*", "abc"), ("*c", "abc"), ("a?c", "abc"), ("a?c", "ac"),
             ("[abc]", "b"), ("[a-c]x", "bx"), ("[!a-c]", "d"), ("[!a-c]", "a"), ("[]]", "]"), ("[]a]", "a"),
             ("[!]a]", "b"), ("[!]a]", "]"), ("[", "["), ("[ab", "[ab"), ("[]", "[]"), ("a[b", "a[b"),
             ("*[!b]", "aab"), ("**a**", "a"), ("a*b*c", "aXbYc"), ("a*b*c", "aXcYb"), ("?*?", "a"),
             ("[a-a]", "a"), ("[!!]", "!"), ("[*]", "*"), ("[?]", "a"), ("a!b", "a!b")]
    for _ in range(3000):
        parts = []
        for _ in range(rng.randint(0, 5)):
            r = rng.random()
            if r < 0.35:
                parts.append(rng.choice("abc"))
            elif r < 0.55:
                parts.append("*")
            elif r < 0.7:
                parts.append("?")
            else:
                items = "".join(rng.choice(["a", "b", "c", "a-b", "b-c", "a-c"]) for _ in range(rng.randint(1, 2)))
                parts.append("[" + ("!" if rng.random() < 0.3 else "") + ("]" if rng.random() < 0.15 else "")
                             + items + "]")
        pat = "".join(parts)
        if rng.random() < 0.1 and "]" not in pat:
            pat += "[" + rng.choice(["", "a", "ab"])          # unclosed: a literal '['
        text = "".join(rng.choice("abc[]") for _ in range(rng.randint(0, 6)))
        cases.append((pat, text))
    return cases


def check_glob(mod, rng):
    results = []
    for pat, text in glob_cases(rng):
        want = fnmatch.fnmatchcase(text, pat)
        got = outcome(mod.match, pat, text)
        results.append((got[0] == "ok" and got[1] == want, f"match({pat!r}, {text!r}) -> {got[:2]}, expected {want}"))
    return results


# ----------------------------------------------------------------------------- bowling
def ref_bowling(rolls):
    def roll(i):
        if i >= len(rolls):
            raise ValueError("incomplete game")
        r = rolls[i]
        if not 0 <= r <= 10:
            raise ValueError("bad roll")
        return r
    total, i = 0, 0
    for frame in range(10):
        a = roll(i)
        if frame < 9:
            if a == 10:
                total += 10 + roll(i + 1) + roll(i + 2)
                i += 1
            else:
                b = roll(i + 1)
                if a + b > 10:
                    raise ValueError("frame over 10")
                total += a + b + (roll(i + 2) if a + b == 10 else 0)
                i += 2
        else:
            b = roll(i + 1)
            if a == 10:
                c = roll(i + 2)
                if b != 10 and b + c > 10:
                    raise ValueError("bonus over 10")
                total += a + b + c
                i += 3
            elif a + b > 10:
                raise ValueError("frame over 10")
            elif a + b == 10:
                total += 10 + roll(i + 2)
                i += 3
            else:
                total += a + b
                i += 2
    if i != len(rolls):
        raise ValueError("too many rolls")
    return total


def random_game(rng):
    rolls = []
    for frame in range(10):
        a = rng.choice([10, 10, rng.randint(0, 10)])
        if frame < 9:
            rolls += [10] if a == 10 else [a, rng.randint(0, 10 - a)]
        else:
            if a == 10:
                b = rng.choice([10, rng.randint(0, 10)])
                c = rng.randint(0, 10) if b == 10 else rng.randint(0, 10 - b)
                rolls += [10, b, c]
            else:
                b = rng.choice([10 - a, rng.randint(0, 10 - a)])
                rolls += [a, b] + ([rng.randint(0, 10)] if a + b == 10 else [])
    return rolls


def check_bowling(mod, rng):
    games = [[10] * 12, [5] * 21, [0] * 20, [9, 0] * 10, [10] * 9 + [5, 5, 10], [10] * 9 + [10, 5, 5],
             [10] * 9 + [10, 5, 6], [10] * 11, [10] * 13, [3, 8] + [0] * 18, [0] * 19, [0] * 21, [-1] + [0] * 19,
             [11] + [0] * 18, [0] * 18 + [5, 5], [0] * 18 + [7, 2, 1], [10] * 9 + [0, 10, 10]]
    for _ in range(1500):
        g = random_game(rng)
        r = rng.random()
        if r < 0.15 and g:
            g = g[:-1]                                   # incomplete
        elif r < 0.25:
            g = g + [rng.randint(0, 10)]                 # too many
        elif r < 0.35:
            i = rng.randrange(len(g))
            g = g[:i] + [rng.randint(0, 11)] + g[i + 1:]  # one roll changed (may stay valid)
        games.append(g)
    results = []
    for g in games:
        want = outcome(ref_bowling, list(g))
        got = outcome(mod.score, list(g))
        if want[0] == "ok":
            ok = got[0] == "ok" and got[1] == want[1]
            exp = want[1]
        else:
            ok = got[0] == "raise" and isinstance(got[2], ValueError)
            exp = "ValueError"
        results.append((ok, f"score({g}) -> {got[:2]}, expected {exp}"))
    return results


# ----------------------------------------------------------------------------- calc
def ref_calc(expr):
    toks, i = [], 0
    while i < len(expr):
        ch = expr[i]
        if ch.isspace():
            i += 1
        elif ch in "0123456789":
            j = i
            while j < len(expr) and expr[j] in "0123456789":
                j += 1
            toks.append(int(expr[i:j]))
            i = j
        elif ch in "+-*/()":
            toks.append(ch)
            i += 1
        else:
            raise ValueError("unknown character")
    pos = [0]

    def peek():
        return toks[pos[0]] if pos[0] < len(toks) else None

    def take():
        pos[0] += 1
        return toks[pos[0] - 1]

    def expr_():
        v = term()
        while peek() in ("+", "-"):
            v = v + term() if take() == "+" else v - term()
        return v

    def term():
        v = unary()
        while peek() in ("*", "/"):
            op = take()
            w = unary()
            if op == "*":
                v *= w
            else:
                if w == 0:
                    raise ZeroDivisionError("division by zero")
                q = abs(v) // abs(w)
                v = q if (v >= 0) == (w >= 0) else -q
        return v

    def unary():
        if peek() == "-":
            take()
            return -unary()
        return primary()

    def primary():
        t = peek()
        if isinstance(t, int):
            take()
            return t
        if t == "(":
            take()
            v = expr_()
            if peek() != ")":
                raise ValueError("unbalanced")
            take()
            return v
        raise ValueError("expected a number")

    if not toks:
        raise ValueError("empty")
    v = expr_()
    if pos[0] != len(toks):
        raise ValueError("unexpected token")
    return v


def random_expr(rng, depth=0):
    r = rng.random()
    if depth > 3 or r < 0.3:
        s = str(rng.randint(0, 40))
    elif r < 0.45:
        s = "-" + random_expr(rng, depth + 1)
    elif r < 0.6:
        s = "(" + random_expr(rng, depth + 1) + ")"
    else:
        s = random_expr(rng, depth + 1) + rng.choice(["+", "-", "*", "/"]) + random_expr(rng, depth + 1)
    return s


def spaced(rng, s):
    """Random spaces, never inside a number."""
    return "".join(c + (" " if not c.isdigit() and rng.random() < 0.25 else "") for c in s)


def check_calc(mod, rng):
    exprs = ["1+2*3", "(1+2)*3", "7/2", "-7/2", "7/-2", "-(2+1)", "2*-3", "--3", "2--3", "10/3*3", "1-2-3",
             "2*(3+4)*5", " 42 ", "", "()", "2+", "*2", "2-+3", "+3", "2(3)", "(2", "2)", "1/0", "5/(2-2)",
             "3 4", "2**3", "1.5+1", "abc", "-(-(-4))", "100/7/2", "-0", "0/-5"]
    for _ in range(1500):
        e = random_expr(rng)
        if rng.random() < 0.25:                     # a damaged version (may stay valid)
            i = rng.randrange(len(e) + 1)
            e = e[:i] + rng.choice(["", "+", "*", "(", ")", "-", " ", "x"]) + e[i + 1:]
        exprs.append(spaced(rng, e))
    results = []
    for e in exprs:
        want = outcome(ref_calc, e)
        got = outcome(mod.evaluate, e)
        if want[0] == "ok":
            ok = got[0] == "ok" and got[1] == want[1] and isinstance(got[1], int)
            exp = want[1]
        else:
            expected = ZeroDivisionError if want[1] == "ZeroDivisionError" else ValueError
            ok = got[0] == "raise" and isinstance(got[2], expected)
            exp = want[1]
        results.append((ok, f"evaluate({e!r}) -> {got[:2]}, expected {exp}"))
    # cross-check the reference itself against Python on expressions without division
    for e in exprs:
        if "/" not in e and outcome(ref_calc, e)[0] == "ok":
            assert ref_calc(e) == eval(e.replace("--", "- -")), e   # noqa: S307 - our own generated input
    return results


# ----------------------------------------------------------------------------- topo
def ref_topo(deps):
    nodes = set(deps) | {d for ds in deps.values() for d in ds}
    need = {n: set(deps.get(n, ())) for n in nodes}
    users = {n: set() for n in nodes}
    for n, ds in need.items():
        for d in ds:
            users[d].add(n)
    ready = [n for n in nodes if not need[n]]
    heapq.heapify(ready)
    order = []
    while ready:
        n = heapq.heappop(ready)
        order.append(n)
        for u in users[n]:
            need[u].discard(n)
            if not need[u]:
                heapq.heappush(ready, u)
    return order if len(order) == len(nodes) else None


def random_graph(rng, cyclic):
    names = list("abcdefgh")[:rng.randint(2, 8)]
    deps = {}
    for i, n in enumerate(names):
        pool = names[i + 1:] if not cyclic else names
        deps[n] = rng.sample(pool, rng.randint(0, min(3, len(pool)))) if pool else []
    if cyclic and ref_topo(deps) is not None:
        a, b = rng.sample(names, 2)
        deps[a] = deps[a] + ([b] if b not in deps[a] else [])
        deps[b] = deps[b] + ([a] if a not in deps[b] else [])
    for n in rng.sample(names, rng.randint(0, 2)):           # some appear only as dependencies
        if all(n not in v for k, v in deps.items() if k != n):
            continue
        deps.pop(n, None)
    return deps


def valid_cycle(deps, cyc):
    if not isinstance(cyc, (list, tuple)) or len(cyc) < 2 or cyc[0] != cyc[-1]:
        return False
    return all(cyc[i + 1] in deps.get(cyc[i], ()) for i in range(len(cyc) - 1))


def check_topo(mod, rng):
    graphs = [{"a": ["b"], "b": ["c"], "c": []}, {"b": [], "a": []}, {"x": ["y", "z"]}, {"a": ["a"]},
              {"a": ["b"], "b": ["a"]}, {"a": ["b"], "b": ["c"], "c": ["a"]}, {}, {"d": ["c"], "c": ["b", "a"]}]
    graphs += [random_graph(rng, rng.random() < 0.4) for _ in range(800)]
    results = []
    for g in graphs:
        want = ref_topo(g)
        got = outcome(mod.order, {k: list(v) for k, v in g.items()})
        if want is not None:
            ok = got[0] == "ok" and list(got[1]) == want
            exp = want
        else:
            err = got[2] if got[0] == "raise" else None
            ok = (err is not None and type(err).__name__ == "CycleError" and isinstance(err, ValueError)
                  and valid_cycle(g, getattr(err, "cycle", None)))
            exp = "CycleError with a valid .cycle"
            if err is not None:
                got = ("raise", type(err).__name__, getattr(err, "cycle", None))
        results.append((ok, f"order({g}) -> {got[:3] if got[0] == 'raise' else got[:2]}, expected {exp}"))
    return results


# ----------------------------------------------------------------------------- slots
def mins(t):
    return int(t[:2]) * 60 + int(t[3:])


def hhmm(m):
    return f"{m // 60:02d}:{m % 60:02d}"


def ref_slots(busy, day_start, day_end, min_length):
    s, e = mins(day_start), mins(day_end)
    taken = [False] * 1440
    for a, b in busy:
        for m in range(mins(a), mins(b)):
            taken[m] = True
    out, m = [], s
    while m < e:
        if taken[m]:
            m += 1
            continue
        j = m
        while j < e and not taken[j]:
            j += 1
        if j - m >= min_length:
            out.append((hhmm(m), hhmm(j)))
        m = j
    return out


def check_slots(mod, rng):
    cases = [([("09:00", "10:00"), ("10:00", "11:00")], "08:00", "12:00", 30),
             ([("09:00", "10:30"), ("10:00", "11:00")], "09:00", "17:00", 60),
             ([], "09:00", "17:00", 30), ([("07:00", "18:00")], "09:00", "17:00", 1),
             ([("12:00", "12:30")], "09:00", "17:00", 180), ([("09:15", "09:45")], "09:00", "10:00", 15)]
    for _ in range(600):
        busy = []
        for _ in range(rng.randint(0, 6)):
            a = rng.randrange(6 * 60, 20 * 60, 5)
            busy.append((hhmm(a), hhmm(a + rng.randrange(5, 180, 5))))
        ds = rng.randrange(7 * 60, 11 * 60, 15)
        cases.append((busy, hhmm(ds), hhmm(ds + rng.randrange(60, 9 * 60, 15)), rng.choice([5, 15, 30, 45, 60])))
    results = []
    for busy, ds, de, ml in cases:
        want = ref_slots(busy, ds, de, ml)
        got = outcome(mod.free_slots, list(busy), ds, de, ml)
        ok = got[0] == "ok" and [tuple(x) for x in got[1]] == want
        results.append((ok, f"free_slots({busy}, {ds!r}, {de!r}, {ml}) -> {got[:2]}, expected {want}"))
    for bad in [([("9:00", "10:00")], "08:00", "12:00", 30), ([("10:00", "09:00")], "08:00", "12:00", 30),
                ([("25:00", "26:00")], "08:00", "12:00", 30), ([], "12:00", "08:00", 30),
                ([("09:60", "10:00")], "08:00", "12:00", 30), ([("aa:bb", "10:00")], "08:00", "12:00", 30)]:
        got = outcome(mod.free_slots, *bad)
        results.append((got[0] == "raise" and isinstance(got[2], ValueError),
                        f"free_slots{bad} -> {got[:2]}, expected ValueError"))
    return results


CHECKS = {"glob": check_glob, "bowling": check_bowling, "calc": check_calc, "topo": check_topo, "slots": check_slots}

if __name__ == "__main__":
    task, path = sys.argv[1], sys.argv[2]
    try:
        mod = load(path)
        results = CHECKS[task](mod, random.Random(20261031))
    except Exception as e:          # noqa: BLE001
        print(f"SCORE 0/1 (could not run: {type(e).__name__}: {e})")
        sys.exit(0)
    bad = [msg for ok, msg in results if not ok]
    print(f"SCORE {len(results) - len(bad)}/{len(results)}")
    for msg in bad[:6]:
        print("  MISMATCH", msg[:300])
