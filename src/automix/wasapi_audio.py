# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (c) 2026 情绪零碎の佳 (Jia060117)
"""Default Windows output loopback and playback. No microphone capture.
Uses ctypes + NumPy, shared-mode WASAPI; timestamps retained for measurements.
"""
import argparse, ctypes as C, json, pathlib, struct, sys, time, uuid, wave,threading
import numpy as np
_event_lock=threading.Lock()
def emit_event(value):
    with _event_lock:sys.stdout.write(json.dumps(value,ensure_ascii=True)+'\n');sys.stdout.flush()

HRESULT=C.c_long; U32=C.c_uint32; U64=C.c_uint64; PTR=C.c_void_p
ole=C.OleDLL('ole32')
ole.CoInitializeEx.argtypes=[PTR,U32];ole.CoInitializeEx.restype=HRESULT
ole.CoCreateInstance.argtypes=[PTR,PTR,U32,PTR,C.POINTER(PTR)];ole.CoCreateInstance.restype=HRESULT
ole.CoTaskMemFree.argtypes=[PTR]
def guid(s): return C.create_string_buffer(uuid.UUID(s).bytes_le,16)
def checked(hr):
    if hr < 0: raise OSError(f'COM/WASAPI HRESULT 0x{hr & 0xffffffff:08x}')
def method(obj,index,types=(),restype=HRESULT):
    table=C.cast(obj,C.POINTER(C.POINTER(PTR))).contents
    return C.WINFUNCTYPE(restype,PTR,*types)(table[index])
def invoke(obj,index,types,*args):
    hr=method(obj,index,types)(obj,*args);checked(hr)
def release(obj):
    if obj: method(obj,2,(),U32)(obj)

class Endpoint:
    def __init__(self,loopback=False):
        self.enumerator=PTR();self.device=PTR();self.client=PTR();self.service=PTR();self.clock=PTR();self.started=False;self.initialized=False
        checked(ole.CoInitializeEx(None,2));self.initialized=True
        try:
            checked(ole.CoCreateInstance(guid('bcde0395-e52f-467c-8e3d-c4579291692e'),None,23,guid('a95664d2-9614-4f35-a746-de8db63617e6'),C.byref(self.enumerator)))
            invoke(self.enumerator,4,(C.c_int,C.c_int,C.POINTER(PTR)),0,1,C.byref(self.device))
            device_id=PTR();invoke(self.device,5,(C.POINTER(PTR),),C.byref(device_id))
            try:self.device_id=C.wstring_at(device_id)
            finally:ole.CoTaskMemFree(device_id)
            invoke(self.device,3,(PTR,U32,PTR,C.POINTER(PTR)),guid('1cb9ad4c-dbfa-4c32-b178-c2f568a703b2'),23,None,C.byref(self.client))
            fmt=PTR();invoke(self.client,8,(C.POINTER(PTR),),C.byref(fmt))
            try:
                header=C.string_at(fmt,18);tag,ch,rate,avg,align,bits,extra=struct.unpack('<HHIIHHH',header)
                self.format_bytes=C.string_at(fmt,18+extra)
                subtype=struct.unpack_from('<I',self.format_bytes,24)[0] if tag==65534 else tag
                self.rate=rate;self.channels=ch;self.align=align;self.bits=bits;self.subtype=subtype
                if not ((subtype==3 and bits==32) or (subtype==1 and bits==16)):raise ValueError(f'Unsupported endpoint format {tag}/{subtype}/{bits}')
                invoke(self.client,3,(C.c_int,U32,C.c_int64,C.c_int64,PTR,PTR),0,0x20000 if loopback else 0,1000000,0,fmt,None)
            finally:ole.CoTaskMemFree(fmt)
            iid='c8adbd64-e71e-48a0-a4de-185c395cd317' if loopback else 'f294acfc-3146-4483-a7bf-addca7c260e2'
            invoke(self.client,14,(PTR,C.POINTER(PTR)),guid(iid),C.byref(self.service))
            invoke(self.client,14,(PTR,C.POINTER(PTR)),guid('cd63314f-3fba-4a1b-812c-ef96358728e7'),C.byref(self.clock))
            frequency=U64();invoke(self.clock,3,(C.POINTER(U64),),C.byref(frequency));self.clock_frequency=frequency.value
            if not self.clock_frequency:raise ValueError('Invalid audio clock frequency')
            self.buffer_frames=U32();invoke(self.client,4,(C.POINTER(U32),),C.byref(self.buffer_frames))
        except BaseException:
            self.close();raise
    def info(self):return {'sampleRate':self.rate,'channels':self.channels,'bits':self.bits,'subtype':self.subtype,'bufferFrames':self.buffer_frames.value,'endpointId':self.device_id,'clockFrequency':self.clock_frequency}
    def clock_position(self):
        pos=U64();qpc=U64()
        hr=method(self.clock,4,(C.POINTER(U64),C.POINTER(U64)))(self.clock,C.byref(pos),C.byref(qpc));checked(hr)
        return {'streamSeconds':pos.value/self.clock_frequency,'qpcSeconds':qpc.value/1e7,'accurate':hr==0,'rawPosition':pos.value}
    def start(self):invoke(self.client,10,());self.started=True
    def close(self):
        if self.started:
            try:invoke(self.client,11,())
            except OSError:pass
            self.started=False
        for name in ('clock','service','client','device','enumerator'):
            obj=getattr(self,name,None);release(obj);setattr(self,name,None)
        if self.initialized:ole.CoUninitialize();self.initialized=False
    def decode(self,data):
        dtype='<f4' if self.subtype==3 else '<i2'
        x=np.frombuffer(data,dtype=dtype).astype(np.float32).reshape(-1,self.channels)
        return x if self.subtype==3 else x/32768

def save_wav(path,audio,rate):
    audio=np.clip(audio,-1,1);samples=np.rint(audio*32767).astype('<i2')
    with wave.open(str(path),'wb') as w:w.setnchannels(audio.shape[1]);w.setsampwidth(2);w.setframerate(rate);w.writeframes(samples.tobytes())

def record(seconds,output,ready=None):
    endpoint=Endpoint(True);chunks=[];packets=[]
    try:
        endpoint.start();started=time.perf_counter();utc=time.time();deadline=started+seconds
        if ready:pathlib.Path(ready).write_text(json.dumps({'qpcStartSeconds':started,'utcStartSeconds':utc,'format':endpoint.info()}),encoding='utf-8')
        while time.perf_counter()<deadline:
            size=U32();invoke(endpoint.service,5,(C.POINTER(U32),),C.byref(size))
            while size.value:
                data=PTR();frames=U32();flags=U32();position=U64();qpc=U64()
                invoke(endpoint.service,3,(C.POINTER(PTR),C.POINTER(U32),C.POINTER(U32),C.POINTER(U64),C.POINTER(U64)),C.byref(data),C.byref(frames),C.byref(flags),C.byref(position),C.byref(qpc))
                try:
                    raw=b'\0'*(frames.value*endpoint.align) if flags.value&2 else C.string_at(data,frames.value*endpoint.align)
                    chunks.append(endpoint.decode(raw));packets.append({'frames':frames.value,'flags':flags.value,'devicePosition':position.value,'qpc100ns':qpc.value,'receivedQpcSeconds':time.perf_counter()})
                finally:invoke(endpoint.service,4,(U32,),frames.value)
                invoke(endpoint.service,5,(C.POINTER(U32),),C.byref(size))
            time.sleep(.003)
        # Anchor once by QPC, then use device frame positions. Re-anchoring every
        # packet to noisy hardware/QPC estimates would insert/delete samples.
        result=np.zeros((round(seconds*endpoint.rate),endpoint.channels),dtype=np.float32)
        anchor=next((p for p in packets if not p['flags']&4),packets[0] if packets else None)
        anchor_frame=round((anchor['qpc100ns']/1e7-started)*endpoint.rate) if anchor else 0
        for chunk,p in zip(chunks,packets):
            at=anchor_frame+p['devicePosition']-anchor['devicePosition'];skip=max(0,-at);at=max(0,at);n=min(len(chunk)-skip,len(result)-at)
            if n>0:result[at:at+n]=chunk[skip:skip+n]
        save_wav(output,result,endpoint.rate)
        meta={'format':endpoint.info(),'seconds':seconds,'qpcStartSeconds':started,'utcStartSeconds':utc,'packets':packets,'nonSilentPackets':sum(not p['flags']&2 for p in packets),'note':'Default render endpoint loopback, potentially includes other application output. No microphone.'}
        pathlib.Path(str(output)+'.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
        return {'format':endpoint.info(),'packets':len(packets),'rms':float(np.sqrt(np.mean(result*result))),'output':str(output)}
    finally:endpoint.close()

def play(path,ready=None,command_start=False):
    with wave.open(str(path),'rb') as w:
        if w.getsampwidth()!=2:raise ValueError('Playback input must be PCM16 WAV')
        rate=w.getframerate();ch=w.getnchannels();audio=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').astype(np.float32).reshape(-1,ch)/32768
    return play_array(audio,rate,ready,command_start)

class LiveBuffer:
    """Atomic future-only edits; never exposes COM objects to analysis threads."""
    def __init__(self,encoded,rate):
        self.encoded=encoded;self.rate=rate;self.written=0;self.played=0;self.lock=threading.Lock();self.closed=False
    def snapshot(self):
        with self.lock:return {'writtenFrames':self.written,'playedFrames':self.played,'frames':len(self.encoded),'sampleRate':self.rate}
    def replace(self,start,audio):
        with self.lock:
            if self.closed or not isinstance(start,int) or start<self.written or start+len(audio)!=len(self.encoded) or audio.shape[1:]!=self.encoded.shape[1:] or not np.isfinite(audio).all():return False
            self.encoded[start:]=audio.astype(self.encoded.dtype) if self.encoded.dtype.kind=='f' else np.rint(np.clip(audio,-1,1)*32767).astype(self.encoded.dtype)
            return True

def play_array(audio,rate,ready=None,command_start=False,on_start=None,on_command=None,report_clock=False,on_live_command=None,on_buffer=None):
    ch=audio.shape[1]
    e=Endpoint(False)
    try:
        if rate!=e.rate:
            positions=np.arange(round(len(audio)*e.rate/rate))*rate/e.rate
            audio=np.stack([np.interp(positions,np.arange(len(audio)),audio[:,c]) for c in range(ch)],axis=1).astype(np.float32)
        if ch==1 and e.channels==2:audio=np.repeat(audio,2,axis=1)
        elif ch==2 and e.channels==1:audio=audio.mean(axis=1,keepdims=True)
        elif ch!=e.channels:raise ValueError('Unsupported channel conversion')
        dtype='<f4' if e.subtype==3 else '<i2'
        encoded=audio.astype(dtype) if e.subtype==3 else np.rint(np.clip(audio,-1,1)*32767).astype(dtype)
        live_buffer=LiveBuffer(encoded,e.rate)
        if on_buffer:on_buffer(live_buffer)
        offset=0;times=[]
        def fill(count):
            nonlocal offset
            ptr=PTR();invoke(e.service,3,(U32,C.POINTER(PTR)),count,C.byref(ptr))
            with live_buffer.lock:
                data=encoded[offset:offset+count].tobytes();live_buffer.written=offset+count
            C.memmove(ptr,data,len(data))
            invoke(e.service,4,(U32,U32),count,0);offset+=count
        fill(min(e.buffer_frames.value,len(encoded)))
        if command_start:
            emit_event({'event':'ready','frames':len(encoded),'durationSeconds':len(encoded)/e.rate,'format':e.info()})
            while True:
                line=sys.stdin.readline(262145)
                if not line:raise ValueError('Controller closed before playback')
                if not line.endswith('\n') or len(line)>262144:raise ValueError('Command budget exceeded')
                command=json.loads(line)
                if command.get('command')=='start':break
                if on_command:on_command(command,e)
                else:raise ValueError('Expected start command')
        if on_start:on_start()
        start=time.perf_counter();e.start()
        if command_start:emit_event({'event':'started','qpcStartSeconds':start,'utcStartSeconds':time.time()})
        # Analysis runs on its own thread, never on the WASAPI buffer-fill path.
        # It receives no COM pointer. The reader may block until controller EOF.
        import threading
        live_stop=threading.Event();live_thread=None
        if on_live_command:
            def read_live():
                while not live_stop.is_set():
                    line=sys.stdin.readline(262145)
                    if not line or live_stop.is_set():return
                    try:
                        if not line.endswith('\n') or len(line)>262144:raise ValueError('Live command budget exceeded')
                        on_live_command(json.loads(line))
                    except Exception:
                        emit_event({'event':'native-clock','valid':False,'reason':'Live packet analysis unavailable'})
            live_thread=threading.Thread(target=read_live,daemon=True);live_thread.start()
        if ready:pathlib.Path(ready).write_text(json.dumps({'qpcStartSeconds':start,'utcStartSeconds':time.time(),'format':e.info()}),encoding='utf-8')
        next_clock=0
        while True:
            padding=U32();invoke(e.client,6,(C.POINTER(U32),),C.byref(padding))
            if offset==len(encoded) and padding.value==0:break
            available=min(e.buffer_frames.value-padding.value,len(encoded)-offset)
            if available:fill(available)
            if report_clock and time.perf_counter()>=next_clock:
                clock=e.clock_position();remaining=len(encoded)/e.rate-clock['streamSeconds']
                with live_buffer.lock:live_buffer.played=round(clock['streamSeconds']*e.rate)
                emit_event({'event':'render-clock',**clock,'remainingSeconds':remaining,'projectedEndQpcSeconds':clock['qpcSeconds']+remaining,'projectedEndUtcSeconds':time.time()+clock['qpcSeconds']+remaining-time.perf_counter()})
                next_clock=time.perf_counter()+.05
            time.sleep(.002)
        return {'qpcStartSeconds':start,'qpcEndSeconds':time.perf_counter(),'frames':len(encoded),'durationSeconds':len(encoded)/e.rate,'format':e.info()}
    finally:
        if 'live_buffer' in locals():
            with live_buffer.lock:live_buffer.closed=True
        if 'live_stop' in locals():live_stop.set()
        if 'live_thread' in locals() and live_thread:live_thread.join(1)
        e.close()
        if 'encoded' in locals():encoded.fill(0)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['info','record','play','serve']);parser.add_argument('--seconds',type=float,default=15);parser.add_argument('--file',default='loopback.wav');parser.add_argument('--ready')
    args=parser.parse_args()
    if args.action=='info':
        e=Endpoint(True)
        try:print(json.dumps(e.info()))
        finally:e.close()
    elif args.action=='record':
        if not 1<=args.seconds<=60:raise ValueError('Recording duration must be 1..60 seconds')
        print(json.dumps(record(args.seconds,pathlib.Path(args.file),args.ready)))
    else:print(json.dumps({'event':'complete',**play(pathlib.Path(args.file),args.ready,args.action=='serve')}),flush=True)
