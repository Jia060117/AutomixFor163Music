# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (c) 2026 情绪零碎の佳 (Jia060117)
"""Local-only CDP transport; no browser, Node or third-party networking runtime."""
import base64,hashlib,json,os,socket,struct,threading,time,urllib.request,urllib.parse
import numpy as np  # Load native DLLs on the main thread before Windows threads start.
from settings import RENDER_PROFILE

class Player:
 def __init__(self,port=19222):
  if not isinstance(port,int) or not 1024<=port<=65535:raise ValueError('Invalid port')
  opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
  with opener.open(f'http://127.0.0.1:{port}/json/list',timeout=4) as r:targets=json.load(r)
  targets=[t for t in targets if t.get('type')=='page' and t.get('url','').split('?')[0].split('#')[0]=='orpheus://orpheus/pub/app.html']
  if len(targets)!=1:raise ValueError('Expected one NetEase main renderer')
  u=urllib.parse.urlsplit(targets[0]['webSocketDebuggerUrl'])
  if u.scheme!='ws' or u.hostname not in ('127.0.0.1','localhost','::1') or u.port!=port:raise ValueError('Nonlocal endpoint rejected')
  self.socket=socket.create_connection(('127.0.0.1',port),4);self.lock=threading.Lock();self.pending={};self.seq=0;self.closed=False
  key=base64.b64encode(os.urandom(16)).decode();path=u.path+('?' +u.query if u.query else '')
  self.socket.sendall(f'GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: {key}\r\n\r\n'.encode())
  head=bytearray()
  while not head.endswith(b'\r\n\r\n'):
   head.extend(self._read(1))
   if len(head)>16384:raise IOError('Handshake too large')
  expected=base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
  headers={a.lower().strip():b.strip() for line in head.decode().split('\r\n')[1:] if ':' in line for a,b in [line.split(':',1)]}
  if not head.startswith(b'HTTP/1.1 101 ') or headers.get('sec-websocket-accept')!=expected:raise IOError('Invalid websocket handshake')
  self.socket.settimeout(None);threading.Thread(target=self._receive,daemon=True).start()
 def _read(self,n):
  b=bytearray(n);view=memoryview(b);pos=0
  while pos<n:
   got=self.socket.recv_into(view[pos:])
   if not got:raise EOFError('CDP disconnected')
   pos+=got
  return b
 def _send(self,payload,opcode=1):
  n=len(payload);mask=os.urandom(4);header=bytes([0x80|opcode,0x80|n]) if n<126 else bytes([0x80|opcode,0xfe])+struct.pack('>H',n) if n<65536 else bytes([0x80|opcode,0xff])+struct.pack('>Q',n)
  # Native NumPy xor keeps large RAM source transfers fast without audio IO.
  data=bytearray(payload);a=np.frombuffer(data,dtype=np.uint8);a^=np.resize(np.frombuffer(mask,dtype=np.uint8),len(a))
  with self.lock:self.socket.sendall(header+mask);self.socket.sendall(data)
 def _receive(self):
  fragment=bytearray()
  try:
   while not self.closed:
    a,b=self._read(2);op=a&15;n=b&127
    if n==126:n=struct.unpack('>H',self._read(2))[0]
    elif n==127:n=struct.unpack('>Q',self._read(8))[0]
    if n>96*1024*1024 or len(fragment)+n>96*1024*1024:raise IOError('CDP message budget exceeded')
    if b&128:raise IOError('Masked server frame rejected')
    data=self._read(n)
    if op==8:break
    if op==9:self._send(data,10);continue
    if op==10:continue
    if op not in (0,1):raise IOError('Unexpected frame type')
    fragment.extend(data)
    if not a&128:continue
    m=json.loads(fragment);fragment.clear();item=self.pending.get(m.get('id'))
    if item:item[1].append(m);item[0].set()
  except Exception:pass
  finally:
   self.closed=True
   for e,result in list(self.pending.values()):result.append({'error':{'message':'CDP disconnected'}});e.set()
 def evaluate(self,expression,timeout=25000):
  if self.closed:raise IOError('CDP disconnected')
  with self.lock:self.seq+=1;i=self.seq
  event=threading.Event();result=[];self.pending[i]=(event,result)
  try:
   self._send(json.dumps({'id':i,'method':'Runtime.evaluate','params':{'expression':expression,'awaitPromise':True,'returnByValue':True}},ensure_ascii=False).encode())
   if not event.wait(timeout/1000):raise TimeoutError('Evaluate timeout')
   m=result[0]
   if m.get('error'):raise IOError(m['error']['message'])
   r=m['result']
   if r.get('exceptionDetails'):raise ValueError(r['exceptionDetails'].get('exception',{}).get('description') or r['exceptionDetails'].get('text'))
   return r.get('result',{}).get('value')
  finally:self.pending.pop(i,None)
 def close(self):
  self.closed=True
  try:self.socket.shutdown(socket.SHUT_RDWR)
  except OSError:pass
  self.socket.close()

def inspect_player():
 import pathlib,datetime
 here=pathlib.Path(__file__).resolve().parent;c=None
 try:
  c=Player()
  try:
   c.evaluate((here/'frontend-probe.js').read_text(encoding='utf-8'))
   value=c.evaluate("(()=>{const info=automixProbe.inspect(),s=info.snapshot;if(!s)return {queueReady:false,clientVersion:info.clientVersion,reason:info.error||'播放器正在加载，请稍后重试。'};let pair,position,reason;try{pair=automixProbe.readPlaybackPair();position=automixProbe.readStoredPosition().value;}catch(e){reason=e.message;}return {clientVersion:info.clientVersion,state:s.playingState,current:s.current?.name,next:pair?.next?.name,queueMode:pair?.mode,queueModeLabel:pair?.modeLabel,queueSource:pair?.queueSource,queueLength:pair?.queueLength,volume:s.audioSettings?.playingVolume,position,queueReady:!!pair&&!reason,controllerBusy:automixProbe.controllerStatus().active,reason};})()")
  except Exception as error:value=dict(queueReady=False,reason='已连接网易云，但播放器接口检查失败：'+str(error).splitlines()[0][:200])
  return dict(value,connected=True,checkedUtc=datetime.datetime.now(datetime.timezone.utc).isoformat(),profileExists=RENDER_PROFILE.exists())
 except Exception:return dict(connected=False,queueReady=False,reason='未连接到网易云本地控制端口 19222。请点击连接网易云。')
 finally:
  if c:c.close()
