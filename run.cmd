@echo off
setlocal
set "OCR_PROJECT_DIR=%~dp0"
set PYTHONUTF8=1
set PYTHONNOUSERSITE=1
set PYTHONHOME=
set PYTHONPATH=
if /I "%PROCESSOR_ARCHITECTURE%"=="x86" if not defined PROCESSOR_ARCHITEW6432 (
  echo A 64-bit Windows system is required.
  exit /b 1
)
powershell.exe -NoProfile -Command "& { $ErrorActionPreference='Stop'; $root=$env:OCR_PROJECT_DIR; $archive=Join-Path $root 'runtimes/windows-x64.zip'; $manifest=Get-Content -LiteralPath (Join-Path $root 'runtimes/manifest.json') -Raw | ConvertFrom-Json; $entry=$manifest.archives.'windows-x64'; if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLower() -ne $entry.sha256) { throw 'Runtime checksum failed.' }; $target=Join-Path $root ('.cache/runtime/windows-x64-'+$entry.sha256.Substring(0,16)); $parent=Split-Path $target; New-Item -ItemType Directory -Force -Path $parent | Out-Null; $lock=$null; try { $lock=[IO.File]::Open((Join-Path $parent 'windows-start.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None); if (!(Test-Path -LiteralPath (Join-Path $target '.ready'))) { Write-Host 'Preparing bundled runtime...'; if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force }; Expand-Archive -LiteralPath $archive -DestinationPath $target; New-Item -ItemType File -Path (Join-Path $target '.ready') | Out-Null }; [IO.File]::WriteAllText((Join-Path $parent 'windows.path'),(Split-Path $target -Leaf)) } finally { if ($lock) { $lock.Dispose() } } }"
if errorlevel 1 exit /b %errorlevel%
< "%~dp0.cache\runtime\windows.path" set /p "OCR_RUNTIME_NAME="
set "OCR_RUNTIME_DIR=%~dp0.cache\runtime\%OCR_RUNTIME_NAME%"
"%OCR_RUNTIME_DIR%\python\python.exe" "%~dp0portable_start.py" %*
exit /b %errorlevel%
