# TorGuard Lite

A minimal Windows GUI for TorGuard WireGuard and OpenVPN connections with automatic server rotation and killswitch. Uses ~10–20 MB RAM and negligible CPU compared to the official TorGuard app (Electron-based, ~200–400 MB).

## Features

- **Dual-protocol support**: WireGuard (.conf) and OpenVPN (.ovpn)
- **Auto-rotate**: Rotate between servers on a configurable interval (default 30 min)
- **Killswitch**: Windows Firewall-based blocking — only VPN and LAN traffic allowed when active
- **LAN bypass**: Automatically routes local subnet traffic through the physical adapter so printers, NAS, and local servers remain accessible
- **Dual-connection rotation**: New VPN connects before old one disconnects — no connectivity gap
- **Edge resolution**: DNS over HTTPS (Cloudflare) with server IP resolution per rotation cycle

## Platform

**Windows only** (admin privileges required). Relies on `netsh advfirewall`, PowerShell cmdlets (`Get-NetAdapter`, `Get-NetAdapterStatistics`), and `taskkill` — none of which have cross-platform equivalents. No Mac available for testing. A Linux port (`nftables`/`iptables` killswitch + `psutil` stats) is possible in the future.

## Requirements

- Windows 10/11
- TorGuard VPN config files (import .ovpn or .conf)
- [OpenVPN Community Edition](https://openvpn.net/community-downloads) (for .ovpn files)
- [WireGuard](https://www.wireguard.com/install) (for .conf files)

## Installation

1. Install Python 3.10+ and `customtkinter`:
   ```
   pip install customtkinter
   ```
2. Place config files in `%LOCALAPPDATA%\TorGuardLite\configs\` or import via the UI
3. Run the script (auto-elevates to admin):
   ```
   python torguard-lite.py
   ```

## Known Issues & Bugs

### Killswitch — still working out bugs
**Status**: Stabilization in progress

The `netsh advfirewall` killswitch blocks all non-VPN traffic when enabled. Current known quirks:

- Occasionally the killswitch may not fully re-enable after a disconnect if firewall rule cleanup overlaps with reconnect.
- LAN bypass routes (`route add`) can fail on some network profiles (metered connections, public Wi-Fi) — the killswitch still blocks, but LAN devices become unreachable.
- If the OpenVPN process crashes unexpectedly, the killswitch relies on the watchdog, which has a detection lag.

### Rotater — still working out bugs
**Status**: Stabilization in progress

The dual-connection rotation (connect new → promote metric → disconnect old) prevents IP leaks during server switches, but edge cases remain:

- If the **new** VPN connection fails to establish, the old one is already assigned a higher metric — manual reconnect is needed.
- WireGuard → OpenVPN rotation can still leave the old WireGuard adapter in a stale state on some systems; a second rotate usually clears it.
- Rotating during a watchdog-triggered reconnect can put the state machine into an inconsistent position.

### DCO adapter crash on WireGuard adapter removal
**Status**: Fixed

Removing the WireGuard adapter (`/uninstalltunnelservice`) during rotation triggers a kernel-mode change that kills the OpenVPN DCO driver.

Fix: Old WireGuard tunnel is stopped with `net stop` but the adapter is kept (`keep_adapter=True`).

### DNS leak from AllowDNS killswitch rule
**Status**: Fixed

The `AllowDNS` firewall rule was removed — DNS now flows only through the VPN adapter routes.

### --block-outside-dns WFP conflict
**Status**: Fixed

The `--block-outside-dns` OpenVPN flag conflicts with `netsh` killswitch rules on Windows. Removed.

### OpenVPN PID-targeted kill
**Status**: Fixed

`taskkill` now targets the specific OpenVPN PID instead of all `openvpn.exe` instances, so concurrent dual-connection rotation doesn't kill the new VPN.

### LAN access blocked when VPN is connected
**Status**: Fixed

The `--redirect-gateway def1` flag routes all traffic through the VPN adapter, making local network servers unreachable.

Fix: Auto-detect physical adapters, their local subnets, and add bypass routes (`route add <subnet> mask <netmask> <gateway> metric 0`) before VPN connects. Routes are removed on disconnect.

### Rotation crash on WireGuard → OpenVPN switch
**Status**: Fixed (race condition)

The watchdog thread could trigger a false disconnect during rotation if it checked `self.vpn` between disconnecting the old WireGuard and assigning the new OpenVPN. This released the killswitch, leaking the real IP.

Fix: `self.vpn` is now assigned **before** the old VPN disconnects.

## Bug Reports

Report issues with the logs file path below:

```
%LOCALAPPDATA%\TorGuardLite\vpn.log
```

Include the log file and describe:
- What you expected to happen vs what happened
- The VPN config type (.ovpn or .conf)
- Whether killswitch was enabled
- Whether auto-rotate was enabled
