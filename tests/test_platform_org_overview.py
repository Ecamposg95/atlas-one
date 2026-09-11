"""Tablero de plataforma por organización (W6, adaptado de la spec 2026-09-09 §4).

Adaptación semántica de Atlas ONE: el SUPERADMIN atiende a muchos clientes
distintos, no a un grupo de un solo dueño. Por eso el resumen es de UNA
organización a la vez (ningún KPI suma dinero de dos organizaciones) y solo
la tira "Atención hoy" cruza a todas.

El día es el de la zona de negocio (México): una venta a las 23:30 MX del 5 de
agosto (05:30 UTC del 6) cuenta para el 5.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.core.security import create_access_token, get_password_hash
from app.models.cash import CashSession, CashSessionStatus
from app.models.cash_audit import CashAuditEvent, CashAuditLog
from app.models.organization import Branch, BranchType, Organization
from app.models.returns import SaleReturn
from app.models.sales import (
    DocumentStatus,
    DocumentType,
    Payment,
    PaymentMethod,
    SalesDocument,
)
from app.models.users import PlatformRole, Role, User, UserOrganization
from app.routers.platform import stats as platform_stats
from app.services.org_overview import (
    ZONA_NEGOCIO,
    compute_attention_today,
    compute_org_overview,
    day_window,
    day_windows,
)

DAY = date(2026, 8, 5)
NOW = datetime(2026, 8, 6, 3, 0, tzinfo=timezone.utc)   # 21:00 MX del 5 de agosto


@pytest.fixture(autouse=True)
def _limpia_cache():
    platform_stats._cache.clear()
    yield
    platform_stats._cache.clear()


# ── Fixtures propias: la segunda organización (el conftest solo trae una) ─────

@pytest.fixture()
def org_b(db):
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
        platform_role=PlatformRole.NONE,
    )
    db.add(u)
    db.flush()
    db.add(UserOrganization(user_id=u.id, organization_id=org_b.id,
                            org_role="MEMBER", is_active=True))
    db.flush()
    return u


@pytest.fixture()
def auth_support(db, org, hq_branch):
    u = User(
        username="soporte_test", password_hash=get_password_hash("test1234"),
        role=Role.ADMINISTRADOR, branch_id=hq_branch.id, is_active=True,
        platform_role=PlatformRole.SUPPORT,
    )
    db.add(u)
    db.flush()
    db.add(UserOrganization(user_id=u.id, organization_id=org.id,
                            org_role="MEMBER", is_active=True))
    db.flush()
    return {"Authorization": f"Bearer {create_access_token({'sub': u.username})}"}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _sale(db, seller, branch, amount, created_at, *, status=DocumentStatus.PAID,
          payments=None, change_given=Decimal("0")):
    sale = SalesDocument(
        seller_id=seller.id, branch_id=branch.id, organization_id=branch.organization_id,
        total_amount=Decimal(str(amount)), subtotal=Decimal(str(amount)), tax_amount=Decimal("0"),
        status=status, doc_type=DocumentType.INVOICE, created_at=created_at,
        change_given=Decimal(str(change_given)),
    )
    db.add(sale)
    db.flush()
    for method, amt in (payments or [(PaymentMethod.CASH, amount)]):
        db.add(Payment(sales_document_id=sale.id, method=method, amount=Decimal(str(amt)),
                       organization_id=branch.organization_id, created_at=created_at))
    db.flush()
    return sale


def _session(db, user, branch, *, status, opened_at, closed_at=None, difference=None):
    s = CashSession(
        user_id=user.id, branch_id=branch.id, organization_id=branch.organization_id,
        status=status, opened_at=opened_at, closed_at=closed_at,
        opening_balance=Decimal("0"), closing_balance=Decimal("0"),
        difference=Decimal(str(difference)) if difference is not None else Decimal("0"),
    )
    db.add(s)
    db.flush()
    return s


def _audit(db, branch, event_type, amount, ts):
    row = CashAuditLog(
        ts=ts, organization_id=branch.organization_id, branch_id=branch.id,
        event_type=event_type, amount=Decimal(str(amount)),
        related_table="x", related_id="x",
    )
    db.add(row)
    db.flush()
    return row


def _return(db, sale, user, branch, amount, created_at, status="PENDING"):
    r = SaleReturn(
        sale_id=sale.id, user_id=user.id, branch_id=branch.id,
        organization_id=branch.organization_id,
        total_refunded=Decimal(str(amount)), refund_method=PaymentMethod.CASH,
        reason="t", status=status, created_at=created_at,
    )
    db.add(r)
    db.flush()
    return r


def _row(overview, branch_id):
    return next(r for r in overview["rows"] if r["id"] == branch_id)


# ── Ventanas ─────────────────────────────────────────────────────────────────

class TestVentanas:
    def test_la_ventana_del_dia_es_medianoche_de_negocio_en_utc(self):
        w = day_window(DAY)
        # Agosto: MX = UTC-6 → el día empieza a las 06:00Z y termina a las 06:00Z del siguiente
        assert w.start == datetime(2026, 8, 5, 6, 0, tzinfo=timezone.utc)
        assert w.end == datetime(2026, 8, 6, 6, 0, tzinfo=timezone.utc)
        assert ZONA_NEGOCIO.key == "America/Mexico_City"

    def test_trae_ayer_y_el_mismo_dia_de_la_semana_pasada(self):
        ws = day_windows(DAY)
        assert ws["yesterday"].start == day_window(date(2026, 8, 4)).start
        assert ws["last_week"].start == day_window(date(2026, 7, 29)).start


# ── Ventas de una organización ───────────────────────────────────────────────

class TestVentas:
    def test_venta_a_las_2330_cuenta_para_ese_dia(self, db, org, cajero_a, branch_a):
        _sale(db, cajero_a, branch_a, 100, datetime(2026, 8, 6, 5, 30, tzinfo=timezone.utc))  # 23:30 MX del 5
        _sale(db, cajero_a, branch_a, 999, datetime(2026, 8, 6, 6, 30, tzinfo=timezone.utc))  # 00:30 MX del 6
        ov = compute_org_overview(db, organization_id=org.id, day=DAY, now=NOW)
        assert _row(ov, branch_a.id)["sales_today"] == 100.0
        assert _row(ov, branch_a.id)["tickets_today"] == 1

    def test_cancelada_fuera_y_devuelta_parcial_neta_dentro(self, db, org, cajero_a, branch_a):
        t = datetime(2026, 8, 5, 18, 0, tzinfo=timezone.utc)
        _sale(db, cajero_a, branch_a, 500, t, status=DocumentStatus.CANCELLED)
        _sale(db, cajero_a, branch_a, 80, t, status=DocumentStatus.REFUNDED_PARTIAL)   # ya neteada
        _sale(db, cajero_a, branch_a, 120, t)
        r = _row(compute_org_overview(db, organization_id=org.id, day=DAY, now=NOW), branch_a.id)
        assert r["sales_today"] == 200.0
        assert r["tickets_today"] == 2
        assert r["avg_ticket"] == 100.0

    def test_deltas_vs_ayer_y_vs_semana_pasada(self, db, org, cajero_a, branch_a):
        _sale(db, cajero_a, branch_a, 150, datetime(2026, 8, 5, 18, 0, tzinfo=timezone.utc))
        _sale(db, cajero_a, branch_a, 100, datetime(2026, 8, 4, 18, 0, tzinfo=timezone.utc))   # ayer
        _sale(db, cajero_a, branch_a, 300, datetime(2026, 7, 29, 18, 0, tzinfo=timezone.utc))  # miércoles pasado
        r = _row(compute_org_overview(db, organization_id=org.id, day=DAY, now=NOW), branch_a.id)
        assert r["sales_yesterday"] == 100.0
        assert r["sales_same_weekday_last_week"] == 300.0
        assert r["delta_yesterday_pct"] == 50.0
        assert r["delta_last_week_pct"] == -50.0

    def test_delta_es_none_si_la_referencia_es_cero(self, db, org, cajero_a, branch_a):
        _sale(db, cajero_a, branch_a, 150, datetime(2026, 8, 5, 18, 0, tzinfo=timezone.utc))
        r = _row(compute_org_overview(db, organization_id=org.id, day=DAY, now=NOW), branch_a.id)
        assert r["delta_yesterday_pct"] is None
        assert r["delta_last_week_pct"] is None

    def test_mix_de_efectivo_neto_de_cambio(self, db, org, cajero_a, branch_a):
        t = datetime(2026, 8, 5, 18, 0, tzinfo=timezone.utc)
        # total 150: tarjeta 100 + efectivo 60 (cambio 10) → efectivo neto 50
        _sale(db, cajero_a, branch_a, 150, t,
              payments=[(PaymentMethod.CARD, 100), (PaymentMethod.CASH, 60)], change_given=10)
        r = _row(compute_org_overview(db, organization_id=org.id, day=DAY, now=NOW), branch_a.id)
        assert r["mix"]["cash"] == 50.0
        assert r["mix"]["card"] == 100.0
        assert r["mix"]["cash_pct"] == pytest.approx(33.3, abs=0.1)
        assert r["mix"]["card_pct"] == pytest.approx(66.7, abs=0.1)

    def test_sucursal_sin_ventas_aparece_en_ceros(self, db, org, branch_a, branch_b):
        ov = compute_org_overview(db, organization_id=org.id, day=DAY, now=NOW)
        ids = {r["id"] for r in ov["rows"]}
        assert branch_a.id in ids and branch_b.id in ids
        r = _row(ov, branch_b.id)
        assert r["sales_today"] == 0.0 and r["tickets_today"] == 0 and r["avg_ticket"] is None
        assert r["mix"]["cash_pct"] is None

    def test_la_sucursal_que_no_vende_no_aparece(self, db, org, hq_branch, branch_a):
        ov = compute_org_overview(db, organization_id=org.id, day=DAY, now=NOW)
        assert hq_branch.id not in {r["id"] for r in ov["rows"]}   # can_sell=False

    def test_totales_son_la_suma_de_las_sucursales_de_esa_organizacion(
        self, db, org, cajero_a, branch_a, branch_b
    ):
        t = datetime(2026, 8, 5, 18, 0, tzinfo=timezone.utc)
        _sale(db, cajero_a, branch_a, 100, t)
        _sale(db, cajero_a, branch_b, 250, t)
        ov = compute_org_overview(db, organization_id=org.id, day=DAY, now=NOW)
        assert ov["totals"]["sales_today"] == sum(r["sales_today"] for r in ov["rows"]) == 350.0
        assert ov["totals"]["tickets_today"] == 2
        assert ov["totals"]["avg_ticket"] == 175.0
        assert ov["totals"]["units"] == 2
        assert ov["organization_id"] == org.id and ov["date"] == "2026-08-05"


class TestAislamientoEntreOrganizaciones:
    """El corazón de la adaptación: ningún KPI suma dinero de dos organizaciones."""

    def test_el_resumen_ignora_las_sucursales_y_el_dinero_de_otra_organizacion(
        self, db, org, org_b, cajero_a, cajero_c, branch_a, branch_c
    ):
        t = datetime(2026, 8, 5, 18, 0, tzinfo=timezone.utc)
        _sale(db, cajero_a, branch_a, 100, t)
        _sale(db, cajero_c, branch_c, 9000, t)
        a = compute_org_overview(db, organization_id=org.id, day=DAY, now=NOW)
        b = compute_org_overview(db, organization_id=org_b.id, day=DAY, now=NOW)
        assert branch_c.id not in {r["id"] for r in a["rows"]}
        assert branch_a.id not in {r["id"] for r in b["rows"]}
        assert a["totals"]["sales_today"] == 100.0
        assert b["totals"]["sales_today"] == 9000.0
        assert all(r["org_id"] == org.id for r in a["rows"])

    def test_una_devolucion_de_otra_organizacion_no_entra_en_los_totales(
        self, db, org, org_b, cajero_c, branch_a, branch_c
    ):
        t = datetime(2026, 8, 5, 18, 0, tzinfo=timezone.utc)
        venta = _sale(db, cajero_c, branch_c, 100, t)
        _return(db, venta, cajero_c, branch_c, 75, NOW - timedelta(days=3))
        a = compute_org_overview(db, organization_id=org.id, day=DAY, now=NOW)
        assert a["totals"]["returns_pending_count"] == 0
        assert a["totals"]["returns_pending_amount"] == 0.0


# ── Caja ─────────────────────────────────────────────────────────────────────

class TestCaja:
    def test_dos_cajeras_abiertas_cuentan_desde_la_mas_antigua(self, db, org, cajero_a, gerente_a, branch_a):
        _session(db, cajero_a, branch_a, status=CashSessionStatus.OPEN, opened_at=NOW - timedelta(hours=2))
        _session(db, gerente_a, branch_a, status=CashSessionStatus.OPEN, opened_at=NOW - timedelta(hours=16))
        r = _row(compute_org_overview(db, organization_id=org.id, day=DAY, now=NOW), branch_a.id)
        assert r["cash"]["status"] == "OPEN"
        assert r["cash"]["open_sessions"] == 2 and r["cash"]["open_hours"] == 16.0

    def test_el_ultimo_corte_usa_la_diferencia_persistida(self, db, org, cajero_a, branch_a):
        _session(db, cajero_a, branch_a, status=CashSessionStatus.CLOSED,
                 opened_at=NOW - timedelta(days=2), closed_at=NOW - timedelta(days=2, hours=-8),
                 difference=-999)
        last = _session(db, cajero_a, branch_a, status=CashSessionStatus.CLOSED,
                        opened_at=NOW - timedelta(hours=10), closed_at=NOW - timedelta(hours=1),
                        difference=-221)
        r = _row(compute_org_overview(db, organization_id=org.id, day=DAY, now=NOW), branch_a.id)
        assert r["cash"]["status"] == "CLOSED"
        assert r["cash"]["last_difference"] == -221.0
        assert r["cash"]["last_session_id"] == last.id

    def test_totales_de_caja_de_la_organizacion(self, db, org, cajero_a, branch_a, branch_b):
        _session(db, cajero_a, branch_a, status=CashSessionStatus.OPEN, opened_at=NOW - timedelta(hours=3))
        ov = compute_org_overview(db, organization_id=org.id, day=DAY, now=NOW)
        assert ov["totals"]["open_sessions"] == 1
        assert ov["totals"]["units_with_open_session"] == 1
        assert ov["totals"]["units"] == 2


# ── Devoluciones y cancelaciones ─────────────────────────────────────────────

class TestDevolucionesYCancelaciones:
    def test_pendientes_monto_y_edad_de_la_mas_vieja(self, db, org, cajero_a, branch_a):
        t = datetime(2026, 8, 5, 18, 0, tzinfo=timezone.utc)
        s1, s2, s3 = (_sale(db, cajero_a, branch_a, 100, t) for _ in range(3))
        _return(db, s1, cajero_a, branch_a, 40, NOW - timedelta(days=93))
        _return(db, s2, cajero_a, branch_a, 60, NOW - timedelta(days=2))
        _return(db, s3, cajero_a, branch_a, 999, NOW - timedelta(days=5), status="APPROVED")
        r = _row(compute_org_overview(db, organization_id=org.id, day=DAY, now=NOW), branch_a.id)["returns"]
        assert r["pending_count"] == 2 and r["pending_amount"] == 100.0
        assert r["oldest_pending_days"] == 93

    def test_aprobadas_de_hoy_salen_del_audit_log(self, db, org, branch_a):
        hoy = datetime(2026, 8, 5, 20, 0, tzinfo=timezone.utc)
        ayer = datetime(2026, 8, 4, 20, 0, tzinfo=timezone.utc)
        _audit(db, branch_a, CashAuditEvent.REFUND_APPROVED, 220, hoy)
        _audit(db, branch_a, CashAuditEvent.REFUND_APPROVED, 999, ayer)
        r = _row(compute_org_overview(db, organization_id=org.id, day=DAY, now=NOW), branch_a.id)
        assert r["returns"]["approved_today_count"] == 1
        assert r["returns"]["approved_today_amount"] == 220.0

    def test_las_canceladas_de_hoy_salen_de_las_ventas_canceladas(self, db, org, cajero_a, branch_a):
        hoy = datetime(2026, 8, 5, 20, 0, tzinfo=timezone.utc)
        ayer = datetime(2026, 8, 4, 20, 0, tzinfo=timezone.utc)
        _sale(db, cajero_a, branch_a, 300, hoy, status=DocumentStatus.CANCELLED)
        _sale(db, cajero_a, branch_a, 120, hoy, status=DocumentStatus.CANCELLED)
        _sale(db, cajero_a, branch_a, 5000, ayer, status=DocumentStatus.CANCELLED)
        r = _row(compute_org_overview(db, organization_id=org.id, day=DAY, now=NOW), branch_a.id)
        assert r["cancellations_today_count"] == 2
        assert r["cancellations_today_amount"] == 420.0
        assert r["sales_today"] == 0.0   # una cancelada no es venta


# ── Atención hoy (cruza TODAS las organizaciones) ────────────────────────────

class TestAtencionHoy:
    def test_una_caja_abierta_15h_entra_y_la_de_13h_no(self, db, cajero_a, branch_a, branch_b):
        _session(db, cajero_a, branch_a, status=CashSessionStatus.OPEN, opened_at=NOW - timedelta(hours=15))
        _session(db, cajero_a, branch_b, status=CashSessionStatus.OPEN, opened_at=NOW - timedelta(hours=13))
        a = compute_attention_today(db, day=DAY, now=NOW)
        assert [i["id"] for i in a["no_cut"]] == [branch_a.id]
        assert a["no_cut"][0]["value"] == 15.0

    def test_la_tira_cruza_organizaciones(self, db, org, org_b, cajero_a, cajero_c, branch_a, branch_c):
        _session(db, cajero_a, branch_a, status=CashSessionStatus.CLOSED,
                 opened_at=NOW - timedelta(hours=10), closed_at=NOW - timedelta(hours=1), difference=-50)
        _session(db, cajero_c, branch_c, status=CashSessionStatus.CLOSED,
                 opened_at=NOW - timedelta(hours=10), closed_at=NOW - timedelta(hours=2), difference=-400)
        a = compute_attention_today(db, day=DAY, now=NOW)
        # ordenadas por diferencia absoluta: primero la de la otra organización
        assert [i["id"] for i in a["cut_difference"]] == [branch_c.id, branch_a.id]
        assert {i["org_id"] for i in a["cut_difference"]} == {org.id, org_b.id}
        assert {i["org_name"] for i in a["cut_difference"]} == {"Test Org", "Otra Org"}

    def test_un_corte_en_cero_no_pide_atencion(self, db, cajero_a, branch_a):
        _session(db, cajero_a, branch_a, status=CashSessionStatus.CLOSED,
                 opened_at=NOW - timedelta(hours=10), closed_at=NOW - timedelta(hours=1), difference=0)
        assert compute_attention_today(db, day=DAY, now=NOW)["cut_difference"] == []

    def test_devoluciones_pendientes_ordenadas_por_monto(self, db, cajero_a, cajero_c, branch_a, branch_c):
        t = datetime(2026, 8, 5, 18, 0, tzinfo=timezone.utc)
        sa = _sale(db, cajero_a, branch_a, 100, t)
        sc = _sale(db, cajero_c, branch_c, 100, t)
        _return(db, sa, cajero_a, branch_a, 10, NOW - timedelta(days=1))
        _return(db, sc, cajero_c, branch_c, 500, NOW - timedelta(days=1))
        a = compute_attention_today(db, day=DAY, now=NOW)
        assert [i["id"] for i in a["oldest_returns"]] == [branch_c.id, branch_a.id]

    def test_canceladas_de_hoy_en_la_tira(self, db, cajero_a, branch_a):
        _sale(db, cajero_a, branch_a, 300, datetime(2026, 8, 5, 20, 0, tzinfo=timezone.utc),
              status=DocumentStatus.CANCELLED)
        a = compute_attention_today(db, day=DAY, now=NOW)
        assert [i["id"] for i in a["cancelled_today"]] == [branch_a.id]
        assert a["cancelled_today"][0]["value"] == 300.0

    def test_la_tira_no_suma_dinero_entre_organizaciones(self, db, cajero_a, cajero_c, branch_a, branch_c):
        """Cada renglón trae SU monto y SU organización; la respuesta no lleva total."""
        t = datetime(2026, 8, 5, 18, 0, tzinfo=timezone.utc)
        sa = _sale(db, cajero_a, branch_a, 100, t)
        sc = _sale(db, cajero_c, branch_c, 100, t)
        _return(db, sa, cajero_a, branch_a, 10, NOW - timedelta(days=1))
        _return(db, sc, cajero_c, branch_c, 500, NOW - timedelta(days=1))
        a = compute_attention_today(db, day=DAY, now=NOW)
        assert set(a) == {"date", "generated_at", "no_cut", "cut_difference",
                          "oldest_returns", "cancelled_today"}
        assert [i["value"] for i in a["oldest_returns"]] == [500.0, 10.0]


# ── Endpoints ────────────────────────────────────────────────────────────────

class TestEndpoints:
    def test_403_para_administrador_de_tenant(self, client, auth_admin, org):
        assert client.get(f"/api/platform/organizations/{org.id}/overview",
                          headers=auth_admin).status_code == 403
        assert client.get("/api/platform/attention-today", headers=auth_admin).status_code == 403

    def test_support_puede_leer(self, client, auth_support, org):
        assert client.get(f"/api/platform/organizations/{org.id}/overview",
                          headers=auth_support).status_code == 200
        assert client.get("/api/platform/attention-today", headers=auth_support).status_code == 200

    def test_forma_de_la_respuesta(self, client, auth_superadmin, db, org, cajero_a, branch_a):
        _sale(db, cajero_a, branch_a, 100, datetime(2026, 8, 5, 18, 0, tzinfo=timezone.utc))
        r = client.get(f"/api/platform/organizations/{org.id}/overview",
                       params={"date": "2026-08-05"}, headers=auth_superadmin)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["organization_id"] == org.id
        assert body["organization_name"] == "Test Org"
        assert body["date"] == "2026-08-05"
        assert set(body["totals"]) >= {"units", "sales_today", "tickets_today", "avg_ticket",
                                       "open_sessions", "units_with_open_session",
                                       "returns_pending_count", "returns_pending_amount",
                                       "cancellations_today_count", "mix"}
        row = next(x for x in body["rows"] if x["id"] == branch_a.id)
        assert row["sales_today"] == 100.0
        assert set(row["cash"]) == {"status", "open_sessions", "open_hours", "last_close_at",
                                    "last_difference", "last_session_id"}

    def test_organizacion_inexistente_404(self, client, auth_superadmin):
        assert client.get("/api/platform/organizations/999999/overview",
                          headers=auth_superadmin).status_code == 404

    def test_fecha_invalida_422(self, client, auth_superadmin, org):
        assert client.get(f"/api/platform/organizations/{org.id}/overview",
                          params={"date": "ayer"}, headers=auth_superadmin).status_code == 422

    def test_fecha_fuera_de_rango_422(self, client, auth_superadmin, org):
        assert client.get(f"/api/platform/organizations/{org.id}/overview",
                          params={"date": "2020-01-01"}, headers=auth_superadmin).status_code == 422

    def test_forma_de_atencion_hoy(self, client, auth_superadmin, db, cajero_a, branch_a):
        _session(db, cajero_a, branch_a, status=CashSessionStatus.OPEN,
                 opened_at=datetime.now(timezone.utc) - timedelta(hours=20))
        r = client.get("/api/platform/attention-today", headers=auth_superadmin)
        assert r.status_code == 200, r.text
        body = r.json()
        assert set(body) == {"date", "generated_at", "no_cut", "cut_difference",
                             "oldest_returns", "cancelled_today"}
        assert [i["id"] for i in body["no_cut"]] == [branch_a.id]
        assert body["no_cut"][0]["org_name"] == "Test Org"

    def test_cache_de_60s_devuelve_lo_mismo_hasta_limpiar(self, client, auth_superadmin, db,
                                                          org, cajero_a, branch_a):
        url = f"/api/platform/organizations/{org.id}/overview"
        params = {"date": "2026-08-05"}
        first = client.get(url, params=params, headers=auth_superadmin).json()
        _sale(db, cajero_a, branch_a, 100, datetime(2026, 8, 5, 18, 0, tzinfo=timezone.utc))
        cached = client.get(url, params=params, headers=auth_superadmin).json()
        assert cached["totals"]["sales_today"] == first["totals"]["sales_today"] == 0.0
        platform_stats._cache.clear()
        fresh = client.get(url, params=params, headers=auth_superadmin).json()
        assert fresh["totals"]["sales_today"] == 100.0

    def test_el_cache_no_confunde_dos_organizaciones(self, client, auth_superadmin, db,
                                                     org, org_b, cajero_a, cajero_c,
                                                     branch_a, branch_c):
        t = datetime(2026, 8, 5, 18, 0, tzinfo=timezone.utc)
        _sale(db, cajero_a, branch_a, 100, t)
        _sale(db, cajero_c, branch_c, 9000, t)
        params = {"date": "2026-08-05"}
        a = client.get(f"/api/platform/organizations/{org.id}/overview",
                       params=params, headers=auth_superadmin).json()
        b = client.get(f"/api/platform/organizations/{org_b.id}/overview",
                       params=params, headers=auth_superadmin).json()
        assert a["totals"]["sales_today"] == 100.0
        assert b["totals"]["sales_today"] == 9000.0
