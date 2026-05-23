@echo off
echo 서울 부동산 앱 시작 중...

start "Backend" cmd /k "cd /d %~dp0backend && uvicorn main:app --port 8000"
timeout /t 2 /nobreak > nul
start "Frontend" cmd /k "cd /d %~dp0frontend && npm run preview -- --port 5173"
timeout /t 3 /nobreak > nul
start "" "http://localhost:5173"
