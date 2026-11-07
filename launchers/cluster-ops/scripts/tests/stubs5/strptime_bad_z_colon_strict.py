"""A correct solution of battery 5's strptime task for validating the checker, written from the goal alone
(its own regex table and rules, no datetime.strptime), so a full score also shows that the goal states
every rule the cases depend on. BUG picks a deliberate defect for the bad variants (mkvariants5.py); ""
is the correct version."""
import datetime
import re

BUG = "z_colon_strict"

WD = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MON = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
       "november", "december"]


def _names(seq):
    return "|".join(sorted(seq, key=len, reverse=True))


FORMS = {"d": r"3[01]|[12]\d|0[1-9]|[1-9]| [1-9]", "m": r"1[0-2]|0[1-9]|[1-9]", "y": r"\d\d", "Y": r"\d\d\d\d",
         "H": r"2[0-3]|[01]\d|\d", "I": r"1[0-2]|0[1-9]|[1-9]", "M": r"[0-5]\d|\d", "S": r"6[01]|[0-5]\d|\d",
         "f": r"[0-9]{1,6}", "j": r"36[0-6]|3[0-5]\d|[12]\d\d|0[1-9]\d|00[1-9]|[1-9]\d|0[1-9]|[1-9]",
         "U": r"5[0-3]|[0-4]\d|\d", "W": r"5[0-3]|[0-4]\d|\d", "V": r"5[0-3]|0[1-9]|[1-4]\d|\d", "G": r"\d\d\d\d",
         "w": r"[0-6]", "u": r"[1-7]", "a": _names(w[:3] for w in WD), "A": _names(WD),
         "b": _names(m[:3] for m in MON), "B": _names(MON), "p": r"am|pm",
         "z": r"[+-]\d\d:?[0-5]\d(?::?[0-5]\d(?:\.\d{1,6})?)?|(?-i:Z)"}


def pattern(fmt):
    out, i = [], 0
    while i < len(fmt):
        c = fmt[i]
        if c == "%":
            if i + 1 >= len(fmt):
                raise ValueError("stray % in format")
            k = fmt[i + 1]
            if k == "%":
                out.append("%")
            elif k in FORMS:
                out.append(f"(?P<{k}>{FORMS[k]})")
            else:
                raise ValueError(f"'{k}' is a bad directive")
            i += 2
        elif c.isspace():
            j = i
            while j < len(fmt) and fmt[j].isspace():
                j += 1
            out.append(re.escape(fmt[i:j]) if BUG == "ws_exact" else r"\s+")
            i = j
        else:
            out.append(re.escape(c))
            i += 1
    return "".join(out)


def offset(v):
    if v == "Z":
        return datetime.timezone.utc
    sign, s = (-1 if v[0] == "-" else 1), v[1:]
    if s[2] == ":":
        s = s[:2] + s[3:]
        if len(s) > 4:
            if s[4] != ":":
                raise ValueError("inconsistent use of :")
            s = s[:4] + s[5:]
    elif ":" in s:
        raise ValueError("inconsistent use of :")
    elif BUG == "z_colon_strict":
        raise ValueError("colons required")
    frac = s[7:] if len(s) > 6 else ""
    td = datetime.timedelta(hours=int(s[0:2]), minutes=int(s[2:4]), seconds=int(s[4:6] or 0),
                            microseconds=int(frac.ljust(6, "0")) if frac else 0)
    return datetime.timezone(td * sign)


def strptime(text, fmt):
    m = re.match(pattern(fmt), text, 0 if BUG == "no_ci" else re.IGNORECASE)
    if not m or m.end() != len(text):
        raise ValueError(f"time data {text!r} does not match format {fmt!r}")
    gd = m.groupdict()
    year = iso_year = iso_week = week = week_start = weekday = julian = tz = None
    month = day = 1
    hour = minute = second = fraction = 0
    items = list(gd.items())
    if BUG == "first_wins":
        items.reverse()
    for k, v in items:
        if k == "y":
            y = int(v)
            year = y + (2000 if y < (50 if BUG == "pivot_50" else 69) else 1900)
        elif k == "Y":
            year = int(v)
        elif k == "G":
            iso_year = int(v)
        elif k == "m":
            month = int(v)
        elif k == "B":
            month = MON.index(v.lower()) + 1
        elif k == "b":
            month = [x[:3] for x in MON].index(v.lower()) + 1
        elif k == "d":
            day = int(v)
        elif k == "H":
            hour = int(v)
        elif k == "I":
            h, p = int(v), (gd.get("p") or "").lower()
            if p == "pm":
                hour = h if h == 12 else h + 12
            else:
                hour = h if (h != 12 or (BUG == "I_no_am" and not p)) else 0
        elif k == "M":
            minute = int(v)
        elif k == "S":
            second = int(v)
        elif k == "f":
            fraction = int(v) if BUG == "f_left" else int(v.ljust(6, "0"))
        elif k == "A":
            weekday = WD.index(v.lower())
        elif k == "a":
            weekday = [x[:3] for x in WD].index(v.lower())
        elif k == "w":
            weekday = (int(v) - 1) % 7
        elif k == "u":
            weekday = int(v) - 1
        elif k == "j":
            julian = None if BUG == "j_ignored" else int(v)
        elif k in "UW":
            week, week_start = int(v), k
        elif k == "V":
            iso_week = int(v)
        elif k == "z":
            tz = offset(v)
    if iso_year is not None and (iso_week is None or weekday is None or julian is not None):
        raise ValueError("%G needs %V and a weekday, and can't be used with %j")
    if iso_week is not None and iso_year is None:
        raise ValueError("%V needs %G")
    if year is None:
        year = 1904 if BUG == "leap_default" and (month, day) == (2, 29) else 1900
    date = None
    if iso_year is not None:
        jan4 = datetime.date(iso_year, 1, 4)
        date = datetime.date.fromordinal(jan4.toordinal() - jan4.weekday() + 7 * (iso_week - 1) + weekday)
    elif julian is None and weekday is not None and week is not None:
        f, d = datetime.date(year, 1, 1).weekday(), weekday
        if week_start == "U":
            f, d = (f + 1) % 7, (d + 1) % 7
        if BUG == "uw_simple":
            julian = 7 * week + d - f + 1
        else:
            julian = 1 + d - f if week == 0 else 1 + (7 - f) % 7 + 7 * (week - 1) + d
    if julian is not None:
        date = datetime.date.fromordinal(datetime.date(year, 1, 1).toordinal() + julian - 1)
    if date is not None:
        year, month, day = date.year, date.month, date.day
    return datetime.datetime(year, month, day, hour, minute, second, fraction, tz)


if __name__ == "__main__":
    import sys
    print(repr(strptime(sys.argv[1], sys.argv[2])))
