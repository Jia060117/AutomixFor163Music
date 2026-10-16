# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (c) 2026 情绪零碎の佳 (Jia060117)
"""Verify PCM hypotheses against WASAPI reference, then export only verified PCM."""
import argparse,json,pathlib,wave
import numpy as np
from wasapi_audio import save_wav

def read_wav(path):
    with wave.open(str(path),'rb') as w:
        if w.getsampwidth()!=2:raise ValueError('Expected PCM16 reference')
        return np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').astype(np.float64).reshape(-1,w.getnchannels())/32768,w.getframerate()

def match(reference,template,stride=6):
    # Sliding normalized cross correlation. Downsample for coarse search then refine.
    if len(reference)<len(template) or not isinstance(stride,int) or not 1<=stride<=16:raise ValueError('Invalid correlation bounds')
    x=template[::stride];x=x-x.mean();n=len(x);xx=np.dot(x,x)
    if xx<1e-18:return {'correlation':0.,'referenceFrame':0}
    # Check all decimation phases. A single phase can conceal the true peak
    # and refine a different repeated musical phrase instead.
    coarse=(-1,0)
    for phase in range(stride):
        y=reference[phase::stride]
        if len(y)<n:continue
        size=1<<(len(y)+n-2).bit_length()
        cc=np.fft.irfft(np.fft.rfft(y,size)*np.fft.rfft(x[::-1],size),size)[n-1:len(y)]
        sums=np.r_[0,np.cumsum(y)];squares=np.r_[0,np.cumsum(y*y)]
        energy=squares[n:]-squares[:-n]-(sums[n:]-sums[:-n])**2/n
        scores=cc/np.sqrt(np.maximum(energy,1e-18)*xx)
        index=int(np.argmax(np.abs(scores)));score=abs(float(scores[index]))
        if score>coarse[0]:coarse=(score,index*stride+phase)
    at=coarse[1]
    best=(-1,at,0)
    for offset in range(max(0,at-stride*2),min(len(reference)-len(template)+1,at+stride*2+1)):
        z=reference[offset:offset+len(template)];score=float(np.corrcoef(z,template)[0,1])
        if abs(score)>best[0]:best=(abs(score),offset,score)
    return {'correlation':best[2],'referenceFrame':best[1]}

def analyze(directory):
    directory=pathlib.Path(directory);raw=(directory/'native.raw').read_bytes();meta=json.loads((directory/'native-packets.json').read_text(encoding='utf-8'))
    reference,rate=read_wav(directory/'loopback.wav');ints=np.frombuffer(raw,dtype='<i2');floats=np.frombuffer(raw,dtype='<f4')
    result={'referenceRate':rate,'referenceChannels':reference.shape[1],'float32FiniteFraction':float(np.isfinite(floats).mean()),'float32AbsMedian':float(np.median(np.abs(floats[np.isfinite(floats)]))),'hypotheses':[]}
    # Compare one packet of each hypothesis: avoids concealing packet loss/PTS jumps.
    first_bytes=meta['packets'][0]['bytes'];packet=np.frombuffer(raw[:first_bytes],dtype='<i2').astype(float)/32768
    for channels,sample_rate in [(2,48000),(1,96000),(2,44100),(1,48000)]:
        candidate=packet.reshape(-1,channels)
        if sample_rate!=rate:
            pos=np.arange(round(len(candidate)*rate/sample_rate))*sample_rate/rate
            candidate=np.stack([np.interp(pos,np.arange(len(candidate)),candidate[:,c]) for c in range(channels)],axis=1)
        channel_matches=[match(reference[:,min(c,reference.shape[1]-1)],candidate[:,c]) for c in range(channels)]
        result['hypotheses'].append({'format':'signed PCM16 little endian','channels':channels,'sampleRate':sample_rate,'matches':channel_matches})
    verified=result['hypotheses'][0]
    if reference.shape[1]==2 and rate==48000 and all(m['correlation']>.95 for m in verified['matches']) and abs(verified['matches'][0]['referenceFrame']-verified['matches'][1]['referenceFrame'])<8:
        result['verifiedFormat']={'sampleRate':48000,'channels':2,'sampleWidthBytes':2,'encoding':'signed PCM16 little endian interleaved'}
        # Raw callback chunks are NOT necessarily contiguous. Export a single packet
        # and report packet alignment before constructing a longer usable excerpt.
        result['packetAlignments']=[];offset=0
        for i,p in enumerate(meta['packets']):
            chunk=np.frombuffer(raw[offset:offset+p['bytes']],dtype='<i2').astype(float).reshape(-1,2)/32768;offset+=p['bytes']
            alignment=match(reference[:,0],chunk[:,0])
            result['packetAlignments'].append({'packet':i,'pts':p['pts'],'frames':len(chunk),**alignment})
        audio=ints.reshape(-1,2).astype(np.float32)/32768
        save_wav(directory/'native-concatenated.wav',audio,48000)
        save_wav(directory/'native-first-packet.wav',audio[:first_bytes//4],48000)
    else:result['verifiedFormat']=None
    (directory/'format-analysis.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='packetAlignments'},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory');analyze(p.parse_args().directory)
