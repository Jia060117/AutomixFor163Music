// SPDX-License-Identifier: GPL-2.0-or-later
// Copyright (c) 2026 情绪零碎の佳 (Jia060117)
#include "quickjs.h"
#include <stdlib.h>
#include <string.h>
typedef const char* (*host_callback)(const char*);
typedef struct{JSRuntime* rt;JSContext* ctx;host_callback cb;char* error;} Host;
static JSValue call_host(JSContext* ctx,JSValueConst this_val,int argc,JSValueConst* argv){
 Host* h=JS_GetContextOpaque(ctx);const char* s=JS_ToCString(ctx,argv[0]);JSValue result=JS_UNDEFINED;if(s){const char* r=h->cb(s);if(r)result=JS_NewString(ctx,r);JS_FreeCString(ctx,s);}return result;
}
static void save_error(Host* h){JSValue e=JS_GetException(h->ctx);const char* s=JS_ToCString(h->ctx,e);free(h->error);h->error=strdup(s?s:"JS error");if(s)JS_FreeCString(h->ctx,s);JS_FreeValue(h->ctx,e);}
__declspec(dllexport) Host* am_js_new(host_callback cb){
 Host* h=calloc(1,sizeof(*h));h->cb=cb;h->rt=JS_NewRuntime();JS_SetMemoryLimit(h->rt,384*1024*1024);JS_SetMaxStackSize(h->rt,2*1024*1024);h->ctx=JS_NewContext(h->rt);JS_SetContextOpaque(h->ctx,h);
 JSValue g=JS_GetGlobalObject(h->ctx);JS_SetPropertyStr(h->ctx,g,"_host",JS_NewCFunction(h->ctx,call_host,"_host",1));JS_FreeValue(h->ctx,g);return h;
}
__declspec(dllexport) int am_js_eval(Host* h,const char* s){JSValue v=JS_Eval(h->ctx,s,strlen(s),"automix",JS_EVAL_TYPE_GLOBAL);int fail=JS_IsException(v);if(fail)save_error(h);JS_FreeValue(h->ctx,v);return !fail;}
__declspec(dllexport) int am_js_jobs(Host* h){JSContext* c;int n=0,r;while((r=JS_ExecutePendingJob(h->rt,&c))>0&&n++<1000){}if(r<0){save_error(h);return -1;}return n;}
__declspec(dllexport) const char* am_js_error(Host* h){return h->error?h->error:"Unknown JS error";}
__declspec(dllexport) size_t am_js_memory(Host* h){JSMemoryUsage m;JS_ComputeMemoryUsage(h->rt,&m);return m.memory_used_size;}
__declspec(dllexport) void am_js_delete(Host* h){JS_FreeContext(h->ctx);JS_FreeRuntime(h->rt);free(h->error);free(h);}
