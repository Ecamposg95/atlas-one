"""Tipo de cambio USD: resolucion por organizacion y conversion.

Fuente UNICA del equivalente en dolares, igual que `app/services/tax.py` lo es
del IVA. La consumen el endpoint de configuracion, el snapshot de la venta
(`app/routers/sales.py::create_sale`) y el ticket (`app/pos_printer.py`). Si
cada uno redondeara por su cuenta, el ticket y la pantalla discreparian en
centavos y el cliente lo veria.

Las funciones de la primera mitad son PURAS (sin DB ni FastAPI) y se prueban
solas en tests/test_exchange_rate_service.py. La segunda mitad son ayudantes
que SI tocan la base; estan marcados.

Redondeo: HALF_UP, el mismo redondeo fiscal mexicano de tax.py.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

logger = logging.getLogger(__name__)

CENTAVOS = Decimal("0.01")
DIEZMILESIMAS = Decimal("0.0001")  # el FIX se publica con 4 decimales

# Modos de `organization.usd_rate_mode`.
MODO_OFF = "off"
MODO_AUTO = "auto"
MODO_MANUAL = "manual"
MODOS_VALIDOS = (MODO_OFF, MODO_AUTO, MODO_MANUAL)

FUENTE_BANXICO = "banxico"
FUENTE_MANUAL = "manual"

MONEDA_USD = "USD"

# Tope del ajuste manual sobre el FIX. No es una regla fiscal, es un guardaraíl
# contra el dedo gordo: 80 en vez de 0.80 convertiria un total de $1,000 en
# USD 10 en lugar de USD 53.
MARGEN_MAXIMO = Decimal("50")


@dataclass(frozen=True)
class ResolvedRate:
    """Tipo de cambio efectivo y de donde salio."""
    rate: Decimal                        # pesos por dolar, ya con el margen
    source: str                          # 'banxico' | 'manual'
    fix_rate: Optional[Decimal] = None   # FIX crudo del dia (informativo)
    fix_date: Optional[date] = None      # dia del FIX segun Banxico


def _dec(valor) -> Optional[Decimal]:
    """Decimal tolerante con None, float y str (columnas nullable y SQLite)."""
    if valor is None:
        return None
    try:
        return Decimal(str(valor))
    except Exception:  # noqa: BLE001 — basura en la columna != error de cobro
        return None


def _modo(org) -> str:
    """Modo normalizado. Una organizacion sin la columna todavia es 'off'."""
    return (getattr(org, "usd_rate_mode", None) or MODO_OFF).strip().lower()


def resolve_usd_rate(org, latest_fix) -> Optional[ResolvedRate]:
    """Tipo de cambio efectivo de la organizacion, o None si no hay que mostrar nada.

    `org` solo necesita `usd_rate_mode`, `usd_rate_manual` y `usd_rate_margin`;
    `latest_fix` solo necesita `rate` y `rate_date` (o None). Ambos van
    duck-typed para que la funcion sea probable sin base de datos.

    Devuelve None —y NO lanza— en todos los casos en los que no hay un tipo
    utilizable: modo apagado, modo manual sin tipo capturado, modo automatico
    sin FIX, o un resultado que quedaria en cero o negativo.
    """
    modo = _modo(org)

    if modo == MODO_MANUAL:
        manual = _dec(getattr(org, "usd_rate_manual", None))
        if manual is None or manual <= 0:
            return None
        fix = _dec(getattr(latest_fix, "rate", None)) if latest_fix is not None else None
        return ResolvedRate(
            rate=manual.quantize(DIEZMILESIMAS, rounding=ROUND_HALF_UP),
            source=FUENTE_MANUAL,
            fix_rate=fix,
            fix_date=getattr(latest_fix, "rate_date", None) if latest_fix is not None else None,
        )

    if modo == MODO_AUTO:
        if latest_fix is None:
            return None
        fix = _dec(getattr(latest_fix, "rate", None))
        if fix is None or fix <= 0:
            return None
        margen = _dec(getattr(org, "usd_rate_margin", None)) or Decimal("0")
        efectivo = (fix + margen).quantize(DIEZMILESIMAS, rounding=ROUND_HALF_UP)
        if efectivo <= 0:
            return None
        return ResolvedRate(
            rate=efectivo,
            source=FUENTE_BANXICO,
            fix_rate=fix,
            fix_date=getattr(latest_fix, "rate_date", None),
        )

    return None


def to_usd(amount_mxn, rate) -> Decimal:
    """Pesos -> dolares, redondeado a centavos HALF_UP.

    Tipo de cambio ausente, cero o negativo devuelve `Decimal("0.00")` en vez de
    lanzar: quien llama esta pintando un numero informativo, no cobrando.
    """
    monto = _dec(amount_mxn) or Decimal("0")
    tasa = _dec(rate)
    if tasa is None or tasa <= 0:
        return Decimal("0.00")
    return (monto / tasa).quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def validar_config_usd(mode, manual, margin) -> None:
    """Valida la configuracion RESULTANTE de una organizacion. Lanza ValueError.

    El caller (el PUT de organizacion) la convierte en 422 con el mensaje tal
    cual, en español y accionable.
    """
    m = (mode or MODO_OFF).strip().lower()
    if m not in MODOS_VALIDOS:
        raise ValueError(
            f"Modo de tipo de cambio inválido: '{mode}'. Usa 'off', 'auto' o 'manual'."
        )

    manual_dec = _dec(manual)
    if m == MODO_MANUAL and (manual_dec is None or manual_dec <= 0):
        raise ValueError(
            "En modo manual hay que capturar un tipo de cambio mayor que cero."
        )

    margen_dec = _dec(margin) or Decimal("0")
    if margen_dec.copy_abs() > MARGEN_MAXIMO:
        raise ValueError(
            f"El ajuste sobre el FIX no puede pasar de {MARGEN_MAXIMO} pesos por dólar."
        )


# ── Ayudantes CON base de datos (no puros) ───────────────────────────────────

def ultimo_fix(db, currency: str = MONEDA_USD):
    """Fila mas reciente de `exchange_rates` para la moneda. None si no hay ninguna."""
    from app.models.exchange_rate import ExchangeRate

    return (
        db.query(ExchangeRate)
        .filter(ExchangeRate.currency == currency)
        .order_by(ExchangeRate.rate_date.desc())
        .first()
    )


def tipo_vigente(db, org) -> Optional[ResolvedRate]:
    """`resolve_usd_rate` resolviendo el FIX contra la base."""
    if _modo(org) == MODO_OFF:
        return None  # apagado: ni siquiera se consulta la tabla
    return resolve_usd_rate(org, ultimo_fix(db))


def guardar_fix(db, dia: date, tipo: Decimal,
                source: str = FUENTE_BANXICO, currency: str = MONEDA_USD):
    """Inserta o actualiza la fila del dia. Idempotente. NO hace commit.

    El job puede correr varias veces (N replicas del backend, refresco manual
    del dueño): la clave (currency, rate_date) es una sola fila, siempre.
    """
    from app.models.exchange_rate import ExchangeRate

    fila = (
        db.query(ExchangeRate)
        .filter(ExchangeRate.currency == currency, ExchangeRate.rate_date == dia)
        .first()
    )
    if fila is None:
        fila = ExchangeRate(currency=currency, rate_date=dia, rate=tipo, source=source)
        db.add(fila)
    else:
        fila.rate = tipo
        fila.source = source
        fila.fetched_at = datetime.now(timezone.utc)
    db.flush()
    return fila


def snapshot_usd_rate(db, org_id: int) -> Optional[Decimal]:
    """Tipo efectivo para congelar en una venta. NUNCA lanza.

    La llama `app/routers/sales.py::create_sale`, el motor ATS-critico: si
    Banxico, la tabla o esta misma funcion fallan, la venta TIENE que cobrarse
    igual. Por eso cualquier excepcion se traga con un warning y devuelve None
    (= la venta queda sin equivalente en dolares, que es exactamente el estado
    de todas las ventas anteriores a esta funcion).
    """
    try:
        from app.models.organization import Organization

        org = db.query(Organization).filter(Organization.id == org_id).first()
        if org is None:
            return None
        resuelto = tipo_vigente(db, org)
        return resuelto.rate if resuelto else None
    except Exception:  # noqa: BLE001 — jamas impedir un cobro
        logger.warning("USD_SNAPSHOT_FAILED org=%s", org_id, exc_info=True)
        return None
