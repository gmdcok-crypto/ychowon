@echo off
REM Edge 키오스크 (클릭 없이 전체화면). URL만 현장에 맞게 수정하세요.

set "URL=http://127.0.0.1:8000/display/"
set "EDGE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"

if not exist "%EDGE%" set "EDGE=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
if not exist "%EDGE%" (
  echo Edge 를 찾을 수 없습니다.
  pause
  exit /b 1
)

start "" "%EDGE%" --kiosk "%URL%"
