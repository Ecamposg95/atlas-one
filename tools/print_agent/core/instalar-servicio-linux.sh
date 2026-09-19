#!/bin/bash
# Atlas Print Agent — instalación como servicio (arranque automático al prender la PC).
#
# Convierte una caja del modo manual ("abrir impresora_linux.sh y dejar la
# ventana abierta") al modo servicio: el agente arranca solo al encender la PC,
# antes de que nadie inicie sesión, y systemd lo revive si se cae.
#
# Uso:
#   sudo bash core/instalar-servicio-linux.sh              # servicio de sistema
#   sudo bash core/instalar-servicio-linux.sh cajero       # bajo otro usuario
#   bash core/instalar-servicio-linux.sh                   # sin root: servicio de usuario
#
# Opciones:
#   --origins "https://a,https://b"   Dominios del POS (CORS del agente)
#   --certs-from /ruta/core/certs     Certificado a conservar (ver abajo)
#   --dry-run                         Imprime lo que haría y sale
#
# CERTIFICADO — importante al convertir una caja que ya venía operando:
# el navegador de esa PC ya aceptó el certificado autofirmado actual. Si el
# servicio arranca con uno nuevo, la cajera tiene que volver a aceptarlo. Este
# script busca y CONSERVA el certificado existente (bundle → destino → home).
#
# Después:
#   systemctl status atlas-print-agent          (sistema)
#   systemctl --user status atlas-print-agent   (usuario)

set -uo pipefail

# Bajo `set -u`, $USER no está garantizado (una shell no interactiva puede no
# traerlo). Se le da valor una sola vez para poder usarlo sin guardas.
USER="${USER:-$(id -un)}"

SERVICE_NAME="atlas-print-agent"
DEFAULT_ORIGINS="https://app.atlasone.com.mx"
AGENT_PORT="${ATLAS_AGENT_PORT:-9100}"

SRC_CORE="$(cd "$(dirname "$0")" && pwd)"
SRC_AGENT="$(cd "$SRC_CORE/.." && pwd)"
SERVICE_TEMPLATE="$SRC_CORE/$SERVICE_NAME.service"

ORIGINS="${ATLAS_AGENT_ORIGINS:-$DEFAULT_ORIGINS}"
CERTS_FROM=""
DRY_RUN=0
TARGET_USER=""

# `warn` va a stderr a propósito: find_existing_certs lo llama y su salida se
# captura con $(...). En stdout, el texto del aviso acababa pegado a la ruta del
# certificado y el `cp` posterior fallaba con un mensaje incomprensible.
# `log`/`ok` no se llaman desde ninguna sustitución; se dejan en stdout.
log()   { echo "[INFO]  $*"; }
ok()    { echo "[OK]    $*"; }
warn()  { echo "[AVISO] $*" >&2; }
die()   { echo "[ERROR] $*" >&2; exit 1; }

# ── Argumentos ────────────────────────────────────────────────────────────────
while [ $# -gt 0 ]; do
    case "$1" in
        --origins)    [ $# -ge 2 ] || die "--origins requiere un valor, p. ej. --origins \"https://app.atlasone.com.mx\""
                      ORIGINS="$2"; shift 2 ;;
        --certs-from) [ $# -ge 2 ] || die "--certs-from requiere una ruta, p. ej. --certs-from ~/Descargas/print_agent/core/certs"
                      CERTS_FROM="$2"; shift 2 ;;
        --dry-run)    DRY_RUN=1; shift ;;
        # El encabezado se imprime entero, sea cual sea su largo: se corta en la
        # primera línea que ya no empieza con '#'. Un rango fijo se desincroniza.
        -h|--help)    awk 'NR>1 { if ($0 ~ /^#/) print; else exit }' "$0"; exit 0 ;;
        -*)           die "Opción desconocida: $1" ;;
        *)            TARGET_USER="$1"; shift ;;
    esac
done

[ -f "$SERVICE_TEMPLATE" ] || die "Bundle incompleto: no se encuentra $SERVICE_TEMPLATE"

# ── Modo: sistema (root) o usuario ───────────────────────────────────────────
# El dueño pidió que funcione aunque la tienda no tenga sudo a la mano. Un
# servicio de usuario con linger también arranca al prender la PC sin que nadie
# inicie sesión; la diferencia es que no puede instalar paquetes del sistema.
if [ "$(id -u)" -eq 0 ]; then
    MODE="system"
    TARGET_USER="${TARGET_USER:-${SUDO_USER:-root}}"
    id "$TARGET_USER" &>/dev/null || die "El usuario '$TARGET_USER' no existe."
    TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
    INSTALL_DIR="/opt/$SERVICE_NAME"
    UNIT_PATH="/etc/systemd/system/$SERVICE_NAME.service"
    SCTL=(systemctl)
else
    MODE="user"
    if [ -n "$TARGET_USER" ] && [ "$TARGET_USER" != "$USER" ]; then
        die "Sin root solo se puede instalar para el usuario actual ($USER), no para '$TARGET_USER'."
    fi
    TARGET_USER="$USER"
    TARGET_HOME="$HOME"
    INSTALL_DIR="$HOME/.local/share/$SERVICE_NAME"
    UNIT_PATH="$HOME/.config/systemd/user/$SERVICE_NAME.service"
    SCTL=(systemctl --user)
    warn "Sin root — se instalará como servicio de USUARIO ($USER)."
    warn "Arranca igual al prender la PC, pero no puede instalar CUPS ni python3-venv."
fi

WORKDIR="$INSTALL_DIR/core"
VENV="$WORKDIR/venv"

command -v systemctl >/dev/null 2>&1 || die "Este sistema no usa systemd — no hay autoarranque que instalar."

echo
echo "════════════════════════════════════════════════════════════"
echo "  Atlas Print Agent — instalación de servicio"
echo "  Modo:       $MODE"
echo "  Usuario:    $TARGET_USER"
echo "  Origen:     $SRC_AGENT"
echo "  Destino:    $INSTALL_DIR"
echo "  Unidad:     $UNIT_PATH"
echo "  Orígenes:   $ORIGINS"
echo "════════════════════════════════════════════════════════════"
echo

# ── 1. Localizar el certificado a conservar ──────────────────────────────────
find_existing_certs() {
    local c
    # a) Ruta explícita.
    if [ -n "$CERTS_FROM" ]; then
        [ -f "$CERTS_FROM/cert.pem" ] && [ -f "$CERTS_FROM/key.pem" ] \
            && { echo "$CERTS_FROM"; return; }
        warn "--certs-from '$CERTS_FROM' no tiene cert.pem + key.pem; se ignora."
    fi
    # b) El bundle desde el que se corre (caja convertida en su propia carpeta).
    [ -f "$SRC_CORE/certs/cert.pem" ] && [ -f "$SRC_CORE/certs/key.pem" ] \
        && { echo "$SRC_CORE/certs"; return; }
    # c) Una instalación previa en el destino (reinstalación / actualización).
    [ -f "$WORKDIR/certs/cert.pem" ] && [ -f "$WORKDIR/certs/key.pem" ] \
        && { echo "$WORKDIR/certs"; return; }
    # d) El caso real de campo: la cajera descomprimió el ZIP en Descargas y
    #    lleva meses usándolo. Buscar el cert más reciente en su home.
    if [ -n "${TARGET_HOME:-}" ] && [ -d "$TARGET_HOME" ]; then
        c="$(find "$TARGET_HOME" -maxdepth 6 -type f -name cert.pem -path '*/core/certs/*' \
              -printf '%T@ %h\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)"
        [ -n "$c" ] && [ -f "$c/key.pem" ] && { echo "$c"; return; }
    fi
}

PRESERVED_CERTS="$(find_existing_certs)"
if [ -n "$PRESERVED_CERTS" ]; then
    ok "Certificado existente encontrado: $PRESERVED_CERTS (se conserva)"
else
    warn "No se encontró certificado previo — se generará uno nuevo."
    warn "En una caja ya operando habrá que volver a aceptarlo en el navegador."
fi

if [ "$DRY_RUN" -eq 1 ]; then
    echo
    log "--dry-run: no se modificó nada. Vuelve a correr sin --dry-run para instalar."
    exit 0
fi

# ── 2. Dependencias del sistema (solo con root) ──────────────────────────────
if [ "$MODE" = "system" ]; then
    if ! command -v lp >/dev/null 2>&1 || ! command -v lpstat >/dev/null 2>&1 \
       || ! command -v lpadmin >/dev/null 2>&1; then
        log "Instalando CUPS…"
        apt-get update -qq || true
        apt-get install -y cups cups-client cups-bsd \
            || die "No se pudo instalar CUPS. Hazlo a mano: apt install cups cups-client cups-bsd"
    fi
    systemctl is-active --quiet cups || systemctl enable --now cups \
        || warn "CUPS no arrancó. Revisa: systemctl status cups"
    ok "CUPS disponible."

    if [ "$TARGET_USER" != "root" ] && ! id -nG "$TARGET_USER" | grep -qw lpadmin; then
        usermod -aG lpadmin "$TARGET_USER" && log "Usuario '$TARGET_USER' agregado al grupo lpadmin."
    fi
else
    command -v lpstat >/dev/null 2>&1 \
        || die "CUPS no está instalado y no hay root. Ejecuta: sudo apt install cups cups-client cups-bsd"
fi

command -v python3 >/dev/null 2>&1 || die "python3 no está instalado."

# ── 3. Detener cualquier agente manual en el puerto ──────────────────────────
# La cajera pudo dejar abierta la ventana del modo manual. Si no se detiene,
# el servicio no puede tomar el 9100 y el diagnóstico se vuelve confuso.
#
# OJO: impresora_linux.sh NO es el agente, es un `while true` que lo relanza a
# los 5 segundos. Matando solo el python, el envoltorio lo resucita y se pone a
# competir con el servicio por el 9100: /health puede acabar respondiendo desde
# el agente manual mientras systemd reinicia el suyo en bucle. Por eso se mata
# PRIMERO el envoltorio y luego el agente.
# El '$' final no es decorativo: sin él, cualquier shell cuya línea de
# comando MENCIONE el launcher (un `zsh -c '…'`, un editor, un script de
# arranque) entraría en la redada. Anclado al final solo casa la invocación
# real, donde el script es el último argumento.
PAT_ENVOLTORIO='(bash|sh|zsh) .*impresora_linux\.sh$'
PAT_AGENTE='python3? .*(atlas-print-agent|print_agent)/core/main\.py$'

_matar() {
    local pids
    pids="$(pgrep -f "$1" 2>/dev/null | tr '\n' ' ')"
    [ -z "${pids// /}" ] && return 1
    log "Deteniendo $2 (PID: ${pids})…"
    # shellcheck disable=SC2086
    kill $pids 2>/dev/null
    sleep 2
    # shellcheck disable=SC2086
    kill -9 $pids 2>/dev/null
    return 0
}

stop_manual_agent() {
    local algo=1
    _matar "$PAT_ENVOLTORIO" "la ventana del modo manual (impresora_linux.sh)" && algo=0
    _matar "$PAT_AGENTE"     "el agente manual en curso"                       && algo=0
    [ "$algo" -eq 0 ] && ok "Modo manual detenido."
    return 0
}
"${SCTL[@]}" stop "$SERVICE_NAME" 2>/dev/null
stop_manual_agent

# ── 4. Copiar el bundle a una ruta estable ───────────────────────────────────
# El servicio NO puede apuntar a ~/Descargas: esa carpeta se vacía y el
# autoarranque queda apuntando al vacío la mañana que menos conviene.
if [ "$SRC_AGENT" != "$INSTALL_DIR" ]; then
    log "Copiando el agente a $INSTALL_DIR…"
    mkdir -p "$INSTALL_DIR" || die "No se pudo crear $INSTALL_DIR"
    # --exclude venv: el venv del origen puede tener rutas absolutas viejas.
    if command -v rsync >/dev/null 2>&1; then
        rsync -a --delete --exclude 'venv' --exclude '__pycache__' --exclude 'certs' \
              "$SRC_AGENT/" "$INSTALL_DIR/" || die "Falló la copia del bundle."
    else
        rm -rf "$INSTALL_DIR/core/__pycache__"
        cp -a "$SRC_AGENT/." "$INSTALL_DIR/" || die "Falló la copia del bundle."
        rm -rf "$INSTALL_DIR/core/venv" "$INSTALL_DIR/core/__pycache__"
    fi
    ok "Bundle copiado."
else
    log "El bundle ya vive en el destino; no se copia."
fi

# Restaurar el certificado conservado (después de copiar: la copia lo excluye).
if [ -n "$PRESERVED_CERTS" ] && [ "$PRESERVED_CERTS" != "$WORKDIR/certs" ]; then
    mkdir -p "$WORKDIR/certs"
    cp -a "$PRESERVED_CERTS/cert.pem" "$PRESERVED_CERTS/key.pem" "$WORKDIR/certs/" \
        && ok "Certificado conservado en $WORKDIR/certs"
fi

[ "$MODE" = "system" ] && chown -R "$TARGET_USER":"$TARGET_USER" "$INSTALL_DIR"

# ── 5. Entorno Python — determinista, sin carreras contra el reloj ───────────
# La versión anterior lanzaba el script interactivo en segundo plano, dormía 20
# segundos y lo mataba. En una PC lenta pip no terminaba: el venv quedaba a
# medias y el servicio arrancaba roto sin que nadie se enterara.
if [ ! -x "$VENV/bin/python3" ]; then
    log "Creando entorno Python…"
    rm -rf "$VENV"
    if ! python3 -m venv "$VENV" 2>/dev/null; then
        [ "$MODE" = "system" ] || die "Falta python3-venv y no hay root: sudo apt install python3-venv"
        PY_VER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
        apt-get install -y "python${PY_VER}-venv" 2>/dev/null || apt-get install -y python3-venv \
            || die "No se pudo instalar python3-venv."
        python3 -m venv "$VENV" || die "No se pudo crear el entorno Python."
    fi
fi

REQ="$WORKDIR/requirements_linux.txt"
[ -f "$REQ" ] || die "Bundle incompleto: falta $REQ"
log "Instalando dependencias (puede tardar varios minutos en una PC lenta)…"
"$VENV/bin/python3" -m pip install --quiet --upgrade pip || die "Falló la actualización de pip."
"$VENV/bin/python3" -m pip install --quiet -r "$REQ" \
    || die "Falló pip install. Revisa la conexión a internet."
ok "Dependencias instaladas."

# ── 6. Certificado ───────────────────────────────────────────────────────────
# Se exigen los DOS archivos: con cert.pem pero sin key.pem, uvicorn no arranca
# en TLS y el agente caía a HTTP sin que nadie entendiera por qué.
if [ ! -f "$WORKDIR/certs/cert.pem" ] || [ ! -f "$WORKDIR/certs/key.pem" ]; then
    log "Generando certificado local…"
    "$VENV/bin/python3" "$WORKDIR/generate_cert.py" \
        || warn "Falló la generación del certificado; el agente arrancará en HTTP."
fi
[ "$MODE" = "system" ] && chown -R "$TARGET_USER":"$TARGET_USER" "$INSTALL_DIR"
if [ -f "$WORKDIR/certs/cert.pem" ] && [ -f "$WORKDIR/certs/key.pem" ]; then
    ok "Certificado listo."
else
    warn "Sin certificado completo: el agente arrancará en HTTP."
fi

# ── 7. Unidad systemd ────────────────────────────────────────────────────────
log "Escribiendo $UNIT_PATH…"
mkdir -p "$(dirname "$UNIT_PATH")"
UNIT="$(sed -e "s|{WORKDIR}|$WORKDIR|g" \
            -e "s|{ORIGINS}|$ORIGINS|g" \
            -e "s|{PORT}|$AGENT_PORT|g" "$SERVICE_TEMPLATE")"

if [ "$MODE" = "system" ]; then
    UNIT="$(printf '%s\n' "$UNIT" | sed -e "s|^User=.*|User=$TARGET_USER|" \
                                        -e "s|^Group=.*|Group=$TARGET_USER|")"
else
    # Un servicio de usuario no lleva User=/Group=, no puede ordenarse contra
    # unidades del sistema (cups.service) y su target es default.target.
    UNIT="$(printf '%s\n' "$UNIT" \
        | sed -e '/^User=/d' -e '/^Group=/d' \
              -e '/^After=/d' -e '/^Wants=/d' \
              -e 's|^WantedBy=multi-user.target|WantedBy=default.target|')"
fi
printf '%s\n' "$UNIT" > "$UNIT_PATH" || die "No se pudo escribir $UNIT_PATH"

"${SCTL[@]}" daemon-reload
"${SCTL[@]}" enable "$SERVICE_NAME" >/dev/null 2>&1 || die "No se pudo habilitar el servicio."

if [ "$MODE" = "user" ]; then
    # Sin linger, el servicio de usuario solo corre mientras hay sesión abierta.
    if loginctl enable-linger "$USER" 2>/dev/null; then
        ok "Linger habilitado: el agente arrancará al prender la PC sin iniciar sesión."
    else
        warn "No se pudo habilitar linger. El agente arrancará al INICIAR SESIÓN,"
        warn "no al prender la PC. Para corregirlo: sudo loginctl enable-linger $USER"
    fi
fi

"${SCTL[@]}" restart "$SERVICE_NAME" || die "El servicio no arrancó. Revisa los logs."

# ── 8. Verificación real — no declarar victoria sin respuesta ────────────────
log "Verificando que el agente responda…"
HEALTH=""
for _ in $(seq 1 20); do
    sleep 1
    HEALTH="$(curl -sk --max-time 2 "https://127.0.0.1:$AGENT_PORT/health" 2>/dev/null)"
    [ -n "$HEALTH" ] && break
    HEALTH="$(curl -s --max-time 2 "http://127.0.0.1:$AGENT_PORT/health" 2>/dev/null)"
    [ -n "$HEALTH" ] && break
done

echo
if [ -z "$HEALTH" ]; then
    echo "════════════════════════════════════════════════════════════"
    echo "  ✗ El servicio quedó instalado pero NO respondió en el $AGENT_PORT"
    echo "════════════════════════════════════════════════════════════"
    if [ "$MODE" = "system" ]; then
        echo "  Revisa:  journalctl -u $SERVICE_NAME -n 50 --no-pager"
    else
        echo "  Revisa:  journalctl --user -u $SERVICE_NAME -n 50 --no-pager"
    fi
    echo
    echo "  Para volver atrás (modo manual como antes):"
    if [ "$MODE" = "system" ]; then
        echo "           sudo systemctl disable --now $SERVICE_NAME"
    else
        echo "           systemctl --user disable --now $SERVICE_NAME"
    fi
    echo "  Mientras tanto el modo manual sigue funcionando: bash impresora_linux.sh"
    exit 1
fi

echo "════════════════════════════════════════════════════════════"
echo "  ✓ Agente instalado y respondiendo"
echo "════════════════════════════════════════════════════════════"
echo "  $HEALTH"
echo
echo "  Ya arranca solo al prender la PC. La cajera no tiene que"
echo "  abrir nada: enciende, abre el navegador y vende."
echo
if [ "$MODE" = "system" ]; then
    echo "  Estado:  systemctl status $SERVICE_NAME"
    echo "  Logs:    journalctl -u $SERVICE_NAME -f"
    echo "  Quitar:  sudo systemctl disable --now $SERVICE_NAME"
else
    echo "  Estado:  systemctl --user status $SERVICE_NAME"
    echo "  Logs:    journalctl --user -u $SERVICE_NAME -f"
    echo "  Quitar:  systemctl --user disable --now $SERVICE_NAME"
fi
echo
if [ -z "$PRESERVED_CERTS" ]; then
    echo "  ATENCIÓN: certificado NUEVO. Abre en el navegador de esta PC"
    echo "            https://127.0.0.1:$AGENT_PORT/health  y acéptalo."
    echo
fi
