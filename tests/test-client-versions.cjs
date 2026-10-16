// SPDX-License-Identifier: GPL-2.0-or-later
// Copyright (c) 2026 情绪零碎の佳 (Jia060117)
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const code=fs.readFileSync('src/automix/frontend-probe.js','utf8');
function fixture(version){
  const modern=version==='3.1.41.205564',ids=modern?[176,148,41,59,86,34,163]:[163,111,38,57,75,33,101];
  const list=[1,2].map(id=>({resourceId:String(id),trackId:String(id),track:{id:String(id),name:'fixture '+id}}));
  const state={playing:{playId:'instance-A',playingState:2,playingMode:'playAi',curPlaying:list[0]},playingList:{curPlayingList:list},host:{isAnonymous:false},setting:{quantity:{listenReg:'standard'}}};
  const progress={playId:'instance-A',current:12.5};let refreshes=0,trial=false,controls=0;
  const source={g:new Map(),f:async function({track,requestSoundQuality}){assert.equal(requestSoundQuality,'standard');return {canPlay:true,playInfo:{musicurl:'https://m7.music.126.net/fixture',freeTrialInfo:trial?{start:0,end:30}:null}};},h:async function({preloadIndex}){}};
  const cache={4:{exports:{AudioPlayer:{seek(){}},Bridge:{appendRegisterCall(){},removeRegisterCall(){}}}},8:{exports:{getStore:()=>state,getDispatch:()=>()=>{controls++;}}}};
  cache[ids[0]]={exports:{a:(mode,queue,current,flag)=>{assert.equal(mode,'playAi');assert.equal(current,list[0]);assert.equal(flag,1);return queue[1];}}};
  cache[ids[1]]={exports:{b:modern?()=>progress:{getValue:()=>progress.current}}};
  cache[ids[2]]={exports:{e:q=>{assert.equal(q,'standard');return {bitRate:128};}}};
  cache[ids[3]]={exports:{b:q=>{assert.equal(q.quality,128);return 'standard';}}};
  cache[ids[4]]={exports:{a:async function(request,skipLocalRpcCache){assert.equal(skipLocalRpcCache,true);refreshes++;return {id:request.ids,code:200,url:'https://m7.music.126.net/fixture'};}}};
  cache[ids[5]]={exports:{l:()=>false,g:()=>false}};cache[ids[6]]={exports:source};
  const runtime=()=>{throw Error('Uncached modules must not execute');};runtime.c=cache;
  const window={webpackJsonp:[]};window.webpackJsonp.push=p=>Object.values(p[1])[0]({}, {},runtime);
  vm.runInNewContext(code,{window,navigator:{userAgent:'NeteaseMusicDesktop/'+version},performance:{now:()=>0},setTimeout,clearTimeout,URL});
  return {probe:window.automixProbe,progress,source,trial:()=>{trial=true;},refreshes:()=>refreshes,controls:()=>controls};
}
(async()=>{
  for(const version of ['3.1.40.205461','3.1.41.205564']){
    const f=fixture(version),p=f.probe;
    assert.equal(p.inspect().clientVersion,version);assert.equal(p.inspect().clientSupported,true);
    assert.equal(p.readPlaybackPair().next.resourceId,'2');assert.equal(p.readStoredPosition().value,12.5);
    await p.prepareSource('2',true);assert.equal(f.refreshes(),1);assert.equal(f.source.g.get('2').isTryOrFullTryTrack,false);
    f.trial();await assert.rejects(p.prepareSource('2'),/Trial-only/);assert.equal(f.controls(),0);
    if(version==='3.1.41.205564'){
      f.progress.playId='stale-instance';assert.throws(()=>p.readStoredPosition(),/进度尚未就绪/);
      f.progress.playId='instance-A';f.progress.current=NaN;assert.throws(()=>p.readStoredPosition(),/invalid/);
    }
  }
  const f=fixture('3.1.99.999999');assert.equal(f.probe.inspect().clientSupported,false);
  assert.match(f.probe.inspect().error,/尚未适配/);assert.throws(()=>f.probe.readPlaybackPair(),/尚未适配/);
  await assert.rejects(f.probe.prepareSource('2'),/尚未适配/);assert.equal(f.controls(),0);
  console.log('PASS: both desktop builds, source refresh and trial policy, stale progress rejection, unsupported build blocked without playback commands.');
})().catch(e=>{console.error(e);process.exitCode=1;});
