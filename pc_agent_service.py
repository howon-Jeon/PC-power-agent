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

    def GetAcceptedControls(self):
        controls = win32service.SERVICE_ACCEPT_STOP | win32service.SERVICE_ACCEPT_SHUTDOWN
        controls |= getattr(win32service, "SERVICE_ACCEPT_PRESHUTDOWN", 0)
        return controls

    def _notify_shutdown(self) -> None:
        try:
            # Ask SCM for extra time so the burst of shutdown packets can finish
            # sending before the process gets killed.
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING, waitHint=5000)
        except Exception as exc:
            servicemanager.LogErrorMsg(f"PC Power Agent failed to report stop-pending: {exc}")
        servicemanager.LogInfoMsg("PC Power Agent received Windows shutdown control")
        pc_agent.request_shutdown_status_mode()
        try:
            pc_agent.notify_windows_shutdown(pc_agent.default_config_path())
        except Exception as exc:
            servicemanager.LogErrorMsg(f"PC Power Agent failed to send shutdown status: {exc}")

    def SvcShutdown(self):
        # pywin32 routes SERVICE_CONTROL_SHUTDOWN here, not to SvcOtherEx.
        self._notify_shutdown()

    def SvcOtherEx(self, control, event_type, data):
        preshutdown = getattr(win32service, "SERVICE_CONTROL_PRESHUTDOWN", None)
        if preshutdown is not None and control == preshutdown:
            self._notify_shutdown()
            return

        return win32serviceutil.ServiceFramework.SvcOtherEx(self, control, event_type, data)

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
