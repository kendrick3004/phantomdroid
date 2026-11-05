"""
PhantomDroid — LAN QR Connect Module
Conecta ao dispositivo Android via Wi-Fi local usando QR Code no terminal.
Funciona sem ativar o modo desenvolvedor manualmente (Android 11+).
Author: Mr. Psycho | @the_psycho_of_hackers
"""

import socket
import threading
import http.server
import urllib.parse
import time
import os
import random
import subprocess
from rich.console import Console
from rich.panel import Panel
from rich.align import Align
from rich import box

console = Console()

# ── Detectar IP local do PC ──────────────────────────────────────────────────

def get_local_ip() -> str:
    """Retorna o IP do PC na rede local Wi-Fi."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

# ── Página HTML servida ao celular ───────────────────────────────────────────

GUIDE_HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PhantomDroid — Conectar via Wi-Fi</title>
<style>
  body {{ font-family: Arial, sans-serif; background: #0d0d1a; color: #e0e0ff; padding: 20px; max-width: 500px; margin: auto; }}
  h1 {{ color: #cc44ff; text-align: center; }}
  .step {{ background: #1a0033; border-left: 4px solid #cc44ff; padding: 12px 16px; margin: 12px 0; border-radius: 6px; }}
  .step span {{ font-size: 1.3em; font-weight: bold; color: #cc44ff; }}
  code {{ background: #2a0044; padding: 2px 7px; border-radius: 4px; color: #ff88ff; font-size: 0.95em; }}
  .warn {{ color: #ffcc00; font-size: 0.9em; margin-top: 20px; text-align: center; }}
  .cmd {{ background: #111; color: #00ff88; padding: 10px; border-radius: 6px; font-family: monospace; word-break: break-all; text-align: center; margin: 10px 0; }}
</style>
</head>
<body>
<h1>👻 PhantomDroid<br><small style="font-size:0.5em;color:#aaa;">Conexão Wi-Fi via QR Code</small></h1>

<div class="step"><span>1.</span> Abra <strong>Configurações</strong> no seu Android</div>
<div class="step"><span>2.</span> Vá em <strong>Sobre o telefone</strong> → toque <strong>7 vezes</strong> em <code>Número da versão</code></div>
<div class="step"><span>3.</span> Volte e abra <strong>Opções do desenvolvedor</strong></div>
<div class="step"><span>4.</span> Ative <strong>Depuração por Wi-Fi</strong> (Wireless debugging)</div>
<div class="step"><span>5.</span> Toque em <strong>Parear dispositivo com código QR</strong> ou anote o <strong>IP e porta</strong> mostrados</div>
<div class="step"><span>6.</span> No PC, execute:<br>
  <div class="cmd">adb connect {ip}:{port}</div>
</div>

<p style="text-align:center;color:#88ff88;font-size:1.1em;">✅ Após conectar, volte ao PhantomDroid!</p>
<p class="warn">⚠ Use apenas em redes confiáveis e com autorização.</p>
</body>
</html>"""

# ── Servidor HTTP simples ─────────────────────────────────────────────────────

class _QRHandler(http.server.BaseHTTPRequestHandler):
    local_ip: str = "127.0.0.1"
    local_port: int = 5555

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        html = GUIDE_HTML.format(ip=self.local_ip, port=self.local_port)
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, *args):
        pass  # Silencia logs do servidor


def _start_server(http_port: int, adb_port: int, ip: str):
    """Inicia o servidor HTTP em thread separada."""
    _QRHandler.local_ip = ip
    _QRHandler.local_port = adb_port
    server = http.server.HTTPServer(("0.0.0.0", http_port), _QRHandler)
    server.timeout = 120  # 2 minutos de vida
    server.handle_request()  # atende uma única requisição
    server.server_close()

# ── QR Code no terminal ───────────────────────────────────────────────────────

def _print_qr(url: str):
    """Gera e imprime QR Code no terminal."""
    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.make(fit=True)
        # Imprime no terminal em ASCII
        qr.print_ascii(invert=True)
    except ImportError:
        console.print("[yellow]⚠ 'qrcode' não instalado. Execute: pip install 'qrcode[terminal]'[/]")
        console.print(f"[bold cyan]URL manual:[/] {url}")

# ── Função principal exportada ────────────────────────────────────────────────

def lan_qr_connect(adb_port: int = 5555):
    """
    Exibe QR Code no terminal. O celular escaneia, abre a página com
    instruções e o usuário conecta via ADB Wi-Fi sem precisar ativar
    o modo desenvolvedor antecipadamente.
    """
    local_ip = get_local_ip()
    http_port = random.randint(8700, 8799)
    url = f"http://{local_ip}:{http_port}"

    console.rule("[bold magenta]📡 Conexão LAN via QR Code[/]")
    console.print(Panel(
        f"[white]Escaneie o QR Code com a câmera do celular.\n"
        f"Ele abrirá as instruções para conectar via Wi-Fi.\n\n"
        f"[bold cyan]URL:[/] {url}\n"
        f"[bold cyan]IP do PC:[/] {local_ip}  |  [bold cyan]Porta ADB:[/] {adb_port}[/]",
        title="[bold magenta]📱 Escaneie com o celular[/]",
        border_style="magenta",
        box=box.DOUBLE_EDGE,
        padding=(1, 2)
    ))

    # Inicia servidor em background
    t = threading.Thread(target=_start_server, args=(http_port, adb_port, local_ip), daemon=True)
    t.start()

    # Exibe QR Code
    _print_qr(url)

    console.print(f"\n[dim]Aguardando acesso do celular em {url} ...[/]")
    t.join(timeout=120)

    # Tenta conectar via ADB
    console.print(f"\n[cyan]Tentando adb connect {local_ip}:{adb_port} ...[/]")
    try:
        result = subprocess.run(
            ["adb", "connect", f"{local_ip}:{adb_port}"],
            capture_output=True, text=True, timeout=10
        )
        out = result.stdout.strip()
        if "connected" in out.lower():
            console.print(f"[bold green]✓ Conectado![/] {out}")
            return f"{local_ip}:{adb_port}"
        else:
            console.print(f"[yellow]⚠ Resposta ADB:[/] {out or result.stderr.strip()}")
            console.print("[dim]Se ainda não conectou, execute manualmente: "
                          f"adb connect {local_ip}:{adb_port}[/]")
            return None
    except Exception as e:
        console.print(f"[yellow]⚠ Erro ao executar adb:[/] {e}")
        console.print("[dim]Se ainda não conectou, execute manualmente: "
                      f"adb connect {local_ip}:{adb_port}[/]")
        return None
