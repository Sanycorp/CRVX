#!/usr/bin/env python3
"""
AEGIS-PRIMORDIAL :: offline model preview renderer
==================================================
Dev-only sanity tool. Reads the built geometry + painted atlas and orthographically
rasterises the model so we can *see* that:
  * the model is a correct human form,
  * every face samples the atlas region it was painted for (no scrambled UVs),
  * the entity faces -Z, i.e. eyes / chest core are on the FRONT.

Face UV convention used here is the same one Bedrock uses for box-unwrapped cubes
(artwork reads upright & un-mirrored when the face is viewed from outside).
"""
import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RP = os.path.join(ROOT, "Aegis_Null_Veil_RP")

GEO = json.load(open(os.path.join(RP, "models", "entity", "aegis_primordial.geo.json")))
GEOM = GEO["minecraft:geometry"][0]
TW = GEOM["description"]["texture_width"]
TH = GEOM["description"]["texture_height"]

TEX_PATH = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
    RP, "textures", "entity", "aegis_primordial.png")
TEX = np.asarray(Image.open(TEX_PATH).convert("RGBA"), dtype=np.float32) / 255.0

# face -> (right vector, down vector) in model space
FACE_AXES = {
    "north": (np.array([-1.0, 0, 0]), np.array([0, -1.0, 0])),
    "south": (np.array([1.0, 0, 0]),  np.array([0, -1.0, 0])),
    "east":  (np.array([0, 0, -1.0]), np.array([0, -1.0, 0])),
    "west":  (np.array([0, 0, 1.0]),  np.array([0, -1.0, 0])),
    "up":    (np.array([1.0, 0, 0]),  np.array([0, 0, 1.0])),
    "down":  (np.array([1.0, 0, 0]),  np.array([0, 0, -1.0])),
}
FACE_NORMAL = {
    "north": np.array([0, 0, -1.0]), "south": np.array([0, 0, 1.0]),
    "east": np.array([1.0, 0, 0]),   "west": np.array([-1.0, 0, 0]),
    "up": np.array([0, 1.0, 0]),     "down": np.array([0, -1.0, 0]),
}
FACE_SIZE = {"north": (0, 1), "south": (0, 1), "east": (2, 1),
             "west": (2, 1), "up": (0, 2), "down": (0, 2)}


def build_faces():
    out = []
    for b in GEOM["bones"]:
        for ci, c in enumerate(b.get("cubes", [])):
            o = np.array(c["origin"], dtype=np.float64)
            s = np.array(c["size"], dtype=np.float64)
            center = o + s / 2.0
            for fname, uvd in c["uv"].items():
                u0, v0 = uvd["uv"]
                uw, uh = uvd["uv_size"]
                R, D = FACE_AXES[fname]
                N = FACE_NORMAL[fname]
                iw, ih = FACE_SIZE[fname]
                fw, fh = float(s[iw]), float(s[ih])
                # face centre sits on the cube surface
                fc = center + N * (float(s[abs(int(np.argmax(np.abs(N))))]) / 2.0)
                c0 = fc - R * (fw / 2.0) - D * (fh / 2.0)
                out.append(dict(c0=c0, R=R * fw, D=D * fh, N=N,
                                u0=u0, v0=v0, uw=uw, uh=uh,
                                bone=b["name"], cube=ci))
    return out


def render(cam_pos, target, out_path, scale=26.0, W=520, H=760, bg=(16, 20, 28),
           fov_up=1.0, pose=None):
    cam = np.array(cam_pos, dtype=np.float64)
    tgt = np.array(target, dtype=np.float64)
    fwd = tgt - cam
    fwd /= np.linalg.norm(fwd)
    up0 = np.array([0.0, 1.0, 0.0])
    right = np.cross(fwd, up0)
    right /= np.linalg.norm(right)
    up = np.cross(right, fwd)

    img = np.zeros((H, W, 3), dtype=np.float32)
    img[:, :] = np.array(bg, dtype=np.float32) / 255.0
    zbuf = np.full((H, W), 1e18, dtype=np.float64)

    faces = build_faces()
    # optional pose: {bone_name: (axis, angle_deg, pivot)}  (dev aid)
    if pose:
        for f in faces:
            pass

    def project(p):
        rel = p - tgt
        x = float(np.dot(rel, right)) * scale + W / 2.0
        y = -float(np.dot(rel, up)) * scale + H * 0.62
        z = float(np.dot(rel, fwd))
        return x, y, z

    for f in faces:
        if float(np.dot(f["N"], fwd)) >= 0:      # backface cull
            continue
        p00 = project(f["c0"])
        p10 = project(f["c0"] + f["R"])
        p01 = project(f["c0"] + f["D"])
        xs = [p00[0], p10[0], p01[0], p10[0] + p01[0] - p00[0]]
        ys = [p00[1], p10[1], p01[1], p10[1] + p01[1] - p00[1]]
        x0, x1 = int(max(0, math.floor(min(xs)))), int(min(W - 1, math.ceil(max(xs))))
        y0, y1 = int(max(0, math.floor(min(ys)))), int(min(H - 1, math.ceil(max(ys))))
        if x1 < x0 or y1 < y0:
            continue
        # affine: screen = M*(a,b) + p00  (a,b in [0,1] face space)
        M = np.array([[p10[0] - p00[0], p01[0] - p00[0]],
                      [p10[1] - p00[1], p01[1] - p00[1]]], dtype=np.float64)
        if abs(np.linalg.det(M)) < 1e-9:
            continue
        Minv = np.linalg.inv(M)
        zbase = p00[2]
        zda = (p10[2] - p00[2])
        zdb = (p01[2] - p00[2])
        yy, xx = np.mgrid[y0:y1 + 1, x0:x1 + 1]
        px = xx - p00[0]
        py = yy - p00[1]
        a = Minv[0, 0] * px + Minv[0, 1] * py
        b = Minv[1, 0] * px + Minv[1, 1] * py
        m = (a >= 0) & (a < 1) & (b >= 0) & (b < 1)
        if not m.any():
            continue
        uu = (f["u0"] + a * f["uw"]).astype(np.int32) % TW
        vv = (f["v0"] + b * f["uh"]).astype(np.int32) % TH
        cols = TEX[vv, uu]
        zz = zbase + a * zda + b * zdb
        alpha = cols[..., 3:4]
        rgb = cols[..., :3]
        # simple lighting
        lam = float(np.dot(f["N"], np.array([0.35, 0.82, 0.45]) /
                           np.linalg.norm([0.35, 0.82, 0.45])))
        lam = 0.72 + 0.34 * max(0.0, lam)
        sub = img[y0:y1 + 1, x0:x1 + 1]
        zsub = zbuf[y0:y1 + 1, x0:x1 + 1]
        upd = m & (zz < zsub)
        sub[upd] = sub[upd] * (1 - alpha[upd]) + rgb[upd] * lam * alpha[upd]
        zsub[upd] = zz[upd]

    Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(out_path)
    print("rendered", out_path)


if __name__ == "__main__":
    os.makedirs(os.path.join(ROOT, "assets"), exist_ok=True)
    A = os.path.join(ROOT, "assets")
    # front (-Z) view : camera in front of the entity
    render([0, 16, -60], [0, 16, 0], os.path.join(A, "render_front.png"))
    # 3/4 hero view
    render([-34, 22, -46], [0, 15, 0], os.path.join(A, "render_hero.png"))
    # back view
    render([0, 16, 60], [0, 16, 0], os.path.join(A, "render_back.png"))
    # side view
    render([-60, 16, 0], [0, 16, 0], os.path.join(A, "render_side.png"))
