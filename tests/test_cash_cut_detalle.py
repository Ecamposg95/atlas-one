# tests/test_cash_cut_detalle.py
"""El corte de turno lleva las devoluciones con hora, folio y marca de
efectivo — no solo un conteo y un total.

`get_session_audit_data` (app/routers/cash.py) es la capa de datos que
consumen la UI, el ticket térmico y el PDF; aquí se prueba la forma de
`returns.list` / `returns.by_method` y cómo el ticket la imprime. El orden
de las cuatro secciones del corte y la aritmética entre ellas viven en
`tests/test_cash_cut_historia.py`, que importa los helpers de este archivo.

La fórmula del esperado NO se toca: `compute_expected_cash` sigue siendo la
única fuente (ver `tests/test_cash_math.py`)."""
from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.pos_printer import PosPrinter

MX = ZoneInfo("America/Mexico_City")

# 58mm → 32 cols, 80mm → 56 cols (ver PosPrinter.DEFAULT_COLS_*). Son los
# dos anchos que el producto realmente imprime.
ALL_WIDTHS_MM = [58, 80]


def _strip_esc_commands(raw: bytes, printer: PosPrinter) -> bytes:
    """Quita los comandos ESC/POS por su longitud REAL, de más largo a más
    corto (un comando corto que sea prefijo de uno largo no puede comerse
    medio comando y dejar basura que descuadre el conteo de columnas).

    `LF` se excluye a propósito: es el mismo byte que un '\\n' de texto, o
    sea el separador de línea real del papel. Borrarlo fusionaría todas las
    líneas en una sola cadena y cualquier medición contra `cols` dejaría de
    significar nada.

    El corte no imprime logo, así que no hay bloques raster `GS v 0` que
    saltar (a diferencia del ticket de venta)."""
    cmds = sorted(
        (v for k, v in printer.CMD.items() if k != "LF"),
        key=len, reverse=True,
    )
    out = raw
    for c in cmds:
        if c:
            out = out.replace(c, b"")
    return out


def _visible_text(raw: bytes, printer: PosPrinter) -> str:
    """Único camino de medición del archivo: limpia y comprueba que no quedó
    ningún byte de control sin remover — si quedara, `CMD` no cubre algún
    comando nuevo y CUALQUIER conteo de columnas hecho sobre ese texto sería
    inválido."""
    stripped = _strip_esc_commands(raw, printer)
    assert b"\x1b" not in stripped, f"quedó un ESC residual: {stripped!r}"
    assert b"\x1d" not in stripped, f"quedó un GS residual: {stripped!r}"
    return stripped.decode("latin-1", "replace")


def _visible_lines(raw: bytes, printer: PosPrinter) -> list:
    return _visible_text(raw, printer).split("\n")


def _audit(**over):
    """Datos mínimos de un corte cerrado, con la forma que devuelve
    `get_session_audit_data`."""
    base = {
        "session": {
            "id": 42,
            "opened_at": datetime(2026, 8, 5, 9, 0, tzinfo=MX),
            "closed_at": datetime(2026, 8, 5, 20, 30, tzinfo=MX),
            "opening_balance": 1000.0,
            "closing_balance": 5000.0,
            "last_activity": datetime(2026, 8, 5, 20, 15, tzinfo=MX),
            "user_name": "KIMBERLY",
            "branch_name": "SUCURSAL NORTE",
            "organization_name": "ATLAS ONE",
        },
        "payments": {
            "cash": {"total": 4000.0, "count": 30},
            "card": {"total": 1920.5, "count": 2},
            "transfer": {"total": 0.0, "count": 0},
            "store_credit": {"total": 0.0, "count": 0},
            "check": {"total": 0.0, "count": 0},
            "others": {"total": 0.0, "count": 0},
        },
        "movements": {"inflows": 0.0, "outflows": 0.0, "list": []},
        "returns": {
            "count": 0, "total": 0.0, "cash_refunds": 0.0, "list": [],
            "by_method": {"cash": 0.0, "card": 0.0, "transfer": 0.0, "other": 0.0},
        },
        "kpis": {
            "total_sales": 5920.5, "total_tickets": 32,
            "avg_ticket": 185.02, "total_taxes": 0.0, "subtotal": 5920.5,
        },
        "expected": {"cash_physical": 5000.0, "total_system": 6920.5},
        "reconciliation": {"reported": 5000.0, "difference": 0.0, "diff_percent": 0.0},
    }
    base.update(over)
    return base


def _devolucion(db, sale, branch, user, session, *, amount, method, created_at,
                status="PENDING"):
    from app.models.returns import SaleReturn
    ret = SaleReturn(
        sale_id=sale.id,
        user_id=user.id,
        branch_id=branch.id,
        cash_session_id=session.id,
        total_refunded=Decimal(str(amount)),
        refund_method=method,
        reason="Defectuoso",
        status=status,
        organization_id=branch.organization_id,
        created_at=created_at,
    )
    db.add(ret)
    db.flush()
    return ret


# ── Forma de los datos (get_session_audit_data) ──────────────────────────────


class TestFormaDeLosDatosDeDevoluciones:
    def _escenario(self, db, cajero_a, branch_a):
        from app.models.sales import PaymentMethod
        from tests.test_cash_math import _open_session, _create_sale

        opened = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)  # 06:00 MX
        session = _open_session(db, cajero_a, branch_a, opening=0, opened_at=opened)
        sale = _create_sale(
            db, cajero_a, branch_a, total=1000.00,
            payments=[(PaymentMethod.CASH, 1000.00)],
            session=session, created_at=opened,
        )
        sale.series, sale.folio = "A", 21444
        db.flush()
        return session, sale

    def test_cada_devolucion_trae_hora_folio_monto_metodo_y_marca_de_efectivo(
        self, db, cajero_a, branch_a
    ):
        from app.models.sales import PaymentMethod
        from app.routers.cash import get_session_audit_data

        session, sale = self._escenario(db, cajero_a, branch_a)
        ret = _devolucion(
            db, sale, branch_a, cajero_a, session,
            amount="220.00", method=PaymentMethod.CASH,
            created_at=datetime(2026, 8, 5, 21, 30, tzinfo=timezone.utc),
            status="APPROVED",
        )
        # Insertada ya APPROVED, sin pasar por `approve_return`: no hay
        # evento en el audit log, así que la hora sale del fallback
        # (`updated_at`). Se fija a mano para no depender del reloj de la
        # corrida. La cadena completa de fuentes se prueba en
        # tests/test_cash_cut_historia.py.
        ret.updated_at = datetime(2026, 8, 6, 0, 2, tzinfo=timezone.utc)  # 18:02 MX
        db.flush()

        audit = get_session_audit_data(db, session.id)
        item = audit["returns"]["list"][0]
        assert item["folio"] == "A-21444"
        assert item["amount"] == 220.0
        assert item["is_cash"] is True
        assert item["method"] == "cash"
        assert item["time"] == "18:02"

    def test_by_method_agrupa_por_metodo_de_reembolso_sin_doble_conteo(
        self, db, cajero_a, branch_a
    ):
        """`by_method` reparte EXACTAMENTE el mismo dinero que `total`: es un
        desglose, no una segunda fuente. Si la suma de los métodos no da el
        total, alguna devolución se está contando dos veces (o ninguna)."""
        from app.models.sales import PaymentMethod
        from app.routers.cash import get_session_audit_data

        session, sale = self._escenario(db, cajero_a, branch_a)
        base = datetime(2026, 8, 5, 18, 0, tzinfo=timezone.utc)
        _devolucion(db, sale, branch_a, cajero_a, session, amount="220.00",
                    method=PaymentMethod.CASH, created_at=base, status="APPROVED")
        _devolucion(db, sale, branch_a, cajero_a, session, amount="100.00",
                    method=PaymentMethod.CARD, created_at=base, status="APPROVED")
        _devolucion(db, sale, branch_a, cajero_a, session, amount="50.00",
                    method=PaymentMethod.TRANSFER, created_at=base, status="APPROVED")

        audit = get_session_audit_data(db, session.id)
        by_method = audit["returns"]["by_method"]
        assert by_method["cash"] == 220.0
        assert by_method["card"] == 100.0
        assert by_method["transfer"] == 50.0
        assert by_method["other"] == 0.0
        assert audit["returns"]["count"] == 3
        assert round(sum(by_method.values()), 2) == audit["returns"]["total"] == 370.0

    def test_una_devolucion_pendiente_no_entra_en_el_corte(
        self, db, cajero_a, branch_a
    ):
        """Solo las APROBADAS mueven dinero — una solicitud pendiente que
        apareciera en el detalle inflaría el relato del corte."""
        from app.models.sales import PaymentMethod
        from app.routers.cash import get_session_audit_data

        session, sale = self._escenario(db, cajero_a, branch_a)
        _devolucion(db, sale, branch_a, cajero_a, session, amount="220.00",
                    method=PaymentMethod.CASH,
                    created_at=datetime(2026, 8, 5, 18, 0, tzinfo=timezone.utc),
                    status="PENDING")

        audit = get_session_audit_data(db, session.id)
        assert audit["returns"]["count"] == 0
        assert audit["returns"]["list"] == []
        assert audit["returns"]["by_method"]["cash"] == 0.0


# ── Cómo lo imprime el ticket ────────────────────────────────────────────────


class TestDetalleImpresoDeDevoluciones:
    def test_el_ticket_imprime_hora_folio_y_marca_de_cada_devolucion(self):
        p = PosPrinter("x", paper_width_mm=80)
        a = _audit(returns={
            "count": 2, "total": 320.0, "cash_refunds": 220.0,
            "list": [
                {"time": "18:02", "folio": "A-21444", "amount": 220.0,
                 "is_cash": True, "method": "cash"},
                {"time": "19:10", "folio": "A-21501", "amount": 100.0,
                 "is_cash": False, "method": "card"},
            ],
            "by_method": {"cash": 220.0, "card": 100.0, "transfer": 0.0, "other": 0.0},
        })
        t = _visible_text(p.build_cash_cut_bytes(a), p)

        linea_efec = next(l for l in t.split("\n") if "18:02" in l)
        linea_card = next(l for l in t.split("\n") if "19:10" in l)
        assert "A-21444" in linea_efec
        assert "EFEC." in linea_efec, "la devolución en efectivo debe ir marcada"
        assert linea_efec.rstrip().endswith("$-220.00")
        assert "A-21501" in linea_card
        assert "EFEC." not in linea_card, "una devolución en tarjeta no toca el cajón"
        assert linea_card.rstrip().endswith("$-100.00")

    def test_el_detalle_va_antes_de_los_totales(self):
        """El lector ve QUÉ se devolvió antes que CUÁNTO en total."""
        p = PosPrinter("x", paper_width_mm=80)
        a = _audit(returns={
            "count": 1, "total": 220.0, "cash_refunds": 220.0,
            "list": [{"time": "18:02", "folio": "A-21444", "amount": 220.0,
                      "is_cash": True, "method": "cash"}],
            "by_method": {"cash": 220.0, "card": 0.0, "transfer": 0.0, "other": 0.0},
        })
        t = _visible_text(p.build_cash_cut_bytes(a), p)
        assert t.index("18:02") < t.index("Devoluciones (1)")

    @pytest.mark.parametrize("width_mm", ALL_WIDTHS_MM)
    def test_el_importe_nunca_se_pierde_aunque_el_folio_no_quepa(self, width_mm):
        """Orden de sacrificio: la marca de efectivo y el importe sobreviven;
        el folio es lo único prescindible. Un folio a medias sería un folio
        DISTINTO igual de verosímil — se omite entero o no se omite."""
        p = PosPrinter("x", paper_width_mm=width_mm)
        a = _audit(returns={
            "count": 1, "total": 98765432.10, "cash_refunds": 98765432.10,
            "list": [{"time": "18:02", "folio": "SUCURSAL-PRINCIPAL-1234567890",
                      "amount": 98765432.10, "is_cash": True, "method": "cash"}],
            "by_method": {"cash": 98765432.10, "card": 0.0,
                          "transfer": 0.0, "other": 0.0},
        })
        linea = next(l for l in _visible_lines(p.build_cash_cut_bytes(a), p)
                     if "18:02" in l)
        assert linea.rstrip().endswith("$-98765432.10")
        assert "EFEC." in linea, "la marca de efectivo se sacrifica al final"
        assert len(linea) <= p.cols, f"{linea!r} mide {len(linea)} en {p.cols} cols"
        folio_tokens = [tok for tok in linea.split() if tok.startswith("SUCURSAL")]
        assert folio_tokens in ([], ["SUCURSAL-PRINCIPAL-1234567890"]), (
            f"el folio salió recortado a medias: {folio_tokens!r}"
        )
