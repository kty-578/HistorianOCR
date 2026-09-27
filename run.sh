#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
case "$(uname -s):$(uname -m)" in
  Darwin:arm64) PLATFORM=macos-arm64 ;;
  Darwin:x86_64) PLATFORM=macos-x64 ;;
  *) echo "This launcher supports macOS. Use run.cmd on Windows." >&2; exit 1 ;;
esac
ARCHIVE="$PROJECT_DIR/runtimes/$PLATFORM.tar.gz"
CHECKSUM="$ARCHIVE.sha256"
if [[ ! -f "$ARCHIVE" || ! -f "$CHECKSUM" ]]; then
  echo "Bundled runtime is missing. Obtain the complete source archive." >&2
  exit 1
fi
EXPECTED="$(cut -d ' ' -f 1 "$CHECKSUM")"
ACTUAL="$(/usr/bin/shasum -a 256 "$ARCHIVE" | cut -d ' ' -f 1)"
if [[ "$ACTUAL" != "$EXPECTED" ]]; then echo "Runtime checksum failed." >&2; exit 1; fi
RUNTIME_DIR="$PROJECT_DIR/.cache/runtime/$PLATFORM-${EXPECTED:0:16}"
if [[ ! -f "$RUNTIME_DIR/.ready" ]]; then
  mkdir -p "$PROJECT_DIR/.cache/runtime"
  LOCK="$PROJECT_DIR/.cache/runtime/$PLATFORM.lock"
  if [[ -f "$LOCK/pid" ]] && ! kill -0 "$(cat "$LOCK/pid")" 2>/dev/null; then rm -rf "$LOCK"; fi
  if ! mkdir "$LOCK" 2>/dev/null; then echo "Runtime preparation is already in progress. Please retry shortly." >&2; exit 1; fi
  echo $$ > "$LOCK/pid"
  STAGING="$PROJECT_DIR/.cache/runtime/$PLATFORM-preparing-$$"
  trap 'rm -rf "$STAGING" "$LOCK"' EXIT
  mkdir -p "$STAGING"
  echo "Preparing bundled runtime..."
  /usr/bin/tar -xzf "$ARCHIVE" -C "$STAGING"
  touch "$STAGING/.ready"
  if [[ -d "$RUNTIME_DIR" ]]; then rm -rf "$RUNTIME_DIR"; fi
  mv "$STAGING" "$RUNTIME_DIR"
  rm -rf "$LOCK"
  trap - EXIT
fi
export OCR_RUNTIME_DIR="$RUNTIME_DIR"
export PYTHONUTF8=1 PYTHONNOUSERSITE=1
unset PYTHONHOME PYTHONPATH
exec "$RUNTIME_DIR/python/bin/python3" "$PROJECT_DIR/portable_start.py" "$@"
