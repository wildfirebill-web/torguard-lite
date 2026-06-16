#!/usr/bin/env python3
import os, sys, json, time, threading, subprocess, platform, socket, re, shutil, signal, ctypes, random
from pathlib import Path
from datetime import datetime
from tkinter import filedialog, messagebox
import customtkinter as ctk
import pystray
from PIL import Image, ImageDraw
from io import BytesIO

SYSTEM = platform.system()

# Fix broken PATH — no System32/Windows/PS dirs found in the env
if SYSTEM == "Windows":
    system32 = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32")
    ps_dir = os.path.join(system32, "WindowsPowerShell", "v1.0")
    os.environ["PATH"] = ps_dir + ";" + system32 + ";" + os.environ.get("PATH", "")
CONFIG_DIR = Path(os.getenv("LOCALAPPDATA", Path.home() / ".local/share")) / "TorGuardLite"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

if SYSTEM == "Windows" and not ctypes.windll.shell32.IsUserAnAdmin():
    script = sys.argv[0]
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{script}"', None, 1)
    sys.exit()
VPN_CONFIGS_DIR = CONFIG_DIR / "configs"
VPN_CONFIGS_DIR.mkdir(exist_ok=True)
SETTINGS_FILE = CONFIG_DIR / "settings.json"
LOG_FILE = CONFIG_DIR / "vpn.log"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")

def log(msg):
    t = datetime.now().strftime("%H:%M:%S")
    line = f"[{t}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def run(cmd, **kw):
    kw.setdefault("capture_output", True)
    kw.setdefault("text", True)
    kw.setdefault("timeout", 15)
    return subprocess.run(cmd, **kw, creationflags=subprocess.CREATE_NO_WINDOW if SYSTEM == "Windows" else 0)

def find_wireguard():
    for p in [r"C:\Program Files\WireGuard\wg.exe", r"C:\Program Files\WireGuard\wg-quick.exe"]:
        if Path(p).exists():
            return Path(p).parent
    p = shutil.which("wg")
    if p:
        return Path(p).parent
    return None

def find_openvpn():
    for p in [r"C:\Program Files\OpenVPN\bin\openvpn.exe",
              r"C:\Program Files\OpenVPN Connect\openvpn.exe"]:
        if Path(p).exists():
            return str(Path(p).parent)
    p = shutil.which("openvpn")
    if p:
        return str(Path(p).parent)
    return None

_lan_routes = []

def add_lan_routes():
    global _lan_routes
    _lan_routes = []
    if SYSTEM != "Windows":
        return
    try:
        script = '''
        Get-NetAdapter -Physical | Where-Object {$_.Status -eq "Up"} | ForEach-Object {
            $ifIndex = $_.ifIndex
            Get-NetIPAddress -InterfaceIndex $ifIndex -AddressFamily IPv4 | ForEach-Object {
                $ip = $_.IPAddress
                $prefix = $_.PrefixLength
                $ipBytes = [net.IPAddress]::Parse($ip).GetAddressBytes()
                [array]::Reverse($ipBytes)
                $ipInt = [bitconverter]::ToUInt32($ipBytes, 0)
                $maskInt = [uint32]([math]::Pow(2, $prefix) - 1) -shl (32 - $prefix)
                $networkInt = $ipInt -band $maskInt
                $networkBytes = [bitconverter]::GetBytes($networkInt)
                [array]::Reverse($networkBytes)
                $network = [net.IPAddress]::new($networkBytes).ToString()
                $maskBytes = [bitconverter]::GetBytes($maskInt)
                [array]::Reverse($maskBytes)
                $mask = [net.IPAddress]::new($maskBytes).ToString()
                $gateway = (Get-NetRoute -InterfaceIndex $ifIndex -DestinationPrefix '0.0.0.0/0' -AddressFamily IPv4 -ErrorAction SilentlyContinue).NextHop
                if ($gateway) {
                    Write-Output "$network $mask $gateway"
                }
            }
        } | Sort-Object -Unique
        '''
        r = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                           capture_output=True, text=True, timeout=15,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        for line in r.stdout.strip().splitlines():
            line = line.strip()
            parts = line.split()
            if len(parts) >= 3:
                try:
                    network = parts[0]
                    mask = parts[1]
                    gateway = parts[2]
                    subprocess.run(["route", "add", network, "mask", mask, gateway, "metric", "0"],
                                   capture_output=True, timeout=5)
                    _lan_routes.append(network)
                    log(f"Added LAN bypass route: {network} via {gateway}")
                except:
                    pass
    except Exception as e:
        log(f"LAN route detection failed: {e}")

def remove_lan_routes():
    global _lan_routes
    for net in _lan_routes:
        try:
            subprocess.run(["route", "delete", net], capture_output=True, timeout=5)
        except:
            pass
    _lan_routes = []

def find_openvpn_connect():
    p = Path(r"C:\Program Files\OpenVPN Connect\OpenVPNConnect.exe")
    return p if p.exists() else None


def resolve_vpn_endpoints(config_path):
    ips = []
    try:
        text = config_path.read_text(errors="replace")
        if config_path.suffix == ".ovpn":
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("remote ") and not line.startswith("remote-cert"):
                    parts = line.split()
                    if len(parts) >= 2:
                        host = parts[1]
                        try:
                            addrs = socket.getaddrinfo(host, 0)
                            for a in addrs:
                                ip = a[4][0]
                                if ip not in ips:
                                    ips.append(ip)
                        except:
                            pass
        elif config_path.suffix == ".conf":
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("Endpoint =") or line.startswith("Endpoint="):
                    host = line.split("=", 1)[1].strip().rsplit(":", 1)[0]
                    try:
                        addrs = socket.getaddrinfo(host, 0)
                        for a in addrs:
                            ip = a[4][0]
                            if ip not in ips:
                                ips.append(ip)
                    except:
                        pass
    except:
        pass
    log(f"Resolved endpoints for {config_path.name}: {ips}")
    return ips


class KillSwitch:
    def __init__(self):
        self.active = False

    def enable(self):
        if self.active:
            return True
        if SYSTEM != "Windows":
            log("Killswitch only supported on Windows currently")
            return False
        try:
            run(["netsh", "advfirewall", "firewall", "add", "rule",
                 "name=TorGuardLite_BlockAll", "dir=out", "action=block",
                 "protocol=any", "enable=yes"])
            run(["netsh", "advfirewall", "firewall", "add", "rule",
                 "name=TorGuardLite_AllowLAN", "dir=out", "action=allow",
                 "remoteip=10.0.0.0-10.255.255.255,172.16.0.0-172.31.255.255,192.168.0.0-192.168.255.255,169.254.0.0-169.254.255.255,127.0.0.0-127.255.255.255",
                 "protocol=any", "enable=yes"])
            run(["netsh", "advfirewall", "firewall", "add", "rule",
                 "name=TorGuardLite_AllowDHCP", "dir=out", "action=allow",
                 "remoteip=255.255.255.255", "protocol=udp", "localport=68", "remoteport=67", "enable=yes"])
            self.active = True
            log("Killswitch ENABLED - non-VPN traffic blocked")
            return True
        except Exception as e:
            log(f"Killswitch enable failed: {e}")
            return False

    def allow_vpn_adapter(self, name):
        if SYSTEM != "Windows" or not name:
            return
        try:
            run(["netsh", "advfirewall", "firewall", "add", "rule",
                 f"name=TorGuardLite_AllowVPN_{name}", "dir=out", "action=allow",
                 f"interface={name}", "protocol=any", "enable=yes"])
            log(f"Allowed traffic through VPN adapter: {name}")
        except Exception as e:
            log(f"VPN adapter rule failed: {e}")

    def remove_vpn_adapter_allow(self, name):
        if SYSTEM != "Windows" or not name:
            return
        try:
            r = run(["netsh", "advfirewall", "firewall", "show", "rule",
                     f"name=TorGuardLite_AllowVPN_{name}"], shell=True)
            if r.returncode == 0:
                run(["netsh", "advfirewall", "firewall", "delete", "rule",
                     f"name=TorGuardLite_AllowVPN_{name}"])
                log(f"Removed VPN adapter allow rule: {name}")
        except Exception as e:
            log(f"Remove VPN adapter rule failed: {e}")

    def disable(self):
        if SYSTEM != "Windows":
            return False
        try:
            rules = run(["netsh", "advfirewall", "firewall", "show", "rule",
                         "name=TorGuardLite_BlockAll"], shell=True)
            if rules.returncode == 0:
                run(["netsh", "advfirewall", "firewall", "delete", "rule",
                     "name=TorGuardLite_BlockAll"])
            result = run(["netsh", "advfirewall", "firewall", "show", "rule",
                          "name=TorGuardLite_AllowLAN"], shell=True)
            if result.returncode == 0:
                run(["netsh", "advfirewall", "firewall", "delete", "rule",
                     "name=TorGuardLite_AllowLAN"])
            result = run(["netsh", "advfirewall", "firewall", "show", "rule",
                          "name=TorGuardLite_AllowDHCP"], shell=True)
            if result.returncode == 0:
                run(["netsh", "advfirewall", "firewall", "delete", "rule",
                     "name=TorGuardLite_AllowDHCP"])
            all_vpn = run(["netsh", "advfirewall", "firewall", "show", "rule",
                           "name=TorGuardLite_AllowVPN_"], shell=True)
            if all_vpn.returncode == 0:
                run(["netsh", "advfirewall", "firewall", "delete", "rule",
                     "name=TorGuardLite_AllowVPN_"])
            temp = run(["netsh", "advfirewall", "firewall", "show", "rule",
                        "name=TorGuardLite_Temp_"], shell=True)
            if temp.returncode == 0:
                run(["netsh", "advfirewall", "firewall", "delete", "rule",
                     "name=TorGuardLite_Temp_"])
            self.active = False
            log("Killswitch DISABLED")
            return True
        except Exception as e:
            log(f"Killswitch disable failed: {e}")
            return False

    def remove_all_temp_allows(self):
        if SYSTEM != "Windows":
            return
        try:
            r = run(["netsh", "advfirewall", "firewall", "show", "rule", "name=TorGuardLite_Temp_"], shell=True)
            if r.returncode == 0:
                run(["netsh", "advfirewall", "firewall", "delete", "rule", "name=TorGuardLite_Temp_"])
                log("All temp allow rules removed")
        except:
            pass

    def add_temp_allow(self, name_suffix, remoteip):
        if SYSTEM != "Windows":
            return
        try:
            run(["netsh", "advfirewall", "firewall", "add", "rule",
                 f"name=TorGuardLite_Temp_{name_suffix}", "dir=out", "action=allow",
                 f"remoteip={remoteip}", "protocol=any", "enable=yes"])
            log(f"Temp allow rule added for {remoteip}")
        except Exception as e:
            log(f"Temp allow rule failed: {e}")

    def remove_temp_allow(self, name_suffix):
        if SYSTEM != "Windows":
            return
        try:
            run(["netsh", "advfirewall", "firewall", "delete", "rule",
                 f"name=TorGuardLite_Temp_{name_suffix}"])
        except:
            pass


ROTATE_TYPE_ANY = "Any"
ROTATE_TYPES = [ROTATE_TYPE_ANY, "Alternate", "WG → OpenVPN", "WG → WG", "OpenVPN → WG", "OpenVPN → OpenVPN"]

class WireGuardConnection:
    vpn_type = "wg"
    def __init__(self, config_path):
        self.config_path = Path(config_path)
        self.name = self.config_path.stem
        self.process = None
        self.running = False
        self.adapter = None
        self.wg_dir = find_wireguard()

    def connect(self):
        if not self.wg_dir:
            raise Exception("WireGuard not found. Install from wireguard.com/install")
        wg = Path(self.wg_dir) / "wg.exe"
        wg_exe = Path(self.wg_dir) / "wireguard.exe"
        log(f"Starting WireGuard: {self.name}")
        # Remove any stale tunnel service from a previous rotation before installing
        subprocess.run([str(wg_exe), "/uninstalltunnelservice", self.name],
                       capture_output=True, timeout=10,
                       creationflags=subprocess.CREATE_NO_WINDOW)
        self._wireguard_cmd(wg_exe, ["/installtunnelservice", str(self.config_path)])
        svc = f"WireGuardTunnel${self.name}"
        subprocess.run(["net", "start", svc], capture_output=True, timeout=10,
                       creationflags=subprocess.CREATE_NO_WINDOW)
        time.sleep(3)
        r = run([str(wg), "show", self.name], timeout=5)
        if r.returncode != 0:
            raise Exception("WireGuard tunnel failed to start")
        self.running = True
        self._detect_adapter()
        log(f"WireGuard connected: {self.name}")
        return True

    def _wireguard_cmd(self, wg_exe, args):
        r = subprocess.run([str(wg_exe)] + args, capture_output=True, text=True, timeout=15,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip()
            if "already installed" not in err.lower():
                raise Exception(f"wireguard.exe failed: {err}")

    def _detect_adapter(self):
        try:
            script = (
                "Get-NetAdapter | Where-Object { "
                "$_.InterfaceDescription -like '*WireGuard*' -or "
                "$_.Name -like 'WireGuard*' } | "
                "Select-Object -First 1 -ExpandProperty Name"
            )
            r = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                               capture_output=True, text=True, timeout=15,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            out = r.stdout.strip()
            if out:
                self.adapter = out
        except:
            pass

    def _disable_service(self, name):
        run(["sc", "config", name, "start=disabled"], timeout=10)

    def disconnect(self, keep_adapter=False):
        if not self.wg_dir:
            return False
        wg_exe = Path(self.wg_dir) / "wireguard.exe"
        svc = f"WireGuardTunnel${self.name}"
        self._disable_service(svc)
        run(["net", "stop", svc], timeout=10)
        if not keep_adapter:
            run([str(wg_exe), "/uninstalltunnelservice", self.name], timeout=10)
        self.running = False
        self.adapter = None
        log(f"WireGuard disconnected (keep_adapter={keep_adapter})")
        return True

    def check(self):
        if not self.running:
            return False
        try:
            r = run([str(Path(self.wg_dir or ".") / "wg"), "show", self.name],
                    capture_output=True, timeout=5)
            return r.returncode == 0
        except:
            try:
                r = run(["powershell", "-Command",
                         "Get-NetAdapter | Where-Object {($_.InterfaceDescription -like '*WireGuard*' -or $_.Name -like 'WireGuard*') -and $_.Status -eq 'Up'} | Measure-Object | Select-Object -ExpandProperty Count"],
                        shell=True)
                return r.stdout.strip() != "0"
            except:
                return False


class OpenVPNConnection:
    vpn_type = "open"
    def __init__(self, config_path):
        self.config_path = Path(config_path)
        self.name = self.config_path.stem
        self.process = None
        self.running = False
        self.adapter = None
        self.pid = None
        self.ovpn_dir = find_openvpn()
        self.log_path = CONFIG_DIR / f"ovpn_{self.name}.log"

    def _needs_auth(self):
        return "auth-user-pass" in self.config_path.read_text(encoding="utf-8", errors="replace")

    @staticmethod
    def _prompt_auth_gui():
        win = ctk.CTkToplevel()
        win.title("OpenVPN Credentials")
        win.geometry("350x250")
        win.transient()
        win.grab_set()
        ctk.CTkLabel(win, text="TorGuard Username:").pack(pady=(15, 0))
        u = ctk.CTkEntry(win, width=280)
        u.pack(pady=5)
        ctk.CTkLabel(win, text="Password:").pack(pady=(5, 0))
        p = ctk.CTkEntry(win, width=280, show="*")
        p.pack(pady=5)
        result = {}
        def ok():
            result["u"] = u.get()
            result["p"] = p.get()
            win.destroy()
        def cancel():
            result["u"] = ""
            result["p"] = ""
            win.destroy()
        btn_frame = ctk.CTkFrame(win, fg_color="transparent")
        btn_frame.pack(pady=10)
        ctk.CTkButton(btn_frame, text="OK", command=ok, width=100).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Cancel", command=cancel, width=100, fg_color="#5a3030").pack(side="left", padx=5)
        win.wait_window()
        return result.get("u"), result.get("p")

    def connect(self):
        if not self.ovpn_dir:
            raise Exception("OpenVPN not found. Install from openvpn.net")
        ovpn_exe = str(Path(self.ovpn_dir) / "openvpn")
        if SYSTEM == "Windows":
            ovpn_exe += ".exe"
        log(f"Starting OpenVPN: {self.name}")
        args = [ovpn_exe, "--config", str(self.config_path),
                "--redirect-gateway", "def1",
                "--auth-nocache",
                "--log", str(self.log_path)]
        if self._needs_auth():
            auth_path = CONFIG_DIR / "auth_global.txt"
            if not auth_path.exists():
                uname, pword = self._prompt_auth_gui()
                if not uname:
                    raise Exception("OpenVPN credentials required")
                auth_path.write_bytes(f"{uname}\n{pword}\n".encode())
            args.extend(["--auth-user-pass", str(auth_path)])
        self.process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW)
        self.pid = self.process.pid
        time.sleep(5)
        if self.process.poll() is not None:
            rc = self.process.returncode
            err = self.process.stderr.read().decode()[:500]
            raise Exception(f"OpenVPN failed (exit {rc}): {err}")
        self._detect_adapter()
        if not self.adapter:
            self.process.terminate()
            raise Exception("OpenVPN started but no TAP/DCO adapter appeared")
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        f"Set-NetIPInterface -InterfaceAlias '{self.adapter}' -InterfaceMetric 5"],
                       capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        log(f"Set VPN adapter metric to 5: {self.adapter}")
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        f"New-NetRoute -DestinationPrefix '0.0.0.0/0' -InterfaceAlias '{self.adapter}' -NextHop '0.0.0.0' -RouteMetric 1 -ErrorAction SilentlyContinue"],
                       capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        log("Added default route via VPN adapter")
        time.sleep(3)
        if self.process.poll() is not None:
            rc = self.process.returncode
            raise Exception(f"OpenVPN failed during DCO stabilization (exit {rc})")
        self.running = True
        log(f"OpenVPN connected: {self.name}")
        return True

    def _detect_adapter(self):
        try:
            script = (
                "Get-NetAdapter | Where-Object { "
                "$_.InterfaceDescription -like '*OpenVPN*' -or "
                "$_.InterfaceDescription -like '*TAP*' -or "
                "$_.Name -like '*TAP*' -or "
                "$_.Name -like '*OpenVPN*' -or "
                "$_.Name -like 'ovpn-dco*' } | "
                "Select-Object -First 1 -ExpandProperty Name"
            )
            r = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                               capture_output=True, text=True, timeout=15,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            out = r.stdout.strip()
            if out:
                self.adapter = out
        except:
            pass

    def disconnect(self):
        log(f"Stopping OpenVPN: {self.name}")
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=8)
            except:
                self.process.kill()
        if SYSTEM == "Windows" and self.pid:
            run(["taskkill", "/F", "/PID", str(self.pid)], capture_output=True)
        self.running = False
        self.adapter = None
        self.pid = None
        log("OpenVPN disconnected")
        return True

    def check(self):
        if not self.running:
            return False
        if self.process and self.process.poll() is not None:
            self.running = False
            return False
        return True


class TorGuardLite(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("TorGuard Lite")
        self.geometry("820x600")
        self.minsize(700, 500)

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.bind("<Unmap>", self._on_minimize)

        self.tray_icon = None
        self._tray_ready = threading.Event()

        self.settings = self._load_settings()
        self.killswitch = KillSwitch()
        self.vpn = None
        self.watchdog = None
        self.rotate_timer = None
        self.temp_rules = []
        self.connected = False

        self.bw_unit_var = ctk.StringVar(value=self.settings.get("bw_unit", "MB"))
        self.bw_prev_bytes = None
        self.bw_prev_time = None
        self.bw_timer = None
        self.bw_total_rx = 0
        self.bw_total_tx = 0

        self._build_ui()
        self._build_tray()
        self._check_binaries()
        self._update_state()
        # Sync auto-start with shortcut state
        if self.settings.get("auto_start", False):
            self._set_auto_start(True)

    def _load_settings(self):
        if SETTINGS_FILE.exists():
            return json.loads(SETTINGS_FILE.read_text())
        return {"killswitch_on_connect": True, "reconnect_on_drop": False,
                "config_dir": "", "auto_start": False,
                "rotate_enabled": False, "rotate_interval": 30,
                "rotate_type": ROTATE_TYPE_ANY}

    def _save_settings(self):
        SETTINGS_FILE.write_text(json.dumps(self.settings, indent=2))

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(15, 0))
        header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(header, text="TorGuard Lite", font=ctk.CTkFont(size=22, weight="bold")).grid(row=0, column=0, sticky="w")

        # Bandwidth monitor
        bw_frame = ctk.CTkFrame(header, fg_color="transparent")
        bw_frame.grid(row=0, column=1, sticky="e")
        self.bw_down_label = ctk.CTkLabel(bw_frame, text="", font=ctk.CTkFont(size=12), text_color="#4ade80")
        self.bw_down_label.pack(side="left", padx=(0, 2))
        self.bw_up_label = ctk.CTkLabel(bw_frame, text="", font=ctk.CTkFont(size=12), text_color="#60a5fa")
        self.bw_up_label.pack(side="left", padx=(2, 4))
        self.bw_unit_dropdown = ctk.CTkComboBox(bw_frame, variable=self.bw_unit_var,
                                                  values=["KB", "Mb", "MB", "Gb", "GB"],
                                                  width=65, state="readonly",
                                                  command=self._on_bw_unit_change)
        self.bw_unit_dropdown.pack(side="left", padx=(0, 6))

        self.status_label = ctk.CTkLabel(header, text="Disconnected", font=ctk.CTkFont(size=13),
                                          text_color="#888")
        self.status_label.grid(row=0, column=2, sticky="e", padx=(0, 0))

        # Main area
        main = ctk.CTkFrame(self)
        main.grid(row=1, column=0, sticky="nsew", padx=20, pady=15)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)

        # === Config selector ===
        cfg_frame = ctk.CTkFrame(main, fg_color="transparent")
        cfg_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        cfg_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(cfg_frame, text="Config:", font=ctk.CTkFont(size=13)).grid(row=0, column=0, sticky="w")
        self.config_var = ctk.StringVar()
        self.config_dropdown = ctk.CTkFrame(cfg_frame, width=300, height=28)
        self.config_dropdown.grid(row=0, column=1, padx=(8, 5), sticky="w")
        self.config_dropdown.grid_propagate(False)
        self.config_dropdown.bind("<Button-1>", self._open_config_popup)
        self.config_dropdown_lbl = ctk.CTkLabel(self.config_dropdown, text="",
                                                  anchor="w", font=ctk.CTkFont(size=13))
        self.config_dropdown_lbl.pack(fill="both", expand=True, padx=8)
        self.config_dropdown_lbl.bind("<Button-1>", self._open_config_popup)
        self._config_popup = None
        self.import_btn = ctk.CTkButton(cfg_frame, text="+ Import", width=90,
                                         command=self._import_config)
        self.import_btn.grid(row=0, column=2, padx=(0, 5))
        self.remove_btn = ctk.CTkButton(cfg_frame, text="Remove", width=80,
                                         command=self._remove_config, fg_color="#5a3030",
                                         hover_color="#7a4040")
        self.remove_btn.grid(row=0, column=3, padx=(0, 5))
        self.scan_btn = ctk.CTkButton(cfg_frame, text="Scan Dir", width=80,
                                       command=self._scan_directory)
        self.scan_btn.grid(row=0, column=4, padx=(0, 5))
        self.dir_btn = ctk.CTkButton(cfg_frame, text="Set Dir", width=80,
                                      command=self._set_config_dir)
        self.dir_btn.grid(row=0, column=5)
        cfg_dir = self.settings.get("config_dir", "")
        self.dir_label = ctk.CTkLabel(cfg_frame, text=cfg_dir if cfg_dir else "(app data default)",
                                       font=ctk.CTkFont(size=11), text_color="#888")
        self.dir_label.grid(row=1, column=1, columnspan=4, sticky="w", padx=(8, 0), pady=(2, 0))

        # === Log area ===
        log_frame = ctk.CTkFrame(main)
        log_frame.grid(row=1, column=0, sticky="nsew")
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)
        self.log_text = ctk.CTkTextbox(log_frame, font=ctk.CTkFont(family="Consolas", size=12),
                                        wrap="word")
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=1, pady=1)

        # === Bottom controls ===
        ctrl = ctk.CTkFrame(self, fg_color="transparent")
        ctrl.grid(row=2, column=0, sticky="ew", padx=20, pady=(5, 15))
        ctrl.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        self.connect_btn = ctk.CTkButton(ctrl, text="Connect", fg_color="#1a6b3c",
                                          hover_color="#218c4e", height=38,
                                          font=ctk.CTkFont(size=14, weight="bold"),
                                          command=self._toggle_connect)
        self.connect_btn.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        self.ks_var = ctk.BooleanVar(value=self.settings.get("killswitch_on_connect", True))
        self.ks_check = ctk.CTkCheckBox(ctrl, text="Killswitch", variable=self.ks_var,
                                          command=self._on_ks_toggle)
        self.ks_check.grid(row=0, column=1, padx=5, sticky="ew")

        self.recon_var = ctk.BooleanVar(value=self.settings.get("reconnect_on_drop", False))
        self.recon_check = ctk.CTkCheckBox(ctrl, text="Auto-Reconnect", variable=self.recon_var,
                                             command=self._on_recon_toggle)
        self.recon_check.grid(row=0, column=2, padx=5, sticky="ew")

        # === Auto-Rotate row ===
        self.rotate_var = ctk.BooleanVar(value=self.settings.get("rotate_enabled", False))
        self.rotate_check = ctk.CTkCheckBox(ctrl, text="Rotate", variable=self.rotate_var,
                                              command=self._on_rotate_toggle)
        self.rotate_check.grid(row=1, column=0, padx=(0,5), sticky="ew", pady=(5,0))
        self.rotate_interval_var = ctk.StringVar(value=str(self.settings.get("rotate_interval", 30)))
        rot_frame = ctk.CTkFrame(ctrl, fg_color="transparent")
        rot_frame.grid(row=1, column=1, columnspan=2, sticky="w", padx=5, pady=(5,0))
        ctk.CTkLabel(rot_frame, text="Rotate every",
                     font=ctk.CTkFont(size=12)).pack(side="left")
        self.rotate_spin = ctk.CTkEntry(rot_frame, width=55,
                                         textvariable=self.rotate_interval_var,
                                         font=ctk.CTkFont(size=12))
        self.rotate_spin.pack(side="left", padx=(4,3))
        ctk.CTkLabel(rot_frame, text="min",
                     font=ctk.CTkFont(size=12)).pack(side="left")
        self.rotate_save_btn = ctk.CTkButton(rot_frame, text="Set", width=42, height=22,
                                                font=ctk.CTkFont(size=11),
                                                command=self._on_rotate_interval_set)
        self.rotate_save_btn.pack(side="left", padx=(5,0))

        self.rotate_type_var = ctk.StringVar(value=self.settings.get("rotate_type", ROTATE_TYPE_ANY))
        rot_type_frame = ctk.CTkFrame(ctrl, fg_color="transparent")
        rot_type_frame.grid(row=2, column=0, columnspan=5, sticky="w", padx=5, pady=(2,0))
        ctk.CTkLabel(rot_type_frame, text="Rotate type:",
                     font=ctk.CTkFont(size=12)).pack(side="left")
        self.rotate_type_dropdown = ctk.CTkComboBox(rot_type_frame, values=ROTATE_TYPES,
                                                      variable=self.rotate_type_var,
                                                      width=150, state="readonly",
                                                      command=self._on_rotate_type_set)
        self.rotate_type_dropdown.pack(side="left", padx=(5,0))

        self.auto_var = ctk.BooleanVar(value=self.settings.get("auto_start", False))
        self.auto_check = ctk.CTkCheckBox(ctrl, text="Run on Boot", variable=self.auto_var,
                                           command=self._on_auto_toggle)
        self.auto_check.grid(row=0, column=3, padx=5, sticky="ew")

        self.clear_btn = ctk.CTkButton(ctrl, text="Clear Log", fg_color="#333",
                                        hover_color="#444", command=self._clear_log)
        self.clear_btn.grid(row=0, column=4, padx=(5, 0), sticky="ew")

    def _list_configs(self):
        files = set()
        dirs = [VPN_CONFIGS_DIR]
        cfg_dir = self.settings.get("config_dir", "")
        if cfg_dir:
            d2 = Path(cfg_dir)
            if d2.is_dir():
                dirs.append(d2)
        for d in dirs:
            for ext in ("*.conf", "*.ovpn"):
                for f in d.glob(ext):
                    files.add(f.name)
        return sorted(files) or ["(no configs imported)"]

    def _set_config_dir(self):
        d = filedialog.askdirectory(title="Select VPN configs folder")
        if not d:
            return
        self.settings["config_dir"] = d
        self._save_settings()
        self.dir_label.configure(text=d)
        log(f"Config directory set to: {d}")
        self._refresh_configs()

    def _refresh_configs(self):
        vals = self._list_configs()
        if vals and vals[0] != "(no configs imported)":
            if self.config_var.get() not in vals:
                self._set_config_name(vals[0])
        else:
            self._set_config_name("(no configs imported)")

    def _set_config_name(self, name):
        self.config_var.set(name)
        self.config_dropdown_lbl.configure(text=name)

    def _open_config_popup(self, event=None):
        if self.connected:
            return
        if self._config_popup:
            self._config_popup_close(self._config_popup)
            return
        popup = ctk.CTkToplevel(self)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        x = self.config_dropdown.winfo_rootx()
        y = self.config_dropdown.winfo_rooty() + self.config_dropdown.winfo_height() + 2
        popup.geometry(f"320x400+{x}+{y}")
        popup.grid_columnconfigure(0, weight=1)
        popup.grid_rowconfigure(0, weight=1)
        frame = ctk.CTkScrollableFrame(popup, border_width=1, border_color="#555")
        frame.grid(row=0, column=0, sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)
        selected = self.config_var.get()
        for name in self._list_configs():
            fg = "#2a3a2a" if name == selected else "transparent"
            btn = ctk.CTkButton(frame, text=name, anchor="w", fg_color=fg,
                                hover_color="#333", font=ctk.CTkFont(size=13), height=28,
                                command=lambda n=name: self._config_popup_pick(n))
            btn.pack(fill="x", padx=4, pady=1)
        self._config_popup = popup
        popup.focus_set()
        popup.bind("<Escape>", lambda e: self._config_popup_close(popup))

    def _config_popup_pick(self, name):
        self._set_config_name(name)
        self._config_popup_close(self._config_popup)

    def _config_popup_close(self, popup=None):
        if popup is None:
            popup = self._config_popup
        if popup:
            try:
                popup.destroy()
            except:
                pass
        self._config_popup = None

    def _error_dialog(self, title, message):
        win = ctk.CTkToplevel(self)
        win.title(title)
        win.geometry("500x200")
        win.transient(self)
        win.grab_set()
        txt = ctk.CTkTextbox(win, wrap="word")
        txt.pack(fill="both", expand=True, padx=10, pady=(10, 5))
        txt.insert("0.0", message)
        txt.configure(state="normal")
        btn = ctk.CTkButton(win, text="OK", command=win.destroy)
        btn.pack(pady=(0, 10))

    def _import_config(self):
        f = filedialog.askopenfilename(
            title="Select VPN Config",
            filetypes=[("VPN Configs", "*.conf *.ovpn"), ("All Files", "*.*")])
        if not f:
            return
        src = Path(f)
        if src.suffix.lower() not in (".conf", ".ovpn"):
            self._error_dialog("Error", "Select a .conf (WireGuard) or .ovpn (OpenVPN) file")
            return
        cfg_dir = self.settings.get("config_dir", "")
        dest_dir = Path(cfg_dir) if cfg_dir and Path(cfg_dir).is_dir() else VPN_CONFIGS_DIR
        dst = dest_dir / src.name
        if src.resolve() != dst.resolve():
            try:
                shutil.copy2(src, dst)
            except PermissionError:
                self._error_dialog("Error", f"Cannot copy config — file is in use. Close any app using it and retry.")
                return
        log(f"Config ready: {dst}")
        self._refresh_configs()
        self._set_config_name(dst.name)

    def _scan_directory(self):
        d = filedialog.askdirectory(title="Scan folder for VPN configs")
        if not d:
            return
        src_dir = Path(d)
        existing = set()
        for ext in ("*.conf", "*.ovpn"):
            for f in VPN_CONFIGS_DIR.glob(ext):
                existing.add(f.name)
        imported = []
        for ext in ("*.conf", "*.ovpn"):
            for f in sorted(src_dir.glob(ext)):
                if f.name in existing:
                    continue
                dst = VPN_CONFIGS_DIR / f.name
                try:
                    shutil.copy2(f, dst)
                    imported.append(f.name)
                    log(f"Imported: {f.name}")
                except PermissionError:
                    self._append_log(f"Skipped {f.name} — file in use")
        if imported:
            msg = f"Imported {len(imported)} new config{'s' if len(imported) != 1 else ''}"
            self._append_log(msg)
        else:
            self._append_log("No new configs found in that folder")
        self._refresh_configs()

    def _remove_config(self):
        name = self.config_var.get()
        if not name or name == "(no configs imported)":
            return
        p = None
        for d in [VPN_CONFIGS_DIR]:
            cfg_dir = self.settings.get("config_dir", "")
            if cfg_dir:
                d2 = Path(cfg_dir)
                if d2.is_dir():
                    d = d2
            p = d / name
            if p.exists():
                break
        if p and p.exists():
            if self.connected and self.vpn and self.vpn.name == p.stem:
                self._disconnect()
            p.unlink()
            log(f"Removed config: {name}")
        self._refresh_configs()

    def _check_binaries(self):
        if SYSTEM == "Windows":
            wg = find_wireguard()
            ov = find_openvpn()
            ovc = find_openvpn_connect()
            if wg:
                self._append_log(f"WireGuard found: {wg}")
            else:
                self._append_log("WireGuard not found. Install from wireguard.com/install")
            if ov:
                self._append_log(f"OpenVPN found: {ov}")
            elif ovc:
                self._append_log("OpenVPN Connect found but missing CLI. Install OpenVPN Community Edition from openvpn.net/community-downloads")
            else:
                self._append_log("OpenVPN not found. Install from openvpn.net/community-downloads")

    def _append_log(self, msg):
        t = datetime.now().strftime("%H:%M:%S")
        display = f"[{t}] {msg}"
        self.log_text.insert("end", display + "\n")
        self.log_text.see("end")
        log(msg)

    def _clear_log(self):
        self.log_text.delete("1.0", "end")

    def _read_bw_bytes(self):
        adapter_name = self.vpn.adapter if self.vpn else None
        if not adapter_name:
            log("BW: no adapter name available")
            return None, None
        rx, tx = self._query_adapter_stats(adapter_name)
        if rx is not None:
            return rx, tx
        log(f"BW: stats failed for '{adapter_name}', re-detecting adapter")
        if self.vpn:
            self.vpn._detect_adapter()
        adapter_name = self.vpn.adapter if self.vpn else None
        if adapter_name:
            rx, tx = self._query_adapter_stats(adapter_name)
            if rx is not None:
                return rx, tx
            log(f"BW: stats still failed after re-detect (adapter='{adapter_name}')")
        else:
            log("BW: adapter re-detect returned nothing")
        return None, None

    def _query_adapter_stats(self, name):
        def _parse_ps_stats(script):
            try:
                r = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                                   capture_output=True, text=True, timeout=5,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
                parts = r.stdout.strip().split()
                if len(parts) >= 2:
                    return int(parts[0]), int(parts[1])
            except:
                pass
            return None, None

        safe = name.replace("'", "''")

        # 1. Exact name via Get-NetAdapterStatistics
        script = (
            "$s=Get-NetAdapterStatistics -Name '" + safe + "' -ErrorAction SilentlyContinue; "
            "if ($s) { Write-Output \"$($s.ReceivedBytes) $($s.SendBytes)\" }"
        )
        rx, tx = _parse_ps_stats(script)
        if rx is not None:
            return rx, tx

        # 2. Broader scan: Name or InterfaceDescription
        script = (
            "$a=Get-NetAdapter | Where-Object { "
            "$_.Name -eq '" + safe + "' -or "
            "$_.InterfaceDescription -like '*WireGuard*' -or "
            "$_.InterfaceDescription -like '*OpenVPN*' -or "
            "$_.InterfaceDescription -like '*TAP*' -or "
            "$_.Name -like 'WireGuard*' -or "
            "$_.Name -like '*TAP*' -or "
            "$_.Name -like '*OpenVPN*' -or "
            "$_.Name -like 'ovpn-dco*' } | Select-Object -First 1; "
            "if ($a) { "
            "$s=Get-NetAdapterStatistics -Name $a.Name -ErrorAction SilentlyContinue; "
            "if ($s) { Write-Output \"$($s.ReceivedBytes) $($s.SendBytes)\" } }"
        )
        rx, tx = _parse_ps_stats(script)
        if rx is not None:
            return rx, tx

        # 3. WMI fallback (most reliable, no module dependency)
        script = (
            "$iface=Get-WmiObject -Class Win32_PerfRawData_Tcpip_NetworkInterface "
            "| Where-Object { "
            "$_.Name -eq '" + safe + "' -or "
            "$_.Name -like '*WireGuard*' -or "
            "$_.Name -like '*OpenVPN*' -or "
            "$_.Name -like '*TAP*' -or "
            "$_.Name -like '*ovpn-dco*' } "
            "| Select-Object -First 1; "
            "if ($iface) { "
            "Write-Output \"$($iface.BytesReceivedPersec) $($iface.BytesSentPersec)\" }"
        )
        rx, tx = _parse_ps_stats(script)
        return rx, tx

    def _format_bw(self, value):
        unit = self.bw_unit_var.get()
        if unit == "KB":
            v = value / 1024
            return f"{v:.1f}" if v < 10 else f"{v:.0f}"
        if unit == "Mb":
            v = value * 8 / 1024 / 1024
            return f"{v:.1f}" if v < 10 else f"{v:.0f}"
        if unit == "MB":
            v = value / 1024 / 1024
            return f"{v:.1f}" if v < 10 else f"{v:.0f}"
        if unit == "Gb":
            v = value * 8 / 1024 / 1024 / 1024
            return f"{v:.2f}" if v < 10 else f"{v:.1f}"
        if unit == "GB":
            v = value / 1024 / 1024 / 1024
            return f"{v:.2f}" if v < 10 else f"{v:.1f}"
        return f"{value:.0f}"

    def _poll_bandwidth(self):
        rx, tx = self._read_bw_bytes()
        if rx is not None and tx is not None and self.bw_prev_bytes is not None:
            prev_rx, prev_tx = self.bw_prev_bytes
            now = time.time()
            dt = now - self.bw_prev_time
            if dt > 0:
                dl = max(0, (rx - prev_rx) / dt)
                ul = max(0, (tx - prev_tx) / dt)
                self.bw_total_rx += rx - prev_rx
                self.bw_total_tx += tx - prev_tx
                dl_str = self._format_bw(dl)
                ul_str = self._format_bw(ul)
                unit = self.bw_unit_var.get()
                self.bw_down_label.configure(text=f"\u2193 {dl_str} {unit}/s")
                self.bw_up_label.configure(text=f"\u2191 {ul_str} {unit}/s")
            elif rx != prev_rx or tx != prev_tx:
                self.bw_down_label.configure(text="\u2193 ...")
                self.bw_up_label.configure(text="\u2191 ...")
        self.bw_prev_bytes = (rx, tx) if rx is not None and tx is not None else self.bw_prev_bytes
        self.bw_prev_time = time.time()
        self.bw_timer = self.after(1000, self._poll_bandwidth)

    def _start_bandwidth_monitor(self):
        self._stop_bandwidth_monitor()
        self.bw_prev_bytes = None
        self.bw_prev_time = time.time()
        self.bw_total_rx = 0
        self.bw_total_tx = 0
        self._poll_bandwidth()

    def _stop_bandwidth_monitor(self):
        if self.bw_timer:
            self.after_cancel(self.bw_timer)
            self.bw_timer = None
        self.bw_down_label.configure(text="")
        self.bw_up_label.configure(text="")
        self.bw_prev_bytes = None

    def _on_bw_unit_change(self, _=None):
        self.settings["bw_unit"] = self.bw_unit_var.get()
        self._save_settings()

    def _update_state(self):
        if self.connected:
            self.status_label.configure(text="Connected", text_color="#4ade80")
            self.connect_btn.configure(text="Disconnect", fg_color="#5a3030",
                                       hover_color="#7a4040")
            self.import_btn.configure(state="disabled")
            self.remove_btn.configure(state="disabled")
            self.config_dropdown_lbl.configure(text_color="#555")
        else:
            self.status_label.configure(text="Disconnected", text_color="#888")
            self.connect_btn.configure(text="Connect", fg_color="#1a6b3c",
                                       hover_color="#218c4e")
            self.import_btn.configure(state="normal")
            self.remove_btn.configure(state="normal")
            self.config_dropdown_lbl.configure(text_color="#d4d4d4")

    def _toggle_connect(self):
        if self.connected:
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        name = self.config_var.get()
        if not name or name == "(no configs imported)":
            messagebox.showwarning("No Config", "Import a WireGuard (.conf) or OpenVPN (.ovpn) config first")
            return
        self._cleanup_orphans()
        cfg_path = None
        for d in [VPN_CONFIGS_DIR]:
            cfg_dir = self.settings.get("config_dir", "")
            if cfg_dir:
                d2 = Path(cfg_dir)
                if d2.is_dir():
                    d = d2
            p = d / name
            if p.exists():
                cfg_path = p
                break
        if not cfg_path:
            self._error_dialog("Error", f"Config file not found: {name}")
            return

        ext = cfg_path.suffix.lower()
        try:
            if ext == ".conf":
                self.vpn = WireGuardConnection(cfg_path)
            elif ext == ".ovpn":
                self.vpn = OpenVPNConnection(cfg_path)
            else:
                self._error_dialog("Error", f"Unsupported config type: {ext}")
                return

            self._append_log(f"Connecting {self.vpn.name}...")
            add_lan_routes()
            self.vpn.connect()
            self.connected = True

            # Killswitch
            if self.ks_var.get():
                self.killswitch.enable()
                if self.vpn.adapter:
                    self.killswitch.allow_vpn_adapter(self.vpn.adapter)
                self._append_log("Killswitch active")

            self._append_log("Connected!")
            self.killswitch.remove_all_temp_allows()
            self._update_state()
            self._start_watchdog()
            self._start_bandwidth_monitor()
            if self.rotate_var.get():
                self._start_rotate_timer()
        except Exception as e:
            self._append_log(f"Connection failed: {e}")
            self._error_dialog("Connection Error", str(e))
            remove_lan_routes()
            self.killswitch.remove_all_temp_allows()
            self._cleanup_orphans()
            self.connected = False
            self.vpn = None

    def _disconnect(self, keep_killswitch=False):
        self._stop_bandwidth_monitor()
        remove_lan_routes()
        self._stop_watchdog()
        self._stop_rotate_timer()
        old_adapter = self.vpn.adapter if self.vpn else None
        if not keep_killswitch and self.killswitch.active:
            self.killswitch.disable()
        elif keep_killswitch and old_adapter:
            self.killswitch.remove_vpn_adapter_allow(old_adapter)
        if self.vpn:
            vpn = self.vpn
            self.connected = False
            self.vpn = None
            try:
                vpn.disconnect()
            except Exception as e:
                log(f"Disconnect error: {e}")
        self._cleanup_orphans()
        self._append_log("Disconnected")
        self._update_state()

    def _start_watchdog(self):
        self._stop_watchdog()

        def watch():
            while self.connected and self.vpn:
                ok = self.vpn.check()
                if not ok:
                    self.after(0, self._on_vpn_drop)
                    break
                time.sleep(3)

        self.watchdog = threading.Thread(target=watch, daemon=True)
        self.watchdog.start()

    def _stop_watchdog(self):
        self.watchdog = None

    def _on_vpn_drop(self):
        exit_code = "?"
        if self.vpn and self.vpn.process:
            try:
                exit_code = self.vpn.process.poll()
            except:
                pass
        self._append_log(f"WARNING: VPN connection dropped! (exit code: {exit_code})")
        self._stop_rotate_timer()
        self.connected = False
        if self.killswitch.active:
            self.killswitch.disable()
            self._append_log("Killswitch released (VPN dropped)")
        state = self.vpn
        self.vpn = None
        self._update_state()
        if self.recon_var.get() and state and state.config_path.exists():
            self._append_log("Auto-reconnecting...")
            self._connect()

    def _start_rotate_timer(self):
        self._stop_rotate_timer()
        secs = int(self.settings.get("rotate_interval", 30)) * 60

        def tick():
            time.sleep(secs)
            self.after(0, self._rotate_connection)

        self.rotate_timer = threading.Thread(target=tick, daemon=True)
        self.rotate_timer.start()

    def _stop_rotate_timer(self):
        self.rotate_timer = None

    @staticmethod
    def _list_adapters():
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-Command",
                "Get-NetAdapter | Where-Object { $_.Status -eq 'Up' } | Select-Object -ExpandProperty Name"],
                capture_output=True, text=True, timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW)
            return set(line.strip() for line in r.stdout.splitlines() if line.strip())
        except:
            return set()

    def _rotate_connection(self):
        if not self.connected or not self.vpn:
            return
        current = self.config_var.get()
        current_type = self.vpn.vpn_type
        rotate_type = self.settings.get("rotate_type", ROTATE_TYPE_ANY)

        def _candidate_type(name):
            p = self._find_config_path(name)
            return "wg" if p and p.suffix.lower() == ".conf" else "open"

        vals = self._list_configs()
        candidates = []
        for v in vals:
            if v == current or v == "(no configs imported)":
                continue
            if rotate_type != ROTATE_TYPE_ANY:
                ct = _candidate_type(v)
                if rotate_type == "Alternate" and ct == current_type:
                    continue
                if rotate_type == "WG → OpenVPN" and not (current_type == "wg" and ct == "open"):
                    continue
                if rotate_type == "WG → WG" and not (current_type == "wg" and ct == "wg"):
                    continue
                if rotate_type == "OpenVPN → WG" and not (current_type == "open" and ct == "wg"):
                    continue
                if rotate_type == "OpenVPN → OpenVPN" and not (current_type == "open" and ct == "open"):
                    continue
            candidates.append(v)

        if not candidates:
            self._append_log(f"Rotate: no candidate matches type '{rotate_type}' (current: {current_type})")
            return
        chosen = random.choice(candidates)
        chosen_path = self._find_config_path(chosen)
        if not chosen_path:
            self._append_log("Rotate: config not found")
            return

        self._append_log(f"Rotating to {chosen}...")

        # Pre-allow new VPN endpoint IPs through killswitch
        self.temp_rules = []
        if self.ks_var.get():
            ips = resolve_vpn_endpoints(chosen_path)
            for ip in ips:
                safe = ip.replace(".", "_").replace(":", "_")
                self.killswitch.add_temp_allow(safe, ip)
                self.temp_rules.append(safe)

        # Snapshot adapters before starting new VPN
        before = self._list_adapters()
        old_vpn = self.vpn
        old_adapter = old_vpn.adapter if old_vpn else None

        ext = chosen_path.suffix.lower()
        try:
            if ext == ".conf":
                new_vpn = WireGuardConnection(chosen_path)
            elif ext == ".ovpn":
                new_vpn = OpenVPNConnection(chosen_path)
            else:
                self.killswitch.remove_all_temp_allows()
                return

            self._append_log(f"Establishing {new_vpn.name} alongside {old_vpn.name}...")
            new_vpn.connect()
        except Exception as e:
            self._append_log(f"Rotate: new VPN failed: {e}")
            self._append_log("Staying on current connection until next rotation tick")
            self.killswitch.remove_all_temp_allows()
            self.temp_rules = []
            return

        # Detect new adapter: prefer snapshot diff, fall back to VPN detection
        after = self._list_adapters()
        new_adapters = after - before
        new_adapter = None
        if len(new_adapters) == 1:
            new_adapter = next(iter(new_adapters))
            log(f"Rotate: detected adapter via diff: {new_adapter}")
        elif new_vpn.adapter in new_adapters:
            new_adapter = new_vpn.adapter
        else:
            new_adapter = new_vpn.adapter

        same_adapter = old_adapter and new_adapter and old_adapter == new_adapter

        if same_adapter:
            self._append_log("New VPN shares the same adapter (DCO) — staying on current connection")
            try:
                new_vpn.disconnect()
            except:
                pass
            self.killswitch.remove_all_temp_allows()
            self.temp_rules = []
            return

        # Allow new adapter through killswitch immediately (before old VPN stops)
        if self.ks_var.get() and new_adapter:
            self.killswitch.allow_vpn_adapter(new_adapter)
            self._append_log(f"Allowed {new_adapter} through killswitch")

        # Promote new adapter metric FIRST so it wins traffic before old VPN stops
        if new_adapter:
            subprocess.run(["powershell", "-NoProfile", "-Command",
                f"Set-NetIPInterface -InterfaceAlias '{new_adapter}' -InterfaceMetric 1"],
                capture_output=True, timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW)
            self._append_log(f"Promoted {new_adapter} metric to 1")

        time.sleep(2)  # route convergence after promotion

        # Switch state to new VPN BEFORE disconnecting old one.
        # This eliminates a race with the watchdog thread — the watchdog
        # always finds self.vpn pointing to a healthy connection.
        self.vpn = new_vpn
        self._set_config_name(chosen)

        # Disconnect old VPN — new adapter already has the lowest metric
        # For WireGuard, keep the adapter to avoid DCO kernel driver crash
        try:
            if old_vpn.vpn_type == "wg":
                old_vpn.disconnect(keep_adapter=True)
            else:
                old_vpn.disconnect()
        except Exception as e:
            log(f"Rotate: old VPN disconnect error: {e}")

        # Old adapter rule is no longer needed (tunnel stopped)
        if self.ks_var.get() and old_adapter and old_adapter != new_adapter:
            self.killswitch.remove_vpn_adapter_allow(old_adapter)

        self.killswitch.remove_all_temp_allows()
        self.temp_rules = []

        self._append_log(f"Rotated to {chosen}")

    def _finish_rotate(self, chosen):
        self._set_config_name(chosen)
        self._connect()

    def _find_config_path(self, name):
        for d in [VPN_CONFIGS_DIR]:
            cfg_dir = self.settings.get("config_dir", "")
            if cfg_dir:
                d2 = Path(cfg_dir)
                if d2.is_dir():
                    d = d2
            p = d / name
            if p.exists():
                return p
        return None

    def _on_rotate_interval_set(self):
        raw = self.rotate_interval_var.get().strip()
        try:
            val = int(raw)
            if val < 1:
                raise ValueError
        except ValueError:
            self._error_dialog("Error", "Enter a number ≥ 1 (minutes)")
            return
        self.settings["rotate_interval"] = val
        self._save_settings()
        self._append_log(f"Rotate interval set to {val} min")
        if self.connected and self.rotate_var.get():
            self._start_rotate_timer()

    def _on_rotate_toggle(self):
        val = self.rotate_var.get()
        self.settings["rotate_enabled"] = val
        self._save_settings()
        if val and self.connected:
            self._start_rotate_timer()
        else:
            self._stop_rotate_timer()

    def _on_rotate_type_set(self, choice):
        self.settings["rotate_type"] = choice
        self._save_settings()
        self._append_log(f"Rotate type set to {choice}")

    def _on_ks_toggle(self):
        self.settings["killswitch_on_connect"] = self.ks_var.get()
        self._save_settings()

    def _on_recon_toggle(self):
        self.settings["reconnect_on_drop"] = self.recon_var.get()
        self._save_settings()

    def _set_auto_start(self, enable):
        if SYSTEM != "Windows":
            return
        startup = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        startup.mkdir(parents=True, exist_ok=True)
        link = startup / "TorGuardLite.lnk"
        vbs = startup / "TorGuardLite.vbs"
        if enable:
            script = f'''CreateObject("WScript.Shell").Run ""{sys.executable}" "{Path(sys.argv[0]).resolve()}"", 0, False
'''
            vbs.write_text(script)
            log(f"Auto-start enabled: {vbs}")
        else:
            if link.exists():
                link.unlink()
            if vbs.exists():
                vbs.unlink()
            log("Auto-start disabled")

    def _on_auto_toggle(self):
        val = self.auto_var.get()
        self.settings["auto_start"] = val
        self._save_settings()
        self._set_auto_start(val)

    def _cleanup_orphans(self):
        if SYSTEM != "Windows":
            return
        subprocess.run(["taskkill", "/F", "/IM", "openvpn.exe"],
                       capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        time.sleep(1)
        subprocess.run(["netsh", "interface", "set", "interface",
                        "name=OpenVPN Data Channel Offload", "admin=disabled"],
                       capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        time.sleep(1)
        subprocess.run(["netsh", "interface", "set", "interface",
                        "name=OpenVPN Data Channel Offload", "admin=enabled"],
                       capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)

    def _make_tray_image(self):
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([4, 4, 60, 60], fill="#22c55e")
        draw.text((18, 14), "TG", fill="white",
                  font=None, anchor=None)
        return img

    def _build_tray(self):
        if self.tray_icon:
            return
        menu = pystray.Menu(
            pystray.MenuItem("Show", self._show_window, default=True),
            pystray.MenuItem("Quit", self._quit_app),
        )
        self.tray_icon = pystray.Icon(
            "torguard_lite", self._make_tray_image(),
            "TorGuard Lite", menu
        )
        t = threading.Thread(target=self.tray_icon.run, daemon=True)
        t.start()
        self._tray_ready.set()

    def _on_minimize(self, event=None):
        if event and getattr(event, "widget", None) is not self:
            return
        self._hide_to_tray()

    def _hide_to_tray(self):
        self.withdraw()
        if not self.tray_icon:
            self._build_tray()

    def _show_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def _quit_app(self):
        if self.tray_icon:
            self.tray_icon.stop()
            self.tray_icon = None
        if self.connected:
            self._disconnect()
        self.destroy()

    def on_close(self):
        self._hide_to_tray()


if __name__ == "__main__":
    # Ensure clean killswitch state on crash
    if SYSTEM == "Windows":
        try:
            r = subprocess.run(["netsh", "advfirewall", "firewall", "show", "rule",
                                "name=TorGuardLite_BlockAll"], capture_output=True, text=True, shell=True)
            if r.returncode == 0:
                print("Cleaning up orphaned killswitch rules from previous session...")
                subprocess.run(["netsh", "advfirewall", "firewall", "delete", "rule",
                                "name=TorGuardLite_BlockAll"], capture_output=True, shell=True)
                subprocess.run(["netsh", "advfirewall", "firewall", "delete", "rule",
                                "name=TorGuardLite_AllowLAN"], capture_output=True, shell=True)
                subprocess.run(["netsh", "advfirewall", "firewall", "delete", "rule",
                                "name=TorGuardLite_AllowDHCP"], capture_output=True, shell=True)
                subprocess.run(["netsh", "advfirewall", "firewall", "delete", "rule",
                                "name=TorGuardLite_AllowDNS"], capture_output=True, shell=True)
                subprocess.run(["netsh", "advfirewall", "firewall", "delete", "rule",
                                "name=TorGuardLite_AllowVPN_"], capture_output=True, shell=True)
                subprocess.run(["netsh", "advfirewall", "firewall", "delete", "rule",
                                "name=TorGuardLite_Temp_"], capture_output=True, shell=True)
        except:
            pass
        try:
            out = subprocess.run(["powershell", "-Command",
                "Get-Service 'WireGuardTunnel*' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name"],
                capture_output=True, text=True, shell=True)
            if out.returncode == 0:
                for svc in out.stdout.strip().splitlines():
                    svc = svc.strip()
                    if svc:
                        print(f"Cleaning up orphaned tunnel: {svc}")
                        subprocess.run(["sc", "config", svc, "start=disabled"], capture_output=True, shell=True)
                        subprocess.run(["net", "stop", svc], capture_output=True, shell=True)
                        tunnel_name = svc.split("$", 1)[-1] if "$" in svc else ""
                        if tunnel_name:
                            wg_dir = find_wireguard()
                            if wg_dir:
                                subprocess.run([str(Path(wg_dir) / "wireguard.exe"),
                                                "/uninstalltunnelservice", tunnel_name],
                                               capture_output=True, shell=True)
        except Exception as e:
            print(f"WireGuard tunnel cleanup error: {e}")
    app = TorGuardLite()
    app.mainloop()
