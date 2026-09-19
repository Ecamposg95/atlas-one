#!/bin/bash
# Atlas POS — Agente Local de Impresión (Linux)
#
# Un solo ejecutable. Hace todo el setup: CUPS, venv, deps, certs SSL,
# grupo lpadmin, y arranca el agente con auto-restart.
#
# Uso:
#   ./impresora_linux.sh
#
# Requisitos mínimos: Python 3.10+. El resto lo instala el script (pide
# sudo cuando es imprescindible).

set -u
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
         Conectando tu computadora con tu impresora

──────────────────────────────────────────────────────────
 Este agente permite que tu computadora se comunique con
 tu impresora de tickets.

 Atlas POS / RMAZH POS podra enviar tickets desde el navegador
 hacia la impresora termica conectada a esta PC.
──────────────────────────────────────────────────────────

 Servidor local     https://127.0.0.1:9100
 Estado             https://127.0.0.1:9100/health
 Diagnostico        https://127.0.0.1:9100/diagnostics
 Version            3.0.0
 Modo               Puente local seguro HTTPS

──────────────────────────────────────────────────────────
EOF
echo

# ── 0. ¿Ya está instalado como servicio? ─────────────────────────────────────
# En las cajas ya convertidas al autoarranque, la cajera va a seguir buscando
# este archivo y dándole doble clic por costumbre durante semanas. Sin esta
# guarda vería un error de puerto ocupado y levantaría el teléfono. Con ella ve
# que todo está bien y cierra la ventana.
#
# En las cajas NO convertidas la condición es falsa y el script sigue haciendo
# exactamente lo de siempre.
if systemctl is-active --quiet atlas-print-agent 2>/dev/null \
   || systemctl --user is-active --quiet atlas-print-agent 2>/dev/null; then
    cat << 'EOF'

 ╭────────────────────────────────────────────────────────╮
 │  El agente YA ESTA ACTIVO                              │
 ╰────────────────────────────────────────────────────────╯

 Esta computadora ya arranca el agente sola al prenderse.
 No necesitas abrir nada: enciende la PC, abre el navegador
 y vende normal.

 Puedes cerrar esta ventana.

EOF
    read -r -t 60 -p " Presiona ENTER para cerrar… " _ || true
    echo
    exit 0
fi

# ── 1. Python ─────────────────────────────────────────────────────────────────
echo "[INICIO]  Iniciando agente de impresion..."
if ! command -v python3 >/dev/null 2>&1; then
    echo "[ERROR] python3 no está instalado."
    echo "        Instala con: sudo apt install python3 python3-venv python3-pip"
    exit 1
fi
PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "[OK]      Python detectado correctamente."

# ── 2. CUPS (sistema) ─────────────────────────────────────────────────────────
NEEDS_CUPS=0
command -v lp        >/dev/null 2>&1 || NEEDS_CUPS=1
command -v lpstat    >/dev/null 2>&1 || NEEDS_CUPS=1
command -v lpadmin   >/dev/null 2>&1 || NEEDS_CUPS=1
command -v lpinfo    >/dev/null 2>&1 || NEEDS_CUPS=1

if [ "$NEEDS_CUPS" -eq 1 ]; then
    echo "[INFO]    Instalando CUPS (solicita privilegios una vez)..."
    sudo apt-get update -qq || true
    sudo apt-get install -y cups cups-client cups-bsd || {
        echo "[ERROR] No se pudo instalar CUPS automáticamente."
        echo "        Ejecuta manualmente: sudo apt install cups cups-client cups-bsd"
        exit 1
    }
fi
echo "[OK]      CUPS disponible."

# ── 3. cupsd corriendo ────────────────────────────────────────────────────────
if ! systemctl is-active --quiet cups; then
    echo "[INFO]    Arrancando CUPS..."
    sudo systemctl enable --now cups || {
        echo "[WARN]    No se pudo arrancar CUPS. Revisa: sudo systemctl status cups"
    }
fi
echo "[OK]      CUPS activo."

# ── 4. Usuario en grupo lpadmin (para lpadmin sin sudo) ───────────────────────
if ! id -nG "$USER" | grep -qw lpadmin; then
    echo "[INFO]    Configurando permisos de usuario..."
    sudo usermod -aG lpadmin "$USER" || true
    echo "[NOTA]    Para los cambios de grupo, cierra sesión y vuelve a entrar"
    echo "[NOTA]    (o ejecuta 'newgrp lpadmin'). El agente ya funcionara igual."
fi

# ── 5. python3-venv ──────────────────────────────────────────────────────────
VENV_DIR="$CORE_DIR/venv"
if [ ! -f "$VENV_DIR/bin/activate" ]; then
    rm -rf "$VENV_DIR"
    echo "[INFO]    Preparando entorno local..."
    if ! python3 -m venv "$VENV_DIR" 2>/dev/null; then
        echo "[INFO]    Instalando python3-venv..."
        sudo apt-get install -y "python${PY_VER}-venv" 2>/dev/null || \
            sudo apt-get install -y python3-venv || {
                echo "[ERROR] No se pudo instalar python3-venv. sudo apt install python${PY_VER}-venv"
                exit 1
            }
        python3 -m venv "$VENV_DIR"
    fi
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
echo "[OK]      Entorno local listo."

# ── 6. Dependencias Python ────────────────────────────────────────────────────
echo "[INFO]    Instalando dependencias..."
REQ_FILE="$CORE_DIR/requirements_linux.txt"
if [ ! -f "$REQ_FILE" ]; then
    echo "[ERROR] Falta $REQ_FILE — bundle incompleto."
    exit 1
fi
pip install --quiet --upgrade pip || {
    echo "[ERROR] Falló pip upgrade."
    exit 1
}
pip install --quiet -r "$REQ_FILE" || {
    echo "[ERROR] Falló pip install -r $REQ_FILE. Revisa conexión a internet o permisos del venv."
    exit 1
}
echo "[OK]      Dependencias listas."

# ── 7. Certificados SSL ───────────────────────────────────────────────────────
# main.py también regenera si quedan ≤ 7 días; acá solo hacemos la primera vez.
if [ ! -f "$CORE_DIR/certs/cert.pem" ] || [ ! -f "$CORE_DIR/certs/key.pem" ]; then
    echo "[INFO]    Preparando certificado local SSL..."
    python3 "$CORE_DIR/generate_cert.py" || {
        echo "[NOTA]    El agente arrancará en HTTP si falla el certificado."
    }
fi
echo "[OK]      Certificado listo."

# ── 8. Diagnóstico rápido pre-arranque ────────────────────────────────────────
echo

# ── 9. Arranque con auto-restart ──────────────────────────────────────────────
echo "[LISTO]   El agente de impresion esta funcionando."
echo "[LISTO]   Tu computadora ya puede enviar tickets a la impresora."
echo
echo "[NOTA]    No cierres esta ventana."
echo "[NOTA]    Puedes minimizarla mientras usas el punto de venta."
echo "[NOTA]    Primera vez: abre https://127.0.0.1:9100/health"
echo

while true; do
    python3 "$CORE_DIR/main.py" || true
    echo
    echo "[AVISO]   El agente se detuvo. Reiniciando en 5s... (Ctrl+C para salir)"
    sleep 5
done
