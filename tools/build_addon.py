#!/usr/bin/env python3
"""Rebuild all generated assets, validate, and package release/Aegis_Primordial.mcaddon"""
import os, subprocess, sys, zipfile
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
os.chdir(ROOT)
def run(*cmd):
    print("+", " ".join(cmd)); subprocess.check_call(cmd)
if "--skip-assets" not in sys.argv:
    run(sys.executable, "tools/build_model.py")
    run(sys.executable, "tools/build_sounds.py")
run(sys.executable, "tools/validate.py")
run("node", "--check", "Aegis_Primordial_BP/scripts/main.js")
run("node", "tools/test_script.mjs")
os.makedirs("release", exist_ok=True)
out = "release/Aegis_Primordial.mcaddon"
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for pack in ("Aegis_Primordial_BP", "Aegis_Primordial_RP"):
        for dp, _, files in os.walk(pack):
            for f in files:
                full = os.path.join(dp, f)
                z.write(full, full)
    z.write("README.txt", "README.txt")
print(f"packaged {out} ({os.path.getsize(out)/1024:.0f} KB)")
