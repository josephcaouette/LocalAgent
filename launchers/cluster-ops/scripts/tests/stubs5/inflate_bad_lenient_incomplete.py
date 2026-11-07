"""A correct solution of battery 5's inflate task for validating the checker, written from the goal alone
(no zlib), so a full score also shows that the goal states every rule the cases depend on. BUG picks a
deliberate defect for the bad variants (mkvariants5.py); "" is the correct version."""
BUG = "lenient_incomplete"

LBASE = [3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 19, 23, 27, 31, 35, 43, 51, 59, 67, 83, 99, 115, 131, 163, 195,
         227, 258]
LEXT = [0] * 8 + [1] * 4 + [2] * 4 + [3] * 4 + [4] * 4 + [5] * 4 + [0]
DBASE = [1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 33, 49, 65, 97, 129, 193, 257, 385, 513, 769, 1025, 1537, 2049, 3073,
         4097, 6145, 8193, 12289, 16385, 24577]
DEXT = [0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10, 10, 11, 11, 12, 12, 13, 13]
ORDER = [16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15]
CRC = []
for _n in range(256):
    _c = _n
    for _ in range(8):
        _c = (_c >> 1) ^ 0xEDB88320 if _c & 1 else _c >> 1
    CRC.append(_c)


def crc32(data, c=0):
    c ^= 0xFFFFFFFF
    for b in data:
        c = CRC[(c ^ b) & 255] ^ (c >> 8)
    return c ^ 0xFFFFFFFF


def adler32(data):
    a, b = 1, 0
    for i in range(0, len(data), 3800):
        for x in data[i:i + 3800]:
            a += x
            b += a
        a %= 65521
        b %= 65521
    return (b << 16) | a


def table(lengths, kind):
    """(decoding list indexed by the next maxlen bits, maxlen), or None for a code with no symbols."""
    count = [0] * 16
    for n in lengths:
        count[n] += 1
    count[0] = 0
    maxlen = max([n for n in range(16) if count[n]] or [0])
    if maxlen == 0:
        if kind == "cl":
            raise ValueError("empty code-length code")
        return None
    left = 1
    for n in range(1, 16):
        left = (left << 1) - count[n]
        if left < 0:
            raise ValueError("over-subscribed code")
    if left > 0 and BUG != "lenient_incomplete" and (kind == "cl" or maxlen != 1):
        raise ValueError("incomplete code")
    code, nxt = 0, [0] * 16
    for n in range(1, 16):
        code = (code + count[n - 1]) << 1
        nxt[n] = code
    tab = [-1] * (1 << maxlen)
    for sym, n in enumerate(lengths):
        if n:
            r = int(bin(nxt[n])[2:].zfill(n)[::-1], 2)
            nxt[n] += 1
            tab[r::1 << n] = [(sym << 4) | n] * (1 << (maxlen - n))
    return tab, maxlen


FIXED = None


class Reader:
    def __init__(self, data, pos):
        self.d, self.pos, self.acc, self.n, self.limit = data, pos, 0, 0, 8 * len(data)

    def need(self, k):
        while self.n < k:
            self.acc |= (self.d[self.pos] if self.pos < len(self.d) else 0) << self.n
            self.pos += 1
            self.n += 8

    def check(self):
        if self.pos * 8 - self.n > self.limit:
            raise ValueError("incomplete or truncated stream")

    def bits(self, k):
        self.need(k)
        v = self.acc & ((1 << k) - 1)
        self.acc >>= k
        self.n -= k
        self.check()
        return v

    def sym(self, tab):
        if tab is None:
            raise ValueError("invalid code")
        t, maxlen = tab
        if self.n < maxlen:
            self.need(maxlen)
        e = t[self.acc & ((1 << maxlen) - 1)]
        if e < 0:
            raise ValueError("invalid code")
        n = e & 15
        self.acc >>= n
        self.n -= n
        if self.pos * 8 - self.n > self.limit:
            raise ValueError("incomplete or truncated stream")
        return e >> 4

    def byte_end(self):
        return self.pos - self.n // 8


def inflate(data, pos):
    """Decode raw deflate from data[pos:]: (output, position of the byte after the last block)."""
    global FIXED
    r, out = Reader(data, pos), bytearray()
    while True:
        final, btype = r.bits(1), r.bits(2)
        if btype == 0:
            r.bits(r.n % 8)
            ln, nl = r.bits(16), r.bits(16)
            if ln != (~nl & 0xFFFF) and BUG != "nlen_unchecked":
                raise ValueError("invalid stored block lengths")
            while ln and r.n:
                out.append(r.bits(8))
                ln -= 1
            if r.pos + ln > len(data):
                raise ValueError("incomplete or truncated stream")
            out += data[r.pos:r.pos + ln]
            r.pos += ln
        elif btype == 3:
            raise ValueError("invalid block type")
        else:
            if btype == 1:
                if FIXED is None:
                    FIXED = (table([8] * 144 + [9] * 112 + [7] * 24 + [8] * 8, "lit"), table([5] * 32, "dist"))
                lit, dist = FIXED
            else:
                hlit, hdist, hclen = r.bits(5) + 257, r.bits(5) + 1, r.bits(4) + 4
                if hlit > 286 or hdist > 30:
                    raise ValueError("too many length or distance symbols")
                cl = [0] * 19
                for i in range(hclen):
                    cl[ORDER[i]] = r.bits(3)
                clt = table(cl, "cl")
                lens = []
                while len(lens) < hlit + hdist:
                    s = r.sym(clt)
                    if s < 16:
                        lens.append(s)
                        continue
                    if s == 16:
                        if not lens or (BUG == "cl_split" and len(lens) == hlit):
                            raise ValueError("invalid bit length repeat")
                        val, rep = lens[-1], 3 + r.bits(2)
                    else:
                        val, rep = 0, (3 + r.bits(3)) if s == 17 else (11 + r.bits(7))
                    end = hlit if BUG == "cl_split" and len(lens) < hlit else hlit + hdist
                    if len(lens) + rep > end:
                        raise ValueError("invalid bit length repeat")
                    lens += [val] * rep
                if lens[256] == 0:
                    raise ValueError("invalid code -- missing end-of-block")
                lit, dist = table(lens[:hlit], "lit"), table(lens[hlit:], "dist")
            while True:
                s = r.sym(lit)
                if s < 256:
                    out.append(s)
                    continue
                if s == 256:
                    break
                if s > 285:
                    raise ValueError("invalid literal/length code")
                length = LBASE[s - 257] + (r.bits(LEXT[s - 257]) if LEXT[s - 257] else 0)
                ds = r.sym(dist)
                if ds > 29:
                    raise ValueError("invalid distance code")
                d = DBASE[ds] + (r.bits(DEXT[ds]) if DEXT[ds] else 0)
                if d > len(out):
                    if BUG == "no_far_check":
                        out += bytes(length)
                        continue
                    raise ValueError("invalid distance too far back")
                start = len(out) - d
                if length <= d:
                    out += out[start:start + length]
                else:
                    out += (out[start:] * (length // d + 1))[:length]
        if final:
            return out, r.byte_end()


def decompress(data, wbits=15):
    data = bytes(data)
    if not data and BUG == "empty_ok":
        return b""
    if wbits == -15:
        out, end = inflate(data, 0)
    elif wbits == 15:
        if len(data) < 2:
            raise ValueError("incomplete or truncated stream")
        cmf, flg = data[0], data[1]
        if (cmf * 256 + flg) % 31 or cmf & 15 != 8 or cmf >> 4 > 7 or flg & 0x20:
            raise ValueError("bad zlib header")
        out, end = inflate(data, 2)
        if end + 4 > len(data):
            raise ValueError("incomplete or truncated stream")
        if int.from_bytes(data[end:end + 4], "big") != adler32(out) and BUG != "no_adler":
            raise ValueError("incorrect data check")
        end += 4
    elif wbits == 31:
        out, end = gunzip(data, 0)
        while BUG == "gzip_multi" and end < len(data):
            more, end = gunzip(data, end)
            out += more
    else:
        raise ValueError("unsupported wbits")
    if BUG == "trailing_error" and end < len(data):
        raise ValueError("trailing data")
    return bytes(out)


def gunzip(data, p):
    def take(n):
        nonlocal p
        if p + n > len(data):
            raise ValueError("incomplete or truncated stream")
        p += n
        return data[p - n:p]
    start = p
    head = take(10)
    if head[:2] != b"\x1f\x8b" or head[2] != 8 or head[3] & 0xE0:
        raise ValueError("bad gzip header")
    flags = head[3]
    if flags & 4:
        take(int.from_bytes(take(2), "little"))
    for bit in (8, 16):
        if flags & bit:
            while take(1) != b"\x00":
                pass
    if flags & 2:
        want = crc32(data[start:p]) & 0xFFFF
        if int.from_bytes(take(2), "little") != want and BUG != "no_hcrc":
            raise ValueError("header crc mismatch")
    out, p = inflate(data, p)
    tail = take(8)
    if int.from_bytes(tail[:4], "little") != crc32(out) or int.from_bytes(tail[4:], "little") != len(out) & 0xFFFFFFFF:
        raise ValueError("incorrect data check")
    return out, p


if __name__ == "__main__":
    import sys
    with open(sys.argv[1], "rb") as f:
        sys.stdout.buffer.write(decompress(f.read(), int(sys.argv[2]) if len(sys.argv) > 2 else 15))
