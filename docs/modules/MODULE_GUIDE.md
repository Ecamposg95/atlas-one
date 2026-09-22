# Atlas BOS — Module Guide

> Cómo se ve, cómo se hace y cómo se mueve un módulo en Atlas BOS.
> Audiencia: dev humano o IA que va a crear un módulo nuevo, mover uno legacy, o necesita orientarse al llegar al proyecto.
> Fuente original: [`context/ATLAS_ONE_BOS_CONTEXT_PACK.md`](../../context/ATLAS_ONE_BOS_CONTEXT_PACK.md) §8, §10, §13 · [`context/PHASE_2_BACKEND_MODULARIZATION.md`](../../context/PHASE_2_BACKEND_MODULARIZATION.md).

---

## 1. TL;DR — Crear un módulo nuevo (checklist)

```
□ 1. Backend: crear app/modules/<key>/ con __init__.py, models.py, schemas.py, router.py
□ 2. Registrar en app/main.py (app.include_router) con prefix=/api/<key>
□ 3. Reverse-shim opcional: app/routers/<key>.py (legacy compat si hay imports antiguos)
□ 4. Catálogo: agregar tupla a MODULES_CATALOG en scripts/init_presets_v2.py
□ 5. Upsell: agregar entrada a MODULE_UPSELL en el mismo script
□ 6. Preset: añadir <key> al ATLAS_ONE_<vertical> que lo necesite
□ 7. Frontend: crear pages/<modulo>/, api/<modulo>.ts, ruta en App.tsx, item en Sidebar.tsx
□ 8. Tests: tests/test_<modulo>_*.py con fixtures de conftest.py
□ 9. Migración (si toca DB): ALTER TABLE en scripts/railway_init.py run_migrations()
□ 10. Push a main → CI/CD despliega al VPS IONOS automáticamente (ver docs/DEPLOY.md) → correr seed si se cambió MODULE_UPSELL
```

---

## 2. Filosofía

Un **módulo** en Atlas BOS es una unidad funcional con responsabilidad única, conectada al core común por interfaces explícitas. Los principios son los del Context Pack §7 y §10:

- **Una responsabilidad** — un módulo cubre un dominio (`inventory`, `pos`, `appointments`). No mezcla.
- **Bajo acoplamiento** — los módulos se comunican vía servicios públicos o eventos, no imports cruzados de modelos.
- **Multi-tenant by design** — toda fila que pertenezca a una org lleva `organization_id` o `tenant_id`. Toda query lo filtra.
- **API-first** — la verdad es el endpoint. UI consume lo mismo que un cliente externo consumiría.
- **Activable/desactivable** — el módulo puede no existir para una org sin romper el sistema. Lo controla `OrganizationModule.is_enabled`.
- **Atlas POS-friendly** — el preset de entrada solo activa los módulos imprescindibles. Lo demás se vende como upsell.

---

## 3. Anatomía backend

### 3.1 Árbol mínimo

```
app/modules/<key>/
├── __init__.py        # docstring + opcional re-exports
├── models.py          # SQLAlchemy ORM
├── schemas.py         # Pydantic in/out
├── router.py          # FastAPI APIRouter
├── services.py        # (opcional) lógica de negocio reutilizable
├── dependencies.py    # (opcional) FastAPI Depends locales
└── templates/         # (raro) Jinja, ej. impresión
```

### 3.2 Ejemplo vivo: `app/modules/users/`

| Archivo | Líneas | Qué hace |
|---|---|---|
| `__init__.py` | ~10 | Docstring describiendo el dominio. Puede re-exportar el `router` para conveniencia. |
| `models.py` | ~110 | Clases SQLAlchemy `User`, `UserOrganization`, enums `Role`, `PlatformRole`. |
| `schemas.py` | ~38 | `UserBase`, `UserCreate`, `UserUpdate`, `UserRead` (Pydantic v2 con `from_attributes=True`). |
| `router.py` | ~250 | `APIRouter()` + handlers. Importa de `app.core.database`, `app.core.security`, `app.models`. |

### 3.3 Convenciones de cada archivo

**`__init__.py`** — siempre con docstring con metadata:

```python
"""Atlas BOS module - <key>.

DOMAIN: <Plain English Domain Name>
STATUS: Stable | Beta | Stub
"""
```

**`models.py`** — SQLAlchemy:
- Importa `Base` de `app.core.database`.
- Si el modelo ya existía como legacy, usa `__table_args__ = {"extend_existing": True}` durante la migración (Phase 2 pattern).
- Enums con `create_type=False` cuando ya existen en la BD (evita doble creación en init).
- Columnas estándar: `id`, `organization_id` (FK), `created_at`, `updated_at`, `is_active`.

**`schemas.py`** — Pydantic v2:
- `<Entity>Base` con campos compartidos.
- `<Entity>Create` con campos requeridos para crear.
- `<Entity>Update` con todos opcionales.
- `<Entity>Read` con `id` + serializables, `class Config: from_attributes = True`.

**`router.py`** — FastAPI:
- `router = APIRouter()` al tope, sin prefix (el prefix se aplica en `main.py`).
- Cada handler recibe `db: Session = Depends(get_db)` y `current_user: User = Depends(get_current_user)` (o `require_platform_admin` para platform).
- Función-local imports cuando hay riesgo de import circular (patrón usado en `app/routers/platform/organizations.py`).
- Respuesta tipada con `response_model=<EntityRead>` o `List[<EntityRead>]`.

---

## 4. Registrar el módulo

### 4.1 En `app/main.py`

```python
from app.modules.<key>.router import router as <key>_router
# o vía reverse-shim:
from app.routers import <key>

app.include_router(
    <key>_router,
    prefix="/api/<key>",
    tags=["<TagHumanReadable>"],
)
```

Convenciones:
- **Prefix**: siempre `/api/<key>` con el mismo key del módulo (matchea `OrganizationModule.module_key`).
- **Tags**: en español, capitalizado, una palabra plural si aplica ("Citas", "Comisiones").
- **Orden**: agrupar imports por bloque (auth, identity, catálogo, ventas, finanzas, plataforma, presets).

### 4.2 Reverse-shim (Phase 2 pattern)

Cuando mueves un dominio existente sin romper imports legacy, dejas un shim en la ruta antigua:

```python
# app/routers/<key>.py  ← reverse-shim, body movido
"""Phase 2 reverse-shim — body moved to app.modules.<key>.router."""
from app.modules.<key>.router import *  # noqa: F401, F403
from app.modules.<key>.router import router  # noqa: F401
```

Idem para `app/models/<key>.py` y `app/schemas/<key>.py`. El shim se mantiene mientras quede algún `from app.routers.<key> import ...` en el código; se borra cuando el grep está limpio.

### 4.3 Migraciones de schema

Mientras no exista Alembic baseline (ver Phase 2 D1), las migraciones se añaden a `scripts/railway_init.py` → `run_migrations()`. El patrón es **idempotente**:

```python
# Tupla (tabla, columna, DDL)
("<table>", "<new_col>", "ALTER TABLE <table> ADD COLUMN <new_col> <TYPE>;"),
```

El script ya filtra por `information_schema.columns` antes de aplicar. Para enums Postgres se usa `ALTER TYPE ... ADD VALUE IF NOT EXISTS '<X>'` dentro de un bloque AUTOCOMMIT.

---

## 5. Catálogo, preset, toggle, upsell

Cuatro tablas se tocan al crear un módulo. Tres viven en BD; una es el seed que las llena.

### 5.1 Tabla `modules` (catálogo global)

Define qué módulos existen. Se llena por el seed `scripts/init_presets_v2.py` en la lista `MODULES_CATALOG`:

```python
MODULES_CATALOG = [
    # (key, name, description, scope, status)
    ("<key>", "<Display Name>", "<Descripción corta>", ModuleScope.GLOBAL, ModuleStatus.BETA),
    ...
]
```

- **`scope`**: `GLOBAL` (transversal), `BRANCH` (por sucursal), `WAREHOUSE`, `HQ`.
- **`status`**: `STABLE` (lista para producción) o `BETA` (visible con badge, puede no funcionar 100%).

### 5.2 Tabla `industry_presets`

Mapea `industry_type` (`ATLAS_POS`, `ATLAS_ONE_BEAUTY`, etc.) → lista de `module_key`. Se llena por el dict `PRESETS` del mismo seed. Para que tu módulo entre a un preset:

```python
{
    "id": "ATLAS_ONE_BEAUTY",
    "name": "Atlas One Beauty",
    "desc": "...",
    "mods": [
        "core", "users", "catalog", ..., "<tu_key>",
    ],
},
```

Decisión clave: ¿en qué presets entra tu módulo por defecto? Pregunta guía: "¿el dueño del negocio lo necesita el día 1 o lo activa después?". Si es día 1, va en el preset; si es upsell, no.

### 5.3 Tabla `organization_modules` (toggle por org)

Se llena automáticamente cuando una org aplica un preset (`POST /platform/organizations/{id}/apply-preset`) o cuando el platform admin lo activa manual (`PATCH /platform/organizations/{id}/modules/{key}?enable=true`). No requiere intervención del módulo nuevo — solo asegúrate que el `key` exista en `modules`.

### 5.4 Upsell metadata

Para que un módulo aparezca en la sección "Módulos disponibles" del platform UI, añade su entrada al dict `MODULE_UPSELL`:

```python
MODULE_UPSELL = {
    "<key>": {
        "category": "advanced",  # base | advanced | vertical
        "recommended_presets": ["ATLAS_ONE_BEAUTY", "ATLAS_ONE_SERVICES"],
        "value_props": ["Bullet 1", "Bullet 2", "Bullet 3"],
        "upgrade_prompt": "Una frase que cierre la venta del módulo.",
        "icon": "fa-calendar",  # FontAwesome class
        "sort_hint": 60,
    },
}
```

Si no añades entrada, el módulo es **invisible** al upsell (ok para `core`, `users`, etc. que siempre vienen activos).

---

## 6. Multi-tenancy obligatorio

**Regla bloqueante:** toda consulta a recursos de negocio incluye `organization_id`. Nunca consultas por `id` solo.

**Mal:**
```python
db.query(Appointment).filter(Appointment.id == appt_id).first()
```

**Bien:**
```python
db.query(Appointment).filter(
    Appointment.id == appt_id,
    Appointment.organization_id == current_user.organization_id,
).first()
```

Mejor todavía con un helper `with_tenant()` cuando esté disponible. La auditoría reciente del Phase 2 doc deja claro que esta regla es la #1 causa de bugs cross-tenant.

**Columnas estándar** en modelos de negocio:

```python
organization_id = Column(Integer, ForeignKey("organization.id"), nullable=False, index=True)
branch_id       = Column(Integer, ForeignKey("branches.id"),     nullable=True)  # si aplica
created_at      = Column(DateTime(timezone=True), server_default=func.now())
updated_at      = Column(DateTime(timezone=True), onupdate=func.now())
created_by      = Column(Integer, ForeignKey("users.id"), nullable=True)
is_active       = Column(Boolean, default=True, nullable=False)
```

---

## 7. Tests

Convención: `tests/test_<modulo>_<feature>.py`. Pytest + SQLite in-memory (ver `tests/conftest.py`).

Fixtures disponibles:
- `db` — sesión SQLAlchemy aislada por test (rollback al final).
- `client` — TestClient de FastAPI con `get_db` override.
- `org` — `Organization` de prueba.
- `branch_a` — `Branch` ligado a `org`.
- `auth_superadmin` — `Authorization: Bearer <token>` headers de un superadmin.
- `cajero_a`, `admin_a` — usuarios con roles típicos.

Patrón TDD esperado (red → green → commit):

```python
# tests/test_appointments_create.py
def test_create_appointment_persists(client, auth_superadmin, db, org, branch_a):
    resp = client.post(
        "/api/appointments",
        json={"customer_id": 1, "service_id": 2, "starts_at": "2026-06-01T10:00:00"},
        headers=auth_superadmin,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["organization_id"] == org.id
```

Suite completa: `pytest tests/` debe quedar verde. Tests propios del módulo + sin regresión en los del resto.

---

## 8. Frontend del módulo

El frontend **NO se obliga a paralelismo 1:1** con backend. Convención laxa:

```
frontend/src/
├── api/<modulo>.ts                  # axios client tipado del módulo
├── pages/<modulo>/                  # rutas / pantallas
│   ├── <ModuloList>.tsx
│   └── <ModuloDetail>.tsx
├── components/<modulo>/             # (opcional) componentes específicos
└── store/<modulo>Store.ts           # (opcional) Zustand
```

Mínimo para que el módulo sea visible:
1. **API client** — `frontend/src/api/<modulo>.ts` con tipos + funciones (`get`, `list`, `create`, `update`, `delete`).
2. **Página** — `frontend/src/pages/<modulo>/<Modulo>.tsx` o ruta `/platform/...`.
3. **Ruta** — entrada en `frontend/src/App.tsx`.
4. **Sidebar** — entrada en `frontend/src/components/layout/Sidebar.tsx` con el `url` matcheando la ruta. Si depende de un módulo gateado, ver §11 (sub-proyecto E).

---

## 9. Migración de un módulo legacy

Pasos para mover `app/routers/<key>.py` → `app/modules/<key>/`. Receta validada por S1 de Phase 2:

1. **Crear carpeta** `app/modules/<key>/` con `__init__.py` (docstring).
2. **Copiar el modelo** de `app/models/<key>.py` → `app/modules/<key>/models.py`. Si el `__tablename__` ya existe, agregar `__table_args__ = {"extend_existing": True}`.
3. **Copiar schemas** de `app/schemas/<key>.py` → `app/modules/<key>/schemas.py`.
4. **Copiar router** de `app/routers/<key>.py` → `app/modules/<key>/router.py`. Ajusta imports relativos (de `app.crud.<key>` → in-line o `app.modules.<key>.services`).
5. **Reverse-shim** en las tres rutas viejas:
   ```python
   from app.modules.<key>.models  import *  # noqa
   from app.modules.<key>.schemas import *  # noqa
   from app.modules.<key>.router  import *  # noqa
   ```
6. **Verificar `app/main.py`** — el include_router sigue funcionando vía el shim.
7. **Test smoke** — `pytest tests/ -k <key>` debe pasar sin tocar tests.
8. **Commit `refactor(modules): move <key> to app/modules/<key>/`**.

Importante: durante una migración del Phase 2, **no cambies la lógica**. Mover ≠ refactor. Si encuentras un bug, abre task separada — no mezcles.

---

## 10. Anti-patrones

Lista negra (revisar antes de PR):

| Anti-patrón | Por qué duele |
|---|---|
| `from app.modules.foo.models import X` desde `app.modules.bar` | Acopla módulos; rompe activación independiente. Usa servicios públicos o evento. |
| Query sin `organization_id` filter | Riesgo cross-tenant. Bloqueante en code review. |
| `Module.upsell_metadata` mutado en runtime | El seed es la fuente de verdad. Cualquier cambio se hace al seed y se re-corre. |
| Endpoints sin `response_model` | Pierdes serialización tipada + OpenAPI degradado. |
| Modelos con FK a otro módulo sin `relationship()` declarado bilateralmente | SQLAlchemy queja en runtime; queries se vuelven lentas. |
| Tocar `industry_type` viejo (ej. RESTAURANT_QSR) | Mantén compat; no borres valores del enum. Aditivo siempre. |
| Crear tabla nueva sin `organization_id` | Si es de negocio, va tenant-scoped. Si es global (catálogo), documentar explícitamente. |
| Sidebar entry sin gate por módulo | Cuando llegue el gating (sub-proyecto E), todos los items que no chequeen `OrganizationModule.is_enabled` se romperán. |
| `print()` en lugar de logger | Usa el logger de `app.core.logging` para que aparezca en los logs estructurados del contenedor (`docker logs atlas-one-prod`). |

---

## 11. Apéndice — plantilla esqueleto

Copy-paste para `app/modules/<key>/`. Reemplaza `<Key>`/`<key>`/`<Entity>` con tu dominio.

**`__init__.py`**

```python
"""Atlas BOS module - <key>.

DOMAIN: <Plain English Domain>
STATUS: Beta
"""
```

**`models.py`**

```python
"""Atlas BOS modules/<key>/models — <Plain English>."""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class <Entity>(Base):
    __tablename__ = "<entity_plural>"

    id              = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organization.id"), nullable=False, index=True)
    branch_id       = Column(Integer, ForeignKey("branches.id"),     nullable=True)
    name            = Column(String, nullable=False)
    is_active       = Column(Boolean, default=True, nullable=False)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), onupdate=func.now())

    organization = relationship("Organization")
    branch       = relationship("Branch")
```

**`schemas.py`**

```python
"""Atlas BOS modules/<key>/schemas — Pydantic v2."""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel


class <Entity>Base(BaseModel):
    name: str
    branch_id: Optional[int] = None
    is_active: bool = True


class <Entity>Create(<Entity>Base):
    pass


class <Entity>Update(BaseModel):
    name: Optional[str] = None
    branch_id: Optional[int] = None
    is_active: Optional[bool] = None


class <Entity>Read(<Entity>Base):
    id: int
    organization_id: int
    created_at: datetime

    class Config:
        from_attributes = True
```

**`router.py`**

```python
"""Atlas BOS modules/<key>/router — REST API."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.tenant_context import get_current_active_organization
from app.models import User
from app.modules.<key>.models  import <Entity>
from app.modules.<key>.schemas import <Entity>Create, <Entity>Read, <Entity>Update

router = APIRouter()


@router.get("", response_model=List[<Entity>Read])
def list_<entity_plural>(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = current_user.organization_id  # ajustar según contexto
    return (
        db.query(<Entity>)
        .filter(<Entity>.organization_id == org_id, <Entity>.is_active == True)  # noqa: E712
        .all()
    )


@router.post("", response_model=<Entity>Read, status_code=status.HTTP_201_CREATED)
def create_<entity>(
    payload: <Entity>Create,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    obj = <Entity>(
        organization_id=current_user.organization_id,
        **payload.dict(),
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj
```

**Registro en `app/main.py`**

```python
from app.modules.<key>.router import router as <key>_router

app.include_router(<key>_router, prefix="/api/<key>", tags=["<TagHumanReadable>"])
```

**Seed (`scripts/init_presets_v2.py`)**

```python
MODULES_CATALOG = [
    ...,
    ("<key>", "<Display Name>", "<descripción>", ModuleScope.GLOBAL, ModuleStatus.BETA),
]

MODULE_UPSELL = {
    ...,
    "<key>": {
        "category": "advanced",
        "recommended_presets": ["ATLAS_ONE_<vertical>"],
        "value_props": ["...", "...", "..."],
        "upgrade_prompt": "...",
        "icon": "fa-<icono>",
        "sort_hint": <int>,
    },
}
```

---

## 12. Cuando algo no encaja

Si tu módulo no cabe en este molde (ej. necesita su propio job runner, o vive fuera de la BD principal):

1. Documenta la excepción en un comentario al inicio del `__init__.py`.
2. Abre un ADR breve en `docs/decisions/` (si la carpeta existe; si no, propón crearla).
3. Discute antes de divergir — la divergencia silenciosa es el origen de la deuda técnica multi-vertical.

**Última actualización:** 2026-05-14 — alineado con Atlas One presets v3 + Module Upsell System.
