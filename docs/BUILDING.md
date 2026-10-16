# 从源码构建 Windows x64 版本

维护者：情绪零碎の佳（Jia060117）。项目采用 GPL-2.0-or-later，第三方组件保留各自许可。

## 环境

- 64 位 Windows 10 / 11。
- Python 3.12 或更高版本，用于下载和打包；实际应用运行时使用锁定的官方 CPython 3.12.10 嵌入包。
- .NET Framework 4.8，编译器路径为系统目录下的 `Microsoft.NET/Framework64/v4.0.30319/csc.exe`。
- Node.js 22+，仅模拟前端测试需要，运行应用不需要。
- 首次准备依赖需要访问 python.org、PyPI 和 ziglang.org。具体 URL 与 SHA-256 在 `tools/dependencies.lock.json`。

## 构建

在仓库根目录运行：

```powershell
python tools/bootstrap.py
python tools/build_native.py
python tools/test.py
python tools/build.py
```

`bootstrap.py` 验证下载内容的 SHA-256，再提取到 `.deps`；不修改系统 Python，不需要管理员权限。Zig 0.14.1 从锁定下载包取得，无需单独安装 Visual Studio C++ 工具链。

`build_native.py` 从 `third_party` 原始源码构建 `quickjs.dll`、`rubberband.dll` 和本项目的 `automix-audio.dll` 到 `build/native`。QuickJS 单线程补丁在临时副本上应用；Rubber Band 使用内置 FFT 与 BQ resampler，完整编译参数都在脚本中。

`build.py` 收集应用、官方 Python 嵌入包、NumPy、上述 DLL 与许可声明，生成文件清单与 SHA-256，使用 LZMA 压缩后交给 C# 编译器，输出：

```text
dist/
  AutomixFor163Music.exe
  build-report.json
  SHA256SUMS.txt
```

这些步骤可在没有原作者工作目录和个人配置的机器上执行。不同系统工具链可能产生不同二进制哈希，当前不承诺逐字节一致。

## 验证范围

`tools/test.py` 使用内置 Python 与本次编译的原生库测试内存 WAV 解码、保音高节拍混音、尾段相关性、普通淡入淡出、能量曲线和峰值保护，再执行 Node.js 模拟测试，覆盖启动不控制播放、队列选择、控制权、异常恢复和音量渐变。**自动回归测试不会启动或控制用户的网易云。**

实际连接检查可显式执行：

```powershell
.\dist\AutomixFor163Music.exe --self-test --diagnostics "build\smoke"
```

该命令启动应用，检查内嵌运行时、界面和连接状态，不执行真实交接。若要进行实际切歌、跳转播放进度并在结束后恢复，可在运行兼容版网易云、队列就绪时显式增加 `--live-test`。真实音频输出与听感需在本机试听，模拟测试无法代替声卡与歌曲适配验证。

## 可选的本机输出校准

`src/automix/calibrate-render.py` 使用生成信号做回环测量，保存经过验证的声卡配置，不保存音乐。使用前请降低系统音量，按实际输出设备执行：

```powershell
.\.deps\python\python.exe src\automix\calibrate-render.py
```

校准文件保存在 `%LOCALAPPDATA%\Automix\render-profile.json`，仅用于同一输出设备的测量参考；不应提交到仓库或分享给其他设备。没有有效校准文件时，程序采用现有回退时钟路径。

## 发布

CI 会在 Windows 上从当前源码构建并上传构建产物。正式发行需同时提供应用、校验和、许可声明及相同版本的完整源码归档；`third_party` 与构建脚本属于对应源码的一部分。个人运行记录、设备校准、账号数据、歌曲或闭源研究材料不进入仓库。
