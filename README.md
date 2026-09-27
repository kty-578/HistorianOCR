# 历史文献 OCR

在本机浏览器中打开 PDF，逐页识别正文与注释，校订后复制或导出。适用于历史印刷文献的转写与阅读，当前法语识别与版面规则主要使用《Ordonnances des rois de France》1902 年排印本验证。

## 功能

- PDF 按需逐页渲染，完全从扫描图像识别文字。
- 分别处理正文、标题、页下注释和左右侧注，保留自然段。
- 显示 PDF 页序与可编辑的印刷页码。
- 复制正文、复制注释、暂存校订、重新识别和导出已识别页面。
- 本地霞鹜文楷 GB 与 Lora 字体，适配窄屏。
- macOS 与 Windows 共用网页界面、PDF 处理及版面分析代码。

## 启动

下载完整源码 ZIP 并解压，在项目目录打开终端。Python、Node.js、识别依赖、法语模型和字体均随项目提供，无需安装依赖或联网下载。

| 系统 | 启动命令 | 默认识别方式 |
| --- | --- | --- |
| macOS 13 及以上，Apple Silicon 或 Intel | `bash run.sh` | Apple Vision |
| Windows 10/11 x64 | `.\run.cmd` | Tesseract |

首次启动会将对应系统的运行文件解压到项目的 `.cache/runtime/`，之后重复使用。在浏览器打开 **http://127.0.0.1:8765/**，上传 PDF 后开始阅读。

程序运行期间保留终端窗口。退出时按 **Control+C**；Windows 为 **Ctrl+C**。

### 打开指定文献

```bash
bash run.sh "/path/to/book.pdf" --first-page 255 --last-page 257
```

Windows 使用：

```powershell
.\run.cmd "C:\Documents\book.pdf" --first-page 255 --last-page 257
```

如需初始印刷页码映射，增加 `--printed-start-pdf 255 --printed-start-page 1`。需要更换端口时增加 `--port 8766`。

macOS 可以通过 `bash run.sh --layout-engine tesseract` 使用 Tesseract 检测文字位置；区域文字识别方式在页面内选择。Windows 提供 Tesseract。

## 文件与缓存

上传的 PDF、页面图像和识别文字只存放在 `.cache/sessions/` 的当前会话目录。按页生成识别数据，导出只包含已处理的页面。

正常退出或点击“清理本次缓存”会删除会话内容。强制终止造成的遗留会话会在下次启动时清理；正在使用的其他会话通过文件锁保护。关闭浏览器标签页不会退出终端中的程序。命令行指定的源 PDF 保持原样。

`models/` 是全部文献共用的识别模型；`static/fonts/` 是界面字体。`runtimes/` 保存随源码提供的运行文件。`.cache/runtime/` 保存解压后的运行环境，可以在退出程序后删除，下次启动会重新解压。文献会话清理不影响共用运行环境。

## 源码结构

```text
app.py                 网页、上传、校订与导出
pdf_pages.py           跨平台逐页 PDF 渲染
layout.py              页面区域划分
reading_order.py       阅读顺序与区域检查
ocr_engines.py         OCR 引擎接口
vision_ocr.swift        macOS Apple Vision
tesseract_ocr.cjs      Tesseract.js 区域识别
session_storage.py     会话缓存与跨平台文件锁
bootstrap.py           开发环境依赖安装
run.sh / run.cmd       macOS / Windows 启动入口
setup.sh / setup.cmd   开发环境安装入口
runtimes/              随源码提供的运行文件
portable_start.py      本地运行环境启动
tools/build_runtimes.py 运行文件构建
models/                法语识别模型
static/                页面样式和网页字体
tests/                 运行环境与真实文献验证
```

## 验证

运行环境检查：

```bash
bash run.sh --check-runtime
```

Windows 使用 `.\run.cmd --check-runtime`。检查使用随项目提供的运行环境，包括真实 Tesseract 初始化、模型、字体和进程文件锁。

使用原始 836 页 Tome 1 PDF 验证识别，文献不包含在源码中：

```bash
bash run.sh --verify-document "/path/to/Tome 1.pdf"
bash run.sh --verify-sample "/path/to/Tome 1.pdf"
```

`--verify-document` 全程使用 PDFium 与 Tesseract，Windows 可使用相同参数。`--verify-sample` 使用 Apple Vision，仅适用于 macOS。测试结束后清理会话数据。

GitHub Actions 使用随源码提供的运行环境检查 macOS 和 Windows 启动。远端结果以工作流执行记录为准。

## 开发与重新构建

修改 Python 与网页代码后，直接重新运行启动脚本即可。`setup.sh` 和 `setup.cmd` 用于开发者建立独立的 `.venv/` 与 `node_modules/`，需要预先安装 Python 3.12、Node.js 22，并连接网络。日常使用无需运行 setup。

需要重新生成运行文件时，在安装了 Xcode Command Line Tools 的 macOS 上运行：

```bash
bash setup.sh
.venv/bin/python tools/build_runtimes.py
```

构建工具按 `runtimes/sources.json` 下载并校验上游文件，生成三个系统版本、共用依赖及 `manifest.json`。修改 `vision_ocr.swift` 或依赖后需要重新构建。组件许可证保留在运行文件中。

## 适用范围

当前为历史印刷文献的试用项目。版面判断采用文字位置、文字高度、栏间空白和注释标记等规则，复杂版式与手写批注仍需人工核对。Tesseract 与 Apple Vision 使用不同的检测结果，相同页面可能得到不同的区域和文字。未建立完整的人工转写评估集，不能宣称统一的字符准确率。

原始拼写应依照扫描页校订。日期数字修正仅使用已有规则与图像复核结果。侧注对应正文的位置需要核对。

本地验证在 Apple Silicon macOS 上进行，包含移动目录后的运行环境检查、真实文献 OCR、HTTP 启动和退出清理。Windows x64 与 Intel Mac 的运行文件已提供，其原生执行需要对应设备或 GitHub Actions 验证。

## 发布到 GitHub

提交源码、`package-lock.json`、`requirements.txt`、`runtimes/`、`models/`、`static/` 和许可证。`.gitignore` 排除本地环境、安装缓存、文献缓存及系统文件。GitHub 的 Download ZIP 会包含仓库文件。

如果直接在本机压缩源码，请排除 `.venv/`、`node_modules/`、`.cache/`、`__pycache__/` 与 `.DS_Store`。用户 PDF 和识别内容无需随项目发送。

## 许可证

项目代码采用 [Apache License 2.0](LICENSE)。字体、模型和第三方依赖保留各自许可证，见 [THIRD_PARTY.md](THIRD_PARTY.md)。
