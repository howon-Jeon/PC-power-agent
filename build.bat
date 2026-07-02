@echo off
setlocal

python -m PyInstaller --onefile --name pc_agent pc_agent.py
python -m PyInstaller --onefile --name pc_agent_service --hidden-import win32timezone pc_agent_service.py
python -m PyInstaller --onefile --name installer installer.py
python -m PyInstaller --onefile --name udp_sender_test udp_sender_test.py

copy /Y install.bat dist\install.bat >nul
copy /Y uninstall.bat dist\uninstall.bat >nul
copy /Y config.example.json dist\config.example.json >nul

echo Build complete. See dist folder.
endlocal
