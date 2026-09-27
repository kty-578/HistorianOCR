"""Local OCR adapters sharing normalized line and word coordinates."""

import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parent
MODEL = ROOT / 'models/tesseract/fra.traineddata'


def default_engine() -> str:
    return 'vision' if sys.platform == 'darwin' else 'tesseract'


def layout_engine() -> str:
    engine = os.environ.get('OCR_LAYOUT_ENGINE', default_engine())
    if engine not in ('vision', 'tesseract'):
        raise ValueError('OCR_LAYOUT_ENGINE 必须是 vision 或 tesseract。')
    return engine


def tesseract_paths() -> tuple[Path, Path]:
    node = Path(os.environ.get('OCR_NODE', shutil.which('node') or 'node'))
    module = Path(os.environ.get('OCR_TESSERACT_JS', str(ROOT / 'node_modules/tesseract.js')))
    return node, module


def tesseract_available() -> bool:
    node, module = tesseract_paths()
    return node.is_file() and (module / 'package.json').is_file() and MODEL.is_file()


def segmentation_mode(region) -> int:
    if len(region.lines) == 1:
        return 7
    return 4 if region.kind in ('footnote', 'marginal_note', 'annotation') else 6


def recognize_regions(jobs: list[dict], engine: str, vision_binary: Path | None) -> list[dict]:
    if engine == 'vision':
        if sys.platform != 'darwin' or vision_binary is None:
            raise ValueError('Apple Vision 需要 macOS。请选择 Tesseract。')
        results = []
        for job in jobs:
            start = time.monotonic()
            response = subprocess.run([str(vision_binary), job['image']],
                                      check=True, capture_output=True, text=True, timeout=120)
            results.append({'region_id': job['region_id'], 'lines': json.loads(response.stdout),
                            'engine': 'vision', 'elapsed_seconds': time.monotonic()-start})
        return results
    if engine != 'tesseract':
        raise ValueError('未知的识别方式。')
    if not tesseract_available():
        raise ValueError('Tesseract 组件或法语模型尚未安装，请运行 setup_tesseract.py。')
    node, module = tesseract_paths()
    payload = {'module': str(module), 'model_dir': str(MODEL.parent), 'jobs': jobs}
    response = subprocess.run([str(node), str(ROOT / 'tesseract_ocr.cjs')],
                              input=json.dumps(payload), capture_output=True, text=True,
                              check=True, timeout=max(120, len(jobs)*60))
    return json.loads(response.stdout)
