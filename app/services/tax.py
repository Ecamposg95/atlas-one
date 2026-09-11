"""Fuente ÚNICA de verdad para el cálculo del IVA.

NUNCA repliques estas fórmulas: todo consumidor (cobro, ticket, devolución,
reportes) importa de aquí. Portado de Atlas-Rmazh (`app/services/tax.py`) por el
hallazgo §3 de `docs/audits/2026-09-01-comparacion-atlas-rmazh.md`: la fórmula
vivía copiada en el checkout, en el ticket reemitido y en la devolución, y cada
copia redondeaba distinto, así que el ticket y el reporte podían discrepar en
centavos —y con precio con IVA incluido, en mucho más—.

Dos modos de precio, resueltos por organización con `resolve_org_tax_mode`:

* **Neto** (`price_includes_tax=False`, el histórico de Atlas ONE y el default
  seguro): el precio del catálogo es la base gravable y el IVA se suma encima.
* **Incluido** (`price_includes_tax=True`): el precio del catálogo ya trae el
  IVA y aquí se descompone; el total cobrado no cambia.

En los dos modos vale la invariante `subtotal + tax == total`, con redondeo
ROUND_HALF_UP a centavos.
"""
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

CENTAVOS = Decimal("0.01")


def _q(monto: Decimal) -> Decimal:
    """Redondea a centavos, half-up (el redondeo fiscal mexicano)."""
    return monto.quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def _dec(valor) -> Decimal:
    """Convierte a Decimal tolerando None y float (columnas nullable del catálogo)."""
    return Decimal(str(valor)) if valor is not None else Decimal("0")


@dataclass(frozen=True)
class TaxResult:
    """subtotal = base gravable · tax = IVA · total = lo que se cobra."""
    subtotal: Decimal
    tax: Decimal
    total: Decimal


def compute_line_tax(
    line_gross,
    tax_rate,
    has_iva: bool,
    price_includes_tax: bool,
    requires_invoice: bool,
    quantize: bool = True,
) -> TaxResult:
    """Desglose de una línea (o de un importe agregado con una sola tasa).

    `line_gross` es el importe de la línea ya con descuentos aplicados, expresado
    en el modo de precio de la organización. `tax_rate` es el porcentaje
    (16, 8…), no la fracción.

    El IVA solo entra si hay factura, el producto está gravado y la tasa es > 0.

    `quantize=False` devuelve los valores SIN redondear, para quien suma varias
    líneas y redondea una sola vez al final con `quantize_totals`. No es un
    detalle estético: redondear renglón por renglón corre el total unos centavos
    contra el que calcula el carrito del POS (`frontend/src/store/posStore.ts`,
    que suma sin redondeos intermedios), y el checkout compara ambos con una
    tolerancia de un centavo antes de cobrar. Ver `create_sale`.
    """
    redondear = _q if quantize else (lambda x: x)
    importe = _dec(line_gross)
    tasa = _dec(tax_rate) / Decimal("100")

    if not (requires_invoice and has_iva and tasa > 0):
        bruto = redondear(importe)
        return TaxResult(subtotal=bruto, tax=Decimal("0.00"), total=bruto)

    if price_includes_tax:
        subtotal = redondear(importe / (Decimal("1") + tasa))
        total = redondear(importe)
        # El IVA se deriva del total para que `subtotal + tax == total` exacto.
        tax = redondear(total - subtotal)
    else:
        subtotal = redondear(importe)
        tax = redondear(importe * tasa)
        total = redondear(subtotal + tax)
    return TaxResult(subtotal=subtotal, tax=tax, total=total)


def quantize_amount(monto) -> Decimal:
    """Redondea un importe a centavos (half-up), para persistirlo."""
    return _q(_dec(monto))


def quantize_totals(subtotal, tax) -> TaxResult:
    """Redondea a centavos un subtotal y un IVA acumulados sin redondear.

    Contraparte de `compute_line_tax(..., quantize=False)`: se llama UNA vez,
    sobre la suma de todas las líneas, y no una vez por línea.
    """
    base = _q(_dec(subtotal))
    impuesto = _q(_dec(tax))
    return TaxResult(subtotal=base, tax=impuesto, total=base + impuesto)


def effective_tax_rate(subtotal, tax) -> Decimal:
    """Tasa implícita de un documento ya emitido, como fracción (0.16, no 16).

    Se usa cuando hay que recomponer totales de una venta existente (ticket
    reemitido, devolución) sin volver a leer el catálogo: el documento guarda su
    propia tasa efectiva en la proporción `tax / subtotal`, que ya contempla
    líneas exentas y ventas sin factura.
    """
    base = _dec(subtotal)
    if base <= 0:
        return Decimal("0")
    return _dec(tax) / base


def prorate_sale_after_refund(
    current_subtotal,
    current_tax,
    refunded_amount,
    refund_includes_tax: bool,
) -> TaxResult:
    """Totales del documento tras aprobar una devolución.

    Opera sobre el estado ACTUAL de la venta (que ya refleja las aprobaciones
    previas), así que varias devoluciones secuenciales convergen sin
    reconstruir el documento original.

    `refund_includes_tax` describe la naturaleza de `refunded_amount`:
    `app/crud/returns.py::create_return` lo calcula como `qty * unit_price`, y
    `unit_price` es neto o bruto según el modo de precio de la organización. Si
    es bruto hay que quitarle el IVA a la tasa efectiva de la venta antes de
    bajar el subtotal; si no, se descuenta directo. Confundir los dos modos
    descuadra los libros: por eso el parámetro es obligatorio y no tiene default.
    """
    base = _dec(current_subtotal)
    impuesto = _dec(current_tax)
    tasa = effective_tax_rate(base, impuesto)

    devuelto = _dec(refunded_amount)
    devuelto_neto = devuelto / (Decimal("1") + tasa) if refund_includes_tax else devuelto

    neto = base - devuelto_neto
    if neto < 0:
        neto = Decimal("0")
    neto = _q(neto)
    nuevo_iva = _q(neto * tasa)
    return TaxResult(subtotal=neto, tax=nuevo_iva, total=_q(neto + nuevo_iva))


def resolve_org_tax_mode(org) -> bool:
    """True si el precio del catálogo YA incluye IVA.

    Default **False** (precio neto, IVA encima) a propósito: es el
    comportamiento histórico de Atlas ONE y el de toda organización que todavía
    no tenga la columna poblada. Invertirlo cambiaría el total cobrado a
    clientes vivos.

    ⚠️ NO ENCENDER `price_includes_tax` EN NINGUNA ORGANIZACIÓN todavía. El
    carrito del POS calcula su total con un 16% fijo sumado encima
    (`frontend/src/store/posStore.ts`, `tax()` y `total()`): con el modo
    encendido la pantalla mostraría un total inflado frente al que cobra el
    backend, y el cajero cobraría de más o vería un descuadre en cada venta. El
    backend ya está listo; falta portar el espejo del front
    (`frontend/src/utils/tax.ts` en Atlas-Rmazh), que es trabajo aparte.
    """
    return bool(getattr(org, "price_includes_tax", False) or False)
