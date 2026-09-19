# Autoarranque del agente de impresión Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** El agente de impresión arranca solo al prender la PC en Linux (systemd, portado de Rmazh) y en macOS (launchd), con instalador, guarda en los launchers, bloque en `printer-settings` y ZIP descargable coherentes.

**Architecture:** Todo vive en `tools/print_agent/` (scripts bash + plantillas), `app/routers/printer.py` (filtro del ZIP), `frontend/src/pages/pos/PrinterSettings.tsx` (bloque admin) y `tests/test_print_agent_bundle.py`. `main.py` no se toca.

**Tech Stack:** bash, systemd, launchd (plist XML), FastAPI (zip), React/TS, pytest.

**Spec:** `docs/superpowers/specs/2026-09-19-agente-autoarranque-design.md`

## Global Constraints

- `tools/print_agent/core/main.py` no cambia.
- Todo es aditivo y opt-in: el modo manual (`impresora_*.sh` con la ventana abierta) sigue funcionando igual en cajas no convertidas.
- Dominio por defecto de orígenes: `https://app.atlasone.com.mx`.
- Textos en español, sin acentos en nombres de archivo.
- Tests: `python3 -m pytest -q -p no:warnings --ignore=tests/test_cash_complete.py` (baseline 872 passed, 2 skipped, 3 xfailed); frontend `npx tsc --noEmit && npm run build` desde `frontend/`. `bash -n` sobre cada script nuevo/modificado; `plutil -lint` no está disponible en Linux: valida el plist generado con `python3 -c "import plistlib,sys; plistlib.load(open(sys.argv[1],'rb'))"`.
- Commits con `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` y `Claude-Session: https://claude.ai/code/session_01Lug2gDi7z3wjW7VJyjctTb`.

---

### Task 1: Portar el autoarranque de Linux desde Atlas-Rmazh

**Files:**
- Source of truth: repo `/mnt/d/Devs/Atlas-Rmazh`, commit `b845a33` (`git -C /mnt/d/Devs/Atlas-Rmazh show b845a33`).
- Modify (copiar desde Rmazh): `tools/print_agent/core/instalar-servicio-linux.sh`, `tools/print_agent/core/atlas-print-agent.service`, `tools/print_agent/core/INSTALL_LINUX.txt`, `tools/print_agent/impresora_linux.sh`.
- Create (copiar desde Rmazh): `tools/print_agent/README.md`, `docs/superpowers/runbooks/print-agent-autostart.md`, `tests/test_print_agent_bundle.py`.
- Modify: `frontend/src/pages/pos/PrinterSettings.tsx` (bloque admin en la tarjeta "Agente Linux", ~línea 548), `app/routers/printer.py` (`download_print_agent`, ~líneas 318-345).

**Interfaces:**
- Produces: `AUTOSTART_CMD_LINUX = 'sudo bash core/instalar-servicio-linux.sh'`; helper de UI `esAdmin` (`user?.role === 'ADMINISTRADOR' || user?.role === 'DUEÑO'`); el bloque de "Instalación automática" como JSX reutilizable (extrae un componente local `AutostartCard({ cmd, bullets })` dentro del archivo para que la Tarea 2 lo reutilice para macOS).

- [ ] **Step 1: Copiar archivos de Rmazh**

```bash
R=/mnt/d/Devs/Atlas-Rmazh
for f in core/instalar-servicio-linux.sh core/atlas-print-agent.service core/INSTALL_LINUX.txt impresora_linux.sh README.md; do
  git -C $R show b845a33:tools/print_agent/$f > tools/print_agent/$f
done
mkdir -p docs/superpowers/runbooks
git -C $R show b845a33:docs/superpowers/runbooks/print-agent-autostart.md > docs/superpowers/runbooks/print-agent-autostart.md
git -C $R show b845a33:tests/test_print_agent_bundle.py > tests/test_print_agent_bundle.py
chmod +x tools/print_agent/core/instalar-servicio-linux.sh tools/print_agent/impresora_linux.sh
```

- [ ] **Step 2: Adaptar a Atlas One**

En `instalar-servicio-linux.sh`: `DEFAULT_ORIGINS="https://app.atlasone.com.mx"`. En `README.md`, `INSTALL_LINUX.txt`, el runbook y `atlas-print-agent.service`: sustituye `rmazh.atlasone.com.mx` por `app.atlasone.com.mx` y `datax.up.railway.app` por `app.atlasone.com.mx` donde aparezca como dominio del POS; quita frases específicas de Rmazh ("17 sucursales", "RMAZH POS") dejando el sentido. `README.md` debe reflejar que Atlas One permite `*.atlasone.com.mx` de fábrica (ver regex en `main.py`).

`tests/test_print_agent_bundle.py`: léelo entero; adapta imports/fixtures a este repo (`conftest.py` expone `client`, `auth_admin`) y los nombres de archivo esperados. Debe pasar.

- [ ] **Step 3: ZIP y UI**

`app/routers/printer.py`: en `platform_exclude` de `windows` y `mac` añade `"README.md"`? NO — el README aplica a todos; no lo excluyas. Añade a la exclusión de `windows` y `mac` nada nuevo de Linux que no esté ya (`instalar-servicio-linux.sh`, `atlas-print-agent.service`, `INSTALL_LINUX.txt` ya están). Confirma que el ZIP de linux incluye el instalador nuevo y el runbook NO (vive en docs/, fuera de `agent_dir`).

`PrinterSettings.tsx`: aplica el bloque de Rmazh (ver `git -C $R show b845a33 -- frontend/src/pages/pos/PrinterSettings.tsx`) adaptado: componente local `AutostartCard`, `esAdmin` desde `useAuthStore`, `AUTOSTART_CMD_LINUX`, textos de la lista de Linux tal cual (`/opt/atlas-print-agent`). Corrige los nombres de archivo que la tarjeta de Linux dicta (`bash impresora_linux.sh`, `sudo bash core/instalar-servicio-linux.sh`).

- [ ] **Step 4: Verificar y commit**

```bash
bash -n tools/print_agent/core/instalar-servicio-linux.sh tools/print_agent/impresora_linux.sh
python3 -m pytest -q -p no:warnings tests/test_print_agent_bundle.py
cd frontend && npx tsc --noEmit && npm run build
```

Commit: `feat(agente): autoarranque en Linux portado de Rmazh (systemd, instalador, bundle test)`.

---

### Task 2: Autoarranque en macOS con launchd

**Files:**
- Create: `tools/print_agent/core/instalar-servicio-mac.sh`, `tools/print_agent/core/com.atlasone.print-agent.plist`, `tools/print_agent/core/INSTALL_MAC.txt`.
- Modify: `tools/print_agent/impresora_mac.sh` (guarda), `tools/print_agent/README.md` (fila macOS), `app/routers/printer.py` (excluir los archivos mac en windows/linux), `frontend/src/pages/pos/PrinterSettings.tsx` (AutostartCard en la tarjeta "Agente macOS", ~línea 630), `tests/test_print_agent_bundle.py` (caso mac), `docs/superpowers/runbooks/print-agent-autostart.md` (sección macOS).

**Interfaces:**
- Consumes: `AutostartCard`, `esAdmin` de la Tarea 1.
- Produces: `AUTOSTART_CMD_MAC = 'bash core/instalar-servicio-mac.sh'`; label launchd `com.atlasone.print-agent`.

- [ ] **Step 1: Plantilla del plist** `core/com.atlasone.print-agent.plist`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.atlasone.print-agent</string>
  <key>ProgramArguments</key>
  <array>
    <string>{WORKDIR}/venv/bin/python3</string>
    <string>{WORKDIR}/main.py</string>
  </array>
  <key>WorkingDirectory</key><string>{WORKDIR}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>ATLAS_AGENT_HOST</key><string>127.0.0.1</string>
    <key>ATLAS_AGENT_PORT</key><string>{PORT}</string>
    <key>ATLAS_AGENT_ORIGINS</key><string>{ORIGINS}</string>
    <key>PATH</key><string>/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>5</integer>
  <key>StandardOutPath</key><string>{LOGDIR}/agent.out.log</string>
  <key>StandardErrorPath</key><string>{LOGDIR}/agent.err.log</string>
</dict>
</plist>
```

`PATH` incluye `/usr/sbin` y `/usr/bin` porque el agente llama `lp`, `lpstat`, `lpadmin`, `lpinfo`.

- [ ] **Step 2: Instalador** `core/instalar-servicio-mac.sh`

Mismo esqueleto que `instalar-servicio-linux.sh` (log/ok/warn/die, parseo de `--origins`, `--certs-from`, `--dry-run`, `--uninstall`, `-h`). Constantes:

```bash
LABEL="com.atlasone.print-agent"
DEFAULT_ORIGINS="https://app.atlasone.com.mx"
AGENT_PORT="${ATLAS_AGENT_PORT:-9100}"
DEST="$HOME/Library/Application Support/AtlasPrintAgent"
LOGDIR="$HOME/Library/Logs/AtlasPrintAgent"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
```

Pasos del instalador (cada uno con su `log`):
1. `[ "$(uname -s)" = Darwin ]` o `die`. No correr con sudo (`[ -n "${SUDO_USER:-}" ] && die "Córrelo sin sudo"`): el LaunchAgent es del usuario.
2. `python3` presente y `python3 -c 'import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)'`; si falta: `die` con "xcode-select --install".
3. `lpstat -r` debe decir `scheduler is running`; si no, `warn` y continúa.
4. Certificado: buscar `cert.pem`+`key.pem` en `$CERTS_FROM`, `$SRC_CORE/certs`, `$DEST/certs`, `$HOME/Downloads/print_agent/core/certs`, `$HOME/Descargas/print_agent/core/certs` (primer hit gana). Imprimir "Certificado existente encontrado: <ruta>" o "No se encontró certificado previo: el navegador tendrá que aceptarlo de nuevo".
5. `--dry-run`: imprime destino, orígenes, certificado, plist, y sale 0.
6. `--uninstall`: `launchctl bootout gui/$(id -u)/$LABEL` (ignorar error), borrar `$PLIST`, dejar `$DEST` (avisar), salir.
7. Copiar `$SRC_CORE/{main.py,generate_cert.py,requirements_mac.txt,requirements.txt}` a `$DEST` (`mkdir -p`, `cp`); copiar certs si se encontraron a `$DEST/certs/`.
8. venv: `python3 -m venv "$DEST/venv"` si falta; `"$DEST/venv/bin/pip" install --quiet --upgrade pip` y `-r "$DEST/requirements_mac.txt"`. Si falla: `die`.
9. Si no hay certificado: `"$DEST/venv/bin/python3" "$DEST/generate_cert.py"` ejecutado con `cd "$DEST"` (revisa cómo `generate_cert.py` resuelve la carpeta `certs`; si usa `Path(__file__).parent`, basta con que viva en `$DEST`).
10. Plist: `mkdir -p "$LOGDIR" "$HOME/Library/LaunchAgents"`; generar desde la plantilla con `sed` sustituyendo `{WORKDIR}` → `$DEST`, `{ORIGINS}`, `{PORT}`, `{LOGDIR}` (escapa `&` y `/` o usa `python3` para la sustitución; la ruta contiene un espacio, que en plist es válido). Validar con `plutil -lint "$PLIST"` si existe `plutil`.
11. `launchctl bootout gui/$(id -u)/$LABEL 2>/dev/null || true`; `launchctl bootstrap gui/$(id -u) "$PLIST"`; `launchctl kickstart -k gui/$(id -u)/$LABEL`.
12. Esperar `/health`: bucle de hasta 60 s con `curl -sk "https://127.0.0.1:$AGENT_PORT/health"` (o `http://` si el agente arrancó sin cert; probar ambos). Éxito: imprimir el JSON y "✓ Agente instalado y respondiendo. Arranca solo al iniciar sesión; si se cae, launchd lo revive." Fallo: `die` con "revisa $LOGDIR/agent.err.log".
13. Recordatorio final: si no había certificado previo, "abre https://127.0.0.1:9100/health en el navegador del POS y acepta el certificado".

- [ ] **Step 3: Guarda en `impresora_mac.sh`**

Después del banner y antes de "[INICIO]":

```bash
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
```

- [ ] **Step 4: INSTALL_MAC.txt, README, runbook, ZIP, UI, test**

- `core/INSTALL_MAC.txt`: espejo de `INSTALL_LINUX.txt` para macOS (requisitos: macOS 12+, Xcode CLT, CUPS incluido; instalación con `bash core/instalar-servicio-mac.sh` desde la carpeta que ya usa la caja; verificación `launchctl print gui/$(id -u)/com.atlasone.print-agent`, `curl -k https://127.0.0.1:9100/health`; logs en `~/Library/Logs/AtlasPrintAgent/`; desinstalar con `--uninstall`; cola raw con `lpadmin -p ticket -E -v <uri> -m raw`).
- `README.md`: fila "macOS (servicio)" en la tabla.
- Runbook: sección "macOS" con el mismo procedimiento (dry-run → instalar → verificar).
- `printer.py`: excluir `instalar-servicio-mac.sh`, `com.atlasone.print-agent.plist`, `INSTALL_MAC.txt` en `windows` y `linux`; el ZIP `mac` los incluye.
- `PrinterSettings.tsx`: `AUTOSTART_CMD_MAC`; `AutostartCard` en la tarjeta macOS con bullets: "Se instala en ~/Library/Application Support/AtlasPrintAgent, no en Descargas.", "Arranca al iniciar sesión y launchd lo revive si se cae.", "Conserva el certificado que este navegador ya aceptó.", "No uses sudo: es un servicio de tu usuario."
- `tests/test_print_agent_bundle.py`: caso `mac` que exige `core/instalar-servicio-mac.sh`, `core/com.atlasone.print-agent.plist`, `core/INSTALL_MAC.txt`, `impresora_mac.sh` presentes y `instalar-servicio-linux.sh` ausente; y que `windows`/`linux` no traen los archivos mac.

- [ ] **Step 5: Verificar y commit**

```bash
bash -n tools/print_agent/core/instalar-servicio-mac.sh tools/print_agent/impresora_mac.sh
python3 - <<'EOF'
import plistlib, re
t = open('tools/print_agent/core/com.atlasone.print-agent.plist').read()
t = t.replace('{WORKDIR}', '/Users/x/Library/Application Support/AtlasPrintAgent').replace('{ORIGINS}', 'https://app.atlasone.com.mx').replace('{PORT}', '9100').replace('{LOGDIR}', '/Users/x/Library/Logs/AtlasPrintAgent')
d = plistlib.loads(t.encode()); assert d['Label'] == 'com.atlasone.print-agent' and d['KeepAlive'] is True; print('plist OK')
EOF
python3 -m pytest -q -p no:warnings tests/test_print_agent_bundle.py
cd frontend && npx tsc --noEmit && npm run build
```

Commit: `feat(agente): autoarranque en macOS con launchd (instalador, guarda, bundle, UI)`.
