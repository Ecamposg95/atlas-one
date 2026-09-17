"""Cliente del SIE de Banxico: tipo de cambio FIX (serie SF43718).

El FIX es el tipo de cambio para solventar obligaciones en dolares que Banxico
publica cada dia habil alrededor del mediodia. Se usa como referencia publica y
auditable; el margen de ventanilla lo pone cada organizacion.

Una sola funcion, sincrona y con timeout corto. La llaman el job diario
(`app/core/exchange_rate_job.py`) y el endpoint de refresco manual. NUNCA se
llama desde el camino de una venta.
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

SERIE_FIX = "SF43718"
URL_SIE = (
    f"https://www.banxico.org.mx/SieAPIRest/service/v1/series/{SERIE_FIX}/datos/oportuno"
)
TIMEOUT_SEGUNDOS = 10.0


class BanxicoError(RuntimeError):
    """El SIE no respondio, o respondio algo que no es un tipo de cambio."""


def token_configurado() -> Optional[str]:
    """Token del SIE desde el entorno. None = la funcion queda apagada."""
    valor = (os.getenv("BANXICO_TOKEN") or "").strip()
    return valor or None


def fetch_fix(token: str) -> Tuple[date, Decimal]:
    """Descarga el FIX mas reciente. Devuelve (dia publicado, tipo de cambio).

    Lanza `BanxicoError` ante cualquier problema: sin token, red caida, HTTP
    distinto de 200, JSON con otra forma, o el 'N/E' que el SIE devuelve en
    dias inhabiles. El caller loguea y sigue; nada de esto debe tumbar el
    arranque del backend ni una venta.
    """
    if not token:
        raise BanxicoError("Falta BANXICO_TOKEN")

    try:
        respuesta = httpx.get(
            URL_SIE,
            params={"token": token},
            headers={"Accept": "application/json"},
            timeout=TIMEOUT_SEGUNDOS,
        )
    except httpx.HTTPError as e:
        raise BanxicoError(f"No se pudo consultar Banxico: {e}") from e

    if respuesta.status_code != 200:
        raise BanxicoError(f"Banxico respondió HTTP {respuesta.status_code}")

    try:
        cuerpo = respuesta.json()
        dato = cuerpo["bmx"]["series"][0]["datos"][0]
        crudo_fecha = dato["fecha"]
        crudo_valor = dato["dato"]
    except (ValueError, KeyError, IndexError, TypeError) as e:
        raise BanxicoError(f"Respuesta de Banxico con formato inesperado: {e}") from e

    try:
        dia = datetime.strptime(str(crudo_fecha), "%d/%m/%Y").date()
    except (ValueError, TypeError) as e:
        raise BanxicoError(f"Fecha inesperada de Banxico: {crudo_fecha!r}") from e

    try:
        # En dias inhabiles el dato es 'N/E'; tambien puede traer separador de miles.
        tipo = Decimal(str(crudo_valor).replace(",", "").strip())
    except (InvalidOperation, AttributeError) as e:
        raise BanxicoError(f"Dato no numérico de Banxico: {crudo_valor!r}") from e

    if tipo <= 0:
        raise BanxicoError(f"Tipo de cambio inválido de Banxico: {tipo}")

    return dia, tipo
