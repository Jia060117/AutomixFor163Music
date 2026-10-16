# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (c) 2026 情绪零碎の佳 (Jia060117)
"""Bounded RAM-only render-loopback measurement, no microphone or file writer."""
import ctypes as C,threading,time
from collections import deque
import numpy as np
from wasapi_audio import Endpoint,invoke,PTR,U32,U64
from analyze_audio import match

class Capture:
    def __init__(self,endpoint_factory=None):
        self.endpoint_factory=endpoint_factory or (lambda:Endpoint(True))
        self.chunks=deque();self.lock=threading.Lock();self.started=False;self.stop=threading.Event();self.ready=threading.Event();self.error=None
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
        if not self.ready.wait(5):raise ValueError('Loopback measurement did not initialize')
        if self.error:raise self.error
    def begin(self):
        with self.lock:self.deadline=time.perf_counter()+40;self.started=True
    def run(self):
        e=None
        try:
            e=self.endpoint_factory()
            if e.rate!=48000 or e.channels!=2:raise ValueError('Measurement requires 48kHz stereo output')
            self.rate=e.rate;self.info=e.info();e.start();self.ready.set()
            from process_clock import VirtualTimeline
            virtual_timeline=VirtualTimeline(self.rate)
            while not self.stop.is_set():
                if self.started and time.perf_counter()>self.deadline:raise ValueError('Loopback measurement budget exceeded')
                size=U32();invoke(e.service,5,(C.POINTER(U32),),C.byref(size))
                while size.value:
                    ptr=PTR();frames=U32();flags=U32();position=U64();qpc=U64()
                    invoke(e.service,3,(C.POINTER(PTR),C.POINTER(U32),C.POINTER(U32),C.POINTER(U64),C.POINTER(U64)),C.byref(ptr),C.byref(frames),C.byref(flags),C.byref(position),C.byref(qpc))
                    try:
                        x=np.zeros((frames.value,e.channels),np.float32) if flags.value&2 else e.decode(C.string_at(ptr,frames.value*e.align))
                        if self.info.get('captureKind')=='process-loopback':
                            # Virtual loopback returns zero device positions on
                            # this Windows build; derive frames from valid QPC.
                            position.value,flags.value=virtual_timeline.position(qpc.value,frames.value,flags.value)
                        with self.lock:
                            self.chunks.append((x,position.value,qpc.value,flags.value))
                            if not self.started:
                                while self.chunks and position.value-self.chunks[0][1]>2*self.rate:self.chunks.popleft()[0].fill(0)
                    finally:invoke(e.service,4,(U32,),frames.value)
                    invoke(e.service,5,(C.POINTER(U32),),C.byref(size))
                time.sleep(.003)
        except Exception as exc:self.error=exc;self.ready.set()
        finally:
            if e:e.close()
    def peek(self,seconds=.7):
        if self.error:raise self.error
        with self.lock:
            packets=list(self.chunks)
            if not packets:return None
            end=packets[-1][1]+len(packets[-1][0]);begin=end-round(seconds*self.rate)
            packets=[(x.copy(),p,q,f) for x,p,q,f in packets if p+len(x)>begin]
        if not packets or packets[0][1]>begin:
            for x,*_ in packets:x.fill(0)
            return None
        if any(packets[k][1]+len(packets[k][0])!=packets[k+1][1] or packets[k+1][3]&1 for k in range(len(packets)-1)):
            for x,*_ in packets:x.fill(0)
            return None
        out=np.concatenate([p[0] for p in packets]);skip=begin-packets[0][1];out=out[skip:].copy()
        anchor=next((p for p in packets if not p[3]&4),None)
        origin=anchor[2]/1e7+(begin-anchor[1])/self.rate if anchor else None
        for x,*_ in packets:x.fill(0)
        return (out,origin) if origin is not None else None
    def finish(self):
        self.stop.set();self.thread.join(3)
        if self.thread.is_alive():raise ValueError('Loopback did not stop')
        if self.error:raise self.error
        if not self.chunks:raise ValueError('No loopback samples')
        first=self.chunks[0][1];last=self.chunks[-1];length=last[1]-first+len(last[0])
        if length>43*self.rate:raise ValueError('Loopback allocation budget exceeded')
        out=np.zeros((length,2),np.float32);anchor=next((p for p in self.chunks if not p[3]&4),self.chunks[0])
        qpc_zero=anchor[2]/1e7-(anchor[1]-first)/self.rate
        for x,pos,_,_ in self.chunks:
            at=pos-first;n=min(len(x),len(out)-at)
            if at>=0 and n>0:out[at:at+n]=x[:n]
            x.fill(0)
        self.chunks.clear();return out,qpc_zero
    def close(self):
        self.stop.set();self.thread.join(3)
        for x,*_ in self.chunks:x.fill(0)
        self.chunks.clear()

def measure(output,qpc_zero,start,a,b,bridge,plan,a_start,transform=None):
    rate=48000;local_a=plan['AtriggerSeconds']-a_start
    # Compare a declared common band: the native decoder/resampler and Windows
    # output can differ at high frequencies and fractional sample phases.
    t=np.arange(-64,65);kernel=2*(4000/rate)*np.sinc(2*(4000/rate)*t)*np.hanning(129);kernel/=kernel.sum()
    filtered=np.stack([np.convolve(output[:,c],kernel,mode='same') for c in range(2)],axis=1)
    anchors=[('native_A',a,local_a-1,-1),('external_mix',bridge,2,2),('native_B',b,plan['BresumeSeconds']+.6,plan['bridgeDurationSeconds']+.6)]
    if plan.get('handoff'):
        at=plan['handoff']['fadeStartSeconds']-.8
        anchors.append(('external_B_tail',bridge,at,at))
    elif plan.get('phaseAdjustment'):
        anchors.append(('external_B_tail',bridge,plan['bridgeDurationSeconds']-.8,plan['bridgeDurationSeconds']-.8))
    align=[];unreliable=[]
    for name,ref,at,expected in anchors:
        first=round(at*rate);last=round((at+.6)*rate);pad=1024
        context_start=max(0,first-pad);context_end=min(len(ref),last+pad)
        context=ref[context_start:context_end]
        corrected=transform.apply(context) if transform else context.astype(np.float64)
        sample=corrected[first-context_start:last-context_start];channels=[]
        if len(sample)!=round(.6*rate):raise ValueError('Verification template out of bounds')
        for c in range(2):
            template=np.convolve(sample[:,c],kernel,mode='same')
            m=match(filtered[:,c],template,stride=4)
            channels.append({'correlation':m['correlation'],'outputAtSeconds':m['referenceFrame']/rate,'offsetMilliseconds':(qpc_zero+m['referenceFrame']/rate-start-expected)*1000})
        if min(c['correlation'] for c in channels)<.85 or abs(channels[0]['outputAtSeconds']-channels[1]['outputAtSeconds'])>.003:unreliable.append(name)
        align.append({'phase':name,'channels':channels,'offsetMilliseconds':float(np.median([c['offsetMilliseconds'] for c in channels]))})
        corrected.fill(0)
    if len(align)>3 and abs(align[3]['offsetMilliseconds']-align[1]['offsetMilliseconds'])>5:unreliable.append('external_tail_clock')
    b_handoff=None
    if len(align)>3:
        trusted=all(min(c['correlation'] for c in p['channels'])>=.97 and abs(p['channels'][0]['outputAtSeconds']-p['channels'][1]['outputAtSeconds'])<=.003 for p in [align[2],align[3]])
        b_handoff={'valid':trusted,'timelineResidualMilliseconds':align[2]['offsetMilliseconds']-align[3]['offsetMilliseconds'] if trusted else None,'minimumCorrelation':min(c['correlation'] for p in [align[2],align[3]] for c in p['channels']),'note':'Compares the actual rendered corrected B tail with native B independently of the earlier mixed bridge head.'}
    boundary=start-qpc_zero+plan['bridgeDurationSeconds']+align[1]['offsetMilliseconds']/1000
    quiet={}
    for name,at in [('A_to_mix',boundary-plan['bridgeDurationSeconds']),('mix_to_B',boundary)]:
        lo=max(0,round((at-.04)*rate));hi=min(len(output),round((at+.12)*rate));silent=np.max(np.abs(output[lo:hi]),axis=1)<.002
        d=np.diff(np.r_[False,silent,False].astype(int));runs=np.flatnonzero(d==-1)-np.flatnonzero(d==1)
        quiet[name]=float(max(runs,default=0)/rate*1000)
    filtered.fill(0)
    from handoff_envelope import transient_stats
    fade_start=boundary-(plan['bridgeDurationSeconds']-plan.get('handoff',{}).get('fadeStartSeconds',plan['bridgeDurationSeconds']))
    lo=max(0,round((fade_start-.15)*rate));hi=min(len(output),round((boundary+.15)*rate))
    transients=transient_stats(output[lo:hi]) if hi>lo else None
    boundary_anchor_reliable=min(c['correlation'] for c in align[1]['channels'])>=.85 and abs(align[1]['channels'][0]['outputAtSeconds']-align[1]['channels'][1]['outputAtSeconds'])<=.003
    return {'valid':not unreliable,'unreliablePhases':unreliable,'measurementProfileApplied':bool(transform and transform.kernel is not None),'measurementBandHz':[0,4000],'alignments':align,'timelineShiftMilliseconds':None if unreliable else {'A_to_mix':align[1]['offsetMilliseconds']-align[0]['offsetMilliseconds'],'mix_to_B':align[2]['offsetMilliseconds']-align[1]['offsetMilliseconds']},'BhandoffVerification':b_handoff,'handoffTransients':transients,'quietRunNearBoundaryMilliseconds':quiet if boundary_anchor_reliable else None,'quietRunAnchorReliable':boundary_anchor_reliable,'quietThreshold':.002,'capturedSeconds':len(output)/rate,'note':'Waveform timeline residual includes seek offset and capture timing; it is not an isolated playback latency. Quiet runs are reported when the external mix anchor is reliable even if another phase is not; they can also be present in the source. Correlation uses a common 0-4kHz band and does not certify high-frequency fidelity. Default output loopback may include other apps; no microphone.'}
