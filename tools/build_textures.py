#!/usr/bin/env python3
"""
AEGIS-PRIMORDIAL :: texture painter
===================================
Paints the 1024x1024 base + emissive atlas directly into the UV regions produced
by build_geometry.py, so the artwork can never miss-map (no pink/black entity).

  outputs:
    Aegis_Null_Veil_RP/textures/entity/aegis_primordial.png
    Aegis_Null_Veil_RP/textures/entity/aegis_primordial_emissive.png

Everything is procedural + deterministic (seeded per cube/face), so re-running
the build reproduces byte-identical textures.
"""
import hashlib
import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from model_def import MAT

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RP = os.path.join(ROOT, "Aegis_Null_Veil_RP")
LAYOUT = json.load(open(os.path.join(ROOT, "tools", "uv_layout.json")))
SIZE = LAYOUT["texture_size"]

FACE_SHADE = {"up": 1.16, "north": 1.00, "south": 0.90, "east": 0.87, "west": 0.87, "down": 0.70}
CYAN = (0.11, 0.91, 1.00)
VOID = (0.02, 0.05, 0.09)


# ---------------------------------------------------------------------------
def seed_of(*parts):
    return int(hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)


def value_noise(w, h, freq, rng, octaves=3):
    """Cheap tileable-ish smooth noise in [0,1]."""
    acc = np.zeros((h, w), dtype=np.float32)
    amp, total = 1.0, 0.0
    for o in range(octaves):
        gw = max(2, int(w * freq * (2 ** o)) + 2)
        gh = max(2, int(h * freq * (2 ** o)) + 2)
        grid = rng.random((gh, gw)).astype(np.float32)
        im = Image.fromarray(grid, mode="F")
        im = im.resize((w, h), Image.BICUBIC)
        acc += np.asarray(im, dtype=np.float32) / 255.0 * amp
        total += amp
        amp *= 0.5
    return acc / total


def streaks(w, h, rng, count=26):
    """Brushed-metal style horizontal scratches."""
    img = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(img)
    for _ in range(count):
        y = int(rng.random() * h)
        x0 = int(rng.random() * w)
        ln = int((0.25 + rng.random() * 0.75) * w)
        v = 0.35 + rng.random() * 0.65
        d.line([(x0, y), (x0 + ln, y + int((rng.random() - 0.5) * 2))],
               fill=int(v * 255), width=1)
    img = img.filter(ImageFilter.GaussianBlur(0.4))
    return np.asarray(img, dtype=np.float32) / 255.0


# ---------------------------------------------------------------------------
def paint_grain(w, h, mat_name, rng):
    """Returns a float32 multiplier field around 1.0 plus an additive field."""
    m = MAT[mat_name]
    grain, freq, amp = m["grain"], m["freq"], m["noise"]
    n = value_noise(w, h, freq, rng, octaves=3) - 0.5

    if grain == "fabric":
        # fine weave: two directional combs
        xs = np.arange(w)[None, :]
        ys = np.arange(h)[:, None]
        weave = (np.sin(xs * 1.9) * 0.5 + np.sin(ys * 1.7) * 0.5) * 0.035
        field = 1.0 + n * amp * 2.0 + weave
    elif grain == "metal":
        field = 1.0 + n * amp * 1.6 + streaks(w, h, rng) * 0.06
    elif grain == "leather":
        cell = value_noise(w, h, freq * 2.2, rng, octaves=2) - 0.5
        field = 1.0 + n * amp * 1.4 + cell * 0.05
    elif grain == "skin":
        field = 1.0 + n * amp * 1.2
    else:
        field = 1.0 + n * amp
    return field


def folds(w, h, mat_name, rng):
    """Large scale drape/fold shading for cloth."""
    m = MAT[mat_name]
    if m["fold"] <= 0:
        return np.ones((h, w), dtype=np.float32)
    xs = np.arange(w, dtype=np.float32)[None, :] / max(w, 1)
    ys = np.arange(h, dtype=np.float32)[:, None] / max(h, 1)
    f = m["fold"]
    ph = rng.random() * 6.28
    v = (np.sin(xs * 9.0 * f + ph) * 0.55 + np.sin(xs * 21.0 * f + ph * 1.7) * 0.25
         + np.sin(ys * 4.0 * f + ph * 0.5) * 0.30)
    return 1.0 + v * 0.11


def bevel(w, h, strength=0.30, px=2):
    """Panel bevel: light on top/left, dark on bottom/right (metal plating)."""
    out = np.ones((h, w), dtype=np.float32)
    if h <= px * 2 or w <= px * 2:
        return out
    ramp = np.linspace(0, 1, px, dtype=np.float32)
    out[:px, :] *= (1.0 + strength * ramp[::-1])[:, None]
    out[-px:, :] *= (1.0 - strength * ramp)[:, None]
    out[:, :px] *= (1.0 + strength * 0.6 * ramp[::-1])[None, :]
    out[:, -px:] *= (1.0 - strength * 0.6 * ramp)[None, :]
    out[:1, :] *= 1.06
    out[:, :1] *= 1.03
    return out


def vignette(w, h, amount=0.22):
    ys = np.linspace(-1, 1, h, dtype=np.float32)[:, None]
    xs = np.linspace(-1, 1, w, dtype=np.float32)[None, :]
    r = np.sqrt(xs * xs * 0.55 + ys * ys * 0.85)
    return 1.0 - np.clip(r - 0.55, 0, None) * amount


# ---------------------------------------------------------------------------
def draw_veins(img, w, h, rng, amount, color, width_range=(1, 3), count=5, emissive=False):
    """Branching cyan energy veins."""
    d = ImageDraw.Draw(img)
    n = max(1, int(count * amount))
    for _ in range(n):
        if rng.random() < 0.5:
            x, y = int(rng.random() * w), 0 if rng.random() < 0.5 else h - 1
            diry = 1 if y == 0 else -1
        else:
            x, y = 0 if rng.random() < 0.5 else w - 1, int(rng.random() * h)
            diry = 0
        pts = [(x, y)]
        ang = (rng.random() * 1.2 - 0.6) + (1.57 if diry else 0)
        if diry == 0:
            ang = rng.random() * 1.0 - 0.5
        steps = int(6 + rng.random() * 14)
        for _ in range(steps):
            ang += (rng.random() - 0.5) * 0.9
            step = (2 + rng.random() * 7) * (1.0 if not emissive else 1.0)
            x = x + math.cos(ang) * step
            y = y + math.sin(ang) * step * (diry if diry else 1)
            if not (0 <= x < w and 0 <= y < h):
                break
            pts.append((x, y))
        if len(pts) > 2:
            lw = width_range[0] + rng.random() * (width_range[1] - width_range[0])
            a = int(255 * (0.35 + 0.55 * amount) * (1.0 if emissive else 0.55))
            d.line(pts, fill=(int(color[0] * 255), int(color[1] * 255), int(color[2] * 255), a),
                   width=max(1, int(lw)), joint="curve")
            if rng.random() < 0.55:  # branch
                bp = pts[len(pts) // 2]
                sub = [bp]
                bx, by = bp
                ang2 = ang + (1.0 if rng.random() < 0.5 else -1.0)
                for _ in range(int(3 + rng.random() * 6)):
                    ang2 += (rng.random() - 0.5) * 0.7
                    bx += math.cos(ang2) * 4
                    by += math.sin(ang2) * 4
                    if not (0 <= bx < w and 0 <= by < h):
                        break
                    sub.append((bx, by))
                if len(sub) > 1:
                    d.line(sub, fill=(int(color[0] * 255), int(color[1] * 255),
                                      int(color[2] * 255), int(a * 0.7)), width=1)


def radial(img, w, h, inner, outer, power=2.0):
    """Radial gradient RGBA painted onto `img` (PIL RGBA)."""
    ys = np.linspace(-1, 1, h, dtype=np.float32)[:, None]
    xs = np.linspace(-1, 1, w, dtype=np.float32)[None, :]
    r = np.sqrt(xs * xs + ys * ys)
    t = np.clip(1.0 - r, 0, 1) ** power
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    for i in range(3):
        arr[..., i] = (inner[i] + (outer[i] - inner[i]) * (1 - t)) * 255
    arr[..., 3] = 255
    g = Image.fromarray(arr, "RGBA")
    img.alpha_composite(g)


def linear_v(img, w, h, top, bottom):
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    t = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    for i in range(3):
        arr[..., i, :] = (top[i] + (bottom[i] - top[i]) * t) * 255
    arr[..., 3] = 255
    img.alpha_composite(Image.fromarray(arr, "RGBA"))


# ---------------------------------------------------------------------------
def paint_face(entry, emissive=False):
    w, h = entry["rect"][2], entry["rect"][3]
    mat = entry["mat"]
    face = entry["face"]
    tag = entry["tag"]
    rng = np.random.default_rng(seed_of(tag, face, mat))
    pyrng = __import__("random").Random(seed_of(tag, face, "v"))

    base_col = np.array(MAT[mat]["base"], dtype=np.float32)

    # emissive map is black except for explicit glow
    if emissive:
        img = Image.new("RGBA", (w, h), (0, 0, 0, 255))
        if entry["glow"] <= 0 and entry["veins"] <= 0:
            return img
        if entry["veins"] > 0:
            draw_veins(img, w, h, pyrng, entry["veins"], CYAN,
                       width_range=(1, 3), count=6, emissive=True)
        if entry["glow"] > 0:
            g = Image.new("RGBA", (w, h), (0, 0, 0, 255))
            radial(g, w, h, (1.0, 1.0, 1.0), (0.05, 0.62, 0.78), power=1.7)
            draw_veins(g, w, h, pyrng, max(0.4, entry["veins"]), CYAN,
                       width_range=(1, 2), count=3, emissive=True)
            img = Image.blend(img, g, float(entry["glow"]))
        return img

    # ---------------- base colour pass ----------------
    field = paint_grain(w, h, mat, rng)
    field *= folds(w, h, mat, rng)
    field *= FACE_SHADE[face]
    if MAT[mat]["grain"] == "metal":
        field *= bevel(w, h)
    field *= vignette(w, h, 0.13)

    col = np.clip(base_col[None, None, :] * field[..., None], 0, 255).astype(np.uint8)
    img = Image.fromarray(col, "RGB").convert("RGBA")

    # seams / rivets for armour plating
    if MAT[mat]["grain"] == "metal" and w > 14 and h > 14:
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, w - 1, h - 1], outline=(12, 14, 18, 220), width=1)
        d.line([(1, 1), (w - 2, 1)], fill=(150, 162, 178, 90), width=1)
        for _ in range(2):
            rx = int(pyrng.uniform(4, max(5, w - 4)))
            ry = int(pyrng.uniform(4, max(5, h - 4)))
            rr = max(1, int(min(w, h) * 0.03))
            d.ellipse([rx - rr, ry - rr, rx + rr, ry + rr], fill=(96, 106, 120, 190))
            d.ellipse([rx - rr, ry - rr, rx + rr, ry - rr + 1], fill=(170, 182, 198, 140))

    # cloth stitching
    if MAT[mat]["grain"] == "fabric" and min(w, h) > 12:
        d = ImageDraw.Draw(img)
        inset = max(2, int(min(w, h) * 0.05))
        d.rectangle([inset, inset, w - 1 - inset, h - 1 - inset],
                    outline=(44, 54, 66, 120), width=1)
        yy = int(h * 0.5)
        d.line([(inset, yy), (w - 1 - inset, yy)], fill=(38, 48, 60, 110), width=1)

    # cyan energy veining
    if entry["veins"] > 0:
        draw_veins(img, w, h, pyrng, entry["veins"], CYAN, count=6)

    # ---- bespoke pieces -------------------------------------------------
    d = ImageDraw.Draw(img)

    if tag in ("eye_bar",) and face == "north":
        d.rectangle([0, 0, w - 1, h - 1], fill=(6, 10, 14, 255))
        band_h = max(2, int(h * 0.46))
        by0 = (h - band_h) // 2
        sub = Image.new("RGBA", (w, band_h), (0, 0, 0, 255))
        radial(sub, w, band_h, (0.85, 1.0, 1.0), (0.02, 0.55, 0.85), power=1.1)
        img.alpha_composite(sub, (0, by0))
        for cx in (0.30, 0.70):
            ex = int(w * cx)
            rr = max(2, int(h * 0.42))
            d.ellipse([ex - rr, by0 + band_h // 2 - rr, ex + rr, by0 + band_h // 2 + rr],
                      fill=(235, 255, 255, 235))
    elif tag in ("eye_bar",) and face != "north":
        d.rectangle([0, 0, w - 1, h - 1], fill=(5, 8, 12, 255))

    if tag.startswith("core_gem") or tag.startswith("ring_"):
        radial(img, w, h, (0.9, 1.0, 1.0), (0.04, 0.45, 0.62), power=1.5)
        d.ellipse([w * 0.22, h * 0.22, w * 0.78, h * 0.78],
                  outline=(190, 250, 255, 200), width=max(1, int(min(w, h) * 0.06)))

    if tag.startswith("palm_glow"):
        if face == "north":
            radial(img, w, h, (0.8, 1.0, 1.0), (0.03, 0.5, 0.7), power=1.6)
        else:
            d.rectangle([0, 0, w - 1, h - 1], fill=(12, 18, 24, 255))

    if tag in ("skull",) and face == "north":
        # hood shadow over the upper face, jaw + cheek definition
        sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        sd = ImageDraw.Draw(sh)
        sd.rectangle([0, 0, w - 1, int(h * 0.34)], fill=(4, 8, 14, 190))
        sd.rectangle([0, int(h * 0.34), w - 1, int(h * 0.46)], fill=(8, 12, 18, 90))
        img.alpha_composite(sh)
        d.line([(int(w * 0.36), int(h * 0.30)), (int(w * 0.36), int(h * 0.58))],
               fill=(96, 88, 82, 120), width=max(1, int(w * 0.03)))
        d.line([(int(w * 0.64), int(h * 0.30)), (int(w * 0.64), int(h * 0.58))],
               fill=(96, 88, 82, 120), width=max(1, int(w * 0.03)))
        d.line([(int(w * 0.42), int(h * 0.74)), (int(w * 0.58), int(h * 0.74))],
               fill=(72, 62, 58, 150), width=max(1, int(h * 0.03)))
        d.line([(int(w * 0.30), int(h * 0.66)), (int(w * 0.70), int(h * 0.66))],
               fill=(120, 112, 104, 60), width=max(1, int(h * 0.02)))

    if tag in ("jaw_guard",) and face == "north":
        d.rectangle([0, int(h * 0.18), w - 1, int(h * 0.26)], fill=(150, 168, 186, 120))

    if tag in ("buckle",) and face == "north":
        d.rectangle([int(w * 0.2), int(h * 0.2), int(w * 0.8), int(h * 0.8)],
                    outline=(170, 190, 210, 200), width=max(1, int(min(w, h) * 0.12)))
        radial(img, int(w * 0.6), int(h * 0.6), (0.5, 0.95, 1.0), (0.02, 0.3, 0.4), power=1.4)

    if tag in ("cloak_u", "cloak_l", "cloak_hem", "veil_r", "veil_base", "veil_back"):
        # void gradient: the lower part of hanging cloth fades into the veil
        sub = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        t = np.linspace(0, 1, h, dtype=np.float32)[:, None]
        arr = np.zeros((h, w, 4), dtype=np.uint8)
        arr[..., 0] = (VOID[0] * 255)
        arr[..., 1] = (VOID[1] * 255)
        arr[..., 2] = (VOID[2] * 255)
        arr[..., 3] = (np.clip((t - 0.15) / 0.85, 0, 1) ** 1.6 * 235).astype(np.uint8)
        sub = Image.fromarray(arr, "RGBA")
        img.alpha_composite(sub)

    return img


# ---------------------------------------------------------------------------
def main():
    base = Image.new("RGBA", (SIZE, SIZE), (16, 20, 26, 255))
    emis = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 255))

    for entry in LAYOUT["faces"]:
        x, y, w, h = entry["rect"]
        pad = entry["pad"]
        bimg = paint_face(entry, emissive=False)
        eimg = paint_face(entry, emissive=True)
        # bleed guard: fill the padded gutter with the region's own edge colour
        for target, src in ((base, bimg), (emis, eimg)):
            bg = Image.new("RGBA", (w + pad * 2, h + pad * 2),
                           src.getpixel((w // 2, h // 2)))
            bg.alpha_composite(src, (pad, pad))
            target.alpha_composite(bg, (x - pad, y - pad))

    outdir = os.path.join(RP, "textures", "entity")
    os.makedirs(outdir, exist_ok=True)
    p1 = os.path.join(outdir, "aegis_primordial.png")
    p2 = os.path.join(outdir, "aegis_primordial_emissive.png")
    base.convert("RGBA").save(p1)
    emis.convert("RGBA").save(p2)

    # dithered/mipped-safe downscaled preview for review
    base.resize((512, 512), Image.LANCZOS).save(
        os.path.join(ROOT, "assets", "preview_base.png"))
    emis.resize((512, 512), Image.LANCZOS).save(
        os.path.join(ROOT, "assets", "preview_emissive.png"))
    print("wrote", p1, os.path.getsize(p1) // 1024, "KB")
    print("wrote", p2, os.path.getsize(p2) // 1024, "KB")


if __name__ == "__main__":
    main()
