"""Planes comerciales de Atlas ONE: catalogo, topes y modulos que habilita cada uno.

Fuente: "Atlas ONE Pricing" (Atlas_Tech, 2026). Seis planes en orden; cada uno
incluye todo lo del anterior. El catalogo vive en codigo a proposito: cambia
poco y una tabla seria YAGNI.

Regla de oro — techo con base libre:

    permitido(org, modulo) = MODULOS_BASE
                           | modulos_del_preset(org.industry_type)
                           | obtener_plan(org.plan).modulos_crecimiento

Los modulos base y los del preset son de cualquier plan (un restaurante FREE
conserva mesas y cocina). El plan gobierna solo los modulos de crecimiento y
los topes de usuarios activos y sucursales que venden. Y NADA se apaga: los
topes frenan altas nuevas, `require_module` sigue leyendo organization_modules
tal cual, y cambiar de plan no toca esa tabla (ver docs/superpowers/specs/
2026-09-30-planes-y-topes-design.md).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Optional, Set

from sqlalchemy.orm import Session

from app.models.modules import IndustryPreset, Module, OrganizationModule
from app.models.organization import Branch, Organization
from app.modules.users.models import PlatformRole, Role, User, UserOrganization
from app.services.capabilities_service import INDUSTRY_PRESETS

# Modulos que toda organizacion puede tener, en cualquier plan: son el POS
# basico del papel de precios mas lo que los presets de punto de venta ya
# siembran hoy (etiquetas, clientes, escaner, variantes, escalones).
MODULOS_BASE: FrozenSet[str] = frozenset({
    "core", "pos", "catalog", "inventory", "cash_management", "payments",
    "returns", "reports", "crm", "labels", "scanner", "variants", "pricing",
    "users", "branch_catalog_enablement",
})

_START = frozenset({"quotes", "promotions"})
_PRO = _START | {"purchasing", "warehouse", "logistics", "invoicing"}
_BUSINESS = _PRO | {"finance", "hr", "commissions", "memberships", "customer_portal"}
_SCALE = _BUSINESS | {"ai"}

# Todo lo que depende del plan. Lo que no esta aqui ni en MODULOS_BASE es
# vertical: lo decide el preset (o ULTRA+, que permite todo el catalogo).
MODULOS_CRECIMIENTO: FrozenSet[str] = _SCALE


@dataclass(frozen=True)
class Plan:
    clave: str                      # lo que se guarda en organization.plan
    nombre: str                     # lo que ve la gente
    lema: str
    precio_mxn: int                 # informativo; el cobro no vive aqui
    precio_desde: bool
    max_usuarios: Optional[int]     # None = sin tope
    max_sucursales_venta: Optional[int]
    modulos_crecimiento: FrozenSet[str]  # acumulado
    permite_todo: bool = False      # ULTRA+: cualquier modulo del catalogo


PLANES: List[Plan] = [
    Plan("FREE", "ONE FREE", "Digitaliza", 0, False, 2, 1, frozenset()),
    Plan("START", "ONE START", "Opera", 499, False, 3, 1, _START),
    Plan("PRO", "ONE PRO", "Controla", 999, False, 10, 2, _PRO),
    Plan("BUSINESS", "BUSINESS", "Gestiona", 5000, False, 25, 5, _BUSINESS),
    Plan("SCALE", "SCALE", "Automatiza", 10000, False, 100, 20, _SCALE),
    Plan("ULTRA_PLUS", "ULTRA+", "Transforma", 30000, True, None, None, _SCALE, permite_todo=True),
]
PLANES_POR_CLAVE: Dict[str, Plan] = {p.clave: p for p in PLANES}


class LimitePlanAlcanzado(ValueError):
    """La organizacion ya llego al tope de su plan para esta alta."""


class ModuloFueraDePlan(ValueError):
    """El modulo no lo cubre ni la base, ni el preset, ni el plan actual."""


def claves_validas() -> List[str]:
    return [p.clave for p in PLANES]


def es_plan_valido(clave: Optional[str]) -> bool:
    return bool(clave) and clave in PLANES_POR_CLAVE


def obtener_plan(clave: Optional[str]) -> Plan:
    """FREE para NULL, vacio o desconocido: las filas viejas no deben romper nada."""
    return PLANES_POR_CLAVE.get(clave or "", PLANES_POR_CLAVE["FREE"])


def plan_minimo_para(modulo: str) -> Optional[Plan]:
    """El primer plan que incluye el modulo; None si no depende del plan (base o vertical)."""
    if modulo not in MODULOS_CRECIMIENTO:
        return None
    for p in PLANES:
        if modulo in p.modulos_crecimiento:
            return p
    return None


def _plan_minimo_usuarios(n: int) -> Plan:
    for p in PLANES:
        if p.max_usuarios is None or p.max_usuarios >= n:
            return p
    return PLANES[-1]


def _plan_minimo_sucursales(n: int) -> Plan:
    for p in PLANES:
        if p.max_sucursales_venta is None or p.max_sucursales_venta >= n:
            return p
    return PLANES[-1]


def modulos_del_preset(db: Session, industry_type) -> Set[str]:
    """Lo que el preset del giro siembra. La fila de industry_presets manda; si no
    hay, el fallback en codigo de capabilities_service. Sin giro: nada."""
    if industry_type is None:
        return set()
    valor = industry_type.value if hasattr(industry_type, "value") else str(industry_type)
    fila = db.query(IndustryPreset).filter(IndustryPreset.industry_type == valor).first()
    if fila is not None and fila.modules:
        return set(fila.modules)
    return set(INDUSTRY_PRESETS.get(industry_type, []))


def modulos_permitidos(db: Session, org: Organization) -> Set[str]:
    plan = obtener_plan(org.plan)
    if plan.permite_todo:
        return {k for (k,) in db.query(Module.key).all()}
    return set(MODULOS_BASE) | modulos_del_preset(db, org.industry_type) | set(plan.modulos_crecimiento)


def modulos_fuera_de_plan(db: Session, org: Organization) -> List[str]:
    """Encendidos que el plan actual no cubre: heredados, siguen funcionando."""
    permitidos = modulos_permitidos(db, org)
    encendidos = {
        m.module_key
        for m in db.query(OrganizationModule).filter(
            OrganizationModule.organization_id == org.id,
            OrganizationModule.is_enabled.is_(True),
        )
    }
    return sorted(encendidos - permitidos)


@dataclass
class Uso:
    usuarios_activos: int
    sucursales_venta: int


def uso(db: Session, org_id: int) -> Uso:
    """Usuarios activos enlazados a la org (sin personal de plataforma) y sucursales
    activas que venden.

    Los clientes del portal (CLIENTE) no son personal y no consumen asiento.
    """
    usuarios = (
        db.query(UserOrganization)
        .join(User, User.id == UserOrganization.user_id)
        .filter(
            UserOrganization.organization_id == org_id,
            UserOrganization.is_active.is_(True),
            User.is_active.is_(True),
            User.platform_role == PlatformRole.NONE,
            User.role != Role.CLIENTE,
        )
        .count()
    )
    sucursales = (
        db.query(Branch)
        .filter(
            Branch.organization_id == org_id,
            Branch.is_active.is_(True),
            Branch.can_sell.is_(True),
        )
        .count()
    )
    return Uso(usuarios_activos=usuarios, sucursales_venta=sucursales)


def verificar_alta_usuario(db: Session, org: Organization) -> None:
    plan = obtener_plan(org.plan)
    if plan.max_usuarios is None:
        return
    actual = uso(db, org.id).usuarios_activos
    if actual >= plan.max_usuarios:
        minimo = _plan_minimo_usuarios(actual + 1)
        raise LimitePlanAlcanzado(
            f"Tu plan {plan.nombre} permite {plan.max_usuarios} usuarios activos. "
            f"Para agregar más, sube a {minimo.nombre}."
        )


def verificar_alta_sucursal(db: Session, org: Organization) -> None:
    """Solo para sucursales que van a vender; almacenes, oficinas y matriz sin venta no cuentan."""
    plan = obtener_plan(org.plan)
    if plan.max_sucursales_venta is None:
        return
    actual = uso(db, org.id).sucursales_venta
    if actual >= plan.max_sucursales_venta:
        minimo = _plan_minimo_sucursales(actual + 1)
        n = plan.max_sucursales_venta
        cuantas = "1 sucursal que vende" if n == 1 else f"{n} sucursales que venden"
        raise LimitePlanAlcanzado(
            f"Tu plan {plan.nombre} permite {cuantas}. Para abrir otra, sube a {minimo.nombre}."
        )


def verificar_activar_modulo(db: Session, org: Organization, modulo: str, nombre_modulo: Optional[str] = None) -> None:
    if modulo in modulos_permitidos(db, org):
        return
    plan = obtener_plan(org.plan)
    etiqueta = nombre_modulo or modulo
    minimo = plan_minimo_para(modulo)
    if minimo is not None:
        raise ModuloFueraDePlan(
            f"El módulo {etiqueta} requiere el plan {minimo.nombre} o superior "
            f"(la organización está en {plan.nombre})."
        )
    preset = org.industry_type.value if org.industry_type is not None else "sin giro"
    raise ModuloFueraDePlan(
        f"El módulo {etiqueta} no forma parte del preset {preset} de la organización; "
        f"se habilita con ULTRA+ o cambiando de preset."
    )
