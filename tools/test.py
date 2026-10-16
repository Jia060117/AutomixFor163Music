# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (c) 2026 情绪零碎の佳 (Jia060117)
"""Synthetic regression suite; never controls the user's music player."""
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]

def main():
    (ROOT/'build/tests').mkdir(parents=True,exist_ok=True)
    python=ROOT/'.deps/python/python.exe'
    subprocess.run([str(python),str(ROOT/'tests/test_mixer.py')],cwd=ROOT,check=True)
    node=shutil.which('node')
    if not node:raise SystemExit('Install Node.js 22+ to run the mocked frontend tests (not required by the app).')
    for path in sorted((ROOT/'tests').glob('*.cjs')):
        print(path.name,flush=True);subprocess.run([node,str(path)],cwd=ROOT,check=True)

if __name__=='__main__':main()
