@echo off
setlocal

set OUTDIR=C:\Users\manup\AppData\Local\neoSlice
set EXEPATH=%OUTDIR%\neoSlice.exe
set LNKPATH=%~dp0dist\neoSlice.lnk

echo [1/3] Compilation neoSlice...
call ".venv\Scripts\python.exe" -m PyInstaller --clean -y neoslice.spec

if %ERRORLEVEL% neq 0 (
    echo ERREUR : build echoue.
    pause
    exit /b 1
)

echo [2/3] Creation du raccourci dans dist\...
if not exist "%~dp0dist" mkdir "%~dp0dist"
powershell -NoProfile -Command ^
  "$s=(New-Object -COM WScript.Shell).CreateShortcut('%LNKPATH%'); $s.TargetPath='%EXEPATH%'; $s.IconLocation='%EXEPATH%,0'; $s.Save()"

echo [3/3] Termine.
echo   EXE    : %EXEPATH%
echo   Lancer : double-cliquez sur dist\neoSlice.lnk
echo.
pause
