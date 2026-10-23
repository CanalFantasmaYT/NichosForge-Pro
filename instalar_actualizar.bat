@echo off
cd /d "%~dp0"
echo Instalando dependencias de NichosForge Pro...
python -m pip install --upgrade pip
python -m pip install -U -r requirements.txt
echo.
echo Listo. Ya puedes abrir iniciar_panel.bat
pause
