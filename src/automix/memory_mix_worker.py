# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (c) 2026 情绪零碎の佳 (Jia060117)
"""Two-source in-memory decoder, mixer and WASAPI bridge. No audio file IO."""
import argparse,base64,json,pathlib,subprocess,sys,time
import numpy as np
from build_pair_mix import onset,grid,lowpass,correlate_tail
from settings import RENDER_PROFILE

RATE=48000

def energy_fade_exponent(a,b,rate=RATE):
    """Gently shift the crossfade toward the quieter source at its midpoint."""
    midpoint=min(len(a),len(b))//2
    half_window=max(1,round(rate*.25))
    start=max(0,midpoint-half_window)
    stop=min(len(a),len(b),midpoint+half_window)
    a_rms=float(np.sqrt(np.mean(np.square(a[start:stop],dtype=np.float64))))
    b_rms=float(np.sqrt(np.mean(np.square(b[start:stop],dtype=np.float64))))
    # Near silence has no reliable loudness ratio; retain the original curve.
    if min(a_rms,b_rms)<.001:return 1.,0.
    difference_db=20*np.log10(b_rms/a_rms)
    return float(np.clip(1+difference_db/40,.75,1.25)),float(difference_db)
def decode(payload,ffmpeg,max_encoded_bytes=24*1024*1024):
    if not isinstance(max_encoded_bytes,int) or not 1024*1024<=max_encoded_bytes<=64*1024*1024:raise ValueError('Encoded memory budget must be 1..64MiB')
    encoded=bytearray(base64.b64decode(payload.pop('base64'),validate=True))
    pcm=None
    try:
        if not 0<len(encoded)<=max_encoded_bytes:raise ValueError('Encoded audio budget exceeded')
        if str(ffmpeg).lower().endswith('automix-audio.dll'):
            from lite_audio import decode_bytes
            return decode_bytes(encoded,payload['startSeconds'])
        r=subprocess.run([ffmpeg,'-hide_banner','-loglevel','error','-i','pipe:0','-ss',str(payload['startSeconds']),'-t','45','-vn','-ar',str(RATE),'-ac','2','-f','f32le','pipe:1'],input=encoded,capture_output=True,timeout=50,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if r.returncode:raise ValueError('Audio decode failed')
        pcm=bytearray(r.stdout)
        if not 15*RATE*8<=len(pcm)<=45*RATE*8+65536 or len(pcm)%8:raise ValueError('Invalid decoded length')
        x=np.frombuffer(pcm,'<f4').reshape(-1,2).copy()
        if not np.isfinite(x).all():raise ValueError('Nonfinite audio')
        return x
    finally:
        encoded[:]=b'\0'*len(encoded)
        if pcm is not None:pcm[:]=b'\0'*len(pcm)

def build(a,b,a_start,ffmpeg,volume):
    ga=grid(*onset(a,RATE));gb=grid(*onset(b,RATE));ratio=ga['bpm']/gb['bpm']
    compatible=.88<=ratio<=1.12 and min(ga['gridStrengthRatio'],gb['gridStrengthRatio'])>=2
    overlap=16*ga['beatPeriodSeconds'] if compatible else 4.
    ramp=8*ga['beatPeriodSeconds'] if compatible else 0.
    # Six seconds of dry B allow cold native loading and silent warmup.
    dry=6.;target=len(a)/RATE-overlap-3
    start_a=max(t for t in ga['beatsSeconds'] if t<=target) if compatible else target
    start_b=next(t for t in gb['beatsSeconds'] if t>=3) if compatible else 0.
    source=b[round(start_b*RATE):]
    total=round((overlap+ramp+dry)*RATE)
    if compatible:
        source_time=overlap*ratio;commands=[]
        for k in range(33):
            speed=ratio+(1-ratio)*k/32
            commands.append(f'{source_time:.8f} rubberband tempo {speed:.8f}')
            source_time+=speed*ramp/32
        filt="asendcmd=c='"+';'.join(commands)+f"',rubberband=tempo={ratio:.8f}:pitch=1:transients=crisp:channels=together"
        if str(ffmpeg).lower().endswith('automix-audio.dll'):
            from lite_audio import stretch
            stretched=stretch(source,ratio,overlap,ramp,RATE)
        else:
            r=subprocess.run([ffmpeg,'-hide_banner','-loglevel','error','-f','f32le','-ar',str(RATE),'-ac','2','-i','pipe:0','-af',filt,'-f','f32le','pipe:1'],input=source.astype('<f4').tobytes(),capture_output=True,timeout=50,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if r.returncode:raise ValueError('Rubberband render failed')
            stretched=np.frombuffer(r.stdout,'<f4').reshape(-1,2).copy()
        # Map a verification tail beyond the actual bridge back to native B.
        if len(stretched)<total+RATE:raise ValueError('B is too short')
        end,corr=correlate_tail(source,stretched[:total+RATE],RATE)
        resume=start_b+end-1
    else:
        stretched=source.copy();resume=start_b+total/RATE;corr=1.
    n=round(overlap*RATE);aa=a[round(start_a*RATE):round(start_a*RATE)+n];bb=stretched[:n]
    if start_a<1 or len(aa)!=n or len(stretched)<total:raise ValueError('Insufficient transition audio')
    u=np.linspace(0,1,n)[:,None]
    fade_exponent=1.;energy_difference_db=0.
    if compatible:
        la=lowpass(aa,RATE);lb=lowpass(bb,RATE);bass=np.clip((u-.35)/.3,0,1)
        mixed=(aa-la)*np.cos(u*np.pi/2)+(bb-lb)*np.sin(u*np.pi/2)+la*(1-bass)+lb*bass
    else:
        fade_exponent,energy_difference_db=energy_fade_exponent(aa,bb)
        phase=np.power(u,fade_exponent)*np.pi/2
        mixed=aa*np.cos(phase)+bb*np.sin(phase)
    peak=float(np.max(np.abs(mixed)));scale=min(1,.97/(peak+1e-12));mixed*=1-(1-scale)*np.sin(np.pi*u)**2
    # Local gain guard preserves the dry ends and bounds summed transient peaks.
    block=480;peaks=np.max(np.pad(np.max(np.abs(mixed),axis=1),(0,(-n)%block)).reshape(-1,block),axis=1)
    gains=np.minimum(1,.998/(peaks+1e-12));guard=np.minimum.reduce([np.r_[gains[0],gains[:-1]],gains,np.r_[gains[1:],gains[-1]]])
    env=np.repeat(guard,block)[:n];env=np.convolve(np.pad(env,(240,240),mode='edge'),np.ones(481)/481,mode='valid')[:n]
    mixed*=env[:,None];clipped=int(np.count_nonzero(np.abs(mixed)>.999));mixed=np.clip(mixed,-.999,.999)
    bridge=np.concatenate([mixed,stretched[n:total]]).astype(np.float32)*volume
    # Lossy decoding/stretching can produce >1 peaks in the dry section too.
    # Guard the whole bridge, including its dry B tail, before WASAPI output.
    before_peak=float(np.max(np.abs(bridge)));length=len(bridge)
    maxima=np.max(np.pad(np.max(np.abs(bridge),axis=1),(0,(-length)%480)).reshape(-1,480),axis=1)
    gains=np.minimum(1,.998/(maxima+1e-12));safe=np.minimum.reduce([np.r_[gains[0],gains[:-1]],gains,np.r_[gains[1:],gains[-1]]])
    envelope=np.repeat(safe,480)[:length];envelope=np.convolve(np.pad(envelope,(240,240),mode='edge'),np.ones(481)/481,mode='valid')[:length]
    bridge*=envelope[:,None];final_guards=int(np.count_nonzero(np.abs(bridge)>.999));np.clip(bridge,-.999,.999,out=bridge)
    from handoff_envelope import protect_tail
    handoff=protect_tail(bridge,RATE)
    plan={'mode':'beat_mix' if compatible else 'crossfade','Agrid':ga,'Bgrid':gb,'tempoFactor':ratio,'AtriggerSeconds':a_start+start_a,'BentrySeconds':start_b,'BresumeSeconds':resume,'bridgeDurationSeconds':len(bridge)/RATE,'overlapSeconds':overlap,'BdryTailCorrelation':corr,'hardGuardSamples':clipped,'finalGuardSamples':final_guards,'minimumBridgeGain':float(envelope.min()),'peakBeforeFinalLimiter':before_peak,'fadeCurveExponent':fade_exponent,'energyDifferenceDb':energy_difference_db,'sampleRate':RATE,'peak':float(np.max(np.abs(bridge))),'audioFilesWritten':0,'handoff':handoff}
    stretched.fill(0);mixed.fill(0)
    return bridge,plan

def emit(value):
    from wasapi_audio import emit_event
    emit_event(value)
def main():
    p=argparse.ArgumentParser();p.add_argument('--ffmpeg',required=True);p.add_argument('--analyse-only',action='store_true');p.add_argument('--measure',action='store_true');p.add_argument('--source-clock',action='store_true');p.add_argument('--process-clock',action='store_true');p.add_argument('--source-limit-mib',type=int,default=24);p.add_argument('--profile',default=str(RENDER_PROFILE));args=p.parse_args()
    if not 1<=args.source_limit_mib<=64:raise ValueError('Source memory budget must be 1..64MiB')
    if args.process_clock and not args.source_clock:raise ValueError('Process clock requires source clock')
    clips=[];metas=[];bridge=None;capture=None;recording=None;locator=None;transform=None;native_locators=[];process_capture=None;process_locators=[];process_map=None;live_buffer=None
    try:
        for label in ['A','B']:
            message_limit=((args.source_limit_mib*1024*1024+2)//3)*4+4096
            line=sys.stdin.readline(message_limit+1)
            if not line.endswith('\n') or len(line)>message_limit:raise ValueError('Input message budget exceeded')
            request=json.loads(line);line=None;clips.append(decode(request,args.ffmpeg,args.source_limit_mib*1024*1024));metas.append(request)
            emit({'event':'decoded','label':label,'seconds':len(clips[-1])/RATE})
        bridge,plan=build(*clips,metas[0]['startSeconds'],args.ffmpeg,metas[0].get('volume',1))
        if args.process_clock:
            # Leave 1% headroom for the explicitly audible calibration pilot.
            start=max(0,len(bridge)-6*RATE);ramp=min(480,len(bridge)-start)
            bridge[start:start+ramp]*=np.linspace(1,.99,ramp)[:,None];bridge[start+ramp:]*=.99
            plan['pilotDryTailGain']=.99
        emit({'event':'plan','plan':plan})
        if not args.measure and not args.source_clock:
            for x in clips:x.fill(0)
            clips.clear()
        if not args.analyse_only:
            from wasapi_audio import play_array
            if args.measure or args.source_clock:
                from memory_measure import Capture,measure
                capture=Capture()
                from render_transform import Transform,Locator
                transform=Transform(args.profile,capture.info)
                if args.process_clock and transform.kernel is None:raise ValueError('Pilot calibration requires a validated profile for the current output device')
                if args.source_clock and transform.kernel is not None:locator=Locator(clips[0],metas[0]['startSeconds'],transform)
                from native_clock import NativeLocator,CallbackDelay
                native_locators=[NativeLocator(x,m['startSeconds']) for x,m in zip(clips,metas)];delay=CallbackDelay()
                if args.process_clock and transform.kernel is not None:
                    from process_audio import PlayerSessions,ProcessEndpoint
                    from process_clock import ProcessClockMap
                    sessions=PlayerSessions()
                    try:
                        pids=set(s['pid'] for s in sessions.sessions)
                        if len(pids)!=1 or any(s['mute'] or abs(s['volume']-1)>.001 for s in sessions.sessions):raise ValueError('Pilot requires one NetEase process at Windows session volume 100%, unmuted')
                        pid=next(iter(pids))
                    finally:sessions.close()
                    process_capture=Capture(lambda:ProcessEndpoint(pid));process_map=ProcessClockMap()
                    process_locators=[Locator(x,m['startSeconds'],transform) for x,m in zip(clips,metas)]
            def process_position(index,expected):
                result={'valid':False,'reason':'Process capture unavailable'}
                snapshot=process_capture.peek(.35) if process_capture else None
                if snapshot:
                    audio,origin=snapshot
                    try:result=process_locators[index].locate(audio,origin,float(expected),minimum_rms=.000001 if index==1 else .0001,minimum_correlation=.97 if index==1 else .94)
                    finally:audio.fill(0)
                return result
            def command(message,e):
                if message.get('command')!='source-position':raise ValueError('Unknown worker command')
                result={'valid':False,'reason':'No validated device-matched render profile'}
                snapshot=capture.peek() if capture and locator else None
                if snapshot:
                    audio,origin=snapshot
                    try:result=locator.locate(audio,origin,float(message['expectedSourceSeconds']))
                    finally:audio.fill(0)
                if native_locators:
                    native=native_locators[0].locate(message.get('nativePacket'));delay.add(native,result)
                    result['nativePacketPosition']=native;result['callbackDelay']=delay.report()
                if process_map:
                    point=process_position(0,message['expectedSourceSeconds']);process_map.add(point,result)
                    result['processPoint']=point;result['processClockMap']=process_map.report()
                emit({'event':'source-clock','requestId':message.get('requestId'),**result})
            def live_command(message):
                if message.get('command')=='phase-shift':
                    patch=None
                    try:
                        from phase_adjust import prepare_patch
                        start,patch,adjustment=prepare_patch(clips[1],bridge,plan,live_buffer.snapshot(),float(message['sourceShiftSeconds']),args.ffmpeg,metas[0].get('volume',1))
                        if not live_buffer.replace(start,patch):raise ValueError('Phase edit arrived after buffer submission')
                        bridge[start:]=patch;plan['originalBresumeSeconds']=plan['BresumeSeconds'];plan['BresumeSeconds']=adjustment['newBresumeSeconds'];plan['phaseAdjustment']=adjustment
                        emit({'event':'phase-adjusted','requestId':message.get('requestId'),'valid':True,'adjustment':adjustment})
                    except Exception as e:emit({'event':'phase-adjusted','requestId':message.get('requestId'),'valid':False,'reason':str(e)})
                    finally:
                        if patch is not None:patch.fill(0)
                    return
                if message.get('command')=='pilot-position':
                    point=process_position(1,message['expectedSourceSeconds']);mapping=process_map.report() if process_map else {'valid':False}
                    point['processClockMap']=mapping
                    if point.get('valid') and mapping['valid']:
                        point['speakerUtcAtSourceEndSeconds']=point['utcAtSourceEndSeconds']+mapping['processToSystemMilliseconds']/1000
                    emit({'event':'pilot-clock','requestId':message.get('requestId'),**point});return
                if message.get('command')!='native-position':raise ValueError('Unknown live command')
                native=native_locators[1].locate(message.get('nativePacket'));calibration=delay.report()
                if native.get('valid') and calibration['usableAsEstimate']:
                    native['estimatedSpeakerUtcAtSourceStartSeconds']=native['observedUtcSeconds']+calibration['medianDelayMilliseconds']/1000
                emit({'event':'native-clock','requestId':message.get('requestId'),**native,'callbackDelay':calibration})
            def start_capture():
                if capture:capture.begin()
                if process_capture:process_capture.begin()
            def set_buffer(buffer):
                nonlocal live_buffer
                live_buffer=buffer
            result=play_array(bridge,RATE,command_start=True,on_start=start_capture,on_command=command,report_clock=args.source_clock,on_live_command=live_command if native_locators else None,on_buffer=set_buffer)
            emit({'event':'complete',**result})
            if capture and (args.measure or transform.kernel is not None):
                time.sleep(2);recording,origin=capture.finish()
                try:
                    measurement=measure(recording,origin,result['qpcStartSeconds'],*clips,bridge,plan,metas[0]['startSeconds'],transform)
                    emit({'event':'handoff-verified',**(measurement.get('BhandoffVerification') or {'valid':False}),'transients':measurement.get('handoffTransients')})
                    if args.measure:emit({'event':'verified','measurement':measurement})
                except Exception as e:
                    emit({'event':'handoff-verified','valid':False,'reason':str(e)})
                    if args.measure:emit({'event':'verified','measurement':{'error':str(e)}})
            else:emit({'event':'handoff-verified','valid':False,'reason':'No validated output profile'})
    finally:
        if locator:locator.close()
        for native in native_locators:native.close()
        for process_locator in process_locators:process_locator.close()
        if process_capture:process_capture.close()
        if capture:capture.close()
        if recording is not None:recording.fill(0)
        for x in clips:x.fill(0)
        if bridge is not None:bridge.fill(0)
if __name__=='__main__':
    try:main()
    except Exception as e:emit({'event':'error','message':str(e)});sys.exit(1)
