@echo off
chcp 65001 >nul
setlocal
pushd "%~dp0" >nul 2>&1
if errorlevel 1 goto failed

set "SERVICE_NAME=PcPowerAgent"
set "RULE_NAME=PC Power Agent UDP"
set "INSTALLER_EXE=installer.exe"
set "SERVICE_EXE=pc_agent_service.exe"
set "PYTHON_INSTALLER=installer.py"
set "PYTHON_SERVICE=pc_agent_service.py"

if not exist config.json (
  call :print_utf8 "7ISk7KCV7YyM7J287J20IOyXhuyKteuLiOuLpC4="
  echo.
  if exist "%INSTALLER_EXE%" (
    "%INSTALLER_EXE%" --manual --enable-shutdown
  ) else (
    python "%PYTHON_INSTALLER%" --manual --enable-shutdown
  )
  if errorlevel 1 goto failed
) else (
  call :print_utf8 "6riw7KG0IOyEpOyglSDtjIzsnbzsnbQg7KG07J6sIO2VqeuLiOuLpC4g7J6s7ISk7KCV7IucIGNvbmZpZyDtjIzsnbzsnYQg7IiY7KCV7ZW07KO87IS47JqULg=="
  echo.
)

for /f "usebackq tokens=*" %%p in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "(Get-Content -Raw -Encoding UTF8 'config.json' | ConvertFrom-Json).port"`) do set "AGENT_PORT=%%p"

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
popd
endlocal
exit /b 0

:print_utf8
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Console]::OutputEncoding=[Text.UTF8Encoding]::new(); Write-Host ([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('%~1')))"
exit /b 0

:failed
echo.
echo Install failed. Please copy this screen text and send it to Codex.
echo Current folder: %CD%
echo.
pause
popd >nul 2>&1
endlocal
exit /b 1
