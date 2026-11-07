"""A correct solution of battery 5's fmtspec task for validating the checker, written from the goal alone
(no format(), %, str.format or decimal), so a full score also shows that the goal states every rule the
cases depend on. BUG picks a deliberate defect for the bad variants (mkvariants5.py); "" is the correct
version."""
BUG = ""


def parse(spec, kind):
    n, i = len(spec), 0
    fill = align = sign = None
    if n >= 2 and spec[1] in "<>=^":
        fill, align, i = spec[0], spec[1], 2
    elif n >= 1 and spec[0] in "<>=^":
        align, i = spec[0], 1
    if i < n and spec[i] in "+- ":
        sign, i = spec[i], i + 1
    z = i < n and spec[i] == "z"
    i += z
    alt = i < n and spec[i] == "#"
    i += alt
    zero = fill is None and i < n and spec[i] == "0"
    i += zero
    j = i
    while j < n and "0" <= spec[j] <= "9":
        j += 1
    width, i = (int(spec[i:j]) if j > i else 0), j
    group = None
    if i < n and spec[i] == ",":
        group, i = ",", i + 1
    if i < n and spec[i] == "_":
        if group:
            raise ValueError("Cannot specify both ',' and '_'.")
        group, i = "_", i + 1
    if i < n and spec[i] == "," and group == "_":
        raise ValueError("Cannot specify both ',' and '_'.")
    prec = None
    if i < n and spec[i] == ".":
        j = i + 1
        while j < n and "0" <= spec[j] <= "9":
            j += 1
        if j == i + 1:
            raise ValueError("Format specifier missing precision")
        prec, i = int(spec[i + 1:j]), j
    if n - i > 1:
        raise ValueError("Invalid format specifier")
    t = spec[i] if i < n else {"int": "d", "str": "s", "float": ""}[kind]
    gn = 3
    if group:
        if t in ("b", "o", "x", "X") and group == "_":
            gn = 4
        elif t not in ("d", "e", "f", "g", "E", "G", "%", "F", ""):
            raise ValueError(f"Cannot specify '{group}' with '{t}'.")
    if BUG == "z_ignored":
        z = False
    return dict(fill=fill, align=align, sign=sign, z=z, alt=alt, zero=zero, width=width, group=group, gn=gn,
                prec=prec, t=t)


def rhe(num, den, k):
    """num/den * 10**k rounded to an integer, ties to even."""
    if k >= 0:
        num *= 10 ** k
    else:
        den *= 10 ** -k
    q, r = divmod(num, den)
    if 2 * r > den or (2 * r == den and (q & 1 or BUG == "half_up")):
        q += 1
    return q


def exp10(num, den):
    def ge(e):
        return num >= den * 10 ** e if e >= 0 else num * 10 ** -e >= den
    e = len(str(num)) - len(str(den))
    while not ge(e):
        e -= 1
    while ge(e + 1):
        e += 1
    return e


def sig(num, den, p):
    """(digits, exponent) of num/den rounded to p significant digits."""
    if num == 0:
        return "0" * p, 0
    e = exp10(num, den)
    q = rhe(num, den, p - 1 - e)
    if q >= 10 ** p:
        q, e = q // 10, e + 1
    return str(q), e


def layout(digits, decpt, code, precision, alt, dot0, upper):
    """CPython's placement of digits around the decimal point (format_float_short)."""
    use_exp, vend = False, len(digits)
    if code == "e":
        use_exp, vend = True, precision
    elif code == "f":
        vend = decpt + precision
    elif code == "g":
        use_exp = decpt <= -4 or decpt > (precision - 1 if dot0 else precision)
        if alt:
            vend = precision
    else:
        use_exp = decpt <= -4 or decpt > (17 if BUG == "repr_exp17" else 16)
    exp = 0
    if use_exp:
        exp, decpt = decpt - 1, 1
    vstart = decpt - 1 if decpt <= 0 else 0
    vend = max(vend, decpt + 1) if (not use_exp and dot0) else max(vend, decpt)
    s = []
    for idx in range(vstart, vend):
        if idx == decpt:
            s.append(".")
        s.append(digits[idx] if 0 <= idx < len(digits) else "0")
    if decpt == vend:
        s.append(".")
    out = "".join(s)
    if out.endswith(".") and not alt:
        out = out[:-1]
    if use_exp:
        out += ("E" if upper else "e") + ("-" if exp < 0 else "+") + str(abs(exp)).zfill(2)
    return out


def float_body(x, t, prec, alt, z, scale=1):
    """(sign, text) for a float, like PyOS_double_to_string."""
    upper = t in ("E", "F", "G")
    if x != x:
        return "", "NAN" if upper else "nan"
    neg = x < 0 or (x == 0 and str(x)[0] == "-")
    if x in (float("inf"), float("-inf")):
        return ("-" if neg else ""), "INF" if upper else "inf"
    num, den = abs(x).as_integer_ratio()
    num *= scale
    dot0 = False
    if t == "":
        if prec is None:
            r = repr(abs(x))
            m, _, ex = r.partition("e")
            ip, _, fp = m.partition(".")
            digits, decpt = (ip + fp).lstrip("0"), len(ip) + int(ex or 0)
            decpt -= len(ip + fp) - len((ip + fp).lstrip("0"))
            digits = digits.rstrip("0") or "0"
            if digits == "0":
                decpt = 1
            code, p, dot0 = "r", 0, True
        else:
            t, dot0 = "g", True
    if t in ("f", "F"):
        p = 6 if prec is None else prec
        q = rhe(num, den, p)
        digits, decpt, code = (str(q), len(str(q)) - p, "f") if q else ("0", 1, "f")
    elif t in ("e", "E"):
        p = (6 if prec is None else prec) + 1
        digits, e = sig(num, den, p)
        decpt, code = e + 1, "e"
    elif t in ("g", "G"):
        p = max(1, 6 if prec is None else prec)
        digits, e = sig(num, den, p)
        decpt, code = e + 1, "g"
        digits = digits.rstrip("0") or "0"
        if digits == "0":
            decpt = 1
    if z and neg and digits.strip("0") == "":
        neg = False
    alt_keep = alt and not (BUG == "g_strip" and code == "g")
    return ("-" if neg else ""), layout(digits, decpt, code, p, alt_keep, dot0, upper)


def group(digits, min_width, sep, n):
    if not sep:
        return digits.rjust(max(min_width, len(digits), 1), "0")
    out, remaining, pos, mw = [], len(digits), len(digits), max(0, min_width)
    while True:
        ln = min(n, max(remaining, mw, 1))
        nz, nc = max(0, ln - remaining), max(0, min(remaining, ln))
        out.append("0" * nz + digits[pos - nc:pos])
        pos, remaining, mw = pos - nc, remaining - nc, mw - ln
        if remaining <= 0 and (mw <= 0 or BUG == "sep_start" and mw <= 1):
            break
        mw -= 1
    return sep.join(reversed(out))


def pad(sp, signc, prefix, intdigits, rest, numeric=True):
    fill = sp["fill"] if sp["fill"] is not None else ("0" if sp["zero"] else " ")
    align = sp["align"] or ("=" if sp["zero"] and numeric else (">" if numeric else "<"))
    if not numeric and sp["zero"] and BUG == "str_zero_right" and not sp["align"]:
        align = ">"
    width = sp["width"]
    non_digit = len(signc) + len(prefix) + len(rest)
    min_width = width - non_digit if fill == "0" and align == "=" and BUG != "no_zero_group" else 0
    grouped = group(intdigits, min_width, sp["group"], sp["gn"]) if intdigits else ""
    body = signc + prefix + grouped + rest
    n = width - len(body)
    if n <= 0:
        return body
    if align == "<":
        return body + fill * n
    if align == ">":
        return fill * n + body
    if align == "^":
        return fill * (n // 2) + body + fill * (n - n // 2)
    return signc + prefix + fill * n + grouped + rest


def split_digits(text):
    i = 0
    while i < len(text) and "0" <= text[i] <= "9":
        i += 1
    return text[:i], text[i:]


def fmt(value, spec):
    if isinstance(value, str):
        sp = parse(spec, "str")
        if sp["t"] != "s":
            raise ValueError(f"Unknown format code '{sp['t']}' for object of type 'str'")
        if sp["sign"] or sp["z"] or sp["alt"] or sp["align"] == "=":
            raise ValueError("not allowed in string format specifier")
        s = value if sp["prec"] is None else value[:sp["prec"]]
        return pad(sp, "", "", "", s, numeric=False)
    kind = "int" if isinstance(value, int) else "float"
    sp = parse(spec, kind)
    t = sp["t"]
    if kind == "int" and t in "bcdoxX":
        if sp["prec"] is not None and BUG != "int_precision_ok":
            raise ValueError("Precision not allowed in integer format specifier")
        if sp["z"]:
            raise ValueError("Negative zero coercion (z) not allowed in integer format specifier")
        if t == "c":
            if sp["sign"] or sp["alt"]:
                raise ValueError("Sign or alternate form not allowed with 'c'")
            if not 0 <= value < 0x110000:
                if BUG != "c_wrap":
                    raise OverflowError("%c arg not in range(0x110000)")
                value %= 0x110000
            return pad(sp, "", "", "", chr(value))
        a = abs(value)
        digits = {"b": bin, "o": oct, "x": hex, "X": hex, "d": lambda v: "--" + str(v)}[t](a)[2:]
        digits = digits.upper() if t == "X" else digits
        prefix = {"b": "0b", "o": "0o", "x": "0x", "X": "0X"}.get(t, "") if sp["alt"] else ""
        signc = "-" if value < 0 else (sp["sign"] if sp["sign"] in ("+", " ") else "")
        return pad(sp, signc, prefix, digits, "")
    if t not in ("e", "E", "f", "F", "g", "G", "%", ""):
        raise ValueError(f"Unknown format code '{t}' for object of type '{kind}'")
    x = float(value)
    pct = t == "%"
    scale = 100 if pct and BUG == "pct_exact" else 1
    if pct and scale == 1:
        x = x * 100
    neg, body = float_body(x, "f" if pct else t, sp["prec"], sp["alt"], sp["z"], scale)
    if pct:
        body += "%"
    signc = neg or (sp["sign"] if sp["sign"] in ("+", " ") else "")
    intdigits, rest = split_digits(body)
    return pad(sp, signc, "", intdigits, rest)


if __name__ == "__main__":
    import sys
    v = sys.argv[1]
    for conv in (int, float, str):
        try:
            v = conv(v)
            break
        except ValueError:
            pass
    print(fmt(v, sys.argv[2]))
