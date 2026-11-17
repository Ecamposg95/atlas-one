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

---

## Anexo 2026-11-14 — Tema full black y nuevo login (aprobado por el usuario)

### Tema oscuro full black
"Full black, el más oscuro será el nav bar, el body un poco menos." Sidebar y barra superior en negro puro; fondo `#0a0a0a`; superficies un poco más claras; todo neutro, sin tinte índigo. Modo claro del contenido sin cambios.

### Login: la distribución del ejemplo del usuario + la identidad de atlasone.com.mx
Decisión del usuario: "combina". El ejemplo (imagen) aporta la distribución: fondo negro, saludo a la izquierda, formulario siempre visible a la derecha en tarjeta. El sitio atlasone.com.mx aporta la identidad:
- Paleta del sitio: añil `#16345F`, añil claro `#24548F`, cal `#F4F0E4`, maíz `#F0B429`, jamaica `#C42B33`, jade `#0F7B5F`, papel `#FBFAF6`, tinta `#14120F`.
- Letras: títulos en **Archivo Black** (Google Fonts, cargada solo en el login), cejilla en IBM Plex Mono mayúsculas con raya maíz, texto en IBM Plex Sans.
- Botón fuerte: fondo maíz, texto añil hondo `#0D2140`, radio 2px, sombra sólida `5px 5px 0` jamaica; hover se desplaza `-2px` y la sombra crece a `7px`.
- Firma visual: el ticket térmico en CSS (papel, borde de sierra con `mask`, Plex Mono, código de barras con `repeating-linear-gradient`), girado ~-1.4°, asomándose detrás de la tarjeta. Sustituye al listón 3D del ejemplo (no se copia).

Contenido:
- Fondo negro `#000` con brillos radiales tenues añil y jade (como `.heroe::before` del sitio, sobre negro).
- Arriba: marca "ATLAS·ONE" (el punto en maíz) con `AtlasMark`.
- Izquierda: cejilla `Software de operación`; titular `Un punto de venta por` + `<em>cada giro.</em>` (em en maíz con raya jamaica); entrada `Atlas ONE llega configurado para tu negocio.`; enlace `Conoce Atlas ONE →` a `https://atlasone.com.mx`.
- Derecha: tarjeta negra semitransparente (borde fino cal al 14 %, radio 2px), título `Entra a tu tienda`, Usuario, Contraseña con ojo, error, botón `Entrar`.
- Pie: `Atlas ONE — Atlas Tech`.
- Sin redes sociales (el sitio no tiene).
- Se van: auroras, arco giratorio, mensajes rotativos, el botón que revela el formulario. El formulario se ve desde el inicio.
- Teléfono (< 768 px): marca + titular corto + formulario; sin ticket.
- Se conserva toda la lógica de `handleSubmit` (login, `setAuth`, `setBranch`, redirección por rol, errores).
