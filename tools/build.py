# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (c) 2026 情绪零碎の佳 (Jia060117)
"""Create the single-file Windows desktop application from this checkout."""
import hashlib
import json
import lzma
import os
from pathlib import Path
import struct
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[1]
BUILD=ROOT/'build/package'
DIST=ROOT/'dist'

def sha(data):return hashlib.sha256(data).hexdigest()

def main():
    BUILD.mkdir(parents=True,exist_ok=True);DIST.mkdir(exist_ok=True)
    runtime=ROOT/'.deps/python'
    if not (runtime/'python.exe').exists():raise SystemExit('Run python tools/bootstrap.py first.')
    files={}
    def add(path,name):files[name]=path.read_bytes()
    # Retain upstream runtime and wheel license files, alongside their DLLs.
    for path in runtime.rglob('*'):
        if path.is_file() and not any(part in ['__pycache__','tests'] for part in path.relative_to(runtime).parts) and path.suffix not in ['.pyc','.pyo']:
            add(path,'runtime/python/'+path.relative_to(runtime).as_posix())
    files['runtime/python/python312._pth']=b'python312.zip\n.\nLib/site-packages\n../../app/automix-probe\n'
    for path in sorted((ROOT/'src/automix').iterdir()):
        if path.suffix in ['.py','.js','.mjs']:add(path,'app/automix-probe/'+path.name)
    for name in ['quickjs.dll','automix-audio.dll','rubberband.dll']:add(ROOT/'build/native'/name,'app/automix-probe/'+name)
    for path,name in [(ROOT/'LICENSE','LICENSE'),(ROOT/'THIRD_PARTY_NOTICES.md','THIRD_PARTY_NOTICES.md'),
        (ROOT/'third_party/rubberband-4.0.0/COPYING','licenses/RubberBand-COPYING.txt'),
        (ROOT/'third_party/quickjs-2026-06-04/LICENSE','licenses/QuickJS-LICENSE.txt'),
        (ROOT/'third_party/lzma-sdk/README.md','licenses/LZMA-SDK.txt')]:add(path,name)
    add(ROOT/'third_party/lzma-sdk/lzma-sdk.txt','licenses/LZMA-SDK-original.txt')
    for path in sorted((ROOT/'third_party/licenses').iterdir()):
        if path.is_file():add(path,'licenses/'+path.name)
    files['manifest.json']=json.dumps({name:sha(data) for name,data in sorted(files.items())},sort_keys=True).encode()
    manifest_hash=BUILD/'manifest.sha256';manifest_hash.write_text(sha(files['manifest.json']),encoding='ascii')
    payload=BUILD/'payload.zip'
    with zipfile.ZipFile(payload,'w',zipfile.ZIP_STORED) as archive:
        for name,data in sorted(files.items()):
            info=zipfile.ZipInfo(name,(2026,10,16,0,0,0));info.compress_type=zipfile.ZIP_STORED;archive.writestr(info,data)
    raw=payload.read_bytes();packed=lzma.compress(raw,format=lzma.FORMAT_ALONE,preset=9)
    packed=packed[:5]+struct.pack('<Q',len(raw))+packed[13:]
    payload=BUILD/'payload.lzma';payload.write_bytes(packed)
    payload_hash=BUILD/'payload.sha256';payload_hash.write_text(sha(packed),encoding='ascii')
    compiler=Path(os.environ.get('WINDIR','C:/Windows'))/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    exe=DIST/'AutomixFor163Music.exe'
    command=[str(compiler),'/nologo','/target:winexe','/platform:x64','/optimize+','/utf8output','/out:'+str(exe),
        '/win32manifest:'+str(ROOT/'assets/Automix.exe.manifest'),'/win32icon:'+str(ROOT/'assets/Automix.ico'),
        '/resource:'+str(manifest_hash)+',manifest.sha256','/resource:'+str(payload)+',payload.lzma','/resource:'+str(payload_hash)+',payload.sha256']
    command += ['/reference:'+name+'.dll' for name in ['System.Windows.Forms','System.Drawing','System.Net.Http','System.Web.Extensions','System.IO.Compression','System.IO.Compression.FileSystem']]
    command += [str(p) for folder in [ROOT/'src/desktop',ROOT/'third_party/lzma-sdk'] for p in sorted(folder.rglob('*.cs'))]
    temp=BUILD/'compiler-temp';temp.mkdir(exist_ok=True)
    subprocess.run(command,check=True,env=dict(os.environ,TEMP=str(temp),TMP=str(temp)))
    report={'file':exe.name,'bytes':exe.stat().st_size,'sha256':sha(exe.read_bytes()),'payloadSha256':sha(packed),
        'runtimeFiles':len(files),'uncompressedBytes':sum(map(len,files.values())),'architecture':'Windows x64','publisher':'Jia060117','version':'0.1.0'}
    try:report['sourceCommit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,stderr=subprocess.DEVNULL,text=True).strip()
    except (OSError,subprocess.CalledProcessError):report['sourceCommit']=None
    (DIST/'build-report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    (DIST/'SHA256SUMS.txt').write_text(report['sha256']+'  '+exe.name+'\n',encoding='ascii')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
