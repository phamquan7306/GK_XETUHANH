#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vẽ ảnh nền 2 joystick (asset của app App Inventor): joy_move.png (di chuyển 4 hướng) và joy_turn.png (xoay trái/phải)."""
import math
import sys

from PIL import Image, ImageDraw

S = 4 * 190                      # vẽ to rồi thu nhỏ cho mịn
OUT = 380                        # = 2 x cạnh canvas (190 px) -> nét trên màn hình mật độ cao
BG = (55, 71, 79)                # trùng BackgroundColor của canvas
RING = (120, 144, 156)
DARK = (38, 50, 56)
ARROW = (176, 190, 197)


def tri(d, cx, cy, ang, size, color):
    pts = []
    for a, r in ((ang, size), (ang + 2.5, size * 0.75), (ang - 2.5, size * 0.75)):
        pts.append((cx + r * math.cos(a), cy - r * math.sin(a)))
    d.polygon(pts, fill=color)


def base(kind):
    im = Image.new('RGB', (S, S), BG)
    d = ImageDraw.Draw(im)
    c = S / 2
    R = S / 2 - S * 0.04
    d.ellipse([c - R, c - R, c + R, c + R], fill=DARK, outline=RING, width=int(S * 0.018))
    if kind == 'move':
        r0 = R * 0.62
        d.ellipse([c - r0, c - r0, c + r0, c + r0], outline=(69, 90, 100), width=int(S * 0.008))
        for ang in (90, 270, 0, 180):
            a = math.radians(ang)
            tri(d, c + R * 0.80 * math.cos(a), c - R * 0.80 * math.sin(a), a, S * 0.075, ARROW)
        w = int(S * 0.006)
        d.line([c - R * 0.55, c, c + R * 0.55, c], fill=(69, 90, 100), width=w)
        d.line([c, c - R * 0.55, c, c + R * 0.55], fill=(69, 90, 100), width=w)
    else:
        h = S * 0.11
        d.rounded_rectangle([c - R * 0.78, c - h, c + R * 0.78, c + h], radius=h, fill=(69, 90, 100))
        # mũi tên cong xoay trái (bên trái) / xoay phải (bên phải)
        for side in (-1, 1):
            cx = c + side * R * 0.52
            cy = c - R * 0.48
            rr = R * 0.20
            box = [cx - rr, cy - rr, cx + rr, cy + rr]
            d.arc(box, start=200, end=340, fill=ARROW, width=int(S * 0.02))
            end = math.radians(200 if side < 0 else 340)
            ex, ey = cx + rr * math.cos(end), cy + rr * math.sin(end)
            tri(d, ex, ey + S * 0.01, math.radians(-90), S * 0.05, ARROW)
            tri(d, c + side * R * 0.86, c, math.radians(0 if side > 0 else 180), S * 0.06, ARROW)
    return im.resize((OUT, OUT), Image.LANCZOS)


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else '.'
    base('move').save(f'{out}/joy_move.png', optimize=True)
    base('turn').save(f'{out}/joy_turn.png', optimize=True)
    print('ok')
