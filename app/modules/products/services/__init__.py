"""Capa de servicio del catálogo de productos (SP1 · Altas, 2026-10).

Un solo lugar para crear, editar, duplicar, importar y crear variantes. Los
servicios hacen `flush`, nunca `commit` (lo hace el handler o el SAVEPOINT del
importador) y levantan `HTTPException` con el mismo `detail` que usaban los
handlers. Nada de aquí importa de `app/modules/products/router/`.
"""
from .codigos import (  # noqa: F401
    asignar_barcode_interno, sku_de_copia, sku_en_uso, validar_barcode_libre,
    validar_sku_unico,
)
