"""Second test battery: goals and reference checkers. Run inside the sandbox (the module under test
is pipeline-written code):  python3 battery2_checks.py TASK /work/<file>.py
Prints `SCORE passed/total` and up to 6 mismatches. TASK is semver, justify, life, csv or cache."""
import csv
import importlib.util
import io
import random
import re
import sys

GOALS = {
    "semver": (
        "Create a Python module with satisfies(version, range_text) -> bool for npm-style version ranges "
        "(no pre-release tags). A version is MAJOR.MINOR.PATCH of non-negative integers. A range is one or "
        "more comparator sets joined by '||' (any set may match); a set is comparators separated by spaces "
        "(all must match), or a hyphen range 'A - B'. Comparators: an optional operator (<, <=, >, >=, =, ^, ~) "
        "then a full or partial version, where a part may be x, X or * (a missing part counts as x). Rules: "
        "'1.2.3' or '=1.2.3' is exact; '*', 'x' or an empty range matches everything; '1.2.x' or '1.2' means "
        ">=1.2.0 <1.3.0 and '1.x' or '1' means >=1.0.0 <2.0.0; '>1.2' means >=1.3.0, '>=1.2' means >=1.2.0, "
        "'<1.2' means <1.2.0, '<=1.2' means <1.3.0; '~1.2.3' means >=1.2.3 <1.3.0, '~1.2' means >=1.2.0 <1.3.0, "
        "'~1' means >=1.0.0 <2.0.0; '^' allows changes that don't modify the left-most non-zero part: "
        "'^1.2.3' is >=1.2.3 <2.0.0, '^0.2.3' is >=0.2.3 <0.3.0, '^0.0.3' is >=0.0.3 <0.0.4, '^1.2' is "
        ">=1.2.0 <2.0.0, '^0.0' is >=0.0.0 <0.1.0, '^0' and '^0.x' are >=0.0.0 <1.0.0; 'A - B' means >=A <=B, "
        "a partial A fills zeros ('1.2 - 2.3.4' is >=1.2.0 <=2.3.4) and a partial B is an upper bound on its "
        "parts ('1.2.3 - 2.3' is >=1.2.3 <2.4.0, '1.2.3 - 2' is >=1.2.3 <3.0.0). Raise ValueError for a "
        "malformed version or range. Command line: python <script> VERSION RANGE prints True or False. In "
        "--test mode check every rule above, including the ^0 cases and unions."),
    "justify": (
        "Create a Python module with justify(text, width) -> list of str that fully justifies text. Words are "
        "the whitespace-separated pieces of text. Fill each line greedily with as many words as fit (words "
        "separated by at least one space). Every line has exactly width characters. On each line except the "
        "last, spread the spaces as evenly as possible between words; when they don't divide evenly, the "
        "left gaps get one more space than the right ones; a line with a single word is the word followed by "
        "spaces. The last line has single spaces between words and is padded with spaces on the right. Empty "
        "or all-whitespace text gives an empty list. Raise ValueError if width is less than 1 or a word is "
        "longer than width. Command line: python <script> WIDTH reads text from stdin and prints the lines "
        "between | characters. In --test mode check even and uneven spacing, single-word lines, the last line "
        "and the errors."),
    "life": (
        "Create a Python module with step(grid, rule='B3/S23', wrap=False) -> list of str that advances a "
        "Life-like cellular automaton by one generation. grid is a list of equal-length strings of '.' (dead) "
        "and '#' (alive); the result has the same size. Each cell has 8 neighbours; with wrap=False cells "
        "outside the grid count as dead, with wrap=True the grid wraps around on both axes (a torus; on a "
        "1-wide or 2-wide axis a neighbour may be the same cell more than once, counted each time). rule is "
        "'B<digits>/S<digits>' (digits 0-8, each part may be empty, e.g. 'B36/S23' or 'B/S'): a dead cell "
        "becomes alive if its live-neighbour count is in the B digits, a live cell stays alive if its count is "
        "in the S digits, otherwise it is dead. Raise ValueError for a malformed rule, rows of different "
        "lengths, any character other than '.' and '#', or an empty grid. Command line: python <script> RULE "
        "STEPS reads the grid from stdin and prints the result. In --test mode check a blinker, a glider with "
        "wrap, B/S rules other than Life's, and the errors."),
    # Set 2 ran with "A line break at the very end doesn't start another record; an empty line elsewhere
    # is a record with no fields ([])", which leaves '\n' open to two readings (no record, or one empty
    # one); the reference follows the csv module. That wording is kept in data/csv_high_case/goal.txt.
    "csv": (
        "Create a Python module with parse_csv(text) -> list of lists of str, without using the csv module. "
        "Fields are separated by commas and records by '\\n' or '\\r\\n'. A field that starts with '\"' is "
        "quoted: inside it, '\"\"' is one literal quote and commas and line breaks are literal; after its "
        "closing quote only a comma, a line break or the end of the text may follow, otherwise raise "
        "ValueError. An unquoted field is taken literally up to the next comma or line break (a '\"' inside "
        "it is an ordinary character). An unterminated quoted field raises ValueError. Every line ends a "
        "record, including an empty line, which is a record with no fields ([]); a line break at the very "
        "end only ends the last line and doesn't start another record. So 'a\\n' gives [['a']], '\\n' gives "
        "[[]] and 'a\\n\\nb' gives [['a'], [], ['b']]. An empty text gives []. Command line: python "
        "<script> FILE prints each record as a Python list. In "
        "--test mode check quoting, escaped quotes, line breaks inside quotes, CRLF, empty fields, empty lines "
        "and the errors."),
    "cache": (
        "Create a Python module with a class TTLCache(capacity, ttl) whose methods take the current time "
        "explicitly: put(key, value, now) and get(key, now). An entry stored at time t expires at t + ttl "
        "(it is gone when now >= t + ttl). get returns the value, or None if the key is missing or expired; a "
        "successful get makes the entry the most recently used. put stores or replaces the value, restarts its "
        "time and makes it the most recently used. When put adds a new key and the cache already holds "
        "capacity unexpired entries, it first discards expired entries and then, if still full, evicts the "
        "least recently used entry. Times never go backwards. Raise ValueError if capacity < 1 or ttl <= 0. "
        "In --test mode check expiry at exactly t + ttl, recency updates by get and put, eviction order and "
        "that expired entries are discarded before evicting a live one."),
}


def load(path):
    spec = importlib.util.spec_from_file_location("under_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def outcome(fn, *args):
    try:
        return ("ok", fn(*args))
    except Exception as e:          # noqa: BLE001 - every exception is a result here
        return ("raise", type(e).__name__, e)


def compare(results, want, got, label):
    if want[0] == "ok":
        results.append((got[0] == "ok" and got[1] == want[1], f"{label} -> {got[:2]}, expected {want[1]!r}"))
    else:
        results.append((got[0] == "raise" and isinstance(got[2], ValueError), f"{label} -> {got[:2]}, expected ValueError"))


# ----------------------------------------------------------------------------- semver
INF = (10 ** 9, 0, 0)


def ref_version(s):
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", s)
    if not m:
        raise ValueError(f"bad version {s!r}")
    return tuple(int(x) for x in m.groups())


def partial(s):
    """'1.2' -> [1, 2, None]; x/X/* or missing parts are None."""
    parts = s.split(".")
    if not 1 <= len(parts) <= 3 or s == "":
        raise ValueError(f"bad partial {s!r}")
    out = []
    for p in parts:
        if p in ("x", "X", "*"):
            out.append(None)
        elif re.fullmatch(r"\d+", p):
            if out and out[-1] is None:
                raise ValueError("number after a wildcard")
            out.append(int(p))
        else:
            raise ValueError(f"bad part {p!r}")
    return out + [None] * (3 - len(out))


def bump(p, i):
    """Smallest version above all versions that share the first i+1 known parts."""
    v = [x or 0 for x in p[:i + 1]] + [0] * (2 - i)
    v[i] += 1
    for j in range(i + 1, 3):
        v[j] = 0
    return tuple(v)


def comparator(text):
    """[(op, version)] constraints, all must hold."""
    m = re.fullmatch(r"(<=|>=|<|>|=|\^|~)?(.*)", text)
    op, rest = m.group(1) or "", m.group(2)
    p = partial(rest)
    known = [x for x in p if x is not None]
    n = len(known)
    lo = tuple(x or 0 for x in p)
    if op in ("", "="):
        if n == 3:
            return [("==", lo)]
        if n == 0:
            return []
        return [(">=", lo), ("<", bump(p, n - 1))]
    if op == ">":
        return [(">", lo)] if n == 3 else ([("<", (0, 0, 0))] if n == 0 else [(">=", bump(p, n - 1))])
    if op == ">=":
        return [(">=", lo)]
    if op == "<":
        return [("<", lo)] if n else [("<", (0, 0, 0))]
    if op == "<=":
        return [("<=", lo)] if n == 3 else ([] if n == 0 else [("<", bump(p, n - 1))])
    if op == "~":
        if n == 0:
            return []
        return [(">=", lo), ("<", bump(p, 1 if n >= 2 else 0))]
    # caret
    if n == 0:
        return []
    if p[0] != 0:
        return [(">=", lo), ("<", bump(p, 0))]
    if n == 1:
        return [(">=", lo), ("<", (1, 0, 0))]
    if p[1] != 0:
        return [(">=", lo), ("<", bump(p, 1))]
    if n == 2:
        return [(">=", lo), ("<", (0, 1, 0))]
    return [(">=", lo), ("<", bump(p, 2))]


def ref_satisfies(version, rng):
    v = ref_version(version)
    ops = {"==": lambda a, b: a == b, ">": lambda a, b: a > b, ">=": lambda a, b: a >= b,
           "<": lambda a, b: a < b, "<=": lambda a, b: a <= b}
    any_match = False
    for part in rng.split("||"):
        part = part.strip()
        hyphen = re.fullmatch(r"(\S+)\s+-\s+(\S+)", part)
        if hyphen:
            a, b = partial(hyphen.group(1)), partial(hyphen.group(2))
            nb = len([x for x in b if x is not None])
            cons = [(">=", tuple(x or 0 for x in a))]
            if nb == 3:
                cons.append(("<=", tuple(b)))
            elif nb:
                cons.append(("<", bump(b, nb - 1)))
        else:
            cons = []
            for tok in part.split():
                cons += comparator(tok)
        if all(ops[o](v, w) for o, w in cons):
            any_match = True
    return any_match


def random_range(rng):
    def ver(allow_star=False):
        """Numbers first, then optionally one wildcard that ends the version (the forms the goal defines)."""
        n = rng.choice([1, 2, 3, 3])
        parts = [str(rng.randint(0, 2)) for _ in range(n)]
        if rng.random() < 0.25 and n < 3:
            parts.append(rng.choice(["x", "X", "*"]))
        if allow_star and rng.random() < 0.05:
            parts = [rng.choice(["x", "*"])]
        return ".".join(parts)

    sets = []
    for _ in range(rng.choice([1, 1, 2])):
        if rng.random() < 0.2:
            sets.append(f"{ver()} - {ver()}")
        else:
            toks = []
            for _ in range(rng.choice([1, 1, 2])):
                op = rng.choice(["", "", "=", "^", "~", ">", ">=", "<", "<="])
                toks.append(op + ver(allow_star=op == ""))
            sets.append(" ".join(toks))
    return " || ".join(sets)


def check_semver(mod, rng):
    cases = [("1.2.3", "1.2.3"), ("1.2.4", "=1.2.3"), ("5.0.0", "*"), ("0.0.0", ""), ("1.2.9", "1.2.x"),
             ("1.3.0", "1.2"), ("1.9.9", "1"), ("1.3.0", ">1.2"), ("1.2.9", ">1.2"), ("1.2.0", "<=1.2"),
             ("1.2.9", "<=1.2"), ("1.3.0", "<=1.2"), ("1.2.9", "~1.2.3"), ("1.3.0", "~1.2.3"), ("1.9.0", "~1"),
             ("1.9.9", "^1.2.3"), ("2.0.0", "^1.2.3"), ("0.2.9", "^0.2.3"), ("0.3.0", "^0.2.3"),
             ("0.0.3", "^0.0.3"), ("0.0.4", "^0.0.3"), ("0.0.9", "^0.0"), ("0.1.0", "^0.0"), ("0.9.9", "^0"),
             ("0.9.9", "^0.x"), ("2.3.4", "1.2 - 2.3.4"), ("2.3.9", "1.2.3 - 2.3"), ("2.4.0", "1.2.3 - 2.3"),
             ("2.9.9", "1.2.3 - 2"), ("3.0.0", "1.2.3 - 2"), ("1.0.0", "<1 || >=2"), ("2.5.0", ">=1.0.0 <2 || 2.5"),
             ("1.2", "1.2.3"), ("1.2.3", ">>1"), ("1.2.3", "1.2.3.4"), ("1.2.3", "a.b.c"), ("x.2.3", "*")]
    for _ in range(1500):
        cases.append((f"{rng.randint(0, 3)}.{rng.randint(0, 3)}.{rng.randint(0, 4)}", random_range(rng)))
    results = []
    for v, r in cases:
        compare(results, outcome(ref_satisfies, v, r), outcome(mod.satisfies, v, r), f"satisfies({v!r}, {r!r})")
    return results


# ----------------------------------------------------------------------------- justify
def ref_justify(text, width):
    if width < 1:
        raise ValueError("width")
    words = text.split()
    if any(len(w) > width for w in words):
        raise ValueError("long word")
    lines, i = [], 0
    while i < len(words):
        j, length = i, len(words[i])
        while j + 1 < len(words) and length + 1 + len(words[j + 1]) <= width:
            j += 1
            length += 1 + len(words[j])
        line_words = words[i:j + 1]
        if j + 1 == len(words) or len(line_words) == 1:
            line = " ".join(line_words)
            line += " " * (width - len(line))
        else:
            gaps = len(line_words) - 1
            spaces = width - sum(len(w) for w in line_words)
            q, extra = divmod(spaces, gaps)
            line = ""
            for k, w in enumerate(line_words[:-1]):
                line += w + " " * (q + (1 if k < extra else 0))
            line += line_words[-1]
        lines.append(line)
        i = j + 1
    return lines


def check_justify(mod, rng):
    vocab = ["a", "an", "the", "quick", "brown", "fox", "jumps", "over", "lazy", "dog", "justification",
             "is", "fun", "x", "yy", "zzz"]
    cases = [("", 10), ("   ", 5), ("word", 4), ("word", 10), ("a b c d", 3), ("This is an example of text", 16),
             ("toolongword", 5), ("a b", 0), ("one two three four", 9)]
    for _ in range(800):
        words = [rng.choice(vocab) for _ in range(rng.randint(0, 14))]
        sep = [rng.choice([" ", "  ", "\n", "\t "]) for _ in words]
        cases.append(("".join(w + s for w, s in zip(words, sep)), rng.randint(3, 25)))
    results = []
    for t, w in cases:
        compare(results, outcome(ref_justify, t, w), outcome(mod.justify, t, w), f"justify({t!r}, {w})")
    return results


# ----------------------------------------------------------------------------- life
def ref_step(grid, rule="B3/S23", wrap=False):
    m = re.fullmatch(r"B([0-8]*)/S([0-8]*)", rule)
    if not m:
        raise ValueError("rule")
    born, survive = {int(c) for c in m.group(1)}, {int(c) for c in m.group(2)}
    if not grid or any(len(r) != len(grid[0]) for r in grid):
        raise ValueError("grid shape")
    if any(c not in ".#" for r in grid for c in r):
        raise ValueError("grid chars")
    h, w = len(grid), len(grid[0])
    out = []
    for y in range(h):
        row = []
        for x in range(w):
            n = 0
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dy == dx == 0:
                        continue
                    yy, xx = y + dy, x + dx
                    if wrap:
                        yy, xx = yy % h, xx % w
                    elif not (0 <= yy < h and 0 <= xx < w):
                        continue
                    n += grid[yy][xx] == "#"
            alive = grid[y][x] == "#"
            row.append("#" if (n in survive if alive else n in born) else ".")
        out.append("".join(row))
    return out


def check_life(mod, rng):
    cases = [([".....", "..#..", "..#..", "..#..", "....."], "B3/S23", False),
             ([".#...", "..#..", "###..", ".....", "....."], "B3/S23", True), (["#"], "B3/S23", True),
             (["##", "##"], "B/S", False), (["#."], "B1/S", True), (["#.", "."], "B3/S23", False),
             (["#x"], "B3/S23", False), ([], "B3/S23", False), (["#."], "B9/S23", False), (["#."], "S23/B3", False)]
    rules = ["B3/S23", "B36/S23", "B2/S", "B/S012345678", "B1357/S1357", "B3678/S34678", "B/S"]
    for _ in range(500):
        h, w = rng.randint(1, 7), rng.randint(1, 7)
        grid = ["".join(rng.choice("..#") for _ in range(w)) for _ in range(h)]
        cases.append((grid, rng.choice(rules), rng.random() < 0.5))
    results = []
    for g, r, wr in cases:
        compare(results, outcome(ref_step, list(g), r, wr), outcome(mod.step, list(g), r, wr),
                f"step({g}, {r!r}, wrap={wr})")
    return results


# ----------------------------------------------------------------------------- csv
def ref_csv(text):
    if text == "":
        return []
    try:
        return [row for row in csv.reader(io.StringIO(text, newline=""), strict=True)]
    except csv.Error as e:
        raise ValueError(str(e)) from None


def check_csv(mod, rng):
    cases = ['a,b,c', 'a,"b,c",d', '"a ""q"" b",x', '"multi\nline",y', 'a,b\r\nc,d\r\n', 'a,,c', ',', 'a\n\nb',
             '"a"b,c', '"unterminated', 'a"b,c', '', '\n', '"",""', 'x\n']
    alphabet = ["a", "b", " ", ",", '"', "\n", "\r\n", "q"]
    for _ in range(800):
        if rng.random() < 0.7:                                  # valid text written by the csv module
            rows = [["".join(rng.choice(alphabet) for _ in range(rng.randint(0, 4))) for _ in range(rng.randint(1, 4))]
                    for _ in range(rng.randint(1, 4))]
            buf = io.StringIO()
            csv.writer(buf, lineterminator=rng.choice(["\n", "\r\n"])).writerows(rows)
            text = buf.getvalue()
            if rng.random() < 0.3:
                text = text.rstrip("\r\n")
        else:                                                    # hand-made, often malformed
            text = "".join(rng.choice(['a', ',', '"', '"x"', '""', '\n', 'b"', ' ']) for _ in range(rng.randint(1, 8)))
        if "\r" in text.replace("\r\n", ""):
            continue                                             # bare '\r' isn't defined by the goal
        cases.append(text)
    results = []
    for t in cases:
        compare(results, outcome(ref_csv, t), outcome(mod.parse_csv, t), f"parse_csv({t!r})")
    return results


# ----------------------------------------------------------------------------- cache
class RefCache:
    def __init__(self, capacity, ttl):
        if capacity < 1 or ttl <= 0:
            raise ValueError("bad arguments")
        self.cap, self.ttl, self.items = capacity, ttl, {}     # key -> [value, stored_at]; dict order = recency

    def _alive(self, key, now):
        return key in self.items and now < self.items[key][1] + self.ttl

    def get(self, key, now):
        if not self._alive(key, now):
            self.items.pop(key, None)
            return None
        self.items[key] = self.items.pop(key)
        return self.items[key][0]

    def put(self, key, value, now):
        if key in self.items:
            self.items.pop(key)
        elif sum(1 for k in self.items if self._alive(k, now)) >= self.cap or len(self.items) >= self.cap:
            for k in [k for k in self.items if not self._alive(k, now)]:
                del self.items[k]
            if len(self.items) >= self.cap:
                del self.items[next(iter(self.items))]
        self.items[key] = [value, now]


def check_cache(mod, rng):
    results = []
    for args in [(0, 5), (2, 0), (1, -1)]:
        got = outcome(mod.TTLCache, *args)
        results.append((got[0] == "raise" and isinstance(got[2], ValueError), f"TTLCache{args} -> {got[:2]}, expected ValueError"))
    scripted = [  # (capacity, ttl, [(op, key, value_or_None, now, expected_get_or_None)])
        (2, 100, [("put", "a", 1, 0, None), ("put", "b", 2, 0, None), ("get", "a", None, 1, 1),
                  ("put", "c", 3, 2, None), ("get", "b", None, 3, None), ("get", "a", None, 3, 1)]),
        (2, 100, [("put", "a", 1, 0, None), ("put", "b", 2, 0, None), ("put", "a", 9, 1, None),
                  ("put", "c", 3, 2, None), ("get", "b", None, 3, None), ("get", "a", None, 3, 9)]),
        (2, 5, [("put", "a", 1, 0, None), ("put", "b", 2, 3, None), ("put", "c", 3, 5, None),
                ("get", "b", None, 5, 2), ("get", "a", None, 5, None)]),
        (1, 4, [("put", "a", 1, 0, None), ("get", "a", None, 3, 1), ("get", "a", None, 4, None)]),
    ]
    for cap, ttl, ops in scripted:
        made = outcome(mod.TTLCache, cap, ttl)
        ok, log = made[0] == "ok", []
        for op, key, value, now, want in ops if ok else []:
            got = outcome(made[1].put, key, value, now) if op == "put" else outcome(made[1].get, key, now)
            log.append(f"{op}({key!r},{now})" + ("" if op == "put" else f"={got[1] if got[0] == 'ok' else got[:2]}"))
            if got[0] != "ok" or (op == "get" and got[1] != want):
                ok = False
                log.append(f"(expected {want})")
                break
        results.append((ok, f"TTLCache({cap}, {ttl}) scripted: " + " ".join(log)))
    for trial in range(300):
        cap, ttl = rng.randint(1, 4), rng.choice([2, 3, 8, 15, 30])
        ref, made = RefCache(cap, ttl), outcome(mod.TTLCache, cap, ttl)
        if made[0] != "ok":
            results.append((False, f"TTLCache({cap}, {ttl}) -> {made[:2]}"))
            continue
        obj, now, log = made[1], 0, []
        ok = True
        for _ in range(rng.randint(5, 25)):
            now += rng.choice([0, 0, 0, 1, 1, 2])
            key = rng.choice("abcdef")
            if rng.random() < 0.45:
                v = rng.randint(0, 99)
                ref.put(key, v, now)
                got = outcome(obj.put, key, v, now)
                log.append(f"put({key!r},{v},{now})")
                if got[0] != "ok":
                    ok = False
                    log.append(f"-> {got[:2]}")
                    break
            else:
                want, got = ref.get(key, now), outcome(obj.get, key, now)
                log.append(f"get({key!r},{now})={want}")
                if got[0] != "ok" or got[1] != want:
                    ok = False
                    log.append(f"-> got {got[:2]}")
                    break
        results.append((ok, f"TTLCache({cap}, {ttl}): " + " ".join(log[-8:])))
    return results


CHECKS = {"semver": check_semver, "justify": check_justify, "life": check_life, "csv": check_csv,
          "cache": check_cache}

if __name__ == "__main__":
    task, path = sys.argv[1], sys.argv[2]
    try:
        mod = load(path)
        results = CHECKS[task](mod, random.Random(20261101))
    except Exception as e:          # noqa: BLE001
        print(f"SCORE 0/1 (could not run: {type(e).__name__}: {e})")
        sys.exit(0)
    bad = [msg for ok, msg in results if not ok]
    print(f"SCORE {len(results) - len(bad)}/{len(results)}")
    for msg in bad[:6]:
        print("  MISMATCH", msg[:300])
