// SPDX-License-Identifier: GPL-2.0-or-later
// Copyright (c) 2026 情绪零碎の佳 (Jia060117)
export async function connectPlayer(port = 19222) {
  if (!Number.isInteger(port) || port < 1024 || port > 65535) throw Error('Invalid port');
  const response = await fetch(`http://127.0.0.1:${port}/json/list`, {signal:AbortSignal.timeout(4000)});
  if (!response.ok) throw Error(`Discovery HTTP ${response.status}`);
  const targets = (await response.json()).filter(t=>t.type==='page' && /^orpheus:\/\/orpheus\/pub\/app\.html(?:[?#]|$)/.test(t.url));
  if (targets.length !== 1) throw Error('Expected exactly one NetEase main renderer');
  const endpoint = new URL(targets[0].webSocketDebuggerUrl);
  if (!['127.0.0.1','localhost','[::1]'].includes(endpoint.hostname) || Number(endpoint.port)!==port) throw Error('Nonlocal endpoint rejected');
  const socket = new WebSocket(endpoint);
  await new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{socket.close();reject(Error('Connect timeout'));},4000);
    socket.addEventListener('open',()=>{clearTimeout(timer);resolve();},{once:true});
    socket.addEventListener('error',()=>{clearTimeout(timer);reject(Error('Connect failed'));},{once:true});
  });
  let nextId=0;
  const pending=new Map();
  socket.addEventListener('message',event=>{
    const message=JSON.parse(event.data), item=pending.get(message.id);
    if (!item) return;
    clearTimeout(item.timer);pending.delete(message.id);
    if(message.error)item.reject(Error(message.error.message));else item.resolve(message.result);
  });
  socket.addEventListener('close',()=>{for(const item of pending.values()){clearTimeout(item.timer);item.reject(Error('CDP disconnected'));}pending.clear();});
  return {
    async evaluate(expression, timeout=25000) {
      const result=await new Promise((resolve,reject)=>{
        const id=++nextId, timer=setTimeout(()=>{pending.delete(id);reject(Error('Evaluate timeout'));},timeout);
        pending.set(id,{resolve,reject,timer});
        socket.send(JSON.stringify({id,method:'Runtime.evaluate',params:{expression,awaitPromise:true,returnByValue:true}}));
      });
      if(result.exceptionDetails)throw Error(result.exceptionDetails.exception?.description||result.exceptionDetails.text);
      return result.result?.value;
    },
    close(){socket.close();}
  };
}
