"""Regresiones de la auditoría funcional del backend (2026-09-22) — reportes.

* A-8 `daily-summary.gross_profit` descartaba la línea entera (ingreso incluido)
  cuando `unit_cost` era NULL — catálogos importados sin costo (Imaltzin).
* A-9 `aging-report` restaba un `datetime.now()` naive a un `created_at` aware
  (TIMESTAMPTZ): 500 en Postgres, invisible en SQLite.
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.models.sales import DocumentStatus, DocumentType, SalesDocument, SalesLineItem
from app.modules.customers.models import Customer, CustomerLedgerEntry


def _h(headers, org):
    return {**headers, "X-Organization-ID": str(org.id)}


# ---------------------------------------------------------------- A-8
def test_a8_linea_sin_costo_suma_su_ingreso_a_la_utilidad(
    client, db, org, branch_a, cajero_a, auth_admin, products_setup
):
    _, variant = products_setup["product_a"]
    sale = SalesDocument(
        id=str(uuid.uuid4()), organization_id=org.id, branch_id=branch_a.id,
        seller_id=cajero_a.id, doc_type=DocumentType.ORDER, status=DocumentStatus.PAID,
        subtotal=Decimal("150.00"), tax_amount=Decimal("0.00"),
        total_amount=Decimal("150.00"), created_at=datetime.now(timezone.utc),
    )
    db.add(sale)
    db.flush()
    db.add_all([
        SalesLineItem(
            document_id=sale.id, variant_id=variant.id, description="Con costo",
            quantity=1, unit_price=Decimal("100.00"), unit_cost=Decimal("60.00"),
            total_line=Decimal("100.00"), organization_id=org.id,
        ),
        SalesLineItem(
            document_id=sale.id, variant_id=variant.id, description="Sin costo (importado)",
            quantity=1, unit_price=Decimal("50.00"), unit_cost=None,
            total_line=Decimal("50.00"), organization_id=org.id,
        ),
    ])
    db.commit()

    r = client.get("/api/reports/daily-summary", params={"branch_id": 0},
                   headers=_h(auth_admin, org))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total_revenue"] == 150.0
    # 100-60 (línea con costo) + 50-0 (línea sin costo) = 90, no 40.
    assert data["gross_profit"] == 90.0


# ---------------------------------------------------------------- A-9
def test_a9_aging_report_clasifica_sin_reventar_por_timezone(
    client, db, org, auth_admin
):
    cliente = Customer(name="Deudor Antiguo", organization_id=org.id,
                       current_balance=Decimal("300.00"), has_credit=True)
    db.add(cliente)
    db.flush()

    ahora = datetime.now(timezone.utc)
    db.add_all([
        CustomerLedgerEntry(customer_id=cliente.id, amount=Decimal("100.00"),
                            description="Reciente", organization_id=org.id,
                            created_at=ahora - timedelta(days=5)),
        CustomerLedgerEntry(customer_id=cliente.id, amount=Decimal("200.00"),
                            description="Viejo", organization_id=org.id,
                            created_at=ahora - timedelta(days=120)),
    ])
    db.commit()

    r = client.get("/api/reports/aging-report", headers=_h(auth_admin, org))
    assert r.status_code == 200, r.text
    data = r.json()
    fila = [c for c in data["customers"] if c["customer_id"] == cliente.id][0]
    assert Decimal(str(fila["current_0_30"])) == Decimal("100.00")
    assert Decimal(str(fila["overdue_91_plus"])) == Decimal("200.00")
