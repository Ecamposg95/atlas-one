"""Candados `FOR UPDATE` de existencias y documentos (auditoría 2026-09-22, A1).

`with_for_update()` es un no-op en SQLite, así que esta suite NO puede probar
la exclusión real entre dos peticiones: eso lo prueba, contra Postgres,
`scripts/prueba_concurrencia_ventas.py` (dos cajas y la última pieza, doble
cancelación). El saldo del cliente va en `test_candados_saldo_cliente.py`.

Lo que sí se puede afirmar aquí:
  * el SQL que se emite en Postgres lleva `FOR UPDATE` (se compila la consulta
    con el dialecto de Postgres, sin conectarse);
  * las rutas que mueven existencias siguen pidiendo el candado, y en orden
    de id (para no interbloquearse);
  * con el candado puesto el flujo normal no cambió.
"""
import inspect
from decimal import Decimal

from sqlalchemy.dialects import postgresql

from app.models.cash import CashSession
from app.models.inventory import StockOnHand
from app.models.modules import Module, OrganizationModule
from app.routers import quotes as quotes_router
from app.routers import sales as sales_router


def _sql_postgres(query) -> str:
    return str(query.statement.compile(dialect=postgresql.dialect()))


def _sin_espacios(fn) -> str:
    return "".join(inspect.getsource(fn).split())


# ── El SQL que llega a Postgres ───────────────────────────────────────────────

def test_existencias_en_orden_de_id_con_for_update(db):
    q = db.query(StockOnHand).filter(
        StockOnHand.variant_id.in_(["a", "b"])
    ).order_by(StockOnHand.id).with_for_update()
    sql = _sql_postgres(q)
    assert "ORDER BY stock_on_hand.id" in sql and sql.rstrip().endswith("FOR UPDATE")


# ── Nadie quitó el candado de las rutas de dinero ─────────────────────────────

ORDENADO = ".order_by(StockOnHand.id).with_for_update()"


def test_create_sale_bloquea_existencias_y_documento():
    src = _sin_espacios(sales_router.create_sale)
    # Las existencias que se van a descontar y las que se revierten al
    # reprocesar un PENDING.
    assert src.count(ORDENADO) == 2
    # El documento PENDING que se reprocesa (doble reversión de stock).
    assert ".with_for_update(of=SalesDocument).first()" in src


def test_cancel_sale_bloquea_documento_y_existencias():
    src = _sin_espacios(sales_router.cancel_sale)
    assert src.count(ORDENADO) == 1
    # El documento se bloquea ANTES de mirar si ya está cancelado.
    assert (src.index(".with_for_update(of=SalesDocument).first()")
            < src.index("sale.status==DocumentStatus.CANCELLED"))


def test_convertir_cotizacion_bloquea_documento_y_existencias():
    src = _sin_espacios(quotes_router.convert_quote_to_sale)
    assert ".with_for_update(of=SalesDocument).first()" in src
    assert src.count(ORDENADO) == 1


# ── El flujo normal no cambió ────────────────────────────────────────────────

def _preparar(db, org, branch, user):
    if db.query(Module).filter(Module.key == "pos").first() is None:
        db.add(Module(key="pos", name="Punto de venta")); db.flush()
    db.add(OrganizationModule(organization_id=org.id, module_key="pos", is_enabled=True))
    db.add(CashSession(user_id=user.id, branch_id=branch.id, organization_id=org.id,
                       opening_balance=Decimal("0"), status="OPEN"))
    db.commit()


def _stock(db, variant, branch) -> Decimal:
    db.expire_all()
    return Decimal(str(db.query(StockOnHand.qty_on_hand).filter(
        StockOnHand.variant_id == variant.id, StockOnHand.branch_id == branch.id).scalar()))


def test_la_ultima_pieza_se_vende_una_vez_y_la_segunda_se_rechaza(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    _preparar(db, org, branch_a, cajero_a)
    _, variant = products_setup["product_a"]
    db.query(StockOnHand).filter(
        StockOnHand.variant_id == variant.id, StockOnHand.branch_id == branch_a.id
    ).update({"qty_on_hand": Decimal("1")})
    db.commit()
    h = {**auth_cajero_a, "X-Organization-ID": str(org.id)}
    cuerpo = {"doc_type": "ORDER", "items": [{"sku": variant.sku, "quantity": 1}],
              "payments": [{"method": "CASH", "amount": "100.00"}]}

    r1 = client.post("/api/sales/", json=cuerpo, headers=h)
    assert r1.status_code == 200, r1.text
    r2 = client.post("/api/sales/", json=cuerpo, headers=h)
    assert r2.status_code == 400 and "Stock insuficiente" in r2.json()["detail"]
    assert _stock(db, variant, branch_a) == Decimal("0")


def test_cancelar_dos_veces_repone_el_stock_una_sola_vez(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    _preparar(db, org, branch_a, cajero_a)
    _, variant = products_setup["product_a"]
    antes = _stock(db, variant, branch_a)
    h = {**auth_cajero_a, "X-Organization-ID": str(org.id)}
    venta = client.post("/api/sales/", json={
        "doc_type": "ORDER", "items": [{"sku": variant.sku, "quantity": 2}],
        "payments": [{"method": "CASH", "amount": "200.00"}]}, headers=h)
    assert venta.status_code == 200, venta.text
    sale_id = venta.json()["sale_id"]
    assert _stock(db, variant, branch_a) == antes - 2

    assert client.delete(f"/api/sales/{sale_id}", headers=h).status_code == 200
    segunda = client.delete(f"/api/sales/{sale_id}", headers=h)
    assert segunda.status_code == 400 and "ya está cancelada" in segunda.json()["detail"]
    assert _stock(db, variant, branch_a) == antes


# ── Aprobar una devolución ───────────────────────────────────────────────────

def test_approve_return_bloquea_devolucion_venta_y_existencias():
    from app.crud import returns as crud_returns
    src = _sin_espacios(crud_returns.approve_return)
    dev = src.index("q.populate_existing().with_for_update().first()")
    venta = src.index(".populate_existing().with_for_update(of=SalesDocument).first()")
    r0 = src.index("sale.status==DocumentStatus.CANCELLED")
    # Devolución → venta, y la venta bloqueada ANTES de mirar si está cancelada.
    assert dev < venta < r0
    assert src.count(ORDENADO) == 1


def test_aprobar_no_usa_la_copia_vieja_de_la_devolucion(
    client, db, org, branch_a, admin_user, auth_admin, products_setup
):
    """La segunda de dos aprobaciones simultáneas espera el candado con la
    devolución ya cargada en su sesión como PENDING. Si al obtenerlo se queda
    con esa copia, vuelve a reingresar la mercancía y a sacar el dinero (en una
    devolución parcial nada más la frenaba). Aquí se reproduce sin hilos: la
    sesión tiene la copia vieja y la base ya dice APPROVED."""
    from sqlalchemy import text

    from app.crud import returns as crud_returns
    from app.models.inventory import InventoryMovement
    from app.models.returns import SaleReturn

    admin_user.branch_id = branch_a.id
    db.add(admin_user); db.commit()
    _preparar(db, org, branch_a, admin_user)
    _, variant = products_setup["product_a"]
    h = {**auth_admin, "X-Organization-ID": str(org.id)}
    venta = client.post("/api/sales/", json={
        "doc_type": "ORDER", "items": [{"sku": variant.sku, "quantity": 2}],
        "payments": [{"method": "CASH", "amount": "200.00"}]}, headers=h)
    assert venta.status_code == 200, venta.text
    dev = client.post("/api/returns/", json={
        "sale_id": venta.json()["sale_id"], "reason": "parcial",
        "total_refunded": "100.00", "refund_method": "CASH",
        "items": [{"variant_id": variant.id, "quantity": "1",
                   "refund_amount": "100.00", "is_inventory_reentry": True}]}, headers=h)
    assert dev.status_code in (200, 201), dev.text
    ret_id = dev.json()["id"]

    copia = db.query(SaleReturn).filter(SaleReturn.id == ret_id).one()
    assert copia.status == "PENDING"
    # "Otra petición" la aprobó por debajo de esta sesión.
    db.execute(text("UPDATE sale_returns SET status = 'APPROVED' WHERE id = :i"), {"i": ret_id})
    antes = Decimal(str(db.query(StockOnHand.qty_on_hand).filter(
        StockOnHand.variant_id == variant.id, StockOnHand.branch_id == branch_a.id).scalar()))

    resultado = crud_returns.approve_return(db, ret_id, admin_user.id, organization_id=org.id)

    assert resultado.status == "APPROVED"
    assert _stock(db, variant, branch_a) == antes, "no debe reingresar otra vez"
    assert db.query(InventoryMovement).filter(
        InventoryMovement.reference == f"RETURN:{ret_id}").count() == 0
