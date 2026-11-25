# Agente A1 · Consultas por rol — Implementation Plan

**Goal:** Cajera, vendedor, gerente, administrador y dueño le preguntan al agente por precios, existencias, ventas, conteos y valor de inventario, y cada quien recibe solo lo que su rol y su sucursal le permiten ver. Nada se escribe.

**Architecture:** Un motor (`app/modules/ai/motor.py`) con bucle de herramientas sobre la interfaz `Proveedor` de A0. Una tabla declarativa rol → herramientas (`matriz.py`); `definiciones(ctx)` entrega al modelo solo las del rol y `ejecutar` rechaza cualquier otra aunque el modelo la nombre. Organización y sucursal salen de la sesión. Todo texto de catálogo entra al modelo dentro de `<datos_tienda>` y saneado. Endpoints en `/api/ai/conversaciones`. En pantalla, un panel de chat perezoso que abre un botón de la barra y otro en Consultar.

**Tech Stack:** FastAPI + SQLAlchemy (pytest, SQLite en memoria, `ProveedorFalso`) · React + TS (vitest).

**Spec:** `docs/superpowers/specs/2026-11-24-megaplan-pendientes-y-agente-design.md` §2 y §5; `2026-10-18-sp4-asistente-ia-design.md` (tablas y bucle).

## Global Constraints

- **Solo lectura.** Ninguna herramienta cambia datos; `proponer_cambio` y `sugerir_sku` son de A2 (registradas o no, ningún rol las recibe).
- **Superadministrador y soporte fuera** (A4): 403 en los endpoints.
- Organización = `exigir_modulo_ai`; sucursal = `user.branch_id`. Solo administrador y dueño pueden nombrar `sucursal_id`, y se valida contra la organización.
- Sin llamadas a modelos reales en la suite. Sin streaming.
- `ai` sigue `en_construccion`: el botón respeta esa regla; se ve en desarrollo con `VITE_AGENTE_PREVIA=1` o `localStorage['atlas.agente.previa']='1'`.
- Reglas únicas que se consumen, no se reescriben: `ventas_cajero.py` (cajera: hoy, su sucursal, conteo ciego), `metricas_ventas.py` (qué es venta), `query_visible_products` (qué producto ve cada quien), `precio_sucursal.py` (precio que cobra la sucursal), `reports_valuacion.py` (valor), `conteos/services.py` (avance).

## Matriz

| Herramienta | Cajera, vendedor | Gerente | Administrador, dueño |
|---|---|---|---|
| `buscar_producto` | precio de su sucursal, sin costo | + costo y margen | + sucursal a elegir |
| `consultar_existencias` | su sucursal | su sucursal | toda la empresa o una sucursal |
| `disponibilidad_otras_sucursales` | hay / no hay | con cantidades | — (usa `consultar_existencias`) |
| `mis_ventas_hoy` | sí (sin importes con conteo ciego) | — | — |
| `resumen_ventas` | — | su sucursal | empresa o sucursal |
| `estado_conteos` | — | su sucursal | empresa o sucursal |
| `stock_bajo` | — | su sucursal | empresa o sucursal |
| `listar_departamentos`, `listar_marcas` | — | sí | sí |
| `comparar_sucursales` | — | — | sí |
| `valor_inventario` | — | — | sí |

## Tareas

- [ ] **T1 Matriz y despachador.** `matriz.py` (`HERRAMIENTAS_POR_ROL`, `perfil_de`, `herramientas_de`); `herramientas.definiciones(ctx)` y `ejecutar` con rechazo por rol; `sucursal_id` solo aparece en el esquema de administrador y dueño.
- [ ] **T2 Datos como datos.** `datos.py`: `dato()` (sanea texto de catálogo) y `envolver()` (`<datos_tienda>…</datos_tienda>`); regla fija en `prompts/base.md`.
- [ ] **T3 Herramientas de catálogo.** `buscar_producto` con precio de sucursal (`precios_de_sucursal`), costo y margen por perfil; `consultar_existencias` sobre `query_visible_products` + `is_active_pos`; `disponibilidad_otras_sucursales`.
- [ ] **T4 Herramientas de operación.** `herramientas_operacion.py`: `mis_ventas_hoy`, `resumen_ventas`, `comparar_sucursales`, `estado_conteos`, `stock_bajo`, `valor_inventario`. Cada una arma además una tabla pequeña para la pantalla.
- [ ] **T5 Prompt por rol.** `base.md` de consultas; la caja no recibe sucursales, marcas, departamentos ni convenciones de alta; nombres delimitados.
- [ ] **T6 Motor.** `responder(db, ctx, conversacion, mensaje)`: cupo → proveedor (`consulta`) → historial acotado → bucle (tope 6) → registro de consumo con rol. Columnas `ai_messages.nativo` y `ai_messages.tablas` (+ ALTER idempotente).
- [ ] **T7 Endpoints.** Crear, listar, leer, enviar mensaje y borrar conversación; 404 para la ajena, 503 sin llave, 429 sin cupo.
- [ ] **T8 Pruebas de servidor.** Matriz por rol, fugas de costo y cantidades, aislamiento entre organizaciones, gerente confinado, precio por sucursal, conteo ciego, inyección por nombre, cupo, conversación ajena.
- [ ] **T9 Panel de chat.** `api/ai.ts`, `components/ai/PanelAgente.tsx` (perezoso, sobre `ui/Modal`), `BotonAgente` en el menú lateral y en la barra del teléfono, `agenteVisible` con su prueba.
- [ ] **T10 Consultar.** Botón "Preguntar al agente" en `StoreScanner` que abre el panel con lo escrito.
- [ ] **T11 Documentación.** `docs/ai/README.md`, `docs/API_REFERENCE.md`, `docs/FRONTEND_VIEWS.md`.

## Fuera de alcance

Escrituras y propuestas (A2), `buscar_ventas` por folio o cliente (A3), panel de plataforma (A4), WhatsApp, voz y avisos (A5), streaming, destapar el módulo `ai`.
