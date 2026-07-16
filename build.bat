@echo off
setlocal

python -m PyInstaller --onefile --name pc_agent pc_agent.py
python -m PyInstaller --onefile --name pc_agent_service --hidden-import win32timezone pc_agent_service.py
python -m PyInstaller --onefile --name installer installer.py

rem udp_sender_test.exe is a dev-only debugging tool. Do not include it in
rem the customer install package (pc_agent.exe / pc_agent_service.exe /
rem installer.exe / install.bat / uninstall.bat only).
python -m PyInstaller --onefile --name udp_sender_test udp_sender_test.py

copy /Y install.bat dist\install.bat >nul
copy /Y uninstall.bat dist\uninstall.bat >nul
copy /Y config.example.json dist\config.example.json >nul
if exist .env copy /Y .env dist\.env >nul

echo Build complete. See dist folder.
endlocal
