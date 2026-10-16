# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (c) 2026 情绪零碎の佳 (Jia060117)
"""Map virtual process-loopback timestamps to measured default render output."""
import numpy as np
class VirtualTimeline:
    def __init__(self,rate):self.rate=rate;self.origin=None;self.next_frame=0
    def position(self,qpc,frames,flags):
        if flags&4 or not qpc or frames<=0:raise ValueError('Invalid process capture timestamp')
        if self.origin is None:self.origin=qpc
        expected=round((qpc-self.origin)/1e7*self.rate)
        if expected<self.next_frame-1:raise ValueError('Process capture timestamp moved backwards')
        if abs(expected-self.next_frame)>1:flags|=1
        self.next_frame=expected+frames;return expected,flags

class ProcessClockMap:
    def __init__(self):self.samples=[]
    def add(self,process,system):
        if process.get('valid') and system.get('valid'):
            delta=process['sourceEndSeconds']-system['sourceEndSeconds']-process['utcAtSourceEndSeconds']+system['utcAtSourceEndSeconds']
            if abs(delta)<.25:self.samples.append(delta)
            self.samples=self.samples[-24:]
    def report(self):
        x=np.asarray(self.samples);spread=float(np.ptp(x)*1000) if len(x) else None
        return {'samples':len(x),'processToSystemMilliseconds':float(np.median(x)*1000) if len(x) else None,'spreadMilliseconds':spread,'valid':len(x)>=5 and spread<=5,'note':'Measured against default render loopback during A; virtual process capture is not a hardware DAC clock.'}
