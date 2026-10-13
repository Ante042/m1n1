#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate the built-in Omarchy logo assets from the Omarchy icon.

The source is icon.png of github.com/omacom/omarchy (300x300 RGBA, kept
here as omarchy_source.png). The mark is put on black and scaled to the
full logo size by sampling the nearest source pixel, so it fills the logo
like the logo stage 2 m1n1 shows and stays two-coloured.
The result is written as omarchy_<size>.bin (raw RGBA, the format of the
other built-in logos) and omarchy_<size>.png. Only the Python standard
library is used, so the output does not depend on an imaging library
version.
"""

from pathlib import Path
import argparse
import struct
import zlib

SIZES = (128, 256)
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def read_png_rgba(path):
    data = path.read_bytes()
    if not data.startswith(PNG_MAGIC):
        raise ValueError(f"{path}: not a PNG file")
    pos = len(PNG_MAGIC)
    idat = b""
    header = None
    while pos < len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            idat += body
        elif kind == b"IEND":
            break
    if header is None:
        raise ValueError(f"{path}: no IHDR")
    width, height, depth, colour, _, _, interlace = header
    if (depth, colour, interlace) != (8, 6, 0):
        raise ValueError(f"{path}: need 8-bit non-interlaced RGBA")

    raw = zlib.decompress(idat)
    stride = width * 4
    rows = []
    prev = bytearray(stride)
    for y in range(height):
        filt = raw[y * (stride + 1)]
        line = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - 4] if i >= 4 else 0
            b = prev[i]
            c = prev[i - 4] if i >= 4 else 0
            if filt == 1:
                line[i] = (line[i] + a) & 0xff
            elif filt == 2:
                line[i] = (line[i] + b) & 0xff
            elif filt == 3:
                line[i] = (line[i] + (a + b) // 2) & 0xff
            elif filt == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                line[i] = (line[i] + pred) & 0xff
            elif filt != 0:
                raise ValueError(f"{path}: bad filter {filt}")
        rows.append(bytes(line))
        prev = line
    return width, height, b"".join(rows)


def write_png_rgb(path, size, rgb):
    def chunk(kind, body):
        crc = zlib.crc32(kind + body) & 0xffffffff
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", crc)

    stride = size * 3
    raw = b"".join(b"\0" + rgb[y * stride:(y + 1) * stride] for y in range(size))
    path.write_bytes(PNG_MAGIC
                     + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw, 9))
                     + chunk(b"IEND", b""))


def render(width, height, rgba, size):
    rgb = bytearray(size * size * 3)
    for y in range(size):
        sy = (2 * y + 1) * height // (2 * size)
        for x in range(size):
            sx = (2 * x + 1) * width // (2 * size)
            px = rgba[(sy * width + sx) * 4:(sy * width + sx + 1) * 4]
            # Composite on black: each channel times alpha.
            i = (y * size + x) * 3
            rgb[i:i + 3] = bytes((px[c] * px[3] + 127) // 255 for c in range(3))
    return bytes(rgb)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parent)
    args = parser.parse_args()

    width, height, rgba = read_png_rgba(args.source)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for size in SIZES:
        rgb = render(width, height, rgba, size)
        write_png_rgb(args.output_dir / f"omarchy_{size}.png", size, rgb)
        out = bytearray()
        for i in range(0, len(rgb), 3):
            out += rgb[i:i + 3] + b"\xff"
        (args.output_dir / f"omarchy_{size}.bin").write_bytes(bytes(out))


if __name__ == "__main__":
    main()
