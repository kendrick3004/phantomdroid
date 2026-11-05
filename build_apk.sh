#!/bin/bash
# ╔══════════════════════════════════════════════════════╗
# ║   PhantomDroid — Build APK (Corrigido)              ║
# ║   Execute: bash build_apk.sh                        ║
# ╚══════════════════════════════════════════════════════╝

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'
YELLOW='\033[1;33m'; BOLD='\033[1m'; NC='\033[0m'

step() { echo -e "\n${CYAN}${BOLD}[*] $1${NC}"; }
ok()   { echo -e "${GREEN}[✓] $1${NC}"; }
warn() { echo -e "${YELLOW}[!] $1${NC}"; }
err()  { echo -e "${RED}[✗] $1${NC}"; exit 1; }

# ── Pasta de saída dos APKs ───────────────────────────────────────────────────
BUILD_DIR="$(dirname "$0")/builds"
mkdir -p "$BUILD_DIR"
ok "Pasta de builds: $BUILD_DIR"

# ── 1. Atualiza lista de pacotes ──────────────────────────────────────────────
step "Atualizando lista de pacotes..."
sudo apt-get update -y
ok "Lista atualizada"

# ── 2. Dependências do sistema ────────────────────────────────────────────────
step "Instalando dependências do sistema (--fix-missing)..."
sudo apt-get install -y --fix-missing \
  python3-pip python3-full python3-dev \
  build-essential git \
  ffmpeg \
  libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev \
  libportmidi-dev \
  libswscale-dev libavformat-dev libavcodec-dev \
  zlib1g-dev \
  openjdk-17-jdk \
  unzip autoconf libtool pkg-config cmake \
  libffi-dev libssl-dev
ok "Dependências do sistema instaladas"

# ── 3. Buildozer em ambiente virtual (evita erro externally-managed) ──────────
step "Criando ambiente virtual Python para o build..."
VENV_DIR="$HOME/.phantom_build_venv"

if [ ! -d "$VENV_DIR" ]; then
  python3 -m venv "$VENV_DIR"
  ok "Venv criado em $VENV_DIR"
else
  ok "Venv já existe, reutilizando"
fi

# Ativa o venv
source "$VENV_DIR/bin/activate"

step "Instalando buildozer e cython no venv..."
pip install --upgrade pip setuptools wheel
pip install buildozer cython
ok "Buildozer instalado"

# ── 4. Compila o APK ──────────────────────────────────────────────────────────
step "Compilando APK... (pode demorar 20-40 min na 1ª vez)"
warn "Baixando Android SDK/NDK automaticamente se necessário"

cd "$(dirname "$0")"
buildozer android debug 2>&1 | tee "$BUILD_DIR/build_$(date +%Y%m%d_%H%M%S).log"

# ── 5. Copia APK para pasta builds/ ──────────────────────────────────────────
step "Procurando APK gerado..."
APK_SRC=$(find bin/ -name "*.apk" 2>/dev/null | sort | tail -1)

if [ -z "$APK_SRC" ]; then
  err "APK não encontrado em bin/. Veja o log em $BUILD_DIR/"
fi

# Nome com timestamp para não sobrescrever builds anteriores
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
APK_NAME="PhantomDroid_${TIMESTAMP}.apk"
cp "$APK_SRC" "$BUILD_DIR/$APK_NAME"

ok "APK copiado para: $BUILD_DIR/$APK_NAME"

# Cria também um link 'latest' para facilitar
ln -sf "$BUILD_DIR/$APK_NAME" "$BUILD_DIR/PhantomDroid_latest.apk"
ok "Link atualizado: builds/PhantomDroid_latest.apk"

# ── 6. Resumo ─────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}${BOLD}║   ✓  BUILD CONCLUÍDO!                       ║${NC}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BOLD}APK:${NC}      $BUILD_DIR/$APK_NAME"
echo -e "  ${BOLD}Latest:${NC}   $BUILD_DIR/PhantomDroid_latest.apk"
echo ""
echo -e "${CYAN}  Instalar via ADB:${NC}"
echo -e "  adb install \"$BUILD_DIR/PhantomDroid_latest.apk\""
echo ""
echo -e "${CYAN}  Builds anteriores em:${NC} $BUILD_DIR/"
ls -lh "$BUILD_DIR/"*.apk 2>/dev/null
echo ""

deactivate
