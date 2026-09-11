"""Comparación de periodos en Reportes (spec 2026-09-09 §5.1).

`prev` = la ventana inmediatamente anterior de la misma longitud.
`yoy`  = las mismas fechas un año atrás (29-feb cae en 28).
El delta es None cuando la referencia es 0: dividir entre cero no es "creció
100%", es "no hay con qué comparar", y la UI pinta un guion.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.services.report_compare import compare_window, decorate_with_previous, pct_delta


def _dt(y, m, d, h=0, mi=0, s=0, us=0):
    return datetime(y, m, d, h, mi, s, us, tzinfo=timezone.utc)


_TIC = timedelta(microseconds=1)


class TestCompareWindow:
    def test_none_no_devuelve_ventana(self):
        assert compare_window(_dt(2026, 9, 1), _dt(2026, 9, 15, 23, 59, 59), "none") is None

    def test_prev_es_la_ventana_anterior_de_la_misma_longitud(self):
        # Ventana real de `_parse_dates` para 2026-09-01..2026-09-15.
        s, e = _dt(2026, 9, 1), _dt(2026, 9, 15, 23, 59, 59, 999999)
        ps, pe = compare_window(s, e, "prev")
        assert (e - s) == (pe - ps)
        assert ps == _dt(2026, 8, 17)                       # 15 días completos antes
        assert pe == _dt(2026, 8, 31, 23, 59, 59, 999999)

    def test_prev_termina_un_tic_antes_de_que_empiece_la_actual(self):
        # Las ventanas son cerradas por los dos extremos: si la previa
        # terminara EN `start`, ese instante contaría en las dos.
        s, e = _dt(2026, 9, 1), _dt(2026, 9, 15, 23, 59, 59, 999999)
        _, pe = compare_window(s, e, "prev")
        assert pe < s                    # no se solapan
        assert s - pe == _TIC            # ni dejan hueco

    def test_prev_de_un_solo_dia(self):
        s, e = _dt(2026, 9, 10), _dt(2026, 9, 10, 23, 59, 59, 999999)
        ps, pe = compare_window(s, e, "prev")
        assert (pe - ps) == (e - s)
        assert ps == _dt(2026, 9, 9)
        assert pe == _dt(2026, 9, 9, 23, 59, 59, 999999)

    def test_yoy_son_las_mismas_fechas_un_ano_atras(self):
        ps, pe = compare_window(_dt(2026, 9, 1), _dt(2026, 9, 15, 23, 59, 59), "yoy")
        assert ps == _dt(2025, 9, 1)
        assert pe == _dt(2025, 9, 15, 23, 59, 59)

    def test_yoy_del_29_de_febrero_cae_en_28(self):
        ps, pe = compare_window(_dt(2028, 2, 29), _dt(2028, 2, 29, 23, 59, 59), "yoy")
        assert ps == _dt(2027, 2, 28)
        assert pe == _dt(2027, 2, 28, 23, 59, 59)

    def test_modo_invalido_es_un_error_de_valor(self):
        with pytest.raises(ValueError):
            compare_window(_dt(2026, 9, 1), _dt(2026, 9, 2), "el mes pasado")


class TestPctDelta:
    def test_crecimiento_y_caida_con_un_decimal(self):
        assert pct_delta(Decimal("150"), Decimal("100")) == 50.0
        assert pct_delta(Decimal("96"), Decimal("100")) == -4.0

    def test_referencia_cero_o_ausente_es_none(self):
        assert pct_delta(Decimal("150"), Decimal("0")) is None
        assert pct_delta(Decimal("150"), None) is None

    def test_acepta_cadenas_y_floats(self):
        assert pct_delta("110", "100") == 10.0
        assert pct_delta(110.0, 100.0) == 10.0


class TestDecorate:
    def test_empareja_por_llave_y_agrega_prev_y_delta(self):
        items = [{"branch_id": 1, "revenue": "100.00", "transactions": 10}]
        prev = [{"branch_id": 1, "revenue": "80.00", "transactions": 8}]
        out = decorate_with_previous(items, prev, key="branch_id", fields=("revenue", "transactions"))
        assert out[0]["prev_revenue"] == "80.00"
        assert out[0]["delta_revenue_pct"] == 25.0
        assert out[0]["prev_transactions"] == 8          # un conteo, no "8.00"
        assert out[0]["delta_transactions_pct"] == 25.0

    def test_el_prev_copia_la_forma_del_campo_actual(self):
        # El dinero llega como cadena con dos decimales y los conteos como
        # enteros: cuantizar todo por igual inventaba decimales en los conteos.
        out = decorate_with_previous(
            [{"k": 1, "revenue": "100.00", "tickets": 10, "units": 2.5}],
            [{"k": 1, "revenue": "80.00", "tickets": 8, "units": 2.0}],
            key="k", fields=("revenue", "tickets", "units"),
        )
        assert out[0]["prev_revenue"] == "80.00"
        assert out[0]["prev_tickets"] == 8 and isinstance(out[0]["prev_tickets"], int)
        assert out[0]["prev_units"] == 2.0 and isinstance(out[0]["prev_units"], float)

    def test_fila_sin_par_previo_lleva_cero_y_delta_none(self):
        out = decorate_with_previous(
            [{"branch_id": 2, "revenue": "50.00"}], [], key="branch_id", fields=("revenue",),
        )
        assert out[0]["prev_revenue"] == "0.00"
        assert out[0]["delta_revenue_pct"] is None

    def test_sin_par_previo_un_conteo_es_cero_entero(self):
        out = decorate_with_previous(
            [{"k": 2, "tickets": 5}], [], key="k", fields=("tickets",),
        )
        assert out[0]["prev_tickets"] == 0
        assert out[0]["delta_tickets_pct"] is None

    def test_no_muta_la_lista_de_entrada(self):
        items = [{"branch_id": 1, "revenue": "100.00"}]
        decorate_with_previous(items, [], key="branch_id", fields=("revenue",))
        assert items[0] == {"branch_id": 1, "revenue": "100.00"}


from app.models.sales import DocumentStatus, DocumentType, SalesDocument
from app.routers.platform import reports as platform_reports


@pytest.fixture(autouse=True)
def _clear_reports_cache():
    platform_reports._cache.clear()
    yield
    platform_reports._cache.clear()


def _sale(db, seller, branch, amount, created_at):
    sale = SalesDocument(
        seller_id=seller.id, branch_id=branch.id, organization_id=branch.organization_id,
        total_amount=Decimal(str(amount)), subtotal=Decimal(str(amount)), tax_amount=Decimal("0"),
        status=DocumentStatus.PAID, doc_type=DocumentType.INVOICE, created_at=created_at,
    )
    db.add(sale)
    db.flush()
    return sale


class TestCompareEnLosPivotes:
    """El endpoint corre la misma consulta para la ventana previa y pega los deltas."""

    def test_branches_sin_compare_no_trae_campos_extra(self, client, auth_superadmin, db, cajero_a, branch_a):
        _sale(db, cajero_a, branch_a, 100, _dt(2026, 9, 10, 18))
        r = client.get(
            "/api/platform/reports/branches",
            params={"start": "2026-09-01", "end": "2026-09-15"},
            headers=auth_superadmin,
        )
        assert r.status_code == 200, r.text
        row = r.json()["items"][0]
        assert "prev_revenue" not in row and "delta_revenue_pct" not in row

    def test_branches_con_prev_trae_prev_y_delta(self, client, auth_superadmin, db, cajero_a, branch_a):
        _sale(db, cajero_a, branch_a, 150, _dt(2026, 9, 10, 18))   # periodo
        _sale(db, cajero_a, branch_a, 100, _dt(2026, 8, 20, 18))   # ventana previa
        r = client.get(
            "/api/platform/reports/branches",
            params={"start": "2026-09-01", "end": "2026-09-15", "compare": "prev"},
            headers=auth_superadmin,
        )
        assert r.status_code == 200, r.text
        row = next(x for x in r.json()["items"] if x["branch_id"] == branch_a.id)
        assert row["revenue"] == "150.00"
        assert row["prev_revenue"] == "100.00"
        assert row["delta_revenue_pct"] == 50.0

    def test_entidad_nueva_en_el_periodo_lleva_delta_none(self, client, auth_superadmin, db, cajero_a, branch_a):
        _sale(db, cajero_a, branch_a, 150, _dt(2026, 9, 10, 18))
        r = client.get(
            "/api/platform/reports/branches",
            params={"start": "2026-09-01", "end": "2026-09-15", "compare": "prev"},
            headers=auth_superadmin,
        )
        row = next(x for x in r.json()["items"] if x["branch_id"] == branch_a.id)
        assert row["prev_revenue"] == "0.00"
        assert row["delta_revenue_pct"] is None

    def test_compare_invalido_422(self, client, auth_superadmin):
        r = client.get(
            "/api/platform/reports/branches",
            params={"compare": "el mes pasado"},
            headers=auth_superadmin,
        )
        assert r.status_code == 422

    def test_los_cuatro_pivotes_aceptan_compare(self, client, auth_superadmin):
        for path in ("products", "branches", "sellers", "customers"):
            r = client.get(
                f"/api/platform/reports/{path}",
                params={"compare": "yoy"},
                headers=auth_superadmin,
            )
            assert r.status_code == 200, f"{path}: {r.text}"

    def test_ventana_previa_se_cachea_entre_paginas_y_orden(
        self, client, auth_superadmin, db, cajero_a, branch_a, monkeypatch,
    ):
        """F4: _rows_for_window de la ventana previa NO debe recalcularse por
        cada combinación de limit/offset/sort — su cache es independiente."""
        _sale(db, cajero_a, branch_a, 150, _dt(2026, 9, 10, 18))
        _sale(db, cajero_a, branch_a, 100, _dt(2026, 8, 20, 18))  # ventana previa

        calls = {"n": 0}
        original = platform_reports._rows_for_window

        def _counting(db_, s_, e_, org_id_, branch_id_, *, pivot):
            if s_.month == 8:  # solo contamos la ventana previa (agosto)
                calls["n"] += 1
            return original(db_, s_, e_, org_id_, branch_id_, pivot=pivot)

        monkeypatch.setattr(platform_reports, "_rows_for_window", _counting)

        common = {"start": "2026-09-01", "end": "2026-09-15", "compare": "prev"}
        r1 = client.get(
            "/api/platform/reports/branches",
            params={**common, "sort": "revenue:desc", "offset": 0},
            headers=auth_superadmin,
        )
        r2 = client.get(
            "/api/platform/reports/branches",
            params={**common, "sort": "name:asc", "offset": 0},
            headers=auth_superadmin,
        )
        assert r1.status_code == 200, r1.text
        assert r2.status_code == 200, r2.text
        assert calls["n"] == 1, "distinto sort recalculó la ventana previa en vez de reusar el cache"
