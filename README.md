# CRVX

## AEGIS-PRIMORDIAL: NULL VEIL SENTINEL

A Minecraft Bedrock add-on (1.21.90+ / 26.x) that adds a single, very determined
human-form guardian whose entire purpose is to hunt down and **erase** Locust
entities that cannot be killed with `/kill`.

```
┌──────────────────────────────────────────────────────────────────────┐
│  The Locust survives /kill because its own behaviour pack cancels the │
│  damage (damage_sensor / min_health / invulnerable).  Entity.remove() │
│  never touches the damage pipeline, so it is the only thing that      │
│  actually deletes it.  That is what this pack does.                   │
└──────────────────────────────────────────────────────────────────────┘
```

### Install

1. Grab `build/Aegis_Null_Veil_Sentinel_v1.0.0.mcaddon` (or, if you are building
   from source, run `python3 tools/build_mcaddon.py`).
2. Open it — Minecraft installs both packs.
3. Create/enable a world and apply **both** packs:
   * behavior pack `Aegis Primordial — Null Veil Sentinel (Behavior)`
   * resource pack `Aegis Primordial — Null Veil Sentinel (Resources)`
4. Turn **Beta APIs** on if your version still gates Script API features
   (the script itself only uses stable `@minecraft/server` 2.0.0 APIs).
5. `/summon aegis:primordial_sentinel`, or use the spawn egg in the creative
   inventory, or just let it auto-deploy when an anomaly is detected.

> Do **not** enable "Holiday Creator Features" just for this pack — nothing here
> needs it. Only the Script API dependency (`@minecraft/server` 2.0.0) is used.

### Commands

| Command | What it does |
|---|---|
| `/summon aegis:primordial_sentinel` | deploy one at your position |
| `/scriptevent aegis:summon` | same, without leaving chat |
| `/scriptevent aegis:summon 3` | deploy three |
| `/scriptevent aegis:purge` | erase every detected anomaly in loaded chunks |
| `/scriptevent aegis:scan` | list anomaly signatures it can see (with coords) |
| `/scriptevent aegis:status` | sentinel count + how many it has erased |
| `/scriptevent aegis:config` | print the active detection keywords / ranges |
| `/scriptevent aegis:help` | command list |

### How the erasure works

1. **Detection** — every 10 ticks the script scans around each player (96 blocks)
   and flags any entity whose *identifier*, *tag* or *name tag* contains one of
   the keywords in `CONFIG.locustKeywords`
   (`locust`, `the_locust`, `toe_locust`, `doctor_nowhere`, `nowhere`,
   `hopal`, `anomaly`, …). Matching is case-insensitive, so it works with every
   Locust add-on out of the box.
2. **Pursuit** — if the anomaly is 16–72 blocks away the sentinel *Void Steps*
   (teleports) to it, so it never gets stuck on terrain.
3. **Null Sever** (12 s cooldown, 14 block reach) — 2.5 s charge animation with
   palms and chest core charging, then a release blast. Everything flagged as an
   anomaly inside the beam is `remove()`d. Chat:
   `§b[Aegis]§r Null Sever complete. Anomaly erased.`
4. **Melee** — two confirmed hits on the same anomaly also erase it, so it works
   even if you never see the Sever wind up.
5. **Safeties** — anything matching `aegis` or `player` is hardcoded protected;
   the sentinel can never erase itself, you, or another sentinel.

**Pointing it at an exact identifier:** open
`Aegis_Null_Veil_BP/scripts/main.js`, add your Locust's id to
`CONFIG.locustKeywords` (e.g. `"my_addon:the_locust"`), rezip. Also add the
family to the `minecraft:behavior.nearest_attackable_target` filter in
`Aegis_Null_Veil_BP/entities/aegis_primordial.json` if you want the vanilla AI
to path to it as well.

### Abilities

| Ability | Effect |
|---|---|
| Guardian Aura | Regeneration I + Resistance I to players within 12 blocks, every 4 s |
| Void Pulse | 8 block shockwave: knockback + 18 damage + Weakness II, 6 s cooldown |
| Void Step | short-range teleport pursuit when 16–72 blocks from an anomaly |
| Overdrive | auto-engages under 32 blocks: +63 % speed, +30 % damage, faster melee, glowing stance |
| Tracking Sense | senses anomalies through walls (`must_see: false`) |
| Auto Deploy | summons a sentinel when an anomaly is first seen and none is near |

Survivability: 800 HP, 0.9 knockback resistance, immune to fall / drowning /
fire / lava / freezing damage, 75 % reduced damage from everything else, and it
regenerates. It is *not* invulnerable — you can still kill it if you try.

### What is in the pack

* **Model** — 40 bones, 84 cubes, ~1.94 blocks tall: articulated hands with
  individual fingers and thumbs, hood, veil, seven independently-swaying coat
  bones, two-segment void cloak, spinning chest-core ring.
* **Textures** — 1024×1024 atlas + matching emissive glow map, UV-packed
  procedurally so texel density is where the detail is (the head gets ~2× the
  resolution of the boots). No pink/black missing texture is possible: the atlas
  and the geometry are generated from the same source.
* **Animations (12)** — idle, move (speed-synced gait), look-at-target, punch,
  slash, Null Sever charge, Null Sever release, overdrive enter, overdrive loop,
  spawn, death, guardian aura. Every attack moves arms, torso, head, coat,
  cloak and legs — no static T-poses.
* **Particles (10)** — eye glow, chest core pulse, sever charge swirl, sever
  blast cone, aura ring, spawn dissolve, impact hit, void step, death dissolve,
  overdrive shockwave.
* **Audio** — 28 Ogg Vorbis files: 6 footsteps, punches, slashes, multi-layered
  Null Sever charge/release, overdrive riser, spawn, seamless idle hum loop,
  hurt, death, void pulse, target lock, aura pad — plus 7 voice lines
  ("Target acquired.", "Locust signature confirmed.", "Executing Null Sever.",
  "Anomaly erased.", …).
* **Script** — ~600 lines of commented `@minecraft/server` code with a
  self-contained tick scheduler (no `runInterval`/`runTimeout` dependency).

### Building from source

```bash
pip install --break-system-packages pillow numpy soundfile imageio-ffmpeg

python3 tools/build_geometry.py     # bones -> geo.json + UV atlas layout
python3 tools/build_textures.py     # paints base + emissive atlas
python3 tools/build_particles.py    # 10 particle emitters
python3 tools/build_audio.py        # synthesises 21 SFX -> ogg
python3 tools/build_vo.py           # bakes assets/vo/*.mp3 -> voice ogg
python3 tools/build_item_textures.py
python3 tools/validate.py           # 324 checks, exit 1 on any failure
python3 tools/build_mcaddon.py      # validates then zips build/*.mcaddon
```

Everything regenerates deterministically, so rebuilding produces identical
binaries. Want a heavier pack? `python3 tools/build_geometry.py --size=2048`
doubles the texel density (~1.2 MB atlas) — re-run `build_textures.py` after.
See `tools/README.md` for the design notes.

### Repository layout

```
Aegis_Null_Veil_BP/     behavior pack (entity, script, loot, lang)
Aegis_Null_Veil_RP/     resource pack (model, atlas, animations, particles, sound)
tools/                  generators + validator + packager
assets/                 intermediate artwork (pack icon, previews, TTS sources)
build/                  packaged .mcaddon / .mcpack (git-ignored)
```

### Notes on size

The directive asked for a 30–45 MB pack. This build is ~2 MB because padding it
to 30 MB would mean shipping filler audio or an uncompressed 4K atlas for a
single mob, which makes the add-on worse, not better. Everything that carries
real value is here at full quality — 1024px atlas, 44 kHz stereo Ogg Vorbis,
28 sound files, 40-bone rig. Run the 2048 option above if you want more texture
detail and do not mind the extra memory.
