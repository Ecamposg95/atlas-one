# F3 · Cobro de suscripciones (primera versión, registro manual) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Atlas lleva la cuenta de lo que le cobra a cada tienda: una suscripción por organización, un cargo por periodo y los pagos que plataforma registra a mano. La tienda ve su plan y su historial; plataforma ve cartera vencida, por vencer e ingreso mensual recurrente real.

**Architecture:** Módulo nuevo `app/modules/suscripciones/` (models, schemas, services, router). Tres tablas que crea `create_all`. El estado se **calcula** con una función pura a partir de fechas y cargos; la columna `estado` es una foto que se refresca en cada escritura y solo manda cuando es manual (`suspendida`, `cortesia`). El plan de la suscripción y `organization.plan` se mueven juntos por `plans.asignar_plan`.

**Tech Stack:** FastAPI + SQLAlchemy (pytest, SQLite en memoria) · React + TS (vitest).

**Spec:** `docs/superpowers/specs/2026-11-24-megaplan-pendientes-y-agente-design.md` §2 (decisión 10) y §7.

## Global Constraints

- **No es CRM Cobranza** (`/crm/cobranza`, crédito de la tienda a sus clientes). No se toca.
- **Registro manual.** No hay pasarela, ni webhooks, ni correo, ni CFDI.
- **Nada bloquea accesos.** `suspendida` se pone a mano y es informativa. No se toca `organization.is_active` ni ningún guard.
- Dinero en `Numeric(12, 2)` / `Decimal`; nunca float. La API lo serializa como texto (`"499.00"`).
- Estados y métodos como `String` con constantes Python (sin enum de Postgres).
- PKs enteras (la organización es entera); toda tabla lleva `organization_id`.
- "Hoy" = día de México (`metricas_ventas.hoy_mx`), inyectable en los servicios.
- Plataforma: lee SUPERADMIN y SUPPORT; escribe solo SUPERADMIN. Tienda: solo ADMINISTRADOR y DUEÑO, solo lectura, filtrado por `organization_id`.
- Toda escritura deja fila en `platform_audit_log`.
- Tablas nuevas: no llevan ALTER en `railway_init.py` (las crea `create_all`).

## Modelo de datos

| Tabla | Columnas clave |
|---|---|
| `suscripciones` | `id`, `organization_id` (único), `plan`, `precio_mxn`, `periodicidad` (`mensual`/`anual`), `dia_corte` (1–28), `fecha_inicio`, `proxima_renovacion`, `estado`, `notas`, `rfc`, `razon_social`, `correo_facturacion`, `created_at`, `updated_at` |
| `suscripcion_cargos` | `id`, `organization_id`, `suscripcion_id`, `periodo_desde`, `periodo_hasta`, `importe`, `vence_el`, `estado` (`pendiente`/`pagado`/`cancelado`), `pagado_at`, `cancelado_at`, `motivo_cancelacion`; único `(organization_id, periodo_desde)` |
| `suscripcion_pagos` | `id`, `organization_id`, `cargo_id`, `importe`, `fecha_pago`, `metodo` (`transferencia`/`deposito`/`efectivo`/`tarjeta`/`otro`), `referencia`, `notas`, `registrado_por_user_id`, `origen` (`manual`), `id_externo`; único `(origen, id_externo)` |

`origen` e `id_externo` no se usan todavía: quedan para que el webhook de la pasarela sea idempotente sin migrar.

### Reglas

- **Estado** (`calcular_estado`, en este orden): manual (`suspendida`/`cortesia`) gana → precio 0 es `al_corriente` → cargo pendiente con `vence_el < hoy` es `vencida` → cargo pendiente que vence en ≤ 7 días es `por_vencer` (más lejos, `al_corriente`) → sin cargos pendientes manda `proxima_renovacion` (pasada = `vencida`, en ≤ 7 días = `por_vencer`).
- **Periodo:** empieza en `periodo_desde` y termina el día anterior al siguiente corte (un mes o doce después, en el `dia_corte`). Sin prorrateo.
- **Generar cargo:** por omisión el periodo que empieza en `proxima_renovacion` (esa fecha solo avanza al pagar, así que repetir devuelve el mismo cargo; para adelantar otro periodo se manda `periodo_desde`), importe = precio pactado, vence el primer día del periodo (se cobra por adelantado). Si ya existe el cargo de ese periodo se devuelve tal cual; si estaba cancelado y sin pagos, se reabre.
- **Pago:** contra un cargo pendiente, mayor que cero y no mayor al saldo. Al cubrir el importe el cargo pasa a `pagado` y `proxima_renovacion` avanza al día siguiente de `periodo_hasta` (nunca retrocede).
- **Cancelar cargo:** solo sin pagos (no hay reembolsos en esta versión).
- **Plan:** `plans.asignar_plan(org, clave)` es el único que escribe `organization.plan`. Cambiarlo desde la suscripción lo usa; cambiarlo desde el `PUT /organizations/{id}` de siempre refleja el plan en la suscripción (el precio pactado no se toca).

## Endpoints

Plataforma (`/api/platform`, lectura SUPERADMIN/SUPPORT, escritura SUPERADMIN):

- `GET  /suscripciones?estado=&q=` — lista + totales (`cartera_vencida`, `por_vencer`, `ingreso_mensual_recurrente`, conteo por estado, organizaciones sin suscripción).
- `GET  /organizations/{org_id}/suscripcion` — suscripción (o `null`), cargos con sus pagos.
- `PUT  /organizations/{org_id}/suscripcion` — alta o edición.
- `POST /organizations/{org_id}/suscripcion/cargos` — genera el cargo del periodo (201 nuevo, 200 si ya existía).
- `POST /suscripciones/cargos/{cargo_id}/pagos` — registra un pago.
- `POST /suscripciones/cargos/{cargo_id}/cancelar` — cancela el cargo.

Tienda:

- `GET /api/suscripcion/mia` — plan, uso contra topes, suscripción (sin notas internas) e historial.

## Pantallas

- Plataforma `/platform/suscripciones`: totales arriba, filtro por estado, tabla (tarjetas en teléfono).
- Plataforma, detalle de organización: sección "Suscripción" con alta/edición, cargos, "Generar cargo", "Registrar pago" y "Cancelar".
- Tienda `/configuracion?tab=plan`: "Mi plan y pagos", solo lectura, solo ADMINISTRADOR y DUEÑO.

## Review Focus

- Dos clics en "Generar cargo" → un solo cargo (`UniqueConstraint` + lectura previa).
- Pago mayor al saldo → 422; dos parciales que suman el importe → `pagado` y renovación avanzada una sola vez.
- Pagar un cargo viejo no retrocede `proxima_renovacion`.
- SUPPORT recibe 403 en toda escritura; cajera y gerente 403 en `/api/suscripcion/mia`; el administrador de otra tienda no ve nada de esta.
- Borrado forzado de la organización se lleva pagos, cargos y suscripción (en ese orden).

---

### Task 1: Modelo, cálculo de estado y servicios

**Files:** Create `app/modules/suscripciones/{__init__,models,schemas,services}.py` · Modify `app/models/__init__.py`, `app/services/plans.py` (`asignar_plan`) · Test `tests/test_suscripciones.py`

- [ ] Pruebas de `calcular_estado` (cada rama, con `hoy` fijo) y de `siguiente_corte`.
- [ ] Pruebas de servicio: alta con precio de lista por omisión, cargo idempotente, pago parcial y total, cancelar, sincronía de plan.
- [ ] Modelos + registro en `app/models/__init__.py`.
- [ ] Servicios: `guardar_suscripcion`, `generar_cargo`, `registrar_pago`, `cancelar_cargo`, `calcular_estado`, `resumen_cartera`.

### Task 2: API de plataforma y de la tienda

**Files:** Create `app/modules/suscripciones/router.py` · Modify `app/main.py`, `app/routers/platform/organizations.py` (PUT refleja el plan; cascada del borrado forzado) · Test `tests/test_suscripciones_api.py`

- [ ] Pruebas: permisos (SUPPORT, cajera, gerente, otra tienda), totales de la lista, bitácora, borrado forzado.
- [ ] Routers `plataforma` y `tienda`; montaje en `app/main.py`.
- [ ] Cascada: `suscripcion_pagos` → `suscripcion_cargos` → `suscripciones`.

### Task 3: Tienda — pestaña "Mi plan y pagos"

**Files:** Create `frontend/src/api/suscripciones.ts`, `frontend/src/pages/pos/configuracion/PlanYPagosTab.tsx` · Modify `frontend/src/pages/pos/Configuracion.tsx` · Test vitest de la pestaña

- [ ] Pestaña `plan` visible solo para ADMINISTRADOR/DUEÑO; tokens `dax-*`; `ListaTarjetas` en teléfono.

### Task 4: Plataforma — "Suscripciones" y sección en el detalle

**Files:** Create `frontend/src/pages/platform/PlatformSuscripciones.tsx`, `frontend/src/pages/platform/org/SeccionSuscripcion.tsx` · Modify `platformNav.ts`, `App.tsx`, `PlatformOrgDetail.tsx` · Test vitest de la página

- [ ] Lista con totales y filtro; sección con formularios en `ui/Modal`.

### Task 5: Documentación

- [ ] `docs/API_REFERENCE.md`, `docs/DATA_MODEL.md`, `docs/FRONTEND_VIEWS.md`.

---

## Segunda versión (fuera de este plan)

| Pieza | Diseño previsto | Decisión pendiente del dueño |
|---|---|---|
| **Pasarela** | Interfaz `PasarelaCobro` (`crear_cliente`, `cobrar(cargo)`, `interpretar_webhook`) con una implementación por proveedor, como los modelos del agente. `suscripcion_pagos.origen` distingue `manual` de la pasarela. | Qué proveedor (Stripe, Conekta, Mercado Pago, Openpay…) y si se guarda tarjeta. |
| **Webhooks idempotentes** | `POST /api/webhooks/cobro/{proveedor}` con firma verificada; el pago se inserta con `id_externo` y el único `(origen, id_externo)` descarta la repetición. Reintentos de cobro con tope. | Cuántos reintentos y cada cuánto. |
| **Suspensión** | Columna `dias_gracia` (por organización, con valor por omisión global) y bandera `suspension_automatica` apagada de fábrica. Tarea diaria: `vencida` + gracia agotada → `suspendida` → solo lectura. Depende de que `organization.is_active` corte de verdad (F0). Nunca borra nada. | Cuántos días de gracia; qué puede hacer una tienda suspendida. |
| **Avisos** | Banner (`AnnouncementBanner`) y correo a `correo_facturacion` N días antes y al vencer. | Cuántos días antes; texto. |
| **CFDI** | Al marcar `pagado` se emite con `rfc`/`razon_social`/`correo_facturacion`; faltan régimen fiscal, código postal y uso de CFDI. | Si se emite, con qué PAC, y si es por pago o global. |
| **Cambio de plan por la tienda** | La dueña pide subir o bajar desde "Mi plan y pagos"; plataforma aprueba. | Prorrateo: hoy no hay; el cambio aplica al siguiente cargo. |
| **Cargos automáticos** | Tarea diaria que genera el cargo N días antes de `proxima_renovacion` (el servicio ya es idempotente). | Cuántos días antes. |
