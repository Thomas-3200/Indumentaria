@echo off
REM ===============================================================
REM Stylo Fino - Bot Telegram en modo watch (long polling 24/7)
REM
REM Doble click en este archivo. Queda en una ventana propia,
REM independiente de Claude Code o cualquier otra sesion.
REM Si el bot se cae (red, error, etc.) se relanza solo cada 10 seg.
REM
REM Para parar: Ctrl+C en la ventana o cerrar la ventana.
REM ===============================================================

REM Trabajamos desde el worktree donde esta el codigo refactorizado MT.
cd /d "C:\Users\PC\Desktop\Stepflow_V1\.claude\worktrees\exciting-hamilton-3f385d"

REM Logs centralizados en el repo principal
set "LOGDIR=C:\Users\PC\Desktop\Stepflow_V1\logs\stylo_fino_bot"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

title Stylo Fino Bot (24/7 watch)

:LOOP
echo.
echo ============================================================
echo  [%date% %time%] Iniciando bot watch para stylo_fino
echo  Log: %LOGDIR%\bot_watch.log
echo  Ctrl+C para detener.
echo ============================================================
echo.

"C:\Users\PC\AppData\Local\Programs\Python\Python312\python.exe" -u ^
  "flows\bot_telegram_mt\fetch_intake.py" ^
  --client stylo_fino ^
  --watch ^
  >> "%LOGDIR%\bot_watch.log" 2>&1

echo.
echo [%date% %time%] Bot terminado (exit=%ERRORLEVEL%). Relanzando en 10 segundos...
timeout /t 10 /nobreak > nul
goto LOOP
