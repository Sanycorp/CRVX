#!/usr/bin/env python3
"""
AEGIS-PRIMORDIAL :: voice-over post processing
==============================================
Takes the TTS renders in assets/vo/*.mp3 and bakes them into
Aegis_Null_Veil_RP/sounds/aegis/voice_*.ogg with a cold, authoritative,
slightly synthetic finish:

  * silence trimmed from head/tail
  * pitch dropped ~0.85 semitones (deeper, colder)
  * gentle high-pass to kill TTS rumble
  * short slap-back echo so it reads as a helmet/void comms channel
  * loudness normalised

If the mp3 sources are missing the script exits without touching the pack
(the rest of the sound bank stands on its own).
"""
import glob
import os
import subprocess
import sys

import imageio_ffmpeg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "assets", "vo")
OUT = os.path.join(ROOT, "Aegis_Null_Veil_RP", "sounds", "aegis")
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

FILTER = (
    "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.03,"
    "areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,areverse,"
    "highpass=f=95,"
    "asetrate=42000,aresample=44100:resampler=soxr:precision=28,"
    "aecho=0.85:0.88:110|170:0.16|0.09,"
    "dynaudnorm=p=0.9:m=8:g=3,"
    "volume=1.15"
)


def main():
    srcs = sorted(glob.glob(os.path.join(SRC, "*.mp3")))
    if not srcs:
        print("no TTS sources in %s - skipping VO pass" % SRC)
        return 0
    os.makedirs(OUT, exist_ok=True)
    total = 0
    for src in srcs:
        name = os.path.splitext(os.path.basename(src))[0]
        dst = os.path.join(OUT, "voice_%s.ogg" % name)
        subprocess.run(
            [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", src,
             "-af", FILTER, "-ac", "1", "-c:a", "libvorbis", "-qscale:a", "6",
             "-ar", "44100", dst],
            check=True)
        size = os.path.getsize(dst)
        total += size
        print("%-30s %6.1f KB" % (os.path.basename(dst), size / 1024.0))
    print("voice bank: %.2f MB, %d lines" % (total / 1048576.0, len(srcs)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
