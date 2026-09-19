# Atlas Print Agent

Puente local entre el navegador y la impresora térmica. Corre en la PC de la caja, expone una API HTTPS pequeña en `https://127.0.0.1:9100` y escribe bytes ESC/POS crudos en la impresora. **Versión 3.0.0**, un solo código para Windows, Linux y macOS.

```
Navegador (SPA)  ──POST /print {printer_name, content_base64}──▶  Agente :9100  ──bytes crudos──▶  Impresora
       ▲                                                                                  Windows: win32print RAW
       └── los bytes los genera el backend (/api/printer/*) o, sin red, el propio navegador   Linux: lp -d <cola>  ·  macOS: lp -d <cola> -o raw
```

El agente **no** genera tickets ni habla con el backend: recibe bytes y los entrega. El sello `ticket_printed_at` lo pone el backend solo cuando el navegador confirma que el agente respondió 2xx.

---

## Instalación en la terminal

Descarga el ZIP desde `/printer-settings` en la app (`GET /api/printer/download-agent?platform=windows|linux|mac`) o copia esta carpeta.

| SO | Comando | Qué hace |
|---|---|---|
| Windows | doble clic en `impresora_win.bat` | Crea venv, instala dependencias, genera certificado y arranca. **No se instala como servicio**: tras reiniciar la PC hay que volver a ejecutarlo |
| Linux (manual — el modo de hoy) | `bash impresora_linux.sh` | Instala CUPS si falta, venv, dependencias, certificado, grupo `lpadmin`, arranca con auto-restart. **La ventana debe quedar abierta**; hay que repetirlo cada mañana |
| Linux (servicio — el destino) | `sudo bash core/instalar-servicio-linux.sh` | Unidad systemd `atlas-print-agent` habilitada al arranque: la cajera no abre nada. Conserva el certificado ya aceptado, cae a servicio de usuario si no hay root, y verifica `/health` antes de declarar éxito. Ver `core/INSTALL_LINUX.txt` y el runbook `docs/superpowers/runbooks/print-agent-autostart.md` |
| macOS (manual — el modo de hoy) | `bash impresora_mac.sh` | Equivalente a Linux sobre el CUPS que ya trae macOS. **La ventana debe quedar abierta** |
| macOS (servicio — el destino) | `bash core/instalar-servicio-mac.sh` | LaunchAgent `com.atlasone.print-agent` (`RunAtLoad` + `KeepAlive`): arranca al iniciar sesión y launchd lo revive. **Sin sudo** — es un servicio del usuario. Instala en `~/Library/Application Support/AtlasPrintAgent`, conserva el certificado ya aceptado y verifica `/health` antes de declarar éxito. Ver `core/INSTALL_MAC.txt` y el runbook `docs/superpowers/runbooks/print-agent-autostart.md` |

Requisitos: Python 3.10+ (en macOS basta el 3.9.6 que traen las herramientas de Xcode; el agente no usa sintaxis de 3.10+). En Linux, CUPS activo y la impresora dada de alta como cola **raw**.

**macOS 14+ ya no admite colas raw** (`lpadmin … -m raw` responde *"Raw queues are no longer supported on macOS"*). Ahí la cola se crea con un **PPD genérico** y el agente fuerza el modo raw en cada impresión mandando `lp -o raw`, que salta los filtros de ese PPD. Por eso, en macOS, el diagnóstico marca **todas** las colas como `raw`: el raw no es propiedad de la cola sino del envío (`raw_mode` lo explica). Ver `core/INSTALL_MAC.txt`.

Verificación:
```bash
curl -k https://127.0.0.1:9100/health        # {"status":"ok","service":...,"version":"3.0.0","os":...}
curl -k https://127.0.0.1:9100/printers      # lista de impresoras locales
```

---

## Configuración

| Variable | Default | Uso |
|---|---|---|
| `ATLAS_AGENT_HOST` | `127.0.0.1` | Interfaz de escucha |
| `ATLAS_AGENT_PORT` | `9100` | Puerto |
| `ATLAS_AGENT_ORIGINS` | vacío | Orígenes CORS adicionales, separados por coma. **Obligatorio al servir el POS desde un dominio ajeno a los de fábrica** (p. ej. `https://pos.micliente.com`); sin él la sucursal vende pero no imprime |

Orígenes admitidos de fábrica (`allow_origin_regex` en `core/main.py`): `localhost`/`127.0.0.1` en cualquier puerto, cualquier `https://*.up.railway.app` y `https://atlasone.com.mx` con o sin subdominio — o sea la producción `https://app.atlasone.com.mx` entra sin configurar nada.

Certificado: `core/generate_cert.py` genera uno autofirmado si falta y lo renueva cuando quedan ≤7 días. Si la generación falla, el agente arranca en HTTP con advertencia.

---

## Requisitos del navegador

1. **Aceptar el certificado autofirmado** una vez: abrir `https://127.0.0.1:9100/health` y continuar.
2. **Permiso "Acceso a la red local" de Chrome.** Chrome lo pide por sitio y por PC; hasta concederlo, cada `fetch` al agente falla en el preflight aunque `/health` responda desde la barra de direcciones. El agente ya manda `Access-Control-Allow-Private-Network: true`. Un cambio de dominio del POS obliga a conceder el permiso de nuevo en cada terminal.
3. Impresoras Bluetooth no están soportadas; la app las rechaza antes de llamar al agente.

---

## API

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/`, `/health` | Estado, versión y SO |
| GET | `/ping` | `pong` |
| GET | `/diagnostics` | Reporte del sistema: spooler/CUPS, colas, certificado, versión |
| GET | `/printers` | Impresoras locales (Windows: `win32print`; *nix: `lpstat`) |
| POST | `/print` | `{printer_name, content_base64}` → escribe bytes crudos. Payload máximo 3 MB en base64 |
| POST | `/printers/test-print` | Página de prueba |
| POST | `/printers/{name}/clear-queue` | Cancela trabajos pendientes |
| POST | `/drawer/open` | Pulso ESC/POS de apertura de cajón |
| GET | `/printers/detect` | Dispositivos USB/serie detectados (Linux/mac) |
| POST | `/printers/install` | Da de alta la cola en CUPS: raw en Linux, PPD genérico en macOS |
| POST | `/printers/{queue}/pause`, `/resume`, `/uninstall` | Administración de colas CUPS |

Sin autenticación: el agente confía en que solo escucha en loopback y en el permiso de red local del navegador.

---

## Comportamiento que conviene conocer

- **"200" significa que el spooler aceptó el trabajo, no que salió papel.** Con la impresora apagada, Windows encola y el agente responde éxito. El backend sellará el ticket como impreso. Ver auditoría 2026-09-07, hallazgo C-06.
- Escrituras serializadas con un lock global; reintento 3× al abrir la impresora en Windows con mensajes por `winerror` (1801 nombre inválido, 5 acceso denegado, 1722 spooler caído).
- Si el servicio Print Spooler de Windows está detenido, el agente intenta arrancarlo.
- Log con rotación en `core/agent.log` (5 MB × 3).
- Linux: `journalctl -u atlas-print-agent -f` para el servicio. macOS: `~/Library/Logs/AtlasPrintAgent/agent.err.log`.
- **El servicio graba `ATLAS_AGENT_ORIGINS` en la unidad / el plist.** En Atlas One `app.atlasone.com.mx` ya lo cubre el regex de fábrica, así que el valor por omisión es refuerzo explícito; para un dominio propio distinto es el único camino, y sin él la caja vende pero no imprime.
- **Los nombres de los scripts que cita `/printer-settings` están bajo test** (`tests/test_print_agent_bundle.py`). En el repo de origen un renombrado al español dejó la pantalla dictando archivos inexistentes durante dos meses, lo que hizo inalcanzable el autoarranque.

---

## Pruebas

```bash
python -m pytest tests/test_print_agent_origins.py tests/test_print_agent_bundle.py -q
```

Cubren los orígenes CORS, el nombre de cola y el bundle (nombres de script citados en la UI, contenido del ZIP por plataforma, placeholders y `ATLAS_AGENT_ORIGINS` de la unidad, guardas de los launchers e instaladores, y la forma de los comandos `lp`/`lpadmin` en macOS). La escritura real (`_print_windows`, `_print_unix`) y los instaladores de shell no tienen pruebas automatizadas — cada instalador se verifica corriéndolo en una caja.
