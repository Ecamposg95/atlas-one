"""Contrato HTTP del módulo de etiquetas (Pydantic v2).

El frontend dibuja la etiqueta a partir de `elements`, que es `layout()`
serializado: misma fuente que el ZPL, así la pantalla no puede mentir sobre lo
que sale del rollo.
"""
from __future__ import annotations

from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field

# Topes del lote. `MAX_COPIAS` es por renglón (un error de dedo no vacía el
# rollo); `MAX_ETIQUETAS` es del trabajo entero.
MAX_COPIAS = 99
MAX_ETIQUETAS = 500


class LabelCandidate(BaseModel):
    """Una variante viva con todo lo que la etiqueta y la tabla necesitan."""

    variant_id: str
    product_id: str
    sku: str = ""
    barcode: str = ""
    product_name: str = ""
    sale_name: str = ""
    brand: str = ""
    department: str = ""
    gender: str = ""
    size: str = ""
    color: str = ""
    price: float = 0.0
    stock: float = 0.0
    # Copias sugeridas = existencia, topada en MAX_COPIAS.
    copies_default: int = 0
    printable: bool = True
    # Por qué NO se puede imprimir. `None` cuando `printable` es True.
    reason: Optional[str] = None


class CandidatesResponse(BaseModel):
    items: List[LabelCandidate]
    total: int


class PreviewRequest(BaseModel):
    """O `variant_id`, o los datos sueltos (para probar un texto sin catálogo)."""

    variant_id: Optional[str] = None
    sku: Optional[str] = None
    name: Optional[str] = None
    brand: Optional[str] = None
    barcode: Optional[str] = None
    price: Optional[str] = None
    size: Optional[str] = None
    color: Optional[str] = None


class TextElement(BaseModel):
    type: Literal["text"] = "text"
    x: int
    y: int
    height: int
    text: str
    width: Optional[int] = None  # caja ^FB; solo con align="R"
    align: str = "L"


class BarcodeElement(BaseModel):
    type: Literal["barcode"] = "barcode"
    x: int
    y: int
    height: int
    bits: str  # módulos '1' (barra) / '0' (espacio)
    module_width: int  # dots por módulo
    kind: str  # "EAN13" | "CODE128"
    data: str
    interpretation: str


class PreviewResponse(BaseModel):
    width: int
    height: int
    kind: str
    warning: str = ""
    elements: List[Union[TextElement, BarcodeElement]]
    zpl: str


class JobItem(BaseModel):
    variant_id: str
    copies: int = Field(default=1, ge=1, le=MAX_COPIAS)


class JobRequest(BaseModel):
    items: List[JobItem] = Field(min_length=1)


class SkippedItem(BaseModel):
    variant_id: str
    sku: str = ""
    reason: str


class JobResponse(BaseModel):
    # ZPL del lote en base64: el navegador se lo pasa tal cual al agente
    # (`POST https://localhost:9100/print`). El backend NO imprime.
    content_base64: str
    labels: int
    skipped: List[SkippedItem]


class TestLabelResponse(BaseModel):
    content_base64: str
