# 视频格式转换器

面向 Windows 的单文件桌面视频转换工具。使用 Python、PySide6 和 FFmpeg 命令行开发，视频在本机处理，无需 API Key 或上传文件。

![软件界面](docs/preview.png)

## 使用方法

1. 点击“选择视频”，或将一个本地视频拖入窗口。
2. 检查视频信息与缩略图。
3. 选择 MP4 / MKV、质量预设和输出路径。
4. 点击“开始转换”，完成后点击“打开输出目录”。

不覆盖源视频及已有输出。同名默认输出会自动加编号。取消或失败会清理本次任务的临时文件；若清理失败，界面会显示路径。

## 从源码运行

环境：Windows 10/11、独立安装的 Python 3.12 64 位。当前验证版本为 Python 3.12.10、PySide6 6.12.0、FFmpeg 9.0.2 Essentials。

首次安装，在项目目录的 PowerShell 执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
```

安装脚本创建 `.venv312`、安装锁定的 Python 依赖、下载并校验 FFmpeg。已有 `tools/ffmpeg` 时会保留原目录并检查启动；不会更改系统 PATH。网络不可用时可按下方说明手动安装 FFmpeg。

安装后双击 `start.cmd`，或在终端运行：

```powershell
.\.venv312\Scripts\python.exe main.py
```

手动安装 FFmpeg：从 [FFmpeg 官方下载入口](https://ffmpeg.org/download.html) 进入 [Gyan Windows builds](https://www.gyan.dev/ffmpeg/builds/)，下载 release essentials ZIP，将完整包放到 `tools/ffmpeg`。确保有 `tools/ffmpeg/bin/ffmpeg.exe` 和 `ffprobe.exe`，并保留 LICENSE 和文档。不要执行 `pip install ffmpeg` 代替安装命令行工具。

## 桌面程序

如取得本项目生成的 `dist/VideoConverter` 文件夹，保留 `_internal` 目录与程序旁的 `tools/ffmpeg`，双击 `VideoConverter.exe`。不要只复制一个 EXE。

自行构建：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1
```

脚本仅复制 `tools/ffmpeg`，避免复制本机额外下载文件。FFmpeg 运行时不纳入 Git 仓库。

构建使用 `video_converter.spec` 排除同名但接口不匹配的第三方 ICU DLL，Qt 使用 Windows 系统 ICU。构建后可执行 `powershell -NoProfile -ExecutionPolicy Bypass -File .\smoke_bundle.ps1` 验证实际窗口启动和正常退出。只在本机 Windows 11 验证过，尚未在干净的另一台电脑验证。

## 功能与范围

- ffprobe JSON：文件大小、时长、编码、分辨率；缺失字段显示“未知”。
- 首个非封面的视频流缩略图；提取失败可继续尝试转换。
- MP4、MKV：视频编码 H.264、像素格式 yuv420p；第一音轨（如有）转 AAC。
- 高质量 / 均衡 / 较小体积：分别使用 CRF 18 / 23 / 28。不是无损转换，也不保证输出一定更小。
- 奇数宽高会补齐到偶数，避免编码限制；不提供分辨率调整功能。
- 根据 FFmpeg `out_time_us` 与输入时长显示进度；未知时长显示活动进度。正式输出验证前最多显示 99%。
- 转换结束后检查退出状态，再用 ffprobe 验证临时输出可读取，最后发布正式文件。该检查不等于对成品逐帧检查；测试套件另有完整解码测试。
- 取消、错误提示、拖拽导入、完成后打开目录；运行中阻止关闭窗口，避免线程被销毁。

目前不支持批量、多音轨保留、字幕/章节保留、HDR 色彩管理、硬件加速、剪辑、网络视频输入。不能承诺任何编码或损坏输入都能转换。读取操作最多等待探测与缩略图各 30 秒；转换耗时取决于视频和电脑性能。

## 代码结构

| 文件 | 作用 |
|---|---|
| `main.py` | 桌面界面、后台预览任务、QProcess 转码生命周期 |
| `video_info.py` | ffprobe 调用和视频流选择，可独立命令行运行 |
| `media.py` | 工具定位、缩略图、转码参数、进度、输出保护 |
| `tests/test_media.py` | 输出保护与进度边界 |
| `tests/test_workflow.py` | Qt 事件循环 + 真实 FFmpeg 的工作流测试 |
| `docs/sessions/` | AI 协作、用户反馈与决策记录 |

## 测试

```powershell
.\.venv312\Scripts\python.exe -m unittest discover -s tests -v
```

测试自行生成短视频，不依赖私人素材。覆盖中文空格路径、有/无音轨、MP4/MKV、完整解码、缩略图、取消重试、错误恢复、源文件/同名输出保护、进程启动失败、工具缺失。测试结果与未验证项见 [验证报告](docs/validation.md)。

## AI 协作与交付

本项目使用 AI 辅助开发。用户完成前期环境、窗口、文件选择、信息读取及误选文件后恢复的验收；后续经授权由 AI 补全并自动验证。记录见 [会话总结](docs/sessions/03-completion.md)，讲解见 [答辩准备](docs/defense.md)。记录是本次对话摘要，不冒充完整原始聊天导出。

GitHub 提交只包含源码、脚本、文档和示例界面截图，不上传虚拟环境、私人视频和 FFmpeg 大型二进制。新机器使用 setup.ps1 重建环境。

## 第三方软件

PySide6/Qt 由其自身许可证约束，参见 [Qt for Python 许可说明](https://doc.qt.io/qtforpython-6/licenses.html)。FFmpeg 构建包的许可证保留在 `tools/ffmpeg/LICENSE`；本次 Gyan Essentials 构建为 GPLv3，版本与构建配置可通过 `ffmpeg -version` 查询，来源与对应源码入口见 [构建站点](https://www.gyan.dev/ffmpeg/builds/)。第三方许可证不因本项目改变。发布打包程序时须同时处理相关第三方许可证及对应源码要求。
