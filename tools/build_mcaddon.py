#!/usr/bin/env python3
"""
AEGIS-PRIMORDIAL :: packaging
=============================
Runs the validator, then zips the two packs into:

  build/Aegis_Null_Veil_Sentinel_v1.0.0.mcaddon   (both packs - double click to install)
  build/Aegis_Null_Veil_BP_v1.0.0.mcpack          (behavior only)
  build/Aegis_Null_Veil_RP_v1.0.0.mcpack          (resources only)

Usage:  python3 tools/build_mcaddon.py [--no-validate]
"""
import json
import os
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build")
BP = os.path.join(ROOT, "Aegis_Null_Veil_BP")
RP = os.path.join(ROOT, "Aegis_Null_Veil_RP")

SKIP_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}
SKIP_EXT = {".pyc", ".bak", ".tmp", ".zip", ".mcaddon", ".mcpack"}


def version():
    m = json.load(open(os.path.join(BP, "manifest.json")))
    return "v" + ".".join(str(x) for x in m["header"]["version"])


def zip_pack(src, dst, root_name):
    files = []
    for dirpath, _, names in os.walk(src):
        for n in names:
            if n in SKIP_NAMES or os.path.splitext(n)[1] in SKIP_EXT:
                continue
            files.append(os.path.join(dirpath, n))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in files:
            arc = os.path.join(root_name, os.path.relpath(f, src)).replace(os.sep, "/")
            z.write(f, arc)
    return len(files), os.path.getsize(dst)


def zip_addon(dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    total = 0
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for src in (BP, RP):
            root_name = os.path.basename(src)
            for dirpath, _, names in os.walk(src):
                for n in names:
                    if n in SKIP_NAMES or os.path.splitext(n)[1] in SKIP_EXT:
                        continue
                    f = os.path.join(dirpath, n)
                    arc = os.path.join(root_name, os.path.relpath(f, src)).replace(os.sep, "/")
                    z.write(f, arc)
                    total += 1
    return total, os.path.getsize(dst)


def tree_report():
    rows = []
    for base, label in ((BP, "BP"), (RP, "RP")):
        n, size = 0, 0
        for dirpath, _, names in os.walk(base):
            for fn in names:
                p = os.path.join(dirpath, fn)
                n += 1
                size += os.path.getsize(p)
        rows.append((label, n, size))
    return rows


def main():
    if "--no-validate" not in sys.argv:
        print("== validating ==")
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "validate.py")],
                           cwd=ROOT)
        if r.returncode != 0:
            print("\nvalidation failed - refusing to package")
            sys.exit(1)

    ver = version()
    os.makedirs(BUILD, exist_ok=True)

    addon = os.path.join(BUILD, "Aegis_Null_Veil_Sentinel_%s.mcaddon" % ver)
    n, size = zip_addon(addon)
    print("\npacked %s  (%d files, %.2f MB)" % (os.path.basename(addon), n, size / 1048576.0))

    bpk = os.path.join(BUILD, "Aegis_Null_Veil_BP_%s.mcpack" % ver)
    rpk = os.path.join(BUILD, "Aegis_Null_Veil_RP_%s.mcpack" % ver)
    n1, s1 = zip_pack(BP, bpk, os.path.basename(BP))
    n2, s2 = zip_pack(RP, rpk, os.path.basename(RP))
    print("packed %s (%d files, %.2f MB)" % (os.path.basename(bpk), n1, s1 / 1048576.0))
    print("packed %s (%d files, %.2f MB)" % (os.path.basename(rpk), n2, s2 / 1048576.0))

    print("\npack contents:")
    for label, n, size in tree_report():
        print("  %s: %d files, %.2f MB" % (label, n, size / 1048576.0))
    print("\ninstall: open the .mcaddon (or the two .mcpack files) with Minecraft.")


if __name__ == "__main__":
    main()
