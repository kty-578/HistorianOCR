"""Check installed components and real cross-process session locks."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
import pypdfium2 as pdfium
from ocr_engines import MODEL, tesseract_paths, tesseract_available
from session_storage import SessionStorage
from setup_tesseract import SHA256


def verify():
    assert tesseract_available()
    assert hashlib.sha256(MODEL.read_bytes()).hexdigest() == SHA256
    node, module = tesseract_paths()
    # Initialize the real WASM engine and French model, then release the worker.
    response = subprocess.run([str(node), str(app.ROOT / 'tesseract_ocr.cjs')],
        input=json.dumps({'module': str(module), 'model_dir': str(MODEL.parent), 'jobs': []}),
        text=True, capture_output=True, check=True, timeout=120)
    assert json.loads(response.stdout) == []
    for name in ('WenKaiGB', 'Lora'):
        assert (app.ROOT / 'static/fonts' / (name+'.woff2')).read_bytes()[:4] == b'wOF2'
    base = app.ROOT / '.cache/runtime-verification'
    with SessionStorage(base) as first:
        code = ('from pathlib import Path; from session_storage import SessionStorage; '
                'import sys; s=SessionStorage(Path(sys.argv[1])); '
                'print(s.path,flush=True); s.close()')
        subprocess.run([sys.executable, '-c', code, str(base)], cwd=app.ROOT, check=True)
        assert first.path.exists(), 'Another process must not remove an active session.'
    assert not first.path.exists()
    # A separate process exits without normal session cleanup.
    code = ('from pathlib import Path; from session_storage import SessionStorage; '
            'import os,sys; s=SessionStorage(Path(sys.argv[1])); os._exit(0)')
    subprocess.run([sys.executable, '-c', code, str(base)], cwd=app.ROOT, check=True)
    abandoned = set(base.glob('session-*'))
    assert abandoned
    with SessionStorage(base):
        assert all(not path.exists() for path in abandoned)
    print('PASS: PDFium', pdfium.PDFIUM_INFO, 'Tesseract initialization, model, fonts and process locks')


if __name__ == '__main__':
    verify()
