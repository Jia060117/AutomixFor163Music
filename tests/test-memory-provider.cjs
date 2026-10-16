// SPDX-License-Identifier: GPL-2.0-or-later
// Copyright (c) 2026 情绪零碎の佳 (Jia060117)
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const code=fs.readFileSync('src/automix/frontend-probe.js','utf8');
const state={playing:{playId:'a',curPlaying:{resourceId:'1',track:{name:'A'}},playingMode:'playCycle'},playingList:{curPlayingList:Array.from({length:60},(_,i)=>({resourceId:String(i+1),track:{name:'T'+i}}))},host:{isAnonymous:true},setting:{quantity:{listenAnon:'x'}}};
let sourceFileSize=7;
const source={f:async function({requestSoundQuality}){return {canPlay:true,playInfo:{musicurl:'https://m7.music.126.net/fixture',fileSize:sourceFileSize}};},h:async function({preloadIndex}){}};
const cache={1:{exports:{AudioPlayer:{seek(){}},Bridge:{appendRegisterCall(){},removeRegisterCall(){}}}},8:{exports:{getStore:()=>state,getDispatch:()=>()=>{throw Error('Unexpected playback control')}}},38:{exports:{e:()=>({bitRate:320})}},57:{exports:{b:()=>320}},101:{exports:source},163:{exports:{a:(mode,list)=>list[40]}}};
function runtime(){throw Error('Existing module execution is forbidden')}runtime.c=cache;
const window={webpackJsonp:[]};window.webpackJsonp.push=p=>Object.values(p[1])[0]({}, {},runtime);
let requests=0,status=206,body=Buffer.from('ID3demo'),declared='bytes 0-6/7';
const context=vm.createContext({window,navigator:{userAgent:'test'},console:{log(){}},performance:{now:()=>0},setTimeout,clearTimeout,AbortController,btoa,
  fetch:async()=>{requests++;return new Response(body,{status,headers:{'content-range':declared,'content-type':'audio/mpeg'}})},URL});
vm.runInContext(code,context);const probe=window.automixProbe;
(async()=>{
  assert.equal(probe.readPlaybackPair().next.resourceId,'41');assert.equal(probe.readPlaybackPair().queueLength,60);
  await probe.prepareSource('41');const valid=await probe.readPreparedSourceBase64('41');assert.equal(valid.base64,Buffer.from('ID3demo').toString('base64'));assert.equal(valid.bytes,7);
  // Sequential fixtures: valid range, truncation, denied response; no retry after denial.
  state.playing.playingMode='playRandom';assert.throws(()=>probe.readPlaybackPair(),/暂未适配/);state.playing.playingMode='playCycle';
  body=Buffer.from('ID3');await probe.prepareSource('41');await assert.rejects(probe.readPreparedSourceBase64('41'),/body length/);
  status=403;await probe.prepareSource('41');const count=requests;await assert.rejects(probe.readPreparedSourceBase64('41'),/HTTP 403/);assert.equal(requests,count+1);
  await assert.rejects(probe.readPreparedSourceBase64('41'),/Prepare/);assert.equal(requests,count+1);
  sourceFileSize=28*1024*1024;status=206;body=Buffer.from('ID3demo');await probe.prepareSource('41');
  await assert.rejects(probe.readPreparedSourceBase64('41'),/memory budget/);
  await assert.rejects(probe.readPreparedSourceBase64('41'),/Prepare/);
  await probe.prepareSource('41');assert.equal((await probe.readPreparedSourceBase64('41',64*1024*1024)).bytes,7);
  await assert.rejects(probe.readPreparedSourceBase64('41',65*1024*1024),/16KiB..64MiB/);
  console.log('PASS: full queue selector, complete memory range, truncated-source rejection, unsupported mode, denial without alternate requests, prepared-source release.');
})().catch(e=>{console.error(e);process.exitCode=1});
