#!/usr/bin/env python3
"""
AEGIS-PRIMORDIAL :: particle emitter builder
============================================
Writes the ten particle effects used by the sentinel into
Aegis_Null_Veil_RP/particles/.

Schema: the modern particle component set (emitter_rate_steady / emitter_lifetime_looping /
emitter_shape_* / particle_appearance_tinting ...) as used by the current
Mojang bedrock-samples and documented on learn.microsoft.com.

UV cells come from the vanilla 128x128 particle atlas:
  [0,24] soft round blob   (same cell vanilla `basic_flame` uses)
  [0,16] hollow ring       (same cell vanilla `basic_bubble` uses)
  [56,0] 8-frame smoke flipbook
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "Aegis_Null_Veil_RP", "particles")

TW = TH = 128
BLOB = {"texture_width": TW, "texture_height": TH, "uv": [0, 24], "uv_size": [8, 8]}
RING = {"texture_width": TW, "texture_height": TH, "uv": [0, 16], "uv_size": [8, 8]}
SMOKE = {
    "texture_width": TW, "texture_height": TH, "uv": [0, 0], "uv_size": [1, 1],
    "flipbook": {"base_UV": [56, 0], "size_UV": [8, 8], "step_UV": [-8, 0],
                 "frames_per_second": 10, "max_frame": 8, "stretch_to_lifetime": True},
}

# cyan palette -------------------------------------------------------------
C_HOT = [0.85, 1.00, 1.00]
C_CYAN = [0.11, 0.91, 1.00]
C_DEEP = [0.03, 0.42, 0.78]
C_VOID = [0.05, 0.12, 0.30]


def tint(stops):
    """stops: list of (position, [r,g,b,a])"""
    return {"color": {"gradient": {"%.6f" % p: c for p, c in stops},
                      "interpolant": "variable.particle_age / variable.particle_lifetime"}}


def billboard(size_w, size_h, uv, mode="lookat_xyz"):
    return {"size": [size_w, size_h], "facing_camera_mode": mode, "uv": uv}


def effect(identifier, components, events=None):
    return {
        "format_version": "1.10.0",
        "particle_effect": {
            "description": {
                "identifier": identifier,
                "basic_render_parameters": {
                    "material": "particles_alpha",
                    "texture": "textures/particle/particles",
                },
            },
            "components": components,
        },
    }


LOCAL = {"position": True, "rotation": True, "velocity": True}

PARTICLES = {}

# 1 ── constant eye glow ----------------------------------------------------
PARTICLES["eye_glow"] = effect("aegis:eye_glow", {
    "minecraft:emitter_local_space": LOCAL,
    "minecraft:emitter_lifetime_looping": {"active_time": 3.2, "sleep_time": 0.05},
    "minecraft:emitter_rate_steady": {"spawn_rate": 16, "max_particles": 26},
    "minecraft:emitter_shape_sphere": {"radius": 0.055, "direction": [0, 0.30, 0]},
    "minecraft:particle_lifetime_expression": {"max_lifetime": "Math.random(0.25, 0.65)"},
    "minecraft:particle_initial_speed": 0.05,
    "minecraft:particle_motion_dynamic": {"linear_acceleration": [0, 0.22, 0]},
    "minecraft:particle_appearance_billboard": billboard(
        "0.05 + variable.particle_random_1 * 0.035",
        "0.05 + variable.particle_random_1 * 0.035", BLOB),
    "minecraft:particle_appearance_tinting": tint([
        (0.0, [C_CYAN[0], C_CYAN[1], C_CYAN[2], 0.0]),
        (0.30, [C_HOT[0], C_HOT[1], C_HOT[2], 0.95]),
        (1.0, [C_DEEP[0], C_DEEP[1], C_DEEP[2], 0.0]),
    ]),
    "minecraft:particle_appearance_lighting": {},
})

# 2 ── chest core pulse -----------------------------------------------------
PARTICLES["chest_core_pulse"] = effect("aegis:chest_core_pulse", {
    "minecraft:emitter_local_space": LOCAL,
    "minecraft:emitter_lifetime_looping": {"active_time": 3.0, "sleep_time": 0.1},
    "minecraft:emitter_rate_steady": {"spawn_rate": 34, "max_particles": 64},
    "minecraft:emitter_shape_sphere": {"radius": 0.34, "direction": [0, 0, 0]},
    "minecraft:particle_lifetime_expression": {"max_lifetime": "Math.random(0.5, 1.1)"},
    "minecraft:particle_initial_speed": "Math.random(0.15, 0.5)",
    "minecraft:particle_motion_dynamic": {
        "linear_acceleration": [
            "Math.cos(variable.emitter_age * 5.0) * 0.35",
            "0.35 + variable.particle_age * 0.25",
            "Math.sin(variable.emitter_age * 5.0) * 0.35",
        ]
    },
    "minecraft:particle_appearance_billboard": billboard(
        "(0.09 + variable.particle_random_1 * 0.06) * (1.0 - variable.particle_age / variable.particle_lifetime * 0.6)",
        "(0.09 + variable.particle_random_1 * 0.06) * (1.0 - variable.particle_age / variable.particle_lifetime * 0.6)", BLOB),
    "minecraft:particle_appearance_tinting": tint([
        (0.0, [C_HOT[0], C_HOT[1], C_HOT[2], 0.0]),
        (0.22, [C_CYAN[0], C_CYAN[1], C_CYAN[2], 0.9]),
        (1.0, [C_VOID[0], C_VOID[1], C_VOID[2], 0.0]),
    ]),
    "minecraft:particle_appearance_lighting": {},
})

# 3 ── Null Sever charge (dense converging swirl) ---------------------------
PARTICLES["null_sever_charge"] = effect("aegis:null_sever_charge", {
    "minecraft:emitter_local_space": LOCAL,
    "minecraft:emitter_lifetime_looping": {"active_time": 2.6, "sleep_time": 0.0},
    "minecraft:emitter_rate_steady": {"spawn_rate": 150, "max_particles": 320},
    "minecraft:emitter_shape_sphere": {"radius": 1.45, "direction": [0, 0, 0]},
    "minecraft:particle_lifetime_expression": {"max_lifetime": "Math.random(0.45, 1.0)"},
    "minecraft:particle_initial_speed": "Math.random(0.1, 0.5)",
    "minecraft:particle_motion_dynamic": {
        "linear_acceleration": [
            "-variable.particle_random_1 * 0.9 + Math.cos(variable.emitter_age * 7.0) * 0.9",
            "0.25 + Math.sin(variable.emitter_age * 3.0) * 0.3",
            "-variable.particle_random_2 * 0.9 + Math.sin(variable.emitter_age * 7.0) * 0.9",
        ],
        "linear_drag_coefficient": 1.2,
    },
    "minecraft:particle_appearance_billboard": billboard(
        "(0.22 + variable.particle_random_1 * 0.16) * (1.0 - variable.particle_age / variable.particle_lifetime)",
        "(0.22 + variable.particle_random_1 * 0.16) * (1.0 - variable.particle_age / variable.particle_lifetime)", BLOB),
    "minecraft:particle_appearance_tinting": tint([
        (0.0, [C_DEEP[0], C_DEEP[1], C_DEEP[2], 0.0]),
        (0.35, [C_CYAN[0], C_CYAN[1], C_CYAN[2], 0.85]),
        (0.85, [C_HOT[0], C_HOT[1], C_HOT[2], 0.95]),
        (1.0, [C_HOT[0], C_HOT[1], C_HOT[2], 0.0]),
    ]),
    "minecraft:particle_appearance_lighting": {},
})

# 4 ── Null Sever release (forward cone blast) ------------------------------
PARTICLES["null_sever_blast"] = effect("aegis:null_sever_blast", {
    "minecraft:emitter_local_space": LOCAL,
    "minecraft:emitter_lifetime_once": {"active_time": 0.35},
    "minecraft:emitter_rate_instant": {"num_particles": 160},
    "minecraft:emitter_shape_custom": {
        "direction": [
            "Math.random(-0.85, 0.85)",
            "Math.random(-0.25, 0.55)",
            "-Math.random(0.45, 1.0)",
        ]
    },
    "minecraft:particle_lifetime_expression": {"max_lifetime": "Math.random(0.45, 1.25)"},
    "minecraft:particle_initial_speed": "Math.random(5.0, 15.0)",
    "minecraft:particle_motion_dynamic": {
        "linear_acceleration": [0, -1.6, 0],
        "linear_drag_coefficient": 3.5,
    },
    "minecraft:particle_motion_collision": {
        "collision_drag": 12.0, "coefficient_of_restitution": 0.15, "collision_radius": 0.25,
    },
    "minecraft:particle_appearance_billboard": billboard(
        "(0.4 + variable.particle_random_1 * 0.55) * (1.0 - variable.particle_age / variable.particle_lifetime * 0.85)",
        "(0.4 + variable.particle_random_1 * 0.55) * (1.0 - variable.particle_age / variable.particle_lifetime * 0.85)", BLOB),
    "minecraft:particle_appearance_tinting": tint([
        (0.0, [C_HOT[0], C_HOT[1], C_HOT[2], 1.0]),
        (0.30, [C_CYAN[0], C_CYAN[1], C_CYAN[2], 0.9]),
        (1.0, [C_VOID[0], C_VOID[1], C_VOID[2], 0.0]),
    ]),
    "minecraft:particle_appearance_lighting": {},
})

# 5 ── guardian aura ring ---------------------------------------------------
PARTICLES["aura_ring"] = effect("aegis:aura_ring", {
    "minecraft:emitter_local_space": {"position": True, "rotation": False, "velocity": False},
    "minecraft:emitter_lifetime_looping": {"active_time": 1.1, "sleep_time": 0.9},
    "minecraft:emitter_rate_steady": {"spawn_rate": 110, "max_particles": 150},
    "minecraft:emitter_shape_disc": {"radius": 2.1, "direction": [0, 1, 0]},
    "minecraft:particle_lifetime_expression": {"max_lifetime": "Math.random(0.9, 1.7)"},
    "minecraft:particle_initial_speed": 0.12,
    "minecraft:particle_motion_dynamic": {"linear_acceleration": [0, 0.55, 0],
                                          "linear_drag_coefficient": 0.6},
    "minecraft:particle_appearance_billboard": billboard(
        "(0.16 + variable.particle_random_1 * 0.12) * (1.0 - variable.particle_age / variable.particle_lifetime * 0.5)",
        "(0.16 + variable.particle_random_1 * 0.12) * (1.0 - variable.particle_age / variable.particle_lifetime * 0.5)", RING),
    "minecraft:particle_appearance_tinting": tint([
        (0.0, [C_CYAN[0], C_CYAN[1], C_CYAN[2], 0.0]),
        (0.25, [C_CYAN[0], C_CYAN[1], C_CYAN[2], 0.55]),
        (1.0, [C_DEEP[0], C_DEEP[1], C_DEEP[2], 0.0]),
    ]),
    "minecraft:particle_appearance_lighting": {},
})

# 6 ── spawn dissolve -------------------------------------------------------
PARTICLES["spawn_dissolve"] = effect("aegis:spawn_dissolve", {
    "minecraft:emitter_local_space": {"position": True, "rotation": False, "velocity": False},
    "minecraft:emitter_lifetime_once": {"active_time": 1.3},
    "minecraft:emitter_rate_steady": {"spawn_rate": 190, "max_particles": 260},
    "minecraft:emitter_shape_entity_aabb": {"direction": [0, 1, 0]},
    "minecraft:particle_lifetime_expression": {"max_lifetime": "Math.random(0.8, 1.9)"},
    "minecraft:particle_initial_speed": "Math.random(0.2, 0.9)",
    "minecraft:particle_motion_dynamic": {"linear_acceleration": [0, 1.15, 0],
                                          "linear_drag_coefficient": 0.9},
    "minecraft:particle_appearance_billboard": billboard(
        "(0.18 + variable.particle_random_1 * 0.18) * (1.0 - variable.particle_age / variable.particle_lifetime * 0.7)",
        "(0.18 + variable.particle_random_1 * 0.18) * (1.0 - variable.particle_age / variable.particle_lifetime * 0.7)", BLOB),
    "minecraft:particle_appearance_tinting": tint([
        (0.0, [C_DEEP[0], C_DEEP[1], C_DEEP[2], 0.0]),
        (0.25, [C_CYAN[0], C_CYAN[1], C_CYAN[2], 0.85]),
        (0.75, [C_HOT[0], C_HOT[1], C_HOT[2], 0.7]),
        (1.0, [C_VOID[0], C_VOID[1], C_VOID[2], 0.0]),
    ]),
    "minecraft:particle_appearance_lighting": {},
})

# 7 ── melee impact ---------------------------------------------------------
PARTICLES["impact_hit"] = effect("aegis:impact_hit", {
    "minecraft:emitter_local_space": LOCAL,
    "minecraft:emitter_lifetime_once": {"active_time": 0.12},
    "minecraft:emitter_rate_instant": {"num_particles": 30},
    "minecraft:emitter_shape_sphere": {"radius": 0.16, "direction": [0, 0, 0]},
    "minecraft:particle_lifetime_expression": {"max_lifetime": "Math.random(0.18, 0.42)"},
    "minecraft:particle_initial_speed": "Math.random(2.5, 7.0)",
    "minecraft:particle_motion_dynamic": {"linear_acceleration": [0, -2.0, 0],
                                          "linear_drag_coefficient": 6.0},
    "minecraft:particle_appearance_billboard": billboard(
        "(0.2 + variable.particle_random_1 * 0.2) * (1.0 - variable.particle_age / variable.particle_lifetime)",
        "(0.2 + variable.particle_random_1 * 0.2) * (1.0 - variable.particle_age / variable.particle_lifetime)", BLOB),
    "minecraft:particle_appearance_tinting": tint([
        (0.0, [C_HOT[0], C_HOT[1], C_HOT[2], 1.0]),
        (0.4, [C_CYAN[0], C_CYAN[1], C_CYAN[2], 0.8]),
        (1.0, [C_DEEP[0], C_DEEP[1], C_DEEP[2], 0.0]),
    ]),
    "minecraft:particle_appearance_lighting": {},
})

# 8 ── void step (teleport puff, used by the script) ------------------------
PARTICLES["void_step"] = effect("aegis:void_step", {
    "minecraft:emitter_local_space": {"position": True, "rotation": False, "velocity": False},
    "minecraft:emitter_lifetime_once": {"active_time": 0.3},
    "minecraft:emitter_rate_instant": {"num_particles": 70},
    "minecraft:emitter_shape_entity_aabb": {"direction": [0, 1, 0]},
    "minecraft:particle_lifetime_expression": {"max_lifetime": "Math.random(0.4, 0.9)"},
    "minecraft:particle_initial_speed": "Math.random(0.4, 1.6)",
    "minecraft:particle_motion_dynamic": {"linear_acceleration": [0, 0.9, 0],
                                          "linear_drag_coefficient": 2.0},
    "minecraft:particle_appearance_billboard": billboard(
        "(0.22 + variable.particle_random_1 * 0.2) * (1.0 - variable.particle_age / variable.particle_lifetime * 0.6)",
        "(0.22 + variable.particle_random_1 * 0.2) * (1.0 - variable.particle_age / variable.particle_lifetime * 0.6)", SMOKE),
    "minecraft:particle_appearance_tinting": tint([
        (0.0, [C_CYAN[0], C_CYAN[1], C_CYAN[2], 0.75]),
        (1.0, [C_VOID[0], C_VOID[1], C_VOID[2], 0.0]),
    ]),
    "minecraft:particle_appearance_lighting": {},
})

# 9 ── death dissolve -------------------------------------------------------
PARTICLES["death_dissolve"] = effect("aegis:death_dissolve", {
    "minecraft:emitter_local_space": {"position": True, "rotation": False, "velocity": False},
    "minecraft:emitter_lifetime_once": {"active_time": 1.9},
    "minecraft:emitter_rate_steady": {"spawn_rate": 170, "max_particles": 240},
    "minecraft:emitter_shape_entity_aabb": {"direction": [0, 1, 0]},
    "minecraft:particle_lifetime_expression": {"max_lifetime": "Math.random(1.1, 2.4)"},
    "minecraft:particle_initial_speed": "Math.random(0.15, 0.7)",
    "minecraft:particle_motion_dynamic": {"linear_acceleration": [0, 0.75, 0],
                                          "linear_drag_coefficient": 0.7},
    "minecraft:particle_appearance_billboard": billboard(
        "(0.2 + variable.particle_random_1 * 0.22) * (1.0 - variable.particle_age / variable.particle_lifetime * 0.65)",
        "(0.2 + variable.particle_random_1 * 0.22) * (1.0 - variable.particle_age / variable.particle_lifetime * 0.65)", BLOB),
    "minecraft:particle_appearance_tinting": tint([
        (0.0, [C_CYAN[0], C_CYAN[1], C_CYAN[2], 0.8]),
        (0.55, [C_DEEP[0], C_DEEP[1], C_DEEP[2], 0.5]),
        (1.0, [C_VOID[0], C_VOID[1], C_VOID[2], 0.0]),
    ]),
    "minecraft:particle_appearance_lighting": {},
})

# 10 ─ overdrive shockwave --------------------------------------------------
PARTICLES["overdrive_burst"] = effect("aegis:overdrive_burst", {
    "minecraft:emitter_local_space": LOCAL,
    "minecraft:emitter_lifetime_once": {"active_time": 0.2},
    "minecraft:emitter_rate_instant": {"num_particles": 110},
    "minecraft:emitter_shape_sphere": {"radius": 0.55, "direction": [0, 0, 0]},
    "minecraft:particle_lifetime_expression": {"max_lifetime": "Math.random(0.35, 0.8)"},
    "minecraft:particle_initial_speed": "Math.random(4.0, 9.0)",
    "minecraft:particle_motion_dynamic": {"linear_acceleration": [0, -0.6, 0],
                                          "linear_drag_coefficient": 5.0},
    "minecraft:particle_appearance_billboard": billboard(
        "(0.3 + variable.particle_random_1 * 0.3) * (1.0 - variable.particle_age / variable.particle_lifetime)",
        "(0.3 + variable.particle_random_1 * 0.3) * (1.0 - variable.particle_age / variable.particle_lifetime)", RING),
    "minecraft:particle_appearance_tinting": tint([
        (0.0, [C_HOT[0], C_HOT[1], C_HOT[2], 0.95]),
        (0.45, [C_CYAN[0], C_CYAN[1], C_CYAN[2], 0.7]),
        (1.0, [C_VOID[0], C_VOID[1], C_VOID[2], 0.0]),
    ]),
    "minecraft:particle_appearance_lighting": {},
})


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, data in PARTICLES.items():
        path = os.path.join(OUT, "%s.json" % name)
        with open(path, "w") as fh:
            json.dump(data, fh, indent=1)
        print("wrote", path)
    print("%d particle effects" % len(PARTICLES))


if __name__ == "__main__":
    main()
