@echo off
setlocal

python -m PyInstaller --onefile --name pc_agent pc_agent.py
if errorlevel 1 goto failed
python -m PyInstaller --onefile --name pc_agent_service --hidden-import win32timezone pc_agent_service.py
if errorlevel 1 goto failed
python tools\write_installer_secret.py
if errorlevel 1 goto failed
python -m PyInstaller --onefile --name installer --hidden-import installer_build_secret installer.py
if errorlevel 1 goto failed
del /Q installer_build_secret.py >nul 2>&1

rem udp_sender_test.exe is a dev-only debugging tool. Do not include it in
rem the customer install package (pc_agent.exe / pc_agent_service.exe /
rem installer.exe / install.bat / uninstall.bat only).
python -m PyInstaller --onefile --name udp_sender_test udp_sender_test.py
if errorlevel 1 goto failed

copy /Y install.bat dist\install.bat >nul
copy /Y uninstall.bat dist\uninstall.bat >nul

echo Build complete. See dist folder.
endlocal
exit /b 0

:failed
del /Q installer_build_secret.py >nul 2>&1
echo Build failed.
endlocal
exit /b 1
