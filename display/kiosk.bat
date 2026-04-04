@echo off
REM 초원농원 예약현황판 키오스크 모드 (주소창 없음, 전체화면)
REM PC IP가 192.168.0.10 이면 아래 주소 그대로, 아니면 수정하세요.

set URL=http://localhost:8000/display/
REM 다른 PC에서 보려면: set URL=http://192.168.0.10:8000/display/

REM Chrome 키오스크 (전체화면 + 주소창 없음)
if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
  "C:\Program Files\Google\Chrome\Application\chrome.exe" --kiosk --disable-pinch --noerrdialogs --disable-session-crashed-bubble "%URL%"
  goto :eof
)

REM Chrome (x64) 다른 경로
if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" (
  "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" --kiosk --disable-pinch --noerrdialogs --disable-session-crashed-bubble "%URL%"
  goto :eof
)

REM Edge 키오스크 (Chrome 없을 때)
if exist "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" (
  "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --kiosk --disable-pinch "%URL%"
  goto :eof
)

echo Chrome 또는 Edge를 찾을 수 없습니다.
pause
