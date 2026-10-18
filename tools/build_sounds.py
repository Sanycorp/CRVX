#!/usr/bin/env python3
"""
Aegis Primordial — procedural sound design.
Synthesises every SFX as 44.1 kHz OGG/Vorbis (no samples, no placeholders),
and post-processes the VO lines (wav -> processed ogg: tape-sat, reverb, sub-layer).
"""
import os, json, math, glob
import numpy as np
import soundfile as sf

ROOT = os.path.join(os.path.dirname(__file__), "..")
RP = os.path.join(ROOT, "Aegis_Primordial_RP")
OUT = os.path.join(RP, "sounds", "aegis")
VO_RAW = os.path.join(ROOT, "tools", "vo_raw")
SR = 44100
rng = np.random.default_rng(42)


def t(sec):
    return np.arange(int(SR * sec)) / SR


def env(n, a=0.01, d=0.1, s=1.0, r=0.2, sr=SR):
    a, d, r = int(a * sr), int(d * sr), int(r * sr)
    sus = max(0, n - a - d - r)
    e = np.concatenate([
        np.linspace(0, 1, max(1, a)),
        np.linspace(1, s, max(1, d)),
        np.full(sus, s),
        np.linspace(s, 0, max(1, r)),
    ])
    return e[:n] if len(e) >= n else np.pad(e, (0, n - len(e)))


def noise(sec):
    return rng.standard_normal(int(SR * sec))


def lowpass(x, cutoff, order=2):
    # simple one-pole cascaded
    rc = 1.0 / (2 * math.pi * cutoff)
    dt = 1.0 / SR
    a = dt / (rc + dt)
    y = x.copy()
    for _ in range(order):
        out = np.empty_like(y)
        acc = 0.0
        for i in range(len(y)):
            acc += a * (y[i] - acc)
            out[i] = acc
        y = out
    return y


def lowpass_fast(x, cutoff):
    # FFT brick-ish lowpass with soft knee (fast for long buffers)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    g = 1 / (1 + (f / cutoff) ** 4)
    return np.fft.irfft(X * g, n=len(x))


def highpass_fast(x, cutoff):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    g = 1 - 1 / (1 + (f / cutoff) ** 4)
    return np.fft.irfft(X * g, n=len(x))


def bandpass(x, lo, hi):
    return highpass_fast(lowpass_fast(x, hi), lo)


def reverb(x, decay=1.2, mix=0.3, pre=0.02):
    n = int(SR * decay)
    ir = rng.standard_normal(n) * np.exp(-np.linspace(0, 7, n))
    ir = lowpass_fast(ir, 5000)
    ir[: int(SR * pre)] = 0
    wet = np.convolve(x, ir)[: len(x)] / (np.abs(ir).sum() ** 0.5)
    wet = wet / (np.max(np.abs(wet)) + 1e-9) * (np.max(np.abs(x)) + 1e-9)
    return x * (1 - mix) + wet * mix


def saturate(x, drive=2.0):
    return np.tanh(x * drive) / math.tanh(drive)


def norm(x, peak=0.89):
    return x / (np.max(np.abs(x)) + 1e-9) * peak


def sweep(sec, f0, f1, shape="exp"):
    tt = t(sec)
    if shape == "exp":
        f = f0 * (f1 / f0) ** (tt / sec)
    else:
        f = f0 + (f1 - f0) * tt / sec
    phase = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(phase)


def shimmer(sec, base, partials=6, detune=0.003, lfo=5.0):
    tt = t(sec)
    out = np.zeros_like(tt)
    for i in range(1, partials + 1):
        f = base * i * (1 + rng.uniform(-detune, detune))
        out += np.sin(2 * np.pi * f * tt + 0.3 * np.sin(2 * np.pi * lfo * tt * i)) / i
    return out


def save(name, x):
    os.makedirs(OUT, exist_ok=True)
    x = np.clip(x, -1, 1).astype(np.float32)
    sf.write(os.path.join(OUT, name + ".ogg"), x, SR, format="OGG", subtype="VORBIS")


# ----------------------------------------------------------------------------
# SFX
# ----------------------------------------------------------------------------
def sfx_spawn():
    sec = 3.2
    hum = shimmer(sec, 55, 8, lfo=0.7) * env(int(SR * sec), 0.6, 0.6, 0.7, 1.2)
    whoosh = bandpass(noise(sec), 300, 6000) * env(int(SR * sec), 0.9, 0.3, 0.2, 1.0)
    rise = sweep(sec, 120, 1800) * env(int(SR * sec), 1.0, 0.2, 0.0, 0.5) * 0.4
    crack = bandpass(noise(0.25), 2000, 12000) * env(int(SR * 0.25), 0.002, 0.05, 0.3, 0.15)
    x = hum * 0.8 + whoosh * 0.5 + rise
    x[int(SR * 1.4): int(SR * 1.4) + len(crack)] += crack * 0.9
    sub = np.sin(2 * np.pi * 42 * t(sec)) * env(int(SR * sec), 1.4, 0.3, 0.3, 1.2)
    return norm(reverb(saturate(x + sub * 0.6, 1.5), 1.6, 0.35))


def sfx_idle_ambient():
    sec = 6.0
    base = shimmer(sec, 82.4, 5, lfo=0.3)
    tt = t(sec)
    breathe = 0.6 + 0.4 * np.sin(2 * np.pi * tt / sec * 2)  # loops cleanly (2 cycles)
    x = base * breathe * 0.4
    x += lowpass_fast(noise(sec), 500) * 0.12 * breathe
    fade = np.minimum(1, np.minimum(tt / 0.3, (sec - tt) / 0.3))
    return norm(x * fade, 0.5)


def sfx_step():
    sec = 0.35
    thud = np.sin(2 * np.pi * sweep(0.001, 1, 1)[0] * 0) if False else sweep(sec, 160, 45) * env(int(SR * sec), 0.002, 0.08, 0.1, 0.2)
    click = bandpass(noise(sec), 1500, 7000) * env(int(SR * sec), 0.001, 0.03, 0.0, 0.05) * 0.5
    metal = np.sin(2 * np.pi * 2100 * t(sec)) * env(int(SR * sec), 0.001, 0.05, 0.0, 0.08) * 0.1
    return norm(reverb(thud + click + metal, 0.5, 0.15), 0.7)


def sfx_attack_slash():
    sec = 0.55
    sw = bandpass(noise(sec), 800, 9000) * env(int(SR * sec), 0.05, 0.1, 0.5, 0.3)
    tone = sweep(sec, 2500, 400) * env(int(SR * sec), 0.02, 0.1, 0.3, 0.3) * 0.4
    return norm(reverb(sw + tone, 0.6, 0.2))


def sfx_attack_impact():
    sec = 0.7
    punch = sweep(sec, 220, 40) * env(int(SR * sec), 0.001, 0.12, 0.2, 0.4)
    crack = bandpass(noise(sec), 1000, 10000) * env(int(SR * sec), 0.001, 0.04, 0.1, 0.3)
    zap = shimmer(sec, 440, 4, lfo=30) * env(int(SR * sec), 0.005, 0.15, 0.0, 0.2) * 0.3
    return norm(reverb(saturate(punch * 1.2 + crack * 0.7 + zap, 2.0), 0.9, 0.25))


def sfx_null_charge():
    sec = 1.5
    rise = sweep(sec, 80, 1400) * env(int(SR * sec), 0.05, 0.2, 0.9, 0.05)
    harm = sweep(sec, 160, 2800) * env(int(SR * sec), 0.3, 0.2, 0.7, 0.05) * 0.5
    grain = bandpass(noise(sec), 2000, 12000) * (t(sec) / sec) ** 2 * 0.5
    tt = t(sec)
    pulses = np.sin(2 * np.pi * 110 * tt) * (0.5 + 0.5 * np.sign(np.sin(2 * np.pi * (4 + 20 * tt / sec) * tt))) * (tt / sec) * 0.4
    return norm(reverb(rise + harm + grain + pulses, 1.0, 0.25))


def sfx_null_charge_layer():
    sec = 1.0
    x = shimmer(sec, 660, 5, lfo=12) * env(int(SR * sec), 0.1, 0.2, 0.8, 0.3) * 0.5
    x += bandpass(noise(sec), 4000, 14000) * env(int(SR * sec), 0.2, 0.2, 0.6, 0.3) * 0.3
    return norm(x, 0.6)


def sfx_null_release():
    sec = 2.4
    n = int(SR * sec)
    boom = sweep(sec, 90, 28) * env(n, 0.001, 0.3, 0.4, 1.6)
    sub = np.sin(2 * np.pi * 36 * t(sec)) * env(n, 0.002, 0.4, 0.5, 1.5)
    blast = bandpass(noise(sec), 200, 9000) * env(n, 0.001, 0.15, 0.1, 0.8)
    tear = sweep(sec, 3000, 120) * env(n, 0.001, 0.25, 0.0, 0.4) * 0.6
    ring = shimmer(sec, 220, 6, lfo=3) * env(n, 0.01, 0.6, 0.3, 1.4) * 0.35
    x = saturate(boom * 1.3 + sub * 0.9 + blast * 0.9 + tear + ring, 2.2)
    return norm(reverb(x, 2.0, 0.35))


def sfx_void_tear():
    sec = 1.6
    n = int(SR * sec)
    # reverse-ish swell then rip
    swell = bandpass(noise(sec), 100, 3000) * np.concatenate([np.linspace(0, 1, n // 3) ** 2, np.linspace(1, 0, n - n // 3) ** 0.5])
    rip = sweep(sec, 1800, 60) * env(n, 0.3, 0.3, 0.2, 0.7) * 0.7
    growl = np.sin(2 * np.pi * 48 * t(sec) + 2.0 * np.sin(2 * np.pi * 7 * t(sec))) * env(n, 0.2, 0.4, 0.5, 0.8) * 0.6
    glitch = np.sign(np.sin(2 * np.pi * 330 * t(sec))) * (rng.random(n) > 0.92) * env(n, 0.2, 0.2, 0.3, 0.6) * 0.25
    return norm(reverb(saturate(swell + rip + growl + glitch, 2.5), 1.8, 0.4))


def sfx_confirm():
    sec = 1.2
    n = int(SR * sec)
    tt = t(sec)
    x = np.zeros(n)
    for i, (f, start) in enumerate([(880, 0.0), (1174.7, 0.12), (1760, 0.24)]):
        e = env(n, 0.005, 0.2, 0.3, 0.6)
        tone = np.sin(2 * np.pi * f * tt) * 0.5 + np.sin(2 * np.pi * f * 2 * tt) * 0.15
        shifted = np.zeros(n)
        s = int(start * SR)
        shifted[s:] = (tone * e)[: n - s]
        x += shifted
    x += np.sin(2 * np.pi * 110 * tt) * env(n, 0.05, 0.3, 0.2, 0.7) * 0.3
    return norm(reverb(x, 1.4, 0.3), 0.8)


def sfx_aura():
    sec = 2.0
    n = int(SR * sec)
    x = shimmer(sec, 261.6, 6, lfo=2.0) * env(n, 0.3, 0.4, 0.6, 1.0) * 0.5
    x += shimmer(sec, 392, 4, lfo=3.0) * env(n, 0.5, 0.4, 0.5, 0.9) * 0.3
    x += bandpass(noise(sec), 3000, 9000) * env(n, 0.4, 0.3, 0.2, 1.0) * 0.12
    return norm(reverb(x, 1.8, 0.4), 0.75)


def sfx_death():
    sec = 3.0
    n = int(SR * sec)
    fall = sweep(sec, 440, 55) * env(n, 0.05, 0.5, 0.6, 1.8) * 0.6
    choir = shimmer(sec, 220, 7, lfo=1.5) * env(n, 0.4, 0.5, 0.5, 1.6) * 0.5
    dust = bandpass(noise(sec), 1500, 10000) * env(n, 0.8, 0.5, 0.4, 1.5) * 0.25
    sub = np.sin(2 * np.pi * 40 * t(sec)) * env(n, 0.3, 0.4, 0.4, 1.8) * 0.5
    return norm(reverb(fall + choir + dust + sub, 2.5, 0.45))


def sfx_blink():
    sec = 0.6
    n = int(SR * sec)
    x = sweep(sec, 2400, 300) * env(n, 0.002, 0.1, 0.2, 0.3) * 0.6
    x += bandpass(noise(sec), 1000, 12000) * env(n, 0.002, 0.08, 0.1, 0.3) * 0.6
    x += np.sin(2 * np.pi * 60 * t(sec)) * env(n, 0.002, 0.1, 0.0, 0.2) * 0.5
    return norm(reverb(x, 0.8, 0.25), 0.8)


def sfx_overdrive_engage():
    sec = 1.6
    n = int(SR * sec)
    x = sweep(sec, 100, 900) * env(n, 0.02, 0.3, 0.6, 0.6) * 0.6
    x += np.sign(np.sin(2 * np.pi * 55 * t(sec))) * env(n, 0.1, 0.3, 0.5, 0.6) * 0.15
    x += shimmer(sec, 330, 5, lfo=8) * env(n, 0.2, 0.3, 0.6, 0.6) * 0.3
    x += bandpass(noise(sec), 500, 8000) * env(n, 0.001, 0.1, 0.0, 0.1) * 0.6
    return norm(reverb(saturate(x, 1.8), 1.2, 0.3))


def sfx_core_activate():
    sec = 1.4
    n = int(SR * sec)
    x = shimmer(sec, 523, 5, lfo=4) * env(n, 0.01, 0.3, 0.4, 0.8) * 0.5
    x += sweep(sec, 300, 1600) * env(n, 0.01, 0.2, 0.0, 0.3) * 0.4
    x += np.sin(2 * np.pi * 70 * t(sec)) * env(n, 0.005, 0.2, 0.2, 0.6) * 0.5
    return norm(reverb(x, 1.2, 0.3), 0.85)


SFX = {
    "spawn": sfx_spawn, "idle_ambient": sfx_idle_ambient, "step": sfx_step,
    "attack_slash": sfx_attack_slash, "attack_impact": sfx_attack_impact,
    "null_sever_charge": sfx_null_charge, "null_sever_charge_layer": sfx_null_charge_layer,
    "null_sever_release": sfx_null_release, "null_sever_tear": sfx_void_tear, "null_sever_confirm": sfx_confirm,
    "aura": sfx_aura, "death": sfx_death, "blink": sfx_blink, "overdrive_engage": sfx_overdrive_engage,
    "core_activate": sfx_core_activate,
}


# ----------------------------------------------------------------------------
# VO processing — "sentinel" voice treatment
# ----------------------------------------------------------------------------
def process_vo(path):
    x, sr = sf.read(path, dtype="float32", always_2d=True)
    x = x.mean(axis=1)
    if sr != SR:
        xi = np.interp(np.arange(0, len(x), sr / SR), np.arange(len(x)), x)
        x = xi
    x = norm(x, 0.8)
    # sub-harmonic layer (octave-down via rectified lowpass) for weight
    sub = lowpass_fast(np.abs(x) * np.sign(np.sin(np.cumsum(np.full(len(x), 2 * np.pi * 95 / SR)))), 180) * 0.35
    body = bandpass(x, 90, 9000)
    # gentle flanger for a synthetic timbre
    delay = (np.sin(2 * np.pi * 0.3 * t(len(x) / SR)) * 0.5 + 0.5) * 0.0012 * SR + 0.0008 * SR
    idx = np.arange(len(x)) - delay
    fl = np.interp(idx, np.arange(len(x)), body)
    y = saturate(body + fl * 0.35 + sub, 1.4)
    y = reverb(y, 1.0, 0.22, pre=0.03)
    tail = np.zeros(int(SR * 0.4))
    return norm(np.concatenate([y, tail]), 0.9)


def build():
    for name, fn in SFX.items():
        save(name, fn())
        print("  sfx", name)
    for p in sorted(glob.glob(os.path.join(VO_RAW, "*.wav"))):
        name = os.path.splitext(os.path.basename(p))[0]
        save(name, process_vo(p))
        print("  vo ", name)

    sd = {"format_version": "1.14.0", "sound_definitions": {}}

    def define(ev, files, cat="neutral", vol=1.0, pitch=(1.0, 1.0), mind=16, maxd=None):
        sounds = []
        for f in files:
            s = {"name": f"sounds/aegis/{f}", "volume": vol, "pitch": list(pitch) if pitch[0] != pitch[1] else pitch[0]}
            sounds.append(s)
        d = {"category": cat, "min_distance": mind, "sounds": sounds}
        if maxd:
            d["max_distance"] = maxd
        sd["sound_definitions"][ev] = d

    define("aegis.spawn", ["spawn"], "hostile", 1.0, (0.95, 1.05), 24, 64)
    define("aegis.idle", ["idle_ambient"], "ambient", 0.5, (0.98, 1.02), 8, 24)
    define("aegis.step", ["step"], "neutral", 0.6, (0.9, 1.1), 8, 24)
    define("aegis.attack.slash", ["attack_slash"], "hostile", 1.0, (0.9, 1.1), 16, 48)
    define("aegis.attack.impact", ["attack_impact"], "hostile", 1.0, (0.9, 1.1), 16, 48)
    define("aegis.null_sever.charge", ["null_sever_charge"], "hostile", 1.0, (1.0, 1.0), 32, 96)
    define("aegis.null_sever.charge_layer", ["null_sever_charge_layer"], "hostile", 0.8, (0.95, 1.1), 24, 64)
    define("aegis.null_sever.release", ["null_sever_release"], "hostile", 1.0, (1.0, 1.0), 48, 128)
    define("aegis.null_sever.tear", ["null_sever_tear"], "hostile", 1.0, (0.95, 1.05), 32, 96)
    define("aegis.null_sever.confirm", ["null_sever_confirm"], "hostile", 0.9, (1.0, 1.0), 24, 64)
    define("aegis.aura", ["aura"], "neutral", 0.8, (0.98, 1.02), 16, 48)
    define("aegis.death", ["death"], "hostile", 1.0, (1.0, 1.0), 32, 96)
    define("aegis.blink", ["blink"], "hostile", 0.9, (0.9, 1.1), 24, 64)
    define("aegis.overdrive_engage", ["overdrive_engage"], "hostile", 0.9, (1.0, 1.0), 32, 96)
    define("aegis.core_activate", ["core_activate"], "player", 1.0, (1.0, 1.0), 16, 48)
    define("aegis.vo.target_acquired", ["vo_target_acquired"], "hostile", 1.0, (1.0, 1.0), 32, 96)
    define("aegis.vo.nullifying", ["vo_nullifying"], "hostile", 1.0, (1.0, 1.0), 32, 96)
    define("aegis.vo.erased", ["vo_erased"], "hostile", 1.0, (1.0, 1.0), 32, 96)
    define("aegis.vo.secured", ["vo_secured"], "hostile", 1.0, (1.0, 1.0), 32, 96)
    define("aegis.vo.online", ["vo_online"], "hostile", 1.0, (1.0, 1.0), 32, 96)
    with open(os.path.join(RP, "sounds", "sound_definitions.json"), "w") as f:
        json.dump(sd, f, indent=1)

    sounds_json = {
        "entity_sounds": {
            "entities": {
                "aegis:primordial_sentinel": {
                    "volume": 1.0, "pitch": [0.95, 1.05],
                    "events": {
                        "ambient": {"sound": "aegis.idle", "volume": 0.5},
                        "step": {"sound": "aegis.step", "volume": 0.6},
                        "hurt": {"sound": "aegis.blink", "volume": 0.5, "pitch": [1.2, 1.4]},
                        "death": {"sound": "aegis.death"},
                        "attack": {"sound": "aegis.attack.slash"},
                    },
                }
            }
        }
    }
    with open(os.path.join(RP, "sounds.json"), "w") as f:
        json.dump(sounds_json, f, indent=1)


if __name__ == "__main__":
    build()
