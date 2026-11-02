"""Correct wrapper for battery 3's ipv6 goal (validates the checker; not pipeline code)."""
import ipaddress

LONGER = lambda run, best: run > best   # noqa: E731  (the bad stubs change this line)
MIN_RUN = 2


def normalize_ipv6(text):
    if "%" in text:
        raise ValueError("zone index")
    text = prepare(text)
    p = ipaddress.IPv6Address(text).packed
    g = [int.from_bytes(p[i:i + 2], "big") for i in range(0, 16, 2)]
    best_start, best_len, i = -1, 0, 0
    while i < 8:
        if g[i] == 0:
            j = i
            while j < 8 and g[j] == 0:
                j += 1
            if LONGER(j - i, best_len):
                best_start, best_len = i, j - i
            i = j
        else:
            i += 1
    parts = [format(x, "x") for x in g]
    if best_len >= MIN_RUN:
        return ":".join(parts[:best_start]) + "::" + ":".join(parts[best_start + best_len:])
    return ":".join(parts)


def prepare(text):
    return text
