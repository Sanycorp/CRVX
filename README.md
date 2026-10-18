# CRVX — Aegis Primordial: Sentinel of the Null Veil

Production Behavior + Resource Pack for **Minecraft Bedrock 1.21.80+** containing a single
ultra-advanced humanoid guardian (`aegis:primordial_sentinel`) engineered to permanently erase
**The Locust** (Doctor Nowhere / T.O.E. ports, Evolution variants) even when they are immune to
`/kill`, use `damage_sensor: "no"`, or a min-health lock.

**Download:** [`release/Aegis_Primordial.mcaddon`](release/Aegis_Primordial.mcaddon) · usage: [`README.txt`](README.txt)

## Layout
| Path | Contents |
|---|---|
| `Aegis_Primordial_BP/` | manifest (script module, `@minecraft/server` 2.0.0), entity (3 synced properties, 10 component groups, 14 events), Aegis Core item with custom component, BP animation controller + command timelines, functions, lang |
| `Aegis_Primordial_BP/scripts/main.js` | the kill-immunity bypass: Locust classification, proximity scan, Null Sever cinematic, blink, aura, auto-deploy, scoreboard, `/scriptevent` API |
| `Aegis_Primordial_RP/` | 34-bone humanoid geometry with per-face UV (512 px atlas, 4 texels/unit) + emissive-alpha textures (guard + overdrive), 11 animations, 4 animation controllers, Molang-driven glow render controller, 17 particle effects, 20 OGG sound events incl. 5 voice lines |
| `tools/` | reproducible asset pipeline: `build_model.py` (geo + textures), `build_sounds.py` (procedural SFX + VO processing), `validate.py` (cross-reference validator), `test_script.mjs` (mock-runtime test of the nullify logic), `build_addon.py` (all of the above + packaging) |

## Build
```bash
pip install pillow numpy soundfile
python3 tools/build_addon.py        # regenerates assets, validates, tests, writes release/*.mcaddon
```

## Why it beats invulnerable Locusts
Invulnerability in those ports lives in the *damage* pipeline. The Aegis never relies on it:
on hit, on contact, and on Null Sever release the script calls `Entity.remove()` — a world-level
despawn that ignores health, `damage_sensor` and `/kill` rules — after first attempting
override-cause damage and forced despawn events. See `README.txt` for the full layer list.
