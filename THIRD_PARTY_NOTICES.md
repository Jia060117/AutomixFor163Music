# 第三方组件、参考来源与版权说明

AutomixFor163Music 的原创代码由情绪零碎の佳（Jia060117）以 **GPL-2.0-or-later** 发布。下列第三方代码保留各自原始许可与版权；项目的 GPL 声明不更改它们的许可，也不表示上游作者认可本项目。

## 直接集成和随程序打包的开源组件

| 项目 / 版本 | 上游与版权主体 | 用途 | 许可与对应材料 |
| --- | --- | --- | --- |
| Rubber Band 4.0.0 | [Breakfast Quay / Particular Programs Ltd](https://github.com/breakfastquay/rubberband)，主要作者 Chris Cannam；Copyright 2007–2024 Particular Programs Ltd | 保音高时间伸缩，`rubberband.dll` | GPL-2.0-or-later；[完整上游源码与 COPYING](third_party/rubberband-4.0.0/)。本项目使用内置 FFT、BQ resampler；不启用 FFTW、IPP、libsamplerate、Speex 或音频插件接口。 |
| QuickJS 2026-06-04 | [Fabrice Bellard、Charlie Gordon 及上游贡献者](https://bellard.org/quickjs/) | 运行控制逻辑，`quickjs.dll` | MIT；[上游源码与 LICENSE](third_party/quickjs-2026-06-04/)。构建时在临时副本禁用 `CONFIG_ATOMICS`，服务于单线程宿主；仓库保留上游原文。自有 C 宿主见 `src/native/quickjs-host.c`。 |
| LZMA SDK 26.03，C# 解码器子集 | [Igor Pavlov / 7-Zip](https://www.7-zip.org/sdk.html) | 单文件应用解压已校验的内嵌载荷 | Public domain；[保留的源码和 SDK 原始说明](third_party/lzma-sdk/)。使用 `CS/7zip` 解码器的 7 个文件，无修改；不包含 7-Zip 主程序的其他模块。 |
| CPython 3.12.10 Windows x64 嵌入包 | [Python Software Foundation 及 Python 贡献者](https://www.python.org/downloads/release/python-31210/) | 随应用运行 Python 音频分析和控制进程 | PSF License Agreement 及原始包所附第三方声明；[官方源代码](https://www.python.org/ftp/python/3.12.10/Python-3.12.10.tar.xz)。未修改解释器；构建脚本配置 `python312._pth`。内嵌包保留 `runtime/python/LICENSE.txt`。 |
| NumPy 2.3.5，cp312 Windows x64 wheel | [NumPy Developers](https://github.com/numpy/numpy/tree/v2.3.5) | 频谱、节拍、相关性与音频数组运算 | BSD-3-Clause 及 wheel 自带组件许可；未修改库。原始 wheel 许可位于 `runtime/python/Lib/site-packages/numpy-2.3.5.dist-info/LICENSE.txt`；仓库也保留副本。 |

NumPy 的锁定 Windows wheel 在原始声明中列出以下组件；完整版权与许可正文见 [NumPy wheel 原始 LICENSE](third_party/licenses/NumPy-2.3.5-wheel-LICENSE.txt)，不将它们重新声明为 NumPy 的 BSD 许可。

| NumPy 内部 / 随带组件 | 原始许可 | 关系 |
| --- | --- | --- |
| [OpenBLAS](https://github.com/OpenMathLib/OpenBLAS) | BSD-3-Clause | wheel 随带的动态数值库；The OpenBLAS Project。 |
| [LAPACK](https://www.netlib.org/lapack/) | BSD-3-Clause-Open-MPI | 随带于 OpenBLAS；University of Tennessee、UC Berkeley、University of Colorado Denver 等。 |
| [GCC runtime / libgfortran](https://gcc.gnu.org/) | GPL-3.0-or-later WITH GCC-exception-3.1 | wheel 随带的数值库运行时，保留运行库例外全文。 |
| lapack-lite / dragon4 / libdivide | BSD-3-Clause / MIT / Zlib | NumPy 源码说明中列出的内部组件，原作者声明由 NumPy 分发文件保留。 |
| NumPy random 与 masked-array 的内部代码 | 见相应目录 LICENSE | `numpy/random/LICENSE.md`、`numpy/ma/LICENSE` 及其余随包声明保留。 |

NumPy 源码声明中另列 Meson、spin、tempita 为仅源码分发的开发工具，本项目不打包它们。Python 嵌入包原始 [LICENSE.txt](third_party/licenses/Python-3.12.10-LICENSE.txt) 还保留 bzip2、libffi、OpenSSL 等随带组件声明；原包中的 SQLite、Expat、zlib、LZMA、decimal 实现及 Microsoft VC runtime 仍适用各自上游与系统分发条款，未被改称为本项目原创代码。

## 构建工具及可能进入原生 DLL 的运行库

Rubber Band 的上游源码包还附带可选组件。本仓库保留源码及原始声明，但本次编译不启用这些外部实现或接口：

| 上游附带源码 | 作者 / 许可 | 本仓库位置 |
| --- | --- | --- |
| KISS FFT | Mark Borgerding，BSD-3-Clause | `third_party/rubberband-4.0.0/src/ext/kissfft` |
| Speex resampler | Xiph.org Foundation、Jean-Marc Valin 等，BSD 风格许可，见 COPYING | `third_party/rubberband-4.0.0/src/ext/speex` |
| Pommier SIMD math functions | Julien Pommier，Zlib；NEON 文件还保留其移植作者声明 | `third_party/rubberband-4.0.0/src/ext/pommier` |
| BSD getopt / getopt_long | University of California, Berkeley 及贡献者，保留各文件 BSD 许可条款 | `third_party/rubberband-4.0.0/src/ext/getopt` |
| float_cast | Erik de Castro Lopo，文件头允许用于任何目的并要求保留声明 | `third_party/rubberband-4.0.0/src/ext/float_cast` |
| Rubber Band .NET 接口 | Jonathan Gilbert，BSD-like，见上游文件与 README | `third_party/rubberband-4.0.0/dotnet` |

上游 BSD getopt 的原始致谢：This product includes software developed by the University of California, Berkeley and its contributors. 本项目未编译该命令行组件。各文件的版权行与条款均以保留的上游原文为准。

| 项目 / 版本 | 用途 | 许可与来源 |
| --- | --- | --- |
| [Zig 0.14.1](https://ziglang.org/download/0.14.1/release-notes.html) | 编译 QuickJS、Windows Media Foundation 适配器和 Rubber Band；不打包 Zig 编译器 | Zig 自身 MIT；下载包 URL 与 SHA-256 在 `tools/dependencies.lock.json`。 |
| MinGW-w64（Zig 0.14.1 所附版本） | Windows GNU 目标的头文件与运行时支持 | 主体 ZPL-2.1，部分文件另有 public domain / BSD / LGPL 声明；保留 Zig 下载包内 `lib/libc/mingw/COPYING`。 |
| LLVM libc++ / libc++abi / libunwind（Zig 0.14.1 所附版本） | C++ 工具链运行时支持；可能被链接进 C++ DLL | Apache-2.0 WITH LLVM-exception；保留各组件 LICENSE.TXT，不能视为 Zig 的 MIT 代码。 |
| Microsoft .NET Framework 4.8 C# 编译器及系统框架 | 构建与运行原生 WinForms 界面 | Windows 平台组件，非本仓库开源代码；不重新分发编译器或 .NET 安装包。 |
| [Node.js](https://nodejs.org/) 22+ | 执行基于 `node:vm` 的模拟测试，亦可用于开发调试 | MIT 及其上游声明；仅为开发依赖，单文件应用不打包 Node.js。 |

上述原生运行库和上游声明副本在 [third_party/licenses](third_party/licenses/)，同时进入发行包内 `licenses/`。编译配方见 `tools/build_native.py`；它声明了实际构建选项，不依赖闭源编译产物。

## 开发阶段参考及可选兼容路径

| 来源 | 关系与边界 |
| --- | --- |
| [FFmpeg](https://ffmpeg.org/) 的 [Rubber Band 滤镜](https://ffmpeg.org/ffmpeg-filters.html#rubberband) | 参考其变速选项含义，早期原型用 FFmpeg 管道处理。本源码保留可显式指定 FFmpeg 的开发路径；公开单文件版使用 Media Foundation 和直接 Rubber Band C API，不打包 FFmpeg。若自行启用或再打包 FFmpeg，需按所用构建的实际许可处理。 |
| [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg)（早期原型 0.6.0，BSD-2-Clause） | 早期原型用于定位 FFmpeg；源码保留仅在明确未提供解码器时尝试定位的兼容路径。无该项目源文件或二进制进入本版发行包；其提供的 FFmpeg 二进制另有 FFmpeg 许可。 |
| [Chrome DevTools Protocol](https://chromedevtools.github.io/devtools-protocol/) | 参考 `Runtime.evaluate` 协议；本项目自行实现本机 CDP 传输，不使用 Puppeteer、Playwright 或 Electron。 |
| [RFC 6455](https://www.rfc-editor.org/rfc/rfc6455) | 本机 WebSocket 握手和帧处理的协议参考，自行实现，不引入其他 WebSocket 库代码。 |
| [Microsoft Core Audio / WASAPI 文档](https://learn.microsoft.com/en-us/windows/win32/coreaudio/wasapi) 与 [Media Foundation 文档](https://learn.microsoft.com/en-us/windows/win32/medfound/microsoft-media-foundation-sdk) | Windows 音频 API 参考；`wasapi_audio.py`、`process_audio.py` 与 `lite-native.cpp` 为本项目适配代码。系统组件不随项目分发。 |
| 网易云音乐 Android 9.6.05 的“智能过渡”表现 | 闭源产品的功能与架构研究背景，尤其是“本地选择策略”和“按能量调整普通淡入淡出”的设计思路。它不是开源依赖；本仓库不包含 APK、反编译代码、其 JS 字节码、资源或反编译结果。Windows 的相应曲线由本项目独立实现。 |

节拍网格、频谱通量、等功率曲线、五次平滑增益和相关性定位是本项目组合实现的通用音频处理方法。此处列出已知的组件与参考关系，不把闭源研究材料当作开源授权来源。

## 源码与再分发

- 仓库自有源码、被实际集成的原生库源码、LZMA 解码器及构建脚本均可随源码包取得。发行页提供对应版本源码归档。
- `third_party` 中保留的上游文件继续适用原声明。Rubber Band 原始分发附带的非默认接口、插件和示例保留其文件头许可，本项目不构建它们。
- Python、NumPy 和 Zig 二进制依赖按版本与 SHA-256 锁定；下载来源在 `tools/dependencies.lock.json`，没有把本机运行缓存当成依赖来源。
- 后续引入第三方代码时，应在提交中给出原始地址、版本、许可、版权声明和修改说明，并更新本清单。
