# 外部项目来源与集成范围

## 界面字体

- 中文：[霞鹜文楷 GB v1.522](https://github.com/lxgw/LxgwWenkaiGB/releases/tag/v1.522)，从 `LXGWWenKaiGB-Regular.ttf` 转换为网页格式 `static/fonts/WenKaiGB.woff2`，保留完整字符覆盖。许可见 `static/fonts/WenKai-OFL.txt`。
- 拉丁文字：[Lora](https://github.com/google/fonts/tree/main/ofl/lora)，使用可变字重字体，网页文件为 `static/fonts/Lora.woff2`。许可见 `static/fonts/Lora-OFL.txt`。

两种字体均随本机程序提供，页面不请求外部字体服务。中文网页字体约 8 MB，供全部页面共用。格式转换使用 FontTools 与 Brotli；这两个工具不属于程序运行依赖。

## PDF 渲染与会话管理

[pypdfium2](https://github.com/pypdfium2-team/pypdfium2) 提供 PDFium 的 Python 接口，用于页数读取和逐页图像渲染。程序以互斥锁保护 PDFium 调用，使用后关闭文档、页面和位图。pypdfium2 使用 Apache-2.0 或 BSD-3-Clause，PDFium 及其依赖的许可随安装组件提供。

[Portalocker](https://github.com/wolph/portalocker) 提供 macOS 和 Windows 的跨进程文件锁，采用 BSD-3-Clause。会话删除前关闭持有的文件句柄。

Python 依赖由 `requirements.txt` 声明，Node.js 依赖由 `package-lock.json` 锁定。各依赖的许可证保留在安装目录中。项目自身代码采用根目录的 Apache License 2.0 许可证。

## PaddleOCR / PaddleX

阅读的 PaddleX 版本为 `c50f5da858020db473a2285f089bb8c7bbd6afdc`，许可为 Apache-2.0。PP-StructureV3 的版面处理由 PaddleX 提供。

- [pipeline_v2.py](https://github.com/PaddlePaddle/PaddleX/blob/c50f5da858020db473a2285f089bb8c7bbd6afdc/paddlex/inference/pipelines/layout_parsing/pipeline_v2.py)：检查文字框与区域的交叠关系，对跨越区域的文字重新裁剪识别，独立处理区域排序。
- [xycut_enhanced/utils.py](https://github.com/PaddlePaddle/PaddleX/blob/c50f5da858020db473a2285f089bb8c7bbd6afdc/paddlex/inference/pipelines/layout_parsing/xycut_enhanced/utils.py)：阅读 `projection_by_bboxes`、`split_projection_profile`、`recursive_xy_cut`、`recursive_yx_cut`。
- [xycut_enhanced/xycuts.py](https://github.com/PaddlePaddle/PaddleX/blob/c50f5da858020db473a2285f089bb8c7bbd6afdc/paddlex/inference/pipelines/layout_parsing/xycut_enhanced/xycuts.py)：根据区域结构选择排序方向。
- [utils.py](https://github.com/PaddlePaddle/PaddleX/blob/c50f5da858020db473a2285f089bb8c7bbd6afdc/paddlex/inference/pipelines/layout_parsing/utils.py)：文字框与区域匹配、交叠检查。

本项目的 `reading_order.py` 独立实现基于区间合并的 XY-Cut 排序，采用归一化坐标，省去逐像素投影数组。正文、侧注和页下注释分别排序。`layout.py` 根据已检测栏位和单词位置分配跨栏文字，各栏重新进行图像 OCR。区域检查保留交叠区域并显示核对提示，检查初步文字检测结果是否全部进入区域。

这些实现参考上述算法思路。当前运行时的区域分类采用本项目规则；尚未接入 PaddleX 的版面检测模型或完整 PP-StructureV3 推理流程。

## Tesseract

阅读的 Tesseract 版本为 `8ae68101439b3f7df123499a784e8896c805179d`，许可为 Apache-2.0。

- [publictypes.h](https://github.com/tesseract-ocr/tesseract/blob/8ae68101439b3f7df123499a784e8896c805179d/include/tesseract/publictypes.h)：页面分割模式。
- [baseapi.cpp](https://github.com/tesseract-ocr/tesseract/blob/8ae68101439b3f7df123499a784e8896c805179d/src/api/baseapi.cpp)：`AnalyseLayout` 与识别流程。
- [colfind.cpp](https://github.com/tesseract-ocr/tesseract/blob/8ae68101439b3f7df123499a784e8896c805179d/src/textord/colfind.cpp)：栏位、相邻文字区域与区域连接关系。

实际识别通过本机 Tesseract.js 7.0.0 调用其 WebAssembly 引擎。每页创建一个 worker，同页全部区域顺序复用该 worker，结束后释放。单行使用 PSM 7，正文文字块使用 PSM 6，包含多行的注释使用 PSM 4。系统词典与高频词词典通过初始化参数关闭。输出包含归一化文字位置、置信度、识别模式与耗时。

法语模型来自 [tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast/tree/87416418657359cb625c412a48b6e1d6d41c29bd)，版本 `87416418657359cb625c412a48b6e1d6d41c29bd`，许可为 Apache-2.0。`fra.traineddata` 的 SHA-256 为 `ced037562e8c80c13122dece28dd477d399af80911a28791a66a63ac1e3445ca`。`setup_tesseract.py` 验证模型摘要。

Tesseract.js、Tesseract.js-core 和模型保留各自的上游许可。源代码阅读所用的 Tesseract 提交与运行组件的内部引擎版本分别记录，不据此推断两者版本相同。

Apache-2.0 许可全文保存在 [licenses/Apache-2.0.txt](licenses/Apache-2.0.txt)。

## 验证范围

`tests/verify_sample.py` 使用真实 PDF 第 234、255、256、257、619 页检查区域归属、排序、按需识别和保存导出。`tests/verify_engines.py` 使用第 619 页实际运行 Tesseract，并通过 HTTP 请求检查识别方式选择、重新识别、文本与 HTML 导出和扫描图像接口。测试会关闭临时服务并删除会话数据。

这些检查验证功能与指定区域归属。字符错误率需要独立的人工转写材料；当前结果不能用于宣称一种引擎在所有历史文献上更准确。

## 随源码提供的运行环境

`runtimes/` 包含 CPython 3.12.14（[python-build-standalone 20260924](https://github.com/astral-sh/python-build-standalone/releases/tag/20260924)）与 [Node.js v22.23.3](https://nodejs.org/dist/v22.23.3/)。上游下载地址与 SHA-256 保存在 `runtimes/sources.json`，项目运行文件摘要保存在 `runtimes/manifest.json`。

Python 的许可证及内含组件说明保留在各系统运行文件的 `python/` 中；Node.js 的许可证及第三方说明保留在 `node/LICENSE`。Pillow 12.3.0、pypdfium2 5.13.0、Portalocker 4.4.0 的许可证保留在 Python 的安装目录中。共用的 Tesseract.js 依赖及许可证保存在 `shared.zip` 的 `node_modules/` 中。Apple Vision 由 macOS 提供，macOS 运行文件包含本项目编译的调用程序。
