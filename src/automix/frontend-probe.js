// SPDX-License-Identifier: GPL-2.0-or-later
// Copyright (c) 2026 情绪零碎の佳 (Jia060117)
/* Execute in the NetEase MAIN renderer DevTools console.
 * Local diagnostic only. No network requests or playback commands on startup.
 * The existing webpack module cache is inspected; existing modules are not loaded.
 */
(() => {
  'use strict';
  if (window.automixProbe?.version === 28) {
    const previous = window.automixProbe.inspect();
    if (previous.snapshot || window.automixProbe.controllerStatus?.().active) return previous;
    // The probe may have loaded before the player store entered webpack's
    // cache. Reinstall it on the next inspection after the page finishes.
    window.automixProbe.dispose?.();
  }
  // Inspection may continue while an older controller runs. Installation of
  // new controls is deferred until its lease is released.
  if (window.automixProbe?.controllerStatus?.().active) return window.automixProbe.inspect();
  window.automixProbe?.dispose?.();
  const queue = window.webpackJsonp;
  let runtime;
  if (queue && typeof queue.push === 'function') {
    const id = 'automix_probe_' + Date.now() + '_' + Math.random().toString(36).slice(2);
    queue.push([[id], { [id]: (module, exports, require) => { runtime = require; } }, [[id]]]);
  }
  const cache = runtime && runtime.c;
  // These bindings are verified per desktop build. Unknown client versions
  // must not reuse module numbers from a different build.
  const clientVersion = /NeteaseMusicDesktop\/([\d.]+)/i.exec(navigator.userAgent)?.[1] || null;
  const bindingsByVersion = {
    '3.1.40.205461': {selector:163,progress:111,quality:38,adjust:57,refresh:75,rights:33},
    '3.1.41.205564': {selector:176,progress:148,quality:41,adjust:59,refresh:86,rights:34}
  };
  const bindings = bindingsByVersion[clientVersion || '3.1.40.205461'];
  let sdk, bridge, storeApi;
  let sourceModule, sourceModuleId;
  const preparedSources = new Map();
  let recoveryLease = null;
  let controllerLease = null;
  function controllerActive(){if(controllerLease&&controllerLease.expiresAt<=performance.now())controllerLease=null;return !!controllerLease;}
  let nativeMonitor = null;
  async function stopNativeMonitor() {
    const m=nativeMonitor;if(!m)return;
    nativeMonitor=null;clearTimeout(m.timer);
    bridge.removeRegisterCall('AudioData','audioplayer',m.callback);
    for(const p of m.packets)p.data.fill(0);m.packets.length=0;
    let timer;try{await Promise.race([sdk.setAudioDataEnableState(false),new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('Audio toggle timed out')),3000);})]);}finally{clearTimeout(timer);}
  }
  const candidates = [];
  function consider(value, moduleId) {
    if (!value || (typeof value !== 'object' && typeof value !== 'function')) return;
    if (value.AudioPlayer && typeof value.AudioPlayer.seek === 'function') {
      sdk = value.AudioPlayer;
      bridge = value.Bridge;
    }
    if (typeof value.getStore === 'function') {
      try {
        const state = value.getStore();
        if (state && state.playing && state.playingList) {
          candidates.push(String(moduleId));
          storeApi = value;
        }
      } catch (_) { /* Non-player stores are ignored. */ }
    }
  }
  for (const [moduleId, module] of Object.entries(cache || {})) {
    const exports = module.exports;
    try {
      if (typeof exports?.f === 'function' && typeof exports?.h === 'function' &&
          exports.f.toString().includes('requestSoundQuality') && exports.h.toString().includes('preloadIndex')) {
        sourceModule=exports;sourceModuleId=moduleId;
      }
      consider(exports, moduleId);
      for (const key of Object.keys(exports || {}).slice(0, 100)) {
        // Only inspect cached exports, never invoke exported functions.
        try { consider(exports[key], moduleId); } catch (_) {}
      }
    } catch (_) {}
  }
  function state() {
    if (!bindings) throw new Error('尚未适配网易云 ' + clientVersion + '；请使用 3.1.40.205461 或 3.1.41.205564。');
    if (!storeApi) throw new Error('The loaded player store was not found. Use the main renderer after the application has loaded.');
    return storeApi.getStore();
  }
  function trackSummary(item) {
    if (!item) return null;
    const track = item.track || item;
    return { resourceId: item.resourceId ?? track.id ?? null, name: track.name ?? null,
      durationRaw: track.duration ?? track.dt ?? null, resourceType: item.resourceType ?? null,
      displayOrder: item.displayOrder ?? null, randomOrder: item.randomOrder ?? null };
  }
  const queueModeLabel = mode => ({playCycle:'列表循环',playOrder:'顺序播放',PlayOrder:'顺序播放',playAi:'心动模式'})[mode] || mode;
  let lastProgress = null;
  const positionObserver = (playId, current, cacheProgress, force) => {
    lastProgress = { playId, positionSeconds: current, cacheProgress, force, source:'PlayProgress callback', observedAt: performance.now() };
  };
  const seekObserver = (playId, seekId, code, position) => {
    if (code === 0 && Number.isFinite(position)) lastProgress = {playId,seekId,positionSeconds:position,source:'Seek acknowledgement',observedAt:performance.now()};
  };
  if (bridge?.appendRegisterCall) bridge.appendRegisterCall('PlayProgress', 'audioplayer', positionObserver);
  if (bridge?.appendRegisterCall) bridge.appendRegisterCall('Seek', 'audioplayer', seekObserver);
  function inspect() {
    let snapshot = null, error = null;
    try {
      const s = state(), p = s.playing;
      snapshot = {
        playId: p.playId, playingStateRaw: p.playingState,
        playingState: ({'-1':'ended',0:'stopped',1:'paused',2:'playing'})[p.playingState] || 'unknown', playingModeRaw: p.playingMode,
        queueModeLabel:queueModeLabel(p.playingMode),queueSource:'playingList.curPlayingList',
        isLoadingFirst: p.isLoadingFirst, current: trackSummary(p.curPlaying),
        audioSettings: {playingVolume:p.playingVolume,playFade:s.setting?.playFade},
        reportedPosition: lastProgress?.playId === p.playId ? lastProgress : null,
        queue: (s.playingList.curPlayingList || []).slice(0, 30).map(trackSummary),
        note: 'Current playback queue, not a displayed source playlist. Heart mode may update this queue. Shuffle/FM are not supported.'
      };
    } catch (e) { error = e.message; }
    return { capturedUtc: new Date().toISOString(), userAgent: navigator.userAgent,
      nativeChannelPresent: !!(window.channel && window.channel.call),
      webpackCaptured: !!cache, cachedModuleCount: Object.keys(cache || {}).length,
      audioPlayerSdkFound: !!sdk, bridgeFound: !!bridge, storeCandidates: candidates,
      sourceModuleFound:!!sourceModule,sourceModuleId,clientVersion,clientSupported:!!bindings,
      snapshot, error, note: 'Control success is recorded by the calling test, not inferred from interface presence.' };
  }
  function dispatch(action, payload) {
    if (!storeApi || typeof storeApi.getDispatch !== 'function') throw new Error('Player dispatch unavailable.');
    const before = inspect();
    const started = performance.now();
    storeApi.getDispatch()({ type: action, payload });
    return { dispatched: action, before, dispatchMilliseconds: performance.now() - started,
      note: 'Dispatch return is NOT native seek completion or audible output latency. Inspect again after the change.' };
  }
  async function recoverLease() {
    const lease=recoveryLease;if(!lease)return;
    recoveryLease=null;clearTimeout(lease.timer);
    const s=state(),p=s.playing;
    // Restore a muted native stream even if the user switched songs; only resume
    // playback when the paused song belongs to this transition.
    try{if([...lease.temporaryVolumes,...(lease.rampVolumes||[])].some(v=>Math.abs(p.playingVolume-v)<.001))await sdk.setVolume(lease.volume);}
    finally{await sdk.switchEffect(lease.fade);}
    if(lease.trackIds.includes(String(p.curPlaying?.resourceId))&&p.playingState===1)dispatch('playing/resume',{triggerScene:'automix-recovery'});
  }
  let pendingWatch = null;
  const events = [];
  async function watchProgress(seconds = 5) {
    if (!bridge || typeof bridge.appendRegisterCall !== 'function' || typeof bridge.removeRegisterCall !== 'function') throw new Error('Native event bridge unavailable.');
    if (!Number.isFinite(seconds) || seconds < 1 || seconds > 30) throw new Error('Duration must be 1..30 seconds.');
    if (pendingWatch) throw new Error('A progress watch is already active.');
    events.length = 0;
    const callback = (playId, current, cacheProgress, force) => {
      if (events.length < 3000) events.push({ t: performance.now(), playId,
        currentRaw: current, cacheProgressRaw: cacheProgress, force });
    };
    pendingWatch = callback;
    try {
      // Add/remove the same callback. SDK subscribePlayStatus wraps callbacks.
      bridge.appendRegisterCall('PlayProgress', 'audioplayer', callback);
      await new Promise(resolve => setTimeout(resolve, seconds * 1000));
      return { events: events.slice(), note: 'These are reported progress callbacks, not measured speaker output.' };
    } finally {
      // SDK unSubscribePlayStatus removes PlayState only; remove the actual event here.
      bridge.removeRegisterCall('PlayProgress', 'audioplayer', callback);
      pendingWatch = null;
    }
  }
  window.automixProbe = {
    version: 28,
    controllerStatus() {return {active:controllerActive(),remainingMilliseconds:controllerLease?Math.max(0,controllerLease.expiresAt-performance.now()):0};},
    claimController() {
      if(controllerActive()||recoveryLease)throw new Error('已有 Automix 控制进程运行中，请先停止它');
      const token='automix-controller-'+Date.now()+'-'+Math.random().toString(36).slice(2);
      controllerLease={token,expiresAt:performance.now()+60000};return {token};
    },
    renewController(token) {
      if(!controllerActive()||controllerLease.token!==token)throw new Error('Automix controller ownership lost');
      controllerLease.expiresAt=performance.now()+60000;return true;
    },
    ownsController(token) {return controllerActive()&&controllerLease.token===token;},
    releaseController(token) {
      if(!controllerActive())return false;
      if(controllerLease.token!==token)throw new Error('Automix controller token does not match');
      controllerLease=null;return true;
    },
    async beginNativeMonitor(seconds=45) {
      if(nativeMonitor)throw new Error('Native monitor already active');
      if(!Number.isFinite(seconds)||seconds<5||seconds>60||typeof sdk?.setAudioDataEnableState!=='function')throw new Error('Invalid native monitor request');
      const m={packets:[],sequence:0};
      m.callback=p=>{
        if(nativeMonitor!==m||!(p?.data instanceof ArrayBuffer)||p.data.byteLength<256||p.data.byteLength>65536||p.data.byteLength%4)return;
        m.packets.push({data:new Uint8Array(p.data).slice(),pts:p.pts,sequence:++m.sequence,playId:state().playing.playId,observedUtcSeconds:(performance.timeOrigin+performance.now())/1000});
        while(m.packets.length>4)m.packets.shift().data.fill(0);
      };
      nativeMonitor=m;bridge.appendRegisterCall('AudioData','audioplayer',m.callback);
      m.timer=setTimeout(()=>stopNativeMonitor().catch(()=>{}),seconds*1000);
      let timer;
      try{await Promise.race([sdk.setAudioDataEnableState(true),new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('Audio toggle timed out')),3000);})]);return {enabled:true,seconds};}
      catch(e){await stopNativeMonitor();throw e;}finally{clearTimeout(timer);}
    },
    readNativePacket() {
      const m=nativeMonitor,p=m?.packets[m.packets.length-1];if(!p)return null;
      let binary='';for(let i=0;i<p.data.length;i+=8192)binary+=String.fromCharCode(...p.data.subarray(i,i+8192));
      return {base64:btoa(binary),bytes:p.data.length,pts:p.pts,sequence:p.sequence,playId:p.playId,observedUtcSeconds:p.observedUtcSeconds};
    },
    endNativeMonitor: stopNativeMonitor,
    armHandoffRecovery(volume,fade,trackIds,seconds,temporaryVolumes=[0]) {
      if(recoveryLease)throw new Error('Another Automix handoff is already active');
      if(!Number.isFinite(volume)||volume<0||volume>1||typeof fade!=='boolean'||!Array.isArray(trackIds)||trackIds.length!==2||!trackIds.every(id=>state().playingList.curPlayingList.some(t=>String(t.resourceId)===String(id)))||!Number.isFinite(seconds)||seconds<5||seconds>60)throw new Error('Invalid handoff recovery settings');
      if(!Array.isArray(temporaryVolumes)||temporaryVolumes.length<1||temporaryVolumes.length>2||!temporaryVolumes.every(v=>Number.isFinite(v)&&v>=0&&v<=.01))throw new Error('Invalid temporary recovery volumes');
      const token='lease_'+Date.now()+'_'+Math.random().toString(36).slice(2);
      recoveryLease={token,volume,fade,trackIds:trackIds.map(String),temporaryVolumes:temporaryVolumes.slice()};
      recoveryLease.timer=setTimeout(()=>recoverLease().catch(()=>{}),seconds*1000);
      return {token,timeoutSeconds:seconds};
    },
    cancelHandoffRecovery(token) {
      if(!recoveryLease)return false;
      if(token!==recoveryLease.token)throw new Error('Handoff recovery token does not match');
      clearTimeout(recoveryLease.timer);recoveryLease=null;return true;
    },
    async restoreHandoffVolume(token) {
      const lease=recoveryLease;if(!lease||lease.token!==token)throw new Error('Handoff recovery token does not match');
      lease.cancelRamp=true;
      const value=state().playing.playingVolume;
      const ours=[...lease.temporaryVolumes,...(lease.rampVolumes||[])].some(v=>Math.abs(value-v)<.001);
      if(ours)await this.setTemporaryVolume(lease.volume);
      return {restored:ours,preservedUserVolume:!ours};
    },
    async rampHandoffVolume(options) {
      const lease=recoveryLease;
      if(!options||!lease||lease.token!==options.recoveryToken||!this.ownsController(options.controllerToken)||typeof options.playId!=='string'||!Number.isFinite(options.from)||options.from<0||options.from>1||!Number.isFinite(options.to)||options.to!==lease.volume||!Number.isFinite(options.durationMilliseconds)||options.durationMilliseconds<100||options.durationMilliseconds>1000)throw new Error('Invalid guarded volume ramp');
      if(lease.ramping)throw new Error('Volume ramp already active');
      const p=state().playing;
      if(p.playId!==options.playId||p.playingState!==2||Math.abs(p.playingVolume-options.from)>.001)throw new Error('Playback changed before volume ramp');
      lease.ramping=true;lease.rampVolumes=[options.from];lease.cancelRamp=false;
      const started=performance.now(),trace=[];let last=options.from,maxGainStep=0;
      const smooth=u=>u*u*u*(10+u*(-15+6*u));
      // Nested CEF timers can be clamped to ~16 ms and stretch a bounded
      // ramp past the PCM fade. Posted tasks yield to native replies and user
      // actions without relying on that timer. Lifetime is only this ramp.
      const channel=typeof MessageChannel==='function'?new MessageChannel():null;
      const tick=()=>channel?new Promise(resolve=>{
        const deadline=performance.now()+4;
        channel.port1.onmessage=()=>{if(performance.now()>=deadline){channel.port1.onmessage=null;resolve();}else channel.port2.postMessage(0);};
        channel.port2.postMessage(0);
      }):new Promise(resolve=>setTimeout(resolve,4));
      try{
        while(true){
          const s=state().playing;
          if(recoveryLease!==lease||lease.cancelRamp||!this.ownsController(options.controllerToken))throw new Error('Volume ramp ownership lost');
          if(s.playId!==options.playId||s.playingState!==2||!lease.rampVolumes.some(v=>Math.abs(s.playingVolume-v)<.001))throw new Error('User changed playback during volume ramp');
          const elapsed=performance.now()-started,u=Math.min(1,elapsed/options.durationMilliseconds);
          const desired=options.from+(options.to-options.from)*smooth(u);
          // Bound every individual gain step even if CEF timers or IPC stall.
          const value=Math.min(desired,last+(options.to-options.from)*.015);maxGainStep=Math.max(maxGainStep,value-last);
          lease.rampVolumes.push(value);if(lease.rampVolumes.length>20)lease.rampVolumes.shift();
          const before=performance.now();await this.setTemporaryVolume(value);trace.push({elapsedMilliseconds:performance.now()-started,volume:value,ackMilliseconds:performance.now()-before});if(trace.length>400)trace.shift();last=value;
          if(value>=options.to-1e-10)break;
          if(performance.now()-started>options.durationMilliseconds+1000)throw new Error('Volume ramp exceeded timing budget');
          await tick();
        }
        return {curve:'quintic',durationMilliseconds:performance.now()-started,requestedMilliseconds:options.durationMilliseconds,steps:trace.length,maxGainStep,trace};
      }finally{lease.ramping=false;if(channel){channel.port1.close();channel.port2.close();}}
    },
    inspect,
    readPlaybackPair() {
      const s=state(),p=s.playing,list=s.playingList.curPlayingList;
      if(!['playCycle','playOrder','PlayOrder','playAi'].includes(p.playingMode))throw new Error('请选择列表循环、顺序播放或心动模式；随机、单曲循环和 FM 暂未适配');
      if(!p.playId||p.isLoadingFirst)throw new Error('Current playback instance is still loading');
      const current=list.find(item=>String(item.resourceId)===String(p.curPlaying?.resourceId));
      const selector=cache?.[bindings.selector]?.exports?.a;
      if(!current||typeof selector!=='function')throw new Error('Current playback queue next-track selector unavailable');
      const next=selector(p.playingMode,list,current,1);
      if(!next||String(next.resourceId)===String(current.resourceId))throw new Error('Two distinct queued tracks required');
      return {playId:p.playId,mode:p.playingMode,modeLabel:queueModeLabel(p.playingMode),current:trackSummary(current),next:trackSummary(next),queueLength:list.length,nativeSelector:true,queueSource:'playingList.curPlayingList',dynamicQueue:p.playingMode==='playAi'};
    },
    async observeAudioStats(seconds=3) {
      if(!Number.isFinite(seconds)||seconds<1||seconds>5)throw new Error('Statistics window must be 1..5 seconds');
      const playId=state().playing.playId,volume=state().playing.playingVolume;
      const stats={playId,volume,packetCount:0,totalBytes:0,packetsWithNonzeroBytes:0,firstPts:null,lastPts:null,byteSizes:{},signed16RmsSum:0,signed16Peak:0};
      const callback=packet=>{
        if(!(packet?.data instanceof ArrayBuffer))return;
        const bytes=new Uint8Array(packet.data);let nonzero=false;
        for(let i=0;i<bytes.length;i++)if(bytes[i]!==0){nonzero=true;break;}
        stats.packetCount++;stats.totalBytes+=bytes.length;stats.packetsWithNonzeroBytes+=Number(nonzero);
        stats.byteSizes[bytes.length]=(stats.byteSizes[bytes.length]||0)+1;
        if(stats.firstPts===null)stats.firstPts=packet.pts;stats.lastPts=packet.pts;
        if(bytes.length%2===0){
          const values=new Int16Array(packet.data);let energy=0,peak=0;
          for(let i=0;i<values.length;i++){const v=values[i]/32768;energy+=v*v;peak=Math.max(peak,Math.abs(v));}
          stats.signed16RmsSum+=Math.sqrt(energy/Math.max(1,values.length));stats.signed16Peak=Math.max(stats.signed16Peak,peak);
        }
        // No audio copy, packet list, base64 payload, or persistent cache is retained.
      };
      let timer;
      const toggle=enabled=>Promise.race([sdk.setAudioDataEnableState(enabled),new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('Audio toggle timed out')),3000);})]).finally(()=>clearTimeout(timer));
      bridge.appendRegisterCall('AudioData','audioplayer',callback);
      try{
        await toggle(true);await new Promise(resolve=>setTimeout(resolve,seconds*1000));
        if(state().playing.playId!==playId)throw new Error('Track changed during audio statistics');
        return {...stats,signed16RmsMean:stats.signed16RmsSum/Math.max(1,stats.packetCount),note:'Nonzero callback bytes do not verify PCM format, continuity, quality, or next-song availability. Signed16 amplitude is an unverified format hypothesis. Audio data is not retained.'};
      }finally{bridge.removeRegisterCall('AudioData','audioplayer',callback);await toggle(false);}
    },
    readStoredPosition() {
      const playing=state().playing,progress=cache?.[bindings.progress]?.exports?.b;
      let value;
      if(clientVersion==='3.1.41.205564'){
        if(typeof progress!=='function')throw new Error('Player progress getter unavailable');
        const sample=progress();
        if(!playing.playId||String(sample?.playId)!==String(playing.playId))throw new Error('播放器进度尚未就绪，请先播放一首歌曲。');
        value=sample.current;
      }else{
        if(typeof progress?.getValue!=='function')throw new Error('Player progress subject unavailable');
        value=progress.getValue();
      }
      if(!Number.isFinite(value)||value<0)throw new Error('Player progress value is invalid');
      return {playId:playing.playId,value,source:clientVersion==='3.1.41.205564'?'Player progress getter':'Player progress subject',note:'UI progress, not measured speaker position'};
    },
    readPosition() {
      const playId = state().playing.playId;
      const position = lastProgress?.playId === playId ? lastProgress : null;
      return { playId, value: position?.positionSeconds ?? null,
        source: position?.source ?? null, ageMilliseconds: position ? performance.now()-position.observedAt : null,
        note: 'Last reported progress or successful seek acknowledgement. Paused seeking may have no progress callback. Not speaker position.' };
    },
    async seekAndWait(seconds) {
      if (!bridge?.appendRegisterCall || !bridge?.removeRegisterCall) throw new Error('Event bridge unavailable.');
      let timer, resolveAck;
      const playId = state().playing.playId, started = performance.now();
      const ack = new Promise(resolve => { resolveAck = resolve; });
      const callback = (id, seekId, code, position) => {
        if (id === playId && Math.abs(position - seconds) < 0.25) resolveAck({playId:id,seekId,code,positionSeconds:position,ackMilliseconds:performance.now()-started});
      };
      bridge.appendRegisterCall('Seek','audioplayer',callback);
      try {
        const command = this.seek(seconds);
        const completion = await Promise.race([ack,new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('Seek acknowledgement timed out')),5000);})]);
        if (completion.code !== 0) throw new Error('Native seek failed with code '+completion.code);
        return {command,completion,note:'Native acknowledgement latency, NOT audible output latency.'};
      } finally { clearTimeout(timer); bridge.removeRegisterCall('Seek','audioplayer',callback); }
    },
    async watchAudioData(seconds = 3, enable = false) {
      if (!bridge?.appendRegisterCall) throw new Error('Event bridge unavailable.');
      if (!Number.isFinite(seconds) || seconds < 1 || seconds > 10) throw new Error('Duration must be 1..10 seconds.');
      if (enable && typeof sdk?.setAudioDataEnableState !== 'function') throw new Error('Audio data toggle unavailable.');
      const frames = [];
      let frameCount = 0;
      const packetMetadata = p => ({keys:Object.keys(p||{}).slice(0,8),dataType:Object.prototype.toString.call(p?.data),dataLength:p?.data?.byteLength??p?.data?.length??null,pts:p?.pts??null});
      async function toggle(enabled) {
        let timer;
        try { return await Promise.race([sdk.setAudioDataEnableState(enabled),new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('Audio toggle timed out')),3000);})]); }
        finally { clearTimeout(timer); }
      }
      const callback = (...args) => {
        frameCount++;
        if (frames.length < 100) frames.push(args.map(x => ({type:typeof x,array:Array.isArray(x),byteLength:x?.byteLength??null,length:x?.length??null,keys:x && typeof x==='object' ? Object.keys(x).slice(0,8) : [],
          observedAt:performance.now(),packets: Array.isArray(x) ? x.slice(0,4).map(packetMetadata) : [packetMetadata(x)]})));
      };
      bridge.appendRegisterCall('AudioData','audioplayer',callback);
      try {
        if (enable) await toggle(true);
        await new Promise(resolve=>setTimeout(resolve,seconds*1000));
        return {enabledDuringWatch:enable,frameCount,recordedFrameCount:frames.length,frames,note:'Packet metadata only; sample values are not saved. The enabled test disables its capture after observation.'};
      }
      finally {
        bridge.removeRegisterCall('AudioData','audioplayer',callback);
        if (enable) await toggle(false);
      }
    },
    async nextAndWait() {
      const previous = state().playing.playId, started = performance.now();
      const command = dispatch('playingList/jump2Track', {flag:1,type:'call',triggerScene:'automix-probe'});
      while (performance.now()-started < 8000) {
        await new Promise(resolve=>setTimeout(resolve,100));
        const p = state().playing;
        if (p.playId && p.playId !== previous && !p.isLoadingFirst && p.playingState === 2)
          return {command,completion:{previousPlayId:previous,playId:p.playId,current:trackSummary(p.curPlaying),stateObservedMilliseconds:performance.now()-started},note:'Renderer state observation, not an acoustic measurement.'};
      }
      throw new Error('Next track did not reach a new loaded playing state within 8 seconds.');
    },
    async captureAudio(seconds = 12, startSeconds = 18) {
      if (!Number.isFinite(seconds) || seconds < 1 || seconds > 15) throw new Error('Capture duration must be 1..15 seconds.');
      if (!Number.isFinite(startSeconds) || startSeconds < 0) throw new Error('Invalid start position.');
      if (typeof sdk?.setAudioDataEnableState !== 'function') throw new Error('Audio data toggle unavailable.');
      const playId = state().playing.playId, packets = [], originalFade = state().setting?.playFade;
      if (typeof originalFade !== 'boolean') throw new Error('Cannot identify original fade setting.');
      let bytes = 0, overflow = false;
      await this.setTemporaryFade(false);
      this.pause();
      const callback = packet => {
        if (!(packet?.data instanceof ArrayBuffer)) return;
        if (bytes + packet.data.byteLength > 4000000) { overflow = true; return; }
        const data = new Uint8Array(packet.data);
        let binary = '';
        for (let i=0; i<data.length; i+=8192) binary += String.fromCharCode(...data.subarray(i,i+8192));
        bytes += data.length;
        packets.push({pts:packet.pts,observedAt:performance.now(),base64:btoa(binary)});
      };
      try {
        await this.seekAndWait(startSeconds);
        bridge.appendRegisterCall('AudioData','audioplayer',callback);
        await sdk.setAudioDataEnableState(true);
        this.play();
        await new Promise(resolve=>setTimeout(resolve,seconds*1000));
        if (state().playing.playId !== playId) throw new Error('Song changed during capture.');
        if (overflow) throw new Error('Capture size limit exceeded.');
        return {playId,startSeconds,requestedSeconds:seconds,bytes,packets,fadeDisabledDuringCapture:true,originalFade,note:'Raw audio bytes; format must be verified before playback. Capture ends paused and restores fade.'};
      } finally {
        this.pause();
        bridge.removeRegisterCall('AudioData','audioplayer',callback);
        try { await sdk.setAudioDataEnableState(false); }
        finally { await this.setTemporaryFade(originalFade); }
      }
    },
    async setTemporaryFade(enabled) {
      if (typeof enabled !== 'boolean' || typeof sdk?.switchEffect !== 'function') throw new Error('Fade control unavailable.');
      let timer;
      try { return await Promise.race([sdk.switchEffect(enabled),new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('Fade control timed out')),3000);})]); }
      finally { clearTimeout(timer); }
    },
    async playbackInfo() {
      const result=await Promise.race([sdk.getPlaybackInfo({playId:state().playing.playId}),new Promise((_,reject)=>setTimeout(()=>reject(new Error('Playback info timed out')),3000))]);
      const formats={};
      for(const name of ['sourceAudioFormat','playAudioFormat','deviceAudioFormat']){
        const value=result?.[name];
        formats[name]=value && typeof value==='object'?Object.fromEntries(Object.entries(value).filter(([key,val])=>!(/url|path|token/i.test(key)) && ['boolean','number','string'].includes(typeof val))):value;
      }
      return {keys:Object.keys(result||{}),formats,fields:Object.fromEntries(Object.entries(result||{}).filter(([key,value])=>/cached|sample|channel|format|bitrate|codec|preload|quality/i.test(key) && ['boolean','number','string'].includes(typeof value) && !/url|path/i.test(key)))};
    },
    async selectNextAndWait(expected) {
      if(!expected||typeof expected.playId!=='string'||typeof expected.mode!=='string'||!/^\d+$/.test(String(expected.nextResourceId)))throw new Error('Invalid expected playback pair');
      const pair=this.readPlaybackPair();
      if(pair.playId!==expected.playId||pair.mode!==expected.mode||String(pair.next.resourceId)!==String(expected.nextResourceId))throw new Error('Playback queue changed before native selection; discard transition');
      // Validation and dispatch run in one renderer turn. Keep the native
      // playing-list action so heart-mode recommendation subscriptions still run.
      return this.selectTrackAndWait(expected.nextResourceId);
    },
    async selectTrackAndWait(resourceId) {
      const item=state().playingList.curPlayingList.find(x=>String(x.resourceId)===String(resourceId));
      if(!item)throw new Error('Track is outside the current queue');
      dispatch('playing/playOneTrackInPlayingList',{item,switchType:'call',flag:1,triggerScene:'automix-probe'});
      const started=performance.now();
      while(performance.now()-started<8000){
        await new Promise(r=>setTimeout(r,50));
        const p=state().playing;
        if(String(p.curPlaying?.resourceId)===String(resourceId)&&p.playId&&!p.isLoadingFirst&&p.playingState===2)return {playId:p.playId,track:trackSummary(p.curPlaying)};
      }
      throw new Error('Selected queued track did not reach loaded playback');
    },
    async setTemporaryVolume(volume) {
      if(!Number.isFinite(volume)||volume<0||volume>1)throw new Error('Volume must be 0..1');
      let timer;
      try{return await Promise.race([sdk.setVolume(volume),new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('Volume control timed out')),3000);})]);}
      finally{clearTimeout(timer);}
    },
    async probePreload(seconds=3) {
      if (!sourceModule) throw new Error('Normal player source module unavailable.');
      if (!Number.isFinite(seconds) || seconds<1 || seconds>5) throw new Error('Preload observation must be 1..5 seconds.');
      if (state().playing.playingState !== 1) throw new Error('Preload probe requires a paused player.');
      const current=state().playing.playId,requests=[];let audioFrames=0;
      const fetchObserver=params=>requests.push({curPlayId:params?.curPlayId,preloadIndex:params?.preloadIndex,keys:Object.keys(params||{})});
      const audioObserver=()=>audioFrames++;
      bridge.appendRegisterCall('FetchPreloadInfo','audioplayer',fetchObserver);
      bridge.appendRegisterCall('AudioData','audioplayer',audioObserver);
      try {
        await sdk.setAudioDataEnableState(true);
        await Promise.race([sourceModule.h({curPlayId:current,preloadIndex:0}),new Promise((_,reject)=>setTimeout(()=>reject(new Error('Normal preload request timed out')),8000))]);
        await new Promise(r=>setTimeout(r,seconds*1000));
        if(state().playing.playId!==current)throw new Error('Track changed during preload observation');
        return {currentPlayId:current,normalPreloadRequestCompleted:true,pausedAudioFrames:audioFrames,requests,note:'Preload request completion does not prove cached bytes or decoded PCM are available.'};
      } finally {
        bridge.removeRegisterCall('FetchPreloadInfo','audioplayer',fetchObserver);
        bridge.removeRegisterCall('AudioData','audioplayer',audioObserver);
        await sdk.setAudioDataEnableState(false);
      }
    },
    async prepareSource(resourceId,refresh = false) {
      if (!sourceModule) throw new Error('Normal player source module unavailable.');
      const s=state(),p=s.playing;
      const item=s.playingList.curPlayingList.find(x=>String(x.resourceId)===String(resourceId));
      if(!item)throw new Error('Only tracks already in the current queue can be analysed.');
      if(typeof refresh!=='boolean')throw new Error('Refresh must be boolean');
      const qualityApi=cache[bindings.quality]?.exports,qualityAdjust=cache[bindings.adjust]?.exports;
      if(typeof qualityApi?.e!=='function'||typeof qualityAdjust?.b!=='function')throw new Error('Normal quality policy modules unavailable.');
      const setting=s.setting.quantity;
      const rawQuality=qualityApi.e(s.host.isAnonymous?setting.listenAnon:setting.listenReg);
      const quality=qualityAdjust.b({...rawQuality,quality:rawQuality.bitRate},p.curPlaying);
      if(refresh){
        // The ordinary factory can restore an expired URL from native disk cache.
        // Use the client's existing RPC refresh option, then seed its source cache
        // with that unmodified response; the factory still evaluates normal policy.
        const api=cache[bindings.refresh]?.exports,rights=cache[bindings.rights]?.exports;
        if(typeof api?.a!=='function'||!api.a.toString().includes('skipLocalRpcCache')||typeof rights?.l!=='function'||typeof rights?.g!=='function'||typeof sourceModule.g?.set!=='function')throw new Error('Normal source refresh unavailable');
        const id=item.trackId ?? item.track?.id ?? item.resourceId;
        const fresh=await api.a({ids:id,soundQuality:quality,trialMode:item.fromInfo?.trialMode},true);
        if(fresh?.code!==200||!fresh.url||String(fresh.id)!==String(id))throw new Error('Normal source refresh rejected');
        const member=s.host.isVinylVip||s.host.isPlusVip||s.host.isMusicPackage;
        const isTryOrFullTryTrack=!!(rights.l(item.track||{privilege:null},member)||rights.g(item.track||{privilege:null}));
        sourceModule.g.set(id,{...fresh,requestSoundQuality:quality,isTryOrFullTryTrack});
      }
      let result,timer;
      try{result=await Promise.race([sourceModule.f({track:item,requestSoundQuality:quality,isNextTrack:String(item.resourceId)!==String(p.curPlaying?.resourceId)}),new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('Normal source request timed out')),10000);})]);}
      finally{clearTimeout(timer);}
      if(!result?.canPlay)throw new Error('Normal client playback rights do not allow this track.');
      const info=result.playInfo;
      if(info?.freeTrialInfo && Object.keys(info.freeTrialInfo).length)throw new Error('Trial-only source is excluded from this prototype.');
      if(!info?.musicurl)throw new Error('Normal source has no online media URL.');
      preparedSources.set(String(item.resourceId),info);
      return {track:trackSummary(item),canPlay:true,trial:false,format:info.format,streamType:info.type,bitrate:info.bitrate,fileSize:info.fileSize,durationRaw:info.songDuration,sourceHost:new URL(info.musicurl).hostname,note:'Source obtained via the existing client playback/quality policy. Signed URLs are kept in memory only.'};
    },
    sourceAccess(resourceId) {
      const info=preparedSources.get(String(resourceId));
      if(!info)throw new Error('Prepare this normally playable source first.');
      return {url:info.musicurl,headers:info.extHeader?JSON.parse(info.extHeader):{}};
    },
    async readPreparedSourceBase64(resourceId,maxBytes=25165824) {
      if(!Number.isInteger(maxBytes)||maxBytes<16384||maxBytes>67108864)throw new Error('Memory source limit must be 16KiB..64MiB');
      const info=preparedSources.get(String(resourceId));
      if(!info?.musicurl)throw new Error('Prepare the normally playable source first');
      if(Number(info.fileSize)>maxBytes){preparedSources.delete(String(resourceId));throw new Error('Normal source exceeds memory budget');}
      const url=new URL(info.musicurl);
      if(!['http:','https:'].includes(url.protocol)||!/(^|\.)music\.(126\.net|163\.com)$/.test(url.hostname))throw new Error('Unsupported media host');
      const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),30000),parts=[];
      let joined,reader,count=0,expectedBytes=null;
      try{
        const response=await fetch(info.musicurl,{headers:{Range:'bytes=0-'+(maxBytes-1)},signal:controller.signal,redirect:'error'});
        if(!response.ok)throw new Error('Media HTTP '+response.status);
        if(Number(response.headers.get('content-length'))>maxBytes)throw new Error('Media exceeds memory budget');
        const range=response.headers.get('content-range');
        if(response.status===206){
          const match=/^bytes 0-(\d+)\/(\d+)$/.exec(range||'');
          if(!match||Number(match[2])>maxBytes||Number(match[1])+1!==Number(match[2]))throw new Error('Incomplete source range');
          expectedBytes=Number(match[2]);
        }
        reader=response.body.getReader();
        while(true){const next=await reader.read();if(next.done)break;parts.push(next.value);count+=next.value.byteLength;if(count>maxBytes)throw new Error('Media exceeds memory budget');}
        if(!count)throw new Error('Empty source');
        if(expectedBytes!==null&&count!==expectedBytes)throw new Error('Source body length differs from declared complete range');
        joined=new Uint8Array(count);let offset=0;
        for(const part of parts){joined.set(part,offset);offset+=part.length;part.fill(0);}
        let binary='';for(let i=0;i<joined.length;i+=8192)binary+=String.fromCharCode(...joined.subarray(i,i+8192));
        return {base64:btoa(binary),bytes:count,httpStatus:response.status,contentType:response.headers.get('content-type'),sourceHost:url.hostname};
      }finally{
        clearTimeout(timer);controller.abort();try{await reader?.cancel();}catch(_){}
        for(const part of parts)part.fill(0);joined?.fill(0);
        preparedSources.delete(String(resourceId));
      }
    },
    pause: () => dispatch('playing/pause', {}),
    play: () => dispatch('playing/resume', { triggerScene: 'automix-probe' }),
    seek(seconds) {
      if (!Number.isFinite(seconds) || seconds < 0) throw new Error('Use a finite nonnegative time in seconds.');
      const p = state().playing;
      if (!p.playId || p.isLoadingFirst || p.restoreResource) throw new Error('Wait for the current track to finish loading before seeking.');
      return dispatch('playing/setPlayingPosition', { duration: seconds });
    },
    watchProgress,
    dispose: () => {
      if(controllerActive())throw new Error('Stop the active Automix controller before disposing');
      stopNativeMonitor().catch(()=>{});
      if(recoveryLease)recoverLease().catch(()=>{});
      bridge?.removeRegisterCall?.('PlayProgress','audioplayer',positionObserver);
      bridge?.removeRegisterCall?.('Seek','audioplayer',seekObserver);
      delete window.automixProbe;
    },
    exportReport: () => JSON.stringify(inspect(), null, 2)
  };
  const result = inspect();
  console.log('Automix probe loaded. Controls run only when explicitly called.', result);
  return result;
})();
