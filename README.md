# 历史文献 OCR

在本机浏览器中打开 PDF，逐页识别正文与注释，校订后复制或导出。适用于历史印刷文献的转写与阅读。

## 功能

- PDF 按需逐页渲染，直接从扫描图像识别文字。
- 分别处理正文、标题、页下注释和左右侧注，尽量保留自然段与版面结构。
- 显示 PDF 页序与可编辑的印刷页码。
- 支持复制正文、复制注释、暂存校订、重新识别和导出已识别页面。
- 内置本地字体，适配窄屏阅读。
- macOS 与 Windows 共用网页界面、PDF 处理及版面分析代码。

## 启动

下载完整源码 ZIP 并解压，在项目目录打开终端。项目提供运行所需的 Python、Node.js、识别依赖、法语模型和字体，正常使用无需另外安装依赖或联网下载。

| 系统 | 启动命令 | 默认识别方式 |
| --- | --- | --- |
| macOS 13 及以上，Apple Silicon 或 Intel | `bash run.sh` | Apple Vision |
| Windows 10/11 x64 | `.\run.cmd` | Tesseract OCR |

首次启动会将对应系统的运行文件解压到项目的 `.cache/runtime/`，之后重复使用。在浏览器打开 **http://127.0.0.1:8765/**，上传 PDF 后即可开始识别和阅读。

程序运行期间请保留终端窗口。退出时按 **Control+C**；Windows 为 **Ctrl+C**。

## 文件与缓存

上传的 PDF、页面图像和识别文字仅保存在本机 `.cache/sessions/` 的当前会话目录中。识别数据按页生成，导出内容只包含已经处理的页面。

正常退出或点击“清理本次缓存”会删除会话内容。强制终止造成的遗留会话会在下次启动时清理；关闭浏览器标签页不会退出终端中的程序。命令行指定的源 PDF 保持原样。

`.cache/runtime/` 保存解压后的本地运行环境，可在程序退出后删除；下次启动时会重新生成。文献会话清理不会影响共用运行环境。

## OCR 引擎

本项目根据平台使用不同的 OCR 后端：

- **macOS**：默认使用 Apple Vision。
- **Windows**：默认使用 [Tesseract OCR](https://github.com/tesseract-ocr/tesseract)。

Tesseract 是开源 OCR 引擎，提供 `libtesseract` 和 `tesseract` 命令行程序。本项目使用 Tesseract 作为 OCR 后端之一；Tesseract 项目本身采用 **Apache License 2.0**，其版权及许可证归原项目及贡献者所有。第三方组件的具体许可信息见 [THIRD_PARTY.md](THIRD_PARTY.md)。

如果在论文、报告或其他学术成果中使用本项目，并需要引用其 OCR 技术来源，可同时引用 Tesseract 官方项目提供的相关文献。通用介绍可引用：

> Ray Smith. “An Overview of the Tesseract OCR Engine.” *Proceedings of the Ninth International Conference on Document Analysis and Recognition (ICDAR 2007)*, pp. 629–633, 2007.

Tesseract 官方仓库还提供了其他与版面分析、多语言 OCR 等主题相关的引用条目，详见其 [`CITATIONS.bib`](https://github.com/tesseract-ocr/tesseract/blob/main/CITATIONS.bib)。

## 适用范围

本项目面向历史印刷文献。版面判断采用文字位置、文字高度、栏间空白和注释标记等规则，复杂版式、低质量扫描和手写批注仍需人工核对。

Tesseract 与 Apple Vision 的检测和识别方式不同，同一页面在不同平台上可能得到不同的区域划分和文字结果。目前尚未建立完整的人工转写评估集，因此不提供统一的字符准确率声明。

原始拼写、日期数字以及侧注与正文的对应关系应以扫描原页为准并进行人工校订。

## 许可证

项目代码采用 [Apache License 2.0](LICENSE)。

Tesseract OCR、字体、模型及其他第三方依赖保留各自的版权和许可证；详情见 [THIRD_PARTY.md](THIRD_PARTY.md)。
