@echo off
cd /d "%~dp0"
python -c "import dotenv, yaml, requests, openpyxl" 2>nul || (
  echo Faltan dependencias, instalando...
  python -m pip install -r requirements.txt
)
echo Abriendo NichosForge Pro...
python main.py panel
pause
