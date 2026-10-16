# 网易云生态的开发参考记录

本说明于 2026-10-16 根据本项目导入的 2026-10-02 开发历史补充，用于明确早期研究来源。它不包含私人对话、播放记录、账号信息或上游闭源代码。当前许可核对链接集中在 [第三方来源清单](../THIRD_PARTY_NOTICES.md)。

## 音乐解析与内存预取

历史记录明确出现了两个由项目发起人提供的候选项目：

- **[Suxiaoqinx/Netease_url](https://github.com/Suxiaoqinx/Netease_url)**：当时研究了 [`music_downloader.py`](https://github.com/Suxiaoqinx/Netease_url/blob/main/music_downloader.py) 中 `get_song_url()` 与 `download_music_to_memory()` 的关系，作为“取得可播放地址 → 把编码音频读入内存 → 解码分析”的参考。上游公开仓库采用 MIT，作者为 Suxiaoqinx。
- **[taurusxin/ncmdump](https://github.com/taurusxin/ncmdump)**：当时评估其处理已有 `.ncm` 文件的用途；它解决文件转换问题，而本项目后来采用客户端正常播放音源的提前读取路径。该方案没有被集成为当前版本的 NCM 解密或导出功能。其上游声明为 MIT，并说明来自 `anonymous5l/ncmdump` 的早期项目。

随后的开发记录确认，当前歌曲继续播放时，可以在客户端环境中通过其正常播放链路取得下一首的可读来源，并通过 Range 请求返回音频。因此项目没有另接第三方解析服务，也没有另建 Cookie 登录、请求加密或会员解析模块。

当前公开源码中的相应入口是 `src/automix/frontend-probe.js` 的音源准备和内存读取逻辑。它查询客户端已加载的正常音质与权限策略，将编码数据交给本机内存解码工作进程。`src/automix/memory_mix_worker.py` 完成后续分析与过渡渲染。

这段历史关系应表述为“研究和思路参考”，不能因加入致谢就把 Netease_url 或 ncmdump 标为本项目的运行依赖，也不能把项目后来的独立链路描述成它们的解析服务。

## 播放器适配和插件生态

早期可行性调研还引用了以下项目：

- **[BetterNCM/LibFrontendPlay](https://github.com/BetterNCM/LibFrontendPlay)**：作者标为 MicroBlock，研究其前端播放方向与网易云播放流程的衔接；上游 LICENSE 为 GPL v3。
- **[apoint123/inflink-rs](https://github.com/apoint123/inflink-rs)**：研究读取播放信息和系统媒体控制能力，以及既有客户端适配的线索；上游 LICENSE 为 GPL v3。
- **[BetterNCM 历史源码](https://github.com/std-microblock/chromatic/tree/v2)**：项目生态和可扩展性的背景参考；对应历史分支 LICENSE 为 GPL v3。原仓库现已改为 chromatic，这一名称变更用于帮助读者找到历史资料，不表示本项目采用了 chromatic 的实现。

本版使用自行实现的本机 CDP 适配，没有加载上述插件、SMTC 模块或注入器。

## 核对范围

历史开发记录保存了这些项目链接、调研目的和后续选型结论，没有完整记录每次浏览的提交号。本文列出的上游许可为 2026-10-16 可核实的文件状态，不追认未知历史版本的许可。

本次是对已有研究来源的补充致谢，不改变运行算法、项目发布者或 GPL-2.0-or-later 的项目许可。后续如果真正复制或集成这些项目的代码，应重新核对所用版本，保留必要声明，并在来源清单中记录具体文件与改动。
