// SPDX-License-Identifier: GPL-2.0-or-later
// Copyright (c) 2026 情绪零碎の佳 (Jia060117)
const vm=require('vm'),fs=require('fs'),assert=require('assert/strict');
const listeners=new Map(),toggles=[];let sequence=0;
const state={playing:{playId:'A',curPlaying:{resourceId:'1'},isLoadingFirst:false},playingList:{curPlayingList:[]}};
const sdk={seek(){},async setAudioDataEnableState(value){toggles.push(value);return {};}};
const bridge={appendRegisterCall(event,scope,callback){listeners.set(event,callback);},removeRegisterCall(event,scope,callback){if(listeners.get(event)===callback)listeners.delete(event);}};
const runtime=()=>{throw Error('Unexpected module loading');};runtime.c={1:{exports:{AudioPlayer:sdk,Bridge:bridge}},2:{exports:{getStore:()=>state,getDispatch:()=>()=>{}}}};
const window={webpackJsonp:[]};window.webpackJsonp.push=entry=>Object.values(entry[1])[0]({}, {},runtime);
const context=vm.createContext({window,navigator:{userAgent:'test'},console:{log(){}},performance:{timeOrigin:Date.now(),now:()=>sequence++},setTimeout,clearTimeout,listeners,btoa});
vm.runInContext(fs.readFileSync('src/automix/frontend-probe.js','utf8'),context);
(async()=>{
 assert.equal(toggles.length,0);await window.automixProbe.beginNativeMonitor(5);assert.equal(toggles[0],true);
 await assert.rejects(()=>window.automixProbe.beginNativeMonitor(5),/already active/);
 for(let i=0;i<8;i++)vm.runInContext('listeners.get("AudioData")({data:new Uint8Array(12800).fill(7).buffer,pts:20000})',context);
 const p=window.automixProbe.readNativePacket();assert.equal(p.bytes,12800);assert.equal(p.sequence,8);assert.equal(p.playId,'A');
 state.playing.playId='B';vm.runInContext('listeners.get("AudioData")({data:new Uint8Array(12800).fill(4).buffer,pts:30000})',context);
 assert.equal(window.automixProbe.readNativePacket().playId,'B');
 await window.automixProbe.endNativeMonitor();assert.equal(window.automixProbe.readNativePacket(),null);assert(!listeners.has('AudioData'));assert.deepEqual(toggles,[true,false]);
 await window.automixProbe.endNativeMonitor();assert.equal(toggles.length,2);
 await window.automixProbe.beginNativeMonitor(5);window.automixProbe.dispose();await new Promise(r=>setTimeout(r,10));assert(!listeners.has('AudioData'));assert.deepEqual(toggles,[true,false,true,false]);
 console.log('PASS: native monitor bounded latest packet, dynamic playId, concurrent monitor rejection, idempotent stop and dispose cleanup.');
})().catch(e=>{console.error(e);process.exitCode=1;});
