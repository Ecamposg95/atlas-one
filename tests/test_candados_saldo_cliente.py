"""Candado del saldo del cliente al abonar (auditoría 2026-09-22, M12).

`with_for_update()` es un no-op en SQLite: la exclusión real entre dos abonos
simultáneos la prueba `scripts/prueba_concurrencia_ventas.py` contra Postgres
(escenario "abono": el mismo ticket fiado se liquida dos veces a la vez).

Aquí se afirma lo que SQLite sí deja afirmar: el SQL que se emitiría en
Postgres, que el candado relee el saldo, que las rutas que mueven el saldo lo
siguen pidiendo en el orden documento → cliente, y que el flujo normal del
abono no cambió.
"""
import inspect
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.dialects import postgresql

from app.models.cash import CashSession
from app.models.modules import Module, OrganizationModule
from app.models.sales import DocumentStatus, Payment, SalesDocument
from app.modules.customers import router as customers_router
from app.modules.customers import services as customers_services
from app.modules.customers.models import Customer
from app.routers import sales as sales_router


def _sin_espacios(fn) -> str:
    return "".join(inspect.getsource(fn).split())


# ── El SQL que llega a Postgres ───────────────────────────────────────────────

def test_la_consulta_del_cliente_emite_for_update(db, org):
    # La misma consulta que arma `cliente_con_candado`, compilada con el
    # dialecto de Postgres; la segunda afirmación vigila que la función la use.
    q = (
        db.query(Customer)
        .filter(Customer.id == 1, Customer.organization_id == org.id)
        .populate_existing()
        .with_for_update(of=Customer)
    )
    sql = str(q.statement.compile(dialect=postgresql.dialect()))
    assert sql.rstrip().endswith("FOR UPDATE OF customers")
    fuente = _sin_espacios(customers_services.cliente_con_candado)
    assert ".populate_existing().with_for_update(of=Customer).first()" in fuente


def test_cliente_con_candado_respeta_la_organizacion(db, org):
    cliente = Customer(name="Fiado", organization_id=org.id, current_balance=Decimal("0"))
    db.add(cliente); db.flush()

    assert customers_services.cliente_con_candado(
        db, org_id=org.id, customer_id=cliente.id) is cliente
    # Otra organización no lo ve (y por tanto no lo bloquea).
    assert customers_services.cliente_con_candado(
        db, org_id=org.id + 999, customer_id=cliente.id) is None


def test_cliente_con_candado_relee_el_saldo(db, org):
    """`populate_existing`: si la sesión ya tenía al cliente cargado sin
    candado, el saldo que se usa es el que hay en la base al tomarlo."""
    cliente = Customer(name="Fiado", organization_id=org.id, current_balance=Decimal("100"))
    db.add(cliente); db.flush()
    # Otra petición movió el saldo por debajo de esta sesión.
    db.execute(text("UPDATE customers SET current_balance = 40 WHERE id = :i"), {"i": cliente.id})
    assert Decimal(str(cliente.current_balance)) == Decimal("100")  # copia vieja en memoria

    con_candado = customers_services.cliente_con_candado(
        db, org_id=org.id, customer_id=cliente.id)
    assert Decimal(str(con_candado.current_balance)) == Decimal("40")


# ── Nadie quitó el candado de las rutas que mueven el saldo ───────────────────

def test_abono_bloquea_documento_y_luego_cliente():
    src = _sin_espacios(customers_router.register_customer_payment)
    doc = src.index(".with_for_update(of=SalesDocument).first()")
    cli = src.index("customer=cliente_con_candado(")
    saldo = src.index("saldo_doc=saldo_documento(")
    aplica = src.index("aplicar_abono(db,")
    # Orden global documento → cliente; el saldo del ticket se lee y el abono
    # se aplica ya con los dos candados puestos (antes, sin ninguno).
    assert doc < cli < saldo < aplica


def test_los_demas_escritores_del_saldo_tambien_lo_bloquean():
    for fn in (
        customers_services.revertir_cargo_de_documento,   # cancelar venta fiada
        customers_services.aplicar_devolucion_a_saldo,    # aprobar devolución
        customers_router.cargar_deuda_anterior_endpoint,
        customers_router.quitar_deuda_anterior_endpoint,
        sales_router.create_sale,                         # cargo de venta fiada
    ):
        assert "cliente_con_candado(" in _sin_espacios(fn), fn.__name__


# ── El flujo normal no cambió ────────────────────────────────────────────────

def _venta_fiada(client, db, org, branch, user, headers, variant):
    if db.query(Module).filter(Module.key == "pos").first() is None:
        db.add(Module(key="pos", name="Punto de venta")); db.flush()
    db.add(OrganizationModule(organization_id=org.id, module_key="pos", is_enabled=True))
    db.add(CashSession(user_id=user.id, branch_id=branch.id, organization_id=org.id,
                       opening_balance=Decimal("0"), status="OPEN"))
    cliente = Customer(name="Cliente fiado", organization_id=org.id, has_credit=True,
                       credit_limit=Decimal("1000"), current_balance=Decimal("0"))
    db.add(cliente)
    db.commit()
    venta = client.post("/api/sales/", json={
        "doc_type": "ORDER", "customer_id": cliente.id,
        "items": [{"sku": variant.sku, "quantity": 1}], "payments": [],
    }, headers=headers)
    assert venta.status_code == 200, venta.text
    return cliente, venta.json()["sale_id"]


def test_liquidar_un_ticket_y_volver_a_abonarlo_se_rechaza(
    client, db, org, branch_a, admin_a, auth_admin_a, products_setup
):
    _, variant = products_setup["product_a"]  # precio 100
    h = {**auth_admin_a, "X-Organization-ID": str(org.id)}
    cliente, sale_id = _venta_fiada(client, db, org, branch_a, admin_a, h, variant)
    db.refresh(cliente)
    assert Decimal(str(cliente.current_balance)) == Decimal("100.00")
    abono = {"amount": "100.00", "method": "CASH", "sales_document_id": sale_id}

    r1 = client.post(f"/api/customers/{cliente.id}/pay", json=abono, headers=h)
    assert r1.status_code == 200, r1.text
    assert Decimal(str(r1.json()["customer_balance_before"])) == Decimal("100.00")
    assert Decimal(str(r1.json()["customer_balance_after"])) == Decimal("0.00")

    # El segundo abono al mismo ticket ya liquidado: es lo que, con el candado,
    # ve la segunda de dos peticiones simultáneas.
    r2 = client.post(f"/api/customers/{cliente.id}/pay", json=abono, headers=h)
    assert r2.status_code == 422 and "excede lo que debe el ticket" in r2.json()["detail"]

    db.expire_all()
    assert db.query(Payment).filter(Payment.sales_document_id == sale_id).count() == 1
    assert Decimal(str(db.get(Customer, cliente.id).current_balance)) == Decimal("0.00")
    assert db.get(SalesDocument, sale_id).status == DocumentStatus.PAID


def test_abono_libre_sigue_cerrando_el_ticket(
    client, db, org, branch_a, admin_a, auth_admin_a, products_setup
):
    _, variant = products_setup["product_a"]
    h = {**auth_admin_a, "X-Organization-ID": str(org.id)}
    cliente, sale_id = _venta_fiada(client, db, org, branch_a, admin_a, h, variant)

    r = client.post(f"/api/customers/{cliente.id}/pay",
                    json={"amount": "100.00", "method": "CASH"}, headers=h)
    assert r.status_code == 200, r.text
    assert [a["sales_document_id"] for a in r.json()["applied"]] == [sale_id]

    db.expire_all()
    assert db.get(SalesDocument, sale_id).status == DocumentStatus.PAID
    assert Decimal(str(db.get(Customer, cliente.id).current_balance)) == Decimal("0.00")
