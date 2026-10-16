// SPDX-License-Identifier: GPL-2.0-or-later
// Copyright (c) 2026 情绪零碎の佳 (Jia060117)
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const code=fs.readFileSync('src/automix/frontend-probe.js','utf8');
const timers=new Map(),controls=[];let index=0,refreshCalls=0;
const list=[1,2,3].map(id=>({resourceId:String(id),trackId:String(id),track:{id,name:'T'+id},fromInfo:{trialMode:43}}));
const state={playing:{playId:'a',curPlaying:list[0],playingVolume:0,playingState:1},playingList:{curPlayingList:list},host:{isAnonymous:false,isVinylVip:false},setting:{playFade:true,quantity:{listenReg:'normal'}}};
const source={g:new Map(),f:async function({track,requestSoundQuality}){const d=this.g.get(track.trackId);return {canPlay:d?.code===200,playInfo:{musicurl:d.url,fileSize:d.size}};},h:async function({preloadIndex}){}};
const cache={1:{exports:{AudioPlayer:{seek(){},async setVolume(v){state.playing.playingVolume=v;controls.push(['volume',v]);},async switchEffect(v){controls.push(['fade',v]);}},Bridge:{appendRegisterCall(){},removeRegisterCall(){}}}},8:{exports:{getStore:()=>state,getDispatch:()=>action=>controls.push(['dispatch',action.type])}},38:{exports:{e:()=>({bitRate:320})}},57:{exports:{b:()=> 'standard'}},33:{exports:{l:()=>false,g:()=>false}},75:{exports:{a:async function(request,skipLocalRpcCache){assert.equal(skipLocalRpcCache,true);assert.equal(request.trialMode,43);assert.equal(request.soundQuality,'standard');refreshCalls++;return {id:request.ids,code:200,url:'https://m7.music.126.net/new',size:7};}}},101:{exports:source}};
function runtime(){throw Error('Unexpected module execution')}runtime.c=cache;
const window={webpackJsonp:[]};window.webpackJsonp.push=p=>Object.values(p[1])[0]({}, {},runtime);
vm.runInNewContext(code,{window,navigator:{userAgent:'test'},console:{log(){}},performance:{now:()=>0},setTimeout:(fn,ms)=>{timers.set(++index,{fn,ms});return index;},clearTimeout:id=>timers.delete(id),URL});
const probe=window.automixProbe;
(async()=>{
 assert.equal(controls.length,0);
 await probe.prepareSource('1',true);assert.equal(refreshCalls,1);assert.equal(source.g.get('1').url,'https://m7.music.126.net/new');assert.equal(source.g.get('1').isTryOrFullTryTrack,false);assert.equal(controls.length,0);
 const lease=probe.armHandoffRecovery(.6,true,['1','2'],10);
 assert.throws(()=>probe.armHandoffRecovery(.6,true,['1','2'],10),/already active/);
 assert.throws(()=>probe.cancelHandoffRecovery('wrong'),/token/);
 await [...timers.values()].find(t=>t.ms===10000).fn();
 assert.equal(state.playing.playingVolume,.6);assert.equal(controls.filter(x=>x[0]==='dispatch').length,1);
 assert.equal(probe.cancelHandoffRecovery(lease.token),false);
 controls.length=0;state.playing.curPlaying=list[2];state.playing.playingVolume=0;
 const other=probe.armHandoffRecovery(.4,true,['1','2'],9);await [...timers.values()].find(t=>t.ms===9000).fn();
 assert.equal(state.playing.playingVolume,.4);assert.equal(controls.filter(x=>x[0]==='dispatch').length,0);
 const canceled=probe.armHandoffRecovery(.4,true,['1','2'],8);assert.equal(probe.cancelHandoffRecovery(canceled.token),true);assert.equal([...timers.values()].some(t=>t.ms===8000),false);
 state.playing.curPlaying=list[0];state.playing.playingVolume=.006;controls.length=0;
 probe.armHandoffRecovery(.6,true,['1','2'],7,[0,.006]);await [...timers.values()].find(t=>t.ms===7000).fn();assert.equal(state.playing.playingVolume,.6);
 state.playing.playingVolume=.2;controls.length=0;probe.armHandoffRecovery(.6,true,['1','2'],6,[0,.006]);await [...timers.values()].find(t=>t.ms===6000).fn();assert.equal(state.playing.playingVolume,.2);assert(!controls.some(x=>x[0]==='volume'));
 assert.throws(()=>probe.armHandoffRecovery(.6,true,['1','2'],10,[.1]),/temporary/);
 console.log('PASS: fresh normal RPC response, unchanged quality/trial policy, watchdog restores mute, no forced play after manual track change, concurrent handoff lock, explicit cancellation.');
})().catch(e=>{console.error(e);process.exitCode=1;});
