@echo off
REM 클릭 없이 전체화면: Chrome을 키오스크 모드로 실행합니다.
REM 1) 아래 URL을 현장 PC의 현황판 주소로 바꿉니다 (예: http://192.168.0.10:8000/display/)
REM 2) Chrome 설치 경로가 다르멀 CHROME 경로를 수정합니다.

set "URL=http://127.0.0.1:8000/display/"
set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"

if not exist "%CHROME%" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" (
  echo Chrome 을 찾을 수 없습니다. CHROME 경로를 수정하세요.
  pause
  exit /b 1
)

start "" "%CHROME%" --kiosk "%URL%" --disable-pinch --overscroll-history-navigation=0
