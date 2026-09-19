"""
Atlas POS Print Agent v3 — unified cross-platform agent.

Runs on Windows / Linux / macOS. Exposes a small HTTPS API that the POS
web app calls to list printers and send raw ESC/POS bytes.

Endpoints
  GET  /           — alias de /health.
  GET  /health     — `{status, service, version, os}`.
  GET  /ping       — "pong".
  GET  /diagnostics — full cross-platform system report.
  GET  /printers   — list local printers (Windows: win32print, *nix: lpstat).
  POST /print      — body `{printer_name, content_base64}`; sends raw bytes.
  POST /printers/{name}/clear-queue — cancela trabajos pendientes
       (Windows via win32print; Linux via `cancel -a {name}`).

Features
  - Logging con rotación (agent.log, 5 MB × 3 backups).
  - Cert SSL autogenerado vía generate_cert.py si falta; arranca HTTP si
    falla (con warning).
  - Cert expiration check (cryptography); renueva si quedan ≤ 7 días.
  - Reintentos (3×) al abrir la impresora en Windows; mensajes accionables
    por winerror (1801, 5, 1722).
  - PRINTER_LOCK global para serializar escrituras.
  - Auto-inicio del Windows Print Spooler service si está detenido.
  - Payload guard (3 MB base64 máx).
  - CORS configurado para dominios Atlas + localhost.
  - Access-Control-Allow-Private-Network para Chrome PNA.
  - Config por env vars: ATLAS_AGENT_HOST, ATLAS_AGENT_PORT.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
import platform as _platform
import re
import subprocess
import sys
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ─────────────────────────────────────────────────────────────────────────────
# Platform-specific imports (lazy, best-effort)
# ─────────────────────────────────────────────────────────────────────────────
_IS_WINDOWS = _platform.system() == "Windows"
_IS_LINUX = _platform.system() == "Linux"
_IS_MAC = _platform.system() == "Darwin"

# Silence noisy WinError 10054 on Windows
if _IS_WINDOWS:
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

# win32print loads only on Windows; run postinstall if COM handlers missing.
win32print = None
_WIN32_ERROR: Optional[str] = None
if _IS_WINDOWS:
    try:
        import win32print as _win32print
        win32print = _win32print
    except ImportError as _e:
        try:
            subprocess.run(
                [sys.executable, "-m", "pywin32_postinstall", "-install"],
                check=True, capture_output=True,
            )
            import win32print as _win32print
            win32print = _win32print
        except Exception as _e2:
            _WIN32_ERROR = f"pywin32 not available: {_e2 or _e}"

# ─────────────────────────────────────────────────────────────────────────────
# Logging (rotating file + console)
# ─────────────────────────────────────────────────────────────────────────────
_LOG_FORMAT = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
_log_file = Path(__file__).parent / "agent.log"
_file_handler = RotatingFileHandler(_log_file, maxBytes=5 * 1024 * 1024, backupCount=3)
_file_handler.setFormatter(_LOG_FORMAT)
_console_handler = logging.StreamHandler()
# Force UTF-8 on Windows consoles to avoid UnicodeEncodeError on cp1252/cp850.
# errors='replace' is a safety net in case the stream ignores the encoding arg.
if hasattr(_console_handler.stream, "reconfigure"):
    try:
        _console_handler.stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
_console_handler.setFormatter(_LOG_FORMAT)

logger = logging.getLogger("AtlasPrintAgent")
logger.setLevel(logging.INFO)
logger.addHandler(_file_handler)
logger.addHandler(_console_handler)


# ─────────────────────────────────────────────────────────────────────────────
# App + middleware
# ─────────────────────────────────────────────────────────────────────────────
VERSION = "3.0.0"
MAX_PAYLOAD_BYTES = 3 * 1024 * 1024  # base64 chars

app = FastAPI(title="Atlas POS Local Print Agent", version=VERSION)

# Dominios extra vía env (separados por coma) para despliegues con dominio
# propio. Ej: ATLAS_AGENT_ORIGINS="https://pos.miempresa.com,https://app.atlasone.mx"
_ENV_ORIGINS = [o.strip() for o in os.environ.get("ATLAS_AGENT_ORIGINS", "").split(",") if o.strip()]
_CORS_ORIGINS = [
    "https://datax.up.railway.app",
    "https://qa-datax.up.railway.app",
    "https://beta-datax.up.railway.app",
    "http://localhost:5173",
    "http://localhost:3000",
    "http://localhost:8080",
    *_ENV_ORIGINS,
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    # Cubre localhost (cualquier puerto), *.up.railway.app y el dominio propio
    # atlasone.com.mx con o sin subdominio. Este ultimo es imprescindible: la
    # produccion se sirve en app.atlasone.com.mx, y sin el, el navegador bloquea
    # al agente y la tienda se queda sin tickets. Otros dominios propios siguen
    # agregandose por ATLAS_AGENT_ORIGINS.
    allow_origin_regex=(
        r"https?://(localhost|127\.0\.0\.1)(:\d+)?"
        r"|https://[a-z0-9-]+\.up\.railway\.app"
        r"|https://([a-z0-9-]+\.)?atlasone\.com\.mx"
    ),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    # Access-Control-Request-Private-Network must be in allow_headers so Chrome
    # PNA preflight is not rejected before reaching the PNA response header.
    allow_headers=["Content-Type", "Access-Control-Request-Private-Network"],
)


@app.middleware("http")
async def add_private_network_header(request: Request, call_next):
    response = await call_next(request)
    response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response


@app.options("/{path:path}")
async def preflight_handler(path: str, request: Request):
    """
    Explicit OPTIONS handler for Chrome Private Network Access (PNA) preflights.

    CORSMiddleware short-circuits OPTIONS responses before the
    add_private_network_header middleware runs, so the PNA header would be
    missing from preflights. This handler returns 200 with all required CORS
    + PNA headers so Chrome allows loopback fetch from the Railway origin.
    """
    from fastapi.responses import Response as _Response

    origin = request.headers.get("origin", "")
    headers = {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Access-Control-Request-Private-Network",
        "Access-Control-Allow-Private-Network": "true",
        "Access-Control-Max-Age": "86400",
    }
    return _Response(status_code=200, headers=headers)


# Global lock para serializar escrituras al driver
PRINTER_LOCK = threading.Lock()


_QUEUE_NAME_RE = re.compile(r"^[A-Za-z0-9_\-. ()]{1,128}$")


def _safe_queue_name(name: str) -> str:
    """
    Valida nombres de impresora/cola contra inyección.

    CUPS usa `[A-Za-z0-9_-]`. Windows permite espacios, puntos y paréntesis.
    Rechaza cualquier metacaracter de shell/path ('/', '\\', ';', '|', '&',
    '$', '`', comillas, saltos de línea). Los subprocesos se invocan con
    `shell=False`, así que el riesgo real es path-traversal o bytes nulos.
    """
    # fullmatch, no match: con `$`, `match` deja pasar un salto de linea final
    # porque `$` casa justo antes del '\n' de cierre sin consumirlo, asi que
    # "POS-80\n" pasaba pese a que este docstring afirma rechazarlos.
    if not name or not _QUEUE_NAME_RE.fullmatch(name):
        raise HTTPException(
            status_code=400,
            detail="Nombre de impresora inválido.",
        )
    return name


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — Windows Spooler
# ─────────────────────────────────────────────────────────────────────────────
def _spooler_running() -> bool:
    if not _IS_WINDOWS:
        return True
    try:
        result = subprocess.run(
            ["sc", "query", "Spooler"],
            capture_output=True, text=True, timeout=5,
        )
        return "RUNNING" in result.stdout
    except Exception:
        return False


def _start_spooler() -> bool:
    try:
        result = subprocess.run(
            ["net", "start", "Spooler"],
            capture_output=True, text=True, timeout=15,
        )
        return result.returncode == 0
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — Linux/macOS CUPS
# ─────────────────────────────────────────────────────────────────────────────
def _cups_query(args: list[str], timeout: float = 5) -> subprocess.CompletedProcess:
    """
    Ejecuta una herramienta CUPS con locale forzado a 'C' para que el
    parsing de stdout sea predecible. Sin esto, sistemas en español
    devuelven 'aceptando peticiones' en vez de 'accepting' y rompen
    todos los parsers que hacen substring-match.
    """
    env = {**os.environ, "LC_ALL": "C", "LANG": "C"}
    return subprocess.run(
        args, capture_output=True, text=True, timeout=timeout, env=env,
    )


def _cups_daemon_running() -> bool:
    """True si `lpstat -r` responde 'scheduler is running'."""
    if _IS_WINDOWS:
        return True
    try:
        result = _cups_query(["lpstat", "-r"])
        return "running" in (result.stdout or "").lower()
    except FileNotFoundError:
        return False
    except Exception:
        return False


def _which(cmd: str) -> Optional[str]:
    try:
        result = subprocess.run(
            ["which", cmd] if not _IS_WINDOWS else ["where", cmd],
            capture_output=True, text=True, timeout=3,
        )
        if result.returncode == 0:
            return result.stdout.strip().splitlines()[0]
    except Exception:
        pass
    return None


def _cups_queues_info() -> list[dict]:
    """Returns [{name, accepting, enabled, is_raw, device_uri}] for each CUPS queue."""
    if _IS_WINDOWS:
        return []
    queues: dict[str, dict] = {}

    # lpstat -v → "device for NAME: uri"
    try:
        r = _cups_query(["lpstat", "-v"])
        for line in (r.stdout or "").splitlines():
            line = line.strip()
            if line.startswith("device for "):
                rest = line[len("device for "):]
                if ":" in rest:
                    name, uri = rest.split(":", 1)
                    queues[name.strip()] = {
                        "name": name.strip(),
                        "device_uri": uri.strip(),
                        "accepting": False,
                        "enabled": False,
                        "is_raw": False,
                    }
    except Exception:
        pass

    # lpstat -a → "NAME accepting requests since ..."
    try:
        r = _cups_query(["lpstat", "-a"])
        for line in (r.stdout or "").splitlines():
            parts = line.strip().split()
            if not parts:
                continue
            name = parts[0]
            q = queues.setdefault(name, {"name": name, "device_uri": None, "accepting": False, "enabled": False, "is_raw": False})
            q["accepting"] = "accepting" in line.lower() and "not" not in line.lower()
    except Exception:
        pass

    # lpstat -p → "printer NAME is idle|busy|disabled ..."
    try:
        r = _cups_query(["lpstat", "-p"])
        for line in (r.stdout or "").splitlines():
            parts = line.strip().split()
            if len(parts) >= 2 and parts[0] == "printer":
                name = parts[1]
                q = queues.setdefault(name, {"name": name, "device_uri": None, "accepting": False, "enabled": False, "is_raw": False})
                q["enabled"] = "disabled" not in line.lower()
    except Exception:
        pass

    # lpoptions -p NAME -l → detect "raw" via printer-make-and-model
    #
    # En macOS no existen las colas raw (macOS 14+ las rechaza) y el agente
    # fuerza el raw con `lp -o raw` en cada impresión. Marcar las colas como
    # "driver" asustaría al usuario con un problema que no tiene: ahí toda cola
    # es raw de facto.
    for name, q in queues.items():
        if _IS_MAC:
            q["is_raw"] = True
            continue
        try:
            r = _cups_query(["lpstat", "-l", "-p", name])
            blob = (r.stdout or "") + (r.stderr or "")
            q["is_raw"] = "raw" in blob.lower() or "local raw printer" in blob.lower()
        except Exception:
            pass

    return list(queues.values())


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — SSL cert info
# ─────────────────────────────────────────────────────────────────────────────
def _cert_info() -> dict:
    cert_dir = Path(__file__).parent / "certs"
    cert_path = cert_dir / "cert.pem"
    if not cert_path.exists():
        return {"exists": False}
    try:
        from cryptography import x509
        from cryptography.hazmat.backends import default_backend
        import datetime as _dt
        with open(cert_path, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read(), default_backend())
        remaining = cert.not_valid_after_utc - _dt.datetime.now(_dt.timezone.utc)
        cn_attrs = cert.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
        return {
            "exists": True,
            "expires_in_days": remaining.days,
            "valid": remaining.days > 0,
            "common_name": cn_attrs[0].value if cn_attrs else "?",
        }
    except Exception as e:
        return {"exists": True, "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — Windows win32print queue mgmt
# ─────────────────────────────────────────────────────────────────────────────
def _win_clear_printer_queue(printer_name: str) -> dict:
    if not win32print:
        return {"cancelled": 0, "error": "win32print not available"}
    try:
        p_handle = win32print.OpenPrinter(printer_name)
        jobs = win32print.EnumJobs(p_handle, 0, 999, 1)
        cancelled = 0
        for job in jobs:
            try:
                win32print.SetJob(
                    p_handle, job["JobId"], 0, None,
                    win32print.JOB_CONTROL_DELETE,
                )
                cancelled += 1
            except Exception:
                pass
        win32print.ClosePrinter(p_handle)
        return {"cancelled": cancelled, "error": None}
    except Exception as e:
        return {"cancelled": 0, "error": str(e)}


def _unix_clear_printer_queue(printer_name: str) -> dict:
    try:
        r = subprocess.run(
            ["cancel", "-a", printer_name],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            return {"cancelled": 0, "error": (r.stderr or r.stdout or "unknown").strip()}
        return {"cancelled": -1, "error": None}  # cancel -a doesn't report count
    except FileNotFoundError:
        return {"cancelled": 0, "error": "cancel not found (CUPS client tools missing)"}
    except Exception as e:
        return {"cancelled": 0, "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/")
@app.get("/health")
def health_check():
    return {
        "status": "running",
        "service": "Atlas POS Print Agent",
        "version": VERSION,
        "os": _platform.system(),
    }


@app.get("/ping")
def ping():
    return "pong"


@app.get("/diagnostics")
def diagnostics():
    """Reporte cross-platform para troubleshoot desde la web app."""
    diag: dict = {
        "version": VERSION,
        "os": _platform.system(),
        "os_release": _platform.release(),
        "python": sys.version.split()[0],
        "cert": _cert_info(),
    }

    if _IS_WINDOWS:
        diag["win32print_available"] = win32print is not None
        diag["spooler_running"] = _spooler_running()
        if _WIN32_ERROR:
            diag["win32print_error"] = _WIN32_ERROR
    else:
        diag["cups_daemon_running"] = _cups_daemon_running()
        diag["lp_path"] = _which("lp")
        diag["lpstat_path"] = _which("lpstat")
        diag["lpadmin_path"] = _which("lpadmin")
        queues = _cups_queues_info()
        diag["queues_count"] = len(queues)
        diag["queues"] = queues
        diag["raw_queues_count"] = sum(1 for q in queues if q.get("is_raw"))
        diag["raw_mode"] = (
            "lp -o raw (macOS sin colas raw)" if _IS_MAC
            else "cola creada con lpadmin -m raw"
        )

    # Checklist — surface issues the UI can render
    issues: list[str] = []
    warnings: list[str] = []

    if _IS_WINDOWS:
        if not win32print:
            issues.append("pywin32 no instalado / registrado. Ejecuta impresora_win.bat como Administrador.")
        if not _spooler_running():
            issues.append("Windows Print Spooler detenido. services.msc → Print Spooler → Start.")
    else:
        if not diag.get("lp_path"):
            issues.append("Comando `lp` no encontrado. Instala CUPS: sudo apt install cups cups-client")
        if not diag.get("cups_daemon_running"):
            issues.append("CUPS no está corriendo. sudo systemctl start cups")
        if diag.get("queues_count", 0) == 0:
            if _IS_MAC:
                warnings.append(
                    "Sin colas CUPS instaladas. Usa el wizard del POS o "
                    "`sudo lpadmin -p ticket -E -v URI -P " + _MAC_GENERIC_PPD + "` "
                    "(macOS ya no admite `-m raw`; el agente fuerza raw con `lp -o raw`)."
                )
            else:
                warnings.append("Sin colas CUPS instaladas. Usa el wizard del POS o `sudo lpadmin -p NAME -E -v URI -m raw`.")
        elif diag.get("raw_queues_count", 0) == 0:
            warnings.append("Ninguna cola está en modo raw. Para térmicas POS re-crea la cola con `-m raw`.")

    cert = diag["cert"]
    if not cert.get("exists"):
        warnings.append("Sin certificado SSL. El agente arranca en HTTP y el navegador puede bloquear la conexión.")
    elif cert.get("expires_in_days") is not None and cert["expires_in_days"] <= 7:
        warnings.append(f"Certificado SSL vence en {cert['expires_in_days']} días. Se renovará en el próximo arranque.")

    diag["issues"] = issues
    diag["warnings"] = warnings
    diag["healthy"] = not issues
    return diag


@app.get("/printers")
def list_printers():
    """List local printers (Windows: win32print, *nix: lpstat -a)."""
    if _IS_WINDOWS:
        if not win32print:
            return {"printers": [], "error": _WIN32_ERROR or "win32print not available"}
        try:
            printers = win32print.EnumPrinters(
                win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
            )
            return {"printers": [p[2] for p in printers]}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    try:
        result = subprocess.run(
            ["lpstat", "-a"], capture_output=True, text=True, timeout=5,
        )
        names = [
            line.split()[0]
            for line in (result.stdout or "").strip().splitlines()
            if line.strip()
        ]
        return {"printers": names}
    except FileNotFoundError:
        return {"printers": [], "error": "CUPS no instalado. sudo apt install cups cups-client"}
    except Exception as e:
        return {"printers": [], "error": str(e)}


@app.post("/printers/{printer_name}/clear-queue")
def clear_queue(printer_name: str):
    """Cancela todos los trabajos pendientes para `printer_name`."""
    printer_name = _safe_queue_name(printer_name)
    if _IS_WINDOWS:
        result = _win_clear_printer_queue(printer_name)
    else:
        result = _unix_clear_printer_queue(printer_name)
    if result.get("error"):
        raise HTTPException(status_code=500, detail=f"Error clearing queue: {result['error']}")
    return {"status": "ok", "cancelled_jobs": result.get("cancelled", 0)}


class PrintJob(BaseModel):
    printer_name: str
    content_base64: str


class InstallPrinterRequest(BaseModel):
    uri: str
    queue_name: str
    set_default: bool = False


class TestPrintRequest(BaseModel):
    printer_name: str
    paper_width_mm: int = 80


class SystemSetupRequest(BaseModel):
    # Si False, solo instala CUPS sin los paquetes de drivers de impresora.
    include_drivers: bool = True


class OpenDrawerRequest(BaseModel):
    printer_name: str


# ESC/POS drawer-kick bytes: ESC p m t1 t2 — pin 2, 25ms on, 250ms off.
# Compatible con la mayoría de cajones RJ-11 conectados a térmicas POS.
_DRAWER_KICK_BYTES = b"\x1B\x70\x00\x19\xFA"


@app.post("/drawer/open")
def open_drawer(req: OpenDrawerRequest):
    """
    Abre el cajón de dinero conectado a la impresora indicada enviando
    la secuencia ESC/POS 'drawer kick' sin imprimir contenido.

    Útil para: apertura de sesión de caja, cash-in/cash-out manuales,
    verificar que el cable del cajón está conectado.
    """
    printer_name = _safe_queue_name(req.printer_name)
    if _IS_WINDOWS:
        result = _print_windows(printer_name, _DRAWER_KICK_BYTES)
    else:
        result = _print_unix(printer_name, _DRAWER_KICK_BYTES)
    logger.info(f"Drawer kick -> {printer_name}")
    return {**result, "action": "drawer_open"}


def _build_test_ticket(paper_width_mm: int) -> bytes:
    """
    Genera un ticket de prueba ESC/POS en la propia impresora — auto-contenido,
    no depende de Atlas backend ni de un template Jinja. Sirve para validar que
    la cola está bien configurada recién instalada.

    Usa la plantilla validada en context/contexto_agente_impresion_linux.md
    (56 cols + fuente compacta para 80mm; 32 cols + Font A para 58mm).
    """
    from datetime import datetime as _dt

    cols = 56 if paper_width_mm >= 70 else 32
    # ESC @ (init) + ESC M 1 (Font B compact para 80mm) o ESC M 0 (Font A para 58mm)
    init = b"\x1b\x40" + (b"\x1b\x4d\x01" if paper_width_mm >= 70 else b"\x1b\x4d\x00")
    sep = ("=" * cols + "\n").encode("latin-1", "replace")
    dash = ("-" * cols + "\n").encode("latin-1", "replace")

    def _center(text: str) -> bytes:
        if len(text) >= cols:
            return (text + "\n").encode("latin-1", "replace")
        pad = (cols - len(text)) // 2
        return ((" " * pad) + text + "\n").encode("latin-1", "replace")

    def _row(left: str, right: str) -> bytes:
        space = max(1, cols - len(left) - len(right))
        return (left + (" " * space) + right + "\n").encode("latin-1", "replace")

    now = _dt.now()
    raw = b""
    raw += init
    raw += sep
    raw += _center("ATLAS POS")
    raw += _center("TICKET DE PRUEBA")
    raw += sep
    raw += _row("Fecha:", now.strftime("%Y-%m-%d"))
    raw += _row("Hora:", now.strftime("%H:%M:%S"))
    raw += _row("Ancho:", f"{paper_width_mm}mm / {cols} cols")
    raw += dash
    raw += _center("Si esta linea llega al borde derecho,")
    raw += _center("el ancho esta configurado correctamente.")
    raw += _center("|" + "-" * (cols - 2) + "|")
    raw += dash
    raw += _center("Impresora instalada con exito.")
    raw += _center("Puedes cerrar el asistente.")
    raw += b"\n\n\n\n"
    # GS V 0 (cut full) si la impresora lo soporta
    raw += b"\x1d\x56\x00"
    return raw


@app.post("/printers/test-print")
def test_print_on_queue(req: TestPrintRequest):
    """
    Imprime un ticket de prueba auto-contenido en la cola especificada.

    Útil después de instalar una impresora nueva para verificar que la cola
    está en modo raw y el ancho/fuente son correctos, sin salir al POS.
    """
    raw = _build_test_ticket(req.paper_width_mm)

    if _IS_WINDOWS:
        return _print_windows(req.printer_name, raw)
    return _print_unix(req.printer_name, raw)


# ─────────────────────────────────────────────────────────────────────────────
# Auto-install (Linux/macOS via CUPS)
# ─────────────────────────────────────────────────────────────────────────────
# Known URI patterns → suggested queue name + friendly label.
_PRINTER_PROFILES = [
    {
        "match": lambda uri: "POS80" in uri,
        "brand": "Nextep / Generic 80mm",
        "model": "POS80",
        "queue_suggestion": "nextep80",
        "paper_width_mm": 80,
    },
    {
        "match": lambda uri: "BIXOLON" in uri.upper() and "SRP-330" in uri.upper(),
        "brand": "BIXOLON",
        "model": "SRP-330II",
        "queue_suggestion": "bixolon80",
        "paper_width_mm": 80,
    },
    {
        "match": lambda uri: "BIXOLON" in uri.upper(),
        "brand": "BIXOLON",
        "model": "genérico",
        "queue_suggestion": "bixolon",
        "paper_width_mm": 80,
    },
    {
        "match": lambda uri: "EPSON" in uri.upper() and "TM-T" in uri.upper(),
        "brand": "Epson",
        "model": "TM-T (térmica)",
        "queue_suggestion": "epson80",
        "paper_width_mm": 80,
    },
    {
        "match": lambda uri: "STAR" in uri.upper(),
        "brand": "Star Micronics",
        "model": "Star",
        "queue_suggestion": "star80",
        "paper_width_mm": 80,
    },
]


def _match_profile(uri: str) -> dict:
    for prof in _PRINTER_PROFILES:
        try:
            if prof["match"](uri):
                return {
                    "brand": prof["brand"],
                    "model": prof["model"],
                    "queue_suggestion": prof["queue_suggestion"],
                    "paper_width_mm": prof["paper_width_mm"],
                }
        except Exception:
            continue
    # Fallback para cualquier térmica USB desconocida
    return {
        "brand": "Impresora USB",
        "model": "genérica",
        "queue_suggestion": "thermal80",
        "paper_width_mm": 80,
    }


@app.get("/printers/detect")
def detect_printers():
    """
    Escanea dispositivos de impresión con `lpinfo -v` y sugiere config.
    Solo Linux/macOS (CUPS). En Windows retorna una lista vacía con nota.
    """
    if _IS_WINDOWS:
        return {
            "candidates": [],
            "note": "Detect auto solo en Linux/macOS. En Windows usa el panel de impresoras del sistema.",
        }

    lpinfo = _which("lpinfo")
    if not lpinfo:
        raise HTTPException(
            status_code=500,
            detail="`lpinfo` no encontrado. Instala CUPS: sudo apt install cups cups-client",
        )

    try:
        r = subprocess.run(
            ["lpinfo", "-v"], capture_output=True, text=True, timeout=10,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="lpinfo timeout")

    candidates: list[dict] = []
    for line in (r.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        # Formato: "kind uri", p.ej. "direct usb://BIXOLON/SRP-330II?serial=00000001"
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        kind, uri = parts
        # Nos interesan solo USB y socket (red) directos.
        if kind not in ("direct", "network"):
            continue
        if not (uri.startswith("usb://") or uri.startswith("socket://")):
            continue
        prof = _match_profile(uri)
        candidates.append({
            "kind": kind,
            "uri": uri,
            **prof,
        })

    return {"candidates": candidates, "count": len(candidates)}


# PPD genérico de macOS. Desde macOS 14 `lpadmin -m raw` responde "Raw queues
# are no longer supported on macOS", así que la cola se crea con este PPD y el
# raw lo fuerza `lp -o raw` en cada impresión.
_MAC_GENERIC_PPD = (
    "/System/Library/Frameworks/ApplicationServices.framework/Versions/A"
    "/Frameworks/PrintCore.framework/Versions/A/Resources/Generic.ppd"
)


def _mac_generic_ppd_args() -> Optional[list[str]]:
    """Argumentos de modelo para `lpadmin` en macOS, o None si no hay ninguno."""
    if Path(_MAC_GENERIC_PPD).exists():
        return ["-P", _MAC_GENERIC_PPD]
    # Respaldo: el driver de ejemplo que CUPS trae compilado.
    return ["-m", "drv:///sample.drv/generic.ppd"]


@app.post("/printers/install")
def install_printer(req: InstallPrinterRequest):
    """
    Crea una cola CUPS + enable + accept.

    Linux: cola en modo raw (`-m raw`), que es lo que quiere una térmica.

    macOS 14+: CUPS ya NO admite colas raw ("Raw queues are no longer supported
    on macOS"), así que la cola se crea con un PPD genérico y el modo raw se
    fuerza en cada impresión con `lp -o raw` (ver `_print_unix`).

    Requiere que el usuario que ejecuta el agente tenga `lpadmin` en sus
    grupos (el launcher `impresora_linux.sh` lo agrega automáticamente).
    Si no, los comandos `lpadmin` fallarán con permiso denegado.
    """
    if _IS_WINDOWS:
        raise HTTPException(
            status_code=400,
            detail="Install via API solo en Linux/macOS. En Windows usa 'Agregar impresora' del sistema.",
        )

    lpadmin = _which("lpadmin")
    if not lpadmin:
        raise HTTPException(
            status_code=500,
            detail="`lpadmin` no encontrado. Instala CUPS: sudo apt install cups",
        )

    # install_printer aplica un sanitizado distinto: el cliente puede mandar
    # nombres humanos que se normalizan a un slug CUPS-safe. No usamos
    # _safe_queue_name aquí porque queremos normalizar en vez de rechazar.
    qname = re.sub(r"[^a-zA-Z0-9_-]", "", req.queue_name).strip() or "thermal80"
    if qname != req.queue_name:
        logger.info(f"queue_name sanitizado: {req.queue_name!r} -> {qname!r}")

    steps: list[dict] = []

    def _run_step(label: str, cmd: list[str]) -> bool:
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            ok = p.returncode == 0
            steps.append({
                "label": label,
                "cmd": " ".join(cmd),
                "ok": ok,
                "stdout": (p.stdout or "").strip(),
                "stderr": (p.stderr or "").strip(),
            })
            return ok
        except Exception as e:
            steps.append({"label": label, "cmd": " ".join(cmd), "ok": False, "error": str(e)})
            return False

    # 1. lpadmin -p NAME -E -v URI  (+ modelo según el sistema)
    if _IS_MAC:
        modelo = _mac_generic_ppd_args()
        if modelo is None:
            raise HTTPException(
                status_code=500,
                detail=(
                    "macOS ya no admite colas raw. Crea la cola con un PPD genérico: "
                    "lpinfo -m | grep -i generic  — y después "
                    f"sudo lpadmin -p {qname} -E -v {req.uri} -P <ruta del PPD genérico>"
                ),
            )
    else:
        modelo = ["-m", "raw"]

    ok1 = _run_step(
        "lpadmin",
        ["lpadmin", "-p", qname, "-E", "-v", req.uri, *modelo],
    )
    if not ok1:
        err = steps[-1].get("stderr") or steps[-1].get("error") or "unknown"
        if _IS_MAC:
            raise HTTPException(
                status_code=500,
                detail=(
                    "No se pudo crear la cola en macOS (" + err[:160] + "). "
                    "Agrégala desde Ajustes del Sistema → Impresoras y escáneres → "
                    "Agregar impresora, con el driver 'Epson 9-Pin Series'; el agente "
                    "imprime con -o raw y el driver no interviene."
                ),
            )
        if "denied" in err.lower() or "permission" in err.lower():
            raise HTTPException(
                status_code=500,
                detail=(
                    "Permiso denegado al crear la cola. El usuario del agente no está en "
                    "el grupo 'lpadmin'. Ejecuta en terminal: "
                    "sudo usermod -aG lpadmin $USER  "
                    "— luego cierra sesión y vuelve a entrar."
                ),
            )
        raise HTTPException(status_code=500, detail=f"lpadmin falló: {err}")

    # 2. cupsenable NAME
    _run_step("cupsenable", ["cupsenable", qname])

    # 3. cupsaccept NAME
    _run_step("cupsaccept", ["cupsaccept", qname])

    # 4. (opcional) setear como default
    if req.set_default:
        _run_step("lpoptions -d", ["lpoptions", "-d", qname])

    logger.info(f"Printer installed: {qname} <- {req.uri}")
    return {
        "status": "installed",
        "queue_name": qname,
        "uri": req.uri,
        "steps": steps,
    }


def _detect_pkg_manager() -> Optional[dict]:
    """Detecta el gestor de paquetes del sistema y devuelve el plan de instalación.

    Returns {name, packages_core, packages_drivers, build(script_body)} o None
    si no se reconoce. Solo Linux."""
    if _which("apt-get"):
        return {
            "name": "apt",
            "core": ["cups", "cups-client", "cups-bsd"],
            "drivers": ["printer-driver-escpr", "printer-driver-gutenprint", "system-config-printer"],
            "update": "apt-get update",
            "install": "DEBIAN_FRONTEND=noninteractive apt-get install -y",
        }
    if _which("dnf"):
        return {
            "name": "dnf",
            "core": ["cups", "cups-client"],
            "drivers": ["gutenprint", "epson-inkjet-printer-escpr"],
            "update": "dnf -y makecache",
            "install": "dnf install -y",
        }
    if _which("pacman"):
        return {
            "name": "pacman",
            "core": ["cups", "cups-pdf"],
            "drivers": ["gutenprint"],
            "update": "pacman -Sy --noconfirm",
            "install": "pacman -S --noconfirm",
        }
    if _which("zypper"):
        return {
            "name": "zypper",
            "core": ["cups", "cups-client"],
            "drivers": ["gutenprint"],
            "update": "zypper --non-interactive refresh",
            "install": "zypper --non-interactive install",
        }
    return None


@app.post("/system/setup")
def system_setup(req: SystemSetupRequest):
    """Actualiza el sistema e instala lo necesario para imprimir: CUPS, drivers
    comunes, arranca el demonio y agrega al usuario al grupo de administración
    de impresión. Requiere privilegios → usa `pkexec` (diálogo gráfico) o
    `sudo -n`. Solo Linux."""
    if _IS_WINDOWS:
        raise HTTPException(status_code=400, detail="Solo Linux. En Windows usa Windows Update y 'Agregar impresora'.")
    if _IS_MAC:
        raise HTTPException(status_code=400, detail="En macOS CUPS ya viene incluido; no requiere instalación de drivers.")

    plan = _detect_pkg_manager()
    if not plan:
        raise HTTPException(
            status_code=500,
            detail="Gestor de paquetes no reconocido (no apt/dnf/pacman/zypper). Instala CUPS manualmente.",
        )

    # Usuario real (antes de elevar; dentro de pkexec $USER sería root).
    target_user = os.environ.get("SUDO_USER") or os.environ.get("USER") or os.environ.get("LOGNAME") or ""
    target_user = re.sub(r"[^a-zA-Z0-9_.-]", "", target_user)

    pkgs = list(plan["core"]) + (list(plan["drivers"]) if req.include_drivers else [])
    lines = [
        "set -e",
        plan["update"],
        f"{plan['install']} {' '.join(pkgs)}",
        "systemctl enable --now cups 2>/dev/null || systemctl enable --now cups.service 2>/dev/null || true",
    ]
    if target_user:
        # apt usa 'lpadmin'; otras distros suelen usar 'lp'/'sys'. Best-effort.
        lines.append(
            f'usermod -aG lpadmin "{target_user}" 2>/dev/null '
            f'|| usermod -aG lp "{target_user}" 2>/dev/null || true'
        )
    script = "\n".join(lines)

    # Elegir mecanismo de elevación.
    if _which("pkexec"):
        cmd = ["pkexec", "bash", "-c", script]
        elevation = "pkexec"
    elif _which("sudo"):
        cmd = ["sudo", "-n", "bash", "-c", script]
        elevation = "sudo -n"
    else:
        raise HTTPException(
            status_code=500,
            detail=(
                "No hay forma de elevar privilegios (falta pkexec y sudo). "
                f"Ejecuta manualmente en terminal: sudo bash -c '{script}'"
            ),
        )

    logger.info(f"system_setup via {elevation} ({plan['name']}): {pkgs}")
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="La instalación excedió el tiempo límite (10 min).")

    ok = p.returncode == 0
    stderr = (p.stderr or "").strip()
    if not ok:
        low = stderr.lower()
        if "dismiss" in low or "authentication" in low or "not authorized" in low or p.returncode == 126:
            raise HTTPException(status_code=403, detail="Autorización cancelada o denegada. Acepta el diálogo de administrador y reintenta.")
        if elevation == "sudo -n" and ("password" in low or "a terminal is required" in low):
            raise HTTPException(
                status_code=403,
                detail="sudo requiere contraseña y no hay diálogo gráfico (pkexec/policykit). Instala 'policykit-1' o corre el agente desde una terminal con sudo disponible.",
            )

    return {
        "status": "ok" if ok else "error",
        "package_manager": plan["name"],
        "elevation": elevation,
        "user": target_user or None,
        "packages": pkgs,
        "returncode": p.returncode,
        "stdout": (p.stdout or "").strip()[-4000:],
        "stderr": stderr[-4000:],
        # Cambio de grupo requiere re-login para que `lpadmin` aplique sin sudo.
        "needs_relogin": ok and bool(target_user),
    }


@app.post("/system/spooler-repair")
def spooler_repair():
    """Windows: deja el Print Spooler en inicio automático y lo arranca.

    Requiere privilegios. Intenta directo (si el agente ya es Administrador) y,
    si falla, eleva con UAC vía `Start-Process -Verb RunAs`. Tras elevar no se
    puede capturar la salida del proceso elevado, así que se sondea el estado
    del servicio para confirmar."""
    if not _IS_WINDOWS:
        raise HTTPException(status_code=400, detail="Solo Windows. En Linux usa 'Actualizar sistema y drivers'.")

    was_running = _spooler_running()
    steps: list[dict] = []

    def _run(label: str, cmd: list[str]) -> bool:
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            steps.append({"label": label, "ok": p.returncode == 0,
                          "stdout": (p.stdout or "").strip(), "stderr": (p.stderr or "").strip()})
            return p.returncode == 0
        except Exception as e:
            steps.append({"label": label, "ok": False, "error": str(e)})
            return False

    # 1) Intento directo (funciona si el agente corre como Administrador).
    _run("sc config", ["sc", "config", "Spooler", "start=", "auto"])
    _run("net start", ["net", "start", "Spooler"])  # exit 2 = ya estaba arrancado

    # 2) Si sigue sin correr, elevar con UAC.
    if not _spooler_running():
        ps_cmd = (
            "Start-Process -FilePath cmd.exe -Verb RunAs -WindowStyle Hidden "
            "-ArgumentList '/c sc config Spooler start= auto & net start Spooler'"
        )
        try:
            p = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True, text=True, timeout=60,
            )
            steps.append({"label": "UAC elevate", "ok": p.returncode == 0,
                          "stderr": (p.stderr or "").strip()})
            if p.returncode != 0:
                raise HTTPException(
                    status_code=403,
                    detail="Elevación cancelada o denegada (UAC). Acepta el diálogo de Administrador y reintenta.",
                )
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=500, detail="Tiempo agotado esperando el diálogo de Administrador.")
        # El proceso elevado es asíncrono: sondear hasta ~8s.
        for _ in range(16):
            if _spooler_running():
                break
            time.sleep(0.5)

    running = _spooler_running()
    logger.info(f"spooler_repair: was_running={was_running} running={running}")
    return {
        "status": "ok" if running else "error",
        "running": running,
        "was_running": was_running,
        "steps": steps,
        "message": (
            "Print Spooler activo y en inicio automático."
            if running else
            "No se pudo iniciar el Print Spooler. Inícialo manualmente: services.msc → Print Spooler → Iniciar."
        ),
    }


@app.post("/printers/{queue_name}/pause")
def pause_printer(queue_name: str):
    """Pausa la cola (cupsdisable) para que CUPS deje de enviar trabajos."""
    if _IS_WINDOWS:
        raise HTTPException(status_code=400, detail="Pause via API solo en Linux/macOS")
    queue_name = _safe_queue_name(queue_name)
    try:
        p = subprocess.run(
            ["cupsdisable", queue_name],
            capture_output=True, text=True, timeout=5,
        )
        if p.returncode != 0:
            raise HTTPException(status_code=500, detail=(p.stderr or p.stdout).strip())
        logger.info(f"Printer paused: {queue_name}")
        return {"status": "paused", "queue_name": queue_name}
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="cupsdisable timeout")


@app.post("/printers/{queue_name}/resume")
def resume_printer(queue_name: str):
    """Reactiva la cola (cupsenable + cupsaccept)."""
    if _IS_WINDOWS:
        raise HTTPException(status_code=400, detail="Resume via API solo en Linux/macOS")
    queue_name = _safe_queue_name(queue_name)
    errors: list[str] = []
    for cmd in (["cupsenable", queue_name], ["cupsaccept", queue_name]):
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if p.returncode != 0:
                errors.append(f"{cmd[0]}: {(p.stderr or p.stdout).strip()}")
        except Exception as e:
            errors.append(f"{cmd[0]}: {e}")
    if errors:
        raise HTTPException(status_code=500, detail="; ".join(errors))
    logger.info(f"Printer resumed: {queue_name}")
    return {"status": "resumed", "queue_name": queue_name}


@app.post("/printers/{queue_name}/uninstall")
def uninstall_printer(queue_name: str):
    """Elimina una cola CUPS (lpadmin -x)."""
    if _IS_WINDOWS:
        raise HTTPException(status_code=400, detail="Uninstall via API solo en Linux/macOS")
    queue_name = _safe_queue_name(queue_name)

    lpadmin = _which("lpadmin")
    if not lpadmin:
        raise HTTPException(status_code=500, detail="lpadmin no encontrado")

    try:
        p = subprocess.run(
            ["lpadmin", "-x", queue_name],
            capture_output=True, text=True, timeout=10,
        )
        if p.returncode != 0:
            err = (p.stderr or "").strip()
            if "denied" in err.lower() or "permission" in err.lower():
                raise HTTPException(
                    status_code=500,
                    detail="Permiso denegado. Usuario no está en grupo lpadmin.",
                )
            raise HTTPException(status_code=500, detail=f"lpadmin -x falló: {err}")
        logger.info(f"Printer uninstalled: {queue_name}")
        return {"status": "uninstalled", "queue_name": queue_name}
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="lpadmin -x timeout")


@app.post("/print")
def print_raw(job: PrintJob):
    """Envía bytes raw ESC/POS a la impresora."""
    if len(job.content_base64) > MAX_PAYLOAD_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Payload demasiado grande (máx {MAX_PAYLOAD_BYTES // 1024 // 1024} MB)",
        )

    try:
        raw_data = base64.b64decode(job.content_base64)
    except Exception as e:
        logger.warning(f"Invalid Base64: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid Base64: {e}")

    printer_name = _safe_queue_name(job.printer_name)
    if _IS_WINDOWS:
        return _print_windows(printer_name, raw_data)
    return _print_unix(printer_name, raw_data)


def _print_windows(printer_name: str, raw_data: bytes) -> dict:
    if not win32print:
        raise HTTPException(
            status_code=500,
            detail="win32print no disponible. Ejecuta impresora_win.bat como Administrador.",
        )
    if not _spooler_running():
        logger.warning("Spooler not running -- attempting to start...")
        if not _start_spooler():
            raise HTTPException(
                status_code=500,
                detail="Windows Print Spooler detenido. services.msc → Print Spooler → Start.",
            )
        # Poll en lugar de sleep(2) fijo: libera el threadpool en cuanto
        # el servicio reporta RUNNING (guard: 2s máx, 8 iteraciones).
        for _ in range(8):
            if _spooler_running():
                break
            time.sleep(0.25)

    with PRINTER_LOCK:
        p_handle = None
        try:
            max_retries = 3
            last_exc: Optional[Exception] = None
            for attempt in range(max_retries):
                try:
                    p_handle = win32print.OpenPrinter(printer_name)
                    break
                except Exception as e:
                    last_exc = e
                    if attempt < max_retries - 1:
                        logger.warning(f"Retry {attempt + 1}/{max_retries} open '{printer_name}': {e}")
                        time.sleep(0.5)
                    else:
                        error_code = getattr(e, "winerror", None)
                        detail = f"No se pudo abrir '{printer_name}'"
                        if error_code == 1801:
                            detail += " — impresora no encontrada. Verifica el nombre con GET /printers."
                        elif error_code == 5:
                            detail += " — acceso denegado. Ejecuta el agente como Administrador."
                        elif error_code == 1722:
                            detail += " — RPC server unavailable. Reinicia Print Spooler."
                        else:
                            detail += f" (winerror={error_code}): {last_exc}"
                        raise HTTPException(status_code=500, detail=detail)

            win32print.StartDocPrinter(p_handle, 1, ("AtlasPOS Ticket", None, "RAW"))
            try:
                win32print.StartPagePrinter(p_handle)
                win32print.WritePrinter(p_handle, raw_data)
                win32print.EndPagePrinter(p_handle)
            finally:
                win32print.EndDocPrinter(p_handle)

            logger.info(f"Windows: sent {len(raw_data)} bytes to '{printer_name}'")
            return {"status": "success", "bytes": len(raw_data), "printer": printer_name}
        except HTTPException:
            raise
        except Exception as e:
            error_code = getattr(e, "winerror", None)
            logger.error(f"Windows print failed '{printer_name}' (winerror={error_code}): {e}")
            raise HTTPException(status_code=500, detail=f"Print error (winerror={error_code}): {e}")
        finally:
            if p_handle:
                try:
                    win32print.ClosePrinter(p_handle)
                except Exception:
                    pass


def _print_unix(printer_name: str, raw_data: bytes) -> dict:
    """
    Envía bytes directamente a la cola CUPS.

    Linux: no se pasa `-o raw`. La cola debe estar creada en modo raw
    (`lpadmin -m raw`); el flag forzaría raw contra drivers no-raw. Si la cola
    tiene driver, CUPS intentará procesarla como texto y puede salir texto
    corrupto — es síntoma de configuración incorrecta, no del agente.

    macOS: sí se pasa `-o raw`, y es obligatorio. Desde macOS 14 CUPS rechaza
    crear colas raw ("Raw queues are no longer supported on macOS"), así que la
    cola de la térmica se crea con un PPD genérico. `-o raw` le dice a CUPS que
    salte los filtros de ese PPD y entregue los bytes ESC/POS tal cual. Sin el
    flag, el PPD genérico reinterpreta el ticket y sale basura.
    """
    with PRINTER_LOCK:
        try:
            # macOS: el PPD genérico filtraría los bytes ESC/POS; -o raw lo evita.
            cmd = (["lp", "-d", printer_name, "-o", "raw", "-"] if _IS_MAC
                   else ["lp", "-d", printer_name, "-"])
            proc = subprocess.run(
                cmd, input=raw_data, capture_output=True, timeout=10,
            )
            if proc.returncode != 0:
                err = (proc.stderr or b"").decode(errors="replace").strip()
                logger.error(f"lp failed '{printer_name}': {err}")
                raise HTTPException(status_code=500, detail=f"lp error: {err}")
            # Parse CUPS job id from stdout: "request id is NAME-NN (1 file(s))"
            stdout = (proc.stdout or b"").decode(errors="replace").strip()
            job_id = None
            if "request id is" in stdout:
                try:
                    job_id = stdout.split("request id is", 1)[1].split()[0]
                except Exception:
                    pass
            logger.info(f"Unix: sent {len(raw_data)} bytes to '{printer_name}' (job_id={job_id})")
            return {
                "status": "success",
                "bytes": len(raw_data),
                "printer": printer_name,
                "job_id": job_id,
            }
        except HTTPException:
            raise
        except FileNotFoundError:
            raise HTTPException(
                status_code=500,
                detail="`lp` no encontrado. Instala CUPS: sudo apt install cups cups-client",
            )
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=500, detail="lp timeout — impresora sin respuesta")


# ─────────────────────────────────────────────────────────────────────────────
# Entrypoint
# ─────────────────────────────────────────────────────────────────────────────
def _ensure_certs() -> tuple[Optional[Path], Optional[Path]]:
    """Genera certs si faltan o están por vencer. Retorna (key, cert) o (None, None)."""
    cert_dir = Path(__file__).parent / "certs"
    key_file = cert_dir / "key.pem"
    cert_file = cert_dir / "cert.pem"

    need_generate = not (key_file.exists() and cert_file.exists())
    if not need_generate:
        # Chequeo de expiración
        info = _cert_info()
        if info.get("expires_in_days") is not None and info["expires_in_days"] <= 7:
            logger.info(f"SSL cert vence en {info['expires_in_days']} dias -> regenerando")
            need_generate = True

    if need_generate:
        gen_script = Path(__file__).parent / "generate_cert.py"
        if gen_script.exists():
            try:
                logger.info("Generando certificados SSL...")
                subprocess.run([sys.executable, str(gen_script)], check=True, timeout=30)
            except Exception as e:
                logger.warning(f"Fallo generate_cert.py: {e}. Arrancara en HTTP.")
                return None, None
        else:
            logger.warning("generate_cert.py no existe. Arrancara en HTTP.")
            return None, None

    if key_file.exists() and cert_file.exists():
        return key_file, cert_file
    return None, None


if __name__ == "__main__":
    port = int(os.environ.get("ATLAS_AGENT_PORT", 9100))
    host = os.environ.get("ATLAS_AGENT_HOST", "127.0.0.1")

    # Version banner — helps identify legacy installs that were not updated.
    # IMPORTANT: ensure all stations run the same version shown here.
    _build_mtime = Path(__file__).stat().st_mtime
    import datetime as _dt_mod
    _build_ts = _dt_mod.datetime.fromtimestamp(_build_mtime).strftime("%Y-%m-%d %H:%M")
    print(
        f"\n"
        f"  +==================================================+\n"
        f"  |  Atlas Print Agent  v{VERSION:<28}|\n"
        f"  |  OS: {_platform.system():<44}|\n"
        f"  |  Python: {sys.version.split()[0]:<40}|\n"
        f"  |  Build:  {_build_ts:<40}|\n"
        f"  |  [!] Ensure all POS stations run this version    |\n"
        f"  +==================================================+\n",
        flush=True,
    )

    logger.info(f"Atlas Print Agent v{VERSION} -- OS={_platform.system()} Python={sys.version.split()[0]}")

    if _IS_WINDOWS and not _spooler_running():
        logger.warning("Print Spooler service detenido -- intentando arrancarlo...")
        if _start_spooler():
            logger.info("Print Spooler arrancado.")
        else:
            logger.warning("No se pudo arrancar Print Spooler. Abre services.msc manualmente.")

    key_file, cert_file = _ensure_certs()
    ssl_config: dict = {}
    if key_file and cert_file:
        logger.info(f"SSL OK -> https://{host}:{port}")
        ssl_config = {"ssl_keyfile": str(key_file), "ssl_certfile": str(cert_file)}
    else:
        logger.warning(f"Sin SSL -> http://{host}:{port}  (el navegador puede bloquear la conexion)")

    try:
        uvicorn.run(app, host=host, port=port, log_level="info", **ssl_config)
    except Exception as e:
        logger.error(f"[FATAL] Uvicorn fallo: {e}")
        if ssl_config:
            logger.error(f"cert={cert_file} exists={cert_file.exists()}")
            logger.error(f"key={key_file} exists={key_file.exists()}")
        import traceback
        traceback.print_exc()
        raise
