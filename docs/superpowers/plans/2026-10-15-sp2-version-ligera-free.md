# SP2 · Versión ligera para cuentas FREE — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que una organización FREE con preset `ATLAS_POS` (Kaory, Novedades, Coqueta) abra la app y vea solo su operación (cobrar, corte, ventas, devoluciones, productos, inventario, reportes, impresora, usuarios, sucursal), y que la ruta login → POS baje menos bytes y tenga un presupuesto vigilado en CI — con la misma base de código y sin apagar ningún módulo.

**Architecture:** Dos capas. (a) El backend expone `plan: {clave, nombre}` en el contexto del usuario (`/api/users/me/context`, que es lo que el frontend lee) y en `/api/org/capabilities`; el frontend lo guarda en `enabledModulesStore` y `visibleNavItems` aplica un **perfil por plan** (`navPerfilPlan.ts`: lista de URLs que FREE no ve) después del gating por módulo, con fail-open si el plan no cargó; `PresetHome` esconde los widgets de módulos no activos en FREE y los resume en una sola tarjeta. (b) Carga: `react/jsx-runtime` sale del chunk `charts` (hoy cada componente importa `jsx` desde ahí, así que chart.js viaja con el login), se audita el chunk de entrada con `rollup-plugin-visualizer`, se mueven a `lazy()` los módulos no críticos, la plataforma migra de recharts a chart.js (una sola librería) y `scripts/presupuesto_bundle.py` falla en CI si la ruta crítica (entrada + `modulepreload` + `POS-*.js`) supera `frontend/presupuesto_bundle.json`.

**Tech Stack:** FastAPI + SQLAlchemy + Pydantic v2; pytest sobre SQLite (`.venv/bin/python -m pytest -q -p no:warnings …`; si no hay `.venv/`, `python3 -m pytest`). React 18 + TypeScript 5 + Vite 5 + vitest 2 (`cd frontend && npx vitest run …`, `npx tsc --noEmit`, `npm run build`). chart.js 4 + react-chartjs-2 5. GitHub Actions (`.github/workflows/ci.yml`).

**Spec:** `docs/superpowers/specs/2026-10-14-mega-plan-altas-docs-responsivo-agente-design.md` (sección "SP2 · Versión ligera para cuentas FREE"; en la copia anterior del diseño aparece como "SP5", §2.6, decisión 7 de §3 y decisiones abiertas 6 y 7, ya tomadas: esconder `/mobile/*` y `/hr/me` en FREE; librería única = chart.js migrando los 3 archivos de plataforma).

## Global Constraints

- **`main` = producción con clientes vivos.** Rama `feat/version-ligera-free`; commits locales sí; **push y merge a `main` solo con permiso explícito del usuario**.
- **Nada se apaga:** no se toca `organization_modules`, `require_module` ni `app/services/plans.py`. Lo escondido sigue accesible por URL si el módulo está activo (`RutaPorRol`/`rolesConAcceso` no cambian).
- **Backend: solo `plan: {clave, nombre}`** en la respuesta de capabilities/contexto. `obtener_plan(None | "" | desconocido)` → FREE (`clave "FREE"`, `nombre "ONE FREE"`); nombres visibles exactos del catálogo: `ONE FREE`, `ONE START`, `ONE PRO`, `BUSINESS`, `SCALE`, `ULTRA+`.
- **Fail-open:** si `plan` no llegó (servidor viejo, petición fallida) el menú no se recorta; plan con clave desconocida tampoco recorta.
- **Perfil FREE (URLs que no ve):** `/hq/control`, `/hr/me`, `/mobile/*`, `/ai`, `/quotes`, `/quotes/new`, `/seguimiento`, `/customers`. Etiquetas se gobierna por `module: 'labels'` (ATLAS_POS lo trae; no entra al perfil). No existe ítem de promociones en `navConfig.ts`; nada que esconder.
- **La operación diaria no recibe `module:` nuevo:** Mi día, Cobrar, Mis ventas, Corte de caja, Devoluciones, Productos, Reportes (POS), Impresora, Inicio, Empresa, Sucursales y Usuarios siguen sin `module:` — un `module:` ahí sería una vía nueva para esconderle la caja a una tienda viva.
- **Antes de esconder un ítem sin `module:`** (Control, Mi expediente, móviles, Clientes) se verifica en producción que ninguna org FREE lo usa (Tarea 3, consulta de solo lectura que corre el usuario con `!`).
- **Una sola librería de gráficas:** chart.js + react-chartjs-2; `recharts` sale de `package.json`. chart.js pinta en canvas: ningún color `var(--p-*)` llega a un dataset sin resolverse con `token()`.
- **Presupuesto:** `tope_bytes` inicial = medición actual × 0.95 (bytes sin comprimir de entrada + `modulepreload` + `POS-*.js`); se baja al cerrar cada tarea de carga; el paso de CI va DESPUÉS de `npm run build` en el job `frontend-build`. El script es solo biblioteca estándar (ese job no instala `requirements.txt`).
- Estilo: comentarios en español, `from __future__ import annotations` y type hints en Python; Pydantic v2; sin `print()` de depuración (el script de presupuesto imprime a propósito: es CLI). Frontend: tokens `--p-*`, kit `ui/`.
- Nunca dos `pytest` a la vez en el mismo worktree; suite completa siempre con `--ignore=tests/test_cash_complete.py`.
- Commits terminan con:
  ```
  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf
  ```

## Review Focus

1. **Respuesta sin `plan`** (contenedor viejo a medio desplegar, caché del navegador con el JS nuevo contra la API vieja): la cajera debe ver su menú completo, no uno vacío ni uno recortado por un plan inventado. → Tarea 2 (`plan` ausente → `null`) y Tarea 4 (`plan: null` → sin recorte).
2. **Plan con clave que el frontend no conoce** (`"XYZ"`, o un plan futuro): sin recorte y sin excepción. → Tarea 4.
3. **Esconder no es quitar acceso:** con plan FREE, `/hq/control` sigue abriendo desde el enlace "Alertas críticas" de `HQOperations` y por URL. → Tarea 4 (`rolesConAcceso` no depende del plan).
4. **Inicio FREE con todos los widgets fuera de plan** (preset `ATLAS_ONE_*` y módulos mínimos): una sola tarjeta, nunca una rejilla vacía; y con todos los módulos activos no aparece tarjeta alguna. → Tarea 5.
5. **`index.html` cambia de forma** (sin `modulepreload`, `POS-*.js` renombrado, o un archivo referenciado que no existe): el script mide lo que hay y, si falta un archivo referenciado, falla con mensaje claro en vez de reportar 0 bytes. → Tarea 6.

---

## Hallazgos del código que ajustan el alcance (leer antes de ejecutar)

- **El frontend NO lee `/api/org/capabilities`.** `frontend/src/store/enabledModulesStore.ts` carga `GET /api/users/me/context` (`app/modules/users/router.py::read_user_context`). Por eso `plan` va en **ambas** respuestas con un mismo helper; si solo se pone en capabilities, el menú nunca se entera.
- **El preset `ATLAS_POS` tiene 11 módulos, no 9:** `core, pos, cash_management, catalog, inventory, returns, pricing, payments, reports, labels, crm` (`app/services/capabilities_service.py:44` y `scripts/init_presets_v2.py:282`). Clientes (`/customers`, `module: 'crm'`) se ve hoy en FREE; por eso está en el perfil y se verifica su uso en la Tarea 3.
- **Las tres orgs FREE no ven `PresetHome`:** con preset `ATLAS_POS` hace `<Navigate to="/hq/operations">`. El recorte de widgets (Tarea 5) protege a cualquier org FREE con preset `ATLAS_ONE_*` y deja el inicio coherente con el menú; para Kaory/Coqueta el "inicio" es `HQOperations`, que no tiene widgets por módulo.
- **El chunk de entrada no mide 443 KB.** En el `dist/` del 2026-10-03: entrada `index-iK6tTYaD.js` = 109 KB; el `index-C8jRveWp.js` de 453 KB es ZXing y solo lo carga `StoreScanner` (lazy). Lo que sí viaja con el login es **`charts-*.js` (184 KB)**: `manualChunks.charts` arrastra `react/jsx-runtime` (dependencia de react-chartjs-2 que no está en `vendor`), así que `index.html` lo precarga y todos los chunks importan `{j as t} from "./charts-…"`. Ruta crítica medida (entrada + precargas + POS): 109,049 + 164,833 + 184,534 + 41,252 + 128,010 = **627,678 B**. El dist está viejo: la Tarea 6 vuelve a medir.
- **`platform_audit_log` no registra uso de pantallas** (solo acciones de plataforma y `PRODUCT_CREATE_CAJERO`). La verificación de uso se hace con el log de acceso de uvicorn (`docker logs atlas-one-prod`) y con evidencia en tablas (`employees`, `sales_documents.doc_type='QUOTE'`, `customers`).
- `vitest.config.ts` sí incluye `src/**/*.test.tsx` con `environment: 'node'` por defecto; las pruebas con DOM llevan `// @vitest-environment jsdom`. Los `*.test.ts(x)` están excluidos de `tsconfig.json`, así que `import.meta.glob` en una prueba no pasa por `tsc`.

---

### Task 1: Backend — `plan` en `/api/users/me/context` y `/api/org/capabilities`

**Files:**
- Modify: `app/services/capabilities_service.py` (añadir `resumen_plan` al final)
- Modify: `app/schemas/capabilities.py`
- Modify: `app/modules/tenants/router.py:325-362` (handler `get_org_caps`)
- Modify: `app/modules/users/router.py:27-130` (handler `read_user_context`)
- Test: `tests/test_plan_en_contexto.py`

**Interfaces:**
- Consumes: `app.services.plans.obtener_plan(clave) -> Plan` (`.clave`, `.nombre`), `Organization.plan` (`String`, default `"FREE"`).
- Produces: `resumen_plan(org: Organization | None) -> dict[str, str]` → `{"clave": "FREE", "nombre": "ONE FREE"}`; `PlanResumen(BaseModel)` con `clave: str`, `nombre: str`; campo `plan` en ambas respuestas (en `/me/context` es `None` cuando no hay organización activa).

- [ ] **Step 1: Escribir la prueba que falla**

```python
# tests/test_plan_en_contexto.py
"""El plan comercial viaja con el contexto del usuario y con las capacidades de la org.

El frontend recorta el menú con `plan.clave`; `plan.nombre` es lo que se muestra
en la tarjeta de inicio. NULL o clave desconocida = FREE (misma regla que
plans.obtener_plan), para que una fila vieja nunca deje a nadie sin menú.
"""
import pytest

from app.models.modules import Module, OrganizationModule
from app.modules.tenants.models import IndustryType


def _cabeceras(auth, org):
    return {**auth, "X-Organization-ID": str(org.id)}


def _con_core(db, org):
    if db.query(Module).filter(Module.key == "core").first() is None:
        db.add(Module(key="core", name="Core"))
        db.flush()
    db.add(OrganizationModule(organization_id=org.id, module_key="core", is_enabled=True))
    db.flush()


@pytest.mark.parametrize("guardado, clave, nombre", [
    (None, "FREE", "ONE FREE"),
    ("FREE", "FREE", "ONE FREE"),
    ("ULTRA_PLUS", "ULTRA_PLUS", "ULTRA+"),
    ("XYZ", "FREE", "ONE FREE"),
])
def test_me_context_trae_el_plan(client, db, auth_admin, org, guardado, clave, nombre):
    org.plan = guardado
    db.flush()
    r = client.get("/api/users/me/context", headers=_cabeceras(auth_admin, org))
    assert r.status_code == 200, r.text
    assert r.json()["plan"] == {"clave": clave, "nombre": nombre}


def test_org_capabilities_trae_el_plan(client, db, auth_admin, org):
    org.industry_type = IndustryType.ATLAS_POS
    org.plan = "PRO"
    _con_core(db, org)
    r = client.get("/api/org/capabilities/", headers=_cabeceras(auth_admin, org))
    assert r.status_code == 200, r.text
    assert r.json()["plan"] == {"clave": "PRO", "nombre": "ONE PRO"}


def test_el_resto_del_contexto_no_cambia(client, db, auth_admin, org):
    cuerpo = client.get("/api/users/me/context", headers=_cabeceras(auth_admin, org)).json()
    for clave in ("user", "organization", "preset", "enabled_modules", "capacidades", "plan"):
        assert clave in cuerpo
```

- [ ] **Step 2: Correrla y ver que falla**

Run: `.venv/bin/python -m pytest -q -p no:warnings tests/test_plan_en_contexto.py`
Expected: FAIL — `KeyError: 'plan'` en los tres tests (la respuesta no trae la clave).

- [ ] **Step 3: Helper + schema + ambos handlers**

Al final de `app/services/capabilities_service.py`:

```python
def resumen_plan(org) -> dict:
    """Clave y nombre visible del plan de la organización, para que la interfaz
    recorte el menú (perfil por plan). NULL, vacío o desconocido → FREE, igual
    que `plans.obtener_plan`: una fila vieja no deja a nadie sin menú.

    Import local: `plans` importa `INDUSTRY_PRESETS` de este módulo al cargar y
    un import en cabecera sería circular.
    """
    from app.services.plans import obtener_plan

    p = obtener_plan(getattr(org, "plan", None))
    return {"clave": p.clave, "nombre": p.nombre}
```

En `app/schemas/capabilities.py`:

```python
class PlanResumen(BaseModel):
    clave: str
    nombre: str


class OrgCapabilities(BaseModel):
    organization_id: int
    industry_type: str
    enabled_modules: List[str]
    ui_profile: str
    default_routes: Dict[str, str]
    nav_items: List[NavItem]
    plan: PlanResumen
```

En `app/modules/tenants/router.py`, junto a los imports del bloque CAPABILITIES (línea ~319):

```python
from app.services.capabilities_service import (
    get_organization_capabilities as _get_org_caps,
    resumen_plan as _resumen_plan,
)
```

y en el `return` de `get_org_caps`, después de `"nav_items": nav,`:

```python
        "plan": _resumen_plan(org),
```

En `app/modules/users/router.py::read_user_context`: en el diccionario inicial `ctx` añadir `"plan": None,` tras `"allowed_templates": []`, y dentro del `if org:` (después de `ctx["organization"] = {...}`):

```python
            # Plan comercial: la interfaz recorta el menú con la clave y muestra
            # el nombre en la tarjeta de inicio. Sin org activa queda None.
            from app.services.capabilities_service import resumen_plan
            ctx["plan"] = resumen_plan(org)
```

- [ ] **Step 4: Correr y ver que pasa; correr las pruebas vecinas**

Run: `.venv/bin/python -m pytest -q -p no:warnings tests/test_plan_en_contexto.py tests/test_contexto_capacidades.py tests/test_consolidated_routers.py tests/test_planes.py`
Expected: PASS (todas).

- [ ] **Step 5: Commit**

```bash
git add tests/test_plan_en_contexto.py app/services/capabilities_service.py app/schemas/capabilities.py app/modules/tenants/router.py app/modules/users/router.py
git commit -m "feat(planes): plan {clave, nombre} en /users/me/context y /org/capabilities"
```

---

### Task 2: Store del frontend — `plan` en `enabledModulesStore`

**Files:**
- Modify: `frontend/src/types/auth.ts` (añadir `PlanOrg`)
- Modify: `frontend/src/store/enabledModulesStore.ts`
- Test: `frontend/src/store/__tests__/enabledModulesStore.test.ts`

**Interfaces:**
- Consumes: respuesta de `GET /users/me/context` con `plan?: { clave, nombre } | null` (Tarea 1).
- Produces: `export interface PlanOrg { clave: string; nombre: string }` en `types/auth.ts`; `useEnabledModulesStore().plan: PlanOrg | null` (`null` = no cargó / servidor sin el campo / falló). Lo leen las Tareas 4 y 5.

- [ ] **Step 1: Escribir la prueba que falla**

```ts
// frontend/src/store/__tests__/enabledModulesStore.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest'

// `vi.mock` se iza por encima de los imports: lo que use la fábrica tiene que
// venir de `vi.hoisted`, no de una const del módulo.
const { get } = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('../../api/client', () => ({ default: { get } }))

import { useEnabledModulesStore } from '../enabledModulesStore'

const contexto = (extra: Record<string, unknown>) => ({
  data: { enabled_modules: ['core', 'pos'], preset: 'ATLAS_POS', capacidades: [], ...extra },
})

beforeEach(() => {
  useEnabledModulesStore.getState().reset()
  get.mockReset()
})

describe('enabledModulesStore.plan', () => {
  it('guarda el plan que manda /users/me/context', async () => {
    get.mockResolvedValue(contexto({ plan: { clave: 'FREE', nombre: 'ONE FREE' } }))
    await useEnabledModulesStore.getState().load()
    expect(useEnabledModulesStore.getState().plan).toEqual({ clave: 'FREE', nombre: 'ONE FREE' })
    expect(useEnabledModulesStore.getState().enabledModules).toEqual(['core', 'pos'])
  })

  it('sin `plan` en la respuesta (servidor viejo) queda null y lo demás carga igual', async () => {
    get.mockResolvedValue(contexto({}))
    await useEnabledModulesStore.getState().load()
    expect(useEnabledModulesStore.getState().plan).toBeNull()
    expect(useEnabledModulesStore.getState().loaded).toBe(true)
  })

  it('un plan mal formado (sin nombre) se descarta en vez de romper el menú', async () => {
    get.mockResolvedValue(contexto({ plan: { clave: 'FREE' } }))
    await useEnabledModulesStore.getState().load()
    expect(useEnabledModulesStore.getState().plan).toBeNull()
  })

  it('si la petición falla, plan null y loaded true (fail-open)', async () => {
    get.mockRejectedValue(new Error('red caída'))
    await useEnabledModulesStore.getState().load()
    expect(useEnabledModulesStore.getState().plan).toBeNull()
    expect(useEnabledModulesStore.getState().loaded).toBe(true)
  })

  it('reset vuelve el plan a null', async () => {
    get.mockResolvedValue(contexto({ plan: { clave: 'PRO', nombre: 'ONE PRO' } }))
    await useEnabledModulesStore.getState().load()
    useEnabledModulesStore.getState().reset()
    expect(useEnabledModulesStore.getState().plan).toBeNull()
  })
})
```

- [ ] **Step 2: Correr y ver que falla**

Run: `cd frontend && npx vitest run src/store/__tests__/enabledModulesStore.test.ts`
Expected: FAIL — `expected undefined to deeply equal { clave: 'FREE', … }` (el store no tiene `plan`).

- [ ] **Step 3: Implementación mínima**

En `frontend/src/types/auth.ts`, después de `export interface Organization { … }`:

```ts
/** Plan comercial de la organización activa, tal como lo manda `/users/me/context`. */
export interface PlanOrg {
  clave: string
  nombre: string
}
```

En `frontend/src/store/enabledModulesStore.ts`:

```ts
import { create } from 'zustand'
import client from '../api/client'
import { puede } from '../utils/capacidades'
import type { PlanOrg } from '../types/auth'
```

```ts
interface ContextResponse {
  enabled_modules?: string[]
  preset?: string | null
  capacidades?: string[]
  plan?: { clave?: unknown; nombre?: unknown } | null
  // (other fields present in /me/context but not needed here)
}

/** Solo acepta un plan completo; cualquier otra cosa es "no sé" (null = sin recorte). */
function leerPlan(crudo: ContextResponse['plan']): PlanOrg | null {
  if (!crudo || typeof crudo.clave !== 'string' || typeof crudo.nombre !== 'string') return null
  return { clave: crudo.clave, nombre: crudo.nombre }
}

interface EnabledModulesStore {
  enabledModules: string[]
  preset: string | null
  capacidades: string[]
  /** Plan comercial; null mientras no carga, si falló o si el servidor no lo manda. */
  plan: PlanOrg | null
  loaded: boolean
  loading: boolean
  load: () => Promise<void>
  reset: () => void
}
```

Estado inicial: añadir `plan: null,` tras `capacidades: [],`. En `load`, dentro del `try`:

```ts
      const plan = leerPlan(r.data?.plan)
      set({
        enabledModules: mods,
        preset,
        capacidades,
        plan,
        loaded: true,
        loading: false,
      })
```

En el `catch`: `set({ enabledModules: [], preset: null, capacidades: [], plan: null, loaded: true, loading: false })`. En `reset`: `set({ enabledModules: [], preset: null, capacidades: [], plan: null, loaded: false, loading: false })`.

- [ ] **Step 4: Correr y ver que pasa**

Run: `cd frontend && npx vitest run src/store/__tests__/enabledModulesStore.test.ts && npx tsc --noEmit`
Expected: 5 passed; tsc sin errores.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/auth.ts frontend/src/store/enabledModulesStore.ts frontend/src/store/__tests__/enabledModulesStore.test.ts
git commit -m "feat(planes): el store de módulos guarda el plan de la org"
```

---

### Task 3: Verificación en producción (manual, solo lectura) — habilita qué se esconde

Esta tarea no cambia código. El agente **no puede leer prod**: prepara los comandos y el usuario los corre con `!` desde este repo (acceso `ssh ionos`, contenedor `atlas-one-prod`). El resultado se anota en el commit de la Tarea 4.

**Files:**
- Ninguno en el repo. Resultado: una tabla pegada en el mensaje de la Tarea 4.

- [ ] **Step 1: Ventana de observación del log de acceso**

El log de uvicorn vive solo desde el último despliegue (ver memoria "Registros efímeros en prod"). Primero saber cuánto cubre:

```bash
ssh ionos 'docker inspect -f "{{.State.StartedAt}}" atlas-one-prod'
```

Si cubre menos de 7 días hábiles, esperar a cubrirlos antes del Step 3 (las tiendas abren todos los días; una semana basta para ver si alguien entra a Mi expediente o al armazón móvil).

- [ ] **Step 2: Qué orgs están en FREE y con qué módulos (y si hay orgs activas sin preset aplicado)**

```bash
ssh ionos 'docker exec -i atlas-one-prod python -' <<'EOF'
from sqlalchemy import text
from app.core.database import engine

SQL = """
SELECT o.id, o.name, o.plan, o.industry_type::text AS preset, o.status,
       COALESCE(array_agg(om.module_key ORDER BY om.module_key) FILTER (WHERE om.is_enabled), '{}') AS modulos
FROM organization o
LEFT JOIN organization_modules om ON om.organization_id = o.id
WHERE o.status = 'ACTIVE'
GROUP BY o.id, o.name, o.plan, o.industry_type, o.status
ORDER BY o.id
"""
with engine.connect() as c:
    for fila in c.execute(text(SQL)):
        print(dict(fila._mapping))
EOF
```

Lectura: anotar los `id` con `plan = 'FREE'` (se esperan 3: Kaory, Novedades, Coqueta) y confirmar que los tres traen `reports`, `catalog`, `crm`. Si alguna org ACTIVE tiene `modulos = {}` o sin `reports`, apuntarlo: en la Tarea 4 **no** se pone `module: 'reports'` a Control/Reportes HQ/móviles (irían solo al perfil FREE).

- [ ] **Step 3: Uso de Mi expediente, móviles y Clientes por las orgs FREE**

```bash
ssh ionos 'docker exec -i atlas-one-prod python -' <<'EOF'
from sqlalchemy import text
from app.core.database import engine

CONSULTAS = {
  # /hr/me escribe y lee `employees` (GET/PUT /api/hr/employees/me)
  "expedientes_por_org_free": """
    SELECT o.id, o.name, count(e.id) AS expedientes
    FROM organization o LEFT JOIN employees e ON e.organization_id = o.id
    WHERE o.plan = 'FREE' GROUP BY o.id, o.name ORDER BY o.id""",
  # /mobile/sales crea cotizaciones (POST /api/quotes/ → sales_documents.doc_type = QUOTE)
  "cotizaciones_por_org_free": """
    SELECT o.id, o.name, count(sd.id) AS cotizaciones, max(sd.created_at) AS ultima
    FROM organization o LEFT JOIN sales_documents sd
      ON sd.organization_id = o.id AND sd.doc_type = 'QUOTE'
    WHERE o.plan = 'FREE' GROUP BY o.id, o.name ORDER BY o.id""",
  # /mobile/dashboard, /mobile/query, /mobile/profile son el inicio de VENDEDOR / SOPORTE_OPERATIVO
  "roles_por_org_free": """
    SELECT o.id, o.name, u.role::text AS rol, count(*) AS usuarios
    FROM users u
    JOIN user_organizations uo ON uo.user_id = u.id AND uo.is_active
    JOIN organization o ON o.id = uo.organization_id
    WHERE o.plan = 'FREE' AND u.is_active
    GROUP BY o.id, o.name, u.role ORDER BY o.id, rol""",
  # /customers: clientes capturados y ventas con cliente en los últimos 30 días
  "clientes_por_org_free": """
    SELECT o.id, o.name,
           (SELECT count(*) FROM customers c WHERE c.organization_id = o.id) AS clientes,
           (SELECT count(*) FROM sales_documents sd WHERE sd.organization_id = o.id
              AND sd.customer_id IS NOT NULL AND sd.created_at > now() - interval '30 days') AS ventas_con_cliente_30d
    FROM organization o WHERE o.plan = 'FREE' ORDER BY o.id""",
}
with engine.connect() as c:
    for nombre, sql in CONSULTAS.items():
        print(f"== {nombre}")
        for fila in c.execute(text(sql)):
            print("  ", dict(fila._mapping))
EOF
```

Y el log de acceso desde el último arranque (uvicorn imprime `"GET /api/… HTTP/1.1" 200`):

```bash
ssh ionos 'docker logs atlas-one-prod 2>&1 | grep -E "/api/hr/employees/me|POST /api/quotes/ |/api/reports/(daily-summary|sales-by-hour)" | awk "{print \$6, \$7}" | sort | uniq -c | sort -rn'
```

Decisión (qué resultado habilita esconder cada URL en FREE):

| URL en el perfil FREE | Se esconde si… | Si no se cumple |
|---|---|---|
| `/hr/me` | `expedientes = 0` en las 3 orgs FREE **y** 0 líneas `GET /api/hr/employees/me` en el log | sale del perfil; queda solo con `module: 'hr'` (FREE no tiene `hr`, así que igual no se ve, pero el motivo es el módulo, no el plan) |
| `/mobile/sales` | `cotizaciones = 0` en las 3 | sale del perfil (queda con `module: 'quotes'`) |
| `/mobile/dashboard`, `/mobile/query`, `/mobile/profile` | ninguna org FREE tiene usuarios `VENDEDOR` ni `SOPORTE_OPERATIVO` | el patrón `/mobile/*` se cambia por la lista explícita sin esas tres |
| `/mobile/owner` | siempre: es la vuelta al armazón móvil del admin y el menú inferior (`navMovilPorRol`) no pasa por `visibleNavItems`, así que el teléfono no pierde nada | — |
| `/customers` | `clientes = 0` **y** `ventas_con_cliente_30d = 0` en las 3 | sale del perfil para todas (el botón Cliente del carrito del POS no es un ítem de menú y no se toca en ningún caso) |
| `/hq/control`, `/ai`, `/quotes`, `/quotes/new`, `/seguimiento` | siempre (IA y cotizaciones no están en FREE; Control sigue enlazado desde Inicio) | — |

- [ ] **Step 4: Dejar constancia**

Pegar la tabla con los conteos reales en el cuerpo del commit de la Tarea 4 (`git commit` con mensaje multilínea) y ajustar `PERFIL_POR_PLAN.FREE` según la tabla antes de escribir las pruebas de esa tarea.

---

### Task 4: Perfil por plan — `navPerfilPlan.ts`, `visibleNavItems(plan)`, `module:` en 7 ítems, Sidebar

**Files:**
- Create: `frontend/src/components/layout/navPerfilPlan.ts`
- Modify: `frontend/src/components/layout/navVisibility.ts`
- Modify: `frontend/src/components/layout/navConfig.ts` (ítems `/hq/reports-hub`, `/hq/control`, `/hr/me`, `/mobile/owner`, `/mobile/dashboard`, `/mobile/query`, `/mobile/sales`)
- Modify: `frontend/src/components/layout/Sidebar.tsx:607-621`
- Test: `frontend/src/components/layout/__tests__/navPerfilPlan.test.ts`
- Test: `frontend/src/components/layout/__tests__/navConfig.test.ts` (añadir un `describe`)

**Interfaces:**
- Consumes: `PlanOrg` (`types/auth.ts`, Tarea 2); `useEnabledModulesStore().plan` (Tarea 2); `NavItem`, `visibleNavItems`, `ALL_NAV`, `ROLE_ROUTES`.
- Produces: `PERFIL_POR_PLAN: Record<string, readonly string[]>`; `coincideUrl(url: string, patron: string): boolean` (patrón `'/mobile/*'` = prefijo); `urlsOcultasPorPlan(plan: PlanOrg | null | undefined): readonly string[]`; `recortarPorPlan(items: NavItem[], plan: PlanOrg | null | undefined): NavItem[]`; `NavVisibilityOptions.plan?: PlanOrg | null`.

- [ ] **Step 1: Escribir las pruebas que fallan**

```ts
// frontend/src/components/layout/__tests__/navPerfilPlan.test.ts
import { describe, it, expect } from 'vitest'

import { ALL_NAV, ROLE_ROUTES, rolesConAcceso } from '../navConfig'
import { visibleNavItems } from '../navVisibility'
import { PERFIL_POR_PLAN, coincideUrl, recortarPorPlan, urlsOcultasPorPlan } from '../navPerfilPlan'
import type { PlanOrg, Role } from '../../../types/auth'

// Kaory, Novedades y Coqueta: preset ATLAS_POS (11 módulos) en plan FREE.
const ATLAS_POS = [
  'core', 'pos', 'cash_management', 'catalog', 'inventory', 'returns',
  'pricing', 'payments', 'reports', 'labels', 'crm',
]
const FREE: PlanOrg = { clave: 'FREE', nombre: 'ONE FREE' }
const ULTRA: PlanOrg = { clave: 'ULTRA_PLUS', nombre: 'ULTRA+' }

const menu = (role: Role, plan: PlanOrg | null, enabledModules = ATLAS_POS) =>
  visibleNavItems(ALL_NAV, {
    role, allowed: ROLE_ROUTES[role] ?? [], enabledModules, isGastro: false, plan,
  }).map((i) => i.url)

// Lo que la dueña y la cajera de una tienda FREE usan a diario: intocable.
const DIARIO_ADMIN = [
  '/hq/operations', '/hq/reports-hub', '/sales', '/products', '/labels', '/printer-settings',
  '/cash-history', '/hq/sales', '/hq/returns', '/inventory', '/admin/catalog',
  '/users', '/hq/branches', '/organization',
]
const DIARIO_CAJERA = [
  '/atlas-pos', '/pos', '/sales', '/cash-history', '/returns', '/products', '/labels', '/printer-settings',
]

describe('perfil FREE', () => {
  it('la administradora conserva toda su operación diaria', () => {
    expect(menu('ADMINISTRADOR', FREE)).toEqual(expect.arrayContaining(DIARIO_ADMIN))
  })

  it('la administradora no ve Control, IA, cotizaciones, Clientes ni el armazón móvil', () => {
    const urls = menu('ADMINISTRADOR', FREE)
    for (const u of ['/hq/control', '/ai', '/quotes', '/quotes/new', '/seguimiento', '/customers', '/mobile/owner']) {
      expect(urls).not.toContain(u)
    }
  })

  it('la cajera conserva Cobrar, Corte, Devoluciones, Productos e Impresora', () => {
    expect(menu('CAJERO', FREE)).toEqual(expect.arrayContaining(DIARIO_CAJERA))
  })

  it('la cajera no ve Mi expediente ni Clientes', () => {
    const urls = menu('CAJERO', FREE)
    expect(urls).not.toContain('/hr/me')
    expect(urls).not.toContain('/customers')
  })

  it('ULTRA+ con los mismos módulos ve todo lo de FREE y además lo recortado', () => {
    const free = menu('ADMINISTRADOR', FREE)
    const ultra = menu('ADMINISTRADOR', ULTRA)
    for (const u of free) expect(ultra).toContain(u)
    expect(ultra).toEqual(expect.arrayContaining(['/hq/control', '/customers', '/mobile/owner']))
    // IA y cotizaciones dependen del módulo, no del plan: sin módulo tampoco en ULTRA+
    expect(ultra).not.toContain('/ai')
    expect(ultra).not.toContain('/quotes')
  })

  it('sin plan (no cargó / servidor viejo) no se recorta nada', () => {
    expect(menu('ADMINISTRADOR', null)).toContain('/hq/control')
    expect(menu('ADMINISTRADOR', null)).toContain('/customers')
  })

  it('plan desconocido = sin recorte, sin excepción', () => {
    expect(menu('ADMINISTRADOR', { clave: 'XYZ', nombre: '?' })).toEqual(menu('ADMINISTRADOR', null))
  })

  it('esconder no quita acceso: el guard de ruta no depende del plan', () => {
    expect(rolesConAcceso('/hq/control')).toContain('ADMINISTRADOR')
    expect(rolesConAcceso('/hr/me')).toContain('CAJERO')
  })

  it('toda URL del perfil apunta a un ítem real (sin fantasmas)', () => {
    const urls = ALL_NAV.map((i) => i.url)
    for (const patron of PERFIL_POR_PLAN.FREE) {
      expect(urls.some((u) => coincideUrl(u, patron)), patron).toBe(true)
    }
  })
})

describe('coincideUrl', () => {
  it('iguala exacto o por prefijo con /*', () => {
    expect(coincideUrl('/hr/me', '/hr/me')).toBe(true)
    expect(coincideUrl('/hr', '/hr/me')).toBe(false)
    expect(coincideUrl('/mobile/owner', '/mobile/*')).toBe(true)
    expect(coincideUrl('/mobile', '/mobile/*')).toBe(false)
    expect(coincideUrl('/mobiles/x', '/mobile/*')).toBe(false)
  })
})

describe('recortarPorPlan', () => {
  it('devuelve la misma lista (misma referencia) cuando no hay nada que recortar', () => {
    const items = ALL_NAV.slice(0, 3)
    expect(recortarPorPlan(items, null)).toBe(items)
    expect(recortarPorPlan(items, ULTRA)).toBe(items)
  })

  it('no reordena lo que deja', () => {
    const urls = recortarPorPlan(ALL_NAV, FREE).map((i) => i.url)
    const esperado = ALL_NAV.map((i) => i.url).filter((u) => !urlsOcultasPorPlan(FREE).some((p) => coincideUrl(u, p)))
    expect(urls).toEqual(esperado)
  })
})
```

Añadir al final de `frontend/src/components/layout/__tests__/navConfig.test.ts`:

```ts
describe('los ítems que recibieron `module:` en SP2', () => {
  const conModulo = Object.fromEntries(ALL_NAV.map((n) => [n.url, n.module]))

  it('Mi expediente exige hr; Cotización móvil, quotes; Consulta móvil, catalog', () => {
    expect(conModulo['/hr/me']).toBe('hr')
    expect(conModulo['/mobile/sales']).toBe('quotes')
    expect(conModulo['/mobile/query']).toBe('catalog')
  })

  it('Reportes HQ, Control y los paneles móviles exigen reports (todo preset lo trae)', () => {
    for (const u of ['/hq/reports-hub', '/hq/control', '/mobile/owner', '/mobile/dashboard']) {
      expect(conModulo[u], u).toBe('reports')
    }
  })

  it('la operación diaria sigue sin `module:` (no hay vía nueva para esconderle la caja a una tienda)', () => {
    for (const u of ['/atlas-pos', '/pos', '/sales', '/cash-history', '/returns', '/products', '/reports',
                     '/printer-settings', '/hq/operations', '/organization', '/hq/branches', '/users']) {
      expect(conModulo[u], u).toBeUndefined()
    }
  })

  it('una org con solo core (preset nunca aplicado) conserva Mi día, Cobrar y Corte', () => {
    expect(menu('CAJERO', ['core'])).toEqual(expect.arrayContaining(['/atlas-pos', '/pos', '/cash-history']))
  })
})
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `cd frontend && npx vitest run src/components/layout/__tests__/navPerfilPlan.test.ts src/components/layout/__tests__/navConfig.test.ts`
Expected: FAIL — `Cannot find module '../navPerfilPlan'` y, en navConfig, `expected undefined to be 'hr'`.

- [ ] **Step 3: Crear `navPerfilPlan.ts`**

```ts
// frontend/src/components/layout/navPerfilPlan.ts
import type { PlanOrg } from '../../types/auth'
import type { NavItem } from './navVisibility'

/**
 * Perfil por plan: URLs que ese plan NO ve en el menú. Se aplica DESPUÉS del
 * gating por módulo y por rol, y solo esconde: la URL sigue abriendo (el
 * candado real es `require_module` en el backend y `RutaPorRol` en la ruta).
 *
 * FREE (Kaory, Novedades, Coqueta — preset ATLAS_POS): su día es cobrar, corte,
 * ventas, devoluciones, productos, inventario, reportes, impresora, usuarios y
 * sucursal. Lo demás estorba en una PC vieja. Qué se puede esconder se verificó
 * contra producción (plan SP2, Tarea 3) antes de entrar aquí.
 *
 * Un patrón que termina en `/*` esconde por prefijo (`/mobile/*`). Planes que
 * no aparecen = sin recorte.
 */
export const PERFIL_POR_PLAN: Record<string, readonly string[]> = {
  FREE: [
    '/hq/control',
    '/hr/me',
    '/mobile/*',
    '/ai',
    '/quotes', '/quotes/new', '/seguimiento',
    '/customers',
  ],
}

export function coincideUrl(url: string, patron: string): boolean {
  if (patron.endsWith('/*')) return url.startsWith(patron.slice(0, -1))
  return url === patron
}

/** Vacío cuando no hay plan (no cargó) o el plan no tiene perfil: fail-open. */
export function urlsOcultasPorPlan(plan: PlanOrg | null | undefined): readonly string[] {
  if (!plan) return []
  return PERFIL_POR_PLAN[plan.clave] ?? []
}

export function recortarPorPlan(items: NavItem[], plan: PlanOrg | null | undefined): NavItem[] {
  const ocultas = urlsOcultasPorPlan(plan)
  if (ocultas.length === 0) return items
  return items.filter((n) => !ocultas.some((p) => coincideUrl(n.url, p)))
}
```

Si la Tarea 3 sacó alguna URL del perfil, quitarla aquí y de la prueba `no ve …` correspondiente (y, si `/mobile/*` se volvió lista explícita, escribir las URLs una por una).

- [ ] **Step 4: `visibleNavItems` recibe `plan`**

En `frontend/src/components/layout/navVisibility.ts`:

```ts
import type { PlanOrg, Role } from '../../types/auth'
import { recortarPorPlan } from './navPerfilPlan'
```

```ts
export interface NavVisibilityOptions {
  role: Role
  /** URLs que ROLE_ROUTES permite a este rol. */
  allowed: string[]
  /** Módulos activos de la org. Vacío = aún no cargó (o falló): fail-open. */
  enabledModules: string[]
  isGastro: boolean
  /** Plan comercial de la org. null/undefined = no cargó: no se recorta (fail-open). */
  plan?: PlanOrg | null
}
```

y en la función, después de `.filter((n) => !(n.hideForGastro && isGastro))` y antes de `.sort(...)` no se puede encadenar (recorta una lista), así que el cuerpo queda:

```ts
export function visibleNavItems(items: NavItem[], opts: NavVisibilityOptions): NavItem[] {
  const { role, allowed, enabledModules, isGastro, plan } = opts
  const modulesLoaded = enabledModules.length > 0
  const hasModule = (key: string | undefined) => !key || !modulesLoaded || enabledModules.includes(key)
  const isBranchRole = BRANCH_ROLES.includes(role)
  const porModulo = items
    .filter((n) => allowed.includes(n.url))
    .filter((n) => hasModule(n.module))
    .filter((n) => !isBranchRole || hasModule(n.branchModule))
    .filter((n) => !(n.hideForGastro && isGastro))
  // El perfil por plan va al final: solo esconde entre lo que ya pasó rol y módulo.
  return recortarPorPlan(porModulo, plan).sort((a, b) => a.sort - b.sort)
}
```

(`navPerfilPlan.ts` importa el tipo `NavItem` de `navVisibility.ts` y `navVisibility.ts` importa la función de `navPerfilPlan.ts`: el import de tipo se borra al compilar, no hay ciclo en runtime.)

- [ ] **Step 5: `module:` en los 7 ítems de `navConfig.ts`**

Reemplazar las líneas de estos ítems en `ALL_NAV` (mismos valores, solo se añade `module`):

```ts
  { label: 'Reportes',          short: 'REP', icon: 'fa-chart-line',          url: '/hq/reports-hub',   group: 'hq',   sort: 1,  module: 'reports' },
  { label: 'Control',           short: 'CTL', icon: 'fa-sliders',             url: '/hq/control',       group: 'hq',   sort: 2,  module: 'reports' },
```

```ts
  // `hr` es de BUSINESS en adelante: sin el módulo, el expediente no existe.
  { label: 'Mi expediente',     short: 'YO',  icon: 'fa-id-card',             url: '/hr/me',            group: 'pos',  sort: 8,  module: 'hr' },
```

```ts
  { label: 'Resumen móvil',     short: 'RSM', icon: 'fa-mobile-screen-button', url: '/mobile/owner',    group: 'mob',  sort: -1, module: 'reports' },
  { label: 'Dashboard móvil',   short: 'DSH', icon: 'fa-mobile-screen',       url: '/mobile/dashboard', group: 'mob',  sort: 0,  module: 'reports' },
  { label: 'Consulta móvil',    short: 'QRY', icon: 'fa-mobile-alt',          url: '/mobile/query',     group: 'mob',  sort: 1,  module: 'catalog' },
  // La "cotización móvil" crea cotizaciones (POST /api/quotes): es el módulo quotes.
  { label: 'Cotización móvil',  short: 'COT', icon: 'fa-file-invoice',        url: '/mobile/sales',     group: 'mob',  sort: 2,  module: 'quotes' },
```

`/mobile/profile` y los 12 de la operación diaria/administración se quedan sin `module:` (ver Global Constraints). Si la Tarea 3 encontró una org ACTIVE sin `reports`, omitir `module: 'reports'` en los cuatro de arriba y dejar un comentario con el id de la org.

- [ ] **Step 6: Sidebar pasa el plan**

En `frontend/src/components/layout/Sidebar.tsx`, línea 607:

```ts
  const { enabledModules, preset, loaded, load, plan } = useEnabledModulesStore()
```

y línea 621:

```ts
  const items = visibleNavItems(ALL_NAV, { role, allowed, enabledModules, isGastro, plan })
```

- [ ] **Step 7: Correr y ver que pasa; typecheck**

Run: `cd frontend && npx vitest run src/components/layout && npx tsc --noEmit`
Expected: PASS (navPerfilPlan, navConfig, navVisibility); tsc limpio.

- [ ] **Step 8: Commit (con la evidencia de la Tarea 3 en el cuerpo)**

```bash
git add frontend/src/components/layout/navPerfilPlan.ts frontend/src/components/layout/navVisibility.ts frontend/src/components/layout/navConfig.ts frontend/src/components/layout/Sidebar.tsx frontend/src/components/layout/__tests__/navPerfilPlan.test.ts frontend/src/components/layout/__tests__/navConfig.test.ts
git commit -F - <<'EOF'
feat(menú): perfil por plan — FREE ve solo su operación

Verificado en prod el <fecha> (Tarea 3 del plan SP2):
<pegar aquí la tabla de conteos: expedientes, cotizaciones, roles, clientes por org FREE y líneas del log>

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf
EOF
```

---

### Task 5: Inicio por preset — widgets por plan y una sola tarjeta de upsell

**Files:**
- Create: `frontend/src/pages/home/widgetsPorPlan.ts`
- Modify: `frontend/src/pages/home/PresetHome.tsx` (`Widget`, `HomeShell`, los 6 homes con `HomeShell`)
- Test: `frontend/src/pages/home/__tests__/widgetsPorPlan.test.ts`
- Test: `frontend/src/pages/home/__tests__/PresetHome.test.tsx`

**Interfaces:**
- Consumes: `useEnabledModulesStore().plan` y `.enabledModules` (Tarea 2); `PlanOrg`.
- Produces: `widgetVisible(w: { module?: string }, plan: PlanOrg | null, enabledModules: string[]): boolean`; `separarWidgets<T extends { module?: string }>(widgets: T[], plan, enabledModules): { visibles: T[]; ocultos: T[] }`; `WidgetProps.module?: string`; `HomeShell` recibe `plan` y `enabledModules` y pinta `TarjetaPlan` cuando hay ocultos. (Los homes gastro usan `GastroHomeDay` con `actions`, no widgets: fuera de alcance, no cambian.)

- [ ] **Step 1: Pruebas de la función pura (fallan)**

```ts
// frontend/src/pages/home/__tests__/widgetsPorPlan.test.ts
import { describe, it, expect } from 'vitest'
import { separarWidgets, widgetVisible } from '../widgetsPorPlan'

const FREE = { clave: 'FREE', nombre: 'ONE FREE' }
const PRO = { clave: 'PRO', nombre: 'ONE PRO' }
const widgets = [
  { title: 'Inventario', module: 'inventory' },
  { title: 'Cotizaciones', module: 'quotes' },
  { title: 'Sucursales' },
]

describe('widgetVisible', () => {
  it('en FREE solo se ve el widget cuyo módulo está activo', () => {
    expect(widgetVisible({ module: 'inventory' }, FREE, ['core', 'inventory'])).toBe(true)
    expect(widgetVisible({ module: 'quotes' }, FREE, ['core', 'inventory'])).toBe(false)
  })
  it('sin módulo declarado siempre se ve', () => {
    expect(widgetVisible({}, FREE, ['core'])).toBe(true)
  })
  it('fuera de FREE se ve todo (el CTA lleva a la pantalla que avisa)', () => {
    expect(widgetVisible({ module: 'quotes' }, PRO, ['core'])).toBe(true)
  })
  it('sin plan cargado no se esconde nada', () => {
    expect(widgetVisible({ module: 'quotes' }, null, ['core'])).toBe(true)
  })
})

describe('separarWidgets', () => {
  it('reparte en visibles y ocultos conservando el orden', () => {
    const { visibles, ocultos } = separarWidgets(widgets, FREE, ['core', 'inventory'])
    expect(visibles.map((w) => w.title)).toEqual(['Inventario', 'Sucursales'])
    expect(ocultos.map((w) => w.title)).toEqual(['Cotizaciones'])
  })
  it('con todos los módulos no hay ocultos', () => {
    expect(separarWidgets(widgets, FREE, ['inventory', 'quotes']).ocultos).toEqual([])
  })
})
```

- [ ] **Step 2: Correr y ver que falla**

Run: `cd frontend && npx vitest run src/pages/home/__tests__/widgetsPorPlan.test.ts`
Expected: FAIL — `Cannot find module '../widgetsPorPlan'`.

- [ ] **Step 3: Implementar `widgetsPorPlan.ts`**

```ts
// frontend/src/pages/home/widgetsPorPlan.ts
import type { PlanOrg } from '../../types/auth'

/**
 * En FREE el inicio solo muestra widgets de módulos activos: una tienda que
 * no tiene cotizaciones no necesita una tarjeta que la mande a una pantalla
 * que le dirá "no disponible". El upsell se concentra en UNA tarjeta (la pinta
 * HomeShell), no en cada widget. Fuera de FREE, o sin plan cargado, se ve todo.
 */
export function widgetVisible(
  w: { module?: string },
  plan: PlanOrg | null,
  enabledModules: string[],
): boolean {
  if (!w.module) return true
  if (!plan || plan.clave !== 'FREE') return true
  return enabledModules.includes(w.module)
}

export function separarWidgets<T extends { module?: string }>(
  widgets: T[],
  plan: PlanOrg | null,
  enabledModules: string[],
): { visibles: T[]; ocultos: T[] } {
  const visibles: T[] = []
  const ocultos: T[] = []
  for (const w of widgets) (widgetVisible(w, plan, enabledModules) ? visibles : ocultos).push(w)
  return { visibles, ocultos }
}
```

- [ ] **Step 4: Correr y ver que pasa**

Run: `cd frontend && npx vitest run src/pages/home/__tests__/widgetsPorPlan.test.ts`
Expected: 6 passed.

- [ ] **Step 5: Prueba de render de `PresetHome` (falla)**

```tsx
// frontend/src/pages/home/__tests__/PresetHome.test.tsx
// @vitest-environment jsdom
import { describe, it, expect, afterEach, beforeEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import { PresetHome } from '../PresetHome'
import { useAuthStore } from '../../../store/authStore'
import { useEnabledModulesStore } from '../../../store/enabledModulesStore'
import type { Organization, User } from '../../../types/auth'

const ana = {
  id: 1, username: 'ana', email: null, full_name: 'Ana López', role: 'ADMINISTRADOR',
  platform_role: 'NONE', branch_id: null, organization_id: 1, is_active: true,
} as User
const tienda = { id: 1, name: 'Tienda Demo', industry_type: 'ATLAS_ONE_RETAIL', hq_branch_id: null } as Organization
const FREE = { clave: 'FREE', nombre: 'ONE FREE' }
const ULTRA = { clave: 'ULTRA_PLUS', nombre: 'ULTRA+' }

function pintar(plan: typeof FREE | null, enabledModules: string[]) {
  useEnabledModulesStore.setState({ loaded: true, loading: false, preset: 'ATLAS_ONE_RETAIL', enabledModules, plan, capacidades: [] })
  return render(<MemoryRouter><PresetHome /></MemoryRouter>)
}

beforeEach(() => {
  useAuthStore.setState({ user: ana, org: tienda, token: 't', isAuthenticated: true, hydrated: true })
})
afterEach(cleanup)

describe('PresetHome en FREE (retail)', () => {
  it('esconde los widgets de módulos no activos y los resume en una sola tarjeta', () => {
    pintar(FREE, ['core', 'pos', 'inventory', 'reports'])
    expect(screen.getByText('Inventario')).toBeTruthy()
    expect(screen.queryByText('Cotizaciones')).toBeNull()
    expect(screen.queryByText('Compras')).toBeNull()
    const tarjeta = screen.getByTestId('tarjeta-plan')
    expect(tarjeta.textContent).toContain('ONE FREE')
    expect(tarjeta.textContent).toContain('Cotizaciones')
    expect(screen.getAllByTestId('tarjeta-plan')).toHaveLength(1)
  })

  it('con todos los módulos activos no hay tarjeta de plan', () => {
    pintar(FREE, ['core', 'inventory', 'purchasing', 'promotions', 'quotes', 'reports'])
    expect(screen.queryByTestId('tarjeta-plan')).toBeNull()
    expect(screen.getByText('Cotizaciones')).toBeTruthy()
  })

  it('con todo fuera de plan queda la tarjeta sola, nunca una rejilla vacía', () => {
    pintar(FREE, ['core'])
    expect(screen.getByTestId('tarjeta-plan')).toBeTruthy()
    expect(screen.getByText('Sucursales')).toBeTruthy() // sin módulo: siempre
  })
})

describe('PresetHome fuera de FREE', () => {
  it('ULTRA+ ve todos los widgets y ninguna tarjeta', () => {
    pintar(ULTRA, ['core'])
    expect(screen.getByText('Cotizaciones')).toBeTruthy()
    expect(screen.queryByTestId('tarjeta-plan')).toBeNull()
  })
  it('sin plan cargado no se esconde nada', () => {
    pintar(null, ['core'])
    expect(screen.getByText('Compras')).toBeTruthy()
  })
})
```

- [ ] **Step 6: Correr y ver que falla**

Run: `cd frontend && npx vitest run src/pages/home/__tests__/PresetHome.test.tsx`
Expected: FAIL — `Unable to find an element by: [data-testid="tarjeta-plan"]` y "Cotizaciones" presente en FREE.

- [ ] **Step 7: `Widget` con `module`, `HomeShell` reparte y pinta la tarjeta**

En `frontend/src/pages/home/PresetHome.tsx`:

```tsx
import { Children, isValidElement, useEffect, type ReactElement, type ReactNode } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { useEnabledModulesStore } from '../../store/enabledModulesStore'
import { useAuthStore } from '../../store/authStore'
import { rolesConAcceso } from '../../components/layout/navConfig'
import type { PlanOrg } from '../../types/auth'
import { GastroHomeDay } from './GastroHomeDay'
import { separarWidgets } from './widgetsPorPlan'
```

En `PresetHome()`: `const { preset, loaded, load, plan, enabledModules } = useEnabledModulesStore()` y `const home = { greeting, orgName, puedeCobrar, plan, enabledModules }`.

```tsx
interface HomeProps {
  greeting: string
  orgName: string
  /** ¿Este rol puede abrir el punto de venta? (ver ROLE_ROUTES). */
  puedeCobrar: boolean
  plan: PlanOrg | null
  enabledModules: string[]
}

interface WidgetProps {
  icon: string
  title: string
  description: string
  cta: string
  ctaUrl: string
  beta?: boolean
  /** Módulo que la pantalla destino necesita. En FREE, sin el módulo el widget no se pinta. */
  module?: string
}

function esWidget(nodo: ReactNode): nodo is ReactElement<WidgetProps> {
  return isValidElement(nodo) && nodo.type === Widget
}

/** Una sola tarjeta para todo lo que el plan no cubre: el upsell no se repite en cada widget. */
function TarjetaPlan({ plan, ocultos }: { plan: PlanOrg; ocultos: string[] }) {
  return (
    <div
      data-testid="tarjeta-plan"
      style={{
        background: 'var(--p-surface)',
        border: '1px dashed var(--p-border)',
        borderRadius: 6,
        padding: 16,
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
      }}
    >
      <strong style={{ fontSize: 13 }}>Tu plan: {plan.nombre}</strong>
      <p style={{ margin: 0, fontSize: 12, color: 'var(--p-muted)', lineHeight: 1.5 }}>
        Disponibles en planes superiores: {ocultos.join(', ')}.
      </p>
      <p style={{ margin: 0, fontSize: 12, color: 'var(--p-muted)' }}>
        Pídelos a tu asesor de Atlas Tech; el cambio de plan lo hace la plataforma.
      </p>
    </div>
  )
}

function HomeShell({
  greeting,
  orgName,
  title,
  subtitle,
  accent,
  plan,
  enabledModules,
  children,
}: Omit<HomeProps, 'puedeCobrar'> & {
  title: string
  subtitle: string
  accent: string
  children: ReactNode
}) {
  // Los widgets llegan como hijos; se reparten aquí para que cada home siga
  // siendo una lista legible de tarjetas y no una tabla de datos.
  const hijos = Children.toArray(children)
  const widgets = hijos.filter(esWidget)
  const otros = hijos.filter((h) => !esWidget(h))
  const { visibles, ocultos } = separarWidgets(
    widgets.map((w) => ({ module: w.props.module, title: w.props.title, nodo: w })),
    plan,
    enabledModules,
  )
  return (
    <div style={{ padding: '2rem', maxWidth: 1200, margin: '0 auto' }}>
      <header style={{ marginBottom: 24 }}>
        {/* … header sin cambios … */}
      </header>
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
        gap: 16,
      }}>
        {visibles.map((w) => w.nodo)}
        {otros}
        {plan && ocultos.length > 0 && <TarjetaPlan plan={plan} ocultos={ocultos.map((w) => w.title)} />}
      </div>
    </div>
  )
}
```

(El bloque `<header>` queda exactamente como está hoy; solo cambia la rejilla.) `Widget` recibe `module` en sus props y no lo usa (lo lee `HomeShell`): `function Widget({ icon, title, description, cta, ctaUrl, beta }: WidgetProps)` se queda igual.

Cada home que usa `HomeShell` pasa `plan` y `enabledModules` y declara `module` en sus widgets:

```tsx
function BarberHome({ greeting, orgName, puedeCobrar, plan, enabledModules }: HomeProps) {
  return (
    <HomeShell greeting={greeting} orgName={orgName} plan={plan} enabledModules={enabledModules}
      title="Atlas One Barber" subtitle="Agenda de cortes, paquetes prepagados y comisiones del equipo." accent="#0891b2">
      <Widget module="appointments" icon="fa-calendar" title="Agenda de hoy" description="Cortes y barbas agendadas, sillas disponibles." cta="Abrir agenda" ctaUrl="/appointments" beta />
      <Widget module="memberships" icon="fa-id-card" title="Paquetes prepagados" description="Bonos de N cortes y vencimientos próximos." cta="Ver paquetes" ctaUrl="/memberships" beta />
      <Widget module="commissions" icon="fa-percent" title="Comisiones del turno" description="Resumen por barbero al cierre del día." cta="Ver comisiones" ctaUrl="/commissions" beta />
      <Widget module="crm" icon="fa-address-book" title="Clientes recurrentes" description="Historial de cortes y preferencias." cta="Ver clientes" ctaUrl="/customers" />
      {puedeCobrar && <Widget module="pos" icon="fa-cash-register" title="Cobrar" description="Cobrar servicio o paquete en silla." cta="Ir al POS" ctaUrl="/pos" />}
      <Widget module="reports" icon="fa-chart-pie" title="Reportes" description="Ingreso por barbero, servicios top." cta="Ver reportes" ctaUrl="/reports" />
    </HomeShell>
  )
}
```

Mapa de `module` para los demás homes (misma edición, mismos textos de hoy):

| Home | Widget → module |
|---|---|
| BeautyWellness | Citas → `appointments`; Membresías → `memberships`; Comisiones → `commissions`; Clientes → `crm`; Vender → `pos`; Reportes → `reports` |
| Health | Consultas → `appointments`; Pacientes → `crm`; Planes → `memberships`; Comisiones → `commissions`; Cobrar → `pos`; Reportes → `reports` |
| Retail | Inventario → `inventory`; Compras → `purchasing`; Sucursales → (sin module); Promociones → `promotions`; Cotizaciones → `quotes`; Reportes → `reports` |
| Services | Órdenes de trabajo → `quotes`; Agenda → `appointments`; Cotizaciones → `quotes`; Comisiones → `commissions`; Clientes → `crm`; Reportes → `reports` |
| Enterprise | Control Tower → (sin module); Copiloto IA → `ai`; Compras → `purchasing`; Manufactura → `inventory`; RRHH → `hr`; Reportes ejecutivos → `reports` |

Los tres homes gastro (`RestaurantHome`, `CafeHome`, `BarHome`) reciben `HomeProps` completo pero siguen pasando solo lo que `GastroHomeDay` acepta: sin cambios en su JSX.

- [ ] **Step 8: Correr y ver que pasa; typecheck**

Run: `cd frontend && npx vitest run src/pages/home && npx tsc --noEmit`
Expected: PASS (widgetsPorPlan 6, PresetHome 5); tsc limpio.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/pages/home/widgetsPorPlan.ts frontend/src/pages/home/PresetHome.tsx frontend/src/pages/home/__tests__/widgetsPorPlan.test.ts frontend/src/pages/home/__tests__/PresetHome.test.tsx
git commit -m "feat(inicio): en FREE los widgets fuera de plan se resumen en una sola tarjeta"
```

---

### Task 6: Presupuesto de la ruta crítica — `scripts/presupuesto_bundle.py` + `frontend/presupuesto_bundle.json`

**Files:**
- Create: `scripts/presupuesto_bundle.py`
- Create: `frontend/presupuesto_bundle.json`
- Test: `tests/test_presupuesto_bundle.py`

**Interfaces:**
- Consumes: `frontend/dist/index.html` (entrada `<script type="module" src>` y `<link rel="modulepreload" href>`), `frontend/dist/assets/POS-*.js`.
- Produces: `medir(dist: Path) -> Medicion` (`.archivos: list[tuple[str, int]]`, `.precargados: list[str]`, `.total: int`); `evaluar(m: Medicion, presupuesto: dict) -> list[str]`; `main(argv=None) -> int` (0 pasa, 1 falla). JSON con `tope_bytes: int`, `prohibidos_en_precarga: list[str]`, `medicion_base: {fecha, bytes, commit}`. Lo usan las Tareas 7, 8 y 9.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
# tests/test_presupuesto_bundle.py
"""scripts/presupuesto_bundle.py: mide la ruta crítica del frontend y falla al pasarse."""
import json
from pathlib import Path

import pytest

from scripts import presupuesto_bundle as pb


def _dist(tmp_path: Path, precarga=("vendor-abc.js", "store-def.js"), pos=True) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    links = "".join(f'<link rel="modulepreload" crossorigin href="/assets/{p}">' for p in precarga)
    (dist / "index.html").write_text(
        "<!doctype html><html><head>"
        '<script type="module" crossorigin src="/assets/index-xyz.js"></script>'
        f'{links}<link rel="stylesheet" crossorigin href="/assets/index-q.css">'
        "</head><body></body></html>",
        encoding="utf-8",
    )
    (dist / "assets" / "index-xyz.js").write_bytes(b"x" * 1000)
    for p in precarga:
        (dist / "assets" / p).write_bytes(b"y" * 500)
    if pos:
        (dist / "assets" / "POS-123.js").write_bytes(b"z" * 300)
    (dist / "assets" / "Reportes-999.js").write_bytes(b"w" * 9000)  # lazy: no cuenta
    (dist / "assets" / "index-q.css").write_bytes(b"c" * 700)       # CSS: no cuenta
    return dist


def _presupuesto(tmp_path: Path, tope=2300, prohibidos=("charts-",)) -> Path:
    f = tmp_path / "presupuesto_bundle.json"
    f.write_text(json.dumps({"tope_bytes": tope, "prohibidos_en_precarga": list(prohibidos)}), encoding="utf-8")
    return f


def test_suma_entrada_precarga_y_pos(tmp_path):
    m = pb.medir(_dist(tmp_path))
    assert dict(m.archivos) == {
        "assets/index-xyz.js": 1000, "assets/vendor-abc.js": 500,
        "assets/store-def.js": 500, "assets/POS-123.js": 300,
    }
    assert m.total == 2300
    assert m.precargados == ["assets/vendor-abc.js", "assets/store-def.js"]


def test_pasa_en_el_tope_exacto(tmp_path):
    assert pb.main(["--dist", str(_dist(tmp_path)), "--presupuesto", str(_presupuesto(tmp_path))]) == 0


def test_falla_un_byte_arriba(tmp_path, capsys):
    pres = _presupuesto(tmp_path, tope=2299, prohibidos=())
    assert pb.main(["--dist", str(_dist(tmp_path)), "--presupuesto", str(pres)]) == 1
    assert "> tope" in capsys.readouterr().err


def test_falla_si_precarga_un_prefijo_prohibido(tmp_path, capsys):
    dist = _dist(tmp_path, precarga=("vendor-abc.js", "charts-777.js"))
    pres = _presupuesto(tmp_path, tope=10_000, prohibidos=("charts-",))
    assert pb.main(["--dist", str(dist), "--presupuesto", str(pres)]) == 1
    assert "charts-" in capsys.readouterr().err


def test_sin_precarga_ni_pos_mide_lo_que_hay(tmp_path):
    m = pb.medir(_dist(tmp_path, precarga=(), pos=False))
    assert m.total == 1000


def test_archivo_referenciado_que_no_existe_es_error_claro(tmp_path):
    dist = _dist(tmp_path)
    (dist / "assets" / "vendor-abc.js").unlink()
    with pytest.raises(SystemExit, match="vendor-abc.js"):
        pb.medir(dist)


def test_index_sin_entrada_es_error_claro(tmp_path):
    dist = _dist(tmp_path)
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")
    with pytest.raises(SystemExit, match="entrada"):
        pb.medir(dist)


def test_el_presupuesto_del_repo_es_valido():
    datos = json.loads(Path("frontend/presupuesto_bundle.json").read_text(encoding="utf-8"))
    assert isinstance(datos["tope_bytes"], int) and datos["tope_bytes"] > 0
    assert all(isinstance(p, str) for p in datos["prohibidos_en_precarga"])
```

- [ ] **Step 2: Correr y ver que falla**

Run: `.venv/bin/python -m pytest -q -p no:warnings tests/test_presupuesto_bundle.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.presupuesto_bundle'`.

- [ ] **Step 3: Escribir el script**

```python
#!/usr/bin/env python3
"""Presupuesto de descarga de la ruta crítica del frontend (login → POS).

Lee `frontend/dist/` después de `vite build` y suma, en bytes sin comprimir,
lo que el navegador baja antes de poder cobrar:

  * el módulo de entrada (`<script type="module" src="/assets/index-*.js">`)
    y todo lo que `index.html` precarga con `<link rel="modulepreload">`;
  * `assets/POS-*.js`, la pantalla de cobro.

Falla (código 1) si la suma supera `tope_bytes` de
`frontend/presupuesto_bundle.json`, o si alguno de los prefijos de
`prohibidos_en_precarga` aparece entre los precargados (chart.js no debe
viajar con el login). Solo biblioteca estándar: en CI corre en el job de
frontend, que no instala requirements.txt.

Uso:
    python3 scripts/presupuesto_bundle.py [--dist frontend/dist]
                                          [--presupuesto frontend/presupuesto_bundle.json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

RE_ENTRADA = re.compile(r'<script[^>]+type="module"[^>]+src="/?([^"]+\.js)"')
RE_PRECARGA = re.compile(r'<link[^>]+rel="modulepreload"[^>]+href="/?([^"]+\.js)"')


@dataclass
class Medicion:
    archivos: List[Tuple[str, int]] = field(default_factory=list)
    precargados: List[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(b for _, b in self.archivos)


def medir(dist: Path) -> Medicion:
    html = (dist / "index.html").read_text(encoding="utf-8")
    entrada = RE_ENTRADA.findall(html)
    precarga = RE_PRECARGA.findall(html)
    if not entrada:
        raise SystemExit(f"{dist / 'index.html'}: no encontré el <script type=\"module\"> de entrada")
    rutas = list(dict.fromkeys(entrada + precarga))  # sin duplicados, en orden de aparición
    rutas += sorted(p.relative_to(dist).as_posix() for p in (dist / "assets").glob("POS-*.js"))
    m = Medicion(precargados=precarga)
    for r in rutas:
        f = dist / r
        if not f.exists():
            raise SystemExit(f"{f}: index.html lo referencia pero no existe en dist/")
        m.archivos.append((r, f.stat().st_size))
    return m


def evaluar(m: Medicion, presupuesto: dict) -> List[str]:
    """Violaciones del presupuesto; lista vacía = pasa."""
    errores: List[str] = []
    tope = int(presupuesto["tope_bytes"])
    if m.total > tope:
        errores.append(f"ruta crítica = {m.total:,} B > tope {tope:,} B (+{m.total - tope:,} B)")
    for prefijo in presupuesto.get("prohibidos_en_precarga", []):
        for ruta in m.precargados:
            if Path(ruta).name.startswith(prefijo):
                errores.append(f"{ruta} se precarga desde index.html; '{prefijo}' no va en la ruta crítica")
    return errores


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dist", type=Path, default=Path("frontend/dist"))
    ap.add_argument("--presupuesto", type=Path, default=Path("frontend/presupuesto_bundle.json"))
    args = ap.parse_args(argv)
    presupuesto = json.loads(args.presupuesto.read_text(encoding="utf-8"))
    m = medir(args.dist)
    for ruta, b in m.archivos:
        print(f"{b:>10,} B  {ruta}")
    print(f"{m.total:>10,} B  TOTAL ruta crítica (tope {int(presupuesto['tope_bytes']):,} B)")
    errores = evaluar(m, presupuesto)
    for e in errores:
        print(f"ERROR: {e}", file=sys.stderr)
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Medir el estado actual y fijar el tope**

```bash
cd frontend && npm run build && cd ..
python3 scripts/presupuesto_bundle.py --dist frontend/dist --presupuesto /dev/stdin <<< '{"tope_bytes": 999999999, "prohibidos_en_precarga": []}'
```

Leer la línea `TOTAL ruta crítica` (referencia del dist del 2026-10-03: 627,678 B; hoy `charts-*.js` aparece entre los precargados — es el hallazgo que corrige la Tarea 7). Escribir `frontend/presupuesto_bundle.json` con `tope_bytes = int(TOTAL * 0.95)`:

```json
{
  "_comentario": "Bytes sin comprimir de la ruta crítica login → POS: entrada + <link rel=modulepreload> + assets/POS-*.js. Lo mide scripts/presupuesto_bundle.py (CI, job frontend-build). Tope inicial = medición × 0.95; se baja al cerrar cada tarea de carga del plan SP2. Si una función nueva lo rebasa, primero se discute qué entra a la ruta crítica, no se sube el número.",
  "tope_bytes": 596294,
  "prohibidos_en_precarga": [],
  "medicion_base": { "fecha": "2026-10-15", "bytes": 627678, "commit": "<sha corto de HEAD>" }
}
```

(Sustituir `596294`, `627678`, fecha y commit por los valores reales de la medición.)

- [ ] **Step 5: Correr y ver que pasa**

Run: `.venv/bin/python -m pytest -q -p no:warnings tests/test_presupuesto_bundle.py`
Expected: 8 passed.

Run: `python3 scripts/presupuesto_bundle.py`
Expected: salida con la lista y `ERROR: ruta crítica = … > tope …` con código 1 (el tope es 5 % menor que lo medido: lo cierran las Tareas 7 y 8; por eso el paso de CI entra hasta la Tarea 9).

- [ ] **Step 6: Commit**

```bash
git add scripts/presupuesto_bundle.py frontend/presupuesto_bundle.json tests/test_presupuesto_bundle.py
git commit -m "feat(ci): script de presupuesto de descarga de la ruta crítica login → POS"
```

---

### Task 7: Carga — `react/jsx-runtime` fuera de `charts`, auditoría del chunk de entrada y `lazy()` de lo no crítico

**Files:**
- Modify: `frontend/vite.config.ts`
- Modify: `frontend/package.json` (+ `rollup-plugin-visualizer` en devDependencies)
- Modify: `frontend/src/App.tsx` (`MobileLayout`, `NotFoundPage` y los 5 mayores no críticos que salgan de la medición)
- Modify: `frontend/presupuesto_bundle.json` (bajar `tope_bytes`, añadir `"charts-"` a prohibidos)
- Test: `frontend/src/__tests__/rutasPerezosas.test.ts`

**Interfaces:**
- Consumes: `scripts/presupuesto_bundle.py` (Tarea 6); `PageLoader` y `PrivateRoute` ya definidos en `App.tsx`.
- Produces: `vendor` contiene `react/jsx-runtime`; variable de entorno `ANALIZAR=1` genera `dist/stats.html` (treemap) y `dist/stats.json` (raw-data); `MobileLayout` y `NotFoundPage` cargados con `lazy()`.

- [ ] **Step 1: Prueba de que lo movido a lazy sigue resolviendo (falla por ahora en la lista, pasa en cuanto se agregue el módulo)**

```ts
// frontend/src/__tests__/rutasPerezosas.test.ts
// @vitest-environment jsdom
import { describe, it, expect } from 'vitest'

// Cada módulo que App.tsx carga con lazy() tiene que seguir resolviendo: un
// import roto no lo ve tsc (la ruta es un string) y en producción se
// manifiesta como un "Cargando..." eterno. Aquí se importa igual que lo hace
// App.tsx y se comprueba que exporta el componente con ese nombre.
const PEREZOSOS: Record<string, () => Promise<Record<string, unknown>>> = {
  MobileLayout: () => import('../components/layout/MobileLayout'),
  NotFoundPage: () => import('../pages/NotFound'),
  // Añadir aquí cada módulo que salga del chunk de entrada en esta tarea.
}

describe('módulos movidos a lazy() en SP2', () => {
  for (const [nombre, cargar] of Object.entries(PEREZOSOS)) {
    it(`${nombre} resuelve y exporta un componente`, async () => {
      const m = await cargar()
      expect(typeof m[nombre]).toBe('function')
    })
  }
})
```

Run: `cd frontend && npx vitest run src/__tests__/rutasPerezosas.test.ts`
Expected: PASS (2) — la prueba pinta la lista; cada módulo que se mueva a lazy en los pasos siguientes se añade aquí y se vuelve a correr.

- [ ] **Step 2: `react/jsx-runtime` a `vendor` y el visualizador bajo `ANALIZAR=1`**

```bash
cd frontend && npm install --save-dev rollup-plugin-visualizer@^5.12.0
```

`frontend/vite.config.ts`:

```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { visualizer } from 'rollup-plugin-visualizer'

// `ANALIZAR=1 npm run build` deja dist/stats.html (treemap) y dist/stats.json
// (datos crudos) para auditar qué entra a cada chunk. No se activa en CI.
const analizar = process.env.ANALIZAR === '1'

export default defineConfig({
  plugins: [
    react(),
    ...(analizar
      ? [
          visualizer({ filename: 'dist/stats.html', template: 'treemap', gzipSize: true }),
          visualizer({ filename: 'dist/stats.json', template: 'raw-data' }),
        ]
      : []),
  ],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/static': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    minify: 'esbuild',
    rollupOptions: {
      output: {
        manualChunks: {
          // `react/jsx-runtime` va explícito: la forma objeto de manualChunks
          // mete en un chunk el paquete Y sus dependencias que no estén en otro
          // manual chunk. react-chartjs-2 importa jsx-runtime, así que sin esta
          // línea jsx-runtime caía en `charts` y TODOS los componentes importaban
          // `jsx` desde ahí: chart.js (184 KB) viajaba con el login.
          vendor: ['react', 'react-dom', 'react-router-dom', 'react/jsx-runtime'],
          charts: ['chart.js', 'react-chartjs-2'],
          store: ['zustand', 'axios'],
        },
      },
    },
  },
})
```

Comprobar:

```bash
cd frontend && npm run build
grep -c 'charts-' dist/index.html            # esperado: 0 (ya no se precarga)
grep -l 'from"./charts-' dist/assets/*.js | wc -l   # esperado: solo los chunks que grafican (~6-8), no ~100
cd .. && python3 scripts/presupuesto_bundle.py      # esperado: TOTAL ≈ medición base − 184 KB
```

- [ ] **Step 3: Auditar el chunk de entrada**

```bash
cd frontend && ANALIZAR=1 npm run build
```

Abrir `frontend/dist/stats.html` en el navegador para la vista de árbol, y para una lista ordenada desde la terminal guardar esto en `/tmp/claude-1000/-mnt-d-Devs-atlas-one/88dd20d9-ffe0-4c18-b01a-da7647838260/scratchpad/leer_stats.py` (no se versiona):

```python
"""Lista los módulos de un chunk por tamaño renderizado, leyendo dist/stats.json (raw-data)."""
import json
import sys
from pathlib import Path

datos = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
prefijo = sys.argv[2]            # p. ej. "index-" (entrada) o "POS-"
partes = datos["nodeParts"]      # uid → {renderedLength, gzipLength, ...}


def hojas(nodo, ruta=""):
    r = f"{ruta}/{nodo['name']}" if ruta else nodo["name"]
    if "uid" in nodo:
        yield r, nodo["uid"]
    for hijo in nodo.get("children", []):
        yield from hojas(hijo, r)


for chunk in datos["tree"]["children"]:
    if not chunk["name"].split("/")[-1].startswith(prefijo):
        continue
    filas = [(partes[uid]["renderedLength"], ruta) for ruta, uid in hojas(chunk) if uid in partes]
    filas.sort(reverse=True)
    print(f"== {chunk['name']}: {sum(b for b, _ in filas):,} B en {len(filas)} módulos")
    for b, ruta in filas[:40]:
        print(f"{b:>9,}  {ruta}")
```

```bash
python3 -I /tmp/claude-1000/-mnt-d-Devs-atlas-one/88dd20d9-ffe0-4c18-b01a-da7647838260/scratchpad/leer_stats.py frontend/dist/stats.json index-
```

(Si `stats.json` no trae `tree`/`nodeParts`, imprimir `list(datos)` y ajustar las dos claves: el formato `raw-data` de la 5.x las llama así.)

Cómo leer el resultado: en el chunk de entrada **es crítico** lo que necesita el login y el armazón: `src/main.tsx`, `src/App.tsx`, `pages/Login.tsx`, `components/layout/{Layout,Sidebar,BranchSwitcher,*Banner}.tsx`, `components/ui/{Toast,ConfirmDialog,Spinner}.tsx`, `store/*`, `api/client.ts`, `context/ThemeContext`, `components/atlas-one/AtlasMark.tsx`. **No es crítico** cualquier `src/pages/**` que no sea Login, cualquier `src/components/**` que solo use una página, `components/atlas-one/*` distinto de `AtlasMark` (señal de que el barrel `components/atlas-one/index.ts` arrastró el kit: cambiar `import { AtlasMark } from '../components/atlas-one'` por `'../components/atlas-one/AtlasMark'` en `pages/Login.tsx` y `components/layout/MobileLayout.tsx`), y cualquier `node_modules/*` que no sea react/react-dom/react-router/zustand/axios (p. ej. `@zxing/*`, `chart.js`). Anotar los **5 mayores no críticos** (nombre y bytes) en el cuerpo del commit.

- [ ] **Step 4: `MobileLayout` y `NotFoundPage` a lazy (siempre), y los 5 mayores medidos**

En `frontend/src/App.tsx` quitar las líneas 14 y 17:

```ts
import { MobileLayout } from './components/layout/MobileLayout'
import { NotFoundPage } from './pages/NotFound'
```

y, junto a los demás `lazy(...)`:

```ts
// Armazón móvil y 404: no son parte de login → POS.
const MobileLayout = lazy(() => import('./components/layout/MobileLayout').then(m => ({ default: m.MobileLayout })))
const NotFoundPage = lazy(() => import('./pages/NotFound').then(m => ({ default: m.NotFoundPage })))
```

Las dos rutas que montan `<MobileLayout />` (`path="/mobile"` y `path="/portal"`) quedan:

```tsx
          element={
            <PrivateRoute>
              <Suspense fallback={<PageLoader />}><MobileLayout /></Suspense>
            </PrivateRoute>
          }
```

y la 404:

```tsx
          <Route path="*" element={<Suspense fallback={<PageLoader />}><NotFoundPage /></Suspense>} />
```

Para cada uno de los 5 mayores no críticos de la medición: si es una página o componente importado estático en `App.tsx`, `Layout.tsx` o `Sidebar.tsx`, aplicar el mismo patrón (`const X = lazy(() => import('<ruta>').then(m => ({ default: m.X })))` + `<Suspense fallback={<PageLoader />}>` en el punto de uso) y añadir `X: () => import('<ruta>')` a `PEREZOSOS` en `rutasPerezosas.test.ts`; si es un paquete de `node_modules` que llega por un import estático, mover ese import al módulo que lo usa de verdad (import dinámico `await import('@zxing/browser')` dentro del handler que lo necesita) y anotarlo en el commit. Si algún candidato resulta ser compartido por Login o el armazón, no se mueve: se anota por qué.

- [ ] **Step 5: Verificar, bajar el tope y prohibir `charts-` en la precarga**

```bash
cd frontend && npx vitest run src/__tests__/rutasPerezosas.test.ts && npx tsc --noEmit && npm run build && cd ..
python3 scripts/presupuesto_bundle.py
```

Con el TOTAL nuevo, editar `frontend/presupuesto_bundle.json`: `tope_bytes = int(TOTAL_nuevo * 0.95)` y `"prohibidos_en_precarga": ["charts-"]`. Volver a correr `python3 scripts/presupuesto_bundle.py` → código 1 esperado (el 5 % restante lo cierra la Tarea 8; si la Tarea 8 no alcanzara, el cierre se anota y el tope se deja en el TOTAL real al entrar a la Tarea 9 — el presupuesto es un techo que no sube, no una meta ideal).

Run: `.venv/bin/python -m pytest -q -p no:warnings tests/test_presupuesto_bundle.py`
Expected: 8 passed.

- [ ] **Step 6: Commit**

```bash
git add frontend/vite.config.ts frontend/package.json frontend/package-lock.json frontend/src/App.tsx frontend/src/__tests__/rutasPerezosas.test.ts frontend/presupuesto_bundle.json
git commit -F - <<'EOF'
perf(carga): jsx-runtime a vendor (chart.js ya no viaja con el login) y lazy de lo no crítico

Medición (scripts/presupuesto_bundle.py): antes <N> B, después <M> B.
Chunk de entrada, 5 mayores no críticos movidos: <lista nombre — bytes>.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf
EOF
```

---

### Task 8: Una sola librería de gráficas — plataforma de recharts a chart.js

**Files:**
- Create: `frontend/src/utils/cssToken.ts`
- Modify: `frontend/src/components/platform/v2/TrendChart.tsx`
- Modify: `frontend/src/pages/platform/PlatformMetrics.tsx:1-8, 168-176, 495-530`
- Modify: `frontend/src/pages/platform/PlatformReports.tsx:1-8, 531-593, 702, 774, 844, 914`
- Modify: `frontend/package.json` (quitar `recharts`)
- Modify: `frontend/presupuesto_bundle.json` (bajar el tope si la medición bajó)
- Test: `frontend/src/utils/__tests__/cssToken.test.ts`
- Test: `frontend/src/components/platform/v2/__tests__/TrendChart.test.tsx`
- Test: `frontend/src/__tests__/sinRecharts.test.ts`

**Interfaces:**
- Consumes: `chart.js` (`Chart`, escalas y elementos), `react-chartjs-2` (`Line`, `Bar`, `Doughnut`), `formatCurrency` (`utils/currency`).
- Produces: `token(nombre: string, respaldo: string): string` (resuelve `--p-*` desde `:root`; `respaldo` fuera del navegador o si está vacío); `conAlpha(color: string, alpha: number): string` (`#rrggbb` → `rgba(...)`; otros formatos se devuelven igual); `TrendChart` con las mismas props de hoy; `TopChart` sin la prop `dataKey`.

- [ ] **Step 1: Pruebas de `cssToken` (fallan)**

```ts
// frontend/src/utils/__tests__/cssToken.test.ts
import { describe, it, expect } from 'vitest'
import { conAlpha, token } from '../cssToken'

describe('token', () => {
  it('fuera del navegador devuelve el respaldo (chart.js no entiende var())', () => {
    expect(token('--p-accent', '#6366f1')).toBe('#6366f1')
  })
})

describe('conAlpha', () => {
  it('convierte #rrggbb a rgba', () => {
    expect(conAlpha('#6366f1', 0.2)).toBe('rgba(99, 102, 241, 0.2)')
  })
  it('deja pasar lo que no es hex de 6', () => {
    expect(conAlpha('rgb(1, 2, 3)', 0.5)).toBe('rgb(1, 2, 3)')
    expect(conAlpha('#fff', 0.5)).toBe('#fff')
  })
})
```

Run: `cd frontend && npx vitest run src/utils/__tests__/cssToken.test.ts`
Expected: FAIL — `Cannot find module '../cssToken'`.

- [ ] **Step 2: `cssToken.ts`**

```ts
// frontend/src/utils/cssToken.ts
/**
 * chart.js pinta en <canvas>: un color `var(--p-accent)` no se resuelve y la
 * serie sale negra o invisible. Estas dos funciones traducen los tokens del
 * tema a colores concretos en el momento de pintar.
 */
export function token(nombre: string, respaldo: string): string {
  if (typeof document === 'undefined') return respaldo
  return getComputedStyle(document.documentElement).getPropertyValue(nombre).trim() || respaldo
}

/** `#rrggbb` → `rgba(r, g, b, alpha)`; cualquier otro formato se devuelve tal cual. */
export function conAlpha(color: string, alpha: number): string {
  const m = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(color)
  if (!m) return color
  const [r, g, b] = [m[1], m[2], m[3]].map((h) => parseInt(h, 16))
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}
```

Run: `cd frontend && npx vitest run src/utils/__tests__/cssToken.test.ts` → 3 passed.

- [ ] **Step 3: Prueba de `TrendChart` con chart.js (falla)**

```tsx
// frontend/src/components/platform/v2/__tests__/TrendChart.test.tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, cleanup, fireEvent } from '@testing-library/react'

// jsdom no tiene canvas: se sustituye <Line> por un stub que expone las series
// recibidas. Lo que se prueba es qué datos construye TrendChart, no el dibujo.
vi.mock('react-chartjs-2', () => ({
  Line: (props: { data: { datasets: { label?: string }[] } }) => (
    <div data-testid="line" data-series={props.data.datasets.map((d) => d.label).join('|')} />
  ),
}))

import { TrendChart, type TrendPoint } from '../TrendChart'

const puntos: TrendPoint[] = [
  { date: '2026-10-01', label: '01', revenue: 100, ma7: 90, sales: 3 },
  { date: '2026-10-02', label: '02', revenue: 150, ma7: 110, sales: 5 },
]

afterEach(cleanup)

describe('TrendChart (chart.js)', () => {
  it('sin datos muestra el aviso y no pinta gráfica', () => {
    render(<TrendChart data={[]} />)
    expect(screen.getByText('Sin datos de tendencia.')).toBeTruthy()
    expect(screen.queryByTestId('line')).toBeNull()
  })

  it('por defecto pinta ventas diarias y promedio móvil 7d', () => {
    render(<TrendChart data={puntos} />)
    expect(screen.getByTestId('line').getAttribute('data-series')).toBe('Ventas diarias|Promedio móvil 7d')
  })

  it('con toggles, activar "Sales" agrega la serie de tickets', () => {
    render(<TrendChart data={puntos} salesSeries={puntos} showSeriesToggles />)
    fireEvent.click(screen.getByRole('button', { name: 'Sales' }))
    expect(screen.getByTestId('line').getAttribute('data-series')).toBe('Ventas diarias|Promedio móvil 7d|Tickets')
  })

  it('apagar "Revenue" deja solo lo demás', () => {
    render(<TrendChart data={puntos} salesSeries={puntos} showSeriesToggles />)
    fireEvent.click(screen.getByRole('button', { name: 'Revenue' }))
    fireEvent.click(screen.getByRole('button', { name: 'Sales' }))
    expect(screen.getByTestId('line').getAttribute('data-series')).toBe('Tickets')
  })
})
```

Run: `cd frontend && npx vitest run src/components/platform/v2/__tests__/TrendChart.test.tsx`
Expected: FAIL — el componente actual importa `recharts` (no `react-chartjs-2`), así que no hay `data-testid="line"`.

- [ ] **Step 4: Reescribir `TrendChart.tsx` con chart.js**

```tsx
// frontend/src/components/platform/v2/TrendChart.tsx
import { useMemo, useState } from 'react'
import {
  Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement, Filler, Tooltip,
  type ChartData, type ChartOptions,
} from 'chart.js'
import { Line } from 'react-chartjs-2'
import { formatCurrency } from '../../../utils/currency'
import { conAlpha, token } from '../../../utils/cssToken'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Filler, Tooltip)

export interface TrendPoint {
  date: string
  label: string
  revenue: number
  ma7?: number | null
  sales?: number
  signups?: number
}

interface Props {
  data: TrendPoint[]
  height?: number
  showGrid?: boolean
  showLegend?: boolean
  /** Optional secondary series (sales count). When provided + toggled on, renders a second line. */
  salesSeries?: TrendPoint[]
  /** Optional tertiary series (signups count). When provided + toggled on, renders a third line. */
  signupsSeries?: TrendPoint[]
  /** When true, render 3 toggle pills above the chart (Revenue / Sales / Signups). Default false. */
  showSeriesToggles?: boolean
}

function chartCurrencyShort(value: number): string {
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `$${(value / 1_000).toFixed(1)}k`
  return `$${value.toFixed(0)}`
}

function intShort(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`
  return `${value.toFixed(0)}`
}

export function TrendChart({
  data,
  height = 300,
  showGrid = true,
  showLegend = true,
  salesSeries,
  signupsSeries,
  showSeriesToggles = false,
}: Props) {
  const [revOn, setRevOn] = useState(true)
  const [salesOn, setSalesOn] = useState(false)
  const [signupsOn, setSignupsOn] = useState(false)

  // Las series opcionales se funden por índice, igual que antes con recharts.
  const merged = useMemo(() => {
    if (!data || data.length === 0) return []
    return data.map((p, i) => ({
      ...p,
      sales: salesSeries?.[i]?.revenue ?? salesSeries?.[i]?.sales ?? p.sales ?? 0,
      signups: signupsSeries?.[i]?.revenue ?? signupsSeries?.[i]?.signups ?? p.signups ?? 0,
    }))
  }, [data, salesSeries, signupsSeries])

  const hasSales = !!salesSeries && salesSeries.length > 0
  const hasSignups = !!signupsSeries && signupsSeries.length > 0
  const ejeDerecho = (hasSales && salesOn) || (hasSignups && signupsOn)

  const chartData = useMemo<ChartData<'line'>>(() => {
    const acento = token('--p-accent', '#6366f1')
    const muted = token('--p-muted', '#94a3b8')
    const datasets: ChartData<'line'>['datasets'] = []
    if (revOn) {
      datasets.push({
        label: 'Ventas diarias', yAxisID: 'y',
        data: merged.map((p) => p.revenue),
        borderColor: acento, borderWidth: 1.75, pointRadius: 0, tension: 0.35,
        fill: true, backgroundColor: conAlpha(acento, 0.18),
      })
      datasets.push({
        label: 'Promedio móvil 7d', yAxisID: 'y',
        data: merged.map((p) => p.ma7 ?? null),
        borderColor: muted, borderWidth: 1.25, borderDash: [3, 3], pointRadius: 0, tension: 0.35,
        spanGaps: true,
      })
    }
    if (hasSales && salesOn) {
      datasets.push({
        label: 'Tickets', yAxisID: 'y2',
        data: merged.map((p) => p.sales ?? 0),
        borderColor: token('--p-success', '#4ade80'), borderWidth: 1.5, pointRadius: 0, tension: 0.35,
      })
    }
    if (hasSignups && signupsOn) {
      datasets.push({
        label: 'Signups', yAxisID: 'y2',
        data: merged.map((p) => p.signups ?? 0),
        borderColor: token('--p-warning', '#fbbf24'), borderWidth: 1.5, pointRadius: 0, tension: 0.35,
      })
    }
    return { labels: merged.map((p) => p.label), datasets }
  }, [merged, revOn, salesOn, signupsOn, hasSales, hasSignups])

  const options = useMemo<ChartOptions<'line'>>(() => {
    const hint = token('--p-hint', '#64748b')
    const borde = token('--p-border', '#1f2937')
    const mono = token('--font-mono', 'ui-monospace, monospace')
    return {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: token('--p-sidebar', '#0f172a'),
          borderColor: borde, borderWidth: 1,
          titleColor: token('--p-text', '#e2e8f0'), bodyColor: token('--p-text', '#e2e8f0'),
          callbacks: {
            title: (items) => `Día ${items[0]?.label ?? ''}`,
            label: (ctx) => {
              const v = typeof ctx.parsed.y === 'number' ? ctx.parsed.y : 0
              const esDinero = ctx.dataset.yAxisID === 'y'
              return `${ctx.dataset.label}: ${esDinero ? formatCurrency(v) : v}`
            },
          },
        },
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: hint, font: { size: 10, family: mono }, maxTicksLimit: 12, maxRotation: 0 },
        },
        y: {
          position: 'left',
          grid: { display: showGrid, color: borde, tickBorderDash: [2, 4] },
          border: { display: false },
          ticks: { color: hint, font: { size: 10, family: mono }, callback: (v) => chartCurrencyShort(Number(v)) },
        },
        y2: {
          position: 'right',
          display: ejeDerecho,
          grid: { drawOnChartArea: false },
          border: { display: false },
          ticks: { color: hint, font: { size: 10, family: mono }, callback: (v) => intShort(Number(v)) },
        },
      },
    }
  }, [showGrid, ejeDerecho])

  if (!data || data.length === 0) {
    return (
      <div style={{ height, display: 'grid', placeItems: 'center', color: 'var(--p-muted)', fontSize: 13 }}>
        Sin datos de tendencia.
      </div>
    )
  }

  return (
    <div className="chart-wrap">
      {showSeriesToggles && (
        <div className="series-toggles" role="group" aria-label="Series">
          <button type="button" className={'pill ' + (revOn ? 'active' : '')} aria-pressed={revOn} onClick={() => setRevOn((v) => !v)}>
            Revenue
          </button>
          {hasSales && (
            <button type="button" className={'pill ' + (salesOn ? 'active' : '')} aria-pressed={salesOn} onClick={() => setSalesOn((v) => !v)}>
              Sales
            </button>
          )}
          {hasSignups && (
            <button type="button" className={'pill ' + (signupsOn ? 'active' : '')} aria-pressed={signupsOn} onClick={() => setSignupsOn((v) => !v)}>
              Signups
            </button>
          )}
        </div>
      )}
      {showLegend && (
        <div className="chart-caption">
          <span className="legend-inline">
            <span className="a"><span className="sw" />Ventas diarias</span>
            <span className="b"><span className="sw" />Promedio móvil 7d</span>
          </span>
          <span className="mono">USD</span>
        </div>
      )}
      <div style={{ height, width: '100%' }}>
        <Line data={chartData} options={options} />
      </div>
    </div>
  )
}
```

Run: `cd frontend && npx vitest run src/components/platform/v2/__tests__/TrendChart.test.tsx`
Expected: 4 passed.

- [ ] **Step 5: `PlatformMetrics.tsx` — la dona de métodos de pago**

Imports (líneas 3-5): reemplazar el bloque de `recharts` por:

```ts
import { Chart as ChartJS, ArcElement, Tooltip } from 'chart.js'
import { Doughnut } from 'react-chartjs-2'
import { token } from '../../utils/cssToken'

ChartJS.register(ArcElement, Tooltip)
```

Junto a `METHOD_COLORS` (línea 168), añadir el traductor para canvas (la lista de la leyenda de abajo sigue usando `METHOD_COLORS` como CSS, con `var()` válido):

```ts
/** `var(--p-accent)` sirve como CSS en la leyenda, pero no en canvas: aquí se resuelve. */
function colorMetodo(i: number): string {
  const c = METHOD_COLORS[i % METHOD_COLORS.length]
  return c.startsWith('var(') ? token(c.slice(4, -1), '#6366f1') : c
}
```

El bloque de la gráfica (líneas 502-529, dentro de `<div style={{ width: '100%', height: 280 }}>`) queda:

```tsx
              <div style={{ width: '100%', height: 280 }}>
                <Doughnut
                  data={{
                    labels: paymentMethods.items.map((m) => m.label),
                    datasets: [{
                      data: paymentMethods.items.map((m) => m.revenue),
                      backgroundColor: paymentMethods.items.map((_, i) => colorMetodo(i)),
                      borderColor: token('--p-bg', '#0b0f14'),
                      borderWidth: 2,
                    }],
                  }}
                  options={{
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: '58%',
                    animation: false,
                    plugins: {
                      legend: { display: false },
                      tooltip: {
                        backgroundColor: token('--p-sidebar', '#0f172a'),
                        borderColor: token('--p-border', '#1f2937'), borderWidth: 1,
                        titleColor: token('--p-text', '#e2e8f0'), bodyColor: token('--p-text', '#e2e8f0'),
                        callbacks: { label: (ctx) => `${ctx.label}: ${formatCurrency(typeof ctx.parsed === 'number' ? ctx.parsed : 0)}` },
                      },
                    },
                  }}
                />
              </div>
```

- [ ] **Step 6: `PlatformReports.tsx` — `TopChart` con barras**

Imports (líneas 3-5): reemplazar el bloque de `recharts` por:

```ts
import { Chart as ChartJS, CategoryScale, LinearScale, BarElement, Tooltip } from 'chart.js'
import { Bar } from 'react-chartjs-2'
import { token } from '../../utils/cssToken'

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip)
```

`TopChart` (línea 531) pierde `dataKey` (los datos ya son `{label, value}`):

```tsx
function TopChart({
  title,
  data,
  labelFormatter,
}: {
  title: string
  data: { label: string; value: number }[]
  labelFormatter?: (v: number) => string
}) {
  const fmt = labelFormatter ?? ((v) => v.toLocaleString('es-MX'))
  const hint = token('--p-hint', '#64748b')
  return (
    <div style={{
      background: 'var(--p-surface)',
      border: '1px solid var(--p-border)',
      borderRadius: 14,
      padding: '16px 18px',
    }}>
      <h3 style={{
        fontFamily: 'var(--font-display)',
        fontSize: 14,
        fontWeight: 600,
        margin: '0 0 12px',
        color: 'var(--p-text)',
        letterSpacing: '-0.01em',
      }}>
        {title}
      </h3>
      <div style={{ height: 260 }}>
        <Bar
          data={{
            labels: data.map((d) => d.label),
            datasets: [{ data: data.map((d) => d.value), backgroundColor: token('--p-accent', '#6366f1'), borderRadius: 4 }],
          }}
          options={{
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            plugins: {
              legend: { display: false },
              tooltip: {
                backgroundColor: token('--p-sidebar', '#0f172a'),
                borderColor: token('--p-border', '#1f2937'), borderWidth: 1,
                titleColor: token('--p-text', '#e2e8f0'), bodyColor: token('--p-text', '#e2e8f0'),
                callbacks: { label: (ctx) => fmt(typeof ctx.parsed.y === 'number' ? ctx.parsed.y : 0) },
              },
            },
            scales: {
              x: {
                grid: { display: false },
                ticks: { color: hint, font: { size: 10 }, autoSkip: false, maxRotation: 25, minRotation: 25 },
              },
              y: {
                grid: { color: token('--p-border', '#1f2937'), tickBorderDash: [2, 4] },
                border: { display: false },
                ticks: { color: hint, font: { size: 10 }, callback: (v) => fmt(Number(v)) },
              },
            },
          }}
        />
      </div>
    </div>
  )
}
```

En las cuatro llamadas (líneas 702, 774, 844, 914) quitar ` dataKey="value"`; `tsc` acusa cualquiera que quede.

- [ ] **Step 7: Prueba de que no queda recharts, y quitar el paquete**

```ts
// frontend/src/__tests__/sinRecharts.test.ts
import { describe, it, expect } from 'vitest'

// Una sola librería de gráficas (chart.js). Si alguien vuelve a importar
// recharts, el chunk `CartesianChart` (340 KB) regresa a la plataforma.
const fuentes = import.meta.glob('/src/**/*.{ts,tsx}', { query: '?raw', import: 'default', eager: true }) as Record<string, string>

describe('librería de gráficas única', () => {
  it('ningún archivo de src importa recharts', () => {
    const culpables = Object.entries(fuentes)
      .filter(([ruta]) => !ruta.includes('/__tests__/'))
      .filter(([, src]) => /from ['"]recharts['"]/.test(src))
      .map(([ruta]) => ruta)
    expect(culpables).toEqual([])
  })
})
```

```bash
cd frontend && npm uninstall recharts
grep -rn "recharts" src package.json   # esperado: solo el comentario de sinRecharts.test.ts
```

- [ ] **Step 8: Correr todo, medir y bajar el tope**

```bash
cd frontend && npx vitest run && npx tsc --noEmit && npm run build && cd ..
ls -l frontend/dist/assets | grep -i "CartesianChart"   # esperado: nada
python3 scripts/presupuesto_bundle.py
```

Si el TOTAL bajó respecto a la Tarea 7 (no debería: la plataforma no está en la ruta crítica; lo que baja es `dist/` total y `PlatformMetrics-*/PlatformReports-*`), ajustar `tope_bytes = int(TOTAL * 0.95)`. Si no bajó, dejar el tope donde lo puso la Tarea 7 y, si sigue dando código 1, fijarlo al TOTAL real medido en esta tarea (anotar en el commit que la meta del 5 % extra queda abierta). Anotar también el tamaño total de `dist/assets/*.js` antes y después (`du -cb frontend/dist/assets/*.js | tail -1`).

- [ ] **Step 9: Revisión visual de la plataforma**

`cd frontend && npm run dev`, entrar como SUPERADMIN, abrir `/platform/metrics` (tendencia con los tres toggles y la dona de métodos de pago) y `/platform/reports` (cuatro "Top 10"). Comprobar en tema claro y oscuro que las series tienen color (no negro), que el tooltip muestra moneda, y que el eje derecho aparece solo al activar Sales/Signups.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/utils/cssToken.ts frontend/src/utils/__tests__/cssToken.test.ts frontend/src/components/platform/v2/TrendChart.tsx frontend/src/components/platform/v2/__tests__/TrendChart.test.tsx frontend/src/pages/platform/PlatformMetrics.tsx frontend/src/pages/platform/PlatformReports.tsx frontend/src/__tests__/sinRecharts.test.ts frontend/package.json frontend/package-lock.json frontend/presupuesto_bundle.json
git commit -m "refactor(plataforma): gráficas con chart.js; recharts fuera del bundle"
```

---

### Task 9: Presupuesto en CI (después de `vite build`)

**Files:**
- Modify: `.github/workflows/ci.yml` (job `frontend-build`, tras el paso "Build frontend")

**Interfaces:**
- Consumes: `scripts/presupuesto_bundle.py` y `frontend/presupuesto_bundle.json` (Tareas 6-8) con el tope ya alcanzado (el script devuelve 0 en local).

- [ ] **Step 1: Confirmar que pasa en local antes de tocar CI**

```bash
cd frontend && npm run build && cd .. && python3 scripts/presupuesto_bundle.py; echo "código: $?"
```

Expected: `código: 0`. Si es 1, volver a la Tarea 8 Step 8 (el tope no se sube para que CI pase; se fija al TOTAL medido y se anota).

- [ ] **Step 2: Añadir el paso**

En `.github/workflows/ci.yml`, job `frontend-build`, después de:

```yaml
      - name: Build frontend
        working-directory: frontend
        run: npm run build
```

añadir:

```yaml
      # Ruta crítica login → POS (entrada + modulepreload + POS-*.js) contra
      # frontend/presupuesto_bundle.json. Solo biblioteca estándar: este job no
      # instala requirements.txt y ubuntu-latest trae python3.
      - name: Presupuesto de descarga de la ruta crítica
        run: python3 scripts/presupuesto_bundle.py --dist frontend/dist --presupuesto frontend/presupuesto_bundle.json
```

- [ ] **Step 3: Validar el YAML y la suite completa**

```bash
.venv/bin/python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('yaml ok')"   # PyYAML está en requirements.txt
.venv/bin/python -m pytest -q -p no:warnings --ignore=tests/test_cash_complete.py
cd frontend && npx vitest run && npx tsc --noEmit && npm run build
```

Expected: `yaml ok`; pytest sin fallos nuevos respecto a `main` (comparar el conteo con `git stash` si hay dudas); vitest y tsc verdes; build ok.

- [ ] **Step 4: Commit y push de la rama (no a `main`)**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: falla el build del frontend si la ruta crítica rebasa el presupuesto"
git push -u origin feat/version-ligera-free
gh run list --branch feat/version-ligera-free --limit 3
```

Expected: el run de la rama muestra `frontend-build` verde con el paso nuevo. (El push es de la rama de trabajo; la fusión a `main` sigue requiriendo permiso explícito.)

---

### Task 10: Medición en tienda real (manual) y revisión con la cajera

Sin código. Se hace con el usuario en el equipo de Kaory o Coqueta, **antes** de pedir permiso para fusionar (lectura del "antes") y **después** del despliegue (lectura del "después"). Los dos registros se guardan en el PR.

**Files:**
- Ninguno. Resultado: dos tablas (antes/después) en la descripción del PR.

- [ ] **Step 1: Preparar el equipo y la red del local**

Mismo equipo de caja de siempre, mismo navegador, misma red del local (no el celular del dueño con datos). Cerrar las demás pestañas. En DevTools → Network: marcar **Disable cache**, `throttling: No throttling` (la red real ya es la del local), y activar la columna **Size** y **Time**; en Performance, "Record and reload" no hace falta: con Network basta.

- [ ] **Step 2: Qué medir ("antes" con la versión actual en producción)**

Repetir 3 veces cada ruta y anotar la mediana:

| Medición | Cómo |
|---|---|
| Bytes transferidos hasta POS usable | Network, filtro `JS`+`CSS`, desde `/login` hasta que el buscador del POS acepta texto; leer "transferred" al pie del panel |
| Tiempo a POS usable | Reloj del pie de Network ("Finish") al momento en que el buscador responde al primer tecleo |
| Chunks que bajan en el login | Lista de `assets/*.js` en Network antes de pulsar "Entrar" (anotar si aparece `charts-*.js`) |
| Chunks que bajan al abrir Cobrar | Lo que aparece al navegar a `/pos` (debe ser `POS-*.js` + sus hermanos, no `index-C8jRveWp`/ZXing ni `charts`) |
| Menú de la cajera | Captura de pantalla del cajón lateral y de "Más" |
| Menú de la dueña | Captura del cajón HQ |

- [ ] **Step 3: Después del despliegue**

Misma tabla. Criterio de salida de SP2 (spec §5): −30 % en bytes de la ruta login → POS respecto al "antes"; si queda entre −20 % y −30 %, anotar qué chunk sigue pesando (del `leer_stats.py` de la Tarea 7) y abrir la tarea siguiente en vez de subir el tope.

- [ ] **Step 4: Revisión con la cajera (10 minutos)**

Pedirle que haga su día sin ayuda: abrir caja, cobrar una venta de prueba (y anularla o devolverla), reimprimir, buscar un producto, hacer el corte. Preguntar qué le falta en el menú. Si nombra algo que el perfil FREE escondió (Clientes es el candidato), ese ítem sale de `PERFIL_POR_PLAN.FREE` en un commit de seguimiento antes de fusionar.

- [ ] **Step 5: Cerrar**

Pegar las dos tablas y la nota de la cajera en el PR; pedir permiso explícito al usuario para fusionar a `main` (regla de oro #1). Tras el despliegue (`gh run list` + `.commit_desplegado`), correr `GET /api/users/me/context` con la cuenta de una cajera FREE y confirmar `plan.clave == "FREE"` y el menú corto en pantalla.

---

## Self-review (hecho al cerrar el plan)

- **Cobertura del spec:** backend `plan` ✔ (T1, en las dos respuestas porque el frontend lee `/me/context`); perfil por plan en `visibleNavItems` con fail-open ✔ (T4); los 20 ítems sin `module:` → 7 reciben uno (Reportes HQ, Control, Mi expediente y los 4 móviles con destino; de esos, Control, Mi expediente y los móviles además entran al perfil FREE), 13 siguen sin `module:`: 1 entra al perfil (`/mobile/profile` vía `/mobile/*`) y 12 son la operación diaria/administración y se dejan visibles a propósito ✔ (T4, Global Constraints); `PresetHome` esconde widgets y una sola tarjeta ✔ (T5); una sola librería de gráficas migrando los 3 archivos de plataforma ✔ (T8); auditoría del chunk de entrada y lazy ✔ (T7, con el hallazgo de `jsx-runtime` en `charts`); presupuesto en CI con script propio, tope = medición × 0.95 y pytest con directorio temporal ✔ (T6, T9); medición en tienda y revisión con la cajera ✔ (T10); verificación en prod antes de esconder ítems sin `module:` ✔ (T3, consultas de solo lectura + log de acceso, con tabla de decisión).
- **Placeholders:** los únicos huecos son valores que solo existen al medir (`tope_bytes`, los 5 módulos mayores del chunk de entrada, la fecha/sha del commit) y vienen con el comando que los produce y la regla para fijarlos.
- **Consistencia de tipos:** `PlanOrg` se define en `types/auth.ts` (T2) y lo consumen el store (T2), `navPerfilPlan.ts`/`navVisibility.ts` (T4) y `widgetsPorPlan.ts`/`PresetHome.tsx` (T5); `resumen_plan` (T1) devuelve exactamente `{clave, nombre}`, que es lo que `leerPlan` (T2) exige; `medir`/`evaluar`/`main` (T6) son lo que T7-T9 invocan; `token`/`conAlpha` (T8 Step 2) se usan en T8 Steps 4-6.
- **Review Focus:** las 5 líneas tienen prueba en T2/T4 (1, 2, 3), T5 (4) y T6 (5).
