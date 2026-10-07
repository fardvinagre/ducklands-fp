@echo off
setlocal
pushd "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 goto fail
)
".venv\Scripts\python.exe" -c "import importlib.util,sys; sys.exit(not all(importlib.util.find_spec(name) for name in ('panda3d','numpy')))"
if errorlevel 1 (
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto fail
)
".venv\Scripts\python.exe" -m game.main %*
set "gameExit=%errorlevel%"
popd
exit /b %gameExit%
:fail
echo Falha ao preparar o projeto. Consulte README.md.
popd
exit /b 1
