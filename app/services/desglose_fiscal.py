"""Desglose fiscal de TODA venta: base e IVA por renglón y totales por tasa.

Por qué existe (megaplan CFDI de Atlas ONE Financials, fase 3): hasta aquí el
IVA solo se calculaba si el ticket pedía factura (`app/services/tax.py`), así
que una venta de mostrador quedaba con `tax_amount = 0` aunque el precio
cobrado sí trajera IVA. Para la factura global y para contabilizar la venta
hace falta saber, de cada ticket, cuánto fue base y cuánto impuesto, por tasa.

Este módulo NO cambia lo que se cobra ni las columnas de siempre
(`subtotal`, `tax_amount`, `total_amount`, `total_line`): calcula aparte una
fotografía fiscal y la guarda en columnas propias (`iva_*` del documento y del
renglón). Las de siempre siguen alimentando ticket, corte y reportes.

Regla (una sola, explícita):

1. **Lo cobrado ya trae el IVA.** Para el SAT, el importe que pagó el cliente
   por un renglón es contraprestación con IVA incluido, pida factura o no y
   sin importar el modo de precio de la organización. Con factura en modo
   neto el renglón cobrado ya es base + IVA; sin factura en modo neto el
   cliente pagó el precio de lista y ese precio contiene el IVA.
2. **El total manda.** El importe cobrado de cada renglón se redondea a
   centavos (half-up) y la diferencia de centavos contra la mercancía del
   documento (`total_amount - tip_amount`) se reparte un centavo a la vez,
   empezando por el renglón de mayor importe. Así la suma de los renglones es
   exactamente lo cobrado.
3. **Base por división, IVA por diferencia.** Con tasa t > 0:
   `base = round_half_up(cobrado / (1 + t))` e `iva = cobrado - base`. Así
   `base + iva == cobrado` por renglón, sin centavos sueltos, y el IVA siempre
   cae dentro de la tolerancia del SAT para el importe de un traslado
   (|iva - base·t| < 1 centavo). Tasa 0, exento y no objeto: base = cobrado.
4. **Totales por tasa = suma de renglones** (nunca se redondea el agregado).

La propina y la comisión de tarjeta NO entran: no son mercancía (la
clasificación fiscal de ambas es decisión del contador).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Optional, Sequence

CENTAVO = Decimal("0.01")
CERO = Decimal("0.00")

# --- Tratamiento de IVA del producto (columna `products.iva_tratamiento`) ---
IVA_16 = "16"
IVA_8 = "8"
IVA_0 = "0"
IVA_EXENTO = "EXENTO"
TRATAMIENTOS_IVA = (IVA_16, IVA_8, IVA_0, IVA_EXENTO)

TASAS = {
    IVA_16: Decimal("0.1600"),
    IVA_8: Decimal("0.0800"),
    IVA_0: Decimal("0.0000"),
}

# c_ObjetoImp del CFDI 4.0. "01" = no objeto de impuesto: el renglón no lleva
# IVA ni entra a ninguna tasa.
OBJETO_NO_OBJETO = "01"

# --- Formatos de las claves del SAT (sin catálogo completo: otra tarea lo carga en Financials) ---
_RE_CLAVE_PROD_SERV = re.compile(r"^\d{8}$")
_RE_CLAVE_UNIDAD = re.compile(r"^[A-Z0-9]{1,3}$")
_RE_OBJETO_IMP = re.compile(r"^0[1-8]$")
_RE_CODIGO_POSTAL = re.compile(r"^\d{5}$")


def _limpio(valor: Optional[str]) -> Optional[str]:
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto or None


def normalizar_clave_prod_serv(valor: Optional[str]) -> Optional[str]:
    """c_ClaveProdServ: ocho dígitos. Vacío = sin capturar (None)."""
    texto = _limpio(valor)
    if texto is None:
        return None
    if not _RE_CLAVE_PROD_SERV.match(texto):
        raise ValueError("La clave de producto o servicio del SAT son 8 dígitos, por ejemplo 01010101.")
    return texto


def normalizar_clave_unidad(valor: Optional[str]) -> Optional[str]:
    """c_ClaveUnidad: de 1 a 3 letras o números, en mayúsculas (H87, E48, KGM)."""
    texto = _limpio(valor)
    if texto is None:
        return None
    texto = texto.upper()
    if not _RE_CLAVE_UNIDAD.match(texto):
        raise ValueError("La clave de unidad del SAT son de 1 a 3 letras o números, por ejemplo H87.")
    return texto


def normalizar_objeto_imp(valor: Optional[str]) -> Optional[str]:
    """c_ObjetoImp: "01" a "08"."""
    texto = _limpio(valor)
    if texto is None:
        return None
    if not _RE_OBJETO_IMP.match(texto):
        raise ValueError("El objeto de impuesto del SAT va de 01 a 08.")
    return texto


def normalizar_tratamiento_iva(valor: Optional[str]) -> Optional[str]:
    """16, 8, 0 o EXENTO. Acepta "16%", "8.0", "exento"."""
    texto = _limpio(valor)
    if texto is None:
        return None
    texto = texto.upper().replace("%", "").strip()
    if texto in ("16.0", "16.00"):
        texto = IVA_16
    elif texto in ("8.0", "8.00"):
        texto = IVA_8
    elif texto in ("0.0", "0.00"):
        texto = IVA_0
    if texto not in TRATAMIENTOS_IVA:
        raise ValueError("La tasa de IVA debe ser 16, 8, 0 o EXENTO.")
    return texto


def normalizar_codigo_postal(valor: Optional[str]) -> Optional[str]:
    """Código postal fiscal: cinco dígitos."""
    texto = _limpio(valor)
    if texto is None:
        return None
    if not _RE_CODIGO_POSTAL.match(texto):
        raise ValueError("El código postal fiscal son 5 dígitos.")
    return texto


# --- Tratamiento efectivo de un renglón ---

@dataclass(frozen=True)
class Tratamiento:
    """Cómo se grava un renglón. `tipo_factor` sigue al CFDI: Tasa | Exento |
    None (no objeto de impuesto). `inferido` = el producto no tenía tasa de IVA
    capturada y se dedujo de las banderas del catálogo."""
    clave: str            # IVA_16 | IVA_8 | IVA_0 | IVA_EXENTO | "NO_OBJETO"
    tipo_factor: Optional[str]
    tasa: Optional[Decimal]
    inferido: bool


NO_OBJETO = "NO_OBJETO"


def tratamiento_de(
    iva_tratamiento: Optional[str],
    objeto_imp: Optional[str],
    has_iva: Optional[bool],
    tax_rate,
) -> Tratamiento:
    """Tratamiento fiscal de un renglón a partir del producto y su variante.

    Prioridad: objeto de impuesto "01" (no objeto) → tasa explícita del
    producto → inferencia desde `has_iva`/`tax_rate` de la variante.

    Inferencia (decisión pendiente del contador, ver PR): `has_iva` nació
    apagado por omisión y el formulario lo deja así, de modo que en la
    mayoría de los catálogos NO distingue "tasa 0" de "nadie lo marcó". Se
    infiere la tasa general (16 %) salvo que la variante diga 8 % con IVA
    encendido; el renglón queda con `inferido=True` para que nadie lo tome
    como clasificación revisada. Es el lado conservador: nunca declara menos
    IVA del que corresponde a la tasa general.
    """
    if objeto_imp == OBJETO_NO_OBJETO:
        return Tratamiento(NO_OBJETO, None, None, inferido=False)
    if iva_tratamiento in TASAS:
        return Tratamiento(iva_tratamiento, "Tasa", TASAS[iva_tratamiento], inferido=False)
    if iva_tratamiento == IVA_EXENTO:
        return Tratamiento(IVA_EXENTO, "Exento", None, inferido=False)
    tasa_variante = Decimal(str(tax_rate)) if tax_rate is not None else None
    if has_iva and tasa_variante is not None and tasa_variante == Decimal("8"):
        return Tratamiento(IVA_8, "Tasa", TASAS[IVA_8], inferido=True)
    return Tratamiento(IVA_16, "Tasa", TASAS[IVA_16], inferido=True)


# --- Cálculo ---

@dataclass(frozen=True)
class RenglonFiscal:
    cobrado: Decimal      # importe del renglón con IVA, a centavos
    base: Decimal
    iva: Decimal
    tratamiento: Tratamiento


@dataclass(frozen=True)
class DesgloseVenta:
    renglones: tuple
    base_16: Decimal
    iva_16: Decimal
    base_8: Decimal
    iva_8: Decimal
    base_0: Decimal
    base_exenta: Decimal
    base_no_objeto: Decimal

    @property
    def total(self) -> Decimal:
        return (
            self.base_16 + self.iva_16 + self.base_8 + self.iva_8
            + self.base_0 + self.base_exenta + self.base_no_objeto
        )


def _q(monto: Decimal) -> Decimal:
    return monto.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def repartir_a_centavos(importes: Sequence, total) -> list[Decimal]:
    """Redondea cada importe a centavos y reparte la diferencia contra `total`.

    La diferencia (normalmente 0 o ±1 centavo, por redondear el documento una
    sola vez y los renglones uno por uno) se aplica un centavo a la vez a los
    renglones de mayor importe, en orden estable. Garantiza
    `sum(resultado) == total` sin dejar ningún renglón negativo cuando el total
    no lo es.
    """
    redondeados = [_q(Decimal(str(i))) for i in importes]
    if not redondeados:
        return []
    objetivo = _q(Decimal(str(total)))
    diferencia = objetivo - sum(redondeados, CERO)
    if diferencia == 0:
        return redondeados
    paso = CENTAVO if diferencia > 0 else -CENTAVO
    orden = sorted(range(len(redondeados)), key=lambda k: (-redondeados[k], k))
    pendientes = int((diferencia / CENTAVO).copy_abs())
    k = 0
    vueltas_sin_aplicar = 0
    while pendientes > 0:
        idx = orden[k % len(orden)]
        k += 1
        if paso < 0 and redondeados[idx] <= 0:
            vueltas_sin_aplicar += 1
            if vueltas_sin_aplicar > len(orden):
                # Todo en cero y el total pide restar: se cuadra en el primero.
                redondeados[orden[0]] += paso
                pendientes -= 1
                vueltas_sin_aplicar = 0
            continue
        redondeados[idx] += paso
        pendientes -= 1
        vueltas_sin_aplicar = 0
    return redondeados


def desglosar_renglon(cobrado: Decimal, tratamiento: Tratamiento) -> RenglonFiscal:
    """Base e IVA de un renglón cuyo importe cobrado (con IVA) ya está a centavos."""
    if tratamiento.tasa is None or tratamiento.tasa == 0:
        return RenglonFiscal(cobrado=cobrado, base=cobrado, iva=CERO, tratamiento=tratamiento)
    base = _q(cobrado / (Decimal("1") + tratamiento.tasa))
    return RenglonFiscal(cobrado=cobrado, base=base, iva=cobrado - base, tratamiento=tratamiento)


def desglosar_venta(
    renglones: Iterable[tuple],
    total_mercancia,
) -> DesgloseVenta:
    """Desglose de un documento.

    `renglones`: pares `(importe_cobrado, Tratamiento)`; el importe puede venir
    sin redondear (como lo acumula el checkout). `total_mercancia`: lo que el
    documento cobró por mercancía, ya a centavos (`total_amount - tip_amount`).
    """
    pares = list(renglones)
    cobrados = repartir_a_centavos([p[0] for p in pares], total_mercancia)
    lineas = tuple(desglosar_renglon(c, t) for c, (_, t) in zip(cobrados, pares))

    def suma(campo: str, clave: str) -> Decimal:
        return sum((getattr(r, campo) for r in lineas if r.tratamiento.clave == clave), CERO)

    return DesgloseVenta(
        renglones=lineas,
        base_16=suma("base", IVA_16),
        iva_16=suma("iva", IVA_16),
        base_8=suma("base", IVA_8),
        iva_8=suma("iva", IVA_8),
        base_0=suma("base", IVA_0),
        base_exenta=suma("base", IVA_EXENTO),
        base_no_objeto=suma("base", NO_OBJETO),
    )


# --- Persistencia sobre los modelos ---

def tratamiento_de_variante(variant) -> Tratamiento:
    producto = getattr(variant, "product", None)
    return tratamiento_de(
        getattr(producto, "iva_tratamiento", None),
        getattr(producto, "sat_objeto_imp", None),
        getattr(variant, "has_iva", None),
        getattr(variant, "tax_rate", None),
    )


def lugar_de_expedicion(branch, organization) -> Optional[str]:
    """CP de la sucursal que vende; si no lo tiene (o no son 5 dígitos), el
    código postal fiscal de la organización. None si ninguno sirve."""
    for valor in (getattr(branch, "postal_code", None), getattr(organization, "codigo_postal_fiscal", None)):
        try:
            cp = normalizar_codigo_postal(valor)
        except ValueError:
            cp = None
        if cp:
            return cp
    return None


def aplicar_desglose(documento, lineas_con_variante: Sequence[tuple], *, branch=None, organization=None) -> DesgloseVenta:
    """Calcula y escribe la fotografía fiscal en el documento y sus renglones.

    `lineas_con_variante`: tríos `(SalesLineItem, variante, importe_cobrado)`.
    El importe cobrado es el del renglón CON IVA tal como lo cobró el checkout
    (sin redondear está bien). Usa `documento.total_amount` y
    `documento.tip_amount`, que deben estar ya asignados.
    """
    total_mercancia = Decimal(str(documento.total_amount or 0)) - Decimal(str(documento.tip_amount or 0))
    trios = list(lineas_con_variante)
    desglose = desglosar_venta(
        ((importe, tratamiento_de_variante(variante)) for _, variante, importe in trios),
        total_mercancia,
    )
    for (linea, variante, _), fiscal in zip(trios, desglose.renglones):
        producto = getattr(variante, "product", None)
        linea.sat_clave_prod_serv = getattr(producto, "sat_clave_prod_serv", None)
        linea.sat_clave_unidad = getattr(producto, "sat_clave_unidad", None)
        linea.sat_objeto_imp = getattr(producto, "sat_objeto_imp", None)
        linea.iva_tipo_factor = fiscal.tratamiento.tipo_factor
        linea.iva_tasa = fiscal.tratamiento.tasa
        linea.iva_base = fiscal.base
        linea.iva_importe = fiscal.iva
        linea.iva_inferido = fiscal.tratamiento.inferido
    documento.iva_base_16 = desglose.base_16
    documento.iva_16 = desglose.iva_16
    documento.iva_base_8 = desglose.base_8
    documento.iva_8 = desglose.iva_8
    documento.iva_base_0 = desglose.base_0
    documento.iva_base_exenta = desglose.base_exenta
    documento.iva_base_no_objeto = desglose.base_no_objeto
    documento.lugar_expedicion = lugar_de_expedicion(branch, organization)
    return desglose
