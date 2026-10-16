# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (c) 2026 情绪零碎の佳 (Jia060117)
"""Verified native packet source positions. Callback delivery is not a device clock."""
import base64,time
import numpy as np
from render_transform import band
from analyze_audio import match

class NativeLocator:
    def __init__(self,source,start):
        self.reference=band(source);self.start=start
    def close(self):self.reference.fill(0)
    def locate(self,packet):
        raw=None;x=None;template=None
        try:
            if not packet:return {'valid':False,'reason':'No native packet'}
            encoded=packet.pop('base64',None)
            if not isinstance(encoded,str) or len(encoded)>90000:return {'valid':False,'reason':'Native packet budget exceeded'}
            raw=bytearray(base64.b64decode(encoded,validate=True))
            if not 256<=len(raw)<=65536 or len(raw)%4:return {'valid':False,'reason':'Invalid native packet size'}
            x=np.frombuffer(raw,'<i2').astype(float).reshape(-1,2)/32768
            template=band(x);expected=float(packet['pts'])/1000
            lo=max(0,round((expected-self.start-1.5)*48000));hi=min(len(self.reference),round((expected-self.start+1.5)*48000))
            age=time.time()-float(packet['observedUtcSeconds'])
            if hi-lo<len(template) or np.sqrt(np.mean(template*template))<.0001 or not -.01<=age<=.3:return {'valid':False,'reason':'Silent, stale or out of reference packet'}
            matches=[match(self.reference[lo:hi,c],template[:,c],stride=4) for c in range(2)]
            positions=[self.start+(lo+m['referenceFrame'])/48000 for m in matches];corr=[m['correlation'] for m in matches]
            return {'valid':min(corr)>=.97 and abs(positions[0]-positions[1])<=.002,'sourceStartSeconds':float(np.median(positions)),'sourceEndSeconds':float(np.median(positions))+len(x)/48000,'observedUtcSeconds':packet['observedUtcSeconds'],'sequence':packet['sequence'],'correlations':corr,'stereoDifferenceMilliseconds':abs(positions[0]-positions[1])*1000,'ageMilliseconds':age*1000,'formatHypothesis':'48kHz stereo s16le','timingValidated':False}
        except (ValueError,KeyError,TypeError):return {'valid':False,'reason':'Invalid native packet'}
        finally:
            if raw is not None:raw[:]=b'\0'*len(raw)
            if x is not None:x.fill(0)
            if template is not None:template.fill(0)

class CallbackDelay:
    def __init__(self):self.samples=[];self.sequence=None
    def add(self,native,acoustic):
        if native.get('valid') and acoustic.get('valid') and native['sequence']!=self.sequence:
            self.sequence=native['sequence']
            delta=(native['sourceStartSeconds']-acoustic['sourceEndSeconds'])-(native['observedUtcSeconds']-acoustic['utcAtSourceEndSeconds'])
            if 0<=delta<=.6:self.samples.append(delta)
            self.samples=self.samples[-24:]
    def report(self):
        values=np.asarray(self.samples);spread=float(np.ptp(values)*1000) if len(values) else None
        return {'samples':len(values),'medianDelayMilliseconds':float(np.median(values)*1000) if len(values) else None,'spreadMilliseconds':spread,'usableAsEstimate':len(values)>=5 and spread<=40,'timingValidated':False,'note':'Per-transition A callback delivery estimate; native B device presentation is not directly measured while muted.'}
