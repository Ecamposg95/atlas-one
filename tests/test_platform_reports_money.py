"""Pestañas de dinero de Reportes (spec 2026-09-09 §5.2): cortes, devoluciones,
cancelaciones y quincenal por método. Cross-org, solo lectura, SUPERADMIN/SUPPORT.

Faltante y sobrante se acumulan POR SEPARADO: un turno con −$500 y otro con
+$500 no son "cero", son dos problemas distintos.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.cash import CashSession, CashSessionStatus
from app.models.sales import DocumentStatus, DocumentType, Payment, PaymentMethod, SalesDocument
from app.routers.platform import reports as platform_reports


@pytest.fixture(autouse=True)
def _clear_reports_cache():
    platform_reports._cache.clear()
    yield
    platform_reports._cache.clear()


def _dt(y, m, d, h=12):
    return datetime(y, m, d, h, tzinfo=timezone.utc)


def _session(db, user, branch, *, status, opened_at, closed_at=None, difference=0,
             expected=0, reported=0):
    # `total_cash_sales` (efectivo NETO de la venta) deliberadamente distinto
    # de `expected` (opening + net_cash + movimientos manuales - reembolsos
    # en efectivo): son campos distintos y un test que los iguala no puede
    # atrapar F1 (el endpoint devolviendo `total_cash_sales` como si fuera
    # `expected`). El fondo de apertura y los movimientos son justo lo que
    # `total_cash_sales` no carga.
    s = CashSession(
        user_id=user.id, branch_id=branch.id, organization_id=branch.organization_id,
        status=status, opened_at=opened_at, closed_at=closed_at,
        opening_balance=Decimal("0"),
        closing_balance=Decimal(str(reported)),
        total_cash_sales=Decimal(str(expected)) - Decimal("250"),
        difference=Decimal(str(difference)),
    )
    db.add(s)
    db.flush()
    return s


PERIODO = {"start": "2026-09-01", "end": "2026-09-15"}


class TestCashCuts:
    def test_faltante_y_sobrante_se_acumulan_por_separado(
        self, client, auth_superadmin, db, cajero_a, gerente_a, branch_a,
    ):
        _session(db, cajero_a, branch_a, status=CashSessionStatus.CLOSED,
                 opened_at=_dt(2026, 9, 5, 8), closed_at=_dt(2026, 9, 5, 20), difference=-500)
        _session(db, gerente_a, branch_a, status=CashSessionStatus.CLOSED,
                 opened_at=_dt(2026, 9, 6, 8), closed_at=_dt(2026, 9, 6, 20), difference=500)
        _session(db, cajero_a, branch_a, status=CashSessionStatus.CLOSED,
                 opened_at=_dt(2026, 9, 7, 8), closed_at=_dt(2026, 9, 7, 20), difference=0)
        r = client.get("/api/platform/reports/cash-cuts", params=PERIODO, headers=auth_superadmin)
        assert r.status_code == 200, r.text
        row = next(x for x in r.json()["items"] if x["branch_id"] == branch_a.id)
        assert row["sessions_closed"] == 3
        assert row["sessions_with_difference"] == 2
        assert row["shortage_total"] == "500.00"      # en positivo
        assert row["overage_total"] == "500.00"
        assert row["avg_abs_difference"] == "333.33"  # (500+500+0)/3

    def test_turno_abierto_cuenta_aparte_y_no_entra_en_los_cerrados(
        self, client, auth_superadmin, db, cajero_a, branch_a,
    ):
        _session(db, cajero_a, branch_a, status=CashSessionStatus.OPEN, opened_at=_dt(2026, 9, 8, 8))
        r = client.get("/api/platform/reports/cash-cuts", params=PERIODO, headers=auth_superadmin)
        row = next(x for x in r.json()["items"] if x["branch_id"] == branch_a.id)
        assert row["sessions_open_unclosed"] == 1
        assert row["sessions_closed"] == 0

    def test_turno_abierto_fuera_de_la_ventana_tambien_cuenta(
        self, client, auth_superadmin, db, cajero_a, branch_a,
    ):
        # F5: un turno abierto 45 días antes del periodo y nunca cerrado es
        # precisamente el caso que este contador existe para encontrar — no
        # debe desaparecer por vivir fuera de [s, e].
        _session(db, cajero_a, branch_a, status=CashSessionStatus.OPEN, opened_at=_dt(2026, 7, 22, 8))
        r = client.get("/api/platform/reports/cash-cuts", params=PERIODO, headers=auth_superadmin)
        row = next(x for x in r.json()["items"] if x["branch_id"] == branch_a.id)
        assert row["sessions_open_unclosed"] == 1

    def test_el_corte_se_ubica_por_su_cierre_no_por_su_apertura(
        self, client, auth_superadmin, db, cajero_a, branch_a,
    ):
        # Abre el 31 de agosto 20:00 MX, cierra el 1 de septiembre 02:00 MX:
        # pertenece a septiembre. Las horas van en UTC (MX = UTC−6), porque el
        # día del reporte es el de México, no el de UTC.
        _session(db, cajero_a, branch_a, status=CashSessionStatus.CLOSED,
                 opened_at=_dt(2026, 9, 1, 2), closed_at=_dt(2026, 9, 1, 8), difference=-10)
        r = client.get("/api/platform/reports/cash-cuts", params=PERIODO, headers=auth_superadmin)
        row = next(x for x in r.json()["items"] if x["branch_id"] == branch_a.id)
        assert row["sessions_closed"] == 1

    def test_sucursal_sin_cortes_no_aparece(self, client, auth_superadmin, db, branch_b):
        r = client.get("/api/platform/reports/cash-cuts", params=PERIODO, headers=auth_superadmin)
        assert branch_b.id not in {x["branch_id"] for x in r.json()["items"]}

    def test_detalle_por_cajera_y_lista_de_sesiones(
        self, client, auth_superadmin, db, cajero_a, gerente_a, branch_a,
    ):
        s1 = _session(db, cajero_a, branch_a, status=CashSessionStatus.CLOSED,
                      opened_at=_dt(2026, 9, 5, 8), closed_at=_dt(2026, 9, 5, 20),
                      difference=-500, expected=1500, reported=1000)
        _session(db, gerente_a, branch_a, status=CashSessionStatus.CLOSED,
                 opened_at=_dt(2026, 9, 6, 8), closed_at=_dt(2026, 9, 6, 20), difference=40)
        r = client.get(
            f"/api/platform/reports/cash-cuts/{branch_a.id}/detail",
            params=PERIODO, headers=auth_superadmin,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["branch_id"] == branch_a.id
        by_cashier = {c["full_name"]: c for c in body["by_cashier"]}
        assert len(by_cashier) == 2
        mia = by_cashier[cajero_a.full_name or cajero_a.username]
        assert mia["sessions"] == 1 and mia["shortage_total"] == "500.00"
        sesion = next(s for s in body["sessions"] if s["session_id"] == s1.id)
        assert sesion["difference"] == "-500.00"
        assert sesion["reported"] == "1000.00"
        # F1: expected = reported - difference = 1000 - (-500) = 1500, NUNCA
        # el `total_cash_sales` persistido (1250 en este fixture) — ese
        # campo es solo el efectivo neto de venta, sin fondo de apertura ni
        # movimientos manuales.
        assert sesion["expected"] == "1500.00"

    def test_csv_trae_los_encabezados_del_pivote(self, client, auth_superadmin, db, cajero_a, branch_a):
        _session(db, cajero_a, branch_a, status=CashSessionStatus.CLOSED,
                 opened_at=_dt(2026, 9, 5, 8), closed_at=_dt(2026, 9, 5, 20), difference=-500)
        r = client.get("/api/platform/reports/cash-cuts.csv", params=PERIODO, headers=auth_superadmin)
        assert r.status_code == 200
        first_line = r.text.lstrip("﻿").splitlines()[0]
        assert first_line.split(",") == [
            "branch_id", "name", "org_name", "sessions_closed", "sessions_with_difference",
            "shortage_total", "overage_total", "avg_abs_difference", "sessions_open_unclosed",
        ]

    def test_403_para_administrador_de_tenant(self, client, auth_admin):
        r = client.get("/api/platform/reports/cash-cuts", headers=auth_admin)
        assert r.status_code == 403


from app.models.cash_audit import CashAuditEvent, CashAuditLog
from app.models.returns import SaleReturn


def _sale(db, seller, branch, amount, created_at, *, status=DocumentStatus.PAID, folio=None):
    sale = SalesDocument(
        seller_id=seller.id, branch_id=branch.id, organization_id=branch.organization_id,
        total_amount=Decimal(str(amount)), subtotal=Decimal(str(amount)), tax_amount=Decimal("0"),
        status=status, doc_type=DocumentType.INVOICE, created_at=created_at,
        series="A", folio=folio,
    )
    db.add(sale)
    db.flush()
    return sale


def _return(db, sale, user, branch, amount, created_at, *, status="PENDING",
            method=PaymentMethod.CASH, reason="Defectuoso"):
    r = SaleReturn(
        sale_id=sale.id, user_id=user.id, branch_id=branch.id,
        organization_id=branch.organization_id, total_refunded=Decimal(str(amount)),
        refund_method=method, reason=reason, status=status, created_at=created_at,
    )
    db.add(r)
    db.flush()
    return r


def _audit(db, branch, event_type, amount, ts, *, user_id=None, related_id=None, payload=None):
    row = CashAuditLog(
        ts=ts, organization_id=branch.organization_id, branch_id=branch.id, user_id=user_id,
        event_type=event_type, amount=Decimal(str(amount)),
        related_table="sale_returns" if event_type == CashAuditEvent.REFUND_APPROVED else "sales_documents",
        related_id=related_id, payload_json=payload,
    )
    db.add(row)
    db.flush()
    return row


class TestReturns:
    def test_conteo_y_monto_por_estatus_y_por_metodo(
        self, client, auth_superadmin, db, cajero_a, branch_a,
    ):
        sale1 = _sale(db, cajero_a, branch_a, 500, _dt(2026, 9, 3), folio=101)
        sale2 = _sale(db, cajero_a, branch_a, 500, _dt(2026, 9, 4), folio=102)
        sale3 = _sale(db, cajero_a, branch_a, 500, _dt(2026, 9, 5), folio=103)
        _return(db, sale1, cajero_a, branch_a, 100, _dt(2026, 9, 6), status="PENDING")
        _return(db, sale2, cajero_a, branch_a, 220, _dt(2026, 9, 7), status="APPROVED")
        _return(db, sale3, cajero_a, branch_a, 50, _dt(2026, 9, 8), status="APPROVED",
                method=PaymentMethod.CARD)
        r = client.get("/api/platform/reports/returns", params=PERIODO, headers=auth_superadmin)
        assert r.status_code == 200, r.text
        row = next(x for x in r.json()["items"] if x["branch_id"] == branch_a.id)
        assert row["pending_count"] == 1 and row["pending_amount"] == "100.00"
        assert row["approved_count"] == 2 and row["approved_amount"] == "270.00"
        assert row["by_method"]["cash"] == "220.00"
        assert row["by_method"]["card"] == "50.00"

    def test_horas_hasta_aprobar_salen_del_audit_log(
        self, client, auth_superadmin, db, cajero_a, gerente_a, branch_a,
    ):
        sale = _sale(db, cajero_a, branch_a, 500, _dt(2026, 9, 3), folio=201)
        ret = _return(db, sale, cajero_a, branch_a, 100, _dt(2026, 9, 5, 10), status="APPROVED")
        # Aprobada 6 horas después; `updated_at` no se usa como fuente.
        _audit(db, branch_a, CashAuditEvent.REFUND_APPROVED, 100, _dt(2026, 9, 5, 16),
               user_id=gerente_a.id, related_id=ret.id)
        r = client.get("/api/platform/reports/returns", params=PERIODO, headers=auth_superadmin)
        row = next(x for x in r.json()["items"] if x["branch_id"] == branch_a.id)
        assert row["avg_hours_to_approve"] == "6.00"

    def test_aprobada_sin_evento_no_rompe_el_promedio(
        self, client, auth_superadmin, db, cajero_a, branch_a,
    ):
        sale = _sale(db, cajero_a, branch_a, 500, _dt(2026, 9, 3), folio=202)
        _return(db, sale, cajero_a, branch_a, 100, _dt(2026, 9, 5), status="APPROVED")
        r = client.get("/api/platform/reports/returns", params=PERIODO, headers=auth_superadmin)
        row = next(x for x in r.json()["items"] if x["branch_id"] == branch_a.id)
        assert row["avg_hours_to_approve"] is None

    def test_motivos_mas_frecuentes_en_orden(self, client, auth_superadmin, db, cajero_a, branch_a):
        for i, motivo in enumerate(["Defectuoso", "Defectuoso", "Error de cliente"]):
            sale = _sale(db, cajero_a, branch_a, 500, _dt(2026, 9, 3), folio=300 + i)
            _return(db, sale, cajero_a, branch_a, 10, _dt(2026, 9, 6), reason=motivo)
        r = client.get("/api/platform/reports/returns", params=PERIODO, headers=auth_superadmin)
        row = next(x for x in r.json()["items"] if x["branch_id"] == branch_a.id)
        assert row["top_reasons"][0] == "Defectuoso"

    def test_detalle_lista_las_devoluciones_con_folio(
        self, client, auth_superadmin, db, cajero_a, branch_a,
    ):
        sale = _sale(db, cajero_a, branch_a, 500, _dt(2026, 9, 3), folio=404)
        _return(db, sale, cajero_a, branch_a, 100, _dt(2026, 9, 6))
        r = client.get(
            f"/api/platform/reports/returns/{branch_a.id}/detail",
            params=PERIODO, headers=auth_superadmin,
        )
        assert r.status_code == 200, r.text
        item = r.json()["items"][0]
        assert item["folio"] == "A-404"
        assert item["amount"] == "100.00"
        assert item["status"] == "PENDING"

    def test_csv_de_devoluciones(self, client, auth_superadmin, db, cajero_a, branch_a):
        sale = _sale(db, cajero_a, branch_a, 500, _dt(2026, 9, 3), folio=405)
        _return(db, sale, cajero_a, branch_a, 100, _dt(2026, 9, 6))
        r = client.get("/api/platform/reports/returns.csv", params=PERIODO, headers=auth_superadmin)
        assert r.status_code == 200
        assert r.text.lstrip("﻿").splitlines()[0].split(",")[:4] == [
            "branch_id", "name", "org_name", "pending_count",
        ]


class TestCancellations:
    def test_salen_del_audit_log_no_del_estatus_de_la_venta(
        self, client, auth_superadmin, db, cajero_a, gerente_a, branch_a,
    ):
        cancelada = _sale(db, cajero_a, branch_a, 300, _dt(2026, 9, 5),
                          status=DocumentStatus.CANCELLED, folio=501)
        _audit(db, branch_a, CashAuditEvent.SALE_CANCELLED, 300, _dt(2026, 9, 5, 14),
               user_id=gerente_a.id, related_id=str(cancelada.id),
               payload={"reason": "Ticket duplicado", "prev_status": "PAID", "folio": 501})
        # Una venta CANCELLED sin evento no cuenta: sin rastro no hay reporte.
        _sale(db, cajero_a, branch_a, 9999, _dt(2026, 9, 6), status=DocumentStatus.CANCELLED, folio=502)
        r = client.get("/api/platform/reports/cancellations", params=PERIODO, headers=auth_superadmin)
        assert r.status_code == 200, r.text
        row = next(x for x in r.json()["items"] if x["branch_id"] == branch_a.id)
        assert row["count"] == 1
        assert row["amount"] == "300.00"
        assert row["by_user"][0]["full_name"] == (gerente_a.full_name or gerente_a.username)
        assert row["top_reasons"] == ["Ticket duplicado"]

    def test_detalle_trae_folio_motivo_y_estado_previo(
        self, client, auth_superadmin, db, cajero_a, gerente_a, branch_a,
    ):
        venta = _sale(db, cajero_a, branch_a, 300, _dt(2026, 9, 5),
                      status=DocumentStatus.CANCELLED, folio=503)
        _audit(db, branch_a, CashAuditEvent.SALE_CANCELLED, 300, _dt(2026, 9, 5, 14),
               user_id=gerente_a.id, related_id=str(venta.id),
               payload={"reason": "Cliente se arrepintió", "prev_status": "PAID", "folio": 503})
        r = client.get(
            f"/api/platform/reports/cancellations/{branch_a.id}/detail",
            params=PERIODO, headers=auth_superadmin,
        )
        assert r.status_code == 200, r.text
        item = r.json()["items"][0]
        assert item["folio"] == "A-503"
        assert item["reason"] == "Cliente se arrepintió"
        assert item["prev_status"] == "PAID"
        assert item["amount"] == "300.00"

    def test_csv_de_cancelaciones(self, client, auth_superadmin, db, cajero_a, gerente_a, branch_a):
        venta = _sale(db, cajero_a, branch_a, 300, _dt(2026, 9, 5),
                      status=DocumentStatus.CANCELLED, folio=504)
        _audit(db, branch_a, CashAuditEvent.SALE_CANCELLED, 300, _dt(2026, 9, 5, 14),
               user_id=gerente_a.id, related_id=str(venta.id), payload={"reason": "x"})
        r = client.get("/api/platform/reports/cancellations.csv", params=PERIODO, headers=auth_superadmin)
        assert r.status_code == 200
        assert r.text.lstrip("﻿").splitlines()[0].split(",") == [
            "branch_id", "name", "org_name", "count", "amount",
        ]


class TestBiweekly:
    def test_parte_el_mes_en_dos_quincenas_por_dia_de_mexico(
        self, client, auth_superadmin, db, cajero_a, branch_a,
    ):
        # 15 sep 23:30 MX = 16 sep 05:30 UTC → primera quincena.
        v1 = _sale(db, cajero_a, branch_a, 100, datetime(2026, 9, 16, 5, 30, tzinfo=timezone.utc), folio=601)
        db.add(Payment(sales_document_id=v1.id, method=PaymentMethod.CASH, amount=Decimal("100"),
                       organization_id=branch_a.organization_id,
                       created_at=datetime(2026, 9, 16, 5, 30, tzinfo=timezone.utc)))
        # 16 sep 00:30 MX = 16 sep 06:30 UTC → segunda quincena.
        v2 = _sale(db, cajero_a, branch_a, 200, datetime(2026, 9, 16, 6, 30, tzinfo=timezone.utc), folio=602)
        db.add(Payment(sales_document_id=v2.id, method=PaymentMethod.CARD, amount=Decimal("200"),
                       organization_id=branch_a.organization_id,
                       created_at=datetime(2026, 9, 16, 6, 30, tzinfo=timezone.utc)))
        db.flush()
        r = client.get(
            "/api/platform/reports/payment-methods-biweekly",
            params={"start": "2026-09-01", "end": "2026-09-30", "unit": "branch"},
            headers=auth_superadmin,
        )
        assert r.status_code == 200, r.text
        rows = {x["period"]: x for x in r.json()["items"] if x["unit_id"] == branch_a.id}
        assert rows["2026-09-Q1"]["cash_net"] == "100.00"
        assert rows["2026-09-Q1"]["period_label"] == "1–15 sep 2026"
        assert rows["2026-09-Q2"]["card"] == "200.00"

    def test_efectivo_neto_de_cambio(self, client, auth_superadmin, db, cajero_a, branch_a):
        venta = _sale(db, cajero_a, branch_a, 150, _dt(2026, 9, 5), folio=603)
        venta.change_given = Decimal("10")
        db.add(Payment(sales_document_id=venta.id, method=PaymentMethod.CARD, amount=Decimal("100"),
                       organization_id=branch_a.organization_id, created_at=_dt(2026, 9, 5)))
        db.add(Payment(sales_document_id=venta.id, method=PaymentMethod.CASH, amount=Decimal("60"),
                       organization_id=branch_a.organization_id, created_at=_dt(2026, 9, 5)))
        db.flush()
        r = client.get(
            "/api/platform/reports/payment-methods-biweekly",
            params={"start": "2026-09-01", "end": "2026-09-15", "unit": "branch"},
            headers=auth_superadmin,
        )
        row = next(x for x in r.json()["items"] if x["unit_id"] == branch_a.id)
        assert row["cash_net"] == "50.00"     # 60 cobrados − 10 de cambio
        assert row["card"] == "100.00"
        assert row["total"] == "150.00"

    def test_cancelada_no_cuenta_y_devuelta_parcial_si(
        self, client, auth_superadmin, db, cajero_a, branch_a,
    ):
        cancelada = _sale(db, cajero_a, branch_a, 500, _dt(2026, 9, 5),
                          status=DocumentStatus.CANCELLED, folio=604)
        db.add(Payment(sales_document_id=cancelada.id, method=PaymentMethod.CASH,
                       amount=Decimal("500"), organization_id=branch_a.organization_id,
                       created_at=_dt(2026, 9, 5)))
        devuelta = _sale(db, cajero_a, branch_a, 80, _dt(2026, 9, 6),
                         status=DocumentStatus.REFUNDED_PARTIAL, folio=605)
        db.add(Payment(sales_document_id=devuelta.id, method=PaymentMethod.CASH,
                       amount=Decimal("100"), organization_id=branch_a.organization_id,
                       created_at=_dt(2026, 9, 6)))
        db.flush()
        r = client.get(
            "/api/platform/reports/payment-methods-biweekly",
            params={"start": "2026-09-01", "end": "2026-09-15", "unit": "branch"},
            headers=auth_superadmin,
        )
        row = next(x for x in r.json()["items"] if x["unit_id"] == branch_a.id)
        assert row["cash_net"] == "100.00"    # la cancelada no entra
        assert row["tickets"] == 1

    @pytest.mark.parametrize("mes,dias", [(2, 28), (4, 30), (7, 31)])
    def test_la_segunda_quincena_llega_al_fin_de_mes(
        self, client, auth_superadmin, db, cajero_a, branch_a, mes, dias,
    ):
        ultimo = datetime(2026, mes, dias, 18, tzinfo=timezone.utc)
        venta = _sale(db, cajero_a, branch_a, 70, ultimo, folio=700 + mes)
        db.add(Payment(sales_document_id=venta.id, method=PaymentMethod.TRANSFER,
                       amount=Decimal("70"), organization_id=branch_a.organization_id,
                       created_at=ultimo))
        db.flush()
        r = client.get(
            "/api/platform/reports/payment-methods-biweekly",
            params={"start": f"2026-{mes:02d}-01", "end": f"2026-{mes:02d}-{dias}", "unit": "branch"},
            headers=auth_superadmin,
        )
        rows = {x["period"]: x for x in r.json()["items"] if x["unit_id"] == branch_a.id}
        assert rows[f"2026-{mes:02d}-Q2"]["transfer"] == "70.00"

    def test_unit_org_suma_sus_sucursales(self, client, auth_superadmin, db, org, cajero_a, branch_a, branch_b):
        for i, branch in enumerate((branch_a, branch_b)):
            venta = _sale(db, cajero_a, branch, 100, _dt(2026, 9, 5), folio=800 + i)
            db.add(Payment(sales_document_id=venta.id, method=PaymentMethod.CASH,
                           amount=Decimal("100"), organization_id=branch.organization_id,
                           created_at=_dt(2026, 9, 5)))
        db.flush()
        r = client.get(
            "/api/platform/reports/payment-methods-biweekly",
            params={"start": "2026-09-01", "end": "2026-09-15", "unit": "org"},
            headers=auth_superadmin,
        )
        row = next(x for x in r.json()["items"] if x["unit_id"] == org.id)
        assert row["cash_net"] == "200.00"
        assert row["tickets"] == 2

    def test_unit_invalido_422(self, client, auth_superadmin):
        r = client.get(
            "/api/platform/reports/payment-methods-biweekly",
            params={"unit": "galaxia"}, headers=auth_superadmin,
        )
        assert r.status_code == 422

    def test_csv_quincenal(self, client, auth_superadmin, db, cajero_a, branch_a):
        venta = _sale(db, cajero_a, branch_a, 100, _dt(2026, 9, 5), folio=900)
        db.add(Payment(sales_document_id=venta.id, method=PaymentMethod.CASH, amount=Decimal("100"),
                       organization_id=branch_a.organization_id, created_at=_dt(2026, 9, 5)))
        db.flush()
        r = client.get(
            "/api/platform/reports/payment-methods-biweekly.csv",
            params={"start": "2026-09-01", "end": "2026-09-15", "unit": "branch"},
            headers=auth_superadmin,
        )
        assert r.status_code == 200
        assert r.text.lstrip("﻿").splitlines()[0].split(",") == [
            "period", "period_label", "unit_id", "name", "org_name",
            "cash_net", "card", "transfer", "other", "total", "tickets",
        ]


# ================================================================== #
# Aislamiento entre organizaciones                                   #
# ================================================================== #

from app.models.organization import Branch, BranchType, Organization
from app.models.users import Role, User, UserOrganization
from app.core.security import get_password_hash


@pytest.fixture()
def org_b(db):
    """Una SEGUNDA organización: sin ella ningún test nota si el `org_id` filtra."""
    o = Organization(name="Otra Org", status="ACTIVE")
    db.add(o)
    db.flush()
    return o


@pytest.fixture()
def branch_c(db, org_b):
    b = Branch(
        name="Sucursal C", branch_type=BranchType.STORE,
        can_sell=True, is_active=True, organization_id=org_b.id,
    )
    db.add(b)
    db.flush()
    return b


@pytest.fixture()
def cajero_c(db, org_b, branch_c):
    u = User(
        username="cajero_c", password_hash=get_password_hash("test1234"),
        role=Role.CAJERO, branch_id=branch_c.id, is_active=True,
    )
    db.add(u)
    db.flush()
    db.add(UserOrganization(user_id=u.id, organization_id=org_b.id,
                            org_role="MEMBER", is_active=True))
    db.flush()
    return u


def _pago(db, venta, branch, monto, cuando, method=PaymentMethod.CASH):
    db.add(Payment(sales_document_id=venta.id, method=method, amount=Decimal(str(monto)),
                   organization_id=branch.organization_id, created_at=cuando))


class TestAislamientoPorOrganizacion:
    """Cross-org por diseño, pero `org_id` tiene que recortar de verdad."""

    def test_cortes_sin_org_id_son_filas_separadas_sin_importes_cruzados(
        self, client, auth_superadmin, db, cajero_a, branch_a, cajero_c, branch_c,
    ):
        _session(db, cajero_a, branch_a, status=CashSessionStatus.CLOSED,
                 opened_at=_dt(2026, 9, 5, 8), closed_at=_dt(2026, 9, 5, 20), difference=-500)
        _session(db, cajero_c, branch_c, status=CashSessionStatus.CLOSED,
                 opened_at=_dt(2026, 9, 5, 8), closed_at=_dt(2026, 9, 5, 20), difference=-70)
        r = client.get("/api/platform/reports/cash-cuts", params=PERIODO, headers=auth_superadmin)
        assert r.status_code == 200, r.text
        filas = {x["branch_id"]: x for x in r.json()["items"]}
        assert filas[branch_a.id]["shortage_total"] == "500.00"
        assert filas[branch_c.id]["shortage_total"] == "70.00"

    def test_cortes_con_org_id_dejan_fuera_la_otra_organizacion(
        self, client, auth_superadmin, db, org, cajero_a, branch_a, cajero_c, branch_c,
    ):
        _session(db, cajero_a, branch_a, status=CashSessionStatus.CLOSED,
                 opened_at=_dt(2026, 9, 5, 8), closed_at=_dt(2026, 9, 5, 20), difference=-500)
        _session(db, cajero_c, branch_c, status=CashSessionStatus.CLOSED,
                 opened_at=_dt(2026, 9, 5, 8), closed_at=_dt(2026, 9, 5, 20), difference=-70)
        r = client.get("/api/platform/reports/cash-cuts",
                       params={**PERIODO, "org_id": org.id}, headers=auth_superadmin)
        ids = {x["branch_id"] for x in r.json()["items"]}
        assert branch_a.id in ids
        assert branch_c.id not in ids

    def test_detalle_de_una_sucursal_de_otra_org_es_404(
        self, client, auth_superadmin, db, org, cajero_c, branch_c,
    ):
        _session(db, cajero_c, branch_c, status=CashSessionStatus.CLOSED,
                 opened_at=_dt(2026, 9, 5, 8), closed_at=_dt(2026, 9, 5, 20), difference=-70)
        r = client.get(f"/api/platform/reports/cash-cuts/{branch_c.id}/detail",
                       params={**PERIODO, "org_id": org.id}, headers=auth_superadmin)
        assert r.status_code == 404, r.text

    def test_devoluciones_con_org_id_dejan_fuera_la_otra_organizacion(
        self, client, auth_superadmin, db, org, cajero_a, branch_a, cajero_c, branch_c,
    ):
        v1 = _sale(db, cajero_a, branch_a, 500, _dt(2026, 9, 3), folio=1001)
        _return(db, v1, cajero_a, branch_a, 100, _dt(2026, 9, 6))
        v2 = _sale(db, cajero_c, branch_c, 500, _dt(2026, 9, 3), folio=1002)
        _return(db, v2, cajero_c, branch_c, 300, _dt(2026, 9, 6))
        r = client.get("/api/platform/reports/returns",
                       params={**PERIODO, "org_id": org.id}, headers=auth_superadmin)
        filas = r.json()["items"]
        assert {x["branch_id"] for x in filas} == {branch_a.id}
        assert filas[0]["pending_amount"] == "100.00"

    def test_cancelaciones_con_org_id_dejan_fuera_la_otra_organizacion(
        self, client, auth_superadmin, db, org, cajero_a, branch_a, cajero_c, branch_c,
    ):
        va = _sale(db, cajero_a, branch_a, 300, _dt(2026, 9, 5),
                   status=DocumentStatus.CANCELLED, folio=1101)
        _audit(db, branch_a, CashAuditEvent.SALE_CANCELLED, 300, _dt(2026, 9, 5, 14),
               user_id=cajero_a.id, related_id=str(va.id), payload={"reason": "x"})
        vc = _sale(db, cajero_c, branch_c, 900, _dt(2026, 9, 5),
                   status=DocumentStatus.CANCELLED, folio=1102)
        _audit(db, branch_c, CashAuditEvent.SALE_CANCELLED, 900, _dt(2026, 9, 5, 14),
               user_id=cajero_c.id, related_id=str(vc.id), payload={"reason": "x"})
        r = client.get("/api/platform/reports/cancellations",
                       params={**PERIODO, "org_id": org.id}, headers=auth_superadmin)
        filas = r.json()["items"]
        assert {x["branch_id"] for x in filas} == {branch_a.id}
        assert filas[0]["amount"] == "300.00"

    def test_quincenal_unit_org_no_suma_organizaciones_distintas(
        self, client, auth_superadmin, db, org, org_b, cajero_a, branch_a, cajero_c, branch_c,
    ):
        va = _sale(db, cajero_a, branch_a, 100, _dt(2026, 9, 5), folio=1201)
        _pago(db, va, branch_a, 100, _dt(2026, 9, 5))
        vc = _sale(db, cajero_c, branch_c, 700, _dt(2026, 9, 5), folio=1202)
        _pago(db, vc, branch_c, 700, _dt(2026, 9, 5))
        db.flush()
        r = client.get(
            "/api/platform/reports/payment-methods-biweekly",
            params={"start": "2026-09-01", "end": "2026-09-15", "unit": "org"},
            headers=auth_superadmin,
        )
        assert r.status_code == 200, r.text
        filas = {x["unit_id"]: x for x in r.json()["items"]}
        assert filas[org.id]["cash_net"] == "100.00"
        assert filas[org_b.id]["cash_net"] == "700.00"

    def test_quincenal_unit_org_con_org_id_deja_fuera_la_otra(
        self, client, auth_superadmin, db, org, org_b, cajero_a, branch_a, cajero_c, branch_c,
    ):
        va = _sale(db, cajero_a, branch_a, 100, _dt(2026, 9, 5), folio=1301)
        _pago(db, va, branch_a, 100, _dt(2026, 9, 5))
        vc = _sale(db, cajero_c, branch_c, 700, _dt(2026, 9, 5), folio=1302)
        _pago(db, vc, branch_c, 700, _dt(2026, 9, 5))
        db.flush()
        r = client.get(
            "/api/platform/reports/payment-methods-biweekly",
            params={"start": "2026-09-01", "end": "2026-09-15", "unit": "org", "org_id": org.id},
            headers=auth_superadmin,
        )
        unidades = {x["unit_id"] for x in r.json()["items"]}
        assert unidades == {org.id}

    def test_quincenal_unit_org_no_junta_sucursales_huerfanas_de_orgs_distintas(
        self, client, auth_superadmin, db, cajero_a, cajero_c,
    ):
        """`organization_id` es nullable: dos sucursales sin org NO son una unidad.

        Antes se agrupaban bajo `unit_id: None` y sus importes se sumaban en
        una sola fila — dinero de nadie presentado como el de alguien.
        """
        huerfanas = []
        for nombre in ("Huérfana 1", "Huérfana 2"):
            b = Branch(name=nombre, branch_type=BranchType.STORE,
                       can_sell=True, is_active=True, organization_id=None)
            db.add(b)
            db.flush()
            huerfanas.append(b)
        for i, (b, monto) in enumerate(zip(huerfanas, (100, 700))):
            v = SalesDocument(
                seller_id=cajero_a.id, branch_id=b.id, organization_id=None,
                total_amount=Decimal(str(monto)), subtotal=Decimal(str(monto)),
                tax_amount=Decimal("0"), status=DocumentStatus.PAID,
                doc_type=DocumentType.INVOICE, created_at=_dt(2026, 9, 5),
                series="H", folio=1400 + i,
            )
            db.add(v)
            db.flush()
            db.add(Payment(sales_document_id=v.id, method=PaymentMethod.CASH,
                           amount=Decimal(str(monto)), organization_id=None,
                           created_at=_dt(2026, 9, 5)))
        db.flush()
        r = client.get(
            "/api/platform/reports/payment-methods-biweekly",
            params={"start": "2026-09-01", "end": "2026-09-15", "unit": "org"},
            headers=auth_superadmin,
        )
        assert r.status_code == 200, r.text
        filas = r.json()["items"]
        assert None not in {x["unit_id"] for x in filas}, "las huérfanas se agruparon bajo None"
        montos = sorted(x["cash_net"] for x in filas if str(x["unit_id"]).startswith("orphan-"))
        assert montos == ["100.00", "700.00"]


class TestDiaDeMexico:
    """`?start=2026-09-11` es el 11 de septiembre en México, no en UTC."""

    def test_un_corte_de_las_19_00_mx_pertenece_a_ese_dia_y_no_al_siguiente(
        self, client, auth_superadmin, db, cajero_a, branch_a,
    ):
        # 11-sep 19:00 MX (UTC−6) = 12-sep 01:00 UTC. Anclando el día en UTC
        # este corte caía en el 12 y desaparecía del reporte del 11.
        _session(db, cajero_a, branch_a, status=CashSessionStatus.CLOSED,
                 opened_at=datetime(2026, 9, 11, 14, tzinfo=timezone.utc),
                 closed_at=datetime(2026, 9, 12, 1, tzinfo=timezone.utc), difference=-40)
        r = client.get("/api/platform/reports/cash-cuts",
                       params={"start": "2026-09-11", "end": "2026-09-11"},
                       headers=auth_superadmin)
        assert r.status_code == 200, r.text
        fila = next(x for x in r.json()["items"] if x["branch_id"] == branch_a.id)
        assert fila["sessions_closed"] == 1
        assert fila["shortage_total"] == "40.00"

    def test_ese_mismo_corte_no_aparece_en_el_dia_siguiente(
        self, client, auth_superadmin, db, cajero_a, branch_a,
    ):
        _session(db, cajero_a, branch_a, status=CashSessionStatus.CLOSED,
                 opened_at=datetime(2026, 9, 11, 14, tzinfo=timezone.utc),
                 closed_at=datetime(2026, 9, 12, 1, tzinfo=timezone.utc), difference=-40)
        r = client.get("/api/platform/reports/cash-cuts",
                       params={"start": "2026-09-12", "end": "2026-09-12"},
                       headers=auth_superadmin)
        filas = [x for x in r.json()["items"] if x["branch_id"] == branch_a.id]
        assert [x["sessions_closed"] for x in filas] in ([], [0])
