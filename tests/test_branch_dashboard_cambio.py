"""Mi día de la cajera (/api/branch/dashboard): el desglose por método resta el
cambio entregado, igual que el corte (`cash_reconciliation`) y los reportes
(`metricas_ventas.por_metodo`). Antes sumaba lo que entregó la clienta: un
ticket de $100 pagado con $150 aparecía como $150 en Efectivo."""
from decimal import Decimal

from tests.cobranza_helpers import _escenario


def _vender(client, h, sku, pagos):
    r = client.post("/api/sales/", json={"items": [{"sku": sku, "quantity": 1}], "payments": pagos}, headers=h)
    assert r.status_code in (200, 201), r.text
    return r.json()


def test_efectivo_de_mi_dia_resta_el_cambio(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    h, variante, _ = _escenario(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup)
    _vender(client, h, variante.sku, [{"method": "CASH", "amount": 150}])
    _vender(client, h, variante.sku, [{"method": "CASH", "amount": 50}, {"method": "CARD", "amount": 50}])

    hoy = client.get("/api/branch/dashboard", headers=h).json()["today"]
    metodos = {k: Decimal(str(v)) for k, v in hoy["payment_methods"].items()}
    assert Decimal(str(hoy["sales_total"])) == Decimal("200")
    assert metodos["CASH"] == Decimal("150")      # 100 + 50, sin los 50 de cambio
    assert metodos["CARD"] == Decimal("50")
    assert sum(metodos.values()) == Decimal("200")
