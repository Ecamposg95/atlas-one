# Cliente en el POS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** La cajera pone el cliente (CRM o nombre libre) desde el carrito; el nombre viaja en la venta, se imprime en el ticket y sobrevive a pausar/reanudar.

**Architecture:** Backend: un bloque en `create_sale` rellena `customer_name` desde el cliente cuando solo llega `customer_id`; el ticket imprime una línea `Cliente:`. Frontend: helper puro `customerPayload.ts` para el payload y el snapshot de pausa; `CustomerModal` (nuevo) montado desde `CartPanel`; `CustomerSelector.tsx` se elimina.

**Tech Stack:** FastAPI + SQLAlchemy (pytest SQLite), React 18 + TS + Zustand (vitest solo para `*.ts` puros).

**Spec:** `docs/superpowers/specs/2026-09-17-cliente-en-pos-design.md`

## Global Constraints

- `app/routers/sales.py::create_sale` es ATS-crítico: solo el bloque descrito en la Tarea 1, sin tocar totales, pagos ni inventario.
- Toda consulta filtra `organization_id`.
- Sin cambios de esquema ni de `railway_init.py`.
- Comentarios y textos de UI en español; el nombre "Público General" no se imprime ni se guarda como cliente.
- Tests: backend `python3 -m pytest -q -p no:warnings --ignore=tests/test_cash_complete.py`; frontend `npx vitest run`, `npx tsc --noEmit`, `npm run build` desde `frontend/`.
- Commits con `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` y `Claude-Session: https://claude.ai/code/session_01Lug2gDi7z3wjW7VJyjctTb`.

---

### Task 1: Backend — nombre desde el cliente y línea `Cliente:` en el ticket

**Files:**
- Modify: `app/routers/sales.py` (justo antes de `# --- 3. Guardar / Actualizar Cabecera ---`, ~línea 823)
- Modify: `app/pos_printer.py` (`_build_header`, después de la "Line 3: date | folio | cashier", ~línea 326)
- Test: `tests/test_sale_customer_name.py` (nuevo), `tests/test_ticket_layout.py` (clase nueva al final)

**Interfaces:**
- Consumes: `SaleCreate.customer_id`, `SaleCreate.customer_name` (ya existen).
- Produces: `sales_documents.customer_name` siempre poblado cuando hay `customer_id` válido; ticket con línea `Cliente: <nombre>`.

- [ ] **Step 1: Test del backend (falla primero)**

```python
# tests/test_sale_customer_name.py
"""El nombre del cliente viaja en la venta.

El POS manda `customer_id` y nunca `customer_name`, así que una venta a un cliente
de CRM quedaba con `customer_name = NULL` y el historial decía "Público general".
Y un nombre libre (sin CRM) debe guardarse tal cual.
"""
from decimal import Decimal

from conftest import _make_product
from app.models.customers import Customer
from app.models.sales import SalesDocument


def _venta(client, headers, sku, **extra):
    body = {
        "items": [{"sku": sku, "quantity": 1, "unit_price": 10}],
        "payments": [{"method": "CASH", "amount": 10}],
        "doc_type": "SALE",
    }
    body.update(extra)
    return client.post("/api/sales/", json=body, headers=headers)


def test_customer_id_sin_nombre_rellena_el_nombre(client, auth_admin, db, org, branch_a):
    _make_product(db, org, "Pluma", "SKU-CLI-1", 10.0, branches_active=[(branch_a.id, True)])
    cliente = Customer(name="Patricio Pérez", organization_id=org.id)
    db.add(cliente); db.flush()
    r = _venta(client, auth_admin, "SKU-CLI-1", customer_id=cliente.id)
    assert r.status_code == 200, r.text
    doc = db.query(SalesDocument).filter(SalesDocument.customer_id == cliente.id).one()
    assert doc.customer_name == "Patricio Pérez"


def test_nombre_libre_se_guarda_sin_cliente(client, auth_admin, db, org, branch_a):
    _make_product(db, org, "Pluma", "SKU-CLI-2", 10.0, branches_active=[(branch_a.id, True)])
    r = _venta(client, auth_admin, "SKU-CLI-2", customer_name="  Sr. Estadounidense ")
    assert r.status_code == 200, r.text
    doc = db.query(SalesDocument).filter(SalesDocument.customer_name.isnot(None)).order_by(SalesDocument.created_at.desc()).first()
    assert doc.customer_id is None
    assert doc.customer_name == "Sr. Estadounidense"


def test_nombre_explicito_gana_sobre_el_del_cliente(client, auth_admin, db, org, branch_a):
    _make_product(db, org, "Pluma", "SKU-CLI-3", 10.0, branches_active=[(branch_a.id, True)])
    cliente = Customer(name="Registrado", organization_id=org.id)
    db.add(cliente); db.flush()
    r = _venta(client, auth_admin, "SKU-CLI-3", customer_id=cliente.id, customer_name="Como lo dijo la cajera")
    assert r.status_code == 200, r.text
    doc = db.query(SalesDocument).filter(SalesDocument.customer_id == cliente.id).one()
    assert doc.customer_name == "Como lo dijo la cajera"
```

Si `Customer` necesita más campos obligatorios (revisa `app/models/customers.py` o `app/modules/customers/models.py`), agrégalos en el test con valores mínimos.

- [ ] **Step 2: Correr y ver fallar**

Run: `python3 -m pytest -q -p no:warnings tests/test_sale_customer_name.py`
Expected: FAIL en el primero (`customer_name is None`) y posiblemente en el segundo (espacios).

- [ ] **Step 3: Implementar en `create_sale`**

Justo antes del comentario `# --- 3. Guardar / Actualizar Cabecera ---`:

```python
    # --- 2b. Nombre del cliente ---
    # El POS manda `customer_id` y no el nombre: sin esto la venta quedaba con
    # `customer_name = NULL` y el historial y el ticket decían "Público general"
    # aunque el cliente estuviera en CRM. Un nombre explícito (libre o el que
    # eligió la cajera) gana; solo se rellena cuando viene vacío.
    nombre_cliente = (sale_in.customer_name or "").strip() or None
    if nombre_cliente is None and sale_in.customer_id:
        _cli = db.query(Customer.name).filter(
            Customer.id == sale_in.customer_id,
            Customer.organization_id == org_id,
        ).first()
        if _cli and _cli[0]:
            nombre_cliente = _cli[0].strip() or None
```

Y en las dos asignaciones existentes (`sales_doc.customer_name = sale_in.customer_name` y `customer_name=sale_in.customer_name` en el constructor) usa `nombre_cliente` en vez de `sale_in.customer_name`. Nada más cambia en el archivo.

- [ ] **Step 4: Test del ticket (falla primero)**

Al final de `tests/test_ticket_layout.py`:

```python
class TestClienteEnEncabezado:
    def test_imprime_cliente_cuando_hay_nombre(self):
        sale = _make_sale([_line("Playera", 1, 100)])
        sale.customer_name = "Patricio Pérez"
        decoded = _decode(_build(sale))
        assert "Cliente: Patricio P" in decoded  # latin-1 conserva la é; se busca el prefijo por si el ancho recorta

    def test_no_imprime_publico_general(self):
        sale = _make_sale([_line("Playera", 1, 100)])
        sale.customer_name = " público general "
        decoded = _decode(_build(sale))
        assert "Cliente:" not in decoded

    def test_sin_nombre_no_agrega_linea(self):
        sale = _make_sale([_line("Playera", 1, 100)])
        sale.customer_name = None
        decoded = _decode(_build(sale))
        assert "Cliente:" not in decoded
```

`_make_sale` en ese archivo ya pone `customer_name="Cliente Test"`; revisa que las pruebas existentes no cuenten líneas del encabezado de forma que la nueva línea las rompa (si alguna cuenta líneas, ajústala y explica en el reporte).

- [ ] **Step 5: Implementar en `_build_header`**

Después de escribir `line3` y antes del `return raw`:

```python
        # Line 4 (opcional): cliente. "Público General" es el valor por defecto
        # del historial, no un cliente: no se imprime.
        cliente = (getattr(sale, "customer_name", None) or "").strip()
        if cliente and cliente.casefold() != "público general":
            raw += (self._truncate(f"Cliente: {cliente}", self.cols) + "\n").encode("latin-1", "replace")
```

- [ ] **Step 6: Suite completa y commit**

Run: `python3 -m pytest -q -p no:warnings --ignore=tests/test_cash_complete.py`
Expected: todo verde (baseline: 862 passed, 2 skipped, 3 xfailed + los nuevos).

```bash
git add app/routers/sales.py app/pos_printer.py tests/test_sale_customer_name.py tests/test_ticket_layout.py
git commit -m "feat(pos): la venta guarda el nombre del cliente y el ticket lo imprime"
```

---

### Task 2: Frontend — helper de payload, pausa/reanudar y envío de `customer_name`

**Files:**
- Create: `frontend/src/pages/pos/customerPayload.ts`
- Test: `frontend/src/pages/pos/__tests__/customerPayload.test.ts`
- Modify: `frontend/src/pages/pos/POS.tsx` (payload del cobro ~línea 222; `parkSale` ~línea 361; reanudar ~líneas 424-440)

**Interfaces:**
- Consumes: `usePOSStore` (`customerId`, `customerName`, `setCustomer(id, name)`), `parkedTicketsApi.park(cartJson, customer_id, notes)`.
- Produces: `customerFields(customerId, customerName)` y `customerFromCartJson(cartJson, parkedCustomerId)`.

- [ ] **Step 1: Test (falla primero)**

```ts
// frontend/src/pages/pos/__tests__/customerPayload.test.ts
import { describe, it, expect } from 'vitest'
import { customerFields, customerFromCartJson } from '../customerPayload'

describe('customerFields', () => {
  it('sin cliente no manda ninguna llave', () => {
    expect(customerFields(null, null)).toEqual({})
    expect(customerFields(null, '   ')).toEqual({})
  })
  it('nombre libre viaja recortado y sin customer_id', () => {
    expect(customerFields(null, '  Sr. Estadounidense ')).toEqual({ customer_name: 'Sr. Estadounidense' })
  })
  it('cliente de CRM manda id y nombre', () => {
    expect(customerFields(7, 'Patricio Pérez')).toEqual({ customer_id: 7, customer_name: 'Patricio Pérez' })
  })
  it('cliente de CRM sin nombre en memoria manda solo el id', () => {
    expect(customerFields(7, null)).toEqual({ customer_id: 7 })
  })
})

describe('customerFromCartJson', () => {
  it('restaura nombre libre guardado al pausar', () => {
    expect(customerFromCartJson({ customer_name: 'Patricio' }, null)).toEqual({ id: null, name: 'Patricio' })
  })
  it('restaura id del parked y nombre del snapshot', () => {
    expect(customerFromCartJson({ customer_name: 'Ana' }, 3)).toEqual({ id: 3, name: 'Ana' })
  })
  it('sin nada devuelve null', () => {
    expect(customerFromCartJson({}, null)).toBeNull()
    expect(customerFromCartJson({ customer_name: 42 }, null)).toBeNull()
  })
})
```

- [ ] **Step 2: Implementar el helper**

```ts
// frontend/src/pages/pos/customerPayload.ts
/**
 * Cliente de la venta, tal como viaja al backend y al snapshot de pausa.
 *
 * El POS mandaba solo `customer_id`, así que hasta una venta con cliente de
 * CRM se guardaba sin nombre y el historial decía "Público general". El nombre
 * libre (sin CRM) va en `customer_name` con `customer_id` ausente.
 */
export interface CustomerFields {
  customer_id?: number
  customer_name?: string
}

export function customerFields(customerId: number | null, customerName: string | null): CustomerFields {
  const out: CustomerFields = {}
  if (customerId != null) out.customer_id = customerId
  const name = (customerName ?? '').trim()
  if (name) out.customer_name = name
  return out
}

/** Cliente guardado en `cart_json` al pausar; `parkedCustomerId` viene aparte en el ticket. */
export function customerFromCartJson(
  cartJson: Record<string, unknown>,
  parkedCustomerId: number | null,
): { id: number | null; name: string | null } | null {
  const raw = cartJson.customer_name
  const name = typeof raw === 'string' && raw.trim() ? raw.trim() : null
  if (parkedCustomerId == null && !name) return null
  return { id: parkedCustomerId ?? null, name }
}
```

Run: `npx vitest run src/pages/pos/__tests__/customerPayload.test.ts` → PASS.

- [ ] **Step 3: Usarlo en `POS.tsx`**

En el payload del cobro sustituye `customer_id: store.customerId ?? undefined,` por `...customerFields(store.customerId, store.customerName),`.

En `parkSale`, el `cartJson` que se manda a `parkedTicketsApi.park` debe incluir `customer_name: store.customerName?.trim() || undefined` (busca dónde se arma `cartJson`, junto a `items`, `requires_invoice`, `global_discount`).

En reanudar, reemplaza el bloque `if (parked.customer_id) { … store.setCustomer(parked.customer_id, null) }` por:

```ts
      const cliente = customerFromCartJson(cartJson, parked.customer_id ?? null)
      if (cliente) store.setCustomer(cliente.id, cliente.name)
```

Verifica que la cola offline reenvía el mismo payload (no toca nada: `customer_name` es un campo más del JSON).

- [ ] **Step 4: Verificar y commit**

Run desde `frontend/`: `npx vitest run && npx tsc --noEmit`
Expected: verde.

```bash
git add frontend/src/pages/pos/customerPayload.ts frontend/src/pages/pos/__tests__/customerPayload.test.ts frontend/src/pages/pos/POS.tsx
git commit -m "feat(pos): el cobro y la pausa llevan el nombre del cliente"
```

---

### Task 3: Frontend — botón Cliente en el carrito y `CustomerModal`

**Files:**
- Create: `frontend/src/components/pos/modals/CustomerModal.tsx`
- Modify: `frontend/src/components/pos/CartPanel.tsx` (header ~líneas 313-343 y bloque "Cliente" ~líneas 343-352)
- Modify: `frontend/src/pages/pos/POS.tsx` (nada nuevo si `CartPanel` abre el modal solo; ver Step 2)
- Delete: `frontend/src/components/pos/CustomerSelector.tsx` (código muerto: nadie lo importa; confirma con grep antes de borrar)

**Interfaces:**
- Consumes: `customersApi.search(q)`, `customersApi.create({ name, phone? })` de `frontend/src/api/customers.ts`; `usePOSStore().setCustomer(id, name)`.
- Produces: `<CustomerModal open onClose />` autocontenido (lee y escribe el store él mismo).

- [ ] **Step 1: `CustomerModal.tsx`**

Sigue el patrón visual de los otros modales de `frontend/src/components/pos/modals/` (velo `fixed inset-0 z-50`, tarjeta `dax-card`, botones `dax-btn-primary`/`dax-btn-secondary`, inputs `dax-input`, tokens `var(--dax-*)`; nada de `text-white`/`slate-*` fijos). Comportamiento:

- Un solo input con `autoFocus`, placeholder "Nombre o teléfono del cliente". Al escribir (debounce 300 ms) llama `customersApi.search(q)`; si falla, muestra en pequeño "Sin acceso a clientes; puedes usar solo el nombre" y sigue funcionando.
- Lista de resultados (nombre + teléfono); clic → `setCustomer(c.id, c.name)` y cierra.
- Pie con dos botones, ambos habilitados solo con texto no vacío: **"Usar solo el nombre"** → `setCustomer(null, texto.trim())` y cierra; **"Guardar en clientes"** → muestra un campo Teléfono opcional y un botón "Crear" que llama `customersApi.create({ name, phone })`, luego `setCustomer(c.id, c.name)` y cierra; si crear falla, muestra el error y deja el botón "Usar solo el nombre" disponible.
- `Escape` cierra; clic en el velo cierra.
- Si ya hay cliente en el store al abrir, el input arranca con ese nombre y hay un botón "Quitar cliente" → `setCustomer(null, null)` y cierra.

- [ ] **Step 2: Montarlo desde `CartPanel`**

- Estado local `const [clienteAbierto, setClienteAbierto] = useState(false)`.
- En el header, a la izquierda de "Pausar", un botón siempre visible (aunque el carrito esté vacío) con icono `fa-user-plus` y texto "Cliente" cuando no hay `customerName`; con cliente, el bloque existente de "Cliente — solo visible cuando hay uno seleccionado" se mantiene, pero el nombre se vuelve botón que reabre el modal (mismo `min-h-[44px]`), y la "x" sigue llamando `onClearCustomer`.
- Renderiza `{clienteAbierto && <CustomerModal onClose={() => setClienteAbierto(false)} />}` al final del panel.
- Respeta `sessionLocked`: el botón Cliente funciona aunque no haya caja abierta (no cobra nada).

- [ ] **Step 3: Borrar `CustomerSelector.tsx`**

`grep -rn CustomerSelector frontend/src` debe devolver solo su propio archivo antes de borrarlo. Si algo lo importa, no lo borres y explícalo en el reporte.

- [ ] **Step 4: Verificar y commit**

Run desde `frontend/`: `npx vitest run && npx tsc --noEmit && npm run build`
Expected: verde, sin warnings nuevos de imports sin usar.

```bash
git add frontend/src/components/pos/modals/CustomerModal.tsx frontend/src/components/pos/CartPanel.tsx
git rm frontend/src/components/pos/CustomerSelector.tsx
git commit -m "feat(pos): botón Cliente en el carrito con búsqueda, alta rápida o nombre libre"
```
