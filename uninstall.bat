@echo off
setlocal
cd /d "%~dp0"

set RULE_NAME=PC Power Agent UDP
set SERVICE_EXE=pc_agent_service.exe
set PYTHON_SERVICE=pc_agent_service.py

if exist "%SERVICE_EXE%" (
  "%SERVICE_EXE%" stop
  "%SERVICE_EXE%" remove
) else (
  python "%PYTHON_SERVICE%" stop
  python "%PYTHON_SERVICE%" remove
)
netsh advfirewall firewall delete rule name="%RULE_NAME%" >nul 2>&1

echo Uninstalled PC Power Agent.
echo.
pause
endlocal
