"""Probe of reference behaviours for set 4 (tomllib, struct, ast). Run in the sandbox:
ssh server@NODE2 "docker run --rm -i --network none agent-sandbox:latest python3 -W ignore -" < probe4.py"""
import ast
import struct
import sys
import tomllib


def t(label, f):
    try:
        r = f()
        print(f"{label}: {r!r}"[:150])
    except BaseException as e:
        print(f"{label}: !{type(e).__name__}: {e}"[:150])


BS = "\\"
L = tomllib.loads
DOCS = ["a = 9223372036854775808", "a = -9223372036854775809", "a = 01", "a = +0x1", "a = 0x", "a = 1__2",
        "a = 1_", "a = .5", "a = 5.", "a = 1_0.0_1", "a = 0.0_1", "a = 1e+05", "a = -nan", "a = -0.0",
        "a = {b = 1,}", "a = {\nb = 1}", "a.b = 1\n[a]", "[a.b]\n[a]", "[a]\nb.c = 1\n[a.b]", "[a]\n[a]",
        "a = [1]\n[[a]]", "a = {b=1}\n[a.c]", "a = {b=1}\na.c = 2", "[[a]]\n[a]", "[a]\n[[a]]",
        'a = "' + BS + 'x41"', 'a = "' + BS + 'ud800"', 'a = "' + BS + 'U00110000"', 'a = """\nx"""',
        'a = """x' + BS + '\n   y"""', "a = '''\nx'''", 'a = "t\tb"', 'a = "c\x01"', 'a = "d\x7f"',
        "a = 1979-05-27", "a = 07:32:00", '"" = 1', "a b = 1", 'a."b.c" = 1', "3.14159 = 'pi'", "ü = 1",
        "a = 1\rb = 2", "a = 1\r\nb = 2", "a = [,]", "a = [1,,2]", "a = True", "[ a . b ]\nc=1", "[[ a ]]",
        "[ [a] ]", "a = 0", "a = -0", "a = +1", "a = 0o17", "a = 0b_1", "a = 0x_1", "a = 1e1_0", "a = 1.e5",
        "a = inf\nb = -inf\nc = +nan", "a = 9_223_372_036_854_775_807", "a.b.c = 1\na.b.d = 2", "a = {b.c = 1}",
        "a = {b = 1, b = 2}", "[a]\nb = 1\n[a]\nc = 2", "a = []\n[[a]]", "[[a]]\nb = 1\n[[a]]\nb = 2",
        "[[a.b]]\n[a]\nc = 1", "x = 'a'\"b\"", "a = 1 # c\n# d", 'a = """a"""""', "a = '''''''", 'a = """"""',
        "a = 1979-05-27T07:32:00Z", 'a = "' + BS + 'e"', 'a = "' + BS + 'u00e9"', "a = 'x' # \x01",
        "a = 0xDEADbeef", "a = 0xG", "a = 1e400", "a = 2_.0", "a = 1._2", "[a]\n[a.b]\n[a]", "a = 1 b = 2",
        "a = \"x\" \n", "a=1#c", "[a] # c\n", "[a]x", "a = [1 2]", "a = { }", "a = {b = {c = 1}}\n[a.b.d]",
        "a.b = 1\na = 2", "a = 1\na.b = 2", "[a]\n[b]\n[a.c]", "a = '''a''''", "a = 1_000_000"]
for doc in DOCS:
    t(repr(doc)[:46], lambda: L(doc))
t("deep array 900", lambda: len(str(L("a = " + "[" * 900 + "]" * 900))))
t("deep array 3000", lambda: len(str(L("a = " + "[" * 3000 + "]" * 3000))))
t("bytes input", lambda: L(b"a = 1"))

P = struct.pack
for label, f in [
        ("calcsize <5x", lambda: struct.calcsize("<5x")), ("0p", lambda: P("<0p", b"x")),
        ("1p", lambda: P("<1p", b"abc")), ("300p", lambda: P("<300p", b"x" * 300)[:2]),
        ("lead space", lambda: P(" <i", 1)), ("space after <", lambda: P("< i", 1)),
        ("3 i", lambda: P("<3 i", 1, 2, 3)), ("i trailing", lambda: P("<i ", 1)), ("tab", lambda: P("<\ti", 1)),
        ("newline", lambda: P("<i\n", 1)), ("bool as i", lambda: P("<i", True)), ("1.0 as i", lambda: P("<i", 1.0)),
        ("c bytearray", lambda: P("<c", bytearray(b"a"))), ("s bytearray", lambda: P("<2s", bytearray(b"ab"))),
        ("s str", lambda: P("<s", "x")), ("? str", lambda: P("<?", "x")), ("unpack ?2", lambda: struct.unpack("<?", b"\x02")),
        ("e 65519.99", lambda: P("<e", 65519.99)), ("e 65520", lambda: P("<e", 65520.0)), ("e 2^-25", lambda: P("<e", 2 ** -25)),
        ("e 3*2^-26", lambda: P("<e", 3 * 2 ** -26)), ("e inf", lambda: P("<e", float("inf"))), ("e nan", lambda: P("<e", float("nan"))),
        ("f 3.5e38", lambda: P("<f", 3.5e38)), ("f 1e-50", lambda: P("<f", 1e-50)), ("d 2^1024", lambda: P("<d", 2 ** 1024)),
        ("f 2^200", lambda: P("<f", 2 ** 200)), ("d str", lambda: P("<d", "1.0")), ("d None", lambda: P("<d", None)),
        ("q 2^63", lambda: P("<q", 2 ** 63)), ("Q -1", lambda: P("<Q", -1)), ("no prefix", lambda: P("i", 1)),
        ("unpack 5 bytes", lambda: struct.unpack("<i", b"\x00" * 5)), ("unpack e -nan", lambda: struct.unpack("<e", b"\x00\xfe")),
        ("3 no char", lambda: P("<3", 1)), ("bad char", lambda: P("<z", 1)), ("prefix twice", lambda: P("<i<", 1)),
        ("empty <", lambda: P("<")), ("0c", lambda: P("<0c")), ("0s", lambda: P("<0s", b"abc")), ("2s short", lambda: P("<2s", b"a")),
        ("too few", lambda: P("<ii", 1)), ("too many", lambda: P("<i", 1, 2)), ("f -0.0", lambda: P(">f", -0.0)),
        ("e 1e-8", lambda: P("<e", 1e-8)), ("f max", lambda: P("<f", 3.4028235677973366e38)), ("f just over", lambda: P("<f", 3.4028236e38)),
        ("f halfway over", lambda: P("<f", 3.4028235677973366e38 * (1 + 2 ** -25))),
        ("index obj", lambda: P("<h", type("I", (), {"__index__": lambda s: 7})())),
        ("float obj", lambda: P("<d", type("F", (), {"__float__": lambda s: 1.5})())),
        ("unpack 0s", lambda: struct.unpack("<0s", b"")), ("unpack p", lambda: struct.unpack("<5p", b"\x09abcd")),
        ("big count", lambda: struct.calcsize("<1000000000000000000000s")), ("! order", lambda: P("!h", 1)), ("= order", lambda: P("=h", 1)),
        ("e from int", lambda: P("<e", 3)), ("? 0.0", lambda: P("<?", 0.0)), ("s None", lambda: P("<s", None)),
        ("c str", lambda: P("<c", "a")), ("c 2 bytes", lambda: P("<c", b"ab")), ("unpack c", lambda: struct.unpack("<2c", b"ab")),
        ("e -0.0", lambda: P("<e", -0.0)), ("e 0.1", lambda: P("<e", 0.1)), ("unpack e max", lambda: struct.unpack("<e", b"\xff\x7b")),
        ("f from huge int", lambda: P("<f", 10 ** 400)), ("i from huge", lambda: P("<i", 10 ** 400)),
        ("count leading zero", lambda: P("<02h", 1, 2)), ("x with value", lambda: P("<xh", 1)),
        ("@ prefix", lambda: P("@h", 1)), ("unpack bytearray", lambda: struct.unpack("<h", bytearray(b"\x01\x00"))),
        ("unpack str data", lambda: struct.unpack("<h", "ab")), ("pack fmt bytes", lambda: P(b"<h", 1)),
        ("unpack f nan payload", lambda: struct.unpack("<f", b"\x01\x00\x80\x7f")), ("e subnormal min", lambda: struct.unpack("<e", b"\x01\x00"))]:
    t(label, f)
t("int digits default", lambda: sys.get_int_max_str_digits())
t("ast 9*5000", lambda: type(ast.parse("9" * 5000, mode="eval")).__name__)
t("ast parens 199", lambda: type(ast.parse("(" * 199 + "1" + ")" * 199, mode="eval")).__name__)
t("ast parens 201", lambda: type(ast.parse("(" * 201 + "1" + ")" * 201, mode="eval")).__name__)
t("ast minus 3000", lambda: type(ast.parse("-" * 3000 + "1", mode="eval")).__name__)
t("ast flat sum 100k", lambda: type(ast.parse("1" + "+1" * 100000, mode="eval")).__name__)
t("ast lead space", lambda: type(ast.parse(" 1", mode="eval")).__name__)
t("eval 00 0_0 0x_1f", lambda: (eval("00"), eval("0_0"), eval("0x_1f"), eval("0B1"), eval("0O7")))
t("eval 0_1", lambda: eval("0_1"))
t("eval 1True", lambda: eval("1True"))
t("eval 1_000", lambda: eval("1_000"))
t("bools", lambda: (~True, True & True, True + True, -True, True ** 2, True // True, True << 1, True ^ True, True | 0))
t("chain", lambda: (eval("1 < 2 == 2"), eval("1 & 3 == 1"), eval("not 1 == 2"), eval("2**-1"), eval("-2**2"), eval("2**3**2")))
t("floor/mod", lambda: (eval("10 // -3"), eval("10 % -3"), eval("-10 % 3"), eval("-7 // 2"), eval("0 or 5"), eval("3 and 0")))
