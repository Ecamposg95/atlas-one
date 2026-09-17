"""Job diario que baja el FIX de Banxico a la tabla `exchange_rates`.

Mismo patron que el worker del outbox (`app/core/outbox.py:151-160`): un
`asyncio.Task` lanzado en el startup de `app/main.py`. Doble apagado:

* **SQLite** — tests y dev local. Igual que el outbox, no queremos un task de
  fondo tocando la base de una suite de pruebas.
* **Sin `BANXICO_TOKEN`** — la funcion es opcional; una instalacion que no la
  use no debe ver un error cada 24 horas en el log.

Ritmo: al arrancar, si falta la fila de hoy la trae; luego duerme hasta las
12:30 de America/Mexico_City. El FIX se publica alrededor del mediodia, asi que
12:30 da margen; mientras tanto se usa la fila del dia anterior, que es lo que
Banxico mismo considera vigente hasta la publicacion.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timedelta
from typing import Tuple
from zoneinfo import ZoneInfo

from app.core.database import SQLALCHEMY_DATABASE_URL, SessionLocal
from app.services.banxico import BanxicoError, fetch_fix, token_configurado
from app.services.exchange_rate import MONEDA_USD, guardar_fix

logger = logging.getLogger(__name__)

_IS_SQLITE = "sqlite" in (SQLALCHEMY_DATABASE_URL or "")
TZ_MX = ZoneInfo("America/Mexico_City")
HORA_CORRIDA = time(12, 30)

_job_task: "asyncio.Task | None" = None


def hay_fix_de_hoy(db) -> bool:
    """¿Ya esta la fila del dia (hora de Mexico) en la tabla?"""
    from app.models.exchange_rate import ExchangeRate

    hoy = datetime.now(TZ_MX).date()
    consulta = db.query(ExchangeRate).filter(
        ExchangeRate.currency == MONEDA_USD,
        ExchangeRate.rate_date == hoy,
    )
    return bool(db.query(consulta.exists()).scalar())


def segundos_hasta_la_proxima_corrida(ahora: datetime) -> float:
    """Segundos hasta las 12:30 de Mexico. Si ya paso (o es exactamente esa
    hora), hasta las de mañana: el bucle nunca duerme cero."""
    local = ahora.astimezone(TZ_MX)
    objetivo = local.replace(
        hour=HORA_CORRIDA.hour, minute=HORA_CORRIDA.minute, second=0, microsecond=0
    )
    if objetivo <= local:
        objetivo += timedelta(days=1)
    return (objetivo - local).total_seconds()


def actualizar_fix_ahora(db, token: str) -> Tuple[bool, str]:
    """Baja el FIX y lo guarda. Devuelve (exito, mensaje). NO lanza.

    El guardado (`guardar_fix` + `commit`) puede fallar por su cuenta —
    conexion caida, un choque de integridad si el job de fondo corre al mismo
    tiempo que un refresco manual — y no solo la descarga HTTP. Ambos casos se
    normalizan al mismo `BanxicoError` para que el endpoint de refresco
    (`app/modules/tenants/router.py::refresh_exchange_rate`) los trate igual
    (503 con detalle accionable) en vez de un 500 sin manejar, y para que no
    quede una fila a medio escribir (rollback explicito).
    """
    try:
        dia, tipo = fetch_fix(token)
    except BanxicoError as e:
        logger.warning("BANXICO_FETCH_FAILED %s", e)
        return False, str(e)

    try:
        guardar_fix(db, dia, tipo)
        db.commit()
    except Exception as e:
        db.rollback()
        error = BanxicoError(f"No se pudo guardar el FIX: {e}")
        logger.warning("BANXICO_SAVE_FAILED %s", error)
        return False, str(error)

    logger.info("BANXICO_FIX_OK fecha=%s tipo=%s", dia, tipo)
    return True, f"FIX {dia.isoformat()} = {tipo}"


async def _job_loop():
    logger.info("Exchange rate job started (FIX de Banxico)")
    while True:
        try:
            token = token_configurado()
            if token:
                db = SessionLocal()
                try:
                    # `fetch_fix` es httpx SINCRONO con timeout de 10 s (y la
                    # lectura pega a la base): llamarlos directo desde el loop
                    # congelaria todo el servidor al arrancar y a las 12:30.
                    hay = await asyncio.to_thread(hay_fix_de_hoy, db)
                    if not hay:
                        await asyncio.to_thread(actualizar_fix_ahora, db, token)
                finally:
                    db.close()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("Exchange rate job tick failed")
        await asyncio.sleep(segundos_hasta_la_proxima_corrida(datetime.now(TZ_MX)))


def start_exchange_rate_job():
    """Lanza el job. No-op en SQLite o sin BANXICO_TOKEN."""
    global _job_task
    if _IS_SQLITE:
        logger.info("Exchange rate job disabled (SQLite backend)")
        return None
    if not token_configurado():
        logger.info("Exchange rate job disabled (sin BANXICO_TOKEN)")
        return None
    if _job_task and not _job_task.done():
        return _job_task
    _job_task = asyncio.create_task(_job_loop())
    return _job_task


async def stop_exchange_rate_job():
    global _job_task
    if _job_task and not _job_task.done():
        _job_task.cancel()
        try:
            await _job_task
        except asyncio.CancelledError:
            pass
    _job_task = None
