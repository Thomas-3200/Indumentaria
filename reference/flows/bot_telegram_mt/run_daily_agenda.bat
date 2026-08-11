@echo off
REM ===============================================================
REM Stylo Fino - Disparo diario del kit a Leo (09:00 AR)
REM Llamado por Windows Task Scheduler todos los dias a las 09:00.
REM ===============================================================

REM Fecha de hoy en YYYY-MM-DD
for /f "tokens=2 delims==" %%a in ('wmic OS Get localdatetime /value') do set "DT=%%a"
set "TODAY=%DT:~0,4%-%DT:~4,2%-%DT:~6,2%"

REM Trabajamos desde el worktree donde esta el codigo refactorizado MT
cd /d "C:\Users\PC\Desktop\Stepflow_V1\.claude\worktrees\exciting-hamilton-3f385d"

REM Log diario en el repo principal
set "LOGDIR=C:\Users\PC\Desktop\Stepflow_V1\logs\stylo_fino_cron"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
set "LOGFILE=%LOGDIR%\daily_agenda_%TODAY%.log"

echo [%date% %time%] Disparando agenda %TODAY% para stylo_fino >> "%LOGFILE%"

"C:\Users\PC\AppData\Local\Programs\Python\Python312\python.exe" -u ^
  "flows\bot_telegram_mt\send_daily_agenda.py" ^
  --client stylo_fino ^
  --date %TODAY% ^
  >> "%LOGFILE%" 2>&1

echo [%date% %time%] FIN exit=%ERRORLEVEL% >> "%LOGFILE%"
exit /b %ERRORLEVEL%
