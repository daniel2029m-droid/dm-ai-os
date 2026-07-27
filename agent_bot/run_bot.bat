@echo off
:loop
echo [%time%] Starting bot... >> bot_log.txt
python bot.py >> bot_log.txt 2>&1
echo [%time%] Bot crashed, restarting in 5 seconds... >> bot_log.txt
timeout /t 5 >nul
goto loop
