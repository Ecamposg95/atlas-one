# Modo básico: la app corta para tiendas FREE — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que una organización FREE (Kaory, Coqueta, Imaltzin) vea un menú de 6 entradas (cajera) u 8 (dueña), un POS sin las opciones que nadie usa, un formulario de producto corto y un Inicio que responde "¿cómo voy?", mientras una organización de paga no nota ningún cambio — con la misma base de código y sin apagar nada en el backend.

**Architecture:** Un perfil de interfaz `perfil_ui: "basico" | "completo"` viaja en `GET /api/users/me/context`; lo calcula `app/services/perfil_ui.py::perfil_efectivo(org)` (FREE → básico; `organization.perfil_ui` forzado por la plataforma manda). El frontend lo guarda en `enabledModulesStore` (`perfilUi`, `useModoBasico()`) y lo consulta en cuatro lugares, siempre con render condicional: el menú (`navPerfilBasico.ts`), el POS (`opcionesPorPerfil`), el formulario de producto (los ocultos de `campos_producto(preset, modulos, perfil)`) y dos rutas que cambian de pantalla (`<PorPerfil>`: `/hq/operations` → `InicioBasico`, `/hq/reports-hub` → `Reports`). El backend solo gana dos columnas en `organization` y un endpoint de lectura, `GET /api/reports/inicio-basico`.

**Tech Stack:** FastAPI + SQLAlchemy + Pydantic v2; pytest sobre SQLite (`python3 -m pytest -q -p no:warnings …`; no hay `.venv/` en esta máquina). React 18 + TypeScript 5 + Vite 5 + Tailwind; vitest 2 con `// @vitest-environment jsdom` + `@testing-library/react` (`cd frontend && npx vitest run …`, `npm run build`); presupuesto de la ruta crítica con `python3 scripts/presupuesto_bundle.py --dist frontend/dist --presupuesto frontend/presupuesto_bundle.json`; Playwright 1.63 en el scratchpad para capturas (herramienta de SP5).

**Spec:** `docs/superpowers/specs/2026-10-18-modo-basico-design.md` (aprobado; "seguro iteramos en el proceso"). Planes de referencia: `docs/superpowers/plans/2026-10-15-sp2-version-ligera-free.md` (perfil por plan, plan en el contexto, presupuesto) y `docs/superpowers/plans/2026-10-18-sp5-responsivo-admin-ola-2.md` (Tarea 0 de capturas, kit `ui/`, guardas).

**Rama:** `feat/modo-basico` (worktree `.worktrees/modo-basico`), creada desde `main` 3d3abdf (ya trae SP1 altas, SP2 ligera, SP3 valor de la tienda y SP5 responsivo).

## Decisiones respecto al spec (levantamiento del 2026-10-19 sobre 4bf2574)

1. **Nota del ticket, panel de diagnóstico del agente y asistente de instalación no existen en el POS.** `AgentDiagnosticsPanel` y `PrinterInstallWizard` solo los montan `PrinterSettings.tsx` y `PrinterSettingsCajera.tsx`; el POS no tiene campo de nota (el `park` manda `notes: undefined`). No hay nada que esconder: `opcionesPorPerfil` no lleva banderas `nota` ni `diagnostico`.
2. **El "aviso" de comisión de tarjeta se queda.** Es el renglón "Comisión tarjeta N %" de `CardPaymentModal`/`MixedPaymentModal`, y solo aparece si la org la configuró (las FREE tienen 0 %, así que no lo ven). Esconderlo con la comisión activa dejaría un importe cobrado mayor al total sin explicación. Se registra para confirmarlo con el usuario en la revisión de tienda (Tarea 9).
3. **El alta rápida del POS vive en `POS.tsx`** (botón "Producto" → `ProductDetailModal mode="create"`, la ficha de 1,077 líneas con marca y departamento obligatorios), no en `ProductSearch.tsx`. En básico ese botón abre `FormularioProducto` (corto) dentro de `ui/Modal`, cargado con `lazy()` para no engordar `POS-*.js`.
4. **"Ventas" del menú de la dueña.** Hay dos: `/sales` ("Mis ventas", que para ADMIN/DUEÑO es global y tiene Reimprimir y Devolver por ticket) y `/hq/sales`. Básico deja `/sales` (así "Devoluciones desde el ticket" se cumple también para la dueña) y esconde `/hq/sales` y `/hq/returns`. La etiqueta sigue siendo "Mis ventas" (cambiarla tocaría a las de paga).
5. **Reportes de la dueña.** `/reports` no está en `ROLE_ROUTES.ADMINISTRADOR`; en vez de tocar roles, `/hq/reports-hub` renderiza `finance/Reports` cuando el perfil es básico (`<PorPerfil>`). `Reports` ya tiene Hoy/Ayer/Semana/Mes, total, tickets, método de pago, ventas por hora y top; el top es de 5 (lo da `/reports/dashboard`) y no se cambia el endpoint (decisión 2 del spec: el backend no cambia).
6. **El SKU se queda en el formulario corto.** `validarProducto` y `ProductCreate` lo exigen; el botón "Sugerir" ya lo resuelve en un clic.
7. **DUEÑO.** `ROLE_ROUTES.DUEÑO` no trae `/organization` ni `/users` (los abre por URL) y sí `/pos`: su menú básico queda en 7 (con Cobrar). No se tocan roles.
8. **Solo el plan explícito `FREE` deriva a básico** (ruling del controlador: NULL, vacío o desconocido → completo, al revés que los topes, para que ninguna org demo/QA ni una org recién creada cambie de interfaz sin que nadie lo decida). La Tarea 9 trae la consulta de solo lectura para listar las orgs FREE en producción y, si hace falta, forzarles `completo` desde la plataforma.
9. **FREE de otros giros.** El recorte es una lista de URLs a esconder (no una lista blanca), así que una FREE gastro conserva mesas, cocina y menú.
10. **Presets `ATLAS_ONE_*` FREE** aterrizan en `/home` (`rutaInicioPorRol`), no en `/hq/operations`: no ven `InicioBasico`. Sin cambio (fuera de alcance).
11. **Productos, vista de sucursal**: no tiene etiquetas, códigos ni rejilla; básico esconde Plantilla e Importar Excel y deja el filtro Todos/Stock bajo (es el único filtro, no uno "avanzado"). La lista HQ ya muestra SKU, producto, departamento, precio, existencia y estado; "activar/desactivar" no existe en ella y no se agrega.
12. **Empresa**: la tarjeta de datos (razón social, RFC, teléfono, email, web, dirección) no se parte; Logo, Tipo de cambio, Comisión y las secciones boutique del ticket van bajo "Más opciones" plegado. La impresora ya tiene su entrada de menú.
13. **Nombres**: el spec propone renombrar `navPerfilPlan.ts` → `navPerfil.ts`; se crea `navPerfilBasico.ts` al lado y `navPerfilPlan.ts` no se toca (sin churn de imports ni de pruebas). `opcionesPorPerfil(perfil)` no recibe capacidades: propina y factura ya se gobiernan con `useCapacidad` y no cambian.
14. **Prueba existente afectada**: `tests/test_campos_producto.py::test_contexto_trae_campos_producto` usa la org de `conftest` (plan por defecto `FREE`), que pasa a básico; la Tarea 2 le fija `plan = "ULTRA_PLUS"`.
15. **Gerente en básico** recibe la lista de la cajera (spec §4.1), así que pierde `/reports` y `/hq/valor-inventario` del menú (siguen abriendo por URL).

## Global Constraints

- **`main` = producción con clientes vivos.** Rama `feat/modo-basico`; commits locales sí; **push y merge a `main` solo con permiso explícito del usuario**.
- **Nada se apaga en el backend:** no se tocan gating, `require_module`, validaciones ni endpoints existentes. Lo único nuevo es `organization.perfil_ui` `String(12)` nullable, `organization.umbral_poca_existencia` `Integer` nullable (ALTER idempotentes en `scripts/railway_init.py`) y el endpoint de lectura `GET /api/reports/inicio-basico`. Las pantallas completas siguen abriendo por URL.
- **Toda consulta nueva filtra `organization_id`** y respeta el ámbito de sucursal como los reportes: ADMIN/DUEÑO/SUPERADMIN ven la org o la sucursal pedida (404 si es de otra org), GERENTE solo la suya, los demás 403.
- **No se toca el payload del cobro ni `saneaCobro`** (`utils/capacidades.ts`), ni `create_sale`.
- **`perfil_ui` solo lo cambia la plataforma** (`PUT /api/platform/organizations/{id}`, valores `auto | basico | completo`); el `PUT /api/organization/` de tenant lo descarta como a `plan`.
- **El frontend arranca en `completo`** hasta que llega el contexto; si la petición falla, `completo` (fail-open). Las rutas que cambian de pantalla esperan a que el contexto cargue antes de elegir.
- **Render condicional, nunca `hidden`**: lo que básico esconde no se monta, para que también aligere el DOM. Un dato que ya existe (un descuento de un ticket pausado, la marca de un producto importado) se sigue viendo.
- **Kit `ui/` y responsivo desde el día uno**: `CabeceraPagina`, `DaxCard`, `ListaTarjetas`, `TarjetaFila`, `Modal`; `useEsTelefono()` para tabla/tarjetas; ningún `grid-cols-N` (N ≥ 3) sin prefijo; ningún `fixed inset-0` nuevo (`overlaysFueraDelKit.test.ts`).
- **Presupuesto**: `InicioBasico` y el alta corta del POS son chunks propios (`lazy()`); `frontend/presupuesto_bundle.json` no se toca y el script pasa.
- **Las de paga no notan nada**: en `completo` cada pantalla es idéntica píxel a píxel; la Tarea 9 lo verifica con capturas a 1440 contra el baseline de la Tarea 0, y en básico revisa 390/768/1024 sin desborde.
- Textos, comentarios y nombres nuevos en español, como el código de alrededor. Pydantic v2, type hints en firmas nuevas, sin `print()`.
- Nunca dos `pytest` a la vez en el mismo worktree; suite completa siempre con `--ignore=tests/test_cash_complete.py`.
- Commits terminan con:
  ```
  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf
  ```

## Review Focus

1. **Contexto que tarda o falla en una PC vieja de tienda FREE**: el POS se pinta completo (nunca un básico a medias para una de paga) y cambia una sola vez al llegar `perfil_ui`; si la petición falla queda completo; Inicio y Reportes no montan ninguna de sus dos pantallas hasta saber el perfil. → Tarea 4 (store: falla → `completo`), Tarea 6 (jsdom `CartPanel`: `loaded: false` → controles completos) y Tarea 7 (jsdom `PorPerfil`: mientras carga no monta ninguna; falla → completa).
2. **Producto que ya tiene marca o descripción, editado en básico**: el formulario corto las muestra con su valor (regla "nada se apaga" de `campoVisible`). → Tarea 5 (jsdom `FormularioProducto`, edición con `brand_id` y `description`).
3. **Org en básico con dos o más sucursales**: la matriz de sucursales sigue y nada se marca solo; con una sola, la matriz se esconde, la sucursal va marcada y la existencia inicial cae ahí. → Tarea 5 (jsdom: una sucursal → payload con `target_branch_ids: [20]` y `branch_id: 20`; dos → "Activación por sucursal" visible).
4. **La plataforma fuerza `completo` a una FREE**: vuelve todo (menú de SP2, campos del formulario, controles del POS). → Tarea 1 (contexto `perfil_ui == "completo"`), Tarea 2 (contexto sin ocultos de básico), Tarea 4 (menú de la cajera FREE en completo conserva Clientes y Devoluciones) y Tarea 9 (diff a 1440 de FREE forzada a completo contra el baseline FREE de antes).
5. **Alta rápida de la cajera desde el POS en básico**: abre el formulario corto (sin marca, unidad, descripción ni foto) y manda un `ProductCreate` válido con su sucursal. → Tarea 6 (jsdom `AltaRapidaProducto`: payload con `name`, `sku`, `price`, `cost`, `branch_id: 20`, `initial_stock: 2`, sin `target_branch_ids`).

---

### Task 0: baseline de pruebas y de capturas

Nada de código de producto. Se mide la suite antes de tocar nada y se toma el baseline visual (completo y FREE "antes") con la herramienta de capturas de SP5.

**Files:**
- Create (scratchpad, no versionado): `$SCRATCH/modo-basico/capturas/` (copia de `$SCRATCH/responsivo/` + `plan_demo.py`), donde `$SCRATCH` es el scratchpad de la sesión que ejecuta.
- Output (gitignored): `/mnt/d/Devs/atlas-one/.superpowers/sdd/2026-10-19-modo-basico/baseline/` y `…/baseline-resumen.md`.

**Interfaces:**
- Consumes: la herramienta de SP5 (`stack.sh up|down`, `capturas.mjs --out DIR [--anchos] [--temas] [--rutas] [--usuario]`, `diff1440.mjs BASE NEW`), descrita en la Tarea 0 de `docs/superpowers/plans/2026-10-18-sp5-responsivo-admin-ola-2.md`.
- Produces: conteos de la suite (`pytest` y `vitest`) anotados en `baseline-resumen.md`; capturas en `baseline/completo-admin`, `baseline/completo-cajero`, `baseline/free-antes-admin`, `baseline/free-antes-cajero`; `plan_demo.py PLAN [perfil]`.

- [ ] **Step 1: Conteo de la suite antes de tocar nada**

Run: `python3 -m pytest -q -p no:warnings --ignore=tests/test_cash_complete.py 2>&1 | tail -3`
Expected: una línea `N passed[, M failed][, K errors]`. Anotar N/M/K en `baseline-resumen.md` (memoria del 2026-09-28: el baseline rojo de CLAUDE.md ya no existe; lo que salga aquí es la referencia).

Run: `cd frontend && npx vitest run 2>&1 | tail -4`
Expected: `Test Files … passed` y `Tests … passed`. Anotar los dos números.

- [ ] **Step 2: Herramienta de capturas**

Si existe `$SCRATCH/responsivo/` (la dejó SP5 en esta misma sesión), copiarla sin la base ni los resultados:

```bash
S=$SCRATCH/modo-basico/capturas; mkdir -p $S
rsync -a --exclude 'responsivo.db*' --exclude '*.log' --exclude 'final*' --exclude 'base-*' \
  --exclude 'reverif*' --exclude 'git-al-*' $SCRATCH/responsivo/ $S/
```

Si no existe, reconstruirla siguiendo los pasos 1-6 de la Tarea 0 del plan de SP5 (mismas reglas: login por `.reveal-cta`, reloj pausado, `<main>` a altura completa para la foto, medición de desborde en el estado real). En los dos casos el `R` de `stack.sh` apunta a este worktree:

```bash
sed -i 's#^R=${R:-.*}#R=${R:-/mnt/d/Devs/atlas-one/.worktrees/modo-basico}#' $S/stack.sh
```

- [ ] **Step 3: `plan_demo.py` — cambia el plan (y el perfil, cuando exista la columna) de la org `demo_pos`**

```python
# $SCRATCH/modo-basico/capturas/plan_demo.py
"""Pone el plan (y el perfil de interfaz, si la columna ya existe) de la org demo_pos.

Solo para la base SQLite de capturas: se niega a correr contra otra cosa.
Uso: DATABASE_URL=sqlite:///…/responsivo.db PYTHONPATH=<worktree> python3 plan_demo.py ULTRA_PLUS [basico|completo|auto]
"""
import os
import sys

if not os.environ.get("DATABASE_URL", "").startswith("sqlite:"):
    sys.exit("solo la base de capturas (sqlite)")

from app.core.database import SessionLocal  # noqa: E402
from app.models import Organization, User  # noqa: E402
from app.models.users import UserOrganization  # noqa: E402

plan = sys.argv[1]
perfil = sys.argv[2] if len(sys.argv) > 2 else None
db = SessionLocal()
admin = db.query(User).filter(User.username == "demo_pos").one()
org = (
    db.query(Organization)
    .join(UserOrganization, UserOrganization.organization_id == Organization.id)
    .filter(UserOrganization.user_id == admin.id)
    .first()
)
org.plan = plan
if hasattr(Organization, "perfil_ui"):
    org.perfil_ui = perfil
db.commit()
print(org.id, org.plan, getattr(org, "perfil_ui", "(sin columna)"))
```

- [ ] **Step 4: Baseline completo (org de paga)**

```bash
cd $S && bash stack.sh up
export DATABASE_URL="sqlite:///$S/responsivo.db" PYTHONPATH=/mnt/d/Devs/atlas-one/.worktrees/modo-basico
python3 plan_demo.py ULTRA_PLUS
B=/mnt/d/Devs/atlas-one/.superpowers/sdd/2026-10-19-modo-basico/baseline
node capturas.mjs --out $B/completo-admin --rutas /hq/operations,/hq/reports-hub,/products,/organization --usuario demo_pos
node capturas.mjs --out $B/completo-cajero --rutas /pos,/products --usuario demo_cajero_pos
```

Expected: 4 rutas × 4 anchos × 2 temas = 32 capturas de admin y 16 de cajera, más las de `ACCIONES` (`/products` abre el importador y el formulario) y un `desbordes.json` por carpeta. Repetir el comando de admin en otra carpeta y correr `node diff1440.mjs $B/completo-admin <otra>`: 0 píxeles distintos (el reloj está pausado).

- [ ] **Step 5: Baseline FREE "antes" (la tienda FREE de hoy, sin modo básico)**

```bash
python3 plan_demo.py FREE
node capturas.mjs --out $B/free-antes-admin --rutas /hq/operations,/hq/reports-hub,/products,/organization --usuario demo_pos
node capturas.mjs --out $B/free-antes-cajero --rutas /pos,/products --usuario demo_cajero_pos
bash stack.sh down
```

`/reports` (spec §6) la ve la dueña en básico por `/hq/reports-hub` (decisión 5); no hay gerente demo, así que no se captura aparte.

- [ ] **Step 6: Sin commit.** Escribir `baseline-resumen.md`: conteos de la suite, rutas que desbordan hoy a 390 (de `desbordes.json`), selectores de `ACCIONES` que no encontraron su botón.

---

### Task 1: Backend — `perfil_ui` y `umbral_poca_existencia` en `organization`, `perfil_efectivo`, contexto y PUTs

**Files:**
- Create: `app/services/perfil_ui.py`
- Modify: `app/modules/tenants/models.py` (después de `card_surcharge_pct`, antes de `# SaaS`)
- Modify: `app/modules/tenants/schemas.py` (`OrganizationUpdate`, `OrganizationRead`)
- Modify: `app/modules/tenants/router.py:87` (tupla de campos de plataforma del PUT de tenant)
- Modify: `app/routers/platform/_shared.py:87-93` (`_ORG_UPDATE_FIELDS`)
- Modify: `app/modules/users/router.py:43-75` (`read_user_context`)
- Modify: `scripts/railway_init.py:162` (después de la línea de `ticket_line_style`)
- Test: `tests/test_perfil_ui.py`

**Interfaces:**
- Consumes: `app.services.plans.obtener_plan(clave) -> Plan` (`.clave`).
- Produces:
  - `perfil_efectivo(org) -> str` → `"basico" | "completo"`; `None` → `"completo"`.
  - `normalizar_perfil_ui(valor: Optional[str]) -> Optional[str]` → `None` | `"auto" | "basico" | "completo"`; otro valor → `ValueError("debe ser uno de: auto, basico, completo")`.
  - Constantes `BASICO = "basico"`, `COMPLETO = "completo"`, `AUTO = "auto"`, `VALORES_PERFIL_UI`.
  - `Organization.perfil_ui: String(12) | None`, `Organization.umbral_poca_existencia: Integer | None`.
  - `OrganizationRead.perfil_ui: Optional[str]`, `OrganizationRead.umbral_poca_existencia: Optional[int]`; `OrganizationUpdate.perfil_ui: Optional[str]` (validado), `OrganizationUpdate.umbral_poca_existencia: Optional[int]` (`0..1000`).
  - `GET /api/users/me/context` → `"perfil_ui": "basico" | "completo"` (siempre presente; `"completo"` sin org activa).

- [ ] **Step 1: Escribir la prueba que falla**

```python
# tests/test_perfil_ui.py
"""Modo básico: el perfil de interfaz sale del plan y la plataforma lo puede forzar.

FREE explícito → básico; el resto (incluido plan NULL o desconocido) → completo. `organization.perfil_ui` = 'basico'/'completo' manda; NULL o
'auto' = derivar. Solo la plataforma lo cambia: el PUT de tenant lo descarta.
"""
from types import SimpleNamespace

import pytest

from app.services.perfil_ui import normalizar_perfil_ui, perfil_efectivo
from scripts import railway_init


def _org(plan=None, perfil=None):
    return SimpleNamespace(plan=plan, perfil_ui=perfil)


@pytest.mark.parametrize("plan, perfil, esperado", [
    ("FREE", None, "basico"),
    ("FREE", "auto", "basico"),
    (None, None, "completo"),          # sin plan: no cambiar la interfaz sin decidirlo
    ("Demo", None, "completo"),        # desconocido: idem (ruling, distinto a los topes)
    ("START", None, "completo"),
    ("ULTRA_PLUS", None, "completo"),
    ("FREE", "completo", "completo"),  # demo de una FREE
    ("ULTRA_PLUS", "basico", "basico"),  # una de paga que quiere lo simple
    ("FREE", " COMPLETO ", "completo"),
    ("PRO", "raro", "completo"),       # valor raro guardado = auto
])
def test_perfil_efectivo(plan, perfil, esperado):
    assert perfil_efectivo(_org(plan, perfil)) == esperado


def test_sin_organizacion_es_completo():
    assert perfil_efectivo(None) == "completo"


def test_normalizar_perfil_ui():
    assert normalizar_perfil_ui(None) is None
    assert normalizar_perfil_ui(" Basico ") == "basico"
    assert normalizar_perfil_ui("auto") == "auto"
    with pytest.raises(ValueError, match="auto, basico, completo"):
        normalizar_perfil_ui("simple")


@pytest.mark.parametrize("columna", ["perfil_ui", "umbral_poca_existencia"])
def test_el_arranque_migra_las_columnas(columna):
    declaradas = {(t, c) for t, c, _ in railway_init.COLUMN_MIGRATIONS}
    assert ("organization", columna) in declaradas


def _contexto(client, auth, org):
    r = client.get("/api/users/me/context", headers={**auth, "X-Organization-ID": str(org.id)})
    assert r.status_code == 200, r.text
    return r.json()


def test_contexto_de_una_free_es_basico(client, db, auth_admin, org):
    org.plan = "FREE"
    db.flush()
    assert _contexto(client, auth_admin, org)["perfil_ui"] == "basico"


def test_contexto_de_una_de_paga_es_completo(client, db, auth_admin, org):
    org.plan = "ULTRA_PLUS"
    db.flush()
    assert _contexto(client, auth_admin, org)["perfil_ui"] == "completo"


def test_contexto_de_una_free_forzada_a_completo(client, db, auth_admin, org):
    """Review Focus #4: la plataforma fuerza completo y todo vuelve."""
    org.plan = "FREE"
    org.perfil_ui = "completo"
    db.flush()
    assert _contexto(client, auth_admin, org)["perfil_ui"] == "completo"


def test_la_plataforma_fuerza_y_regresa_a_auto(client, db, auth_superadmin, org):
    r = client.put(f"/api/platform/organizations/{org.id}", json={"perfil_ui": "completo"}, headers=auth_superadmin)
    assert r.status_code == 200, r.text
    assert r.json()["perfil_ui"] == "completo"
    r = client.put(f"/api/platform/organizations/{org.id}", json={"perfil_ui": "auto"}, headers=auth_superadmin)
    assert r.status_code == 200, r.text
    db.refresh(org)
    assert org.perfil_ui == "auto"


def test_la_plataforma_rechaza_un_perfil_desconocido(client, auth_superadmin, org):
    r = client.put(f"/api/platform/organizations/{org.id}", json={"perfil_ui": "simple"}, headers=auth_superadmin)
    assert r.status_code == 422
    assert "auto, basico, completo" in r.text


def test_el_tenant_no_cambia_su_perfil(client, db, auth_admin, org, admin_user):
    org.plan = "FREE"
    db.commit()
    r = client.put(
        "/api/organization/",
        json={"name": "Mi tienda", "perfil_ui": "completo"},
        headers={**auth_admin, "X-Organization-ID": str(org.id)},
    )
    assert r.status_code == 200, r.text
    db.refresh(org)
    assert org.perfil_ui is None
    assert org.name == "Mi tienda"


def test_el_tenant_guarda_el_umbral(client, db, auth_admin, org, admin_user):
    r = client.put(
        "/api/organization/",
        json={"umbral_poca_existencia": 5},
        headers={**auth_admin, "X-Organization-ID": str(org.id)},
    )
    assert r.status_code == 200, r.text
    assert r.json()["umbral_poca_existencia"] == 5


def test_umbral_negativo_es_422(client, auth_admin, org, admin_user):
    r = client.put(
        "/api/organization/",
        json={"umbral_poca_existencia": -1},
        headers={**auth_admin, "X-Organization-ID": str(org.id)},
    )
    assert r.status_code == 422
```

- [ ] **Step 2: Correr y ver que falla**

Run: `python3 -m pytest -q -p no:warnings tests/test_perfil_ui.py`
Expected: FAIL en la colección con `ModuleNotFoundError: No module named 'app.services.perfil_ui'`.

- [ ] **Step 3: `app/services/perfil_ui.py`**

```python
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
```

- [ ] **Step 4: Columnas en el modelo**

En `app/modules/tenants/models.py`, reemplazar:

```python
    card_surcharge_pct = Column(Numeric(5, 2), default=0, server_default="0", nullable=False)

    # SaaS
```

por:

```python
    card_surcharge_pct = Column(Numeric(5, 2), default=0, server_default="0", nullable=False)

    # Modo básico (2026-10). `perfil_ui`: NULL o 'auto' = se deriva del plan
    # (FREE → básico); 'basico'/'completo' = forzado por la plataforma. Solo
    # decide qué muestra la interfaz (app/services/perfil_ui.py).
    perfil_ui = Column(String(12), nullable=True)
    # Tope de "se está acabando" del Inicio básico, en piezas. NULL = 3.
    umbral_poca_existencia = Column(Integer, nullable=True)

    # SaaS
```

- [ ] **Step 5: Schemas**

En `app/modules/tenants/schemas.py`, después de `from app.models.organization import IndustryType` añadir:

```python
from app.services.perfil_ui import normalizar_perfil_ui
```

En `OrganizationUpdate`, reemplazar:

```python
    card_surcharge_pct: Optional[Decimal] = None

    _estilo_valido = field_validator("ticket_line_style")(_valida_estilo_de_linea)

    model_config = {"extra": "ignore"}
```

por:

```python
    card_surcharge_pct: Optional[Decimal] = None

    # Modo básico (2026-10). `perfil_ui` es de PLATAFORMA: el PUT de tenant lo
    # descarta como a `plan`; solo `/api/platform/organizations/{id}` lo guarda.
    perfil_ui: Optional[str] = None
    # Tope de "se está acabando" del Inicio básico. Cae FUERA de la whitelist
    # de no-admins del router: solo ADMINISTRADOR/DUEÑO lo cambia.
    umbral_poca_existencia: Optional[int] = Field(default=None, ge=0, le=1000)

    _estilo_valido = field_validator("ticket_line_style")(_valida_estilo_de_linea)
    _perfil_valido = field_validator("perfil_ui")(normalizar_perfil_ui)

    model_config = {"extra": "ignore"}
```

En `OrganizationRead`, reemplazar:

```python
    card_surcharge_pct: Decimal = Decimal("0")

    class Config:
        from_attributes = True
```

por:

```python
    card_surcharge_pct: Decimal = Decimal("0")

    # Modo básico: la plataforma lee el perfil forzado; Empresa, el tope.
    perfil_ui: Optional[str] = None
    umbral_poca_existencia: Optional[int] = None

    class Config:
        from_attributes = True
```

- [ ] **Step 6: El PUT de tenant descarta `perfil_ui`; el de plataforma lo acepta**

En `app/modules/tenants/router.py` reemplazar:

```python
    for _campo_plataforma in ("plan", "status", "is_active"):
```

por:

```python
    for _campo_plataforma in ("plan", "status", "is_active", "perfil_ui"):
```

En `app/routers/platform/_shared.py` reemplazar:

```python
    "industry_type", "status", "plan", "branding_config", "is_active",
```

por:

```python
    "industry_type", "status", "plan", "branding_config", "is_active", "perfil_ui",
```

- [ ] **Step 7: `perfil_ui` en `/me/context`**

En `app/modules/users/router.py`, reemplazar:

```python
        "allowed_templates": [],
        "plan": None,
    }
```

por:

```python
        "allowed_templates": [],
        "plan": None,
        # Modo básico: qué tan larga es la interfaz. Sin org activa, completa.
        "perfil_ui": "completo",
    }
```

y reemplazar:

```python
            from app.services.capabilities_service import resumen_plan
            ctx["plan"] = resumen_plan(org)
```

por:

```python
            from app.services.capabilities_service import resumen_plan
            ctx["plan"] = resumen_plan(org)
            from app.services.perfil_ui import perfil_efectivo
            ctx["perfil_ui"] = perfil_efectivo(org)
```

- [ ] **Step 8: ALTER idempotente**

En `scripts/railway_init.py`, reemplazar:

```python
    ("organization", "ticket_line_style", "ALTER TABLE organization ADD COLUMN ticket_line_style VARCHAR(12) NOT NULL DEFAULT 'compact';"),
```

por:

```python
    ("organization", "ticket_line_style", "ALTER TABLE organization ADD COLUMN ticket_line_style VARCHAR(12) NOT NULL DEFAULT 'compact';"),
    # Modo básico 2026-10. Las dos nacen NULL: NULL = 'auto' (el perfil sale
    # del plan: las FREE ven la interfaz corta, las de paga la de siempre) y
    # NULL = tope de 3 piezas en "se está acabando".
    ("organization", "perfil_ui", "ALTER TABLE organization ADD COLUMN perfil_ui VARCHAR(12);"),
    ("organization", "umbral_poca_existencia", "ALTER TABLE organization ADD COLUMN umbral_poca_existencia INTEGER;"),
```

- [ ] **Step 9: Correr y ver que pasa**

Run: `python3 -m pytest -q -p no:warnings tests/test_perfil_ui.py tests/test_plan_en_contexto.py tests/test_planes_enforcement.py tests/test_migraciones_de_despliegue.py`
Expected: PASS (todas).

- [ ] **Step 10: Commit**

```bash
git add app/services/perfil_ui.py app/modules/tenants/models.py app/modules/tenants/schemas.py \
  app/modules/tenants/router.py app/routers/platform/_shared.py app/modules/users/router.py \
  scripts/railway_init.py tests/test_perfil_ui.py
git commit -m "$(cat <<'EOF'
feat(modo-basico): perfil de interfaz por plan y tope de poca existencia

perfil_efectivo(org): FREE → básico, la plataforma lo fuerza con
organization.perfil_ui; viaja en /me/context. El PUT de tenant lo descarta
como a plan. umbral_poca_existencia lo guarda la dueña desde Empresa.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf
EOF
)"
```

---

### Task 2: Backend — `campos_producto(preset, modulos, perfil)`

**Files:**
- Modify: `app/modules/products/campos.py`
- Modify: `app/modules/users/router.py` (llamada a `campos_producto` en `read_user_context`)
- Test: `tests/test_campos_producto.py`

**Interfaces:**
- Consumes: `ctx["perfil_ui"]` (Tarea 1).
- Produces: `OCULTOS_BASICO = ("brand_id", "description", "unit", "image_url", "tax_rate", "packaging_units", "variants")`; `campos_producto(preset: Optional[str], modulos: Iterable[str], perfil: str = "completo") -> dict` (`{"visibles": [...], "ocultos": [...]}`); en básico los de `OCULTOS_BASICO` salen de `visibles` y entran a `ocultos` (después de la ficha, sin repetir).

- [ ] **Step 1: Escribir las pruebas que fallan**

En `tests/test_campos_producto.py`, cambiar el import:

```python
from app.modules.products.campos import CAMPOS_FICHA, campos_producto
```

por:

```python
from app.modules.products.campos import CAMPOS_FICHA, OCULTOS_BASICO, campos_producto
```

En `test_contexto_trae_campos_producto`, reemplazar:

```python
    org.industry_type = IndustryType.ATLAS_POS_BOUTIQUE
    db.commit()
```

por:

```python
    org.industry_type = IndustryType.ATLAS_POS_BOUTIQUE
    # De paga: la org de conftest nace FREE y desde el modo básico eso ya
    # esconde campos. Esta prueba mira la ficha boutique, no el perfil.
    org.plan = "ULTRA_PLUS"
    db.commit()
```

Y añadir al final del archivo:

```python
def test_basico_esconde_marca_descripcion_unidad_foto_tasa_empaques_y_variantes():
    r = campos_producto("ATLAS_POS", ["core", "catalog", "variants"], "basico")
    for clave in OCULTOS_BASICO:
        assert clave in r["ocultos"]
        assert clave not in r["visibles"]
    # El formulario corto del spec §4.2 (+ SKU, que la API exige).
    for clave in ("name", "sku", "barcode", "department_id", "price", "cost",
                  "has_iva", "initial_stock", "prices"):
        assert clave in r["visibles"]
    # La ficha sigue oculta primero y nada se repite.
    assert r["ocultos"][:3] == list(CAMPOS_FICHA)
    assert len(r["ocultos"]) == len(set(r["ocultos"]))


def test_completo_es_el_default_y_no_cambia_nada():
    for preset in ("ATLAS_POS", "ATLAS_POS_BOUTIQUE", None):
        assert campos_producto(preset, ["core", "variants"]) == campos_producto(preset, ["core", "variants"], "completo")


def test_basico_aplica_aunque_no_haya_preset():
    r = campos_producto(None, [], "basico")
    assert "brand_id" in r["ocultos"]
    assert set(CAMPOS_FICHA) <= set(r["visibles"])  # la ficha sigue fallando abierto


def test_contexto_de_una_free_trae_los_ocultos_de_basico(client, db, auth_admin, org):
    org.industry_type = IndustryType.ATLAS_POS
    org.plan = "FREE"
    db.commit()
    cuerpo = client.get("/api/users/me/context",
                        headers={**auth_admin, "X-Organization-ID": str(org.id)}).json()
    assert cuerpo["perfil_ui"] == "basico"
    assert "brand_id" in cuerpo["campos_producto"]["ocultos"]
    assert "description" in cuerpo["campos_producto"]["ocultos"]


def test_contexto_de_una_free_forzada_a_completo_no_esconde_de_mas(client, db, auth_admin, org):
    """Review Focus #4: forzar completo devuelve el formulario entero."""
    org.industry_type = IndustryType.ATLAS_POS
    org.plan = "FREE"
    org.perfil_ui = "completo"
    db.commit()
    cuerpo = client.get("/api/users/me/context",
                        headers={**auth_admin, "X-Organization-ID": str(org.id)}).json()
    assert cuerpo["campos_producto"]["ocultos"] == list(CAMPOS_FICHA)
```

- [ ] **Step 2: Correr y ver que falla**

Run: `python3 -m pytest -q -p no:warnings tests/test_campos_producto.py`
Expected: FAIL con `ImportError: cannot import name 'OCULTOS_BASICO'`.

- [ ] **Step 3: Implementación**

En `app/modules/products/campos.py`, reemplazar desde `# Presets que capturan la ficha.` hasta el final del archivo por:

```python
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
```

En `app/modules/users/router.py`, reemplazar:

```python
    ctx["campos_producto"] = campos_producto(ctx["preset"], ctx["enabled_modules"])
```

por:

```python
    ctx["campos_producto"] = campos_producto(ctx["preset"], ctx["enabled_modules"], ctx["perfil_ui"])
```

- [ ] **Step 4: Correr y ver que pasa**

Run: `python3 -m pytest -q -p no:warnings tests/test_campos_producto.py tests/test_perfil_ui.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/modules/products/campos.py app/modules/users/router.py tests/test_campos_producto.py
git commit -m "$(cat <<'EOF'
feat(modo-basico): el formulario de producto corto sale de campos_producto

En básico se esconden marca, descripción, unidad, foto, tasa de IVA,
empaques y variantes; un producto que ya los trae los sigue mostrando.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf
EOF
)"
```

---

### Task 3: Backend — `GET /api/reports/inicio-basico`

**Files:**
- Create: `app/routers/reports_inicio.py`
- Modify: `app/schemas/reports.py` (al final)
- Modify: `app/main.py:15` (import) y `:212` (montaje)
- Test: `tests/test_reports_inicio_basico.py`

**Interfaces:**
- Consumes: `app.routers.reports._today_mx() -> date`, `_mx(col)`, `_describe_name(name, variant_name) -> str`, `get_daily_summary(target_date, branch_id, db, current_user, org_id) -> dict` (usa `["payments"]`, ya con el vuelto descontado); `SALES_REPORT_STATUSES`, `compute_expected_cash(db, session).expected`; `Organization.umbral_poca_existencia` (Tarea 1).
- Produces: `GET /api/reports/inicio-basico?branch_id=` con esta forma exacta (la Tarea 7 la reusa tal cual):

```json
{
  "branch_id": null,
  "hoy":    {"desde": "2026-10-19", "hasta": "2026-10-19", "total": 1234.5, "tickets": 12},
  "ayer":   {"desde": "2026-10-18", "hasta": "2026-10-18", "total": 800.0, "tickets": 9},
  "semana": {"desde": "2026-10-13", "hasta": "2026-10-19", "total": 9000.0, "tickets": 70},
  "por_metodo_hoy": {"CASH": 1000.0, "CARD": 234.5},
  "top_semana": [{"nombre": "Blusa roja", "cantidad": 14.0, "total": 1400.0}],
  "poca_existencia": {"umbral": 3, "productos": [
    {"variant_id": "uuid", "nombre": "Falda negra", "sku": "FAL-1", "existencia": 1.0}
  ]},
  "corte": {"estado": "abierto", "cajera": "Mirna", "abierto_en": "2026-10-19T15:00:00+00:00",
            "cerrado_en": null, "efectivo_esperado": 1500.0, "efectivo_contado": null}
}
```

  `corte.estado` ∈ `"abierto" | "cerrado" | "sin_turno"`; `efectivo_esperado` solo con turno abierto, `efectivo_contado` solo con cerrado. `semana` = hoy y los 6 días anteriores. `top_semana` máximo 5 por piezas. `poca_existencia.productos` máximo 10, existencia sumada por variante ≤ umbral (`organization.umbral_poca_existencia` o 3), activos y no borrados; sin `branch_id` solo cuentan las sucursales que venden y están activas.
- Schemas: `PeriodoVentas`, `ProductoTop`, `ProductoPocaExistencia`, `PocaExistencia`, `CorteInicio`, `InicioBasicoResponse`.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
# tests/test_reports_inicio_basico.py
"""`GET /api/reports/inicio-basico` — el "¿cómo voy?" de la dueña en modo básico.

Una sola llamada (una PC vieja de tienda no debe hacer cinco): vendido hoy,
ayer y en 7 días, cobros de hoy por método, lo más vendido, lo que se está
acabando y el estado de la caja. Aislado por organización y por sucursal con
las mismas reglas que el valor de la tienda.
"""
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from itertools import count
from zoneinfo import ZoneInfo

from app.models.cash import CashSession
from app.models.inventory import StockOnHand
from app.models.organization import Branch, BranchType, Organization
from app.models.products import Product, ProductVariant
from app.models.sales import DocumentStatus, Payment, PaymentMethod, SalesDocument, SalesLineItem

_MX = ZoneInfo("America/Mexico_City")
URL = "/api/reports/inicio-basico"
_folios = count(1)


def _instante(dias_atras: int, hora: int = 12) -> datetime:
    """Mediodía (hora de México) de hace `dias_atras` días, en UTC."""
    dia = datetime.now(_MX).date() - timedelta(days=dias_atras)
    return datetime.combine(dia, time(hora), tzinfo=_MX).astimezone(timezone.utc)


def _variante(db, org, branch, nombre, sku, existencia):
    p = Product(name=nombre, organization_id=org.id, is_active=True)
    db.add(p)
    db.flush()
    v = ProductVariant(product_id=p.id, sku=sku, price=Decimal("100"), cost=Decimal("40"),
                       organization_id=org.id)
    db.add(v)
    db.flush()
    db.add(StockOnHand(variant_id=v.id, branch_id=branch.id, organization_id=org.id,
                       qty_on_hand=Decimal(str(existencia)), is_active=True))
    db.flush()
    return v


def _venta(db, org, branch, user, variante, total, *, metodo=PaymentMethod.CASH, dias_atras=0,
           descripcion="Producto", cantidad=1, status=DocumentStatus.PAID):
    doc = SalesDocument(
        organization_id=org.id, branch_id=branch.id, seller_id=user.id, folio=next(_folios),
        series="A", subtotal=Decimal(total), tax_amount=Decimal("0"),
        total_amount=Decimal(total), status=status, doc_type="ORDER",
    )
    doc.created_at = _instante(dias_atras)
    db.add(doc)
    db.flush()
    db.add(SalesLineItem(
        organization_id=org.id, document_id=doc.id, variant_id=variante.id,
        description=descripcion, quantity=cantidad,
        unit_price=Decimal(total) / cantidad, total_line=Decimal(total), unit_cost=Decimal("10"),
    ))
    pago = Payment(organization_id=org.id, sales_document_id=doc.id, method=metodo, amount=Decimal(total))
    pago.created_at = _instante(dias_atras)
    db.add(pago)
    db.commit()
    return doc


def test_hoy_ayer_y_semana(client, db, org, branch_a, admin_user, auth_admin):
    v = _variante(db, org, branch_a, "Blusa", "BLU-1", 50)
    _venta(db, org, branch_a, admin_user, v, "100")
    _venta(db, org, branch_a, admin_user, v, "50", metodo=PaymentMethod.CARD)
    _venta(db, org, branch_a, admin_user, v, "500", status=DocumentStatus.CANCELLED)
    _venta(db, org, branch_a, admin_user, v, "70", dias_atras=1)
    _venta(db, org, branch_a, admin_user, v, "30", dias_atras=6)
    _venta(db, org, branch_a, admin_user, v, "999", dias_atras=7)

    r = client.get(URL, headers=auth_admin)

    assert r.status_code == 200, r.text
    d = r.json()
    assert d["branch_id"] is None
    assert (d["hoy"]["total"], d["hoy"]["tickets"]) == (150.0, 2)
    assert (d["ayer"]["total"], d["ayer"]["tickets"]) == (70.0, 1)
    assert (d["semana"]["total"], d["semana"]["tickets"]) == (250.0, 4)
    assert d["hoy"]["desde"] == d["hoy"]["hasta"] == d["semana"]["hasta"]


def test_cobros_de_hoy_por_metodo(client, db, org, branch_a, admin_user, auth_admin):
    v = _variante(db, org, branch_a, "Blusa", "BLU-1", 50)
    _venta(db, org, branch_a, admin_user, v, "100")
    _venta(db, org, branch_a, admin_user, v, "50", metodo=PaymentMethod.CARD)
    _venta(db, org, branch_a, admin_user, v, "80", dias_atras=1)

    d = client.get(URL, headers=auth_admin).json()

    assert d["por_metodo_hoy"] == {"CASH": 100.0, "CARD": 50.0}


def test_lo_mas_vendido_de_la_semana_por_piezas_y_maximo_cinco(client, db, org, branch_a, admin_user, auth_admin):
    v = _variante(db, org, branch_a, "Blusa", "BLU-1", 50)
    _venta(db, org, branch_a, admin_user, v, "40", descripcion="Blusa", cantidad=2)
    _venta(db, org, branch_a, admin_user, v, "20", descripcion="Blusa", cantidad=1, dias_atras=3)
    for nombre in ("Falda", "Short", "Gorra", "Bolsa", "Cinto"):
        _venta(db, org, branch_a, admin_user, v, "10", descripcion=nombre)
    _venta(db, org, branch_a, admin_user, v, "999", descripcion="Vieja", cantidad=50, dias_atras=8)

    top = client.get(URL, headers=auth_admin).json()["top_semana"]

    assert len(top) == 5
    assert top[0] == {"nombre": "Blusa", "cantidad": 3.0, "total": 60.0}
    assert "Vieja" not in [t["nombre"] for t in top]


def test_poca_existencia_con_el_tope_de_la_empresa(client, db, org, branch_a, admin_user, auth_admin):
    for n in range(12):
        _variante(db, org, branch_a, f"Prod {n:02d}", f"SKU-{n:02d}", n)
    db.commit()

    d = client.get(URL, headers=auth_admin).json()["poca_existencia"]
    assert d["umbral"] == 3
    assert [p["existencia"] for p in d["productos"]] == [0.0, 1.0, 2.0, 3.0]
    assert d["productos"][0]["nombre"] == "Prod 00"

    org.umbral_poca_existencia = 20
    db.commit()
    d = client.get(URL, headers=auth_admin).json()["poca_existencia"]
    assert d["umbral"] == 20
    assert len(d["productos"]) == 10


def test_poca_existencia_sin_inactivos_borrados_ni_bodegas(client, db, org, branch_a, hq_branch, admin_user, auth_admin):
    _variante(db, org, branch_a, "Activo", "A-1", 1)
    inactivo = _variante(db, org, branch_a, "Inactivo", "I-1", 0)
    db.get(Product, inactivo.product_id).is_active = False
    borrada = _variante(db, org, branch_a, "Borrada", "B-1", 0)
    borrada.deleted_at = datetime.now(timezone.utc)
    _variante(db, org, hq_branch, "Bodega", "H-1", 0)  # HQ de conftest: can_sell=False
    db.commit()

    productos = client.get(URL, headers=auth_admin).json()["poca_existencia"]["productos"]

    assert [p["nombre"] for p in productos] == ["Activo"]


def test_otra_organizacion_no_se_mezcla(client, db, org, branch_a, admin_user, auth_admin):
    otra = Organization(name="Otra", status="ACTIVE")
    db.add(otra)
    db.flush()
    ajena = Branch(name="Ajena", branch_type=BranchType.STORE, can_sell=True, is_active=True,
                   organization_id=otra.id)
    db.add(ajena)
    db.flush()
    v = _variante(db, otra, ajena, "Ajeno", "AJ-1", 0)
    _venta(db, otra, ajena, admin_user, v, "777")

    d = client.get(URL, headers=auth_admin).json()

    assert d["hoy"]["tickets"] == 0
    assert d["por_metodo_hoy"] == {}
    assert d["top_semana"] == []
    assert d["poca_existencia"]["productos"] == []
    assert client.get(f"{URL}?branch_id={ajena.id}", headers=auth_admin).status_code == 404


def test_la_duena_puede_mirar_una_sucursal(client, db, org, branch_a, branch_b, admin_user, auth_admin):
    v = _variante(db, org, branch_a, "Blusa", "BLU-1", 50)
    _venta(db, org, branch_a, admin_user, v, "100")
    _venta(db, org, branch_b, admin_user, v, "700")

    d = client.get(f"{URL}?branch_id={branch_b.id}", headers=auth_admin).json()

    assert d["branch_id"] == branch_b.id
    assert d["hoy"]["total"] == 700.0
    assert client.get(URL, headers=auth_admin).json()["hoy"]["total"] == 800.0


def test_el_gerente_solo_ve_su_sucursal(client, db, org, branch_a, branch_b, gerente_a, auth_gerente_a):
    v = _variante(db, org, branch_a, "Blusa", "BLU-1", 50)
    _venta(db, org, branch_a, gerente_a, v, "100")
    _venta(db, org, branch_b, gerente_a, v, "700")

    d = client.get(f"{URL}?branch_id={branch_b.id}", headers=auth_gerente_a).json()

    assert d["branch_id"] == branch_a.id
    assert d["hoy"]["total"] == 100.0
    assert d["por_metodo_hoy"] == {"CASH": 100.0}


def test_la_cajera_no_ve_el_inicio(client, cajero_a, auth_cajero_a):
    assert client.get(URL, headers=auth_cajero_a).status_code == 403


def test_corte_abierto_con_efectivo_esperado(client, db, org, branch_a, cajero_a, admin_user, auth_admin):
    db.add(CashSession(user_id=cajero_a.id, branch_id=branch_a.id, organization_id=org.id,
                       opening_balance=Decimal("500"), status="OPEN"))
    db.commit()

    c = client.get(URL, headers=auth_admin).json()["corte"]

    assert c["estado"] == "abierto"
    assert c["cajera"] == "cajero_a"
    assert c["efectivo_esperado"] == 500.0
    assert c["abierto_en"] is not None
    assert c["efectivo_contado"] is None


def test_corte_sin_turno_y_cerrado(client, db, org, branch_a, cajero_a, admin_user, auth_admin):
    assert client.get(URL, headers=auth_admin).json()["corte"] == {
        "estado": "sin_turno", "cajera": None, "abierto_en": None, "cerrado_en": None,
        "efectivo_esperado": None, "efectivo_contado": None,
    }
    db.add(CashSession(user_id=cajero_a.id, branch_id=branch_a.id, organization_id=org.id,
                       opening_balance=Decimal("500"), closing_balance=Decimal("850"),
                       status="CLOSED", closed_at=datetime.now(timezone.utc)))
    db.commit()

    c = client.get(URL, headers=auth_admin).json()["corte"]

    assert c["estado"] == "cerrado"
    assert c["efectivo_contado"] == 850.0
    assert c["efectivo_esperado"] is None
    assert c["cerrado_en"] is not None
```

- [ ] **Step 2: Correr y ver que falla**

Run: `python3 -m pytest -q -p no:warnings tests/test_reports_inicio_basico.py`
Expected: FAIL, 11 pruebas con `assert 404 == 200` o `KeyError` (la ruta no existe).

- [ ] **Step 3: Schemas**

En `app/schemas/reports.py`, reemplazar:

```python
from datetime import date
```

por:

```python
from datetime import date, datetime
```

y añadir al final del archivo:

```python


# --- Inicio básico (GET /api/reports/inicio-basico, modo básico 2026-10) ----
# Floats y no Decimal: igual que la valuación, la pantalla no tiene que parsear.

class PeriodoVentas(BaseModel):
    desde: date
    hasta: date
    total: float
    tickets: int


class ProductoTop(BaseModel):
    nombre: str
    cantidad: float
    total: float


class ProductoPocaExistencia(BaseModel):
    variant_id: str
    nombre: str
    sku: str
    existencia: float


class PocaExistencia(BaseModel):
    umbral: int
    productos: List[ProductoPocaExistencia]


class CorteInicio(BaseModel):
    estado: str  # 'abierto' | 'cerrado' | 'sin_turno'
    cajera: Optional[str] = None
    abierto_en: Optional[datetime] = None
    cerrado_en: Optional[datetime] = None
    efectivo_esperado: Optional[float] = None  # solo con turno abierto
    efectivo_contado: Optional[float] = None   # solo con turno cerrado


class InicioBasicoResponse(BaseModel):
    branch_id: Optional[int]  # None = todas las sucursales de la org
    hoy: PeriodoVentas
    ayer: PeriodoVentas
    semana: PeriodoVentas
    por_metodo_hoy: Dict[str, float]
    top_semana: List[ProductoTop]
    poca_existencia: PocaExistencia
    corte: CorteInicio
```

- [ ] **Step 4: Router**

```python
# app/routers/reports_inicio.py
"""Atlas BOS routers/reports_inicio — "¿cómo voy?" del Inicio básico (modo básico, 2026-10).

`GET /api/reports/inicio-basico` junta en UNA respuesta lo que la dueña de una
tienda FREE mira al entrar: vendido hoy, ayer y en 7 días; cobros de hoy por
método; lo que más se vende; lo que se está acabando y el estado de la caja.
Una PC vieja de mostrador no debe hacer cinco llamadas para pintar el inicio.

Solo lectura. Reusa el criterio de los reportes: `SALES_REPORT_STATUSES` para
"esto ya es venta", `get_daily_summary` para los cobros (descuenta el vuelto
del efectivo) y `compute_expected_cash` para la caja. Ámbito como la valuación:
ADMIN/DUEÑO/SUPERADMIN ven la org o la sucursal que pidan; GERENTE, la suya.
"""
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.tenant_context import get_current_active_organization
from app.models import (
    Branch, Organization, Product, ProductVariant, SalesDocument, SalesLineItem,
    StockOnHand, User,
)
from app.models.cash import CashSession, CashSessionStatus
from app.models.users import PlatformRole, Role
from app.routers.reports import _describe_name, _mx, _today_mx, get_daily_summary
from app.schemas.reports import (
    CorteInicio, InicioBasicoResponse, PeriodoVentas, PocaExistencia,
    ProductoPocaExistencia, ProductoTop,
)
from app.services.cash_reconciliation import SALES_REPORT_STATUSES, compute_expected_cash

router = APIRouter()

UMBRAL_POCA_EXISTENCIA = 3   # piezas, si la empresa no capturó otro tope
MAX_POCA_EXISTENCIA = 10
MAX_TOP = 5
DIAS_SEMANA = 7


def _sucursal_del_inicio(db: Session, current_user: User, org_id: int, branch_id: Optional[int]) -> Optional[int]:
    """Sucursal que mira el inicio; None = toda la organización.

    ADMIN/DUEÑO/SUPERADMIN: la org entera o la sucursal pedida (404 si no es de
    su org). GERENTE: siempre la suya, el parámetro se ignora (403 sin
    sucursal). Los demás roles: 403.
    """
    if current_user.platform_role == PlatformRole.SUPERADMIN or current_user.role in (Role.ADMINISTRADOR, Role.DUEÑO):
        if branch_id is None:
            return None
        existe = db.query(Branch.id).filter(Branch.id == branch_id, Branch.organization_id == org_id).first()
        if existe is None:
            raise HTTPException(status_code=404, detail="Sucursal no encontrada")
        return branch_id
    if current_user.role == Role.GERENTE:
        if not current_user.branch_id:
            raise HTTPException(status_code=403, detail="Tu usuario no tiene una sucursal asignada")
        return current_user.branch_id
    raise HTTPException(status_code=403, detail="Solo administrador, dueño o gerente pueden ver el inicio")


def _filtros_venta(org_id: int, sucursal: Optional[int], desde: date, hasta: date) -> list:
    filtros = [
        SalesDocument.organization_id == org_id,
        func.date(_mx(SalesDocument.created_at)) >= desde,
        func.date(_mx(SalesDocument.created_at)) <= hasta,
        SalesDocument.status.in_(SALES_REPORT_STATUSES),
    ]
    if sucursal is not None:
        filtros.append(SalesDocument.branch_id == sucursal)
    return filtros


def _periodo(db: Session, org_id: int, sucursal: Optional[int], desde: date, hasta: date) -> PeriodoVentas:
    fila = db.query(
        func.count(SalesDocument.id).label("tickets"),
        func.coalesce(func.sum(SalesDocument.total_amount), 0).label("total"),
    ).filter(*_filtros_venta(org_id, sucursal, desde, hasta)).one()
    return PeriodoVentas(desde=desde, hasta=hasta, total=round(float(fila.total or 0), 2),
                         tickets=int(fila.tickets or 0))


def _top(db: Session, org_id: int, sucursal: Optional[int], desde: date, hasta: date) -> List[ProductoTop]:
    filas = (
        db.query(
            SalesLineItem.description,
            func.sum(SalesLineItem.quantity).label("qty"),
            func.sum(SalesLineItem.total_line).label("importe"),
        )
        .join(SalesDocument, SalesDocument.id == SalesLineItem.document_id)
        .filter(*_filtros_venta(org_id, sucursal, desde, hasta))
        .group_by(SalesLineItem.description)
        .order_by(desc("qty"), SalesLineItem.description)
        .limit(MAX_TOP)
        .all()
    )
    return [
        ProductoTop(nombre=f.description or "", cantidad=round(float(f.qty or 0), 2),
                    total=round(float(f.importe or 0), 2))
        for f in filas
    ]


def _poca_existencia(db: Session, org_id: int, sucursal: Optional[int], umbral: int) -> List[ProductoPocaExistencia]:
    """Variantes activas cuya existencia (sumada entre sucursales) es ≤ umbral.

    Sin sucursal pedida solo cuentan las que venden y siguen activas: la bodega
    de una org multi-sucursal no es "la tienda" (mismo criterio que la valuación).
    """
    existencia = func.sum(StockOnHand.qty_on_hand)
    q = (
        db.query(ProductVariant.id, Product.name, ProductVariant.variant_name, ProductVariant.sku,
                 existencia.label("existencia"))
        .select_from(StockOnHand)
        .join(ProductVariant, ProductVariant.id == StockOnHand.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .join(Branch, Branch.id == StockOnHand.branch_id)
        .filter(
            StockOnHand.organization_id == org_id,
            Product.organization_id == org_id,
            Branch.organization_id == org_id,
            Product.is_active == True,  # noqa: E712
            Product.deleted_at.is_(None),
            ProductVariant.deleted_at.is_(None),
        )
    )
    if sucursal is not None:
        q = q.filter(Branch.id == sucursal)
    else:
        q = q.filter(Branch.can_sell == True, Branch.is_active.is_(True))  # noqa: E712
    filas = (
        q.group_by(ProductVariant.id, Product.name, ProductVariant.variant_name, ProductVariant.sku)
        .having(existencia <= umbral)
        .order_by(existencia.asc(), Product.name)
        .limit(MAX_POCA_EXISTENCIA)
        .all()
    )
    return [
        ProductoPocaExistencia(variant_id=str(f[0]), nombre=_describe_name(f[1], f[2]), sku=f[3] or "",
                               existencia=round(float(f.existencia or 0), 2))
        for f in filas
    ]


def _nombre(user: Optional[User]) -> Optional[str]:
    return (user.full_name or user.username) if user else None


def _corte(db: Session, org_id: int, sucursal: Optional[int]) -> CorteInicio:
    """El turno abierto más reciente; si no hay, el último cerrado."""
    base = db.query(CashSession).join(Branch, Branch.id == CashSession.branch_id).filter(
        Branch.organization_id == org_id,
    )
    if sucursal is not None:
        base = base.filter(CashSession.branch_id == sucursal)
    abierta = (
        base.filter(CashSession.status == CashSessionStatus.OPEN)
        .order_by(CashSession.opened_at.desc(), CashSession.id.desc())
        .first()
    )
    if abierta is not None:
        return CorteInicio(
            estado="abierto", cajera=_nombre(abierta.user), abierto_en=abierta.opened_at,
            efectivo_esperado=round(float(compute_expected_cash(db, abierta).expected), 2),
        )
    cerrada = (
        base.filter(CashSession.status == CashSessionStatus.CLOSED)
        .order_by(CashSession.closed_at.desc(), CashSession.id.desc())
        .first()
    )
    if cerrada is not None:
        return CorteInicio(
            estado="cerrado", cajera=_nombre(cerrada.user), abierto_en=cerrada.opened_at,
            cerrado_en=cerrada.closed_at,
            efectivo_contado=round(float(cerrada.closing_balance or 0), 2),
        )
    return CorteInicio(estado="sin_turno")


@router.get("/inicio-basico", response_model=InicioBasicoResponse)
def inicio_basico(
    branch_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Resumen del Inicio básico: ventas, cobros, top, poca existencia y caja."""
    sucursal = _sucursal_del_inicio(db, current_user, org_id, branch_id)
    hoy = _today_mx()
    ayer = hoy - timedelta(days=1)
    inicio_semana = hoy - timedelta(days=DIAS_SEMANA - 1)

    # `branch_id=0` es "toda la organización" para los roles de oficina en
    # get_daily_summary; el gerente llega aquí ya fijado a su sucursal.
    resumen = get_daily_summary(
        target_date=hoy, branch_id=0 if sucursal is None else sucursal,
        db=db, current_user=current_user, org_id=org_id,
    )
    por_metodo = {str(getattr(m, "value", m)): round(float(v), 2) for m, v in resumen["payments"].items()}

    org = db.query(Organization).filter(Organization.id == org_id).first()
    umbral = org.umbral_poca_existencia if org and org.umbral_poca_existencia is not None else UMBRAL_POCA_EXISTENCIA

    return InicioBasicoResponse(
        branch_id=sucursal,
        hoy=_periodo(db, org_id, sucursal, hoy, hoy),
        ayer=_periodo(db, org_id, sucursal, ayer, ayer),
        semana=_periodo(db, org_id, sucursal, inicio_semana, hoy),
        por_metodo_hoy=por_metodo,
        top_semana=_top(db, org_id, sucursal, inicio_semana, hoy),
        poca_existencia=PocaExistencia(umbral=umbral, productos=_poca_existencia(db, org_id, sucursal, umbral)),
        corte=_corte(db, org_id, sucursal),
    )
```

- [ ] **Step 5: Montar el router**

En `app/main.py` reemplazar:

```python
    inventory, sales, cash, customers, reports, reports_valuacion,
```

por:

```python
    inventory, sales, cash, customers, reports, reports_valuacion, reports_inicio,
```

y reemplazar:

```python
app.include_router(reports_valuacion.router, prefix="/api/reports", tags=["Reportes"])
```

por:

```python
app.include_router(reports_valuacion.router, prefix="/api/reports", tags=["Reportes"])
app.include_router(reports_inicio.router,   prefix="/api/reports", tags=["Reportes"])
```

- [ ] **Step 6: Correr y ver que pasa**

Run: `python3 -m pytest -q -p no:warnings tests/test_reports_inicio_basico.py tests/test_reports_daily_summary.py tests/test_reports_valor_inventario.py`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/routers/reports_inicio.py app/schemas/reports.py app/main.py tests/test_reports_inicio_basico.py
git commit -m "$(cat <<'EOF'
feat(reports): /reports/inicio-basico, el "¿cómo voy?" en una sola llamada

Hoy/ayer/7 días, cobros de hoy por método, top 5, lo que se está acabando
(tope de Empresa, máximo 10) y el estado de la caja. Aislado por org y por
sucursal como la valuación.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf
EOF
)"
```

---

### Task 4: Frontend — `perfilUi` en el store y menú por perfil

**Files:**
- Modify: `frontend/src/types/auth.ts` (tipo `PerfilUi`)
- Modify: `frontend/src/store/enabledModulesStore.ts`
- Create: `frontend/src/components/layout/navPerfilBasico.ts`
- Modify: `frontend/src/components/layout/navVisibility.ts`
- Modify: `frontend/src/components/layout/Sidebar.tsx:607,621`
- Test: `frontend/src/store/__tests__/enabledModulesStore.test.ts` (añadir), `frontend/src/components/layout/__tests__/navPerfilBasico.test.ts`

**Interfaces:**
- Consumes: `perfil_ui` de `/users/me/context` (Tarea 1); `coincideUrl(url, patron)` y `recortarPorPlan` de `navPerfilPlan.ts`.
- Produces:
  - `export type PerfilUi = 'basico' | 'completo'` (`types/auth.ts`).
  - Store: `perfilUi: PerfilUi` (inicial `'completo'`; `'completo'` también al fallar y en `reset`), `leerPerfilUi(crudo: unknown): PerfilUi`, hook `useModoBasico(): boolean`.
  - `OCULTAS_BASICO_SUCURSAL: readonly string[]`, `OCULTAS_BASICO_HQ: readonly string[]`, `urlsOcultasPorPerfil(perfil, esSucursal): readonly string[]`, `recortarPorPerfil(items: NavItem[], perfil: PerfilUi | null | undefined, esSucursal: boolean): NavItem[]`.
  - `NavVisibilityOptions.perfilUi?: PerfilUi | null` (se aplica después del recorte por plan).

- [ ] **Step 1: Escribir las pruebas que fallan**

Añadir al final de `frontend/src/store/__tests__/enabledModulesStore.test.ts`:

```ts
describe('enabledModulesStore.perfilUi', () => {
  it('arranca en completo mientras el contexto no carga', () => {
    expect(useEnabledModulesStore.getState().perfilUi).toBe('completo')
  })

  it('guarda basico cuando el servidor lo manda', async () => {
    get.mockResolvedValue(contexto({ perfil_ui: 'basico' }))
    await useEnabledModulesStore.getState().load()
    expect(useEnabledModulesStore.getState().perfilUi).toBe('basico')
  })

  it.each([undefined, null, 'raro', 'BASICO', 3])('%s (servidor viejo o valor raro) = completo', async (valor) => {
    get.mockResolvedValue(contexto({ perfil_ui: valor }))
    await useEnabledModulesStore.getState().load()
    expect(useEnabledModulesStore.getState().perfilUi).toBe('completo')
  })

  it('si la petición falla, completo (fail-open, Review Focus #1)', async () => {
    get.mockRejectedValue(new Error('red caída'))
    await useEnabledModulesStore.getState().load()
    expect(useEnabledModulesStore.getState().perfilUi).toBe('completo')
    expect(useEnabledModulesStore.getState().loaded).toBe(true)
  })

  it('reset vuelve a completo', async () => {
    get.mockResolvedValue(contexto({ perfil_ui: 'basico' }))
    await useEnabledModulesStore.getState().load()
    useEnabledModulesStore.getState().reset()
    expect(useEnabledModulesStore.getState().perfilUi).toBe('completo')
  })
})
```

Crear `frontend/src/components/layout/__tests__/navPerfilBasico.test.ts`:

```ts
import { describe, it, expect } from 'vitest'

import { ALL_NAV, ROLE_ROUTES, rolesConAcceso } from '../navConfig'
import { visibleNavItems } from '../navVisibility'
import { OCULTAS_BASICO_HQ, OCULTAS_BASICO_SUCURSAL, recortarPorPerfil, urlsOcultasPorPerfil } from '../navPerfilBasico'
import type { PerfilUi, PlanOrg, Role } from '../../../types/auth'

// Kaory, Coqueta, Imaltzin: preset ATLAS_POS (11 módulos) en plan FREE.
const ATLAS_POS = [
  'core', 'pos', 'cash_management', 'catalog', 'inventory', 'returns',
  'pricing', 'payments', 'reports', 'labels', 'crm',
]
const FREE: PlanOrg = { clave: 'FREE', nombre: 'ONE FREE' }
const ULTRA: PlanOrg = { clave: 'ULTRA_PLUS', nombre: 'ULTRA+' }

const menu = (role: Role, perfilUi: PerfilUi | null | undefined, plan: PlanOrg | null = FREE, enabledModules = ATLAS_POS) =>
  visibleNavItems(ALL_NAV, {
    role, allowed: ROLE_ROUTES[role] ?? [], enabledModules, isGastro: false, plan, perfilUi,
  }).map((i) => i.url)

describe('menú en modo básico', () => {
  it('cajera: exactamente seis entradas (spec §4.1)', () => {
    expect([...menu('CAJERO', 'basico')].sort()).toEqual(
      ['/atlas-pos', '/cash-history', '/pos', '/printer-settings', '/products', '/sales'],
    )
  })

  it('administradora: exactamente ocho entradas (spec §4.2)', () => {
    expect([...menu('ADMINISTRADOR', 'basico')].sort()).toEqual(
      ['/cash-history', '/hq/operations', '/hq/reports-hub', '/organization', '/printer-settings', '/products', '/sales', '/users'],
    )
  })

  it('completo con el mismo plan y módulos: igual que sin perfil (las de paga no notan nada)', () => {
    for (const r of ['ADMINISTRADOR', 'DUEÑO', 'GERENTE', 'CAJERO', 'VENDEDOR'] as Role[]) {
      expect(menu(r, 'completo', ULTRA)).toEqual(menu(r, undefined, ULTRA))
      expect(menu(r, 'completo', FREE)).toEqual(menu(r, null, FREE))
    }
  })

  it('FREE forzada a completo recupera el menú de SP2 (Review Focus #4)', () => {
    const urls = menu('CAJERO', 'completo')
    expect(urls).toContain('/customers')
    expect(urls).toContain('/returns')
    expect(urls).toContain('/labels')
  })

  it('una de paga forzada a básico también se recorta', () => {
    expect(menu('ADMINISTRADOR', 'basico', ULTRA)).not.toContain('/hq/control')
    expect(menu('ADMINISTRADOR', 'basico', ULTRA)).not.toContain('/customers')
  })

  it('una FREE gastro conserva mesas y cocina: la lista esconde, no es blanca', () => {
    const urls = menu('CAJERO', 'basico', FREE, [...ATLAS_POS, 'tables', 'kitchen'])
    expect(urls).toContain('/tables')
    expect(urls).toContain('/kitchen')
  })

  it('esconder no es quitar acceso: rolesConAcceso no depende del perfil', () => {
    expect(rolesConAcceso('/customers')).toContain('CAJERO')
    expect(rolesConAcceso('/hq/control')).toContain('ADMINISTRADOR')
  })

  it('sin perfil o completo no se esconde nada; sucursal y HQ tienen su lista', () => {
    expect(urlsOcultasPorPerfil(null, true)).toEqual([])
    expect(urlsOcultasPorPerfil('completo', false)).toEqual([])
    expect(urlsOcultasPorPerfil('basico', true)).toBe(OCULTAS_BASICO_SUCURSAL)
    expect(urlsOcultasPorPerfil('basico', false)).toBe(OCULTAS_BASICO_HQ)
    const item = ALL_NAV.find((n) => n.url === '/customers')!
    expect(recortarPorPerfil([item], 'basico', true)).toEqual([])
    expect(recortarPorPerfil([item], 'completo', true)).toEqual([item])
  })
})
```

- [ ] **Step 2: Correr y ver que falla**

Run: `cd frontend && npx vitest run src/store/__tests__/enabledModulesStore.test.ts src/components/layout/__tests__/navPerfilBasico.test.ts`
Expected: FAIL (`perfilUi` es `undefined`; no se resuelve `../navPerfilBasico`).

- [ ] **Step 3: Tipo y store**

En `frontend/src/types/auth.ts`, después de la interfaz `PlanOrg` añadir:

```ts

/** Perfil de interfaz (modo básico, 2026-10). Lo decide el servidor en /users/me/context. */
export type PerfilUi = 'basico' | 'completo'
```

En `frontend/src/store/enabledModulesStore.ts`:

1. Reemplazar `import type { PlanOrg } from '../types/auth'` por `import type { PerfilUi, PlanOrg } from '../types/auth'`.
2. En `ContextResponse`, después de `campos_producto?: unknown` añadir `perfil_ui?: unknown`.
3. Después de la función `leerPlan` añadir:

```ts

/** Solo 'basico' acorta la interfaz; ausente (servidor viejo) o raro = completo. */
export function leerPerfilUi(crudo: unknown): PerfilUi {
  return crudo === 'basico' ? 'basico' : 'completo'
}
```

4. En `EnabledModulesStore`, después de `camposProducto: CamposProducto` añadir:

```ts
  /** Perfil de interfaz; 'completo' mientras no carga, si falló o si el servidor no lo manda. */
  perfilUi: PerfilUi
```

5. En el estado inicial, después de `camposProducto: TODO_VISIBLE,` añadir `perfilUi: 'completo',`.
6. En el `set({...})` de éxito, después de `camposProducto: leerCamposProducto(r.data?.campos_producto),` añadir `perfilUi: leerPerfilUi(r.data?.perfil_ui),`.
7. En el `catch` y en `reset`, añadir `perfilUi: 'completo'` a cada objeto de `set(...)` (al lado de `camposProducto: TODO_VISIBLE`).
8. Al final del archivo:

```ts

/** `true` cuando la organización ve la interfaz corta (modo básico). */
export const useModoBasico = (): boolean =>
  useEnabledModulesStore((s) => s.perfilUi === 'basico')
```

- [ ] **Step 4: `navPerfilBasico.ts`**

```ts
// frontend/src/components/layout/navPerfilBasico.ts
import type { PerfilUi } from '../../types/auth'
import type { NavItem } from './navVisibility'
import { coincideUrl } from './navPerfilPlan'

/**
 * Perfil de interfaz "básico" (modo básico, spec 2026-10-18 §4): URLs que NO
 * se ven en el menú. Se aplica DESPUÉS del gating por rol, módulo y plan, y
 * solo esconde: la URL sigue abriendo (`RutaPorRol` no cambia). Es una lista
 * de lo que sobra y no una lista blanca, para que una FREE de otro giro
 * (gastro) conserve sus pantallas.
 *
 * Para esconder algo más en básico, agrégalo aquí (CLAUDE.md §5).
 */

/** Cajera y gerente: Cobrar · Mis ventas · Corte · Productos · Impresora · Mi día. */
export const OCULTAS_BASICO_SUCURSAL: readonly string[] = [
  '/returns',             // se llega desde el ticket en Mis ventas y desde el POS
  '/labels', '/scanner', '/customers', '/hr/me',
  '/reports', '/hq/valor-inventario',   // gerente
]

/** Dueña: Inicio · Mis ventas · Corte · Productos · Reportes · Empresa · Usuarios · Impresora. */
export const OCULTAS_BASICO_HQ: readonly string[] = [
  '/hq/control', '/admin/catalog', '/departments', '/brands', '/labels', '/scanner',
  '/customers', '/hq/branches', '/inventory', '/hq/inventory',
  '/hq/sales', '/hq/returns',          // Mis ventas (/sales) es global para la dueña y devuelve por ticket
  '/hq/valor-inventario',              // entra como tarjeta en el Inicio básico
  '/mobile/owner', '/hr/me', '/ai',
  '/quotes', '/quotes/new', '/seguimiento', '/purchases', '/expenses', '/purchasing',
]

export function urlsOcultasPorPerfil(perfil: PerfilUi | null | undefined, esSucursal: boolean): readonly string[] {
  if (perfil !== 'basico') return []
  return esSucursal ? OCULTAS_BASICO_SUCURSAL : OCULTAS_BASICO_HQ
}

export function recortarPorPerfil(items: NavItem[], perfil: PerfilUi | null | undefined, esSucursal: boolean): NavItem[] {
  const ocultas = urlsOcultasPorPerfil(perfil, esSucursal)
  if (ocultas.length === 0) return items
  return items.filter((n) => !ocultas.some((p) => coincideUrl(n.url, p)))
}
```

- [ ] **Step 5: `visibleNavItems` y Sidebar**

En `frontend/src/components/layout/navVisibility.ts`:

1. Reemplazar las dos primeras líneas:

```ts
import type { PlanOrg, Role } from '../../types/auth'
import { recortarPorPlan } from './navPerfilPlan'
```

por:

```ts
import type { PerfilUi, PlanOrg, Role } from '../../types/auth'
import { recortarPorPlan } from './navPerfilPlan'
import { recortarPorPerfil } from './navPerfilBasico'
```

2. En `NavVisibilityOptions`, después de `plan?: PlanOrg | null` añadir:

```ts
  /** Perfil de interfaz. 'basico' esconde lo de navPerfilBasico; null/undefined/'completo' = nada. */
  perfilUi?: PerfilUi | null
```

3. Reemplazar:

```ts
  const { role, allowed, enabledModules, isGastro, plan } = opts
```

por:

```ts
  const { role, allowed, enabledModules, isGastro, plan, perfilUi } = opts
```

4. Reemplazar:

```ts
  // El perfil por plan va al final: solo esconde entre lo que ya pasó rol y módulo.
  return recortarPorPlan(porModulo, plan).sort((a, b) => a.sort - b.sort)
```

por:

```ts
  // Plan y perfil van al final: solo esconden entre lo que ya pasó rol y módulo.
  const porPlan = recortarPorPlan(porModulo, plan)
  return recortarPorPerfil(porPlan, perfilUi, isBranchRole).sort((a, b) => a.sort - b.sort)
```

En `frontend/src/components/layout/Sidebar.tsx` reemplazar:

```tsx
  const { enabledModules, preset, loaded, load, plan } = useEnabledModulesStore()
```

por:

```tsx
  const { enabledModules, preset, loaded, load, plan, perfilUi } = useEnabledModulesStore()
```

y:

```tsx
  const items = visibleNavItems(ALL_NAV, { role, allowed, enabledModules, isGastro, plan })
```

por:

```tsx
  const items = visibleNavItems(ALL_NAV, { role, allowed, enabledModules, isGastro, plan, perfilUi })
```

- [ ] **Step 6: Correr y ver que pasa**

Run: `cd frontend && npx vitest run src/store src/components/layout`
Expected: PASS (incluidas `navPerfilPlan.test.ts`, `navVisibility.test.ts` y `navConfig.test.ts` sin tocar).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/types/auth.ts frontend/src/store/enabledModulesStore.ts \
  frontend/src/store/__tests__/enabledModulesStore.test.ts \
  frontend/src/components/layout/navPerfilBasico.ts frontend/src/components/layout/navVisibility.ts \
  frontend/src/components/layout/Sidebar.tsx frontend/src/components/layout/__tests__/navPerfilBasico.test.ts
git commit -m "$(cat <<'EOF'
feat(modo-basico): perfilUi en el store y menú de 6 (cajera) y 8 (dueña)

useModoBasico() lee perfil_ui del contexto (completo mientras carga o si
falla). navPerfilBasico esconde después de rol, módulo y plan; las URLs
siguen abriendo.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf
EOF
)"
```

---

### Task 5: Frontend — formulario de producto corto y listas de Productos en básico

**Files:**
- Modify: `frontend/src/components/products/ProductBasicsSection.tsx` (reescrito completo)
- Modify: `frontend/src/components/products/ProductCommercialSection.tsx`
- Modify: `frontend/src/components/products/ProductTieredPricesSection.tsx`
- Modify: `frontend/src/components/products/FormularioProducto.tsx`
- Modify: `frontend/src/pages/inventory/Products.tsx` (`ProductsHQView`)
- Modify: `frontend/src/components/branch/ProductsBranchView.tsx`
- Test: `frontend/src/components/products/__tests__/FormularioProducto.test.tsx` (añadir), `frontend/src/pages/inventory/__tests__/ProductsBasico.test.tsx`

**Interfaces:**
- Consumes: `useModoBasico()`, `perfilUi`, `camposProducto` (Tarea 4); `campoVisible(campos, clave, valorActual)` de `camposProducto.ts`; ocultos de básico de la Tarea 2 (`brand_id, description, unit, image_url, tax_rate, packaging_units, variants`).
- Produces: `ProductBasicsSection` acepta `campos?: CamposProducto`; `ProductTieredPricesSection` acepta `titulo?: string` (default `'Precios escalonados'`). En `FormularioProducto`: básico + una sola sucursal → matriz no se pinta, la sucursal va `enabled: true` y `initial_stock_branch_id` = su id.

- [ ] **Step 1: Escribir las pruebas que fallan**

En `frontend/src/components/products/__tests__/FormularioProducto.test.tsx`:

1. Después de `const { useEnabledModulesStore } = await import('../../../store/enabledModulesStore')` añadir:

```tsx
const { organizationApi } = await import('../../../api/organization')
```

2. En `beforeEach`, reemplazar:

```tsx
  useEnabledModulesStore.setState({ enabledModules: ['core'], loaded: true, camposProducto: { visibles: [], ocultos: [] } } as never)
```

por:

```tsx
  useEnabledModulesStore.setState({ enabledModules: ['core'], loaded: true, perfilUi: 'completo', camposProducto: { visibles: [], ocultos: [] } } as never)
```

3. Añadir al final del archivo:

```tsx
// Lo que manda el servidor a una FREE (Tarea 2): ficha + OCULTOS_BASICO.
const OCULTOS_BASICO = ['gender', 'model', 'material', 'brand_id', 'description', 'unit', 'image_url', 'tax_rate', 'packaging_units', 'variants']
const enBasico = () => useEnabledModulesStore.setState({
  enabledModules: ['core', 'variants'], loaded: true, perfilUi: 'basico',
  camposProducto: { visibles: [], ocultos: OCULTOS_BASICO },
} as never)

describe('FormularioProducto en modo básico', () => {
  it('alta corta de la dueña con una sucursal: sin matriz, la sucursal va sola (Review Focus #3)', async () => {
    enBasico()
    api.create.mockResolvedValue({ ...producto, id: 'nuevo' })
    render(<MemoryRouter><FormularioProducto mode="create" presentacion="pagina" onDone={() => {}} onCancel={() => {}} /></MemoryRouter>)
    await screen.findByText('Crear producto')
    for (const oculto of ['Marca', 'Unidad', 'Descripción', 'URL de imagen', 'Tasa IVA (%)', 'Empaques / Cajas', 'Activación por sucursal']) {
      expect(screen.queryByText(oculto)).toBeNull()
    }
    expect(screen.getByText('Precio por cantidad')).toBeTruthy()
    expect(screen.getByText('Departamento')).toBeTruthy()
    escribir(/^Nombre/, 'Blusa'); escribir(/^SKU/, 'blu'); escribir(/^Precio/, '120'); escribir(/^Costo/, '60')
    escribir(/Stock inicial/, '3')
    fireEvent.click(screen.getByText('Crear producto'))
    await waitFor(() => expect(api.create).toHaveBeenCalled())
    const payload = api.create.mock.calls[0][0]
    expect(payload.target_branch_ids).toEqual([20])
    expect(payload.branch_id).toBe(20)
    expect(payload.initial_stock).toBe(3)
  })

  it('con dos sucursales la matriz sigue y nada se marca solo (Review Focus #3)', async () => {
    enBasico()
    vi.mocked(organizationApi.getBranches).mockResolvedValueOnce([
      { id: 20, name: 'Roma', branch_type: 'STORE', is_headquarters: false },
      { id: 21, name: 'Condesa', branch_type: 'STORE', is_headquarters: false },
    ] as never)
    render(<MemoryRouter><FormularioProducto mode="create" presentacion="pagina" onDone={() => {}} onCancel={() => {}} /></MemoryRouter>)
    await screen.findByText('Crear producto')
    expect(screen.getByText('Activación por sucursal')).toBeTruthy()
    escribir(/^Nombre/, 'Blusa'); escribir(/^SKU/, 'blu'); escribir(/^Precio/, '120'); escribir(/^Costo/, '60')
    fireEvent.click(screen.getByText('Crear producto'))
    expect(await screen.findByText('Activa al menos una sucursal')).toBeTruthy()
    expect(api.create).not.toHaveBeenCalled()
  })

  it('edición: un producto con marca y descripción las sigue mostrando (Review Focus #2)', async () => {
    enBasico()
    api.getBrands.mockResolvedValueOnce([{ id: 'b1', name: 'Nike' }] as never)
    api.getById.mockResolvedValue({
      ...producto, brand_id: 'b1', description: 'Algodón peinado',
      variants: [producto.variants[0]], packaging_units: [],
    })
    render(<MemoryRouter><FormularioProducto mode="edit" productId="p1" presentacion="pagina" onDone={() => {}} onCancel={() => {}} /></MemoryRouter>)
    await screen.findByText('Guardar cambios')
    expect(screen.getByText('Marca')).toBeTruthy()
    expect((screen.getByLabelText('Descripción') as HTMLTextAreaElement).value).toBe('Algodón peinado')
    expect(screen.queryByText('Unidad')).toBeNull()          // trae 'pza', el valor por defecto
    expect(screen.queryByText('Empaques / Cajas')).toBeNull() // sin empaques
  })

  it('edición: los empaques que ya existen se ven aunque básico los esconda', async () => {
    enBasico()
    api.getById.mockResolvedValue({ ...producto, variants: [producto.variants[0]] })
    render(<MemoryRouter><FormularioProducto mode="edit" productId="p1" presentacion="pagina" onDone={() => {}} onCancel={() => {}} /></MemoryRouter>)
    await screen.findByText('Guardar cambios')
    expect(screen.getByText('Empaques / Cajas')).toBeTruthy()
  })
})
```

Crear `frontend/src/pages/inventory/__tests__/ProductsBasico.test.tsx`:

```tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, cleanup, waitFor } from '@testing-library/react'

const api = vi.hoisted(() => ({
  list: vi.fn(async () => ({ items: [], total: 0 })),
  getDepartments: vi.fn(async () => []),
  barcodesMissingCount: vi.fn(async () => 4),
  getCatalogKpis: vi.fn(async () => null),
}))
vi.mock('../../../api/products', () => ({ productsApi: api }))
vi.mock('../../../api/inventory', () => ({ inventoryApi: {} }))
vi.mock('../../../api/organization', () => ({ organizationApi: { getBranches: vi.fn(async () => []) } }))

import { Products } from '../Products'
import { useAuthStore } from '../../../store/authStore'
import { useEnabledModulesStore } from '../../../store/enabledModulesStore'
import { useBranchCountStore } from '../../../store/branchCountStore'

const admin = { id: 1, username: 'admin', role: 'ADMINISTRADOR', branch_id: null, branch_name: null }
const cajera = { id: 2, username: 'caja', role: 'CAJERO', branch_id: 20, branch_name: 'Roma' }
const perfil = (perfilUi: 'basico' | 'completo') =>
  useEnabledModulesStore.setState({ loaded: true, perfilUi } as never)
const pintar = () => render(<MemoryRouter><Products /></MemoryRouter>)

beforeEach(() => {
  vi.clearAllMocks()
  useBranchCountStore.setState({ count: 1 })
})
afterEach(cleanup)

describe('Productos HQ', () => {
  it('completo: importar, etiquetas CSV, generar códigos y vista de rejilla', async () => {
    useAuthStore.setState({ user: admin } as never); perfil('completo')
    pintar()
    expect(await screen.findByLabelText('Generar códigos de barras faltantes (4)')).toBeTruthy()
    expect(screen.getByLabelText('Importar productos')).toBeTruthy()
    expect(screen.getByLabelText('Descargar etiquetas CSV')).toBeTruthy()
    expect(screen.getByLabelText('Vista cuadrícula')).toBeTruthy()
  })

  it('básico: solo Nuevo producto (no se montan los demás)', async () => {
    useAuthStore.setState({ user: admin } as never); perfil('basico')
    pintar()
    expect(await screen.findByLabelText('Nuevo producto')).toBeTruthy()
    await waitFor(() => expect(api.barcodesMissingCount).toHaveBeenCalled())
    expect(screen.queryByLabelText('Importar productos')).toBeNull()
    expect(screen.queryByLabelText('Descargar etiquetas CSV')).toBeNull()
    expect(screen.queryByLabelText(/Generar códigos/)).toBeNull()
    expect(screen.queryByLabelText('Vista cuadrícula')).toBeNull()
  })
})

describe('Productos de sucursal (cajera)', () => {
  it('completo: Plantilla e Importar Excel', async () => {
    useAuthStore.setState({ user: cajera } as never); perfil('completo')
    pintar()
    expect(await screen.findByText('Importar Excel')).toBeTruthy()
    expect(screen.getByText('Plantilla')).toBeTruthy()
  })

  it('básico: sin plantilla ni importador; Nuevo producto sigue', async () => {
    useAuthStore.setState({ user: cajera } as never); perfil('basico')
    pintar()
    expect(await screen.findByText('Nuevo producto')).toBeTruthy()
    expect(screen.queryByText('Importar Excel')).toBeNull()
    expect(screen.queryByText('Plantilla')).toBeNull()
  })
})
```

- [ ] **Step 2: Correr y ver que falla**

Run: `cd frontend && npx vitest run src/components/products/__tests__/FormularioProducto.test.tsx src/pages/inventory/__tests__/ProductsBasico.test.tsx`
Expected: FAIL en las 4 pruebas nuevas del formulario ('Marca' sí se pinta, no existe 'Precio por cantidad') y en las 2 de básico de Productos (el importador sigue).

- [ ] **Step 3: `ProductBasicsSection` con `campos`**

Reemplazar el archivo completo por:

```tsx
import { campoVisible, TODO_VISIBLE, type CamposProducto } from './camposProducto'
import type { ProductErrors, ProductFormValue, SetField } from './types'

interface Props {
  value: ProductFormValue
  onChange: SetField
  errors: ProductErrors
  /** Pide la sugerencia de SKU. Sin este prop el botón no se pinta. */
  onSuggestSku?: () => void
  suggestingSku?: boolean
  /** Qué campos ve este giro/perfil; sin la prop se ve todo. */
  campos?: CamposProducto
}

const UNIDADES = ['pza', 'kg', 'lt', 'mt', 'caja', 'par', 'srv']

export function ProductBasicsSection({ value, onChange, errors, onSuggestSku, suggestingSku, campos = TODO_VISIBLE }: Props) {
  // 'pza' es el valor por defecto: no cuenta como "ya trae unidad".
  const verUnidad = campoVisible(campos, 'unit', value.unit !== 'pza' ? value.unit : null)
  return (
    <section className="space-y-3">
      <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wide">Básicos</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <label className="text-xs text-slate-400 space-y-1">
          Nombre *
          <input className="dax-input w-full" value={value.name}
            onChange={(e) => onChange('name', e.target.value)} />
          {errors.name && <span className="text-rose-400 text-[11px]">{errors.name}</span>}
        </label>
        <label className="text-xs text-slate-400 space-y-1">
          SKU *
          <span className="flex gap-2">
            <input className="dax-input w-full font-mono" value={value.sku}
              onChange={(e) => onChange('sku', e.target.value.toUpperCase().trim())} />
            {onSuggestSku && (
              // La sugerencia NUNCA se aplica sola: el botón pregunta antes de
              // pisar lo que el usuario escribió (ver ProductForm).
              <button type="button" className="dax-btn-secondary text-[11px] whitespace-nowrap"
                onClick={onSuggestSku} disabled={suggestingSku}>
                {suggestingSku
                  ? <i className="fa-solid fa-spinner fa-spin" />
                  : <><i className="fa-solid fa-wand-magic-sparkles mr-1" />Sugerir</>}
              </button>
            )}
          </span>
          {errors.sku && <span className="text-rose-400 text-[11px]">{errors.sku}</span>}
        </label>
        <label className="text-xs text-slate-400 space-y-1">
          Código de barras
          <input className="dax-input w-full font-mono" value={value.barcode}
            onChange={(e) => onChange('barcode', e.target.value)} />
        </label>
        {verUnidad && (
          <label className="text-xs text-slate-400 space-y-1">
            Unidad
            <select className="dax-input w-full" value={value.unit}
              onChange={(e) => onChange('unit', e.target.value)}>
              {UNIDADES.map((u) => <option key={u} value={u}>{u}</option>)}
              {/* Un producto viejo con una unidad fuera de la lista no se queda sin opción. */}
              {value.unit && !UNIDADES.includes(value.unit) && <option value={value.unit}>{value.unit}</option>}
            </select>
          </label>
        )}
        {campoVisible(campos, 'description', value.description) && (
          <label className="text-xs text-slate-400 space-y-1 md:col-span-2">
            Descripción
            <textarea className="dax-input w-full" rows={2} value={value.description}
              onChange={(e) => onChange('description', e.target.value)} />
          </label>
        )}
        {campoVisible(campos, 'image_url', value.image_url) && (
          <label className="text-xs text-slate-400 space-y-1 md:col-span-2">
            URL de imagen
            <input className="dax-input w-full" placeholder="https://..." value={value.image_url}
              onChange={(e) => onChange('image_url', e.target.value)} />
          </label>
        )}
      </div>
    </section>
  )
}
```

- [ ] **Step 4: Marca y tasa de IVA por `campos`; título de escalones**

En `ProductCommercialSection.tsx` reemplazar:

```tsx
        <label className="text-xs text-slate-400 space-y-1">
          Marca
          <select className="dax-input w-full" value={value.brand_id}
            onChange={(e) => onChange('brand_id', e.target.value)}>
            <option value="">— Ninguna —</option>
            {brands.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
        </label>
```

por:

```tsx
        {campoVisible(campos, 'brand_id', value.brand_id) && (
          <label className="text-xs text-slate-400 space-y-1">
            Marca
            <select className="dax-input w-full" value={value.brand_id}
              onChange={(e) => onChange('brand_id', e.target.value)}>
              <option value="">— Ninguna —</option>
              {brands.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
          </label>
        )}
```

y reemplazar:

```tsx
        {value.has_iva && (
          <label className="text-xs text-slate-400 space-y-1">
```

por:

```tsx
        {/* En básico la tasa se queda en 16 y no se pinta, salvo que el producto ya traiga otra. */}
        {value.has_iva && campoVisible(campos, 'tax_rate', Number(value.tax_rate) !== 16 ? value.tax_rate : null) && (
          <label className="text-xs text-slate-400 space-y-1">
```

En `ProductTieredPricesSection.tsx` reemplazar:

```tsx
  /** Copy de ayuda opcional bajo el header. */
  help?: string
}

export function ProductTieredPricesSection({ prices, onChange, errors, help }: Props) {
```

por:

```tsx
  /** Copy de ayuda opcional bajo el header. */
  help?: string
  /** Encabezado de la sección; el modo básico lo dice más llano. */
  titulo?: string
}

export function ProductTieredPricesSection({ prices, onChange, errors, help, titulo = 'Precios escalonados' }: Props) {
```

y reemplazar:

```tsx
        <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wide">Precios escalonados</h2>
```

por:

```tsx
        <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wide">{titulo}</h2>
```

- [ ] **Step 5: `FormularioProducto`**

1. Reemplazar:

```tsx
import { useCamposProducto, useEnabledModulesStore } from '../../store/enabledModulesStore'
```

por:

```tsx
import { useCamposProducto, useEnabledModulesStore, useModoBasico } from '../../store/enabledModulesStore'
```

y después de `import { ProductImageUploader } from './ProductImageUploader'` añadir:

```tsx
import { campoVisible } from './camposProducto'
```

2. Después de `  const campos = useCamposProducto()` añadir:

```tsx
  const modoBasico = useModoBasico()
```

3. Reemplazar:

```tsx
      loaders.push(organizationApi.getBranches().then((bchs) => {
        if (cancelled) return
        setBranches(bchs)
        const init: Record<number, BranchActivation> = {}
        for (const b of bchs) init[b.id] = { enabled: false, is_active_pos: true, is_active_hq: false, is_visible: true }
        setBranchActivation(init)
      }))
```

por:

```tsx
      loaders.push(organizationApi.getBranches().then((bchs) => {
        if (cancelled) return
        setBranches(bchs)
        // Modo básico con una sola sucursal: la matriz no se pinta, así que la
        // sucursal va marcada y es el destino de la existencia inicial.
        const unica = modoBasico && bchs.length === 1
        const init: Record<number, BranchActivation> = {}
        for (const b of bchs) init[b.id] = { enabled: unica, is_active_pos: true, is_active_hq: false, is_visible: true }
        setBranchActivation(init)
        if (unica && mode === 'create') setForm((f) => ({ ...f, initial_stock_branch_id: String(bchs[0].id) }))
      }))
```

4. Reemplazar:

```tsx
  }, [mode, productId, variantId, isAdmin, userBranchId, user?.branch_name])
```

por:

```tsx
  }, [mode, productId, variantId, isAdmin, userBranchId, user?.branch_name, modoBasico])
```

5. Después de `  const cta = mode === 'create' ? 'Crear producto' : 'Guardar cambios'` añadir:

```tsx
  // Modo básico: con una sola sucursal la matriz sobra (ya va marcada); tallas
  // y empaques se esconden salvo que el producto ya los tenga (nada se apaga).
  const matrizOculta = modoBasico && branches.length === 1
  const muestraTallas = hasVariantsModule && campoVisible(campos, 'variants', (loaded?.variants?.length ?? 0) > 1 ? 'si' : null)
```

6. Reemplazar el bloque:

```tsx
      <ProductBasicsSection value={form} onChange={setField} errors={errors} onSuggestSku={sugerirSku} suggestingSku={sugiriendoSku} />
      {mode === 'edit' && loaded && (
        <ProductImageUploader product={loaded} onUpdated={(p) => { setLoaded(p); setField('image_url', p.image_url ?? '') }} />
      )}
      <ProductCommercialSection value={form} onChange={setField} errors={errors} departments={departments} brands={brands} campos={campos} />
      <ProductTieredPricesSection prices={prices} onChange={setPrices} errors={errors}
        help="Para precios por cantidad (mayoreo, promo). Se aplica sobre el precio base." />
      <ProductPackagingSection packagings={packagings} onChange={setPackagings} errors={errors} />
      {mode === 'create' && hasVariantsModule && (
```

por:

```tsx
      <ProductBasicsSection value={form} onChange={setField} errors={errors} onSuggestSku={sugerirSku} suggestingSku={sugiriendoSku} campos={campos} />
      {mode === 'edit' && loaded && campoVisible(campos, 'image_url', loaded.image_url) && (
        <ProductImageUploader product={loaded} onUpdated={(p) => { setLoaded(p); setField('image_url', p.image_url ?? '') }} />
      )}
      <ProductCommercialSection value={form} onChange={setField} errors={errors} departments={departments} brands={brands} campos={campos} />
      <ProductTieredPricesSection prices={prices} onChange={setPrices} errors={errors}
        titulo={modoBasico ? 'Precio por cantidad' : undefined}
        help={modoBasico
          ? 'Ej.: «Mayoreo» a partir de 6 piezas, a $45 cada una.'
          : 'Para precios por cantidad (mayoreo, promo). Se aplica sobre el precio base.'} />
      {campoVisible(campos, 'packaging_units', packagings.length > 0 ? 'si' : null) && (
        <ProductPackagingSection packagings={packagings} onChange={setPackagings} errors={errors} />
      )}
      {mode === 'create' && muestraTallas && (
```

7. Reemplazar:

```tsx
      {mode === 'create' && isAdmin && (
        <ProductBranchMatrixSection branches={branches} activation={branchActivation} onToggle={toggleBranch} onSetAll={setAllBranches} errors={errors} />
      )}
      {mode === 'create' && (
        <ProductInitialStockSection value={form} onChange={setField} errors={errors} branches={branches} enabledBranchIds={enabledBranchIds}
          lockedBranchId={!isAdmin && userBranchId ? userBranchId : undefined}
          perVariantTotal={hasVariantsModule && variantRows.length > 0 ? total : null}
          footer={isAdmin ? 'Para existencia en varias sucursales, usa Inventario después de crear.' : 'La existencia se aplica a tu sucursal.'} />
      )}
      {mode === 'edit' && hasVariantsModule && loaded && <ProductVariantsEditor product={loaded} onChanged={alCambiarTallas} />}
```

por:

```tsx
      {mode === 'create' && isAdmin && !matrizOculta && (
        <ProductBranchMatrixSection branches={branches} activation={branchActivation} onToggle={toggleBranch} onSetAll={setAllBranches} errors={errors} />
      )}
      {mode === 'create' && (
        <ProductInitialStockSection value={form} onChange={setField} errors={errors} branches={branches} enabledBranchIds={enabledBranchIds}
          lockedBranchId={!isAdmin && userBranchId ? userBranchId : matrizOculta ? branches[0].id : undefined}
          perVariantTotal={hasVariantsModule && variantRows.length > 0 ? total : null}
          footer={isAdmin
            ? (matrizOculta ? 'La existencia se aplica a tu tienda.' : 'Para existencia en varias sucursales, usa Inventario después de crear.')
            : 'La existencia se aplica a tu sucursal.'} />
      )}
      {mode === 'edit' && muestraTallas && loaded && <ProductVariantsEditor product={loaded} onChanged={alCambiarTallas} />}
```

- [ ] **Step 6: Productos HQ en básico**

En `frontend/src/pages/inventory/Products.tsx`:

1. Después de `import { useEsTelefono } from '../../hooks/useIsMobile'` añadir:

```tsx
import { useModoBasico } from '../../store/enabledModulesStore'
```

2. En `ProductsHQView`, después de `  const esTelefono = useEsTelefono()` añadir:

```tsx
  // Modo básico: sin importador, etiquetas CSV, códigos ni rejilla (render condicional).
  const modoBasico = useModoBasico()
```

3. Reemplazar:

```tsx
              {canEdit && (
                <>
                  <button
                    onClick={() => setShowImport(true)}
```

por:

```tsx
              {canEdit && (
                <>
                  {!modoBasico && (
                  <>
                  <button
                    onClick={() => setShowImport(true)}
```

4. Reemplazar:

```tsx
                      <span className="hidden sm:inline">Generar códigos </span>({codigosFaltantes})
                    </button>
                  )}
                  <button
                    onClick={handleNewProductClick}
```

por:

```tsx
                      <span className="hidden sm:inline">Generar códigos </span>({codigosFaltantes})
                    </button>
                  )}
                  </>
                  )}
                  <button
                    onClick={handleNewProductClick}
```

5. Reemplazar:

```tsx
              <div className="flex items-center bg-slate-800 rounded-lg border border-slate-700/50 p-0.5">
```

por:

```tsx
              {!modoBasico && (
              <div className="flex items-center bg-slate-800 rounded-lg border border-slate-700/50 p-0.5">
```

6. Reemplazar:

```tsx
                  <i className="fa-solid fa-grip w-4 text-xs" />
                </button>
              </div>
```

por:

```tsx
                  <i className="fa-solid fa-grip w-4 text-xs" />
                </button>
              </div>
              )}
```

- [ ] **Step 7: Productos de sucursal en básico**

En `frontend/src/components/branch/ProductsBranchView.tsx`:

1. Después de `import { useAuthStore } from '../../store/authStore'` añadir:

```tsx
import { useModoBasico } from '../../store/enabledModulesStore'
```

2. Reemplazar:

```tsx
  const [showImport, setShowImport] = useState(false)
```

por:

```tsx
  const [showImport, setShowImport] = useState(false)
  // Modo básico: sin plantilla ni importador de Excel (render condicional).
  const modoBasico = useModoBasico()
```

3. Reemplazar:

```tsx
          <div className="flex items-center gap-2">
            <button
              onClick={downloadTemplate}
```

por:

```tsx
          <div className="flex items-center gap-2">
            {!modoBasico && (
            <>
            <button
              onClick={downloadTemplate}
```

4. Reemplazar:

```tsx
              <i className="fa-solid fa-file-import" />
              Importar Excel
            </button>
```

por:

```tsx
              <i className="fa-solid fa-file-import" />
              Importar Excel
            </button>
            </>
            )}
```

- [ ] **Step 8: Correr y ver que pasa**

Run: `cd frontend && npx vitest run src/components/products src/pages/inventory src/pages/__tests__ src/__tests__`
Expected: PASS (incluidas `responsivoOla2.test.ts`, `overlaysFueraDelKit.test.ts` y `unSoloFormularioDeProducto.test.ts`).

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/products frontend/src/pages/inventory/Products.tsx \
  frontend/src/pages/inventory/__tests__/ProductsBasico.test.tsx frontend/src/components/branch/ProductsBranchView.tsx
git commit -m "$(cat <<'EOF'
feat(modo-basico): formulario de producto corto y Productos sin importador

En básico el formulario esconde marca, descripción, unidad, foto, tasa,
empaques y tallas (salvo que el producto ya los traiga); con una sola
sucursal la matriz no se pinta y la sucursal va marcada. Productos HQ y de
sucursal dejan solo Nuevo producto.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf
EOF
)"
```

---

### Task 6: Frontend — POS en básico (`opcionesPorPerfil`) y alta rápida corta

**Files:**
- Create: `frontend/src/pages/pos/opcionesPos.ts`
- Create: `frontend/src/components/pos/AltaRapidaProducto.tsx`
- Modify: `frontend/src/components/pos/CartPanel.tsx`
- Modify: `frontend/src/components/pos/ProductSearch.tsx:1-12,74-76,395,465`
- Modify: `frontend/src/pages/pos/POS.tsx:1,41,57,936-948`
- Test: `frontend/src/pages/pos/__tests__/opcionesPos.test.ts`, `frontend/src/components/pos/__tests__/CartPanelPerfil.test.tsx`, `frontend/src/components/pos/__tests__/AltaRapidaProducto.test.tsx`, `frontend/src/__tests__/modoBasico.test.ts`

**Interfaces:**
- Consumes: `useEnabledModulesStore((s) => s.perfilUi)` (Tarea 4); `FormularioProducto` corto (Tarea 5); `Modal` de `components/ui/Modal`.
- Produces:
  - `interface OpcionesPos { descuentos: boolean; cliente: boolean; usd: boolean; editarProducto: boolean; forzarPieza: boolean; altaCorta: boolean }`
  - `opcionesPorPerfil(perfil: PerfilUi | null | undefined): OpcionesPos` (completo: todo `true` salvo `altaCorta: false`; básico: todo `false` salvo `altaCorta: true`).
  - `export default function AltaRapidaProducto({ onClose, onCreado }: { onClose: () => void; onCreado: () => void })` (se carga con `lazy()`).

- [ ] **Step 1: Escribir las pruebas que fallan**

```ts
// frontend/src/pages/pos/__tests__/opcionesPos.test.ts
import { describe, it, expect } from 'vitest'
import { opcionesPorPerfil } from '../opcionesPos'

describe('opcionesPorPerfil', () => {
  it('completo: todo como hoy y alta con la ficha de siempre', () => {
    expect(opcionesPorPerfil('completo')).toEqual({
      descuentos: true, cliente: true, usd: true, editarProducto: true, forzarPieza: true, altaCorta: false,
    })
  })

  it('básico: sin descuentos, cliente, dólares, edición de producto ni forzar pieza; alta corta', () => {
    expect(opcionesPorPerfil('basico')).toEqual({
      descuentos: false, cliente: false, usd: false, editarProducto: false, forzarPieza: false, altaCorta: true,
    })
  })

  it('sin perfil (contexto sin cargar) = completo', () => {
    expect(opcionesPorPerfil(null)).toEqual(opcionesPorPerfil('completo'))
    expect(opcionesPorPerfil(undefined)).toEqual(opcionesPorPerfil('completo'))
  })

  it('devuelve una copia: mutarla no cambia la siguiente llamada', () => {
    const o = opcionesPorPerfil('basico')
    o.descuentos = true
    expect(opcionesPorPerfil('basico').descuentos).toBe(false)
  })
})
```

```tsx
// frontend/src/components/pos/__tests__/CartPanelPerfil.test.tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'

vi.mock('../../../api/products', () => ({ productsApi: { getById: vi.fn(async () => null) } }))

const { CartPanel } = await import('../CartPanel')
const { usePOSStore } = await import('../../../store/posStore')
const { useEnabledModulesStore } = await import('../../../store/enabledModulesStore')
const { useExchangeRateStore } = await import('../../../store/exchangeRateStore')

const blusa = { product_id: 'p1', sku: 'BLU-1', name: 'Blusa', price: 100, base_price: 100, quantity: 1, discount: 0, subtotal: 100 }
const pintar = () => render(
  <CartPanel onPay={() => {}} onPark={() => {}} customerName={null} onClearCustomer={() => {}}
    sessionLocked={false} onOpenSession={() => {}} />,
)

beforeEach(() => {
  usePOSStore.setState({ cart: [blusa], globalDiscount: 0 } as never)
  useExchangeRateStore.setState({ rate: 18 } as never)
})
afterEach(cleanup)

describe('CartPanel según el perfil', () => {
  it('completo: Cliente, descuentos y dólares', () => {
    useEnabledModulesStore.setState({ loaded: true, perfilUi: 'completo' } as never)
    pintar()
    expect(screen.getByTitle('Asignar cliente a la venta')).toBeTruthy()
    expect(screen.getByTitle('Descuento')).toBeTruthy()
    expect(screen.getByText('Descuento global')).toBeTruthy()
    expect(screen.getByText(/T\.C\. 18\.00/)).toBeTruthy()
  })

  it('básico: sin Cliente, descuentos ni dólares; cobrar y pausar siguen', () => {
    useEnabledModulesStore.setState({ loaded: true, perfilUi: 'basico' } as never)
    pintar()
    expect(screen.queryByTitle('Asignar cliente a la venta')).toBeNull()
    expect(screen.queryByTitle('Descuento')).toBeNull()
    expect(screen.queryByText('Descuento global')).toBeNull()
    expect(screen.queryByText(/T\.C\./)).toBeNull()
    for (const t of ['Efectivo', 'Tarjeta', 'Transfer.', 'Mixto', 'Aplicar caja']) expect(screen.getByText(t)).toBeTruthy()
    expect(screen.getByTitle('Guardar como pedido pendiente')).toBeTruthy()
  })

  it('contexto sin cargar: se pinta completo, nunca un básico a medias (Review Focus #1)', () => {
    useEnabledModulesStore.getState().reset()
    pintar()
    expect(screen.getByTitle('Asignar cliente a la venta')).toBeTruthy()
    expect(screen.getByText('Descuento global')).toBeTruthy()
  })

  it('básico con un ticket pausado que ya traía descuento: el descuento se sigue viendo', () => {
    useEnabledModulesStore.setState({ loaded: true, perfilUi: 'basico' } as never)
    usePOSStore.setState({ cart: [{ ...blusa, discount: 10 }], globalDiscount: 5 } as never)
    pintar()
    expect(screen.getByText('-10%')).toBeTruthy()
    expect(screen.getByText('Desc. -5%')).toBeTruthy()
  })
})
```

```tsx
// frontend/src/components/pos/__tests__/AltaRapidaProducto.test.tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react'

const api = vi.hoisted(() => ({
  getDepartments: vi.fn(async () => [{ id: 'd1', name: 'Blusas' }]),
  getBrands: vi.fn(async () => [{ id: 'b1', name: 'Nike' }]),
  create: vi.fn(),
}))
vi.mock('../../../api/products', () => ({ productsApi: api }))
vi.mock('../../../api/organization', () => ({ organizationApi: { getBranches: vi.fn(async () => []) } }))
vi.mock('../../../store/toastStore', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

const { default: AltaRapidaProducto } = await import('../AltaRapidaProducto')
const { useAuthStore } = await import('../../../store/authStore')
const { useEnabledModulesStore } = await import('../../../store/enabledModulesStore')

const cajera = { id: 2, username: 'caja', role: 'CAJERO', branch_id: 20, branch_name: 'Roma' }
const escribir = (etiqueta: RegExp, valor: string) =>
  fireEvent.change(screen.getByLabelText(etiqueta), { target: { value: valor } })

beforeEach(() => {
  vi.clearAllMocks()
  useAuthStore.setState({ user: cajera } as never)
  useEnabledModulesStore.setState({
    enabledModules: ['core', 'pos'], loaded: true, perfilUi: 'basico',
    camposProducto: { visibles: [], ocultos: ['gender', 'model', 'material', 'brand_id', 'description', 'unit', 'image_url', 'tax_rate', 'packaging_units', 'variants'] },
  } as never)
})
afterEach(cleanup)

describe('Alta rápida desde el POS en básico (Review Focus #5)', () => {
  it('formulario corto y ProductCreate válido con la sucursal de la cajera', async () => {
    api.create.mockResolvedValue({ id: 'nuevo', name: 'Blusa', sku: 'BLU', price: 120 })
    const onCreado = vi.fn()
    render(<MemoryRouter><AltaRapidaProducto onClose={() => {}} onCreado={onCreado} /></MemoryRouter>)
    await screen.findByText('Crear producto')
    expect(screen.getByText('Nuevo producto')).toBeTruthy()          // título del Modal
    for (const oculto of ['Marca', 'Unidad', 'Descripción', 'URL de imagen', 'Empaques / Cajas']) {
      expect(screen.queryByText(oculto)).toBeNull()
    }
    escribir(/^Nombre/, 'Blusa'); escribir(/^SKU/, 'blu'); escribir(/^Precio/, '120'); escribir(/^Costo/, '60')
    escribir(/Stock inicial/, '2')
    fireEvent.click(screen.getByText('Crear producto'))
    await waitFor(() => expect(onCreado).toHaveBeenCalled())
    const payload = api.create.mock.calls[0][0]
    expect(payload).toEqual(expect.objectContaining({ name: 'Blusa', sku: 'BLU', branch_id: 20, initial_stock: 2 }))
    expect(Number(payload.price)).toBe(120)
    expect(Number(payload.cost)).toBe(60)
    expect(payload.target_branch_ids).toBeUndefined()
    expect(payload.brand_id ?? null).toBeNull()
  })
})
```

```ts
// frontend/src/__tests__/modoBasico.test.ts
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const src = (p: string) => readFileSync(resolve(__dirname, '..', p), 'utf8')

/** Archivos nuevos del modo básico: render condicional, nunca `hidden`. Cada tarea añade los suyos. */
const NUEVOS = ['pages/pos/opcionesPos.ts', 'components/pos/AltaRapidaProducto.tsx', 'components/layout/navPerfilBasico.ts']

describe('modo básico: carga y render condicional', () => {
  it('el POS carga el alta corta con lazy(), sin import estático del formulario', () => {
    const pos = src('pages/pos/POS.tsx')
    expect(pos).toMatch(/lazy\(\(\) => import\('\.\.\/\.\.\/components\/pos\/AltaRapidaProducto'\)\)/)
    expect(pos).not.toMatch(/from '\.\.\/\.\.\/components\/products\/FormularioProducto'/)
    expect(pos).not.toMatch(/from '\.\.\/\.\.\/components\/pos\/AltaRapidaProducto'/)
  })

  it.each(NUEVOS)('%s no esconde con la clase hidden', (p) => {
    expect(src(p)).not.toMatch(/className=["'`][^"'`]*\bhidden\b/)
  })
})
```

- [ ] **Step 2: Correr y ver que falla**

Run: `cd frontend && npx vitest run src/pages/pos/__tests__/opcionesPos.test.ts src/components/pos/__tests__ src/__tests__/modoBasico.test.ts`
Expected: FAIL (no se resuelven `../opcionesPos` ni `../AltaRapidaProducto`; en `CartPanelPerfil` la prueba de básico encuentra el botón Cliente).

- [ ] **Step 3: `opcionesPos.ts`**

```ts
// frontend/src/pages/pos/opcionesPos.ts
import type { PerfilUi } from '../../types/auth'

/**
 * Qué controles opcionales pinta el POS según el perfil de interfaz (modo
 * básico, spec 2026-10-18 §4.1). Solo decide qué se MUESTRA: el cobro
 * (`saneaCobro`, propina y factura por capacidad, comisión de tarjeta) no
 * cambia. Un dato que ya viene en el ticket (un descuento o un cliente de un
 * ticket pausado) se sigue viendo aunque su control esté escondido.
 */
export interface OpcionesPos {
  /** Descuento por renglón y descuento global. */
  descuentos: boolean
  /** Botón «Cliente» del carrito. */
  cliente: boolean
  /** Equivalente en dólares (bajo el total y en las tarjetas del buscador). */
  usd: boolean
  /** Editar el producto desde el carrito o desde «Ver detalles» del buscador. */
  editarProducto: boolean
  /** Forzar el precio por pieza al vender por caja. */
  forzarPieza: boolean
  /** Alta rápida con el formulario corto en vez de la ficha completa. */
  altaCorta: boolean
}

const COMPLETO: OpcionesPos = {
  descuentos: true, cliente: true, usd: true, editarProducto: true, forzarPieza: true, altaCorta: false,
}
const BASICO: OpcionesPos = {
  descuentos: false, cliente: false, usd: false, editarProducto: false, forzarPieza: false, altaCorta: true,
}

/** Sin perfil (el contexto no ha cargado) = completo: nunca un básico a medias para una de paga. */
export function opcionesPorPerfil(perfil: PerfilUi | null | undefined): OpcionesPos {
  return { ...(perfil === 'basico' ? BASICO : COMPLETO) }
}
```

- [ ] **Step 4: `AltaRapidaProducto.tsx`**

```tsx
// frontend/src/components/pos/AltaRapidaProducto.tsx
import { Modal } from '../ui/Modal'
import { FormularioProducto } from '../products/FormularioProducto'

/**
 * Alta rápida desde el POS en modo básico: el formulario único (corto por
 * `campos_producto`) dentro del Modal del kit. POS.tsx lo carga con `lazy()`
 * para que el formulario no viaje en `POS-*.js` (presupuesto de la ruta
 * crítica). El toast de "Producto creado." ya lo da el formulario.
 */
export default function AltaRapidaProducto({ onClose, onCreado }: { onClose: () => void; onCreado: () => void }) {
  return (
    <Modal open onClose={onClose} size="xl" closeOnBackdrop={false} closeOnEscape={false} title="Nuevo producto">
      <FormularioProducto mode="create" presentacion="modal" onDone={() => onCreado()} onCancel={onClose} />
    </Modal>
  )
}
```

- [ ] **Step 5: `CartPanel.tsx`**

1. Reemplazar:

```tsx
import { useCapacidad } from '../../store/enabledModulesStore'
```

por:

```tsx
import { useCapacidad, useEnabledModulesStore } from '../../store/enabledModulesStore'
import { opcionesPorPerfil } from '../../pages/pos/opcionesPos'
```

2. Reemplazar:

```tsx
  const hayFactura = useCapacidad('factura')
  const [editingGlobalDisc, setEditingGlobalDisc] = useState(false)
```

por:

```tsx
  const hayFactura = useCapacidad('factura')
  // Modo básico: qué controles opcionales se pintan. El cobro no cambia.
  const opciones = opcionesPorPerfil(useEnabledModulesStore((s) => s.perfilUi))
  // Un descuento que ya viene (ticket pausado) se sigue viendo aunque básico esconda el control.
  const muestraDescuentoGlobal = opciones.descuentos || globalDiscount > 0
  const [editingGlobalDisc, setEditingGlobalDisc] = useState(false)
```

3. Reemplazar:

```tsx
          {!customerName && (
            <button
              onClick={() => setClienteAbierto(true)}
```

por:

```tsx
          {!customerName && opciones.cliente && (
            <button
              onClick={() => setClienteAbierto(true)}
```

4. Reemplazar:

```tsx
                            <button
                              onClick={() => { setEditing({ key: priceKey!, mode: 'discount' }); setDiscountInput(String(unitItem.discount || 0)) }}
```

por:

```tsx
                            {(opciones.descuentos || (unitItem.discount ?? 0) > 0) && (
                            <button
                              onClick={() => { setEditing({ key: priceKey!, mode: 'discount' }); setDiscountInput(String(unitItem.discount || 0)) }}
```

y reemplazar:

```tsx
                              {(unitItem.discount ?? 0) > 0 ? `-${unitItem.discount}%` : '%'}
                            </button>
```

por:

```tsx
                              {(unitItem.discount ?? 0) > 0 ? `-${unitItem.discount}%` : '%'}
                            </button>
                            )}
```

5. Reemplazar:

```tsx
                              <button
                                ref={(el) => {
                                  if (editingPrice === cajaKey) activePriceTriggerRef.current = el
                                }}
```

por:

```tsx
                              {opciones.forzarPieza ? (
                              <button
                                ref={(el) => {
                                  if (editingPrice === cajaKey) activePriceTriggerRef.current = el
                                }}
```

y reemplazar:

```tsx
                                {isCajaForced && <i className="fa-solid fa-bolt text-[8px]" />}
                                {formatCurrency(unitPriceCaja)}/pz
                              </button>
```

por:

```tsx
                                {isCajaForced && <i className="fa-solid fa-bolt text-[8px]" />}
                                {formatCurrency(unitPriceCaja)}/pz
                              </button>
                              ) : (
                              <span
                                className="flex items-center gap-1"
                                style={{ color: isCajaForced ? 'var(--dax-warning)' : 'var(--dax-text-muted)' }}
                              >
                                {isCajaForced && <i className="fa-solid fa-bolt text-[8px]" />}
                                {formatCurrency(unitPriceCaja)}/pz
                              </span>
                              )}
```

6. Reemplazar:

```tsx
        <div className="grid grid-cols-2 gap-2 mt-2">
          {/* Izquierda — Descuento global */}
          {editingGlobalDisc ? (
```

por:

```tsx
        <div className={muestraDescuentoGlobal ? 'grid grid-cols-2 gap-2 mt-2' : 'grid grid-cols-1 gap-2 mt-2'}>
          {/* Izquierda — Descuento global */}
          {muestraDescuentoGlobal && (editingGlobalDisc ? (
```

y reemplazar:

```tsx
              <span className="truncate">Descuento global</span>
            </button>
          )}
```

por:

```tsx
              <span className="truncate">Descuento global</span>
            </button>
          ))}
```

7. Reemplazar:

```tsx
        {usdLine && (
```

por:

```tsx
        {opciones.usd && usdLine && (
```

8. Reemplazar:

```tsx
      <ProductDetailModal
        product={detailProduct}
        onClose={() => setDetailProduct(null)}
        canEdit={true}
      />
```

por:

```tsx
      <ProductDetailModal
        product={detailProduct}
        onClose={() => setDetailProduct(null)}
        canEdit={opciones.editarProducto}
      />
```

- [ ] **Step 6: `ProductSearch.tsx`**

1. Después de `import { useAuthStore } from '../../store/authStore'` añadir:

```tsx
import { useEnabledModulesStore } from '../../store/enabledModulesStore'
import { opcionesPorPerfil } from '../../pages/pos/opcionesPos'
```

2. Reemplazar:

```tsx
  const canEdit = !!user?.role && EDIT_ROLES.includes(user.role)
```

por:

```tsx
  const canEdit = !!user?.role && EDIT_ROLES.includes(user.role)
  const opciones = opcionesPorPerfil(useEnabledModulesStore((s) => s.perfilUi))
```

3. Reemplazar `                      {usdRate !== null && (` por `                      {opciones.usd && usdRate !== null && (`.
4. Reemplazar `        canEdit={canEdit}` por `        canEdit={canEdit && opciones.editarProducto}`.

- [ ] **Step 7: `POS.tsx`**

1. Reemplazar `import { useEffect, useState, useCallback, useRef } from 'react'` por `import { lazy, Suspense, useEffect, useState, useCallback, useRef } from 'react'`.
2. Reemplazar:

```tsx
  type PendingSale,
} from '../../utils/offlineQueue'
```

por:

```tsx
  type PendingSale,
} from '../../utils/offlineQueue'
import { opcionesPorPerfil } from './opcionesPos'

// Alta corta del modo básico: chunk propio, no viaja en POS-*.js.
const AltaRapidaProducto = lazy(() => import('../../components/pos/AltaRapidaProducto'))
```

3. Reemplazar:

```tsx
  const hayFactura = useCapacidad('factura')
  // `capacidades` arranca vacia
```

por:

```tsx
  const hayFactura = useCapacidad('factura')
  const opciones = opcionesPorPerfil(useEnabledModulesStore((s) => s.perfilUi))
  // `capacidades` arranca vacia
```

4. Reemplazar:

```tsx
      {createProductOpen && (
        <ProductDetailModal
          product={null}
          mode="create"
          canEdit={canEditProducts}
          onClose={() => setCreateProductOpen(false)}
          onSaved={() => {
            setCreateProductOpen(false)
            setProductRefreshKey(k => k + 1)
            showToast('Producto creado')
          }}
        />
      )}
```

por:

```tsx
      {createProductOpen && (opciones.altaCorta ? (
        <Suspense fallback={null}>
          <AltaRapidaProducto
            onClose={() => setCreateProductOpen(false)}
            onCreado={() => {
              setCreateProductOpen(false)
              setProductRefreshKey(k => k + 1)
            }}
          />
        </Suspense>
      ) : (
        <ProductDetailModal
          product={null}
          mode="create"
          canEdit={canEditProducts}
          onClose={() => setCreateProductOpen(false)}
          onSaved={() => {
            setCreateProductOpen(false)
            setProductRefreshKey(k => k + 1)
            showToast('Producto creado')
          }}
        />
      ))}
```

- [ ] **Step 8: Correr y ver que pasa**

Run: `cd frontend && npx vitest run src/pages/pos src/components/pos src/__tests__`
Expected: PASS.

- [ ] **Step 9: Build y presupuesto**

Run: `cd frontend && npm run build && cd .. && python3 scripts/presupuesto_bundle.py --dist frontend/dist --presupuesto frontend/presupuesto_bundle.json`
Expected: build sin errores; el script termina en 0 y la suma queda bajo `tope_bytes` (452,500). `ls frontend/dist/assets | grep AltaRapidaProducto` muestra un chunk propio y `grep -c AltaRapidaProducto frontend/dist/index.html` da `0`.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/pages/pos/opcionesPos.ts frontend/src/pages/pos/__tests__/opcionesPos.test.ts \
  frontend/src/components/pos/AltaRapidaProducto.tsx frontend/src/components/pos/CartPanel.tsx \
  frontend/src/components/pos/ProductSearch.tsx frontend/src/pages/pos/POS.tsx \
  frontend/src/components/pos/__tests__/CartPanelPerfil.test.tsx \
  frontend/src/components/pos/__tests__/AltaRapidaProducto.test.tsx frontend/src/__tests__/modoBasico.test.ts
git commit -m "$(cat <<'EOF'
feat(pos): modo básico sin descuentos, cliente, dólares ni edición de ficha

opcionesPorPerfil decide qué controles se pintan; el cobro no cambia y lo
que ya trae un ticket pausado se sigue viendo. El alta rápida abre el
formulario corto en su propio chunk.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf
EOF
)"
```

---

### Task 7: Frontend — Inicio básico, `PorPerfil` y rutas

**Files:**
- Create: `frontend/src/components/layout/PorPerfil.tsx`
- Create: `frontend/src/pages/hq/InicioBasico.tsx`
- Modify: `frontend/src/api/reports.ts` (tipos + `inicioBasico`)
- Modify: `frontend/src/App.tsx:15,34,253-254`
- Modify: `frontend/src/pages/__tests__/responsivoOla2.test.ts:6` (`PAGINAS`)
- Modify: `frontend/src/__tests__/modoBasico.test.ts` (`NUEVOS` + prueba de rutas)
- Test: `frontend/src/components/layout/__tests__/PorPerfil.test.tsx`, `frontend/src/pages/hq/__tests__/InicioBasico.test.tsx`

**Interfaces:**
- Consumes: `GET /api/reports/inicio-basico` con la forma JSON de la Tarea 3; `reportsApi.valorInventario`; `ValorTiendaCard`; store `loaded`, `load`, `perfilUi` (Tarea 4).
- Produces:
  - Tipos en `api/reports.ts`: `PeriodoVentas { desde: string; hasta: string; total: number; tickets: number }`, `ProductoTop { nombre: string; cantidad: number; total: number }`, `ProductoPocaExistencia { variant_id: string; nombre: string; sku: string; existencia: number }`, `CorteInicio { estado: 'abierto' | 'cerrado' | 'sin_turno'; cajera: string | null; abierto_en: string | null; cerrado_en: string | null; efectivo_esperado: number | null; efectivo_contado: number | null }`, `InicioBasico { branch_id: number | null; hoy; ayer; semana: PeriodoVentas; por_metodo_hoy: Record<string, number>; top_semana: ProductoTop[]; poca_existencia: { umbral: number; productos: ProductoPocaExistencia[] }; corte: CorteInicio }`; `reportsApi.inicioBasico(branchId?: number): Promise<InicioBasico>`.
  - `PorPerfil({ basico, completo }: { basico: ReactNode; completo: ReactNode })`: carga el contexto si no está; mientras `!loaded` no monta ninguna.
  - `InicioBasico()` (export nombrado; chunk propio por `lazy()`).

- [ ] **Step 1: Escribir las pruebas que fallan**

```tsx
// frontend/src/components/layout/__tests__/PorPerfil.test.tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'

const { get } = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('../../../api/client', () => ({ default: { get } }))

import { PorPerfil } from '../PorPerfil'
import { useEnabledModulesStore } from '../../../store/enabledModulesStore'

const pintar = () => render(<PorPerfil basico={<p>pantalla básica</p>} completo={<p>pantalla completa</p>} />)

beforeEach(() => { useEnabledModulesStore.getState().reset(); get.mockReset() })
afterEach(cleanup)

describe('PorPerfil (Review Focus #1)', () => {
  it('mientras el contexto no llega no monta ninguna de las dos y lo pide', () => {
    get.mockReturnValue(new Promise(() => {}))
    pintar()
    expect(screen.queryByText('pantalla básica')).toBeNull()
    expect(screen.queryByText('pantalla completa')).toBeNull()
    expect(get).toHaveBeenCalledWith('/users/me/context')
  })

  it('FREE: monta solo la básica', async () => {
    get.mockResolvedValue({ data: { enabled_modules: ['core'], perfil_ui: 'basico' } })
    pintar()
    expect(await screen.findByText('pantalla básica')).toBeTruthy()
    expect(screen.queryByText('pantalla completa')).toBeNull()
  })

  it('de paga o servidor viejo: la completa', async () => {
    get.mockResolvedValue({ data: { enabled_modules: ['core'] } })
    pintar()
    expect(await screen.findByText('pantalla completa')).toBeTruthy()
  })

  it('si el contexto falla: la completa', async () => {
    get.mockRejectedValue(new Error('red caída'))
    pintar()
    expect(await screen.findByText('pantalla completa')).toBeTruthy()
    expect(screen.queryByText('pantalla básica')).toBeNull()
  })
})
```

```tsx
// frontend/src/pages/hq/__tests__/InicioBasico.test.tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, cleanup } from '@testing-library/react'

const { inicioBasico, valorInventario } = vi.hoisted(() => ({ inicioBasico: vi.fn(), valorInventario: vi.fn() }))
vi.mock('../../../api/reports', () => ({ reportsApi: { inicioBasico, valorInventario } }))

import { InicioBasico } from '../InicioBasico'

// La forma exacta de la Tarea 3.
const DATOS = {
  branch_id: null,
  hoy: { desde: '2026-10-19', hasta: '2026-10-19', total: 1234.5, tickets: 12 },
  ayer: { desde: '2026-10-18', hasta: '2026-10-18', total: 800, tickets: 1 },
  semana: { desde: '2026-10-13', hasta: '2026-10-19', total: 9000, tickets: 70 },
  por_metodo_hoy: { CARD: 234.5, CASH: 1000 },
  top_semana: [{ nombre: 'Blusa roja', cantidad: 14, total: 1400 }],
  poca_existencia: { umbral: 3, productos: [{ variant_id: 'v1', nombre: 'Falda negra', sku: 'FAL-1', existencia: 1 }] },
  corte: { estado: 'abierto', cajera: 'Mirna', abierto_en: '2026-10-19T15:00:00+00:00', cerrado_en: null, efectivo_esperado: 1500, efectivo_contado: null },
}
const VALUACION = {
  agrupar: 'sucursal', branch_id: null, ve_costo: true, grupos: [],
  totales: { piezas: 10, skus: 2, valor_venta: 5000, valor_costo: 2000, piezas_sin_costo: 0, skus_sin_costo: 0 },
}
const pintar = () => render(<MemoryRouter><InicioBasico /></MemoryRouter>)

beforeEach(() => {
  inicioBasico.mockReset().mockResolvedValue(DATOS)
  valorInventario.mockReset().mockResolvedValue(VALUACION)
})
afterEach(cleanup)

describe('InicioBasico', () => {
  it('vendido hoy, ayer y en 7 días', async () => {
    pintar()
    const hoy = await screen.findByTestId('cifra-hoy')
    expect(hoy.textContent).toContain('$1,234.50')
    expect(hoy.textContent).toContain('12 ventas')
    expect(screen.getByTestId('cifra-ayer').textContent).toContain('1 venta')
    expect(screen.getByTestId('cifra-semana').textContent).toContain('$9,000.00')
  })

  it('cobros de hoy con efectivo primero', async () => {
    pintar()
    await screen.findByTestId('cifra-hoy')
    const metodos = screen.getAllByTestId('metodo').map((li) => li.textContent)
    expect(metodos[0]).toContain('Efectivo')
    expect(metodos[1]).toContain('Tarjeta')
  })

  it('caja, lo que se acaba, lo más vendido y el valor de la tienda', async () => {
    pintar()
    const corte = await screen.findByTestId('corte')
    expect(corte.textContent).toContain('Turno abierto')
    expect(corte.textContent).toContain('Mirna')
    expect(corte.textContent).toContain('$1,500.00')
    expect(screen.getByText('Falda negra')).toBeTruthy()
    expect(screen.getByText('1 pieza')).toBeTruthy()
    expect(screen.getByText('Blusa roja')).toBeTruthy()
    expect(await screen.findByTestId('valor-tienda')).toBeTruthy()
  })

  it('turno cerrado y sin turno', async () => {
    inicioBasico.mockResolvedValue({ ...DATOS, corte: { ...DATOS.corte, estado: 'cerrado', cerrado_en: '2026-10-19T23:00:00+00:00', efectivo_esperado: null, efectivo_contado: 850 } })
    pintar()
    expect((await screen.findByTestId('corte')).textContent).toContain('$850.00')
    cleanup()
    inicioBasico.mockResolvedValue({ ...DATOS, corte: { estado: 'sin_turno', cajera: null, abierto_en: null, cerrado_en: null, efectivo_esperado: null, efectivo_contado: null } })
    pintar()
    expect((await screen.findByTestId('corte')).textContent).toContain('Nadie ha abierto turno')
  })

  it('si el resumen falla, el mensaje del servidor y la tarjeta del valor siguen', async () => {
    inicioBasico.mockRejectedValue({ response: { data: { detail: 'Solo administrador, dueño o gerente pueden ver el inicio' } } })
    pintar()
    expect(await screen.findByText('Solo administrador, dueño o gerente pueden ver el inicio')).toBeTruthy()
    expect(await screen.findByTestId('valor-tienda')).toBeTruthy()
  })
})
```

En `frontend/src/__tests__/modoBasico.test.ts`, reemplazar:

```ts
const NUEVOS = ['pages/pos/opcionesPos.ts', 'components/pos/AltaRapidaProducto.tsx', 'components/layout/navPerfilBasico.ts']
```

por:

```ts
const NUEVOS = [
  'pages/pos/opcionesPos.ts', 'components/pos/AltaRapidaProducto.tsx', 'components/layout/navPerfilBasico.ts',
  'pages/hq/InicioBasico.tsx', 'components/layout/PorPerfil.tsx',
]
```

y añadir dentro del `describe`, después de la primera prueba:

```ts
  it('Inicio y Reportes cambian de pantalla por perfil; InicioBasico es chunk propio sin chart.js', () => {
    const app = src('App.tsx')
    expect(app).toMatch(/const InicioBasico\s+= lazy\(\(\) => import\('\.\/pages\/hq\/InicioBasico'\)/)
    expect(app).toMatch(/<PorPerfil basico=\{<InicioBasico \/>\} completo=\{<HQOperations \/>\} \/>/)
    expect(app).toMatch(/<PorPerfil basico=\{<Reports \/>\} completo=\{<HQReportsHub \/>\} \/>/)
    expect(src('pages/hq/InicioBasico.tsx')).not.toMatch(/chart\.js|react-chartjs-2/)
  })
```

En `frontend/src/pages/__tests__/responsivoOla2.test.ts`, reemplazar:

```ts
export const PAGINAS = ['core/Brands.tsx', 'core/Departments.tsx', 'core/Users.tsx', 'crm/Customers.tsx', 'inventory/Inventory.tsx', 'hq/HQInventory.tsx', 'inventory/Products.tsx', 'core/AdminCatalog.tsx']
```

por:

```ts
export const PAGINAS = ['core/Brands.tsx', 'core/Departments.tsx', 'core/Users.tsx', 'crm/Customers.tsx', 'inventory/Inventory.tsx', 'hq/HQInventory.tsx', 'inventory/Products.tsx', 'core/AdminCatalog.tsx', 'hq/InicioBasico.tsx']
```

- [ ] **Step 2: Correr y ver que falla**

Run: `cd frontend && npx vitest run src/components/layout/__tests__/PorPerfil.test.tsx src/pages/hq src/__tests__/modoBasico.test.ts src/pages/__tests__/responsivoOla2.test.ts`
Expected: FAIL (no se resuelven `../PorPerfil` ni `../InicioBasico`; `ENOENT` en las guardas).

- [ ] **Step 3: Tipos y API**

En `frontend/src/api/reports.ts`, justo antes de `export const reportsApi = {` añadir:

```ts
// --- Inicio básico (GET /reports/inicio-basico, modo básico 2026-10) ------
export interface PeriodoVentas {
  desde: string
  hasta: string
  total: number
  tickets: number
}

export interface ProductoTop {
  nombre: string
  cantidad: number
  total: number
}

export interface ProductoPocaExistencia {
  variant_id: string
  nombre: string
  sku: string
  existencia: number
}

export interface CorteInicio {
  estado: 'abierto' | 'cerrado' | 'sin_turno'
  cajera: string | null
  abierto_en: string | null
  cerrado_en: string | null
  /** Solo con turno abierto. */
  efectivo_esperado: number | null
  /** Solo con turno cerrado. */
  efectivo_contado: number | null
}

export interface InicioBasico {
  /** null = todas las sucursales de la org. */
  branch_id: number | null
  hoy: PeriodoVentas
  ayer: PeriodoVentas
  semana: PeriodoVentas
  por_metodo_hoy: Record<string, number>
  top_semana: ProductoTop[]
  poca_existencia: { umbral: number; productos: ProductoPocaExistencia[] }
  corte: CorteInicio
}

```

y dentro de `reportsApi`, después de `valorInventario` (antes del `}` final), añadir:

```ts

  inicioBasico: async (branchId?: number): Promise<InicioBasico> => {
    const params = branchId != null ? { branch_id: branchId } : {}
    const { data } = await client.get<InicioBasico>('/reports/inicio-basico', { params })
    return data
  },
```

- [ ] **Step 4: `PorPerfil.tsx`**

```tsx
// frontend/src/components/layout/PorPerfil.tsx
import { useEffect, type ReactNode } from 'react'
import { useEnabledModulesStore } from '../../store/enabledModulesStore'
import { Spinner } from '../ui/Spinner'

/**
 * Elige pantalla por perfil de interfaz (modo básico). Espera al contexto
 * antes de decidir: así una FREE no monta la pantalla completa (ni baja su
 * chunk) para cambiarla un segundo después, y una de paga nunca ve la básica.
 * Si el contexto falla, el store queda en 'completo' (fail-open).
 */
export function PorPerfil({ basico, completo }: { basico: ReactNode; completo: ReactNode }) {
  const loaded = useEnabledModulesStore((s) => s.loaded)
  const load = useEnabledModulesStore((s) => s.load)
  const perfilUi = useEnabledModulesStore((s) => s.perfilUi)
  useEffect(() => {
    if (!loaded) void load()
  }, [loaded, load])
  if (!loaded) {
    return (
      <div className="flex items-center justify-center h-full">
        <Spinner size="lg" text="Cargando..." />
      </div>
    )
  }
  return <>{perfilUi === 'basico' ? basico : completo}</>
}
```

- [ ] **Step 5: `InicioBasico.tsx`**

```tsx
// frontend/src/pages/hq/InicioBasico.tsx
import { useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { reportsApi, type InicioBasico as DatosInicio, type ValuacionInventario } from '../../api/reports'
import { ValorTiendaCard } from '../../components/reports/ValorTiendaCard'
import { CabeceraPagina } from '../../components/ui/CabeceraPagina'
import { DaxCard } from '../../components/ui/DaxCard'
import { ListaTarjetas } from '../../components/ui/ListaTarjetas'
import { TarjetaFila } from '../../components/ui/TarjetaFila'
import { Spinner } from '../../components/ui/Spinner'
import { useEsTelefono } from '../../hooks/useIsMobile'
import { formatCurrency } from '../../utils/currency'
import { errorDetailText } from '../../utils/errorDetail'

/**
 * Inicio básico (modo básico, spec 2026-10-18 §4.2): una sola pantalla que
 * responde "¿cómo voy?" para la dueña de una tienda FREE. Una llamada
 * (`/reports/inicio-basico`) + la tarjeta de valor de la tienda de SP3. Sin
 * gráficas: chart.js no viaja en este chunk.
 */

const METODOS: Record<string, string> = { CASH: 'Efectivo', CARD: 'Tarjeta', TRANSFER: 'Transferencia' }
const ORDEN_METODOS = ['CASH', 'CARD', 'TRANSFER']

const hora = (iso: string | null) =>
  iso ? new Date(iso).toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' }) : ''
const piezas = (n: number) => {
  const r = Math.round(n * 100) / 100
  return `${r.toLocaleString('es-MX')} ${r === 1 ? 'pieza' : 'piezas'}`
}
const ventas = (n: number) => `${n} ${n === 1 ? 'venta' : 'ventas'}`

function Cifra({ etiqueta, total, tickets, testId }: { etiqueta: string; total: number; tickets: number; testId: string }) {
  return (
    <div className="dax-card p-4" data-testid={testId}>
      <p className="text-[10px] font-black uppercase tracking-widest text-slate-500">{etiqueta}</p>
      <p className="text-2xl font-bold text-white tabular-nums">{formatCurrency(total)}</p>
      <p className="text-xs text-slate-400">{ventas(tickets)}</p>
    </div>
  )
}

function Titulo({ children, enlace }: { children: ReactNode; enlace?: { a: string; texto: string } }) {
  return (
    <div className="flex items-center justify-between gap-2 mb-3">
      <p className="text-[10px] font-black uppercase tracking-widest text-slate-500">{children}</p>
      {enlace && (
        <Link to={enlace.a} className="text-[10px] font-bold text-indigo-400 hover:underline whitespace-nowrap">
          {enlace.texto}
        </Link>
      )}
    </div>
  )
}

function Corte({ corte }: { corte: DatosInicio['corte'] }) {
  if (corte.estado === 'abierto') {
    return (
      <div className="space-y-1" data-testid="corte">
        <p className="text-sm font-bold text-emerald-400">Turno abierto</p>
        <p className="text-sm text-slate-300">{corte.cajera ?? 'Sin nombre'} · desde las {hora(corte.abierto_en)}</p>
        <p className="text-sm text-slate-300">
          Efectivo esperado en caja:{' '}
          <span className="font-bold tabular-nums text-white">{formatCurrency(corte.efectivo_esperado)}</span>
        </p>
      </div>
    )
  }
  if (corte.estado === 'cerrado') {
    return (
      <div className="space-y-1" data-testid="corte">
        <p className="text-sm font-bold text-slate-300">Turno cerrado</p>
        <p className="text-sm text-slate-400">{corte.cajera ?? 'Sin nombre'} cerró a las {hora(corte.cerrado_en)}</p>
        <p className="text-sm text-slate-400">
          Contó <span className="font-bold tabular-nums text-white">{formatCurrency(corte.efectivo_contado)}</span>
        </p>
      </div>
    )
  }
  return <p className="text-sm text-slate-400" data-testid="corte">Nadie ha abierto turno.</p>
}

export function InicioBasico() {
  const esTelefono = useEsTelefono()
  const [datos, setDatos] = useState<DatosInicio | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [valuacion, setValuacion] = useState<ValuacionInventario | null>(null)
  const [valuacionError, setValuacionError] = useState<string | null>(null)

  useEffect(() => {
    let vivo = true
    reportsApi.inicioBasico()
      .then((d) => { if (vivo) setDatos(d) })
      .catch((e: any) => {
        if (vivo) setError(errorDetailText(e?.response?.data?.detail, 'No se pudo cargar el resumen. Vuelve a intentar en unos segundos.'))
      })
    reportsApi.valorInventario({ agrupar: 'sucursal' })
      .then((v) => { if (vivo) setValuacion(v) })
      .catch((e: any) => {
        if (vivo) setValuacionError(errorDetailText(e?.response?.data?.detail, 'No se pudo calcular el valor de la tienda.'))
      })
    return () => { vivo = false }
  }, [])

  const metodos = datos
    ? [
        ...ORDEN_METODOS.filter((m) => m in datos.por_metodo_hoy),
        ...Object.keys(datos.por_metodo_hoy).filter((m) => !ORDEN_METODOS.includes(m)),
      ]
    : []
  const acabando = datos?.poca_existencia.productos ?? []
  const top = datos?.top_semana ?? []

  return (
    <div className="space-y-5">
      <CabeceraPagina
        titulo={<h1 className="text-2xl font-black text-white">¿Cómo voy?</h1>}
        descripcion="Lo vendido, la caja y lo que se está acabando."
      />

      {error ? (
        <DaxCard><p className="text-sm text-rose-300">{error}</p></DaxCard>
      ) : !datos ? (
        <Spinner size="lg" text="Cargando…" />
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <Cifra etiqueta="Hoy" total={datos.hoy.total} tickets={datos.hoy.tickets} testId="cifra-hoy" />
            <Cifra etiqueta="Ayer" total={datos.ayer.total} tickets={datos.ayer.tickets} testId="cifra-ayer" />
            <Cifra etiqueta="Últimos 7 días" total={datos.semana.total} tickets={datos.semana.tickets} testId="cifra-semana" />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            <DaxCard>
              <Titulo>Cómo te pagaron hoy</Titulo>
              {metodos.length === 0 ? (
                <p className="text-sm text-slate-400">Sin cobros hoy.</p>
              ) : (
                <ul className="space-y-1">
                  {metodos.map((m) => (
                    <li key={m} data-testid="metodo" className="flex justify-between text-sm">
                      <span className="text-slate-300">{METODOS[m] ?? m}</span>
                      <span className="font-bold tabular-nums text-white">{formatCurrency(datos.por_metodo_hoy[m])}</span>
                    </li>
                  ))}
                </ul>
              )}
            </DaxCard>
            <DaxCard>
              <Titulo enlace={{ a: '/cash-history', texto: 'Ver corte →' }}>Caja</Titulo>
              <Corte corte={datos.corte} />
            </DaxCard>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            <DaxCard>
              <Titulo enlace={{ a: '/products', texto: 'Ver productos →' }}>
                Se está acabando (quedan {datos.poca_existencia.umbral} o menos)
              </Titulo>
              {esTelefono ? (
                <ListaTarjetas vacio={acabando.length === 0} textoVacio="Nada se está acabando.">
                  {acabando.map((p) => (
                    <TarjetaFila key={p.variant_id} titulo={p.nombre} subtitulo={p.sku} importe={piezas(p.existencia)} />
                  ))}
                </ListaTarjetas>
              ) : acabando.length === 0 ? (
                <p className="text-sm text-slate-400">Nada se está acabando.</p>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-[10px] uppercase tracking-widest text-slate-500">
                      <th className="py-1">Producto</th><th className="py-1">Código</th><th className="py-1 text-right">Quedan</th>
                    </tr>
                  </thead>
                  <tbody>
                    {acabando.map((p) => (
                      <tr key={p.variant_id} className="border-t border-slate-800/60">
                        <td className="py-1.5 text-slate-200">{p.nombre}</td>
                        <td className="py-1.5 font-mono text-xs text-slate-400">{p.sku}</td>
                        <td className="py-1.5 text-right tabular-nums font-bold text-amber-400">{piezas(p.existencia)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </DaxCard>
            <DaxCard>
              <Titulo>Lo que más se vendió (7 días)</Titulo>
              {esTelefono ? (
                <ListaTarjetas vacio={top.length === 0} textoVacio="Sin ventas esta semana.">
                  {top.map((t) => (
                    <TarjetaFila key={t.nombre} titulo={t.nombre} subtitulo={piezas(t.cantidad)} importe={formatCurrency(t.total)} />
                  ))}
                </ListaTarjetas>
              ) : top.length === 0 ? (
                <p className="text-sm text-slate-400">Sin ventas esta semana.</p>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-[10px] uppercase tracking-widest text-slate-500">
                      <th className="py-1">Producto</th><th className="py-1 text-right">Piezas</th><th className="py-1 text-right">Importe</th>
                    </tr>
                  </thead>
                  <tbody>
                    {top.map((t) => (
                      <tr key={t.nombre} className="border-t border-slate-800/60">
                        <td className="py-1.5 text-slate-200">{t.nombre}</td>
                        <td className="py-1.5 text-right tabular-nums text-slate-300">{piezas(t.cantidad)}</td>
                        <td className="py-1.5 text-right tabular-nums font-bold text-white">{formatCurrency(t.total)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </DaxCard>
          </div>
        </>
      )}

      <ValorTiendaCard
        valorVenta={valuacion?.totales.valor_venta ?? 0}
        valorCosto={valuacion ? valuacion.totales.valor_costo : null}
        piezas={valuacion?.totales.piezas ?? 0}
        piezasSinCosto={valuacion?.totales.piezas_sin_costo ?? 0}
        skusSinCosto={valuacion?.totales.skus_sin_costo ?? 0}
        cargando={!valuacion && !valuacionError}
        error={valuacionError}
      />
    </div>
  )
}
```

- [ ] **Step 6: Rutas en `App.tsx`**

1. Después de `import { RequireRole, RutaPorRol } from './components/layout/RequireRole'` añadir:

```tsx
import { PorPerfil } from './components/layout/PorPerfil'
```

2. Después de la línea `const HQValorInventario = lazy(...)` añadir:

```tsx
// Modo básico: chunk propio (sin chart.js); lo monta PorPerfil en /hq/operations.
const InicioBasico    = lazy(() => import('./pages/hq/InicioBasico').then(m => ({ default: m.InicioBasico })))
```

3. Reemplazar:

```tsx
            <Route path="operations" element={<RutaPorRol url="/hq/operations"><Suspense fallback={<PageLoader />}><HQOperations /></Suspense></RutaPorRol>} />
            <Route path="reports-hub" element={<RutaPorRol url="/hq/reports-hub"><Suspense fallback={<PageLoader />}><HQReportsHub /></Suspense></RutaPorRol>} />
```

por:

```tsx
            {/* Modo básico (FREE): Inicio corto y los Reportes de la cajera; las de paga, lo de siempre. */}
            <Route path="operations" element={<RutaPorRol url="/hq/operations"><Suspense fallback={<PageLoader />}><PorPerfil basico={<InicioBasico />} completo={<HQOperations />} /></Suspense></RutaPorRol>} />
            <Route path="reports-hub" element={<RutaPorRol url="/hq/reports-hub"><Suspense fallback={<PageLoader />}><PorPerfil basico={<Reports />} completo={<HQReportsHub />} /></Suspense></RutaPorRol>} />
```

- [ ] **Step 7: Correr y ver que pasa**

Run: `cd frontend && npx vitest run src/components/layout src/pages/hq src/pages/__tests__ src/__tests__`
Expected: PASS.

- [ ] **Step 8: Build, chunk y presupuesto**

Run: `cd frontend && npm run build && ls dist/assets | grep -E '^InicioBasico-.*\.js$' && grep -c InicioBasico dist/index.html; cd .. && python3 scripts/presupuesto_bundle.py --dist frontend/dist --presupuesto frontend/presupuesto_bundle.json`
Expected: existe `InicioBasico-*.js`; `grep -c` imprime `0` (no se precarga con el login); el presupuesto pasa con el mismo `tope_bytes`.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/api/reports.ts frontend/src/components/layout/PorPerfil.tsx \
  frontend/src/components/layout/__tests__/PorPerfil.test.tsx frontend/src/pages/hq/InicioBasico.tsx \
  frontend/src/pages/hq/__tests__/InicioBasico.test.tsx frontend/src/App.tsx \
  frontend/src/pages/__tests__/responsivoOla2.test.ts frontend/src/__tests__/modoBasico.test.ts
git commit -m "$(cat <<'EOF'
feat(modo-basico): Inicio básico "¿cómo voy?" y Reportes de la cajera para la dueña

PorPerfil espera al contexto y monta una sola pantalla: InicioBasico (chunk
propio, sin chart.js) en /hq/operations y Reports en /hq/reports-hub para
las FREE; las de paga ven lo de siempre.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf
EOF
)"
```

---

### Task 8: Frontend — Empresa con "Más opciones" y tope; selector de perfil en la plataforma

**Files:**
- Create: `frontend/src/components/ui/MasOpciones.tsx`
- Create: `frontend/src/pages/platform/SelectorPerfilUi.tsx`
- Modify: `frontend/src/api/organization.ts` (`Organization`)
- Modify: `frontend/src/api/platform.ts` (`PlatformOrg`)
- Modify: `frontend/src/pages/core/Organization.tsx`
- Modify: `frontend/src/pages/platform/PlatformOrgDetail.tsx:262,419,686-688`
- Modify: `frontend/src/__tests__/modoBasico.test.ts` (`NUEVOS`)
- Test: `frontend/src/components/ui/__tests__/MasOpciones.test.tsx`, `frontend/src/pages/core/__tests__/OrganizationBasico.test.tsx`, `frontend/src/pages/platform/__tests__/SelectorPerfilUi.test.tsx`

**Interfaces:**
- Consumes: `useModoBasico()` (Tarea 4); `OrganizationRead.perfil_ui`/`umbral_poca_existencia` y el PUT de plataforma con `perfil_ui` (Tarea 1).
- Produces:
  - `MasOpciones({ activo, titulo = 'Más opciones', children }: { activo: boolean; titulo?: string; children: ReactNode })`: con `activo=false` devuelve los hijos sin envoltorio (DOM idéntico); con `activo` monta los hijos solo al abrir.
  - `OPCIONES_PERFIL_UI` y `SelectorPerfilUi({ valor, onCambio, deshabilitado, estilo }: { valor: string | null | undefined; onCambio: (v: string) => void; deshabilitado?: boolean; estilo?: CSSProperties })`.
  - `Organization.perfil_ui?: string | null`, `Organization.umbral_poca_existencia?: number | null`; `PlatformOrg.perfil_ui?: string | null`.

- [ ] **Step 1: Escribir las pruebas que fallan**

```tsx
// frontend/src/components/ui/__tests__/MasOpciones.test.tsx
// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup, fireEvent } from '@testing-library/react'
import { MasOpciones } from '../MasOpciones'

afterEach(cleanup)

describe('MasOpciones', () => {
  it('inactivo (completo): los hijos tal cual, sin botón ni envoltorio', () => {
    const { container } = render(<div><MasOpciones activo={false}><p>hijo</p></MasOpciones></div>)
    expect(screen.getByText('hijo')).toBeTruthy()
    expect(screen.queryByRole('button')).toBeNull()
    expect(container.firstElementChild!.innerHTML).toBe('<p>hijo</p>')
  })

  it('activo (básico): plegado y sin montar hasta abrir', () => {
    render(<MasOpciones activo titulo="Más opciones del ticket"><p>hijo</p></MasOpciones>)
    const boton = screen.getByRole('button', { name: 'Más opciones del ticket' })
    expect(boton.getAttribute('aria-expanded')).toBe('false')
    expect(screen.queryByText('hijo')).toBeNull()
    fireEvent.click(boton)
    expect(boton.getAttribute('aria-expanded')).toBe('true')
    expect(screen.getByText('hijo')).toBeTruthy()
  })
})
```

```tsx
// frontend/src/pages/core/__tests__/OrganizationBasico.test.tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react'

const api = vi.hoisted(() => ({
  getOrg: vi.fn(),
  getBranches: vi.fn(async () => []),
  getExchangeRate: vi.fn(async () => ({ mode: 'off', rate: null, source: null, fix_rate: null, fix_date: null, margin: '0', manual_rate: null })),
  updateOrg: vi.fn(),
}))
vi.mock('../../../api/organization', () => ({ organizationApi: api }))
vi.mock('../../../api/client', () => ({ default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }))

import { Organization } from '../Organization'
import { useEnabledModulesStore } from '../../../store/enabledModulesStore'

const ORG = {
  id: 1, name: 'Kaory', tax_id: null, address: null, phone: null, email: null, logo_url: null, website: null,
  ticket_header: 'Kaory', ticket_footer: 'Gracias', industry_type: 'ATLAS_POS', usd_rate_mode: 'off',
  usd_rate_margin: '0', card_surcharge_pct: '0', ticket_line_style: 'compact', ticket_show_vendor: false,
  perfil_ui: null, umbral_poca_existencia: null,
}

beforeEach(() => {
  vi.clearAllMocks()
  api.getOrg.mockResolvedValue({ ...ORG })
  api.updateOrg.mockImplementation(async (d: object) => ({ ...ORG, ...d }))
})
afterEach(cleanup)

describe('Empresa', () => {
  it('completo: todo a la vista, sin Más opciones ni tope', async () => {
    useEnabledModulesStore.setState({ loaded: true, perfilUi: 'completo' } as never)
    render(<Organization />)
    expect(await screen.findByText(/Tipo de cambio USD/)).toBeTruthy()
    expect(screen.getByText('Términos y condiciones')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Más opciones' })).toBeNull()
    expect(screen.queryByLabelText(/Avisar cuando queden/)).toBeNull()
  })

  it('básico: datos, encabezado y pie; lo demás plegado y sin montar', async () => {
    useEnabledModulesStore.setState({ loaded: true, perfilUi: 'basico' } as never)
    render(<Organization />)
    expect(await screen.findByText('Información de la Empresa')).toBeTruthy()
    expect(screen.getByText('Encabezado del ticket')).toBeTruthy()
    expect(screen.getByText('Pie de página del ticket')).toBeTruthy()
    expect(screen.queryByText(/Tipo de cambio USD/)).toBeNull()
    expect(screen.queryByText('Términos y condiciones')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Más opciones' }))
    expect(screen.getByText(/Tipo de cambio USD/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Más opciones del ticket' }))
    expect(screen.getByText('Términos y condiciones')).toBeTruthy()
  })

  it('básico: el tope de "se está acabando" se guarda', async () => {
    useEnabledModulesStore.setState({ loaded: true, perfilUi: 'basico' } as never)
    render(<Organization />)
    const tope = await screen.findByLabelText(/Avisar cuando queden/)
    fireEvent.change(tope, { target: { value: '5' } })
    fireEvent.click(screen.getByText('Guardar aviso'))
    await waitFor(() => expect(api.updateOrg).toHaveBeenCalledWith(expect.objectContaining({ umbral_poca_existencia: 5 })))
  })
})
```

```tsx
// frontend/src/pages/platform/__tests__/SelectorPerfilUi.test.tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, cleanup, fireEvent } from '@testing-library/react'
import { OPCIONES_PERFIL_UI, SelectorPerfilUi } from '../SelectorPerfilUi'

afterEach(cleanup)

describe('SelectorPerfilUi', () => {
  it('tres opciones; sin valor guardado muestra Automático', () => {
    render(<SelectorPerfilUi valor={null} onCambio={() => {}} />)
    const sel = screen.getByLabelText('Perfil de interfaz') as HTMLSelectElement
    expect(sel.value).toBe('auto')
    expect(OPCIONES_PERFIL_UI.map((o) => o.valor)).toEqual(['auto', 'basico', 'completo'])
    expect(sel.options).toHaveLength(3)
  })

  it('avisa el valor elegido', () => {
    const onCambio = vi.fn()
    render(<SelectorPerfilUi valor="basico" onCambio={onCambio} />)
    fireEvent.change(screen.getByLabelText('Perfil de interfaz'), { target: { value: 'completo' } })
    expect(onCambio).toHaveBeenCalledWith('completo')
  })
})
```

En `frontend/src/__tests__/modoBasico.test.ts`, reemplazar:

```ts
  'pages/hq/InicioBasico.tsx', 'components/layout/PorPerfil.tsx',
]
```

por:

```ts
  'pages/hq/InicioBasico.tsx', 'components/layout/PorPerfil.tsx',
  'components/ui/MasOpciones.tsx', 'pages/platform/SelectorPerfilUi.tsx',
]
```

- [ ] **Step 2: Correr y ver que falla**

Run: `cd frontend && npx vitest run src/components/ui/__tests__/MasOpciones.test.tsx src/pages/core src/pages/platform src/__tests__/modoBasico.test.ts`
Expected: FAIL (no se resuelven `../MasOpciones` ni `../SelectorPerfilUi`; en Empresa básico se ve "Tipo de cambio USD").

- [ ] **Step 3: `MasOpciones.tsx`**

```tsx
// frontend/src/components/ui/MasOpciones.tsx
import { useState, type ReactNode } from 'react'

/**
 * "Más opciones" plegado del modo básico. Con `activo=false` (perfil
 * completo) devuelve los hijos tal cual, sin envoltorio: la pantalla de paga
 * queda idéntica. Con `activo`, los hijos se MONTAN solo al abrir (render
 * condicional, no `hidden`).
 */
export function MasOpciones({ activo, titulo = 'Más opciones', children }: { activo: boolean; titulo?: string; children: ReactNode }) {
  const [abierto, setAbierto] = useState(false)
  if (!activo) return <>{children}</>
  return (
    <div className="space-y-4">
      <button
        type="button"
        onClick={() => setAbierto((a) => !a)}
        aria-expanded={abierto}
        className="dax-btn-secondary text-xs min-h-[44px] sm:min-h-0 w-full sm:w-auto justify-center"
      >
        <i className={`fa-solid ${abierto ? 'fa-chevron-up' : 'fa-chevron-down'}`} aria-hidden="true" /> {titulo}
      </button>
      {abierto && <div className="space-y-4">{children}</div>}
    </div>
  )
}
```

- [ ] **Step 4: `SelectorPerfilUi.tsx`**

```tsx
// frontend/src/pages/platform/SelectorPerfilUi.tsx
import type { CSSProperties } from 'react'

/** Valores de `organization.perfil_ui` (app/services/perfil_ui.py). */
export const OPCIONES_PERFIL_UI = [
  { valor: 'auto', etiqueta: 'Automático (FREE = básico)' },
  { valor: 'basico', etiqueta: 'Básico' },
  { valor: 'completo', etiqueta: 'Completo' },
] as const

/** Selector del perfil de interfaz junto a "Plan y uso". NULL guardado = automático. */
export function SelectorPerfilUi({ valor, onCambio, deshabilitado, estilo }: {
  valor: string | null | undefined
  onCambio: (v: string) => void
  deshabilitado?: boolean
  estilo?: CSSProperties
}) {
  return (
    <select
      value={valor ?? 'auto'}
      onChange={(e) => onCambio(e.target.value)}
      disabled={deshabilitado}
      aria-label="Perfil de interfaz"
      style={estilo}
    >
      {OPCIONES_PERFIL_UI.map((o) => <option key={o.valor} value={o.valor}>{o.etiqueta}</option>)}
    </select>
  )
}
```

- [ ] **Step 5: Tipos**

En `frontend/src/api/organization.ts`, en `Organization`, reemplazar:

```ts
  card_surcharge_pct?: number | string
}
```

(el primer `}` que cierra la interfaz `Organization`) por:

```ts
  card_surcharge_pct?: number | string
  // Modo básico (2026-10). `perfil_ui` lo cambia solo la plataforma; aquí se
  // lee y el PUT de tenant lo descarta. El tope es de "se está acabando".
  perfil_ui?: string | null
  umbral_poca_existencia?: number | null
}
```

En `frontend/src/api/platform.ts`, en `PlatformOrg`, reemplazar:

```ts
  created_at: string
  plan: string | null
}
```

por:

```ts
  created_at: string
  plan: string | null
  /** 'auto' | 'basico' | 'completo'; null = auto. */
  perfil_ui?: string | null
}
```

- [ ] **Step 6: Empresa**

En `frontend/src/pages/core/Organization.tsx`:

1. Después de `import { errorDetailText } from '../../utils/errorDetail'` añadir:

```tsx
import { MasOpciones } from '../../components/ui/MasOpciones'
import { useModoBasico } from '../../store/enabledModulesStore'
```

2. Reemplazar:

```tsx
  const [fxRefreshing, setFxRefreshing] = useState(false)
```

por:

```tsx
  const [fxRefreshing, setFxRefreshing] = useState(false)
  // Modo básico: logo, dólares, comisión y lo boutique del ticket van plegados.
  const modoBasico = useModoBasico()
```

3. Reemplazar:

```tsx
          {/* Logo de la empresa */}
          <DaxCard>
```

por:

```tsx
          <MasOpciones activo={modoBasico}>
          {/* Logo de la empresa */}
          <DaxCard>
```

4. Reemplazar:

```tsx
          </DaxCard>

          {/* Encabezado y pie de ticket */}
```

por:

```tsx
          </DaxCard>
          </MasOpciones>

          {/* Encabezado y pie de ticket */}
```

5. Reemplazar:

```tsx
              <div>
                <label className="dax-label">Términos y condiciones</label>
```

por:

```tsx
              <MasOpciones activo={modoBasico} titulo="Más opciones del ticket">
              <div>
                <label className="dax-label">Términos y condiciones</label>
```

6. Reemplazar:

```tsx
                  <span className="block text-[10px] text-slate-600">Dos líneas al final del ticket con el proveedor del sistema.</span>
                </label>
              </div>
```

por:

```tsx
                  <span className="block text-[10px] text-slate-600">Dos líneas al final del ticket con el proveedor del sistema.</span>
                </label>
              </div>
              </MasOpciones>
```

7. Reemplazar:

```tsx
          </DaxCard>
        </div>
      )}

      {tab === 'branches' && (
```

por:

```tsx
          </DaxCard>

          {/* Modo básico: tope de "Se está acabando" del Inicio. */}
          {modoBasico && (
            <DaxCard>
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-4">
                <i className="fa-solid fa-boxes-stacked mr-1.5" />Lo que se está acabando
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 items-end">
                <div>
                  <label className="dax-label" htmlFor="umbral-poca-existencia">Avisar cuando queden (piezas o menos)</label>
                  <input
                    id="umbral-poca-existencia"
                    type="number" min="0" max="1000" step="1"
                    value={orgForm.umbral_poca_existencia ?? ''}
                    onChange={(e) => setOrgForm((p) => ({ ...p, umbral_poca_existencia: e.target.value === '' ? null : Number(e.target.value) }))}
                    className="dax-input w-full tabular-nums"
                    placeholder="3"
                  />
                  <p className="text-[10px] mt-1 text-slate-600">Vacío = 3. Se ve en Inicio, en «Se está acabando».</p>
                </div>
                <div className="flex justify-end">
                  <button onClick={saveOrg} disabled={saving || nameInvalido} className="dax-btn-primary disabled:opacity-40">
                    {saving ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-check" /> Guardar aviso</>}
                  </button>
                </div>
              </div>
            </DaxCard>
          )}
        </div>
      )}

      {tab === 'branches' && (
```

- [ ] **Step 7: Plataforma — selector junto a "Plan y uso"**

En `frontend/src/pages/platform/PlatformOrgDetail.tsx`:

1. Añadir a los imports (junto a los demás de la página):

```tsx
import { SelectorPerfilUi } from './SelectorPerfilUi'
```

2. Reemplazar:

```tsx
  const [cambiandoPlan, setCambiandoPlan] = useState(false)
```

por:

```tsx
  const [cambiandoPlan, setCambiandoPlan] = useState(false)
  const [cambiandoPerfil, setCambiandoPerfil] = useState(false)
```

3. Reemplazar:

```tsx
    if (idx(nuevo) < idx(actual)) setPlanPendiente(nuevo)
    else aplicarPlan(nuevo)
  }
```

por:

```tsx
    if (idx(nuevo) < idx(actual)) setPlanPendiente(nuevo)
    else aplicarPlan(nuevo)
  }

  // ── Perfil de interfaz (modo básico) ───────────────────────────────────
  // Solo cambia qué se MUESTRA; la tienda lo ve al recargar (vuelve a pedir /me/context).
  const aplicarPerfilUi = async (nuevo: string) => {
    if (nuevo === (org?.perfil_ui ?? 'auto')) return
    setCambiandoPerfil(true)
    try {
      await platformApi.updateOrg(id, { perfil_ui: nuevo })
      toast.success('Perfil de interfaz actualizado')
      await load()
    } catch (err: any) {
      const detalle = err?.response?.data?.detail
      toast.error(typeof detalle === 'string' ? detalle : 'No se pudo cambiar el perfil de interfaz')
    } finally {
      setCambiandoPerfil(false)
    }
  }
```

4. Reemplazar:

```tsx
            ))}
          </select>
        </div>
        {!planUso ? (
```

por:

```tsx
            ))}
          </select>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
          <span style={{ fontSize: 12, color: 'var(--p-muted)' }}>Perfil de interfaz</span>
          <SelectorPerfilUi
            valor={org.perfil_ui}
            onCambio={aplicarPerfilUi}
            deshabilitado={cambiandoPerfil}
            estilo={{ ...inputStyle, width: 'auto', minWidth: 220 }}
          />
        </div>
        {!planUso ? (
```

- [ ] **Step 8: Correr y ver que pasa**

Run: `cd frontend && npx vitest run src/components/ui src/pages/core src/pages/platform src/__tests__`
Expected: PASS (incluida `overlaysFueraDelKit.test.ts`: `Organization.tsx` sigue con 1 overlay).

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/ui/MasOpciones.tsx frontend/src/components/ui/__tests__/MasOpciones.test.tsx \
  frontend/src/pages/platform/SelectorPerfilUi.tsx frontend/src/pages/platform/__tests__/SelectorPerfilUi.test.tsx \
  frontend/src/api/organization.ts frontend/src/api/platform.ts frontend/src/pages/core/Organization.tsx \
  frontend/src/pages/core/__tests__/OrganizationBasico.test.tsx frontend/src/pages/platform/PlatformOrgDetail.tsx \
  frontend/src/__tests__/modoBasico.test.ts
git commit -m "$(cat <<'EOF'
feat(modo-basico): Empresa con Más opciones y tope; perfil en la plataforma

En básico Empresa deja datos, encabezado y pie del ticket y el tope de
"se está acabando"; lo demás va plegado. La plataforma fuerza el perfil
junto a Plan y uso.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf
EOF
)"
```

---

### Task 9: Docs, verificación final y lista para el usuario

**Files:**
- Create: `docs/modo-basico.md`
- Modify: `docs/FRONTEND_VIEWS.md:58-59` (tabla de rutas) y sección nueva antes de `### \`/hq/reports-hub\``
- Modify: `docs/API_REFERENCE.md:24` (`/me/context`), tabla de Reportes (`:147`), sección Platform (`:189`)
- Modify: `docs/DATA_MODEL.md` (tabla de columnas de `organization`, después de `usd_rate_margin`)
- Modify: `CLAUDE.md` §5 (receta nueva después de "Hacer responsiva una pantalla de admin")
- Output (gitignored): `/mnt/d/Devs/atlas-one/.superpowers/sdd/2026-10-19-modo-basico/final/` y `final-resumen.md`

**Interfaces:**
- Consumes: todo lo anterior; baseline de la Tarea 0.
- Produces: docs al día; evidencia de verificación; lista manual para el usuario.

- [ ] **Step 1: `docs/modo-basico.md`**

```markdown
# Modo básico

La interfaz corta para quien no paga licencia (spec: `docs/superpowers/specs/2026-10-18-modo-basico-design.md`).
Solo cambia lo que se **muestra**: el backend no apaga nada y las pantallas completas siguen
abriendo por URL.

## Quién lo ve

`app/services/perfil_ui.py::perfil_efectivo(org)`:

| `organization.perfil_ui` | Plan | Perfil |
|---|---|---|
| `NULL` o `auto` | FREE (o NULL, vacío, desconocido: `plans.obtener_plan`) | básico |
| `NULL` o `auto` | START, PRO, BUSINESS, SCALE, ULTRA_PLUS | completo |
| `basico` | cualquiera | básico |
| `completo` | cualquiera | completo |

Viaja en `GET /api/users/me/context` como `perfil_ui`; el frontend lo lee con `useModoBasico()`
(`store/enabledModulesStore.ts`) y arranca en `completo` hasta que el contexto carga (si falla, se
queda en `completo`).

## Forzar un perfil (plataforma)

`/platform/organizations/{id}` → "Perfil de interfaz", o
`PUT /api/platform/organizations/{id}` con `{"perfil_ui": "completo"}` (`auto` regresa a la regla del
plan). El `PUT /api/organization/` de la tienda lo descarta. La tienda lo ve al recargar.

## Qué esconde

| Dónde | Básico | Dónde vive la lista |
|---|---|---|
| Menú de cajera/gerente | Devoluciones, Etiquetas, Escáner, Clientes, Mi expediente, Reportes, Valor de la tienda | `components/layout/navPerfilBasico.ts` (`OCULTAS_BASICO_SUCURSAL`) |
| Menú de la dueña | Control, Catálogo, Departamentos, Marcas, Etiquetas, Escáner, Clientes, Sucursales, Inventario, Existencias, Ventas HQ, Devoluciones HQ, Valor de la tienda, Resumen móvil, Mi expediente, IA, Cotizaciones, Pedidos, Compras, Gastos | `navPerfilBasico.ts` (`OCULTAS_BASICO_HQ`) |
| POS | descuentos, botón Cliente, dólares, editar producto, forzar precio por pieza; el alta rápida usa el formulario corto | `pages/pos/opcionesPos.ts` |
| Formulario de producto | marca, descripción, unidad, foto, tasa de IVA, empaques, tallas (y la matriz con una sola sucursal) | `app/modules/products/campos.py` (`OCULTOS_BASICO`) |
| Productos | importador, plantilla, etiquetas CSV, generar códigos, rejilla | `pages/inventory/Products.tsx`, `components/branch/ProductsBranchView.tsx` |
| Inicio y Reportes de la dueña | `/hq/operations` → `InicioBasico`; `/hq/reports-hub` → `finance/Reports` | `App.tsx` (`<PorPerfil>`) |
| Empresa | logo, dólares, comisión y lo boutique del ticket bajo "Más opciones"; aparece el tope de "Se está acabando" | `pages/core/Organization.tsx` (`<MasOpciones>`) |

Un dato que ya existe (una marca, un descuento de un ticket pausado) se sigue viendo.
```

- [ ] **Step 2: Docs de referencia**

`docs/FRONTEND_VIEWS.md`: reemplazar las dos filas de la tabla de rutas:

```markdown
| `/hq/operations` | `hq/HQOperations` | Admin, Dueño | pos |
| `/hq/reports-hub` | `hq/HQReportsHub` | Admin, Dueño | pos |
```

por:

```markdown
| `/hq/operations` | `hq/HQOperations` · en modo básico `hq/InicioBasico` | Admin, Dueño | pos |
| `/hq/reports-hub` | `hq/HQReportsHub` · en modo básico `finance/Reports` | Admin, Dueño | pos |
```

e insertar antes de la línea `### \`/hq/reports-hub\` — Reportes HQ (Ultra) 📱`:

```markdown
### `/hq/operations` en modo básico — Inicio básico 📱
- **Archivo:** `pages/hq/InicioBasico.tsx` (chunk propio, sin chart.js); lo monta `components/layout/PorPerfil.tsx` cuando `perfil_ui = basico` (ver `docs/modo-basico.md`).
- **Propósito:** "¿Cómo voy?": vendido hoy, ayer y 7 días; cobros de hoy por método; caja (turno abierto/cerrado, quién, efectivo esperado); lo que se está acabando (tope de Empresa); lo más vendido; valor de la tienda (`ValorTiendaCard`).
- **Datos/API:** `reportsApi.inicioBasico` (`GET /reports/inicio-basico`) y `reportsApi.valorInventario`.
- **Responsivo:** kit `ui/`; listas con tabla en escritorio y `TarjetaFila` bajo 768 (`useEsTelefono`). Está en `PAGINAS` de `responsivoOla2.test.ts`.

```

`docs/API_REFERENCE.md`:
- En la fila `| GET | /me/context | …`, reemplazar ` · \`campos_producto\` \`{visibles, ocultos}\`:` por ` · \`perfil_ui\` (\`basico\`|\`completo\`; FREE → básico, forzable por la plataforma; ver \`docs/modo-basico.md\`) · \`campos_producto\` \`{visibles, ocultos}\` (en básico además oculta \`brand_id, description, unit, image_url, tax_rate, packaging_units, variants\`):`.
- En la tabla de Reportes, después de la fila de `/valor-inventario`, añadir:

```markdown
| **/inicio-basico** `?branch_id=` | Inicio del modo básico (2026-10), una sola llamada: `hoy`/`ayer`/`semana` `{desde, hasta, total, tickets}` (7 días incluido hoy, `SALES_REPORT_STATUSES`), `por_metodo_hoy` (de `daily-summary`, sin vuelto), `top_semana[]` (máx. 5 por piezas), `poca_existencia {umbral, productos[]}` (existencia por variante ≤ `organization.umbral_poca_existencia` o 3, máx. 10, activos y no borrados; sin `branch_id` solo sucursales activas que venden) y `corte {estado: abierto\|cerrado\|sin_turno, cajera, abierto_en, cerrado_en, efectivo_esperado, efectivo_contado}`. ADMIN/DUEÑO/SUPERADMIN: org o sucursal pedida (404 si es de otra org); GERENTE: siempre la suya; demás 403. Vive en `app/routers/reports_inicio.py`. |
```

- En la sección `## Platform (SaaS)`, añadir al final de su lista: ``- `PUT /api/platform/organizations/{id}` acepta `perfil_ui` (`auto`\|`basico`\|`completo`, 422 si es otro); el `PUT /api/organization/` de tenant lo descarta como a `plan`. `OrganizationRead` expone `perfil_ui` y `umbral_poca_existencia` (este sí lo guarda la dueña).``

`docs/DATA_MODEL.md`: después de la fila de `usd_rate_margin` en la tabla de columnas de `organization` añadir:

```markdown
| `perfil_ui` | `String(12)` | `NULL` | Modo básico (2026-10): `NULL`/`auto` = se deriva del plan (FREE → básico), `basico`/`completo` = forzado por la plataforma. Solo decide qué muestra la interfaz (`app/services/perfil_ui.py`) |
| `umbral_poca_existencia` | `Integer` | `NULL` | Tope en piezas de "Se está acabando" del Inicio básico; `NULL` = 3. Lo guarda la dueña en Empresa |
```

`CLAUDE.md` §5: después del punto 6 de "Hacer responsiva una pantalla de admin" (antes de la línea `---` de la sección 6) añadir:

```markdown

### Esconder algo en modo básico
- El perfil (`basico` | `completo`) sale de `app/services/perfil_ui.py::perfil_efectivo` (FREE → básico; la plataforma lo fuerza con `organization.perfil_ui`) y viaja en `/me/context.perfil_ui`. En pantalla: `useModoBasico()`.
- Menú: `OCULTAS_BASICO_SUCURSAL` / `OCULTAS_BASICO_HQ` en `components/layout/navPerfilBasico.ts`. POS: banderas de `opcionesPorPerfil` (`pages/pos/opcionesPos.ts`). Campos del producto: `OCULTOS_BASICO` en `app/modules/products/campos.py`. Pantalla entera: `<PorPerfil basico completo>` en `App.tsx`. Una sección: `<MasOpciones activo={modoBasico}>`.
- Siempre render condicional (nunca `hidden`), sin tocar el backend, y lo que ya trae un dato se sigue viendo. Detalle: `docs/modo-basico.md`.
```

- [ ] **Step 3: Suite completa**

Run: `python3 -m pytest -q -p no:warnings --ignore=tests/test_cash_complete.py 2>&1 | tail -3`
Expected: `passed` = baseline de la Tarea 0 + las nuevas (≈ +48); `failed`/`errors` iguales al baseline.

Run: `cd frontend && npx vitest run 2>&1 | tail -4 && npm run build && cd .. && python3 scripts/presupuesto_bundle.py --dist frontend/dist --presupuesto frontend/presupuesto_bundle.json`
Expected: vitest todo verde (baseline + las nuevas); build sin errores; presupuesto en 0 con el mismo `tope_bytes`.

Run: `git diff main --stat -- frontend/presupuesto_bundle.json frontend/src/__tests__/overlaysFueraDelKit.test.ts`
Expected: vacío (ni el presupuesto ni el inventario de overlays cambiaron).

- [ ] **Step 4: Capturas finales**

```bash
S=$SCRATCH/modo-basico/capturas
B=/mnt/d/Devs/atlas-one/.superpowers/sdd/2026-10-19-modo-basico/baseline
cd $S && bash stack.sh up   # arrancar de nuevo: Vite en /mnt/d no detecta cambios
export DATABASE_URL="sqlite:///$S/responsivo.db" PYTHONPATH=/mnt/d/Devs/atlas-one/.worktrees/modo-basico
# la base del baseline no tiene las columnas nuevas: se agregan con el mismo ALTER del despliegue
python3 -c "
from sqlalchemy import create_engine
from scripts.railway_init import COLUMN_MIGRATIONS, aplicar_migraciones_de_columna
eng = create_engine('$DATABASE_URL')
with eng.connect() as c:
    print(aplicar_migraciones_de_columna(c, [m for m in COLUMN_MIGRATIONS if m[0] == 'organization']))
"
F=/mnt/d/Devs/atlas-one/.superpowers/sdd/2026-10-19-modo-basico/final
RA=/hq/operations,/hq/reports-hub,/products,/organization; RC=/pos,/products

# 1) De paga: idéntica píxel a píxel a 1440
python3 plan_demo.py ULTRA_PLUS
node capturas.mjs --out $F/completo-admin --anchos 1440 --rutas $RA --usuario demo_pos
node capturas.mjs --out $F/completo-cajero --anchos 1440 --rutas $RC --usuario demo_cajero_pos
node diff1440.mjs $B/completo-admin $F/completo-admin; node diff1440.mjs $B/completo-cajero $F/completo-cajero

# 2) FREE forzada a completo: igual que la FREE de antes (Review Focus #4)
python3 plan_demo.py FREE completo
node capturas.mjs --out $F/free-completo-admin --anchos 1440 --rutas $RA --usuario demo_pos
node capturas.mjs --out $F/free-completo-cajero --anchos 1440 --rutas $RC --usuario demo_cajero_pos
node diff1440.mjs $B/free-antes-admin $F/free-completo-admin; node diff1440.mjs $B/free-antes-cajero $F/free-completo-cajero

# 3) FREE en básico: sin desborde a 390/768/1024 (y 1440 para revisar a ojo)
python3 plan_demo.py FREE
node capturas.mjs --out $F/basico-admin --rutas $RA --usuario demo_pos
node capturas.mjs --out $F/basico-cajero --rutas $RC --usuario demo_cajero_pos
bash stack.sh down
```

Expected:
1. `diff1440.json` de `completo-*` y de `free-completo-*`: **0 píxeles distintos** en cada clave (incluidas las `__modal`/`__formulario` de `/products`). Si una clave difiere, el diff PNG dice dónde; un cambio en completo es un bug de esta rama, no una excepción a documentar.
2. `basico-*/desbordes.json`: ninguna clave con `desborda: true` a 390, 768 ni 1024; `tap < 44` sin entradas nuevas respecto a `free-antes-*` en las mismas rutas.
3. A ojo en `basico-admin`: menú de 8, `/hq/operations` con "¿Cómo voy?", `/hq/reports-hub` con los Reportes de la cajera, Empresa con "Más opciones"; en `basico-cajero`: menú de 6, POS sin Cliente, descuentos ni dólares.

Escribir `final-resumen.md` con los tres puntos y la ruta de cada diff.

- [ ] **Step 5: Commit de docs**

```bash
git add docs/modo-basico.md docs/FRONTEND_VIEWS.md docs/API_REFERENCE.md docs/DATA_MODEL.md CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(modo-basico): perfil de interfaz, Inicio básico y receta para esconder

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf
EOF
)"
```

- [ ] **Step 6: Lista para el usuario (manual, no la corre el agente)**

Antes de fusionar (push/merge solo con su permiso):

1. **Qué orgs caen en básico en producción** (solo lectura, la corre el usuario con `!` en el VPS):

   ```sql
   SELECT id, name, plan FROM organization
   WHERE is_active AND coalesce(plan, '') NOT IN ('START', 'PRO', 'BUSINESS', 'SCALE', 'ULTRA_PLUS')
   ORDER BY id;
   ```

   Esperado: Kaory 14, Ginebra 15, Imaltzin 16, Coqueta 18 y cualquier demo/QA con plan NULL, `Demo` o desconocido (decisión 8). A las demo/QA que deban verse completas, forzarles `completo` desde `/platform/organizations/{id}` justo después del despliegue.
2. **Forzar y regresar en producción:** a una FREE, "Perfil de interfaz" → Completo, recargar su sesión y ver el menú de siempre; regresar a Automático y ver el básico.
3. **10 minutos con la cajera de Kaory:** cobrar con escalón (Mayoreo/Caja), editar el precio de un renglón ("Servicios" a importe libre), pausar y retomar, reimprimir con PIN, devolver desde Mis ventas, crear un producto desde el POS (formulario corto).
4. **10 minutos con Mirna (Coqueta):** Inicio (¿cuadra lo de hoy y la caja con lo que ve en Corte?), Corte, Reportes, Empresa → tope de "se está acabando".
5. **Pendiente de confirmar con el usuario:** el desglose de comisión de tarjeta se dejó visible (decisión 2). Lo que la cajera eche de menos vuelve al perfil en un commit de seguimiento antes de fusionar (spec §7): mover la URL fuera de `OCULTAS_BASICO_*` o poner en `true` la bandera de `opcionesPorPerfil`.

---

## Self-review (hecho al cerrar el plan)

**1. Cobertura del spec.**
- §3.1 perfil derivado y forzable → T1. §3.2 nada se apaga → Global Constraints; único endpoint nuevo en T3. §3.3 la cajera conserva lo suyo y no se toca `saneaCobro` → T6 (prueba de que cobrar/pausar/Aplicar caja siguen). §3.4 Inicio + menú de 8 → T4 y T7. §3.5 formulario corto por `campos_producto` → T2 y T5. §3.6 kit y guardas → T7 (`PAGINAS`), T6-T8 (`modoBasico.test.ts`), T9 (capturas). §3.7 fuera de alcance respetado (sin plataforma salvo el selector, T8).
- §4.1 menú de 6 → T4; POS: descuentos, Cliente, dólares, editar producto, forzar pieza → T6; propina/factura ya por capacidad (sin cambio); comisión → decisión 2; nota/diagnóstico/asistente → decisión 1; alta rápida corta → T6. Productos de sucursal → T5 (decisión 11).
- §4.2 menú de 8 → T4 (decisión 4 y 7); Inicio básico (hoy/ayer/semana, efectivo vs tarjeta, corte, poca existencia ≤ tope máx. 10, top 5, valor de la tienda, kit) → T3 + T7; Reportes → T7 (decisión 5); Productos HQ y formulario corto (escalones como "Precio por cantidad", sin matriz con una sucursal) → T5; Empresa → T8 (decisión 12); Usuarios sin cambios.
- §5 backend (columnas, ALTER, `perfil_efectivo`, contexto, PUTs, endpoint) → T1-T3. Frontend (store, nav, App, POS, Formulario, Products, InicioBasico, Organization, plataforma, guardas, presupuesto) → T4-T8.
- §6 pruebas y capturas → cada tarea + T0/T9. Manual → T9 Step 6. §7 sale cuando → T9 Steps 3-4.

**2. Placeholders.** Sin "TBD", "similar a", ni pasos sin código. Las rutas del scratchpad se dan como `$SCRATCH`, `$S`, `$B`, `$F` porque dependen de la sesión que ejecute; la Tarea 0 las define.

**3. Consistencia de nombres.** `perfil_ui` (backend/JSON) ↔ `perfilUi` (store) ↔ `PerfilUi` (tipo); `useModoBasico()` en T5, T8; `opcionesPorPerfil` y sus 6 banderas iguales en T6 (prueba, implementación, CartPanel, ProductSearch, POS); `OCULTOS_BASICO` (backend, T2) y la lista de ocultos de las pruebas jsdom de T5/T6 coinciden; la forma JSON de `inicio-basico` de T3 Interfaces es la de los tipos y el fixture `DATOS` de T7; `PorPerfil`, `InicioBasico`, `AltaRapidaProducto`, `MasOpciones`, `SelectorPerfilUi` con las mismas firmas en Produces y en uso.

**4. Review Focus.** Cada línea tiene su prueba en la tarea dueña: #1 T4 (store) + T6 (CartPanel sin cargar) + T7 (PorPerfil); #2 T5; #3 T5 (dos pruebas); #4 T1 + T2 + T4 + T9; #5 T6 (`AltaRapidaProducto`).
