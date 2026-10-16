// SPDX-License-Identifier: GPL-2.0-or-later
// Copyright (c) 2026 情绪零碎の佳 (Jia060117)
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
async function scenario(kind){
 const posted=kind.startsWith('posted-');const action=kind.replace(/^posted-/,'');let portsClosed=0;
 let now=0,seq=0,calls=0;const timers=new Map(),volumes=[];const list=[{resourceId:'1'},{resourceId:'2'}];
 const s={playing:{playId:'B',curPlaying:list[1],playingVolume:0,playingState:2},playingList:{curPlayingList:list},setting:{playFade:true}};
 let interrupt=false,p,owner;
 const sdk={seek(){},async setVolume(v){now+=action==='stalled'&&calls++===10?80:1;s.playing.playingVolume=v;volumes.push(v);if(!interrupt&&v>.1){interrupt=true;if(action==='manual')s.playing.playingVolume=.9;if(action==='pause')s.playing.playingState=1;if(action==='track')s.playing.playId='user-track';if(action==='ownership')p.releaseController(owner);}},async switchEffect(){}};
 const runtime=()=>{};runtime.c={1:{exports:{AudioPlayer:sdk,Bridge:{appendRegisterCall(){},removeRegisterCall(){}}}},2:{exports:{getStore:()=>s,getDispatch:()=>()=>{}}}};
 const window={webpackJsonp:[]};window.webpackJsonp.push=p=>Object.values(p[1])[0]({}, {},runtime);
 class FakeChannel {constructor(){let closed=false;this.port1={onmessage:null,close(){closed=true;portsClosed++;}};this.port2={postMessage:()=>{now+=.25;queueMicrotask(()=>{if(!closed)this.port1.onmessage?.();});},close(){closed=true;portsClosed++;}};}}
 const ctx=vm.createContext({window,MessageChannel:posted?FakeChannel:undefined,navigator:{userAgent:'mock'},console:{log(){}},performance:{now:()=>now},setTimeout:(fn,ms)=>{if(ms===4){now+=4;queueMicrotask(fn);return ++seq;}timers.set(++seq,{fn,ms});return seq;},clearTimeout:i=>timers.delete(i)});
 vm.runInContext(fs.readFileSync('src/automix/frontend-probe.js','utf-8'),ctx);p=window.automixProbe;owner=p.claimController().token;const lease=p.armHandoffRecovery(1,true,['1','2'],5).token;
 const options={controllerToken:owner,recoveryToken:lease,playId:'B',from:0,to:1,durationMilliseconds:600};
 if(['manual','pause','track','ownership'].includes(action)){
  await assert.rejects(()=>p.rampHandoffVolume(options),/User changed|ownership lost/);
  const commands=volumes.length;await p.restoreHandoffVolume(lease);
  if(action==='manual'){assert.equal(s.playing.playingVolume,.9);assert.equal(volumes.length,commands);}
  else {assert.equal(s.playing.playingVolume,1);assert.equal(volumes.length,commands+1);}
  if(action==='pause')assert.equal(s.playing.playingState,1);
  if(action==='track')assert.equal(s.playing.playId,'user-track');
 }else{
  const r=await p.rampHandoffVolume(options);assert.equal(volumes.at(-1),1);assert(r.steps>=65);assert(r.maxGainStep<=.015001);assert(volumes.every((v,i)=>i===0||v>=volumes[i-1]));
  assert(r.durationMilliseconds>=600 && r.durationMilliseconds<1000);
 }
 if(posted)assert.equal(portsClosed,2);
 p.cancelHandoffRecovery(lease);p.releaseController(owner);return {kind,commands:volumes.length,passed:true};
}
(async()=>{const results=[];for(const k of ['normal','stalled','manual','pause','track','ownership','posted-normal','posted-stalled','posted-manual'])results.push(await scenario(k));fs.writeFileSync('build/tests/ramp-tests.json',JSON.stringify({passed:true,backendMocked:true,scenarios:results},null,2));console.log(JSON.stringify(results));})().catch(e=>{console.error(e);process.exitCode=1;});
