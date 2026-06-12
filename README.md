# TorGuard Lite: A Lightweight, SEO-Optimized GUI for TorGuard WireGuard and OpenVPN Connections

![Badge][badge-build] ![Badge][badge-license] ![Badge][badge-version]

## Title: TorGuard Lite - Minimal Windows GUI for TorGuard VPN Connections
### Subtitle: Automatic Server Rotation, Killswitch, and Dual-Protocol Support

Welcome to TorGuard Lite! This lightweight, minimal Windows Graphical User Interface (GUI) enables seamless connections to TorGuard WireGuard and OpenVPN servers with automatic server rotation, killswitch, and dual-protocol support.

### Features

- **Dual-Protocol Support**: WireGuard (.conf) and OpenVPN (.ovpn) configurations
- **Auto-Rotate Servers**: Configurable interval (default 30 minutes) for seamless server switching
- **Killswitch**: Windows Firewall-based blocking for enhanced security, allowing only VPN and LAN traffic when active
- **LAN Bypass**: Automatic routing of local subnet traffic through the physical adapter for easy access to printers, NAS, and local servers
- **Dual-Connection Rotation**: New VPN connections established before old ones disconnect, ensuring uninterrupted service
- **Edge Resolution**: DNS over HTTPS (Cloudflare) with server IP resolution per rotation cycle for enhanced privacy

### Platform

**Windows only** (admin privileges required). This application utilizes `netsh advfirewall`, PowerShell cmdlets (`Get-NetAdapter`, `Get-NetAdapterStatistics`), and `taskkill`—none of which have cross-platform equivalents. While a Linux port is possible in the future, at present no Mac version is available for testing.

### Requirements

- **Operating System**: Windows 10/11
- **TorGuard VPN Config Files**: Importable .ovpn or .conf files
- **OpenVPN Community Edition**: [Download](https://openvpn.net/community-downloads) (required for .ovpn files)
- **WireGuard**: [Download](https://www.wireguard.com/install) (required for .conf files)

### Installation

**Option A — Pre-built exe (recommended):**

Run `dist\TorGuardLite.exe` directly. No Python required.

**Option B — From source:**

1. Clone the repository:
   ```
   git clone https://github.com/wildfirebill-web/torguard-lite.git
   ```
2. Navigate to the cloned directory:
   ```
   cd torguard-lite
   ```
3. Install requirements:
   ```
   pip install -r requirements.txt
   ```
4. Run TorGuard Lite:
   ```
   python torguard-lite.py
   ```

**Building the exe yourself:**

```
pip install pyinstaller
pyinstaller --onefile --noconsole --name "TorGuardLite" torguard-lite.py
```

### Usage

Upon startup, TorGuard Lite will display a list of available servers. Click on a server to connect, and use the settings menu for configuration options.

### Contributing

We welcome contributions from the open-source community! To submit your changes, please follow our [contribution guidelines](CONTRIBUTING.md).

### License

This project is licensed under the [MIT License](LICENSE).

[badge-build]: https://img.shields.io/github/workflow/status/username/torguard-lite/Build?style=for-the-badge
[badge-license]: https://img.shields.io/github/license/username/torguard-lite?style=for-the-badge
[badge-version]: https://img.shields.io/github/v/tag/username/torguard-lite?style=for-the-badge