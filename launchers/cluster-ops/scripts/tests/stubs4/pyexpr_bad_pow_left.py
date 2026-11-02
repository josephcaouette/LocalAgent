"""A correct solution of battery 4's pyexpr task, to validate the checker (stubs4/). No recursion, so
100,000-deep nesting works; one regex pass to tokenize, a precedence (shunting-yard) parse to a tree,
then an iterative evaluation that keeps Python's short-circuiting. BUG picks a deliberate defect for
the bad variants that mkvariants4.py writes; "" is the correct version."""
import operator
import re
import sys

BUG = "pow_left"
LIMIT = 1_000_000

TOKEN = re.compile(r"[ \t]*(?:(?P<num>[0-9][0-9A-Za-z_]*)|(?P<name>[A-Za-z_][A-Za-z0-9_]*)|"
                   r"(?P<op>\*\*|//|<<|>>|<=|>=|==|!=|[-+*%&|^~<>()]))")
TRAIL = re.compile(r"[ \t]*\Z")
DEC = re.compile(r"(?:0(?:_?0)*|[1-9](?:_?[0-9])*)\Z")
PREFIXED = {"x": (re.compile(r"_?[0-9a-fA-F](?:_?[0-9a-fA-F])*\Z"), 16),
            "o": (re.compile(r"_?[0-7](?:_?[0-7])*\Z"), 8), "b": (re.compile(r"_?[01](?:_?[01])*\Z"), 2)}
BINARY = {"or": (1, "L"), "and": (2, "L"), "<": (4, "C"), "<=": (4, "C"), ">": (4, "C"), ">=": (4, "C"),
          "==": (4, "C"), "!=": (4, "C"), "|": (5, "L"), "^": (6, "L"), "&": (7, "L"), "<<": (8, "L"),
          ">>": (8, "L"), "+": (9, "L"), "-": (9, "L"), "*": (10, "L"), "//": (10, "L"), "%": (10, "L"),
          "**": (12, "R")}
PREFIX = {"not": 3, "-": 11, "+": 11, "~": 11}
if BUG == "not_tight":
    PREFIX["not"] = 4.5
if BUG == "pow_left":
    BINARY["**"] = (12, "L")
if BUG == "unary_tight":
    PREFIX.update({"-": 13, "+": 13, "~": 13})
CMP = {"<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge, "==": operator.eq,
       "!=": operator.ne}
ARITH = {"+": operator.add, "-": operator.sub, "*": operator.mul, "&": operator.and_, "|": operator.or_,
         "^": operator.xor}


def big_int(s):
    """int() of a long decimal string without lifting Python 3.11's 4,300-digit limit."""
    if len(s) <= 4000:
        return int(s)
    half = len(s) // 2
    return big_int(s[:-half]) * 10 ** half + big_int(s[-half:])


def literal(text):
    if len(text) > 1 and text[0] == "0" and text[1] in "xXoObB":
        pattern, base = PREFIXED[text[1].lower()]
        if not pattern.match(text, 2):
            raise ValueError(f"invalid literal {text[:20]!r}")
        return int(text[2:].replace("_", ""), base)
    if not DEC.match(text):
        raise ValueError(f"invalid literal {text[:20]!r}")
    digits = text.replace("_", "")
    return int(digits) if BUG == "int_limit" else big_int(digits)


def tokens(expr):
    if not isinstance(expr, str):
        raise ValueError("the expression must be a str")
    out, pos = [], 0
    while True:
        if BUG == "quadratic":
            m = TOKEN.match(expr[pos:])
            end = pos + m.end() if m else pos
        else:
            m = TOKEN.match(expr, pos)
            end = m.end() if m else pos
        if not m:
            if TRAIL.match(expr, pos):
                return out
            raise ValueError(f"unexpected character at {pos}")
        pos, kind = end, m.lastgroup
        text = m.group(kind)
        if kind == "num":
            out.append(("num", literal(text)))
        elif kind == "name":
            if text in ("True", "False"):
                out.append(("num", text == "True"))
            elif text in ("not", "and", "or"):
                out.append(("op", text))
            else:
                raise ValueError(f"unknown name {text[:20]!r}")
        else:
            out.append(("op", text))


def parse(toks):
    vals, ops, want_operand, prev = [], [], True, None

    def reduce():
        name, _prec, kind = ops.pop()
        if kind == "P":
            vals.append(("un", name, vals.pop()))
            return
        right, left = vals.pop(), vals.pop()
        if BINARY[name][1] == "C" and BUG != "no_chain":
            if left[0] == "cmp":
                left[1].append(right)
                left[2].append(name)
                vals.append(left)
            else:
                vals.append(("cmp", [left, right], [name]))
        elif name in ("and", "or"):
            vals.append((name, left, right))
        elif BINARY[name][1] == "C":
            vals.append(("cmp", [left, right], [name]))
        else:
            vals.append(("bin", name, left, right))

    for kind, tok in toks:
        if want_operand:
            if kind == "num":
                vals.append(("num", tok))
                want_operand = False
            elif tok == "(":
                ops.append(("(", 0, "("))
            elif tok in ("-", "+", "~"):
                ops.append((tok, PREFIX[tok], "P"))
            elif tok == "not" and prev in (None, "(", "and", "or", "not"):
                ops.append(("not", PREFIX["not"], "P"))
            else:
                raise ValueError(f"expected an operand, got {tok!r}")
        elif kind == "num" or tok in ("(", "~", "not"):
            raise ValueError("expected an operator")
        elif tok == ")":
            while ops and ops[-1][2] != "(":
                reduce()
            if not ops:
                raise ValueError("unbalanced )")
            ops.pop()
            if vals[-1][0] == "cmp":
                vals[-1] = ("un", "()", vals[-1])
        else:
            prec, assoc = BINARY[tok]
            while ops and ops[-1][2] != "(" and (ops[-1][1] > prec or (ops[-1][1] == prec and assoc != "R")):
                reduce()
            ops.append((tok, prec, "B"))
            want_operand = True
        prev = tok if kind == "op" else "num"
    if want_operand:
        raise ValueError("incomplete expression")
    while ops:
        if ops[-1][2] == "(":
            raise ValueError("unbalanced (")
        reduce()
    return vals[0]


def sized(v):
    if abs(v).bit_length() > LIMIT:
        raise ValueError("result over 1,000,000 bits")
    return v


def apply_un(op, v):
    if op == "()":
        return v
    if op == "not":
        return int(not v) if BUG == "bool_as_int" else not v
    return sized(-v if op == "-" else (+v if op == "+" else ~v))


def apply_bin(op, a, b):
    if op == "**":
        if b < 0:
            raise ValueError("negative exponent")
        if BUG != "no_size_check" and abs(a) >= 2 and (abs(a).bit_length() - 1) * b >= LIMIT:
            raise ValueError("result over 1,000,000 bits")
        return sized(a ** b)
    if op in ("<<", ">>"):
        if b < 0:
            raise ValueError("negative shift count")
        if op == ">>":
            return a >> b
        if BUG != "no_size_check" and a and abs(a).bit_length() + b > LIMIT:
            raise ValueError("result over 1,000,000 bits")
        return sized(a << b)
    if op in ("//", "%"):
        if BUG == "trunc_div" and b:
            q = abs(a) // abs(b)
            q = q if (a >= 0) == (b > 0) else -q
            return q if op == "//" else a - b * q
        return a // b if op == "//" else a % b
    return sized(ARITH[op](a, b))


def run(root):
    if BUG == "recursive":
        return run_rec(root)
    stack, vals = [(root, 0, None)], []
    while stack:
        node, st, data = stack.pop()
        k = node[0]
        if k == "num":
            vals.append(node[1])
        elif k == "un":
            if st == 0:
                stack += [(node, 1, None), (node[2], 0, None)]
            else:
                vals.append(apply_un(node[1], vals.pop()))
        elif k == "bin":
            if st == 0:
                stack += [(node, 1, None), (node[3], 0, None), (node[2], 0, None)]
            else:
                b = vals.pop()
                vals.append(apply_bin(node[1], vals.pop(), b))
        elif k in ("and", "or"):
            if st == 0:
                stack += [(node, 1, None), (node[1], 0, None)]
            elif st == 1:
                if BUG == "eager":
                    stack += [(node, 2, None), (node[2], 0, None)]
                elif (k == "and") == bool(vals[-1]):
                    vals.pop()
                    stack.append((node[2], 0, None))
            else:
                b, a = vals.pop(), vals.pop()
                vals.append((a and b) if k == "and" else (a or b))
        else:
            operands, names = node[1], node[2]
            if st == 0:
                stack += [(node, 1, None), (operands[0], 0, None)]
                continue
            v = vals.pop()
            if st > 1 and not CMP[names[st - 2]](data, v):
                vals.append(0 if BUG == "bool_as_int" else False)
                continue
            if st == len(operands):
                vals.append(1 if BUG == "bool_as_int" else True)
                continue
            stack += [(node, st + 1, v), (operands[st], 0, None)]
    return vals[0]


def run_rec(node):
    k = node[0]
    if k == "num":
        return node[1]
    if k == "un":
        return apply_un(node[1], run_rec(node[2]))
    if k == "bin":
        a = run_rec(node[2])
        return apply_bin(node[1], a, run_rec(node[3]))
    if k in ("and", "or"):
        v = run_rec(node[1])
        return (run_rec(node[2]) if v else v) if k == "and" else (v if v else run_rec(node[2]))
    left = run_rec(node[1][0])
    for name, operand in zip(node[2], node[1][1:]):
        right = run_rec(operand)
        if not CMP[name](left, right):
            return False
        left = right
    return True


def evaluate(expr):
    return run(parse(tokens(expr)))


if __name__ == "__main__":
    if sys.argv[1:] == ["--test"]:
        cases = [("1 + 2 * 3", 7), ("2 ** 3 ** 2", 512), ("-2 ** 2", -4), ("1 < 2 < 3", True), ("0 or 5", 5)]
        bad = [(e, w, evaluate(e)) for e, w in cases if evaluate(e) != w]
        print("\n".join(f"FAIL {e}: {g!r} != {w!r}" for e, w, g in bad) or "ALL PASS")
        sys.exit(1 if bad else 0)
    sys.set_int_max_str_digits(0)
    print(evaluate(sys.argv[1]))
