# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (c) 2026 情绪零碎の佳 (Jia060117)
"""Fetch checksum-locked build tools and an official Windows Python runtime."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import urllib.parse
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
DEPS=ROOT/'.deps'
LOCK=json.loads((Path(__file__).with_name('dependencies.lock.json')).read_text())

def fetch(spec):
    path=DEPS/'downloads'/Path(urllib.parse.urlsplit(spec['url']).path).name
    path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists():
        print('Downloading',path.name,flush=True)
        request=urllib.request.Request(spec['url'],headers={'User-Agent':'AutomixFor163Music-build'})
        with urllib.request.urlopen(request,timeout=120) as response, path.with_suffix(path.suffix+'.part').open('wb') as output:
            shutil.copyfileobj(response,output)
        path.with_suffix(path.suffix+'.part').replace(path)
    if hashlib.sha256(path.read_bytes()).hexdigest()!=spec['sha256']:
        raise ValueError('Checksum mismatch: '+path.name)
    return path

def extract(path,dest):
    dest=dest.resolve();dest.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(path) as archive:
        for item in archive.infolist():
            if not (dest/item.filename).resolve().is_relative_to(dest):
                raise ValueError('Unsafe archive path')
        archive.extractall(dest)

def main():
    if os.name!='nt':raise SystemExit('Build on 64-bit Windows with Python 3.12 or later.')
    runtime=DEPS/'python'
    for key in ['python','numpy','zig']:
        archive=fetch(LOCK[key])
        marker=DEPS/(key+'.ready')
        if marker.exists() and marker.read_text()==LOCK[key]['sha256']:continue
        if key=='python':extract(archive,runtime)
        elif key=='numpy':extract(archive,runtime/'Lib/site-packages')
        else:extract(archive,DEPS)
        marker.write_text(LOCK[key]['sha256'])
    (runtime/'python312._pth').write_text('python312.zip\n.\nLib/site-packages\n../../src/automix\n',encoding='utf-8')
    print('Ready: .deps/python/python.exe and Zig '+LOCK['zig']['version'])

if __name__=='__main__':main()
