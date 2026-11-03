"""struct_high_fb.py - a self-contained struct-like pack/unpack/calcsize module.

Implements standard-size (no alignment) format strings that begin with
'<', '>', '!' or '='.  No use of struct, array, ctypes or numpy.
"""

import math
import sys

# ---------------------------------------------------------------------------
# Format parsing
# ---------------------------------------------------------------------------

_FIXED_SIZES = {
    "x": 1, "c": 1, "b": 1, "B": 1, "?": 1,
    "h": 2, "H": 2, "i": 4, "I": 4, "l": 4, "L": 4,
    "q": 8, "Q": 8, "e": 2, "f": 4, "d": 8,
}

_STRING_CHARS = {"s", "p"}

_INT_RANGES = {
    "b": (-128, 127),
    "B": (0, 255),
    "h": (-32768, 32767),
    "H": (0, 65535),
    "i": (-2147483648, 2147483647),
    "I": (0, 4294967295),
    "l": (-2147483648, 2147483647),
    "L": (0, 4294967295),
    "q": (-9223372036854775808, 9223372036854775807),
    "Q": (0, 18446744073709551615),
}

_FLOAT_SPECS = {
    "e": {"bits": 16, "precision": 11, "bias": 15, "min_exp": -14, "max_exp": 15},
    "f": {"bits": 32, "precision": 24, "bias": 127, "min_exp": -126, "max_exp": 127},
    "d": {"bits": 64, "precision": 53, "bias": 1023, "min_exp": -1022, "max_exp": 1023},
}


class _ParsedFormat:
    __slots__ = ("order", "fields")

    def __init__(self, order, fields):
        self.order = order
        self.fields = fields


def _parse_format(fmt: str) -> _ParsedFormat:
    if not isinstance(fmt, str):
        raise ValueError("format must be a string")
    if len(fmt) == 0:
        raise ValueError("empty format string")

    first = fmt[0]
    if first == "<":
        order = "little"
    elif first == ">":
        order = "big"
    elif first == "!":
        order = "big"
    elif first == "=":
        order = "little" if sys.byteorder == "little" else "big"
    else:
        raise ValueError("bad byte-order character or missing prefix")

    rest = fmt[1:]
    fields = []
    i = 0
    n = len(rest)
    while i < n:
        ch = rest[i]
        if ch.isspace():
            i += 1
            continue
        if ch.isdigit():
            j = i
            while j < n and rest[j].isdigit():
                j += 1
            count = int(rest[i:j])
            if j >= n:
                raise ValueError("repeat count without format character")
            cch = rest[j]
            if cch.isspace():
                raise ValueError("whitespace between count and format character")
            if cch not in _FIXED_SIZES and cch not in _STRING_CHARS:
                raise ValueError(f"unknown format character {cch!r}")
            fields.append((count, cch))
            i = j + 1
        else:
            if ch not in _FIXED_SIZES and ch not in _STRING_CHARS:
                raise ValueError(f"unknown format character {ch!r}")
            fields.append((1, ch))
            i += 1

    return _ParsedFormat(order, fields)


def calcsize(fmt: str) -> int:
    parsed = _parse_format(fmt)
    total = 0
    for count, ch in parsed.fields:
        if ch in _STRING_CHARS:
            total += count
        else:
            total += count * _FIXED_SIZES[ch]
    return total


# ---------------------------------------------------------------------------
# Integer helpers
# ---------------------------------------------------------------------------

def _to_index(value):
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    idx = getattr(value, "__index__", None)
    if idx is not None:
        r = idx()
        if isinstance(r, int) and not isinstance(r, bool):
            return r
        raise ValueError("object __index__ did not return an integer")
    raise ValueError("integer format requires an integer, bool, or __index__ object")


def _pack_int(value, ch: str, order: str) -> bytes:
    v = _to_index(value)
    lo, hi = _INT_RANGES[ch]
    if v < lo or v > hi:
        raise ValueError(f"integer {v} out of range for {ch}")
    size = _FIXED_SIZES[ch]
    if ch in "bBhHiIlLqQ" and ch.islower():
        if v < 0:
            v = (1 << (size * 8)) + v
    return v.to_bytes(size, order)


def _unpack_int(data: bytes, ch: str, order: str) -> int:
    size = _FIXED_SIZES[ch]
    v = int.from_bytes(data, order)
    if ch.islower():
        if v >= (1 << (size * 8 - 1)):
            v -= (1 << (size * 8))
    return v


# ---------------------------------------------------------------------------
# Float helpers
# ---------------------------------------------------------------------------

def _float_input_to_float(value):
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int):
        return float(value)
    if isinstance(value, float):
        return value
    f = getattr(value, "__float__", None)
    if f is not None:
        r = f()
        if isinstance(r, float):
            return r
        raise ValueError("object __float__ did not return a float")
    raise ValueError("float format requires int, float, or __float__ object")


def _double_to_mantissa_exp(x: float):
    m, e = x.as_integer_ratio()
    sign = m < 0
    m = abs(m)
    # m is an integer; e is the exponent such that x = m * 2**e.
    return m, e, sign


def _round_to_target(m: int, e: int, spec: dict):
    p = spec["precision"]
    # We want to represent x = m * 2**e as a p-bit significand.
    # Find the position of the LSB of the target significand.
    # The target significand (for a normal number) has its MSB at bit (p-1).
    # The value x has its MSB at bit (m.bit_length() - 1 + e).
    msb_pos = m.bit_length() - 1 + e
    # The target LSB is at bit (msb_pos - (p - 1)).
    lsb_pos = msb_pos - (p - 1)
    # Scale m so that its LSB aligns with lsb_pos.
    # scaled = m * 2**(e - lsb_pos) = m * 2**(e - msb_pos + p - 1)
    shift = e - lsb_pos
    if shift >= 0:
        scaled = m << shift
        rem = 0
    else:
        s = -shift
        scaled = m >> s
        rem = m & ((1 << s) - 1)

    # Round to nearest, ties to even.
    if rem:
        half = 1 << (s - 1)
        if rem > half:
            scaled += 1
        elif rem == half:
            if scaled & 1:
                scaled += 1
        # rem < half: round down
    else:
        # No remainder: exact.
        pass

    # Carry check.
    if scaled >= (1 << p):
        scaled >>= 1
        lsb_pos += 1

    # Determine exponent for the target.
    # For a normal number, the exponent is such that the MSB of the significand
    # is at bit (p-1), i.e., the value is significand * 2**(lsb_pos - (p-1)).
    target_exp = lsb_pos - (p - 1)

    if scaled == 0:
        return 0, 0

    if scaled < (1 << (p - 1)):
        # Subnormal: the significand is scaled, exponent is min_exp.
        # Value = scaled * 2**(lsb_pos - (p-1)) but we want it as a fraction
        # of 2**min_exp.  min_exp = -(p-1) - (bias-1) ... use spec.
        # For subnormals, value = scaled * 2**(min_exp - (p-1) + (p-1))
        # Actually: subnormal value = scaled * 2**(min_exp - (p - 1) + (p - 1))
        # Let's just use: value = scaled * 2**(lsb_pos - (p-1)) and we want
        # to express as (scaled') * 2**(min_exp) where scaled' is integer.
        # min_exp - (p-1) is the scale of the LSB of a subnormal.
        sub_lsb = spec["min_exp"] - (p - 1)
        delta = lsb_pos - sub_lsb
        if delta >= 0:
            sub = scaled << delta
            if sub >= (1 << (p - 1)):
                # Rounded up into normal range.
                return sub, spec["min_exp"]
            return sub, spec["min_exp"]
        else:
            # Below subnormal range: round to zero (or nearest subnormal).
            # For simplicity, round to zero.
            return 0, 0

    # Normal.
    exp = target_exp
    if exp > spec["max_exp"]:
        raise OverflowError("float out of range")
    if exp < spec["min_exp"]:
        # Should be subnormal; handle as above.
        sub_lsb = spec["min_exp"] - (p - 1)
        delta = lsb_pos - sub_lsb
        if delta >= 0:
            sub = scaled << delta
            if sub >= (1 << (p - 1)):
                return sub, spec["min_exp"]
            return sub, spec["min_exp"]
        return 0, 0

    return scaled, exp


def _encode_float(m: int, exp: int, spec: dict, sign: bool) -> int:
    p = spec["precision"]
    bias = spec["bias"]
    bits = spec["bits"]

    if m == 0:
        return (1 << (bits - 1)) if sign else 0

    if m >= (1 << (p - 1)):
        biased_exp = exp + bias
        fraction = m ^ (1 << (p - 1))
        return (int(sign) << (bits - 1)) | (biased_exp << (p - 1)) | fraction
    else:
        fraction = m & ((1 << (p - 1)) - 1)
        return (int(sign) << (bits - 1)) | fraction


def _pack_float(value, ch: str, order: str) -> bytes:
    spec = _FLOAT_SPECS[ch]
    x = _float_input_to_float(value)

    if math.isnan(x):
        bits = spec["bits"]
        payload = (1 << (bits - 2))
        sign_bit = 1 if math.copysign(1.0, x) < 0 else 0
        pattern = (sign_bit << (bits - 1)) | payload
        return pattern.to_bytes(bits // 8, order)

    if math.isinf(x):
        bits = spec["bits"]
        sign_bit = 1 if x < 0 else 0
        pattern = (sign_bit << (bits - 1)) | ((1 << (bits - 1)) - 1)
        return pattern.to_bytes(bits // 8, order)

    if x == 0.0:
        bits = spec["bits"]
        sign_bit = 1 if math.copysign(1.0, x) < 0 else 0
        return (sign_bit << (bits - 1)).to_bytes(bits // 8, order)

    m, e, sign = _double_to_mantissa_exp(x)
    rounded_m, rounded_exp = _round_to_target(m, e, spec)
    pattern = _encode_float(rounded_m, rounded_exp, spec, sign)
    return pattern.to_bytes(spec["bits"] // 8, order)


def _unpack_float(data: bytes, ch: str, order: str) -> float:
    spec = _FLOAT_SPECS[ch]
    bits = spec["bits"]
    p = spec["precision"]
    bias = spec["bias"]
    n = int.from_bytes(data, order)

    sign = n >> (bits - 1)
    exp_bits = (n >> (p - 1)) & ((1 << (bits - p)) - 1)
    frac = n & ((1 << (p - 1)) - 1)

    if exp_bits == 0:
        if frac == 0:
            return math.copysign(0.0, -1.0 if sign else 1.0)
        value = frac / (1 << (p - 1)) * (2.0 ** (spec["min_exp"] - (p - 1)))
        return math.copysign(value, -1.0 if sign else 1.0)

    if exp_bits == ((1 << (bits - p)) - 1):
        if frac == 0:
            return math.inf if sign == 0 else -math.inf
        return math.copysign(math.nan, -1.0 if sign else 1.0)

    m = (1 << (p - 1)) | frac
    exp = exp_bits - bias
    value = m * (2.0 ** (exp - (p - 1)))
    return math.copysign(value, -1.0 if sign else 1.0)


# ---------------------------------------------------------------------------
# String helpers
# ---------------------------------------------------------------------------

def _as_bytes(value, field: str):
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    raise ValueError(f"{field} requires bytes or bytearray")


def _pack_s(value, count: int) -> bytes:
    b = _as_bytes(value, "s")
    if count == 0:
        return b""
    if len(b) < count:
        return b + b"\x00" * (count - len(b))
    return b[:count]


def _pack_p(value, count: int) -> bytes:
    if count == 0:
        return b""
    b = _as_bytes(value, "p")
    length = min(len(b), count - 1, 255)
    payload = b[:length]
    if len(payload) < count - 1:
        payload += b"\x00" * ((count - 1) - len(payload))
    return bytes([length]) + payload


def _unpack_s(data: bytes, count: int) -> bytes:
    if count == 0:
        return b""
    return bytes(data[:count])


def _unpack_p(data: bytes, count: int) -> bytes:
    if count == 0:
        return b""
    length = data[0]
    return bytes(data[1:1 + length])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def pack(fmt: str, *values) -> bytes:
    parsed = _parse_format(fmt)
    out = bytearray()
    arg_index = 0

    def _next_arg():
        nonlocal arg_index
        if arg_index >= len(values):
            raise ValueError("not enough arguments")
        v = values[arg_index]
        arg_index += 1
        return v

    for count, ch in parsed.fields:
        if ch == "x":
            out += b"\x00" * count
            continue

        if ch in _STRING_CHARS:
            # s and p always consume exactly one argument.
            value = _next_arg()
            if ch == "s":
                out += _pack_s(value, count)
            else:
                out += _pack_p(value, count)
            continue

        # Every other field consumes one argument per repetition.
        for _ in range(count):
            value = _next_arg()
            if ch == "c":
                b = _as_bytes(value, "c")
                if len(b) != 1:
                    raise ValueError("c requires a 1-byte bytes object")
                out += b
            elif ch == "?":
                out += b"\x01" if bool(value) else b"\x00"
            elif ch in "bBhHiIlLqQ":
                out += _pack_int(value, ch, parsed.order)
            else:  # e, f, d
                out += _pack_float(value, ch, parsed.order)

    if arg_index != len(values):
        raise ValueError("too many arguments")

    return bytes(out)


def unpack(fmt: str, data) -> tuple:
    parsed = _parse_format(fmt)
    if not isinstance(data, (bytes, bytearray)):
        raise ValueError("unpack data must be bytes or bytearray")
    data = bytes(data)
    expected = calcsize(fmt)
    if len(data) != expected:
        raise ValueError("incorrect data length")

    result = []
    pos = 0

    for count, ch in parsed.fields:
        if ch == "x":
            pos += count
            continue

        if ch in _STRING_CHARS:
            if ch == "s":
                result.append(_unpack_s(data[pos:pos + count], count))
            else:
                result.append(_unpack_p(data[pos:pos + count], count))
            pos += count
            continue

        size = _FIXED_SIZES[ch]
        for _ in range(count):
            if ch == "c":
                result.append(bytes(data[pos:pos + 1]))
                pos += 1
            elif ch == "?":
                result.append(data[pos] != 0)
                pos += 1
            elif ch in "bBhHiIlLqQ":
                result.append(_unpack_int(data[pos:pos + size], ch, parsed.order))
                pos += size
            else:  # e, f, d
                result.append(_unpack_float(data[pos:pos + size], ch, parsed.order))
                pos += size

    return tuple(result)


# ---------------------------------------------------------------------------
# Command-line interface and built-in tests
# ---------------------------------------------------------------------------

def _cli_pack(argv: list) -> int:
    if len(argv) < 2:
        sys.stderr.write("usage: struct_high_fb.py FMT VALUE...\n")
        return 2

    fmt = argv[0]
    values = []
    for raw in argv[1:]:
        try:
            values.append(int(raw))
        except ValueError:
            values.append(float(raw))

    try:
        packed = pack(fmt, *values)
    except Exception as exc:
        sys.stderr.write(f"{type(exc).__name__}: {exc}\n")
        return 1

    sys.stdout.write(packed.hex() + "\n")
    return 0


def _check(name: str, condition: bool, detail: str = "") -> bool:
    if condition:
        print(f"PASS {name}")
        return True
    print(f"FAIL {name} {detail}")
    return False


def _expect_raises(name: str, exc_type, fn, *args, **kwargs) -> bool:
    try:
        fn(*args, **kwargs)
    except exc_type:
        return _check(name, True)
    except Exception as exc:
        return _check(name, False, f"raised {type(exc).__name__}: {exc}")
    return _check(name, False, "did not raise")


def _run_tests() -> int:
    ok = True

    # Basic byte orders and integers.
    ok &= _check("calcsize <B", calcsize("<B") == 1)
    ok &= _check("pack <B 5", pack("<B", 5) == b"\x05")
    ok &= _check("pack >B 255", pack(">B", 255) == b"\xff")
    ok &= _check("pack !B 255", pack("!B", 255) == b"\xff")
    ok &= _check("pack =B 1", pack("=B", 1) == b"\x01")

    ok &= _check("pack <i max", pack("<i", 2147483647) == b"\xff\xff\xff\x7f")
    ok &= _check("pack >i min", pack(">i", -2147483648) == b"\x80\x00\x00\x00")
    ok &= _check("pack <q min", pack("<q", -9223372036854775808) == b"\x00" * 7 + b"\x80")
    ok &= _check("pack >Q max", pack(">Q", 18446744073709551615) == b"\xff" * 8)

    ok &= _expect_raises("int range <i high", ValueError, pack, "<i", 2147483648)
    ok &= _expect_raises("int range <i low", ValueError, pack, "<i", -2147483649)
    ok &= _expect_raises("int range >B high", ValueError, pack, ">B", 256)
    ok &= _expect_raises("int range <b high", ValueError, pack, "<b", 128)
    ok &= _expect_raises("int range <b low", ValueError, pack, "<b", -129)
    ok &= _expect_raises("int range <q high", ValueError, pack, "<q", 9223372036854775808)
    ok &= _expect_raises("int range >Q high", ValueError, pack, ">Q", 18446744073709551616)
    ok &= _expect_raises("int bad type", ValueError, pack, "<B", "1")

    # __index__ support.
    class Indexed:
        def __init__(self, v):
            self.v = v
        def __index__(self):
            return self.v

    ok &= _check("pack __index__", pack("<h", Indexed(42)) == pack("<h", 42))
    ok &= _expect_raises("__index__ out of range", ValueError, pack, "<B", Indexed(256))

    # bool and ?
    ok &= _check("pack ? true", pack("<?", True) == b"\x01")
    ok &= _check("pack ? false", pack("<?", False) == b"\x00")
    ok &= _check("unpack ? nonzero", unpack("<?", b"\x07") == (True,))
    ok &= _check("unpack ? zero", unpack("<?", b"\x00") == (False,))
    ok &= _check("pack b bool", pack("<b", True) == b"\x01")

    # c
    ok &= _check("pack c", pack("<c", b"a") == b"a")
    ok &= _check("unpack c", unpack("<c", b"a") == (b"a",))
    ok &= _expect_raises("c wrong length", ValueError, pack, "<c", b"ab")
    ok &= _expect_raises("c not bytes", ValueError, pack, "<c", 97)

    # x and whitespace
    ok &= _check("calcsize x", calcsize("<3x") == 3)
    ok &= _check("pack x", pack("<3x") == b"\x00" * 3)
    ok &= _check("whitespace between items", pack("< B", 0) == b"\x00")
    ok &= _expect_raises("whitespace between count and char", ValueError, pack, "<2 B", 1, 2)
    ok &= _expect_raises("no prefix", ValueError, pack, "B", 1)
    ok &= _expect_raises("@ prefix", ValueError, pack, "@B", 1)
    ok &= _expect_raises("bad char", ValueError, pack, "<z", 1)
    ok &= _expect_raises("count no char", ValueError, calcsize, "<2")

    # Repeated numeric fields.
    ok &= _check("calcsize <2B", calcsize("<2B") == 2)
    ok &= _check("pack <2B", pack("<2B", 1, 2) == b"\x01\x02")
    ok &= _check("unpack <2B", unpack("<2B", b"\x01\x02") == (1, 2))
    ok &= _expect_raises("too few args", ValueError, pack, "<2B", 1)
    ok &= _expect_raises("too many args", ValueError, pack, "<2B", 1, 2, 3)

    # Repeated scalar fields: each repetition takes/returns its own value.
    ok &= _check("pack <3B", pack("<3B", 1, 2, 3) == b"\x01\x02\x03")
    ok &= _check("unpack <3B", unpack("<3B", b"\x01\x02\x03") == (1, 2, 3))
    ok &= _check("pack >3h", pack(">3h", 1, -2, 3) == b"\x00\x01\xff\xfe\x00\x03")
    ok &= _check("unpack >3h", unpack(">3h", b"\x00\x01\xff\xfe\x00\x03") == (1, -2, 3))
    ok &= _check("pack <2c", pack("<2c", b"a", b"b") == b"ab")
    ok &= _check("unpack <2c", unpack("<2c", b"ab") == (b"a", b"b"))
    ok &= _check("pack <2? mixed", pack("<2?", 1, 0) == b"\x01\x00")
    ok &= _check("pack <2e", pack("<2e", 1.0, 2.0) == b"\x00\x3c\x00\x40")
    ok &= _check("unpack <2e", unpack("<2e", b"\x00\x3c\x00\x40") == (1.0, 2.0))
    ok &= _check("pack <2f", pack("<2f", 1.0, 2.0) == b"\x00\x00\x80\x3f\x00\x00\x00\x40")
    ok &= _check("pack <2d", pack("<2d", 1.0, 2.0) == b"\x00\x00\x00\x00\x00\x00\xf0\x3f\x00\x00\x00\x00\x00\x00\x00\x40")
    ok &= _check("pack <2s", pack("<2s", b"ab", b"cd") == b"abcd")
    ok &= _check("unpack <2s", unpack("<2s", b"abcd") == (b"ab", b"cd"))
    ok &= _check("pack <2p", pack("<2p", b"ab", b"cd") == b"\x02ab\x02cd")
    ok &= _check("unpack <2p", unpack("<2p", b"\x02ab\x02cd") == (b"ab", b"cd"))
    ok &= _expect_raises("repeat too few args", ValueError, pack, "<3B", 1, 2)
    ok &= _expect_raises("repeat too many args", ValueError, pack, "<2c", b"a", b"b", b"c")

    # s and p
    ok &= _check("calcsize <5s", calcsize("<5s") == 5)
    ok &= _check("pack s short", pack("<5s", b"ab") == b"ab\x00\x00\x00")
    ok &= _check("pack s long", pack("<5s", b"abcdef") == b"abcde")
    ok &= _check("unpack s", unpack("<5s", b"abcde") == (b"abcde",))
    ok &= _check("pack s bytearray", pack("<5s", bytearray(b"ab")) == b"ab\x00\x00\x00")
    ok &= _expect_raises("s not bytes", ValueError, pack, "<5s", "ab")

    ok &= _check("calcsize <4p", calcsize("<4p") == 4)
    ok &= _check("pack p short", pack("<4p", b"ab") == b"\x02ab\x00")
    ok &= _check("pack p long", pack("<4p", b"abcdef") == b"\x03abc")
    ok &= _check("unpack p", unpack("<4p", b"\x02ab\x00") == (b"ab",))
    ok &= _check("pack p count 1", pack("<1p", b"abc") == b"\x00")
    ok &= _check("calcsize p0", calcsize("<p0") == 0)
    ok &= _check("pack p0", pack("<p0", b"abc") == b"")
    ok &= _check("unpack p0", unpack("<p0", b"") == (b"",))

    # Floats: exact common values.
    ok &= _check("pack e 1.0", pack("<e", 1.0) == b"\x3c\x00")
    ok &= _check("pack e -1.0", pack("<e", -1.0) == b"\xbc\x00")
    ok &= _check("pack e 65504", pack("<e", 65504) == b"\x7b\xff")
    ok &= _check("pack f 1.0", pack("<f", 1.0) == b"\x00\x00\x80\x3f")
    ok &= _check("pack f -1.0", pack("<f", -1.0) == b"\x00\x00\x80\xc0")
    ok &= _check("pack d 1.0", pack("<d", 1.0) == b"\x00\x00\x00\x00\x00\x00\xf0\x3f")
    ok &= _check("pack d -1.0", pack("<d", -1.0) == b"\x00\x00\x00\x00\x00\x00\xf0\xff")

    # Endianness for floats.
    ok &= _check("pack >e 1.0", pack(">e", 1.0) == b"\x00\x3c")
    ok &= _check("pack >f 1.0", pack(">f", 1.0) == b"\x3f\x80\x00\x00")
    ok &= _check("pack >d 1.0", pack(">d", 1.0) == b"\x3f\xf0\x00\x00\x00\x00\x00\x00")
    ok &= _check("pack !f 1.0", pack("!f", 1.0) == b"\x3f\x80\x00\x00")

    # NaN and inf.
    ok &= _check("pack e nan", pack("<e", float("nan")) == b"\x7e\x00")
    ok &= _check("pack e -nan", pack("<e", -float("nan")) == b"\xfe\x00")
    ok &= _check("pack f nan", pack("<f", float("nan")) == b"\x00\x00\x80\x7f")
    ok &= _check("pack d nan", pack("<d", float("nan")) == b"\x00\x00\x00\x00\x00\x00\xf8\x7f")
    ok &= _check("pack e inf", pack("<e", math.inf) == b"\x7c\x00")
    ok &= _check("pack e -inf", pack("<e", -math.inf) == b"\xfc\x00")
    ok &= _check("pack f inf", pack("<f", math.inf) == b"\x00\x80\x7f\x7f")
    ok &= _check("pack d inf", pack("<d", math.inf) == b"\x00\x00\x00\x00\x00\x00\xf0\x7f")

    # Zero signs.
    ok &= _check("pack e -0.0", pack("<e", -0.0) == b"\x80\x00")
    ok &= _check("pack f -0.0", pack("<f", -0.0) == b"\x00\x00\x00\x80")
    ok &= _check("pack d -0.0", pack("<d", -0.0) == b"\x00\x00\x00\x00\x00\x00\x00\x80")

    # Round-trips.
    for fmt, value in [
        ("<e", 0.5), ("<e", -0.5), ("<e", 1234.5), ("<e", 65504),
        ("<f", 0.5), ("<f", -0.5), ("<f", 1234.5), ("<f", 1e30),
        ("<d", 0.5), ("<d", -0.5), ("<d", 1234.5), ("<d", 1e300),
    ]:
        packed = pack(fmt, value)
        unpacked = unpack(fmt, packed)[0]
        ok &= _check(f"roundtrip {fmt} {value}", unpacked == value)

    # Rounding and overflow for e and f.
    ok &= _expect_raises("e overflow 65520", OverflowError, pack, "<e", 65520)
    ok &= _expect_raises("f overflow", OverflowError, pack, "<f", 3.5e38)
    ok &= _check("e max finite", pack("<e", 65504.0) == b"\x7b\xff")

    # Unpack size mismatch.
    ok &= _expect_raises("unpack size mismatch", ValueError, unpack, "<B", b"\x01\x02")
    ok &= _expect_raises("unpack not bytes", ValueError, unpack, "<B", "ab")

    if ok:
        print("OK all tests passed")
        return 0
    print("SOME TESTS FAILED")
    return 1


def main(argv: list) -> int:
    if argv and argv[0] == "--test":
        return _run_tests()
    return _cli_pack(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
