"""Estado de construcción de cada módulo del catálogo: la única fuente.

Decisión del dueño (2026-11-24): lo que se vende y no está construido se OCULTA
hasta que exista. Aquí se declara, módulo por módulo, en cuál de tres estados está:

    disponible       backend real + pantalla real: se ofrece y se muestra.
    en_construccion  hay la mitad (backend sin pantalla, o al revés): no se muestra.
    oculto           cascarón o sin código: no se muestra.

Solo es de INTERFAZ. No apaga nada: `organization_modules` no se toca,
`require_module` sigue leyendo lo que la organización tiene encendido y la
plataforma puede seguir encendiendo cualquier módulo (lo ve marcado "En
construcción" o "No construido"). Si una organización ya tenía encendido un
módulo no disponible, sigue encendido y simplemente deja de verse.

Quién lo lee: `/users/me/context` (`modulos_no_disponibles`, para menú e Inicio),
`/platform/plans` y `/platform/organizations/{id}/modules` (marcas), y el upsell
de plataforma. El frontend guarda un espejo en `frontend/src/utils/estadoModulos.ts`
que una prueba de vitest compara contra este archivo; por eso cada módulo va en
una línea `"clave": ESTADO,` — no cambies el formato.

Evidencia de cada estado: docs/presets/ESTADO-DE-MODULOS.md.
Para destapar un módulo terminado: CLAUDE.md §5 «Destapar un módulo».
"""
from __future__ import annotations

from typing import Dict, Iterable, List

DISPONIBLE = "disponible"
EN_CONSTRUCCION = "en_construccion"
OCULTO = "oculto"
ESTADOS = (DISPONIBLE, EN_CONSTRUCCION, OCULTO)

ESTADO_MODULOS: Dict[str, str] = {
    # ── Base (cualquier plan) ────────────────────────────────────────────────
    "core": DISPONIBLE,
    "pos": DISPONIBLE,
    "catalog": DISPONIBLE,
    "inventory": DISPONIBLE,
    "cash_management": DISPONIBLE,
    "payments": DISPONIBLE,
    "returns": DISPONIBLE,
    "reports": DISPONIBLE,
    "crm": DISPONIBLE,
    "labels": DISPONIBLE,
    "scanner": DISPONIBLE,
    "variants": DISPONIBLE,
    "pricing": DISPONIBLE,
    "users": DISPONIBLE,
    "branch_catalog_enablement": DISPONIBLE,
    # ── Crecimiento (los gobierna el plan) ───────────────────────────────────
    "quotes": DISPONIBLE,
    "promotions": OCULTO,
    "purchasing": DISPONIBLE,
    "warehouse": EN_CONSTRUCCION,
    "logistics": DISPONIBLE,
    "invoicing": EN_CONSTRUCCION,
    "finance": DISPONIBLE,
    "hr": DISPONIBLE,
    "commissions": OCULTO,
    "memberships": OCULTO,
    "customer_portal": DISPONIBLE,
    "ai": EN_CONSTRUCCION,
    # ── Verticales (los trae el preset) ──────────────────────────────────────
    "appointments": EN_CONSTRUCCION,
    "tables": DISPONIBLE,
    "kitchen": DISPONIBLE,
    "menu": DISPONIBLE,
    "recipes": DISPONIBLE,
    "bar": DISPONIBLE,
    "tips": DISPONIBLE,
    "workshops": OCULTO,
    "manufacturing": OCULTO,
    # ── Contratación aparte ──────────────────────────────────────────────────
    "tienda_en_linea": DISPONIBLE,
    # ── Claves viejas que solo siembra seed_global_modules ───────────────────
    "kds": OCULTO,
    "work_orders": OCULTO,
}


def estado_de(clave: str) -> str:
    """Estado declarado; una clave que no está aquí (módulo creado a mano desde
    la plataforma) no tiene código detrás: `oculto`."""
    return ESTADO_MODULOS.get(clave, OCULTO)


def esta_disponible(clave: str) -> bool:
    return estado_de(clave) == DISPONIBLE


def no_disponibles() -> Dict[str, str]:
    """`{clave: estado}` de lo que la interfaz no debe mostrar. Viaja en /me/context."""
    return {k: v for k, v in ESTADO_MODULOS.items() if v != DISPONIBLE}


def solo_disponibles(claves: Iterable[str]) -> List[str]:
    return sorted(k for k in claves if esta_disponible(k))


def solo_no_disponibles(claves: Iterable[str]) -> List[str]:
    return sorted(k for k in claves if not esta_disponible(k))
