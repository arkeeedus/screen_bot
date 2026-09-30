@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv (
  echo Первый запуск: создаю окружение...
  python -m venv .venv || (echo Установите Python 3.10+ с python.org & pause & exit /b 1)
  .venv\Scripts\python -m pip install --upgrade pip
  .venv\Scripts\pip install -r requirements.txt
)
if not "%~1"=="" goto args
set /p TOPIC=Тема ролика: 
.venv\Scripts\python main.py "%TOPIC%"
goto end
:args
.venv\Scripts\python main.py %*
:end
pause
