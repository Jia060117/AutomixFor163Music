# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (c) 2026 情绪零碎の佳 (Jia060117)
"""Known signal through WASAPI, RAM-only loopback diagnostics."""
import argparse,json,pathlib,sys,time
import numpy as np
from memory_measure import Capture
from wasapi_audio import play_array
from analyze_audio import match
from settings import RENDER_PROFILE
p=argparse.ArgumentParser();p.add_argument('--directory',type=pathlib.Path,default=RENDER_PROFILE.parent);args=p.parse_args();args.directory.mkdir(parents=True,exist_ok=True)
rate=48000;rng=np.random.default_rng(771);length=6*rate
audio=rng.normal(0,.035,(length,2)).astype(np.float32)
# Keep this bounded, quiet diagnostic pleasant enough for a short output test.
freq=np.fft.rfftfreq(length,1/rate);gain=np.exp(-(freq/5500)**6)
for c in range(2):audio[:,c]=np.fft.irfft(np.fft.rfft(audio[:,c])*gain,length)
audio[:2400]*=np.linspace(0,1,2400)[:,None];audio[-2400:]*=np.linspace(1,0,2400)[:,None]
capture=Capture();output=None
try:
    result=play_array(audio,rate,on_start=capture.begin);time.sleep(.2);output,origin=capture.finish()
    measurements=[];training=[];observed=[];held=[]
    for at in [1,2,3,4]:
        entry={'atSeconds':at,'channels':[]}
        for c in range(2):
            sample=audio[at*rate:(at+1)*rate,c].astype(float)
            m=match(output[:,c].astype(float),sample,stride=4);frame=m['referenceFrame'];segment=output[frame:frame+len(sample),c].astype(float)
            regression=float(np.dot(sample,segment)/np.dot(sample,sample))
            error=segment-sample*regression
            entry['channels'].append({**m,'gain':regression,'errorRms':float(np.sqrt(np.mean(error**2))),'signalRms':float(np.sqrt(np.mean(segment**2))),'offsetMilliseconds':(origin+frame/rate-result['qpcStartSeconds']-at)*1000})
        measurements.append(entry)
        frame=entry['channels'][0]['referenceFrame'];inputs=audio[at*rate:(at+1)*rate].astype(float);actual=output[frame:frame+rate].astype(float)
        if at<4:training.append(inputs);observed.append(actual)
        else:held=[inputs,actual]
    matrix=np.linalg.lstsq(np.concatenate(training),np.concatenate(observed),rcond=None)[0]
    predicted=held[0]@matrix
    fit={'matrixInputToOutput':matrix.tolist(),'heldOutCorrelations':[float(np.corrcoef(predicted[:,c],held[1][:,c])[0,1]) for c in range(2)]}
    # Frequency-dependent stereo transfer, learned from training segments only.
    size=8192;S=np.zeros((size//2+1,2,2),complex);T=np.zeros_like(S)
    for x,y in zip(training,observed):
        for pos in range(0,len(x)-size+1,4096):
            X=np.fft.rfft(x[pos:pos+size]*np.hanning(size)[:,None],axis=0);Y=np.fft.rfft(y[pos:pos+size]*np.hanning(size)[:,None],axis=0)
            S+=X[:,:,None]*X[:,None,:].conj();T+=Y[:,:,None]*X[:,None,:].conj()
    power=np.trace(S,axis1=1,axis2=2).real
    S+=np.eye(2)[None]*max(power.max()*1e-6,1e-12)
    H=T@np.linalg.inv(S)
    hz=np.fft.rfftfreq(size,1/rate);mask=np.clip((6500-hz)/1000,0,1);H*=mask[:,None,None]
    raw=np.fft.irfft(H,n=size,axis=0);kernel=np.concatenate([raw[-512:],raw[:513]],axis=0)*np.hanning(1025)[:,None,None]
    prediction=np.stack([sum(np.convolve(held[0][:,i],kernel[:,o,i],mode='same') for i in range(2)) for o in range(2)],axis=1)
    fit['firHeldOutCorrelations']=[float(np.corrcoef(prediction[512:-512,c],held[1][512:-512,c])[0,1]) for c in range(2)]
    fit['kernelEnergy']=float(np.sum(kernel*kernel))
    if min(fit['firHeldOutCorrelations'])<.97:raise ValueError('Render profile did not pass held-out validation')
    profile={'version':1,'format':capture.info,'sampleRate':rate,'measurementBandHz':[0,4000],'kernel':kernel.tolist(),'heldOutCorrelations':fit['firHeldOutCorrelations'],'audioFilesWritten':0,'note':'Measurement-only stereo FIR learned from a generated signal, with an independent held-out second; not applied to music playback.'}
    (args.directory/'render-profile.json').write_text(json.dumps(profile),encoding='utf-8')
    report={'measurements':measurements,'stereoTransfer':fit,'audioFilesWritten':0,'inputPeak':float(np.max(np.abs(audio))),'outputPeak':float(np.max(np.abs(output))),'sampleRate':rate}
    (args.directory/'render-diagnostic.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
finally:
    capture.close();audio.fill(0)
    if output is not None:output.fill(0)
