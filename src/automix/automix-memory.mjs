// SPDX-License-Identifier: GPL-2.0-or-later
// Copyright (c) 2026 情绪零碎の佳 (Jia060117)
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawn,spawnSync} from 'node:child_process';
import {createInterface} from 'node:readline';
import {connectPlayer} from './cdp-client.mjs';

const here=path.dirname(fileURLToPath(import.meta.url)),args=process.argv.slice(2);
function arg(name,fallback){const i=args.indexOf(name);return i<0?fallback:args[i+1];}
const test=args.includes('--test-transitions'),limit=Number(arg('--test-transitions',arg('--max-transitions','0'))),seconds=Number(arg('--seconds','0'));
const testPair=arg('--test-pair',null)?.split(',');
const naturalTest=args.includes('--natural-test');
const measuring=test||args.includes('--verify');
const sourceLimitMiB=Number(arg('--source-limit-mib','64'));
if(!Number.isInteger(sourceLimitMiB)||sourceLimitMiB<1||sourceLimitMiB>64)throw Error('Source memory budget must be 1..64MiB');
const pilotClock=args.includes('--pilot-clock'),pilotCorrect=args.includes('--pilot-correct');
if(pilotCorrect&&!pilotClock)throw Error('--pilot-correct requires --pilot-clock');
if(naturalTest&&(!test||testPair))throw Error('--natural-test requires --test-transitions and normal queue');
if(testPair&&(!test||limit!==1||testPair.length!==2||testPair.some(id=>!/^\d+$/.test(id))||testPair[0]===testPair[1]))throw Error('--test-pair requires a single test transition and two distinct queued IDs');
const seekOffset=Number(arg('--b-seek-offset-ms','0')),resumeLead=Number(arg('--resume-lead-ms','312')),volumeLead=Number(arg('--volume-lead-ms','130'));
let effectiveSeekOffset=seekOffset,handoffUserInterrupted=false;
const triggerDelay=Number(arg('--a-trigger-delay-ms','229'));
const acousticLead=Number(arg('--acoustic-lead-ms','60')),sourceClock=!args.includes('--legacy-ui-clock');
if(pilotClock&&!sourceClock)throw Error('--pilot-clock requires source clock mode');
const renderProfile=path.resolve(arg('--render-profile',path.join(process.env.LOCALAPPDATA||here,'Automix/render-profile.json')));
if(![seekOffset,resumeLead,volumeLead,triggerDelay,acousticLead].every(x=>Number.isFinite(x)&&Math.abs(x)<=500))throw Error('Timing offsets must be within 500ms');
if(!Number.isInteger(limit)||limit<0||limit>10000||!Number.isFinite(seconds)||seconds<0||seconds>86400||test&&limit<1)throw Error('Invalid run limit');
const python=arg('--python','python');
let ffmpeg=arg('--ffmpeg',process.env.AUTOMIX_FFMPEG||null);
if(!ffmpeg){const r=spawnSync(python,['-c','import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())'],{encoding:'utf8',windowsHide:true});if(r.status===0)ffmpeg=r.stdout.trim();}
if(!ffmpeg||!fs.existsSync(ffmpeg))throw Error('Set --ffmpeg / AUTOMIX_FFMPEG or install imageio-ffmpeg');
const directory=path.resolve(arg('--directory',path.join(process.env.LOCALAPPDATA||here,'Automix/data')));fs.mkdirSync(directory,{recursive:true});
const report={startedUtc:new Date().toISOString(),test,timing:{seekOffset,resumeLead,volumeLead,triggerDelay,acousticLead,sourceClock},transitions:[],events:[],errors:[],audioFilesWritten:0,timingNote:'A uses validated live output waveform position when available; legacy UI offsets are fallback only. Bridge end follows its WASAPI device clock. Test mode additionally measures waveform alignment in RAM.'};
report.accelerated=test&&!naturalTest;report.verificationEnabled=measuring;report.sourceLimitMiB=sourceLimitMiB;
report.controllerRevision='heart-selection-recovery-1';
report.pilot={enabled:pilotClock,correctionEnabled:pilotCorrect,nativeVolumeFraction:.01,note:'Experimental low-level audible B under the dry B bridge tail; not digital silence.'};
const started=Date.now(),pause=ms=>new Promise(r=>setTimeout(r,Math.max(0,ms)));let stopping=false,client,original,originalPosition,worker,activeSettings,activeTarget,activeHandoffTargets,recoveryToken,nativeMonitoring=false,completedTransitions=0;
let controllerToken,controllerTimer;
process.on('SIGINT',()=>{stopping=true;});process.on('SIGTERM',()=>{stopping=true;});
const inputControl=args.includes('--stdin-control')?createInterface({input:process.stdin}):null;
inputControl?.on('line',line=>{if(line.trim()==='stop')stopping=true;});
let closingInput=false;
inputControl?.on('close',()=>{if(!closingInput)stopping=true;});
// A vanished desktop server also closes the controller's output pipe. Consume
// EPIPE/ECONNRESET so its asynchronous error cannot interrupt native recovery.
const parentPipeLost=()=>{stopping=true;report.parentPipeClosed=true;};
if(inputControl){
  inputControl.on('error',parentPipeLost);
  process.stdin?.on('error',parentPipeLost);
  process.stdout?.on('error',parentPipeLost);
  process.stderr?.on('error',parentPipeLost);
}
function stopped(){return stopping||seconds>0&&Date.now()-started>=seconds*1000;}
function log(event,data={}){report.events.push({event,utcMilliseconds:Date.now(),...data});if(report.events.length>1000)report.events.shift();console.log(JSON.stringify({event,...data}));}
function recordError(message){report.errorCount=(report.errorCount||0)+1;report.errors.push(message);if(report.errors.length>100)report.errors.shift();}
function safeError(e){return String(e.message||e).replace(/https?:\/\/\S+/g,'[media address]');}
async function state(){return (await client.evaluate('automixProbe.inspect()')).snapshot;}
async function ownsController(){return !!(client&&controllerToken&&await client.evaluate(`automixProbe.ownsController(${JSON.stringify(controllerToken)})`));}
async function recoverActiveHandoff(){
  if(!activeSettings||!await ownsController())throw Error('Cannot recover an unowned handoff');
  const settings=activeSettings,before=await state();
  await client.evaluate(`automixProbe.setTemporaryFade(${settings.playFade})`);
  // Restore only our mute/pilot level; keep a volume changed by the user.
  if(recoveryToken)await client.evaluate(`automixProbe.restoreHandoffVolume(${JSON.stringify(recoveryToken)})`);
  else if(Math.abs(before.audioSettings.playingVolume)<.001||(pilotClock&&Math.abs(before.audioSettings.playingVolume-settings.playingVolume*.01)<.001))await client.evaluate(`automixProbe.setTemporaryVolume(${settings.playingVolume})`);
  const now=await state();
  if(!handoffUserInterrupted&&activeHandoffTargets?.includes(String(now.current.resourceId))&&now.playingState==='paused')await client.evaluate('automixProbe.play()');
  if(recoveryToken)await client.evaluate(`automixProbe.cancelHandoffRecovery(${JSON.stringify(recoveryToken)})`);
  recoveryToken=null;activeSettings=null;activeHandoffTargets=null;report.recoveredNativePlayback=true;
}
async function selectPaused(id){if(String((await state()).current.resourceId)!==String(id))await client.evaluate(`automixProbe.selectTrackAndWait(${JSON.stringify(String(id))})`);await client.evaluate('automixProbe.pause()');}
function spawnWorker(){
  const p=spawn(python,['-X','utf8','-B',path.join(here,'memory_mix_worker.py'),'--ffmpeg',ffmpeg,'--profile',renderProfile,'--source-limit-mib',String(sourceLimitMiB),...(sourceClock?['--source-clock']:[]),...(pilotClock?['--process-clock']:[]),...(measuring?['--measure']:[])],{windowsHide:true,stdio:['pipe','pipe','pipe']});
  const messages=[];let error,exited=false;
  p.stdin.on('error',e=>{error=e;});p.on('error',e=>{error=e;});p.on('exit',code=>{exited=true;if(code&&!error)error=Error(`Memory worker exited ${code}`);});
  // Do not persist stderr: codec diagnostics can include media contents/addresses.
  p.stderr.on('data',()=>{});
  createInterface({input:p.stdout}).on('line',line=>{try{const m=JSON.parse(line);messages.push(m);if(messages.length>512)messages.splice(0,64);if(m.event==='error')error=Error(m.message);}catch{error=Error('Invalid worker message');}});
  async function event(name,timeout=60000,label,requestId){const until=Date.now()+timeout;while(true){const m=messages.find(x=>x.event===name&&(!label||x.label===label)&&(requestId===undefined||x.requestId===requestId));if(m)return m;if(error)throw error;if(exited)throw Error(`Worker ended before ${name}`);if(stopped())throw Error('Run stopped');if(Date.now()>until)throw Error(`Worker timeout: ${name}`);await pause(10);}}
  async function send(request){const bytes=Buffer.from(JSON.stringify(request)+'\n');if(request.base64)request.base64=null;try{await new Promise((resolve,reject)=>p.stdin.write(bytes,e=>e?reject(e):resolve()));}finally{bytes.fill(0);}}
  let requestId=0;
  return {p,event,send,latest(name){return messages.findLast(m=>m.event===name);},async position(expected,nativePacket){const id=++requestId;await send({command:'source-position',expectedSourceSeconds:expected,nativePacket,requestId:id});if(nativePacket)nativePacket.base64=null;return event('source-clock',3000,undefined,id);},async nativePosition(nativePacket){const id=++requestId;await send({command:'native-position',nativePacket,requestId:id});if(nativePacket)nativePacket.base64=null;return event('native-clock',1500,undefined,id);},async pilotPosition(expected){const id=++requestId;await send({command:'pilot-position',expectedSourceSeconds:expected,requestId:id});return event('pilot-clock',1500,undefined,id);},async phaseShift(shift){const id=++requestId;await send({command:'phase-shift',sourceShiftSeconds:shift,requestId:id});return event('phase-adjusted',2500,undefined,id);},close(){p.stdin.destroy();if(!exited)p.kill();}};
}
async function assertPair(pair){const now=await client.evaluate('automixProbe.readPlaybackPair()');if(now.playId!==pair.playId||now.mode!==pair.mode||String(now.next.resourceId)!==String(pair.testQueueNext??pair.next.resourceId))throw Error('Playback queue changed; discard transition');}
async function untilTime(at){while(Date.now()<at){if(stopped())throw Error('Run stopped');await pause(Math.min(50,at-Date.now()));}}
async function waitTrigger(pair,plan){
  if(test&&!naturalTest){await client.evaluate('automixProbe.pause()');await client.evaluate(`automixProbe.seekAndWait(${Math.max(0,plan.AtriggerSeconds-4)})`);await client.evaluate('automixProbe.play()');}
  let nextCheck=0,nextAcoustic=0,lastPoint,stablePoints=0,lastUi;const points=[];
  while(!stopped()){
    const s=await state();if(s.playId!==pair.playId)throw Error('Current song changed; discard transition');
    if(Date.now()>nextCheck){await assertPair(pair);nextCheck=Date.now()+1000;}
    if(s.playingState==='playing'){
      const pos=await client.evaluate('automixProbe.readPosition()');
      if(pos.playId===pair.playId&&pos.value!=null){
        const estimated=pos.value+(pos.source==='PlayProgress callback'?Math.min(pos.ageMilliseconds||0,100)/1000:0);
        if(lastUi&&Math.abs((estimated-lastUi.value)-(Date.now()-lastUi.at)/1000)>.5){lastPoint=null;stablePoints=0;}
        lastUi={value:estimated,at:Date.now()};
        if(estimated>plan.AtriggerSeconds+1.5)throw Error('Transition prepared too late; keep normal playback');
        const predictedCue=lastPoint?lastPoint.utcAtSourceEndSeconds+plan.AtriggerSeconds-acousticLead/1000-lastPoint.sourceEndSeconds:null;
        // A fresh stable point is enough for the final fraction of a second.
        // Starting another FFT/RPC here can cross the deadline before returning.
        const coast=lastPoint&&stablePoints>=2&&Date.now()/1000-lastPoint.utcAtSourceEndSeconds<.3&&predictedCue-lastPoint.utcAtSourceEndSeconds<=.28&&predictedCue>=Date.now()/1000-.05;
        if(sourceClock&&!coast&&estimated>=plan.AtriggerSeconds-3.5&&Date.now()>=nextAcoustic){
          if(!nativeMonitoring){try{await client.evaluate('automixProbe.beginNativeMonitor(60)');nativeMonitoring=true;}catch(e){log('native-monitor-unavailable',{message:safeError(e)});}}
          const packet=nativeMonitoring?await client.evaluate('automixProbe.readNativePacket()'):null;
          const point=await worker.position(estimated,packet?.playId===pair.playId?packet:null);if(packet)packet.base64=null;nextAcoustic=Date.now()+150;points.push(point);if(points.length>32)points.shift();
          if(point.valid){
            const drift=lastPoint?(point.sourceEndSeconds-lastPoint.sourceEndSeconds)-(point.utcAtSourceEndSeconds-lastPoint.utcAtSourceEndSeconds):0;
            stablePoints=lastPoint&&Math.abs(drift)>.025?1:stablePoints+1;lastPoint=point;
          }else{stablePoints=0;lastPoint=null;}
        }
        if(lastPoint&&stablePoints>=2&&Date.now()/1000-lastPoint.utcAtSourceEndSeconds<.3){
          const speakerEstimate=lastPoint.sourceEndSeconds+(Date.now()/1000-lastPoint.utcAtSourceEndSeconds);
          if(speakerEstimate>=plan.AtriggerSeconds-acousticLead/1000)return {source:'acoustic-clock',position:pos,estimated,speakerEstimate,stablePoints,points};
        }else if(estimated>=plan.AtriggerSeconds+triggerDelay/1000)return {source:'legacy-ui-fallback',position:pos,estimated,points};
      }
    }
    if(s.playingState!=='playing'){lastPoint=null;stablePoints=0;}
    await pause(s.playingState==='playing'?(lastUi&&lastUi.value<plan.AtriggerSeconds-5?150:5):200);
  }
  throw Error('Run stopped');
}
async function transition(pair,plan){
  const trigger=await waitTrigger(pair,plan);await assertPair(pair);
  const s=await state();if(s.playingState!=='playing')throw Error('Playback paused before transition');
  const volume=s.audioSettings.playingVolume;
  if(Math.abs(volume-plan.nativeVolume)>.001)throw Error('Volume changed after mix rendering; discard transition');
  activeSettings=s.audioSettings;activeTarget=String(pair.current.resourceId);activeHandoffTargets=[String(pair.current.resourceId),String(pair.next.resourceId)];handoffUserInterrupted=false;
  recoveryToken=(await client.evaluate(`automixProbe.armHandoffRecovery(${volume},${activeSettings.playFade},${JSON.stringify([pair.current.resourceId,pair.next.resourceId])},${Math.ceil(plan.bridgeDurationSeconds)+12},${JSON.stringify(pilotClock?[0,volume*.01]:[0])})`)).token;
  await client.evaluate('automixProbe.setTemporaryFade(false)');
  await client.evaluate('automixProbe.pause()');await worker.send({command:'start'});
  const audioStart=await worker.event('started',5000);log('bridge-started',{A:pair.current.name,B:pair.next.name,mode:plan.mode,trigger:trigger.source,sourcePositionSeconds:trigger.speakerEstimate??trigger.estimated});
  const fallbackEnd=audioStart.utcStartSeconds*1000+plan.bridgeDurationSeconds*1000;
  function end(){const c=worker.latest('render-clock');return c?.accurate&&c.streamSeconds>.1&&c.remainingSeconds>=-.1?c.projectedEndUtcSeconds*1000:fallbackEnd;}
  async function waitEndOffset(offset){while(Date.now()<end()-offset){if(stopped())throw Error('Run stopped');await pause(Math.min(40,end()-offset-Date.now()));}}
  await client.evaluate('automixProbe.setTemporaryVolume(0)');
  // Selection normally starts playback. Muting first prevents the native intro leaking.
  activeTarget=String(pair.next.resourceId);
  if(testPair)await selectPaused(activeTarget);
  else{
    await client.evaluate(`automixProbe.selectNextAndWait(${JSON.stringify({playId:pair.playId,mode:pair.mode,nextResourceId:activeTarget})})`);
    await client.evaluate('automixProbe.pause()');
  }
  const warmSeconds=pilotClock?6:4;
  plan.effectiveSeekOffsetMilliseconds=effectiveSeekOffset;
  const seek=await client.evaluate(`automixProbe.seekAndWait(${Math.max(0,plan.BresumeSeconds-warmSeconds+effectiveSeekOffset/1000)})`);
  if(Date.now()>end()-warmSeconds*1000-resumeLead)throw Error('Native B preparation overran bridge');
  await waitEndOffset(warmSeconds*1000+resumeLead);const before=await state();
  if(String(before.current.resourceId)!==activeTarget||before.playingState!=='paused')throw Error('B changed before silent warmup');
  const warmVolume=pilotClock?volume*.01:0;
  if(pilotClock)await client.evaluate(`automixProbe.setTemporaryVolume(${warmVolume})`);
  await client.evaluate('automixProbe.play()');log(pilotClock?'B-playing-pilot':'B-playing-muted');
  const nativeBPoints=[],pilotPoints=[],corrections=[];let nextNative=0,nextPilot=Date.now()+600,stablePilot=0,lastPilot;
  if(!plan.handoff)throw Error('Bridge handoff envelope missing');
  const handoff=plan.handoff,handoffLead=(plan.bridgeDurationSeconds-handoff.fadeStartSeconds)*1000+volumeLead;
  while(Date.now()<end()-handoffLead){
    const now=await state();if(String(now.current.resourceId)!==activeTarget||now.playingState!=='playing'||Math.abs(now.audioSettings.playingVolume-warmVolume)>.001)throw Error('User changed playback during warmup');
    if(pilotClock&&Date.now()>=nextPilot&&Date.now()<end()-300){
      const ui=await client.evaluate('automixProbe.readPosition()');const point=await worker.pilotPosition(ui.value);pilotPoints.push(point);if(pilotPoints.length>32)pilotPoints.shift();nextPilot=Date.now()+150;
      if(point.valid&&point.speakerUtcAtSourceEndSeconds){
        const drift=lastPilot?(point.sourceEndSeconds-lastPilot.sourceEndSeconds)-(point.speakerUtcAtSourceEndSeconds-lastPilot.speakerUtcAtSourceEndSeconds):0;
        stablePilot=lastPilot&&Math.abs(drift)>.01?1:stablePilot+1;lastPilot=point;
        const sourceAdvance=point.sourceEndSeconds+end()/1000-point.speakerUtcAtSourceEndSeconds-plan.BresumeSeconds;
        if(pilotCorrect&&stablePilot>=3&&corrections.length===0&&Math.abs(sourceAdvance)>.008&&Math.abs(sourceAdvance)<=.08&&Date.now()<end()-4000){
          const corrected=await worker.phaseShift(sourceAdvance);corrections.push({...corrected,utcMilliseconds:Date.now()});
          if(corrected.valid){plan.originalBresumeSeconds=plan.BresumeSeconds;plan.BresumeSeconds=corrected.adjustment.newBresumeSeconds;plan.phaseAdjustment=corrected.adjustment;}
          log('B-pilot-tail-adjusted',{valid:corrected.valid,reason:corrected.reason,adjustment:corrected.adjustment});lastPilot=null;stablePilot=0;nextPilot=Date.now()+200;
        }
      }else{lastPilot=null;stablePilot=0;}
    }
    if(nativeMonitoring&&Date.now()>=nextNative&&Date.now()<end()-250){
      const packet=await client.evaluate('automixProbe.readNativePacket()');
      if(packet?.playId===now.playId){const point=await worker.nativePosition(packet);nativeBPoints.push(point);if(nativeBPoints.length>32)nativeBPoints.shift();}if(packet)packet.base64=null;
      nextNative=Date.now()+150;
    }
    await pause(Math.max(0,Math.min(40,end()-handoffLead-Date.now())));if(stopped())throw Error('Run stopped');
  }
  if(stopped())throw Error('Run stopped');
  const rampStartedUtcMilliseconds=Date.now();
  log('handoff-ramping',{durationMilliseconds:handoff.durationMilliseconds});
  const ramp=await client.evaluate(`automixProbe.rampHandoffVolume(${JSON.stringify({recoveryToken,controllerToken,playId:before.playId,from:warmVolume,to:volume,durationMilliseconds:handoff.durationMilliseconds})})`,4000);
  const rampCompletedUtcMilliseconds=Date.now();
  const bridgeFadeEndUtcMilliseconds=end()-handoff.settleMilliseconds;
  const handoffSchedule={rampStartedUtcMilliseconds,rampCompletedUtcMilliseconds,bridgeFadeEndUtcMilliseconds,completionLeadMilliseconds:bridgeFadeEndUtcMilliseconds-rampCompletedUtcMilliseconds,note:'Positive lead means the volume command completed before the bridge reached its zero tail; speaker latency is not measured here.'};
  log('handoff-timing',{completionLeadMilliseconds:handoffSchedule.completionLeadMilliseconds});
  if(stopped())throw Error('Run stopped');
  const pos=await client.evaluate('automixProbe.readPosition()');log('B-unmuted',{positionSeconds:pos.value,ramp});
  const lastNative=nativeBPoints.findLast(p=>p.valid&&p.estimatedSpeakerUtcAtSourceStartSeconds);
  const sourceAdvance=lastNative?(lastNative.sourceStartSeconds+end()/1000-lastNative.estimatedSpeakerUtcAtSourceStartSeconds-plan.BresumeSeconds)*1000:null;
  const nativeBClock={version:2,validPackets:nativeBPoints.filter(p=>p.valid).length,points:nativeBPoints,estimatedSourceAdvanceMilliseconds:sourceAdvance,estimatedTimelineResidualMilliseconds:sourceAdvance===null?null:-sourceAdvance,timingControlApplied:false,note:'Positive source advance means B runs ahead; positive timeline residual means B runs behind. Source position verified by muted native PCM. Callback-to-speaker delay estimated from A; B prediction remains diagnostic and does not replace unmute timing.'};
  const afterCorrection=corrections.at(-1)?.utcMilliseconds||0;
  const lastPilotPoint=pilotPoints.findLast(p=>p.valid&&p.speakerUtcAtSourceEndSeconds&&p.speakerUtcAtSourceEndSeconds*1000>afterCorrection&&Date.now()/1000-p.speakerUtcAtSourceEndSeconds<.6);
  const pilotBClock={enabled:pilotClock,nativeVolumeFraction:pilotClock ? .01 : 0,warmSeconds,points:pilotPoints,corrections,estimatedTimelineResidualMilliseconds:lastPilotPoint?-(lastPilotPoint.sourceEndSeconds+end()/1000-lastPilotPoint.speakerUtcAtSourceEndSeconds-plan.BresumeSeconds)*1000:null,timingControlApplied:corrections.some(c=>c.valid),note:'Process timestamp map measured during A; tiny audible pilot measures current B. At most one pitch-preserving edit of the unsubmitted bridge tail, <=80ms source shift and <=5% tempo change. Native B is never seeked during correction.'};
  if(pilotClock)log('B-pilot-position',{validPoints:pilotPoints.filter(p=>p.valid).length,estimatedTimelineResidualMilliseconds:pilotBClock.estimatedTimelineResidualMilliseconds,corrections:corrections.length});
  log('B-native-position',{validPackets:nativeBClock.validPackets,estimatedTimelineResidualMilliseconds:nativeBClock.estimatedTimelineResidualMilliseconds});
  await worker.event('complete',5000);if(nativeMonitoring){await client.evaluate('automixProbe.endNativeMonitor()');nativeMonitoring=false;}await client.evaluate(`automixProbe.setTemporaryFade(${activeSettings.playFade})`);await client.evaluate(`automixProbe.cancelHandoffRecovery(${JSON.stringify(recoveryToken)})`);recoveryToken=null;activeSettings=null;activeHandoffTargets=null;
  const handoffVerification=await worker.event('handoff-verified',15000);
  if(handoffVerification.valid&&handoffVerification.minimumCorrelation>=.97&&Number.isFinite(handoffVerification.timelineResidualMilliseconds)&&Math.abs(handoffVerification.timelineResidualMilliseconds)<=80){
    const previous=effectiveSeekOffset;effectiveSeekOffset=Math.max(-80,Math.min(80,effectiveSeekOffset+handoffVerification.timelineResidualMilliseconds*.7));
    log('handoff-calibrated',{previousSeekOffsetMilliseconds:previous,nextSeekOffsetMilliseconds:effectiveSeekOffset,measuredResidualMilliseconds:handoffVerification.timelineResidualMilliseconds});
  }
  const measurement=measuring?(await worker.event('verified',15000)).measurement:null;
  if(measurement)log('measurement',measurement);
  return {A:pair.current,B:pair.next,queueMode:pair.mode,queueModeLabel:pair.modeLabel,queueSource:pair.queueSource,plan,trigger,seek:seek.completion,audioStart,renderClockAtEnd:worker.latest('render-clock'),nativePositionAtUnmute:pos,nativeBClock,pilotBClock,measurement,volumeRamp:ramp,handoffSchedule,handoffVerification,completedUtc:new Date().toISOString()};
}
try{
  client=await connectPlayer();const installed=await client.evaluate(fs.readFileSync(path.join(here,'frontend-probe.js'),'utf8'));
  if(await client.evaluate('automixProbe.version')!==27)throw Error('旧版 Automix 控制进程仍在运行，请先停止它再启动新版');
  controllerToken=(await client.evaluate('automixProbe.claimController()')).token;original=installed.snapshot;
  controllerTimer=setInterval(()=>{client.evaluate(`automixProbe.renewController(${JSON.stringify(controllerToken)})`).catch(()=>{recordError('Controller heartbeat failed; stopping');stopping=true;});},10000);
  originalPosition=(await client.evaluate('automixProbe.readStoredPosition()')).value;
  if(!original.current||!['playing','paused'].includes(original.playingState)||typeof original.audioSettings?.playFade!=='boolean')throw Error('Playback state unavailable');
  if(test&&!Number.isFinite(originalPosition))throw Error('Original position unavailable for test restoration');
  report.original={track:original.current,positionSeconds:originalPosition,state:original.playingState,audioSettings:original.audioSettings};
  if(naturalTest&&original.playingState==='paused')await client.evaluate('automixProbe.play()');
  if(testPair){
    // Only a diagnostic option; production always follows the native selector.
    if(!testPair.every(id=>original.queue.some(t=>String(t.resourceId)===id)))throw Error('Controlled test tracks must appear in the diagnostic queue preview');
    await client.evaluate('automixProbe.pause()');await client.evaluate('automixProbe.setTemporaryVolume(0)');await selectPaused(testPair[0]);await client.evaluate(`automixProbe.setTemporaryVolume(${original.audioSettings.playingVolume})`);report.controlledTestPair=testPair;
  }
  let previousFailure;
  while(!stopped()&&(!limit||completedTransitions<limit)){
    let pair;
    try{
      pair=await client.evaluate('automixProbe.readPlaybackPair()');
      if(testPair){const target=(await state()).queue.find(t=>String(t.resourceId)===testPair[1]);if(!target)throw Error('Controlled B left the queue');pair.testQueueNext=pair.next.resourceId;pair.next=target;}
      const signature=JSON.stringify([pair.playId,pair.mode,pair.next.resourceId]);
      if(signature===previousFailure){await pause(500);continue;}
      const s=await state(),nativeVolume=s.audioSettings.playingVolume;
      if(!test&&s.playingState!=='playing'){await pause(500);continue;}
      worker=spawnWorker();const transports=[];
      for(const [label,track,startSeconds] of [['A',pair.current,Math.max(0,pair.current.durationRaw/1000-55)],['B',pair.next,0]]){
        await client.evaluate(`automixProbe.prepareSource(${JSON.stringify(String(track.resourceId))},true)`,15000);
        let source=await client.evaluate(`automixProbe.readPreparedSourceBase64(${JSON.stringify(String(track.resourceId))},${sourceLimitMiB*1048576})`,40000);
        transports.push({label,httpStatus:source.httpStatus,bytes:source.bytes});
        await worker.send({base64:source.base64,startSeconds,volume:nativeVolume});source.base64=null;source=null;
        await worker.event('decoded',60000,label);await assertPair(pair);
      }
      const {plan}=await worker.event('plan');plan.nativeVolume=nativeVolume;await worker.event('ready',10000);
      log('mix-ready',{A:pair.current.name,B:pair.next.name,mode:plan.mode,queueMode:pair.mode,queueModeLabel:pair.modeLabel,queueSource:pair.queueSource,durationSeconds:plan.bridgeDurationSeconds});
      const result=await transition(pair,plan);result.transports=transports;completedTransitions++;report.transitions.push(result);if(report.transitions.length>100)report.transitions.shift();worker.close();worker=null;previousFailure=null;
      const usage=process.memoryUsage();log('controller-memory',{rssMiB:usage.rss/1048576,heapUsedMiB:usage.heapUsed/1048576,externalMiB:usage.external/1048576});
    }catch(e){
      if(nativeMonitoring){try{if(await ownsController())await client.evaluate('automixProbe.endNativeMonitor()');}catch{}nativeMonitoring=false;}
      const message=safeError(e);log('fallback',{message});recordError(message);worker?.close();worker=null;
      if(message.includes('User changed playback during'))handoffUserInterrupted=true;
      // The final queue guard can reject B after we have paused and muted A.
      // Resume that original stream and follow the new queue instead of leaving
      // A paused or ending an unattended run for this recoverable race.
      if(activeSettings&&pair&&message.includes('Playback queue changed before native selection')){
        const now=await state();
        if(String(now.current.resourceId)===String(pair.current.resourceId)&&await ownsController()){
          await recoverActiveHandoff();log('queue-handoff-recovered',{A:pair.current.name});
        }
      }
      if(activeSettings)throw e;
      if(test)throw e;
      previousFailure=pair?JSON.stringify([pair.playId,pair.mode,pair.next.resourceId]):null;
      await pause(500);
    }
  }
}catch(e){const message=safeError(e);if(!report.errors.includes(message))recordError(message);if(!stopped())process.exitCode=1;}
finally{
  clearInterval(controllerTimer);
  closingInput=true;
  inputControl?.close();
  worker?.close();
  try{
    const owns=await ownsController();
    if(nativeMonitoring){if(owns)await client.evaluate('automixProbe.endNativeMonitor()');nativeMonitoring=false;}
    if(original&&!owns){report.controllerOwnershipLost=true;recordError('Controller ownership lost; skip playback recovery to avoid changing another controller');}
    if(owns&&test&&original&&Number.isFinite(originalPosition)){
      await client.evaluate('automixProbe.pause()');await client.evaluate('automixProbe.setTemporaryVolume(0)');
      await selectPaused(original.current.resourceId);await client.evaluate(`automixProbe.seekAndWait(${originalPosition})`);
      await client.evaluate(`automixProbe.setTemporaryFade(${original.audioSettings.playFade})`);await client.evaluate(`automixProbe.setTemporaryVolume(${original.audioSettings.playingVolume})`);
      if(original.playingState==='playing')await client.evaluate('automixProbe.play()');report.restored=true;
    }else if(owns&&activeSettings){
      await recoverActiveHandoff();
    }
    if(client){if(owns&&recoveryToken)await client.evaluate(`automixProbe.cancelHandoffRecovery(${JSON.stringify(recoveryToken)})`);const s=await state();report.final={track:s.current,state:s.playingState,audioSettings:s.audioSettings,position:await client.evaluate('automixProbe.readStoredPosition()')};}
  }catch(e){recordError('Recovery failed: '+safeError(e));process.exitCode=1;}
  if(controllerToken){try{await client.evaluate(`automixProbe.releaseController(${JSON.stringify(controllerToken)})`);}catch{}}
  client?.close();report.finishedUtc=new Date().toISOString();report.stopped=stopped();
  report.totalTransitions=completedTransitions;report.historyLimits={transitions:100,events:1000,errors:100};
  fs.writeFileSync(path.join(directory,test?'memory-transition-test.json':'memory-automix-report.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify({transitionsCompleted:completedTransitions,restored:report.restored,audioFilesWritten:0,errors:report.errors}));
}
