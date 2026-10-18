# tools/ — build pipeline

Everything in both packs is generated from source except the JSON you would
actually want to hand-edit (entity, client entity, animations, controllers,
sound definitions). Regeneration is deterministic: same seeds in, same bytes out.

## Setup

```bash
pip install --break-system-packages pillow numpy soundfile imageio-ffmpeg
```

`imageio-ffmpeg` supplies the ffmpeg binary used for the Ogg Vorbis encodes.

## The pipeline, in order

| Script | Input | Output |
|---|---|---|
| `build_geometry.py [--size=N]` | `model_def.py` | `RP/models/entity/aegis_primordial.geo.json`, `tools/uv_layout.json` |
| `build_textures.py` | `uv_layout.json`, `model_def.py` | `RP/textures/entity/aegis_primordial{,_emissive}.png` |
| `build_particles.py` | (self-contained) | `RP/particles/*.json` (10 emitters) |
| `build_audio.py` | (self-contained) | `RP/sounds/aegis/*.ogg` (21 SFX) |
| `build_vo.py` | `assets/vo/*.mp3` | `RP/sounds/aegis/voice_*.ogg` |
| `build_item_textures.py` | (self-contained) | `RP/textures/items/aegis_spawn_egg.png`, `RP/textures/item_texture.json` |
| `validate.py` | both packs | 324 checks, exit code 1 on failure |
| `build_mcaddon.py` | both packs | `build/*.mcaddon` + `*.mcpack` |
| `preview_render.py` | geo + atlas | `assets/render_*.png` (offline model view, dev only) |

## Model source of truth — `model_def.py`

Bones are declared as a flat list with `parent`, `pivot`, `cubes` and optional
`locators`; `mirror_of` clones the right side onto the left (mirroring X and the
UVs). Materials live in the `MAT` table and drive the painter.

Conventions, verified against the official Mojang `bedrock-samples`:

* **1 unit = 1/16 block**, so the ~31 unit tall model is ~1.94 blocks.
* **Forward is −Z.** Proof: in `pig.geo.json` the snout cube sits at z=−15 in
  front of a head spanning z=−14…−6; `wolf.geo.json` has its snout at z=−12 and
  its tail at z=+8. So the *north* cube face is the front of the entity — that is
  where the eyes and chest core are painted.
* **The model's right is −X**, matching `geometry.humanoid.custom`
  (`rightArm` pivot x = −5, `leftArm` pivot x = +5).
* Rotation sign: a bone hanging down (−Y) swings **forward** on positive X
  rotation; positive Z rotation swings it toward +X (inward for the right arm).

## UV packing

`build_geometry.py` shelf-packs all 504 cube faces into one atlas and emits
**per-face UVs** (`"uv": {"north": {"uv": [x,y], "uv_size": [w,h]}, …}`) instead
of relying on the legacy box unwrap. That makes the mapping fully deterministic
and lets the painter use non-uniform texel density — the head/hood get detail
2.2×, hands 2.0×, torso 1.5×, legs 1.25×. Regions get a 2 px gutter filled with
the region's own edge colour, so mip bleeding cannot happen.

At 1024² the packer reaches 6.27 px/unit at 88 % fill; at 2048² it reaches
10.56 px/unit.

## Texture painter

Per face region, in order: base colour → material grain (fabric weave / brushed
metal / leather cells / skin) → drape folds → face shading by direction
(up 1.16, north 1.00, south 0.90, sides 0.87, down 0.70) → bevel + rivets for
plates → cloth stitching → cyan energy veins → bespoke pieces (eye visor, core
gem, palm emitters, hood shadow over the face, void gradient on hanging cloth).
The emissive map is the same layout painted black except for glow.

## Audio

Small numpy synth: chirps, filtered noise, swept band-pass, FFT convolution
reverb, tanh saturation. Loopables (the idle hum) are built from frequencies that
are integer multiples of 1/loop-length so they seam perfectly, then cross-faded.
VO lines are TTS renders in `assets/vo/`, pitched down ~0.85 semitones with
silence trimming and a slap-back echo in `build_vo.py`.

## Validation

`validate.py` is the gate that prevents the classic failure modes: missing
geometry, wrong texture path, empty material, unmapped faces, animated bones that
do not exist, particles/sounds referenced but not defined, ogg files referenced
but missing, script events that do not exist on the entity, static attack
animations, non-power-of-two textures, and `main.js` not parsing as an ES module
(via `node --check`). `build_mcaddon.py` refuses to package if it fails.
