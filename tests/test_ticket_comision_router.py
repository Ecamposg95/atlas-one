"""El cambio impreso en el ticket sale del cambio REAL de la venta.

Prueba a nivel router (y no de `PosPrinter`, como
`tests/test_ticket_comision_tarjeta.py`) porque el defecto no estaba en el
formateo sino en la aritmetica que hacen los endpoints antes de llamar a
`build_ticket_bytes`: derivaban el cambio de `sum(pagos) - total_amount`, y
`total_amount` NO incluye la comision mientras que el `Payment` de CARD SI.
Resultado: una venta 100% tarjeta imprimia como "cambio" la comision entera.

El numero correcto ya esta persistido en `sales_documents.change_given`, que es
justo lo que `create_sale` le entrego al cajero.
"""
import base64
from decimal import Decimal

from conftest import _make_product
from tests.test_sale_variant_name_null import _abrir_caja, _habilitar_pos


def _preparar(db, org, branch, cajero, precio="1000.00", pct=None):
    _habilitar_pos(db, org)
    _make_product(db, org, "Mercancia", "COM-01", Decimal(precio), [(branch.id, True)])
    _abrir_caja(db, org, branch, cajero)
    if pct is not None:
        org.card_surcharge_pct = Decimal(pct)
    db.commit()


def _vender(client, org, auth, pagos):
    return client.post("/api/sales/", json={
        "doc_type": "ORDER",
        "items": [{"sku": "COM-01", "quantity": 1}],
        "payments": pagos,
    }, headers={**auth, "X-Organization-ID": str(org.id)})


def _papel(resp) -> str:
    """Texto del ticket tal como sale del endpoint, sin comandos ESC/POS."""
    crudo = base64.b64decode(resp.json()["content_base64"]).decode("latin-1")
    # Los comandos ESC/POS son secuencias de control; para lo que aqui se mide
    # (los renglones REC:/CAM:) basta con quedarse con lo imprimible.
    return "".join(c for c in crudo if c == "\n" or c >= " ")


def _imprimir(client, org, auth, sale_id):
    return client.post(
        "/api/printer/print-ticket",
        json={"order_id": sale_id},
        headers={**auth, "X-Organization-ID": str(org.id)},
    )


def _reimprimir(client, org, auth, sale_id):
    return client.post(
        f"/api/printer/reprint-ticket/{sale_id}",
        json={"pin": None},
        headers={**auth, "X-Organization-ID": str(org.id)},
    )


class TestCambioImpreso:
    def test_venta_solo_tarjeta_no_imprime_cambio(
        self, client, db, org, branch_a, cajero_a, auth_cajero_a
    ):
        """1,000 de mercancia + 3.5% = la terminal cobra 1,035.00 y NO hay cambio.

        Antes del fix el ticket decia CAM:35.00: la comision disfrazada de
        cambio entregado.
        """
        _preparar(db, org, branch_a, cajero_a, pct="3.5")
        venta = _vender(client, org, auth_cajero_a, [{"method": "CARD", "amount": "1035.00"}])
        assert venta.status_code in (200, 201), venta.text
        assert venta.json()["change"] == 0.0

        ticket = _imprimir(client, org, auth_cajero_a, venta.json()["sale_id"])
        assert ticket.status_code == 200, ticket.text
        papel = _papel(ticket)
        assert "CAM:0.00" in papel, papel
        assert "CAM:35.00" not in papel, papel

    def test_venta_mixta_imprime_el_cambio_real(
        self, client, db, org, branch_a, cajero_a, auth_cajero_a
    ):
        """Ejemplo C del diseño: CASH 600 + CARD 517.50 sobre 1,000 al 3.5%.

        Cambio real 103.50; la resta ingenua daba 117.50 (103.50 + la comision
        de 14.00).
        """
        _preparar(db, org, branch_a, cajero_a, pct="3.5")
        venta = _vender(client, org, auth_cajero_a, [
            {"method": "CASH", "amount": "600.00"},
            {"method": "CARD", "amount": "517.50"},
        ])
        assert venta.status_code in (200, 201), venta.text
        assert venta.json()["change"] == 103.5

        ticket = _imprimir(client, org, auth_cajero_a, venta.json()["sale_id"])
        assert ticket.status_code == 200, ticket.text
        papel = _papel(ticket)
        assert "CAM:103.50" in papel, papel
        assert "CAM:117.50" not in papel, papel

    def test_la_reimpresion_trae_el_mismo_cambio(
        self, client, db, org, branch_a, cajero_a, auth_cajero_a
    ):
        """El segundo endpoint tenia la misma resta y por tanto el mismo error."""
        _preparar(db, org, branch_a, cajero_a, pct="3.5")
        venta = _vender(client, org, auth_cajero_a, [
            {"method": "CASH", "amount": "600.00"},
            {"method": "CARD", "amount": "517.50"},
        ])
        assert venta.status_code in (200, 201), venta.text

        ticket = _reimprimir(client, org, auth_cajero_a, venta.json()["sale_id"])
        assert ticket.status_code == 200, ticket.text
        assert "CAM:103.50" in _papel(ticket)

    def test_sin_comision_el_cambio_de_siempre_no_cambia(
        self, client, db, org, branch_a, cajero_a, auth_cajero_a
    ):
        """Neutralidad: con el porcentaje apagado el ticket es el de siempre."""
        _preparar(db, org, branch_a, cajero_a)
        venta = _vender(client, org, auth_cajero_a, [{"method": "CASH", "amount": "1200.00"}])
        assert venta.status_code in (200, 201), venta.text

        ticket = _imprimir(client, org, auth_cajero_a, venta.json()["sale_id"])
        assert ticket.status_code == 200, ticket.text
        assert "CAM:200.00" in _papel(ticket)
