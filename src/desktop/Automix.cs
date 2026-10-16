// SPDX-License-Identifier: GPL-2.0-or-later
// Copyright (c) 2026 情绪零碎の佳 (Jia060117)
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Net.Sockets;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;

namespace AutomixDesktop {
static class Program {
    internal static readonly JavaScriptSerializer Json = new JavaScriptSerializer { MaxJsonLength = 8000000 };
    internal static string[] Args;
    internal static string DataRoot;
    internal static bool Test { get { return Args.Contains("--self-test"); } }
    internal static string Option(string name, string fallback) { int i=Array.IndexOf(Args,name);return i>=0 && i+1<Args.Length ? Args[i+1] : fallback; }
    [STAThread] static int Main(string[] args) {
        Args=args;
        // Some launchers supply both Path and PATH. .NET Framework's child
        // environment dictionary rejects that duplicate before a process starts.
        var env=Environment.GetEnvironmentVariables();
        foreach(var group in env.Keys.Cast<string>().GroupBy(k=>k,StringComparer.OrdinalIgnoreCase).Where(g=>g.Count()>1)){
            string value=Convert.ToString(env[group.First()]);foreach(string key in group)Environment.SetEnvironmentVariable(key,null);Environment.SetEnvironmentVariable(group.First(),value);
        }
        DataRoot=Path.GetFullPath(Option("--data",Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"Automix","data")));
        bool created;
        using(var mutex=new Mutex(true,"Local\\AutomixLite-3E2A53CD-"+Environment.UserName,out created)) {
            if(!created) { if(!Test)MessageBox.Show("Automix 已经运行，请从系统托盘打开。","Automix");return 2; }
            Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);
            try { Directory.CreateDirectory(DataRoot);using(var form=new MainForm())Application.Run(form);return Environment.ExitCode; }
            catch(Exception e) { if(Test)File.WriteAllText(Path.Combine(DataRoot,"startup-error.txt"),e.ToString());else MessageBox.Show("启动失败："+e.Message,"Automix");return 1; }
        }
    }
    internal static string Quote(string value) {
        // Windows CommandLineToArgvW quoting; paths may contain spaces or Chinese.
        var b=new StringBuilder("\"");int slashes=0;
        foreach(char c in value){if(c=='\\'){slashes++;continue;}if(c=='\"'){b.Append('\\',slashes*2+1);b.Append(c);}else{b.Append('\\',slashes);b.Append(c);}slashes=0;}
        b.Append('\\',slashes*2);return b.Append('"').ToString();
    }
    internal static string Hash(Stream s) {using(var sha=SHA256.Create())return BitConverter.ToString(sha.ComputeHash(s)).Replace("-","").ToLowerInvariant();}
    internal static string Extract() {
        var assembly=Assembly.GetExecutingAssembly();string digest;
        using(var s=assembly.GetManifestResourceStream("payload.sha256"))using(var r=new StreamReader(s))digest=r.ReadToEnd().Trim();
        string cache=Path.Combine(Path.GetFullPath(Option("--cache",Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"Automix","runtime"))),digest.Substring(0,20));
        string marker=Path.Combine(cache,".complete");
        if(File.Exists(marker)&&File.ReadAllText(marker)==digest&&Verify(cache))return cache;
        if(Directory.Exists(cache))Directory.Move(cache,cache+".corrupt-"+Guid.NewGuid().ToString("N"));
        string temp=cache+".extract-"+Guid.NewGuid().ToString("N");Directory.CreateDirectory(temp);
        try {
            using(var packed=assembly.GetManifestResourceStream("payload.lzma"))using(var s=new MemoryStream()) {
                if(Hash(packed)!=digest)throw new IOException("压缩包校验失败");packed.Position=0;
                byte[] properties=new byte[5];if(packed.Read(properties,0,5)!=5)throw new IOException("Invalid package header");
                byte[] sizeBytes=new byte[8];if(packed.Read(sizeBytes,0,8)!=8)throw new IOException("Invalid package size");
                long size=BitConverter.ToInt64(sizeBytes,0);if(size<0||size>120*1024*1024)throw new IOException("Package size exceeded");
                var decoder=new SevenZip.Compression.LZMA.Decoder();decoder.SetDecoderProperties(properties);decoder.Code(packed,s,packed.Length-13,size,null);
                if(s.Length!=size)throw new IOException("Invalid package length");s.Position=0;
                using(var archive=new ZipArchive(s,ZipArchiveMode.Read)) {
                string prefix=Path.GetFullPath(temp)+Path.DirectorySeparatorChar;
                foreach(var entry in archive.Entries) {
                    string target=Path.GetFullPath(Path.Combine(temp,entry.FullName.Replace('/',Path.DirectorySeparatorChar)));
                    if(!target.StartsWith(prefix,StringComparison.OrdinalIgnoreCase))throw new IOException("Invalid package path");
                    if(entry.FullName.EndsWith("/")){Directory.CreateDirectory(target);continue;}
                    Directory.CreateDirectory(Path.GetDirectoryName(target));entry.ExtractToFile(target,false);
                }
            }
            }
            if(!Verify(temp))throw new IOException("程序包校验失败");
            File.WriteAllText(Path.Combine(temp,".complete"),digest);Directory.CreateDirectory(Path.GetDirectoryName(cache));Directory.Move(temp,cache);
            return cache;
        } finally { if(Directory.Exists(temp))Directory.Delete(temp,true); }
    }
    static bool Verify(string root) {
        string manifest=Path.Combine(root,"manifest.json");if(!File.Exists(manifest))return false;
        string expected;using(var stream=Assembly.GetExecutingAssembly().GetManifestResourceStream("manifest.sha256"))using(var reader=new StreamReader(stream))expected=reader.ReadToEnd().Trim();
        using(var stream=File.OpenRead(manifest))if(Hash(stream)!=expected)return false;
        var files=Json.Deserialize<Dictionary<string,string>>(File.ReadAllText(manifest));
        foreach(var pair in files) {
            string file=Path.GetFullPath(Path.Combine(root,pair.Key.Replace('/',Path.DirectorySeparatorChar)));
            if(!file.StartsWith(Path.GetFullPath(root)+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase)||!File.Exists(file))return false;
            using(var s=File.OpenRead(file))if(Hash(s)!=pair.Value)return false;
        }return true;
    }
}

sealed class Backend : IDisposable {
    internal Process Process;
    internal string Root,Origin,Token;
    readonly HttpClient http=new HttpClient(new HttpClientHandler { UseProxy=false }) { Timeout=TimeSpan.FromSeconds(40) };
    readonly TaskCompletionSource<bool> ready=new TaskCompletionSource<bool>();
    string error="";bool closing;
    internal async Task Start(string root) {
        Root=root;
        int port;var listener=new TcpListener(IPAddress.Loopback,0);listener.Start();port=((IPEndPoint)listener.LocalEndpoint).Port;listener.Stop();
        var info=new ProcessStartInfo(Path.Combine(root,"runtime","python","python.exe"),"-X utf8 -B "+Program.Quote(Path.Combine(root,"app","automix-probe","lite_server.py"))+" --port "+port+" --data "+Program.Quote(Program.DataRoot)+(Program.Test?" --verify":""));
        info.WorkingDirectory=root;info.UseShellExecute=false;info.CreateNoWindow=true;info.RedirectStandardInput=true;info.RedirectStandardOutput=true;info.RedirectStandardError=true;
        info.StandardOutputEncoding=Encoding.UTF8;info.StandardErrorEncoding=Encoding.UTF8;
        info.EnvironmentVariables["PYTHONUTF8"]="1";info.EnvironmentVariables["PYTHONUNBUFFERED"]="1";info.EnvironmentVariables["PYTHONNOUSERSITE"]="1";
        info.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"]="1";
        info.EnvironmentVariables.Remove("PYTHONHOME");info.EnvironmentVariables.Remove("PYTHONPATH");
        // Prove that the client does not discover developer tools from PATH.
        info.EnvironmentVariables["PATH"]=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows),"System32");
        Process=new Process{StartInfo=info,EnableRaisingEvents=true};
        Process.OutputDataReceived+=(s,e)=>{
            if(e.Data==null)return;
            try { var m=Program.Json.Deserialize<Dictionary<string,object>>(e.Data);if(Convert.ToString(m["event"])=="desktop-ready"){Origin=Convert.ToString(m["origin"]);Token=Convert.ToString(m["token"]);ready.TrySetResult(true);} }catch{}
        };
        Process.ErrorDataReceived+=(s,e)=>{if(e.Data!=null)error=(error+e.Data+"\n").Substring(Math.Max(0,(error+e.Data+"\n").Length-2000));};
        Process.Exited+=(s,e)=>ready.TrySetException(new IOException("混音服务无法启动："+error));
        Process.Start();Process.BeginOutputReadLine();Process.BeginErrorReadLine();
        if(await Task.WhenAny(ready.Task,Task.Delay(20000))!=ready.Task)throw new IOException("混音服务启动超时");
        await ready.Task;
    }
    internal async Task<Dictionary<string,object>> Request(string api,object body=null) {
        var message=new HttpRequestMessage(body==null?HttpMethod.Get:HttpMethod.Post,Origin+api);
        if(body!=null){message.Headers.TryAddWithoutValidation("Origin",Origin);message.Headers.TryAddWithoutValidation("X-Automix-Token",Token);message.Content=new StringContent(Program.Json.Serialize(body),Encoding.UTF8,"application/json");}
        using(message)using(var response=await http.SendAsync(message)) {
            var result=Program.Json.Deserialize<Dictionary<string,object>>(await response.Content.ReadAsStringAsync());
            if(!response.IsSuccessStatusCode)throw new IOException(result.ContainsKey("error")?Convert.ToString(result["error"]):"连接失败");return result;
        }
    }
    internal async Task Close(bool disconnect=false) {
        if(closing)return;closing=true;
        if(Process!=null&&!Process.HasExited) {
            try {if(disconnect)Process.StandardInput.Close();else{await Process.StandardInput.WriteLineAsync("shutdown");await Process.StandardInput.FlushAsync();}}catch(IOException){}
            await Task.Run(()=>Process.WaitForExit());
        }
    }
    public void Dispose(){http.Dispose();if(Process!=null)Process.Dispose();}
}

sealed class MainForm : Form {
    readonly Color bg=Color.FromArgb(17,22,28),card=Color.FromArgb(27,35,44),text=Color.FromArgb(232,239,244),muted=Color.FromArgb(155,174,188),green=Color.FromArgb(152,233,193);
    readonly Label title=new Label(),subtitle=new Label(),track=new Label(),next=new Label(),stage=new Label(),queue=new Label(),count=new Label(),hint=new Label();
    readonly Button start=new FlatButton(),stop=new FlatButton(),connect=new FlatButton(),folder=new FlatButton(),modeButton=new FlatButton();
    readonly ComboBox mode=new ComboBox();readonly TextBox logs=new TextBox();
    readonly System.Windows.Forms.Timer timer=new System.Windows.Forms.Timer{Interval=1000};
    readonly ToolTip tips=new ToolTip();readonly NotifyIcon tray=new NotifyIcon();
    readonly Backend backend=new Backend();Dictionary<string,object> state;bool refreshing,action,exiting,closed,initialized;Icon appIcon;
    internal MainForm() {
        SuspendLayout();AutoScaleDimensions=new SizeF(96F,96F);
        Text="AutomixFor163Music";ClientSize=new Size(320,350);StartPosition=FormStartPosition.CenterScreen;
        FormBorderStyle=FormBorderStyle.FixedSingle;MaximizeBox=false;
        BackColor=bg;ForeColor=text;Font=new Font("Microsoft YaHei UI",9F);AutoScaleMode=AutoScaleMode.Dpi;
        appIcon=MakeIcon();Icon=appIcon;
        SetupLabel(title,"Automix",20,10,280,30,18,Color.White);SetupLabel(subtitle,"网易云音乐 · 自动混音",20,40,280,22,9,muted);
        var p=new Panel { Location=new Point(20,66),Size=new Size(280,117),BackColor=card,Anchor=AnchorStyles.Top|AnchorStyles.Left|AnchorStyles.Right };Controls.Add(p);
        SetupLabel(track,"正在启动…",12,10,256,28,13,text,p);SetupLabel(next,"下一首  —",12,43,256,22,9,muted,p);
        SetupLabel(stage,"准备运行文件",12,69,256,22,10,green,p);SetupLabel(queue,"顺序 / 列表循环 / 心动模式",12,95,256,19,8.5F,muted,p);
        mode.Items.AddRange(new object[]{"持续自动混音","快速测试：1 次交接"});mode.SelectedIndex=0;
        SetupButton(modeButton,"持续自动混音 ▾",20,197,168,28,false);
        var modes=new ContextMenuStrip();modes.Items.Add("持续自动混音",null,(s,e)=>mode.SelectedIndex=0);modes.Items.Add("快速测试：1 次交接",null,(s,e)=>mode.SelectedIndex=1);modeButton.Click+=(s,e)=>modes.Show(modeButton,new Point(0,modeButton.Height));modeButton.Disposed+=(s,e)=>modes.Dispose();
        SetupButton(connect,"连接网易云",198,197,102,28,false);SetupButton(start,"开始自动混音",20,237,170,36,true);SetupButton(stop,"停止并恢复",200,237,100,36,false);
        SetupLabel(count,"本次交接  0",20,286,150,20,9,muted);SetupButton(folder,"运行记录 ↗",194,282,106,27,false);
        SetupLabel(hint,"先在网易云播放音乐，然后点击开始。",20,316,280,28,9,muted);
        logs.Visible=false;logs.SetBounds(20,350,280,22);logs.Anchor=AnchorStyles.Left|AnchorStyles.Right|AnchorStyles.Top;logs.Multiline=true;logs.ReadOnly=true;logs.BorderStyle=BorderStyle.None;logs.BackColor=bg;logs.ForeColor=muted;logs.TabStop=false;Controls.Add(logs);
        tips.SetToolTip(modeButton,"持续模式等待歌尾；快速测试会跳到歌尾，完成后恢复原歌曲和进度。");tips.SetToolTip(stop,"停止混音，并等待网易云恢复音量和播放状态。");tips.SetToolTip(connect,"未连接时，可启动或重启网易云 3.1.40 并启用本地控制端口。");
        start.Enabled=false;stop.Enabled=false;connect.Enabled=false;
        start.Click+=async(s,e)=>await Perform(async()=>{await StartMix();});stop.Click+=async(s,e)=>await Perform(async()=>{await backend.Request("/api/stop",new{});});
        connect.Click+=async(s,e)=>await Perform(ConnectPlayer);folder.Click+=(s,e)=>System.Diagnostics.Process.Start(new ProcessStartInfo("explorer.exe",Program.Quote(Program.DataRoot)) { UseShellExecute=true });
        timer.Tick+=async(s,e)=>await RefreshState();mode.SelectedIndexChanged+=(s,e)=>{modeButton.Text=Convert.ToString(mode.SelectedItem)+" ▾";UpdateControls();};
        var menu=new ContextMenuStrip();menu.Items.Add("打开 Automix",null,(s,e)=>RestoreWindow());menu.Items.Add("停止并恢复",null,async(s,e)=>{if(initialized)await Perform(async()=>{await backend.Request("/api/stop",new{});});});menu.Items.Add("退出",null,(s,e)=>Close());
        tray.Icon=appIcon;tray.Text="Automix · 自动混音";tray.ContextMenuStrip=menu;tray.DoubleClick+=(s,e)=>RestoreWindow();
        Resize+=(s,e)=>{if(WindowState==FormWindowState.Minimized){tray.Visible=true;Hide();}};
        FormClosing+=async(s,e)=>{if(closed)return;e.Cancel=true;if(exiting)return;exiting=true;timer.Stop();start.Enabled=false;stop.Enabled=false;connect.Enabled=false;stage.Text="正在停止并恢复网易云…";hint.Text="恢复完成后会自动退出。";try{await backend.Close();closed=true;Close();}catch(Exception err){stage.Text="恢复尚未完成";hint.Text=err.Message;exiting=false;timer.Start();}};
        Shown+=async(s,e)=>await Initialize();
        ResumeLayout(true);
    }
    void SetupLabel(Label label,string value,int x,int y,int w,int h,float size,Color color,Control parent=null){label.Text=value;label.SetBounds(x,y,w,h);label.ForeColor=color;label.Font=new Font("Microsoft YaHei UI",size);label.AutoEllipsis=true;label.Anchor=AnchorStyles.Left|AnchorStyles.Right|AnchorStyles.Top;(parent??this).Controls.Add(label);}
    void SetupButton(Button b,string value,int x,int y,int w,int h,bool primary){b.Text=value;b.SetBounds(x,y,w,h);b.FlatStyle=FlatStyle.Flat;b.FlatAppearance.BorderSize=primary?0:1;b.FlatAppearance.BorderColor=Color.FromArgb(52,66,80);b.BackColor=primary?green:card;b.ForeColor=primary?Color.FromArgb(15,40,29):text;b.Cursor=Cursors.Hand;Controls.Add(b);}
    static Icon MakeIcon(){using(var bitmap=new Bitmap(32,32))using(var g=Graphics.FromImage(bitmap)){g.Clear(Color.FromArgb(17,22,28));using(var brush=new SolidBrush(Color.FromArgb(152,233,193)))g.FillEllipse(brush,1,1,30,30);using(var pen=new Pen(Color.FromArgb(17,22,28),3)){g.DrawLines(pen,new[]{new Point(8,22),new Point(13,9),new Point(18,22),new Point(22,12)});}IntPtr handle=bitmap.GetHicon();try{return (Icon)Icon.FromHandle(handle).Clone();}finally{DestroyIcon(handle);}}}
    [System.Runtime.InteropServices.DllImport("user32.dll")]static extern bool DestroyIcon(IntPtr h);
    void RestoreWindow(){Show();WindowState=FormWindowState.Normal;Activate();tray.Visible=false;}
    static Dictionary<string,object> Obj(Dictionary<string,object> m,string key){object v;return m!=null&&m.TryGetValue(key,out v)?v as Dictionary<string,object>:null;}
    static string Str(Dictionary<string,object> m,string key,string fallback=""){object v;return m!=null&&m.TryGetValue(key,out v)&&v!=null?Convert.ToString(v):fallback;}
    static bool Flag(Dictionary<string,object> m,string key){return Str(m,key)=="True";}
    async Task Initialize(){
        try {string root=await Task.Run(()=>Program.Extract());stage.Text="正在连接网易云…";await backend.Start(root);initialized=true;connect.Enabled=true;await backend.Request("/api/check",new{});await RefreshState();timer.Start();if(Program.Test)await SelfTest();}
        catch(Exception e){stage.Text="启动失败";hint.ForeColor=Color.Salmon;hint.Text=e.Message;if(Program.Test){SaveTest(new{passed=false,error=e.ToString()});Environment.ExitCode=1;Close();}}
    }
    async Task Perform(Func<Task> work){if(action||exiting)return;action=true;UpdateControls();try{await work();await RefreshState();}catch(Exception e){hint.ForeColor=Color.Salmon;hint.Text=e.Message;tips.SetToolTip(hint,hint.Text);}finally{action=false;UpdateControls();}}
    async Task StartMix(){await backend.Request("/api/start",new{mode=mode.SelectedIndex==0?"continuous":"test",pilot=false,transitions=1});}
    async Task RefreshState(){if(refreshing||!initialized||exiting)return;refreshing=true;try{state=await backend.Request("/api/state");Render();}catch(Exception e){stage.Text="连接暂时不可用";hint.Text=e.Message;start.Enabled=false;}finally{refreshing=false;}}
    void UpdateControls(){var p=Obj(state,"player");bool running=Flag(state,"running");start.Enabled=initialized&&!action&&!exiting&&!running&&Flag(p,"connected")&&Flag(p,"queueReady")&&!Flag(p,"controllerBusy")&&(mode.SelectedIndex==1||Str(p,"state")=="playing");stop.Enabled=initialized&&!action&&running&&!Flag(state,"stopping")&&!exiting;connect.Enabled=initialized&&!action&&!running&&!exiting;modeButton.Enabled=!running&&!action&&!exiting;}
    void Render(){
        var p=Obj(state,"player");bool running=Flag(state,"running"),connected=Flag(p,"connected");
        track.Text=Str(p,"current","网易云未连接");next.Text="下一首  "+Str(p,"next","—");
        var names=new Dictionary<string,string>{{"idle","待机"},{"checking","检查连接"},{"preparing","分析下一组歌曲"},{"waiting","已就绪 · 等待歌尾"},{"mixing","正在混音"},{"warming","下一首静音预跑"},{"handoff","平滑交接音量"},{"verifying","已交接 · 验证中"},{"stopping","正在停止并恢复"},{"error","本次运行已结束"}};string code=Str(state,"stage","idle");stage.Text=names.ContainsKey(code)?names[code]:code;
        queue.Text=connected?Str(p,"queueModeLabel","播放列表")+" · "+Str(p,"queueLength","—")+" 首":"支持网易云 3.1.40 · 点击连接";count.Text="本次交接  "+Str(state,"transitions","0");
        if(!action){hint.ForeColor=muted;hint.Text=running?"最小化到托盘后仍会继续运行。":!connected?"点击连接，可启动或重启网易云并开启本地控制。":Flag(p,"controllerBusy")?"另一控制进程正在运行，请先停止它。":!Flag(p,"queueReady")?Str(p,"reason","请使用顺序、列表循环或心动模式。"):Str(p,"state")!="playing"?"先在网易云播放音乐，然后点击开始。":"已连接。按网易云右侧播放列表自动衔接。";}
        object raw;if(state.TryGetValue("logs",out raw)&&raw is object[]){var entries=(object[])raw;logs.Text=String.Join(Environment.NewLine,entries.Skip(Math.Max(0,entries.Length-1)).Select(v=>Str(v as Dictionary<string,object>,"message")));}
        tips.SetToolTip(hint,hint.Text);UpdateControls();
    }
    async Task ConnectPlayer(){
        await backend.Request("/api/check",new{});await RefreshState();if(Flag(Obj(state,"player"),"connected"))return;
        if(MessageBox.Show(this,"需要启动或重启网易云音乐，并开启仅本机可访问的控制端口。当前播放会中断，登录信息和歌单会保留。\n\n现在连接吗？","连接网易云",MessageBoxButtons.OKCancel,MessageBoxIcon.Information)!=DialogResult.OK)return;
        string exe=FindNetease();if(FileVersionInfo.GetVersionInfo(exe).FileVersion!="3.1.40.205461")throw new IOException("当前仅验证了网易云 3.1.40.205461。请使用该版本。");
        var socket=new TcpClient();try {var pending=socket.ConnectAsync("127.0.0.1",19222);if(await Task.WhenAny(pending,Task.Delay(500))==pending&&socket.Connected)throw new IOException("控制端口 19222 被占用，请先退出使用该端口的程序。");}catch(SocketException){}finally{socket.Close();}
        foreach(var process in System.Diagnostics.Process.GetProcessesByName("cloudmusic")){using(process){string actual;try{actual=process.MainModule.FileName;}catch{continue;}if(!String.Equals(actual,exe,StringComparison.OrdinalIgnoreCase))continue;try{process.CloseMainWindow();}catch{}}}
        await Task.Delay(1200);
        // The user explicitly chose restart. Only this verified executable is stopped.
        for(int attempt=0;attempt<5;attempt++){bool remains=false;foreach(var process in System.Diagnostics.Process.GetProcessesByName("cloudmusic")){using(process){try{if(!String.Equals(process.MainModule.FileName,exe,StringComparison.OrdinalIgnoreCase))continue;remains=true;process.Kill();process.WaitForExit(1500);}catch(InvalidOperationException){}}}if(!remains)break;await Task.Delay(500);}
        foreach(var process in System.Diagnostics.Process.GetProcessesByName("cloudmusic")){using(process){try{if(String.Equals(process.MainModule.FileName,exe,StringComparison.OrdinalIgnoreCase))throw new IOException("网易云仍未退出，暂未启动新实例。请从网易云托盘退出后重试。");}catch(InvalidOperationException){}}}
        using(var process=System.Diagnostics.Process.Start(new ProcessStartInfo(exe,"--remote-debugging-port=19222 --remote-debugging-address=127.0.0.1") { WorkingDirectory=Path.GetDirectoryName(exe),UseShellExecute=true })){}
        for(int i=0;i<25;i++){await Task.Delay(800);await backend.Request("/api/check",new{});await RefreshState();if(Flag(Obj(state,"player"),"connected"))return;}
        throw new IOException("网易云已启动，暂未找到播放器。请等待窗口加载后再次点击连接。");
    }
    string FindNetease(){
        foreach(var p in System.Diagnostics.Process.GetProcessesByName("cloudmusic")){using(p){try{var file=p.MainModule.FileName;if(File.Exists(file)&&FileVersionInfo.GetVersionInfo(file).FileVersion=="3.1.40.205461")return file;}catch{}}}
        foreach(var file in new[]{@"C:\Program Files\NetEase\CloudMusic\cloudmusic.exe",@"C:\Program Files (x86)\NetEase\CloudMusic\cloudmusic.exe",Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"NetEase","CloudMusic","cloudmusic.exe")})if(File.Exists(file))return file;
        using(var dialog=new OpenFileDialog{Title="选择网易云 cloudmusic.exe",Filter="网易云音乐|cloudmusic.exe",CheckFileExists=true}){if(dialog.ShowDialog(this)==DialogResult.OK)return dialog.FileName;}
        throw new IOException("未选择网易云音乐。");
    }
    async Task<string> RuntimeCheck(string exe,string arguments){
        var info=new ProcessStartInfo(exe,arguments){UseShellExecute=false,CreateNoWindow=true,RedirectStandardOutput=true,RedirectStandardError=true,StandardOutputEncoding=Encoding.UTF8,StandardErrorEncoding=Encoding.UTF8};
        info.EnvironmentVariables["PATH"]=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows),"System32");info.EnvironmentVariables.Remove("PYTHONHOME");info.EnvironmentVariables.Remove("PYTHONPATH");info.EnvironmentVariables["PYTHONUTF8"]="1";
        using(var p=System.Diagnostics.Process.Start(info)){var output=p.StandardOutput.ReadToEndAsync();var err=p.StandardError.ReadToEndAsync();await Task.Run(()=>p.WaitForExit());if(p.ExitCode!=0)throw new IOException(await err);return await output;}
    }
    void SaveTest(object report){string folder=Program.Option("--diagnostics",Program.DataRoot);Directory.CreateDirectory(folder);File.WriteAllText(Path.Combine(folder,"desktop-report.json"),Program.Json.Serialize(report),new UTF8Encoding(false));}
    void CaptureView(string name){string folder=Program.Option("--diagnostics",Program.DataRoot);Directory.CreateDirectory(folder);using(var image=new Bitmap(Width,Height)){DrawToBitmap(image,new Rectangle(0,0,Width,Height));image.Save(Path.Combine(folder,name));}}
    async Task SelfTest(){
        try {
            var py=await RuntimeCheck(Path.Combine(backend.Root,"runtime","python","python.exe"),"-I -B -X utf8 -c "+Program.Quote("import sys,numpy,ctypes,wasapi_audio,memory_mix_worker,process_audio,native_clock,lite_audio,lite_controller; print(numpy.__version__); print(numpy.__file__); print(sys.executable)"));
            var ff=await RuntimeCheck(Path.Combine(backend.Root,"runtime","python","python.exe"),"-I -B -X utf8 -c "+Program.Quote("import ctypes,lite_audio;from lite_controller import Host;h=Host(['--directory','"+Program.DataRoot.Replace("\\","/")+"']);h.eval('_host(JSON.stringify({op: '+chr(39)+'log'+chr(39)+',line: JSON.stringify({engine: 1+2,modern: [1,2].findLast(x=>x>0)})}))');h.close();print('rubberband',ctypes.CDLL(str(lite_audio.HERE / 'rubberband.dll')).rubberband_new)"));
            WindowState=FormWindowState.Minimized;await Task.Delay(100);bool trayPassed=!Visible&&tray.Visible;RestoreWindow();if(!trayPassed)throw new IOException("Tray minimize failed");
            await RefreshState();var before=state;CaptureView("desktop-ready.png");
            bool rampTest=Program.Args.Contains("--ramp-stop-test")||Program.Args.Contains("--ramp-backend-loss-test");
            bool live=Program.Args.Contains("--live-test"),stopTest=Program.Args.Contains("--stop-test")||Program.Args.Contains("--ramp-stop-test"),backendLoss=Program.Args.Contains("--backend-loss-test")||Program.Args.Contains("--ramp-backend-loss-test"),loss=Program.Args.Contains("--parent-loss-test")||backendLoss;Dictionary<string,object> lossRecovery=null;
            if(live||stopTest||loss){
                if(!Flag(Obj(state,"player"),"connected")||!Flag(Obj(state,"player"),"queueReady"))throw new IOException("Live player unavailable");
                mode.SelectedIndex=1;await StartMix();var deadline=DateTime.UtcNow.AddMinutes(4);bool sawRunning=false,stopped=false;
                do {await Task.Delay(250);await RefreshState();if(Flag(state,"running"))sawRunning=true;
                    if(!stopped&&(stopTest||loss)&&Str(state,"stage")== (rampTest?"handoff":"warming")) {
                        stopped=true;CaptureView(rampTest?"desktop-handoff.png":"desktop-warming.png");
                        if(loss){
                            timer.Stop();var latest=Directory.GetDirectories(Program.DataRoot,"panel-*").OrderByDescending(d=>d).First();
                            if(backendLoss){backend.Process.Kill();await Task.Run(()=>backend.Process.WaitForExit());}else await backend.Close(true);
                            var recoveryDeadline=DateTime.UtcNow.AddSeconds(45);
                            while(lossRecovery==null){try{lossRecovery=Program.Json.Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(latest,"memory-transition-test.json")));}catch{}if(lossRecovery==null){if(DateTime.UtcNow>recoveryDeadline)throw new IOException("Parent loss recovery report timed out");await Task.Delay(100);}}
                            if(!Flag(lossRecovery,"restored"))throw new IOException("Parent pipe loss did not restore native playback");break;
                        }else await backend.Request("/api/stop",new{});
                    }
                    if(DateTime.UtcNow>deadline)throw new IOException("Live transition test timed out");
                }while(!sawRunning||Flag(state,"running"));
                if((stopTest||loss)&&!stopped)throw new IOException("Did not reach requested handoff stage");
                if(!loss){await backend.Request("/api/check",new{});await RefreshState();var result=Obj(state,"lastResult");if(!Flag(result,"restored"))throw new IOException("Native playback was not restored");if(live&&Str(result,"transitions")!="1")throw new IOException("No completed transition");}
            }
            CaptureView("desktop-result.png");SaveTest(new{passed=true,bundledPython=py.Trim(),rubberband=true,trayMinimizeRestore=trayPassed,developerPathRemoved=true,cache=backend.Root,backendPid=backend.Process.Id,before=before,after=state,liveTest=live,stopDuringWarmup=stopTest&&!rampTest,interruptDuringRamp=rampTest,parentPipeLoss=loss,backendKilled=backendLoss,parentLossRecovery=lossRecovery,executable=Application.ExecutablePath});
        }catch(Exception e){Environment.ExitCode=1;SaveTest(new{passed=false,error=e.ToString(),state=state});}
        finally{Close();}
    }
    protected override void Dispose(bool disposing){if(disposing){timer.Dispose();tray.Visible=false;tray.Dispose();tips.Dispose();backend.Dispose();if(appIcon!=null)appIcon.Dispose();}base.Dispose(disposing);}
}
sealed class FlatButton : Button {
    protected override void OnPaint(PaintEventArgs e){
        Color fill=Enabled?BackColor:Color.FromArgb(35,43,51),ink=Enabled?ForeColor:Color.FromArgb(106,125,137);
        using(var brush=new SolidBrush(fill))e.Graphics.FillRectangle(brush,ClientRectangle);
        if(FlatAppearance.BorderSize>0)using(var pen=new Pen(FlatAppearance.BorderColor))e.Graphics.DrawRectangle(pen,0,0,Width-1,Height-1);
        TextRenderer.DrawText(e.Graphics,Text,Font,ClientRectangle,ink,TextFormatFlags.HorizontalCenter|TextFormatFlags.VerticalCenter|TextFormatFlags.EndEllipsis);
        if(Focused&&Enabled)ControlPaint.DrawFocusRectangle(e.Graphics,new Rectangle(4,4,Width-8,Height-8),ink,fill);
    }
}
}
