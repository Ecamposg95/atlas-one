"""Catálogo de campos del producto por giro (mega plan 2026-10, principio 3).

Una sola fuente de verdad que consumen el formulario (hoy), el importador y el
asistente (después). Aquí solo se decide QUÉ se ve; nunca se borra ni se apaga
nada: un producto que ya trae un campo oculto lo sigue mostrando (eso lo
resuelve el frontend con el valor en mano).
"""
from typing import Iterable, Optional

# Siempre presentes, para cualquier giro.
CAMPOS_BASE = (
    "name", "sku", "barcode", "unit", "description", "image_url",
    "department_id", "brand_id", "price", "cost", "has_iva", "tax_rate",
    "initial_stock", "prices", "packaging_units", "uses_inventory",
)
# Ficha boutique: nombre de venta y etiqueta de ropa/calzado.
CAMPOS_FICHA = ("gender", "model", "material")
# Presets que capturan la ficha. El resto la esconde (sin apagarla).
PRESETS_CON_FICHA = frozenset({"ATLAS_POS_BOUTIQUE"})


def campos_producto(preset: Optional[str], modulos: Iterable[str]) -> dict:
    """`{"visibles": [...], "ocultos": [...]}` para el preset y módulos dados.

    Sin preset (org recién creada, contexto de plataforma) se falla abierto:
    todo visible. `variants` solo es visible con el módulo encendido.
    """
    con_ficha = preset is None or preset in PRESETS_CON_FICHA
    visibles = list(CAMPOS_BASE)
    if con_ficha:
        visibles.extend(CAMPOS_FICHA)
    if "variants" in set(modulos):
        visibles.append("variants")
    ocultos = [] if con_ficha else list(CAMPOS_FICHA)
    return {"visibles": visibles, "ocultos": ocultos}
