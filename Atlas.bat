@echo off
REM Porta unica do Atlas: ativa a venv e abre o menu (ou repassa o comando).
REM   Atlas.bat            -> menu interativo
REM   Atlas.bat hoje       -> atualiza carteira e abre o cockpit
REM   Atlas.bat ver        -> so abre o visor do que ja rodou
cd /d "%~dp0"
if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"
python atlas.py %*
if errorlevel 1 pause
