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
set "INSTALL_DIR=%ProgramFiles%\PC Power Agent"
set "INSTALLED_CONFIG=%INSTALL_DIR%\config.json"
set "INSTALLED_SERVICE=%INSTALL_DIR%\pc_agent_service.exe"

if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
if errorlevel 1 goto failed

if not exist "%INSTALLED_CONFIG%" if exist "config.json" (
  copy /Y "config.json" "%INSTALLED_CONFIG%" >nul
  if errorlevel 1 goto failed
)

if not exist "%INSTALLED_CONFIG%" (
  call :print_utf8 "7ISk7KCV7YyM7J287J20IOyXhuyKteuLiOuLpC4="
  echo.
  if exist "%INSTALLER_EXE%" (
    "%INSTALLER_EXE%" --manual --enable-shutdown --config "%INSTALLED_CONFIG%"
  ) else (
    python "%PYTHON_INSTALLER%" --manual --enable-shutdown --config "%INSTALLED_CONFIG%"
  )
  if errorlevel 1 goto failed
) else (
  call :print_utf8 "6riw7KG0IOyEpOyglSDtjIzsnbzsnbQg7KG07J6sIO2VqeuLiOuLpC4g7J6s7ISk7KCV7IucIGNvbmZpZyDtjIzsnbzsnYQg7IiY7KCV7ZW07KO87IS47JqULg=="
  echo.
)

for /f "usebackq tokens=*" %%p in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "(Get-Content -Raw -Encoding UTF8 '%INSTALLED_CONFIG%' | ConvertFrom-Json).port"`) do set "AGENT_PORT=%%p"

if "%AGENT_PORT%"=="" (
  echo Failed to read UDP port from config.json.
  goto failed
)

netsh advfirewall firewall delete rule name="%RULE_NAME%" >nul 2>&1
netsh advfirewall firewall add rule name="%RULE_NAME%" dir=in action=allow protocol=UDP localport=%AGENT_PORT%
if errorlevel 1 goto failed

if exist "%SERVICE_EXE%" (
  if exist "%INSTALLED_SERVICE%" (
    "%INSTALLED_SERVICE%" stop >nul 2>&1
    "%INSTALLED_SERVICE%" remove >nul 2>&1
  )
  "%SERVICE_EXE%" stop >nul 2>&1
  "%SERVICE_EXE%" remove >nul 2>&1
  timeout /t 2 /nobreak >nul
  copy /Y "%SERVICE_EXE%" "%INSTALLED_SERVICE%" >nul
  if errorlevel 1 goto failed
  if exist "pc_agent.exe" copy /Y "pc_agent.exe" "%INSTALL_DIR%\pc_agent.exe" >nul
  if exist "config.example.json" copy /Y "config.example.json" "%INSTALL_DIR%\config.example.json" >nul
  "%INSTALLED_SERVICE%" --startup auto install
  if errorlevel 1 goto failed
  "%INSTALLED_SERVICE%" start
  if errorlevel 1 goto failed
) else (
  python "%PYTHON_SERVICE%" stop >nul 2>&1
  python "%PYTHON_SERVICE%" remove >nul 2>&1
  for %%f in (pc_agent_service.py pc_agent.py config_store.py crypto_codec.py network_broadcast.py protocol.py replay_guard.py) do (
    copy /Y "%%f" "%INSTALL_DIR%\%%f" >nul
    if errorlevel 1 goto failed
  )
  python "%INSTALL_DIR%\pc_agent_service.py" stop >nul 2>&1
  python "%INSTALL_DIR%\pc_agent_service.py" remove >nul 2>&1
  python "%INSTALL_DIR%\pc_agent_service.py" --startup auto install
  if errorlevel 1 goto failed
  python "%INSTALL_DIR%\pc_agent_service.py" start
  if errorlevel 1 goto failed
)

echo Installed %SERVICE_NAME% on UDP port %AGENT_PORT%.
echo Install folder: %INSTALL_DIR%
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
