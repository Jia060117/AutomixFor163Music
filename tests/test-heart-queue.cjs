// SPDX-License-Identifier: GPL-2.0-or-later
// Copyright (c) 2026 情绪零碎の佳 (Jia060117)
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const tracks=Array.from({length:55},(_,i)=>({resourceId:String(1000+i),displayOrder:i,randomOrder:55-i,scene:i?'aiMode':'playlist',aiRcmd:i>0,track:{id:String(1000+i),name:'queue '+i,duration:200000}}));
const state={playing:{playId:'heart-original',playingMode:'playAi',playingState:2,curPlaying:{...tracks[40],displayOrder:-1}},playingList:{curPlayingList:[...tracks]},setting:{playFade:true},'page:playlist':{tracks:[{resourceId:'wrong-playlist-id'}]}};
let selected=0,selectorCalls=0,clockOffset=0;
const selector=(mode,list,current,flag)=>{selectorCalls++;assert.equal(mode,state.playing.playingMode);assert.equal(list,state.playingList.curPlayingList);assert.equal(flag,1);const next=list.filter(t=>t.displayOrder>current.displayOrder).sort((a,b)=>a.displayOrder-b.displayOrder)[0];return next||[...list].sort((a,b)=>a.displayOrder-b.displayOrder)[0];};
const api={getStore:()=>state,getDispatch:()=>a=>{assert.equal(a.type,'playing/playOneTrackInPlayingList');assert.equal(a.payload.flag,1);assert.equal(a.payload.switchType,'call');selected++;state.playing.curPlaying=a.payload.item;state.playing.playId='selected-'+selected;}};
const runtime=()=>{throw Error('Existing modules must not execute')};runtime.c={8:{exports:{a:api}},4:{exports:{AudioPlayer:{seek(){}},Bridge:{appendRegisterCall(){},removeRegisterCall(){}}}},163:{exports:{a:selector}}};
const window={webpackJsonp:[]};window.webpackJsonp.push=p=>Object.values(p[1])[0]({}, {}, runtime);
const ctx=vm.createContext({window,navigator:{userAgent:'Test'},performance:{now:()=>Date.now()+clockOffset},setTimeout,clearTimeout,console:{log(){}}});
vm.runInContext(fs.readFileSync('src/automix/frontend-probe.js','utf8'),ctx);const p=window.automixProbe;
(async()=>{
  let checks=0;
  assert.equal(selected,0);assert.equal(p.version,27);checks++;
  let pair=p.readPlaybackPair();assert.equal(pair.next.resourceId,'1041');assert.equal(pair.queueLength,55);assert.equal(pair.dynamicQueue,true);assert.equal(pair.queueSource,'playingList.curPlayingList');assert.equal(pair.modeLabel,'心动模式');assert.equal(p.inspect().snapshot.queue.length,30);checks++;
  // Recommendations inserted ahead of the preanalysed song must invalidate it.
  state.playingList.curPlayingList.push({resourceId:'9999',displayOrder:40.5,scene:'aiMode',track:{id:'9999',name:'new recommendation',duration:180000}});
  await assert.rejects(p.selectNextAndWait({playId:pair.playId,mode:pair.mode,nextResourceId:pair.next.resourceId}),/queue changed/);assert.equal(selected,0);checks++;
  pair=p.readPlaybackPair();assert.equal(pair.next.resourceId,'9999');await p.selectNextAndWait({playId:pair.playId,mode:pair.mode,nextResourceId:pair.next.resourceId});assert.equal(selected,1);assert.equal(state.playing.playingMode,'playAi');assert.equal(state.playing.curPlaying.scene,'aiMode');checks++;
  pair=p.readPlaybackPair();await assert.rejects(p.selectNextAndWait({...pair,nextResourceId:pair.next.resourceId,playId:'old-instance'}),/queue changed/);assert.equal(selected,1);checks++;
  state.playing.playingMode='playCycle';await assert.rejects(p.selectNextAndWait({playId:pair.playId,mode:pair.mode,nextResourceId:pair.next.resourceId}),/queue changed/);assert.equal(selected,1);checks++;
  for(const mode of ['playCycle','playOrder','PlayOrder']){state.playing.playingMode=mode;assert.equal(p.readPlaybackPair().dynamicQueue,false);}checks++;
  for(const mode of ['playRandom','playFm','playOneCycle','unknown']){state.playing.playingMode=mode;assert.throws(()=>p.readPlaybackPair(),/暂未适配/);}checks++;
  state.playing.playingMode='playAi';state.playing.curPlaying=tracks.at(-1);assert.equal(p.readPlaybackPair().next.resourceId,'1000');checks++;
  state.playing.curPlaying={resourceId:'absent'};assert.throws(()=>p.readPlaybackPair(),/selector unavailable/);checks++;
  await assert.rejects(p.selectNextAndWait({nextResourceId:'x'}),/Invalid expected/);assert.equal(selected,1);checks++;
  const owner=p.claimController();assert(p.controllerStatus().active);assert(p.ownsController(owner.token));assert.throws(()=>p.claimController(),/已有 Automix/);assert.throws(()=>p.dispose(),/active Automix/);checks++;
  assert.throws(()=>p.releaseController('wrong'),/does not match/);assert.throws(()=>p.renewController('wrong'),/ownership lost/);assert(p.ownsController(owner.token));checks++;
  p.version=24;vm.runInContext(fs.readFileSync('src/automix/frontend-probe.js','utf8'),ctx);assert.equal(window.automixProbe,p);assert.equal(p.version,24);p.version=27;checks++;
  clockOffset+=59000;p.renewController(owner.token);clockOffset+=2000;assert(p.ownsController(owner.token));clockOffset+=61000;assert.equal(p.controllerStatus().active,false);assert.throws(()=>p.renewController(owner.token),/ownership lost/);checks++;
  const second=p.claimController();assert.equal(p.ownsController(owner.token),false);assert.equal(p.releaseController(second.token),true);assert.equal(p.controllerStatus().active,false);checks++;
  console.log(JSON.stringify({passed:true,checks,selectorCalls,tests:['current playback queue differs from source playlist','full queue beyond 30 preview items','native selector with current queue entry','dynamic insertion invalidates stale prepared B before dispatch','guarded selection preserves heart mode and recommendation metadata','playId and mode changes rejected','correct lowercase playOrder supported','shuffle/FM/single loop still rejected','native selector used at queue boundary','missing current and malformed pair rejected']}));
})().catch(e=>{console.error(e);process.exitCode=1;});
