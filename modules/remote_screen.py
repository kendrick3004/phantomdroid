"""
PhantomDroid — Remote Android Screen Module
Visualiza a tela do Android em tempo real via ADB + servidor HTTP com MJPEG.
Não requer app externo no celular — usa apenas ADB (screencap nativo).
Author: Mr. Psycho | @the_psycho_of_hackers
"""

import subprocess
import threading
import socket
import random
import time
import io
from rich.console import Console
from rich.panel import Panel
from rich import box

console = Console()

# ── Captura de frame via ADB ──────────────────────────────────────────────────

def _capture_frame_raw(device_id: str = None) -> bytes | None:
    """Captura um PNG da tela via 'adb shell screencap -p' e retorna os bytes."""
    cmd = ["adb"]
    if device_id:
        cmd += ["-s", device_id]
    cmd += ["shell", "screencap", "-p"]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=8)
        data = result.stdout
        if not data or len(data) < 100:
            return None
        # Windows: ADB converte \r\n → \n, corrigir bytes PNG
        data = data.replace(b"\r\n", b"\n")
        return data
    except Exception:
        return None


# ── Servidor MJPEG ────────────────────────────────────────────────────────────

BOUNDARY = b"--phantomframe"

_latest_frame: bytes = b""
_frame_lock = threading.Lock()
_server_running = False


def _frame_producer(device_id: str, fps: int):
    """Thread: captura frames continuamente e atualiza _latest_frame."""
    global _latest_frame, _server_running
    delay = 1.0 / max(1, fps)
    while _server_running:
        frame = _capture_frame_raw(device_id)
        if frame:
            with _frame_lock:
                _latest_frame = frame
        time.sleep(delay)


class _MJPEGHandler:
    """Handler HTTP manual (sem BaseHTTPRequestHandler para suportar streaming)."""

    def __init__(self, conn: socket.socket, addr, local_ip: str, http_port: int):
        self.conn = conn
        self.addr = addr
        self.local_ip = local_ip
        self.http_port = http_port

    def handle(self):
        try:
            raw = self.conn.recv(2048).decode("utf-8", errors="ignore")
            path = ""
            if raw:
                first = raw.splitlines()[0]
                parts = first.split()
                if len(parts) >= 2:
                    path = parts[1]

            if path == "/stream":
                self._stream()
            else:
                self._index()
        except Exception:
            pass
        finally:
            try:
                self.conn.close()
            except Exception:
                pass

    def _send(self, data: bytes):
        self.conn.sendall(data)

    def _index(self):
        """Página HTML com o player de tela."""
        html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PhantomDroid — Tela Remota</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #0d0d1a; color: #e0e0ff; font-family: Arial, sans-serif;
         display: flex; flex-direction: column; align-items: center; min-height: 100vh; padding: 16px; }}
  h1 {{ color: #cc44ff; margin-bottom: 12px; font-size: 1.4em; text-align: center; }}
  #screen {{ max-width: 100%; max-height: 85vh; border: 2px solid #cc44ff;
             border-radius: 10px; box-shadow: 0 0 24px #cc44ff66; }}
  .info {{ margin-top: 10px; color: #888; font-size: 0.8em; }}
  .badge {{ display:inline-block; background:#1a0033; border:1px solid #cc44ff;
            padding:3px 10px; border-radius:20px; color:#cc44ff; margin:4px; font-size:0.8em; }}
</style>
</head>
<body>
<h1>👻 PhantomDroid &nbsp;—&nbsp; Tela Remota</h1>
<img id="screen" src="/stream" alt="Tela do Android">
<div class="info">
  <span class="badge">📡 MJPEG Stream</span>
  <span class="badge">🔗 {self.local_ip}:{self.http_port}</span>
  <span class="badge">⚠ Apenas uso autorizado</span>
</div>
</body>
</html>"""
        body = html.encode("utf-8")
        header = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/html; charset=utf-8\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n\r\n"
        ).encode()
        self._send(header + body)

    def _stream(self):
        """Stream MJPEG contínuo."""
        header = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: multipart/x-mixed-replace; boundary=phantomframe\r\n"
            "Cache-Control: no-cache\r\n"
            "Connection: keep-alive\r\n\r\n"
        ).encode()
        self._send(header)

        while _server_running:
            with _frame_lock:
                frame = _latest_frame

            if frame:
                chunk = (
                    BOUNDARY + b"\r\n"
                    b"Content-Type: image/png\r\n"
                    + f"Content-Length: {len(frame)}\r\n\r\n".encode()
                    + frame + b"\r\n"
                )
                try:
                    self._send(chunk)
                except Exception:
                    break
            time.sleep(0.1)


def _accept_loop(server_sock: socket.socket, local_ip: str, http_port: int):
    """Aceita conexões e despacha handlers."""
    server_sock.settimeout(1.0)
    while _server_running:
        try:
            conn, addr = server_sock.accept()
            h = _MJPEGHandler(conn, addr, local_ip, http_port)
            t = threading.Thread(target=h.handle, daemon=True)
            t.start()
        except socket.timeout:
            continue
        except Exception:
            break


# ── QR Code ───────────────────────────────────────────────────────────────────

def _print_qr(url: str):
    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.make(fit=True)
        qr.print_ascii(invert=True)
    except ImportError:
        console.print("[yellow]⚠ 'qrcode' não instalado. pip install 'qrcode[terminal]'[/]")
        console.print(f"[bold cyan]Acesse manualmente:[/] {url}")


# ── IP local ──────────────────────────────────────────────────────────────────

def _get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# ── Função principal ──────────────────────────────────────────────────────────

def remote_screen(device_id: str = None, fps: int = 3, port: int = None):
    """
    Inicia um servidor MJPEG local e exibe a tela do Android em tempo real.
    Abrir no navegador (PC ou celular na mesma rede).
    - device_id : serial ADB do dispositivo (None = auto)
    - fps       : frames por segundo (1–10 recomendado; ADB é lento)
    - port      : porta HTTP (None = aleatória entre 8800–8899)
    """
    global _server_running, _latest_frame

    local_ip = _get_local_ip()
    http_port = port or random.randint(8800, 8899)
    url = f"http://{local_ip}:{http_port}"

    console.rule("[bold magenta]🖥️  Remote Android Screen[/]")

    # Captura um frame teste para verificar conexão ADB
    console.print("[cyan]Verificando conexão ADB e capturando frame de teste...[/]")
    test_frame = _capture_frame_raw(device_id)
    if not test_frame:
        console.print(
            "[bold red]✗ Falha ao capturar tela.[/]\n"
            "[yellow]Verifique se o dispositivo está conectado via ADB "
            "(USB ou Wi-Fi) e com depuração USB/Wi-Fi ativa.[/]"
        )
        return

    console.print("[green]✓ Frame capturado! Iniciando servidor de stream...[/]")

    # Inicia servidor TCP
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server_sock.bind(("0.0.0.0", http_port))
        server_sock.listen(5)
    except OSError as e:
        console.print(f"[bold red]✗ Não foi possível iniciar servidor na porta {http_port}:[/] {e}")
        return

    _latest_frame = test_frame
    _server_running = True

    # Thread: produtor de frames
    producer = threading.Thread(target=_frame_producer, args=(device_id, fps), daemon=True)
    producer.start()

    # Thread: aceitador de conexões HTTP
    acceptor = threading.Thread(target=_accept_loop, args=(server_sock, local_ip, http_port), daemon=True)
    acceptor.start()

    console.print(Panel(
        f"[bold green]✓ Servidor de tela remota ativo![/]\n\n"
        f"[bold cyan]Acesse no navegador:[/] [bold white]{url}[/]\n"
        f"[bold cyan]FPS:[/] {fps}  |  "
        f"[bold cyan]Dispositivo:[/] {device_id or 'auto'}\n\n"
        "[dim]Escaneie o QR Code abaixo com o celular para ver a tela "
        "em outro dispositivo na mesma rede.[/]\n"
        "[bold red]Pressione Ctrl+C para encerrar o stream.[/]",
        title="[bold magenta]🖥️  Remote Screen[/]",
        border_style="magenta",
        box=box.DOUBLE_EDGE,
        padding=(1, 2)
    ))

    _print_qr(url)

    console.print(f"\n[dim]Stream em: {url}/stream[/]")
    console.print("[dim]Aguardando conexões... (Ctrl+C para parar)[/]\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        _server_running = False
        try:
            server_sock.close()
        except Exception:
            pass
        console.print("\n[bold magenta]✓ Stream encerrado.[/]")
