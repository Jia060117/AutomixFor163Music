# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (c) 2026 情绪零碎の佳 (Jia060117)
"""RAM-only Windows decoder plus the native Rubber Band C API."""
import ctypes,pathlib,numpy as np
HERE=pathlib.Path(__file__).resolve().parent
P=ctypes.POINTER(ctypes.c_float);PP=ctypes.POINTER(P)
def decode_bytes(encoded,start):
 lib=ctypes.CDLL(str(HERE/'automix-audio.dll'))
 lib.am_decode.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_double,ctypes.POINTER(P),ctypes.POINTER(ctypes.c_uint)];lib.am_decode.restype=ctypes.c_long
 lib.am_free.argtypes=[P]
 output=P();frames=ctypes.c_uint();data=(ctypes.c_ubyte*len(encoded)).from_buffer(encoded)
 hr=lib.am_decode(data,len(encoded),float(start),ctypes.byref(output),ctypes.byref(frames))
 if hr<0:raise ValueError('Windows audio decode failed (0x%08x)'%(hr&0xffffffff))
 try:
  x=np.ctypeslib.as_array(output,shape=(frames.value*2,)).reshape(-1,2).copy()
  if not np.isfinite(x).all():raise ValueError('Nonfinite decoded audio')
  return x
 finally:
  if output:ctypes.memset(output,0,frames.value*8);lib.am_free(output)

def stretch(source,ratio,overlap,ramp,rate=48000):
 lib=ctypes.CDLL(str(HERE/'rubberband.dll'))
 signatures={'rubberband_new':([ctypes.c_uint,ctypes.c_uint,ctypes.c_int,ctypes.c_double,ctypes.c_double],ctypes.c_void_p),'rubberband_delete':([ctypes.c_void_p],None),'rubberband_set_time_ratio':([ctypes.c_void_p,ctypes.c_double],None),'rubberband_get_samples_required':([ctypes.c_void_p],ctypes.c_uint),'rubberband_process':([ctypes.c_void_p,PP,ctypes.c_uint,ctypes.c_int],None),'rubberband_available':([ctypes.c_void_p],ctypes.c_int),'rubberband_retrieve':([ctypes.c_void_p,PP,ctypes.c_uint],ctypes.c_uint)}
 for name,(args,result) in signatures.items():fn=getattr(lib,name);fn.argtypes=args;fn.restype=result
 # Same R2/crisp/compound/laminar/standard/quality/together choices as FFmpeg.
 state=lib.rubberband_new(rate,2,1|0x10000000,1/ratio,1)
 if not state:raise MemoryError('Rubber Band allocation failed')
 planar=np.ascontiguousarray(source.T,dtype=np.float32);result=[];pos=0;segment=0
 times=[];t=overlap*ratio
 for k in range(33):speed=ratio+(1-ratio)*k/32;times.append((t,speed));t+=speed*ramp/32
 try:
  while pos<len(source):
   while segment<len(times) and pos/rate>=times[segment][0]:lib.rubberband_set_time_ratio(state,1/times[segment][1]);segment+=1
   n=min(max(1,lib.rubberband_get_samples_required(state)),len(source)-pos)
   channels=(P*2)(planar[0,pos:].ctypes.data_as(P),planar[1,pos:].ctypes.data_as(P));pos+=n
   lib.rubberband_process(state,channels,n,int(pos==len(source)))
   available=lib.rubberband_available(state)
   if available>0:
    block=np.empty((2,available),np.float32);ptrs=(P*2)(block[0].ctypes.data_as(P),block[1].ctypes.data_as(P));count=lib.rubberband_retrieve(state,ptrs,available);result.append(block[:,:count].T.copy());block.fill(0)
  # Drain the completed real-time stream, including its buffered tail.
  while lib.rubberband_available(state)>0:
   n=lib.rubberband_available(state);block=np.empty((2,n),np.float32);ptrs=(P*2)(block[0].ctypes.data_as(P),block[1].ctypes.data_as(P));count=lib.rubberband_retrieve(state,ptrs,n);result.append(block[:,:count].T.copy());block.fill(0)
  output=np.concatenate(result)
  return output
 finally:
  planar.fill(0)
  for a in result:a.fill(0)
  lib.rubberband_delete(state)
