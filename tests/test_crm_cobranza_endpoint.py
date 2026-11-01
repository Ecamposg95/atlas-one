"""GET /customers/cobranza (spec 2026-10-29 §3.1): quién debe, cuánto, desde
cuándo. Roles de oficina; antigüedad por cargo FIFO; saldo a favor aparte."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from itertools import count

from app.models.modules import Module, OrganizationModule
from app.models.sales import DocumentStatus, SalesDocument
from app.modules.customers.models import Customer, CustomerLedgerEntry

_folios = count(500)


def _habilitar(db, org, *keys):
    for key in keys:
        if db.query(Module).filter(Module.key == key).first() is None:
            db.add(Module(key=key, name=key)); db.flush()
        if db.query(OrganizationModule).filter(
            OrganizationModule.organization_id == org.id,
            OrganizationModule.module_key == key).first() is None:
            db.add(OrganizationModule(organization_id=org.id, module_key=key, is_enabled=True))
    db.commit()


def _hace(dias: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=dias)


def _cliente(db, org, nombre, telefono=None):
    c = Customer(name=nombre, phone=telefono, organization_id=org.id, current_balance=Decimal("0"))
    db.add(c); db.commit(); db.refresh(c)
    return c


def _cargo(db, org, branch, user, cliente, monto, dias_atras):
    """Venta fiada completa (PENDING con cliente) y su cargo, con `dias_atras` de edad."""
    doc = SalesDocument(
        organization_id=org.id, branch_id=branch.id, seller_id=user.id, customer_id=cliente.id,
        folio=next(_folios), series="A", subtotal=Decimal(monto), tax_amount=Decimal("0"),
        total_amount=Decimal(monto), status=DocumentStatus.PENDING, doc_type="ORDER",
    )
    doc.created_at = _hace(dias_atras)
    db.add(doc); db.flush()
    a = CustomerLedgerEntry(customer_id=cliente.id, sales_document_id=doc.id, organization_id=org.id,
                            amount=Decimal(monto), description=f"Venta a crédito #{doc.folio}")
    a.created_at = doc.created_at
    cliente.current_balance = Decimal(str(cliente.current_balance)) + Decimal(monto)
    db.add(a); db.commit()
    return doc


def _abono(db, org, cliente, monto, dias_atras):
    a = CustomerLedgerEntry(customer_id=cliente.id, organization_id=org.id, amount=-Decimal(monto),
                            description="PAGO RECIBIDO: CASH")
    a.created_at = _hace(dias_atras)
    cliente.current_balance = Decimal(str(cliente.current_balance)) - Decimal(monto)
    db.add(a); db.commit()


def _escenario(db, org, branch_a, branch_b, cajero_a):
    """Ana: 100 hace 45 días, abonó 30 hace 10 → debe 70 (31_60). Beto: 80 hoy
    en la sucursal B. Carla: solo un abono de 20 → a favor. Dora: 10 y lo pagó."""
    _habilitar(db, org, "crm")
    ana = _cliente(db, org, "Ana Pérez", "55 1234 5678")
    _cargo(db, org, branch_a, cajero_a, ana, "100", 45)
    _abono(db, org, ana, "30", 10)
    beto = _cliente(db, org, "Beto")
    _cargo(db, org, branch_b, cajero_a, beto, "80", 0)
    carla = _cliente(db, org, "Carla")
    _abono(db, org, carla, "20", 1)
    dora = _cliente(db, org, "Dora")
    _cargo(db, org, branch_a, cajero_a, dora, "10", 3)
    _abono(db, org, dora, "10", 2)
    return ana, beto, carla, dora


def test_la_cajera_no_ve_las_cuentas_por_cobrar(client, db, org, branch_a, branch_b, cajero_a, auth_cajero_a):
    _escenario(db, org, branch_a, branch_b, cajero_a)
    r = client.get("/api/customers/cobranza", headers={**auth_cajero_a, "X-Organization-ID": str(org.id)})
    assert r.status_code == 403, r.text


def test_resumen_y_antiguedad_cuadran_con_el_saldo(client, db, org, branch_a, branch_b, cajero_a, auth_admin_a):
    ana, beto, carla, dora = _escenario(db, org, branch_a, branch_b, cajero_a)
    h = {**auth_admin_a, "X-Organization-ID": str(org.id)}
    d = client.get("/api/customers/cobranza", headers=h).json()

    # Los Decimal viajan como cadenas; se comparan como números.
    assert {k: float(v) for k, v in d["resumen"].items()} == {"por_cobrar": 150.0, "vencido_30": 70.0, "clientes": 2, "a_favor": 20.0}
    assert d["total"] == 2
    assert [i["id"] for i in d["items"]] == [beto.id, ana.id], "orden por saldo"
    fila = next(i for i in d["items"] if i["id"] == ana.id)
    assert float(fila["balance"]) == 70.0
    assert fila["dias"] == 45 and fila["cargo_mas_viejo"] is not None and fila["ultimo_abono"] is not None
    assert {k: float(v) for k, v in fila["antiguedad"].items()} == {"current": 0.0, "31_60": 70.0, "61_90": 0.0, "91_plus": 0.0}
    assert fila["tickets_abiertos"] == 1
    assert (fila["branch_id"], fila["branch_name"], fila["phone"]) == (branch_a.id, branch_a.name, "55 1234 5678")


def test_el_saldo_a_favor_va_aparte_y_el_cero_no_aparece(client, db, org, branch_a, branch_b, cajero_a, auth_admin_a):
    """Review Focus 4."""
    ana, beto, carla, dora = _escenario(db, org, branch_a, branch_b, cajero_a)
    h = {**auth_admin_a, "X-Organization-ID": str(org.id)}
    d = client.get("/api/customers/cobranza", headers=h).json()
    ids = [i["id"] for i in d["items"]]
    assert carla.id not in ids and dora.id not in ids
    assert float(d["resumen"]["a_favor"]) == 20.0


def test_filtros_y_orden(client, db, org, branch_a, branch_b, cajero_a, auth_admin_a):
    ana, beto, _, _ = _escenario(db, org, branch_a, branch_b, cajero_a)
    h = {**auth_admin_a, "X-Organization-ID": str(org.id)}
    g = lambda qs: client.get(f"/api/customers/cobranza?{qs}", headers=h).json()
    assert [i["id"] for i in g("order=antiguedad")["items"]] == [ana.id, beto.id]
    assert [i["id"] for i in g("bucket=31_60")["items"]] == [ana.id]
    assert [i["id"] for i in g(f"branch_id={branch_b.id}")["items"]] == [beto.id]
    assert [i["id"] for i in g("search=ana")["items"]] == [ana.id]
    assert [i["id"] for i in g("search=1234")["items"]] == [ana.id], "también busca por teléfono"
    assert float(g("bucket=31_60")["resumen"]["por_cobrar"]) == 70.0, "el resumen sigue al filtro"
    pagina = g("limit=1&skip=1")
    assert pagina["total"] == 2 and [i["id"] for i in pagina["items"]] == [ana.id]
    assert client.get("/api/customers/cobranza?bucket=viejo", headers=h).status_code == 422


def _asiento_de_ticket(db, org, cliente, doc, monto, descripcion):
    """Asiento negativo ligado a un ticket (abono a ticket o reversión)."""
    a = CustomerLedgerEntry(customer_id=cliente.id, sales_document_id=doc.id, organization_id=org.id,
                            amount=-Decimal(monto), description=descripcion)
    a.created_at = _hace(0)  # explícito: el default de SQLite trunca al segundo y podría quedar antes del cargo
    cliente.current_balance = Decimal(str(cliente.current_balance)) - Decimal(monto)
    db.add(a); db.commit()


def test_la_cancelacion_de_una_venta_reciente_no_rejuvenece_la_deuda_vieja(
    client, db, org, branch_a, cajero_a, auth_cajero_a, auth_admin_a, products_setup
):
    """Fiada vieja de 100 (45 días) y fiada de hoy de 100 cancelada por la API:
    la reversión descuenta el cargo de SU ticket, no el más viejo."""
    from app.models.cash import CashSession
    _habilitar(db, org, "pos", "crm")
    db.add(CashSession(user_id=cajero_a.id, branch_id=branch_a.id, organization_id=org.id,
                       opening_balance=Decimal("0"), status="OPEN")); db.commit()
    ana = _cliente(db, org, "Ana Pérez")
    _cargo(db, org, branch_a, cajero_a, ana, "100", 45)
    hc = {**auth_cajero_a, "X-Organization-ID": str(org.id)}
    _, variant = products_setup["product_a"]
    venta = client.post("/api/sales/", json={
        "doc_type": "ORDER", "customer_id": ana.id,
        "items": [{"sku": variant.sku, "quantity": 1}], "payments": [],
    }, headers=hc)
    assert venta.status_code in (200, 201), venta.text
    r = client.delete(f"/api/sales/{venta.json()['sale_id']}", params={"reason": "Se arrepintió"}, headers=hc)
    assert r.status_code == 200, r.text

    h = {**auth_admin_a, "X-Organization-ID": str(org.id)}
    d = client.get("/api/customers/cobranza", headers=h).json()
    assert [i["id"] for i in d["items"]] == [ana.id]
    fila = d["items"][0]
    assert float(fila["balance"]) == 100.0
    assert {k: float(v) for k, v in fila["antiguedad"].items()} == {"current": 0.0, "31_60": 100.0, "61_90": 0.0, "91_plus": 0.0}
    assert float(d["resumen"]["vencido_30"]) == 100.0
    assert client.get("/api/customers/cobranza?bucket=current", headers=h).json()["items"] == []


def test_el_abono_a_un_ticket_baja_ese_ticket_en_la_antiguedad(
    client, db, org, branch_a, branch_b, cajero_a, auth_admin_a
):
    """El abono a un ticket concreto no consume el cargo más viejo; el abono
    libre sí (FIFO)."""
    _habilitar(db, org, "crm")
    h = {**auth_admin_a, "X-Organization-ID": str(org.id)}
    ana = _cliente(db, org, "Ana")
    _cargo(db, org, branch_a, cajero_a, ana, "100", 45)
    nuevo = _cargo(db, org, branch_a, cajero_a, ana, "50", 0)
    _asiento_de_ticket(db, org, ana, nuevo, "50", f"ABONO A TICKET #{nuevo.folio}")
    fila = client.get("/api/customers/cobranza", headers=h).json()["items"][0]
    assert {k: float(v) for k, v in fila["antiguedad"].items()} == {"current": 0.0, "31_60": 100.0, "61_90": 0.0, "91_plus": 0.0}

    beto = _cliente(db, org, "Beto")
    _cargo(db, org, branch_a, cajero_a, beto, "100", 45)
    _cargo(db, org, branch_a, cajero_a, beto, "50", 0)
    _abono(db, org, beto, "50", 0)
    d = client.get("/api/customers/cobranza?search=beto", headers=h).json()
    assert {k: float(v) for k, v in d["items"][0]["antiguedad"].items()} == {"current": 50.0, "31_60": 50.0, "61_90": 0.0, "91_plus": 0.0}


def test_el_gerente_queda_confinado_a_su_sucursal(
    client, db, org, branch_a, branch_b, cajero_a, gerente_a, auth_gerente_a
):
    """Igual que el Inicio: el GERENTE ve solo su sucursal y el `branch_id` que
    mande se ignora; el resumen es el de su sucursal, no el de la organización."""
    ana, beto, _, _ = _escenario(db, org, branch_a, branch_b, cajero_a)
    h = {**auth_gerente_a, "X-Organization-ID": str(org.id)}
    for qs in ("", f"?branch_id={branch_b.id}", f"?branch_id={branch_a.id}"):
        d = client.get(f"/api/customers/cobranza{qs}", headers=h).json()
        assert [i["id"] for i in d["items"]] == [ana.id], qs
        assert float(d["resumen"]["por_cobrar"]) == 70.0 and d["resumen"]["clientes"] == 1, qs


def test_un_cliente_sin_nombre_con_deuda_no_rompe_la_lista(client, db, org, branch_a, cajero_a, auth_admin_a):
    """`customers.name` es nullable: deudores sin nombre y con nombre del mismo
    saldo (empate en el orden) deben listarse, con `name` nulo en la respuesta."""
    _habilitar(db, org, "crm")
    for nombre in (None, "Zoe", None):
        _cargo(db, org, branch_a, cajero_a, _cliente(db, org, nombre), "40", 1)
    h = {**auth_admin_a, "X-Organization-ID": str(org.id)}
    for qs in ("", "?order=antiguedad"):
        r = client.get(f"/api/customers/cobranza{qs}", headers=h)
        assert r.status_code == 200, r.text
        assert [i["name"] for i in r.json()["items"]] == [None, None, "Zoe"]
