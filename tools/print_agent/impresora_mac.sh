#!/bin/bash
# Atlas POS - Agente Local de Impresión para macOS
# Requiere: Python 3.10+, CUPS (incluido en macOS)
set -e
AGENT_DIR="$(cd "$(dirname "$0")" && pwd)"
CORE_DIR="$AGENT_DIR/core"
cd "$AGENT_DIR"

cat << 'EOF'

╭────────────────────────────────────────────────────────╮
│ ✦ ATLAS TECH × RMAZH                                   │
│ Agente Local de Impresión                              │
╰────────────────────────────────────────────────────────╯

 █████╗ ████████╗██╗      █████╗ ███████╗
██╔══██╗╚══██╔══╝██║     ██╔══██╗██╔════╝
███████║   ██║   ██║     ███████║███████╗
██╔══██║   ██║   ██║     ██╔══██║╚════██║
██║  ██║   ██║   ███████╗██║  ██║███████║
╚═╝  ╚═╝   ╚═╝   ╚══════╝╚═╝  ╚═╝╚══════╝

         RMAZH POS - AGENTE LOCAL DE IMPRESION
         macOS — Conectando tu computadora con tu impresora

──────────────────────────────────────────────────────────
EOF
echo

# ── 0. ¿Ya está instalado como servicio? ─────────────────────────────────────
# En las Macs ya convertidas al autoarranque, la cajera va a seguir buscando
# este archivo y abriéndolo por costumbre durante semanas. Sin esta guarda
# vería un error de puerto ocupado y levantaría el teléfono. Con ella ve que
# todo está bien y cierra la ventana.
#
# En las Macs NO convertidas la condición es falsa y el script sigue haciendo
# exactamente lo de siempre.
if launchctl print "gui/$(id -u)/com.atlasone.print-agent" >/dev/null 2>&1; then
    cat << 'EOF'

 ╭────────────────────────────────────────────────────────╮
 │  El agente YA ESTA ACTIVO                              │
 ╰────────────────────────────────────────────────────────╯

 Esta Mac ya arranca el agente sola al iniciar sesion.
 No necesitas abrir nada: abre el navegador y vende normal.

 Puedes cerrar esta ventana.

EOF
    read -r -t 60 -p " Presiona ENTER para cerrar… " _ || true
    echo
    exit 0
fi

echo "[INICIO]  Iniciando agente de impresion..."
# Verificar Python 3
if ! command -v python3 &>/dev/null; then
    echo "[ERROR] Python3 no encontrado."
    echo "        Instala las Xcode Command Line Tools: xcode-select --install"
    echo "        O instala Python desde https://python.org"
    exit 1
fi
echo "[OK]      Python detectado correctamente."

# macOS incluye CUPS nativo — verificar que lp está disponible
if ! command -v lp &>/dev/null; then
    echo "[NOTA]    lp no encontrado. Intenta: sudo launchctl load -w /System/Library/LaunchDaemons/org.cups.cupsd.plist"
fi

# Crear entorno virtual si no existe
VENV_DIR="$CORE_DIR/venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "[INFO]    Preparando entorno local..."
    python3 -m venv "$VENV_DIR"
fi

# Activar entorno virtual
source "$VENV_DIR/bin/activate"

# Instalar / actualizar dependencias
echo "[INFO]    Instalando dependencias..."
pip install --quiet --upgrade pip
pip install --quiet -r "$CORE_DIR/requirements_mac.txt"

# Generar certificados SSL si no existen
if [ ! -f "$CORE_DIR/certs/cert.pem" ]; then
    echo "[INFO]    Preparando certificado local SSL..."
    python3 "$CORE_DIR/generate_cert.py"
fi
echo "[OK]      Certificado listo."

echo ""
echo "[LISTO]   El agente de impresion esta funcionando."
echo "[LISTO]   Tu computadora ya puede enviar tickets a la impresora."
echo ""
echo "[NOTA]    Primera vez: abre https://127.0.0.1:9100/health en Safari/Chrome"
echo "[NOTA]    y acepta el aviso de certificado antes de usar el POS."
echo "[NOTA]    No cierres esta ventana Terminal."
echo ""

# Auto-restart loop
while true; do
    python3 "$CORE_DIR/main.py" || true
    echo ""
    echo "[AVISO]   El agente se detuvo. Reiniciando en 5 segundos... (Ctrl+C para salir)"
    sleep 5
done
