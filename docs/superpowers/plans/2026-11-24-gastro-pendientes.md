# Gastro: pendientes

Fecha: 2026-11-24. Estado: pendiente, sin fecha. Sale del megaplan [`../specs/2026-11-24-megaplan-pendientes-y-agente-design.md`](../specs/2026-11-24-megaplan-pendientes-y-agente-design.md) por decisión del dueño.
Origen: `specs/2026-06-29-gastro-suite-initiative-design.md` (GS-0 a GS-8), revisado contra el código de `origin/main` (79cb8eb0) por lectura; reconfirmar al arrancar cada tanda.

## Qué está hecho

| Fase | Estado | Evidencia |
|---|---|---|
| GS-0 recetas | Parcial: CRUD, costo y descuento de insumos por evento | `app/modules/recipes/`, `app/subscribers/recipes.py` |
| GS-1 operación de restaurante | Hecho: mesas (13 endpoints), cocina (16), modificadores en KDS | `app/modules/tables/`, `app/modules/kitchen/` |
| GS-2 pantallas de restaurante | Hecho en versión propia: plano, KDS, comanda móvil, menú visual, reporte de meseros | `pages/tables/FloorPlan.tsx`, `pages/mobile/Comanda*.tsx` |
| GS-3 bar, servidor | Parcial: botellas, servidos, merma y bitácora con varianza | `app/modules/bar/` |
| GS-4 a GS-8 | Sin construir | — |

## Qué falta, en tandas

**Tanda 1: cerrar restaurante**
- Merma: el modelo `WasteLog` existe sin endpoints ni pantalla.
- Margen por ticket y por platillo.
- Plano de mesas arrastrable (`pos_x`/`pos_y` ya están en el modelo).
- Menú separado del catálogo.
- Responsivo de `Recipes`, `RecipeForm`, `FloorPlan`, `KDS`, `Meseros`, `Botellas`, `MenuVisual` y `GastroHomeDay`.
- Modo básico para vistas gastro.
- Hallazgo abierto: los suscriptores de `recipes` y `tables` no se registran para todas las organizaciones que deberían (auditoría de presets §12; no verificado a fondo).
- `quotes convert-to-sale` no descuenta insumos ni libera mesa (lo cierra F0 del megaplan).

**Tanda 2: bar y café**
- Bar: promociones por horario, corte nocturno, inicio en tema oscuro, POS de coctelería (GS-3, GS-4).
- Café: panel de modificadores, cola de barista, inicio de café (GS-5).

**Tanda 3: abasto**
- Entidad Proveedor (`supplier_name` hoy es texto en `app/models/finance.py:73`).
- Compras y reabasto (GS-6). Es el mismo módulo `purchasing` que el megaplan lista en F5; se construye una sola vez.
- Reglas de abasto configurables (hoy fijas en `app/subscribers/abasto.py:11`).

**Tanda 4: suite**
- Roles MESERO, BARISTA, BARTENDER y COCINA (GS-8).
- Rentabilidad por concepto entre sucursales (GS-7).
- Prueba con vencimiento y asistente de arranque del piloto (GS-8). La prueba con vencimiento se apoya en el cobro de suscripciones (F3 del megaplan).

## Relación con el megaplan

- Presets: mientras gastro siga pendiente, F2 decide qué presets gastro quedan disponibles (Restaurant, sí; Café y Bar, en preparación) y retira el preset "Gastro (legacy)".
- Agente: las herramientas de recetas, mesas y cocina no entran en las fases A0 a A5.

## Preguntas abiertas

1. ¿Hay cliente esperando alguna tanda? Sin eso no tiene fecha.
2. ¿Bar y café van juntos o se separa café, que es más chico?
3. ¿Los roles de mesero y cocina se necesitan antes que bar?
