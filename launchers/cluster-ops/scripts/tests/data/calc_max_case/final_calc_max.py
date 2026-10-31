"""Integer arithmetic evaluator without eval, exec, ast, or compile."""

import sys


def _tokenize(expr):
    tokens = []
    i = 0
    n = len(expr)

    while i < n:
        ch = expr[i]

        if ch == " ":
            i += 1
        elif "0" <= ch <= "9":
            value = 0
            j = i
            while j < n and "0" <= expr[j] <= "9":
                value = value * 10 + (ord(expr[j]) - 48)
                j += 1
            tokens.append(("num", value))
            i = j
        elif ch in "+-*/()":
            tokens.append((ch, ch))
            i += 1
        else:
            raise ValueError("unknown character")

    if not tokens:
        raise ValueError("empty expression")

    return tokens


def _int_div(a, b):
    if b == 0:
        raise ZeroDivisionError("division by zero")

    quotient = abs(a) // abs(b)
    if (a < 0) ^ (b < 0):
        return -quotient
    return quotient


class _Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def peek(self):
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def advance(self):
        token = self.peek()
        if token is None:
            raise ValueError("missing operand")
        self.pos += 1
        return token

    def parse(self):
        value = self.parse_expr()

        token = self.peek()
        if token is not None:
            if token[0] == ")":
                raise ValueError("unbalanced parentheses")
            raise ValueError("adjacent operands")

        return value

    def parse_expr(self):
        value = self.parse_term()

        while self.peek() is not None and self.peek()[0] in ("+", "-"):
            op = self.advance()[0]
            rhs = self.parse_term()
            if op == "+":
                value += rhs
            else:
                value -= rhs

        return value

    def parse_term(self):
        value = self.parse_factor()

        while self.peek() is not None and self.peek()[0] in ("*", "/"):
            op = self.advance()[0]
            rhs = self.parse_factor()
            if op == "*":
                value *= rhs
            else:
                value = _int_div(value, rhs)

        return value

    def parse_factor(self):
        sign = 1

        while self.peek() is not None and self.peek()[0] == "-":
            self.advance()
            sign = -sign

        return sign * self.parse_primary()

    def parse_primary(self):
        token = self.peek()

        if token is None:
            raise ValueError("missing operand")

        kind = token[0]

        if kind == "num":
            self.advance()
            return token[1]

        if kind == "(":
            self.advance()
            value = self.parse_expr()

            token = self.peek()
            if token is None or token[0] != ")":
                raise ValueError("unbalanced parentheses")

            self.advance()
            return value

        raise ValueError("missing operand")


def evaluate(expr):
    if not isinstance(expr, str):
        raise ValueError("expression must be a string")

    tokens = _tokenize(expr)
    return _Parser(tokens).parse()


def _expect_value(expr, expected):
    try:
        value = evaluate(expr)
    except (ValueError, ZeroDivisionError):
        return False
    return value == expected


def _expect_value_error(expr):
    try:
        evaluate(expr)
    except ValueError:
        return True
    except ZeroDivisionError:
        return False
    return False


def _expect_zero_division(expr):
    try:
        evaluate(expr)
    except ZeroDivisionError:
        return True
    except ValueError:
        return False
    return False


def _test_precedence():
    return all(
        (
            _expect_value("2+3*4", 14),
            _expect_value("(2+3)*4", 20),
            _expect_value("10-2-3", 5),
            _expect_value("10/2/2", 2),
        )
    )


def _test_unary_minus():
    return all(
        (
            _expect_value("--3", 3),
            _expect_value("2*-3", -6),
            _expect_value("-(1+2)", -3),
            _expect_value("2--3", 5),
        )
    )


def _test_truncation():
    return all(
        (
            _expect_value("7/2", 3),
            _expect_value("-7/2", -3),
            _expect_value("7/-2", -3),
            _expect_value("-7/-2", 3),
            _expect_value("1/-2", 0),
        )
    )


def _test_errors():
    return all(
        (
            _expect_value_error(""),
            _expect_value_error("   "),
            _expect_value_error("1."),
            _expect_value_error("(1"),
            _expect_value_error("1)"),
            _expect_value_error("2+"),
            _expect_value_error("+2"),
            _expect_value_error("*2"),
            _expect_value_error("3 4"),
            _expect_value_error("2(3)"),
            _expect_zero_division("1/0"),
        )
    )


def run_tests():
    groups = (
        ("precedence", _test_precedence),
        ("unary_minus", _test_unary_minus),
        ("truncation", _test_truncation),
        ("errors", _test_errors),
    )

    for name, func in groups:
        if not func():
            print(f"FAIL {name}")
            return 1

    print("PASS precedence")
    print("PASS unary_minus")
    print("PASS truncation")
    print("PASS errors")
    return 0


def main(argv):
    args = argv[1:]

    if len(args) != 1:
        print("usage: python3 calc_max.py EXPR", file=sys.stderr)
        return 2

    arg = args[0]

    if arg == "--test":
        return run_tests()

    try:
        result = evaluate(arg)
    except (ValueError, ZeroDivisionError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
