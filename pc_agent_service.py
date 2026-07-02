from __future__ import annotations

import sys

import servicemanager
import win32event
import win32service
import win32serviceutil
import win32timezone  # Required by pywin32 service helpers when packaged by PyInstaller.

import pc_agent


class PcPowerAgentService(win32serviceutil.ServiceFramework):
    _svc_name_ = "PcPowerAgent"
    _svc_display_name_ = "PC Power Agent"
    _svc_description_ = "Receives encrypted UDP power-control commands."

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        pc_agent.stop_agent()
        win32event.SetEvent(self.stop_event)

    def SvcDoRun(self):
        servicemanager.LogInfoMsg("PC Power Agent service started")
        self.ReportServiceStatus(win32service.SERVICE_RUNNING)
        pc_agent.run_agent(pc_agent.default_config_path(), foreground=False)
        servicemanager.LogInfoMsg("PC Power Agent service stopped")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(PcPowerAgentService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(PcPowerAgentService)
