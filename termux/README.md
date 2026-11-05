# PhantomDroid — Termux Edition

Roda direto no Termux, sem precisar compilar APK.

## Instalação (1x)

```bash
# 1. Instale dependências no Termux
pkg update && pkg install python termux-api git

# 2. Instale Flask
pip install flask

# 3. Instale o app "Termux:API" na Play Store
#    (necessário para IR e WiFi scan)
```

## Como rodar

```bash
# Baixe os arquivos (ou clone o repo)
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
║  http://localhost:8080               ║
╚══════════════════════════════════════╝
```

Abra o navegador e acesse o IP mostrado na porta 8080.

## Funcionalidades

| Recurso | Requer |
|---|---|
| IR Remote — presets Samsung/LG/Sony/Philips | Termux:API + hardware IR |
| IR Remote — código manual | Termux:API + hardware IR |
| WiFi Scanner | Termux:API |
| Evil Twin AP | Root + hostapd + dnsmasq |
| BT Scanner | bluetoothctl |
| BT L2CAP Flood (Deauth) | Bluetooth ativo |

## Parar o servidor

`Ctrl + C` no terminal Termux.
