"""Nearest-neighbour PNG upscaler (stdlib only).

Bicubic/Lanczos resamplers (sips, most image tools) blur pixel art back into
mush. This keeps the hard edges, which is the whole point of the pixelated
register. Usage:  python3 nnscale.py in.png out.png FACTOR
"""
import struct, zlib, sys


def decode(fn):
    d = open(fn, 'rb').read()
    assert d[:8] == b'\x89PNG\r\n\x1a\n', "not a PNG"
    pos, idat, w = 8, b'', None
    while pos < len(d):
        ln = struct.unpack('>I', d[pos:pos + 4])[0]
        typ = d[pos + 4:pos + 8]
        body = d[pos + 8:pos + 8 + ln]
        if typ == b'IHDR':
            w, h, bd, ct, comp, filt, inter = struct.unpack('>IIBBBBB', body)
            assert bd == 8 and ct in (2, 6) and inter == 0, \
                f"unsupported PNG (bitdepth={bd} colortype={ct} interlace={inter})"
        elif typ == b'IDAT':
            idat += body
        pos += 12 + ln
    raw = zlib.decompress(idat)
    nch = 4 if ct == 6 else 3
    stride = w * nch
    out, prev, p = [], bytearray(stride), 0
    for _ in range(h):
        f = raw[p]; p += 1
        line = bytearray(raw[p:p + stride]); p += stride
        for i in range(stride):
            a = line[i - nch] if i >= nch else 0
            b = prev[i]
            c = prev[i - nch] if i >= nch else 0
            if f == 1:   line[i] = (line[i] + a) & 0xff
            elif f == 2: line[i] = (line[i] + b) & 0xff
            elif f == 3: line[i] = (line[i] + (a + b) // 2) & 0xff
            elif f == 4:
                pp = a + b - c
                pa, pb, pc = abs(pp - a), abs(pp - b), abs(pp - c)
                line[i] = (line[i] + (a if (pa <= pb and pa <= pc)
                                      else (b if pb <= pc else c))) & 0xff
        out.append(bytes(line)); prev = line
    return w, h, nch, out


def encode(fn, w, h, nch, rows):
    ihdr = struct.pack('>IIBBBBB', w, h, 8, 6 if nch == 4 else 2, 0, 0, 0)
    raw = b''.join(b'\x00' + r for r in rows)

    def chunk(t, b):
        return (struct.pack('>I', len(b)) + t + b +
                struct.pack('>I', zlib.crc32(t + b) & 0xffffffff))
    open(fn, 'wb').write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) +
                         chunk(b'IDAT', zlib.compress(raw, 9)) +
                         chunk(b'IEND', b''))


def upscale(src, dst, factor):
    w, h, nch, rows = decode(src)
    big = []
    for r in rows:
        wide = bytearray(w * factor * nch)
        for x in range(w):
            px = r[x * nch:(x + 1) * nch]
            for k in range(factor):
                o = (x * factor + k) * nch
                wide[o:o + nch] = px
        wide = bytes(wide)
        big.extend([wide] * factor)
    encode(dst, w * factor, h * factor, nch, big)
    return w * factor, h * factor


if __name__ == "__main__":
    src, dst, f = sys.argv[1], sys.argv[2], int(sys.argv[3])
    print("wrote", dst, "%dx%d" % upscale(src, dst, f))
