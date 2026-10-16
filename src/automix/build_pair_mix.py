# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (c) 2026 情绪零碎の佳 (Jia060117)
"""Offline beat-grid prototype. Requires NumPy and FFmpeg with rubberband."""
import argparse,json,pathlib,subprocess,wave
import numpy as np

def read(path):
    with wave.open(str(path),'rb') as w:
        if w.getsampwidth()!=2:raise ValueError('Expected PCM16 capture')
        return np.frombuffer(w.readframes(w.getnframes()),'<i2').reshape(-1,w.getnchannels()).astype(np.float64)/32768,w.getframerate()
def write(path,x,sr):
    with wave.open(str(path),'wb') as w:
        w.setnchannels(x.shape[1]);w.setsampwidth(2);w.setframerate(sr);w.writeframes((np.clip(x,-1,1)*32767).astype('<i2').tobytes())
def trim(x,sr):
    # Preserve the first transient; only remove the leading loopback silence.
    active=np.flatnonzero(np.max(np.abs(x),axis=1)>.002)
    if not len(active):raise ValueError('No audible signal captured')
    begin=max(0,int(active[0])-round(.01*sr))
    return x[begin:],begin/sr
def onset(x,sr):
    mono=x.mean(axis=1)[::2];rate=sr/2;hop=256;size=1024
    frames=np.lib.stride_tricks.sliding_window_view(mono,size)[::hop]
    spec=np.abs(np.fft.rfft(frames*np.hanning(size),axis=1))
    freqs=np.fft.rfftfreq(size,1/rate)
    bands=[]
    for lo,hi in [(35,180),(180,1500),(1500,9000)]:
        s=np.log1p(spec[:,(freqs>=lo)&(freqs<hi)]*10)
        f=np.maximum(0,np.diff(s,axis=0)).mean(axis=1)
        f=np.r_[0,f];f/=np.percentile(f,95)+1e-9;bands.append(f)
    flux=.5*bands[0]+.2*bands[1]+.3*bands[2]
    flux=np.maximum(0,flux-np.convolve(flux,np.ones(31)/31,mode='same'))
    times=(np.arange(len(flux))*hop+size/2)/rate
    return times,flux
def grid(times,flux,low=70,high=175):
    dt=times[1]-times[0];center=flux-flux.mean();acf=np.correlate(center,center,'full')[len(center)-1:]
    acf/=acf[0]+1e-12
    candidates=[]
    for bpm in np.arange(low,high,.1):
        period=60/bpm
        score=sum(weight*np.interp(period*k/dt,np.arange(len(acf)),acf) for k,weight in [(1,1),(2,.6),(3,.4),(4,.3)])
        candidates.append((float(score),float(bpm)))
    candidates.sort(reverse=True);distinct=[]
    for score,bpm in candidates:
        if all(abs(bpm-other['bpm'])>3 for other in distinct):distinct.append({'bpm':round(bpm,2),'periodicityScore':round(score,4)})
        if len(distinct)==6:break
    bpm=distinct[0]['bpm'];period=60/bpm
    # Gaussian tolerance: spectral attacks can precede the exact beat slightly.
    offsets=np.arange(-3,4)*dt;smoothed=sum(np.interp(times+o,times,flux,left=0,right=0)*np.exp(-.5*(o/.02)**2) for o in offsets)
    phases=np.arange(0,period,dt/2)
    scores=[np.interp(np.arange(p,times[-1],period),times,smoothed,left=0,right=0).mean() for p in phases]
    phase=float(phases[int(np.argmax(scores))]);beats=np.arange(phase,times[-1],period)
    # Diagnostic ratio, not a calibrated probability.
    strength=float(max(scores)/(np.mean(smoothed)+1e-9))
    return {'bpm':bpm,'phaseSeconds':phase,'beatPeriodSeconds':period,'gridStrengthRatio':round(strength,3),'candidates':distinct,'beatsSeconds':beats.tolist()}
def correlate_tail(reference,rendered,sr):
    # Once tempo returns to 1, a dry tail must match the original source.
    stride=4;length=round(.8*sr)
    full_ref=reference.mean(axis=1);full_template=rendered[-length:].mean(axis=1)
    # Smooth only for the coarse decimated search, preventing phase aliasing.
    smooth=np.ones(7)/7
    template=np.convolve(full_template,smooth,mode='same')[::stride];ref=np.convolve(full_ref,smooth,mode='same')[::stride]
    n=len(ref)+len(template)-1;nfft=1<<(n-1).bit_length()
    numerator=np.fft.irfft(np.fft.rfft(ref,nfft)*np.fft.rfft(template[::-1],nfft),nfft)[len(template)-1:len(ref)]
    energy=np.r_[0,np.cumsum(ref*ref)];den=np.sqrt((energy[len(template):]-energy[:-len(template)])*np.sum(template*template))
    corr=numerator/(den+1e-12);i=int(np.argmax(corr));value=float(corr[i])
    # A stride-only location can be several samples off for broadband sources.
    # Refine on the original samples before judging the continuation match.
    best=(-1,i*stride)
    for at in range(max(0,i*stride-stride*2),min(len(full_ref)-length+1,i*stride+stride*2+1)):
        score=float(np.corrcoef(full_ref[at:at+length],full_template)[0,1])
        if score>best[0]:best=(score,at)
    value,frame=best
    if value<.9:raise ValueError(f'Unstretched tail could not be mapped back to B: correlation {value:.3f}')
    return (frame+length)/sr,value
def lowpass(x,sr):
    # One-pole 180Hz crossover; high = original - low so recombination is exact.
    a=np.exp(-2*np.pi*180/sr);y=np.zeros_like(x);state=np.zeros(x.shape[1])
    for i in range(len(x)):
        state=(1-a)*x[i]+a*state;y[i]=state
    return y

def build(directory,ffmpeg):
    report=json.loads((directory/'capture-report.json').read_text(encoding='utf-8'))
    if report['errors'] or len(report['captures'])!=2:raise ValueError('A complete capture pair is required')
    a,sr=read(directory/'A-capture.wav');b,bsr=read(directory/'B-capture.wav')
    if sr!=bsr or a.shape[1]!=b.shape[1]:raise ValueError('Capture formats differ')
    a,aTrim=trim(a,sr);b,bTrim=trim(b,sr)
    a=a[:round(report['captures'][0]['seconds']*sr)];b=b[:round(report['captures'][1]['seconds']*sr)]
    ga=grid(*onset(a,sr));gb=grid(*onset(b,sr));ratio=ga['bpm']/gb['bpm']
    if not .88<=ratio<=1.12:raise ValueError(f'Tempo difference too large for conservative automatic transition: {ratio:.3f}')
    period=60/ga['bpm'];mixBeats=16;mixSeconds=mixBeats*period;preSeconds=8*period;rampSeconds=8*period;postSeconds=4*period
    # Pick a stable A beat inside the analysed tail, leaving enough source.
    startA=next(t for t in ga['beatsSeconds'] if t>=preSeconds+5 and t+mixSeconds+1<len(a)/sr)
    startB=next(t for t in gb['beatsSeconds'] if t>=3)
    source=b[round(startB*sr):];write(directory/'B-stretch-input.wav',source,sr)
    # Tempo command timestamps are source/input time, with mapping tracked explicitly.
    commands=[];sourceTime=mixSeconds*ratio;steps=32;stepDuration=rampSeconds/steps
    for k in range(steps+1):
        speed=ratio+(1-ratio)*k/steps
        commands.append(f'{sourceTime:.8f} rubberband tempo {speed:.8f}')
        sourceTime+=speed*stepDuration
    filt="asendcmd=c='"+';'.join(commands)+f"',rubberband=tempo={ratio:.8f}:pitch=1:transients=crisp:channels=together"
    renderedPath=directory/'B-stretched.wav'
    run=subprocess.run([str(ffmpeg),'-hide_banner','-loglevel','error','-y','-i',str(directory/'B-stretch-input.wav'),'-af',filt,'-ar',str(sr),'-c:a','pcm_s16le',str(renderedPath)],capture_output=True,text=True)
    if run.returncode:raise ValueError(run.stderr)
    stretched,_=read(renderedPath)
    # Only require the rendered tail needed by the transition and dry B preview.
    length=round((mixSeconds+rampSeconds+postSeconds)*sr)
    if len(stretched)<length:raise ValueError('B capture too short for planned mix')
    stretched=stretched[:length]
    bEnd,bCorr=correlate_tail(source,stretched,sr)
    n=round(mixSeconds*sr);aa=a[round(startA*sr):round(startA*sr)+n];bb=stretched[:n]
    if len(aa)!=n:raise ValueError('A capture too short')
    # Equal-power mid/high fade plus complementary bass gains: avoid two full kicks.
    u=np.linspace(0,1,n)[:,None];loA=lowpass(aa,sr);loB=lowpass(bb,sr)
    gainA=np.cos(u*np.pi/2);gainB=np.sin(u*np.pi/2)
    bassB=np.clip((u-.35)/.3,0,1);bassA=1-bassB
    mixed=(aa-loA)*gainA+(bb-loB)*gainB+loA*bassA+loB*bassB
    # Smooth headroom only inside the overlap; dry edges retain native level.
    peak=float(np.max(np.abs(mixed)));scale=min(1,.97/(peak+1e-12))
    envelope=1-(1-scale)*np.sin(np.pi*u)**2
    mixed*=envelope
    # A 10ms stereo-linked lookahead peak envelope catches isolated transient sums.
    block=round(.01*sr);pad=(-len(mixed))%block
    maxima=np.max(np.pad(np.max(np.abs(mixed),axis=1),(0,pad)).reshape(-1,block),axis=1)
    gains=np.minimum(1,.998/(maxima+1e-12))
    guarded=np.minimum.reduce([np.r_[gains[0],gains[:-1]],gains,np.r_[gains[1:],gains[-1]]])
    sampleGain=np.repeat(guarded,block)[:n]
    sampleGain=np.convolve(np.pad(sampleGain,(block//2,block//2),mode='edge'),np.ones(block+1)/(block+1),mode='valid')[:n]
    mixed*=sampleGain[:,None]
    # Final sample guard; report any samples affected instead of hiding clipping.
    clipped=int(np.count_nonzero(np.abs(mixed)>.999));mixed=np.clip(mixed,-.999,.999)
    before=a[round((startA-preSeconds)*sr):round(startA*sr)]
    bridge=np.concatenate([mixed,stretched[n:round((mixSeconds+rampSeconds)*sr)]])
    dry=stretched[round((mixSeconds+rampSeconds)*sr):]
    demo=np.concatenate([before,bridge,dry]);fade=round(.015*sr)
    demo[:fade]*=np.linspace(0,1,fade)[:,None];demo[-fade:]*=np.linspace(1,0,fade)[:,None]
    write(directory/'mix-demo.wav',demo,sr);write(directory/'mix-bridge.wav',bridge,sr)
    # Endpoint mapping derives from the recovered dry-tail correlation.
    bResume=startB+bEnd-len(dry)/sr
    plan={'sampleRate':sr,'channels':a.shape[1],'A':report['captures'][0]['track'],'B':report['captures'][1]['track'],
      'Agrid':ga,'Bgrid':gb,'BtempoFactor':ratio,'overlapBeats':mixBeats,'overlapSeconds':mixSeconds,'returnToNativeTempoSeconds':rampSeconds,
      'bridgeDurationSeconds':len(bridge)/sr,'demoDurationSeconds':len(demo)/sr,'AtriggerSeconds':report['captures'][0]['sourceStartSeconds']+startA,
      'ApreviewStartSeconds':report['captures'][0]['sourceStartSeconds']+startA-preSeconds,'BentrySeconds':startB,'BresumeSeconds':bResume,
      'nativeVolume':report['captures'][0]['nativeVolume'],'loopbackLeadingTrimSeconds':{'A':aTrim,'B':bTrim},
      'BdryTailCorrelation':bCorr,'mixPeakBeforeHeadroom':peak,'minimumOverlapGain':scale,'hardGuardSamples':clipped,
      'notes':['Beat grids are estimated from 40-second snippets; first beats of bars and vocal phrases are not classified.',
        'Capture seek-to-waveform offset is not calibrated. Plan source times are approximate until a live handoff is measured.',
        'No calibrated tempo confidence or listening quality claim. Grid strength is a diagnostic ratio.',
        'Loopback may include audio from other applications.']}
    (directory/'mix-plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:plan[k] for k in ['BtempoFactor','overlapSeconds','bridgeDurationSeconds','BdryTailCorrelation','hardGuardSamples']}))
    print(json.dumps({'A_BPM':ga['bpm'],'B_BPM':gb['bpm'],'A_strength':ga['gridStrengthRatio'],'B_strength':gb['gridStrengthRatio']}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--directory',type=pathlib.Path,required=True);p.add_argument('--ffmpeg',type=pathlib.Path,required=True);args=p.parse_args();build(args.directory,args.ffmpeg)
