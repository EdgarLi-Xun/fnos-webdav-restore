#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate teal restore-arrow PNG icons for the FPK package."""
import math
import os
import struct
import zlib

ROOT = os.path.dirname(os.path.abspath(__file__))


def chunk(tag, data):
    crc = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


def write_png(path, width, pixels):
    height = width
    raw = b""
    row = width * 3
    for y in range(height):
        raw += b"\x00" + pixels[y * row : (y + 1) * row]
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
    data += chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    with open(path, "wb") as handle:
        handle.write(data)


def lerp(a, b, t):
    return int(a + (b - a) * t)


def draw(size):
    bg = (8, 47, 54)
    fill = (8, 127, 140)
    white = (245, 250, 252)
    cx = cy = (size - 1) / 2.0
    r_out = size * 0.42
    r_in = size * 0.28
    pixels = bytearray(size * size * 3)
    for y in range(size):
        for x in range(size):
            dx = x - cx
            dy = y - cy
            dist = math.hypot(dx, dy)
            ang = (math.atan2(dy, dx) + math.pi) / (2 * math.pi)
            color = bg
            if dist <= r_out + 1:
                edge = max(0.0, min(1.0, r_out + 1 - dist))
                color = (
                    lerp(bg[0], fill[0], edge),
                    lerp(bg[1], fill[1], edge),
                    lerp(bg[2], fill[2], edge),
                )
            ring = abs(dist - (r_in + r_out) / 2)
            ring_w = (r_out - r_in) / 2
            in_arc_a = 0.08 <= ang <= 0.46
            in_arc_b = 0.58 <= ang <= 0.96
            if ring <= ring_w and (in_arc_a or in_arc_b):
                t = max(0.0, min(1.0, 1.2 - ring / ring_w))
                color = (
                    lerp(color[0], white[0], t),
                    lerp(color[1], white[1], t),
                    lerp(color[2], white[2], t),
                )
            # arrow heads
            for head_ang in (0.46, 0.96):
                rad = (r_in + r_out) / 2
                hx = cx + math.cos(head_ang * 2 * math.pi - math.pi) * rad
                hy = cy + math.sin(head_ang * 2 * math.pi - math.pi) * rad
                if math.hypot(x - hx, y - hy) <= size * 0.055:
                    color = white
            idx = (y * size + x) * 3
            pixels[idx : idx + 3] = bytes(color)
    return pixels


def main():
    images = os.path.join(ROOT, "app", "ui", "images")
    os.makedirs(images, exist_ok=True)
    mapping = {
        32: os.path.join(images, "icon-32.png"),
        64: os.path.join(images, "icon-64.png"),
        128: os.path.join(images, "icon-128.png"),
        256: os.path.join(images, "icon-256.png"),
    }
    for size, path in mapping.items():
        write_png(path, size, draw(size))
        print("wrote", path)
    write_png(os.path.join(ROOT, "ICON.PNG"), 64, draw(64))
    write_png(os.path.join(ROOT, "ICON_256.PNG"), 256, draw(256))
    print("icons ready")


if __name__ == "__main__":
    main()
