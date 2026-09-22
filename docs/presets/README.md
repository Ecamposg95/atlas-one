# Cómo crear un preset nuevo

`docs/presets/` documenta presets de industria concretos, con el detalle operativo que
un dueño real necesitó (estándar de datos, checklist de alta, decisiones tomadas). Es
un nivel más abajo que `docs/DATA_MODEL.md`/`docs/API_REFERENCE.md` (qué existe en el
sistema) y que `docs/ARCHITECTURE.md` (cómo está construido): aquí va **qué elegir**
para un vertical de negocio concreto.

- [`BOUTIQUE.md`](BOUTIQUE.md) — el primer preset documentado así (`ATLAS_POS_BOUTIQUE`,
  Eleven Fashion). Úsalo como plantilla de estructura para el siguiente.

---

## 1. Dónde viven los presets (código vs. datos)

Un preset **no es una tabla especial ni un vertical de código aparte** — es una
composición de módulos ya existentes, más (opcionalmente) columnas nuevas si el
vertical necesita capturar algo que ningún módulo captura hoy.

| Pieza | Es código o datos | Dónde vive |
|---|---|---|
| Catálogo de módulos (`MODULES_CATALOG`) | datos (seed) | `scripts/init_presets_v2.py` |
| Composición del preset (qué módulos trae) | datos (seed) | `scripts/init_presets_v2.py::PRESETS` + fallback en `app/services/capabilities_service.py::INDUSTRY_PRESETS` |
| Enum `IndustryType` | esquema (enum de Postgres) | `app/modules/tenants/models.py`, sincronizado por `scripts/railway_init.py` (`ALTER TYPE … ADD VALUE IF NOT EXISTS`, AUTOCOMMIT) |
| Un módulo nuevo (si el preset lo necesita) | código | `app/modules/<x>/` (router, schemas, services) + entrada en `MODULES_CATALOG` |
| Columnas nuevas de datos del vertical (p. ej. `products.gender`) | código + migración | modelo en `app/modules/<x>/models.py` + `ALTER TABLE` idempotente en `scripts/railway_init.py::migrations` |
| El estándar de negocio (nombres, SKU, checklist de alta) | **documentación**, no código | `docs/presets/<PRESET>.md` |

**La regla que evita presets huérfanos:** `seed_modules_and_presets` (llamado
automáticamente por `railway_init.py` en cada deploy, línea ~611) es la fuente de
verdad en base de datos; el diccionario `INDUSTRY_PRESETS` de `capabilities_service.py`
es **solo un fallback** que se consulta si la tabla `industry_presets` no tiene fila
para esa industria (base nueva sin seed, o carrera de deploy). **Si agregas un preset,
edita los dos** y deja el comentario que ya existe ("Must mirror… DB row is the source
of truth") — que diverjan es el hallazgo §1.3 de la auditoría de esquema de 2026-09-19
(ningún FK ata `industry_presets.industry_type` al enum `IndustryType`; nada impide que
uno nombre un vertical que el otro no tiene).

## 2. Cuándo el vertical necesita un módulo nuevo vs. solo activar módulos existentes

La mayoría de los presets son una **composición**: Atlas POS (`core, pos,
cash_management, catalog, inventory, returns, pricing, payments, reports`) más los
módulos que el vertical necesita de la lista ya existente (`crm`, `quotes`, `tables`,
`kds`, `menu`, `recipes`, `bar`, `appointments`, `warehouse`, `branch_catalog_enablement`,
`promotions`, `purchasing`…). Boutique lo es: **no** se escribió ningún módulo desde
cero, `scanner` y `variants` ya existían de un trabajo previo.

Escribe un módulo nuevo (`app/modules/<x>/`, ver
[`docs/modules/MODULE_GUIDE.md`](../modules/MODULE_GUIDE.md)) solo cuando el vertical
necesita una **capacidad que ningún módulo existente cubre** (una tabla nueva, un
endpoint nuevo, una regla de negocio nueva). Antes de escribir uno, revisa si es en
realidad una variación de datos sobre un módulo existente (como `gender/model/material`
lo fue sobre `products`, sin módulo nuevo) — es más barato y no fragmenta el catálogo.

## 3. Checklist para crear un preset nuevo

1. **Decide la composición.** ¿Atlas POS + módulos existentes, o hace falta algo
   nuevo? Si hace falta algo nuevo, sigue `MODULE_GUIDE.md` primero.
2. **Agrega el `IndustryType`** si el vertical no tiene uno (enum de Postgres — el
   `ALTER TYPE` va en `railway_init.py`, junto al bloque que ya sincroniza el enum).
3. **Agrega el preset en los dos lugares:** `scripts/init_presets_v2.py::PRESETS`
   (fuente de verdad en BD) y `app/services/capabilities_service.py::INDUSTRY_PRESETS`
   (fallback). Usa una constante `MOD_*` para cada módulo, como las que ya existen.
4. **Si el vertical necesita columnas nuevas** en tablas existentes (como
   `products.gender/model/material` o las columnas `ticket_*` de boutique): agrégalas
   al modelo de SQLAlchemy **y** a la lista `migrations` de `railway_init.py` como
   `ALTER TABLE … ADD COLUMN` idempotente. Nunca Alembic (regla de oro §3). Si el
   vertical necesita un enum de valores fijos (como `gender`), usa una columna
   `String` con constantes Python, no un enum de Postgres — evita el `ALTER TYPE` cada
   vez que se agregue un valor (regla de oro §5, y la lección de `usd_rate_mode`).
5. **Escribe la documentación del preset** en `docs/presets/<PRESET>.md` con la
   estructura de `BOUTIQUE.md`: qué es (módulos y por qué), estándar de datos (si el
   vertical necesita uno), pantallas/flujos específicos, checklist de alta, deuda
   conocida.
6. **Actualiza `docs/DATA_MODEL.md`/`docs/API_REFERENCE.md`** con las columnas y
   endpoints nuevos — no reescribas su estructura, añade a las secciones que ya
   existen (ver cómo se hizo con boutique en el historial de commits de esos archivos).
7. **Prueba el alta de punta a punta** en una organización de prueba antes de
   ofrecerlo a un cliente real: `apply_industry_preset` → `GET /api/org/capabilities/`
   trae los módulos correctos → cada pantalla nueva aparece solo con el preset activo
   → una organización con Atlas POS normal no ve NADA nuevo (esa es la prueba de
   neutralidad que se le exigió a cada feature de boutique, ver los specs en
   `docs/superpowers/specs/2026-09-1{7,9}-*.md`).

## 4. Qué copiar de boutique y qué es específico de Eleven

**Copiable a cualquier preset nuevo (patrón, no dato):**
- La estructura del documento (`docs/presets/<PRESET>.md`).
- El patrón de "capacidad universal pero neutra por defecto" — USD y comisión por
  tarjeta son features **generales** (cualquier organización las puede activar), no
  exclusivas de boutique; nacen apagadas y no cambian nada hasta que el dueño las
  configura. Repite este patrón para cualquier feature que no sea intrínsecamente del
  vertical.
- El patrón de scripts operativos API-driven, idempotentes, corriendo como el admin de
  la tienda (`docs/presets/BOUTIQUE.md §7`).
- El checklist de "decisiones a tomar con el dueño ANTES de cargar datos" — adapta las
  preguntas al vertical, pero la disciplina de decidirlas antes de tocar el catálogo es
  general.

**Específico de boutique, NO copiar tal cual a otro vertical:**
- El estándar de nombre de venta (marca · prenda · modelo · atributos) y la convención
  de SKU (`sale_name.py`) — es la gramática de una prenda con talla/color; una
  ferretería o una farmacia necesitan su propia convención.
- Los módulos `scanner` y `variants` en sí — reutilízalos si el vertical nuevo también
  vende variantes por atributo (color, talla, capacidad…), pero no los actives por
  costumbre si el vertical no los necesita.
- El estilo de ticket `detailed` — pensado para prendas con marca/talla; puede no
  aportar nada a un vertical sin esa necesidad.

## 5. Decisiones que hay que pedirle al dueño (la lista, genérica)

Extraída de las que realmente se le preguntaron al dueño de Eleven Fashion — la lista
concreta de boutique está en `BOUTIQUE.md §6`; en general, para cualquier preset nuevo:

- ¿Cómo se llama un producto en este negocio? (¿el nombre incluye la marca, el
  modelo, algún atributo?)
- ¿Qué atributos distinguen una variante vendible (talla, color, capacidad, sabor…)?
- ¿Cómo arma este dueño sus departamentos/categorías?
- ¿Tiene una convención de SKU propia, o adopta la sugerida?
- ¿Qué necesita el ticket (redes, términos, proveedor, estilo de línea)?
- ¿Comisión por tarjeta? ¿Equivalente en USD? (universales — preguntar siempre,
  aunque el vertical no sea boutique)
- ¿Cómo va a imprimir? (agente local, qué impresora, qué SO)
- ¿PIN de reimpresión, y para quién?

Documenta las respuestas en el `docs/presets/<PRESET>.md` del vertical nuevo, igual
que boutique documenta las de Eleven.
