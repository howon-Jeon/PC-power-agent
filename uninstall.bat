@echo off
setlocal
cd /d "%~dp0"

set "RULE_NAME=PC Power Agent UDP"
set "INSTALL_DIR=%ProgramFiles%\PC Power Agent"
set "INSTALLED_SERVICE=%INSTALL_DIR%\pc_agent_service.exe"

if exist "%INSTALLED_SERVICE%" (
  "%INSTALLED_SERVICE%" stop >nul 2>&1
  "%INSTALLED_SERVICE%" remove >nul 2>&1
) else (
  sc.exe stop PcPowerAgent >nul 2>&1
  sc.exe delete PcPowerAgent >nul 2>&1
)
timeout /t 2 /nobreak >nul
netsh advfirewall firewall delete rule name="%RULE_NAME%" >nul 2>&1
rmdir /S /Q "%INSTALL_DIR%" >nul 2>&1

echo Uninstalled PC Power Agent.
echo.
pause
endlocal
