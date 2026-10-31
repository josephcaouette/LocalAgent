import re, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from battery_checks import ref_slots
def _t(s):
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", s):
        raise ValueError(s)
def free_slots(busy, day_start, day_end, min_length):
    for a, b in busy:
        _t(a); _t(b)
        if a >= b: raise ValueError("start >= end")
    _t(day_start); _t(day_end)
    if day_start >= day_end: raise ValueError("day")
    return ref_slots(busy, day_start, day_end, min_length)
