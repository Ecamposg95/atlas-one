# Fase 2 · Inicio, Reportes y tema — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** El Inicio del administrador con las cuatro gráficas y variaciones, una sola pantalla de Reportes (`pages/reports/Reportes.tsx`) por periodos con comparativo, un kit de gráficas sobre react-chartjs-2 que se repinta con el tema, y las pantallas de esta fase pintadas solo con tokens `dax-*` (guardia `coloresPorTokens.test.ts`).

**Architecture:** El backend solo suma campos a dos respuestas que ya existen (`/reports/inicio`: `tendencia`, `por_hora_hoy`, `utilidad_bruta_ayer`; `/reports/dashboard`: utilidad bruta y el importe del top), todo calculado por `app/services/metricas_ventas.py`. En el frontend, `components/graficas/` envuelve chart.js (una sola registración, colores leídos de las variables `--dax-*` con `getComputedStyle` y releídos al cambiar la clase de `<html>`), `components/ui/KpiCard.tsx` sustituye a `KPICard` y a la `Cifra` del Inicio, el Inicio carga sus gráficas con `lazy()` desde `pages/hq/InicioGraficas.tsx` solo en perfil completo (el chunk `charts` no baja en básico), y `pages/reports/Reportes.tsx` reemplaza a `finance/Reports.tsx` y `hq/HQReportsHub.tsx` para todos los roles. Nada de la Fase 3 (fusiones, menú, redirects) se toca.

**Tech Stack:** FastAPI + SQLAlchemy + pytest (SQLite con shims `timezone`/`to_char` en `tests/conftest.py`); React 18 + Vite + TypeScript + Tailwind (tokens `dax` en `tailwind.config.js`), chart.js 4.5 + react-chartjs-2 5.3 (ya instalados, chunk `charts` en `vite.config.ts`), vitest 2 + @testing-library/react 16 (jsdom 25).

**Spec:** `docs/superpowers/specs/2026-10-23-admin-precision-inicio-fusiones-design.md` — §3 (3.1 Inicio, 3.2 Reportes, 3.3 Gráficas y tarjetas, 3.4 Tema por tokens), §5, §6, §7, §8. §2 (Fase 1) ya está en `main` (b8d6f3c6); §4 (Fase 3) NO es de este plan.

## Global Constraints

- **Worktree:** `/mnt/d/Devs/atlas-one/.worktrees/admin-fase2`, rama `feat/admin-fase2-inicio-reportes` (base `main` b8d6f3c6). Todas las rutas de este plan son relativas a esa raíz. `frontend/node_modules` es un enlace al checkout principal: `npm ci` no hace falta.
- **Nada de la Fase 3:** no tocar `components/layout/navConfig.ts`, redirects de `App.tsx`/`app/main.py`, ni las pantallas duplicadas (`HQSalesLog`, `HQReturns`, `HQInventory`, `AdminCatalog`, `SalesHistory`, `Returns`, `Inventory`, `Products`). Los enlaces del Inicio a `/hq/inventory`, `/hq/sales`, `/hq/returns` se conservan tal cual.
- **Regla de venta:** todo número sale de `app/services/metricas_ventas.py` (neta = cobradas − devoluciones aprobadas, día de México). Ningún router escribe otro `status.in_(...)` a mano.
- **Gráficas (spec §3.3):** envoltorios de react-chartjs-2 en `frontend/src/components/graficas/`; registración de chart.js una sola vez (`registro.ts`); animación de **300 ms**; **sin degradados ni relleno** (`fill: false`, sin `createLinearGradient`); ejes con moneda abreviada (`$1.2k`, `dineroCorto`); tooltips con `formatCurrency`. Colores: serie principal = `--dax-accent`; comparativo = `--dax-text-faint`; métodos: `CASH` = `--dax-success`, `CARD` = `--dax-accent`, `TRANSFER` = `--dax-warning`, otros = `--dax-text-faint`. `useTemaGrafica()` lee `--dax-text-muted`, `--dax-border-dim`, `--dax-accent`, `--dax-success`, `--dax-warning`, `--dax-danger` (y `--dax-text`, `--dax-text-faint`, `--dax-card-solid`) con `getComputedStyle(document.documentElement)` y se vuelve a leer cuando cambia la clase de `<html>` (MutationObserver).
- **Tokens (spec §3.4):** en `pages/hq/`, `pages/home/`, `pages/finance/`, `pages/sales/`, `pages/inventory/`, `pages/core/`, `pages/reports/`, `components/reports/`, `components/graficas/` no se escribe `text-white`, `text-slate-*`, `bg-slate-*`, `border-slate-*` ni hex sueltos (`#rrggbb`). Los archivos que esta fase crea o reescribe (`Inicio.tsx`, `InicioGraficas.tsx`, `Reportes.tsx`, `presetsReportes.ts`, `Heatmap.tsx`, `ValorTiendaCard.tsx`, `components/graficas/*`, `components/ui/KpiCard.tsx`) tampoco usan ninguna clase de paleta Tailwind (`emerald`, `rose`, `amber`, `indigo`, `violet`, `sky`…): solo `text-dax-*`, `bg-dax-*`, `border-dax-*` (`tailwind.config.js` → `colors.dax`: `bg`, `surface`, `card`, `border`, `border-dim`, `accent`, `accent-text`, `accent-soft`, `on-accent`, `text`, `muted`, `faint`, `elevated`, `success`, `warning`, `danger`, `success-soft`, `warning-soft`, `danger-soft`). **Sin `!important` nuevos** en `index.css`.
- **Tipografía:** títulos de sección con `dax-section-title` y formulados como pregunta; cifras con `dax-kpi-label` / `dax-kpi-value` (ya existen en `index.css:612-632`; no se redefinen). Un solo `CabeceraPagina` por pantalla.
- **Modo básico (`perfilUi === 'basico'`):** el Inicio sigue sin gráficas y sin cargar el chunk `charts`; `/hq/reports-hub` y `/reports` montan el mismo `Reportes`.
- **Responsivo (CLAUDE.md §5):** `useEsTelefono()`; `CabeceraPagina`, `BarraFiltros`; `<table>` en escritorio y `ListaTarjetas`/`TarjetaFila` bajo 768 con render condicional (`esTelefono ? … : …`), nunca `hidden md:block`; rejillas de 3+ columnas siempre con prefijo (`lg:grid-cols-12`); botones `dax-btn-primary/-secondary/-danger/-ghost`; ningún `fixed inset-0` nuevo. En `pages/hq/` no hay `style={{` salvo líneas con el comentario `estilo dinámico` (`pages/__tests__/hqSinEstilosInline.test.ts`).
- **Presupuesto:** `frontend/presupuesto_bundle.json` no cambia; `charts-*` sigue fuera de la precarga del POS.
- **Pruebas backend:** `python3 -m pytest -q -p no:warnings <archivo>`; suite completa `python3 -m pytest -q -p no:warnings --ignore=tests/test_cash_complete.py --ignore=tests/test_branch_dashboard.py --ignore=tests/test_cash_close_guided.py` (hoy 1627 passed tras sincronizar la rama con `main` 78a191fb, que trae Cancelar conteo; los dos últimos fallan en esta máquina por un uvicorn ajeno en :8000). **Un solo pytest por worktree.** Las pruebas crean filas reales con las fixtures de `tests/conftest.py`.
- **Pruebas frontend:** `cd frontend && npx vitest run <rutas> --reporter=dot`; `npx tsc --noEmit -p tsconfig.json` (excluye `*.test.ts(x)`); `npm run build`. Las pruebas de pantallas usan los stores reales (`useAuthStore.setState`, `useEnabledModulesStore.setState`) y `vi.mock` para los módulos de API (patrón de `pages/hq/__tests__/Inicio.test.tsx`); jsdom no tiene canvas, así que `react-chartjs-2` o el kit `components/graficas` se sustituyen con stubs que exponen las series recibidas (patrón de `components/platform/v2/__tests__/TrendChart.test.tsx`).
- **Estilo:** comentarios e identificadores en español; Pydantic v2; type hints; sin `print()`.
- **Commits:** uno por tarea, con `git add` de rutas explícitas y los trailers
  `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` y
  `Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf`. **Nunca push ni merge**: la fusión la autoriza el usuario.

## Review Focus

1. **Un día con más devoluciones que ventas** deja netas negativas en la tendencia y en las horas: los ejes deben formatearlo (`-$1.2k`) y la dona no debe recibir valores negativos (Tarea 3, `formato.test.ts` «negativos con signo» y `graficas.test.tsx` «la dona recorta negativos a cero»); una variación contra una referencia ≤ 0 dice «Sin referencia» en vez de dividir entre cero (Tarea 4, `variacion.test.ts` «sin referencia cuando el anterior es cero o negativo»).
2. **Catálogo sin costos** (Imaltzin, lotes de Eleven por WhatsApp): Reportes no pinta «Utilidad bruta» cuando nada de lo vendido tiene costo aunque el backend mande `gross_profit` (Tarea 8, `Reportes.test.tsx` «oculta la utilidad bruta sin costo o sin permiso»).
3. **Cajera en `/reports`:** sin selector de sucursal y sin llamar a `/reports/command-center/stats`, que es de toda la organización y no tiene guardia de rol (Tarea 8, `Reportes.test.tsx` «sin selector no pide sucursales ni el centro de mando»).
4. **Cambiar de tema con una gráfica en pantalla:** los colores se vuelven a leer de `<html>` al cambiar la clase (Tarea 3, `tema.test.tsx` «se vuelve a leer al cambiar la clase de <html>»).
5. **Perfil básico en `/hq/operations`:** nunca se pide el módulo `InicioGraficas` (Tarea 6, `Inicio.test.tsx` «en básico no monta ninguna gráfica…» y las aserciones estáticas de `modoBasico.test.ts`: `lazy(() => import('./InicioGraficas'))` y solo `import type`); el presupuesto de la ruta crítica del POS no cambia (Tarea 11, paso 4).

---

### Task 1: `/reports/inicio` gana `tendencia`, `por_hora_hoy` y `utilidad_bruta_ayer`

**Files:**
- Modify: `app/schemas/reports.py:150-155` (`InicioResponse`) y añadir tres clases antes de ella
- Modify: `app/routers/reports_inicio.py:2-17` (docstring), `:313-353` (`inicio`), añadir `_tendencia` y `_por_hora_hoy`
- Modify: `tests/test_reports_inicio.py:248-249` (conjunto de claves) y añadir casos al final
- Modify: `docs/API_REFERENCE.md:148` (fila `/inicio`)

**Interfaces:**
- Consumes: `mv.por_dia(db, ambito, periodo) -> list[DiaVentas(fecha, bruta, devuelto, neta, tickets)]`, `mv.por_hora(db, ambito, periodo) -> list[HoraVentas(hora, neta, tickets)]` (24), `mv.utilidad_bruta(db, ambito, periodo) -> (utilidad, venta_sin_costo)`, `mv.Periodo.anterior()`, `_ambito`, `DIAS_SEMANA = 7`, `_ve_costos` (todo ya en `reports_inicio.py`).
- Produces (JSON de `GET /api/reports/inicio?completo=true`): `tendencia: {dias: [{fecha, neta, tickets}] × 7, anterior: [...] × 7}`, `por_hora_hoy: [{hora, neta, tickets}] × 24`, `utilidad_bruta_ayer: float | null`. Sin `completo`, los tres van en `null`. El frontend (Tareas 5-6) los lee como `Inicio.tendencia`, `Inicio.por_hora_hoy`, `Inicio.utilidad_bruta_ayer`.

**Decisión (la spec no lo dice):** los tres campos viajan **solo con `completo=true`**. El Inicio básico no pinta gráficas (spec §3.1) y el contrato de SP6 es «lo que no se pinta no se consulta»: una FREE en una PC vieja no paga seis consultas (dos `por_dia`, una `por_hora`, una `utilidad_bruta`, cada una con su par documentos/devoluciones) para nada. La variación «Hoy vs ayer» sí sale en básico porque `hoy` y `ayer` ya vienen.

- [ ] **Step 1: Escribir las pruebas que fallan**

En `tests/test_reports_inicio.py`, cambiar el conjunto de claves de `test_alias_inicio_basico_sigue_respondiendo` (líneas 248-249) por:

```python
    assert set(a) == {"branch_id", "hoy", "ayer", "semana", "por_metodo_hoy", "top_semana", "poca_existencia", "corte",
                      "sin_movimiento", "pendientes", "sucursales", "utilidad_bruta_hoy", "venta_sin_costo_hoy",
                      "tendencia", "por_hora_hoy", "utilidad_bruta_ayer"}
```

Y añadir al final del archivo:

```python
# ── Fase 2 (spec 2026-10-23 §3.1): tendencia de 7 días, horas de hoy y utilidad de ayer ──

def test_inicio_completo_trae_tendencia_de_7_dias_y_los_7_anteriores(client, db, org, branch_a, admin_user, auth_admin):
    v = _variante(db, org, branch_a, "Blusa", "BLU-1", 50)
    tarde = _venta(db, org, branch_a, admin_user, v, "100")
    tarde.created_at = _instante(0, hora=19)        # 01:00 UTC de mañana: sigue siendo hoy en México
    _venta(db, org, branch_a, admin_user, v, "70", dias_atras=6)      # primer día del tramo actual
    _venta(db, org, branch_a, admin_user, v, "999", dias_atras=7)     # último día del comparativo
    _venta(db, org, branch_a, admin_user, v, "5", dias_atras=14)      # fuera de los dos tramos
    db.commit()

    t = client.get(f"{INICIO}?completo=true", headers=auth_admin).json()["tendencia"]

    hoy = datetime.now(_MX).date()
    assert [d["fecha"] for d in t["dias"]] == [str(hoy - timedelta(days=6 - i)) for i in range(7)]
    assert [d["neta"] for d in t["dias"]] == [70.0, 0.0, 0.0, 0.0, 0.0, 0.0, 100.0]
    assert [d["tickets"] for d in t["dias"]] == [1, 0, 0, 0, 0, 0, 1]
    assert [d["fecha"] for d in t["anterior"]] == [str(hoy - timedelta(days=13 - i)) for i in range(7)]
    assert [d["neta"] for d in t["anterior"]] == [0.0] * 6 + [999.0]


def test_inicio_tendencia_respeta_la_sucursal_pedida(client, db, org, branch_a, branch_b, admin_user, auth_admin):
    v = _variante(db, org, branch_a, "Blusa", "BLU-1", 50)
    _venta(db, org, branch_a, admin_user, v, "100")
    _venta(db, org, branch_b, admin_user, v, "700")
    t = client.get(f"{INICIO}?completo=true&branch_id={branch_a.id}", headers=auth_admin).json()["tendencia"]
    assert t["dias"][-1]["neta"] == 100.0
    assert client.get(f"{INICIO}?completo=true", headers=auth_admin).json()["tendencia"]["dias"][-1]["neta"] == 800.0


def test_inicio_por_hora_hoy_trae_24_horas_en_hora_de_mexico(client, db, org, branch_a, admin_user, auth_admin):
    v = _variante(db, org, branch_a, "Blusa", "BLU-1", 50)
    tarde = _venta(db, org, branch_a, admin_user, v, "100")
    tarde.created_at = _instante(0, hora=19)
    dev = SaleReturn(organization_id=org.id, sale_id=tarde.id, user_id=admin_user.id, branch_id=branch_a.id,
                     total_refunded=Decimal("40"), refund_method=PaymentMethod.CASH, reason="Prueba", status="APPROVED")
    dev.created_at = _instante(0, hora=20)
    db.add(dev)
    db.commit()

    h = client.get(f"{INICIO}?completo=true", headers=auth_admin).json()["por_hora_hoy"]

    assert [x["hora"] for x in h] == list(range(24))
    assert h[19] == {"hora": 19, "neta": 100.0, "tickets": 1}
    assert h[20] == {"hora": 20, "neta": -40.0, "tickets": 0}   # la devolución resta en su hora


def test_inicio_sin_completo_no_trae_tendencia_horas_ni_utilidad_de_ayer(client, db, org, branch_a, admin_user, auth_admin):
    _variante(db, org, branch_a, "Blusa", "BLU-1", 50)
    db.commit()
    d = client.get(INICIO, headers=auth_admin).json()
    assert d["tendencia"] is None and d["por_hora_hoy"] is None and d["utilidad_bruta_ayer"] is None


def test_inicio_utilidad_bruta_ayer_para_admin_y_null_para_gerente(client, db, org, branch_a, admin_user, gerente_a, auth_admin, auth_gerente_a):
    v = _variante(db, org, branch_a, "Blusa", "BLU-1", 50)
    _venta(db, org, branch_a, admin_user, v, "100", cantidad=2, dias_atras=1)   # 100 − 10 × 2 = 80
    d = client.get(f"{INICIO}?completo=true", headers=auth_admin).json()
    assert d["utilidad_bruta_ayer"] == 80.0
    assert client.get(f"{INICIO}?completo=true", headers=auth_gerente_a).json()["utilidad_bruta_ayer"] is None
```

- [ ] **Step 2: Correr y ver que falla**

Run: `python3 -m pytest -q -p no:warnings tests/test_reports_inicio.py`
Expected: 6 fallos (`assert set(a) == …` y `KeyError: 'tendencia'` / `'por_hora_hoy'` / `'utilidad_bruta_ayer'`).

- [ ] **Step 3: Schemas**

En `app/schemas/reports.py`, antes de `class InicioResponse` (línea 150), añadir:

```python
class DiaTendencia(BaseModel):
    fecha: date
    neta: float      # cobradas − devoluciones aprobadas de ese día (día de México)
    tickets: int


class Tendencia(BaseModel):
    dias: List[DiaTendencia]       # hoy y los 6 anteriores, en orden
    anterior: List[DiaTendencia]   # los 7 días previos a `dias`, en orden


class HoraInicio(BaseModel):
    hora: int        # 0..23, hora de México
    neta: float
    tickets: int
```

Y dentro de `InicioResponse`, después de `venta_sin_costo_hoy` (línea 155):

```python
    # Fase 2 (spec §3.1): solo con `completo=true`; el Inicio básico no pinta gráficas y no las paga.
    tendencia: Optional[Tendencia] = None
    por_hora_hoy: Optional[List[HoraInicio]] = None     # 24 renglones; el frontend recorta la ventana
    utilidad_bruta_ayer: Optional[float] = None         # para la variación de la utilidad de hoy; None sin costos
```

- [ ] **Step 4: Router**

En `app/routers/reports_inicio.py`:

1. En el import de `app.schemas.reports` (líneas 35-38) añadir `DiaTendencia, HoraInicio, Tendencia`.
2. Al final del docstring del módulo (antes de la línea `"""` de cierre, línea 17) añadir el párrafo:

```
Fase 2 (2026-10-24): con `completo=true` también viajan `tendencia` (7 días y
los 7 previos, para la línea y las variaciones), `por_hora_hoy` (24 horas) y
`utilidad_bruta_ayer`. En básico van en None y no se consultan.
```

3. Después de `_utilidad_bruta_hoy` (línea 238) añadir:

```python
def _tendencia(db: Session, org_id: int, sucursal: Optional[int], hoy: date) -> Tendencia:
    """Venta neta por día: hoy y los 6 anteriores, y los 7 previos como comparativo."""
    periodo = mv.Periodo(hoy - timedelta(days=DIAS_SEMANA - 1), hoy)
    ambito = _ambito(org_id, sucursal)

    def _dias(filas) -> List[DiaTendencia]:
        return [DiaTendencia(fecha=d.fecha, neta=d.neta, tickets=d.tickets) for d in filas]

    return Tendencia(dias=_dias(mv.por_dia(db, ambito, periodo)),
                     anterior=_dias(mv.por_dia(db, ambito, periodo.anterior())))


def _por_hora_hoy(db: Session, org_id: int, sucursal: Optional[int], hoy: date) -> List[HoraInicio]:
    return [HoraInicio(hora=h.hora, neta=h.neta, tickets=h.tickets)
            for h in mv.por_hora(db, _ambito(org_id, sucursal), mv.Periodo(hoy, hoy))]
```

4. En `inicio()`, sustituir el bloque final (líneas 347-353) por:

```python
    respuesta.sin_movimiento = _sin_movimiento(db, org_id, sucursal, dias_sin_movimiento)
    respuesta.pendientes = _pendientes(db, org_id, sucursal)
    respuesta.tendencia = _tendencia(db, org_id, sucursal, hoy)
    respuesta.por_hora_hoy = _por_hora_hoy(db, org_id, sucursal, hoy)
    # El gerente ya viene fijado a su sucursal: la sección de sucursales no aplica.
    respuesta.sucursales = _sucursales(db, org_id, hoy, umbral) if sucursal is None else None
    if _ve_costos(current_user):
        respuesta.utilidad_bruta_hoy, respuesta.venta_sin_costo_hoy = _utilidad_bruta_hoy(db, org_id, sucursal, hoy)
        respuesta.utilidad_bruta_ayer, _ = mv.utilidad_bruta(db, _ambito(org_id, sucursal), mv.Periodo(ayer, ayer))
    return respuesta
```

- [ ] **Step 5: Correr y ver que pasa**

Run: `python3 -m pytest -q -p no:warnings tests/test_reports_inicio.py tests/test_metricas_ventas.py`
Expected: todo en verde.

- [ ] **Step 6: Documentar**

En `docs/API_REFERENCE.md`, fila `**/inicio**` (línea 148), después de «`venta_sin_costo_hoy` (lo vendido hoy sin costo).» insertar: «Fase 2 (2026-10-24), también solo con `completo=true`: `tendencia {dias[7]{fecha, neta, tickets}, anterior[7]}` (hoy y 6 anteriores / los 7 previos, netos, día de México), `por_hora_hoy[24]{hora, neta, tickets}` (hora de México, el frontend recorta la ventana) y `utilidad_bruta_ayer` (`null` para el gerente).» y cambiar «Sin `completo` esas cuatro van en `null` y no se consultan.» por «Sin `completo` esas siete van en `null` y no se consultan.»

- [ ] **Step 7: Commit**

```bash
git add app/schemas/reports.py app/routers/reports_inicio.py tests/test_reports_inicio.py docs/API_REFERENCE.md
git commit -m "feat(inicio): tendencia de 7 días, ventas por hora de hoy y utilidad de ayer en /reports/inicio

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf"
```

---

### Task 2: `/reports/dashboard` gana utilidad bruta y el importe del top

**Files:**
- Modify: `app/services/metricas_ventas.py` (añadir `ve_costos` después de `resolver_ambito`, línea 120)
- Modify: `app/routers/reports.py:220-225` (`get_dashboard_stats`: utilidad), `:251-252` (top a 10), `:318-335` (`kpis`), `:341-343` (`top_products`)
- Modify: `app/routers/reports_inicio.py:54-55` (`_ve_costos` → alias de `mv.ve_costos`)
- Modify: `tests/test_reports_dashboard.py` (añadir casos al final)
- Modify: `docs/API_REFERENCE.md:143` (fila `/daily-summary · /dashboard · /sales-by-hour`)
- Modify: `frontend/src/pages/home/GastroHomeDay.tsx:79` (`slice(0, 6)` → `slice(0, 5)`: con el top a 10 seguiría mostrando 5 productos, como hoy; spec §5 "sin cambiar de pantalla")

**Interfaces:**
- Consumes: `mv.utilidad_bruta(db, ambito, periodo) -> (utilidad: float, venta_sin_costo: float)`, `mv.top_productos(..., limite) -> list[ProductoTop(nombre, cantidad, total)]`, `mv._rol`, `PlatformRole`.
- Produces: `mv.ve_costos(user) -> bool`; en `GET /api/reports/dashboard`: `kpis.gross_profit`, `kpis.prev_gross_profit`, `kpis.sales_without_cost` (`null` los tres para roles sin costos: GERENTE y los demás no HQ), `top_products[]` con hasta **10** entradas y la clave nueva `total` (importe). Reportes (Tarea 8) lee `kpis.gross_profit`/`prev_gross_profit`/`sales_without_cost`/`gross_sales` y `top_products[].total`.

**Decisión:** la spec pide en Reportes «Utilidad bruta (solo si la org tiene costos)» y «Lo más vendido: producto, piezas, importe». `/reports/dashboard` no traía ni la utilidad ni el importe; se añaden aquí (una respuesta, no una segunda lluvia de peticiones). «Tiene costos» lo decide el frontend: `gross_profit != null` y `gross_sales − sales_without_cost > 0`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Añadir al final de `tests/test_reports_dashboard.py`:

```python
# ── Fase 2 (spec 2026-10-23 §3.2): utilidad bruta e importe del top en /dashboard ──

def test_dashboard_utilidad_bruta_para_admin_y_null_para_gerente(client, db, org, branch_a, cajero_a, gerente_a, auth_admin_a, auth_gerente_a, products_setup):
    hoy = mv.hoy_mx()
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "100", dia=hoy)                       # costo 10 → 90
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "50", dia=hoy - timedelta(days=1))    # ayer: 40
    d = client.get(f"/api/reports/dashboard?start_date={hoy}&end_date={hoy}&branch_id=0", headers=auth_admin_a).json()
    k = d["kpis"]
    assert (k["gross_profit"], k["prev_gross_profit"], k["sales_without_cost"]) == (90.0, 40.0, 0.0)
    g = client.get(f"/api/reports/dashboard?start_date={hoy}&end_date={hoy}", headers=auth_gerente_a).json()["kpis"]
    assert (g["gross_profit"], g["prev_gross_profit"], g["sales_without_cost"]) == (None, None, None)


def test_dashboard_top_products_trae_importe_y_hasta_diez(client, db, org, branch_a, cajero_a, auth_admin_a, products_setup):
    hoy = mv.hoy_mx()
    primera = _venta(db, org, branch_a, cajero_a, _v(products_setup), "100", dia=hoy)
    d = client.get(f"/api/reports/dashboard?start_date={hoy}&end_date={hoy}&branch_id=0", headers=auth_admin_a).json()
    assert d["top_products"] == [{"name": f"Producto {primera.folio}", "qty": 1.0, "total": 100.0, "trend": [1.0]}]
    for i in range(11):   # 12 descripciones distintas ("Producto <folio>") → se devuelven 10
        _venta(db, org, branch_a, cajero_a, _v(products_setup), str(10 + i), dia=hoy)
    top = client.get(f"/api/reports/dashboard?start_date={hoy}&end_date={hoy}&branch_id=0", headers=auth_admin_a).json()["top_products"]
    assert len(top) == 10
    assert all(p["total"] > 0 for p in top)
```

- [ ] **Step 2: Correr y ver que falla**

Run: `python3 -m pytest -q -p no:warnings tests/test_reports_dashboard.py`
Expected: 2 fallos (`KeyError: 'gross_profit'`; el top trae 5 entradas y sin `total`).

- [ ] **Step 3: `mv.ve_costos`**

En `app/services/metricas_ventas.py`, después de `resolver_ambito` (línea 120):

```python
def ve_costos(user: User) -> bool:
    """Quién ve costos y utilidad: dueño, administrador y superadmin. El gerente no
    (misma regla que la valuación y el Inicio)."""
    if getattr(user, "platform_role", None) == PlatformRole.SUPERADMIN:
        return True
    return _rol(user) in ("ADMINISTRADOR", "DUEÑO")
```

En `app/routers/reports_inicio.py` sustituir la función `_ve_costos` (líneas 54-55) por el alias:

```python
_ve_costos = mv.ve_costos
```

(`PlatformRole` y `Role` siguen importados: los usa `_sucursal_del_inicio`.)

- [ ] **Step 4: Dashboard**

En `app/routers/reports.py`, dentro de `get_dashboard_stats`:

Después del bloque `pendientes = {...}` (termina en la línea 238) añadir:

```python
    # 1b. Utilidad bruta del periodo y del anterior: solo renglones con costo, menos lo
    # devuelto por el costo de su variante (metricas_ventas.utilidad_bruta). Quien no ve
    # costos (gerente) recibe None en los tres.
    utilidad = utilidad_prev = sin_costo = None
    if mv.ve_costos(current_user):
        utilidad, sin_costo = mv.utilidad_bruta(db, ambito, periodo)
        utilidad_prev, _ = mv.utilidad_bruta(db, ambito, periodo.anterior())
```

Cambiar las líneas 251-252 por:

```python
    # 5. Top productos del periodo, por piezas, con su importe (Reportes pinta hasta 10)
    top = mv.top_productos(db, ambito, periodo, limite=10)
```

En el diccionario `kpis`, después de `"prev_returns": anterior.devuelto,` (línea 332) añadir:

```python
            "gross_profit": utilidad,
            "prev_gross_profit": utilidad_prev,
            "sales_without_cost": sin_costo,
```

Y en `"top_products"` (líneas 341-343) cambiar la comprensión por:

```python
        "top_products": [
            {"name": p.nombre, "qty": p.cantidad, "total": p.total, "trend": top_product_trends.get(p.nombre, [])} for p in top
        ],
```

- [ ] **Step 5: Correr**

Run: `python3 -m pytest -q -p no:warnings tests/test_reports_dashboard.py tests/test_reports_inicio.py tests/test_reports_umbral.py tests/test_variant_traceability.py tests/test_regresion_reportes.py`
Expected: todo en verde (los tres últimos leen `/reports/dashboard` y no miran la longitud del top).

- [ ] **Step 6: Documentar**

En `docs/API_REFERENCE.md`, fila `/daily-summary · /dashboard · /sales-by-hour` (línea 143), añadir al final del texto: «Fase 2 (2026-10-24): `kpis.gross_profit`/`prev_gross_profit`/`sales_without_cost` (utilidad bruta solo sobre renglones con costo y neta de devoluciones por el costo de la variante; `null` para roles sin costos, p. ej. GERENTE) y `top_products[]` trae hasta 10 con `total` (importe).»

- [ ] **Step 7: Commit**

```bash
git add app/services/metricas_ventas.py app/routers/reports.py app/routers/reports_inicio.py tests/test_reports_dashboard.py docs/API_REFERENCE.md
git commit -m "feat(reportes): utilidad bruta e importe del top en /reports/dashboard

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf"
```

---

### Task 3: Kit de gráficas — `components/graficas/` y `useTemaGrafica()`

**Files:**
- Create: `frontend/src/components/graficas/registro.ts`
- Create: `frontend/src/components/graficas/tema.ts`
- Create: `frontend/src/components/graficas/formato.ts`
- Create: `frontend/src/components/graficas/GraficaLinea.tsx`
- Create: `frontend/src/components/graficas/GraficaBarras.tsx`
- Create: `frontend/src/components/graficas/GraficaDona.tsx`
- Create: `frontend/src/components/graficas/index.ts`
- Test: `frontend/src/components/graficas/__tests__/tema.test.tsx`, `__tests__/formato.test.ts`, `__tests__/graficas.test.tsx`

**Interfaces:**
- Consumes: `useTemaActual()` de `frontend/src/utils/cssToken.ts` (señal que cambia con la clase o el `data-preset` de `<html>`, vía MutationObserver), `formatCurrency` de `utils/currency.ts`, `Line`/`Bar`/`Doughnut` de `react-chartjs-2`.
- Produces (todo exportado desde `components/graficas/index.ts`):
  - `interface TemaGrafica { texto; muted; faint; borde; cardSolid; acento; success; warning; danger }` (strings de color).
  - `leerTemaGrafica(): TemaGrafica`, `useTemaGrafica(): TemaGrafica`, `colorMetodo(metodo: string, tema: TemaGrafica): string`.
  - `dineroCorto(valor: number): string` (`$950`, `$1.2k`, `$3.4M`, `-$1.2k`), `recortarHoras(horas: {hora: number; neta: number}[]): {desde: number; hasta: number}`, `etiquetaHora(h: number): string` (`"9:00"`).
  - `GraficaLinea({ etiquetas: string[]; series: SerieLinea[]; alto?: number })` con `SerieLinea = { nombre: string; valores: number[]; comparativo?: boolean }`.
  - `GraficaBarras({ etiquetas: string[]; valores: number[]; resaltar?: number | null; horizontal?: boolean; alto?: number; nombre?: string })`.
  - `GraficaDona({ partes: ParteDona[]; centro?: ReactNode; alto?: number })` con `ParteDona = { nombre: string; valor: number; color: string }`.

- [ ] **Step 1: Pruebas que fallan — tema y formato**

Crear `frontend/src/components/graficas/__tests__/tema.test.tsx`:

```tsx
// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { cleanup, renderHook, waitFor } from '@testing-library/react'
import { colorMetodo, leerTemaGrafica, useTemaGrafica } from '../tema'

const raiz = document.documentElement
afterEach(() => {
  cleanup()
  for (const v of ['--dax-accent', '--dax-text-muted', '--dax-success']) raiz.style.removeProperty(v)
  raiz.className = ''
})

describe('useTemaGrafica', () => {
  it('lee los tokens --dax-* de <html>', () => {
    raiz.style.setProperty('--dax-accent', '#123456')
    raiz.style.setProperty('--dax-text-muted', '#654321')
    const t = leerTemaGrafica()
    expect(t.acento).toBe('#123456')
    expect(t.muted).toBe('#654321')
  })

  it('sin la variable usa el respaldo del tema oscuro', () => {
    expect(leerTemaGrafica().danger).toBe('#F87171')
    expect(leerTemaGrafica().borde).toBe('rgba(237, 237, 248, 0.08)')
  })

  it('se vuelve a leer al cambiar la clase de <html>', async () => {
    raiz.style.setProperty('--dax-accent', '#111111')
    const { result } = renderHook(() => useTemaGrafica())
    expect(result.current.acento).toBe('#111111')
    raiz.style.setProperty('--dax-accent', '#222222')
    raiz.classList.add('dark')
    await waitFor(() => expect(result.current.acento).toBe('#222222'))
  })

  it('métodos: efectivo = success, tarjeta = acento, transferencia = warning, otros = tenue', () => {
    raiz.style.setProperty('--dax-success', '#00aa00')
    const t = leerTemaGrafica()
    expect(colorMetodo('CASH', t)).toBe('#00aa00')
    expect(colorMetodo('card', t)).toBe(t.acento)
    expect(colorMetodo('TRANSFER', t)).toBe(t.warning)
    expect(colorMetodo('MIXED', t)).toBe(t.faint)
  })
})
```

Crear `frontend/src/components/graficas/__tests__/formato.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { dineroCorto, etiquetaHora, recortarHoras } from '../formato'

describe('dineroCorto', () => {
  it('abrevia miles y millones con un decimal', () => {
    expect(dineroCorto(950)).toBe('$950')
    expect(dineroCorto(1234)).toBe('$1.2k')
    expect(dineroCorto(12500)).toBe('$12.5k')
    expect(dineroCorto(3_400_000)).toBe('$3.4M')
    expect(dineroCorto(0)).toBe('$0')
  })
  it('negativos con signo delante (un día con más devoluciones que ventas)', () => {
    expect(dineroCorto(-1234)).toBe('-$1.2k')
    expect(dineroCorto(-40)).toBe('-$40')
  })
})

describe('recortarHoras (spec §2.1: min(9, primera con venta) .. max(21, última con venta))', () => {
  const horas = (con: Record<number, number>) => Array.from({ length: 24 }, (_, h) => ({ hora: h, neta: con[h] ?? 0 }))
  it('sin ventas: de 9 a 21', () => {
    expect(recortarHoras(horas({}))).toEqual({ desde: 9, hasta: 21 })
  })
  it('una venta dentro de la ventana no la mueve', () => {
    expect(recortarHoras(horas({ 12: 100 }))).toEqual({ desde: 9, hasta: 21 })
  })
  it('ventas temprano o tarde la abren', () => {
    expect(recortarHoras(horas({ 7: 100 }))).toEqual({ desde: 7, hasta: 21 })
    expect(recortarHoras(horas({ 23: 100 }))).toEqual({ desde: 9, hasta: 23 })
  })
  it('una devolución (neta negativa) también cuenta como movimiento', () => {
    expect(recortarHoras(horas({ 6: -40 }))).toEqual({ desde: 6, hasta: 21 })
  })
})

describe('etiquetaHora', () => {
  it('pinta "9:00"', () => {
    expect(etiquetaHora(9)).toBe('9:00')
    expect(etiquetaHora(0)).toBe('0:00')
  })
})
```

Run: `cd frontend && npx vitest run src/components/graficas --reporter=dot`
Expected: fallan (no existen `../tema` ni `../formato`).

- [ ] **Step 2: `registro.ts`, `tema.ts` y `formato.ts`**

Crear `frontend/src/components/graficas/registro.ts`:

```ts
// frontend/src/components/graficas/registro.ts
import {
  ArcElement, BarElement, CategoryScale, Chart as ChartJS, LineElement, LinearScale, PointElement, Tooltip,
} from 'chart.js'

/**
 * Registración única de chart.js para el kit. Sin `Legend` (la leyenda la
 * pinta cada pantalla con tokens) y sin `Filler` (spec §3.3: sin relleno ni
 * degradados). Importar este módulo basta; `register` es idempotente.
 */
ChartJS.register(CategoryScale, LinearScale, BarElement, PointElement, LineElement, ArcElement, Tooltip)
```

Crear `frontend/src/components/graficas/tema.ts`:

```ts
// frontend/src/components/graficas/tema.ts
import { useMemo } from 'react'
import { useTemaActual } from '../../utils/cssToken'

/**
 * Colores del tema para chart.js (spec 2026-10-23 §3.3). El canvas no entiende
 * `var(--dax-accent)`: aquí se leen los tokens de `<html>` con
 * `getComputedStyle` y se vuelven a leer cuando cambia la clase (`.dark`) o
 * el `data-preset` de `<html>` (MutationObserver en `useTemaActual`), para que
 * la gráfica se repinte al cambiar de tema sin recargar.
 */
export interface TemaGrafica {
  texto: string
  muted: string
  faint: string
  /** `--dax-border-dim`: rejilla y bordes de tooltip. */
  borde: string
  /** `--dax-card-solid`: fondo del tooltip y separación entre gajos de la dona. */
  cardSolid: string
  acento: string
  success: string
  warning: string
  danger: string
}

/** Respaldos = tema oscuro de index.css; solo se usan sin DOM o sin la variable. */
const RESPALDO: TemaGrafica = {
  texto: '#ededf8', muted: '#b9b9d0', faint: '#8c8cab', borde: 'rgba(237, 237, 248, 0.08)', cardSolid: '#14142e',
  acento: '#6366f1', success: '#34D399', warning: '#FBBF24', danger: '#F87171',
}

const VARIABLES: Record<keyof TemaGrafica, string> = {
  texto: '--dax-text', muted: '--dax-text-muted', faint: '--dax-text-faint', borde: '--dax-border-dim',
  cardSolid: '--dax-card-solid', acento: '--dax-accent', success: '--dax-success', warning: '--dax-warning',
  danger: '--dax-danger',
}

/** El token en <html>: el valor calculado y, si el entorno no lo calcula (jsdom), el declarado en línea. */
function leerVariable(nombre: string): string {
  const raiz = document.documentElement
  return (getComputedStyle(raiz).getPropertyValue(nombre) || raiz.style.getPropertyValue(nombre)).trim()
}

/** `color-mix(...)` (acento del tema oscuro) no lo entiende el canvas: una sonda hace que el navegador lo calcule a `rgb(...)`. */
function resolver(valor: string): string {
  if (/^(#[0-9a-f]{3,8}|rgba?\(.*\))$/i.test(valor) || !document.body) return valor
  const sonda = document.createElement('span')
  sonda.style.color = valor
  document.body.appendChild(sonda)
  const c = getComputedStyle(sonda).color
  sonda.remove()
  return c || valor
}

export function leerTemaGrafica(): TemaGrafica {
  if (typeof document === 'undefined') return RESPALDO
  const salida: TemaGrafica = { ...RESPALDO }
  for (const clave of Object.keys(VARIABLES) as (keyof TemaGrafica)[]) {
    const v = leerVariable(VARIABLES[clave])
    if (v) salida[clave] = resolver(v)
  }
  return salida
}

/** Colores del tema actual; cambia de identidad cuando cambia la clase de <html>. */
export function useTemaGrafica(): TemaGrafica {
  const claveTema = useTemaActual()
  // La señal es la dependencia a propósito: es lo que avisa que hay que releer.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useMemo(() => leerTemaGrafica(), [claveTema])
}

/** Efectivo = success, tarjeta = acento, transferencia = warning, lo demás tenue (spec §3.3). */
export function colorMetodo(metodo: string, tema: TemaGrafica): string {
  switch (metodo.toUpperCase()) {
    case 'CASH': return tema.success
    case 'CARD': return tema.acento
    case 'TRANSFER': return tema.warning
    default: return tema.faint
  }
}
```

Crear `frontend/src/components/graficas/formato.ts`:

```ts
// frontend/src/components/graficas/formato.ts

/** Moneda abreviada para ejes: "$950", "$1.2k", "$3.4M"; negativos con el signo delante ("-$1.2k"). */
export function dineroCorto(valor: number): string {
  const abs = Math.abs(valor)
  const signo = valor < 0 ? '-' : ''
  if (abs >= 1_000_000) return `${signo}$${(abs / 1_000_000).toFixed(1)}M`
  if (abs >= 1_000) return `${signo}$${(abs / 1_000).toFixed(1)}k`
  return `${signo}$${Math.round(abs)}`
}

/**
 * Ventana de horas a pintar (spec §2.1): de `min(9, primera hora con
 * movimiento)` a `max(21, última hora con movimiento)`. El backend manda las
 * 24; una venta a las 7 o una devolución a las 23 abren la ventana.
 */
export function recortarHoras(horas: { hora: number; neta: number }[]): { desde: number; hasta: number } {
  const conMovimiento = horas.filter((h) => h.neta !== 0).map((h) => h.hora)
  const desde = conMovimiento.length ? Math.min(9, ...conMovimiento) : 9
  const hasta = conMovimiento.length ? Math.max(21, ...conMovimiento) : 21
  return { desde, hasta }
}

export const etiquetaHora = (h: number): string => `${h}:00`
```

Run: `cd frontend && npx vitest run src/components/graficas --reporter=dot`
Expected: verde.

- [ ] **Step 3: Pruebas que fallan — los tres envoltorios**

Crear `frontend/src/components/graficas/__tests__/graficas.test.tsx`:

```tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'

// jsdom no tiene canvas: los componentes de react-chartjs-2 se sustituyen por
// stubs que exponen lo que el kit les construye. Se prueba la configuración,
// no el dibujo.
type Dataset = Record<string, unknown>
type Props = { data: { labels?: unknown[]; datasets: Dataset[] }; options: Record<string, any> }
const volcar = (id: string) => (p: Props) => (
  <div data-testid={id} data-datasets={JSON.stringify(p.data.datasets)} data-labels={JSON.stringify(p.data.labels)}
    data-animacion={String(p.options.animation?.duration)} data-eje={String(p.options.indexAxis)} data-cutout={String(p.options.cutout)} />
)
vi.mock('react-chartjs-2', () => ({ Line: volcar('line'), Bar: volcar('bar'), Doughnut: volcar('dona') }))

import { GraficaBarras, GraficaDona, GraficaLinea } from '..'

const raiz = document.documentElement
const datasets = (id: string) => JSON.parse(screen.getByTestId(id).getAttribute('data-datasets') ?? '[]') as Dataset[]

afterEach(() => { cleanup(); raiz.style.removeProperty('--dax-accent'); raiz.style.removeProperty('--dax-text-faint') })

describe('GraficaLinea', () => {
  it('serie principal en acento y comparativo tenue y discontinuo; sin relleno; 300 ms', () => {
    raiz.style.setProperty('--dax-accent', '#111111')
    raiz.style.setProperty('--dax-text-faint', '#999999')
    render(<GraficaLinea etiquetas={['l', 'm']} series={[
      { nombre: 'Estos 7 días', valores: [1, 2] },
      { nombre: 'Semana anterior', valores: [3, 4], comparativo: true },
    ]} />)
    const [principal, comparativo] = datasets('line')
    expect(principal).toMatchObject({ label: 'Estos 7 días', borderColor: '#111111', fill: false, pointRadius: 0 })
    expect(principal.borderDash).toBeUndefined()
    expect(comparativo).toMatchObject({ label: 'Semana anterior', borderColor: '#999999', borderDash: [4, 4], fill: false })
    expect(screen.getByTestId('line').getAttribute('data-animacion')).toBe('300')
  })
})

describe('GraficaBarras', () => {
  it('sin resaltar todas las barras van en acento', () => {
    raiz.style.setProperty('--dax-accent', '#111111')
    render(<GraficaBarras etiquetas={['a', 'b']} valores={[1, 2]} />)
    expect(datasets('bar')[0].backgroundColor).toEqual(['#111111', '#111111'])
    expect(screen.getByTestId('bar').getAttribute('data-eje')).toBe('x')
  })
  it('con resaltar, esa barra va en acento y el resto tenue', () => {
    raiz.style.setProperty('--dax-accent', '#111111')
    raiz.style.setProperty('--dax-text-faint', '#999999')
    render(<GraficaBarras etiquetas={['a', 'b', 'c']} valores={[1, 2, 3]} resaltar={1} />)
    expect(datasets('bar')[0].backgroundColor).toEqual(['#999999', '#111111', '#999999'])
  })
  it('horizontal cambia el eje índice a y', () => {
    render(<GraficaBarras etiquetas={['Roma', 'Condesa']} valores={[6000, 3000]} horizontal />)
    expect(screen.getByTestId('bar').getAttribute('data-eje')).toBe('y')
    expect(screen.getByTestId('bar').getAttribute('data-animacion')).toBe('300')
  })
})

describe('GraficaDona', () => {
  it('la dona recorta negativos a cero, respeta los colores y pinta el centro', () => {
    render(<GraficaDona partes={[
      { nombre: 'Efectivo', valor: 500, color: '#0a0' },
      { nombre: 'Tarjeta', valor: -40, color: '#00a' },
    ]} centro={<span>Total</span>} />)
    const [d] = datasets('dona')
    expect(d.data).toEqual([500, 0])
    expect(d.backgroundColor).toEqual(['#0a0', '#00a'])
    expect(screen.getByTestId('dona').getAttribute('data-cutout')).toBe('70%')
    expect(screen.getByText('Total')).toBeTruthy()
  })
})
```

Run: `cd frontend && npx vitest run src/components/graficas --reporter=dot`
Expected: `graficas.test.tsx` falla (no existe `..`/`index.ts`).

- [ ] **Step 4: Los tres envoltorios y el índice**

Crear `frontend/src/components/graficas/GraficaLinea.tsx`:

```tsx
// frontend/src/components/graficas/GraficaLinea.tsx
import { useMemo } from 'react'
import type { ChartData, ChartOptions } from 'chart.js'
import { Line } from 'react-chartjs-2'
import './registro'
import { formatCurrency } from '../../utils/currency'
import { dineroCorto } from './formato'
import { useTemaGrafica } from './tema'

export interface SerieLinea {
  nombre: string
  valores: number[]
  /** Serie de referencia (periodo anterior): tenue y discontinua. */
  comparativo?: boolean
}

/** Línea plana (spec §3.3): acento para la serie principal, tenue para el comparativo, sin relleno. */
export function GraficaLinea({ etiquetas, series, alto = 224 }: { etiquetas: string[]; series: SerieLinea[]; alto?: number }) {
  const tema = useTemaGrafica()
  const data = useMemo<ChartData<'line'>>(() => ({
    labels: etiquetas,
    datasets: series.map((s) => ({
      label: s.nombre,
      data: s.valores,
      borderColor: s.comparativo ? tema.faint : tema.acento,
      backgroundColor: s.comparativo ? tema.faint : tema.acento,
      borderWidth: s.comparativo ? 1.5 : 2,
      borderDash: s.comparativo ? [4, 4] : undefined,
      pointRadius: 0,
      pointHoverRadius: 4,
      tension: 0.3,
      fill: false,
    })),
  }), [etiquetas, series, tema])

  const opciones = useMemo<ChartOptions<'line'>>(() => ({
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 300 },
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: tema.cardSolid, borderColor: tema.borde, borderWidth: 1,
        titleColor: tema.texto, bodyColor: tema.texto,
        callbacks: { label: (ctx) => `${ctx.dataset.label ?? ''}: ${formatCurrency(Number(ctx.parsed.y ?? 0))}` },
      },
    },
    scales: {
      x: { grid: { display: false }, ticks: { color: tema.muted, font: { size: 10 }, maxRotation: 0, autoSkipPadding: 8 } },
      y: {
        beginAtZero: true, grid: { color: tema.borde }, border: { display: false },
        ticks: { color: tema.muted, font: { size: 10 }, callback: (v) => dineroCorto(Number(v)) },
      },
    },
  }), [tema])

  return <div style={{ height: alto }}><Line data={data} options={opciones} /></div>
}
```

Crear `frontend/src/components/graficas/GraficaBarras.tsx`:

```tsx
// frontend/src/components/graficas/GraficaBarras.tsx
import { useMemo } from 'react'
import type { ChartData, ChartOptions } from 'chart.js'
import { Bar } from 'react-chartjs-2'
import './registro'
import { formatCurrency } from '../../utils/currency'
import { dineroCorto } from './formato'
import { useTemaGrafica } from './tema'

export interface GraficaBarrasProps {
  etiquetas: string[]
  valores: number[]
  /** Índice que se pinta con el acento (la hora actual); el resto va tenue. Sin él, todas en acento. */
  resaltar?: number | null
  /** Barras horizontales (sucursales). */
  horizontal?: boolean
  alto?: number
  /** Nombre de la serie en el tooltip. */
  nombre?: string
}

/** Barras planas (spec §3.3): un solo color por barra, sin degradados; ejes con `dineroCorto`. */
export function GraficaBarras({ etiquetas, valores, resaltar = null, horizontal = false, alto = 224, nombre = 'Venta' }: GraficaBarrasProps) {
  const tema = useTemaGrafica()
  const data = useMemo<ChartData<'bar'>>(() => ({
    labels: etiquetas,
    datasets: [{
      label: nombre,
      data: valores,
      backgroundColor: valores.map((_, i) => (resaltar === null || i === resaltar ? tema.acento : tema.faint)),
      borderWidth: 0,
      borderRadius: 3,
      maxBarThickness: 28,
    }],
  }), [etiquetas, valores, resaltar, nombre, tema])

  const opciones = useMemo<ChartOptions<'bar'>>(() => ({
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 300 },
    indexAxis: horizontal ? 'y' : 'x',
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: tema.cardSolid, borderColor: tema.borde, borderWidth: 1,
        titleColor: tema.texto, bodyColor: tema.texto,
        callbacks: { label: (ctx) => `${nombre}: ${formatCurrency(Number(horizontal ? ctx.parsed.x : ctx.parsed.y))}` },
      },
    },
    scales: horizontal
      ? {
          x: { beginAtZero: true, grid: { color: tema.borde }, border: { display: false }, ticks: { color: tema.muted, font: { size: 10 }, callback: (v) => dineroCorto(Number(v)) } },
          y: { grid: { display: false }, ticks: { color: tema.muted, font: { size: 10 } } },
        }
      : {
          x: { grid: { display: false }, ticks: { color: tema.muted, font: { size: 10 }, maxRotation: 0, autoSkipPadding: 8 } },
          y: { beginAtZero: true, grid: { color: tema.borde }, border: { display: false }, ticks: { color: tema.muted, font: { size: 10 }, callback: (v) => dineroCorto(Number(v)) } },
        },
  }), [tema, horizontal, nombre])

  return <div style={{ height: alto }}><Bar data={data} options={opciones} /></div>
}
```

Crear `frontend/src/components/graficas/GraficaDona.tsx`:

```tsx
// frontend/src/components/graficas/GraficaDona.tsx
import { useMemo, type ReactNode } from 'react'
import type { ChartData, ChartOptions } from 'chart.js'
import { Doughnut } from 'react-chartjs-2'
import './registro'
import { formatCurrency } from '../../utils/currency'
import { useTemaGrafica } from './tema'

export interface ParteDona {
  nombre: string
  valor: number
  color: string
}

/**
 * Dona plana con el total al centro (spec §3.1/§3.2). Un método con neta
 * negativa (más devuelto que cobrado) se pinta como 0: un gajo negativo no
 * existe; la lista bajo la dona sí enseña el número real.
 */
export function GraficaDona({ partes, centro, alto = 224 }: { partes: ParteDona[]; centro?: ReactNode; alto?: number }) {
  const tema = useTemaGrafica()
  const valores = useMemo(() => partes.map((p) => Math.max(0, p.valor)), [partes])
  const total = valores.reduce((s, v) => s + v, 0)

  const data = useMemo<ChartData<'doughnut'>>(() => ({
    labels: partes.map((p) => p.nombre),
    datasets: [{
      data: valores,
      backgroundColor: partes.map((p) => p.color),
      borderColor: tema.cardSolid,
      borderWidth: 2,
      hoverOffset: 6,
    }],
  }), [partes, valores, tema])

  const opciones = useMemo<ChartOptions<'doughnut'>>(() => ({
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 300 },
    cutout: '70%',
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: tema.cardSolid, borderColor: tema.borde, borderWidth: 1,
        titleColor: tema.texto, bodyColor: tema.texto,
        callbacks: {
          label: (ctx) => {
            const v = Number(ctx.parsed)
            const pct = total > 0 ? Math.round((v / total) * 100) : 0
            return `${ctx.label}: ${formatCurrency(v)} (${pct} %)`
          },
        },
      },
    },
  }), [tema, total])

  return (
    <div className="relative" style={{ height: alto }}>
      <Doughnut data={data} options={opciones} />
      {centro && (
        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">{centro}</div>
      )}
    </div>
  )
}
```

Crear `frontend/src/components/graficas/index.ts`:

```ts
// frontend/src/components/graficas/index.ts
// Kit de gráficas (spec 2026-10-23 §3.3): envoltorios planos de react-chartjs-2
// pintados con los tokens del tema. Quien lo importa cae en el chunk `charts`:
// el Inicio solo lo alcanza con lazy() y en perfil completo.
export { GraficaLinea, type SerieLinea } from './GraficaLinea'
export { GraficaBarras, type GraficaBarrasProps } from './GraficaBarras'
export { GraficaDona, type ParteDona } from './GraficaDona'
export { useTemaGrafica, leerTemaGrafica, colorMetodo, type TemaGrafica } from './tema'
export { dineroCorto, recortarHoras, etiquetaHora } from './formato'
```

- [ ] **Step 5: Correr y comprobar tipos**

Run: `cd frontend && npx vitest run src/components/graficas --reporter=dot && npx tsc --noEmit -p tsconfig.json`
Expected: verde y tsc sin errores. Si tsc se queja de `indexAxis`, dejarlo como `indexAxis: horizontal ? ('y' as const) : ('x' as const)`.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/graficas
git commit -m "feat(graficas): kit GraficaLinea/Barras/Dona sobre react-chartjs-2 con tema por tokens

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf"
```

---

### Task 4: `KpiCard` y la regla de variación

**Files:**
- Create: `frontend/src/utils/variacion.ts`
- Create: `frontend/src/components/ui/KpiCard.tsx`
- Test: `frontend/src/utils/__tests__/variacion.test.ts`, `frontend/src/components/ui/__tests__/KpiCard.test.tsx`

**Interfaces:**
- Consumes: clases `dax-kpi-label`, `dax-kpi-value`, `dax-card` (`index.css:442, 619-632`, ya existen: **no se añade CSS**); tokens Tailwind `text-dax-success/warning/danger/muted`.
- Produces:
  - `interface Variacion { pct: number | null; texto: string; invertida?: boolean }`.
  - `porcentajeVariacion(actual: number, anterior: number): number | null` (entero; `null` = sin referencia).
  - `variacion(actual, anterior, texto, invertida = false): Variacion`.
  - `KpiCard({ etiqueta: string; valor: string; detalle?: ReactNode; variacion?: Variacion; tono?: 'success'|'warning'|'danger'; 'data-testid'?: string })`. Dentro, la variación lleva `data-testid="variacion"`.

**Decisión (la spec dice «▲ 12 %» en success, «▼» en danger, «igual» en muted):** porcentaje **entero** (`Math.round`); `anterior > 0` → `(actual − anterior) / anterior`; `anterior ≤ 0` con `actual ≠ 0` → `null` y se pinta «Sin referencia» en muted (no se divide entre cero ni se inventa «+100 %»); ambos 0 → 0 («Igual»). `invertida` voltea los colores para cifras donde subir es malo (Devoluciones).

- [ ] **Step 1: Pruebas que fallan**

Crear `frontend/src/utils/__tests__/variacion.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { porcentajeVariacion, variacion } from '../variacion'

describe('porcentajeVariacion', () => {
  it('porcentaje entero contra el anterior', () => {
    expect(porcentajeVariacion(112, 100)).toBe(12)
    expect(porcentajeVariacion(88, 100)).toBe(-12)
    expect(porcentajeVariacion(0, 100)).toBe(-100)
    expect(porcentajeVariacion(1234.5, 800)).toBe(54)
  })
  it('redondea: 100.4 contra 100 es igual', () => {
    expect(porcentajeVariacion(100.4, 100)).toBe(0)
    expect(porcentajeVariacion(100, 100)).toBe(0)
  })
  it('sin referencia cuando el anterior es cero o negativo', () => {
    expect(porcentajeVariacion(50, 0)).toBeNull()
    expect(porcentajeVariacion(50, -10)).toBeNull()
  })
  it('cero contra cero es igual, no "sin referencia"', () => {
    expect(porcentajeVariacion(0, 0)).toBe(0)
  })
})

describe('variacion', () => {
  it('arma el objeto con texto e inversión', () => {
    expect(variacion(120, 100, 'vs ayer')).toEqual({ pct: 20, texto: 'vs ayer', invertida: false })
    expect(variacion(400, 100, 'vs periodo anterior', true)).toEqual({ pct: 300, texto: 'vs periodo anterior', invertida: true })
  })
})
```

Crear `frontend/src/components/ui/__tests__/KpiCard.test.tsx`:

```tsx
// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { KpiCard } from '../KpiCard'

afterEach(cleanup)

describe('KpiCard', () => {
  it('pinta etiqueta, valor y detalle con las clases dax-kpi-*', () => {
    render(<KpiCard etiqueta="Hoy" valor="$1,234.50" detalle="12 ventas" data-testid="k" />)
    const k = screen.getByTestId('k')
    expect(k.querySelector('.dax-kpi-label')?.textContent).toBe('Hoy')
    expect(k.querySelector('.dax-kpi-value')?.textContent).toBe('$1,234.50')
    expect(k.textContent).toContain('12 ventas')
    expect(screen.queryByTestId('variacion')).toBeNull()
  })
  it('sube: flecha arriba en success', () => {
    render(<KpiCard etiqueta="Hoy" valor="$1" variacion={{ pct: 12, texto: 'vs ayer' }} />)
    const v = screen.getByTestId('variacion')
    expect(v.textContent).toContain('▲ 12 %')
    expect(v.textContent).toContain('vs ayer')
    expect(v.className).toContain('text-dax-success')
  })
  it('baja: flecha abajo en danger', () => {
    render(<KpiCard etiqueta="Hoy" valor="$1" variacion={{ pct: -8, texto: 'vs ayer' }} />)
    const v = screen.getByTestId('variacion')
    expect(v.textContent).toContain('▼ 8 %')
    expect(v.className).toContain('text-dax-danger')
  })
  it('igual y sin referencia van en muted', () => {
    render(<KpiCard etiqueta="A" valor="$1" variacion={{ pct: 0, texto: 'vs ayer' }} data-testid="a" />)
    render(<KpiCard etiqueta="B" valor="$1" variacion={{ pct: null, texto: 'vs semana anterior' }} data-testid="b" />)
    const [a, b] = screen.getAllByTestId('variacion')
    expect(a.textContent).toBe('Igual · vs ayer')
    expect(a.className).toContain('text-dax-muted')
    expect(b.textContent).toBe('Sin referencia · vs semana anterior')
    expect(b.className).toContain('text-dax-muted')
  })
  it('invertida: subir es malo (devoluciones) y se pinta en danger', () => {
    render(<KpiCard etiqueta="Devoluciones" valor="$400" variacion={{ pct: 300, texto: 'vs periodo anterior', invertida: true }} />)
    const v = screen.getByTestId('variacion')
    expect(v.textContent).toContain('▲ 300 %')
    expect(v.className).toContain('text-dax-danger')
  })
  it('el tono colorea el valor', () => {
    render(<KpiCard etiqueta="Utilidad" valor="$400" tono="success" data-testid="k" />)
    expect(screen.getByTestId('k').querySelector('.dax-kpi-value')?.className).toContain('text-dax-success')
  })
})
```

Run: `cd frontend && npx vitest run src/utils/__tests__/variacion.test.ts src/components/ui/__tests__/KpiCard.test.tsx --reporter=dot`
Expected: fallan (módulos inexistentes).

- [ ] **Step 2: Implementar**

Crear `frontend/src/utils/variacion.ts`:

```ts
// frontend/src/utils/variacion.ts

/** Variación de una cifra contra su referencia (spec 2026-10-23 §3.1/§3.2). */
export interface Variacion {
  /** Porcentaje entero contra la referencia; null = sin referencia (anterior ≤ 0 con cifra ≠ 0). */
  pct: number | null
  /** "vs ayer", "vs antier", "vs semana anterior", "vs periodo anterior". */
  texto: string
  /** Subir es malo (devoluciones): invierte los colores. */
  invertida?: boolean
}

/**
 * Porcentaje entero de cambio. Con referencia cero o negativa no hay contra
 * qué comparar (no se divide entre cero ni se inventa "+100 %"): null. Cero
 * contra cero es "igual" (0).
 */
export function porcentajeVariacion(actual: number, anterior: number): number | null {
  if (anterior === 0 && actual === 0) return 0
  if (!(anterior > 0)) return null
  return Math.round(((actual - anterior) / anterior) * 100)
}

export function variacion(actual: number, anterior: number, texto: string, invertida = false): Variacion {
  return { pct: porcentajeVariacion(actual, anterior), texto, invertida }
}
```

Crear `frontend/src/components/ui/KpiCard.tsx`:

```tsx
// frontend/src/components/ui/KpiCard.tsx
import type { ReactNode } from 'react'
import type { Variacion } from '../../utils/variacion'

/**
 * KpiCard — una cifra del kit (spec 2026-10-23 §3.3): etiqueta
 * (`dax-kpi-label`), valor (`dax-kpi-value`), variación contra su referencia
 * (▲ en success, ▼ en danger, "Igual"/"Sin referencia" en muted) y un detalle
 * opcional. Sustituye a `components/reports/KPICard` (conteo animado y
 * chispas) y a la `Cifra` local del Inicio. Solo tokens; sin colores fijos.
 */
export type TonoKpi = 'success' | 'warning' | 'danger'
const TONO: Record<TonoKpi, string> = { success: 'text-dax-success', warning: 'text-dax-warning', danger: 'text-dax-danger' }

export interface KpiCardProps {
  etiqueta: string
  /** Ya formateado ("$1,234.50", "12"). */
  valor: string
  detalle?: ReactNode
  variacion?: Variacion
  tono?: TonoKpi
  'data-testid'?: string
}

export function KpiCard({ etiqueta, valor, detalle, variacion, tono, 'data-testid': testId }: KpiCardProps) {
  return (
    <div className="dax-card p-4" data-testid={testId}>
      <p className="dax-kpi-label">{etiqueta}</p>
      <p className={`dax-kpi-value mt-1 ${tono ? TONO[tono] : ''}`}>{valor}</p>
      {variacion && <TextoVariacion v={variacion} />}
      {detalle != null && detalle !== '' && <p className="text-xs text-dax-muted mt-1">{detalle}</p>}
    </div>
  )
}

function TextoVariacion({ v }: { v: Variacion }) {
  if (v.pct === null) return <p className="text-xs text-dax-muted mt-1" data-testid="variacion">Sin referencia · {v.texto}</p>
  if (v.pct === 0) return <p className="text-xs text-dax-muted mt-1" data-testid="variacion">Igual · {v.texto}</p>
  const sube = v.pct > 0
  const bien = v.invertida ? !sube : sube
  return (
    <p className={`text-xs font-bold tabular-nums mt-1 ${bien ? 'text-dax-success' : 'text-dax-danger'}`} data-testid="variacion">
      <span aria-hidden="true">{sube ? '▲' : '▼'}</span> {Math.abs(v.pct)} %{' '}
      <span className="font-normal text-dax-muted">{v.texto}</span>
    </p>
  )
}

export default KpiCard
```

- [ ] **Step 3: Correr**

Run: `cd frontend && npx vitest run src/utils/__tests__/variacion.test.ts src/components/ui/__tests__/KpiCard.test.tsx --reporter=dot && npx tsc --noEmit -p tsconfig.json`
Expected: verde; tsc limpio.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/utils/variacion.ts frontend/src/utils/__tests__/variacion.test.ts frontend/src/components/ui/KpiCard.tsx frontend/src/components/ui/__tests__/KpiCard.test.tsx
git commit -m "feat(ui): KpiCard con variación (▲/▼/igual) y utils/variacion

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf"
```

---

### Task 5: Tipos de la API y el módulo perezoso `InicioGraficas`

**Files:**
- Modify: `frontend/src/api/reports.ts:3-31` (`DashboardData`), `:139-144` (`PeriodoVentas`), `:190-218` (`SucursalInicio`, `Inicio`)
- Create: `frontend/src/pages/hq/InicioGraficas.tsx`
- Modify: `frontend/src/__tests__/rutasPerezosas.test.ts:8-12`
- Test: `frontend/src/pages/hq/__tests__/InicioGraficas.test.tsx`

**Interfaces:**
- Consumes: Tarea 1 (JSON de `/reports/inicio`), Tarea 2 (`/reports/dashboard`), Tarea 3 (`GraficaLinea`, `GraficaBarras`, `GraficaDona`, `colorMetodo`, `recortarHoras`, `etiquetaHora`, `useTemaGrafica` desde `components/graficas`).
- Produces:
  - Tipos en `api/reports.ts`: `DiaTendencia { fecha: string; neta: number; tickets: number }`, `Tendencia { dias: DiaTendencia[]; anterior: DiaTendencia[] }`, `HoraInicio { hora: number; neta: number; tickets: number }`; `PeriodoVentas.devuelto: number`; `SucursalInicio.devuelto_hoy: number`; `Inicio.tendencia: Tendencia | null`, `Inicio.por_hora_hoy: HoraInicio[] | null`, `Inicio.utilidad_bruta_ayer: number | null`; `DashboardData.kpis` gana `gross_sales?`, `returns?`, `returns_count?`, `prev_returns?`, `gross_profit?: number | null`, `prev_gross_profit?: number | null`, `sales_without_cost?: number | null`; `DashboardData.top_products[].total?: number`.
  - `export type SeccionGrafica = 'tendencia' | 'metodos' | 'horas' | 'sucursales'` y `export function InicioGraficas({ seccion, datos, horaActual? })` en `pages/hq/InicioGraficas.tsx` (la Tarea 6 lo carga con `lazy()`; `rutasPerezosas` exige el nombre `InicioGraficas`).
  - `export const METODOS` (etiquetas de método) desde `InicioGraficas.tsx` NO: cada pantalla tiene su propio diccionario local (evita que `Inicio.tsx` importe algo del módulo perezoso).

- [ ] **Step 1: Tipos**

En `frontend/src/api/reports.ts`:

Sustituir `kpis` de `DashboardData` (líneas 4-17) por:

```ts
  kpis: {
    /** Venta NETA del periodo (cobradas − devoluciones aprobadas). */
    sales: number
    gross_sales?: number
    returns?: number
    returns_count?: number
    orders: number
    avg_ticket: number
    pending: number
    draft: number
    total_products: number
    transit_shipments: number
    unique_skus_sold?: number
    // Comparativo del periodo anterior (mismo largo).
    prev_sales?: number
    prev_orders?: number
    prev_avg_ticket?: number
    prev_returns?: number
    /** Utilidad bruta solo sobre renglones con costo; null para roles sin costos (gerente). */
    gross_profit?: number | null
    prev_gross_profit?: number | null
    /** Lo vendido en renglones sin costo (fuera de la utilidad). */
    sales_without_cost?: number | null
  }
```

Sustituir la línea de `top_products` (línea 28) por:

```ts
  // `total` = importe (Fase 2); `trend` (opcional): piezas por día alineadas al rango.
  top_products: { name: string; qty: number; total?: number; trend?: number[] }[]
```

Sustituir `PeriodoVentas` (líneas 139-144) por:

```ts
export interface PeriodoVentas {
  desde: string
  hasta: string
  /** Venta NETA: cobradas menos devoluciones aprobadas del periodo. */
  total: number
  devuelto: number
  tickets: number
}
```

Sustituir `SucursalInicio` (líneas 190-197) por:

```ts
export interface SucursalInicio {
  branch_id: number
  nombre: string
  /** Neta. */
  ventas_hoy: number
  devuelto_hoy: number
  tickets_hoy: number
  corte: CorteInicio
  poca_existencia: number
}

export interface DiaTendencia {
  fecha: string
  neta: number
  tickets: number
}

/** Hoy y los 6 anteriores (`dias`) y los 7 previos (`anterior`), netos, día de México. */
export interface Tendencia {
  dias: DiaTendencia[]
  anterior: DiaTendencia[]
}

export interface HoraInicio {
  hora: number
  neta: number
  tickets: number
}
```

Y en `Inicio`, después de `venta_sin_costo_hoy: number | null` (línea 217):

```ts
  /** Fase 2: solo con `completo: true` (el Inicio básico no pinta gráficas); null en básico. */
  tendencia: Tendencia | null
  /** 24 horas de hoy; el frontend recorta la ventana con `recortarHoras`. */
  por_hora_hoy: HoraInicio[] | null
  /** Para la variación de la utilidad de hoy; null sin `completo` o sin costos. */
  utilidad_bruta_ayer: number | null
```

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json`
Expected: sin errores (nadie construye `Inicio` ni `PeriodoVentas` a mano fuera de pruebas; las pruebas no entran en este tsconfig).

- [ ] **Step 2: Prueba que falla — `InicioGraficas`**

Crear `frontend/src/pages/hq/__tests__/InicioGraficas.test.tsx`:

```tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'

// Stubs del kit: exponen etiquetas, valores y colores; el dibujo lo prueba el kit.
vi.mock('../../../components/graficas', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../components/graficas')>()),
  GraficaLinea: (p: { etiquetas: string[]; series: { nombre: string; valores: number[]; comparativo?: boolean }[] }) => (
    <div data-testid="linea" data-etiquetas={p.etiquetas.join('|')}
      data-series={p.series.map((s) => `${s.nombre}${s.comparativo ? '*' : ''}=${s.valores.join(',')}`).join('|')} />
  ),
  GraficaBarras: (p: { etiquetas: string[]; valores: number[]; resaltar?: number | null; horizontal?: boolean }) => (
    <div data-testid={p.horizontal ? 'barras-h' : 'barras'} data-etiquetas={p.etiquetas.join('|')}
      data-valores={p.valores.join(',')} data-resaltar={String(p.resaltar)} />
  ),
  GraficaDona: (p: { partes: { nombre: string; valor: number; color: string }[]; centro?: React.ReactNode }) => (
    <div data-testid="dona" data-partes={p.partes.map((x) => `${x.nombre}=${x.valor}`).join('|')}>{p.centro}</div>
  ),
}))

import { InicioGraficas } from '../InicioGraficas'
import type { Inicio } from '../../../api/reports'

const dia = (n: number) => `2026-10-${String(n).padStart(2, '0')}`
const corte = { estado: 'sin_turno' as const, cajera: null, abierto_en: null, cerrado_en: null, efectivo_esperado: null, efectivo_contado: null }
const DATOS: Inicio = {
  branch_id: null,
  hoy: { desde: dia(19), hasta: dia(19), total: 1234.5, devuelto: 0, tickets: 12 },
  ayer: { desde: dia(18), hasta: dia(18), total: 800, devuelto: 0, tickets: 1 },
  semana: { desde: dia(13), hasta: dia(19), total: 9000, devuelto: 0, tickets: 70 },
  por_metodo_hoy: { CARD: 234.5, CASH: 1000, MIXED: -10 },
  top_semana: [], poca_existencia: { umbral: 3, productos: [] }, corte,
  sin_movimiento: null, pendientes: null, utilidad_bruta_hoy: null, venta_sin_costo_hoy: null, utilidad_bruta_ayer: null,
  sucursales: [
    { branch_id: 1, nombre: 'Roma', ventas_hoy: 1000, devuelto_hoy: 0, tickets_hoy: 9, corte, poca_existencia: 0 },
    { branch_id: 2, nombre: 'Condesa', ventas_hoy: 3000, devuelto_hoy: 0, tickets_hoy: 3, corte, poca_existencia: 0 },
  ],
  tendencia: {
    dias: [500, 900, 1100, 1300, 1000, 800, 1234.5].map((neta, i) => ({ fecha: dia(13 + i), neta, tickets: 1 })),
    anterior: [1, 2, 3, 4, 5, 6, 7].map((neta, i) => ({ fecha: dia(6 + i), neta, tickets: 1 })),
  },
  por_hora_hoy: Array.from({ length: 24 }, (_, h) => ({ hora: h, neta: h === 7 ? 100 : h === 12 ? 1134.5 : 0, tickets: 0 })),
}

afterEach(cleanup)

describe('InicioGraficas', () => {
  it('tendencia: siete etiquetas de día y la semana anterior como comparativo', () => {
    render(<InicioGraficas seccion="tendencia" datos={DATOS} />)
    const l = screen.getByTestId('linea')
    expect(l.getAttribute('data-etiquetas')?.split('|')).toHaveLength(7)
    expect(l.getAttribute('data-series')).toBe('Estos 7 días=500,900,1100,1300,1000,800,1234.5|Semana anterior*=1,2,3,4,5,6,7')
  })

  it('métodos: efectivo, tarjeta y lo demás con nombre legible y el total de hoy al centro', () => {
    render(<InicioGraficas seccion="metodos" datos={DATOS} />)
    const d = screen.getByTestId('dona')
    expect(d.getAttribute('data-partes')).toBe('Efectivo=1000|Tarjeta=234.5|MIXED=-10')
    expect(d.textContent).toContain('$1,224.50')
  })

  it('horas: recorta la ventana a la primera venta (7) .. 21 y resalta la hora actual', () => {
    render(<InicioGraficas seccion="horas" datos={DATOS} horaActual={12} />)
    const b = screen.getByTestId('barras')
    const etiquetas = b.getAttribute('data-etiquetas')?.split('|') ?? []
    expect(etiquetas[0]).toBe('7:00')
    expect(etiquetas[etiquetas.length - 1]).toBe('21:00')
    expect(b.getAttribute('data-resaltar')).toBe(String(12 - 7))
  })

  it('horas: fuera de la ventana no resalta nada', () => {
    render(<InicioGraficas seccion="horas" datos={DATOS} horaActual={23} />)
    expect(screen.getByTestId('barras').getAttribute('data-resaltar')).toBe('null')
  })

  it('sucursales: barras horizontales ordenadas por venta', () => {
    render(<InicioGraficas seccion="sucursales" datos={DATOS} />)
    const b = screen.getByTestId('barras-h')
    expect(b.getAttribute('data-etiquetas')).toBe('Condesa|Roma')
    expect(b.getAttribute('data-valores')).toBe('3000,1000')
  })

  it('sin tendencia ni horas (servidor viejo) no pinta nada', () => {
    const { container } = render(<InicioGraficas seccion="tendencia" datos={{ ...DATOS, tendencia: null }} />)
    expect(container.innerHTML).toBe('')
  })
})
```

Run: `cd frontend && npx vitest run src/pages/hq/__tests__/InicioGraficas.test.tsx --reporter=dot`
Expected: falla (no existe `../InicioGraficas`).

- [ ] **Step 3: `InicioGraficas.tsx`**

Crear `frontend/src/pages/hq/InicioGraficas.tsx`:

```tsx
// frontend/src/pages/hq/InicioGraficas.tsx
import type { Inicio as DatosInicio } from '../../api/reports'
import {
  GraficaBarras, GraficaDona, GraficaLinea, colorMetodo, etiquetaHora, recortarHoras, useTemaGrafica,
} from '../../components/graficas'
import { formatCurrency } from '../../utils/currency'

/**
 * Las cuatro gráficas del Inicio (spec 2026-10-23 §3.1). Vive aparte de
 * `Inicio.tsx` y se carga con `lazy()` SOLO en perfil completo: el chunk
 * `charts` (chart.js) no debe bajar en modo básico (PC viejas, SP2/SP6).
 * `Inicio.tsx` solo puede importar de aquí el tipo `SeccionGrafica`.
 */
export type SeccionGrafica = 'tendencia' | 'metodos' | 'horas' | 'sucursales'

const METODOS: Record<string, string> = { CASH: 'Efectivo', CARD: 'Tarjeta', TRANSFER: 'Transferencia' }
const ORDEN_METODOS = ['CASH', 'CARD', 'TRANSFER']
/** "vie 17": a mediodía local para que la zona horaria no mueva el día. */
const diaCorto = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString('es-MX', { weekday: 'short', day: 'numeric' })

export function InicioGraficas({ seccion, datos, horaActual = new Date().getHours() }: {
  seccion: SeccionGrafica
  datos: DatosInicio
  /** Hora que se resalta en "horas"; por defecto la del reloj del navegador. */
  horaActual?: number
}) {
  const tema = useTemaGrafica()

  if (seccion === 'tendencia') {
    const t = datos.tendencia
    if (!t) return null
    return (
      <GraficaLinea
        etiquetas={t.dias.map((d) => diaCorto(d.fecha))}
        series={[
          { nombre: 'Estos 7 días', valores: t.dias.map((d) => d.neta) },
          { nombre: 'Semana anterior', valores: t.anterior.map((d) => d.neta), comparativo: true },
        ]}
      />
    )
  }

  if (seccion === 'metodos') {
    const claves = [
      ...ORDEN_METODOS.filter((m) => m in datos.por_metodo_hoy),
      ...Object.keys(datos.por_metodo_hoy).filter((m) => !ORDEN_METODOS.includes(m)),
    ]
    const partes = claves.map((m) => ({ nombre: METODOS[m] ?? m, valor: datos.por_metodo_hoy[m], color: colorMetodo(m, tema) }))
    const total = partes.reduce((s, p) => s + p.valor, 0)
    return (
      <GraficaDona
        partes={partes}
        alto={200}
        centro={(
          <>
            <span className="dax-kpi-label">Hoy</span>
            <span className="text-base font-black tabular-nums text-dax-text">{formatCurrency(total)}</span>
          </>
        )}
      />
    )
  }

  if (seccion === 'horas') {
    const horas = datos.por_hora_hoy
    if (!horas) return null
    const { desde, hasta } = recortarHoras(horas)
    const ventana = horas.slice(desde, hasta + 1)
    const indice = ventana.findIndex((h) => h.hora === horaActual)
    return (
      <GraficaBarras
        etiquetas={ventana.map((h) => etiquetaHora(h.hora))}
        valores={ventana.map((h) => h.neta)}
        resaltar={indice >= 0 ? indice : null}
        alto={200}
        nombre="Venta de hoy"
      />
    )
  }

  const lista = [...(datos.sucursales ?? [])].sort((a, b) => b.ventas_hoy - a.ventas_hoy)
  return (
    <GraficaBarras
      etiquetas={lista.map((s) => s.nombre)}
      valores={lista.map((s) => s.ventas_hoy)}
      horizontal
      alto={Math.max(120, 36 * lista.length + 40)}
      nombre="Venta de hoy"
    />
  )
}
```

- [ ] **Step 4: Registrar el módulo perezoso**

En `frontend/src/__tests__/rutasPerezosas.test.ts`, dentro de `PEREZOSOS` (líneas 8-12), antes del comentario `// Añadir aquí…`:

```ts
  // Fase 2 del admin: las gráficas del Inicio solo bajan en perfil completo.
  InicioGraficas: () => import('../pages/hq/InicioGraficas'),
```

- [ ] **Step 5: Correr**

Run: `cd frontend && npx vitest run src/pages/hq/__tests__/InicioGraficas.test.tsx src/__tests__/rutasPerezosas.test.ts src/pages/__tests__/hqSinEstilosInline.test.ts --reporter=dot && npx tsc --noEmit -p tsconfig.json`
Expected: verde (`InicioGraficas.tsx` está en `pages/hq` y no tiene `style={{`; las alturas se pasan como `alto`); tsc limpio.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/reports.ts frontend/src/pages/hq/InicioGraficas.tsx frontend/src/pages/hq/__tests__/InicioGraficas.test.tsx frontend/src/__tests__/rutasPerezosas.test.ts
git commit -m "feat(inicio): módulo perezoso InicioGraficas (tendencia, métodos, horas, sucursales) y tipos de la Fase 2

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf"
```

---

### Task 6: Inicio — cifras con variación, rejilla de 12, gráficas perezosas y tokens

**Files:**
- Modify: `frontend/src/pages/hq/Inicio.tsx` (reescritura completa)
- Modify: `frontend/src/components/reports/ValorTiendaCard.tsx` (solo clases → tokens; props y `data-testid` iguales)
- Modify: `frontend/src/pages/hq/__tests__/Inicio.test.tsx` (reescritura completa)
- Modify: `frontend/src/__tests__/modoBasico.test.ts:8-12` (NUEVOS) y `:28` (aserción del Inicio)

**Interfaces:**
- Consumes: `KpiCard`, `variacion` (Tarea 4); `InicioGraficas`/`SeccionGrafica` (Tarea 5, solo vía `lazy()` e `import type`); tipos `Inicio` con `tendencia`, `por_hora_hoy`, `utilidad_bruta_ayer`, `hoy.devuelto` (Tarea 5).
- Produces: `Inicio` sigue exportándose con el mismo nombre (App.tsx no cambia). `data-testid` estables para capturas y pruebas: `cifra-hoy`, `cifra-ayer`, `cifra-semana`, `cifra-utilidad`, `metodo`, `corte`, `pendientes`, `sucursales`, `grafica-<seccion>` (lo pone el stub en pruebas; en producción el módulo real no lo pone).

**Decisiones:** variaciones = Hoy vs ayer (`ayer.total`, también en básico), Ayer vs antier (`tendencia.dias[4].neta`), 7 días vs semana anterior (suma de `tendencia.anterior`), Utilidad de hoy vs `utilidad_bruta_ayer`; sin `tendencia` (básico o servidor viejo) esas tres cifras no llevan variación y la pantalla cae al diseño sin gráficas. Orden de escritorio = spec §3.1; `ValorTiendaCard` se queda al final, donde está hoy (la spec no la mueve).

- [ ] **Step 1: Pruebas que fallan**

Sustituir `frontend/src/pages/hq/__tests__/Inicio.test.tsx` entero por:

```tsx
// frontend/src/pages/hq/__tests__/Inicio.test.tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, cleanup, within } from '@testing-library/react'

const { inicio, valorInventario } = vi.hoisted(() => ({ inicio: vi.fn(), valorInventario: vi.fn() }))
vi.mock('../../../api/reports', () => ({ reportsApi: { inicio, valorInventario } }))
// El módulo perezoso de gráficas se sustituye por un marcador: aquí se prueba
// CUÁNDO se monta (perfil), no el dibujo (eso es de InicioGraficas.test.tsx).
vi.mock('../InicioGraficas', () => ({
  InicioGraficas: ({ seccion }: { seccion: string }) => <div data-testid={`grafica-${seccion}`} />,
}))

import { Inicio } from '../Inicio'
import { useEnabledModulesStore } from '../../../store/enabledModulesStore'

const dia = (n: number) => `2026-10-${String(n).padStart(2, '0')}`
// La forma exacta de GET /reports/inicio sin `completo` (modo básico).
const DATOS = {
  branch_id: null,
  hoy: { desde: dia(19), hasta: dia(19), total: 1234.5, devuelto: 0, tickets: 12 },
  ayer: { desde: dia(18), hasta: dia(18), total: 800, devuelto: 0, tickets: 1 },
  semana: { desde: dia(13), hasta: dia(19), total: 9000, devuelto: 0, tickets: 70 },
  por_metodo_hoy: { CARD: 234.5, CASH: 1000 },
  top_semana: [{ nombre: 'Blusa roja', cantidad: 14, total: 1400 }],
  poca_existencia: { umbral: 3, productos: [{ variant_id: 'v1', nombre: 'Falda negra', sku: 'FAL-1', existencia: 1 }] },
  corte: { estado: 'abierto', cajera: 'Mirna', abierto_en: '2026-10-19T15:00:00+00:00', cerrado_en: null, efectivo_esperado: 1500, efectivo_contado: null },
  sin_movimiento: null, pendientes: null, sucursales: null, utilidad_bruta_hoy: null, venta_sin_costo_hoy: null,
  tendencia: null, por_hora_hoy: null, utilidad_bruta_ayer: null,
}
// Lo que trae `completo=true` para una org de paga con dos sucursales.
const COMPLETO = {
  ...DATOS,
  sin_movimiento: { dias: 30, productos: [{ variant_id: 'v9', nombre: 'Abrigo largo', sku: 'ABR-1', existencia: 3, importe_venta: 2700 }] },
  pendientes: {
    devoluciones: 2, turnos_abiertos: 1,
    diferencias_caja: [{ session_id: 7, sucursal: 'Roma', cajera: 'Lupita', cerrado_en: '2026-10-18T23:00:00+00:00', esperado: 500, contado: 480, diferencia: -20 }],
  },
  sucursales: [
    { branch_id: 1, nombre: 'Roma', ventas_hoy: 1000, devuelto_hoy: 0, tickets_hoy: 9, corte: DATOS.corte, poca_existencia: 2 },
    { branch_id: 2, nombre: 'Condesa', ventas_hoy: 234.5, devuelto_hoy: 0, tickets_hoy: 3, corte: { ...DATOS.corte, estado: 'sin_turno' }, poca_existencia: 0 },
  ],
  utilidad_bruta_hoy: 400, venta_sin_costo_hoy: 234.5, utilidad_bruta_ayer: 300,
  // 7 días terminando hoy (antier = índice 4 → 1000) y los 7 previos (suman 7500).
  tendencia: {
    dias: [500, 900, 1100, 1300, 1000, 800, 1234.5].map((neta, i) => ({ fecha: dia(13 + i), neta, tickets: i + 1 })),
    anterior: [1000, 1000, 1000, 1000, 1000, 1000, 1500].map((neta, i) => ({ fecha: dia(6 + i), neta, tickets: 1 })),
  },
  por_hora_hoy: Array.from({ length: 24 }, (_, h) => ({ hora: h, neta: h === 12 ? 1234.5 : 0, tickets: h === 12 ? 12 : 0 })),
}
const VALUACION = {
  agrupar: 'sucursal', branch_id: null, ve_costo: true, grupos: [],
  totales: { piezas: 10, skus: 2, valor_venta: 5000, valor_costo: 2000, piezas_sin_costo: 0, skus_sin_costo: 0 },
}
const pintar = () => render(<MemoryRouter><Inicio /></MemoryRouter>)
const perfil = (perfilUi: 'basico' | 'completo') => useEnabledModulesStore.setState({ loaded: true, perfilUi })
const variacionDe = (testId: string) => within(screen.getByTestId(testId)).queryByTestId('variacion')

beforeEach(() => {
  perfil('basico')
  inicio.mockReset().mockResolvedValue(DATOS)
  valorInventario.mockReset().mockResolvedValue(VALUACION)
})
afterEach(() => { cleanup(); useEnabledModulesStore.getState().reset() })

describe('Inicio', () => {
  it('los enlaces de las tarjetas miden 44px en teléfono', async () => {
    pintar()
    await screen.findByTestId('cifra-hoy')
    for (const texto of ['Ver corte →', 'Ver productos →', 'Ver desglose →']) {
      expect(screen.getByText(texto).className).toContain('max-md:min-h-[44px]')
    }
  })

  it('vendido hoy, ayer y en 7 días', async () => {
    pintar()
    const hoy = await screen.findByTestId('cifra-hoy')
    expect(hoy.textContent).toContain('$1,234.50')
    expect(hoy.textContent).toContain('12 ventas')
    expect(screen.getByTestId('cifra-ayer').textContent).toContain('1 venta')
    expect(screen.getByTestId('cifra-semana').textContent).toContain('$9,000.00')
  })

  it('hoy con devoluciones dice cuánto se devolvió', async () => {
    inicio.mockResolvedValue({ ...DATOS, hoy: { ...DATOS.hoy, total: 1194.5, devuelto: 40 } })
    pintar()
    expect((await screen.findByTestId('cifra-hoy')).textContent).toContain('12 ventas · $40.00 devuelto')
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
    inicio.mockResolvedValue({ ...DATOS, corte: { ...DATOS.corte, estado: 'cerrado', cerrado_en: '2026-10-19T23:00:00+00:00', efectivo_esperado: null, efectivo_contado: 850 } })
    pintar()
    expect((await screen.findByTestId('corte')).textContent).toContain('$850.00')
    cleanup()
    inicio.mockResolvedValue({ ...DATOS, corte: { estado: 'sin_turno', cajera: null, abierto_en: null, cerrado_en: null, efectivo_esperado: null, efectivo_contado: null } })
    pintar()
    expect((await screen.findByTestId('corte')).textContent).toContain('Nadie ha abierto turno')
  })

  it('si el resumen falla, el mensaje del servidor y la tarjeta del valor siguen', async () => {
    inicio.mockRejectedValue({ response: { data: { detail: 'Solo administrador, dueño o gerente pueden ver el inicio' } } })
    pintar()
    expect(await screen.findByText('Solo administrador, dueño o gerente pueden ver el inicio')).toBeTruthy()
    expect(await screen.findByTestId('valor-tienda')).toBeTruthy()
  })

  it('en básico pide completo=false y no pinta No se mueve, Pendientes ni Sucursales', async () => {
    pintar()
    await screen.findByTestId('cifra-hoy')
    expect(inicio).toHaveBeenCalledWith({ completo: false })
    expect(screen.queryByText(/No se mueve/)).toBeNull()
    expect(screen.queryByText('Pendientes')).toBeNull()
    expect(screen.queryByTestId('sucursales')).toBeNull()
    expect(screen.queryByTestId('cifra-utilidad')).toBeNull()
  })

  it('en básico no monta ninguna gráfica (el chunk charts no baja) y solo Hoy trae variación', async () => {
    pintar()
    await screen.findByTestId('cifra-hoy')
    await new Promise((r) => setTimeout(r, 20))
    expect(document.querySelector('[data-testid^="grafica-"]')).toBeNull()
    expect(screen.queryByText('Cargando gráfica…')).toBeNull()
    expect(variacionDe('cifra-hoy')?.textContent).toContain('▲ 54 %')   // 1234.5 vs 800
    expect(variacionDe('cifra-ayer')).toBeNull()
    expect(variacionDe('cifra-semana')).toBeNull()
  })

  it('en completo pide completo=true y pinta las tres secciones y la utilidad', async () => {
    perfil('completo')
    inicio.mockResolvedValue(COMPLETO)
    pintar()
    await screen.findByTestId('cifra-hoy')
    expect(inicio).toHaveBeenCalledWith({ completo: true })
    expect(screen.getByTestId('cifra-utilidad').textContent).toContain('$400.00')
    expect(screen.getByTestId('cifra-utilidad').textContent).toContain('sobre $1,000.00 con costo · $234.50 vendidos sin costo')
    expect(screen.getByText(/No se mueve \(sin venta en 30 días\)/)).toBeTruthy()
    expect(screen.getByText('Abrigo largo').closest('a')?.getAttribute('href')).toBe('/hq/inventory?q=ABR-1&variant=v9')
    expect(screen.getByText('2 devoluciones por aprobar →').getAttribute('href')).toBe('/hq/returns')
    expect(screen.getByText(/1 turno abierto desde hace más de un día/)).toBeTruthy()
    expect(screen.getByText('Lupita')).toBeTruthy()
    const sucursales = screen.getByTestId('sucursales')
    expect(sucursales.textContent).toContain('Roma')
    expect(sucursales.textContent).toContain('2 productos se están acabando')
    expect(sucursales.querySelector('a')?.getAttribute('href')).toBe('/hq/branches/1')
  })

  it('en completo monta las cuatro gráficas y conserva la lista de métodos y la caja', async () => {
    perfil('completo')
    inicio.mockResolvedValue(COMPLETO)
    pintar()
    for (const s of ['tendencia', 'metodos', 'horas', 'sucursales']) expect(await screen.findByTestId(`grafica-${s}`)).toBeTruthy()
    expect(screen.getAllByTestId('metodo')).toHaveLength(2)
    expect(screen.getByTestId('corte').textContent).toContain('Turno abierto')
    expect(screen.getByText('Ver corte →').className).toContain('max-md:min-h-[44px]')
  })

  it('variaciones: hoy vs ayer, ayer vs antier, 7 días vs semana anterior, utilidad vs ayer', async () => {
    perfil('completo')
    inicio.mockResolvedValue(COMPLETO)
    pintar()
    await screen.findByTestId('cifra-hoy')
    expect(variacionDe('cifra-hoy')?.textContent).toBe('▲ 54 % vs ayer')                // 1234.5 vs 800
    expect(variacionDe('cifra-ayer')?.textContent).toBe('▼ 20 % vs antier')             // 800 vs 1000
    expect(variacionDe('cifra-semana')?.textContent).toBe('▲ 20 % vs semana anterior')  // 9000 vs 7500
    expect(variacionDe('cifra-utilidad')?.textContent).toBe('▲ 33 % vs ayer')           // 400 vs 300
  })

  it('completo sin tendencia (servidor viejo) cae al diseño sin gráficas', async () => {
    perfil('completo')
    inicio.mockResolvedValue({ ...COMPLETO, tendencia: null, por_hora_hoy: null })
    pintar()
    await screen.findByTestId('cifra-hoy')
    await new Promise((r) => setTimeout(r, 20))
    expect(screen.queryByTestId('grafica-tendencia')).toBeNull()
    expect(screen.queryByTestId('grafica-horas')).toBeNull()
    expect(screen.getAllByTestId('metodo')).toHaveLength(2)
    expect(variacionDe('cifra-ayer')).toBeNull()
  })

  it('completo con una sola sucursal y nada pendiente: sin sección de sucursales y "Nada pendiente"', async () => {
    perfil('completo')
    inicio.mockResolvedValue({ ...COMPLETO, sucursales: null, pendientes: { devoluciones: 0, turnos_abiertos: 0, diferencias_caja: [] } })
    pintar()
    await screen.findByTestId('cifra-hoy')
    expect(screen.queryByTestId('sucursales')).toBeNull()
    expect(screen.queryByTestId('grafica-sucursales')).toBeNull()
    expect(screen.getByText('Nada pendiente.')).toBeTruthy()
  })

  it('espera al contexto antes de pedir (no manda completo=true por el default del store)', async () => {
    useEnabledModulesStore.setState({ loaded: false, perfilUi: 'completo', loading: true })
    pintar()
    await new Promise((r) => setTimeout(r, 20))
    expect(inicio).not.toHaveBeenCalled()
    perfil('basico')
    await screen.findByTestId('cifra-hoy')
    expect(inicio).toHaveBeenCalledWith({ completo: false })
  })

  it('en básico los enlaces van a Productos y Mis ventas, nunca a pantallas HQ escondidas', async () => {
    pintar()
    await screen.findByTestId('cifra-hoy')
    const hrefs = Array.from(document.querySelectorAll('a')).map((a) => a.getAttribute('href'))
    expect(hrefs).toContain('/products')
    expect(hrefs).toContain('/sales')
    expect(hrefs.some((h) => h?.startsWith('/hq/inventory') || h?.startsWith('/hq/sales'))).toBe(false)
    expect(screen.getByText('Falda negra').closest('a')?.getAttribute('href')).toBe('/products')
  })

  it('en completo los mismos enlaces abren Existencias y Ventas HQ', async () => {
    perfil('completo')
    inicio.mockResolvedValue(COMPLETO)
    pintar()
    await screen.findByTestId('cifra-hoy')
    expect(screen.getByText('Falda negra').closest('a')?.getAttribute('href')).toBe('/hq/inventory?q=FAL-1&variant=v1')
    expect(screen.getByText('Ver ventas →').getAttribute('href')).toBe('/hq/sales')
  })
})
```

En `frontend/src/__tests__/modoBasico.test.ts`:

- En `NUEVOS` (líneas 8-12) añadir `'pages/hq/InicioGraficas.tsx'` después de `'pages/hq/Inicio.tsx'`.
- Sustituir la línea 28 (`expect(src('pages/hq/Inicio.tsx')).not.toMatch(/chart\.js|react-chartjs-2/)`) por:

```ts
    // El Inicio solo llega a las gráficas por lazy(): chart.js no viaja en su chunk.
    const inicio = src('pages/hq/Inicio.tsx')
    expect(inicio).not.toMatch(/chart\.js|react-chartjs-2|components\/graficas/)
    expect(inicio).toMatch(/lazy\(\(\) => import\('\.\/InicioGraficas'\)/)
    expect(inicio).not.toMatch(/^import \{[^}]*\} from '\.\/InicioGraficas'/m)   // solo `import type`
```

(La aserción de `PorPerfil` de la línea 27 se queda hasta la Tarea 9.)

Run: `cd frontend && npx vitest run src/pages/hq/__tests__/Inicio.test.tsx src/__tests__/modoBasico.test.ts --reporter=dot`
Expected: fallan (sin variaciones, sin gráficas, sin `lazy`).

- [ ] **Step 2: Reescribir `Inicio.tsx`**

Sustituir `frontend/src/pages/hq/Inicio.tsx` entero por:

```tsx
// frontend/src/pages/hq/Inicio.tsx
import { lazy, Suspense, useEffect, useState, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { reportsApi, type Inicio as DatosInicio, type ValuacionInventario } from '../../api/reports'
import { ValorTiendaCard } from '../../components/reports/ValorTiendaCard'
import { CabeceraPagina } from '../../components/ui/CabeceraPagina'
import { DaxCard } from '../../components/ui/DaxCard'
import { KpiCard } from '../../components/ui/KpiCard'
import { ListaTarjetas } from '../../components/ui/ListaTarjetas'
import { TarjetaFila } from '../../components/ui/TarjetaFila'
import { Spinner } from '../../components/ui/Spinner'
import { useEsTelefono } from '../../hooks/useIsMobile'
import { useEnabledModulesStore } from '../../store/enabledModulesStore'
import { formatCurrency } from '../../utils/currency'
import { errorDetailText } from '../../utils/errorDetail'
import { variacion } from '../../utils/variacion'
import type { SeccionGrafica } from './InicioGraficas'

/**
 * Inicio del dueño (SP6, spec 2026-10-21 §3; gráficas de la Fase 2, spec
 * 2026-10-23 §3.1): UNA pantalla que responde sus preguntas al entrar. Cada
 * sección es una pregunta y enlaza a su detalle. En perfil básico (FREE) pinta
 * el subconjunto de hoy (preguntas 1, 2, 3, 4 y 6), pide `completo=false` y NO
 * pinta gráficas; en completo pide las secciones nuevas (5, 7, 8) y monta las
 * cuatro gráficas en una rejilla de 12 columnas. Una llamada (`/reports/inicio`)
 * + la tarjeta de valor de la tienda de SP3. La librería de gráficas nunca
 * viaja en este chunk: las gráficas viven en `./InicioGraficas` y se cargan
 * con `lazy()` solo cuando se pintan.
 */
const InicioGraficas = lazy(() => import('./InicioGraficas').then((m) => ({ default: m.InicioGraficas })))

const METODOS: Record<string, string> = { CASH: 'Efectivo', CARD: 'Tarjeta', TRANSFER: 'Transferencia' }
const ORDEN_METODOS = ['CASH', 'CARD', 'TRANSFER']

const hora = (iso: string | null) =>
  iso ? new Date(iso).toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' }) : ''
const fecha = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString('es-MX', { day: '2-digit', month: 'short' }) : ''
const piezas = (n: number) => {
  const r = Math.round(n * 100) / 100
  return `${r.toLocaleString('es-MX')} ${r === 1 ? 'pieza' : 'piezas'}`
}
const ventas = (n: number) => `${n} ${n === 1 ? 'venta' : 'ventas'}`
/** Enlaces de detalle por perfil: en básico, a las pantallas que SÍ están en su menú
 *  (Productos y Mis ventas); en completo, a Existencias (kardex, ajuste, costo) y Ventas HQ. */
const ENLACES = {
  basico:   { existencias: '/products', ventas: '/sales' },
  completo: { existencias: '/hq/inventory', ventas: '/hq/sales' },
} as const
const urlExistencias = (basico: boolean, sku: string, variantId: string) =>
  basico ? ENLACES.basico.existencias : `/hq/inventory?q=${encodeURIComponent(sku)}&variant=${encodeURIComponent(variantId)}`

/** Título de sección: la pregunta que responde y, si hay, el enlace a su detalle. */
function Titulo({ children, enlace }: { children: ReactNode; enlace?: { a: string; texto: string } }) {
  return (
    <div className="flex items-center justify-between gap-2 mb-3">
      <p className="dax-section-title">{children}</p>
      {enlace && (
        <Link to={enlace.a} className="text-[10px] font-bold text-dax-accent-text hover:underline whitespace-nowrap max-md:inline-flex max-md:items-center max-md:min-h-[44px]">
          {enlace.texto}
        </Link>
      )}
    </div>
  )
}

const Vacio = ({ children }: { children: ReactNode }) => <p className="text-sm text-dax-muted">{children}</p>
const Th = ({ children, der }: { children: ReactNode; der?: boolean }) => (
  <th className={`py-1 ${der ? 'text-right' : ''}`}>{children}</th>
)
const cabecera = 'text-left text-[10px] uppercase tracking-widest text-dax-faint'
const fila = 'border-t border-dax-border-dim'

/** Una gráfica del módulo perezoso; solo se monta en perfil completo. */
function Grafica({ seccion, datos }: { seccion: SeccionGrafica; datos: DatosInicio }) {
  return (
    <Suspense fallback={<p className="text-xs text-dax-faint py-10 text-center">Cargando gráfica…</p>}>
      <InicioGraficas seccion={seccion} datos={datos} />
    </Suspense>
  )
}

function Corte({ corte }: { corte: DatosInicio['corte'] }) {
  if (corte.estado === 'abierto') {
    return (
      <div className="space-y-1" data-testid="corte">
        <p className="text-sm font-bold text-dax-success">Turno abierto</p>
        <p className="text-sm text-dax-muted">{corte.cajera ?? 'Sin nombre'} · desde las {hora(corte.abierto_en)}</p>
        <p className="text-sm text-dax-muted">
          Efectivo esperado en caja:{' '}
          <span className="font-bold tabular-nums text-dax-text">{formatCurrency(corte.efectivo_esperado)}</span>
        </p>
      </div>
    )
  }
  if (corte.estado === 'cerrado') {
    return (
      <div className="space-y-1" data-testid="corte">
        <p className="text-sm font-bold text-dax-muted">Turno cerrado</p>
        <p className="text-sm text-dax-muted">{corte.cajera ?? 'Sin nombre'} cerró a las {hora(corte.cerrado_en)}</p>
        <p className="text-sm text-dax-muted">
          Contó <span className="font-bold tabular-nums text-dax-text">{formatCurrency(corte.efectivo_contado)}</span>
        </p>
      </div>
    )
  }
  return <p className="text-sm text-dax-muted" data-testid="corte">Nadie ha abierto turno.</p>
}

function ListaMetodos({ datos, metodos }: { datos: DatosInicio; metodos: string[] }) {
  return (
    <ul className="space-y-1">
      {metodos.map((m) => (
        <li key={m} data-testid="metodo" className="flex justify-between text-sm">
          <span className="text-dax-muted">{METODOS[m] ?? m}</span>
          <span className="font-bold tabular-nums text-dax-text">{formatCurrency(datos.por_metodo_hoy[m])}</span>
        </li>
      ))}
    </ul>
  )
}

function SeAcaba({ datos, esTelefono, basico }: { datos: DatosInicio; esTelefono: boolean; basico: boolean }) {
  const navigate = useNavigate()
  const acabando = datos.poca_existencia.productos
  const enlaces = basico ? ENLACES.basico : ENLACES.completo
  return (
    <DaxCard>
      <Titulo enlace={{ a: enlaces.existencias, texto: basico ? 'Ver productos →' : 'Ver existencias →' }}>
        Se está acabando (quedan {datos.poca_existencia.umbral} o menos)
      </Titulo>
      {esTelefono ? (
        <ListaTarjetas vacio={acabando.length === 0} textoVacio="Nada se está acabando.">
          {acabando.map((p) => (
            <TarjetaFila key={p.variant_id} titulo={p.nombre} subtitulo={p.sku} importe={piezas(p.existencia)}
              onClick={() => navigate(urlExistencias(basico, p.sku, p.variant_id))} />
          ))}
        </ListaTarjetas>
      ) : acabando.length === 0 ? (
        <Vacio>Nada se está acabando.</Vacio>
      ) : (
        <table className="w-full text-sm">
          <thead><tr className={cabecera}><Th>Producto</Th><Th>Código</Th><Th der>Quedan</Th></tr></thead>
          <tbody>
            {acabando.map((p) => (
              <tr key={p.variant_id} className={fila}>
                <td className="py-1.5 text-dax-text"><Link to={urlExistencias(basico, p.sku, p.variant_id)} className="hover:underline">{p.nombre}</Link></td>
                <td className="py-1.5 font-mono text-xs text-dax-muted">{p.sku}</td>
                <td className="py-1.5 text-right tabular-nums font-bold text-dax-warning">{piezas(p.existencia)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </DaxCard>
  )
}

function MasVendido({ datos, esTelefono }: { datos: DatosInicio; esTelefono: boolean }) {
  const top = datos.top_semana
  return (
    <DaxCard>
      <Titulo enlace={{ a: '/hq/reports-hub', texto: 'Ver reportes →' }}>Lo que más se vendió (7 días)</Titulo>
      {esTelefono ? (
        <ListaTarjetas vacio={top.length === 0} textoVacio="Sin ventas esta semana.">
          {top.map((t) => (
            <TarjetaFila key={t.nombre} titulo={t.nombre} subtitulo={piezas(t.cantidad)} importe={formatCurrency(t.total)} />
          ))}
        </ListaTarjetas>
      ) : top.length === 0 ? (
        <Vacio>Sin ventas esta semana.</Vacio>
      ) : (
        <table className="w-full text-sm">
          <thead><tr className={cabecera}><Th>Producto</Th><Th der>Piezas</Th><Th der>Importe</Th></tr></thead>
          <tbody>
            {top.map((t) => (
              <tr key={t.nombre} className={fila}>
                <td className="py-1.5 text-dax-text">{t.nombre}</td>
                <td className="py-1.5 text-right tabular-nums text-dax-muted">{piezas(t.cantidad)}</td>
                <td className="py-1.5 text-right tabular-nums font-bold text-dax-text">{formatCurrency(t.total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </DaxCard>
  )
}

function NoSeMueve({ datos, esTelefono }: { datos: NonNullable<DatosInicio['sin_movimiento']>; esTelefono: boolean }) {
  const navigate = useNavigate()
  const lista = datos.productos
  return (
    <DaxCard>
      <Titulo enlace={{ a: '/hq/inventory', texto: 'Ver existencias →' }}>
        No se mueve (sin venta en {datos.dias} días)
      </Titulo>
      {esTelefono ? (
        <ListaTarjetas vacio={lista.length === 0} textoVacio="Todo se ha vendido en ese plazo.">
          {lista.map((p) => (
            <TarjetaFila key={p.variant_id} titulo={p.nombre} subtitulo={p.sku}
              importe={formatCurrency(p.importe_venta)} estado={piezas(p.existencia)}
              onClick={() => navigate(urlExistencias(false, p.sku, p.variant_id))} />
          ))}
        </ListaTarjetas>
      ) : lista.length === 0 ? (
        <Vacio>Todo se ha vendido en ese plazo.</Vacio>
      ) : (
        <table className="w-full text-sm">
          <thead><tr className={cabecera}><Th>Producto</Th><Th>Código</Th><Th der>Existencia</Th><Th der>Parado</Th></tr></thead>
          <tbody>
            {lista.map((p) => (
              <tr key={p.variant_id} className={fila}>
                <td className="py-1.5 text-dax-text"><Link to={urlExistencias(false, p.sku, p.variant_id)} className="hover:underline">{p.nombre}</Link></td>
                <td className="py-1.5 font-mono text-xs text-dax-muted">{p.sku}</td>
                <td className="py-1.5 text-right tabular-nums text-dax-muted">{piezas(p.existencia)}</td>
                <td className="py-1.5 text-right tabular-nums font-bold text-dax-text">{formatCurrency(p.importe_venta)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </DaxCard>
  )
}

function Pendientes({ datos, esTelefono }: { datos: NonNullable<DatosInicio['pendientes']>; esTelefono: boolean }) {
  const nada = datos.devoluciones === 0 && datos.turnos_abiertos === 0 && datos.diferencias_caja.length === 0
  const enlace = 'max-md:inline-flex max-md:items-center max-md:min-h-[44px] hover:underline'
  const tonoDiferencia = (d: number) => (d < 0 ? 'text-dax-danger' : 'text-dax-success')
  return (
    <DaxCard>
      <Titulo>Pendientes</Titulo>
      {nada ? (
        <Vacio>Nada pendiente.</Vacio>
      ) : (
        <div className="space-y-3" data-testid="pendientes">
          {datos.devoluciones > 0 && (
            <Link to="/hq/returns" className={`block text-sm text-dax-warning ${enlace}`}>
              {datos.devoluciones === 1 ? '1 devolución por aprobar' : `${datos.devoluciones} devoluciones por aprobar`} →
            </Link>
          )}
          {datos.turnos_abiertos > 0 && (
            <Link to="/cash-history" className={`block text-sm text-dax-warning ${enlace}`}>
              {datos.turnos_abiertos === 1 ? '1 turno abierto desde hace más de un día' : `${datos.turnos_abiertos} turnos abiertos desde hace más de un día`} →
            </Link>
          )}
          {datos.diferencias_caja.length > 0 && (
            <div>
              <p className="text-xs font-bold text-dax-muted mb-1">Cortes que no cuadraron (7 días)</p>
              {esTelefono ? (
                <ListaTarjetas>
                  {datos.diferencias_caja.map((d) => (
                    <TarjetaFila key={d.session_id} titulo={`${d.sucursal} · ${d.cajera ?? 'Sin nombre'}`}
                      subtitulo={fecha(d.cerrado_en)}
                      importe={<span className={tonoDiferencia(d.diferencia)}>{formatCurrency(d.diferencia)}</span>}
                      datos={[{ etiqueta: 'Esperado', valor: formatCurrency(d.esperado) }, { etiqueta: 'Contado', valor: formatCurrency(d.contado) }]} />
                  ))}
                </ListaTarjetas>
              ) : (
                <table className="w-full text-sm">
                  <thead><tr className={cabecera}><Th>Fecha</Th><Th>Sucursal</Th><Th>Cajera</Th><Th der>Esperado</Th><Th der>Contado</Th><Th der>Diferencia</Th></tr></thead>
                  <tbody>
                    {datos.diferencias_caja.map((d) => (
                      <tr key={d.session_id} className={fila}>
                        <td className="py-1.5 text-dax-muted">{fecha(d.cerrado_en)}</td>
                        <td className="py-1.5 text-dax-text">{d.sucursal}</td>
                        <td className="py-1.5 text-dax-muted">{d.cajera ?? 'Sin nombre'}</td>
                        <td className="py-1.5 text-right tabular-nums text-dax-muted">{formatCurrency(d.esperado)}</td>
                        <td className="py-1.5 text-right tabular-nums text-dax-muted">{formatCurrency(d.contado)}</td>
                        <td className={`py-1.5 text-right tabular-nums font-bold ${tonoDiferencia(d.diferencia)}`}>{formatCurrency(d.diferencia)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </div>
      )}
    </DaxCard>
  )
}

function Sucursales({ lista, grafica }: { lista: NonNullable<DatosInicio['sucursales']>; grafica: ReactNode }) {
  const estadoCorte = (c: DatosInicio['corte']) =>
    c.estado === 'abierto' ? <span className="text-dax-success">Turno abierto</span>
      : c.estado === 'cerrado' ? <span className="text-dax-muted">Turno cerrado</span>
        : <span className="text-dax-faint">Sin turno</span>
  return (
    <DaxCard>
      <Titulo enlace={{ a: '/hq/branches', texto: 'Ver sucursales →' }}>Cómo va cada sucursal (hoy)</Titulo>
      {grafica}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 mt-3" data-testid="sucursales">
        {lista.map((s) => (
          <Link key={s.branch_id} to={`/hq/branches/${s.branch_id}`} className="block rounded-lg border border-dax-border-dim p-3 hover:border-dax-accent max-md:min-h-[44px]">
            <p className="font-bold text-dax-text text-sm">{s.nombre}</p>
            <p className="text-xl font-bold text-dax-text tabular-nums">{formatCurrency(s.ventas_hoy)}</p>
            <p className="text-xs text-dax-muted">{ventas(s.tickets_hoy)} · {estadoCorte(s.corte)}</p>
            {s.poca_existencia > 0 && (
              <p className="text-xs text-dax-warning mt-1">{s.poca_existencia === 1 ? '1 producto se está acabando' : `${s.poca_existencia} productos se están acabando`}</p>
            )}
          </Link>
        ))}
      </div>
    </DaxCard>
  )
}

export function Inicio() {
  const esTelefono = useEsTelefono()
  const loaded = useEnabledModulesStore((s) => s.loaded)
  const load = useEnabledModulesStore((s) => s.load)
  const perfilUi = useEnabledModulesStore((s) => s.perfilUi)
  const [datos, setDatos] = useState<DatosInicio | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [valuacion, setValuacion] = useState<ValuacionInventario | null>(null)
  const [valuacionError, setValuacionError] = useState<string | null>(null)

  // Espera al contexto: con el default 'completo' del store una FREE pediría
  // las secciones de paga para cambiarlas un segundo después.
  useEffect(() => {
    if (!loaded) void load()
  }, [loaded, load])

  useEffect(() => {
    if (!loaded) return
    let vivo = true
    reportsApi.inicio({ completo: perfilUi !== 'basico' })
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
  }, [loaded, perfilUi])

  const metodos = datos
    ? [
        ...ORDEN_METODOS.filter((m) => m in datos.por_metodo_hoy),
        ...Object.keys(datos.por_metodo_hoy).filter((m) => !ORDEN_METODOS.includes(m)),
      ]
    : []
  const basico = perfilUi === 'basico'
  const conUtilidad = datos?.utilidad_bruta_hoy != null
  const sinCosto = datos?.venta_sin_costo_hoy ?? 0
  const conCosto = Math.max(0, (datos?.hoy.total ?? 0) - sinCosto)
  const devueltoHoy = datos?.hoy.devuelto ?? 0

  // Variaciones (spec §3.1): hoy vs ayer sale de lo que siempre viene; ayer vs
  // antier y 7 días vs la semana anterior salen de `tendencia`, que solo viaja
  // en perfil completo (en básico esas dos cifras van sin variación).
  const tendencia = datos?.tendencia ?? null
  const antier = tendencia && tendencia.dias.length >= 3 ? tendencia.dias[tendencia.dias.length - 3].neta : null
  const semanaAnterior = tendencia ? tendencia.anterior.reduce((s, d) => s + d.neta, 0) : null
  // Sin `tendencia` (básico o servidor viejo) no hay gráficas y la pantalla cae al diseño plano.
  const conGraficas = !basico && tendencia !== null && (datos?.por_hora_hoy ?? null) !== null

  return (
    <div className="space-y-5">
      <CabeceraPagina
        titulo={<h1 className="text-2xl font-black text-dax-text">¿Cómo voy?</h1>}
        descripcion="Lo vendido, la caja, lo que se acaba y lo que hay que atender."
      />

      {error ? (
        <DaxCard><p className="text-sm text-dax-danger">{error}</p></DaxCard>
      ) : !datos ? (
        <Spinner size="lg" text="Cargando…" />
      ) : (
        <>
          {/* 1 · Cifras */}
          <div className={`grid grid-cols-1 sm:grid-cols-2 ${conUtilidad ? 'lg:grid-cols-4' : 'lg:grid-cols-3'} gap-3`}>
            <KpiCard etiqueta="Hoy" valor={formatCurrency(datos.hoy.total)}
              detalle={devueltoHoy > 0 ? `${ventas(datos.hoy.tickets)} · ${formatCurrency(devueltoHoy)} devuelto` : ventas(datos.hoy.tickets)}
              variacion={variacion(datos.hoy.total, datos.ayer.total, 'vs ayer')} data-testid="cifra-hoy" />
            <KpiCard etiqueta="Ayer" valor={formatCurrency(datos.ayer.total)} detalle={ventas(datos.ayer.tickets)}
              variacion={antier !== null ? variacion(datos.ayer.total, antier, 'vs antier') : undefined} data-testid="cifra-ayer" />
            <KpiCard etiqueta="Últimos 7 días" valor={formatCurrency(datos.semana.total)} detalle={ventas(datos.semana.tickets)}
              variacion={semanaAnterior !== null ? variacion(datos.semana.total, semanaAnterior, 'vs semana anterior') : undefined} data-testid="cifra-semana" />
            {conUtilidad && (
              <KpiCard etiqueta="Utilidad bruta de hoy" valor={formatCurrency(datos.utilidad_bruta_hoy as number)}
                detalle={sinCosto > 0 ? `sobre ${formatCurrency(conCosto)} con costo · ${formatCurrency(sinCosto)} vendidos sin costo` : 'sobre lo que tiene costo'}
                variacion={datos.utilidad_bruta_ayer != null ? variacion(datos.utilidad_bruta_hoy as number, datos.utilidad_bruta_ayer, 'vs ayer') : undefined}
                data-testid="cifra-utilidad" />
            )}
          </div>

          {conGraficas ? (
            <>
              {/* 2 · Tendencia (8) · Cómo te pagaron (4) */}
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
                <DaxCard className="lg:col-span-8">
                  <Titulo enlace={{ a: '/hq/reports-hub', texto: 'Ver reportes →' }}>Cómo van los últimos 7 días</Titulo>
                  <Grafica seccion="tendencia" datos={datos} />
                </DaxCard>
                <DaxCard className="lg:col-span-4">
                  <Titulo enlace={{ a: ENLACES.completo.ventas, texto: 'Ver ventas →' }}>Cómo te pagaron hoy</Titulo>
                  {metodos.length === 0 ? (
                    <Vacio>Sin cobros hoy.</Vacio>
                  ) : (
                    <div className="space-y-3">
                      <Grafica seccion="metodos" datos={datos} />
                      <ListaMetodos datos={datos} metodos={metodos} />
                    </div>
                  )}
                </DaxCard>
              </div>
              {/* 3 · Ventas por hora (8) · Caja (4) */}
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
                <DaxCard className="lg:col-span-8">
                  <Titulo>A qué hora vendiste hoy</Titulo>
                  {datos.hoy.tickets === 0 && devueltoHoy === 0 ? <Vacio>Sin ventas hoy.</Vacio> : <Grafica seccion="horas" datos={datos} />}
                </DaxCard>
                <DaxCard className="lg:col-span-4">
                  <Titulo enlace={{ a: '/cash-history', texto: 'Ver corte →' }}>Caja</Titulo>
                  <Corte corte={datos.corte} />
                </DaxCard>
              </div>
            </>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
              <DaxCard>
                <Titulo enlace={{ a: basico ? ENLACES.basico.ventas : ENLACES.completo.ventas, texto: 'Ver ventas →' }}>Cómo te pagaron hoy</Titulo>
                {metodos.length === 0 ? <Vacio>Sin cobros hoy.</Vacio> : <ListaMetodos datos={datos} metodos={metodos} />}
              </DaxCard>
              <DaxCard>
                <Titulo enlace={{ a: '/cash-history', texto: 'Ver corte →' }}>Caja</Titulo>
                <Corte corte={datos.corte} />
              </DaxCard>
            </div>
          )}

          {/* 4 · Pendientes */}
          {datos.pendientes && <Pendientes datos={datos.pendientes} esTelefono={esTelefono} />}

          {/* 5 · Se está acabando · Lo que más se vendió */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            <SeAcaba datos={datos} esTelefono={esTelefono} basico={basico} />
            <MasVendido datos={datos} esTelefono={esTelefono} />
          </div>

          {/* 6 · No se mueve */}
          {datos.sin_movimiento && <NoSeMueve datos={datos.sin_movimiento} esTelefono={esTelefono} />}

          {/* 7 · Sucursales: barras (solo con gráficas) + tarjetas */}
          {datos.sucursales && (
            <Sucursales lista={datos.sucursales} grafica={conGraficas ? <Grafica seccion="sucursales" datos={datos} /> : null} />
          )}
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

- [ ] **Step 3: `ValorTiendaCard` con tokens**

Sustituir `frontend/src/components/reports/ValorTiendaCard.tsx` entero por (misma lógica, mismos `data-testid`; solo cambian las clases de color):

```tsx
import { Link } from 'react-router-dom'
import { formatCurrency } from '../../utils/currency'

/**
 * ValorTiendaCard — "¿cuánto vale mi tienda hoy?" en el inicio del dueño.
 *
 * Dos cifras que SIEMPRE van juntas: valor a precio de venta (completo) y
 * valor a costo (solo SKUs con costo > 0). Si hay piezas sin costo, el costo
 * está incompleto: la cifra grande es la de venta y el costo baja a
 * secundaria con el aviso "N piezas sin costo", para que un catálogo
 * importado sin costos nunca se lea como "mi tienda vale $0". Con el costo
 * completo, la cifra grande es el costo (lo invertido) y la venta queda al
 * lado. `valorCosto === null` = el rol no ve costos (gerente): venta y piezas.
 * Solo tokens `dax-*` (Fase 2, spec 2026-10-23 §3.4).
 */
export interface ValorTiendaCardProps {
  valorVenta: number
  valorCosto: number | null
  piezas: number
  piezasSinCosto: number
  skusSinCosto: number
  cargando?: boolean
  error?: string | null
}

const piezasTxt = (n: number) => {
  const r = Math.round(n)
  return `${r.toLocaleString('es-MX')} ${r === 1 ? 'pieza' : 'piezas'}`
}

export function ValorTiendaCard({
  valorVenta, valorCosto, piezas, piezasSinCosto, skusSinCosto, cargando = false, error = null,
}: ValorTiendaCardProps) {
  const costoIncompleto = piezasSinCosto > 0
  const costoPrincipal = valorCosto !== null && !costoIncompleto
  const principal = costoPrincipal ? (valorCosto as number) : valorVenta
  const etiquetaPrincipal = costoPrincipal ? 'Valor a costo' : 'Valor a precio de venta'

  return (
    <section
      className="dax-card p-5 rounded-2xl border-t-2 border-t-dax-accent relative overflow-hidden"
      aria-label="Valor de la tienda"
      data-testid="valor-tienda"
    >
      <div className="flex justify-between items-start gap-2 mb-1">
        <p className="dax-section-title">Valor de la tienda</p>
        <Link to="/hq/valor-inventario" className="text-[10px] font-bold text-dax-accent-text hover:underline whitespace-nowrap max-md:inline-flex max-md:items-center max-md:min-h-[44px]">
          Ver desglose →
        </Link>
      </div>
      {error ? (
        <p className="text-sm text-dax-danger">{error}</p>
      ) : cargando ? (
        <p className="text-sm text-dax-faint">Calculando…</p>
      ) : (
        <>
          <p className="dax-kpi-label">{etiquetaPrincipal}</p>
          <h2 className="text-2xl md:text-3xl font-bold text-dax-text tabular-nums" data-testid="valor-principal">
            {formatCurrency(principal)}
          </h2>
          <div className="mt-1 flex flex-wrap justify-between gap-x-3 gap-y-1 text-xs font-mono">
            <span className="text-dax-muted">{piezasTxt(piezas)}</span>
            {valorCosto !== null && !costoPrincipal && (
              <span className="text-dax-muted">
                A costo: <span className="text-dax-text font-bold tabular-nums" data-testid="valor-costo">{formatCurrency(valorCosto)}</span>
              </span>
            )}
            {costoPrincipal && (
              <span className="text-dax-muted">
                A venta: <span className="text-dax-text font-bold tabular-nums" data-testid="valor-venta">{formatCurrency(valorVenta)}</span>
              </span>
            )}
          </div>
          {costoIncompleto && valorCosto !== null && (
            <p className="mt-1 text-[10px] font-bold text-dax-warning" role="status">
              {piezasTxt(piezasSinCosto)} sin costo ({skusSinCosto} {skusSinCosto === 1 ? 'SKU' : 'SKUs'}): el valor a costo está incompleto.
            </p>
          )}
        </>
      )}
    </section>
  )
}

export default ValorTiendaCard
```

- [ ] **Step 4: Correr**

Run: `cd frontend && npx vitest run src/pages/hq src/components/reports src/__tests__/modoBasico.test.ts src/pages/__tests__ --reporter=dot && npx tsc --noEmit -p tsconfig.json`
Expected: verde (`responsivoOla2` sigue viendo `useEsTelefono()`, `<CabeceraPagina` y `<TarjetaFila` en `hq/Inicio.tsx`, y ninguna `grid-cols-12` sin prefijo; `hqSinEstilosInline` no encuentra `style={{`); tsc limpio.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/hq/Inicio.tsx frontend/src/pages/hq/__tests__/Inicio.test.tsx frontend/src/components/reports/ValorTiendaCard.tsx frontend/src/__tests__/modoBasico.test.ts
git commit -m "feat(inicio): cifras con variación, rejilla de 12 con las cuatro gráficas perezosas y tokens dax-*

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf"
```

---

### Task 7: Presets de Reportes y `Heatmap` repintado con tokens

**Files:**
- Create: `frontend/src/pages/reports/presetsReportes.ts`
- Modify: `frontend/src/components/reports/Heatmap.tsx` (reescritura; mismas exportaciones `SalesHeatmap`, `HeatmapCell`)
- Test: `frontend/src/pages/reports/__tests__/presetsReportes.test.ts`, `frontend/src/components/reports/__tests__/Heatmap.test.tsx`

**Interfaces:**
- Consumes: `todayStr`, `daysAgoStr` de `utils/dates.ts`; `formatCurrency`.
- Produces (`presetsReportes.ts`): `type ClavePreset = 'hoy'|'ayer'|'7d'|'30d'|'mes'`; `interface Rango { inicio: string; fin: string }` (`YYYY-MM-DD`, inclusive); `PRESETS: { clave; etiqueta }[]` en el orden `Hoy · Ayer · 7 días · 30 días · Este mes`; `rangoPreset(clave): Rango`; `presetActivo(r): ClavePreset | null`; `fechasDelRango(r): string[]`; `diasDelRango(r): number`; `etiquetaDia(iso): string` («vie 23»); `etiquetaRango(r): string` («17 oct – 23 oct»); `etiquetasTendencia(r, puntos, respaldo): string[]`.
- Produces (`Heatmap.tsx`): `SalesHeatmap({ data: HeatmapCell[]; hourStart?: number; hourEnd?: number })` (defaults 9 y 21), celdas con `data-testid="celda-<day>-<hour>"` y `data-intensidad="0|20|40|60|80|100"`; `escalon(ratio): 0..5`; `INTENSIDAD = [0, 20, 40, 60, 80, 100]`.

**Decisiones:** los presets se calculan en el navegador con la fecha local (como hoy) y replican `metricas_ventas.periodo_preset` (7d = hoy y 6 anteriores; 30d = hoy y 29; mes = del 1 a hoy). Las etiquetas de la tendencia se arman del rango en español (`etiquetaDia`) porque el backend las manda en inglés (`strftime("%a %d")`); si el servidor devuelve otra cantidad de puntos, se usan las suyas. La intensidad del heatmap es `color-mix(in srgb, var(--dax-success) N%, transparent)` en línea (cinco escalones): Tailwind no admite `/20` sobre un color definido con `var()` y `components/` no está bajo `hqSinEstilosInline`.

- [ ] **Step 1: Pruebas que fallan — presets**

Crear `frontend/src/pages/reports/__tests__/presetsReportes.test.ts`:

```ts
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import {
  PRESETS, diasDelRango, etiquetaRango, etiquetasTendencia, fechasDelRango, presetActivo, rangoPreset,
} from '../presetsReportes'

// 23 de octubre de 2026 (viernes), mediodía local.
beforeEach(() => { vi.useFakeTimers(); vi.setSystemTime(new Date(2026, 9, 23, 12)) })
afterEach(() => vi.useRealTimers())

describe('rangoPreset (mismos tramos que metricas_ventas.periodo_preset)', () => {
  it('hoy, ayer, 7 días, 30 días y este mes', () => {
    expect(rangoPreset('hoy')).toEqual({ inicio: '2026-10-23', fin: '2026-10-23' })
    expect(rangoPreset('ayer')).toEqual({ inicio: '2026-10-22', fin: '2026-10-22' })
    expect(rangoPreset('7d')).toEqual({ inicio: '2026-10-17', fin: '2026-10-23' })
    expect(rangoPreset('30d')).toEqual({ inicio: '2026-09-24', fin: '2026-10-23' })
    expect(rangoPreset('mes')).toEqual({ inicio: '2026-10-01', fin: '2026-10-23' })
  })
  it('la barra va en el orden de la spec', () => {
    expect(PRESETS.map((p) => p.etiqueta)).toEqual(['Hoy', 'Ayer', '7 días', '30 días', 'Este mes'])
  })
})

describe('presetActivo', () => {
  it('reconoce el preset del rango y null para uno a mano', () => {
    expect(presetActivo(rangoPreset('mes'))).toBe('mes')
    expect(presetActivo({ inicio: '2026-10-17', fin: '2026-10-23' })).toBe('7d')
    expect(presetActivo({ inicio: '2026-10-10', fin: '2026-10-23' })).toBeNull()
  })
})

describe('fechas del rango', () => {
  it('fechasDelRango enumera cada día y diasDelRango las cuenta', () => {
    const f = fechasDelRango(rangoPreset('7d'))
    expect(f).toHaveLength(7)
    expect(f[0]).toBe('2026-10-17')
    expect(f[6]).toBe('2026-10-23')
    expect(diasDelRango(rangoPreset('hoy'))).toBe(1)
    expect(diasDelRango(rangoPreset('30d'))).toBe(30)
  })
  it('etiquetaRango: un día solo o "desde – hasta"', () => {
    expect(etiquetaRango(rangoPreset('hoy'))).toMatch(/23.*oct/)
    expect(etiquetaRango(rangoPreset('7d'))).toMatch(/17.*oct.* – .*23.*oct/)
  })
  it('etiquetasTendencia usa las fechas del rango en español cuando cuadran y las del servidor si no', () => {
    const e = etiquetasTendencia(rangoPreset('7d'), 7, ['Sat 17', 'Sun 18', 'Mon 19', 'Tue 20', 'Wed 21', 'Thu 22', 'Fri 23'])
    expect(e).toHaveLength(7)
    expect(e[0]).toMatch(/sáb.*17/)
    expect(e[6]).toMatch(/vie.*23/)
    expect(etiquetasTendencia(rangoPreset('7d'), 5, ['a', 'b', 'c', 'd', 'e'])).toEqual(['a', 'b', 'c', 'd', 'e'])
  })
})
```

Run: `cd frontend && npx vitest run src/pages/reports/__tests__/presetsReportes.test.ts --reporter=dot`
Expected: falla (módulo inexistente).

- [ ] **Step 2: `presetsReportes.ts`**

Crear `frontend/src/pages/reports/presetsReportes.ts`:

```ts
// frontend/src/pages/reports/presetsReportes.ts
import { daysAgoStr, todayStr } from '../../utils/dates'

/**
 * Periodos de Reportes (spec 2026-10-23 §3.2). Replican
 * `metricas_ventas.periodo_preset`: `7d` = hoy y 6 anteriores, `30d` = hoy y
 * 29, `mes` = del 1 a hoy. El comparativo lo calcula el backend
 * (`Periodo.anterior()`: mismo largo, termina el día antes del inicio).
 * Fechas `YYYY-MM-DD` locales (como `todayStr`), inclusivas.
 */
export type ClavePreset = 'hoy' | 'ayer' | '7d' | '30d' | 'mes'
export interface Rango { inicio: string; fin: string }

export const PRESETS: { clave: ClavePreset; etiqueta: string }[] = [
  { clave: 'hoy', etiqueta: 'Hoy' },
  { clave: 'ayer', etiqueta: 'Ayer' },
  { clave: '7d', etiqueta: '7 días' },
  { clave: '30d', etiqueta: '30 días' },
  { clave: 'mes', etiqueta: 'Este mes' },
]

export function rangoPreset(clave: ClavePreset): Rango {
  const hoy = todayStr()
  switch (clave) {
    case 'hoy': return { inicio: hoy, fin: hoy }
    case 'ayer': return { inicio: daysAgoStr(1), fin: daysAgoStr(1) }
    case '7d': return { inicio: daysAgoStr(6), fin: hoy }
    case '30d': return { inicio: daysAgoStr(29), fin: hoy }
    case 'mes': return { inicio: `${hoy.slice(0, 8)}01`, fin: hoy }
  }
}

/** Qué botón de la barra corresponde al rango; null si lo escribió a mano. */
export function presetActivo(r: Rango): ClavePreset | null {
  for (const p of PRESETS) {
    const x = rangoPreset(p.clave)
    if (x.inicio === r.inicio && x.fin === r.fin) return p.clave
  }
  return null
}

/** A mediodía local para que la zona horaria no mueva el día. */
const aFecha = (iso: string) => new Date(`${iso}T12:00:00`)
const aIso = (d: Date) => d.toLocaleDateString('en-CA')

export function fechasDelRango(r: Rango): string[] {
  const salida: string[] = []
  const d = aFecha(r.inicio)
  while (aIso(d) <= r.fin && salida.length < 400) {
    salida.push(aIso(d))
    d.setDate(d.getDate() + 1)
  }
  return salida
}

export const diasDelRango = (r: Rango): number => fechasDelRango(r).length

/** "vie 23" */
export const etiquetaDia = (iso: string): string =>
  aFecha(iso).toLocaleDateString('es-MX', { weekday: 'short', day: 'numeric' })

const diaMes = (iso: string) => aFecha(iso).toLocaleDateString('es-MX', { day: 'numeric', month: 'short' })

/** "23 oct" o "17 oct – 23 oct". */
export const etiquetaRango = (r: Rango): string =>
  r.inicio === r.fin ? diaMes(r.inicio) : `${diaMes(r.inicio)} – ${diaMes(r.fin)}`

/**
 * Etiquetas de la tendencia: las fechas del rango en español (el backend las
 * manda en inglés, `strftime("%a %d")`). Si el servidor devolvió otra cantidad
 * de puntos, se usan las suyas para no desalinear la gráfica.
 */
export function etiquetasTendencia(r: Rango, puntos: number, respaldo: string[]): string[] {
  const fechas = fechasDelRango(r)
  return fechas.length === puntos ? fechas.map(etiquetaDia) : respaldo
}
```

Run: `cd frontend && npx vitest run src/pages/reports/__tests__/presetsReportes.test.ts --reporter=dot`
Expected: verde.

- [ ] **Step 3: Prueba que falla — Heatmap**

Crear `frontend/src/components/reports/__tests__/Heatmap.test.tsx`:

```tsx
// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup, fireEvent } from '@testing-library/react'
import { SalesHeatmap, escalon } from '../Heatmap'

afterEach(cleanup)

const DATA = [
  { day: 1, hour: 12, amount: 1000, tickets: 4 },   // lunes 12:00, el máximo
  { day: 5, hour: 18, amount: 300, tickets: 1 },    // viernes 18:00, 30 %
]

describe('SalesHeatmap', () => {
  it('siete filas con el lunes arriba y la ventana de horas pedida', () => {
    const { container } = render(<SalesHeatmap data={DATA} hourStart={10} hourEnd={20} />)
    const filas = container.querySelectorAll('tbody tr')
    expect(filas).toHaveLength(7)
    expect(filas[0].querySelector('td')?.textContent).toBe('L')
    expect(filas[6].querySelector('td')?.textContent).toBe('D')
    expect(container.querySelectorAll('thead th')).toHaveLength(12)   // 1 vacío + 10..20
  })

  it('la intensidad es el dato: 100 % el máximo, 40 % para 0.3 del máximo, 0 sin venta', () => {
    render(<SalesHeatmap data={DATA} />)
    expect(screen.getByTestId('celda-1-12').getAttribute('data-intensidad')).toBe('100')
    expect(screen.getByTestId('celda-5-18').getAttribute('data-intensidad')).toBe('40')
    const vacia = screen.getByTestId('celda-2-12')
    expect(vacia.getAttribute('data-intensidad')).toBe('0')
    expect(vacia.className).toContain('bg-dax-elevated')
    expect(screen.getByTestId('celda-1-12').getAttribute('style')).toContain('--dax-success')
  })

  it('escalon reparte en cinco pasos', () => {
    expect([0, 0.1, 0.3, 0.5, 0.7, 1].map(escalon)).toEqual([0, 1, 2, 3, 4, 5])
  })

  it('al pasar el ratón enseña día, hora, importe y tickets', () => {
    render(<SalesHeatmap data={DATA} />)
    fireEvent.mouseEnter(screen.getByTestId('celda-1-12'))
    const tip = screen.getByRole('tooltip')
    expect(tip.textContent).toContain('Lunes · 12:00')
    expect(tip.textContent).toContain('$1,000.00')
    expect(tip.textContent).toContain('4 tickets')
    fireEvent.mouseLeave(screen.getByTestId('celda-1-12'))
    expect(screen.queryByRole('tooltip')).toBeNull()
  })

  it('no usa colores fijos (slate/emerald/hex)', () => {
    const { container } = render(<SalesHeatmap data={DATA} />)
    expect(container.innerHTML).not.toMatch(/slate-|emerald-|#[0-9a-f]{6}/i)
  })
})
```

Run: `cd frontend && npx vitest run src/components/reports/__tests__/Heatmap.test.tsx --reporter=dot`
Expected: falla (no exporta `escalon`, celdas sin `data-testid`, clases `slate`/`emerald`).

- [ ] **Step 4: Reescribir `Heatmap.tsx`**

Sustituir `frontend/src/components/reports/Heatmap.tsx` entero por:

```tsx
import { useMemo, useState } from 'react'
import { formatCurrency } from '../../utils/currency'

/**
 * SalesHeatmap — rejilla día de la semana × hora (spec 2026-10-23 §3.2),
 * pintada con el verde del tema: la intensidad es `amount / max` en cinco
 * escalones de `color-mix(var(--dax-success) N%)`, así se repinta sola en
 * claro y oscuro. Convención de PostgreSQL: day 0 = domingo … 6 = sábado;
 * aquí el lunes va arriba. La ventana de horas la decide quien llama
 * (`recortarHoras` del kit); por defecto 9..21.
 */
export interface HeatmapCell {
  day: number   // 0..6 (0 = domingo)
  hour: number  // 0..23
  amount: number
  tickets: number
}

interface Props {
  data: HeatmapCell[]
  hourStart?: number
  hourEnd?: number
}

const WEEK_ORDER_PG = [1, 2, 3, 4, 5, 6, 0]
const WEEK_LABELS = ['L', 'M', 'X', 'J', 'V', 'S', 'D']
const WEEK_LONG = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']

/** Porcentaje del verde del tema por escalón (0 = sin venta). */
export const INTENSIDAD = [0, 20, 40, 60, 80, 100]

export function escalon(ratio: number): number {
  if (!(ratio > 0)) return 0
  if (ratio < 0.2) return 1
  if (ratio < 0.4) return 2
  if (ratio < 0.6) return 3
  if (ratio < 0.8) return 4
  return 5
}

const fondo = (pct: number) => `color-mix(in srgb, var(--dax-success) ${pct}%, transparent)`

export function SalesHeatmap({ data, hourStart = 9, hourEnd = 21 }: Props) {
  const hours = useMemo(
    () => Array.from({ length: Math.max(0, hourEnd - hourStart + 1) }, (_, i) => hourStart + i),
    [hourStart, hourEnd],
  )

  const { cells, maxAmount } = useMemo(() => {
    const map = new Map<string, HeatmapCell>()
    let max = 0
    for (const c of data) {
      map.set(`${c.day}-${c.hour}`, c)
      if (c.amount > max) max = c.amount
    }
    return { cells: map, maxAmount: max }
  }, [data])

  const [hover, setHover] = useState<{ dayIdx: number; hour: number; amount: number; tickets: number } | null>(null)

  return (
    <div className="relative">
      <div className="overflow-x-auto">
        <table className="w-full border-separate" style={{ borderSpacing: '3px' }}>
          <thead>
            <tr>
              <th className="w-6" />
              {hours.map((h) => (
                <th key={h} className="text-[9px] font-mono font-bold text-dax-faint text-center">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {WEEK_ORDER_PG.map((pgDay, rowIdx) => (
              <tr key={pgDay}>
                <td className="text-[10px] font-bold text-dax-muted pr-1 w-6 text-right align-middle">{WEEK_LABELS[rowIdx]}</td>
                {hours.map((h) => {
                  const c = cells.get(`${pgDay}-${h}`)
                  const amt = c?.amount ?? 0
                  const pct = INTENSIDAD[escalon(maxAmount > 0 ? amt / maxAmount : 0)]
                  return (
                    <td
                      key={`${pgDay}-${h}`}
                      data-testid={`celda-${pgDay}-${h}`}
                      data-intensidad={pct}
                      className={`relative h-6 rounded-sm cursor-pointer transition-all duration-200 hover:ring-2 hover:ring-dax-accent ${pct === 0 ? 'bg-dax-elevated' : ''}`}
                      style={pct > 0 ? { background: fondo(pct) } : undefined} /* estilo dinámico: la intensidad es el dato */
                      onMouseEnter={() => setHover({ dayIdx: rowIdx, hour: h, amount: amt, tickets: c?.tickets ?? 0 })}
                      onMouseLeave={() => setHover(null)}
                    />
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-3 flex items-center justify-end gap-1.5">
        <span className="text-[9px] font-bold uppercase tracking-wider text-dax-faint">Menos</span>
        {INTENSIDAD.map((pct) => (
          <div key={pct} className={`h-2 w-4 rounded-sm ${pct === 0 ? 'bg-dax-elevated' : ''}`}
            style={pct > 0 ? { background: fondo(pct) } : undefined} /* estilo dinámico: la leyenda repite los escalones */ />
        ))}
        <span className="text-[9px] font-bold uppercase tracking-wider text-dax-faint">Más</span>
      </div>

      {hover && (
        <div role="tooltip" className="pointer-events-none absolute top-0 right-0 bg-dax-card border border-dax-border rounded-lg px-3 py-2 shadow-lg z-10">
          <p className="text-[10px] font-bold uppercase tracking-wider text-dax-success">
            {WEEK_LONG[hover.dayIdx]} · {hover.hour}:00
          </p>
          <p className="text-sm font-black tabular-nums text-dax-text">{formatCurrency(hover.amount)}</p>
          <p className="text-[10px] text-dax-muted">{hover.tickets} {hover.tickets === 1 ? 'ticket' : 'tickets'}</p>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 5: Correr**

Run: `cd frontend && npx vitest run src/components/reports src/pages/reports --reporter=dot && npx tsc --noEmit -p tsconfig.json`
Expected: verde; tsc limpio. (`HQReportsHub.tsx` sigue importando `SalesHeatmap` con las mismas props: compila hasta que la Tarea 9 lo borre.)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/reports/presetsReportes.ts frontend/src/pages/reports/__tests__/presetsReportes.test.ts frontend/src/components/reports/Heatmap.tsx frontend/src/components/reports/__tests__/Heatmap.test.tsx
git commit -m "feat(reportes): presets del periodo y Heatmap repintado con tokens del tema

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf"
```

---

### Task 8: `pages/reports/Reportes.tsx` — una pantalla de Reportes para todos

**Files:**
- Create: `frontend/src/pages/reports/Reportes.tsx`
- Test: `frontend/src/pages/reports/__tests__/Reportes.test.tsx`

**Interfaces:**
- Consumes: `reportsApi.dashboard({ start_date, end_date, branch_id? })`, `reportsApi.commandCenterStats({ start_date, end_date })`, `reportsApi.exportCsv({ start_date, end_date, branch_id? })`, `organizationApi.getBranches()` (`Branch.is_active`, `name`, `id`); tipos `DashboardData` (Tareas 2 y 5), `CommandCenterStats.branches[].{id, name, total_sales, is_hq}`; kit (Tarea 3), `KpiCard`/`variacion` (Tarea 4), `SalesHeatmap` y `presetsReportes` (Tarea 7); `CabeceraPagina`, `BarraFiltros`, `ParFechas`, `DaxCard`, `ListaTarjetas`, `TarjetaFila`, `Spinner`, `useEsTelefono`, `errorDetailText`.
- Produces: `export function Reportes({ conSucursales?: boolean })`. `App.tsx` (Tarea 9) monta `<Reportes conSucursales />` en `/hq/reports-hub` y `<Reportes />` en `/reports`. `data-testid`: `kpi-venta`, `kpi-tickets`, `kpi-promedio`, `kpi-devoluciones`, `kpi-utilidad`, `metodo`, `sucursales`, `top`.

**Decisiones:**
- Preset inicial **7 días** (el hoy vive en el Inicio; Reportes es periodos y comparativos).
- `branch_id` solo viaja con selector y sucursal elegida; omitido = toda la organización para roles de oficina (Fase 1) y la sucursal propia para cajera/gerente (el backend la impone).
- `/reports/command-center/stats` (toda la org, sin guardia de rol) solo se pide con `conSucursales`; la sección Sucursales aparece con ≥ 2 sucursales con venta o que venden (se excluye la HQ sin venta); el selector, con ≥ 2 sucursales activas.
- Ventas por hora = total de la hora en el periodo ÷ días naturales del rango («Promedio por hora en N días»; con un día, la etiqueta del día).
- Utilidad bruta visible solo si `gross_profit != null` y `gross_sales − sales_without_cost > 0`.
- Rango escrito a mano con fin < inicio: se avisa y no se llama al servidor.
- La variación de Devoluciones es `invertida` (subir es malo).

- [ ] **Step 1: Prueba que falla**

Crear `frontend/src/pages/reports/__tests__/Reportes.test.tsx`:

```tsx
// frontend/src/pages/reports/__tests__/Reportes.test.tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, cleanup, fireEvent, waitFor, within } from '@testing-library/react'

const { dashboard, commandCenterStats, exportCsv, getBranches } = vi.hoisted(() => ({
  dashboard: vi.fn(), commandCenterStats: vi.fn(), exportCsv: vi.fn(), getBranches: vi.fn(),
}))
vi.mock('../../../api/reports', () => ({ reportsApi: { dashboard, commandCenterStats, exportCsv } }))
vi.mock('../../../api/organization', () => ({ organizationApi: { getBranches } }))
// jsdom no tiene canvas: el kit se sustituye por stubs que exponen las series. El dibujo lo prueba el kit.
vi.mock('../../../components/graficas', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../components/graficas')>()),
  GraficaLinea: (p: { etiquetas: string[]; series: { nombre: string }[] }) => (
    <div data-testid="grafica-linea" data-etiquetas={p.etiquetas.join('|')} data-series={p.series.map((s) => s.nombre).join('|')} />
  ),
  GraficaBarras: (p: { etiquetas: string[]; valores: number[]; horizontal?: boolean }) => (
    <div data-testid={p.horizontal ? 'grafica-barras-h' : 'grafica-barras'} data-etiquetas={p.etiquetas.join('|')}
      data-valores={p.valores.map((v) => Math.round(v)).join('|')} />
  ),
  GraficaDona: (p: { partes: { nombre: string; valor: number }[] }) => (
    <div data-testid="grafica-dona" data-partes={p.partes.map((x) => `${x.nombre}=${x.valor}`).join('|')} />
  ),
}))

import { Reportes } from '../Reportes'
import { rangoPreset } from '../presetsReportes'

const r7 = rangoPreset('7d')
const DASH = {
  kpis: {
    sales: 9000, gross_sales: 9400, returns: 400, returns_count: 2, orders: 70, avg_ticket: 128.57, pending: 0, draft: 0,
    total_products: 10, transit_shipments: 0, prev_sales: 7500, prev_orders: 60, prev_avg_ticket: 125, prev_returns: 100,
    gross_profit: 3000, prev_gross_profit: 2000, sales_without_cost: 400,
  },
  charts: {
    trend: { labels: ['a', 'b', 'c', 'd', 'e', 'f', 'g'], data: [1, 2, 3, 4, 5, 6, 7] },
    trend_previous: { labels: ['a', 'b', 'c', 'd', 'e', 'f', 'g'], data: [1, 1, 1, 1, 1, 1, 1] },
    hourly: { labels: Array.from({ length: 24 }, (_, h) => `${h}:00`), data: Array.from({ length: 24 }, (_, h) => (h === 12 ? 7000 : 0)) },
    payments: { CARD: { total: 4000, count: 30 }, CASH: { total: 5000, count: 40 } },
    heatmap: [{ day: 1, hour: 12, amount: 500, tickets: 3 }],
  },
  top_products: [{ name: 'Blusa roja', qty: 14, total: 1400, trend: [] }, { name: 'Falda', qty: 7, total: 700, trend: [] }],
  low_stock: [], recent_sales: [],
}
const sucursalCc = (id: number, name: string, total_sales: number, is_hq = false) =>
  ({ id, name, status: 'ONLINE', total_sales, pending_cuts: 0, pending_users: [], critical_stock: 0, is_hq })
const CC = {
  global: { total_sales: 9000, total_tickets: 70, ticket_average: 128.57, items_per_ticket: 1, canceled_tickets: 0, overrides_total: 0, returns_total: 400, sales_growth: 20 },
  payment_methods: {}, hourly_distribution: [], alerts: [], top_products: [],
  branches: [sucursalCc(1, 'Roma', 6000), sucursalCc(2, 'Condesa', 3000), sucursalCc(9, 'Bodega', 0, true)],
}
const SUC = (id: number, name: string) => ({ id, name, branch_type: 'STORE', address: null, phone: null, is_headquarters: false, is_active: true, can_sell: true })
const variacionDe = (testId: string) => within(screen.getByTestId(testId)).queryByTestId('variacion')
const espera = () => new Promise((r) => setTimeout(r, 20))

beforeEach(() => {
  dashboard.mockReset().mockResolvedValue(DASH)
  commandCenterStats.mockReset().mockResolvedValue(CC)
  exportCsv.mockReset().mockResolvedValue(undefined)
  getBranches.mockReset().mockResolvedValue([SUC(1, 'Roma'), SUC(2, 'Condesa')])
})
afterEach(cleanup)

describe('Reportes', () => {
  it('arranca en 7 días y pide ese rango al dashboard sin sucursal', async () => {
    render(<Reportes />)
    await screen.findByTestId('kpi-venta')
    expect(dashboard).toHaveBeenCalledWith({ start_date: r7.inicio, end_date: r7.fin })
    expect(screen.getByRole('button', { name: '7 días' }).getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByRole('button', { name: 'Hoy' }).getAttribute('aria-pressed')).toBe('false')
  })

  it('cifras con variación contra el periodo anterior; devoluciones al alza en rojo', async () => {
    render(<Reportes />)
    const venta = await screen.findByTestId('kpi-venta')
    expect(venta.textContent).toContain('$9,000.00')
    expect(variacionDe('kpi-venta')?.textContent).toBe('▲ 20 % vs periodo anterior')
    expect(variacionDe('kpi-tickets')?.textContent).toBe('▲ 17 % vs periodo anterior')
    expect(variacionDe('kpi-promedio')?.textContent).toBe('▲ 3 % vs periodo anterior')
    const dev = variacionDe('kpi-devoluciones')
    expect(dev?.textContent).toBe('▲ 300 % vs periodo anterior')
    expect(dev?.className).toContain('text-dax-danger')
    expect(screen.getByTestId('kpi-devoluciones').textContent).toContain('2 devoluciones')
  })

  it('utilidad bruta con el detalle de lo que tiene costo', async () => {
    render(<Reportes />)
    const u = await screen.findByTestId('kpi-utilidad')
    expect(u.textContent).toContain('$3,000.00')
    expect(u.textContent).toContain('sobre $9,000.00 con costo · $400.00 sin costo')
    expect(variacionDe('kpi-utilidad')?.textContent).toBe('▲ 50 % vs periodo anterior')
  })

  it('oculta la utilidad bruta sin costo o sin permiso', async () => {
    dashboard.mockResolvedValue({ ...DASH, kpis: { ...DASH.kpis, gross_profit: null, prev_gross_profit: null, sales_without_cost: null } })
    render(<Reportes />)
    await screen.findByTestId('kpi-venta')
    expect(screen.queryByTestId('kpi-utilidad')).toBeNull()
    cleanup()
    dashboard.mockResolvedValue({ ...DASH, kpis: { ...DASH.kpis, gross_profit: 0, sales_without_cost: 9400 } })   // nada de lo vendido tiene costo
    render(<Reportes />)
    await screen.findByTestId('kpi-venta')
    expect(screen.queryByTestId('kpi-utilidad')).toBeNull()
  })

  it('"Este mes" manda del 1 a hoy', async () => {
    render(<Reportes />)
    await screen.findByTestId('kpi-venta')
    fireEvent.click(screen.getByRole('button', { name: 'Este mes' }))
    const mes = rangoPreset('mes')
    await waitFor(() => expect(dashboard).toHaveBeenLastCalledWith({ start_date: mes.inicio, end_date: mes.fin }))
    expect(mes.inicio.endsWith('-01')).toBe(true)
  })

  it('tendencia con el periodo anterior y etiquetas en español armadas del rango', async () => {
    render(<Reportes />)
    const l = await screen.findByTestId('grafica-linea')
    expect(l.getAttribute('data-series')).toBe('Este periodo|Periodo anterior')
    const etiquetas = l.getAttribute('data-etiquetas')?.split('|') ?? []
    expect(etiquetas).toHaveLength(7)
    expect(etiquetas).not.toEqual(['a', 'b', 'c', 'd', 'e', 'f', 'g'])
  })

  it('ventas por hora promedia por día del periodo y recorta la ventana', async () => {
    render(<Reportes />)
    const b = await screen.findByTestId('grafica-barras')
    const etiquetas = b.getAttribute('data-etiquetas')?.split('|') ?? []
    const valores = b.getAttribute('data-valores')?.split('|') ?? []
    expect(etiquetas[0]).toBe('9:00')
    expect(etiquetas[etiquetas.length - 1]).toBe('21:00')
    expect(valores[etiquetas.indexOf('12:00')]).toBe('1000')   // 7000 / 7 días
    expect(screen.getByText('Promedio por hora en 7 días')).toBeTruthy()
  })

  it('métodos: efectivo primero con sus cobros, y la dona con las partes', async () => {
    render(<Reportes />)
    const dona = await screen.findByTestId('grafica-dona')
    expect(dona.getAttribute('data-partes')).toBe('Efectivo=5000|Tarjeta=4000')
    const metodos = screen.getAllByTestId('metodo').map((li) => li.textContent)
    expect(metodos[0]).toContain('Efectivo')
    expect(metodos[0]).toContain('40 cobros')
    expect(metodos[0]).toContain('$5,000.00')
  })

  it('lo más vendido: producto, piezas e importe', async () => {
    render(<Reportes />)
    const top = await screen.findByTestId('top')
    expect(top.textContent).toContain('Blusa roja')
    expect(top.textContent).toContain('14 piezas')
    expect(top.textContent).toContain('$1,400.00')
  })

  it('con selector y dos sucursales: selector, sección sin la bodega, y filtra al elegir', async () => {
    render(<Reportes conSucursales />)
    await screen.findByTestId('kpi-venta')
    expect(commandCenterStats).toHaveBeenCalledWith({ start_date: r7.inicio, end_date: r7.fin })
    const selector = await screen.findByLabelText('Sucursal')
    const suc = await screen.findByTestId('sucursales')
    expect(within(suc).getByTestId('grafica-barras-h').getAttribute('data-etiquetas')).toBe('Roma|Condesa')
    expect(suc.textContent).not.toContain('Bodega')
    fireEvent.change(selector, { target: { value: '2' } })
    await waitFor(() => expect(dashboard).toHaveBeenLastCalledWith({ start_date: r7.inicio, end_date: r7.fin, branch_id: 2 }))
  })

  it('con selector pero una sola sucursal no hay selector ni sección', async () => {
    getBranches.mockResolvedValue([SUC(1, 'Roma')])
    commandCenterStats.mockResolvedValue({ ...CC, branches: [CC.branches[0], CC.branches[2]] })
    render(<Reportes conSucursales />)
    await screen.findByTestId('kpi-venta')
    await espera()
    expect(screen.queryByLabelText('Sucursal')).toBeNull()
    expect(screen.queryByTestId('sucursales')).toBeNull()
  })

  it('sin selector no pide sucursales ni el centro de mando', async () => {
    render(<Reportes />)
    await screen.findByTestId('kpi-venta')
    expect(getBranches).not.toHaveBeenCalled()
    expect(commandCenterStats).not.toHaveBeenCalled()
    expect(screen.queryByLabelText('Sucursal')).toBeNull()
    expect(screen.queryByTestId('sucursales')).toBeNull()
  })

  it('Exportar CSV manda el rango vigente', async () => {
    render(<Reportes />)
    await screen.findByTestId('kpi-venta')
    fireEvent.click(screen.getByRole('button', { name: /Exportar CSV/ }))
    await waitFor(() => expect(exportCsv).toHaveBeenCalledWith({ start_date: r7.inicio, end_date: r7.fin, branch_id: undefined }))
  })

  it('un rango invertido no llama al servidor y avisa', async () => {
    render(<Reportes />)
    await screen.findByTestId('kpi-venta')
    fireEvent.change(screen.getByLabelText('Desde'), { target: { value: '2026-10-20' } })
    fireEvent.change(screen.getByLabelText('Hasta'), { target: { value: '2026-10-19' } })
    fireEvent.click(screen.getByRole('button', { name: 'Aplicar' }))
    expect(screen.getByRole('alert').textContent).toContain('La fecha final no puede ser anterior a la inicial')
    expect(dashboard).toHaveBeenCalledTimes(1)
  })

  it('si el dashboard falla, enseña el detalle del servidor', async () => {
    dashboard.mockRejectedValue({ response: { data: { detail: 'end_date no puede ser anterior a start_date' } } })
    render(<Reportes />)
    expect((await screen.findByRole('alert')).textContent).toContain('end_date no puede ser anterior a start_date')
  })
})
```

Run: `cd frontend && npx vitest run src/pages/reports/__tests__/Reportes.test.tsx --reporter=dot`
Expected: falla (no existe `../Reportes`).

- [ ] **Step 2: `Reportes.tsx`**

Crear `frontend/src/pages/reports/Reportes.tsx`:

```tsx
// frontend/src/pages/reports/Reportes.tsx
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { reportsApi, type CommandCenterStats, type DashboardData } from '../../api/reports'
import { organizationApi, type Branch } from '../../api/organization'
import {
  GraficaBarras, GraficaDona, GraficaLinea, colorMetodo, etiquetaHora, recortarHoras, useTemaGrafica,
} from '../../components/graficas'
import { SalesHeatmap } from '../../components/reports/Heatmap'
import { BarraFiltros, ParFechas } from '../../components/ui/BarraFiltros'
import { CabeceraPagina } from '../../components/ui/CabeceraPagina'
import { DaxCard } from '../../components/ui/DaxCard'
import { KpiCard } from '../../components/ui/KpiCard'
import { ListaTarjetas } from '../../components/ui/ListaTarjetas'
import { Spinner } from '../../components/ui/Spinner'
import { TarjetaFila } from '../../components/ui/TarjetaFila'
import { useEsTelefono } from '../../hooks/useIsMobile'
import { formatCurrency } from '../../utils/currency'
import { errorDetailText } from '../../utils/errorDetail'
import { variacion } from '../../utils/variacion'
import {
  PRESETS, diasDelRango, etiquetaRango, etiquetasTendencia, presetActivo, rangoPreset, type Rango,
} from './presetsReportes'

/**
 * Reportes (spec 2026-10-23 §3.2): periodos y comparativos contra el periodo
 * anterior; el "hoy" vive en el Inicio. Un solo componente para todos:
 * `/hq/reports-hub` lo monta con `conSucursales` (selector, visible solo con
 * más de una sucursal) y `/reports` fijado a la sucursal del usuario (el
 * backend la impone a cajera y gerente por `resolver_ambito`). Datos:
 * `/reports/dashboard` en una llamada y, solo con selector,
 * `/reports/command-center/stats` para la comparativa de sucursales (es de
 * toda la organización y no tiene guardia de rol: una cajera no lo pide).
 * Sustituye a `finance/Reports.tsx` y `hq/HQReportsHub.tsx`; sin velocímetro,
 * conteo animado ni sondeo cada 30 s. Solo tokens `dax-*`.
 */
const METODOS: Record<string, string> = { CASH: 'Efectivo', CARD: 'Tarjeta', TRANSFER: 'Transferencia' }
const ORDEN_METODOS = ['CASH', 'CARD', 'TRANSFER']
const piezas = (n: number) => {
  const r = Math.round(n * 100) / 100
  return `${r.toLocaleString('es-MX')} ${r === 1 ? 'pieza' : 'piezas'}`
}
const plural = (n: number, uno: string, varios: string) => `${n} ${n === 1 ? uno : varios}`

/** Título de sección: la pregunta que responde y una nota a la derecha. */
function Titulo({ children, nota }: { children: ReactNode; nota?: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-2 mb-3">
      <p className="dax-section-title">{children}</p>
      {nota && <p className="text-xs text-dax-faint text-right">{nota}</p>}
    </div>
  )
}
const Vacio = ({ children }: { children: ReactNode }) => <p className="text-sm text-dax-muted">{children}</p>

export function Reportes({ conSucursales = false }: { conSucursales?: boolean }) {
  const esTelefono = useEsTelefono()
  const tema = useTemaGrafica()
  const [rango, setRango] = useState<Rango>(() => rangoPreset('7d'))
  const [desde, setDesde] = useState(rango.inicio)
  const [hasta, setHasta] = useState(rango.fin)
  const [sucursal, setSucursal] = useState<number | ''>('')
  const [sucursales, setSucursales] = useState<Branch[]>([])
  const [data, setData] = useState<DashboardData | null>(null)
  const [cc, setCc] = useState<CommandCenterStats | null>(null)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [exportando, setExportando] = useState(false)

  useEffect(() => {
    if (!conSucursales) return
    organizationApi.getBranches()
      .then((bs) => setSucursales(bs.filter((b) => b.is_active !== false)))
      .catch(() => { /* sin lista no hay selector; el reporte sigue */ })
  }, [conSucursales])

  useEffect(() => {
    let vivo = true
    setCargando(true)
    setError(null)
    const params = {
      start_date: rango.inicio, end_date: rango.fin,
      ...(conSucursales && sucursal !== '' ? { branch_id: sucursal } : {}),
    }
    const peticiones: Promise<unknown>[] = [reportsApi.dashboard(params).then((d) => { if (vivo) setData(d) })]
    if (conSucursales) {
      peticiones.push(
        reportsApi.commandCenterStats({ start_date: rango.inicio, end_date: rango.fin })
          .then((c) => { if (vivo) setCc(c) })
          .catch(() => { if (vivo) setCc(null) }),
      )
    }
    Promise.all(peticiones)
      .catch((e: any) => {
        if (!vivo) return
        setData(null)
        setError(errorDetailText(e?.response?.data?.detail, 'No se pudieron cargar los reportes. Vuelve a intentar en unos segundos.'))
      })
      .finally(() => { if (vivo) setCargando(false) })
    return () => { vivo = false }
  }, [rango, sucursal, conSucursales])

  const aplicar = (r: Rango) => { setDesde(r.inicio); setHasta(r.fin); setRango(r) }
  const aplicarFechas = () => {
    if (!desde || !hasta) return
    if (hasta < desde) { setError('La fecha final no puede ser anterior a la inicial.'); return }
    aplicar({ inicio: desde, fin: hasta })
  }
  const exportar = async () => {
    setExportando(true)
    try {
      await reportsApi.exportCsv({
        start_date: rango.inicio, end_date: rango.fin,
        branch_id: conSucursales && sucursal !== '' ? sucursal : undefined,
      })
    } catch {
      setError('No se pudo exportar el CSV.')
    } finally {
      setExportando(false)
    }
  }

  const activo = presetActivo(rango)
  const dias = diasDelRango(rango)
  const etiquetaPeriodo = etiquetaRango(rango)
  const k = data?.kpis
  // "Tiene costos": algo de lo vendido en el periodo lleva costo (spec §3.2).
  const conCosto = k ? Math.max(0, (k.gross_sales ?? k.sales) - (k.sales_without_cost ?? 0)) : 0
  const conUtilidad = k?.gross_profit != null && conCosto > 0

  const metodos = useMemo(() => {
    const crudo = data?.charts.payments ?? {}
    const claves = [...ORDEN_METODOS.filter((m) => m in crudo), ...Object.keys(crudo).filter((m) => !ORDEN_METODOS.includes(m))]
    return claves.map((m) => ({ clave: m, nombre: METODOS[m] ?? m, total: crudo[m].total, count: crudo[m].count, color: colorMetodo(m, tema) }))
  }, [data, tema])
  const totalMetodos = metodos.reduce((s, m) => s + m.total, 0)

  // Las 24 horas sumadas en el periodo; la gráfica pinta el promedio por día del rango.
  const horas = useMemo(() => (data?.charts.hourly.data ?? []).map((neta, hora) => ({ hora, neta })), [data])
  const ventana = recortarHoras(horas)
  const horasVentana = horas.slice(ventana.desde, ventana.hasta + 1)
  const sinHoras = horas.every((h) => h.neta === 0)

  const sucursalesCc = useMemo(() => {
    if (!conSucursales || !cc) return []
    return cc.branches.filter((b) => !b.is_hq || b.total_sales > 0).sort((a, b) => b.total_sales - a.total_sales)
  }, [cc, conSucursales])

  const top = data?.top_products ?? []
  const maxTop = Math.max(0, ...top.map((p) => p.total ?? 0))
  const heatmap = data?.charts.heatmap ?? []

  return (
    <div className="space-y-5">
      <CabeceraPagina
        titulo={<h1 className="text-2xl font-black text-dax-text">Reportes</h1>}
        descripcion="Periodos y comparativos contra el periodo anterior. Lo de hoy está en el Inicio."
        acciones={(
          <button type="button" onClick={exportar} disabled={exportando || cargando || !data} className="dax-btn-secondary text-xs">
            <i className={`fa-solid ${exportando ? 'fa-spinner fa-spin' : 'fa-file-arrow-down'}`} aria-hidden="true" />{' '}
            {exportando ? 'Exportando…' : 'Exportar CSV'}
          </button>
        )}
      />

      <BarraFiltros
        className="items-center"
        accion={<button type="button" onClick={aplicarFechas} className="dax-btn-primary text-xs">Aplicar</button>}
      >
        <div className="flex flex-wrap gap-1" role="group" aria-label="Periodo">
          {PRESETS.map((p) => (
            <button
              key={p.clave}
              type="button"
              onClick={() => aplicar(rangoPreset(p.clave))}
              aria-pressed={activo === p.clave}
              className={`${activo === p.clave ? 'dax-btn-primary' : 'dax-btn-secondary'} text-xs max-sm:min-h-[44px]`}
            >
              {p.etiqueta}
            </button>
          ))}
        </div>
        <ParFechas>
          <input type="date" aria-label="Desde" value={desde} onChange={(e) => setDesde(e.target.value)} className="dax-input w-36 text-xs" />
          <input type="date" aria-label="Hasta" value={hasta} onChange={(e) => setHasta(e.target.value)} className="dax-input w-36 text-xs" />
        </ParFechas>
        {conSucursales && sucursales.length > 1 && (
          <select
            aria-label="Sucursal"
            value={sucursal}
            onChange={(e) => setSucursal(e.target.value ? Number(e.target.value) : '')}
            className="dax-input text-xs max-w-[180px]"
          >
            <option value="">Todas las sucursales</option>
            {sucursales.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
        )}
      </BarraFiltros>

      {error && <p role="alert" className="text-sm text-dax-danger">{error}</p>}

      {cargando && !data ? (
        <Spinner text="Cargando reportes…" />
      ) : !data || !k ? (
        !error && <DaxCard><Vacio>Sin datos para el periodo.</Vacio></DaxCard>
      ) : (
        <>
          {/* Cifras del periodo con variación contra el anterior */}
          <div className={`grid grid-cols-1 sm:grid-cols-2 ${conUtilidad ? 'lg:grid-cols-5' : 'lg:grid-cols-4'} gap-3`}>
            <KpiCard etiqueta="Venta neta" valor={formatCurrency(k.sales)} detalle={etiquetaPeriodo}
              variacion={variacion(k.sales, k.prev_sales ?? 0, 'vs periodo anterior')} data-testid="kpi-venta" />
            <KpiCard etiqueta="Tickets" valor={String(k.orders)} detalle={plural(k.orders, 'venta', 'ventas')}
              variacion={variacion(k.orders, k.prev_orders ?? 0, 'vs periodo anterior')} data-testid="kpi-tickets" />
            <KpiCard etiqueta="Ticket promedio" valor={formatCurrency(k.avg_ticket)}
              variacion={variacion(k.avg_ticket, k.prev_avg_ticket ?? 0, 'vs periodo anterior')} data-testid="kpi-promedio" />
            <KpiCard etiqueta="Devoluciones" valor={formatCurrency(k.returns ?? 0)} detalle={plural(k.returns_count ?? 0, 'devolución', 'devoluciones')}
              variacion={variacion(k.returns ?? 0, k.prev_returns ?? 0, 'vs periodo anterior', true)} data-testid="kpi-devoluciones" />
            {conUtilidad && (
              <KpiCard etiqueta="Utilidad bruta" valor={formatCurrency(k.gross_profit as number)}
                detalle={`sobre ${formatCurrency(conCosto)} con costo${(k.sales_without_cost ?? 0) > 0 ? ` · ${formatCurrency(k.sales_without_cost as number)} sin costo` : ''}`}
                variacion={variacion(k.gross_profit as number, k.prev_gross_profit ?? 0, 'vs periodo anterior')} data-testid="kpi-utilidad" />
            )}
          </div>

          {/* Tendencia (8) · Cómo me pagaron (4) */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
            <DaxCard className="lg:col-span-8">
              <Titulo nota="El periodo anterior, en gris">¿Cómo fue cada día?</Titulo>
              {data.charts.trend.data.length === 0 ? <Vacio>Sin ventas en el periodo.</Vacio> : (
                <GraficaLinea
                  etiquetas={etiquetasTendencia(rango, data.charts.trend.data.length, data.charts.trend.labels)}
                  series={[
                    { nombre: 'Este periodo', valores: data.charts.trend.data },
                    ...(data.charts.trend_previous ? [{ nombre: 'Periodo anterior', valores: data.charts.trend_previous.data, comparativo: true }] : []),
                  ]}
                />
              )}
            </DaxCard>
            <DaxCard className="lg:col-span-4">
              <Titulo>¿Cómo me pagaron?</Titulo>
              {metodos.length === 0 ? <Vacio>Sin cobros en el periodo.</Vacio> : (
                <div className="space-y-3">
                  <GraficaDona
                    partes={metodos.map((m) => ({ nombre: m.nombre, valor: m.total, color: m.color }))}
                    alto={200}
                    centro={(
                      <>
                        <span className="dax-kpi-label">Total</span>
                        <span className="text-base font-black tabular-nums text-dax-text">{formatCurrency(totalMetodos)}</span>
                      </>
                    )}
                  />
                  <ul className="space-y-1">
                    {metodos.map((m) => (
                      <li key={m.clave} data-testid="metodo" className="flex justify-between text-sm">
                        <span className="text-dax-muted">{m.nombre} <span className="text-dax-faint">· {plural(m.count, 'cobro', 'cobros')}</span></span>
                        <span className="font-bold tabular-nums text-dax-text">{formatCurrency(m.total)}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </DaxCard>
          </div>

          {/* Ventas por hora (5) · Día y hora (7) */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
            <DaxCard className="lg:col-span-5">
              <Titulo nota={dias > 1 ? `Promedio por hora en ${dias} días` : etiquetaPeriodo}>¿A qué hora vendo más?</Titulo>
              {sinHoras ? <Vacio>Sin ventas en el periodo.</Vacio> : (
                <GraficaBarras
                  etiquetas={horasVentana.map((h) => etiquetaHora(h.hora))}
                  valores={horasVentana.map((h) => h.neta / dias)}
                  alto={220}
                  nombre="Venta por hora"
                />
              )}
            </DaxCard>
            <DaxCard className="lg:col-span-7">
              <Titulo>¿Qué días y a qué horas vendo más?</Titulo>
              {heatmap.length === 0 ? <Vacio>Sin desglose por día y hora para este periodo.</Vacio> : (
                <SalesHeatmap data={heatmap} hourStart={ventana.desde} hourEnd={ventana.hasta} />
              )}
            </DaxCard>
          </div>

          {/* Sucursales: solo con selector y más de una */}
          {sucursalesCc.length > 1 && (
            <DaxCard>
              <Titulo nota="Venta neta del periodo">¿Cómo va cada sucursal?</Titulo>
              <div data-testid="sucursales">
                <GraficaBarras
                  etiquetas={sucursalesCc.map((b) => b.name)}
                  valores={sucursalesCc.map((b) => b.total_sales)}
                  horizontal
                  alto={Math.max(120, 36 * sucursalesCc.length + 40)}
                  nombre="Venta neta"
                />
                <ul className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1 text-sm">
                  {sucursalesCc.map((b) => (
                    <li key={b.id} className="flex justify-between border-t border-dax-border-dim py-1">
                      <span className="text-dax-muted">{b.name}</span>
                      <span className="font-bold tabular-nums text-dax-text">{formatCurrency(b.total_sales)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </DaxCard>
          )}

          {/* Lo más vendido */}
          <DaxCard>
            <Titulo nota="Por piezas; la barra es su parte del importe">¿Qué se vendió más?</Titulo>
            {top.length === 0 ? <Vacio>Sin ventas en el periodo.</Vacio> : esTelefono ? (
              <ListaTarjetas>
                {top.map((p, i) => (
                  <TarjetaFila key={`${p.name}-${i}`} titulo={`${i + 1}. ${p.name}`} subtitulo={piezas(p.qty)} importe={formatCurrency(p.total ?? 0)} />
                ))}
              </ListaTarjetas>
            ) : (
              <table className="w-full text-sm" data-testid="top">
                <thead>
                  <tr className="text-left text-[10px] uppercase tracking-widest text-dax-faint">
                    <th className="py-1 w-8">#</th>
                    <th className="py-1">Producto</th>
                    <th className="py-1 text-right">Piezas</th>
                    <th className="py-1 text-right">Importe</th>
                    <th className="py-1 w-32"><span className="sr-only">Proporción del importe</span></th>
                  </tr>
                </thead>
                <tbody>
                  {top.map((p, i) => (
                    <tr key={`${p.name}-${i}`} className="border-t border-dax-border-dim">
                      <td className="py-1.5 text-dax-faint tabular-nums">{i + 1}</td>
                      <td className="py-1.5 text-dax-text">{p.name}</td>
                      <td className="py-1.5 text-right tabular-nums text-dax-muted">{piezas(p.qty)}</td>
                      <td className="py-1.5 text-right tabular-nums font-bold text-dax-text">{formatCurrency(p.total ?? 0)}</td>
                      <td className="py-1.5 pl-3">
                        <div className="h-1.5 rounded-full bg-dax-border-dim overflow-hidden">
                          <div className="h-full rounded-full bg-dax-accent"
                            style={{ width: `${maxTop > 0 ? ((p.total ?? 0) / maxTop) * 100 : 0}%` }} /* estilo dinámico: el ancho es el dato */ />
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </DaxCard>
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Correr**

Run: `cd frontend && npx vitest run src/pages/reports --reporter=dot && npx tsc --noEmit -p tsconfig.json`
Expected: verde; tsc limpio. Si tsc rechaza `!error && <DaxCard>…` dentro del ternario, envolverlo: `error ? null : <DaxCard>…</DaxCard>`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/reports/Reportes.tsx frontend/src/pages/reports/__tests__/Reportes.test.tsx
git commit -m "feat(reportes): pantalla única Reportes con presets, comparativo, gráficas del kit y lo más vendido

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf"
```

---

### Task 9: Bajas, rutas, registro de perezosos y docs de las vistas

**Files:**
- Delete: `frontend/src/pages/finance/Reports.tsx`, `frontend/src/pages/finance/Reports.test.tsx`, `frontend/src/pages/finance/parametrosReportes.ts`, `frontend/src/pages/finance/parametrosReportes.test.ts`, `frontend/src/pages/hq/HQReportsHub.tsx`, `frontend/src/components/reports/Gauge.tsx`, `frontend/src/components/reports/Sparkline.tsx`, `frontend/src/components/reports/Leaderboard.tsx`, `frontend/src/components/reports/KPICard.tsx`
- Modify: `frontend/src/App.tsx:15, 28, 70, 277-279, 340`
- Modify: `frontend/src/__tests__/rutasPerezosas.test.ts` (añadir `Reportes`), `frontend/src/__tests__/modoBasico.test.ts:22-29`, `frontend/src/pages/__tests__/responsivoOla2.test.ts:9`
- Modify: `docs/FRONTEND_VIEWS.md:31, 58-59, 74, 247-251, 398-403`, `docs/modo-basico.md:38`

**Interfaces:**
- Consumes: `Reportes` (Tarea 8).
- Produces: `/hq/reports-hub` → `<Reportes conSucursales />`; `/reports` → `<Reportes />`. `PorPerfil` deja de usarse en `App.tsx` (el componente y su prueba se quedan: la Fase 3 y `modoBasico.test.ts` lo conocen). `parametrosReportes` desaparece: su regla (`branch_id: 0` para la dueña en básico y «Semana» de 7 días) la sustituyen el ámbito de la Fase 1 (sin `branch_id` = toda la org para roles de oficina) y los presets exactos de la Tarea 7. `reportsApi.salesByHour` se queda en `api/reports.ts` aunque ya nadie lo llame (es la API, no una pantalla).

- [ ] **Step 1: Bajas**

```bash
git rm frontend/src/pages/finance/Reports.tsx frontend/src/pages/finance/Reports.test.tsx \
  frontend/src/pages/finance/parametrosReportes.ts frontend/src/pages/finance/parametrosReportes.test.ts \
  frontend/src/pages/hq/HQReportsHub.tsx \
  frontend/src/components/reports/Gauge.tsx frontend/src/components/reports/Sparkline.tsx \
  frontend/src/components/reports/Leaderboard.tsx frontend/src/components/reports/KPICard.tsx
```

Comprobar que nadie más los importa: `git grep -n "HQReportsHub\|finance/Reports\|parametrosReportes\|reports/Gauge\|reports/Sparkline\|reports/Leaderboard\|reports/KPICard" -- frontend/src` debe devolver solo `App.tsx`, `__tests__/modoBasico.test.ts` y `pages/__tests__/responsivoOla2.test.ts` (se arreglan abajo). Los `Sparkline`/`Leaderboard` de `components/atlas-one/` y `components/platform/v2/` son otros archivos y no se tocan.

- [ ] **Step 2: Rutas en `App.tsx`**

1. Borrar la línea 15: `import { PorPerfil } from './components/layout/PorPerfil'`.
2. Sustituir la línea 28 (`const HQReportsHub    = lazy(…)`) por:

```tsx
// Reportes (Fase 2 del admin): una sola pantalla para HQ y sucursal; chart.js va en su chunk, no en el de entrada.
const Reportes        = lazy(() => import('./pages/reports/Reportes').then(m => ({ default: m.Reportes })))
```

3. Borrar la línea 70: `const Reports         = lazy(() => import('./pages/finance/Reports').then(m => ({ default: m.Reports })))`.
4. Sustituir las líneas 277-279 (comentario + `operations` + `reports-hub`) por:

```tsx
            {/* Inicio: la misma pantalla en básico y completo (decide con perfilUi). Reportes: una para todos; aquí con selector de sucursal. */}
            <Route path="operations" element={<RutaPorRol url="/hq/operations"><Suspense fallback={<PageLoader />}><Inicio /></Suspense></RutaPorRol>} />
            <Route path="reports-hub" element={<RutaPorRol url="/hq/reports-hub"><Suspense fallback={<PageLoader />}><Reportes conSucursales /></Suspense></RutaPorRol>} />
```

5. Sustituir la línea 340 por:

```tsx
          <Route path="reports"      element={<RutaPorRol url="/reports"><Suspense fallback={<PageLoader />}><Reportes /></Suspense></RutaPorRol>} />
```

- [ ] **Step 3: Guardias**

En `frontend/src/__tests__/rutasPerezosas.test.ts`, dentro de `PEREZOSOS`, debajo de `InicioGraficas`:

```ts
  Reportes: () => import('../pages/reports/Reportes'),
```

En `frontend/src/__tests__/modoBasico.test.ts`, sustituir la prueba completa de las líneas 22-29 (la que en la Tarea 6 ya recibió las aserciones del Inicio) por:

```ts
  it('el Inicio es una sola pantalla por perfil (SP6) en chunk propio sin chart.js; Reportes es una sola pantalla para todos (Fase 2)', () => {
    const app = src('App.tsx')
    expect(app).toMatch(/const Inicio\s+= lazy\(\(\) => import\('\.\/pages\/hq\/Inicio'\)/)
    expect(app).toMatch(/path="operations"[^\n]*<Inicio \/>/)
    expect(app).not.toMatch(/HQOperations|InicioBasico|HQReportsHub|finance\/Reports|PorPerfil/)
    expect(app).toMatch(/path="reports-hub"[^\n]*<Reportes conSucursales \/>/)
    expect(app).toMatch(/path="reports"\s+element=[^\n]*<Reportes \/>/)
    // El Inicio solo llega a las gráficas por lazy(): chart.js no viaja en su chunk.
    const inicio = src('pages/hq/Inicio.tsx')
    expect(inicio).not.toMatch(/chart\.js|react-chartjs-2|components\/graficas/)
    expect(inicio).toMatch(/lazy\(\(\) => import\('\.\/InicioGraficas'\)/)
    expect(inicio).not.toMatch(/^import \{[^}]*\} from '\.\/InicioGraficas'/m)   // solo `import type`
  })
```

En `frontend/src/pages/__tests__/responsivoOla2.test.ts` línea 9, cambiar `'hq/HQReportsHub.tsx'` por `'reports/Reportes.tsx'` (el comentario de la línea 5 pasa a decir «…y, desde SP6, todo el grupo HQ; desde la Fase 2 del admin, Reportes»).

- [ ] **Step 4: Correr**

Run: `cd frontend && npx vitest run --reporter=dot 2>&1 | tail -4 && npx tsc --noEmit -p tsconfig.json`
Expected: toda la suite verde (`overlaysFueraDelKit` y `botonesDelKit` no listaban los archivos borrados; `sinRecharts` sigue sin hallazgos); tsc limpio.

- [ ] **Step 5: Docs de las vistas**

En `docs/FRONTEND_VIEWS.md`:

- Línea 31: cambiar «las que respetan el tema claro de verdad son pocas (Reports, HQReportsHub, MobileOwnerDashboard)» por «las que respetan el tema de verdad son pocas: desde la Fase 2 del admin (2026-10-24) el Inicio, Reportes y el kit `components/graficas` se pintan solo con tokens `dax-*` (guardia `src/__tests__/coloresPorTokens.test.ts`), más MobileOwnerDashboard».
- Línea 58: `| /hq/operations | hq/Inicio (básico y completo: misma pantalla; en completo monta las cuatro gráficas de hq/InicioGraficas con lazy()) | Admin, Dueño | pos |`
- Línea 59: `| /hq/reports-hub | reports/Reportes (con selector de sucursal; básico y completo) | Admin, Dueño | pos |`
- Línea 74: `| /reports | reports/Reportes (fijado a la sucursal del usuario) | Gerente | — |`
- Sustituir la sección `### /hq/operations — Inicio` (líneas 241-245) por:

```markdown
### `/hq/operations` — Inicio ("¿Cómo voy?") 📱
- **Archivo:** `pages/hq/Inicio.tsx` (chunk propio, sin chart.js) + `pages/hq/InicioGraficas.tsx` (las cuatro gráficas, cargado con `lazy()` solo en perfil completo). Es la misma pantalla en básico y en completo: espera `enabledModulesStore.loaded` y decide con `perfilUi`.
- **Propósito:** responder las preguntas del dueño al entrar. Orden en escritorio (rejilla de 12 columnas, apilado en teléfono): 1 cifras Hoy / Ayer / 7 días / Utilidad bruta de hoy con variación (▲/▼ vs ayer, vs antier, vs semana anterior; `components/ui/KpiCard`) · 2 tendencia de 7 días (línea, la semana anterior en gris) y cómo te pagaron (dona con el total al centro + lista) · 3 ventas por hora de hoy (barras, la hora actual en acento) y caja · 4 pendientes · 5 se está acabando y lo más vendido · 6 no se mueve · 7 sucursales (barras horizontales + tarjetas; solo con más de una que vende) · valor de la tienda (`ValorTiendaCard`). En básico: cifras (solo Hoy con variación), lista de métodos, caja, se acaba, lo más vendido y valor de la tienda; **sin gráficas y sin bajar el chunk `charts`**.
- **Datos/API:** `reportsApi.inicio({ completo: !modoBasico })` (`GET /reports/inicio`: con `completo`, `tendencia`, `por_hora_hoy`, `utilidad_bruta_ayer`) y `reportsApi.valorInventario`.
- **Responsivo:** kit `ui/`; tablas en escritorio y `TarjetaFila` bajo 768. Filas de "se acaba"/"no se mueve" enlazan a `/hq/inventory?q=<sku>&variant=<id>`.
- **Tema:** solo tokens `dax-*` (`coloresPorTokens.test.ts`); las gráficas leen los tokens con `useTemaGrafica` y se repintan al cambiar de tema.
```

- Sustituir la sección `### /hq/reports-hub — Reportes` (líneas 247-251) por:

```markdown
### `/hq/reports-hub` — Reportes 📱
- **Archivo:** `pages/reports/Reportes.tsx` (`<Reportes conSucursales />`; la misma pantalla que `/reports`). Sustituye a `hq/HQReportsHub.tsx` y `finance/Reports.tsx` (borrados 2026-10-24).
- **Propósito:** periodos y comparativos (lo de hoy vive en el Inicio). Barra `Hoy · Ayer · 7 días · 30 días · Este mes` + rango a mano (`pages/reports/presetsReportes.ts`, mismos tramos que `metricas_ventas.periodo_preset`); sucursal (solo con más de una); Exportar CSV. Cifras con variación vs el periodo anterior: venta neta, tickets, ticket promedio, devoluciones (al alza en rojo), utilidad bruta (solo si algo de lo vendido tiene costo). ¿Cómo fue cada día? (línea con el periodo anterior en gris) · ¿Cómo me pagaron? (dona + lista) · ¿A qué hora vendo más? (barras, promedio por hora del periodo) · ¿Qué días y a qué horas? (`components/reports/Heatmap`, tokens) · ¿Cómo va cada sucursal? (barras horizontales, solo con selector y más de una) · ¿Qué se vendió más? (tabla con barra de proporción del importe; `TarjetaFila` en teléfono).
- **Datos/API:** `reportsApi.dashboard` (una llamada) y, solo con selector, `reportsApi.commandCenterStats` y `organizationApi.getBranches`; `reportsApi.exportCsv`.
- **Notas:** sin velocímetro, conteo animado ni sondeo cada 30 s. Gráficas del kit `components/graficas` (chart.js en el chunk `charts`, fuera de la ruta crítica del POS).
```

- Sustituir la sección `### /reports — Reportes` (líneas 398-403) por:

```markdown
### `/reports` — Reportes 📱
- **Archivo:** `pages/reports/Reportes.tsx` (`<Reportes />`, fijado a la sucursal del usuario: el backend la impone a cajera y gerente).
- **Propósito:** la misma pantalla que `/hq/reports-hub` sin selector de sucursal ni comparativa de sucursales (no llama a `/reports/command-center/stats`).
- **Quién la ve:** Gerente.
- **Datos/API:** `reportsApi.dashboard`, `reportsApi.exportCsv`.
```

En `docs/modo-basico.md`, fila «Inicio y Reportes de la dueña» (línea 38): cambiar «`/hq/reports-hub` → `finance/Reports`» por «`/hq/reports-hub` → `reports/Reportes` (la misma pantalla que en completo; el selector de sucursal solo aparece con más de una)» y la tercera columna por «`pages/hq/Inicio.tsx` (`perfilUi`; en básico no monta `InicioGraficas`)».

- [ ] **Step 6: Commit**

```bash
git add -A frontend/src/pages/finance frontend/src/pages/hq/HQReportsHub.tsx frontend/src/components/reports \
  frontend/src/App.tsx frontend/src/__tests__/rutasPerezosas.test.ts frontend/src/__tests__/modoBasico.test.ts \
  frontend/src/pages/__tests__/responsivoOla2.test.ts docs/FRONTEND_VIEWS.md docs/modo-basico.md
git commit -m "refactor(reportes): Reportes sustituye a HQReportsHub y finance/Reports; fuera Gauge, Sparkline, Leaderboard y KPICard

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf"
```

---

### Task 10: Guardia `coloresPorTokens.test.ts` y limpieza de sobrescrituras muertas en `index.css`

**Files:**
- Create: `frontend/src/__tests__/coloresPorTokens.test.ts`
- Modify: `frontend/src/index.css:346-351, 354-359, 362-366, 369-371, 373-376, 389-392, 398, 402-403, 406-407, 419-422, 433-434`

**Interfaces:**
- Consumes: el estado del árbol tras las Tareas 6-9 (los archivos de esta fase ya solo usan tokens; los borrados ya no existen).
- Produces: guardia que (a) prohíbe `text-white`, `text-slate-*`, `bg-slate-*`, `border-slate-*` y hex `#rrggbb` en las carpetas de la spec §3.4 salvo la lista `PENDIENTES` (deuda que cada fase vacía) y los respaldos hex de `components/graficas/tema.ts` (el canvas no entiende `var()`); (b) exige que los archivos de esta fase (`LIMPIOS`) no usen ninguna clase de paleta Tailwind; (c) impide `!important` nuevos en el bloque `LIGHT MODE` de `index.css` (tope 30 tras la limpieza).

**Decisión (spec §3.4: «las sobrescrituras `html.light` se quedan mientras POS y plataforma las usen»):** solo se retiran los selectores que **ningún archivo de `frontend/src` ni `frontend/index.html` usa hoy** (verificado el 2026-10-24 con `git grep -F` sobre la clase exacta; `dark:group-hover:text-slate-400` y `divide-slate-700/40` son otras clases y no cuentan): `bg-slate-900/80`, `bg-slate-900/50`, `bg-slate-900/20`, `bg-slate-800/80`, `bg-slate-700/80`, `bg-slate-700/20`, `border-slate-900`, `border-white/10`, `border-white/5`, `hover:text-slate-300`, `hover:text-slate-400`, `hover:bg-white/5`, `ring-slate-800`, `divide-slate-700`, `border-slate-700/20`, `bg-black/80`, y la regla duplicada `html.light .hover\:text-white:hover` de la línea 390 (la de la línea 437, idéntica y posterior, es la que gana). Las tareas 6-9 no dejan sin uso ningún otro selector (todos siguen en POS, plataforma u otras pantallas). Nada se añade.

- [ ] **Step 1: Prueba que falla**

Crear `frontend/src/__tests__/coloresPorTokens.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'

/**
 * Tema por tokens (spec 2026-10-23 §3.4): las pantallas del admin se pintan
 * con `text-dax-*`, `bg-dax-*`, `border-dax-*` (tailwind.config.js →
 * colors.dax), nunca con `text-white`, `slate-*` ni hex sueltos: el modo claro
 * los sobrescribe con `!important` en index.css y cada color fijo es un parche
 * más. PENDIENTES es la deuda que quedó al cerrar la Fase 2 (2026-10-24); cada
 * fase la vacía. Para limpiar un archivo: quita sus colores fijos Y bórralo de
 * la lista (la segunda prueba lo exige).
 */
const raiz = resolve(__dirname, '..')
const CARPETAS = ['pages/hq', 'pages/home', 'pages/finance', 'pages/sales', 'pages/inventory', 'pages/core',
  'pages/reports', 'components/reports', 'components/graficas']
const PROHIBIDAS = /(?<![\w-])(?:text-white|text-slate-\d{2,3}|bg-slate-\d{2,3}|border-slate-\d{2,3})(?![\w-])|#[0-9a-fA-F]{6}\b/
/** Cualquier color de la paleta de Tailwind (los archivos de esta fase no usan ninguno). */
const PALETA = /(?<![\w-])(?:(?:hover|focus|active|dark|group-hover|max-md|sm|md|lg):)*(?:text|bg|border|ring|from|to|via|fill|stroke)-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose|white|black)(?:-\d{2,3})?(?:\/\d{1,3})?(?![\w-])/

const PENDIENTES = [
  'pages/core/AdminCatalog.tsx', 'pages/core/Brands.tsx', 'pages/core/Departments.tsx', 'pages/core/Organization.tsx',
  'pages/core/Users.tsx', 'pages/core/catalogActions.ts',
  'pages/finance/CashHistory.tsx', 'pages/finance/Expenses.tsx', 'pages/finance/Purchases.tsx',
  'pages/home/GastroHomeDay.tsx', 'pages/home/PresetHome.tsx',
  'pages/hq/HQBranches.tsx', 'pages/hq/HQInventory.tsx', 'pages/hq/HQReturns.tsx', 'pages/hq/HQSalesLog.tsx',
  'pages/inventory/Boxes.tsx', 'pages/inventory/Inventory.tsx', 'pages/inventory/Logistics.tsx', 'pages/inventory/Products.tsx',
  'pages/inventory/conteos/BuscadorVariante.tsx', 'pages/inventory/conteos/ConteoReporte.tsx', 'pages/inventory/conteos/avance.ts',
  'pages/inventory/conteos/ConteoSesion.tsx', 'pages/inventory/conteos/Conteos.tsx',
  'pages/inventory/conteos/FichaProducto.tsx', 'pages/inventory/conteos/ListaDepartamento.tsx',
  'pages/inventory/conteos/lista.ts',
  'pages/reports/Meseros.tsx',
  'pages/sales/QuoteMaker.tsx', 'pages/sales/Quotes.tsx', 'pages/sales/Returns.tsx', 'pages/sales/SalesHistory.tsx',
  'pages/sales/Seguimiento.tsx',
]
/** chart.js pinta en canvas y no entiende `var()`: `tema.ts` necesita un color concreto
 *  de respaldo por si el token falta. Es el único hex permitido en estas carpetas. */
const RESPALDOS_DEL_CANVAS = ['components/graficas/tema.ts']
/** Lo que esta fase creó o reescribió: cero colores fijos, de ninguna paleta. */
const LIMPIOS = [
  'pages/hq/Inicio.tsx', 'pages/hq/InicioGraficas.tsx', 'pages/reports/Reportes.tsx', 'pages/reports/presetsReportes.ts',
  'components/reports/Heatmap.tsx', 'components/reports/ValorTiendaCard.tsx', 'components/ui/KpiCard.tsx',
]

function archivos(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n)
    if (statSync(p).isDirectory()) return n === '__tests__' ? [] : archivos(p)
    return /\.tsx?$/.test(n) && !/\.test\.tsx?$/.test(n) ? [p] : []
  })
}
const relativo = (p: string) => p.slice(raiz.length + 1).replace(/\\/g, '/')
const fuente = (rel: string) => readFileSync(join(raiz, rel), 'utf8')

describe('colores por tokens (spec §3.4)', () => {
  const todos = CARPETAS.flatMap((c) => archivos(join(raiz, c))).map(relativo)

  it('ningún archivo fuera de PENDIENTES usa text-white, slate-* ni hex', () => {
    const culpables = todos.filter((f) => !PENDIENTES.includes(f) && !RESPALDOS_DEL_CANVAS.includes(f) && PROHIBIDAS.test(fuente(f)))
    expect(culpables).toEqual([])
  })

  it('todo PENDIENTES sigue sucio y existe (al limpiar o borrar un archivo, quítalo de la lista)', () => {
    const limpios = PENDIENTES.filter((f) => !todos.includes(f) || !PROHIBIDAS.test(fuente(f)))
    expect(limpios).toEqual([])
  })

  it('los archivos de la Fase 2 y el kit de gráficas no usan ninguna paleta de Tailwind', () => {
    const kit = archivos(join(raiz, 'components/graficas')).map(relativo)
    const culpables = [...LIMPIOS, ...kit]
      .map((f) => ({ f, hallazgos: fuente(f).match(new RegExp(PALETA.source, 'g')) ?? [] }))
      .filter(({ hallazgos }) => hallazgos.length > 0)
      .map(({ f, hallazgos }) => `${f}: ${[...new Set(hallazgos)].join(', ')}`)
    expect(culpables).toEqual([])
  })

  it('el modo claro no gana sobrescrituras !important nuevas', () => {
    const css = readFileSync(join(raiz, 'index.css'), 'utf8')
    const bloque = css.slice(css.indexOf('LIGHT MODE'), css.indexOf('@layer components'))
    expect(bloque.length).toBeGreaterThan(0)
    expect((bloque.match(/!important/g) ?? []).length).toBeLessThanOrEqual(30)
  })
})
```

Run: `cd frontend && npx vitest run src/__tests__/coloresPorTokens.test.ts --reporter=dot`
Expected: la última prueba falla (hoy hay 34 `!important`); las tres primeras pasan si las Tareas 6-9 quedaron bien (si la primera señala un archivo de esta fase, arreglar ahí el color, no la lista).

- [ ] **Step 2: Retirar los selectores muertos de `index.css`**

Dentro del bloque `LIGHT MODE` (líneas 334-437), hacer estos cambios exactos:

1. Líneas 346-351 → 
```css
  html.light .bg-slate-900\/60,
  html.light .bg-slate-900\/40,
  html.light .bg-slate-900\/30 { background-color: rgba(251,250,246,0.97) !important; }
```
2. Líneas 354-359 → 
```css
  html.light .bg-slate-800\/60,
  html.light .bg-slate-800\/50,
  html.light .bg-slate-800\/40,
  html.light .bg-slate-800\/30,
  html.light .bg-slate-800\/20 { background-color: rgba(242,239,231,0.9) !important; }
```
3. Líneas 362-366 → 
```css
  html.light .bg-slate-700\/60,
  html.light .bg-slate-700\/50,
  html.light .bg-slate-700\/30 { background-color: rgba(232,229,221,0.8) !important; }
```
4. Líneas 369-371 → 
```css
  html.light .border-slate-700,
  html.light .border-slate-800  { border-color: rgba(127,102,82,0.24) !important; }
```
5. Líneas 373-376 → 
```css
  html.light .border-slate-700\/50,
  html.light .border-slate-700\/30 { border-color: rgba(127,102,82,0.14) !important; }
```
6. Borrar las líneas 389-392 completas (el comentario `/* hover:text-* en modo claro */` y las tres reglas `hover\:text-white`, `hover\:text-slate-300`, `hover\:text-slate-400`; la de `hover\:text-white` sobrevive en la línea 437, que ya era la que ganaba) y la línea en blanco 393.
7. Borrar la línea 398 (`html.light .hover\:bg-white\/5:hover …`).
8. Líneas 402-403 → `  html.light .ring-slate-700    { --tw-ring-color: rgba(127,102,82,0.4) !important; }`
9. Líneas 406-407 → `  html.light .divide-slate-800 > * + * { border-color: rgba(127,102,82,0.18) !important; }`
10. Líneas 418-422 → 
```css
  /* border-slate-700/30, /40, /60 — divisores de filas y secciones */
  html.light .border-slate-700\/30,
  html.light .border-slate-700\/40,
  html.light .border-slate-700\/60 { border-color: rgba(127,102,82,0.16) !important; }
```
11. Líneas 433-434 → `  html.light .bg-black\/70 { background-color: rgba(40,32,24,0.42) !important; }`

Comprobar que no quedó ningún uso: `cd frontend && git grep -n -E "(^|[^-/\w])(bg-slate-900/(80|50|20)|bg-slate-800/80|bg-slate-700/(80|20)|border-slate-900|border-white/(10|5)|hover:text-slate-(300|400)|hover:bg-white/5|ring-slate-800|divide-slate-700|border-slate-700/20|bg-black/80)([^-/\w]|$)" -- src index.html ':!src/index.css'` → sin salida.

- [ ] **Step 3: Correr**

Run: `cd frontend && npx vitest run src/__tests__/coloresPorTokens.test.ts src/__tests__/botonesDelKit.test.ts --reporter=dot && grep -c '!important' src/index.css`
Expected: verde; el conteo total del archivo baja 4 respecto a antes (de 35 a 31: 34 → 30 en el bloque claro; el de `#cajon-lateral` no está en el bloque).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/__tests__/coloresPorTokens.test.ts frontend/src/index.css
git commit -m "test(tema): guardia coloresPorTokens y retiro de sobrescrituras html.light sin uso

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf"
```

---

### Task 11: Verificación completa, capturas y cierre de docs

**Files:**
- Modify: `docs/superpowers/specs/2026-10-23-admin-precision-inicio-fusiones-design.md:3` (`**Estado:**`)
- Modify: `CLAUDE.md` §6 (una viñeta nueva)

- [ ] **Step 1: Suite de backend**

Run: `python3 -m pytest -q -p no:warnings --ignore=tests/test_cash_complete.py --ignore=tests/test_branch_dashboard.py --ignore=tests/test_cash_close_guided.py 2>&1 | tail -5`
Expected: `0 failed`; `passed` = 1619 + 7 (cinco de la Tarea 1, dos de la Tarea 2) = 1626. Si falla algo que no tocaron las Tareas 1-2, compararlo con `main` antes de tocarlo. Un solo pytest por worktree.

- [ ] **Step 2: Frontend**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json && npx vitest run --reporter=dot 2>&1 | tail -4 && npm run build 2>&1 | tail -6`
Expected: tsc sin errores; vitest todo verde (incluidos `coloresPorTokens`, `rutasPerezosas`, `modoBasico`, `responsivoOla2`, `hqSinEstilosInline`, `overlaysFueraDelKit`, `botonesDelKit`, `sinRecharts`); `vite build` termina y en `dist/assets/` hay un `charts-*.js`, un chunk de `Inicio-*.js` **que no contiene chart.js** y chunks de `InicioGraficas-*.js` y `Reportes-*.js`. Comprobar que el Inicio no arrastra chart.js: `grep -l "Chart.register\|chart.js" dist/assets/Inicio-*.js` → sin salida.

- [ ] **Step 3: Presupuesto de la ruta crítica del POS**

Run: `python3 scripts/presupuesto_bundle.py --dist frontend/dist --presupuesto frontend/presupuesto_bundle.json`
Expected: código 0; `charts-*` no aparece entre los precargados; el TOTAL no sube respecto a `main` (ninguna pantalla de esta fase entra en la precarga del POS). **No tocar `presupuesto_bundle.json`.**

- [ ] **Step 4: Capturas Playwright (claro y oscuro, 1440 y 390) sobre la base de demo**

Con la herramienta del controlador (receta `playwright-sin-sudo-wsl`: backend SQLite desechable con `demo_server.py`, sesión inyectada por `localStorage`), capturar estas rutas en los dos temas y los dos anchos:

| Ruta | Sesión | Qué comprobar |
|---|---|---|
| `/hq/operations` | administrador de la demo (perfil completo) | cuatro gráficas en la rejilla de 12 (8/4, 8/4), variaciones ▲/▼, ningún color fijo que no cambie entre claro y oscuro; en 390 todo apilado y las tablas como `TarjetaFila` |
| `/hq/operations` | organización en perfil básico (`perfil_ui = 'basico'`) | sin gráficas; en la pestaña de red no se pide ningún `assets/charts-*.js` ni `InicioGraficas-*.js` (`page.on('request')`) |
| `/hq/reports-hub` | administrador (demo con dos sucursales) | barra de presets con «7 días» activo, cinco cifras (utilidad solo si la demo tiene costos), línea con el comparativo en gris, dona, barras por hora, heatmap repintado, sucursales, lo más vendido; en 390 la tabla del top es `TarjetaFila` |
| `/reports` | cajera de la demo | sin selector de sucursal ni sección de sucursales; mismo resto |

Cambiar de tema con el conmutador del sidebar con una gráfica en pantalla y comprobar que la gráfica se repinta (ejes y serie cambian de color sin recargar).

- [ ] **Step 5: Docs de cierre**

- En el spec, línea 3: `**Estado:** fases 1 y 2 implementadas (fase 2 en \`feat/admin-fase2-inicio-reportes\`, pendiente de fusión); fase 3 (fusiones y menú) pendiente ·`.
- En `CLAUDE.md` §6 añadir la viñeta: «**Colores por tokens en el admin.** `frontend/src/__tests__/coloresPorTokens.test.ts` prohíbe `text-white`, `text-slate-*`, `bg-slate-*`, `border-slate-*` y hex sueltos en `pages/hq|home|finance|sales|inventory|core|reports` y `components/reports|graficas`, salvo la lista `PENDIENTES` (deuda que cada fase vacía: al limpiar un archivo, bórralo de la lista). Pinta con `text-dax-*`/`bg-dax-*`/`border-dax-*` (`tailwind.config.js`) y, para chart.js, con `useTemaGrafica()` de `components/graficas`. El bloque `html.light … !important` de `index.css` no admite reglas nuevas (tope en esa prueba).»
- `docs/API_REFERENCE.md` y `docs/FRONTEND_VIEWS.md` ya quedaron al día en las Tareas 1, 2 y 9; releer las filas tocadas.

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md docs/superpowers/specs/2026-10-23-admin-precision-inicio-fusiones-design.md
git commit -m "docs: guardia de colores por tokens en CLAUDE.md y estado de la Fase 2 en el spec del admin

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf"
```

La fusión a `main` y el despliegue los autoriza el usuario (spec §7).

---

## Cobertura de la spec (revisión del plan)

| Spec | Tarea |
|---|---|
| §3.1 `/reports/inicio` con `tendencia` y `por_hora_hoy` | 1 |
| §3.1 orden de escritorio, rejilla de 12, cifras con variación, cuatro gráficas, secciones conservadas, básico sin gráficas ni chunk `charts` | 5, 6 |
| §3.2 `Reportes` único para `/hq/reports-hub` y `/reports`; barra de presets; cifras con variación (utilidad solo con costos); tendencia, dona, horas (promedio), heatmap con tokens, sucursales, lo más vendido; CSV; bajas de `Gauge`, conteo animado, `Leaderboard`, sondeo de 30 s, «En tránsito» y «Ritmo actual» | 2 (datos que faltaban), 7, 8, 9 |
| §3.3 kit `components/graficas`, `useTemaGrafica` (tokens + MutationObserver), colores de método, ejes `$1.2k`, tooltips `formatCurrency`, 300 ms, sin degradados ni relleno; `components/ui/KpiCard` con `dax-kpi-*` | 3, 4 |
| §3.4 guardia `coloresPorTokens.test.ts` con lista blanca; pantallas de la fase sin colores fijos; `dax-section-title` como pregunta; un `CabeceraPagina` por pantalla; sin `!important` nuevos | 6, 7, 8, 10 |
| §5 lo que no cambia (POS, caja, `GastroHomeDay`, `HQBranches` siguen con `/reports/dashboard`; `top_products` crece a 10 con `total` sin romperlos) | 2 |
| §6 `rutasPerezosas` registra los módulos nuevos; `botonesDelKit`/`overlaysFueraDelKit` siguen vigentes | 5, 9 |
| §7 verificación por fase | 11 |
| §8.2 Inicio con las cuatro gráficas en claro y oscuro sin colores fijos; §8.4 docs al día | 6, 9, 11 |
