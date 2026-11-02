"""A correct solution of battery 4's struct task for validating the checker: struct (the reference
itself) behind the goal's byte-order rule. BUG picks a deliberate defect for the bad variants
(mkvariants4.py); "" is the correct version."""
import math
import re
import struct as _struct

BUG = "c_bytearray"


class StructError(ValueError):
    pass


def _fmt(fmt):
    if not isinstance(fmt, str) or not fmt:
        raise StructError("bad format")
    if fmt[0] not in "<>!=" and BUG != "noprefix_ok":
        raise StructError("a format must start with <, >, ! or =")
    if BUG == "ws_count":
        fmt = fmt[0] + re.sub(r"\s+", "", fmt[1:])
    return fmt


def _half_trunc(order, x):
    """Half precision with truncation instead of rounding (the e_trunc defect)."""
    sign = 0x8000 if math.copysign(1.0, x) < 0 else 0
    x = abs(x)
    if x == 0:
        bits = 0
    else:
        m, e = math.frexp(x)
        e -= 1
        if e > 15:
            raise OverflowError("float too large to pack with e format")
        bits = int(x / 2.0 ** -24) if e < -14 else ((e + 15) << 10) | int((m * 2 - 1) * 1024)
    return (bits | sign).to_bytes(2, "big" if order in ">!" else "little")


def pack(fmt, *values):
    fmt = _fmt(fmt)
    if BUG == "c_bytearray":
        values = tuple(bytes(v) if isinstance(v, bytearray) else v for v in values)
    if (BUG == "e_trunc" and re.fullmatch(r"[<>!=]e", fmt) and len(values) == 1
            and isinstance(values[0], float) and math.isfinite(values[0])):
        return _half_trunc(fmt[0], values[0])
    try:
        return _struct.pack(fmt, *values)
    except _struct.error as e:
        raise StructError(str(e)) from None
    except OverflowError as e:
        if BUG == "overflow_as_value":
            raise StructError(str(e)) from None
        raise


def unpack(fmt, data):
    fmt = _fmt(fmt)
    try:
        if BUG == "unpack_lenient":
            data = data[:_struct.calcsize(fmt)]
        return _struct.unpack(fmt, data)
    except _struct.error as e:
        raise StructError(str(e)) from None


def calcsize(fmt):
    fmt = _fmt(fmt)
    try:
        return _struct.calcsize(fmt)
    except _struct.error as e:
        raise StructError(str(e)) from None
