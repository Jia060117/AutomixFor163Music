# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (c) 2026 情绪零碎の佳 (Jia060117)
"""Private localhost UI service for the compact desktop build."""
import argparse,datetime,http.server,json,pathlib,re,secrets,subprocess,sys,threading,time
from lite_cdp import inspect_player
HERE=pathlib.Path(__file__).resolve().parent
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def clean(s):return re.sub(r'https?://\S+','[地址]',str(s))[:400]
class Panel:
 def __init__(self,args):
  self.args=args;self.origin=f'http://127.0.0.1:{args.port}';self.token=secrets.token_hex(32);self.lock=threading.RLock();self.child=None;self.closing=False;self.checking=False;self.last_check=0
  self.state=dict(running=False,stopping=False,stage='idle',transitions=0,logs=[],player=None,lastResult=None,config=None)
 def log(self,event,message):
  with self.lock:self.state['logs'].append(dict(time=utc(),event=event,message=clean(message)));self.state['logs']=self.state['logs'][-100:]
 def refresh(self):
  if self.checking:return
  self.checking=True
  try:
   value=inspect_player()
   with self.lock:self.state['player']=value;self.last_check=time.monotonic()
  finally:self.checking=False
 def stop(self):
  with self.lock:
   if self.child and not self.state['stopping']:
    self.state.update(stopping=True,stage='stopping');self.log('stop','正在停止，并等待网易云恢复。')
    try:self.child.stdin.write('stop\n');self.child.stdin.flush()
    except OSError:self.log('error','停止指令发送失败，请检查网易云音量。')
 def consume(self,m):
  e=m.get('event')
  with self.lock:
   if e=='mix-ready':self.state.update(stage='waiting',A=m['A'],B=m['B'],mixMode=m['mode'],queueModeLabel=m['queueModeLabel']);self.log(e,f'{m["A"]} → {m["B"]}：过渡已就绪，等待歌尾。')
   elif e=='bridge-started':self.state['stage']='mixing';self.log(e,'过渡片段正在播放。')
   elif e in ('B-playing-muted','B-playing-pilot'):self.state['stage']='warming';self.log(e,'下一首正在静音预跑。')
   elif e=='handoff-ramping':self.state['stage']='handoff';self.log(e,'正在平滑交接音量。')
   elif e=='B-unmuted':self.state['stage']='verifying';self.log(e,'已恢复下一首音量。')
   elif e=='controller-memory':self.state['transitions']+=1;self.state['stage']='preparing'
   elif e=='measurement':
    b=m.get('BhandoffVerification') or {};self.state['measurement']=dict(valid=m['valid'],Bvalid=b.get('valid',m['valid']),Bresidual=b.get('timelineResidualMilliseconds',m.get('timelineShiftMilliseconds',{}).get('mix_to_B')));self.log(e,'波形交接验证'+('通过' if self.state['measurement']['Bvalid'] else '未通过'))
   elif e=='fallback':self.log(e,m['message'])
   elif e=='queue-handoff-recovered':self.state['stage']='preparing';self.log(e,'播放列表已变化，恢复当前歌曲并重新准备。')
 def start(self,body):
  if body.get('mode') not in ('continuous','test') or body.get('pilot') is not False:raise ValueError('运行选项无效')
  if body['mode']=='test' and body.get('transitions') not in (1,2,3):raise ValueError('测试次数无效')
  with self.lock:
   if self.child or self.state['running'] or self.closing:raise ValueError('已有任务运行中')
   self.state.update(running=True,stage='checking')
  try:
   self.refresh();p=self.state['player']
   if not p.get('connected') or not p.get('queueReady'):raise ValueError(p.get('reason','播放队列未就绪'))
   if p.get('controllerBusy'):raise ValueError('另一个 Automix 控制进程正在运行')
   if body['mode']=='continuous' and p.get('state')!='playing':raise ValueError('请先在网易云播放音乐')
   if self.closing:raise ValueError('客户端正在关闭')
   directory=pathlib.Path(self.args.data)/('panel-'+utc().replace(':','-').replace('.','-'));directory.mkdir(parents=True)
   report=directory/('memory-transition-test.json' if body['mode']=='test' else 'memory-automix-report.json')
   cmd=[sys.executable,'-X','utf8','-B',str(HERE/'lite_controller.py'),'--stdin-control','--directory',str(directory),'--python',sys.executable,'--ffmpeg',str(HERE/'automix-audio.dll')]
   if body['mode']=='test':cmd+=['--test-transitions',str(body['transitions'])]
   if self.args.verify:cmd.append('--verify')
   with self.lock:
    self.state.update(config=body,transitions=0,lastResult=None,measurement=None,A=None,B=None,stopping=False,stage='preparing')
    self.child=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8',bufsize=1,creationflags=subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP)
   def consume():
    child=self.child
    for line in child.stdout:
     try:self.consume(json.loads(line))
     except Exception:self.log('warning','一条运行状态未能显示，继续等待控制进程完成。')
    child.wait();child.stdout.close();child.stdin.close()
    with self.lock:
     self.child=None;self.state.update(running=False,stopping=False,stage='idle' if child.returncode==0 else 'error')
     try:
      r=json.loads(report.read_text(encoding='utf-8'));self.state['lastResult']=dict(transitions=r.get('totalTransitions',len(r['transitions'])),restored=r.get('restored',False),recoveredNativePlayback=r.get('recoveredNativePlayback'),errors=[clean(e) for e in r['errors']],reportPath=str(report))
     except (ValueError,OSError):self.state['lastResult']=dict(transitions=0,restored=False,errors=['控制进程未写入恢复报告'])
     self.log('finished','本次运行已结束。' if child.returncode==0 else '运行结束，请查看错误记录。')
    self.refresh()
   threading.Thread(target=consume,daemon=True).start();self.log('start','已按网易云当前播放列表启动自动混音。')
  except Exception:
   self.state.update(running=False,stage='error');raise
 def close(self):
  self.closing=True;self.stop()
  while self.child:time.sleep(.02)
  self.server.shutdown()

def main():
 p=argparse.ArgumentParser();p.add_argument('--port',type=int,required=True);p.add_argument('--data',required=True);p.add_argument('--verify',action='store_true');args=p.parse_args()
 if not 1024<=args.port<=65535:raise ValueError('Invalid port')
 app=Panel(args)
 class Handler(http.server.BaseHTTPRequestHandler):
  def log_message(self,*a):pass
  def respond(self,status,value):
   data=json.dumps(value,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
  def do_GET(self):
   if self.headers.get('Host')!=f'127.0.0.1:{args.port}':return self.respond(403,{'error':'Host rejected'})
   if self.path!='/api/state':return self.respond(404,{'error':'Not found'})
   with app.lock:value=json.loads(json.dumps(app.state))
   self.respond(200,value)
  def do_POST(self):
   if self.headers.get('Host')!=f'127.0.0.1:{args.port}' or self.headers.get('Origin')!=app.origin or self.headers.get('X-Automix-Token')!=app.token:return self.respond(403,{'error':'Origin or token rejected'})
   if not self.headers.get('Content-Type','').lower().startswith('application/json'):return self.respond(415,{'error':'JSON required'})
   try:
    size=int(self.headers.get('Content-Length','0'))
    if not 0<=size<=2048:return self.respond(413,{'error':'Request too large'})
    body=json.loads(self.rfile.read(size) or b'{}')
    if self.path=='/api/check':app.refresh()
    elif self.path=='/api/start':app.start(body)
    elif self.path=='/api/stop':app.stop()
    else:return self.respond(404,{'error':'Not found'})
    with app.lock:value=json.loads(json.dumps(app.state))
    self.respond(200,value)
   except Exception as e:self.respond(400,{'error':clean(e)})
 app.server=http.server.ThreadingHTTPServer(('127.0.0.1',args.port),Handler);app.server.timeout=8
 def supervise():
  try:
   for line in sys.stdin:
    if line.strip()=='shutdown':break
  finally:app.close()
 threading.Thread(target=supervise,daemon=True).start()
 def poll():
  while not app.closing:
   app.refresh();time.sleep(2.5)
 threading.Thread(target=poll,daemon=True).start()
 print(json.dumps(dict(event='desktop-ready',origin=app.origin,token=app.token)),flush=True)
 app.server.serve_forever(poll_interval=.05);app.server.server_close()
if __name__=='__main__':main()
