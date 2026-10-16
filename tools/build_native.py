# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (c) 2026 情绪零碎の佳 (Jia060117)
"""Compile the native helpers from the exact vendored sources."""
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build/native'
ZIG=ROOT/'.deps/zig-x86_64-windows-0.14.1/zig.exe'

def run(args):
    print('Building',args[-1],flush=True)
    subprocess.run([str(ZIG),*map(str,args)],cwd=OUT,check=True)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    os.environ['ZIG_GLOBAL_CACHE_DIR']=str(ROOT/'build/zig-cache/global')
    os.environ['ZIG_LOCAL_CACHE_DIR']=str(ROOT/'build/zig-cache/local')
    quickjs=ROOT/'third_party/quickjs-2026-06-04'
    # Single-thread host. Only the compiled copy is patched; vendor source stays intact.
    code=(quickjs/'quickjs.c').read_text(encoding='utf-8')
    (OUT/'quickjs.c').write_text(code.replace('#define CONFIG_ATOMICS','/* single-thread host: no CONFIG_ATOMICS */'),encoding='utf-8')
    run(['cc','-shared','-O2','-target','x86_64-windows-gnu','-DCONFIG_VERSION="2026-06-04"','-I'+str(quickjs),
        ROOT/'src/native/quickjs-host.c',OUT/'quickjs.c',*[quickjs/f for f in ['cutils.c','libregexp.c','libunicode.c','dtoa.c']],'-o',OUT/'quickjs.dll'])
    run(['c++','-shared','-O2','-target','x86_64-windows-gnu',ROOT/'src/native/lite-native.cpp',
        '-lmfplat','-lmfreadwrite','-lmfuuid','-lole32','-lshlwapi','-o',OUT/'automix-audio.dll'])
    rb=ROOT/'third_party/rubberband-4.0.0'
    names=['rubberband-c.cpp','RubberBandStretcher.cpp','RubberBandLiveShifter.cpp','faster/AudioCurveCalculator.cpp','faster/CompoundAudioCurve.cpp','faster/HighFrequencyAudioCurve.cpp','faster/SilentAudioCurve.cpp','faster/PercussiveAudioCurve.cpp','faster/R2Stretcher.cpp','faster/StretcherChannelData.cpp','faster/StretcherProcess.cpp','common/Allocators.cpp','common/FFT.cpp','common/Log.cpp','common/Profiler.cpp','common/Resampler.cpp','common/StretchCalculator.cpp','common/sysutils.cpp','common/mathmisc.cpp','common/Thread.cpp','finer/R3Stretcher.cpp','finer/R3LiveShifter.cpp','common/BQResampler.cpp']
    run(['c++','-shared','-O2','-std=c++11','-target','x86_64-windows-gnu','-DUSE_BUILTIN_FFT','-DUSE_BQRESAMPLER',
        '-I'+str(rb),*[rb/'src'/name for name in names],'-o',OUT/'rubberband.dll'])

if __name__=='__main__':main()
