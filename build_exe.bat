@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Project Python environment is missing.
    exit /b 1
)
if not exist "assets\fonts\NotoSansKR.ttf" (
    echo Bundled Korean font is missing.
    exit /b 1
)
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --onefile --windowed --noupx --add-data "%~dp0assets;assets" --name Tetris --specpath build --workpath build --distpath dist main.py
if errorlevel 1 exit /b 1
echo Created dist\Tetris.exe

