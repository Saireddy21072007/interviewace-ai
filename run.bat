@echo off
REM ===========================================================================
REM  InterviewAce AI - one-command launcher (Windows)
REM
REM    run.bat          install anything missing, then start API + web app
REM    run.bat setup    install dependencies only
REM    run.bat test     run the Python test suite
REM    run.bat api      start only the backend  (http://localhost:8000/docs)
REM    run.bat web      start only the frontend (http://localhost:5173)
REM    run.bat stop     kill whatever is holding ports 8000 and 5173
REM ===========================================================================
setlocal EnableDelayedExpansion
cd /d "%~dp0"

set "ACTION=%~1"
if "%ACTION%"=="" set "ACTION=start"

REM --- locate Python ---------------------------------------------------------
set "PY=python"
where python >nul 2>nul || set "PY=py"
where %PY% >nul 2>nul
if errorlevel 1 (
  echo [X] Python was not found on PATH.
  echo     Install Python 3.11 or newer from https://python.org and tick
  echo     "Add python.exe to PATH" during setup.
  exit /b 1
)

if /i "%ACTION%"=="stop" goto :stop
if /i "%ACTION%"=="test" goto :test

REM --- first-run setup -------------------------------------------------------
if not exist ".env" (
  echo [~] Creating .env from .env.example
  copy /y ".env.example" ".env" >nul
)

REM A marker file keeps repeat launches fast. Delete it to force a reinstall.
if not exist ".deps-installed" (
  echo [~] Installing Python packages ^(first run only^)...
  %PY% -m pip install --disable-pip-version-check -q -r backend\requirements.txt
  if errorlevel 1 (
    echo [X] pip install failed. Scroll up for the reason.
    exit /b 1
  )
  echo installed> ".deps-installed"
)

if /i "%ACTION%"=="api" goto :api

where npm >nul 2>nul
if errorlevel 1 (
  echo [!] npm was not found, so the web app cannot start.
  echo     Install Node.js 18+ from https://nodejs.org
  if /i "%ACTION%"=="web" exit /b 1
  echo     Starting the API only. Open http://localhost:8000/docs
  goto :api
)

if not exist "frontend\node_modules" (
  echo [~] Installing web packages ^(first run only, ~1 min^)...
  pushd frontend
  call npm install --no-fund --no-audit
  if errorlevel 1 (
    popd
    echo [X] npm install failed.
    exit /b 1
  )
  popd
)

if /i "%ACTION%"=="web" goto :web
if /i "%ACTION%"=="setup" (
  echo [OK] Setup complete. Run "run.bat" to start the app.
  exit /b 0
)

REM --- start both ------------------------------------------------------------
echo.
echo   InterviewAce AI
echo   ---------------
echo   API      http://localhost:8000/docs
echo   Web app  http://localhost:5173
echo.
echo   Two windows will open. Close them to stop the servers.
echo.

start "InterviewAce API" cmd /k "%PY% -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload"
start "InterviewAce Web" cmd /k "cd /d "%~dp0frontend" && npm run dev"

REM Give Vite a moment to bind the port before the browser asks for it.
timeout /t 5 /nobreak >nul
start "" http://localhost:5173
exit /b 0

REM --- individual targets ----------------------------------------------------
:api
echo [~] API on http://localhost:8000  (docs at /docs)
%PY% -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
exit /b 0

:web
echo [~] Web app on http://localhost:5173
pushd frontend
call npm run dev
popd
exit /b 0

:test
echo [~] Running tests...
%PY% -m pytest tests -q
exit /b %errorlevel%

:stop
echo [~] Stopping anything on ports 8000 and 5173...
for %%P in (8000 5173) do (
  for /f "tokens=5" %%A in ('netstat -ano ^| findstr ":%%P" ^| findstr "LISTENING"') do (
    taskkill /f /pid %%A >nul 2>nul && echo     stopped PID %%A on port %%P
  )
)
echo [OK] Done.
exit /b 0
