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
    row = width * 4
    for y in range(height):
        raw += b"\x00" + pixels[y * row : (y + 1) * row]
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
    data += chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    with open(path, "wb") as handle:
        handle.write(data)


def lerp(a, b, t):
    return int(a + (b - a) * t)


def in_triangle(px, py, ax, ay, bx, by, cx, cy):
    def side(x1, y1, x2, y2):
        return (px - x2) * (y1 - y2) - (x1 - x2) * (py - y2)

    d1 = side(ax, ay, bx, by)
    d2 = side(bx, by, cx, cy)
    d3 = side(cx, cy, ax, ay)
    has_neg = d1 < 0 or d2 < 0 or d3 < 0
    has_pos = d1 > 0 or d2 > 0 or d3 > 0
    return not (has_neg and has_pos)


def draw(size):
    scale = 4
    big = size * scale
    tile = bytearray(big * big)
    glyph = bytearray(big * big)
    margin = big * 0.06
    left = margin
    top = margin
    side = big - margin * 2
    radius = side * 0.24
    cx = left + side / 2
    cy = top + side / 2
    half = side / 2 - radius
    ring = side * 0.27
    stroke = max(big * 0.055, 3 * scale)
    start = math.radians(-40)
    sweep = math.radians(292)
    stroke_sweep = sweep - math.radians(16)
    end = start + sweep
    tip_len = stroke * 2.15
    tip_w = stroke * 1.7
    ex = cx + math.cos(end) * ring
    ey = cy + math.sin(end) * ring
    tx, ty = -math.sin(end), math.cos(end)
    nx, ny = math.cos(end), math.sin(end)
    triangle = (
        (ex + tx * tip_len, ey + ty * tip_len),
        (ex + nx * tip_w / 2 - tx * stroke * 0.15, ey + ny * tip_w / 2 - ty * stroke * 0.15),
        (ex - nx * tip_w / 2 - tx * stroke * 0.15, ey - ny * tip_w / 2 - ty * stroke * 0.15),
    )
    for y in range(big):
        py = y + 0.5
        for x in range(big):
            px = x + 0.5
            qx = abs(px - cx) - half
            qy = abs(py - cy) - half
            outside = math.hypot(max(qx, 0), max(qy, 0))
            inside = min(max(qx, qy), 0)
            if outside + inside - radius <= 0:
                tile[y * big + x] = 1
            dx = px - cx
            dy = py - cy
            dist = math.hypot(dx, dy)
            ang = math.atan2(dy, dx)
            delta = (ang - start) % (2 * math.pi)
            if abs(dist - ring) <= stroke / 2 and delta <= stroke_sweep:
                glyph[y * big + x] = 1
            if in_triangle(px, py, triangle[0][0], triangle[0][1], triangle[1][0], triangle[1][1], triangle[2][0], triangle[2][1]):
                glyph[y * big + x] = 1
    pixels = bytearray(size * size * 4)
    samples = scale * scale
    for y in range(size):
        mix = y / max(size - 1, 1)
        base = (lerp(15, 8, mix), lerp(118, 92, mix), lerp(110, 112, mix))
        for x in range(size):
            bg_n = 0
            fg_n = 0
            for sy in range(scale):
                for sx in range(scale):
                    idx = (y * scale + sy) * big + (x * scale + sx)
                    bg_n += tile[idx]
                    fg_n += glyph[idx]
            a_bg = bg_n / samples
            a_fg = fg_n / samples
            alpha = a_fg + a_bg * (1 - a_fg)
            out = (y * size + x) * 4
            if alpha <= 0:
                continue
            red = (248 * a_fg + base[0] * a_bg * (1 - a_fg)) / alpha
            green = (250 * a_fg + base[1] * a_bg * (1 - a_fg)) / alpha
            blue = (252 * a_fg + base[2] * a_bg * (1 - a_fg)) / alpha
            pixels[out] = max(0, min(255, int(round(red))))
            pixels[out + 1] = max(0, min(255, int(round(green))))
            pixels[out + 2] = max(0, min(255, int(round(blue))))
            pixels[out + 3] = max(0, min(255, int(round(alpha * 255))))
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
