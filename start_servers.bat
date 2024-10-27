@echo off
echo Starting Instagram Scraper API...

REM Activate virtual environment first
call env\Scripts\activate.bat

REM Install requirements
echo Installing requirements...
pip install -r requirements.txt

REM Start Redis in WSL and verify it's running
echo Starting Redis...
wsl sudo service redis-server start
wsl redis-cli ping
IF %ERRORLEVEL% NEQ 0 (
    echo Redis failed to start! Please check Redis installation.
    exit /b 1
)
echo Redis started successfully!

REM Start Celery worker
start cmd /k "celery -A igscrape.celery worker --loglevel=info"

REM Start Flask server in a new window
start cmd /k "python igscrape.py"

REM Wait for Flask to initialize
timeout /t 5

REM Start ngrok with reserved domain
start cmd /k "ngrok http --domain=ethical-lemur-specially.ngrok-free.app 5001"

echo Servers starting... Check the new windows for URLs and status
