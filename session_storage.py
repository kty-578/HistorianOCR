"""Temporary sessions with cross-platform process locks."""

from pathlib import Path
import secrets
import shutil
import portalocker


class SessionStorage:
    def __init__(self, base: Path) -> None:
        self.base = base
        self.closed = False
        base.mkdir(parents=True, exist_ok=True)
        with portalocker.Lock(str(base / '.lock'), mode='a+b', timeout=15):
            for folder in base.glob('session-*'):
                if not folder.is_dir() or folder.is_symlink():
                    continue
                previous = portalocker.Lock(str(folder / '.lock'), mode='a+b', timeout=0)
                try:
                    previous.acquire()
                except portalocker.exceptions.LockException:
                    continue
                previous.release()
                shutil.rmtree(folder)
            self.path = base / f'session-{secrets.token_hex(16)}'
            self.path.mkdir()
            self._lock = portalocker.Lock(str(self.path / '.lock'), mode='a+b', timeout=0)
            self._lock.acquire()

    def close(self) -> None:
        if not self.closed:
            with portalocker.Lock(str(self.base / '.lock'), mode='a+b', timeout=15):
                self._lock.release()
                shutil.rmtree(self.path)
                self.closed = True

    def __enter__(self) -> 'SessionStorage':
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
