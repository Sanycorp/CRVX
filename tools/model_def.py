"""
AEGIS-PRIMORDIAL :: NULL VEIL SENTINEL
--------------------------------------
Single source of truth for the entity model.

Coordinate conventions (verified against official Mojang bedrock-samples geometry):
  * 1 geometry unit = 1/16 block, so a ~31 unit tall model == ~1.94 blocks.
  * FORWARD  = -Z   (verified: vanilla pig snout sits at z=-15 in front of a head
                     spanning z=-14..-6; vanilla wolf snout z=-12 with tail at z=+8).
                     => the "north" cube face is the FRONT of the entity.
  * The model's own right side is -X, matching `geometry.humanoid.custom`
    (rightArm pivot x = -5, leftArm pivot x = +5) in the official samples.

This module only describes bones/cubes; `build_geometry.py` packs the UV atlas and
emits models/entity/aegis_primordial.geo.json, `build_textures.py` paints it.
"""

# ----------------------------------------------------------------------------
# cube helper
# ----------------------------------------------------------------------------
def cube(x, y, z, w, h, d, mat, detail=1.0, veins=0.0, glow=0.0, tag=""):
    """Axis aligned box in geometry units (1 unit = 1/16 block)."""
    return {
        "origin": [float(x), float(y), float(z)],
        "size": [float(w), float(h), float(d)],
        "mat": mat,
        "detail": detail,
        "veins": veins,   # 0..1 amount of cyan energy veining on the base texture
        "glow": glow,     # 0..1 how strongly this cube emits on the emissive map
        "tag": tag,
    }


def mirror(c):
    """Mirror a cube across X (right side -> left side)."""
    x, y, z = c["origin"]
    w, h, d = c["size"]
    out = dict(c)
    out["origin"] = [-(x + w), float(y), float(z)]
    out["tag"] = (c["tag"] or "") + "_M"
    return out


# ----------------------------------------------------------------------------
# materials (consumed by the texture painter)
# ----------------------------------------------------------------------------
MAT = {
    "coat":     dict(base=(46, 52, 63),   noise=0.16, freq=0.55, fold=1.0, grain="fabric"),
    "coat_in":  dict(base=(27, 31, 39),   noise=0.13, freq=0.55, fold=0.7, grain="fabric"),
    "veil":     dict(base=(36, 43, 56),   noise=0.10, freq=0.40, fold=1.4, grain="fabric"),
    "armor":    dict(base=(84, 93, 107),  noise=0.11, freq=0.90, fold=0.0, grain="metal"),
    "armor_d":  dict(base=(58, 65, 76),   noise=0.11, freq=0.90, fold=0.0, grain="metal"),
    "plate":    dict(base=(112, 124, 142),noise=0.09, freq=1.10, fold=0.0, grain="metal"),
    "leather":  dict(base=(48, 48, 55),   noise=0.14, freq=0.70, fold=0.3, grain="leather"),
    "leather2": dict(base=(34, 35, 41),   noise=0.14, freq=0.70, fold=0.3, grain="leather"),
    "skin":     dict(base=(150, 142, 134),noise=0.10, freq=1.40, fold=0.0, grain="skin"),
    "visor":    dict(base=(10, 13, 18),   noise=0.05, freq=1.60, fold=0.0, grain="metal"),
    "eye":      dict(base=(8, 30, 38),    noise=0.03, freq=1.60, fold=0.0, grain="metal"),
    "core":     dict(base=(10, 40, 50),   noise=0.04, freq=1.20, fold=0.0, grain="metal"),
}


# ============================================================================
# BONE TREE
#   name, parent, pivot, cubes, locators, detail-multiplier
# ============================================================================
BONES = [
    # ---- root / spine -------------------------------------------------------
    dict(name="root", parent=None, pivot=[0, 0, 0], cubes=[], locators={}),

    dict(name="waist", parent="root", pivot=[0, 12, 0], cubes=[
        cube(-4.7, 11.6, -2.7, 9.4, 2.0, 5.4, "leather2", 1.4, veins=0.25, tag="belt"),
        cube(-1.6, 11.4, -3.0, 3.2, 2.4, 0.8, "plate", 1.6, veins=0.6, tag="buckle"),
    ], locators={}),

    dict(name="body", parent="waist", pivot=[0, 12, 0], cubes=[
        cube(-4.5, 12.0, -2.5, 9.0, 12.0, 5.0, "coat", 1.5, veins=0.35, tag="torso"),
        cube(-3.4, 12.6, -3.0, 6.8, 6.4, 0.9, "armor", 1.6, veins=0.45, tag="abs_plate"),
        cube(-3.4, 13.6, 2.4, 6.8, 7.0, 0.9, "armor_d", 1.6, veins=0.30, tag="back_plate"),
        cube(-0.35, 12.6, -3.2, 0.7, 8.0, 0.6, "plate", 1.6, veins=0.7, tag="spine_line"),
    ], locators={}),

    dict(name="chest", parent="body", pivot=[0, 19.5, 0], cubes=[
        cube(-4.6, 18.0, -2.6, 9.2, 6.2, 5.2, "armor", 1.6, veins=0.50, tag="chest_plate"),
        cube(-5.4, 22.6, -3.0, 10.8, 1.6, 6.0, "plate", 1.6, veins=0.35, tag="collar"),
        cube(-5.2, 19.6, -3.1, 3.0, 3.2, 0.7, "armor_d", 1.5, veins=0.55, tag="pec_r"),
        cube(2.2, 19.6, -3.1, 3.0, 3.2, 0.7, "armor_d", 1.5, veins=0.55, tag="pec_l"),
    ], locators={"core": [0.0, 21.0, -4.2], "aura": [0.0, 18.0, 0.0]}),

    dict(name="chest_core", parent="chest", pivot=[0, 21, -3.4], cubes=[
        cube(-1.3, 19.7, -3.7, 2.6, 2.6, 1.0, "core", 2.0, glow=1.0, tag="core_gem"),
        cube(-1.7, 19.3, -3.3, 3.4, 3.4, 0.5, "armor", 2.0, veins=0.8, tag="core_frame"),
    ], locators={}),

    # slowly counter-rotating ring of shards around the core
    dict(name="core_ring", parent="chest", pivot=[0, 21, -3.2], cubes=[
        cube(-0.45, 23.0, -3.5, 0.9, 0.9, 0.5, "core", 2.0, glow=0.9, tag="ring_0"),
        cube(-0.45, 19.0, -3.5, 0.9, 0.9, 0.5, "core", 2.0, glow=0.9, tag="ring_1"),
        cube(-2.85, 20.55, -3.5, 0.9, 0.9, 0.5, "core", 2.0, glow=0.9, tag="ring_2"),
        cube(1.95, 20.55, -3.5, 0.9, 0.9, 0.5, "core", 2.0, glow=0.9, tag="ring_3"),
    ], locators={}),

    dict(name="neck", parent="chest", pivot=[0, 24, -0.2], cubes=[
        cube(-1.5, 22.6, -1.5, 3.0, 1.6, 3.0, "coat_in", 1.6, tag="neck"),
    ], locators={}),

    # ---- head ---------------------------------------------------------------
    dict(name="head", parent="neck", pivot=[0, 24.4, -0.2], cubes=[
        cube(-3.5, 24.2, -3.5, 7.0, 7.0, 7.0, "skin", 2.2, tag="skull"),
        cube(-3.0, 24.4, -4.0, 6.0, 3.4, 0.8, "visor", 2.4, veins=0.2, tag="jaw_guard"),
        cube(-2.7, 27.6, -3.9, 5.4, 1.4, 0.7, "eye", 2.6, glow=1.0, tag="eye_bar"),
        cube(-3.0, 30.4, -3.4, 6.0, 0.9, 6.8, "visor", 2.2, tag="brow"),
    ], locators={"eyes": [0.0, 28.3, -4.6], "breath": [0.0, 26.0, -4.4]}),

    dict(name="hood", parent="head", pivot=[0, 30.5, 0.2], cubes=[
        cube(-4.3, 28.6, -4.3, 8.6, 2.6, 8.6, "coat", 2.0, veins=0.25, tag="hood_top"),
        cube(-4.3, 23.6, 2.2, 8.6, 6.0, 2.1, "coat", 2.0, veins=0.25, tag="hood_back"),
        cube(-4.5, 23.6, -4.3, 1.8, 6.0, 8.6, "coat", 2.0, veins=0.25, tag="hood_side_r"),
        cube(2.7, 23.6, -4.3, 1.8, 6.0, 8.6, "coat", 2.0, veins=0.25, tag="hood_side_l"),
        cube(-1.1, 30.6, -4.8, 2.2, 1.2, 9.4, "coat_in", 2.0, veins=0.4, tag="hood_peak"),
        cube(-2.2, 31.4, -2.0, 4.4, 0.8, 6.0, "coat_in", 2.0, tag="hood_ridge"),
    ], locators={}),

    dict(name="hood_veil", parent="head", pivot=[0, 24.0, 2.0], cubes=[
        cube(-3.6, 20.6, 2.6, 7.2, 4.4, 0.9, "veil", 2.0, veins=0.35, tag="veil_back"),
    ], locators={}),

    # ---- right arm (-X) ----------------------------------------------------
    dict(name="arm_right", parent="chest", pivot=[-5.6, 22.8, 0], cubes=[
        cube(-7.9, 17.0, -1.9, 3.4, 6.0, 3.6, "coat", 1.6, veins=0.3, tag="upperarm_r"),
        cube(-7.7, 18.0, -2.1, 3.0, 2.6, 4.0, "armor", 1.6, veins=0.4, tag="bicep_r"),
    ], locators={}),

    dict(name="pauldron_right", parent="arm_right", pivot=[-5.6, 22.8, 0], cubes=[
        cube(-8.2, 21.7, -3.3, 4.2, 3.0, 6.4, "armor", 1.8, veins=0.55, tag="pauldron_r"),
        cube(-8.4, 20.8, -3.1, 4.6, 1.1, 6.0, "plate", 1.8, veins=0.4, tag="pauldron_trim_r"),
    ], locators={}),

    dict(name="forearm_right", parent="arm_right", pivot=[-6.2, 17.0, 0], cubes=[
        cube(-7.7, 11.6, -1.8, 3.0, 5.6, 3.2, "armor_d", 1.6, veins=0.4, tag="forearm_r"),
        cube(-7.9, 12.6, -2.0, 3.2, 2.2, 3.6, "plate", 1.6, veins=0.6, tag="bracer_r"),
    ], locators={}),

    dict(name="hand_right", parent="forearm_right", pivot=[-6.2, 11.6, 0], cubes=[
        cube(-7.3, 9.2, -1.6, 2.6, 2.4, 2.6, "leather", 2.0, veins=0.5, tag="palm_r"),
        cube(-7.1, 9.4, -2.0, 2.2, 1.2, 0.6, "core", 2.2, glow=0.85, tag="palm_glow_r"),
    ], locators={"palm": [-6.2, 8.6, -0.4]}),

    dict(name="fingers_right", parent="hand_right", pivot=[-6.2, 9.2, 0], cubes=[
        cube(-7.3, 7.4, -1.5, 0.55, 1.9, 1.5, "leather2", 2.2, tag="f1_r"),
        cube(-6.65, 7.3, -1.5, 0.55, 2.0, 1.5, "leather2", 2.2, tag="f2_r"),
        cube(-6.0, 7.4, -1.5, 0.55, 1.9, 1.5, "leather2", 2.2, tag="f3_r"),
        cube(-5.35, 7.6, -1.5, 0.55, 1.7, 1.5, "leather2", 2.2, tag="f4_r"),
    ], locators={}),

    dict(name="thumb_right", parent="hand_right", pivot=[-6.6, 10.0, -0.4], cubes=[
        cube(-7.6, 8.6, -1.9, 0.6, 1.5, 0.9, "leather2", 2.2, tag="thumb_r"),
    ], locators={}),

    # ---- left arm (+X) : generated by mirroring -----------------------------
    dict(name="arm_left", parent="chest", pivot=[5.6, 22.8, 0], mirror_of="arm_right"),
    dict(name="pauldron_left", parent="arm_left", pivot=[5.6, 22.8, 0], mirror_of="pauldron_right"),
    dict(name="forearm_left", parent="arm_left", pivot=[6.2, 17.0, 0], mirror_of="forearm_right"),
    dict(name="hand_left", parent="forearm_left", pivot=[6.2, 11.6, 0], mirror_of="hand_right"),
    dict(name="fingers_left", parent="hand_left", pivot=[6.2, 9.2, 0], mirror_of="fingers_right"),
    dict(name="thumb_left", parent="hand_left", pivot=[6.6, 10.0, -0.4], mirror_of="thumb_right"),

    # ---- legs ---------------------------------------------------------------
    dict(name="leg_right", parent="waist", pivot=[-2.3, 12.0, 0], cubes=[
        cube(-4.1, 0.9, -2.0, 3.6, 11.1, 3.6, "coat", 1.25, veins=0.25, tag="thigh_r"),
        cube(-3.9, 3.0, -2.2, 3.2, 3.4, 4.0, "armor", 1.25, veins=0.35, tag="cuisse_r"),
    ], locators={}),

    dict(name="shin_right", parent="leg_right", pivot=[-2.3, 6.0, 0], cubes=[
        cube(-3.9, 1.4, -1.8, 3.2, 4.7, 3.2, "armor_d", 1.3, veins=0.3, tag="shin_r"),
        cube(-4.1, 2.4, -2.1, 3.6, 1.6, 3.8, "plate", 1.3, veins=0.45, tag="knee_r"),
    ], locators={}),

    dict(name="boot_right", parent="shin_right", pivot=[-2.3, 1.4, 0], cubes=[
        cube(-4.2, 0.0, -3.2, 3.8, 1.5, 5.2, "leather", 1.4, veins=0.2, tag="boot_r"),
        cube(-4.4, 1.2, -2.2, 4.2, 0.7, 4.2, "plate", 1.4, veins=0.35, tag="boottrim_r"),
    ], locators={"step": [-2.3, 0.0, -1.6]}),

    dict(name="leg_left", parent="waist", pivot=[2.3, 12.0, 0], mirror_of="leg_right"),
    dict(name="shin_left", parent="leg_left", pivot=[2.3, 6.0, 0], mirror_of="shin_right"),
    dict(name="boot_left", parent="shin_left", pivot=[2.3, 1.4, 0], mirror_of="boot_right"),

    # ---- coat (7 independently swaying bones) -------------------------------
    dict(name="coat_hips", parent="waist", pivot=[0, 12.6, 0], cubes=[
        cube(-4.9, 11.4, -3.1, 9.8, 1.6, 6.2, "coat", 1.5, veins=0.4, tag="coat_waist"),
    ], locators={}),

    dict(name="coat_flap_fr", parent="coat_hips", pivot=[-3.2, 12.4, -2.9], cubes=[
        cube(-5.3, 2.6, -3.5, 4.8, 9.2, 1.1, "coat", 1.5, veins=0.45, tag="flap_fr"),
        cube(-5.35, 2.2, -3.6, 4.9, 0.8, 1.3, "coat_in", 1.5, veins=0.5, tag="hem_fr"),
    ], locators={}),

    dict(name="coat_flap_fl", parent="coat_hips", pivot=[3.2, 12.4, -2.9],
         cubes=[mirror(c) for c in [
             cube(-5.3, 2.6, -3.5, 4.8, 9.2, 1.1, "coat", 1.5, veins=0.45, tag="flap_base"),
             cube(-5.35, 2.2, -3.6, 4.9, 0.8, 1.3, "coat_in", 1.5, veins=0.5, tag="hem_base"),
         ]]),

    dict(name="coat_flap_br", parent="coat_hips", pivot=[-3.2, 12.4, 2.9], cubes=[
        cube(-5.3, 2.6, 2.4, 4.8, 9.2, 1.1, "coat", 1.5, veins=0.40, tag="flap_br"),
        cube(-5.35, 2.2, 2.3, 4.9, 0.8, 1.3, "coat_in", 1.5, veins=0.45, tag="hem_br"),
    ], locators={}),

    dict(name="coat_flap_bl", parent="coat_hips", pivot=[3.2, 12.4, 2.9],
         cubes=[mirror(c) for c in [
             cube(-5.3, 2.6, 2.4, 4.8, 9.2, 1.1, "coat", 1.5, veins=0.40, tag="flap_base_b"),
             cube(-5.35, 2.2, 2.3, 4.9, 0.8, 1.3, "coat_in", 1.5, veins=0.45, tag="hem_base_b"),
         ]]),

    dict(name="coat_side_r", parent="coat_hips", pivot=[-4.8, 12.4, 0], cubes=[
        cube(-5.7, 5.2, -3.1, 1.3, 7.6, 6.2, "coat", 1.5, veins=0.35, tag="side_r"),
    ], locators={}),

    dict(name="coat_side_l", parent="coat_hips", pivot=[4.8, 12.4, 0],
         cubes=[mirror(c) for c in [
             cube(-5.7, 5.2, -3.1, 1.3, 7.6, 6.2, "coat", 1.5, veins=0.35, tag="side_base"),
         ]]),

    dict(name="coat_tail", parent="coat_hips", pivot=[0, 12.4, 2.6], cubes=[
        cube(-3.1, 4.4, 2.5, 6.2, 8.0, 1.0, "coat_in", 1.5, veins=0.4, tag="tail"),
        cube(-3.15, 3.9, 2.4, 6.3, 0.7, 1.2, "coat", 1.5, veins=0.45, tag="tail_hem"),
    ], locators={}),

    # ---- void cloak (2 bone chain, heavy sway) ------------------------------
    dict(name="cloak_upper", parent="chest", pivot=[0, 23.2, 2.2], cubes=[
        cube(-5.5, 13.6, 2.0, 11.0, 9.8, 1.2, "veil", 1.6, veins=0.5, tag="cloak_u"),
    ], locators={}),

    dict(name="cloak_lower", parent="cloak_upper", pivot=[0, 13.6, 2.4], cubes=[
        cube(-5.0, 4.4, 2.3, 10.0, 9.4, 1.0, "veil", 1.6, veins=0.55, tag="cloak_l"),
        cube(-5.1, 3.6, 2.2, 10.2, 0.9, 1.2, "coat_in", 1.6, veins=0.6, tag="cloak_hem"),
    ], locators={}),

    # ---- front veil / tabard ------------------------------------------------
    dict(name="veil_r", parent="chest", pivot=[-1.9, 23.0, -2.9], cubes=[
        cube(-3.0, 14.6, -3.3, 2.2, 8.4, 0.8, "veil", 1.7, veins=0.5, tag="veil_r"),
    ], locators={}),

    dict(name="veil_l", parent="chest", pivot=[1.9, 23.0, -2.9],
         cubes=[mirror(c) for c in [
             cube(-3.0, 14.6, -3.3, 2.2, 8.4, 0.8, "veil", 1.7, veins=0.5, tag="veil_base"),
         ]]),
]

GEOMETRY_ID = "geometry.aegis_primordial"
TEXTURE_SIZE = 1024          # atlas is 1024 x 1024 (both base and emissive)
PAD = 2                      # gutter between face regions (stops mip bleeding)
TARGET_FILL = 0.58           # aim to use this fraction of the atlas
BASE_SCALE = 8.0             # px per geometry unit before per-cube detail multipliers
