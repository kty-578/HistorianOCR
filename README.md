# Scriptorium

`Scriptorium` 一词源自中世纪拉丁语，意为缮写室，也常指修道院抄写书籍的场所。

本项目致力于制作面向历史文献的本地 OCR 工具，重点处理非标准印刷文献。在浏览器中上传 PDF，打开需要的页面，识别正文与注释，对照扫描图像校订后复制或导出。

目前主要涉及法语历史印刷文献。未来可继续扩展至拉丁语、英语、德语等拉丁字母文献，以及哥特体、加洛林小写体等手稿书体。语言识别与手稿书体识别属于不同的工作方向，当前识别范围见“适用范围”。

## 功能

- **按页识别**：打开页面时进行处理，大型 PDF 也可以从需要的页码开始阅读。
- **从图像识别**：将 PDF 页面渲染为图像，再进行 OCR。
- **区分正文与注释**：识别标题、正文、页下注释和左右侧注，并分别整理阅读顺序。
- **保留自然段**：尽量保留原文的段落划分，合并同一自然段中的印刷换行。
- **对照校订**：同时查看扫描图像、识别文字、PDF 页序和可编辑的印刷页码。
- **复制与导出**：分别复制正文和注释，也可以导出已识别页面的文本。

## 快速开始

在仓库页面选择 **Code → Download ZIP**，下载后完整解压。在解压后的项目目录打开终端，运行对应命令：

| 系统 | 启动命令 | 默认 OCR 引擎 |
| --- | --- | --- |
| macOS 13 及以上，Apple Silicon 或 Intel | `bash run.sh` | Apple Vision |
| Windows 10/11 x64 | `.\run.cmd` | Tesseract |

当前提供 macOS 和 Windows 运行环境，Linux 运行环境尚未提供。

项目随附 Python、Node.js、识别依赖、法语模型和界面字体。正常启动和识别无需另外安装依赖或联网下载。请保留解压目录中的 `runtimes/`、`models/` 和 `static/` 等文件夹。

首次启动会在项目内解压运行环境，可能需要等待片刻。终端显示服务地址后，在浏览器打开：

**http://127.0.0.1:8765/**

上传 PDF，打开需要的页面，对照原图检查文字，再点击“复制正文”或“复制注释”。暂存和导出功能可用于整理本次识别结果；导出范围为已经处理的页面。

运行期间请保留终端窗口。使用结束后，在终端按 **Ctrl+C** 退出。关闭浏览器标签页后，程序仍会继续运行。

### 开发环境

`setup.sh` 和 `setup.cmd` 会建立项目内的 `.venv/`，并安装 Python 与 Node.js 依赖，需要联网。开发环境需要 Python 3.10 或更新版本，以及 Node.js 20 或更新版本。macOS 若要使用 Apple Vision，还需要安装 Xcode Command Line Tools。

配置完成后，使用项目内的 Python 直接启动开发版本：

```bash
# macOS
.venv/bin/python app.py
```

```powershell
# Windows PowerShell
.\.venv\Scripts\python.exe app.py
```

日常使用便携运行环境时，使用 `run.sh` 或 `run.cmd`。

### 常用启动选项

直接打开本地 PDF，并指定初始页面范围：（以下为示例）

```bash
# macOS
bash run.sh "/path/to/book.pdf" --first-page 255 --last-page 257
```

```powershell
# Windows PowerShell
.\run.cmd "C:\Documents\book.pdf" --first-page 255 --last-page 257
```

默认端口被占用时，在启动命令后增加 `--port 8766`，并打开 `http://127.0.0.1:8766/`。

## 文件与缓存

识别在本机进行。上传的 PDF、页面图像和校订文字保存在 `.cache/sessions/` 的当前会话目录中，页面数据按需生成。

**退出或清理缓存前，请复制或导出需要保留的文字。** 正常退出程序或点击“清理本次缓存”会删除会话内容。异常退出后的遗留会话会在下次启动时清理。命令行指定的原始 PDF 保持原样。

`.cache/runtime/` 保存全部文献共用的运行环境，后续启动会重复使用。可以在退出程序后删除此目录，下次启动时程序会从随附文件重新解压。

## 识别流程与引擎

每页独立处理：

1. 将 PDF 页面渲染为图像。
2. 检测文字位置，根据本页的文字大小、栏间空白和注释标记等信息划分区域。
3. 对各区域分别识别，整理正文与注释的阅读顺序和自然段。
4. 显示结果，供用户对照扫描图像校订。

macOS 默认通过本项目的 Swift 调用程序使用系统提供的 **Apple Vision**。Windows 使用 **Tesseract.js 7.0.0** 和 **Tesseract.js-core 7.0.0**，在本机通过 Node.js 运行 Tesseract 的 WebAssembly 版本。macOS 也提供 Tesseract 区域识别选项。

页面区域划分与阅读顺序由本项目代码处理，参考了 PaddleOCR / PaddleX 和 Tesseract 的相关处理思路。具体来源、参考范围和组件许可见 [THIRD_PARTY.md](THIRD_PARTY.md)。

## 适用范围

当前主要使用法语历史印刷文献验证。复杂版式、低质量扫描、手写批注，以及数字与形近字母的混淆，仍可能造成错误。正文和注释的分类也需要对照原页检查。

原始拼写、日期数字、印刷页码和侧注对应关系应以扫描原页为准。同一页面在 Apple Vision 与 Tesseract 下可能得到不同结果。项目尚未建立完整的人工转写评估集，因此不提供统一的字符准确率声明。

## 学术引用

引用 Scriptorium 时，请使用 GitHub 仓库中的 **Cite this repository**，或参考项目根目录 `CITATION.cff` 提供的引用信息。该文件单独保存软件引用资料，GitHub 可据此生成 APA 和 BibTeX 格式。

在论文或报告中使用识别结果时，建议记录项目版本、实际使用的 OCR 引擎和人工校订方式。介绍 Tesseract 的技术来源时，可另行引用：

> Ray Smith. “An Overview of the Tesseract OCR Engine.” *Proceedings of the Ninth International Conference on Document Analysis and Recognition (ICDAR 2007)*, pp. 629–633, 2007.

其他相关文献见 Tesseract 官方仓库的 [`CITATIONS.bib`](https://github.com/tesseract-ocr/tesseract/blob/main/CITATIONS.bib)。

## 许可证与第三方组件

本项目代码采用 [Apache License 2.0](LICENSE)，版权声明见 [NOTICE](NOTICE)。

Tesseract.js、Tesseract.js-core、识别模型、字体及随附运行环境中的第三方组件分别适用其各自许可证。

Apple Vision 由 macOS 提供，适用 Apple 的相关条款。组件来源与许可说明见 [THIRD_PARTY.md](THIRD_PARTY.md)。

再分发项目时，请一并保留项目与第三方组件的许可证、版权声明及适用的 NOTICE 文件。
