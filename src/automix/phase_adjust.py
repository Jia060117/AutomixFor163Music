# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (c) 2026 情绪零碎の佳 (Jia060117)
"""Pitch-preserving future bridge-tail alignment. No native seek or audio file IO."""
import subprocess,time
import numpy as np
from build_pair_mix import correlate_tail
RATE=48000
def prepare_patch(source,bridge,plan,snapshot,shift,ffmpeg,volume):
    if not np.isfinite(shift) or not .008<abs(shift)<=.08:raise ValueError('Phase shift must be 8..80ms')
    if snapshot['sampleRate']!=RATE:raise ValueError('Phase adjustment requires 48kHz output')
    start=max(snapshot['writtenFrames']+round(.1*RATE),snapshot['playedFrames']+round(.75*RATE))
    total=len(bridge);duration=(total-start)/RATE;warp=duration-1.25
    if duration<2.9 or start<total-6*RATE:raise ValueError('Insufficient future dry B tail')
    source_start=plan['BresumeSeconds']-duration;at=round(source_start*RATE)
    if at<0:raise ValueError('Phase source bounds')
    clip=source[at:round((source_start+duration+2)*RATE)]
    if len(clip)<round((duration+1.5)*RATE):raise ValueError('Phase source too short')
    desired=plan['BresumeSeconds']+shift;factor=1+shift/warp;patch=None;started=time.perf_counter();candidates=[]
    for iteration in range(3):
        if not .95<=factor<=1.05:raise ValueError('Phase tempo adjustment exceeds 5%')
        switch=warp*factor
        filt=f"asendcmd=c='{switch:.8f} rubberband tempo 1',rubberband=tempo={factor:.8f}:pitch=1:transients=crisp:channels=together"
        r=subprocess.run([ffmpeg,'-hide_banner','-loglevel','error','-f','f32le','-ar',str(RATE),'-ac','2','-i','pipe:0','-af',filt,'-f','f32le','pipe:1'],input=clip.astype('<f4').tobytes(),capture_output=True,timeout=2,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if r.returncode:raise ValueError('Phase render failed')
        raw=bytearray(r.stdout);candidate=np.frombuffer(raw,'<f4').reshape(-1,2).copy();raw[:]=b'\0'*len(raw)
        try:
            n=total-start
            if len(candidate)<n+RATE:raise ValueError('Phase render too short')
            end,corr=correlate_tail(clip,candidate[:n+RATE],RATE);mapped=at/RATE+end-1;error=mapped-desired
            candidates.append({'tempoFactor':factor,'mappedEndSeconds':mapped,'errorMilliseconds':error*1000,'correlation':corr})
            if abs(error)<=.004:
                patch=candidate[:n].copy()*volume*.99;np.clip(patch,-.989,.989,out=patch)
                fade=min(4800,n);u=np.linspace(0,1,fade)[:,None];patch[:fade]=bridge[start:start+fade]*(1-u)+patch[:fade]*u
                if plan.get('handoff'):
                    from handoff_envelope import smooth_gain
                    h=plan['handoff'];u=(np.arange(start,total)-h['fadeStartFrame'])/(h['fadeEndFrame']-h['fadeStartFrame'])
                    patch*=(1-smooth_gain(u))[:,None]
                return start,patch,{'applied':True,'sourceShiftMilliseconds':(mapped-plan['BresumeSeconds'])*1000,'requestedShiftMilliseconds':shift*1000,'newBresumeSeconds':mapped,'startFrame':start,'durationSeconds':duration,'candidateRenders':candidates,'processingMilliseconds':(time.perf_counter()-started)*1000,'pitchPreserved':True,'nativeSeekApplied':False}
            factor-=error/warp
        finally:candidate.fill(0)
        if time.perf_counter()-started>.55:break
    raise ValueError('Phase render could not map target within 4ms')
