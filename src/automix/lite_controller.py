# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (c) 2026 情绪零碎の佳 (Jia060117)
"""Single-thread QuickJS controller host, supervised through the desktop pipe."""
import concurrent.futures,ctypes,heapq,json,os,pathlib,queue,re,subprocess,sys,threading,time
from lite_cdp import Player
from settings import RENDER_PROFILE
HERE=pathlib.Path(__file__).resolve().parent
def j(value):return json.dumps(value,ensure_ascii=False,separators=(',',':'))

class Host:
 def __init__(self,args):
  self.args=args;self.pending=queue.Queue();self.timers=[];self.workers={};self.worker_seq=0;self.client=None;self.done=False;self.code=0;self.pool=concurrent.futures.ThreadPoolExecutor(max_workers=4)
  self.directory=pathlib.Path(args[args.index('--directory')+1]).resolve();self.directory.mkdir(parents=True,exist_ok=True)
  self.lib=ctypes.CDLL(str(HERE/'quickjs.dll'));self.cb_type=ctypes.CFUNCTYPE(ctypes.c_void_p,ctypes.c_char_p);self.cb=self.cb_type(self.call)
  self.lib.am_js_new.argtypes=[self.cb_type];self.lib.am_js_new.restype=ctypes.c_void_p
  self.lib.am_js_eval.argtypes=[ctypes.c_void_p,ctypes.c_char_p];self.lib.am_js_eval.restype=ctypes.c_int
  self.lib.am_js_jobs.argtypes=[ctypes.c_void_p];self.lib.am_js_jobs.restype=ctypes.c_int
  self.lib.am_js_error.argtypes=[ctypes.c_void_p];self.lib.am_js_error.restype=ctypes.c_char_p
  self.lib.am_js_delete.argtypes=[ctypes.c_void_p]
  self.lib.am_js_memory.argtypes=[ctypes.c_void_p];self.lib.am_js_memory.restype=ctypes.c_size_t
  self.ctx=self.lib.am_js_new(self.cb)
 def eval(self,text):
  if not self.lib.am_js_eval(self.ctx,text.encode()):raise ValueError(self.lib.am_js_error(self.ctx).decode())
 def call(self,raw):
  try:r=self.handle(json.loads(raw));result={'value':r}
  except Exception as e:result={'error':str(e)}
  self.result_buffer=ctypes.create_string_buffer(j(result).encode());return ctypes.addressof(self.result_buffer)
 def emit(self,text):self.pending.put(text)
 def handle(self,m):
  op=m['op']
  if op=='rpc':
   def perform():
    try:self.emit(f'_result({m["id"]},{j(self.action(m))},null)')
    except Exception as e:self.emit(f'_result({m["id"]},null,{j(str(e))})')
   self.pool.submit(perform)
  elif op=='timer':heapq.heappush(self.timers,(time.monotonic()+min(3600000,max(0,float(m['ms'])))/1000,m['id']))
  elif op=='log':
   try:print(m['line'],flush=True)
   except (BrokenPipeError,OSError):self.emit("_signal('SIGTERM')")
  elif op=='report':
   target=pathlib.Path(m['file']).resolve()
   if not target.is_relative_to(self.directory) or target.name not in ('memory-transition-test.json','memory-automix-report.json'):raise ValueError('Invalid report path')
   target.write_text(m['data'],encoding='utf-8')
  elif op=='worker-new':
   self.worker_seq+=1;wid=self.worker_seq;options=m['options']
   cmd=[sys.executable,'-X','utf8','-B',str(HERE/'memory_mix_worker.py'),'--ffmpeg',str(HERE/'automix-audio.dll'),'--profile',str(RENDER_PROFILE),'--source-limit-mib','64']
   if options['sourceClock']:cmd.append('--source-clock')
   if options['measuring']:cmd.append('--measure')
   if options['pilotClock']:cmd.append('--process-clock')
   p=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW);self.workers[wid]=p
   def read():
    try:
     for line in p.stdout:
      if len(line)>262144:raise ValueError('Worker event budget exceeded')
      self.emit(f'_worker({wid},{j(json.loads(line))})')
    except Exception:self.emit(f'_worker({wid},{{event:"error",message:"Invalid worker message"}})')
    finally:p.wait();self.emit(f'_worker({wid},{{event:"exit",code:{p.returncode}}})')
   threading.Thread(target=read,daemon=True).start();return wid
  elif op=='worker-close':
   p=self.workers.pop(m['worker'],None)
   if p:
    try:p.stdin.close()
    except OSError:pass
    if p.poll() is None:p.kill()
    p.wait(timeout=5);p.stdout.close()
  elif op=='disconnect':
   if self.client:self.client.close();self.client=None
  elif op=='done':self.done=True;self.code=int(m.get('code',0))
  elif op=='memory':
   class Counters(ctypes.Structure):_fields_=[('cb',ctypes.c_ulong),('faults',ctypes.c_ulong),('peakWorking',ctypes.c_size_t),('working',ctypes.c_size_t),('peakPaged',ctypes.c_size_t),('paged',ctypes.c_size_t),('peakNonpaged',ctypes.c_size_t),('nonpaged',ctypes.c_size_t),('pagefile',ctypes.c_size_t),('peakPagefile',ctypes.c_size_t),('private',ctypes.c_size_t)]
   counters=Counters();counters.cb=ctypes.sizeof(counters);kernel=ctypes.WinDLL('kernel32');kernel.GetCurrentProcess.restype=ctypes.c_void_p
   get=ctypes.WinDLL('psapi').GetProcessMemoryInfo;get.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_ulong];get.restype=ctypes.c_int
   if not get(kernel.GetCurrentProcess(),ctypes.byref(counters),counters.cb):raise OSError('Memory counters unavailable')
   return dict(rss=counters.working,heapUsed=self.lib.am_js_memory(self.ctx),external=0)
  else:raise ValueError('Invalid bridge operation')
 def action(self,m):
  if m['action']=='connect':self.client=Player();return True
  if m['action']=='evaluate':return self.client.evaluate(m['expression'],min(60000,max(1,int(m['timeout']))))
  if m['action']=='worker-send':
   p=self.workers[m['worker']];data=bytearray((j(m['request'])+'\n').encode())
   try:
    if len(data)>((64*1024*1024+2)//3)*4+4096:raise ValueError('Worker input budget exceeded')
    p.stdin.write(data);p.stdin.flush();return True
   finally:data[:]=b'\0'*len(data);m['request']=None
  raise ValueError('Invalid RPC action')
 def run(self):
  pre='const HOST_ARGS='+j(self.args)+',HOST_ENV='+j({'LOCALAPPDATA':os.environ.get('LOCALAPPDATA',''),'AUTOMIX_FFMPEG':str(HERE/'automix-audio.dll')})+',HOST_HERE='+j(HERE.as_posix())+',FRONTEND_PROBE='+j((HERE/'frontend-probe.js').read_text(encoding='utf-8'))+';'
  self.eval(pre+(HERE/'lite-shims.js').read_text(encoding='utf-8'))
  script=(HERE/'automix-memory.mjs').read_text(encoding='utf-8');script=re.sub(r'^import .*;\s*','',script,flags=re.M)
  script=script.replace('import.meta.url',j('controller'))
  a=script.index('function spawnWorker(){');b=script.index('async function assertPair',a)
  script=script[:a]+"function spawnWorker(){return liteSpawnWorker({sourceClock,pilotClock,measuring,stopped,pause});}\n"+script[b:]
  # Process stream errors are replaced by a supervised stdin reader below.
  a=script.index('if(inputControl){');b=script.index('function stopped()',a);script=script[:a]+script[b:]
  self.eval('(async()=>{'+script+'\nsync("done",{code:process.exitCode});})().catch(e=>{console.log(JSON.stringify({event:"fatal",message:String(e)}));sync("done",{code:1});});')
  def input_reader():
   try:
    for line in sys.stdin:
     if line.strip()=='stop':self.emit("_signal('STOP')")
   finally:self.emit("_signal('SIGTERM')")
  threading.Thread(target=input_reader,daemon=True).start()
  while not self.done:
   if self.lib.am_js_jobs(self.ctx)<0:raise ValueError(self.lib.am_js_error(self.ctx).decode())
   now=time.monotonic()
   while self.timers and self.timers[0][0]<=now:self.eval(f'_tick({heapq.heappop(self.timers)[1]})')
   try:self.eval(self.pending.get(timeout=min(.005,max(0,self.timers[0][0]-now)) if self.timers else .005))
   except queue.Empty:pass
  return self.code
 def close(self):
  for wid in list(self.workers):self.handle({'op':'worker-close','worker':wid})
  if self.client:self.client.close()
  self.pool.shutdown(wait=True);self.lib.am_js_delete(self.ctx)

if __name__=='__main__':
 host=Host(sys.argv[1:])
 try:code=host.run()
 finally:host.close()
 sys.exit(code)
