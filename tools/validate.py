#!/usr/bin/env python3
"""Static cross-reference validator for the Aegis Primordial add-on."""
import json, os, re, sys, glob

ROOT = os.path.join(os.path.dirname(__file__), "..")
BP = os.path.join(ROOT, "Aegis_Primordial_BP")
RP = os.path.join(ROOT, "Aegis_Primordial_RP")
errors, warnings = [], []


def J(p):
    with open(p) as f:
        return json.load(f)


# 1. every json parses
for p in glob.glob(os.path.join(ROOT, "Aegis_Primordial_*", "**", "*.json"), recursive=True):
    try:
        J(p)
    except Exception as e:
        errors.append(f"JSON parse error {p}: {e}")

bp_m, rp_m = J(os.path.join(BP, "manifest.json")), J(os.path.join(RP, "manifest.json"))
if not any(d.get("uuid") == rp_m["header"]["uuid"] for d in bp_m["dependencies"]):
    errors.append("BP does not depend on RP uuid")
if rp_m["dependencies"][0]["uuid"] != bp_m["header"]["uuid"]:
    errors.append("RP does not depend on BP uuid")

ent = J(os.path.join(BP, "entities/aegis_primordial.json"))["minecraft:entity"]
cli = J(os.path.join(RP, "entity/aegis_primordial.entity.json"))["minecraft:client_entity"]["description"]
if ent["description"]["identifier"] != cli["identifier"]:
    errors.append("identifier mismatch BP/RP")

# 2. BP events referenced exist
events = set(ent["events"].keys())
txt = json.dumps(ent)
for ev in set(re.findall(r'"event":\s*"(aegis:[a-z_]+)"', txt)):
    if ev not in events:
        errors.append(f"BP references undefined event {ev}")
# component groups referenced exist
groups = set(ent["component_groups"].keys())
for g in set(re.findall(r'"(aegis:[a-z_]+)"', json.dumps(ent["events"]))):
    if g not in groups and g not in events and g not in ("aegis:state", "aegis:glow", "aegis:erased"):
        errors.append(f"event references undefined component group {g}")

# 3. BP animations/controllers linked
bp_ac = J(os.path.join(BP, "animation_controllers/aegis_primordial.ac.json"))["animation_controllers"]
bp_an = J(os.path.join(BP, "animations/aegis_primordial.bp.animation.json"))["animations"]
for k, v in ent["description"]["animations"].items():
    if v not in bp_ac and v not in bp_an:
        errors.append(f"BP animation '{k}' -> {v} not found")
for st in bp_ac["controller.animation.aegis_primordial.bp_state"]["states"].values():
    for a in st.get("animations", []):
        if a not in ent["description"]["animations"]:
            errors.append(f"BP controller uses unknown short name {a}")

# 4. RP animations/controllers linked
rp_ac = J(os.path.join(RP, "animation_controllers/aegis_primordial.ac.json"))["animation_controllers"]
rp_an = J(os.path.join(RP, "animations/aegis_primordial.animation.json"))["animations"]
for k, v in cli["animations"].items():
    if v not in rp_ac and v not in rp_an:
        errors.append(f"RP animation '{k}' -> {v} not found")
for cname, c in rp_ac.items():
    for st in c["states"].values():
        for a in st.get("animations", []):
            name = a if isinstance(a, str) else list(a.keys())[0]
            if name not in cli["animations"]:
                errors.append(f"RP controller {cname} uses unknown short name {name}")
for a in cli["scripts"]["animate"]:
    name = a if isinstance(a, str) else list(a.keys())[0]
    if name not in cli["animations"]:
        errors.append(f"client animate uses unknown {name}")

# 5. bones referenced in animations exist in geometry
geo = J(os.path.join(RP, "models/entity/aegis_primordial.geo.json"))["minecraft:geometry"][0]
bones = {b["name"] for b in geo["bones"]}
parents = {b.get("parent") for b in geo["bones"] if b.get("parent")}
for p in parents - bones:
    errors.append(f"geometry parent {p} missing")
for an, a in rp_an.items():
    for b in a.get("bones", {}):
        if b not in bones:
            errors.append(f"animation {an} animates missing bone {b}")
if geo["description"]["identifier"] != cli["geometry"]["default"]:
    errors.append("geometry id mismatch")

# 6. textures exist
for k, v in cli["textures"].items():
    if not os.path.exists(os.path.join(RP, v + ".png")):
        errors.append(f"texture {v}.png missing")

# 7. particles referenced anywhere exist
particles = {}
for p in glob.glob(os.path.join(RP, "particles/*.json")):
    pj = J(p)
    particles[pj["particle_effect"]["description"]["identifier"]] = p
    tex = pj["particle_effect"]["description"]["basic_render_parameters"]["texture"]
    if not os.path.exists(os.path.join(RP, tex + ".png")):
        errors.append(f"particle texture {tex} missing")
alltext = ""
for p in glob.glob(os.path.join(ROOT, "Aegis_Primordial_*", "**", "*.*"), recursive=True):
    if p.endswith((".json", ".js", ".mcfunction")):
        alltext += open(p, errors="ignore").read()
for pid in set(re.findall(r'aegis:[a-z_]+', alltext)):
    pass
for pid in set(re.findall(r'(?:particle |spawnParticle\(")(aegis:[a-z_]+)', alltext)):
    if pid not in particles:
        errors.append(f"particle {pid} referenced but not defined")
for pid in set(re.findall(r'"(aegis:[a-z_]+)"', json.dumps(cli.get("particle_effects", {})))):
    if pid not in particles:
        errors.append(f"client particle_effects {pid} not defined")

# 8. sounds referenced exist
sd = J(os.path.join(RP, "sounds/sound_definitions.json"))["sound_definitions"]
for ev, d in sd.items():
    for s in d["sounds"]:
        if not os.path.exists(os.path.join(RP, s["name"] + ".ogg")):
            errors.append(f"sound file {s['name']}.ogg missing")
for sid in set(re.findall(r'(?:playsound |playSound\(")(aegis\.[a-z_.]+)', alltext)):
    if sid not in sd:
        errors.append(f"sound event {sid} referenced but not defined")
sj = J(os.path.join(RP, "sounds.json"))
for e in sj["entity_sounds"]["entities"]["aegis:primordial_sentinel"]["events"].values():
    if e["sound"] not in sd:
        errors.append(f"sounds.json uses undefined {e['sound']}")

# 9. item texture + custom component
item = J(os.path.join(BP, "items/aegis_core.json"))["minecraft:item"]
it = J(os.path.join(RP, "textures/item_texture.json"))["texture_data"]
if item["components"]["minecraft:icon"] not in it:
    errors.append("item icon not in item_texture.json")
js = open(os.path.join(BP, "scripts/main.js")).read()
for comp in item["components"].get("minecraft:custom_components", []):
    if f'registerCustomComponent("{comp}"' not in js:
        errors.append(f"custom component {comp} not registered in script")

# 10. lang keys
lang = open(os.path.join(RP, "texts/en_US.lang")).read()
for key in ("entity.aegis:primordial_sentinel.name", "item.aegis:aegis_core.name", "item.spawn_egg.entity.aegis:primordial_sentinel.name"):
    if key not in lang:
        errors.append(f"lang key {key} missing")

print(f"particles: {len(particles)}, sound events: {len(sd)}, bones: {len(bones)}, rp animations: {len(rp_an)}, rp controllers: {len(rp_ac)}")
for w in warnings:
    print("WARN", w)
for e in errors:
    print("ERROR", e)
print("VALIDATION", "FAILED" if errors else "PASSED")
sys.exit(1 if errors else 0)
