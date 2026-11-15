# Ventas del día para el CAJERO — diseño

**Fecha:** 2026-11-14 · **Rama:** `feat/cajero-ventas-del-dia` · **Tamaño:** cambio chico (diseño corto)
**Contexto:** primer paso de "robustecer GERENTE (super-cajero) y simplificar la interfaz del CAJERO"
(`docs/audits/cajero-visibility/00-policy.md`). El GERENTE se trabaja después, en su propio diseño.

## Intención

La cajera solo debe ver la venta del día actual, no el histórico, en una pantalla de Ventas más simple.
Además, la pantalla de hoy le enseña totales del día y desglose por método, lo que le permite calcular
el esperado de caja y anula el conteo ciego de `fix/pendientes-2026-11-10`.

## Decisiones (aprobadas por el usuario 2026-11-14)

1. **Solo CAJERO.** GERENTE conserva el histórico de su sucursal tal como está hoy. ADMINISTRADOR/DUEÑO sin cambios.
2. **"Hoy" = día calendario de México** (`metricas_ventas.hoy_mx()`). A medianoche la lista se vacía aunque el turno siga abierto.
3. **Toda la sucursal**, no solo las ventas que cobró ella (para devolver un ticket de otra cajera del mismo día).
4. **Sin totales del día:** fuera los 6 KPIs (total, transacciones, ticket promedio, método principal, devoluciones, hora pico). Cada ticket sí muestra su importe.
5. **Sin** filtros de periodo, fechas, selector de sucursal, ni "incluir abiertos". Queda el buscador de folio o cliente.
6. **Acciones por ticket:** Ver, Reimprimir (con el PIN existente), WhatsApp, Devolver.
7. **Devoluciones de días anteriores las hace GERENTE/DUEÑO/ADMINISTRADOR.** La cajera solo inicia devoluciones de tickets de hoy de su sucursal.
8. **Candado en el servidor**, no solo en la pantalla.

## Cambios

### Backend
- `GET /api/sales/` (`app/routers/sales.py::read_sales`): si el rol es CAJERO, ignora `start_date`/`end_date`/`branch_id` y fuerza su sucursal + día de hoy MX. Aplica también a `folio_search` (Devoluciones busca por folio con esta consulta).
- `GET /api/sales/stats`: CAJERO recibe **403** (nadie en su pantalla lo necesita ya).
- `GET /api/sales/{sale_id}` y `/{sale_id}/print-view`: CAJERO solo si la venta es de su sucursal y de hoy; si no, 404 (no revelar existencia).
- `POST /api/returns/`: CAJERO solo sobre ventas de su sucursal y de hoy; si no, 403 con `detail` accionable ("Las devoluciones de días anteriores las hace el gerente"). De paso se valida la sucursal para todos los roles branch-scoped (hoy no se valida: hueco).
- Un helper único (p. ej. en `metricas_ventas.py` o `sales.py`) decide "¿esta venta es visible para este cajero?" para no duplicar la regla.
- Tests nuevos en `tests/test_cajero_ventas_del_dia.py`: lista solo de hoy aunque pida otro rango, otra sucursal invisible, stats 403, detalle de ayer 404, devolución de ayer 403, GERENTE sigue viendo ayer.

### Frontend (`pages/sales/SalesHistory.tsx`)
- Si el rol es CAJERO: título "Ventas de hoy · <día>", sin KPIs ni `getStats`, sin presets/fechas/sucursal; buscador y tabla (Folio, Hora, Cliente, Pago, Importe, acciones). Teléfono: mismas tarjetas de hoy.
- Botón Devolver: igual que hoy (ya solo hay tickets de hoy en la lista).
- `Returns.tsx`: si el folio buscado no aparece para la cajera, mensaje "Solo puedes devolver ventas de hoy; para días anteriores pide al gerente".
- Tests en `pages/sales/__tests__/SalesHistory.test.tsx`: la cajera no llama `getStats` ni ve filtros de fecha.

## No-objetivos
- Rediseño del GERENTE (siguiente diseño).
- Cambiar Mi caja, Corte o el POS (lo cubre la rama de conteo ciego).
- Lista de `/returns` de la cajera (histórico de devoluciones): se revisa con el GERENTE.

## Anti-objetivos
- Que la cajera pueda ver o sumar el total del día por cualquier vía (pantalla o API).
- Romper el flujo de devoluciones del gerente o del dueño.

## Enfoques considerados
- **Solo esconder en la pantalla:** rápido, pero la API sigue sirviendo el histórico. Descartado (decisión 8).
- **Pantalla nueva aparte para la cajera:** duplica tabla, acciones y reimpresión. Descartado: se ramifica `SalesHistory` por rol.
- **Elegido:** candado por rol en el servidor + la misma pantalla en versión cajera.

## Para el implementador
- Rol vía enum `Role.CAJERO`, no strings (bug recurrente enum-vs-string).
- `create_sale` no se toca.
- Antes de desplegar: esta rama y `fix/pendientes-2026-11-10` tocan pantallas vecinas; avisar a los dueños que la cajera deja de ver el histórico.
