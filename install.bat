@echo off
setlocal
cd /d "%~dp0"

set SERVICE_NAME=PcPowerAgent
set RULE_NAME=PC Power Agent UDP
set INSTALLER_EXE=installer.exe
set SERVICE_EXE=pc_agent_service.exe
set PYTHON_INSTALLER=installer.py
set PYTHON_SERVICE=pc_agent_service.py

if not exist config.json (
  echo config.json not found.
  echo.
  if exist "%INSTALLER_EXE%" (
    "%INSTALLER_EXE%" --manual --enable-shutdown
  ) else (
    python "%PYTHON_INSTALLER%" --manual --enable-shutdown
  )
  if errorlevel 1 goto failed
)

for /f "usebackq tokens=*" %%p in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "(Get-Content -Raw -Encoding UTF8 'config.json' | ConvertFrom-Json).port"`) do set AGENT_PORT=%%p

if "%AGENT_PORT%"=="" (
  echo Failed to read UDP port from config.json.
  goto failed
)

netsh advfirewall firewall delete rule name="%RULE_NAME%" >nul 2>&1
netsh advfirewall firewall add rule name="%RULE_NAME%" dir=in action=allow protocol=UDP localport=%AGENT_PORT%
if errorlevel 1 goto failed

if exist "%SERVICE_EXE%" (
  "%SERVICE_EXE%" stop >nul 2>&1
  "%SERVICE_EXE%" remove >nul 2>&1
  "%SERVICE_EXE%" --startup auto install
  if errorlevel 1 goto failed
  "%SERVICE_EXE%" start
  if errorlevel 1 goto failed
) else (
  python "%PYTHON_SERVICE%" stop >nul 2>&1
  python "%PYTHON_SERVICE%" remove >nul 2>&1
  python "%PYTHON_SERVICE%" --startup auto install
  if errorlevel 1 goto failed
  python "%PYTHON_SERVICE%" start
  if errorlevel 1 goto failed
)

echo Installed %SERVICE_NAME% on UDP port %AGENT_PORT%.
echo.
pause
endlocal
exit /b 0

:failed
echo.
echo Install failed. Please copy this screen text and send it to Codex.
echo Current folder: %CD%
echo.
pause
endlocal
exit /b 1
