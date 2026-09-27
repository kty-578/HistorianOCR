"""Start from bundled runtimes without installers or network access."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile
import portalocker

ROOT = Path(__file__).resolve().parent


def main():
    runtime = Path(os.environ['OCR_RUNTIME_DIR'])
    spec = json.loads((ROOT/'runtimes/manifest.json').read_text(encoding='utf-8'))
    entry = spec['archives']['shared']
    archive = ROOT/'runtimes'/entry['file']
    with archive.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != entry['sha256']:
            raise SystemExit('Shared runtime checksum failed. Obtain a complete source archive.')
    cache = ROOT/'.cache/runtime'
    cache.mkdir(parents=True, exist_ok=True)
    shared = cache/('shared-'+entry['sha256'][:16])
    with portalocker.Lock(str(cache/'shared.lock'), timeout=30):
        if not (shared/'.ready').exists():
            if shared.exists():
                shutil.rmtree(shared)
            shared.mkdir()
            with zipfile.ZipFile(archive) as source:
                for name in source.namelist():
                    if not (shared/name).resolve().is_relative_to(shared.resolve()):
                        raise ValueError('Invalid path in shared runtime.')
                source.extractall(shared)
            (shared/'.ready').touch()
    environment = dict(os.environ)
    environment.pop('PYTHONHOME', None)
    environment.pop('PYTHONPATH', None)
    environment.update({'PYTHONUTF8': '1', 'PYTHONNOUSERSITE': '1',
                        'OCR_NODE': str(runtime/'node'/('node.exe' if os.name == 'nt' else 'node')),
                        'OCR_TESSERACT_JS': str(shared/'node_modules/tesseract.js')})
    if sys.platform == 'darwin':
        environment['OCR_VISION_BINARY'] = str(runtime/'vision_ocr')
    else:
        environment['OCR_LAYOUT_ENGINE'] = 'tesseract'
    if sys.argv[1:2] == ['--check-runtime']:
        command = [sys.executable, str(ROOT/'tests/check_runtime.py')]
    elif sys.argv[1:2] == ['--verify-document']:
        command = [sys.executable, str(ROOT/'tests/verify_portable.py'), *sys.argv[2:]]
    elif sys.argv[1:2] == ['--verify-sample']:
        command = [sys.executable, str(ROOT/'tests/verify_sample.py'), *sys.argv[2:]]
    else:
        command = [sys.executable, str(ROOT/'app.py'), *sys.argv[1:]]
    if os.name == 'nt':
        # Keep the console available while the child processes Ctrl+C and cleanup.
        process = subprocess.Popen(command, env=environment, cwd=ROOT)
        while True:
            try:
                raise SystemExit(process.wait())
            except KeyboardInterrupt:
                continue
    os.execve(sys.executable, command, environment)


if __name__ == '__main__':
    main()
