# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (c) 2026 情绪零碎の佳 (Jia060117)
"""Complementary C2 handoff gains and bounded transient diagnostics, all in RAM."""
import numpy as np
RATE=48000
def smooth_gain(u):
    u=np.clip(np.asarray(u,dtype=np.float64),0,1)
    return u*u*u*(10+u*(-15+6*u))

def protect_tail(bridge,rate=RATE,duration_ms=600,settle_ms=80):
    if bridge.ndim!=2 or not 2<=bridge.shape[1]<=8 or not np.isfinite(bridge).all():raise ValueError('Invalid handoff audio')
    if not 100<=duration_ms<=1000 or not 40<=settle_ms<=200:raise ValueError('Invalid handoff envelope duration')
    end=len(bridge)-round(settle_ms*rate/1000);start=end-round(duration_ms*rate/1000)
    if start<rate or end<=start:raise ValueError('Insufficient dry tail for handoff')
    u=np.arange(end-start+1,dtype=np.float64)/(end-start)
    bridge[start:end+1]*=(1-smooth_gain(u))[:,None];bridge[end:]=0
    return dict(version=1,curve='quintic-complementary',fadeStartFrame=start,fadeEndFrame=end,fadeStartSeconds=start/rate,fadeEndSeconds=end/rate,durationMilliseconds=duration_ms,settleMilliseconds=settle_ms,nativeCommandLeadMilliseconds=130,zeroTailFrames=len(bridge)-end)

def transient_stats(audio,rate=RATE):
    if audio.ndim!=2 or not len(audio) or not np.isfinite(audio).all():raise ValueError('Invalid transient window')
    peak=float(np.max(np.abs(audio)));d=np.abs(np.diff(audio.astype(np.float64),axis=0));jump=float(d.max(initial=0))
    saturated=np.any(np.abs(audio)>=.9999,axis=1);changes=np.diff(np.r_[False,saturated,False].astype(np.int8));runs=np.flatnonzero(changes==-1)-np.flatnonzero(changes==1)
    # This is a diagnostic indicator, not a certificate of inaudibility.
    scale=float(np.percentile(d,99.5)) if len(d) else 0
    return dict(peak=peak,overFullScaleSamples=int(np.count_nonzero(np.abs(audio)>1.0001)),longestFullScaleRunMilliseconds=float(max(runs,default=0)/rate*1000),maximumSampleJump=jump,jumpToTypicalRatio=jump/max(scale,1e-6),suspectedImpulse=bool(jump>.04 and jump>max(.01,scale)*8),note='Wideband sample-edge indicator; musical attacks can also trigger it. Listening and repeated device checks remain necessary.')
