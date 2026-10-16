<div align="center">

# AutomixFor163Music

**让下一首自然接上。**

为网易云音乐 Windows 客户端打造的自动衔接与节拍混音工具。

[![License: GPL v2 or later](https://img.shields.io/badge/License-GPL--2.0--or--later-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/平台-Windows%20x64-0078D4)](#运行环境与兼容版本)
[![Release](https://img.shields.io/github/v/release/Jia060117/AutomixFor163Music?include_prereleases&label=下载)](https://github.com/Jia060117/AutomixFor163Music/releases)
[![Build](https://github.com/Jia060117/AutomixFor163Music/actions/workflows/windows.yml/badge.svg)](https://github.com/Jia060117/AutomixFor163Music/actions/workflows/windows.yml)

由 **[情绪零碎の佳 · Jia060117](https://github.com/Jia060117)** 开发与维护

[下载预览版](https://github.com/Jia060117/AutomixFor163Music/releases) · [兼容客户端](#运行环境与兼容版本) · [使用方法](#开始使用) · [源码构建](docs/BUILDING.md) · [反馈问题](https://github.com/Jia060117/AutomixFor163Music/issues)

</div>

听歌时，上一首的尾奏和下一首的前奏，值得有一次更自然的交接。

AutomixFor163Music 会跟随网易云**实际播放队列**，提前准备下一组歌曲，在本机分析音频的节拍与能量，再选择适合的衔接方式：节奏接近、节拍清晰时尝试对拍混音，条件不足时回退到普通淡入淡出。它会在过渡片段结束前让网易云静音预跑下一首，并逐步交还音量，尽量减少切歌时的空隙和突变。

这是一个仍在迭代的个人开源项目。它面向希望在熟悉的网易云客户端里获得更连贯听歌体验的用户，也欢迎对音频处理、播放时序和桌面开发感兴趣的开发者参与。

## 能做什么

| 功能 | 具体表现 |
| --- | --- |
| 跟随真实队列 | 从网易云当前播放队列读取下一首，支持顺序、列表循环和心动模式。 |
| 节拍混音 | 分析节拍网格，在速度和节拍强度满足条件时进行对齐，并通过 Rubber Band 保持音高地调整速度。 |
| 自适应淡入淡出 | 普通过渡会参考两首歌的短时能量，轻微调整进入和退出速度，减少响度突变。 |
| 平滑交还播放 | 下一首静音预跑，混音尾段与原播放器音量渐变交接；使用恢复保护应对停止和后台异常退出。 |
| 单文件运行 | 原生 Windows 小窗口，支持托盘；发行版内置运行依赖，无需另装 Python、Node.js 或 FFmpeg。 |
| 音频留在内存 | 正常混音路径通过内存和管道处理音频，不主动保存歌曲或过渡音频文件。 |

## 运行环境与兼容版本

- **Windows 10 / 11，x64**，需要 .NET Framework 4.8 和系统媒体组件。Windows N 等缺少媒体组件的系统需先补齐对应组件。
- **目前仅验证网易云音乐 Windows 3.1.40.205461，64 位。** 其他版本的内部接口可能不同，暂不保证兼容。

👉 **[下载兼容的网易云音乐 3.1.40.205461（64 位官方安装包）](https://d8.music.126.net/dmusic2/NeteaseCloudMusic_Music_official_3.1.40.205461_64.exe)**

上面的链接由网易云官方域名提供；网易云客户端不包含在本项目源码或发行包中，其软件与商标属于各自权利人。本项目为独立开发的第三方工具，与网易云音乐官方没有隶属关系。

## 开始使用

1. 从 [Releases](https://github.com/Jia060117/AutomixFor163Music/releases) 下载 Windows x64 发行包，解压后运行 `AutomixFor163Music.exe`。
2. 安装并打开上面列出的兼容版本网易云，登录自己的账号，播放一个包含至少两首可播放歌曲的列表。
3. 在工具里点击 **“连接网易云”**。需要时会提示重启网易云，以启用仅本机可访问的控制端口；当前播放会中断。
4. 选择 **“快速测试：1 次交接”**，先确认你的声卡和常听歌曲能够正常衔接。快速测试会跳转播放位置，完成后尝试恢复原歌曲、位置、播放状态与音量。
5. 选择 **“持续自动混音”** 并点击 **“开始自动混音”**。最小化后工具会留在托盘，继续等待歌尾并准备下一组歌曲。

结束时点击 **“停止并恢复”**，等待播放器恢复后再退出。快速测试和持续模式都会实际控制播放；调整音量、暂停或手动切歌会中断当前交接，工具会尝试保留你的操作并重新准备。

## 使用前了解这些边界

- 随机播放、单曲循环、私人 FM 暂未适配。心动模式队列可能动态变化，工具会重新检查下一首。
- 不同音乐、音效设置、输出设备和系统负载都会影响衔接。独立音频流与播放器控制命令没有共同的逐采样时钟，暂不能保证每次交接都完全无缝。
- 工具依赖播放器已有的合法播放能力，不提供会员解锁、付费资源绕过或下载接口。当前账号无法播放、无法取得可解码音源、过短或超出内存预算的歌曲可能跳过混音。
- 启用本地控制后，工具通过 `127.0.0.1:19222` 与网易云通信。调试端口具有播放器页面控制能力，请保持只监听本机。
- 运行记录保存在本机，可能含歌名、播放位置与错误信息；提交 Issue 前请检查并删去个人信息。

## 常见问题

**显示未连接网易云**

确认是上面列出的 64 位兼容版本，并等待网易云主页加载完成，再点击“连接网易云”。没有开启控制端口时，按工具内提示重启。若端口 19222 被其他程序占用，需要先退出占用程序。本版会在状态尚未加载的情况下重新安装探针，避免一直复用启动早期的失败结果。

**从静音恢复音量时有短暂空隙**

目前版本已把音量渐变启动提前量调整到 130 毫秒，为页面调度和控制命令留出余量。若仍能听到停顿，请反馈网易云版本、输出设备、播放模式、歌曲对和复现步骤；单次测试的测量结果不能代替实际听感。

**为什么没有对拍，只有淡入淡出？**

对拍要求节奏速度接近且节拍网格足够清晰。策略主动回退属于正常行为，慢板、自由速度或鼓点不清楚的歌曲不一定适合节拍混音。

**文件放在哪里？怎么清理？**

首次启动会将校验后的依赖解压到 `%LOCALAPPDATA%\Automix\runtime`，运行记录保存在 `%LOCALAPPDATA%\Automix\data`。退出工具后可以清理这些目录；删除运行缓存后，下次会重新解压。可选的声卡校准文件保存在 `%LOCALAPPDATA%\Automix\render-profile.json`，不随发行版提供。

## 开发与构建

完整步骤见 **[构建说明](docs/BUILDING.md)**，实现结构见 **[架构与策略](docs/ARCHITECTURE.md)**。

```powershell
git clone https://github.com/Jia060117/AutomixFor163Music.git
cd AutomixFor163Music
python tools/bootstrap.py
python tools/build_native.py
python tools/test.py
python tools/build.py
```

构建需要 Windows x64、Python 3.12+、.NET Framework 4.8；运行模拟前端测试还需要 Node.js 22+。`bootstrap.py` 会下载校验和锁定的 Python 嵌入包、NumPy wheel 与 Zig 编译器。第三方原生库及 LZMA 解码器对应源码已随仓库提供。

## 开源许可与致谢

本项目由 **情绪零碎の佳（[Jia060117](https://github.com/Jia060117)）** 发布，采用 **GNU GPL v2 或任何后续版本（GPL-2.0-or-later）**。修改和再发布时，请保留版权与许可声明，并按 GPL 提供对应源码与构建材料。详见 [LICENSE](LICENSE)。

感谢 [Rubber Band](https://github.com/breakfastquay/rubberband)、[QuickJS](https://bellard.org/quickjs/)、[Python](https://www.python.org/)、[NumPy](https://numpy.org/)、[7-Zip LZMA SDK](https://www.7-zip.org/sdk.html) 和 [Zig](https://ziglang.org/) 等项目。

网易云适配和音源预取方案的早期调研还参考了 [Suxiaoqinx/Netease_url](https://github.com/Suxiaoqinx/Netease_url)、[taurusxin/ncmdump](https://github.com/taurusxin/ncmdump)、[BetterNCM/LibFrontendPlay](https://github.com/BetterNCM/LibFrontendPlay)、[apoint123/inflink-rs](https://github.com/apoint123/inflink-rs) 和 [BetterNCM 的历史源码](https://github.com/std-microblock/chromatic/tree/v2)。其中 `Netease_url` 为播放地址请求和音频读入内存提供了研究线索；当前程序通过已登录的网易云客户端正常播放链路取得音源，没有接入第三方解析服务。具体参考范围见 [开发参考项目记录](docs/REFERENCE_PROJECTS.md)。

**完整的版本、用途、上游作者、许可、修改情况与参考来源见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)**，其中还列出 NumPy wheel 和编译工具带入的运行库。调研项目与实际打包依赖分别说明，各项目的版权和许可归其原作者所有。

欢迎通过 Issue 分享复现条件、通过 Pull Request 改善策略或兼容性。涉及第三方代码的提交，请同时标注原始来源和许可。
