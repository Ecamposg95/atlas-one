"""Duración de cada petición, en el log.

Portado de Atlas-Rmazh (`app/observability/timing.py`, commits `4c35b24` y
`425bf78`). Atlas ONE hoy solo registra errores efímeros: cada redespliegue
en Railway borra el historial y no hay forma de contestar "¿qué tardó, en
qué organización/sucursal y a qué hora?" (ver memoria `atlas-one-logs-efimeros`).

POR QUÉ ES ASGI PURO Y NO `@app.middleware("http")`
---------------------------------------------------
`@app.middleware("http")` usa BaseHTTPMiddleware y envuelve la petición con
`call_next` dentro de un grupo de tareas: si el cliente se desconecta a media
request —terminales POS en redes inestables—, puede impedir que corra el
`finally: db.close()` de `get_db()` y agotar el pool de conexiones. Un
middleware ASGI puro solo observa: envuelve `send` para leer el estado y mide
el tiempo, sin interponer tareas ni consumir el cuerpo, así que el teardown
de las dependencias ocurre exactamente igual que sin él. El candado de esa
regresión está en `tests/test_request_timing.py`.

DIFERENCIAS CON EL ORIGEN DE RMAZH
-----------------------------------
- El campo de duración se llama `ms` (no `duration_ms`) — así lo pide el
  contrato de este flujo (W4).
- `org` sale del header `X-Organization-ID` (igual que Rmazh), pero `branch`
  y `user` NO salen de un header `X-Branch-ID`: este repo no tiene ese
  header. Ambos se leen del JWT en `Authorization: Bearer …`, decodificado
  con la config de `app/core/security/jwt.py` (SECRET_KEY/ALGORITHM). El
  claim `ctx_id` ya es la sucursal activa (o `None` cuando el contexto es
  HQ — ver `app/modules/auth/router.py::login`/`switch-context`) y `sub` es
  el username.
"""
from __future__ import annotations

import json
import logging
import time

from jose import JWTError, jwt

from app.core.security.jwt import ALGORITHM, SECRET_KEY

logger = logging.getLogger("atlas.timing")

# Umbral para marcar una petición como lenta: 500 ms es donde una persona deja
# de percibirla como inmediata. Debajo de eso no hay nada que revisar.
SLOW_MS = 500

IGNORAR = frozenset({"/health"})
PREFIJOS_IGNORADOS = ("/assets/", "/icons/", "/static/")


def _ignorada(path: str | None) -> bool:
    if not path:
        return False
    return path in IGNORAR or path.startswith(PREFIJOS_IGNORADOS)


def _header_int(scope, nombre: bytes) -> int | None:
    """Lee un header numérico del scope ASGI; basura → None, nunca excepción."""
    for k, v in scope.get("headers", []):
        if k == nombre:
            try:
                return int(v.decode("latin-1").strip())
            except (ValueError, UnicodeDecodeError):
                return None
    return None


def _claims_del_token(scope) -> tuple[str | None, int | None]:
    """Lee `user` (sub) y `branch` (ctx_id) del JWT en Authorization.

    Un token ausente, corrupto o vencido nunca tumba la petición: se pierde
    el dato, no la venta. `ctx_id` ya es `None` cuando el contexto activo es
    HQ (ver `app/modules/auth/router.py`), así que no hace falta filtrar por
    `ctx_type`.
    """
    for k, v in scope.get("headers", []):
        if k == b"authorization":
            try:
                valor = v.decode("latin-1")
            except UnicodeDecodeError:
                return None, None
            if not valor.lower().startswith("bearer "):
                return None, None
            token = valor.split(" ", 1)[1].strip()
            try:
                payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            except JWTError:
                return None, None
            return payload.get("sub"), payload.get("ctx_id")
    return None, None


class TimingMiddleware:
    """Middleware ASGI puro: método, ruta con plantilla, estado, duración, org, sucursal y usuario."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or _ignorada(scope.get("path")):
            await self.app(scope, receive, send)
            return

        t0 = time.perf_counter()
        estado = {"status": 500}  # si nunca responde, queda como fallo

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                estado["status"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            _registrar(scope, estado["status"], (time.perf_counter() - t0) * 1000)


def ruta_con_plantilla(scope) -> str:
    """`/api/sales/{sale_id}` y no `/api/sales/abc-123`.

    Con el id concreto cada petición sería su propia serie y no se podría
    promediar ni comparar nada. Starlette deja la ruta que empató en
    `scope["route"]` una vez resuelto el enrutamiento.
    """
    ruta = scope.get("route")
    plantilla = getattr(ruta, "path", None)
    return plantilla or scope.get("path", "?")


def _registrar(scope, status: int, ms: float) -> None:
    """Nunca puede tumbar la petición: medir no vale una venta perdida."""
    try:
        user, branch = _claims_del_token(scope)
        dato = {
            "method": scope.get("method", "?"),
            "path": ruta_con_plantilla(scope),
            "status": status,
            "ms": round(ms, 1),
            "org": _header_int(scope, b"x-organization-id"),
            "branch": branch,
            "user": user,
        }
        if ms >= SLOW_MS:
            dato["slow"] = True
        # `extra` deja los campos en el record; el formateador JSON de
        # app/main.py los sube al primer nivel cuando LOG_JSON=true, para
        # que Railway filtre por campo.
        logger.info(json.dumps(dato, ensure_ascii=False), extra={"atlas": dato})
    except Exception:
        pass
