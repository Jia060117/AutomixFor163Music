# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (c) 2026 情绪零碎の佳 (Jia060117)
import base64
import io
from pathlib import Path
import sys
import wave
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/automix'))
import lite_audio
lite_audio.HERE=ROOT/'build/native'
from memory_mix_worker import build,decode,energy_fade_exponent,RATE
from handoff_envelope import protect_tail,smooth_gain

def signal(bpm):
    t=np.arange(45*RATE)/RATE
    phase=(t+.025)%(60/bpm)
    kick=.65*np.sin(2*np.pi*(60*phase+45*phase*np.exp(-phase*40)))*np.exp(-phase*30)
    x=kick+.04*np.sin(2*np.pi*220*t)+.015*np.sin(2*np.pi*(420*t+.05*t*t))
    return np.column_stack((x,x*.97+.01*np.sin(2*np.pi*661*t))).astype(np.float32)

a=signal(120);b=signal(126);native=str(lite_audio.HERE/'automix-audio.dll')
bridge,plan=build(a,b,100,native,.8)
assert plan['mode']=='beat_mix' and plan['BdryTailCorrelation']>.9
assert np.isfinite(bridge).all() and plan['peak']<=.8
end=plan['handoff']['fadeStartFrame'];start=end-round(.6*RATE)
source_end=round(plan['BresumeSeconds']*RATE)-(len(bridge)-end)
assert np.corrcoef(bridge[start:end,0]/.8,b[source_end-(end-start):source_end,0])[0,1]>.9
assert np.all(bridge[plan['handoff']['fadeEndFrame']:]==0)
_,fallback=build(a,signal(90),100,native,1)
assert fallback['mode']=='crossfade' and fallback['BresumeSeconds']==10
_,loud=build(a*3,signal(90)*3,100,native,1)
assert loud['peak']<=1
for first,second in [(.05,.15),(.15,.05)]:
    exponent,_=energy_fade_exponent(np.full((RATE,2),first),np.full((RATE,2),second))
    phase=.5**exponent*np.pi/2
    adaptive=np.hypot(first*np.cos(phase),second*np.sin(phase))
    target=(first+second)/2
    assert abs(adaptive-target)<abs(np.hypot(first,second)/np.sqrt(2)-target)
with io.BytesIO() as buffer:
    with wave.open(buffer,'wb') as stream:
        stream.setnchannels(2);stream.setsampwidth(2);stream.setframerate(RATE);stream.writeframes((a*32767).astype('<i2').tobytes())
    payload={'base64':base64.b64encode(buffer.getvalue()).decode(),'startSeconds':0}
    decoded=decode(payload,native)
assert 'base64' not in payload and len(decoded)==45*RATE and np.isfinite(decoded).all()
for lag in [0,.003,.032,.08]:
    t=np.arange(2*RATE)/RATE;x=.95*np.sin(2*np.pi*997*t+.8);y=.95*np.sin(2*np.pi*997*(t+lag)+.8)
    audio=np.column_stack((x,x));h=protect_tail(audio)
    u=np.clip((np.arange(len(t))-h['fadeStartFrame'])/(h['fadeEndFrame']-h['fadeStartFrame']),0,1)
    combined=audio[:,0]+smooth_gain(u)*y
    assert np.max(np.abs(combined))<=.951 and np.all(audio[h['fadeEndFrame']:]==0)
print('PASS: native RAM decode, beat mix, dry tail alignment, fallback, peak guard, energy curve, smooth handoff')
