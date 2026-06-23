<div align="center">
  <h1>TorGuard Lite</h1>
  <p><strong>Lightweight Windows GUI for TorGuard WireGuard &amp; OpenVPN</strong></p>
  <p>Auto-rotation &bull; Killswitch &bull; Dual-protocol &bull; LAN bypass &bull; Bandwidth monitor</p>

  <!-- Badges -->
  <a href="https://github.com/wildfirebill-web/torguard-lite/releases"><img src="https://img.shields.io/github/v/release/wildfirebill-web/torguard-lite?style=for-the-badge&label=version&color=blue" alt="Release"></a>
  <a href="https://github.com/wildfirebill-web/torguard-lite/blob/main/LICENSE"><img src="https://img.shields.io/github/license/wildfirebill-web/torguard-lite?style=for-the-badge&color=brightgreen" alt="License"></a>
  <img src="https://img.shields.io/badge/python-3.8%2B-blue?style=for-the-badge&logo=python" alt="Python">
  <img src="https://img.shields.io/badge/platform-windows-lightgrey?style=for-the-badge&logo=windows" alt="Windows">
  <a href="https://github.com/wildfirebill-web/torguard-lite/releases"><img src="https://img.shields.io/github/downloads/wildfirebill-web/torguard-lite/total?style=for-the-badge&color=orange" alt="Downloads"></a>
</div>

---

TorGuard Lite is a **minimal, open-source Windows GUI** for connecting to **TorGuard VPN** servers via **WireGuard** and **OpenVPN**. It runs in the system tray, rotates servers automatically, enforces a firewall killswitch, and monitors bandwidth — all at ~15 MB RAM and <1% CPU.

## Features

| Feature | Description |
|---------|-------------|
| **Dual-Protocol** | Load `.conf` (WireGuard) and `.ovpn` (OpenVPN) configs from the same UI |
| **Auto-Rotate** | Switch servers at a configurable interval (default: 30 min) without dropping connection |
| **Killswitch** | Windows Firewall `BlockAll` rule stops all non-VPN traffic. LAN traffic exempted via RFC1918 rules |
| **LAN Bypass** | Automatically routes `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` through the physical adapter |
| **Bandwidth Monitor** | Real-time download/upload speed per adapter with 8 fallback detection methods |
| **Minimize to Tray** | Closes to system tray with `Show` / `Quit` context menu |
| **Dual-Connect Rotation** | New VPN connects *before* old one disconnects — zero-gap switching |
| **DNS over HTTPS** | Resolves server IPs via Cloudflare DoH each cycle to prevent DNS leaks |

## Screenshots

*(screenshot coming soon)*

## Installation

### Download (recommended)

1. Go to the [Releases page](https://github.com/wildfirebill-web/torguard-lite/releases)
2. Download `TorGuardLite_v0.3.0-beta.exe`
3. **Run as Administrator** (required for firewall rules and VPN adapters)

### Build from source

```batch
pip install -r requirements.txt
pip install pyinstaller
pyinstaller --onefile --noconsole ^
  --version-file version_info.txt ^
  --name TorGuardLite ^
  torguard-lite.py
```

The executable will be in `dist\TorGuardLite.exe`.

## Usage

1. Launch `TorGuardLite.exe` as Administrator
2. Enter your **TorGuard credentials** (username/password)
3. Select a **server** from the list
4. Click **Connect**

The app minimizes to the system tray. Use the tray icon to show/hide the window or quit.

### Command-line helpers

- `TorGuardLite.vbs` — launches the EXE silently (no console window)

## Requirements

- **OS:** Windows 10 / 11 (x64)
- **Python:** 3.8+ (only needed for building from source)
- **VPN config files:**
  - WireGuard: `.conf` files in `config/wireguard/`
  - OpenVPN: `.ovpn` files in `config/openvpn/`
- **Admin rights** — always required

## Configuration

Settings are saved to `%LOCALAPPDATA%\TorGuardLite\settings.json`. Logs are written to `%LOCALAPPDATA%\TorGuardLite\vpn.log`.

| Setting | Default | Description |
|---------|---------|-------------|
| `rotate_interval` | 30 | Minutes between server rotations |
| `killswitch` | true | Enable firewall killswitch on connect |
| `lan_bypass` | true | Route LAN traffic through physical adapter |

## Known Issues

- OpenVPN DCO adapters expose `ReceivedBytes` but not `SendBytes` in `Get-NetAdapterStatistics` — tx defaults to 0 on those adapters
- WireGuard tunnel service (`WireGuardTunnel$<name>`) may leave orphans on crash; startup cleanup handles this
- Must run as Administrator

## Resource Usage

| Metric | Value |
|--------|-------|
| RAM | ~10–20 MB |
| CPU | <1% (idle) |
| Disk | ~21 MB (EXE) |
| GPU | None |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). All contributions welcome — bug reports, feature requests, pull requests.

## License

[MIT](LICENSE)

## Security

Found a vulnerability? See [SECURITY.md](SECURITY.md) for our disclosure process.

---

<div align="center">
  <sub>Built with Python, customtkinter, pystray &middot; Not affiliated with TorGuard Inc.</sub>
</div>
