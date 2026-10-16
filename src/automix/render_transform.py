# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (c) 2026 情绪零碎の佳 (Jia060117)
"""Measurement reference correction only. Never filters the played music."""
import json,pathlib
import numpy as np

class Transform:
    def __init__(self,path,info):
        self.profile=None;self.kernel=None
        if not path or not pathlib.Path(path).is_file():return
        p=json.loads(pathlib.Path(path).read_text(encoding='utf-8'))
        if p.get('version')!=1 or p.get('sampleRate')!=info['sampleRate'] or p.get('format',{}).get('endpointId')!=info['endpointId']:return
        k=np.asarray(p['kernel'],dtype=np.float64)
        if k.ndim!=3 or k.shape[1:]!=(2,2) or not 129<=len(k)<=2049 or len(k)%2!=1 or not np.isfinite(k).all() or np.sum(k*k)>20:raise ValueError('Invalid render measurement profile')
        if min(p.get('heldOutCorrelations',[0]))<.97:raise ValueError('Unvalidated render measurement profile')
        self.profile=p;self.kernel=k
    def apply(self,audio):
        if self.kernel is None:return audio.astype(np.float64)
        # FFT convolution keeps reference preparation bounded even for long FIRs.
        size=1<<(len(audio)+len(self.kernel)-2).bit_length();X=np.fft.rfft(audio,n=size,axis=0)
        output=np.zeros_like(audio,dtype=np.float64);half=len(self.kernel)//2
        for o in range(2):
            spectrum=sum(X[:,i]*np.fft.rfft(self.kernel[:,o,i],n=size) for i in range(2))
            output[:,o]=np.fft.irfft(spectrum,n=size)[half:half+len(audio)]
        return output

def band(audio):
    t=np.arange(-64,65);kernel=2*(4000/48000)*np.sinc(2*(4000/48000)*t)*np.hanning(129);kernel/=kernel.sum()
    return np.stack([np.convolve(audio[:,c],kernel,mode='same') for c in range(2)],axis=1)

class Locator:
    def __init__(self,source,start,transform):
        self.reference=band(transform.apply(source));self.start=start
    def close(self):self.reference.fill(0)
    def locate(self,audio,origin,expected,minimum_rms=.0001,minimum_correlation=.94):
        from analyze_audio import match
        import time
        rate=48000;template=band(audio);end=origin+len(audio)/rate
        begin=max(0,round((expected-self.start-len(audio)/rate-1.5)*rate));last=min(len(self.reference),round((expected-self.start+1.5)*rate))
        if last-begin<len(template) or np.sqrt(np.mean(template*template))<minimum_rms:return {'valid':False,'reason':'Insufficient reference or silent output'}
        positions=[];correlations=[]
        for c in range(2):
            m=match(self.reference[begin:last,c],template[:,c],stride=4)
            positions.append(self.start+(begin+m['referenceFrame']+len(template))/rate);correlations.append(m['correlation'])
        template.fill(0)
        # Driver packet timestamps can put the final frame a few ms ahead of
        # receipt. Bound this separately; larger/future or stale points fail.
        valid=min(correlations)>=minimum_correlation and abs(positions[0]-positions[1])<=.002 and -.01<=time.perf_counter()-end<=.25
        return {'valid':valid,'sourceEndSeconds':float(np.median(positions)),'qpcAtSourceEndSeconds':end,'utcAtSourceEndSeconds':time.time()+end-time.perf_counter(),'correlations':correlations,'stereoDifferenceMilliseconds':abs(positions[0]-positions[1])*1000,'ageMilliseconds':(time.perf_counter()-end)*1000,'measurementProfileApplied':True}
