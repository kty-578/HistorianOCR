"""Rebuild the bundled runtimes from pinned, checksum-verified upstream files."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / '.cache/runtime-build'
OUTPUT = ROOT / 'runtimes'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def download(url, expected, target):
    if not target.exists() or digest(target) != expected:
        subprocess.run(['curl', '-fLsS', '--retry', '2', '--connect-timeout', '15',
                        '--max-time', '240', url, '-o', str(target)], check=True)
    if digest(target) != expected:
        raise ValueError(f'Checksum mismatch: {target.name}')
    return target


def unpack(archive, target):
    if archive.suffix in ('.zip', '.whl'):
        with zipfile.ZipFile(archive) as source:
            source.extractall(target)
    else:
        with tarfile.open(archive) as source:
            source.extractall(target, filter='data')


def build():
    if sys.platform != 'darwin':
        raise SystemExit('Building the Apple Vision executables requires macOS and Swift.')
    BUILD.mkdir(parents=True, exist_ok=True)
    spec = json.loads((OUTPUT / 'sources.json').read_text())
    archives = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        pending = []
        for name, item in spec['platforms'].items():
            for kind in ('python', 'node'):
                extension = '.zip' if item[kind+'_url'].endswith('.zip') else '.tar.gz'
                path = BUILD / f'{name}-{kind}{extension}'
                archives[name, kind] = path
                pending.append(pool.submit(download, item[kind+'_url'], item[kind+'_sha256'], path))
        for task in pending:
            task.result()
    environment = {**os.environ, 'TMPDIR': str(BUILD), 'TMP': str(BUILD), 'TEMP': str(BUILD)}
    manifest = {'python': spec['python_version'], 'node': spec['node_version'], 'archives': {}}
    for name in spec['platforms']:
        target = BUILD / name
        if target.exists():
            shutil.rmtree(target)
        target.mkdir()
        unpack(archives[name, 'python'], target)
        unpack(archives[name, 'node'], target)
        node_folder = next(target.glob('node-*'))
        node_dir = target / 'node'
        node_dir.mkdir()
        source = node_folder / ('node.exe' if name.startswith('windows') else 'bin/node')
        shutil.copy2(source, node_dir / source.name)
        shutil.copy2(node_folder / 'LICENSE', node_dir / 'LICENSE')
        shutil.rmtree(node_folder)
        platform = {'macos-arm64': 'macosx_13_0_arm64', 'macos-x64': 'macosx_13_0_x86_64',
                    'windows-x64': 'win_amd64'}[name]
        wheels = BUILD / (name+'-wheels')
        wheels.mkdir(exist_ok=True)
        subprocess.run([sys.executable, '-m', 'pip', 'download', '--dest', str(wheels),
                        '--cache-dir', str(BUILD/'pip'), '--only-binary=:all:', '--no-deps',
                        '--platform', platform, '--python-version', '3.12', '--implementation', 'cp',
                        '--abi', 'cp312', *spec['packages']], check=True, env=environment)
        site = target / 'python' / ('Lib/site-packages' if name.startswith('windows') else 'lib/python3.12/site-packages')
        site.mkdir(parents=True, exist_ok=True)
        for wheel in wheels.glob('*.whl'):
            unpack(wheel, site)
        if name.startswith('macos'):
            architecture = 'arm64' if name.endswith('arm64') else 'x86_64'
            subprocess.run(['swiftc', '-O', '-target', architecture+'-apple-macosx13.0',
                            '-o', str(target/'vision_ocr'), str(ROOT/'vision_ocr.swift')], check=True, env=environment)
            subprocess.run(['codesign', '--force', '--sign', '-', str(target/'vision_ocr')], check=True, env=environment)
        for folder in target.rglob('__pycache__'):
            shutil.rmtree(folder)
        suffix = '.zip' if name.startswith('windows') else '.tar.gz'
        output = OUTPUT / (name+suffix)
        if suffix == '.zip':
            with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                for path in sorted(target.rglob('*')):
                    if path.is_file():
                        archive.write(path, path.relative_to(target))
        else:
            with tarfile.open(output, 'w:gz', compresslevel=6) as archive:
                for path in sorted(target.iterdir()):
                    archive.add(path, arcname=path.name)
        if output.stat().st_size >= 100*1024*1024:
            raise ValueError(f'Archive exceeds GitHub file size limit: {output}')
        output.with_name(output.name+'.sha256').write_text(digest(output)+'  '+output.name+'\n')
        manifest['archives'][name] = {'file': output.name, 'sha256': digest(output), 'bytes': output.stat().st_size}
        print('Built', name, output.stat().st_size, flush=True)
    output = OUTPUT / 'shared.zip'
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted((ROOT/'node_modules').rglob('*')):
            if path.is_file():
                archive.write(path, path.relative_to(ROOT))
    manifest['archives']['shared'] = {'file': output.name, 'sha256': digest(output), 'bytes': output.stat().st_size}
    (OUTPUT/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')


if __name__ == '__main__':
    build()
