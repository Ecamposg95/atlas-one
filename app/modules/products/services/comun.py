"""Constantes y helpers que comparten servicios y routers de productos.

Viven aquí (y no en `router/_shared.py`) porque los servicios NO pueden
importar del router: `router/__init__` importa `core`, `core` importa los
servicios, y un servicio que importara `router._shared` cerraría el ciclo.
`router/_shared.py` re-exporta estos nombres con sus alias históricos.
"""
from __future__ import annotations

import math
from decimal import Decimal
from typing import Optional

from app.models import Product, ProductVariant

MANAGER_ROLES: frozenset = frozenset({"ADMINISTRADOR", "GERENTE", "DUEÑO"})

# Track 3 (POS bug-fix): el cajero es el usuario con más control en tiendas.
# Tiene CRUD completo + bulk + import/export + approve/reject/restore sobre
# productos visibles en su sucursal.
PRODUCT_ADVANCED_ROLES: frozenset = frozenset({"ADMINISTRADOR", "GERENTE", "DUEÑO", "CAJERO"})


def variantes_vivas(product: Product) -> list[ProductVariant]:
    """Variantes del producto que siguen vendibles (sin soft-delete)."""
    return [v for v in (product.variants or []) if v.deleted_at is None]


def variante_principal(product: Product) -> Optional[ProductVariant]:
    """La variante "principal": la primera VIVA en orden de creación.

    `product.variants[0]` incluye las retiradas (`DELETE /variants/{id}`), así
    que después de retirar la primera talla las rutas de escritura terminaban
    editando una variante que ya no se vende. None si no queda ninguna viva.
    """
    vivas = variantes_vivas(product)
    return vivas[0] if vivas else None


def celda_texto(val) -> str:
    """Celda de Excel/CSV como texto recortado ("" si viene vacía o 'nan')."""
    if val is None:
        return ""
    s = str(val).strip()
    if s.lower() == "nan":
        return ""
    return s


def celda_vacia(val) -> bool:
    """True cuando una celda de openpyxl/csv debe tratarse como ausente."""
    if val is None:
        return True
    if isinstance(val, float) and math.isnan(val):
        return True
    if isinstance(val, str) and val.strip().lower() in ("nan", "none"):
        return True
    return False


def celda_decimal(val, default: Decimal = Decimal(0)) -> Decimal:
    try:
        if celda_vacia(val):
            return default
        return Decimal(str(val))
    except Exception:
        return default
