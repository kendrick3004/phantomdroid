#!/data/data/com.termux/files/usr/bin/bash
# ╔══════════════════════════════════════════════════════╗
# ║   PhantomDroid — Instalador Termux                  ║
# ║   Execute: bash install_termux.sh                   ║
# ╚══════════════════════════════════════════════════════╝

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'
YELLOW='\033[1;33m'; MAGENTA='\033[0;35m'; BOLD='\033[1m'; NC='\033[0m'

banner() {
  clear
  echo -e "${MAGENTA}${BOLD}"
  echo "  ____  _           _                    ____            _     __"
  echo " |  _ \| |__   __ _| |_ ___  _ __ ___  |  _ \ _ __ ___ (_) __| |"
  echo " | |_) | '_ \ / _\` | __/ _ \| '_ \` _ \ | | | | '__/ _ \| |/ _\` |"
  echo " |  __/| | | | (_| | || (_) | | | | | || |_| | | | (_) | | (_| |"
  echo " |_|   |_| |_|\__,_|\__\___/|_| |_| |_||____/|_|  \___/|_|\__,_|"
  echo -e "${NC}"
  echo -e "${CYAN}  Instalador Termux — Advanced Android Pentesting Framework${NC}"
  echo -e "${RED}  ⚠  Apenas para uso autorizado em pentest${NC}"
  echo ""
}

step() { echo -e "\n${CYAN}${BOLD}[*] $1${NC}"; }
ok()   { echo -e "${GREEN}[✓] $1${NC}"; }
warn() { echo -e "${YELLOW}[!] $1${NC}"; }
err()  { echo -e "${RED}[✗] $1${NC}"; }

banner

# ── Verifica se é Termux ──────────────────────────────────────────────────────
if [ ! -d "/data/data/com.termux" ]; then
  err "Este script deve ser executado no Termux!"
  exit 1
fi

step "Atualizando pacotes..."
pkg update -y && pkg upgrade -y
ok "Pacotes atualizados"

step "Instalando dependências do sistema..."
pkg install -y python git curl wget openssl-dev libffi-dev
ok "Dependências do sistema instaladas"

step "Instalando ferramentas ADB..."
pkg install -y android-tools
ok "ADB instalado"

step "Instalando Termux:API (para IR, WiFi, etc)..."
pkg install -y termux-api
ok "Termux:API instalado"
warn "Instale também o app 'Termux:API' da Play Store/F-Droid para funcionalidades avançadas"

step "Instalando Python e pip..."
pkg install -y python
pip install --upgrade pip
ok "Python pronto"

step "Instalando dependências Python..."
pip install flask flask-socketio rich requests qrcode colorama
ok "Flask e dependências instalados"

# Scapy (opcional — pode falhar em alguns dispositivos)
step "Instalando Scapy (opcional, para WiFi Deauth)..."
pip install scapy 2>/dev/null && ok "Scapy instalado" || warn "Scapy não disponível neste dispositivo (funcionalidades de deauth limitadas)"

step "Configurando acesso ao armazenamento..."
termux-setup-storage 2>/dev/null || warn "Conceda permissão de armazenamento quando solicitado"

step "Configurando permissões..."
chmod +x start.sh 2>/dev/null
chmod +x install_termux.sh

# ── Cria atalho de inicialização ──────────────────────────────────────────────
step "Criando script de inicialização..."
cat > start.sh << 'STARTSCRIPT'
#!/data/data/com.termux/files/usr/bin/bash
cd "$(dirname "$0")"
echo -e "\033[0;35m[*] Iniciando PhantomDroid Web Panel...\033[0m"
python phantomdroid_web.py
STARTSCRIPT
chmod +x start.sh
ok "start.sh criado"

# ── Instala atalho no menu Termux ─────────────────────────────────────────────
mkdir -p ~/.shortcuts
cat > ~/.shortcuts/PhantomDroid << 'SHORTCUT'
#!/data/data/com.termux/files/usr/bin/bash
cd ~/phantomdroid
bash start.sh
SHORTCUT
chmod +x ~/.shortcuts/PhantomDroid 2>/dev/null

echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}${BOLD}║   ✓  INSTALAÇÃO CONCLUÍDA!                  ║${NC}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${CYAN}  Para iniciar:${NC}"
echo -e "  ${BOLD}bash start.sh${NC}  ou  ${BOLD}python phantomdroid_web.py${NC}"
echo ""
echo -e "${CYAN}  Depois abra no navegador:${NC}"
echo -e "  ${BOLD}http://localhost:8080${NC}"
echo ""
echo -e "${YELLOW}  ⚠  Instale 'Termux:API' da F-Droid para IR e WiFi scan${NC}"
echo ""
