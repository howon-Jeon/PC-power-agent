from __future__ import annotations

import ctypes
import ipaddress
import sys
from ctypes import wintypes

BROADCAST_PLACEHOLDER = "255.255.255.255"

MAX_ADAPTER_NAME_LENGTH = 256
MAX_ADAPTER_DESCRIPTION_LENGTH = 128
MAX_ADAPTER_ADDRESS_LENGTH = 8
ERROR_BUFFER_OVERFLOW = 111

# IFTYPE values (RFC 1213 ifType) for adapters worth broadcasting on.
IF_TYPE_ETHERNET_CSMACD = 6
IF_TYPE_IEEE80211 = 71
_RELEVANT_ADAPTER_TYPES = {IF_TYPE_ETHERNET_CSMACD, IF_TYPE_IEEE80211}

# Adapter description keywords that indicate a virtual/host-only adapter
# (Hyper-V, WSL, VPN, VM hypervisors) that isn't a real LAN link.
_VIRTUAL_KEYWORDS = ("virtual", "hyper-v", "vmware", "virtualbox", "wsl", "tap-", "loopback", "vpn")


class IP_ADDR_STRING(ctypes.Structure):
    pass


IP_ADDR_STRING._fields_ = [
    ("Next", ctypes.POINTER(IP_ADDR_STRING)),
    ("IpAddress", ctypes.c_char * 16),
    ("IpMask", ctypes.c_char * 16),
    ("Context", wintypes.DWORD),
]


class IP_ADAPTER_INFO(ctypes.Structure):
    pass


IP_ADAPTER_INFO._fields_ = [
    ("Next", ctypes.POINTER(IP_ADAPTER_INFO)),
    ("ComboIndex", wintypes.DWORD),
    ("AdapterName", ctypes.c_char * (MAX_ADAPTER_NAME_LENGTH + 4)),
    ("Description", ctypes.c_char * (MAX_ADAPTER_DESCRIPTION_LENGTH + 4)),
    ("AddressLength", wintypes.UINT),
    ("Address", ctypes.c_byte * MAX_ADAPTER_ADDRESS_LENGTH),
    ("Index", wintypes.DWORD),
    ("Type", wintypes.UINT),
    ("DhcpEnabled", wintypes.UINT),
    ("CurrentIpAddress", ctypes.POINTER(IP_ADDR_STRING)),
    ("IpAddressList", IP_ADDR_STRING),
    ("GatewayList", IP_ADDR_STRING),
    ("DhcpServer", IP_ADDR_STRING),
    ("HaveWins", wintypes.BOOL),
    ("PrimaryWinsServer", IP_ADDR_STRING),
    ("SecondaryWinsServer", IP_ADDR_STRING),
    ("LeaseObtained", ctypes.c_long),
    ("LeaseExpires", ctypes.c_long),
]


def _iter_adapters() -> list[IP_ADAPTER_INFO]:
    iphlpapi = ctypes.windll.iphlpapi
    size = wintypes.ULONG(0)
    result = iphlpapi.GetAdaptersInfo(None, ctypes.byref(size))
    if result not in (0, ERROR_BUFFER_OVERFLOW):
        return []

    buffer = ctypes.create_string_buffer(size.value)
    adapter_info = ctypes.cast(buffer, ctypes.POINTER(IP_ADAPTER_INFO))
    result = iphlpapi.GetAdaptersInfo(adapter_info, ctypes.byref(size))
    if result != 0:
        return []

    adapters = []
    current = adapter_info
    while current:
        adapters.append(current.contents)
        current = current.contents.Next
    return adapters


def get_directed_broadcast_addresses() -> list[str]:
    """Return the subnet-directed broadcast address for each active, real
    (non-virtual) network adapter, so status packets don't rely on the OS
    picking an interface for 255.255.255.255 when multiple NICs are up."""
    if sys.platform != "win32":
        return []

    try:
        adapters = _iter_adapters()
    except OSError:
        return []

    broadcasts: list[str] = []
    for adapter in adapters:
        if adapter.Type not in _RELEVANT_ADAPTER_TYPES:
            continue
        description = adapter.Description.decode("mbcs", errors="ignore").lower()
        if any(keyword in description for keyword in _VIRTUAL_KEYWORDS):
            continue

        ip_entry = adapter.IpAddressList
        while True:
            ip_str = ip_entry.IpAddress.decode("ascii", errors="ignore")
            mask_str = ip_entry.IpMask.decode("ascii", errors="ignore")
            if ip_str and ip_str != "0.0.0.0" and mask_str and mask_str != "0.0.0.0":
                try:
                    network = ipaddress.ip_network(f"{ip_str}/{mask_str}", strict=False)
                    broadcasts.append(str(network.broadcast_address))
                except ValueError:
                    pass
            if not ip_entry.Next:
                break
            ip_entry = ip_entry.Next.contents

    seen: set[str] = set()
    unique: list[str] = []
    for addr in broadcasts:
        if addr not in seen:
            seen.add(addr)
            unique.append(addr)
    return unique


def resolve_broadcast_targets(configured_host: str) -> list[str]:
    """Expand a configured notify host into concrete send targets.

    A specific unicast/custom host is used as-is. The generic broadcast
    placeholder is replaced with per-adapter directed broadcasts so the
    packet reaches the right subnet even when several NICs are active;
    if none can be determined, it falls back to the plain broadcast."""
    if configured_host != BROADCAST_PLACEHOLDER:
        return [configured_host]

    return get_directed_broadcast_addresses() or [BROADCAST_PLACEHOLDER]
