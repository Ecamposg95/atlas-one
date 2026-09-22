from fastapi import FastAPI, Request, Depends, status
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
from app.core.database import get_db
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, RedirectResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone
from app.modules.platform.dependencies import require_platform_admin
from app.core.database import engine
from app.models import Base
from app.routers import (
    auth, users, branches, products,
    inventory, sales, cash, customers, reports,
    printer, returns, quotes, organization, hr, portal, logistics,
    platform, transfers, purchases, expenses, branch,
    announcements,
)
from app.subscribers.abasto import setup_abasto_subscribers

import os
import sys
import json
import logging

# LOG_JSON=true: cada línea de log sale como JSON de un campo por nivel en
# vez de texto plano, para que Railway pueda filtrar por campo (ej. `org`,
# `branch`, `slow` de app/observability/timing.py). record.atlas (dict) se
# sube al primer nivel del payload — lo pone TimingMiddleware via `extra`.
LOG_JSON = os.getenv("LOG_JSON", "false").lower() == "true"


class _JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "time": self.formatTime(record),
        }
        extra = getattr(record, "atlas", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


# Logging básico hacia stderr — garantiza que los tracebacks lleguen a docker logs
# incluso cuando uvicorn corre en worker spawn (reload mode). Idempotente.
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )
    if LOG_JSON:
        for _h in logging.getLogger().handlers:
            _h.setFormatter(_JsonLogFormatter())

# 1.5 USERS BOOTSTRAP
if os.getenv("INIT_USERS_ON_BOOT") == "true":
    try:
        print("Bootstrapping users (INIT_USERS_ON_BOOT=true)...")
        from scripts.init_users import init_users
        init_users()
    except Exception as e:
        print(f"Error bootstrapping users: {e}")

app = FastAPI(
    title="Atlas ERP & POS",
    description="Sistema robusto de administración de recursos y punto de venta",
    version="2.0.0"
)

@app.on_event("startup")
async def startup_event():
    setup_abasto_subscribers()
    from app.core.database import SessionLocal
    from app.services.capabilities_service import seed_global_modules
    db = SessionLocal()
    try:
        seed_global_modules(db)
    finally:
        db.close()
    # Worker del outbox transaccional: reintenta la entrega de eventos que la
    # entrega inmediata no cerró (fallo de handler, caída del proceso). No-op en SQLite.
    from app.core.outbox import start_outbox_worker
    start_outbox_worker()
    # FIX de Banxico para el equivalente en dolares del POS. No-op en SQLite y
    # sin BANXICO_TOKEN (ver el docstring del modulo).
    from app.core.exchange_rate_job import start_exchange_rate_job
    start_exchange_rate_job()


@app.on_event("shutdown")
async def shutdown_event():
    from app.core.outbox import stop_outbox_worker
    await stop_outbox_worker()
    from app.core.exchange_rate_job import stop_exchange_rate_job
    await stop_exchange_rate_job()


# ── Middleware ────────────────────────────────────────────────────────────────
from fastapi.middleware.trustedhost import TrustedHostMiddleware

# El "*" comodín anulaba por completo TrustedHostMiddleware. Se listan los hosts
# reales: Railway (healthcheck + subdominio del servicio) y los dominios propios
# (incluye el destino del corte a app.atlasone.com.mx). Extensible por env sin
# tocar código.
_EXTRA_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "").split(",") if h.strip()]
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[
        "healthcheck.railway.app",
        "*.up.railway.app",
        "atlasone.com.mx",
        "*.atlasone.com.mx",
        "localhost",
        "127.0.0.1",
        *_EXTRA_HOSTS,
    ],
)

# Duración de cada petición en el log (org, sucursal y usuario incluidos).
# ASGI puro a propósito: BaseHTTPMiddleware puede impedir que corra el
# `finally: db.close()` de `get_db()` si el cliente se desconecta a media
# request (terminales POS en redes inestables) — ver el detalle en
# app/observability/timing.py.
from app.observability.timing import TimingMiddleware
app.add_middleware(TimingMiddleware)

# allow_credentials=False: la sesión viaja en el header Authorization (token en
# localStorage), no en cookies. Con credentials=True + allow_origins=["*"],
# Starlette reflejaba cualquier Origin — superficie innecesaria para una API de
# token en header servida en el mismo origen que su SPA.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Healthcheck & PWA ─────────────────────────────────────────────────────────
@app.get("/health", include_in_schema=False)
def health_check():
    return {"status": "ok"}

@app.get("/manifest.json", include_in_schema=False)
def pwa_manifest():
    return FileResponse("app/static/manifest.json", media_type="application/manifest+json")

@app.get("/sw.js", include_in_schema=False)
def pwa_sw():
    return FileResponse("app/static/sw.js", media_type="application/javascript")

# Timezone
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

MX_TZ = ZoneInfo("America/Mexico_City")

# ── Static files ──────────────────────────────────────────────────────────────
@app.middleware("http")
async def static_cache_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        if request.url.path.endswith((".js", ".css")):
            response.headers["Cache-Control"] = "public, max-age=3600, must-revalidate"
        elif request.url.path.endswith((".png", ".jpg", ".jpeg", ".webp", ".svg", ".ico")):
            response.headers["Cache-Control"] = "public, max-age=604800"
        else:
            response.headers["Cache-Control"] = "public, max-age=3600"
    return response

app.mount("/static", StaticFiles(directory="app/static"), name="static")

import os as _os
_REACT_DIST = "frontend/dist"
if _os.path.isdir(_REACT_DIST):
    app.mount("/assets", StaticFiles(directory=f"{_REACT_DIST}/assets"), name="react-assets")


# ── API Routers ───────────────────────────────────────────────────────────────
app.include_router(auth.router,             prefix="/api/auth",             tags=["Autenticación"])
app.include_router(organization.router,     prefix="/api/organization",     tags=["Organización"])
app.include_router(users.router,            prefix="/api/users",            tags=["Usuarios"])
app.include_router(branches.router,         prefix="/api/branches",         tags=["Sucursales"])
# `departments_router` y `brands_router` viven en products.py (Fase A cleanup).
# Mantenemos los prefixes históricos /api/departments y /api/brands para no
# romper al frontend.
app.include_router(products.departments_router, prefix="/api/departments", tags=["Departamentos"])
app.include_router(products.brands_router,      prefix="/api/brands",      tags=["Marcas"])
app.include_router(products.router,         prefix="/api/products",         tags=["Catálogo"])
app.include_router(inventory.router,        prefix="/api/inventory",        tags=["Inventario"])
app.include_router(sales.router,            prefix="/api/sales",            tags=["Ventas"])
app.include_router(cash.router,             prefix="/api/cash",             tags=["Caja"])
app.include_router(returns.router,          prefix="/api/returns",          tags=["Devoluciones"])
app.include_router(quotes.router,           prefix="/api/quotes",           tags=["Cotizaciones"])
app.include_router(customers.router,        prefix="/api/customers",        tags=["Clientes"])
# documents.router eliminado en Sprint 4: estaba broken (template pdf/statement.html
# nunca existió + import faltante de datetime). PDF de estados de cuenta se genera
# via app/modules/customers/router.py (GET /{customer_id}/pdf-statement) →
# app/modules/customers/statement_pdf.generate_account_statement_pdf (fpdf2).
app.include_router(reports.router,          prefix="/api/reports",          tags=["Reportes"])
app.include_router(printer.router,          prefix="/api/printer",          tags=["Impresora"])
app.include_router(hr.router,               prefix="/api/hr",               tags=["RRHH"])
app.include_router(portal.router,           prefix="/api/portal",           tags=["Portal"])
app.include_router(logistics.router,        prefix="/api/logistics",        tags=["Logística"])
app.include_router(platform.router,         prefix="/api/platform",         tags=["Platform"])
# Consumidor del inquilino: el paquete /api/platform/* esta detras de
# require_platform_admin, asi que los avisos necesitan su propia ruta de lectura.
app.include_router(announcements.router,    prefix="/api/announcements",    tags=["Avisos"])
app.include_router(transfers.router,        prefix="/api/transfers",        tags=["Transferencias"])
# `capabilities_router` vive en organization.py (Fase A cleanup). Mantiene
# el prefix histórico /api/org/capabilities para no romper al frontend.
app.include_router(organization.capabilities_router, prefix="/api/org/capabilities", tags=["Capacidades"])
app.include_router(purchases.router,        prefix="/api/purchases",        tags=["Compras"])
app.include_router(expenses.router,         prefix="/api/expenses",         tags=["Gastos"])
app.include_router(branch.router,           prefix="/api/branch",           tags=["Branch"])

from app.routers import setup
app.include_router(setup.router, prefix="/api/setup", tags=["Setup"])

# ─── Atlas One stub modules (2026-05-14) ────────────────────────────
# Beta scaffolds exposing only /health. Real endpoints will be added
# when each module is built out per docs/modules/MODULE_GUIDE.md.
from app.modules.appointments.router import router as appointments_router
from app.modules.commissions.router  import router as commissions_router
from app.modules.memberships.router  import router as memberships_router
from app.modules.recipes.router      import router as recipes_router
from app.modules.ai.router           import router as ai_router
from app.modules.purchasing.router   import router as purchasing_router
# Gastro modules (2026-06-22) — Mesas, Cocina/KDS, Recetas
from app.modules.tables.router       import router as tables_router
from app.modules.bar.router          import router as bar_router
from app.modules.kitchen.router      import router as kitchen_router
# Etiquetas (2026-09-22) — ZPL para la Zebra; el agente local imprime
from app.modules.labels.router       import router as labels_router

app.include_router(appointments_router, prefix="/api/appointments", tags=["Agenda"])

from app.modules.appointments.portal_router import router as appointments_portal_router

app.include_router(
    appointments_portal_router,
    prefix="/api/portal/booking",
    tags=["Portal: Booking (público)"],
)
app.include_router(commissions_router,  prefix="/api/commissions",  tags=["Comisiones (Beta)"])
app.include_router(memberships_router,  prefix="/api/memberships",  tags=["Membresías (Beta)"])
app.include_router(recipes_router,      prefix="/api/recipes",      tags=["Recetas (Beta)"])
app.include_router(ai_router,           prefix="/api/ai",           tags=["IA (Beta)"])
app.include_router(purchasing_router,   prefix="/api/purchasing",   tags=["Compras (Beta)"])
app.include_router(tables_router,       prefix="/api/tables",       tags=["Mesas"])
app.include_router(bar_router,          prefix="/api/bar",          tags=["Bar líquido"])
app.include_router(kitchen_router,      prefix="/api/kitchen",      tags=["Cocina / KDS"])
app.include_router(labels_router,       prefix="/api/labels",       tags=["Etiquetas"])
# daxpos.router eliminado en Sprint 3 (tech-debt roadmap).
# Sus 15 rutas SSR fueron desactivadas: las que coinciden con rutas React
# caen al catch-all de la SPA; las que necesitan cambio de destino están
# listadas en la sección "Redirects legacy" más abajo.

# Alias de compatibilidad para departamentos (URLs históricas).
# El handler canonical vive en products.list_departments — aquí lo
# re-exportamos bajo prefijos legacy para no romper llamadas viejas.
from app.core.security import get_current_user as _gcu_for_alias
from app.core.tenant_context import get_current_active_organization as _gcao_for_alias
from app.routers.products import list_departments as _list_departments_canonical

@app.get("/api/products/departments",   tags=["Departamentos"], include_in_schema=False)
@app.get("/api/productos/departaments", tags=["Departamentos"], include_in_schema=False)
@app.get("/api/productos/departamentos",tags=["Departamentos"], include_in_schema=False)
def departments_alias(
    db: Session = Depends(get_db),
    current_user = Depends(_gcu_for_alias),
    org_id: int = Depends(_gcao_for_alias),
):
    return _list_departments_canonical(db=db, current_user=current_user, org_id=org_id)

# ── Redirects legacy ──────────────────────────────────────────────────────────
@app.get("/command-center", include_in_schema=False)
async def command_center_redirect():
    return RedirectResponse(url="/hq/operations", status_code=302)

@app.get("/hq/reports", include_in_schema=False)
async def hq_reports_redirect():
    return RedirectResponse(url="/hq/reports-hub", status_code=302)

@app.get("/pos/inbox", include_in_schema=False)
async def pos_inbox_redirect():
    return RedirectResponse(url="/pos", status_code=302)

@app.get("/portal/dashboard", include_in_schema=False)
async def portal_dashboard_redirect():
    return RedirectResponse(url="/portal", status_code=302)

@app.get("/branches", include_in_schema=False)
async def branches_redirect():
    return RedirectResponse(url="/hq/branches", status_code=302)

@app.get("/home", include_in_schema=False)
async def home_redirect():
    return RedirectResponse(url="/atlas-pos", status_code=302)

@app.get("/sales/light", include_in_schema=False)
async def sales_light_redirect():
    return RedirectResponse(url="/sales", status_code=302)

@app.get("/boxes-old", include_in_schema=False)
async def boxes_old_redirect():
    return RedirectResponse(url="/boxes", status_code=302)

# Sprint 3 — rescate de 2 redirects que estaban en daxpos.py antes de su deprecación.
# /hq/sales mantiene compat con bookmarks viejos; la ruta React es /hq/sales-log.
# /boxes redirige al tab de empaques en /brands (UX consolidada).
@app.get("/hq/sales", include_in_schema=False)
async def hq_sales_redirect():
    return RedirectResponse(url="/hq/sales-log", status_code=302)

@app.get("/boxes", include_in_schema=False)
async def boxes_redirect():
    return RedirectResponse(url="/brands?tab=empaques", status_code=302)

# ── Platform support context cookies (usados por impersonation) ───────────────
@app.post("/api/platform/set-support-context")
async def set_support_context(payload: dict):
    org_id = payload.get("organization_id")
    response = JSONResponse({"status": "ok"})
    response.set_cookie(key="support_org_id", value=str(org_id), httponly=True, max_age=14400)
    return response

@app.post("/api/platform/clear-support-context")
async def clear_support_context():
    response = JSONResponse({"status": "ok"})
    response.delete_cookie("support_org_id")
    return response

# ── Error handlers ────────────────────────────────────────────────────────────
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Registra QUE campo rechazo un 422, y devuelve la respuesta de siempre.

    Sin esto, un 422 solo aparece como `POST /api/products/ 422` y no hay forma
    de saber que le fallo al usuario sin reproducirlo a ciegas. Paso justo eso
    con un producto que un dueño no podia dar de alta.

    Se registran los NOMBRES de los campos y el motivo, NUNCA los valores: un
    payload de producto o de venta lleva datos del negocio.
    """
    campos = "; ".join(
        f"{'.'.join(str(x) for x in e.get('loc', [])[1:]) or '(cuerpo)'}: {e.get('msg', '')}"
        for e in exc.errors()
    )
    logging.getLogger("app.errors").warning(
        "VALIDATION_ERROR: %s %s -> %s",
        request.method, request.url.path, campos or "(sin detalle)",
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=jsonable_encoder({"detail": exc.errors()}),
    )


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    if request.url.path.startswith("/api/"):
        detail = getattr(exc, "detail", "Recurso no encontrado")
        return JSONResponse(status_code=404, content={"detail": detail})
    # Para rutas de navegador — React Router maneja el 404 client-side
    _REACT_INDEX = "frontend/dist/index.html"
    if _os.path.isfile(_REACT_INDEX):
        return FileResponse(_REACT_INDEX)
    return JSONResponse(status_code=404, content={"detail": "Not found"})

@app.exception_handler(401)
async def unauthorized_handler(request: Request, exc):
    return JSONResponse(status_code=401, content={"detail": "No autenticado"})

@app.exception_handler(403)
async def forbidden_handler(request: Request, exc):
    detail = getattr(exc, "detail", "No autorizado")
    if request.url.path.startswith("/api/") or request.url.path.startswith("/platform/"):
        return JSONResponse(status_code=403, content={"detail": detail})
    _REACT_INDEX = "frontend/dist/index.html"
    if _os.path.isfile(_REACT_INDEX):
        return FileResponse(_REACT_INDEX)
    return JSONResponse(status_code=403, content={"detail": detail})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # Log con traceback completo para que docker logs capture el error real.
    logging.getLogger("app.errors").exception(
        "Unhandled exception on %s %s: %s", request.method, request.url.path, exc
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error", "error": type(exc).__name__, "message": str(exc)},
    )

# ── React SPA catch-all ───────────────────────────────────────────────────────
_REACT_INDEX = "frontend/dist/index.html"

@app.get("/{full_path:path}", include_in_schema=False)
async def serve_react_app(full_path: str):
    # No servir SPA para rutas /api/* — evita que el catch-all intercepte
    # sub-rutas API con trailing slash antes del redirect de FastAPI
    if full_path.startswith("api/"):
        return JSONResponse(status_code=404, content={"detail": "Not found"})
    if _os.path.isfile(_REACT_INDEX):
        return FileResponse(_REACT_INDEX, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
    return JSONResponse(
        status_code=404,
        content={"detail": f"Route /{full_path} not found and React build is not available"}
    )
