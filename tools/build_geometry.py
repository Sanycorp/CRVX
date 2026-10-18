#!/usr/bin/env python3
"""
AEGIS-PRIMORDIAL :: geometry + UV atlas builder
===============================================
Reads tools/model_def.py, shelf-packs every cube face into a single 1024x1024
UV atlas, and writes:

  Aegis_Null_Veil_RP/models/entity/aegis_primordial.geo.json
  tools/uv_layout.json          (consumed by build_textures.py)

Per-face UVs are emitted explicitly ("uv": {"north": {...}, ...}) instead of
relying on the legacy box-unwrap, so the packing is fully deterministic and the
texture painter can use non-uniform texel density (head gets ~2x the resolution
of the boots).
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from model_def import BONES, GEOMETRY_ID, TEXTURE_SIZE, PAD, TARGET_FILL, BASE_SCALE, mirror

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RP = os.path.join(ROOT, "Aegis_Null_Veil_RP")

FACES = ["north", "east", "south", "west", "up", "down"]


# ---------------------------------------------------------------------------
def resolve_mirrors(bones):
    by_name = {b["name"]: b for b in bones if "cubes" in b}
    for b in bones:
        if b.get("mirror_of"):
            src = by_name[b["mirror_of"]]
            b["cubes"] = [mirror(c) for c in src["cubes"]]
            b["locators"] = {
                k: [-v[0], v[1], v[2]] for k, v in src.get("locators", {}).items()
            }
            b["detail"] = 1.0
        b.setdefault("locators", {})
    return bones


def face_unit_size(size, face):
    w, h, d = size
    return {
        "north": (w, h), "south": (w, h),
        "east": (d, h),  "west": (d, h),
        "up": (w, d),    "down": (w, d),
    }[face]


# ---------------------------------------------------------------------------
class ShelfPacker:
    def __init__(self, W, H, pad):
        self.W, self.H, self.pad = W, H, pad
        self.shelf_y = 0
        self.cursor_x = 0
        self.shelf_h = 0
        self.placed = []

    def add(self, w, h):
        w += self.pad * 2
        h += self.pad * 2
        if self.cursor_x + w > self.W:
            self.shelf_y += self.shelf_h
            self.cursor_x = 0
            self.shelf_h = 0
        if self.shelf_y + h > self.H:
            return None
        x, y = self.cursor_x, self.shelf_y
        self.cursor_x += w
        self.shelf_h = max(self.shelf_h, h)
        self.placed.append((x, y, w, h))
        return (x + self.pad, y + self.pad, w - self.pad * 2, h - self.pad * 2)


def pack(bones, scale):
    """Returns (layout, used_area) or None if it does not fit."""
    rects = []  # (h_px, w_px, bone, cube, face)
    unit_area = 0.0
    for b in bones:
        for c in b["cubes"]:
            for f in FACES:
                uw, uh = face_unit_size(c["size"], f)
                pw = max(2, int(round(uw * scale * c["detail"])))
                ph = max(2, int(round(uh * scale * c["detail"])))
                rects.append((ph, pw, b, c, f))
                unit_area += (pw + PAD * 2) * (ph + PAD * 2)
    rects.sort(key=lambda r: (-r[0], -r[1]))
    pk = ShelfPacker(TEXTURE_SIZE, TEXTURE_SIZE, PAD)
    layout = []
    for ph, pw, b, c, f in rects:
        r = pk.add(pw, ph)
        if r is None:
            return None
        layout.append({
            "bone": b["name"], "tag": c["tag"], "mat": c["mat"], "face": f,
            "detail": c["detail"], "veins": c["veins"], "glow": c["glow"],
            "units": list(face_unit_size(c["size"], f)),
            "rect": list(r), "pad": PAD,
        })
    return layout, unit_area


# ---------------------------------------------------------------------------
def main():
    global TEXTURE_SIZE
    for arg in sys.argv[1:]:
        if arg.startswith("--size="):
            TEXTURE_SIZE = int(arg.split("=", 1)[1])
    bones = resolve_mirrors([dict(b) for b in BONES])

    # find the biggest scale that packs into the atlas at ~TARGET_FILL
    scale = BASE_SCALE
    for _ in range(400):
        res = pack(bones, scale)
        if res is not None:
            layout, area = res
            break
        scale *= 0.97
    else:
        raise SystemExit("could not pack atlas")

    fill = area / float(TEXTURE_SIZE * TEXTURE_SIZE)
    if fill < TARGET_FILL * 0.75:          # room to spare -> grow resolution
        s2, best = scale, (layout, area)
        for _ in range(400):
            s2 *= 1.02
            res = pack(bones, s2)
            if res is None:
                break
            best = res
            if best[1] / float(TEXTURE_SIZE ** 2) > TARGET_FILL:
                break
        layout, area = best
        scale = s2
    fill = area / float(TEXTURE_SIZE * TEXTURE_SIZE)

    # ---- geometry json -----------------------------------------------------
    uv_by_cube = {}
    for e in layout:
        uv_by_cube.setdefault((e["bone"], e["tag"]), {})[e["face"]] = e["rect"]

    geo_bones = []
    for b in bones:
        gb = {"name": b["name"], "pivot": [round(v, 4) for v in b["pivot"]]}
        if b["parent"]:
            gb["parent"] = b["parent"]
        cubes = []
        for c in b["cubes"]:
            faces = uv_by_cube[(b["name"], c["tag"])]
            uv = {}
            for f in FACES:
                x, y, w, h = faces[f]
                uv[f] = {"uv": [x, y], "uv_size": [w, h]}
            cubes.append({
                "origin": [round(v, 4) for v in c["origin"]],
                "size": [round(v, 4) for v in c["size"]],
                "uv": uv,
            })
        if cubes:
            gb["cubes"] = cubes
        if b.get("locators"):
            gb["locators"] = {k: [round(v, 4) for v in val]
                              for k, val in b["locators"].items()}
        geo_bones.append(gb)

    geo = {
        "format_version": "1.21.0",
        "minecraft:geometry": [{
            "description": {
                "identifier": GEOMETRY_ID,
                "texture_width": TEXTURE_SIZE,
                "texture_height": TEXTURE_SIZE,
                "visible_bounds_width": 3.0,
                "visible_bounds_height": 2.6,
                "visible_bounds_offset": [0, 1.05, 0],
            },
            "bones": geo_bones,
        }],
    }

    out_geo = os.path.join(RP, "models", "entity", "aegis_primordial.geo.json")
    os.makedirs(os.path.dirname(out_geo), exist_ok=True)
    with open(out_geo, "w") as fh:
        json.dump(geo, fh, indent=1)

    with open(os.path.join(ROOT, "tools", "uv_layout.json"), "w") as fh:
        json.dump({"texture_size": TEXTURE_SIZE, "scale": scale,
                   "geometry": GEOMETRY_ID, "faces": layout}, fh)

    ncubes = sum(len(b["cubes"]) for b in bones)
    print(f"geometry : {out_geo}")
    print(f"bones    : {len(geo_bones)}")
    print(f"cubes    : {ncubes}")
    print(f"faces    : {len(layout)}")
    print(f"atlas    : {TEXTURE_SIZE}x{TEXTURE_SIZE}  scale={scale:.2f} px/unit  fill={fill*100:.1f}%")
    # sanity: no region outside atlas / overlapping
    seen = {}
    for e in layout:
        x, y, w, h = e["rect"]
        assert 0 <= x and x + w <= TEXTURE_SIZE and 0 <= y and y + h <= TEXTURE_SIZE, e
        seen.setdefault((e["bone"], e["tag"]), set()).add(e["face"])
    for k, v in seen.items():
        assert v == set(FACES), (k, v)
    print("validation: all cube faces mapped, all regions inside atlas  -> OK")


if __name__ == "__main__":
    main()
