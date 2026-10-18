#!/usr/bin/env python3
"""
AEGIS-PRIMORDIAL :: spawn egg icon
==================================
Draws RP/textures/items/aegis_spawn_egg.png (64x64, alpha) and the matching
item_texture.json registration.
"""
import json
import math
import os
import random

from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RP = os.path.join(ROOT, "Aegis_Null_Veil_RP")
SIZE = 64


def egg_mask(size=SIZE):
    """Union of two ellipses -> classic egg silhouette."""
    m = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(m)
    cx = size / 2.0
    # lower body
    d.ellipse([cx - 20, size - 50, cx + 20, size - 4], fill=255)
    # upper, narrower dome
    d.ellipse([cx - 14.5, 6, cx + 14.5, size - 24], fill=255)
    return m.filter(ImageFilter.GaussianBlur(0.6))


def main():
    rng = random.Random(1337)
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    mask = egg_mask()

    # vertical gradient: deep void -> cyan
    grad = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 255))
    px = grad.load()
    for y in range(SIZE):
        t = y / float(SIZE - 1)
        r = int(8 + 6 * t)
        g = int(26 + 150 * (t ** 1.6))
        b = int(38 + 190 * (t ** 1.35))
        for x in range(SIZE):
            px[x, y] = (r, g, b, 255)
    img.paste(grad, (0, 0), mask)

    d = ImageDraw.Draw(img)
    # darker speckles (vanilla egg look) + cyan energy flecks
    for _ in range(90):
        x = rng.randint(6, SIZE - 7)
        y = rng.randint(8, SIZE - 6)
        if mask.getpixel((x, y)) < 180:
            continue
        r = rng.randint(1, 3)
        if rng.random() < 0.72:
            col = (6, 20, 30, 210)
        else:
            col = (170, 250, 255, 220)
        d.ellipse([x - r, y - r, x + r, y + r], fill=col)

    # glowing vertical slit (the sentinel's eye) across the middle
    cx = SIZE // 2
    for i in range(-9, 10):
        w = int(3.2 * math.cos(i / 9.0 * math.pi / 2.0)) + 1
        a = int(215 * (1 - abs(i) / 11.0))
        d.line([(cx - w, cx - 6 + i), (cx + w, cx - 6 + i)], fill=(210, 255, 255, a))

    # rim light + outline
    outline = mask.filter(ImageFilter.FIND_EDGES)
    edge = Image.new("RGBA", (SIZE, SIZE), (7, 16, 24, 235))
    img.paste(edge, (0, 0), outline)

    out_dir = os.path.join(RP, "textures", "items")
    os.makedirs(out_dir, exist_ok=True)
    img.save(os.path.join(out_dir, "aegis_spawn_egg.png"))

    it = {
        "resource_pack_name": "aegis_null_veil",
        "texture_name": "atlas.items",
        "texture_data": {
            "aegis_spawn_egg": {"textures": "textures/items/aegis_spawn_egg"}
        },
    }
    with open(os.path.join(RP, "textures", "item_texture.json"), "w") as fh:
        json.dump(it, fh, indent=1)
    print("wrote spawn egg texture + item_texture.json")


if __name__ == "__main__":
    main()
