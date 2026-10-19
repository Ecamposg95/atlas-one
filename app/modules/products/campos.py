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
    "initial_stock", "prices", "packaging_units",
)
# Ficha boutique: nombre de venta y etiqueta de ropa/calzado.
CAMPOS_FICHA = ("gender", "model", "material")
# Presets que capturan la ficha. El resto la esconde (sin apagarla).
PRESETS_CON_FICHA = frozenset({"ATLAS_POS_BOUTIQUE"})
# Modo básico (2026-10): lo que las tiendas FREE no capturan (spec §2: 0 marcas,
# 0 fotos, 0 empaques, 0 tallas en 60 días). Igual que la ficha: se esconde, no
# se apaga; un producto que ya trae el dato lo sigue mostrando.
OCULTOS_BASICO = (
    "brand_id", "description", "unit", "image_url", "tax_rate",
    "packaging_units", "variants",
)


def campos_producto(preset: Optional[str], modulos: Iterable[str], perfil: str = "completo") -> dict:
    """`{"visibles": [...], "ocultos": [...]}` para el preset, módulos y perfil.

    Sin preset (org recién creada, contexto de plataforma) la ficha falla
    abierta. `variants` solo es visible con el módulo encendido. En perfil
    'basico' los campos de `OCULTOS_BASICO` pasan a ocultos.
    """
    con_ficha = preset is None or preset in PRESETS_CON_FICHA
    visibles = list(CAMPOS_BASE)
    if con_ficha:
        visibles.extend(CAMPOS_FICHA)
    if "variants" in set(modulos):
        visibles.append("variants")
    ocultos = [] if con_ficha else list(CAMPOS_FICHA)
    if perfil == "basico":
        visibles = [c for c in visibles if c not in OCULTOS_BASICO]
        ocultos.extend(c for c in OCULTOS_BASICO if c not in ocultos)
    return {"visibles": visibles, "ocultos": ocultos}
