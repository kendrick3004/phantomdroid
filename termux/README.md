# PhantomDroid — Termux Edition

Roda direto no Termux, sem precisar compilar APK.

---

## ⚠️ IMPORTANTE — Instale pelo F-Droid, NÃO pela Play Store

O Termux e o Termux:API da **Play Store estão quebrados/desatualizados**.
Instale as versões corretas pelo **F-Droid**:

| App | Link F-Droid |
|---|---|
| **Termux** | https://f-droid.org/packages/com.termux/ |
| **Termux:API** | https://f-droid.org/packages/com.termux.api/ |

> Se já tiver Termux da Play Store, **desinstale** e reinstale pelo F-Droid.

---

## Instalação (1x)

```bash
# 1. Dentro do Termux (F-Droid), instale as dependências
pkg update && pkg install python termux-api bluez

# 2. Instale Flask
pip install flask

# 3. No Android — Configurações > Apps > Termux > Permissões:
#    ✅ Localização (necessário para WiFi scan)
#    ✅ Bluetooth (necessário para BT scan)
```

---

## Como rodar

```bash
# Clone o repositório
git clone https://github.com/kendrick3004/phantomdroid.git
cd phantomdroid/termux

# Rode o servidor
python server.py
```

Aparece no terminal:
```
╔══════════════════════════════════════╗
║       PhantomDroid - Termux          ║
╠══════════════════════════════════════╣
║  Acesse no navegador:                ║
║  http://192.168.1.X:8080             ║
╚══════════════════════════════════════╝
```

Abra o navegador no celular e acesse o IP mostrado na porta **8080**.
Pode acessar de outro dispositivo na mesma rede WiFi também.

---

## Funcionalidades

| Recurso | Requer |
|---|---|
| IR Remote — presets Samsung/LG/Sony/Philips | Termux:API (F-Droid) + hardware IR |
| IR Remote — código manual | Termux:API (F-Droid) + hardware IR |
| WiFi Scanner (via Termux:API) | Termux:API (F-Droid) + permissão Localização |
| WiFi Scanner (via wpa_cli) | Funciona sem Termux:API (fallback automático) |
| Evil Twin AP | Root + hostapd + dnsmasq |
| BT Scanner | bluez (`pkg install bluez`) |
| BT L2CAP Flood (Deauth) | Bluetooth ativo |

---

## Atualizar

```bash
cd phantomdroid
git pull
python termux/server.py
```

## Parar

`Ctrl + C` no terminal Termux.
