"""La comision de tarjeta en el corte de caja.

Dos cosas que NO pueden romperse: `Total cobrado` sigue siendo la suma exacta
de los metodos (la comision YA esta dentro de `card`), y `compute_expected_cash`
no se entera de que la comision existe."""
from decimal import Decimal

from app.models.sales import SalesDocument
from app.pos_printer import PosPrinter
from conftest import _make_product
from tests.test_cash_cut_detalle import _audit, _visible_text
from tests.test_sale_variant_name_null import _abrir_caja, _habilitar_pos


class TestCorteImpreso:
    def test_sin_comision_no_imprime_el_renglon(self):
        p = PosPrinter("x", paper_width_mm=80)
        assert "incl. comision" not in _visible_text(p.build_cash_cut_bytes(_audit()), p)

    def test_imprime_la_comision_bajo_el_renglon_de_tarjeta(self):
        p = PosPrinter("x", paper_width_mm=80)
        t = _visible_text(p.build_cash_cut_bytes(_audit(card_surcharges=67.22)), p)
        renglones = [l for l in t.split("\n") if l.strip()]
        i_tarjeta = next(i for i, l in enumerate(renglones) if l.lstrip().startswith("Tarjeta"))
        assert renglones[i_tarjeta + 1].lstrip().startswith("incl. comision")
        assert "67.22" in renglones[i_tarjeta + 1]

    def test_la_comision_no_se_suma_al_total_cobrado(self):
        # La comision YA viaja dentro de payments['card']['total']; sumarla
        # aparte romperia la invariante de que el desglose da el total.
        p = PosPrinter("x", paper_width_mm=80)
        sin = _visible_text(p.build_cash_cut_bytes(_audit()), p)
        con = _visible_text(p.build_cash_cut_bytes(_audit(card_surcharges=67.22)), p)
        linea = lambda t: next(l for l in t.split("\n") if l.lstrip().startswith("Total cobrado"))
        assert linea(sin) == linea(con)

    def test_el_renglon_cabe_en_papel_de_58mm(self):
        p = PosPrinter("x", paper_width_mm=58)
        t = _visible_text(p.build_cash_cut_bytes(_audit(card_surcharges=12345.67)), p)
        for l in t.split("\n"):
            assert len(l.rstrip()) <= 32, f"línea de {len(l)} columnas: {l!r}"


class TestAuditData:
    def _venta(self, db, org, branch, cajero, client, auth, pct):
        _habilitar_pos(db, org)
        _make_product(db, org, "Mercancia", "CRT-01", Decimal("1000.00"), [(branch.id, True)])
        _abrir_caja(db, org, branch, cajero)
        org.card_surcharge_pct = Decimal(pct)
        db.commit()
        r = client.post("/api/sales/", json={
            "doc_type": "ORDER",
            "items": [{"sku": "CRT-01", "quantity": 1}],
            "payments": [{"method": "CARD", "amount": "1035.00"}],
        }, headers={**auth, "X-Organization-ID": str(org.id)})
        assert r.status_code in (200, 201), r.text
        return r.json()

    def test_suma_las_comisiones_del_turno(self, client, db, org, branch_a, cajero_a, auth_cajero_a):
        from app.models.cash import CashSession
        from app.routers.cash import get_session_audit_data

        self._venta(db, org, branch_a, cajero_a, client, auth_cajero_a, "3.5")
        sesion = db.query(CashSession).filter(CashSession.user_id == cajero_a.id).one()

        datos = get_session_audit_data(db, sesion.id)
        assert datos["card_surcharges"] == 35.0
        # La comision viaja DENTRO del importe de tarjeta, no aparte.
        assert datos["payments"]["card"]["total"] == 1035.0
        # Y `total_amount` sigue siendo solo mercancia.
        assert datos["kpis"]["total_sales"] == 1000.0

    def test_sin_comision_la_clave_es_cero(self, client, db, org, branch_a, cajero_a, auth_cajero_a):
        from app.models.cash import CashSession
        from app.routers.cash import get_session_audit_data

        self._venta(db, org, branch_a, cajero_a, client, auth_cajero_a, "0")
        sesion = db.query(CashSession).filter(CashSession.user_id == cajero_a.id).one()
        assert get_session_audit_data(db, sesion.id)["card_surcharges"] == 0.0

    def test_compute_expected_cash_no_ve_la_comision(self, client, db, org, branch_a, cajero_a, auth_cajero_a):
        # La comision entra por tarjeta: NO es efectivo y el arqueo no puede
        # moverse ni un centavo por su culpa.
        from app.models.cash import CashSession
        from app.services.cash_reconciliation import compute_expected_cash

        self._venta(db, org, branch_a, cajero_a, client, auth_cajero_a, "3.5")
        sesion = db.query(CashSession).filter(CashSession.user_id == cajero_a.id).one()
        antes = compute_expected_cash(db, sesion).expected

        venta = db.query(SalesDocument).filter(SalesDocument.organization_id == org.id).one()
        assert venta.card_surcharge_amount == Decimal("35.00")
        assert antes == Decimal(str(sesion.opening_balance or 0))


class TestExportCsv:
    def test_columnas_nuevas(self, client, db, org, branch_a, cajero_a, auth_cajero_a):
        _habilitar_pos(db, org)
        _make_product(db, org, "Mercancia", "CSV-01", Decimal("1000.00"), [(branch_a.id, True)])
        _abrir_caja(db, org, branch_a, cajero_a)
        org.card_surcharge_pct = Decimal("3.5")
        db.commit()
        client.post("/api/sales/", json={
            "doc_type": "ORDER",
            "items": [{"sku": "CSV-01", "quantity": 1}],
            "payments": [{"method": "CARD", "amount": "1035.00"}],
        }, headers={**auth_cajero_a, "X-Organization-ID": str(org.id)})

        r = client.get("/api/sales/export/csv",
                       headers={**auth_cajero_a, "X-Organization-ID": str(org.id)})
        assert r.status_code == 200, r.text
        texto = r.content.decode("utf-8-sig")
        encabezado, renglon = texto.strip().split("\r\n")[:2]
        cols = encabezado.split(",")
        assert cols[4:7] == ["Total", "Comisión tarjeta", "Total cobrado"]
        valores = renglon.split(",")
        assert valores[4:7] == ["1000.00", "35.00", "1035.00"]
