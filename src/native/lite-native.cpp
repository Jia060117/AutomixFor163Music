// SPDX-License-Identifier: GPL-2.0-or-later
// Copyright (c) 2026 情绪零碎の佳 (Jia060117)
#include <windows.h>
#include <shlwapi.h>
#include <mfapi.h>
#include <mfidl.h>
#include <mfreadwrite.h>
#include <vector>
#include <algorithm>
#include <cmath>
extern "C" __declspec(dllimport) HRESULT WINAPI MFCreateMFByteStreamOnStream(IStream*,IMFByteStream**);
template<class T> void drop(T*& p){if(p){p->Release();p=nullptr;}}
extern "C" __declspec(dllexport) void am_free(float* p){free(p);}
// Decode only the requested excerpt; the encoded stream and all PCM stay in RAM.
extern "C" __declspec(dllexport) long am_decode(const unsigned char* bytes,unsigned length,double start,float** output,unsigned* frames){
 *output=nullptr;*frames=0;if(!bytes||!length||length>64*1024*1024||!std::isfinite(start)||start<0||start>7200)return E_INVALIDARG;
 HRESULT init=CoInitializeEx(nullptr,COINIT_MULTITHREADED),hr=MFStartup(MF_VERSION,MFSTARTUP_LITE);
 if(FAILED(hr)){if(SUCCEEDED(init))CoUninitialize();return hr;}
 IStream* stream=SHCreateMemStream(bytes,length);IMFByteStream* bs=nullptr;IMFAttributes* attr=nullptr;IMFSourceReader* reader=nullptr;IMFMediaType* type=nullptr;
 std::vector<float> pcm;unsigned long streamflags=0;LONGLONG timestamp=0;
 if(!stream){hr=E_OUTOFMEMORY;goto done;}
 hr=MFCreateMFByteStreamOnStream(stream,&bs);if(FAILED(hr))goto done;
 hr=MFCreateAttributes(&attr,2);if(FAILED(hr))goto done;
 attr->SetUINT32(MF_READWRITE_DISABLE_CONVERTERS,FALSE);
 hr=MFCreateSourceReaderFromByteStream(bs,attr,&reader);if(FAILED(hr))goto done;
 reader->SetStreamSelection(MF_SOURCE_READER_ALL_STREAMS,FALSE);reader->SetStreamSelection(MF_SOURCE_READER_FIRST_AUDIO_STREAM,TRUE);
 hr=MFCreateMediaType(&type);if(FAILED(hr))goto done;
 type->SetGUID(MF_MT_MAJOR_TYPE,MFMediaType_Audio);type->SetGUID(MF_MT_SUBTYPE,MFAudioFormat_Float);
 type->SetUINT32(MF_MT_AUDIO_NUM_CHANNELS,2);type->SetUINT32(MF_MT_AUDIO_SAMPLES_PER_SECOND,48000);
 type->SetUINT32(MF_MT_AUDIO_BITS_PER_SAMPLE,32);type->SetUINT32(MF_MT_AUDIO_BLOCK_ALIGNMENT,8);type->SetUINT32(MF_MT_AUDIO_AVG_BYTES_PER_SECOND,384000);
 type->SetUINT32(MF_MT_ALL_SAMPLES_INDEPENDENT,TRUE);
 hr=reader->SetCurrentMediaType(MF_SOURCE_READER_FIRST_AUDIO_STREAM,nullptr,type);if(FAILED(hr))goto done;
 // Decode from the beginning to preserve the decoder's exact timestamp origin.
 while(pcm.size()<45*48000*2){
  IMFSample* sample=nullptr;IMFMediaBuffer* buffer=nullptr;DWORD actual=0;streamflags=0;
  hr=reader->ReadSample(MF_SOURCE_READER_FIRST_AUDIO_STREAM,0,&actual,&streamflags,&timestamp,&sample);
  if(FAILED(hr)){drop(sample);break;}
  if(sample){
   hr=sample->ConvertToContiguousBuffer(&buffer);
   if(SUCCEEDED(hr)){
    BYTE* p=nullptr;DWORD count=0;hr=buffer->Lock(&p,nullptr,&count);
    if(SUCCEEDED(hr)){
     if(count%8){hr=E_FAIL;}else{
      LONGLONG index=llround((timestamp/10000000.0-start)*48000.0);unsigned n=count/8;
      unsigned skip=index<0?(unsigned)std::min<LONGLONG>(n,-index):0;
      unsigned take=std::min<unsigned>(n-skip,(45*48000*2-pcm.size())/2);
      if(take){const float* f=(const float*)p+skip*2;pcm.insert(pcm.end(),f,f+take*2);}
     }
     buffer->Unlock();
    }
   }
   drop(buffer);drop(sample);if(FAILED(hr))break;
  }
  if(streamflags&MF_SOURCE_READERF_ENDOFSTREAM)break;
 }
 if(SUCCEEDED(hr)&&pcm.size()>=15*48000*2){
  *output=(float*)malloc(pcm.size()*sizeof(float));if(!*output)hr=E_OUTOFMEMORY;
  else{memcpy(*output,pcm.data(),pcm.size()*sizeof(float));*frames=(unsigned)pcm.size()/2;}
 }else if(SUCCEEDED(hr))hr=E_FAIL;
done:
 if(!pcm.empty())SecureZeroMemory(pcm.data(),pcm.size()*sizeof(float));
 drop(type);drop(reader);drop(attr);drop(bs);drop(stream);MFShutdown();if(SUCCEEDED(init))CoUninitialize();return hr;
}
