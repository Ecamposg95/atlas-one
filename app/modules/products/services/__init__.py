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
from .comun import (  # noqa: F401
    MANAGER_ROLES, PRODUCT_ADVANCED_ROLES, celda_decimal, celda_texto, celda_vacia,
    variante_principal, variantes_vivas,
)
from .validaciones import (  # noqa: F401
    atributos_principal, exigir_campos_de_cajero, validar_departamento_y_marca,
    validar_escalones, validar_precio, validar_sucursales_de_la_org,
)

from .sucursales import (  # noqa: F401
    armar_estado_por_sucursal, copiar_estado_por_sucursal, fijar_existencia,
    registrar_stock_inicial, resolver_sucursales_destino,
    sucursal_de_existencia_inicial, sucursales_que_venden,
)
