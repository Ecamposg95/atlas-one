"""Comision por pago con tarjeta: calculo, politica y validacion.

Fuente UNICA de la comision, igual que `app/services/tax.py` lo es del IVA y
`app/services/exchange_rate.py` del tipo de cambio. La consumen el checkout
(`app/routers/sales.py::create_sale`), el `PUT` de organizacion y —a traves de
`GET /api/organization/card-surcharge`— el POS, que tiene su espejo puro en
`frontend/src/pages/pos/cardSurcharge.ts`. Si cada uno redondeara por su
cuenta, la pantalla y el cobro discreparian en centavos con el dinero del
cliente en la mano.

Regla (ver el diseño §4):

    base_tarjeta  = max(0, total - suma de los pagos cuyo metodo NO es CARD)
    comision      = redondear(base_tarjeta * pct / 100)
    pago_tarjeta  = base_tarjeta + comision
    total_a_pagar = total + comision

`total_amount` de la venta NO incluye la comision: se persiste aparte
(`sales_documents.card_surcharge_amount`) para no inflar el reporte de ingresos
ni el histórico.

Todo aqui es PURO: sin base de datos, sin FastAPI. Redondeo HALF_UP a centavos,
el mismo redondeo fiscal mexicano de tax.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

CENTAVOS = Decimal("0.01")
CERO = Decimal("0.00")

# Unico metodo que causa comision. Los otros tres de `PaymentMethod`
# (CASH, TRANSFER, OTHER) son base sin comision.
METODO_TARJETA = "CARD"

# Tope del porcentaje. No es una regla fiscal, es un guardarail contra el dedo
# gordo: 35 en vez de 3.5 convertiria una venta de $1,000 en $1,350 cobrados.
PCT_MAXIMO = Decimal("20")


@dataclass(frozen=True)
class ComisionTarjeta:
    """Resultado del calculo. Invariantes que SIEMPRE valen:

        total_a_pagar == total + monto
        pago_tarjeta  == base + monto
        monto == 0  <=>  pct == 0
    """
    base: Decimal           # importe sobre el que se cobra la comision
    pct: Decimal            # porcentaje EFECTIVAMENTE aplicado (0 si no aplico)
    monto: Decimal          # la comision, a centavos
    pago_tarjeta: Decimal   # base + monto: lo que debe pasar por la terminal
    total_a_pagar: Decimal  # total + monto: lo que el cliente entrega


def _dec(valor) -> Optional[Decimal]:
    """Decimal tolerante con None, float y str (columnas nullable y SQLite)."""
    if valor is None:
        return None
    try:
        return Decimal(str(valor))
    except Exception:  # noqa: BLE001 — basura en la columna != error de cobro
        return None


def _centavos(valor) -> Decimal:
    """Decimal cuantizado a centavos. Entrada invalida -> 0.00."""
    d = _dec(valor)
    if d is None:
        return CERO
    return d.quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def _metodo(pago) -> str:
    """Metodo del pago, normalizado. Acepta enum, string, objeto o dict."""
    if isinstance(pago, dict):
        crudo = pago.get("method")
    else:
        crudo = getattr(pago, "method", None)
    return (crudo.value if hasattr(crudo, "value") else str(crudo or "")).strip().upper()


def _monto_pago(pago) -> Decimal:
    if isinstance(pago, dict):
        return _centavos(pago.get("amount"))
    return _centavos(getattr(pago, "amount", None))


def pct_de_organizacion(org) -> Decimal:
    """Porcentaje configurado en la organizacion, leido a prueba de balas.

    Devuelve `CERO` —nunca lanza— si la organizacion es None, si todavia no
    tiene la columna (base legada leida antes del ALTER), si viene NULL o si
    trae un valor sin sentido. `CERO` significa "funcion apagada", que es el
    estado de toda organizacion existente.
    """
    if org is None:
        return CERO
    pct = _dec(getattr(org, "card_surcharge_pct", None))
    if pct is None or pct <= 0:
        return CERO
    return pct.quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def hay_pago_con_tarjeta(pagos) -> bool:
    """¿Alguno de los pagos pasa por la terminal?"""
    return any(_metodo(p) == METODO_TARJETA for p in (pagos or []))


def calcular_comision(total, pagos, pct) -> ComisionTarjeta:
    """Comision que corresponde a esta venta. NUNCA lanza.

    `pagos` va duck-typed: cualquier objeto con `.method` y `.amount` sirve
    (`PaymentCreate` en produccion, `SimpleNamespace` o dict en las pruebas).

    Devuelve una comision de CERO —y `total_a_pagar` igual al total— en todos
    los casos en los que no hay nada que cobrar: porcentaje apagado, sin pagos,
    sin ningun pago con tarjeta, o efectivo que ya cubre el total entero.
    """
    total_q = _centavos(total)
    pct_q = _dec(pct) or CERO
    if pct_q < 0:
        pct_q = CERO

    pagos = list(pagos or [])
    _neutro = ComisionTarjeta(
        base=CERO, pct=CERO, monto=CERO, pago_tarjeta=CERO, total_a_pagar=total_q
    )
    if pct_q == 0 or not hay_pago_con_tarjeta(pagos):
        return _neutro

    no_tarjeta = sum(
        (_monto_pago(p) for p in pagos if _metodo(p) != METODO_TARJETA), CERO
    )
    # `max(0, ...)`: un billete grande tecleado como efectivo no puede empujar
    # la base a negativo y regalarle una comision negativa al cliente.
    base = total_q - no_tarjeta
    if base <= 0:
        return _neutro

    monto = (base * pct_q / Decimal("100")).quantize(CENTAVOS, rounding=ROUND_HALF_UP)
    if monto <= 0:
        return _neutro

    return ComisionTarjeta(
        base=base,
        pct=pct_q,
        monto=monto,
        pago_tarjeta=base + monto,
        total_a_pagar=total_q + monto,
    )


def validar_pct(pct) -> None:
    """Valida el porcentaje que quiere guardar el administrador. Lanza ValueError.

    El caller (el PUT de organizacion) lo convierte en 422 con el mensaje tal
    cual, en español y accionable.
    """
    valor = _dec(pct)
    if valor is None:
        raise ValueError("La comisión por pago con tarjeta debe ser un número.")
    if valor < 0 or valor > PCT_MAXIMO:
        raise ValueError(
            f"La comisión por pago con tarjeta debe estar entre 0 y {PCT_MAXIMO:.0f} %."
        )
