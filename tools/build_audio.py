#!/usr/bin/env python3
"""
AEGIS-PRIMORDIAL :: procedural sound bank
=========================================
Synthesises every non-voice SFX from scratch (numpy) and encodes them to Ogg
Vorbis into Aegis_Null_Veil_RP/sounds/aegis/.

Everything is deterministic (seeded), so the pack rebuilds byte-identically.
Voice lines are generated separately (see tools/README.md) and dropped into the
same folder as *.ogg before sound_definitions.json is written.
"""
import os
import subprocess
import sys
import tempfile

import numpy as np
import imageio_ffmpeg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "Aegis_Null_Veil_RP", "sounds", "aegis")
SR = 44100
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

# ---------------------------------------------------------------- primitives
def ts(n):
    return np.arange(n, dtype=np.float64) / SR


def noise(n, rng):
    return rng.standard_normal(n)


def sine(freq, n, phase=0.0):
    """One or more partials; multiple frequencies are averaged (not summed)."""
    freqs = np.atleast_1d(np.asarray(freq, dtype=np.float64)).ravel()
    t = ts(n)
    out = np.zeros(n, dtype=np.float64)
    for i, f in enumerate(freqs):
        out += np.sin(2 * np.pi * float(f) * t + phase + i * 0.7)
    return out / len(freqs)


def chirp(f0, f1, n, method="exp"):
    t = ts(n)
    T = max(n / SR, 1e-6)
    if method == "exp":
        f = f0 * (max(f1, 1e-6) / max(f0, 1e-6)) ** (t / T)
        phase = 2 * np.pi * np.cumsum(f) / SR
    else:
        phase = 2 * np.pi * (f0 * t + (f1 - f0) * t * t / (2 * T))
    return np.sin(phase)


def env_exp(n, tau, attack=0.002):
    t = ts(n)
    a = np.clip(t / max(attack, 1e-6), 0, 1)
    return a * np.exp(-t / max(tau, 1e-4))


def env_ar(n, attack, release, hold=0.0):
    t = ts(n)
    ah = max(attack, 1e-6)
    rh = max(release, 1e-6)
    a = np.clip(t / ah, 0, 1)
    r = np.clip((n / SR - hold - t) / rh, 0, 1) if release > 0 else np.ones(n)
    return np.clip(np.minimum(a, r), 0, 1)


def lp(x, cutoff):
    a = 1.0 - np.exp(-2 * np.pi * cutoff / SR)
    y = np.zeros_like(x)
    acc = 0.0
    # one-pole IIR, vectorised via cumulative trick is unstable -> loop in C-ish way
    for i in range(len(x)):
        acc += a * (x[i] - acc)
        y[i] = acc
    return y


def lp_fast(x, cutoff):
    """Approximate low-pass using a Hann-window FIR (fast, good enough)."""
    w = max(1, int(SR / max(cutoff, 20.0)))
    if w > len(x) // 2:
        w = max(1, len(x) // 2)
    k = np.hanning(w * 2 + 1)
    k /= k.sum()
    return np.convolve(x, k, mode="same")


def hp(x, cutoff):
    return x - lp_fast(x, cutoff)


def band(x, lo, hi):
    return lp_fast(hp(x, lo), hi)


def sweep_band(x, f0, f1):
    """Time varying band-pass: chunked filtering."""
    n = len(x)
    chunks = 48
    out = np.zeros(n)
    step = max(1, n // chunks)
    rng = np.random.default_rng(7)
    for i in range(0, n, step):
        seg = x[i:i + step]
        k = i / max(n - 1, 1)
        f = f0 * (f1 / f0) ** k
        w = max(2, int(SR / max(f, 30)))
        if w > len(seg):
            w = max(2, len(seg))
        win = np.hanning(w * 2 + 1)
        win /= win.sum()
        conv = np.convolve(seg, win, mode="same")
        if len(conv) > len(seg):
            conv = conv[:len(seg)]
        elif len(conv) < len(seg):
            conv = np.pad(conv, (0, len(seg) - len(conv)))
        out[i:i + len(seg)] = conv
        out[i:i + len(seg)] *= (1.0 + 0.4 * k)
    return out


def reverb(x, decay=2.6, mix=0.32, seed=3):
    rng = np.random.default_rng(seed)
    ir_len = int(SR * 1.9)
    ir = rng.standard_normal(ir_len) * np.exp(-decay * np.arange(ir_len) / SR)
    ir[:int(SR * 0.005)] *= 0.2
    n = len(x) + ir_len
    X = np.fft.rfft(x, n)
    H = np.fft.rfft(ir, n)
    y = np.fft.irfft(X * H, n)[:len(x) + ir_len]
    y = y[:len(x)] * mix + x * (1 - mix * 0.35)
    return y


def saturate(x, amount=1.4):
    return np.tanh(x * amount) / np.tanh(amount)


def norm(x, peak=0.89):
    m = np.max(np.abs(x))
    if m < 1e-9:
        return x
    return x / m * peak


def stereo(l, r=None, spread_ms=6.0):
    if r is None:
        r = l
    d = int(SR * spread_ms / 1000.0)
    if d > 0:
        r = np.concatenate([np.zeros(d), r[:-d]])
    return np.stack([l, r], axis=1)


def loopify(x, fade=0.25):
    """Make a signal seamlessly loopable by cross-fading the tail into the head."""
    n = len(x)
    f = int(SR * fade)
    if f * 2 >= n:
        return x
    head = x[:f].copy()
    tail = x[-f:].copy()
    w = np.linspace(0, 1, f)
    x = x.copy()
    x[:f] = head * w + tail * w            # tail fades out under head fade-in
    x = x[:-f]                              # drop the duplicated tail
    return x


def s(n):
    return int(SR * n)


# ------------------------------------------------------------------ recipes
def footstep(variant=0):
    rng = np.random.default_rng(100 + variant)
    n = s(0.30)
    f = 62 + variant * 7 + rng.uniform(-4, 4)
    thump = chirp(f * 1.9, f * 0.55, n, "exp") * env_exp(n, 0.055, 0.001)
    body = lp_fast(noise(n, rng), 700 + variant * 90) * env_exp(n, 0.032, 0.001) * 0.85
    grit = band(noise(n, rng), 1800 + variant * 200, 8000) * env_exp(n, 0.020, 0.001) * 0.35
    plate = sine([f * 3.1, f * 4.7], n) * env_exp(n, 0.030, 0.001) * 0.14
    mix = thump * 0.95 + body + grit + plate
    mix = norm(saturate(mix, 1.2), 0.8)
    return stereo(mix, spread_ms=2 + variant * 0.7)


def punch_impact(variant=0):
    rng = np.random.default_rng(200 + variant)
    n = s(0.85)
    sub = chirp(140 - variant * 12, 36, n, "exp") * env_exp(n, 0.20, 0.001)
    hit = band(noise(n, rng), 260, 2600) * env_exp(n, 0.11, 0.0008) * 0.9
    crack = hp(noise(n, rng), 2600) * env_exp(n, 0.035, 0.0005) * 0.5
    tail = lp_fast(noise(n, rng), 320) * env_exp(n, 0.30, 0.01) * 0.30
    ring = sine([212, 318, 404], n) * env_exp(n, 0.22, 0.002) * 0.12
    mix = sub * 1.1 + hit + crack + tail + ring
    mix = reverb(norm(saturate(mix, 1.8)), decay=3.2, mix=0.26, seed=11 + variant)
    return stereo(mix, spread_ms=9)


def slash_energy(variant=0):
    rng = np.random.default_rng(300 + variant)
    n = s(1.0)
    whoosh = sweep_band(noise(n, rng) * env_ar(n, 0.02, 0.45, 0.1),
                        320 + variant * 60, 5200) * 1.5
    tone = chirp(940, 170, n, "exp") * env_exp(n, 0.28, 0.004) * 0.42
    tone2 = chirp(1420, 240, n, "exp") * env_exp(n, 0.16, 0.003) * 0.22
    sizzle = hp(noise(n, rng), 4200) * env_exp(n, 0.22, 0.01) * 0.22
    mix = whoosh + tone + tone2 + sizzle
    mix = reverb(norm(saturate(mix, 1.5)), decay=3.0, mix=0.30, seed=21 + variant)
    return stereo(mix, spread_ms=14)


def null_sever_charge():
    rng = np.random.default_rng(400)
    n = s(2.5)
    t = ts(n)
    drone = sum(sine(f, n) for f in (55.0, 82.5, 110.0)) / 3.0
    drone *= np.clip(t / 0.9, 0, 1) * (0.55 + 0.35 * np.sin(2 * np.pi * 4.0 * t))
    sweep = chirp(180, 1900, n, "exp") * np.clip(t / 1.6, 0, 1) ** 1.4 * 0.34
    shimmer = sum(sine(f, n, phase=i) for i, f in enumerate((1180.0, 1770.0, 2360.0, 3540.0)))
    shimmer *= np.clip((t - 0.7) / 1.5, 0, 1) * 0.10
    bed = sweep_band(noise(n, rng) * np.clip(t / 2.0, 0, 1), 200, 4200) * 0.30
    lock = hp(noise(int(SR * 0.08), rng), 3000) * env_exp(int(SR * 0.08), 0.02)
    mix = drone * 0.5 + sweep + shimmer + bed
    mix = mix.copy()
    st = int(SR * 2.30)
    mix[st:st + len(lock)] += lock * 0.7
    mix *= 1.0 - np.clip((t - 2.42) / 0.08, 0, 1) * 0.0
    mix = reverb(norm(saturate(mix, 1.3)), decay=2.4, mix=0.28, seed=31)
    return stereo(mix, spread_ms=18)


def null_sever_release():
    rng = np.random.default_rng(500)
    n = s(2.9)
    t = ts(n)
    # transient
    boom = chirp(120, 26, n, "exp") * env_exp(n, 0.42, 0.001) * 1.2
    blast = band(noise(n, rng), 120, 9000) * env_exp(n, 0.30, 0.0008) * 0.85
    crack = hp(noise(n, rng), 3200) * env_exp(n, 0.06, 0.0004) * 0.55
    # beam body
    beam = (sine(146.8, n) * 0.5 + sine(220.0, n) * 0.35 + sine(293.7, n) * 0.2)
    beam *= env_exp(n, 0.85, 0.006) * (0.8 + 0.2 * np.sin(2 * np.pi * 11.0 * t))
    fall = chirp(2100, 90, n, "exp") * env_exp(n, 0.9, 0.01) * 0.22
    tail = lp_fast(noise(n, rng), 1400) * env_exp(n, 1.0, 0.02) * 0.28
    shimmer = sum(sine(f, n, phase=i) for i, f in enumerate((880.0, 1320.0, 1760.0, 2640.0)))
    shimmer *= env_exp(n, 1.2, 0.02) * 0.08
    mix = boom + blast + crack + beam + fall + tail + shimmer
    mix = reverb(norm(saturate(mix, 1.9)), decay=2.0, mix=0.38, seed=41)
    return stereo(mix, spread_ms=22)


def overdrive_activate():
    rng = np.random.default_rng(600)
    n = s(1.7)
    t = ts(n)
    riser = sweep_band(noise(n, rng) * np.clip(t / 0.95, 0, 1), 180, 6800) * 1.1
    riser *= 1.0 - np.clip((t - 0.92) / 0.12, 0, 1)
    hit = chirp(180, 42, n, "exp") * env_exp(n, 0.22, 0.001)
    hit = np.concatenate([np.zeros(int(SR * 0.9)), hit[:n - int(SR * 0.9)]]) * 1.1
    pulse = (sine(110.0, n) * 0.5 + sine(165.0, n) * 0.3) * np.clip((t - 0.92) / 0.1, 0, 1)
    pulse *= (1.0 + 0.9 * (np.sin(2 * np.pi * 6.0 * t) > 0.1)) * env_ar(n, 0.05, 0.5, 0.4)
    mix = riser + hit + pulse * 0.5
    mix = reverb(norm(saturate(mix, 1.6)), decay=2.8, mix=0.30, seed=51)
    return stereo(mix, spread_ms=16)


def spawn_materialize():
    rng = np.random.default_rng(700)
    n = s(3.2)
    t = ts(n)
    drone = sum(sine(f, n) for f in (41.2, 61.7, 82.4)) / 3.0 * np.clip(t / 1.4, 0, 1) * 0.85
    air = sweep_band(noise(n, rng) * np.clip(t / 1.2, 0, 1) ** 1.2, 120, 3400) * 0.55
    shim = sum(sine(f, n, phase=i) for i, f in enumerate((659.3, 987.8, 1318.5, 1975.5)))
    shim *= np.clip((t - 0.6) / 1.6, 0, 1) * 0.09
    th = chirp(90, 34, int(SR * 1.1), "exp") * env_exp(int(SR * 1.1), 0.25, 0.001)
    thump = np.concatenate([np.zeros(int(SR * 2.1)), th[:n - int(SR * 2.1)]]) * 1.0
    mix = drone + air + shim + thump
    mix = reverb(norm(saturate(mix, 1.4)), decay=2.2, mix=0.40, seed=61)
    return stereo(mix, spread_ms=20)


def idle_hum_loop():
    rng = np.random.default_rng(800)
    n = s(4.0)
    t = ts(n)
    # frequencies are integer multiples of 1/4 Hz so the 4s loop is seamless
    parts = [55.0, 82.5, 110.0, 164.0]
    drone = sum(sine(f, n, phase=i * 0.7) * (0.5 / (i + 1)) for i, f in enumerate(parts))
    lfo = 0.72 + 0.28 * np.sin(2 * np.pi * 0.5 * t) + 0.10 * np.sin(2 * np.pi * 1.5 * t)
    bed = lp_fast(loopify(noise(n + s(0.3), rng)), 420) * 0.16
    bed = bed[:n]
    airy = band(loopify(noise(n + s(0.3), rng)), 900, 5200)[:n] * 0.045
    mix = (drone * lfo + bed + airy) * 0.85
    return stereo(loopify(norm(mix, 0.62)), spread_ms=4)


def hurt():
    rng = np.random.default_rng(900)
    n = s(0.8)
    partials = [430.0, 611.0, 902.0, 1330.0, 1870.0]
    clang = sum(sine(f, n, phase=i) * (0.5 / (i + 1)) for i, f in enumerate(partials))
    clang *= env_exp(n, 0.18, 0.001)
    hit = band(noise(n, rng), 400, 5200) * env_exp(n, 0.07, 0.0008) * 0.6
    mix = clang * 0.8 + hit
    mix = reverb(norm(saturate(mix, 1.5)), decay=4.0, mix=0.28, seed=71)
    return stereo(mix, spread_ms=8)


def death():
    rng = np.random.default_rng(1000)
    n = s(2.8)
    t = ts(n)
    fall = chirp(150, 28, n, "exp") * env_exp(n, 1.1, 0.01) * 0.9
    pad = sum(sine(f, n) for f in (82.4, 110.0, 164.8)) / 3.0 * env_ar(n, 0.05, 1.4, 0.3) * 0.5
    dissolve = sweep_band(noise(n, rng), 380, 7200) * env_ar(n, 0.15, 1.6, 0.2) * 0.5
    shim = sum(sine(f, n, phase=i) for i, f in enumerate((987.8, 1318.5, 1975.5)))
    shim *= env_exp(n, 1.3, 0.05) * 0.10
    mix = fall + pad + dissolve + shim
    mix = reverb(norm(saturate(mix, 1.5)), decay=1.8, mix=0.45, seed=81)
    return stereo(mix, spread_ms=24)


def void_pulse():
    rng = np.random.default_rng(1100)
    n = s(1.5)
    boom = chirp(95, 30, n, "exp") * env_exp(n, 0.30, 0.002)
    sweep = sweep_band(noise(n, rng), 260, 4200) * env_ar(n, 0.05, 0.7, 0.05) * 0.9
    ring = sum(sine(f, n) for f in (196.0, 293.7)) * env_exp(n, 0.5, 0.01) * 0.14
    mix = boom * 1.0 + sweep + ring
    mix = reverb(norm(saturate(mix, 1.7)), decay=2.6, mix=0.34, seed=91)
    return stereo(mix, spread_ms=18)


def target_lock():
    n = s(0.55)
    a = sine(1318.5, n) * env_exp(n, 0.10, 0.002)
    b = np.concatenate([np.zeros(int(SR * 0.13)),
                        (sine(1975.5, n) * env_exp(n, 0.13, 0.002))[:n - int(SR * 0.13)]])
    c = np.concatenate([np.zeros(int(SR * 0.26)),
                        (sine(2637.0, n) * env_exp(n, 0.16, 0.002))[:n - int(SR * 0.26)]])
    mix = a * 0.5 + b * 0.35 + c * 0.22
    mix = reverb(norm(mix, 0.5), decay=6.0, mix=0.22, seed=101)
    return stereo(mix, spread_ms=5)


def aura_pulse():
    rng = np.random.default_rng(1200)
    n = s(2.0)
    t = ts(n)
    pad = sum(sine(f, n, phase=i) for i, f in enumerate((220.0, 330.0, 440.0, 660.0)))
    pad *= env_ar(n, 0.5, 0.9, 0.2) * 0.10
    shimmer = sweep_band(noise(n, rng), 900, 6400) * env_ar(n, 0.4, 1.0, 0.1) * 0.16
    mix = pad + shimmer
    mix = reverb(norm(mix, 0.5), decay=3.0, mix=0.4, seed=111)
    return stereo(mix, spread_ms=20)


def void_step():
    rng = np.random.default_rng(1300)
    n = s(0.7)
    whoosh = sweep_band(noise(n, rng), 2400, 260) * env_ar(n, 0.01, 0.35, 0.02) * 0.9
    sub = chirp(220, 55, n, "exp") * env_exp(n, 0.12, 0.002) * 0.5
    mix = whoosh + sub
    mix = reverb(norm(mix, 0.62), decay=3.4, mix=0.3, seed=121)
    return stereo(mix, spread_ms=12)


# ------------------------------------------------------------------- driver
RECIPES = {}
for i in range(6):
    RECIPES["step%d" % (i + 1)] = (lambda v: (lambda: footstep(v)))(i)
RECIPES["punch_impact"] = lambda: punch_impact(0)
RECIPES["punch_impact_2"] = lambda: punch_impact(1)
RECIPES["slash_energy"] = lambda: slash_energy(0)
RECIPES["slash_energy_2"] = lambda: slash_energy(1)
RECIPES["null_sever_charge"] = null_sever_charge
RECIPES["null_sever_release"] = null_sever_release
RECIPES["overdrive_activate"] = overdrive_activate
RECIPES["spawn_materialize"] = spawn_materialize
RECIPES["idle_hum_loop"] = idle_hum_loop
RECIPES["hurt"] = hurt
RECIPES["death"] = death
RECIPES["void_pulse"] = void_pulse
RECIPES["target_lock"] = target_lock
RECIPES["aura_pulse"] = aura_pulse
RECIPES["void_step"] = void_step


def main():
    os.makedirs(OUT, exist_ok=True)
    tmp = tempfile.mkdtemp()
    total = 0
    for name, fn in RECIPES.items():
        data = fn()
        data = np.clip(data, -1.0, 1.0)
        wav = os.path.join(tmp, name + ".wav")
        pcm = (data * 32767.0).astype(np.int16)
        import soundfile as sf
        sf.write(wav, pcm, SR, format="WAV", subtype="PCM_16")
        ogg = os.path.join(OUT, name + ".ogg")
        subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
                        "-i", wav, "-c:a", "libvorbis", "-qscale:a", "5",
                        "-ar", "44100", ogg], check=True)
        size = os.path.getsize(ogg)
        total += size
        print("%-22s %5.2fs  %6.1f KB" % (name, len(data) / SR, size / 1024.0))
    print("total: %.2f MB across %d files" % (total / 1048576.0, len(RECIPES)))


if __name__ == "__main__":
    main()
