# Gastro — Mesas & Comandas

> Operación de restaurante en Atlas One Gastro (`ATLAS_ONE_RESTAURANT`): plano de
> mesas premium + vista móvil donde el mesero levanta comandas y las manda a cocina.
> Estado: **en producción en `staging`** (desde 2026-07-02).
> Origen: [spec](../superpowers/specs/2026-07-02-gastro-mesas-comandas-design.md) ·
> [plan](../superpowers/plans/2026-07-02-gastro-mesas-comandas.md).

---

## 1. Qué resuelve

Un restaurante necesita tres cosas que el POS base no cubre solo:

1. Ver el **estado del salón** de un vistazo (qué mesa está libre/ocupada, cuánto
   lleva abierta, cuánto va de cuenta, quién la atiende).
2. Que el **mesero levante la comanda** desde el celular y llegue a la cocina.
3. Que esos platillos se **acumulen en la cuenta** para que el cajero cobre sin
   recapturar nada.

## 2. Actores y roles

| Rol | Dónde opera | Qué hace |
|---|---|---|
| **VENDEDOR** (mesero) | `/mobile/comanda` (celular) | Abre mesas, levanta comandas, las envía a cocina, pide la cuenta. |
| **CAJERO / GERENTE / ADMIN** | `/tables` (desktop/tablet) + POS | Ve el plano premium, cobra la cuenta en POS (la mesa se libera sola al pagar). |
| **Cocina** | `/kitchen` (KDS) | Recibe las comandas (tickets) y las despacha. |

> No existe un rol `MESERO`: **VENDEDOR** cumple esa función. La mesa guarda al
> mesero que la abrió en `server_user_id`.

## 3. Rutas (frontend)

| Ruta | Pantalla | Componente |
|---|---|---|
| `/tables` | Mesas premium (plano + KPIs) | `pages/tables/FloorPlan.tsx` |
| `/mobile/comanda` | "Mis mesas / Todas" (táctil) | `pages/mobile/ComandaTables.tsx` |
| `/mobile/comanda/:tableId` | Comanda de la mesa (menú + enviar) | `pages/mobile/ComandaOrder.tsx` |
| `/kitchen` | KDS (display de cocina) | `pages/kitchen/KDS.tsx` |

Acceso del mesero: enlace **"Comanda"** en `pages/mobile/MobileDashboard.tsx`.

## 4. Endpoints (backend)

| Método | Endpoint | Uso |
|---|---|---|
| `POST` | `/api/tables/{id}/open` | Abre la mesa → crea la cuenta (`ParkedTicket`), la marca `OCCUPIED`, fija `server_user_id`/`opened_at`. |
| `POST` | `/api/tables/{id}/free` | Libera la mesa. |
| `PATCH` | `/api/tables/{id}/status` | Cambia estado (p.ej. `BILL_REQUESTED` = "pidió cuenta"). |
| `POST` | `/api/kitchen/tickets` | Dispara la comanda al KDS (`items[]`, `table_id`, `parked_ticket_id`). |
| `GET` | `/api/kitchen/tickets?branch_id=` | Feed del KDS (usado para el badge "en cocina" del plano). |
| `PATCH` | `/api/sales/parked/{id}` | **Acumula los platillos en la cuenta.** Shallow-merge de `cart_json` (ver §6). |
| `GET` | `/api/sales/parked/{id}` | Lee la cuenta (total = suma de `cart_json.items[].subtotal`). |

## 5. Flujo de datos

```
Mesero abre mesa → POST /tables/{id}/open (crea ParkedTicket = la cuenta)
   → agrega platillos del catálogo de productos → "Enviar a cocina":
        POST /kitchen/tickets      → comanda visible en el KDS
        PATCH /sales/parked/{id}   → platillos sumados a la cuenta
Cajero retoma la cuenta en POS → cobra → Sale creada
        → subscriber free_table_on_sale libera la mesa automáticamente
```

- El **menú** son los **productos** del catálogo (los platillos = productos;
  categorías = departamentos de producto). No hay modelo "menú" aparte.
- El ítem de la cuenta tiene shape **consistente con el POS**:
  `{ product_id, sku, name, price, quantity, discount, subtotal }`.
- La vista móvil separa **"Por enviar"** (borrador local) de **"Enviado a cocina"**.
  El envío maneja falla parcial: si cocina recibe pero la cuenta no persiste,
  avisa de forma accionable y **nunca re-dispara** los mismos platillos.

## 6. Contrato de `PATCH /sales/parked/{id}`

- **Last-write-wins** sobre las llaves que trae el payload (típicamente `items`,
  que el cliente manda ya mergeado = existentes + nuevos).
- **Shallow-merge** de nivel superior: preserva llaves hermanas que el POS guarda
  junto a `items` (`requires_invoice`, `global_discount`).
- Scoped por `organization_id` + `branch_id`; `404` si no existe, `410` si la
  cuenta ya no está `ACTIVE`, `422` si `cart_json` viene vacío.
- **Asume un solo escritor por cuenta.** Si dos meseros editan la misma cuenta en
  paralelo, gana el último PATCH (ver limitaciones).

## 7. Limitaciones conocidas (deferred)

- **Race de lost-update**: dos editores concurrentes de la misma cuenta con
  full-replace → se pierden los ítems no fusionados del otro (ya en cocina) →
  sub-cobro. Mitigado (llaves hermanas) y documentado; el fix completo
  (concurrencia optimista / append en servidor) queda pendiente de decisión.
- **Sin role-gate** en las rutas `/mobile/comanda` (el backend sí queda
  org/branch-scoped). Dejado abierto a propósito para no bloquear pruebas con
  usuarios admin.
- **N+1** en el plano: `FloorPlan.load()` pide una cuenta por mesa ocupada. OK a
  escala de demo; un endpoint batch es el fix eventual.
- **Fase 2 (pendiente)**: plano del salón **arrastrable** con `pos_x/pos_y`.

## 8. Probar

> El entorno `staging` de Railway (`atlas-bos-staging`) que alimentaba esta demo se
> eliminó el 2026-07-28 y la rama `staging` se fusionó a `main` el 2026-09-22 — no hay
> URL demo pública hoy. Prueba localmente (`docker compose up -d` + `npm run dev`, ver
> `README.md` raíz) o contra una organización con el preset gastro habilitado en
> producción.

Datos de ejemplo (si el seed local aún los siembra):

```
usuario: demo_restaurant   PIN: demo1234
org:     Demo Atlas One Restaurant (ATLAS_ONE_RESTAURANT)
```

- Desktop → `/tables` (plano premium).
- Celular → `/mobile/comanda` (o vista móvil de devtools).

Tests: `tests/test_parked_update.py` (endpoint) y `tests/test_comanda_flow_e2e.py`
(flujo abrir → comanda → KDS → cuenta).
