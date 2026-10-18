#!/usr/bin/env python3
"""
AEGIS-PRIMORDIAL :: pack validator
==================================
Runs the Phase-9 checklist mechanically. Catches every "invisible entity" /
"broken attack" failure mode before the pack is zipped:

  * JSON syntax of every file
  * manifest cross-references (BP -> RP uuid, script entry exists)
  * client entity -> geometry / texture / material / render controller wiring
  * atlas rectangles inside the texture, all six faces present
  * every bone animated by an animation exists in the geometry
  * every particle / sound referenced by an animation or controller exists
  * every ogg referenced by sound_definitions.json exists
  * every BP event the script triggers actually exists on the entity
  * loot table exists, lang keys present, textures power-of-two
  * main.js parses as an ES module (node --check)

Exit code 0 = all checks green.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BP = os.path.join(ROOT, "Aegis_Null_Veil_BP")
RP = os.path.join(ROOT, "Aegis_Null_Veil_RP")

FACES = ["north", "east", "south", "west", "up", "down"]

ok, warn, fail = [], [], []


def OK(msg):
    ok.append(msg)
    print("  [ok]   " + msg)


def WARN(msg):
    warn.append(msg)
    print("  [warn] " + msg)


def FAIL(msg):
    fail.append(msg)
    print("  [FAIL] " + msg)


def check(cond, msg, warn_only=False):
    if cond:
        OK(msg)
    else:
        (WARN if warn_only else FAIL)(msg)
    return cond


def load(path):
    with open(path) as fh:
        return json.load(fh)


def all_json(base):
    out = []
    for dirpath, _, files in os.walk(base):
        for f in files:
            if f.endswith(".json"):
                out.append(os.path.join(dirpath, f))
    return sorted(out)


def is_pot(n):
    return n > 0 and (n & (n - 1)) == 0


# ------------------------------------------------------------------ 1. JSON
print("\n== 1. JSON syntax ==")
bp_json, rp_json = {}, {}
bad = 0
for base, store in ((BP, bp_json), (RP, rp_json)):
    for p in all_json(base):
        rel = os.path.relpath(p, ROOT)
        try:
            store[rel] = load(p)
        except Exception as e:
            bad += 1
            FAIL("%s : %s" % (rel, e))
check(bad == 0, "all %d JSON files parse" % (len(bp_json) + len(rp_json)))

# -------------------------------------------------------------- 2. manifests
print("\n== 2. Manifests ==")
bpm = bp_json.get("Aegis_Null_Veil_BP/manifest.json")
rpm = rp_json.get("Aegis_Null_Veil_RP/manifest.json")
if not check(bpm is not None, "behavior manifest present"):
    sys.exit(1)
if not check(rpm is not None, "resource manifest present"):
    sys.exit(1)

bp_uuid = bpm["header"]["uuid"]
rp_uuid = rpm["header"]["uuid"]
check(re.match(r"^[0-9a-fA-F-]{36}$", bp_uuid) is not None, "BP header uuid well formed")
check(re.match(r"^[0-9a-fA-F-]{36}$", rp_uuid) is not None, "RP header uuid well formed")
check(bp_uuid != rp_uuid, "BP and RP have distinct uuids")
deps = [d.get("uuid") for d in bpm.get("dependencies", [])]
check(rp_uuid in deps, "BP depends on the RP uuid")
mods = {m["type"]: m for m in bpm.get("modules", [])}
check("data" in mods, "BP has a data module")
check("script" in mods, "BP has a script module")
if "script" in mods:
    entry = mods["script"].get("entry", "")
    check(os.path.exists(os.path.join(BP, entry)),
          "script entry '%s' exists" % entry)
    check(mods["script"].get("language") == "javascript", "script module language is javascript")
srv = [d for d in bpm.get("dependencies", []) if d.get("module_name") == "@minecraft/server"]
check(len(srv) == 1, "declares exactly one @minecraft/server dependency")
if srv:
    print("         -> @minecraft/server %s" % srv[0].get("version"))
check(len([m for m in rpm.get("modules", []) if m["type"] == "resources"]) == 1,
      "RP has a resources module")
for m, label in ((bpm, "BP"), (rpm, "RP")):
    check(os.path.exists(os.path.join(BP if label == "BP" else RP, "pack_icon.png")),
          "%s pack_icon.png present" % label)

# ------------------------------------------------------------ 3. BP entity
print("\n== 3. Behavior entity ==")
bpent = bp_json.get("Aegis_Null_Veil_BP/entities/aegis_primordial.json")
if not check(bpent is not None, "BP entity file present"):
    sys.exit(1)
ent = bpent["minecraft:entity"]
ident = ent["description"]["identifier"]
OK("entity identifier: " + ident)
check(ent["description"].get("is_summonable") is True, "is_summonable")
check(ent["description"].get("is_spawnable") is True, "is_spawnable")
comps = ent.get("components", {})
check("minecraft:collision_box" in comps, "has minecraft:collision_box")
cb = comps.get("minecraft:collision_box", {})
check(0.4 <= cb.get("width", 0) <= 1.2 and 1.6 <= cb.get("height", 0) <= 2.4,
      "collision box is human sized (%s x %s)" % (cb.get("width"), cb.get("height")))
check("minecraft:health" in comps, "has health")
check(comps.get("minecraft:fire_immune") is True, "fire immune")
check("minecraft:damage_sensor" in comps, "has damage_sensor (self protection)")
ds = comps.get("minecraft:damage_sensor", {}).get("triggers", [])
check(not any(t.get("deals_damage") == "no" and t.get("cause") == "all" for t in ds),
      "damage_sensor is not making it invulnerable")
check("minecraft:behavior.melee_attack" in comps, "has melee attack behaviour")
check("minecraft:behavior.nearest_attackable_target" in comps, "has target acquisition")
check(any("locust" in json.dumps(t).lower()
          for t in comps.get("minecraft:behavior.nearest_attackable_target", {})
          .get("entity_types", [])), "target filter mentions locust families")
props = ent["description"].get("properties", {})
check("aegis:mode" in props and props["aegis:mode"].get("client_sync") is True,
      "aegis:mode property is client synced")
check("aegis:attack" in props and props["aegis:attack"].get("client_sync") is True,
      "aegis:attack property is client synced")
for name, p in props.items():
    if p.get("type") == "int":
        rng = p.get("range")
        check(isinstance(rng, list) and len(rng) == 2, "int property %s has a range" % name)
events = ent.get("events", {})
needed = ["aegis:enter_combat", "aegis:return_guard", "aegis:overdrive_enter",
          "aegis:overdrive_hold", "aegis:null_sever_charge", "aegis:null_sever_release",
          "aegis:attack_punch", "aegis:attack_slash", "aegis:attack_clear",
          "aegis:force_nullify_target", "aegis:void_step", "aegis:spawn"]
for e in needed:
    check(e in events, "event '%s' declared" % e)
lt = comps.get("minecraft:loot", {}).get("table")
check(lt is None or os.path.exists(os.path.join(BP, lt)), "loot table '%s' exists" % lt)

# ------------------------------------------------------- 4. client entity
print("\n== 4. Client entity (visibility critical) ==")
ce = rp_json.get("Aegis_Null_Veil_RP/entity/aegis_primordial.entity.json")
if not check(ce is not None, "client entity file present"):
    sys.exit(1)
d = ce["minecraft:client_entity"]["description"]
check(d.get("identifier") == ident, "client identifier matches BP (%s)" % ident)

geo_key = d.get("geometry", {}).get("default")
check(geo_key is not None, "geometry.default set: %s" % geo_key)
mats = d.get("materials", {})
check(mats.get("default") in ("entity_alphatest", "entity_emissive_alpha", "entity_emissive"),
      "default material is emissive/alphatest capable: %s" % mats.get("default"))
texs = d.get("textures", {})
check("default" in texs, "texture.default set")
for key, path in texs.items():
    p = os.path.join(RP, path + ".png")
    check(os.path.exists(p), "texture file for '%s' exists (%s.png)" % (key, path))

rcl = d.get("render_controllers", [])
check(len(rcl) > 0, "render controllers referenced: %s" % rcl)

# ------------------------------------------------------------ 5. geometry
print("\n== 5. Geometry ==")
geo_files = [v for k, v in rp_json.items() if k.startswith("Aegis_Null_Veil_RP/models/entity/")]
found = None
for g in geo_files:
    for gg in g.get("minecraft:geometry", []):
        if gg["description"]["identifier"] == geo_key:
            found = gg
if not check(found is not None, "geometry '%s' defined in the RP" % geo_key):
    sys.exit(1)
desc = found["description"]
TW, TH = desc.get("texture_width"), desc.get("texture_height")
check(is_pot(TW) and is_pot(TH), "geometry texture size is power of two (%sx%s)" % (TW, TH))
bones = found["bones"]
names = [b["name"] for b in bones]
check(len(names) == len(set(names)), "no duplicate bone names")
check(len(bones) >= 25, "bone count = %d (target >= 25)" % len(bones))
bone_by_name = {b["name"]: b for b in bones}
for b in bones:
    if b.get("parent"):
        check(b["parent"] in bone_by_name, "parent '%s' of '%s' exists" % (b["parent"], b["name"]))

cubes = 0
oob = 0
missing_face = 0
for b in bones:
    for c in b.get("cubes", []):
        cubes += 1
        uv = c.get("uv")
        if not isinstance(uv, dict) or any(f not in uv for f in FACES):
            missing_face += 1
            continue
        for f in FACES:
            x, y = uv[f]["uv"]
            w, h = uv[f]["uv_size"]
            if x < 0 or y < 0 or x + w > TW or y + h > TH or w <= 0 or h <= 0:
                oob += 1
check(missing_face == 0, "every cube has all six per-face UVs")
check(oob == 0, "all %d cube faces map inside the %dx%d atlas" % (cubes * 6, TW, TH))
check(cubes >= 40, "cube count = %d" % cubes)

# model height
ymax = 0
for b in bones:
    for c in b.get("cubes", []):
        ymax = max(ymax, c["origin"][1] + c["size"][1])
check(1.75 <= ymax / 16.0 <= 2.15, "model height = %.2f blocks" % (ymax / 16.0))

# --------------------------------------------------------- 6. render ctrls
print("\n== 6. Render controllers ==")
rcs = {}
for k, v in rp_json.items():
    if "render_controllers/" in k:
        rcs.update(v.get("render_controllers", {}))
for name in rcl:
    if isinstance(name, str):
        check(name in rcs, "render controller '%s' defined" % name)
        rc = rcs.get(name, {})
        check("geometry" in rc, "  -> declares geometry")
        check("materials" in rc, "  -> declares materials")

# --------------------------------------------------------- 7. animations
print("\n== 7. Animations ==")
anims = {}
for k, v in rp_json.items():
    if k.startswith("Aegis_Null_Veil_RP/animations/"):
        anims.update(v.get("animations", {}))
ctrl = {}
for k, v in rp_json.items():
    if k.startswith("Aegis_Null_Veil_RP/animation_controllers/"):
        ctrl.update(v.get("animation_controllers", {}))

declared = d.get("animations", {})
for short, full in declared.items():
    check(full in anims, "animation '%s' -> %s exists" % (short, full))

controllers = d.get("animation_controllers", [])
for c in controllers:
    for slot, full in c.items():
        check(full in ctrl, "animation controller '%s' -> %s exists" % (slot, full))

# bones used by animations must exist
missing_bones = set()
for name, a in anims.items():
    for b in (a.get("bones") or {}):
        if b not in bone_by_name:
            missing_bones.add((name, b))
check(not missing_bones, "all animated bones exist in the geometry",
      warn_only=False) if not missing_bones else FAIL(
          "animated bones missing: %s" % sorted(missing_bones))

# controllers referenced must exist + their animations declared
for full, c in ctrl.items():
    states = c.get("states", {})
    check(c.get("initial_state") in states,
          "controller '%s' initial_state is a real state" % full)
    for sname, st in states.items():
        for a in st.get("animations", []):
            if isinstance(a, str):
                check(a in declared, "  '%s' state '%s' uses declared animation '%s'"
                      % (full, sname, a))
        for tr in st.get("transitions", []):
            for target in tr:
                check(target in states, "  '%s' transition target '%s' exists" % (full, target))

# attack animations must actually move bones (no static T-poses)
for short in ["attack_punch", "attack_slash", "null_sever_charge", "null_sever_release",
              "overdrive_enter", "spawn", "death", "idle", "move"]:
    full = declared.get(short)
    if not full or full not in anims:
        continue
    rot_bones = anims[full].get("bones", {})
    moved = [b for b, v in rot_bones.items()
             if "rotation" in v or "position" in v or "scale" in v]
    check(len(moved) >= 6, "'%s' animates %d bones" % (short, len(moved)))
    if short in ("attack_punch", "attack_slash", "null_sever_release"):
        check(any("arm" in b for b in moved), "'%s' moves at least one arm" % short)

# ---------------------------------------------------------- 8. particles
print("\n== 8. Particles ==")
particles = set()
for k, v in rp_json.items():
    if k.startswith("Aegis_Null_Veil_RP/particles/"):
        pid = v["particle_effect"]["description"]["identifier"]
        particles.add(pid)
        comp = v["particle_effect"]["components"]
        check(any(c.startswith("minecraft:emitter_rate") for c in comp),
              "%s has an emitter rate component" % pid, warn_only=False)
        check(any(c.startswith("minecraft:emitter_lifetime") for c in comp),
              "%s has an emitter lifetime component" % pid, warn_only=False)
        check(any(c.startswith("minecraft:emitter_shape") for c in comp),
              "%s has an emitter shape component" % pid, warn_only=False)
        check("minecraft:particle_appearance_billboard" in comp,
              "%s has a billboard component" % pid, warn_only=False)
        uv = comp.get("minecraft:particle_appearance_billboard", {}).get("uv", {})
        if uv:
            x, y = uv.get("uv", [0, 0])
            w, h = uv.get("uv_size", [8, 8])
            check(0 <= x and 0 <= y and x + w <= uv.get("texture_width", 128)
                  and y + h <= uv.get("texture_height", 128),
                  "%s UV inside the vanilla atlas" % pid, warn_only=False)

mapped_particles = set(d.get("particle_effects", {}).values())
for p in mapped_particles:
    check(p in particles, "client entity particle '%s' defined" % p)

used_particles = set()
for name, a in anims.items():
    for _, ev in (a.get("particle_effects") or {}).items():
        used_particles.add(ev.get("effect"))
for eff in used_particles:
    check(eff in d.get("particle_effects", {}),
          "animation particle key '%s' mapped in the client entity" % eff)

# locators used by particle effects must exist
locators = set()
for b in bones:
    for l in (b.get("locators") or {}):
        locators.add(l)
for name, a in anims.items():
    for _, ev in (a.get("particle_effects") or {}).items():
        if ev.get("locator") and ev["locator"] not in locators:
            FAIL("animation '%s' uses unknown locator '%s'" % (name, ev["locator"]))
OK("locators referenced by animations exist: %s" % sorted(locators))

# ------------------------------------------------------------- 9. sounds
print("\n== 9. Sounds ==")
sd = rp_json.get("Aegis_Null_Veil_RP/sounds/sound_definitions.json", {})
defs = sd.get("sound_definitions", {})
check(len(defs) > 0, "sound_definitions.json has %d events" % len(defs))
missing_files = []
for ev, body in defs.items():
    for s in body.get("sounds", []):
        p = os.path.join(RP, s["name"] + ".ogg")
        if not os.path.exists(p):
            missing_files.append(s["name"] + ".ogg")
check(not missing_files, "every referenced ogg exists")
if missing_files:
    FAIL("missing: %s" % missing_files)
mapped_sounds = set(d.get("sound_effects", {}).values())
for ev in mapped_sounds:
    check(ev in defs, "client sound mapping '%s' defined" % ev)
used_sounds = set()
for name, a in anims.items():
    for _, ev in (a.get("sound_effects") or {}).items():
        used_sounds.add(ev.get("effect"))
for eff in used_sounds:
    check(eff in d.get("sound_effects", {}),
          "animation sound key '%s' mapped in the client entity" % eff)
ogg_count = len([f for f in os.listdir(os.path.join(RP, "sounds", "aegis"))
                 if f.endswith(".ogg")])
bytes_total = sum(os.path.getsize(os.path.join(RP, "sounds", "aegis", f))
                  for f in os.listdir(os.path.join(RP, "sounds", "aegis"))
                  if f.endswith(".ogg"))
check(ogg_count >= 25, "%d ogg files in the sound bank (%.2f MB)"
      % (ogg_count, bytes_total / 1048576.0))
check(len([f for f in os.listdir(os.path.join(RP, "sounds", "aegis"))
           if f.startswith("voice_")]) >= 7, "at least 7 voice lines present")

# ----------------------------------------------------------- 10. textures
print("\n== 10. Textures ==")
try:
    from PIL import Image
    for rel in ["textures/entity/aegis_primordial.png",
                "textures/entity/aegis_primordial_emissive.png",
                "textures/items/aegis_spawn_egg.png"]:
        p = os.path.join(RP, rel)
        im = Image.open(p)
        check(is_pot(im.width) and is_pot(im.height),
              "%s is %dx%d (power of two)" % (rel.split("/")[-1], im.width, im.height))
    b = Image.open(os.path.join(RP, "textures/entity/aegis_primordial.png"))
    e = Image.open(os.path.join(RP, "textures/entity/aegis_primordial_emissive.png"))
    check((b.width, b.height) == (e.width, e.height),
          "base and emissive atlases are the same size")
    check(b.width >= 512, "entity atlas is %dpx (>= 512 as specified)" % b.width)
    # emissive must not be blank and must not be fully white
    import numpy as np
    ea = np.asarray(e.convert("RGB"), dtype=np.float32).mean()
    check(2 < ea < 120, "emissive map has glow but is not blown out (mean %.1f)" % ea)
    ba = np.asarray(b.convert("RGB"), dtype=np.float32).mean()
    check(ba > 20, "base texture is not a black blob (mean %.1f)" % ba)
except ImportError:
    WARN("Pillow not installed - skipping pixel checks")

it = rp_json.get("Aegis_Null_Veil_RP/textures/item_texture.json")
check(it is not None, "item_texture.json present")
if it and "texture" in d.get("spawn_egg", {}):
    key = d["spawn_egg"]["texture"]
    check(key in it.get("texture_data", {}), "spawn egg texture '%s' registered" % key)

# -------------------------------------------------------------- 11. lang
print("\n== 11. Language files ==")
for pack, label in ((BP, "BP"), (RP, "RP")):
    p = os.path.join(pack, "texts", "en_US.lang")
    if not check(os.path.exists(p), "%s en_US.lang present" % label):
        continue
    content = open(p).read()
    check(("entity.%s.name" % ident) in content,
          "%s defines the entity display name" % label)
check("item.spawn_egg.entity.%s.name" % ident in
      open(os.path.join(RP, "texts", "en_US.lang")).read(),
      "spawn egg display name defined")

# ------------------------------------------------------------- 12. script
print("\n== 12. Script API ==")
script = os.path.join(BP, "scripts", "main.js")
check(os.path.exists(script), "scripts/main.js present")
if os.path.exists(script):
    src = open(script).read()
    check('import { world, system } from "@minecraft/server"' in src,
          "imports @minecraft/server")
    check("remove()" in src, "calls Entity.remove() (the Locust eraser)")
    check("locust" in src.lower(), "contains locust detection keywords")
    check("aegis_nullified" in src, "tags erased entities")
    # every "aegis:*" string in the script must either be an entity event or a
    # /scriptevent command the handler implements
    script_cmds = {"aegis:summon", "aegis:purge", "aegis:scan",
                   "aegis:status", "aegis:config", "aegis:help"}
    # explicit triggerEvent(...) calls, plus the aegis:* event name tables
    triggered = set(re.findall(r'triggerEvent\("([^"]+)"\)', src))
    for block in re.findall(r'\[\s*((?:"aegis:[^"]*"\s*,?\s*)+)\]', src):
        triggered |= set(re.findall(r'"(aegis:[^"]+)"', block))
    # identifiers that only look like events
    triggered -= {"aegis:mode", "aegis:attack", "aegis:primordial_sentinel"}
    for ev in sorted(triggered):
        check(ev in events, "script event '%s' exists on the entity" % ev)
    handled = set(re.findall(r'case "([a-z_]+)":', src))
    for c in sorted(script_cmds):
        check(c.split(":", 1)[1] in handled,
              "/scriptevent command '%s' is implemented" % c)
    # node syntax check as an ES module
    node = shutil.which("node")
    if node:
        tmp = tempfile.mkdtemp()
        mjs = os.path.join(tmp, "main.mjs")
        shutil.copy(script, mjs)
        r = subprocess.run([node, "--check", mjs], capture_output=True, text=True)
        check(r.returncode == 0, "main.js parses as an ES module")
        if r.returncode != 0:
            print(r.stderr[:1200])
    else:
        WARN("node not available - skipping JS syntax check")

# ------------------------------------------------------------ 13. dangling
print("\n== 13. Cross references ==")
# every ogg in the folder is referenced somewhere
folder = set("sounds/aegis/" + f[:-4] for f in os.listdir(os.path.join(RP, "sounds", "aegis"))
             if f.endswith(".ogg"))
referenced = set()
for ev, body in defs.items():
    for s in body.get("sounds", []):
        referenced.add(s["name"])
orphans = folder - referenced
check(not orphans, "no orphaned ogg files", warn_only=True)
if orphans:
    print("         orphans: %s" % sorted(orphans))

# script-referenced sound events exist
for ev in sorted(set(re.findall(r'"(aegis\.[a-z_.]+)"', open(script).read()))):
    if ev not in defs:
        FAIL("script plays undefined sound event '%s'" % ev)
OK("all sound events played by the script are defined")

# ------------------------------------------------------------------ report
print("\n" + "=" * 66)
print("  PASS %d   WARN %d   FAIL %d" % (len(ok), len(warn), len(fail)))
print("=" * 66)
if fail:
    print("\nFailures:")
    for f in fail:
        print("  - " + f)
sys.exit(1 if fail else 0)
