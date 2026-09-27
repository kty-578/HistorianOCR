"""Install project-local dependencies on macOS and Windows."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parent


def main():
    if sys.version_info < (3, 10):
        raise SystemExit('Python 3.10 or newer is required.')
    node = shutil.which('node')
    npm = shutil.which('npm')
    if not node or not npm:
        raise SystemExit('Install Node.js 20 or newer (including npm), then run setup again.')
    major = int(subprocess.check_output([node, '--version'], text=True).strip().lstrip('v').split('.')[0])
    if major < 20:
        raise SystemExit('Node.js 20 or newer is required.')
    npm_path = Path(npm).resolve()
    npm_cli = npm_path if npm_path.suffix == '.js' else npm_path.parent / 'node_modules/npm/bin/npm-cli.js'
    if not npm_cli.is_file():
        raise SystemExit('Cannot locate npm-cli.js. Reinstall Node.js including npm.')
    temporary = ROOT / '.cache/install-temp'
    temporary.mkdir(parents=True, exist_ok=True)
    environment = {**os.environ, 'TMPDIR': str(temporary), 'TMP': str(temporary), 'TEMP': str(temporary),
                   'PIP_CACHE_DIR': str(ROOT / '.cache/pip'), 'npm_config_cache': str(ROOT / '.cache/npm'),
                   'PYTHONUTF8': '1'}
    os.environ.update({name: environment[name] for name in ('TMPDIR', 'TMP', 'TEMP')})
    python = ROOT / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.is_file():
        venv.EnvBuilder(with_pip=True).create(ROOT / '.venv')
    subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(ROOT / 'requirements.txt')],
                   check=True, cwd=ROOT, env=environment)
    subprocess.run([node, str(npm_cli), 'ci', '--ignore-scripts', '--no-audit', '--no-fund'],
                   check=True, cwd=ROOT, env=environment)
    subprocess.run([str(python), str(ROOT / 'setup_tesseract.py')], check=True, cwd=ROOT, env=environment)
    print('Ready. Start with run.cmd on Windows or bash run.sh on macOS.')


if __name__ == '__main__':
    main()
