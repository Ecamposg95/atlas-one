"""Matriz del agente: qué herramientas recibe cada rol (fase A1, solo consultas).

**Esta tabla es la única fuente.** `herramientas.definiciones(ctx)` le entrega
al modelo solo las de su fila y `herramientas.ejecutar` rechaza cualquier otra
aunque el modelo la nombre. Un rol que no aparece aquí no tiene agente.

El *perfil* decide cuánto enseña cada herramienta (no cuáles hay):

- `caja` (cajera, vendedor): su sucursal, sin costos, sin cantidades de otras.
- `gerencia` (gerente): lo de dirección, confinado a su sucursal.
- `direccion` (administrador, dueño): toda la empresa o la sucursal que pidan.

La organización y la sucursal salen SIEMPRE de la sesión. Solo `direccion`
puede nombrar una sucursal (`sucursal_id`), y se valida contra la organización.

Superadministrador y soporte no entran en A1 (fase A4): `tiene_agente` es False.
"""
from __future__ import annotations

from typing import Any, Optional

CAJA, GERENCIA, DIRECCION = "caja", "gerencia", "direccion"

PERFIL_POR_ROL: dict[str, str] = {
    "CAJERO": CAJA,
    "VENDEDOR": CAJA,
    "GERENTE": GERENCIA,
    "ADMINISTRADOR": DIRECCION,
    "DUEÑO": DIRECCION,
}

_CAJA = (
    "buscar_producto",
    "consultar_existencias",
    "disponibilidad_otras_sucursales",
    "mis_ventas_hoy",
)
_GERENCIA = (
    "buscar_producto",
    "consultar_existencias",
    "disponibilidad_otras_sucursales",
    "resumen_ventas",
    "estado_conteos",
    "stock_bajo",
    "listar_departamentos",
    "listar_marcas",
)
_DIRECCION = (
    "buscar_producto",
    "consultar_existencias",
    "resumen_ventas",
    "comparar_sucursales",
    "estado_conteos",
    "stock_bajo",
    "valor_inventario",
    "listar_departamentos",
    "listar_marcas",
)

HERRAMIENTAS_POR_ROL: dict[str, tuple[str, ...]] = {
    "CAJERO": _CAJA,
    "VENDEDOR": _CAJA,
    "GERENTE": _GERENCIA,
    "ADMINISTRADOR": _DIRECCION,
    "DUEÑO": _DIRECCION,
}


def rol_de(user: Any) -> str:
    rol = getattr(user, "role", None)
    return str(getattr(rol, "value", rol) or "")


def es_de_plataforma(user: Any) -> bool:
    plataforma = getattr(user, "platform_role", None)
    return str(getattr(plataforma, "value", plataforma) or "NONE") in ("SUPERADMIN", "SUPPORT")


def perfil_de(user: Any) -> Optional[str]:
    if es_de_plataforma(user):
        return None
    return PERFIL_POR_ROL.get(rol_de(user))


def herramientas_de(user: Any) -> tuple[str, ...]:
    if es_de_plataforma(user):
        return ()
    return HERRAMIENTAS_POR_ROL.get(rol_de(user), ())


def tiene_agente(user: Any) -> bool:
    return bool(herramientas_de(user))
