#!/usr/bin/env python3
"""
Aegis Primordial — geometry + texture builder.

Generates:
  RP/models/entity/aegis_primordial.geo.json          (Blockbench-compatible, per-face UV)
  RP/textures/entity/aegis_primordial.png             (diffuse + emissive-alpha, guard)
  RP/textures/entity/aegis_primordial_overdrive.png   (brighter veins variant)
  RP/textures/items/aegis_core.png, pack icons

Units: 1 unit = 1/16 block. Model is 32 units (2.0 blocks) tall.
Texture: 4 texels per unit -> 4x the fidelity of vanilla box-UV skins.
"""
import json, math, os, random
from PIL import Image, ImageDraw, ImageFilter

random.seed(7)
ROOT = os.path.join(os.path.dirname(__file__), "..")
RP = os.path.join(ROOT, "Aegis_Primordial_RP")
TEX_SIZE = 256
S = 4  # texels per unit

# ----------------------------------------------------------------------------
# Rig definition
# ----------------------------------------------------------------------------
bones = []  # list of dict(name, parent, pivot, cubes=[(origin,size,inflate,material,mirror)])


def bone(name, parent, pivot, cubes=(), **extra):
    b = {"name": name, "parent": parent, "pivot": list(pivot), "cubes": [], **extra}
    for c in cubes:
        origin, size, material = c[0], c[1], c[2]
        inflate = c[3] if len(c) > 3 else 0.0
        b["cubes"].append({"origin": list(origin), "size": list(size), "inflate": inflate, "material": material})
    bones.append(b)
    return b


# Materials: coat, plate, plate_dark, glow, glow_core, skin_visor, hood, glove, boot, belt, vein_strip
bone("root", None, (0, 0, 0))
bone("waist", "root", (0, 12, 0), [((-4.5, 11, -2.5), (9, 2, 5), "belt")])
bone("torso", "waist", (0, 12, 0), [
    ((-5, 13, -3), (10, 12, 6), "coat"),            # torso under coat
    ((-4, 18.5, -3.6), (8, 6, 1), "plate"),          # breastplate
    ((-4.2, 13.2, 3.0), (8.4, 11, 0.6), "plate_dark"),  # back plate
])
bone("chest_core", "torso", (0, 21, -3.6), [((-1.5, 19.5, -4.2), (3, 3, 1), "glow_core", 0.1)])
bone("collar", "torso", (0, 24, 0), [((-4.5, 24, -3.5), (9, 2, 7), "plate_dark", 0.2)])
bone("coat_back", "waist", (0, 12, 2.5), [((-5.2, 0.5, 2.6), (10.4, 12.5, 0.8), "coat"), ((-5.6, 0.5, 3.2), (11.2, 6, 0.6), "coat")])
bone("coat_front_l", "waist", (0.5, 12, -2.5), [((0.6, 2, -3.4), (4.4, 10.5, 0.8), "coat")])
bone("coat_front_r", "waist", (-0.5, 12, -2.5), [((-5, 2, -3.4), (4.4, 10.5, 0.8), "coat")])
bone("coat_side_l", "waist", (5, 12, 0), [((5.0, 2, -2.4), (0.8, 10.5, 4.8), "coat")])
bone("coat_side_r", "waist", (-5, 12, 0), [((-5.8, 2, -2.4), (0.8, 10.5, 4.8), "coat")])

bone("head", "collar", (0, 26, 0), [((-4, 26, -4), (8, 8, 8), "skin_visor")])
bone("hood", "head", (0, 26, 0), [
    ((-4.6, 33.6, -4.6), (9.2, 1.2, 9.2), "hood"),  # top
    ((-4.6, 25.6, 3.8), (9.2, 9.2, 1.0), "hood"),   # back
    ((3.8, 27.0, -4.6), (1.0, 7.8, 9.2), "hood"),   # right side
    ((-4.8, 27.0, -4.6), (1.0, 7.8, 9.2), "hood"),  # left side
    ((-4.6, 33.0, -5.6), (9.2, 1.6, 1.4), "hood"),  # brow lip
    ((-5.0, 23.5, -1.5), (10.0, 2.6, 6.0), "hood"),  # cowl draped on shoulders
])
bone("eye_l", "head", (1.8, 30.5, -4.0), [((0.9, 30.2, -4.35), (2.0, 0.7, 0.4), "glow")])
bone("eye_r", "head", (-1.8, 30.5, -4.0), [((-2.9, 30.2, -4.35), (2.0, 0.7, 0.4), "glow")])

# Right arm (character's right = model -x)
bone("arm_r", "torso", (-5.5, 23, 0), [((-8.5, 15, -2), (3.5, 9, 4), "coat")])
bone("pauldron_r", "arm_r", (-6, 24, 0), [((-9.4, 21, -2.6), (4.8, 4, 5.2), "plate", 0.2)])
bone("vein_r", "arm_r", (-7, 19, 0), [((-8.9, 16, -0.5), (0.6, 7, 1), "vein_strip")])
bone("forearm_r", "arm_r", (-6.8, 15.5, 0), [((-8.5, 8, -2), (3.5, 7.5, 4), "plate_dark"), ((-8.7, 11, -2.2), (3.9, 3, 4.4), "plate", 0.0)])
bone("hand_r", "forearm_r", (-6.8, 8, 0), [((-8.5, 4.5, -2), (3.5, 3.5, 4), "glove")])
bone("palm_glow_r", "hand_r", (-6.8, 6, -2), [((-7.7, 5.3, -2.3), (1.8, 1.8, 0.4), "glow")])

# Left arm
bone("arm_l", "torso", (5.5, 23, 0), [((5, 15, -2), (3.5, 9, 4), "coat")])
bone("pauldron_l", "arm_l", (6, 24, 0), [((4.6, 21, -2.6), (4.8, 4, 5.2), "plate", 0.2)])
bone("vein_l", "arm_l", (7, 19, 0), [((8.3, 16, -0.5), (0.6, 7, 1), "vein_strip")])
bone("forearm_l", "arm_l", (6.8, 15.5, 0), [((5, 8, -2), (3.5, 7.5, 4), "plate_dark"), ((4.8, 11, -2.2), (3.9, 3, 4.4), "plate", 0.0)])
bone("hand_l", "forearm_l", (6.8, 8, 0), [((5, 4.5, -2), (3.5, 3.5, 4), "glove")])
bone("palm_glow_l", "hand_l", (6.8, 6, -2), [((5.9, 5.3, -2.3), (1.8, 1.8, 0.4), "glow")])

# Legs
bone("leg_r", "waist", (-2.2, 12, 0), [((-4.2, 6, -2), (4, 6, 4), "coat")])
bone("lowerleg_r", "leg_r", (-2.2, 6, 0), [((-4.2, 0, -2), (4, 6, 4), "plate_dark")])
bone("boot_r", "lowerleg_r", (-2.2, 0, 0), [((-4.4, 0, -2.6), (4.4, 2.6, 4.8), "boot")])
bone("knee_r", "lowerleg_r", (-2.2, 6, -2), [((-3.9, 4.8, -2.4), (3.4, 2.4, 0.6), "plate")])

bone("leg_l", "waist", (2.2, 12, 0), [((0.2, 6, -2), (4, 6, 4), "coat")])
bone("lowerleg_l", "leg_l", (2.2, 6, 0), [((0.2, 0, -2), (4, 6, 4), "plate_dark")])
bone("boot_l", "lowerleg_l", (2.2, 0, 0), [((0.0, 0, -2.6), (4.4, 2.6, 4.8), "boot")])
bone("knee_l", "lowerleg_l", (2.2, 6, -2), [((0.5, 4.8, -2.4), (3.4, 2.4, 0.6), "plate")])

# Energy wings (hidden in guard mode via v.wings scale, unfold in overdrive / null sever)
bone("wing_l", "torso", (1.5, 22.5, 3.2))
bone("wing_r", "torso", (-1.5, 22.5, 3.2))
for side, sx, parent in (("l", 1, "wing_l"), ("r", -1, "wing_r")):
    for i, (ang, length, thick) in enumerate(((18, 11, 0.9), (42, 13, 0.8), (68, 10, 0.7))):
        ox = 1.5 if sx > 0 else -1.5 - length
        bone(f"wing_{side}_{i}", parent, (1.5 * sx, 22.5, 3.2), [((ox, 22.1, 3.0), (length, thick, 0.4), "glow")],
             rotation=[0, 0, -ang * sx])

# Particle / locator attachment points
LOCATORS = {
    "head": {"eyes": [0, 30.5, -4.5]},
    "chest_core": {"core": [0, 21, -4.5]},
    "hand_r": {"hand_r": [-6.8, 4.5, 0]},
    "hand_l": {"hand_l": [6.8, 4.5, 0]},
    "root": {"feet": [0, 0, 0]},
}

# ----------------------------------------------------------------------------
# UV packing (per-face, shelf packer)
# ----------------------------------------------------------------------------
FACES = ["north", "south", "east", "west", "up", "down"]


def face_dims(size):
    w, h, d = size
    return {
        "north": (w, h), "south": (w, h),
        "east": (d, h), "west": (d, h),
        "up": (w, d), "down": (w, d),
    }


class Packer:
    def __init__(self, size):
        self.size = size
        self.x = 0
        self.y = 0
        self.rowh = 0

    def alloc(self, w, h):
        w, h = int(math.ceil(w)), int(math.ceil(h))
        if self.x + w > self.size:
            self.x = 0
            self.y += self.rowh + 1
            self.rowh = 0
        if self.y + h > self.size:
            raise RuntimeError("texture too small")
        r = (self.x, self.y, w, h)
        self.x += w + 1
        self.rowh = max(self.rowh, h)
        return r


def build():
    global TEX_SIZE
    # Sort cubes by face height to reduce shelf waste
    all_cubes = []
    for b in bones:
        for c in b["cubes"]:
            all_cubes.append((b["name"], c))
    all_cubes.sort(key=lambda bc: -max(bc[1]["size"][1], bc[1]["size"][2]))

    for attempt in (256, 512):
        TEX_SIZE = attempt
        packer = Packer(TEX_SIZE)
        try:
            for bname, c in all_cubes:
                dims = face_dims(c["size"])
                c["uv"] = {}
                for f in FACES:
                    fw, fh = dims[f]
                    px_w, px_h = max(1, fw * S), max(1, fh * S)
                    x, y, w, h = packer.alloc(px_w, px_h)
                    c["uv"][f] = {"uv": [x, y], "uv_size": [w, h]}
            break
        except RuntimeError:
            continue

    # Build geometry json
    geo_bones = []
    for b in bones:
        gb = {"name": b["name"], "pivot": b["pivot"]}
        if "rotation" in b:
            gb["rotation"] = b["rotation"]
        if b["parent"]:
            gb["parent"] = b["parent"]
        if b["cubes"]:
            gb["cubes"] = []
            for c in b["cubes"]:
                gc = {"origin": c["origin"], "size": c["size"], "uv": c["uv"]}
                if c["inflate"]:
                    gc["inflate"] = c["inflate"]
                gb["cubes"].append(gc)
        if b["name"] in LOCATORS:
            gb["locators"] = LOCATORS[b["name"]]
        geo_bones.append(gb)

    geo = {
        "format_version": "1.16.0",
        "minecraft:geometry": [{
            "description": {
                "identifier": "geometry.aegis_primordial",
                "texture_width": TEX_SIZE,
                "texture_height": TEX_SIZE,
                "visible_bounds_width": 3,
                "visible_bounds_height": 3,
                "visible_bounds_offset": [0, 1.0, 0],
            },
            "bones": geo_bones,
        }],
    }
    os.makedirs(os.path.join(RP, "models/entity"), exist_ok=True)
    with open(os.path.join(RP, "models/entity/aegis_primordial.geo.json"), "w") as f:
        json.dump(geo, f, indent=1)

    paint_texture(all_cubes, "aegis_primordial.png", overdrive=False)
    paint_texture(all_cubes, "aegis_primordial_overdrive.png", overdrive=True)
    print(f"geometry: {len(bones)} bones, {len(all_cubes)} cubes, atlas {TEX_SIZE}px")


# ----------------------------------------------------------------------------
# Texture painting
# ----------------------------------------------------------------------------
CYAN = (62, 236, 255)
CYAN_DEEP = (20, 140, 190)
WHITE_HOT = (220, 255, 255)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def noise_fill(img, rect, base, var=8, grain=1.0):
    x0, y0, w, h = rect
    px = img.load()
    for y in range(y0, y0 + h):
        for x in range(x0, x0 + w):
            n = random.randint(-var, var)
            # subtle vertical weave for fabric
            weave = int(2 * math.sin(x * 1.7) * grain)
            px[x, y] = tuple(max(0, min(255, base[i] + n + weave)) for i in range(3)) + (255,)


def bevel(img, rect, light=(70, 78, 92), dark=(8, 9, 12), width=1):
    d = ImageDraw.Draw(img)
    x0, y0, w, h = rect
    for i in range(width):
        d.line([(x0 + i, y0 + i), (x0 + w - 1 - i, y0 + i)], fill=light + (255,))
        d.line([(x0 + i, y0 + i), (x0 + i, y0 + h - 1 - i)], fill=light + (255,))
        d.line([(x0 + i, y0 + h - 1 - i), (x0 + w - 1 - i, y0 + h - 1 - i)], fill=dark + (255,))
        d.line([(x0 + w - 1 - i, y0 + i), (x0 + w - 1 - i, y0 + h - 1 - i)], fill=dark + (255,))


def glow_px(img, x, y, intensity, hot=False):
    """Draw an emissive texel. Alpha encodes emissive strength for entity_emissive_alpha."""
    col = lerp(CYAN_DEEP, WHITE_HOT if hot else CYAN, min(1.0, intensity))
    a = int(255 - 235 * min(1.0, intensity))
    img.putpixel((x, y), col + (a,))


def glow_line(img, pts, intensity, width=1):
    """Polyline of emissive texels with soft falloff."""
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        n = int(max(abs(x2 - x1), abs(y2 - y1))) + 1
        for i in range(n + 1):
            t = i / max(1, n)
            x, y = int(round(x1 + (x2 - x1) * t)), int(round(y1 + (y2 - y1) * t))
            for dx in range(-width + 1, width):
                for dy in range(-width + 1, width):
                    xx, yy = x + dx, y + dy
                    if 0 <= xx < img.width and 0 <= yy < img.height:
                        falloff = 1.0 if (dx == 0 and dy == 0) else 0.45
                        glow_px(img, xx, yy, intensity * falloff, hot=(falloff == 1.0 and intensity > 0.9))


def vein_pattern(img, rect, intensity, density=1.0, seed=0):
    """Branching null-energy veins inside rect."""
    rnd = random.Random(seed)
    x0, y0, w, h = rect
    if w < 4 or h < 4:
        return
    branches = max(1, int((w * h) / 90 * density))
    for _ in range(branches):
        x, y = rnd.randint(x0 + 1, x0 + w - 2), rnd.randint(y0 + 1, y0 + h - 2)
        pts = [(x, y)]
        for _ in range(rnd.randint(2, 5)):
            x = max(x0 + 1, min(x0 + w - 2, x + rnd.choice([-3, -2, -1, 0, 1, 2, 3])))
            y = max(y0 + 1, min(y0 + h - 2, y + rnd.randint(2, 6)))
            pts.append((x, y))
        glow_line(img, pts, intensity * rnd.uniform(0.6, 1.0))


def paint_face(img, rect, material, face, cube_size, overdrive, seed):
    x0, y0, w, h = rect
    d = ImageDraw.Draw(img)
    g = 1.0 if overdrive else 0.72  # glow intensity multiplier
    rnd = random.Random(seed)

    if material == "coat":
        noise_fill(img, rect, (18, 20, 27), var=5, grain=1.2)
        # seams
        d.line([(x0 + 1, y0), (x0 + 1, y0 + h - 1)], fill=(10, 11, 15, 255))
        d.line([(x0 + w - 2, y0), (x0 + w - 2, y0 + h - 1)], fill=(10, 11, 15, 255))
        # hem highlight
        d.line([(x0, y0 + h - 1), (x0 + w - 1, y0 + h - 1)], fill=(34, 38, 48, 255))
        if face in ("north", "south") and h >= 20:
            # luminous trim along coat edges
            glow_line(img, [(x0 + 2, y0 + 2), (x0 + 2, y0 + h - 3)], 0.55 * g)
            glow_line(img, [(x0 + w - 3, y0 + 2), (x0 + w - 3, y0 + h - 3)], 0.55 * g)
            vein_pattern(img, (x0 + 3, y0 + 3, w - 6, h - 6), 0.5 * g, density=0.6 if not overdrive else 1.2, seed=seed)
        elif face in ("east", "west") and h >= 20:
            vein_pattern(img, rect, 0.4 * g, density=0.5, seed=seed + 1)

    elif material in ("plate", "plate_dark"):
        base = (44, 49, 60) if material == "plate" else (30, 33, 41)
        noise_fill(img, rect, base, var=4, grain=0)
        bevel(img, rect, light=lerp(base, (120, 130, 150), 0.5), dark=(8, 9, 12))
        # panel groove
        if w >= 8 and h >= 8:
            d.rectangle([x0 + 3, y0 + 3, x0 + w - 4, y0 + h - 4], outline=lerp(base, (0, 0, 0), 0.5) + (255,))
            # rivets
            for rx, ry in ((x0 + 2, y0 + 2), (x0 + w - 3, y0 + 2), (x0 + 2, y0 + h - 3), (x0 + w - 3, y0 + h - 3)):
                img.putpixel((rx, ry), (150, 160, 180, 255))
        if face in ("north", "up") and w >= 10 and h >= 6:
            # energy groove
            cy = y0 + h // 2
            glow_line(img, [(x0 + 3, cy), (x0 + w - 4, cy)], 0.8 * g)
            if material == "plate" and h >= 12:
                glow_line(img, [(x0 + w // 2, y0 + 3), (x0 + w // 2, y0 + h - 4)], 0.7 * g)
        if overdrive and w >= 8:
            vein_pattern(img, rect, 0.6, density=0.8, seed=seed + 7)

    elif material == "belt":
        noise_fill(img, rect, (26, 24, 28), var=4, grain=0)
        bevel(img, rect, light=(60, 56, 64), dark=(6, 6, 8))
        if face == "north":
            # buckle with core light
            cx, cy = x0 + w // 2, y0 + h // 2
            d.rectangle([cx - 3, cy - 2, cx + 3, cy + 2], fill=(70, 76, 90, 255), outline=(120, 130, 150, 255))
            glow_px(img, cx, cy, 0.9 * g, hot=True)

    elif material == "hood":
        noise_fill(img, rect, (13, 14, 19), var=4, grain=1.5)
        d.line([(x0, y0 + h - 1), (x0 + w - 1, y0 + h - 1)], fill=(28, 30, 40, 255))
        if face in ("north", "up") and w >= 20:
            glow_line(img, [(x0 + 2, y0 + h // 2), (x0 + w - 3, y0 + h // 2)], 0.5 * g)

    elif material == "skin_visor":
        if face == "north":
            # Lower face: skin with jaw shadow; upper: visor glass
            skin = (214, 178, 150)
            noise_fill(img, rect, skin, var=4, grain=0)
            visor_h = int(h * 0.58)
            noise_fill(img, (x0, y0, w, visor_h), (12, 16, 22), var=3, grain=0)
            d.line([(x0, y0 + visor_h), (x0 + w - 1, y0 + visor_h)], fill=(90, 100, 120, 255))
            # eye slits
            ey = y0 + int(h * 0.42)
            for ex in (x0 + int(w * 0.18), x0 + int(w * 0.58)):
                glow_line(img, [(ex, ey), (ex + int(w * 0.24), ey)], 1.0 * g, width=1)
                glow_line(img, [(ex, ey + 1), (ex + int(w * 0.24), ey + 1)], 0.5 * g)
            # visor sheen
            for i in range(0, w, 6):
                img.putpixel((x0 + i, y0 + 2), (60, 80, 100, 255))
            # nose shadow, cheek shading, mouth + chin shadow
            nx = x0 + w // 2
            d.line([(nx, y0 + visor_h + 1), (nx, y0 + visor_h + int(h * 0.12))], fill=lerp(skin, (0, 0, 0), 0.25) + (255,))
            d.line([(nx + 1, y0 + visor_h + int(h * 0.10)), (nx + 2, y0 + visor_h + int(h * 0.12))], fill=lerp(skin, (0, 0, 0), 0.35) + (255,))
            for cx_ in (x0 + 2, x0 + w - 3):
                for yy in range(y0 + visor_h + 1, y0 + h - 2):
                    img.putpixel((cx_, yy), lerp(skin, (0, 0, 0), 0.18) + (255,))
            my = y0 + int(h * 0.82)
            d.line([(x0 + int(w * 0.36), my), (x0 + int(w * 0.64), my)], fill=(140, 90, 85, 255))
            d.line([(x0 + int(w * 0.38), my + 1), (x0 + int(w * 0.62), my + 1)], fill=lerp(skin, (255, 255, 255), 0.15) + (255,))
            d.line([(x0, y0 + h - 1), (x0 + w - 1, y0 + h - 1)], fill=lerp(skin, (0, 0, 0), 0.4) + (255,))
            d.line([(x0, y0 + visor_h + 1), (x0, y0 + h - 1)], fill=lerp(skin, (0, 0, 0), 0.3) + (255,))
            d.line([(x0 + w - 1, y0 + visor_h + 1), (x0 + w - 1, y0 + h - 1)], fill=lerp(skin, (0, 0, 0), 0.3) + (255,))
        elif face == "down":
            noise_fill(img, rect, (190, 155, 130), var=3, grain=0)
        else:
            # under-hood: dark cowl fabric with faint cyan rim
            noise_fill(img, rect, (16, 17, 23), var=3, grain=1.0)
            if face in ("east", "west"):
                glow_line(img, [(x0 + 1, y0 + int(h * 0.42)), (x0 + 3, y0 + int(h * 0.42))], 0.5 * g)

    elif material == "glow":
        for y in range(y0, y0 + h):
            for x in range(x0, x0 + w):
                cx, cy = (x - x0) / max(1, w - 1) - 0.5, (y - y0) / max(1, h - 1) - 0.5
                r = math.sqrt(cx * cx + cy * cy) * 2
                glow_px(img, x, y, max(0.6, 1.0 - r * 0.4) * g, hot=r < 0.5)

    elif material == "glow_core":
        for y in range(y0, y0 + h):
            for x in range(x0, x0 + w):
                cx, cy = (x - x0) / max(1, w - 1) - 0.5, (y - y0) / max(1, h - 1) - 0.5
                r = math.sqrt(cx * cx + cy * cy) * 2
                if r > 0.95:
                    img.putpixel((x, y), (60, 66, 80, 255))
                else:
                    glow_px(img, x, y, (1.0 - r * 0.5) * g, hot=r < 0.45)
        if face == "north":
            # hex frame
            bevel(img, rect, light=(140, 150, 170), dark=(20, 22, 28))

    elif material == "vein_strip":
        for y in range(y0, y0 + h):
            for x in range(x0, x0 + w):
                pulse = 0.6 + 0.4 * math.sin((y - y0) * 0.5)
                glow_px(img, x, y, pulse * g)

    elif material == "glove":
        noise_fill(img, rect, (22, 22, 28), var=4, grain=0.6)
        bevel(img, rect, light=(48, 50, 60), dark=(6, 6, 8))
        if face in ("north", "up") and w >= 10:
            for i in range(3):
                kx = x0 + 3 + i * (w - 6) // 3
                d.line([(kx, y0 + 2), (kx, y0 + h - 3)], fill=(12, 12, 16, 255))
            glow_line(img, [(x0 + 2, y0 + 1), (x0 + w - 3, y0 + 1)], 0.6 * g)

    elif material == "boot":
        noise_fill(img, rect, (20, 21, 26), var=4, grain=0)
        bevel(img, rect, light=(56, 60, 72), dark=(5, 5, 7))
        if face != "down":
            d.line([(x0, y0 + h - 2), (x0 + w - 1, y0 + h - 2)], fill=(40, 44, 54, 255))
            glow_line(img, [(x0 + 1, y0 + h - 4), (x0 + w - 2, y0 + h - 4)], 0.5 * g)
        else:
            # sole tread
            for ty in range(y0 + 1, y0 + h - 1, 3):
                d.line([(x0 + 1, ty), (x0 + w - 2, ty)], fill=(8, 8, 10, 255))
    else:
        noise_fill(img, rect, (255, 0, 255))


FACE_LIGHT = {"up": 1.18, "north": 1.0, "east": 0.9, "west": 0.9, "south": 0.82, "down": 0.6}


def is_emissive(px):
    return px[3] < 250


def finish_face(img, rect, material, face, seed):
    """Directional light, edge AO, cloth folds, specular and glow bloom."""
    x0, y0, w, h = rect
    rnd = random.Random(seed)
    pix = img.load()
    light = FACE_LIGHT[face]
    for y in range(y0, y0 + h):
        for x in range(x0, x0 + w):
            px = pix[x, y]
            if px[3] == 0 or is_emissive(px):
                continue
            # edge ambient occlusion
            ex = min(x - x0, x0 + w - 1 - x)
            ey = min(y - y0, y0 + h - 1 - y)
            ao = 1.0 - 0.22 * max(0.0, 1.0 - min(ex, ey) / 3.0)
            # vertical gradient (top lit)
            grad = 1.08 - 0.16 * (y - y0) / max(1, h - 1)
            m = light * ao * grad
            if material == "coat" and face in ("north", "south", "east", "west") and h > 24:
                # soft diagonal folds
                fold = 0.06 * math.sin((x - x0) * 0.9 + (y - y0) * 0.25 + rnd.random() * 0.2)
                m += fold
            pix[x, y] = (
                max(0, min(255, int(px[0] * m))),
                max(0, min(255, int(px[1] * m))),
                max(0, min(255, int(px[2] * m))),
                255,
            )
    # specular highlights on plates/boots/gloves
    if material in ("plate", "plate_dark", "boot", "glove", "belt") and w >= 6 and h >= 6:
        for i in range(2, min(w, h) // 2):
            xx, yy = x0 + 1 + i, y0 + 1
            if xx < x0 + w - 1:
                p = pix[xx, yy]
                if not is_emissive(p):
                    pix[xx, yy] = (min(255, p[0] + 40), min(255, p[1] + 44), min(255, p[2] + 52), 255)
    # bloom: non-emissive cyan tint around emissive texels
    bloom = []
    for y in range(y0, y0 + h):
        for x in range(x0, x0 + w):
            if is_emissive(pix[x, y]):
                continue
            n = 0
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                xx, yy = x + dx, y + dy
                if x0 <= xx < x0 + w and y0 <= yy < y0 + h and is_emissive(pix[xx, yy]):
                    n += 1
            if n:
                bloom.append((x, y, n))
    for x, y, n in bloom:
        p = pix[x, y]
        k = 0.22 * n
        pix[x, y] = (int(p[0] + (40 - p[0]) * k), int(p[1] + (170 - p[1]) * k), int(p[2] + (210 - p[2]) * k), 255)


def paint_texture(all_cubes, filename, overdrive):
    random.seed(1234)
    img = Image.new("RGBA", (TEX_SIZE, TEX_SIZE), (0, 0, 0, 0))
    seed = 0
    for bname, c in all_cubes:
        for f in FACES:
            uv = c["uv"][f]
            rect = (uv["uv"][0], uv["uv"][1], uv["uv_size"][0], uv["uv_size"][1])
            seed += 1
            paint_face(img, rect, c["material"], f, c["size"], overdrive, seed)
            finish_face(img, rect, c["material"], f, seed)
    out = os.path.join(RP, "textures/entity", filename)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    img.save(out)


# ----------------------------------------------------------------------------
# Item + pack icons
# ----------------------------------------------------------------------------
def paint_core_icon():
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = cy = size / 2
    # outer dark ring (hex)
    pts = [(cx + 26 * math.cos(math.radians(a)), cy + 26 * math.sin(math.radians(a))) for a in range(30, 390, 60)]
    d.polygon(pts, fill=(22, 25, 33, 255), outline=(90, 100, 120, 255))
    pts2 = [(cx + 20 * math.cos(math.radians(a)), cy + 20 * math.sin(math.radians(a))) for a in range(30, 390, 60)]
    d.polygon(pts2, fill=(12, 14, 20, 255), outline=(40, 160, 200, 255))
    # glowing core radial
    for r in range(16, 0, -1):
        t = r / 16
        col = lerp(WHITE_HOT, CYAN_DEEP, t)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col + (255,))
    # vein spokes
    for a in range(0, 360, 60):
        x2 = cx + 24 * math.cos(math.radians(a + 30))
        y2 = cy + 24 * math.sin(math.radians(a + 30))
        d.line([(cx, cy), (x2, y2)], fill=(120, 240, 255, 255), width=2)
    img = img.filter(ImageFilter.SMOOTH)
    img.save(os.path.join(RP, "textures/items/aegis_core.png"))
    # spawn egg & pack icons
    pack = Image.new("RGBA", (256, 256), (10, 12, 18, 255))
    big = img.resize((200, 200), Image.LANCZOS)
    pack.alpha_composite(big, (28, 28))
    d2 = ImageDraw.Draw(pack)
    for i in range(6):
        d2.rectangle([i, i, 255 - i, 255 - i], outline=lerp(CYAN, (10, 12, 18), i / 6) + (255,))
    pack.save(os.path.join(RP, "pack_icon.png"))
    pack.save(os.path.join(ROOT, "Aegis_Primordial_BP", "pack_icon.png"))


if __name__ == "__main__":
    build()
    paint_core_icon()
