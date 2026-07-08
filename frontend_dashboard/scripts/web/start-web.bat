@echo off
chcp 65001 >nul
pushd "%~dp0..\.."

set "CODEX_NODE=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
set "VITE_CLI=%CD%\node_modules\vite\bin\vite.js"

if not exist "%VITE_CLI%" (
  echo Missing node_modules. Please run npm install first.
  pause
  popd
  exit /b 1
)

if exist "%CODEX_NODE%" (
  echo Starting web server with built-in Node...
  "%CODEX_NODE%" "%VITE_CLI%" --host 0.0.0.0 --port 5173
) else (
  echo Built-in Node was not found. Falling back to system Node.
  echo If it still reports that Node is too old, install Node.js 20.19 or newer.
  npm run dev
)

popd
pause
