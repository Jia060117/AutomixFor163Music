// SPDX-License-Identifier: GPL-2.0-or-later
// Copyright (c) 2026 情绪零碎の佳 (Jia060117)
// A small host API; the tested controller and its native queue guards are reused.
let _sequence=0;const _promises=new Map(),_timers=new Map(),_signals=new Map(),_workers=new Map();
function sync(op,data={}){const r=JSON.parse(_host(JSON.stringify({op,...data})));if(r?.error)throw Error(r.error);return r?.value;}
function rpc(op,data={}){return new Promise((resolve,reject)=>{const id=++_sequence;_promises.set(id,{resolve,reject});sync('rpc',{id,action:op,...data});});}
function _result(id,value,error){const p=_promises.get(id);if(!p)return;_promises.delete(id);if(error)p.reject(Error(error));else p.resolve(value);}
function setTimeout(fn,ms){const id=++_sequence;_timers.set(id,()=>{_timers.delete(id);fn();});sync('timer',{id,ms:Math.max(0,ms||0)});return id;}
function clearTimeout(id){_timers.delete(id);}
function setInterval(fn,ms){const id=++_sequence;const tick=()=>{fn();if(_timers.has(id))sync('timer',{id,ms});};_timers.set(id,tick);sync('timer',{id,ms});return id;}
function clearInterval(id){_timers.delete(id);}
function _tick(id){const f=_timers.get(id);if(f)f();}
function _signal(name){for(const f of _signals.get(name)||[])f();}
const console={log:s=>sync('log',{line:String(s)})};
const process={argv:['lite','controller',...HOST_ARGS],env:HOST_ENV,exitCode:0,on:(name,f)=>{if(!_signals.has(name))_signals.set(name,[]);_signals.get(name).push(f);},memoryUsage:()=>sync('memory')};
const path={join:(...a)=>a.join('/'),dirname:s=>s.slice(0,s.lastIndexOf('/')),resolve:(...a)=>a.join('/')};
const fs={existsSync:s=>true,mkdirSync:()=>{},readFileSync:()=>FRONTEND_PROBE,writeFileSync:(file,data)=>sync('report',{file,data})};
function fileURLToPath(s){return HOST_HERE+'/automix-memory.mjs';}
function createInterface(){return {on:(name,f)=>{if(name==='line'){process.on('STOP',()=>f('stop'));}else if(name==='close')process.on('SIGTERM',f);return this;},close:()=>{}};}
async function connectPlayer(){await rpc('connect');return {evaluate:(expression,timeout)=>rpc('evaluate',{expression,timeout:timeout||25000}),close:()=>sync('disconnect')};}
function liteSpawnWorker(options){
 const stopped=options.stopped,pause=options.pause;
 const id=sync('worker-new',{options}),messages=[];let error,exited=false,requestId=0;
 _workers.set(id,m=>{if(m.event==='exit'){exited=true;if(m.code)error=Error('Memory worker exited '+m.code);}else{messages.push(m);if(messages.length>512)messages.splice(0,64);if(m.event==='error')error=Error(m.message);}});
 async function event(name,timeout=60000,label,request){const until=Date.now()+timeout;while(true){const m=messages.find(x=>x.event===name&&(!label||x.label===label)&&(request===undefined||x.requestId===request));if(m)return m;if(error)throw error;if(exited)throw Error('Worker ended before '+name);if(stopped())throw Error('Run stopped');if(Date.now()>until)throw Error('Worker timeout: '+name);await pause(10);}}
 async function send(request){try{await rpc('worker-send',{worker:id,request});}finally{if(request.base64)request.base64=null;}}
 return {event,send,latest:name=>messages.findLast(m=>m.event===name),async position(expected,nativePacket){const n=++requestId;await send({command:'source-position',expectedSourceSeconds:expected,nativePacket,requestId:n});if(nativePacket)nativePacket.base64=null;return event('source-clock',3000,undefined,n);},async nativePosition(nativePacket){const n=++requestId;await send({command:'native-position',nativePacket,requestId:n});if(nativePacket)nativePacket.base64=null;return event('native-clock',1500,undefined,n);},async pilotPosition(expected){const n=++requestId;await send({command:'pilot-position',expectedSourceSeconds:expected,requestId:n});return event('pilot-clock',1500,undefined,n);},async phaseShift(shift){const n=++requestId;await send({command:'phase-shift',sourceShiftSeconds:shift,requestId:n});return event('phase-adjusted',2500,undefined,n);},close(){sync('worker-close',{worker:id});_workers.delete(id);}};
}
function _worker(id,m){_workers.get(id)?.(m);}
