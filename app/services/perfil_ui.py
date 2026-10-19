"""Perfil de interfaz de una organización: 'basico' o 'completo' (modo básico, 2026-10).

La interfaz se acorta para quien no paga licencia: FREE → básico, cualquier
otro plan → completo. La plataforma puede forzarlo por organización con
`organization.perfil_ui` ('basico' | 'completo'); NULL o 'auto' = derivar del
plan. Aquí solo se decide qué se MUESTRA: el backend no cambia gating,
validaciones ni endpoints por perfil (principio de los planes: nada se apaga).

Sin imports de modelos en cabecera: `app/modules/tenants/schemas.py` importa
`normalizar_perfil_ui` y un import de `plans` aquí arriba sería circular.
"""
from __future__ import annotations

from typing import Optional

BASICO = "basico"
COMPLETO = "completo"
AUTO = "auto"
VALORES_PERFIL_UI = (AUTO, BASICO, COMPLETO)
_FORZABLES = (BASICO, COMPLETO)


def normalizar_perfil_ui(valor: Optional[str]) -> Optional[str]:
    """None pasa (el PUT no lo manda); cualquier otro valor se limpia y tiene
    que ser auto/basico/completo, o la org quedaría con un perfil muerto."""
    if valor is None:
        return None
    limpio = str(valor).strip().lower()
    if limpio not in VALORES_PERFIL_UI:
        raise ValueError(f"debe ser uno de: {', '.join(VALORES_PERFIL_UI)}")
    return limpio


def perfil_efectivo(org) -> str:
    """'basico' | 'completo' para la organización. Sin org (plataforma) = completo.

    Un valor forzado que no se reconoce cuenta como 'auto'. Solo el plan
    explícito FREE deriva a básico: NULL o desconocido es completo (al revés
    que los topes de `plans.obtener_plan`: la interfaz no cambia sin decidirlo).
    """
    if org is None:
        return COMPLETO
    forzado = str(getattr(org, "perfil_ui", None) or AUTO).strip().lower()
    if forzado in _FORZABLES:
        return forzado
    plan = str(getattr(org, "plan", None) or "").strip().upper()
    return BASICO if plan == "FREE" else COMPLETO
