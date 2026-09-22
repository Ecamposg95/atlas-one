"""Layout ZPL de la etiqueta 51 x 25 mm a 203 dpi.

PORTADO de `atlas_labels/zpl.py` del agente de impresión
(<https://github.com/Ecamposg95/Atlas-Print-Agent>). Lo único que cambia
respecto del original es de dónde salen los datos: allá era el `Product`
dataclass que leía el CSV, aquí es `DatosEtiqueta`, que se arma desde la
variante de Atlas One. **Coordenadas, alturas, márgenes y el ZPL generado son
idénticos** — la tienda ya validó esa etiqueta en papel.

`layout()` es la única fuente tanto del ZPL como de la vista previa: la
pantalla no puede mentir sobre lo que va a salir del rollo.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional, Union

from .barcode import BarcodeSpec, detect

DPI = 203
LABEL_WIDTH = 408
LABEL_HEIGHT = 200
MARGIN = 12
TEXT_WIDTH = LABEL_WIDTH - 2 * MARGIN  # 384
SKU_WIDTH = 240
PRICE_WIDTH = 150
BARCODE_HEIGHT = 48
# Ancho promedio de un carácter en fuente escalable A0, como fracción de su altura.
CHAR_WIDTH_FACTOR = 0.55


@dataclass(frozen=True)
class DatosEtiqueta:
    """Lo que se imprime de UNA variante. Equivale al `Product` del agente.

    `price_text` guarda el precio cuando no es numérico (nunca pasa viniendo de
    la BD, donde es `Numeric`; se conserva por el endpoint de datos sueltos).
    """

    sku: str = ""
    name: str = ""
    brand: str = ""
    barcode: str = ""
    price: Optional[Decimal] = None
    price_text: str = ""
    size: str = ""
    color: str = ""

    @property
    def price_display(self) -> str:
        if self.price is not None:
            return f"${self.price:,.2f}"
        return self.price_text


def parse_price(text: str) -> tuple[Optional[Decimal], str]:
    """Devuelve (Decimal, "") si el texto es un número, o (None, texto) si no."""
    raw = (text or "").strip()
    if not raw:
        return None, ""
    cleaned = raw.replace("$", "").replace(",", "").replace(" ", "")
    try:
        return Decimal(cleaned), ""
    except InvalidOperation:
        return None, raw


def zpl_safe(value) -> str:
    return str(value or "").replace("^", " ").replace("~", " ").strip()


def text_width(text: str, height: int) -> int:
    return int(len(text) * height * CHAR_WIDTH_FACTOR)


def fit_text(value, height: int, max_width: int) -> str:
    text = zpl_safe(value)
    if text_width(text, height) <= max_width:
        return text
    while text and text_width(text + "..", height) > max_width:
        text = text[:-1]
    return text.rstrip() + ".."


@dataclass(frozen=True)
class Text:
    x: int
    y: int
    height: int
    text: str
    width: Optional[int] = None  # caja ^FB; solo se usa con align="R"
    align: str = "L"  # "L" | "R"


@dataclass(frozen=True)
class Bars:
    x: int
    y: int
    height: int
    bits: str  # módulos '1'/'0'
    module_width: int
    interpretation: str  # línea legible bajo las barras
    kind: str  # "EAN13" | "CODE128"
    data: str


Elemento = Union[Text, Bars]


def layout(product: DatosEtiqueta, spec: Optional[BarcodeSpec] = None) -> list[Elemento]:
    """Elementos de la etiqueta con sus coordenadas en dots. Única fuente para ZPL y preview."""
    spec = spec if spec is not None else detect(product.barcode)
    if spec is None:
        raise ValueError(f"{product.sku or product.name}: sin código de barras")

    elements: list[Elemento] = [
        Text(MARGIN, 8, 22, fit_text(product.brand, 22, TEXT_WIDTH)),
        Text(MARGIN, 34, 18, fit_text(product.name, 18, TEXT_WIDTH)),
    ]
    variant = fit_text(
        " / ".join(x for x in (zpl_safe(product.size), zpl_safe(product.color)) if x),
        15,
        TEXT_WIDTH,
    )
    if variant:
        elements.append(Text(MARGIN, 56, 15, variant))
    x = max(MARGIN, (LABEL_WIDTH - spec.width_dots) // 2)
    elements.append(Bars(x, 76, BARCODE_HEIGHT, spec.bits, spec.module_width, spec.data, spec.kind, spec.data))
    elements.append(Text(MARGIN, 168, 14, fit_text(product.sku, 14, SKU_WIDTH)))
    price = fit_text(product.price_display, 22, PRICE_WIDTH)
    if price:
        elements.append(Text(LABEL_WIDTH - MARGIN - PRICE_WIDTH, 162, 22, price, PRICE_WIDTH, "R"))
    return elements


def _element_lines(el: Elemento) -> list[str]:
    if isinstance(el, Bars):
        lines = [f"^FO{el.x},{el.y}^BY{el.module_width},2,{el.height}"]
        if el.kind == "EAN13":
            lines.append(f"^BEN,{el.height},Y,N^FD{el.data}^FS")
        else:
            lines.append(f"^BCN,{el.height},Y,N,N,A^FD{el.data}^FS")
        return lines
    if el.width is not None and el.align == "R":
        return [f"^FO{el.x},{el.y}^A0N,{el.height},{el.height}^FB{el.width},1,0,R^FD{el.text}^FS"]
    return [f"^FO{el.x},{el.y}^A0N,{el.height},{el.height}^FD{el.text}^FS"]


def build_label(product: DatosEtiqueta, copies: int = 1, spec: Optional[BarcodeSpec] = None) -> str:
    lines = [
        "^XA",
        f"^PW{LABEL_WIDTH}",
        f"^LL{LABEL_HEIGHT}",
        "^LH0,0",
        "^CI28",
        f"^PQ{max(1, int(copies))}",
    ]
    for el in layout(product, spec):
        lines.extend(_element_lines(el))
    lines.append("^XZ")
    return "\n".join(lines)


def build_batch(items: list[tuple[DatosEtiqueta, int]]) -> str:
    return "".join(build_label(product, copies) + "\n" for product, copies in items)


def build_test_label() -> str:
    product = DatosEtiqueta(
        sku="PRUEBA-51X25", name="Etiqueta de prueba 51 x 25 mm", brand="ATLAS TECH",
        barcode="2017000000013", price=Decimal("1800"), size="M", color="Negro",
    )
    return build_label(product, 1)
