# Planes y topes de Atlas ONE — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que `Organization.plan` signifique algo: un catálogo de seis planes en código, topes de usuarios activos y sucursales que venden que frenan altas nuevas, y gating de módulos de crecimiento al encenderlos desde la plataforma, sin quitarle nada a ninguna organización existente.

**Architecture:** Un servicio puro `app/services/plans.py` (catálogo + reglas + conteos) que consumen cuatro puntos de enforcement ya existentes (alta/reactivación de usuario, alta/activación de venta de sucursal, toggle de módulo, PUT de organización) y una API de plataforma nueva (`/api/platform/plans`, `/organizations/{id}/plan-uso`) que alimenta la pantalla de detalle de organización y la lista. `require_module` y `apply_industry_preset` no cambian: los módulos encendidos se heredan.

**Tech Stack:** FastAPI + SQLAlchemy 2 + Pydantic v2; pytest sobre SQLite (`python3 -m pytest -q -p no:warnings`, Python 3.12 del sistema); React 18 + TypeScript + Vite (`cd frontend && npm run build` = `tsc && vite build`).

**Spec:** `docs/superpowers/specs/2026-09-30-planes-y-topes-design.md`

## Global Constraints

- **`main` = producción.** Trabajar en `feat/planes`; commits locales sí; **push y merge solo con permiso explícito**.
- **Sin migración de esquema**: `organization.plan` ya existe como `String`. `railway_init.py` no se toca.
- **Nada se apaga**: cambiar de plan no modifica `organization_modules`; `require_module` no cambia; `apply_industry_preset` no cambia.
- **Regla de módulos permitidos**: `MODULOS_BASE ∪ modulos_del_preset(org.industry_type) ∪ plan.modulos_crecimiento`; ULTRA_PLUS permite todo el catálogo.
- **Topes**: usuarios activos FREE 2 / START 3 / PRO 10 / BUSINESS 25 / SCALE 100 / ULTRA_PLUS sin tope; sucursales que venden FREE 1 / START 1 / PRO 2 / BUSINESS 5 / SCALE 20 / ULTRA_PLUS sin tope. Usuarios: enlaces `UserOrganization.is_active` con `User.is_active` y `User.platform_role == NONE`. Sucursales: `Branch.is_active and can_sell`.
- **Claves**: `FREE`, `START`, `PRO`, `BUSINESS`, `SCALE`, `ULTRA_PLUS`; nombre visible de la última "ULTRA+". `obtener_plan(None|""|desconocido)` → FREE.
- **Mensajes** (exactos, español): `"Tu plan {nombre} permite {n} usuarios activos. Para agregar más, sube a {nombre_minimo}."` · `"Tu plan {nombre} permite {n} sucursal(es) que vende(n). Para abrir otra, sube a {nombre_minimo}."` · `"El módulo {nombre_modulo} requiere el plan {nombre_minimo} o superior (la organización está en {nombre})."` · módulo fuera de preset y de todo plan salvo ULTRA+: `"El módulo {nombre_modulo} no forma parte del preset {preset} de la organización; se habilita con ULTRA+ o cambiando de preset."`
- Los routers convierten `LimitePlanAlcanzado`/`ModuloFueraDePlan` en `HTTPException(403, detail=str(e))`; plan desconocido en el PUT → 400 con las claves válidas.
- Estilo: comentarios en español, `from __future__ import annotations`, type hints, sin `print()` de depuración. Frontend: tokens `--p-*` de la plataforma, componentes del kit (`StatusBadge`, `ConfirmDialog`, `toast`).
- Commits terminan con:
  ```
  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_014rnFXXn9to8upxnFg1bpw8
  ```
- Nunca dos `pytest` a la vez en el mismo worktree. Suite completa siempre con `--ignore=tests/test_cash_complete.py`.

## Review Focus

1. **Usuario inactivo que se reactiva por `PUT`** cuando la org ya está al tope: debe recibir 403, no colarse por la rama de actualización. → Tarea 2.
2. **Sucursal que no vende y se pasa a vender por `PUT can_sell=true`** al tope: 403. Y una matriz HQ nueva con `can_sell` explícito `True` sí cuenta. → Tarea 2.
3. **Organización sin `industry_type`** (filas viejas, preset `CUSTOM`): `modulos_del_preset` devuelve vacío y nada revienta; FREE permite base; el toggle de un módulo vertical da el mensaje de "fuera de preset". → Tarea 1.
4. **Módulo encendido a mano fuera de plan** (herencia): `require_module` lo deja pasar y el detalle lo lista en `modulos_fuera_de_plan`. → Tareas 2 y 3.
5. **Bajar de plan desde la UI** no debe disparar ningún apagado: la confirmación lo dice y la petición es solo `PUT {plan}`. → Tarea 4 (y Tarea 2 prueba que el PUT no toca `organization_modules`).

---

### Task 1: `app/services/plans.py` — catálogo, reglas y conteos

**Files:**
- Create: `app/services/plans.py`
- Test: `tests/test_planes.py`

**Interfaces:**
- Consumes: `Organization`, `Branch` (`app.models.organization`); `IndustryPreset`, `Module` (`app.models.modules`); `User`, `UserOrganization`, `PlatformRole` (`app.modules.users.models`); `INDUSTRY_PRESETS` (`app.services.capabilities_service`); `IndustryType` (`app.modules.tenants.models`).
- Produces (lo usan las tareas 2 y 3):
  - `MODULOS_BASE: frozenset[str]`, `MODULOS_CRECIMIENTO: frozenset[str]`, `PLANES: list[Plan]`, `PLANES_POR_CLAVE: dict[str, Plan]`
  - `@dataclass(frozen=True) Plan(clave, nombre, lema, precio_mxn: int, precio_desde: bool, max_usuarios: Optional[int], max_sucursales_venta: Optional[int], modulos_crecimiento: frozenset[str], permite_todo: bool)`
  - `obtener_plan(clave: Optional[str]) -> Plan`, `es_plan_valido(clave: Optional[str]) -> bool`, `claves_validas() -> list[str]`
  - `modulos_del_preset(db, industry_type) -> set[str]`, `modulos_permitidos(db, org) -> set[str]`, `plan_minimo_para(modulo: str) -> Optional[Plan]`
  - `@dataclass Uso(usuarios_activos: int, sucursales_venta: int)`, `uso(db, org_id: int) -> Uso`
  - `class LimitePlanAlcanzado(ValueError)`, `class ModuloFueraDePlan(ValueError)`
  - `verificar_alta_usuario(db, org) -> None`, `verificar_alta_sucursal(db, org) -> None`, `verificar_activar_modulo(db, org, modulo: str, nombre_modulo: Optional[str] = None) -> None`
  - `modulos_fuera_de_plan(db, org) -> list[str]` (encendidos y no permitidos, ordenados)

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_planes.py`:

```python
"""Tests: catalogo de planes, reglas de modulos y topes (app/services/plans.py)."""
import pytest

from app.models.modules import Module, OrganizationModule
from app.models.organization import Branch
from app.modules.tenants.models import BranchType, IndustryType
from app.modules.users.models import PlatformRole, Role, User, UserOrganization
from app.services import plans


def _usuario(db, org, username, activo=True, platform_role=PlatformRole.NONE, enlace_activo=True):
    u = User(username=username, password_hash="x", role=Role.CAJERO, is_active=activo, platform_role=platform_role)
    db.add(u); db.flush()
    db.add(UserOrganization(user_id=u.id, organization_id=org.id, org_role="MEMBER", is_active=enlace_activo)); db.flush()
    return u


def _sucursal(db, org, nombre, can_sell=True, activa=True, tipo=BranchType.STORE):
    b = Branch(name=nombre, branch_type=tipo, can_sell=can_sell, is_active=activa, organization_id=org.id)
    db.add(b); db.flush()
    return b


class TestCatalogo:
    def test_seis_planes_en_orden(self):
        assert [p.clave for p in plans.PLANES] == ["FREE", "START", "PRO", "BUSINESS", "SCALE", "ULTRA_PLUS"]
        assert plans.PLANES_POR_CLAVE["ULTRA_PLUS"].nombre == "ULTRA+"

    def test_cada_plan_incluye_al_anterior(self):
        for ant, sig in zip(plans.PLANES, plans.PLANES[1:]):
            assert ant.modulos_crecimiento <= sig.modulos_crecimiento, (ant.clave, sig.clave)
            if ant.max_usuarios is not None and sig.max_usuarios is not None:
                assert ant.max_usuarios <= sig.max_usuarios
            if ant.max_sucursales_venta is not None and sig.max_sucursales_venta is not None:
                assert ant.max_sucursales_venta <= sig.max_sucursales_venta

    def test_topes_del_spec(self):
        topes = {p.clave: (p.max_usuarios, p.max_sucursales_venta) for p in plans.PLANES}
        assert topes == {
            "FREE": (2, 1), "START": (3, 1), "PRO": (10, 2),
            "BUSINESS": (25, 5), "SCALE": (100, 20), "ULTRA_PLUS": (None, None),
        }

    def test_modulos_de_crecimiento_del_spec(self):
        c = {p.clave: set(p.modulos_crecimiento) for p in plans.PLANES}
        assert c["FREE"] == set()
        assert c["START"] == {"quotes", "promotions"}
        assert c["PRO"] == c["START"] | {"purchasing", "warehouse", "logistics", "invoicing"}
        assert c["BUSINESS"] == c["PRO"] | {"finance", "hr", "commissions", "memberships", "customer_portal"}
        assert c["SCALE"] == c["BUSINESS"] | {"ai"}
        assert c["ULTRA_PLUS"] == c["SCALE"] and plans.PLANES_POR_CLAVE["ULTRA_PLUS"].permite_todo
        assert plans.MODULOS_CRECIMIENTO == frozenset(c["SCALE"])

    def test_base_y_crecimiento_no_se_pisan(self):
        assert not (plans.MODULOS_BASE & plans.MODULOS_CRECIMIENTO)

    def test_todo_modulo_gobernado_existe_en_el_catalogo(self, db):
        from app.services.capabilities_service import seed_global_modules
        seed_global_modules(db)
        claves = {k for (k,) in db.query(Module.key)}
        assert plans.MODULOS_CRECIMIENTO <= claves
        assert plans.MODULOS_BASE <= claves

    @pytest.mark.parametrize("clave", [None, "", "XYZ", "free"])
    def test_obtener_plan_desconocido_es_free(self, clave):
        assert plans.obtener_plan(clave).clave == "FREE"

    def test_es_plan_valido(self):
        assert plans.es_plan_valido("ULTRA_PLUS") and plans.es_plan_valido("FREE")
        assert not plans.es_plan_valido("GOLD") and not plans.es_plan_valido(None)
        assert plans.claves_validas() == ["FREE", "START", "PRO", "BUSINESS", "SCALE", "ULTRA_PLUS"]


class TestModulosPermitidos:
    def test_pos_free_tiene_base_y_preset_pero_no_quotes(self, db, org):
        org.industry_type = IndustryType.ATLAS_POS; org.plan = "FREE"; db.flush()
        permitidos = plans.modulos_permitidos(db, org)
        assert {"pos", "catalog", "labels", "crm"} <= permitidos
        assert "quotes" not in permitidos and "ai" not in permitidos

    def test_pos_start_tiene_quotes(self, db, org):
        org.industry_type = IndustryType.ATLAS_POS; org.plan = "START"; db.flush()
        assert "quotes" in plans.modulos_permitidos(db, org)

    def test_gastro_free_conserva_mesas_y_cocina(self, db, org):
        org.industry_type = IndustryType.RESTAURANT_FULL; org.plan = "FREE"; db.flush()
        permitidos = plans.modulos_permitidos(db, org)
        assert {"tables", "kds", "menu"} <= permitidos

    def test_preset_de_la_base_de_datos_manda_sobre_el_fallback(self, db, org):
        from app.models.modules import IndustryPreset
        db.add(IndustryPreset(industry_type="ATLAS_POS", display_name="x", modules=["core", "pos", "workshops"])); db.flush()
        org.industry_type = IndustryType.ATLAS_POS; org.plan = "FREE"; db.flush()
        assert "workshops" in plans.modulos_permitidos(db, org)

    def test_sin_industria_solo_base(self, db, org):
        """Review Focus #3."""
        org.industry_type = None; org.plan = "FREE"; db.flush()
        assert plans.modulos_del_preset(db, None) == set()
        assert plans.modulos_permitidos(db, org) == set(plans.MODULOS_BASE)

    def test_ultra_plus_permite_todo_el_catalogo(self, db, org):
        from app.services.capabilities_service import seed_global_modules
        seed_global_modules(db)
        org.industry_type = IndustryType.ATLAS_POS; org.plan = "ULTRA_PLUS"; db.flush()
        claves = {k for (k,) in db.query(Module.key)}
        assert plans.modulos_permitidos(db, org) == claves

    def test_plan_minimo_para(self):
        assert plans.plan_minimo_para("quotes").clave == "START"
        assert plans.plan_minimo_para("purchasing").clave == "PRO"
        assert plans.plan_minimo_para("hr").clave == "BUSINESS"
        assert plans.plan_minimo_para("ai").clave == "SCALE"
        assert plans.plan_minimo_para("pos") is None
        assert plans.plan_minimo_para("tables") is None


class TestUso:
    def test_cuenta_usuarios_activos_y_sucursales_que_venden(self, db, org, admin_user, hq_branch, branch_a):
        # admin_user (activo, NONE) + hq_branch (no vende) + branch_a (vende)
        _usuario(db, org, "inactivo", activo=False)
        _usuario(db, org, "enlace_apagado", enlace_activo=False)
        _usuario(db, org, "soporte", platform_role=PlatformRole.SUPERADMIN)
        _sucursal(db, org, "Almacen", can_sell=False, tipo=BranchType.WAREHOUSE)
        _sucursal(db, org, "Cerrada", can_sell=True, activa=False)
        u = plans.uso(db, org.id)
        assert u.usuarios_activos == 1
        assert u.sucursales_venta == 1


class TestVerificaciones:
    def test_alta_usuario_al_tope_free_nombra_start(self, db, org, admin_user, cajero_a):
        org.plan = "FREE"; db.flush()
        with pytest.raises(plans.LimitePlanAlcanzado) as e:
            plans.verificar_alta_usuario(db, org)
        assert str(e.value) == "Tu plan ONE FREE permite 2 usuarios activos. Para agregar más, sube a ONE START."

    def test_alta_usuario_bajo_el_tope_pasa(self, db, org, admin_user):
        org.plan = "FREE"; db.flush()
        plans.verificar_alta_usuario(db, org)

    def test_alta_usuario_ultra_plus_nunca_bloquea(self, db, org, admin_user, cajero_a):
        org.plan = "ULTRA_PLUS"; db.flush()
        plans.verificar_alta_usuario(db, org)

    def test_alta_sucursal_al_tope_free_nombra_pro(self, db, org, branch_a):
        org.plan = "FREE"; db.flush()
        with pytest.raises(plans.LimitePlanAlcanzado) as e:
            plans.verificar_alta_sucursal(db, org)
        assert str(e.value) == "Tu plan ONE FREE permite 1 sucursal que vende. Para abrir otra, sube a ONE PRO."

    def test_alta_sucursal_business_con_dos_pasa(self, db, org, branch_a, branch_b):
        org.plan = "BUSINESS"; db.flush()
        plans.verificar_alta_sucursal(db, org)

    def test_mensaje_plural_de_sucursales(self, db, org, branch_a, branch_b):
        org.plan = "PRO"; db.flush()
        with pytest.raises(plans.LimitePlanAlcanzado) as e:
            plans.verificar_alta_sucursal(db, org)
        assert str(e.value) == "Tu plan ONE PRO permite 2 sucursales que venden. Para abrir otra, sube a BUSINESS."

    def test_activar_modulo_fuera_de_plan(self, db, org):
        org.industry_type = IndustryType.ATLAS_POS; org.plan = "FREE"; db.flush()
        with pytest.raises(plans.ModuloFueraDePlan) as e:
            plans.verificar_activar_modulo(db, org, "quotes", "Cotizaciones")
        assert str(e.value) == "El módulo Cotizaciones requiere el plan ONE START o superior (la organización está en ONE FREE)."

    def test_activar_modulo_base_o_de_preset_pasa(self, db, org):
        org.industry_type = IndustryType.RESTAURANT_FULL; org.plan = "FREE"; db.flush()
        plans.verificar_activar_modulo(db, org, "pos")
        plans.verificar_activar_modulo(db, org, "tables")

    def test_activar_modulo_vertical_ajeno_al_preset(self, db, org):
        """Review Focus #3: no es base, no es del preset, no lo gobierna ningun plan."""
        org.industry_type = IndustryType.ATLAS_POS; org.plan = "FREE"; db.flush()
        with pytest.raises(plans.ModuloFueraDePlan) as e:
            plans.verificar_activar_modulo(db, org, "tables", "Mesas")
        assert str(e.value) == "El módulo Mesas no forma parte del preset ATLAS_POS de la organización; se habilita con ULTRA+ o cambiando de preset."

    def test_activar_modulo_sin_nombre_usa_la_clave(self, db, org):
        org.industry_type = IndustryType.ATLAS_POS; org.plan = "FREE"; db.flush()
        with pytest.raises(plans.ModuloFueraDePlan, match="El módulo quotes requiere"):
            plans.verificar_activar_modulo(db, org, "quotes")

    def test_modulos_fuera_de_plan_lista_los_heredados(self, db, org):
        """Review Focus #4."""
        org.industry_type = IndustryType.ATLAS_POS; org.plan = "FREE"; db.flush()
        for k in ("pos", "quotes", "hr"):
            db.add(OrganizationModule(organization_id=org.id, module_key=k, is_enabled=True))
        db.add(OrganizationModule(organization_id=org.id, module_key="ai", is_enabled=False)); db.flush()
        assert plans.modulos_fuera_de_plan(db, org) == ["hr", "quotes"]
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `python3 -m pytest -q -p no:warnings tests/test_planes.py`
Expected: error de colección `ModuleNotFoundError: No module named 'app.services.plans'`.

- [ ] **Step 3: Implementar el servicio**

Crear `app/services/plans.py`:

```python
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
from app.modules.users.models import PlatformRole, User, UserOrganization
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
    activas que venden."""
    usuarios = (
        db.query(UserOrganization)
        .join(User, User.id == UserOrganization.user_id)
        .filter(
            UserOrganization.organization_id == org_id,
            UserOrganization.is_active.is_(True),
            User.is_active.is_(True),
            User.platform_role == PlatformRole.NONE,
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
```

- [ ] **Step 4: Correr y ver que pasan**

Run: `python3 -m pytest -q -p no:warnings tests/test_planes.py`
Expected: 27 passed. Si `test_todo_modulo_gobernado_existe_en_el_catalogo` falla porque alguna clave de `MODULOS_CRECIMIENTO` o `MODULOS_BASE` no existe en `seed_global_modules`, la lista del catálogo manda: corrige la constante y anótalo en el reporte (el spec se actualiza en la Tarea 5).

- [ ] **Step 5: Commit**

```bash
git add app/services/plans.py tests/test_planes.py
git commit -m "feat(planes): catalogo de planes, topes y modulos permitidos

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_014rnFXXn9to8upxnFg1bpw8"
```

---

### Task 2: enforcement en usuarios, sucursales, toggle de módulo, PUT de organización y onboard

**Files:**
- Modify: `app/modules/users/router.py` (`create_user` ~l.177; `update_user` ~l.230-290)
- Modify: `app/routers/branches.py` (`create_branch` ~l.30; `update_branch` ~l.123-165)
- Modify: `app/routers/platform/organizations.py` (`update_organization` l.86-108; `toggle_org_module` l.711-750)
- Modify: `scripts/onboard_org.py` (`--plan`)
- Test: `tests/test_planes_enforcement.py`

**Interfaces:**
- Consumes: `app.services.plans` (`verificar_alta_usuario`, `verificar_alta_sucursal`, `verificar_activar_modulo`, `es_plan_valido`, `claves_validas`, `LimitePlanAlcanzado`, `ModuloFueraDePlan`).
- Rutas: `POST /api/users/`, `PUT /api/users/{id}`, `POST /api/branches/`, `PUT /api/branches/{id}`, `PATCH /api/platform/organizations/{id}/modules/{key}?enable=`, `PUT /api/platform/organizations/{id}`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_planes_enforcement.py`:

```python
"""Tests: los topes y el gating de plan en las rutas (usuarios, sucursales, toggle, PUT)."""
import pytest

from app.models.modules import Module, OrganizationModule
from app.models.organization import Branch
from app.modules.tenants.models import BranchType, IndustryType


def _nuevo_usuario(username="nuevo"):
    return {"username": username, "password": "clave-segura-1", "role": "CAJERO", "full_name": "Nuevo", "is_active": True}


class TestUsuarios:
    def test_free_con_dos_activos_rechaza_el_tercero(self, client, auth_admin, db, org, admin_user, cajero_a):
        org.plan = "FREE"; db.commit()
        r = client.post("/api/users/", json=_nuevo_usuario(), headers=auth_admin)
        assert r.status_code == 403
        assert r.json()["detail"] == "Tu plan ONE FREE permite 2 usuarios activos. Para agregar más, sube a ONE START."

    def test_free_con_uno_activo_acepta(self, client, auth_admin, db, org, admin_user):
        org.plan = "FREE"; db.commit()
        r = client.post("/api/users/", json=_nuevo_usuario(), headers=auth_admin)
        assert r.status_code in (200, 201), r.text

    def test_inactivo_no_cuenta(self, client, auth_admin, db, org, admin_user, cajero_a):
        org.plan = "FREE"; cajero_a.is_active = False; db.commit()
        r = client.post("/api/users/", json=_nuevo_usuario(), headers=auth_admin)
        assert r.status_code in (200, 201), r.text

    def test_reactivar_al_tope_rechaza(self, client, auth_admin, db, org, admin_user, cajero_a):
        """Review Focus #1."""
        org.plan = "FREE"
        # tercer usuario, inactivo: admin + cajero_a ya llenan el tope
        r = client.post("/api/users/", json=dict(_nuevo_usuario("dormido"), is_active=False), headers=auth_admin)
        assert r.status_code in (200, 201), r.text
        uid = r.json()["id"]
        r = client.put(f"/api/users/{uid}", json={"is_active": True}, headers=auth_admin)
        assert r.status_code == 403
        assert "ONE START" in r.json()["detail"]

    def test_editar_sin_reactivar_no_pasa_por_el_tope(self, client, auth_admin, db, org, admin_user, cajero_a):
        org.plan = "FREE"; db.commit()
        r = client.put(f"/api/users/{cajero_a.id}", json={"full_name": "Cajero Uno"}, headers=auth_admin)
        assert r.status_code == 200, r.text

    def test_ultra_plus_nunca_bloquea(self, client, auth_admin, db, org, admin_user, cajero_a, gerente_a):
        org.plan = "ULTRA_PLUS"; db.commit()
        r = client.post("/api/users/", json=_nuevo_usuario(), headers=auth_admin)
        assert r.status_code in (200, 201), r.text


class TestSucursales:
    def test_free_con_una_que_vende_rechaza_otra_tienda(self, client, auth_admin, db, org, admin_user, branch_a):
        org.plan = "FREE"; db.commit()
        r = client.post("/api/branches/", json={"name": "Tienda 2", "branch_type": "STORE", "can_sell": True}, headers=auth_admin)
        assert r.status_code == 403
        assert r.json()["detail"] == "Tu plan ONE FREE permite 1 sucursal que vende. Para abrir otra, sube a ONE PRO."

    def test_almacen_no_cuenta(self, client, auth_admin, db, org, admin_user, branch_a):
        org.plan = "FREE"; db.commit()
        r = client.post("/api/branches/", json={"name": "Bodega", "branch_type": "WAREHOUSE"}, headers=auth_admin)
        assert r.status_code in (200, 201), r.text

    def test_tienda_que_no_vende_no_cuenta(self, client, auth_admin, db, org, admin_user, branch_a):
        org.plan = "FREE"; db.commit()
        r = client.post("/api/branches/", json={"name": "Exhibicion", "branch_type": "STORE", "can_sell": False}, headers=auth_admin)
        assert r.status_code in (200, 201), r.text

    def test_pasar_a_vender_al_tope_rechaza(self, client, auth_admin, db, org, admin_user, branch_a):
        """Review Focus #2."""
        org.plan = "FREE"
        b = Branch(name="Exhibicion", branch_type=BranchType.STORE, can_sell=False, is_active=True, organization_id=org.id)
        db.add(b); db.commit()
        r = client.put(f"/api/branches/{b.id}", json={"can_sell": True}, headers=auth_admin)
        assert r.status_code == 403
        assert "ONE PRO" in r.json()["detail"]

    def test_editar_la_que_ya_vende_no_pasa_por_el_tope(self, client, auth_admin, db, org, admin_user, branch_a):
        org.plan = "FREE"; db.commit()
        r = client.put(f"/api/branches/{branch_a.id}", json={"can_sell": True, "name": "Sucursal A renombrada"}, headers=auth_admin)
        assert r.status_code == 200, r.text

    def test_matriz_con_venta_explicita_cuenta(self, client, auth_admin_a, db, org, admin_a, branch_a):
        """Review Focus #2: una HQ nueva con can_sell=True es una sucursal que vende.
        Usa admin_a (sucursal A, sin HQ previa) para que el guard de 'HQ unica' no se dispare antes."""
        org.plan = "FREE"; db.commit()
        r = client.post("/api/branches/", json={"name": "Matriz", "branch_type": "HQ", "can_sell": True}, headers=auth_admin_a)
        assert r.status_code == 403, r.text

    def test_pro_permite_la_segunda(self, client, auth_admin, db, org, admin_user, branch_a):
        org.plan = "PRO"; db.commit()
        r = client.post("/api/branches/", json={"name": "Tienda 2", "branch_type": "STORE", "can_sell": True}, headers=auth_admin)
        assert r.status_code in (200, 201), r.text


class TestToggleModulo:
    @pytest.fixture(autouse=True)
    def _catalogo(self, db):
        from app.services.capabilities_service import seed_global_modules
        seed_global_modules(db)

    def test_encender_quotes_en_free_rechaza_con_start(self, client, auth_superadmin, db, org):
        org.industry_type = IndustryType.ATLAS_POS; org.plan = "FREE"; db.commit()
        r = client.patch(f"/api/platform/organizations/{org.id}/modules/quotes?enable=true", headers=auth_superadmin)
        assert r.status_code == 403
        assert "ONE START" in r.json()["detail"]
        assert db.query(OrganizationModule).filter_by(organization_id=org.id, module_key="quotes").first() is None

    def test_encender_quotes_en_start_pasa(self, client, auth_superadmin, db, org):
        org.industry_type = IndustryType.ATLAS_POS; org.plan = "START"; db.commit()
        r = client.patch(f"/api/platform/organizations/{org.id}/modules/quotes?enable=true", headers=auth_superadmin)
        assert r.status_code == 200, r.text

    def test_apagar_siempre_pasa(self, client, auth_superadmin, db, org):
        org.industry_type = IndustryType.ATLAS_POS; org.plan = "FREE"
        db.add(OrganizationModule(organization_id=org.id, module_key="quotes", is_enabled=True)); db.commit()
        r = client.patch(f"/api/platform/organizations/{org.id}/modules/quotes?enable=false", headers=auth_superadmin)
        assert r.status_code == 200, r.text

    def test_encender_modulo_del_preset_en_free_pasa(self, client, auth_superadmin, db, org):
        org.industry_type = IndustryType.RESTAURANT_FULL; org.plan = "FREE"; db.commit()
        r = client.patch(f"/api/platform/organizations/{org.id}/modules/tables?enable=true", headers=auth_superadmin)
        assert r.status_code == 200, r.text


class TestCambioDePlan:
    def test_put_plan_valido_no_toca_modulos(self, client, auth_superadmin, db, org):
        """Review Focus #5."""
        org.industry_type = IndustryType.ATLAS_POS; org.plan = "PRO"
        db.add(OrganizationModule(organization_id=org.id, module_key="quotes", is_enabled=True))
        db.add(OrganizationModule(organization_id=org.id, module_key="pos", is_enabled=True)); db.commit()
        antes = sorted((m.module_key, m.is_enabled) for m in db.query(OrganizationModule).filter_by(organization_id=org.id))
        r = client.put(f"/api/platform/organizations/{org.id}", json={"plan": "FREE"}, headers=auth_superadmin)
        assert r.status_code == 200, r.text
        assert r.json()["plan"] == "FREE"
        db.expire_all()
        despues = sorted((m.module_key, m.is_enabled) for m in db.query(OrganizationModule).filter_by(organization_id=org.id))
        assert antes == despues

    def test_put_plan_desconocido_400_con_las_claves(self, client, auth_superadmin, db, org):
        r = client.put(f"/api/platform/organizations/{org.id}", json={"plan": "GOLD"}, headers=auth_superadmin)
        assert r.status_code == 400
        assert "FREE, START, PRO, BUSINESS, SCALE, ULTRA_PLUS" in r.json()["detail"]

    def test_put_sin_plan_sigue_igual(self, client, auth_superadmin, db, org):
        r = client.put(f"/api/platform/organizations/{org.id}", json={"name": "Renombrada"}, headers=auth_superadmin)
        assert r.status_code == 200, r.text


class TestHerencia:
    def test_modulo_fuera_de_plan_encendido_sigue_pasando_require_module(self, client, auth_admin, db, org, admin_user, hq_branch):
        """Review Focus #4: nada se apaga."""
        org.industry_type = IndustryType.ATLAS_POS; org.plan = "FREE"
        db.add(OrganizationModule(organization_id=org.id, module_key="quotes", is_enabled=True)); db.commit()
        r = client.get("/api/quotes/", headers=auth_admin)
        assert r.status_code != 403, r.text


class TestOnboard:
    def test_onboard_rechaza_plan_desconocido(self, db):
        import importlib
        on = importlib.import_module("scripts.onboard_org")
        with pytest.raises(ValueError, match="FREE, START, PRO, BUSINESS, SCALE, ULTRA_PLUS"):
            on.onboard(db, name="Org Plan Malo", industry="ATLAS_POS", admin_username="plan_malo", password="x" * 12, plan="GOLD")

    def test_onboard_acepta_ultra_plus(self, db):
        import importlib
        on = importlib.import_module("scripts.onboard_org")
        r = on.onboard(db, name="Org Ultra", industry="ATLAS_POS", admin_username="ultra_admin", password="x" * 12, plan="ULTRA_PLUS")
        assert r["plan"] == "ULTRA_PLUS"
```

Antes de correr, comprueba dos cosas del repo y adapta la prueba si hace falta (anótalo en el reporte): (a) el `response_model` de `POST /api/users/` y el código que devuelve (200 o 201); (b) `GET /api/quotes/` existe con ese path (si la lista vive en otra ruta bajo el router de `quotes`, usa esa; lo que se prueba es que `require_module("quotes")` no estorbe).

- [ ] **Step 2: Correr y ver que fallan**

Run: `python3 -m pytest -q -p no:warnings tests/test_planes_enforcement.py`
Expected: fallan las de 403/400 (hoy devuelven 200/201) y las de onboard (hoy acepta cualquier plan); pasan las que esperan 200.

- [ ] **Step 3: `create_user` y `update_user`**

En `app/modules/users/router.py`, importar arriba:

```python
from app.models.organization import Organization
from app.services import plans
```

En `create_user`, justo después de la validación de duplicado de username y antes de hashear:

```python
    # Tope del plan: cuenta usuarios activos de la organizacion (ver app/services/plans.py).
    # Un alta inactiva no consume tope; se cobra cuando se reactive (update_user).
    if user.is_active:
        org = db.query(Organization).filter(Organization.id == org_id).first()
        try:
            plans.verificar_alta_usuario(db, org)
        except plans.LimitePlanAlcanzado as e:
            raise HTTPException(status_code=403, detail=str(e))
```

En `update_user`, justo antes del bucle `for field, value in update_data.items():`:

```python
    # Reactivar a alguien es un alta para el tope del plan.
    if update_data.get("is_active") is True and not user_db.is_active:
        org = db.query(Organization).filter(Organization.id == org_id).first()
        try:
            plans.verificar_alta_usuario(db, org)
        except plans.LimitePlanAlcanzado as e:
            raise HTTPException(status_code=403, detail=str(e))
```

- [ ] **Step 4: `create_branch` y `update_branch`**

En `app/routers/branches.py`, importar `from app.services import plans` (y `Organization` si no está importado). En `create_branch`, después del bloque que decide `can_sell` por tipo (justo antes de `branch_data = branch.dict(exclude_unset=True)`):

```python
    # Tope del plan: solo las sucursales que venden cuentan.
    if branch.can_sell:
        org = db.query(Organization).filter(Organization.id == org_id).first()
        try:
            plans.verificar_alta_sucursal(db, org)
        except plans.LimitePlanAlcanzado as e:
            raise HTTPException(status_code=403, detail=str(e))
```

En `update_branch`, antes de `for key, value in branch.dict(exclude_unset=True).items():`:

```python
    # Pasar a vender una sucursal que no vendia es un alta para el tope del plan.
    datos = branch.dict(exclude_unset=True)
    if datos.get("can_sell") is True and not db_branch.can_sell:
        org = db.query(Organization).filter(Organization.id == org_id).first()
        try:
            plans.verificar_alta_sucursal(db, org)
        except plans.LimitePlanAlcanzado as e:
            raise HTTPException(status_code=403, detail=str(e))
```

- [ ] **Step 5: `toggle_org_module` y `update_organization`**

En `app/routers/platform/organizations.py`, importar `from app.services import plans`. En `toggle_org_module`, después del guard de `core` y antes de consultar `org_mod`:

```python
    if enable:
        from app.models.modules import Module
        mod = db.query(Module).filter(Module.key == module_key).first()
        try:
            plans.verificar_activar_modulo(db, org, module_key, mod.name if mod else None)
        except plans.ModuloFueraDePlan as e:
            raise HTTPException(status_code=403, detail=str(e))
```

En `update_organization`, después de calcular `applied` y antes del `setattr`:

```python
    if "plan" in applied and not plans.es_plan_valido(applied["plan"]):
        raise HTTPException(
            status_code=400,
            detail=f"Plan desconocido {applied['plan']!r}. Válidos: {', '.join(plans.claves_validas())}",
        )
```

(El cambio de plan no toca `organization_modules`: no se añade nada más. El `_audit` existente ya registra `plan` en el payload.)

- [ ] **Step 6: `onboard_org.py`**

En `onboard()` (antes de crear la organización) y en `main()` (`--plan` con `choices`):

```python
    from app.services.plans import claves_validas, es_plan_valido
    if not es_plan_valido(plan):
        raise ValueError(f"plan desconocido {plan!r}. Validos: {', '.join(claves_validas())}")
```

```python
    p.add_argument("--plan", default="FREE", help="FREE, START, PRO, BUSINESS, SCALE o ULTRA_PLUS")
```

- [ ] **Step 7: Correr y ver que pasan**

Run: `python3 -m pytest -q -p no:warnings tests/test_planes_enforcement.py tests/test_planes.py`
Expected: todo en verde (21 + 27).

- [ ] **Step 8: Regresión**

Run: `python3 -m pytest -q -p no:warnings tests/test_users*.py tests/test_branch*.py tests/test_platform_security.py tests/test_onboard_org.py tests/test_upsell_recommendations.py tests/test_seed_presets.py tests/test_crm_en_presets_pos.py tests/test_boutique_preset.py 2>&1 | tail -3`
Expected: mismo conteo de `failed` que en `main` (0 esperado; la suite estaba en 1250/0 el 2026-09-30). Si una prueba existente crea un tercer usuario o una segunda tienda en una org FREE y ahora recibe 403, **ese test asume un mundo sin topes**: ajústalo poniendo `org.plan = "ULTRA_PLUS"` en su fixture o setup y anótalo en el reporte.

- [ ] **Step 9: Commit**

```bash
git add app/modules/users/router.py app/routers/branches.py app/routers/platform/organizations.py scripts/onboard_org.py tests/test_planes_enforcement.py tests/
git commit -m "feat(planes): topes de usuarios y sucursales, gating de modulos y validacion del plan

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_014rnFXXn9to8upxnFg1bpw8"
```

---

### Task 3: API de plataforma — catálogo, uso y marcas por módulo

**Files:**
- Create: `app/routers/platform/plans.py`
- Create: `app/schemas/plans.py`
- Modify: `app/routers/platform/__init__.py` (incluir `plans.router`)
- Modify: `app/routers/platform/organizations.py` (`get_org_module_status` l.683-709; `get_upsell_recommendations` l.755-820)
- Modify: `app/schemas/modules.py` (`UpsellRecommendation.plan_minimo`)
- Test: `tests/test_planes_api.py`

**Interfaces:**
- Consumes: `app.services.plans`.
- Produces (contrato que consume la Tarea 4):
  - `GET /api/platform/plans` → `list[PlanRead]` con `clave, nombre, lema, precio_mxn, precio_desde, max_usuarios, max_sucursales_venta, modulos_crecimiento: list[str], permite_todo`.
  - `GET /api/platform/organizations/{org_id}/plan-uso` → `PlanUsoRead {plan: PlanRead, usuarios_activos, sucursales_venta, modulos_fuera_de_plan: list[str]}`.
  - `GET /api/platform/organizations/{org_id}/modules` → cada ítem gana `plan_minimo: str | null` y `permitido_por_plan: bool`.
  - `GET /api/platform/organizations/{org_id}/upsell-recommendations` → cada recomendación gana `plan_minimo: str | null`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_planes_api.py`:

```python
"""Tests: API de plataforma de planes (catalogo, uso, marcas por modulo)."""
import pytest

from app.models.modules import OrganizationModule
from app.modules.tenants.models import IndustryType


@pytest.fixture(autouse=True)
def _catalogo(db):
    from app.services.capabilities_service import seed_global_modules
    seed_global_modules(db)


class TestCatalogo:
    def test_lista_seis_planes_en_orden(self, client, auth_superadmin):
        r = client.get("/api/platform/plans", headers=auth_superadmin)
        assert r.status_code == 200
        claves = [p["clave"] for p in r.json()]
        assert claves == ["FREE", "START", "PRO", "BUSINESS", "SCALE", "ULTRA_PLUS"]
        ultra = r.json()[-1]
        assert ultra["nombre"] == "ULTRA+" and ultra["max_usuarios"] is None and ultra["permite_todo"] is True
        assert r.json()[1]["modulos_crecimiento"] == sorted(["quotes", "promotions"])

    def test_requiere_plataforma(self, client, auth_admin):
        r = client.get("/api/platform/plans", headers=auth_admin)
        assert r.status_code in (401, 403)


class TestPlanUso:
    def test_uso_y_fuera_de_plan(self, client, auth_superadmin, db, org, admin_user, hq_branch, branch_a):
        org.industry_type = IndustryType.ATLAS_POS; org.plan = "FREE"
        db.add(OrganizationModule(organization_id=org.id, module_key="quotes", is_enabled=True)); db.commit()
        r = client.get(f"/api/platform/organizations/{org.id}/plan-uso", headers=auth_superadmin)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["plan"]["clave"] == "FREE" and j["plan"]["max_usuarios"] == 2
        assert j["usuarios_activos"] == 1  # admin_user; el superadmin es de plataforma y no cuenta
        assert j["sucursales_venta"] == 1
        assert j["modulos_fuera_de_plan"] == ["quotes"]

    def test_org_inexistente_404(self, client, auth_superadmin):
        r = client.get("/api/platform/organizations/999999/plan-uso", headers=auth_superadmin)
        assert r.status_code == 404


class TestModulosConPlan:
    def test_cada_modulo_trae_plan_minimo_y_permitido(self, client, auth_superadmin, db, org):
        org.industry_type = IndustryType.ATLAS_POS; org.plan = "FREE"; db.commit()
        r = client.get(f"/api/platform/organizations/{org.id}/modules", headers=auth_superadmin)
        assert r.status_code == 200
        por_clave = {m["key"]: m for m in r.json()}
        assert por_clave["pos"]["plan_minimo"] is None and por_clave["pos"]["permitido_por_plan"] is True
        assert por_clave["quotes"]["plan_minimo"] == "START" and por_clave["quotes"]["permitido_por_plan"] is False
        assert por_clave["tables"]["plan_minimo"] is None and por_clave["tables"]["permitido_por_plan"] is False
        assert por_clave["ai"]["plan_minimo"] == "SCALE"

    def test_en_ultra_plus_todo_permitido(self, client, auth_superadmin, db, org):
        org.industry_type = IndustryType.ATLAS_POS; org.plan = "ULTRA_PLUS"; db.commit()
        r = client.get(f"/api/platform/organizations/{org.id}/modules", headers=auth_superadmin)
        assert all(m["permitido_por_plan"] for m in r.json())


class TestUpsellConPlan:
    def test_recomendacion_trae_plan_minimo(self, client, auth_superadmin, db, org):
        org.industry_type = IndustryType.ATLAS_POS; org.plan = "FREE"; db.commit()
        r = client.get(f"/api/platform/organizations/{org.id}/upsell-recommendations", headers=auth_superadmin)
        assert r.status_code == 200
        recs = {x["module_key"]: x for x in r.json()["recommendations"]}
        if "purchasing" in recs:
            assert recs["purchasing"]["plan_minimo"] == "PRO"
        for x in recs.values():
            assert "plan_minimo" in x
```

Ojo con `test_uso_y_fuera_de_plan`: la fixture `superadmin` (que respalda `auth_superadmin`) también está enlazada a `org`, con `platform_role=SUPERADMIN`, y **no debe contar**; `hq_branch` no vende y `branch_a` sí. De ahí 1 y 1.

- [ ] **Step 2: Correr y ver que fallan**

Run: `python3 -m pytest -q -p no:warnings tests/test_planes_api.py`
Expected: 404 en `/api/platform/plans` y `/plan-uso`; `KeyError: 'plan_minimo'` en módulos y upsell.

- [ ] **Step 3: Schemas**

Crear `app/schemas/plans.py`:

```python
"""Schemas de la API de planes de plataforma."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class PlanRead(BaseModel):
    clave: str
    nombre: str
    lema: str
    precio_mxn: int
    precio_desde: bool
    max_usuarios: Optional[int]
    max_sucursales_venta: Optional[int]
    modulos_crecimiento: List[str]
    permite_todo: bool


class PlanUsoRead(BaseModel):
    plan: PlanRead
    usuarios_activos: int
    sucursales_venta: int
    modulos_fuera_de_plan: List[str]
```

En `app/schemas/modules.py`, añadir a `UpsellRecommendation` tras `sort_hint`:

```python
    plan_minimo: Optional[str] = None  # clave del plan que lo incluye; None si no depende del plan
```

- [ ] **Step 4: Router de planes**

Crear `app/routers/platform/plans.py`:

```python
"""Planes de plataforma: catalogo y uso por organizacion.

Solo lectura. El cambio de plan va por el PUT de organizations (valida la
clave); encender modulos va por el PATCH de modules (valida el plan).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.organization import Organization
from app.modules.platform.dependencies import require_platform_admin
from app.schemas.plans import PlanRead, PlanUsoRead
from app.services import plans

router = APIRouter(dependencies=[Depends(require_platform_admin)])


def _a_read(p: plans.Plan) -> PlanRead:
    return PlanRead(
        clave=p.clave, nombre=p.nombre, lema=p.lema, precio_mxn=p.precio_mxn,
        precio_desde=p.precio_desde, max_usuarios=p.max_usuarios,
        max_sucursales_venta=p.max_sucursales_venta,
        modulos_crecimiento=sorted(p.modulos_crecimiento), permite_todo=p.permite_todo,
    )


@router.get("/plans", response_model=list[PlanRead])
def listar_planes():
    return [_a_read(p) for p in plans.PLANES]


@router.get("/organizations/{org_id}/plan-uso", response_model=PlanUsoRead)
def plan_uso(org_id: int, db: Session = Depends(get_db)):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    u = plans.uso(db, org.id)
    return PlanUsoRead(
        plan=_a_read(plans.obtener_plan(org.plan)),
        usuarios_activos=u.usuarios_activos,
        sucursales_venta=u.sucursales_venta,
        modulos_fuera_de_plan=plans.modulos_fuera_de_plan(db, org),
    )
```

En `app/routers/platform/__init__.py`: añadir `plans` al `from . import (...)` y `router.include_router(plans.router)` junto a los demás. Verifica cómo importa `require_platform_admin` ese paquete (línea 14) y usa el mismo origen.

- [ ] **Step 5: Marcas por módulo en el listado y en el upsell**

En `get_org_module_status` (`organizations.py`), cargar la org y los permitidos una vez y añadir dos campos por ítem:

```python
    org = db.query(Organization).filter(Organization.id == org_id).first()
    permitidos = plans.modulos_permitidos(db, org) if org is not None else set()
    …
        minimo = plans.plan_minimo_para(mod.key)
        result.append({
            "key": mod.key,
            "name": mod.name,
            "scope": mod.scope,
            "status": mod.status,
            "is_enabled": is_enabled,
            "plan_minimo": minimo.clave if minimo else None,
            "permitido_por_plan": mod.key in permitidos,
        })
```

En `get_upsell_recommendations`, al construir cada `UpsellRecommendation`:

```python
            plan_minimo=(plans.plan_minimo_para(mod.key).clave if plans.plan_minimo_para(mod.key) else None),
```

- [ ] **Step 6: Correr y ver que pasan**

Run: `python3 -m pytest -q -p no:warnings tests/test_planes_api.py tests/test_upsell_recommendations.py tests/test_platform_security.py`
Expected: todo en verde.

- [ ] **Step 7: Commit**

```bash
git add app/routers/platform/plans.py app/schemas/plans.py app/routers/platform/__init__.py app/routers/platform/organizations.py app/schemas/modules.py tests/test_planes_api.py
git commit -m "feat(planes): API de plataforma — catalogo, uso por organizacion y marcas por modulo

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_014rnFXXn9to8upxnFg1bpw8"
```

---

### Task 4: pantallas de plataforma — selector de plan, uso y marcas

**Files:**
- Modify: `frontend/src/api/platform.ts` (`PlatformOrg` l.17-35; `OrgModule` l.221-227; `UpsellRecommendation` l.241-253; funciones junto a `getOrgModules` l.399)
- Modify: `frontend/src/pages/platform/PlatformOrgDetail.tsx` (carga l.296-347; header l.598-630; sección Módulos l.632-716; upsell l.718-838)
- Modify: `frontend/src/pages/platform/PlatformOrganizations.tsx` (filtros l.237-324 y chips ~l.590; columnas l.471-530)

**Interfaces:**
- Consumes el contrato de la Tarea 3 (tipos abajo). El backend puede no estar fusionado aún en el worktree del implementador: la UI se escribe contra el contrato y se verifica con `npm run build` (tsc).

- [ ] **Step 1: Tipos y funciones en `api/platform.ts`**

```ts
export interface PlatformOrg {
  …(campos existentes)…
  plan: string | null
}

export interface OrgModule {
  key: string
  name: string
  scope: string
  status: string
  is_enabled: boolean
  plan_minimo: string | null
  permitido_por_plan: boolean
}

export interface Plan {
  clave: string
  nombre: string
  lema: string
  precio_mxn: number
  precio_desde: boolean
  max_usuarios: number | null
  max_sucursales_venta: number | null
  modulos_crecimiento: string[]
  permite_todo: boolean
}

export interface PlanUso {
  plan: Plan
  usuarios_activos: number
  sucursales_venta: number
  modulos_fuera_de_plan: string[]
}
```

`UpsellRecommendation` gana `plan_minimo: string | null`. Funciones (junto a `getOrgModules`):

```ts
  getPlans: () => client.get<Plan[]>('/platform/plans').then((r) => r.data),
  getPlanUso: (orgId: number) => client.get<PlanUso>(`/platform/organizations/${orgId}/plan-uso`).then((r) => r.data),
```

Helper exportado para pintar el nombre cuando solo se tiene la clave (lista de organizaciones):

```ts
export const NOMBRE_PLAN: Record<string, string> = {
  FREE: 'ONE FREE', START: 'ONE START', PRO: 'ONE PRO', BUSINESS: 'BUSINESS', SCALE: 'SCALE', ULTRA_PLUS: 'ULTRA+',
}
export const nombrePlan = (clave: string | null | undefined) => NOMBRE_PLAN[clave ?? 'FREE'] ?? (clave || 'ONE FREE')
```

- [ ] **Step 2: `PlatformOrgDetail.tsx`**

1. **Carga**: añadir `platformApi.getPlans()` y `platformApi.getPlanUso(id)` al `Promise.all` de `load()` (l.309-316) con estados `plans: Plan[]` y `planUso: PlanUso | null`. Si `getPlanUso` falla, `null` y la tarjeta muestra "Sin datos de plan" (no romper la página).
2. **Header**: junto al chip de `industry_type`, un chip con `nombrePlan(org.plan)` (mismo estilo de chip, color `var(--p-teal)` sobre `rgba(20,184,166,0.12)`).
3. **Sección nueva "Plan y uso"** inmediatamente antes de "Módulos activos":
   - `<select>` con las seis opciones `"{nombre} · ${precio_mxn.toLocaleString('es-MX')}/mes"` (`precio_desde` → "desde $…"), valor `org.plan ?? 'FREE'`.
   - Al cambiar: si el índice del plan nuevo es menor que el actual (bajar), abrir `ConfirmDialog` con título "Bajar de plan" y texto exacto: "No se apaga ningún módulo; solo cambian los topes para altas nuevas. Los módulos que el plan nuevo no cubre quedarán marcados como fuera de plan." Confirmar → `platformApi.updateOrg(id, { plan: nuevo })`, `toast.success('Plan actualizado')`, `load()`. Subir → directo sin confirmar. Error → `toast.error(err?.response?.data?.detail || 'No se pudo cambiar el plan')`.
   - Dos medidores de texto: "Usuarios activos **{usuarios_activos}** de {max_usuarios ?? 'sin tope'}" y "Sucursales que venden **{sucursales_venta}** de {max_sucursales_venta ?? 'sin tope'}"; en rojo (`var(--p-danger)`) cuando el uso supera el tope.
   - Si `modulos_fuera_de_plan.length > 0`: línea "Fuera de plan (heredados, siguen activos): quotes, hr".
4. **Sección Módulos activos**: en cada tarjeta, junto a los badges BETA/STABLE:
   - si `!m.permitido_por_plan && !m.is_enabled && m.plan_minimo` → `<StatusBadge status="beta" label={`Requiere ${nombrePlan(m.plan_minimo)}`} />`
   - si `!m.permitido_por_plan && !m.is_enabled && !m.plan_minimo` → `<StatusBadge status="beta" label="Fuera del preset" />`
   - si `!m.permitido_por_plan && m.is_enabled` → `<StatusBadge status="archived" label="Fuera de plan" />`
   El toggle sigue habilitado: el 403 del backend ya llega al `toast.error` existente en `toggleModule`.
5. **Upsell**: bajo el nombre del módulo, si `rec.plan_minimo`, texto pequeño "Incluido desde {nombrePlan(rec.plan_minimo)}".

Si `StatusBadge` no admite `label` libre con esos `status`, usa el `<span>` estilizado del propio archivo (como el chip de BETA en la sección upsell, l.764-775) y anótalo en el reporte.

- [ ] **Step 3: `PlatformOrganizations.tsx`**

1. Columna nueva después de "Industry":
```tsx
    {
      key: 'plan',
      label: 'Plan',
      sortable: true,
      sortValue: o => ['FREE','START','PRO','BUSINESS','SCALE','ULTRA_PLUS'].indexOf(o.plan ?? 'FREE'),
      accessor: o => (
        <span style={{ background: 'rgba(20,184,166,0.12)', color: 'var(--p-teal)', padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 600 }}>
          {nombrePlan(o.plan)}
        </span>
      ),
    },
```
2. Filtro por plan con la misma mecánica de chips que `industryFilter` (`planFilter: string[]`, opciones = planes presentes en `orgs`, condición en `filtered`, chip en la barra de filtros junto a los de industria, incluido en el `useMemo` deps).

- [ ] **Step 4: Verificar**

Run: `cd frontend && npm run build 2>&1 | tail -5`
Expected: `tsc` sin errores y `vite build` termina. Run también `npm test -- --run 2>&1 | tail -3` (vitest) y confirma que no suma fallos.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/platform.ts frontend/src/pages/platform/PlatformOrgDetail.tsx frontend/src/pages/platform/PlatformOrganizations.tsx
git commit -m "feat(plataforma): selector de plan, uso contra topes y marcas de plan por modulo

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_014rnFXXn9to8upxnFg1bpw8"
```

---

### Task 5: documentación

**Files:**
- Modify: `CLAUDE.md` (§1 un renglón sobre planes; §5 receta "Cambiar el plan de una organización")
- Modify: `docs/DATA_MODEL.md` (columna `organization.plan`: claves y semántica)
- Modify: `docs/API_REFERENCE.md` (los dos endpoints nuevos y los campos nuevos de modules/upsell)
- Modify: `docs/RBAC.md` (nota: los 403 de tope de plan no son RBAC)
- Add: `docs/superpowers/specs/2026-09-30-planes-y-topes-design.md`, `docs/superpowers/plans/2026-09-30-planes-y-topes.md` (ya existen sin versionar; se incluyen en el commit)

- [ ] **Step 1: CLAUDE.md**

En §1, tras la frase "un **preset de industria** decide qué **módulos** se activan por organización", añadir: ` Un **plan comercial** (`organization.plan`: FREE, START, PRO, BUSINESS, SCALE, ULTRA_PLUS; catálogo en `app/services/plans.py`) pone topes de usuarios activos y sucursales que venden y gobierna los módulos de crecimiento; nunca apaga lo ya encendido.`

En §5, añadir la receta:

```
### Cambiar el plan de una organización
- Desde `/platform/organizations/{id}` (selector "Plan y uso") o `PUT /api/platform/organizations/{id}` con `{"plan": "PRO"}`. Claves válidas en `app/services/plans.py::claves_validas()`.
- Cambiar de plan NO toca `organization_modules`: los módulos encendidos se heredan y la pantalla los marca "Fuera de plan". Los topes (usuarios activos, sucursales que venden) solo frenan altas nuevas con un 403 cuyo `detail` nombra el plan mínimo.
- Módulos permitidos = base ∪ preset del giro ∪ crecimiento del plan. Para añadir un módulo a un plan, edita `_START/_PRO/_BUSINESS/_SCALE` en `plans.py` y corre `tests/test_planes.py`.
```

- [ ] **Step 2: DATA_MODEL.md** — en la fila/sección de `organization.plan`: "String. Claves: FREE, START, PRO, BUSINESS, SCALE, ULTRA_PLUS (NULL o desconocido se tratan como FREE). Catálogo, topes y módulos por plan en `app/services/plans.py`. No tiene FK ni enum DB a propósito."

- [ ] **Step 3: API_REFERENCE.md** — bajo plataforma: `GET /api/platform/plans` (catálogo), `GET /api/platform/organizations/{id}/plan-uso` (plan, uso, módulos fuera de plan), y los campos `plan_minimo`/`permitido_por_plan` en `GET …/modules` y `plan_minimo` en upsell. Códigos: `PUT …/organizations/{id}` → 400 plan desconocido; `PATCH …/modules/{key}?enable=true` → 403 fuera de plan; `POST /api/users/`, `PUT /api/users/{id}`, `POST /api/branches/`, `PUT /api/branches/{id}` → 403 tope de plan.

- [ ] **Step 4: RBAC.md** — una nota al final de la sección de guards: "Los 403 por tope de plan (`app/services/plans.py`) no son RBAC: dependen de la organización, no del rol. Un ADMINISTRADOR en una org FREE al tope recibe 403 al crear el tercer usuario."

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md docs/DATA_MODEL.md docs/API_REFERENCE.md docs/RBAC.md docs/superpowers/specs/2026-09-30-planes-y-topes-design.md docs/superpowers/plans/2026-09-30-planes-y-topes.md
git commit -m "docs: planes comerciales, topes y API de plataforma

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_014rnFXXn9to8upxnFg1bpw8"
```

---

### Task 6: despliegue y asignación de planes (manual, con permiso en cada paso)

- [ ] **Step 1 — PERMISO: fusionar y desplegar**

```bash
cd /mnt/d/Devs/atlas-one
git checkout main && git merge --no-ff feat/planes -m "merge: planes comerciales con topes y gating de modulos"
git push origin main
gh run watch "$(gh run list --branch main --limit 1 --json databaseId -q '.[0].databaseId')" --exit-status
ssh ionos 'docker exec atlas-one-prod cat /app/.commit_desplegado; echo; curl -fsS https://app.atlasone.com.mx/health'
```

- [ ] **Step 2 — Verificación de solo lectura**

```bash
TOKEN=<token de superadmin de plataforma>
curl -fsS -H "Authorization: Bearer $TOKEN" https://app.atlasone.com.mx/api/platform/plans | python3 -c "import sys,json;print([p['clave'] for p in json.load(sys.stdin)])"
for o in 14 15 16 17 18; do curl -fsS -H "Authorization: Bearer $TOKEN" https://app.atlasone.com.mx/api/platform/organizations/$o/plan-uso; echo; done
```
Expected: seis claves; las cinco orgs en FREE con `usuarios_activos`/`sucursales_venta` = 2/1 (Kaory, Ginebra, Imaltzin, Coqueta) y 4/1 (Eleven); `modulos_fuera_de_plan` vacío en todas (crm, labels, scanner, variants son base).

- [ ] **Step 3 — PERMISO: Eleven a ULTRA+**

```bash
curl -fsS -X PUT -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"plan":"ULTRA_PLUS"}' https://app.atlasone.com.mx/api/platform/organizations/17 | python3 -c "import sys,json;print(json.load(sys.stdin)['plan'])"
```
Expected: `ULTRA_PLUS`. Kaory (14) y Coqueta (18) se quedan en `FREE`: confirmar con `plan-uso` que siguen así (el usuario pidió explícitamente verlas en FREE; ya lo están, no hay escritura).

- [ ] **Step 4 — Cierre**: memoria `planes-atlas-one.md` (controlador) con claves, topes, quién está en qué plan y la regla de herencia.
