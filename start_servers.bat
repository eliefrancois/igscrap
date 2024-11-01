@echo off
echo Starting Instagram Scraper API...

REM Activate virtual environment first
call env\Scripts\activate.bat

REM Install requirements
echo Installing requirements...
pip install -r requirements.txt

REM Start Redis in WSL
echo Starting Redis...
wsl sudo service redis-server start
wsl redis-cli ping

REM Start Celery worker (changed command)
start cmd /k "celery -A celery_worker.celery worker --pool=solo --loglevel=info"

REM Start Flask server
start cmd /k "python igscrape.py"

timeout /t 5

REM Start ngrok
start cmd /k "ngrok http --domain=ethical-lemur-specially.ngrok-free.app 5001"

echo Servers starting... Check the new windows for URLs and status
