@echo off
echo ========================================
echo   DevHunter - One-Click Startup
echo ========================================
echo.

cd /d "%~dp0"

echo [1/2] Starting Backend (http://localhost:8100) ...
start "DevHunter Backend" cmd /k "cd /d "%~dp0backend" && venv\Scripts\activate && python run.py"

echo [2/2] Starting Frontend (http://localhost:5200) ...
start "DevHunter Frontend" cmd /k "cd /d "%~dp0frontend" && npm run dev"

echo.
echo ========================================
echo   Done!
echo   Backend:  http://localhost:8100
echo   Frontend: http://localhost:5200
echo ========================================
echo.
pause
