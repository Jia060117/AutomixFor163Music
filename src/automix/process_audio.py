# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (c) 2026 情绪零碎の佳 (Jia060117)
"""Windows process loopback in RAM. No microphone or virtual-driver install."""
import ctypes as C,struct,threading,pathlib
from wasapi_audio import Endpoint,PTR,U32,HRESULT,ole,guid,checked,invoke,method,release

_pending=[]
class Blob(C.Structure):_fields_=[('size',U32),('data',PTR)]
class VariantData(C.Union):_fields_=[('blob',Blob),('space',C.c_byte*16)]
class PropVariant(C.Structure):_fields_=[('vt',C.c_ushort),('reserved',C.c_ushort*3),('value',VariantData)]
class Activation(C.Structure):_fields_=[('kind',U32),('pid',U32),('mode',U32)]
class Object(C.Structure):_fields_=[('vtable',PTR)]
k32=C.WinDLL('kernel32',use_last_error=True)
k32.CreateEventW.argtypes=[PTR,C.c_int,C.c_int,C.c_wchar_p];k32.CreateEventW.restype=PTR
k32.CloseHandle.argtypes=[PTR];k32.CloseHandle.restype=C.c_int
k32.OpenProcess.argtypes=[U32,C.c_int,U32];k32.OpenProcess.restype=PTR
k32.QueryFullProcessImageNameW.argtypes=[PTR,U32,C.c_wchar_p,C.POINTER(U32)];k32.QueryFullProcessImageNameW.restype=C.c_int
def process_name(pid):
    handle=k32.OpenProcess(0x1000,False,pid)
    if not handle:return None
    try:
        buf=C.create_unicode_buffer(32768);size=U32(len(buf))
        return pathlib.PureWindowsPath(buf.value).name.lower() if k32.QueryFullProcessImageNameW(handle,0,buf,C.byref(size)) else None
    finally:k32.CloseHandle(handle)

class ProcessEndpoint(Endpoint):
    def __init__(self,pid):
        if not isinstance(pid,int) or pid<=0:raise ValueError('Invalid process capture PID')
        self.pid=pid;self.device_id='process:'+str(pid);self.enumerator=PTR();self.device=PTR();self.client=PTR();self.service=PTR();self.clock=PTR();self.started=False;self.initialized=False;self.event=PTR();self.operation=PTR()
        checked(ole.CoInitializeEx(None,0));self.initialized=True
        self.done=threading.Event();self.error=None;self.references=1
        qi_type=C.WINFUNCTYPE(HRESULT,PTR,PTR,C.POINTER(PTR));ref_type=C.WINFUNCTYPE(U32,PTR);complete_type=C.WINFUNCTYPE(HRESULT,PTR,PTR)
        allowed=[C.string_at(guid(s),16) for s in ['00000000-0000-0000-c000-000000000046','41d949ab-9862-444a-80f6-c261334da5eb','94ea2b94-e9cc-49e0-c0ff-ee64ca8f5b90']]
        def qi(this,iid,out):
            if C.string_at(iid,16) not in allowed:out[0]=None;return -2147467262
            out[0]=C.addressof(self.object);self.references+=1;return 0
        def add(this):self.references+=1;return self.references
        def drop(this):self.references=max(0,self.references-1);return self.references
        def completed(this,operation):
            unknown=PTR()
            try:
                result=HRESULT();invoke(operation,3,(C.POINTER(HRESULT),C.POINTER(PTR)),C.byref(result),C.byref(unknown));checked(result.value)
                invoke(unknown,0,(PTR,C.POINTER(PTR)),guid('1cb9ad4c-dbfa-4c32-b178-c2f568a703b2'),C.byref(self.client))
            except BaseException as e:self.error=e
            finally:release(unknown);self.done.set()
            return 0
        self.callbacks=[qi_type(qi),ref_type(add),ref_type(drop),complete_type(completed)]
        self.table=(PTR*4)(*[C.cast(f,PTR).value for f in self.callbacks]);self.object=Object(C.cast(self.table,PTR))
        self.activation=Activation(1,pid,0);self.variant=PropVariant();self.variant.vt=65;self.variant.value.blob=Blob(C.sizeof(self.activation),C.addressof(self.activation))
        activate=C.WinDLL('mmdevapi').ActivateAudioInterfaceAsync;activate.argtypes=[C.c_wchar_p,PTR,C.POINTER(PropVariant),PTR,C.POINTER(PTR)];activate.restype=HRESULT
        try:
            checked(activate('VAD\\Process_Loopback',guid('1cb9ad4c-dbfa-4c32-b178-c2f568a703b2'),C.byref(self.variant),C.byref(self.object),C.byref(self.operation)))
            if not self.done.wait(8):
                _pending.append(self);raise ValueError('Process capture activation timed out')
            if self.error:raise self.error
            self.rate=48000;self.channels=2;self.bits=32;self.align=8;self.subtype=3;self.clock_frequency=0
            self.format_bytes=struct.pack('<HHIIHHH',3,2,48000,384000,8,32,0);fmt=C.create_string_buffer(self.format_bytes)
            invoke(self.client,3,(C.c_int,U32,C.c_int64,C.c_int64,PTR,PTR),0,0x80060000,0,0,fmt,None)
            self.event=k32.CreateEventW(None,False,False,None)
            if not self.event:raise C.WinError(C.get_last_error())
            invoke(self.client,13,(PTR,),self.event)
            # The virtual capture has no physical render buffer. Some builds
            # leave GetBufferSize's output undefined; capture never needs it.
            self.buffer_frames=U32()
            invoke(self.client,14,(PTR,C.POINTER(PTR)),guid('c8adbd64-e71e-48a0-a4de-185c395cd317'),C.byref(self.service))
        except BaseException:
            self.close();raise
    def info(self):return {**super().info(),'captureKind':'process-loopback','processId':self.pid,'positionSource':'QPC timestamps (virtual device position may remain zero)'}
    def close(self):
        super().close()
        if self.event:k32.CloseHandle(self.event);self.event=None
        if self.operation and self.done.is_set():release(self.operation);self.operation=PTR()

class PlayerSessions:
    """Only NetEase render sessions on the current default multimedia endpoint."""
    def __init__(self):
        self.endpoint=Endpoint(False);self.manager=PTR();self.enumerator=PTR();self.sessions=[]
        try:
            invoke(self.endpoint.device,3,(PTR,U32,PTR,C.POINTER(PTR)),guid('77aa99a0-1bd6-484f-8bc7-2c654c9a9b6f'),23,None,C.byref(self.manager))
            invoke(self.manager,5,(C.POINTER(PTR),),C.byref(self.enumerator));count=C.c_int();invoke(self.enumerator,3,(C.POINTER(C.c_int),),C.byref(count))
            for index in range(count.value):
                control=PTR();control2=PTR();volume=PTR()
                try:
                    invoke(self.enumerator,4,(C.c_int,C.POINTER(PTR)),index,C.byref(control));invoke(control,0,(PTR,C.POINTER(PTR)),guid('bfb7ff88-7239-4fc9-8fa2-07c950be9c6d'),C.byref(control2))
                    pid=U32();invoke(control2,14,(C.POINTER(U32),),C.byref(pid))
                    if process_name(pid.value)!='cloudmusic.exe':continue
                    invoke(control,0,(PTR,C.POINTER(PTR)),guid('87ce5498-68d6-44e5-9215-6da47ef883d8'),C.byref(volume))
                    level=C.c_float();mute=C.c_int();invoke(volume,4,(C.POINTER(C.c_float),),C.byref(level));invoke(volume,6,(C.POINTER(C.c_int),),C.byref(mute))
                    status=C.c_int();invoke(control,3,(C.POINTER(C.c_int),),C.byref(status))
                    self.sessions.append({'pid':pid.value,'state':status.value,'volume':level.value,'mute':bool(mute.value),'pointer':volume});volume=PTR()
                finally:release(volume);release(control2);release(control)
            if not self.sessions:raise ValueError('No NetEase render session found')
        except BaseException:self.close();raise
    def info(self):return [{k:v for k,v in s.items() if k!='pointer'} for s in self.sessions]
    def mute(self):
        for s in self.sessions:invoke(s['pointer'],5,(C.c_int,PTR),True,None)
    def set_level(self,level):
        if not 0<=level<=1:raise ValueError('Invalid session volume')
        for s in self.sessions:invoke(s['pointer'],3,(C.c_float,PTR),level,None)
    def restore(self):
        for s in self.sessions:
            invoke(s['pointer'],3,(C.c_float,PTR),s['volume'],None)
            invoke(s['pointer'],5,(C.c_int,PTR),s['mute'],None)
    def close(self):
        for s in self.sessions:release(s['pointer'])
        self.sessions=[];release(self.enumerator);self.enumerator=PTR();release(self.manager);self.manager=PTR();self.endpoint.close()

if __name__=='__main__':
    import json
    sessions=PlayerSessions()
    try:print(json.dumps(sessions.info()))
    finally:sessions.close()
