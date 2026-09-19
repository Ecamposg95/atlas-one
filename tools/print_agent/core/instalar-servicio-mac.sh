#!/bin/bash
# Atlas Print Agent — instalación como servicio en macOS (arranque automático).
#
# Convierte una Mac del modo manual ("abrir impresora_mac.sh y dejar la ventana
# de Terminal abierta") al modo servicio: el agente arranca solo al iniciar
# sesión y launchd lo revive si se cae. La cajera no abre nada.
#
# Uso (desde la carpeta que la caja ya venía usando):
#   bash core/instalar-servicio-mac.sh
#
# Opciones:
#   --origins "https://a,https://b"   Dominios del POS (CORS del agente)
#   --certs-from /ruta/core/certs     Certificado a conservar (ver abajo)
#   --dry-run                         Imprime lo que haría y sale
#   --uninstall                       Quita el servicio (deja los archivos)
#   -h | --help                       Esta ayuda
#
# NO uses sudo: es un LaunchAgent de TU usuario, no un LaunchDaemon. Así
# arranca al iniciar sesión sin contraseña de administrador y ve la misma cola
# de CUPS que la cajera.
#
# CERTIFICADO — importante al convertir una Mac que ya venía operando:
# el navegador de esa Mac ya aceptó el certificado autofirmado actual. Si el
# servicio arranca con uno nuevo, la cajera tiene que volver a aceptarlo. Este
# script busca y CONSERVA el certificado existente (bundle → destino →
# ~/Downloads/print_agent → ~/Descargas/print_agent).
#
# Después:
#   launchctl print gui/$(id -u)/com.atlasone.print-agent
#   curl -k https://127.0.0.1:9100/health
#   tail -f ~/Library/Logs/AtlasPrintAgent/agent.err.log

set -uo pipefail

# Bajo `set -u`, $USER no está garantizado (una shell no interactiva puede no
# traerlo). Se le da valor una sola vez para poder usarlo sin guardas.
USER="${USER:-$(id -un)}"

LABEL="com.atlasone.print-agent"
DEFAULT_ORIGINS="https://app.atlasone.com.mx"
AGENT_PORT="${ATLAS_AGENT_PORT:-9100}"
DEST="$HOME/Library/Application Support/AtlasPrintAgent"
LOGDIR="$HOME/Library/Logs/AtlasPrintAgent"
LAUNCHAGENTS="$HOME/Library/LaunchAgents"
PLIST="$LAUNCHAGENTS/$LABEL.plist"

SRC_CORE="$(cd "$(dirname "$0")" && pwd)"
SRC_AGENT="$(cd "$SRC_CORE/.." && pwd)"
PLIST_TEMPLATE="$SRC_CORE/$LABEL.plist"

ORIGINS="${ATLAS_AGENT_ORIGINS:-$DEFAULT_ORIGINS}"
CERTS_FROM=""
PRESERVED_CERTS=""
DRY_RUN=0
UNINSTALL=0

# `warn` va a stderr a propósito: se le llama desde funciones cuyo resultado
# podría capturarse con $(...) y el texto del aviso acabaría pegado al valor.
log()   { echo "[INFO]  $*"; }
ok()    { echo "[OK]    $*"; }
warn()  { echo "[AVISO] $*" >&2; }
die()   { echo "[ERROR] $*" >&2; exit 1; }

# ── Argumentos ────────────────────────────────────────────────────────────────
while [ $# -gt 0 ]; do
    case "$1" in
        --origins)    [ $# -ge 2 ] || die "--origins requiere un valor, p. ej. --origins \"https://app.atlasone.com.mx\""
                      ORIGINS="$2"; shift 2 ;;
        --certs-from) [ $# -ge 2 ] || die "--certs-from requiere una ruta, p. ej. --certs-from ~/Downloads/print_agent/core/certs"
                      CERTS_FROM="$2"; shift 2 ;;
        --dry-run)    DRY_RUN=1; shift ;;
        --uninstall)  UNINSTALL=1; shift ;;
        # El encabezado se imprime entero, sea cual sea su largo: se corta en la
        # primera línea que ya no empieza con '#'. Un rango fijo se desincroniza.
        -h|--help)    awk 'NR>1 { if ($0 ~ /^#/) print; else exit }' "$0"; exit 0 ;;
        *)            die "Opción desconocida: $1" ;;
    esac
done

GUI_TARGET="gui/$(id -u)"

# ── 1. Plataforma y usuario ──────────────────────────────────────────────────
[ "$(uname -s)" = "Darwin" ] \
    || die "Este instalador es solo para macOS. En Linux usa core/instalar-servicio-linux.sh."

# El LaunchAgent es del usuario: con sudo se instalaría en el home de root y
# la cajera nunca lo vería arrancar.
if [ -n "${SUDO_USER:-}" ] || [ "$(id -u)" -eq 0 ]; then
    die "Córrelo SIN sudo. El agente se instala como servicio de TU usuario."
fi

# ── 2. Desinstalar (antes de cualquier chequeo: revertir debe funcionar
#       siempre, incluso en una Mac donde python3 o CUPS ya no estén) ─────────
if [ "$UNINSTALL" -eq 1 ]; then
    if [ "$DRY_RUN" -eq 1 ]; then
        log "--dry-run --uninstall: esto es lo que se haría, sin tocar nada:"
        echo "    launchctl bootout $GUI_TARGET/$LABEL"
        echo "    rm -f \"$PLIST\""
        echo
        log "Los archivos de $DEST y los logs de $LOGDIR NO se borrarían."
        exit 0
    fi
    log "Quitando el servicio $LABEL…"
    launchctl bootout "$GUI_TARGET/$LABEL" 2>/dev/null
    rm -f "$PLIST"
    ok "Servicio quitado. Ya no arranca al iniciar sesión."
    warn "Los archivos siguen en: $DEST"
    warn "Los logs siguen en:     $LOGDIR"
    echo
    echo "  El modo manual vuelve a funcionar: bash impresora_mac.sh"
    echo "  Para borrar también los archivos:  rm -rf \"$DEST\""
    exit 0
fi

# ── 3. Python ────────────────────────────────────────────────────────────────
# El mínimo real es 3.9: las Command Line Tools de Xcode traen 3.9.6 y el
# agente no usa sintaxis de 3.10+. Exigir 3.10 abortaba en una Mac de fábrica
# y el mensaje mandaba de vuelta a xcode-select, que vuelve a dar 3.9.6: un
# callejón sin salida. Por eso el remedio nunca es xcode-select.
PY_MIN_MSG="Instala Python desde https://python.org/downloads/macos/ o con Homebrew:  brew install python@3.12"
command -v python3 >/dev/null 2>&1 \
    || die "python3 no está instalado. $PY_MIN_MSG"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' \
    || die "Se necesita Python 3.9 o superior (esta Mac tiene $(python3 -V 2>&1)). $PY_MIN_MSG"

# ── 4. CUPS ──────────────────────────────────────────────────────────────────
# macOS trae CUPS de fábrica; que el planificador esté caído es raro pero
# posible. No es motivo para abortar: el agente arranca igual y /health
# responde; lo que no habrá es impresión hasta arreglarlo.
CUPS_STATUS=""
command -v lpstat >/dev/null 2>&1 && CUPS_STATUS="$(lpstat -r 2>/dev/null)"
case "$CUPS_STATUS" in
    "" | *"not running"* | *"no se está ejecutando"* | *"no se esta ejecutando"*)
        warn "CUPS no reporta 'scheduler is running' (lpstat -r dijo: ${CUPS_STATUS:-nada})."
        warn "El agente se instalará igual, pero no imprimirá hasta que CUPS esté activo:"
        warn "  sudo launchctl kickstart -k system/org.cups.cupsd"
        ;;
    *)  ok "CUPS activo ($CUPS_STATUS)." ;;
esac

echo
echo "════════════════════════════════════════════════════════════"
echo "  Atlas Print Agent — instalación de servicio (macOS)"
echo "  Usuario:    $USER ($GUI_TARGET)"
echo "  Origen:     $SRC_AGENT"
echo "  Destino:    $DEST"
echo "  Plist:      $PLIST"
echo "  Logs:       $LOGDIR"
echo "  Puerto:     $AGENT_PORT"
echo "  Orígenes:   $ORIGINS"
echo "════════════════════════════════════════════════════════════"
echo

# ── 5. Localizar el certificado a conservar ──────────────────────────────────
# Deja el resultado en $PRESERVED_CERTS en vez de imprimirlo: un `warn` dentro
# de una sustitución de comandos acabaría pegado a la ruta y rompería el `cp`.
buscar_certificado() {
    local d
    if [ -n "$CERTS_FROM" ]; then
        if [ -f "$CERTS_FROM/cert.pem" ] && [ -f "$CERTS_FROM/key.pem" ]; then
            PRESERVED_CERTS="$CERTS_FROM"
            return
        fi
        warn "--certs-from '$CERTS_FROM' no tiene cert.pem + key.pem; se ignora."
    fi
    for d in "$SRC_CORE/certs" \
             "$DEST/certs" \
             "$HOME/Downloads/print_agent/core/certs" \
             "$HOME/Descargas/print_agent/core/certs"; do
        if [ -f "$d/cert.pem" ] && [ -f "$d/key.pem" ]; then
            PRESERVED_CERTS="$d"
            return
        fi
    done
}
buscar_certificado

if [ -n "$PRESERVED_CERTS" ]; then
    ok "Certificado existente encontrado: $PRESERVED_CERTS (se conserva)"
else
    warn "No se encontró certificado previo: el navegador tendrá que aceptarlo de nuevo."
fi

# ── 6. Ensayo en seco ────────────────────────────────────────────────────────
# La plantilla se valida ANTES de salir del dry-run: si falta, el ensayo tiene
# que decirlo, no fingir que todo está bien y reventar en la instalación real.
[ -f "$PLIST_TEMPLATE" ] || die "Bundle incompleto: no se encuentra $PLIST_TEMPLATE"

if [ "$DRY_RUN" -eq 1 ]; then
    echo
    log "--dry-run: no se modificó nada. Vuelve a correr sin --dry-run para instalar."
    exit 0
fi

# ── 7. Copiar el agente a una ruta estable ───────────────────────────────────
# El servicio NO puede apuntar a ~/Downloads: esa carpeta se vacía y el
# autoarranque queda apuntando al vacío la mañana que menos conviene.
if [ "$SRC_CORE" = "$DEST" ]; then
    log "El agente ya vive en el destino; no se copia."
else
    log "Copiando el agente a $DEST…"
    mkdir -p "$DEST" || die "No se pudo crear $DEST"
    for f in main.py generate_cert.py requirements_mac.txt requirements.txt; do
        [ -f "$SRC_CORE/$f" ] || die "Bundle incompleto: falta $SRC_CORE/$f"
        cp "$SRC_CORE/$f" "$DEST/$f" || die "No se pudo copiar $f a $DEST"
    done
    # Extras: dejan la instalación autosuficiente para reinstalar o desinstalar
    # desde $DEST aunque la carpeta de Descargas ya no exista.
    for f in "$LABEL.plist" instalar-servicio-mac.sh INSTALL_MAC.txt; do
        [ -f "$SRC_CORE/$f" ] && cp "$SRC_CORE/$f" "$DEST/$f" 2>/dev/null
    done
    ok "Agente copiado."
fi

if [ -n "$PRESERVED_CERTS" ] && [ "$PRESERVED_CERTS" != "$DEST/certs" ]; then
    mkdir -p "$DEST/certs" || die "No se pudo crear $DEST/certs"
    if cp "$PRESERVED_CERTS/cert.pem" "$PRESERVED_CERTS/key.pem" "$DEST/certs/"; then
        chmod 600 "$DEST/certs/key.pem" 2>/dev/null
        ok "Certificado conservado en $DEST/certs"
    else
        warn "No se pudo copiar el certificado; se generará uno nuevo."
        PRESERVED_CERTS=""
    fi
fi

# ── 8. Entorno Python ────────────────────────────────────────────────────────
# Siempre se invoca "$DEST/venv/bin/python3" -m pip, nunca "$DEST/venv/bin/pip":
# la ruta lleva un espacio ("Application Support") y el shebang de los scripts
# del venv se parte en ese espacio. Llamar al binario con -m lo evita.
VENV_PY="$DEST/venv/bin/python3"
if [ ! -x "$VENV_PY" ]; then
    log "Creando entorno Python…"
    rm -rf "$DEST/venv"
    python3 -m venv "$DEST/venv" || die "No se pudo crear el entorno Python en $DEST/venv."
fi
[ -x "$VENV_PY" ] || die "El entorno Python quedó incompleto: no existe $VENV_PY"

log "Instalando dependencias (puede tardar un par de minutos)…"
"$VENV_PY" -m pip install --quiet --upgrade pip || die "Falló la actualización de pip."
"$VENV_PY" -m pip install --quiet -r "$DEST/requirements_mac.txt" \
    || die "Falló pip install. Revisa la conexión a internet."
ok "Dependencias instaladas."

# ── 9. Certificado ───────────────────────────────────────────────────────────
# generate_cert.py resuelve la carpeta como os.path.dirname(__file__)/certs,
# así que vivir en $DEST basta para que el certificado caiga en $DEST/certs.
# Se exigen los DOS archivos: con cert.pem pero sin key.pem, uvicorn no arranca
# en TLS y el agente caía a HTTP sin que nadie entendiera por qué.
if [ ! -f "$DEST/certs/cert.pem" ] || [ ! -f "$DEST/certs/key.pem" ]; then
    log "Generando certificado local…"
    ( cd "$DEST" && "$VENV_PY" "$DEST/generate_cert.py" ) \
        || warn "Falló la generación del certificado; el agente arrancará en HTTP."
fi
if [ -f "$DEST/certs/cert.pem" ] && [ -f "$DEST/certs/key.pem" ]; then
    ok "Certificado listo."
else
    warn "Sin certificado completo: el agente arrancará en HTTP."
fi

# ── 10. Escribir el LaunchAgent ──────────────────────────────────────────────
log "Escribiendo $PLIST…"
mkdir -p "$LOGDIR" "$LAUNCHAGENTS" || die "No se pudieron crear $LOGDIR / $LAUNCHAGENTS"

# La sustitución la hace python3, no sed: la ruta del destino lleva un espacio
# y podría llevar & o /, que en un sed s|…| son mina. Además escapa el XML.
ATLAS_TPL="$PLIST_TEMPLATE" ATLAS_OUT="$PLIST" ATLAS_WORKDIR="$DEST" \
ATLAS_ORIGINS="$ORIGINS" ATLAS_PORT="$AGENT_PORT" ATLAS_LOGDIR="$LOGDIR" \
python3 - <<'PY' || die "No se pudo escribir $PLIST"
import os
from xml.sax.saxutils import escape

with open(os.environ["ATLAS_TPL"], encoding="utf-8") as fh:
    tpl = fh.read()
for marca, valor in (
    ("{WORKDIR}", os.environ["ATLAS_WORKDIR"]),
    ("{ORIGINS}", os.environ["ATLAS_ORIGINS"]),
    ("{PORT}",    os.environ["ATLAS_PORT"]),
    ("{LOGDIR}",  os.environ["ATLAS_LOGDIR"]),
):
    tpl = tpl.replace(marca, escape(valor))
for marca in ("{WORKDIR}", "{ORIGINS}", "{PORT}", "{LOGDIR}"):
    assert marca not in tpl, f"quedó sin sustituir {marca}"
with open(os.environ["ATLAS_OUT"], "w", encoding="utf-8") as fh:
    fh.write(tpl)
PY

if command -v plutil >/dev/null 2>&1; then
    plutil -lint "$PLIST" >/dev/null \
        || die "El plist generado no es válido. Revisa $PLIST"
    ok "plist válido."
fi

# ── 11. Cargar en launchd ────────────────────────────────────────────────────
# Si quedó una ventana de Terminal con el modo manual, ocupa el 9100 y el
# servicio no arranca; se cierra antes de cargar el nuevo.
#
# OJO: impresora_mac.sh NO es el agente, es un `while true` que lo relanza a los
# 5 segundos. Matando solo el python, el envoltorio lo resucita y se pone a
# competir con el servicio por el 9100: /health puede acabar respondiendo desde
# el agente manual mientras launchd reinicia el suyo en bucle. Por eso se mata
# PRIMERO el envoltorio y luego el agente.
# El '$' final no es decorativo: sin él, cualquier shell cuya línea de
# comando MENCIONE el launcher (un `zsh -c '…'`, un editor, un script de
# arranque) entraría en la redada. Anclado al final solo casa la invocación
# real, donde el script es el último argumento.
PAT_ENVOLTORIO='(bash|sh|zsh) .*impresora_mac\.sh$'
PAT_AGENTE='python3? .*(AtlasPrintAgent|print_agent/core)/main\.py$'

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

detener_agente_manual() {
    local algo=1
    _matar "$PAT_ENVOLTORIO" "la ventana del modo manual (impresora_mac.sh)" && algo=0
    _matar "$PAT_AGENTE"     "el agente manual en curso"                     && algo=0
    [ "$algo" -eq 0 ] && ok "Modo manual detenido."
    return 0
}

launchctl bootout "$GUI_TARGET/$LABEL" 2>/dev/null
detener_agente_manual
sleep 1

# ── FIX 4: bootstrap falla por SSH ("Bootstrap failed: 5: Input/output error").
# launchd no deja cargar un LaunchAgent en el dominio gui desde una sesión sin
# GUI. El plist ya está escrito, así que cargará solo en el siguiente inicio de
# sesión gráfico; el mensaje tiene que decir eso en vez de mandar a "reintentar".
BOOTSTRAP_SALIDA="$(launchctl bootstrap "$GUI_TARGET" "$PLIST" 2>&1)"
if [ $? -ne 0 ]; then
    echo
    echo "════════════════════════════════════════════════════════════"
    echo "  ✗ launchctl bootstrap falló"
    echo "════════════════════════════════════════════════════════════"
    echo "  ${BOOTSTRAP_SALIDA:-(sin mensaje)}"
    echo
    case "$BOOTSTRAP_SALIDA" in
        *"Bootstrap failed: 5"*|*"Input/output error"*)
            echo "  Casi siempre es esto: estás por SSH. Un LaunchAgent solo se"
            echo "  carga desde la sesión GRÁFICA de la Mac."
            echo
            echo "  1. Entra a la Mac en persona (Terminal) o por Compartir pantalla."
            echo "  2. Corre:  launchctl bootout $GUI_TARGET/$LABEL"
            echo "  3. Vuelve a correr este instalador."
            ;;
        *)
            echo "  Corre este instalador desde la sesión GRÁFICA de la Mac"
            echo "  (Terminal en la Mac o Compartir pantalla), NO por SSH."
            echo "  Si insiste:  launchctl bootout $GUI_TARGET/$LABEL  y reintenta."
            ;;
    esac
    echo
    echo "  El plist YA quedó escrito en:"
    echo "    $PLIST"
    echo "  Así que el agente arrancará solo en el próximo inicio de sesión"
    echo "  gráfico de esta Mac, aunque este comando haya fallado."
    echo
    die "launchctl bootstrap falló; ver arriba."
fi
launchctl kickstart -k "$GUI_TARGET/$LABEL" \
    || warn "launchctl kickstart falló; launchd debería arrancarlo igual por RunAtLoad."

# ── 12. Verificación real — no declarar victoria sin respuesta ───────────────
log "Verificando que el agente responda (hasta 60 s)…"
# Cualquier cosa que conteste en el 9100 no sirve: tiene que ser NUESTRO
# /health. Un cuerpo vacío, un 404 de otro servicio o una página de error
# darían un falso "instalado y respondiendo".
_es_health() {
    case "$1" in
        *'"status"'*|*'"ok"'*) return 0 ;;
        *) return 1 ;;
    esac
}
HEALTH=""
LIMITE=$(( $(date +%s) + 60 ))
while [ "$(date +%s)" -lt "$LIMITE" ]; do
    HEALTH="$(curl -sk --max-time 2 "https://127.0.0.1:$AGENT_PORT/health" 2>/dev/null)"
    _es_health "$HEALTH" && break
    HEALTH="$(curl -s --max-time 2 "http://127.0.0.1:$AGENT_PORT/health" 2>/dev/null)"
    _es_health "$HEALTH" && break
    HEALTH=""
    sleep 2
done

echo
if [ -z "$HEALTH" ]; then
    echo "════════════════════════════════════════════════════════════"
    echo "  ✗ El servicio quedó cargado pero NO respondió en el $AGENT_PORT"
    echo "════════════════════════════════════════════════════════════"
    echo "  Revisa:  tail -n 50 \"$LOGDIR/agent.err.log\""
    echo "           launchctl print $GUI_TARGET/$LABEL"
    echo
    echo "  Para volver atrás (deja la Mac como estaba, en modo manual):"
    echo "           bash core/instalar-servicio-mac.sh --uninstall"
    echo "  Mientras tanto el modo manual sigue funcionando: bash impresora_mac.sh"
    die "El agente no respondió; revisa $LOGDIR/agent.err.log"
fi

echo "════════════════════════════════════════════════════════════"
echo "  ✓ Agente instalado y respondiendo"
echo "════════════════════════════════════════════════════════════"
echo "  $HEALTH"
echo
echo "  Arranca solo al iniciar sesión; si se cae, launchd lo revive."
echo "  La cajera no tiene que abrir nada: enciende, abre el navegador y vende."
echo
echo "  Estado:  launchctl print $GUI_TARGET/$LABEL"
echo "  Logs:    tail -f \"$LOGDIR/agent.err.log\""
echo "  Quitar:  bash core/instalar-servicio-mac.sh --uninstall"
echo
if [ -z "$PRESERVED_CERTS" ]; then
    echo "  ATENCIÓN: certificado NUEVO. Abre en el navegador del POS de esta Mac"
    echo "            https://127.0.0.1:$AGENT_PORT/health  y acéptalo."
    echo
fi
