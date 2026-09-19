# Autoarranque del agente de impresión (Linux y macOS) — diseño

**Problema.** El agente local (`tools/print_agent/core/main.py`, HTTPS en
`127.0.0.1:9100`) se arranca a mano: la cajera abre `impresora_*.sh` y deja la
ventana abierta toda la jornada; al apagar la PC hay que repetirlo. En Atlas-Rmazh
(commit `b845a33`, 2026-09-17) ya existe la conversión a servicio para Linux
(systemd) y no hay nada para macOS, que es lo que usa Eleven Fashion.

**Objetivo.** Un comando, ejecutado una vez por el administrador en la PC de la
caja, deja el agente arrancando solo al encender/iniciar sesión y reviviéndose si
se cae, sin que la cajera abra nada. Linux: systemd (portado de Rmazh). macOS:
launchd LaunchAgent.

**Decisiones.**
- Linux se porta tal cual de Rmazh (instalador, plantilla `.service`,
  `INSTALL_LINUX.txt`, guarda en `impresora_linux.sh`, README, runbook, test del
  bundle), cambiando el dominio por defecto de orígenes a
  `https://app.atlasone.com.mx` (el regex de fábrica de Atlas One ya lo cubre;
  el env queda como refuerzo explícito).
- macOS usa un **LaunchAgent de usuario** (`~/Library/LaunchAgents/
  com.atlasone.print-agent.plist`, `RunAtLoad` + `KeepAlive`), no un LaunchDaemon:
  no requiere sudo, arranca al iniciar sesión (las cajas inician sesión sola o
  con la cajera) y tiene acceso a CUPS del usuario. Instalación en
  `~/Library/Application Support/AtlasPrintAgent` (no en Descargas). Logs en
  `~/Library/Logs/AtlasPrintAgent/`.
- El instalador de macOS (`core/instalar-servicio-mac.sh`) sigue el contrato del
  de Linux: `--dry-run`, `--origins`, `--certs-from`, `--uninstall`; conserva el
  certificado ya aceptado (bundle → destino → `~/Downloads/print_agent`); crea el
  venv con `python3 -m venv` e instala `requirements_mac.txt`; escribe el plist
  desde una plantilla `core/com.atlasone.print-agent.plist` sustituyendo
  `{WORKDIR}`, `{ORIGINS}`, `{PORT}`, `{LOGDIR}`; `launchctl bootout` previo si ya
  existía, luego `launchctl bootstrap gui/$UID` + `kickstart`; no declara éxito
  hasta que `curl -k https://127.0.0.1:9100/health` responde (hasta 60 s).
- `impresora_mac.sh` gana la misma guarda que Linux: si `launchctl print
  gui/$UID/com.atlasone.print-agent` responde, muestra "El agente YA ESTÁ ACTIVO"
  y sale.
- `printer-settings`: bloque "Instalación automática" solo para ADMINISTRADOR y
  DUEÑO, en la tarjeta de Linux y en la de macOS, con el comando y botón Copiar.
- El ZIP descargable incluye los archivos nuevos según plataforma; el test del
  bundle valida que cada nombre de archivo que la pantalla dicta exista en el ZIP.
- El agente (`main.py`) NO cambia en este plan.

**Fuera de alcance.** Windows como servicio; impresoras Bluetooth; cambios al
protocolo del agente.
