# tests/test_cash_cut_historia.py
"""Corte con historia: el corte impreso mezclaba dos convenciones.

"Ventas Totales" ya viene NETO de devoluciones aprobadas (`approve_return`
reescribe `sale.total_amount`) mientras "POR METODO DE PAGO" es BRUTO (los
`Payment` no se tocan). Una cajera que resta "Ventas Totales - Tarjeta -
Devoluciones" resta la devolución DOS VECES.

La fórmula NO cambia (`compute_expected_cash` sigue siendo la única fuente,
ver `tests/test_cash_math.py`): solo se reordena el ticket en una sola
historia causal --

    COBRADO POR METODO -> DEVOLUCIONES -> VENTAS NETAS -> ARQUEO DE CAJA

-- y se hacen explícitos dos datos que antes había que inferir: el "Total
cobrado" (bruto, suma de métodos) y el desglose de las devoluciones por
método de reembolso.

Los helpers de medición viven en `tests/test_cash_cut_detalle.py`."""
import re
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.pos_printer import PosPrinter
from tests.test_cash_cut_detalle import (
    ALL_WIDTHS_MM,
    _audit,
    _visible_lines,
    _visible_text,
)


def _amount_of(t: str, label_prefix: str) -> float:
    """Encuentra el primer renglón cuya etiqueta arranca con `label_prefix` y
    devuelve el importe anclado al borde derecho como float con signo."""
    line = next(l for l in t.split("\n") if l.lstrip().startswith(label_prefix))
    m = re.search(r"\$-?\d+\.\d{2}\s*$", line)
    assert m, f"no se encontró importe en la línea {line!r}"
    return float(m.group(0).replace("$", "").strip())


def test_el_orden_de_secciones_cuenta_la_historia():
    """La historia se lee en orden: cuánto entró, qué se devolvió, cuánto
    quedó neto, y cómo se concilia contra el cajón."""
    p = PosPrinter("x", paper_width_mm=80)
    a = _audit(
        returns={
            "count": 1, "total": 220.0, "cash_refunds": 220.0,
            "list": [{"time": "18:02", "folio": "A-21444", "amount": 220.0,
                      "is_cash": True, "method": "cash"}],
            "by_method": {"cash": 220.0, "card": 0.0, "transfer": 0.0, "other": 0.0},
        },
        movements={
            "inflows": 0.0, "outflows": 0.0,
            "list": [{"time": "10:00", "type": "IN", "amount": 100.0, "reason": "FONDO"}],
        },
    )
    t = _visible_text(p.build_cash_cut_bytes(a), p)

    idx_cobrado = t.index("COBRADO POR METODO")
    idx_devoluciones = t.index("DEVOLUCIONES")
    idx_ventas = t.index("VENTAS NETAS")
    idx_arqueo = t.index("ARQUEO DE CAJA")

    assert idx_cobrado < idx_devoluciones < idx_ventas < idx_arqueo, (
        f"orden real: cobrado={idx_cobrado} devoluciones={idx_devoluciones} "
        f"ventas={idx_ventas} arqueo={idx_arqueo}"
    )


def test_total_cobrado_menos_devoluciones_es_ventas_totales():
    """Caso real (sesión 1582 de Rmazh): Efectivo 39,640 (284) + Tarjeta
    6,070 (15) = Total cobrado 45,710; una devolución de 220; Ventas
    Totales (neto, así viene de `kpis['total_sales']`) 45,490.
    `cobrado - devoluciones == ventas`: la resta ya NO se hace dos veces."""
    p = PosPrinter("x", paper_width_mm=80)
    a = _audit(
        payments={
            "cash": {"total": 39640.0, "count": 284},
            "card": {"total": 6070.0, "count": 15},
            "transfer": {"total": 0.0, "count": 0},
            "store_credit": {"total": 0.0, "count": 0},
            "check": {"total": 0.0, "count": 0},
            "others": {"total": 0.0, "count": 0},
        },
        returns={
            "count": 1, "total": 220.0, "cash_refunds": 220.0,
            "list": [{"time": "18:02", "folio": "A-21444", "amount": 220.0,
                      "is_cash": True, "method": "cash"}],
            "by_method": {"cash": 220.0, "card": 0.0, "transfer": 0.0, "other": 0.0},
        },
        kpis={
            "total_sales": 45490.0, "total_tickets": 299,
            "avg_ticket": 45490.0 / 299, "total_taxes": 0.0, "subtotal": 45490.0,
        },
    )
    t = _visible_text(p.build_cash_cut_bytes(a), p)

    cobrado = _amount_of(t, "Total cobrado")
    devoluciones = _amount_of(t, "Devoluciones (1)")
    ventas = _amount_of(t, "Ventas Totales")

    assert cobrado == 45710.0, f"Total cobrado debería ser 45710.0, salió {cobrado}"
    assert devoluciones == -220.0, f"Devoluciones debería ser -220.0, salió {devoluciones}"
    assert ventas == 45490.0, f"Ventas Totales debería ser 45490.0, salió {ventas}"
    assert round(cobrado + devoluciones, 2) == ventas, (
        f"cobrado ({cobrado}) - devoluciones ({-devoluciones}) debería dar "
        f"ventas ({ventas})"
    )
    assert "(cobrado - devoluciones)" in t, (
        "la resta tiene que quedar escrita en el corte, no inferirse"
    )


def test_el_total_cobrado_no_cuenta_dos_veces_ningun_metodo():
    """El "Total cobrado" es la suma de los métodos que lo preceden, ni uno
    más ni uno menos — es el número contra el que se resta la devolución."""
    p = PosPrinter("x", paper_width_mm=80)
    a = _audit(payments={
        "cash": {"total": 100.0, "count": 1},
        "card": {"total": 200.0, "count": 1},
        "transfer": {"total": 300.0, "count": 1},
        "store_credit": {"total": 400.0, "count": 1},
        "check": {"total": 500.0, "count": 1},
        "others": {"total": 600.0, "count": 1},
    })
    t = _visible_text(p.build_cash_cut_bytes(a), p)
    assert _amount_of(t, "Total cobrado") == 2100.0


def _venta_y_devolucion_aprobada(db, cajero_a, gerente_a, branch_a):
    """Sesión + venta en efectivo + una devolución de $220.00 CREADA a las
    15:30 MX (21:30 UTC) y APROBADA de verdad vía `approve_return` (no un
    fixture que la inserte ya en APPROVED — necesitamos que el audit log
    real se escriba). Devuelve `(session, ret)`."""
    from app.models.sales import PaymentMethod
    from app.crud.returns import approve_return
    from tests.test_cash_cut_detalle import _devolucion
    from tests.test_cash_math import _open_session, _create_sale

    opened = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)  # 06:00 MX
    session = _open_session(db, cajero_a, branch_a, opening=0, opened_at=opened)
    sale = _create_sale(
        db, cajero_a, branch_a, total=1000.00,
        payments=[(PaymentMethod.CASH, 1000.00)],
        session=session, created_at=opened,
    )
    ret = _devolucion(
        db, sale, branch_a, cajero_a, session,
        amount="220.00", method=PaymentMethod.CASH,
        created_at=datetime(2026, 8, 5, 21, 30, tzinfo=timezone.utc),
    )
    approve_return(db, ret.id, supervisor_id=gerente_a.id,
                   organization_id=branch_a.organization_id)
    return session, ret


def test_la_devolucion_imprime_la_hora_del_audit_log_no_la_de_updated_at(
    db, cajero_a, gerente_a, branch_a
):
    """La hora impresa viene del `cash_audit_log` (append-only, nunca se hace
    UPDATE sobre él) — NO de `SaleReturn.updated_at`, que puede driftear:
    `app/routers/platform/users.py` hace
    `db.query(SaleReturn).filter(SaleReturn.supervisor_id == user_id)
    .update({"supervisor_id": None}, ...)` al borrar un usuario, SIN filtro
    de status, y el `onupdate` del `AuditMixin` pisa `updated_at` de
    devoluciones APROBADAS HISTÓRICAS con la hora del borrado. Este test
    fija la hora REAL de aprobación en el audit log (18:02 MX) y después
    CONTAMINA `updated_at` con una hora bien distinta."""
    from app.models.cash_audit import CashAuditLog, CashAuditEvent
    from app.routers.cash import get_session_audit_data

    session, ret = _venta_y_devolucion_aprobada(db, cajero_a, gerente_a, branch_a)

    # `approve_return` escribe `ts` con el reloj real de esta corrida; hay
    # que fijarla para que el test sea determinista.
    audit_row = db.query(CashAuditLog).filter(
        CashAuditLog.event_type == CashAuditEvent.REFUND_APPROVED,
        CashAuditLog.related_table == "sale_returns",
        CashAuditLog.related_id == ret.id,
    ).one()
    audit_row.ts = datetime(2026, 8, 6, 0, 2, tzinfo=timezone.utc)  # 18:02 MX

    # Contamina `updated_at` con una hora MUY distinta — el escenario exacto
    # del hallazgo (un borrado de usuario meses después).
    ret.updated_at = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)
    db.flush()

    audit = get_session_audit_data(db, session.id)
    item = audit["returns"]["list"][0]
    assert item["time"] == "18:02", (
        f"debió usar la hora del audit log (18:02), no la de updated_at "
        f"contaminado ('2026-09-01 10:00'): salió {item['time']!r}"
    )
    assert item["method"] == "cash"


def test_sin_evento_en_el_audit_log_cae_a_updated_at(
    db, cajero_a, gerente_a, branch_a
):
    """`audit_cash_event` es failsafe (nunca revierte la aprobación si falla
    al escribir) — si el evento REFUND_APPROVED no está, el corte tiene que
    seguir mostrando algo razonable: cae a `updated_at` (la aprobación real
    siempre lo toca) antes que a `created_at` (la hora de la SOLICITUD)."""
    from app.models.cash_audit import CashAuditLog, CashAuditEvent
    from app.routers.cash import get_session_audit_data

    session, ret = _venta_y_devolucion_aprobada(db, cajero_a, gerente_a, branch_a)

    db.query(CashAuditLog).filter(
        CashAuditLog.event_type == CashAuditEvent.REFUND_APPROVED,
        CashAuditLog.related_table == "sale_returns",
        CashAuditLog.related_id == ret.id,
    ).delete(synchronize_session=False)

    ret.updated_at = datetime(2026, 8, 6, 0, 2, tzinfo=timezone.utc)  # 18:02 MX
    db.flush()

    audit = get_session_audit_data(db, session.id)
    item = audit["returns"]["list"][0]
    assert item["time"] == "18:02", (
        f"sin evento en el audit log debió caer a updated_at, salió {item['time']!r}"
    )


def test_subtotales_por_metodo_de_reembolso():
    """Una devolución en efectivo y otra en tarjeta: cada una imprime su
    propio subtotal ("en efectivo"/"en tarjeta"); un método sin devoluciones
    no imprime renglón."""
    p = PosPrinter("x", paper_width_mm=80)
    a = _audit(returns={
        "count": 2, "total": 320.0, "cash_refunds": 220.0,
        "list": [
            {"time": "10:00", "folio": "A-1", "amount": 220.0, "is_cash": True, "method": "cash"},
            {"time": "11:00", "folio": "A-2", "amount": 100.0, "is_cash": False, "method": "card"},
        ],
        "by_method": {"cash": 220.0, "card": 100.0, "transfer": 0.0, "other": 0.0},
    })
    t = _visible_text(p.build_cash_cut_bytes(a), p)

    linea_efectivo = next(l for l in t.split("\n") if "en efectivo" in l)
    linea_tarjeta = next(l for l in t.split("\n") if "en tarjeta" in l)
    assert linea_efectivo.rstrip().endswith("$-220.00"), linea_efectivo
    assert linea_tarjeta.rstrip().endswith("$-100.00"), linea_tarjeta
    assert "en transferencia" not in t
    assert "en otros" not in t


def test_sin_devoluciones_no_hay_bloque_ni_subtotales():
    p = PosPrinter("x", paper_width_mm=80)
    t = _visible_text(p.build_cash_cut_bytes(_audit()), p)
    assert "DEVOLUCIONES" not in t
    assert "en efectivo" not in t
    assert "en tarjeta" not in t


@pytest.mark.parametrize("width_mm", ALL_WIDTHS_MM)
def test_ninguna_linea_del_corte_excede_el_ancho(width_mm):
    """Importes de 8-9 cifras + devoluciones con desglose por método: el
    bloque nuevo ("Total cobrado", detalle reordenado, subtotales) respeta
    el mismo invariante de ancho que el resto del corte.

    `movements['list']` va vacía a propósito: el renglón de movimientos ya
    desbordaba a 32 columnas ANTES de este cambio (`reason[:28]` sobre una
    columna de 18) — es un defecto preexistente, no una regresión de esta
    rama, y arreglarlo es un cambio aparte."""
    p = PosPrinter("x", paper_width_mm=width_mm)
    a = _audit(
        kpis={
            "total_sales": 98765432.10, "total_tickets": 999,
            "avg_ticket": 98864.30, "total_taxes": 15802469.14,
            "subtotal": 82962962.96,
        },
        movements={"inflows": 1234567.89, "outflows": 987654.32, "list": []},
        returns={
            "count": 2, "total": 987654.32, "cash_refunds": 887654.32,
            "list": [
                {"time": "10:00", "folio": "A-1234567890", "amount": 887654.32,
                 "is_cash": True, "method": "cash"},
                {"time": "11:00", "folio": "B-9876543210", "amount": 100000.00,
                 "is_cash": False, "method": "card"},
            ],
            "by_method": {"cash": 887654.32, "card": 100000.00,
                          "transfer": 0.0, "other": 0.0},
        },
        expected={"cash_physical": 98765432.10, "total_system": 98765432.10},
        reconciliation={"reported": 98765432.10, "difference": -12345678.90,
                        "diff_percent": -12.5},
    )
    for l in _visible_lines(p.build_cash_cut_bytes(a), p):
        assert len(l) <= p.cols, f"{width_mm}mm ({p.cols} cols): {l!r} mide {len(l)}"
