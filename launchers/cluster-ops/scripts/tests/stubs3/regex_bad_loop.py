"""Bug: no guard against empty passes, so (a*)* recurses without end."""


def _char(p, j):
    if p[j] != "\\":
        return p[j], j + 1
    if j + 1 >= len(p) or p[j + 1].isalnum():
        raise ValueError("bad escape")
    return p[j + 1], j + 2


def _parse_class(p, i):
    j = i + 1
    neg = j < len(p) and p[j] == "^"
    if neg:
        j += 1
    start, ranges = j, []
    while True:
        if j >= len(p):
            raise ValueError("class with no closing ]")
        if p[j] == "]" and j > start:
            return ("cls", neg, ranges), j + 1
        lo, j = _char(p, j)
        if j + 1 < len(p) and p[j] == "-" and p[j + 1] != "]":
            hi, j = _char(p, j + 1)
            if hi < lo:
                raise ValueError("backwards range")
            ranges.append((lo, hi))
        else:
            ranges.append((lo, lo))


def _parse_alt(p, i):
    alts = []
    while True:
        seq, i = _parse_seq(p, i)
        alts.append(seq)
        if i < len(p) and p[i] == "|":
            i += 1
            continue
        return ("alt", alts), i


def _parse_seq(p, i):
    items = []
    while i < len(p) and p[i] not in "|)":
        c = p[i]
        if c in "*+?":
            raise ValueError("nothing to repeat")
        if c == "(":
            node, i = _parse_alt(p, i + 1)
            if i >= len(p) or p[i] != ")":
                raise ValueError("unmatched (")
            i += 1
        elif c == "[":
            node, i = _parse_class(p, i)
        elif c == ".":
            node, i = ("any",), i + 1
        else:
            ch, i = _char(p, i)
            node = ("chr", ch)
        if i < len(p) and p[i] in "*+?":
            node, i = ("rep", node, p[i]), i + 1
            if i < len(p) and p[i] in "*+?":
                raise ValueError("a quantifier after a quantifier")
        items.append(node)
    return ("seq", items), i


def _match(node, s, i, k):
    kind = node[0]
    if kind == "chr":
        return i < len(s) and s[i] == node[1] and k(i + 1)
    if kind == "any":
        return i < len(s) and s[i] != "\n" and k(i + 1)
    if kind == "cls":
        if i >= len(s):
            return False
        hit = any(lo <= s[i] <= hi for lo, hi in node[2])
        return hit != node[1] and k(i + 1)
    if kind == "seq":
        items = node[1]

        def go(n, j):
            if n == len(items):
                return k(j)
            return _match(items[n], s, j, lambda j2: go(n + 1, j2))
        return go(0, i)
    if kind == "alt":
        return any(_match(a, s, i, k) for a in node[1])
    sub, q = node[1], node[2]
    if q == "?":
        return _match(sub, s, i, k) or k(i)
    if q == "*":
        return _star(sub, s, i, k)
    return _match(sub, s, i, lambda j: _star(sub, s, j, k))


def _star(sub, s, i, k):
    # another pass only if it consumes something, so (a*)* can't loop forever
    return _match(sub, s, i, lambda j: _star(sub, s, j, k)) or k(i)


def full_match(pattern, text):
    tree, i = _parse_alt(pattern, 0)
    if i != len(pattern):
        raise ValueError("unmatched )")
    return bool(_match(tree, text, 0, lambda j: j == len(text)))
