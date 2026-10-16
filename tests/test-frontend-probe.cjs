// SPDX-License-Identifier: GPL-2.0-or-later
// Copyright (c) 2026 情绪零碎の佳 (Jia060117)
const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');
const code = fs.readFileSync('src/automix/frontend-probe.js', 'utf8');
let dispatches = [], nativeCalls = 0, registered, removed;
const fakeState = { playing: { playId:'123',curPlaying:{resourceId:123,track:{name:'Demo',url:'secret-url'}},isLoadingFirst:false },
  playingList: { curPlayingList:[{resourceId:456,track:{name:'Next',url:'secret-url'}}] },host:{cookie:'secret-cookie'} };
const store = { getStore:()=>fakeState, getDispatch:()=>action=>dispatches.push(action) };
const bridge = { appendRegisterCall:(event,scope,cb)=>{ registered=cb; cb('123',1.5,10,true); }, removeRegisterCall:(event,scope,cb)=>{ removed=cb; } };
const cache = { 1:{exports:{AudioPlayer:{seek(){}},Bridge:bridge}},2:{exports:{a:store}} };
function requireFake() { throw Error('Existing modules must never be required'); }
requireFake.c = cache;
const window = { channel:{call:()=>nativeCalls++},webpackJsonp:[] };
window.webpackJsonp.push = packet=>Object.values(packet[1])[0]({}, {}, requireFake);
const context = vm.createContext({window,navigator:{userAgent:'Test'},console:{log(){}},performance:{now:()=>1},setTimeout:cb=>cb()});
vm.runInContext(code,context);
assert.equal(nativeCalls,0);
assert.equal(dispatches.length,0);
assert.equal(window.automixProbe.inspect().audioPlayerSdkFound,true);
assert(!window.automixProbe.exportReport().includes('secret-'));
assert.throws(()=>window.automixProbe.seek(-1));
fakeState.playing.isLoadingFirst=true;
assert.throws(()=>window.automixProbe.seek(10));
fakeState.playing.isLoadingFirst=false;
window.automixProbe.seek(10);
assert.equal(dispatches[0].type,'playing/setPlayingPosition');
assert.equal(dispatches[0].payload.duration,10);
(async()=>{
  const report=await window.automixProbe.watchProgress(1);
  assert.equal(report.events.length,1);
  assert.equal(registered,removed);
  const missing = vm.createContext({window:{},navigator:{userAgent:'Test'},console:{log(){}}});
  vm.runInContext(code,missing);
  assert.equal(missing.window.automixProbe.inspect().webpackCaptured,false);
  assert.throws(()=>missing.window.automixProbe.pause());
  console.log('PASS: no startup controls, no existing module execution, redacted reports, seek validation, event cleanup, missing-runtime handling.');
})().catch(e=>{console.error(e);process.exitCode=1});
