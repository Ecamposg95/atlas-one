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


def _venta_con_iva(db, org, branch, user, variant, session):
    """Venta real con IVA y renglones: 2 x $500 pre-IVA + 16% = $1,160.00.

    `tests/test_cash_math.py::_create_sale` fuerza `tax_amount=0` y no crea
    renglones, así que no sirve para este caso: sin IVA y sin `SaleReturnItem`
    el prorrateo de `approve_return` no se ejercita."""
    from app.models.sales import (
        DocumentStatus, Payment, PaymentMethod, SalesDocument, SalesLineItem,
    )
    sale = SalesDocument(
        organization_id=org.id, branch_id=branch.id, seller_id=user.id,
        series="A", folio=7001,
        subtotal=Decimal("1000.00"), tax_amount=Decimal("160.00"),
        total_amount=Decimal("1160.00"),
        status=DocumentStatus.PAID, cash_session_id=session.id,
        # `create_sale` persiste `change_given` en toda venta nueva. Fijarlo
        # aquí no es cosmético: con NULL, el fallback legado de
        # `_compute_change_given` recalcula el cambio contra
        # `sale.total_amount`, que `approve_return` YA neteó — inventaría un
        # cambio de $580 y el efectivo cobrado saldría 580 en vez de 1160
        # (ver "Hallazgo" en w8-report.md).
        change_given=Decimal("0.00"),
        created_at=session.opened_at,
    )
    db.add(sale)
    db.flush()
    db.add(SalesLineItem(
        document_id=sale.id, variant_id=variant.id, description="Producto",
        quantity=Decimal("2"), unit_price=Decimal("500.00"),
        total_line=Decimal("1000.00"), organization_id=org.id,
    ))
    db.add(Payment(
        sales_document_id=sale.id, method=PaymentMethod.CASH,
        amount=Decimal("1160.00"), organization_id=org.id,
        created_at=session.opened_at,
    ))
    db.flush()
    return sale


def test_el_corte_no_afirma_que_cobrado_menos_devoluciones_sea_ventas_totales(
    db, org, branch_a, cajero_a, gerente_a, products_setup
):
    """Esa identidad es FALSA con IVA y el corte no debe imprimirla.

    `SaleReturn.total_refunded` es PRE-IVA; `approve_return` baja
    `sale.total_amount` por el pre-IVA MÁS el IVA prorrateado. Con una venta
    de $1,160.00 (1,000 + 16%) y una devolución de $500.00 pre-IVA:

        Total cobrado 1160 - Devoluciones 500 = 660
        Ventas Totales (neto real)            = 580     <- 80 de IVA de diferencia

    El corte imprime las tres cifras, pero NO afirma que las dos primeras den
    la tercera. La resta que sí es cierta por construcción se rotula "Neto
    cobrado"."""
    from app.crud.returns import approve_return, create_return
    from app.models.sales import PaymentMethod
    from app.routers.cash import get_session_audit_data
    from app.schemas.returns import SaleReturnCreate
    from tests.test_cash_math import _open_session

    _, variant = products_setup["product_a"]
    opened = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)
    session = _open_session(db, cajero_a, branch_a, opening=0, opened_at=opened)
    sale = _venta_con_iva(db, org, branch_a, cajero_a, variant, session)

    ret = create_return(
        db,
        SaleReturnCreate(
            sale_id=sale.id, reason="Defectuoso",
            total_refunded=Decimal("500.00"),
            refund_method=PaymentMethod.CASH,
            cash_session_id=session.id,
            items=[{"variant_id": variant.id, "quantity": Decimal("1"),
                    "refund_amount": Decimal("500.00")}],
        ),
        user_id=cajero_a.id, branch_id=branch_a.id, organization_id=org.id,
    )
    approve_return(db, ret.id, supervisor_id=gerente_a.id, organization_id=org.id)

    db.refresh(sale)
    assert float(sale.total_amount) == 580.0, (
        "el prorrateo de IVA de approve_return cambió; el escenario ya no "
        f"prueba lo que dice (total_amount={sale.total_amount})"
    )

    audit = get_session_audit_data(db, session.id)
    p = PosPrinter("x", paper_width_mm=80)
    t = _visible_text(p.build_cash_cut_bytes(audit), p)

    cobrado = _amount_of(t, "Total cobrado")
    devoluciones = _amount_of(t, "Devoluciones (1)")
    ventas = _amount_of(t, "Ventas Totales")
    neto = _amount_of(t, "Neto cobrado")

    assert cobrado == 1160.0, cobrado
    assert devoluciones == -500.0, devoluciones
    assert ventas == 580.0, ventas
    # La identidad es falsa: 1160 - 500 = 660 != 580.
    assert round(cobrado + devoluciones, 2) != ventas
    # ...y el corte no la afirma en ninguna parte.
    assert "(cobrado - devoluciones)" not in t
    # La resta que sí es cierta, rotulada como lo que es.
    assert neto == round(cobrado + devoluciones, 2) == 660.0, neto


def test_neto_cobrado_es_exactamente_cobrado_menos_devoluciones():
    """Cierta por construcción: ambos sumandos salen del mismo ticket."""
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
    )
    t = _visible_text(p.build_cash_cut_bytes(a), p)
    assert _amount_of(t, "Total cobrado") == 45710.0
    assert _amount_of(t, "Devoluciones (1)") == -220.0
    assert _amount_of(t, "Neto cobrado") == 45490.0


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


# ── Correcciones de revisión (ronda 1) ───────────────────────────────────────


def test_el_detalle_sale_en_orden_cronologico_estable(db, cajero_a, branch_a):
    """La PK de `sale_returns` es un UUID aleatorio y Postgres devuelve las
    filas en el orden físico del heap, que cambia con cada UPDATE: sin orden
    explícito, dos reimpresiones del MISMO corte listan las devoluciones en
    orden distinto y el detalle deja de ser auditable. Aquí se insertan al
    revés (la de las 19:10 primero) y el corte debe ordenarlas igual."""
    from app.models.sales import PaymentMethod
    from app.routers.cash import get_session_audit_data
    from tests.test_cash_cut_detalle import _devolucion
    from tests.test_cash_math import _open_session, _create_sale

    opened = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)
    session = _open_session(db, cajero_a, branch_a, opening=0, opened_at=opened)
    sale = _create_sale(
        db, cajero_a, branch_a, total=1000.00,
        payments=[(PaymentMethod.CASH, 1000.00)],
        session=session, created_at=opened,
    )

    tarde = _devolucion(db, sale, branch_a, cajero_a, session, amount="100.00",
                        method=PaymentMethod.CARD, created_at=opened, status="APPROVED")
    tarde.updated_at = datetime(2026, 8, 6, 1, 10, tzinfo=timezone.utc)  # 19:10 MX
    temprano = _devolucion(db, sale, branch_a, cajero_a, session, amount="220.00",
                           method=PaymentMethod.CASH, created_at=opened, status="APPROVED")
    temprano.updated_at = datetime(2026, 8, 6, 0, 2, tzinfo=timezone.utc)  # 18:02 MX
    db.flush()

    horas = [i["time"] for i in get_session_audit_data(db, session.id)["returns"]["list"]]
    assert horas == ["18:02", "19:10"], horas


def test_una_devolucion_aprobada_otro_dia_va_marcada(db, cajero_a, branch_a):
    """Ruta `[POST-CLOSE]` de `approve_return`: se aprueba hoy una devolución
    cuya caja cerró ayer. Una hora suelta se leería como de esta jornada."""
    from app.models.sales import PaymentMethod
    from app.routers.cash import get_session_audit_data
    from tests.test_cash_cut_detalle import _devolucion
    from tests.test_cash_math import _open_session, _create_sale

    opened = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)  # 05/08 06:00 MX
    session = _open_session(db, cajero_a, branch_a, opening=0, opened_at=opened)
    sale = _create_sale(
        db, cajero_a, branch_a, total=1000.00,
        payments=[(PaymentMethod.CASH, 1000.00)],
        session=session, created_at=opened,
    )
    ret = _devolucion(db, sale, branch_a, cajero_a, session, amount="220.00",
                      method=PaymentMethod.CASH, created_at=opened, status="APPROVED")
    ret.updated_at = datetime(2026, 8, 8, 18, 30, tzinfo=timezone.utc)  # 08/08 12:30 MX
    db.flush()

    audit = get_session_audit_data(db, session.id)
    item = audit["returns"]["list"][0]
    assert item["cross_day"] is True
    assert item["date"] == "08/08"

    p = PosPrinter("x", paper_width_mm=80)
    linea = next(l for l in _visible_lines(p.build_cash_cut_bytes(audit), p)
                 if "12:30" in l)
    assert "08/08" in linea, f"la fecha debe ir en el renglón: {linea!r}"


def test_una_devolucion_del_mismo_dia_no_lleva_fecha(db, cajero_a, branch_a):
    from app.models.sales import PaymentMethod
    from app.routers.cash import get_session_audit_data
    from tests.test_cash_cut_detalle import _devolucion
    from tests.test_cash_math import _open_session, _create_sale

    opened = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)
    session = _open_session(db, cajero_a, branch_a, opening=0, opened_at=opened)
    sale = _create_sale(
        db, cajero_a, branch_a, total=1000.00,
        payments=[(PaymentMethod.CASH, 1000.00)],
        session=session, created_at=opened,
    )
    ret = _devolucion(db, sale, branch_a, cajero_a, session, amount="220.00",
                      method=PaymentMethod.CASH, created_at=opened, status="APPROVED")
    ret.updated_at = datetime(2026, 8, 6, 0, 2, tzinfo=timezone.utc)  # 05/08 18:02 MX
    db.flush()

    audit = get_session_audit_data(db, session.id)
    assert audit["returns"]["list"][0]["cross_day"] is False
    p = PosPrinter("x", paper_width_mm=80)
    linea = next(l for l in _visible_lines(p.build_cash_cut_bytes(audit), p)
                 if "18:02" in l)
    assert "05/08" not in linea and "18:02+" not in linea, linea


def test_la_marca_de_otro_dia_sobrevive_al_papel_angosto():
    """A 58mm con un importe largo, el folio se sacrifica pero la fecha (o al
    menos el "+") se queda: es lo que impide leer la hora como de hoy."""
    p = PosPrinter("x", paper_width_mm=58)
    a = _audit(returns={
        "count": 1, "total": 98765432.10, "cash_refunds": 98765432.10,
        "list": [{"time": "12:30", "date": "08/08", "cross_day": True,
                  "folio": "A-1234567890", "amount": 98765432.10,
                  "is_cash": True, "method": "cash"}],
        "by_method": {"cash": 98765432.10, "card": 0.0, "transfer": 0.0, "other": 0.0},
    })
    linea = next(l for l in _visible_lines(p.build_cash_cut_bytes(a), p) if "12:30" in l)
    assert len(linea) <= p.cols, f"{linea!r} mide {len(linea)}"
    assert "08/08" in linea or "12:30+" in linea, linea
    assert "A-1234567890" not in linea, "el folio es lo primero que se sacrifica"


def test_las_etiquetas_del_arqueo_salen_completas_a_32_columnas():
    """La guarda de ancho de `_rline` recorta en silencio; las etiquetas del
    arqueo están dimensionadas para no necesitarla nunca — a 58mm (32
    columnas) con importes de 8 cifras siguen enteras."""
    p = PosPrinter("x", paper_width_mm=58)
    grande = 98765432.10
    a = _audit(
        session={**_audit()["session"], "opening_balance": grande},
        payments={
            "cash": {"total": grande, "count": 9},
            "card": {"total": 0.0, "count": 0},
            "transfer": {"total": 0.0, "count": 0},
            "store_credit": {"total": 0.0, "count": 0},
            "check": {"total": 0.0, "count": 0},
            "others": {"total": 0.0, "count": 0},
        },
        movements={"inflows": grande, "outflows": grande, "list": []},
        returns={
            "count": 1, "total": grande, "cash_refunds": grande,
            "list": [{"time": "10:00", "folio": "A-1", "amount": grande,
                      "is_cash": True, "method": "cash"}],
            "by_method": {"cash": grande, "card": 0.0, "transfer": 0.0, "other": 0.0},
        },
        expected={"cash_physical": grande, "total_system": grande},
        reconciliation={"reported": 0.0, "difference": -grande, "diff_percent": -100.0},
    )
    t = _visible_text(p.build_cash_cut_bytes(a), p)
    for etiqueta in ("Fondo Inicial (+)", "Efec. cobrado (+)", "Entradas man. (+)",
                     "Salidas/Gastos (-)", "Reembolsos (-)", "ESPERADO CAJA",
                     "REPORTADO", "FALTANTE (-)"):
        assert f"{etiqueta}: $" in t, (
            f"la etiqueta {etiqueta!r} salió recortada a {p.cols} columnas"
        )


def test_el_residuo_sin_clasificar_cuadra_la_columna():
    """`en efectivo` sale de `cash_refunds` (CashMovement) y el resto de
    `by_method` (SaleReturn). En datos previos a la reasignación de sesión de
    `approve_return` pueden vivir en cortes distintos y los subtotales no
    suman el total: el residuo lo deja visible en vez de esconderlo."""
    p = PosPrinter("x", paper_width_mm=80)
    a = _audit(returns={
        "count": 2, "total": 320.0,
        "cash_refunds": 100.0,  # sólo 100 de los 220 en efectivo llegó a esta caja
        "list": [
            {"time": "10:00", "folio": "A-1", "amount": 220.0, "is_cash": True, "method": "cash"},
            {"time": "11:00", "folio": "A-2", "amount": 100.0, "is_cash": False, "method": "card"},
        ],
        "by_method": {"cash": 220.0, "card": 100.0, "transfer": 0.0, "other": 0.0},
    })
    t = _visible_text(p.build_cash_cut_bytes(a), p)
    subtotales = [
        _amount_of(t, "en efectivo"),
        _amount_of(t, "en tarjeta"),
        _amount_of(t, "sin clasificar"),
    ]
    assert subtotales == [-100.0, -100.0, -120.0], subtotales
    assert round(sum(subtotales), 2) == _amount_of(t, "Devoluciones (2)") == -320.0


def test_sin_residuo_no_aparece_el_renglon_sin_clasificar():
    p = PosPrinter("x", paper_width_mm=80)
    a = _audit(returns={
        "count": 2, "total": 320.0, "cash_refunds": 220.0,
        "list": [
            {"time": "10:00", "folio": "A-1", "amount": 220.0, "is_cash": True, "method": "cash"},
            {"time": "11:00", "folio": "A-2", "amount": 100.0, "is_cash": False, "method": "card"},
        ],
        "by_method": {"cash": 220.0, "card": 100.0, "transfer": 0.0, "other": 0.0},
    })
    assert "sin clasificar" not in _visible_text(p.build_cash_cut_bytes(a), p)


def test_una_devolucion_sin_metodo_se_marca_y_se_clasifica_igual(
    db, cajero_a, branch_a
):
    """`is_cash` y `by_method` salen del MISMO `_method_key`: una fila legada
    con `refund_method` NULL no puede caer en el bucket "cash" y a la vez
    imprimirse sin la marca de efectivo."""
    from app.routers.cash import get_session_audit_data
    from tests.test_cash_cut_detalle import _devolucion
    from tests.test_cash_math import _open_session, _create_sale
    from app.models.sales import PaymentMethod

    opened = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)
    session = _open_session(db, cajero_a, branch_a, opening=0, opened_at=opened)
    sale = _create_sale(
        db, cajero_a, branch_a, total=1000.00,
        payments=[(PaymentMethod.CASH, 1000.00)],
        session=session, created_at=opened,
    )
    ret = _devolucion(db, sale, branch_a, cajero_a, session, amount="220.00",
                      method=None, created_at=opened, status="APPROVED")
    ret.refund_method = None
    db.flush()

    item = get_session_audit_data(db, session.id)["returns"]["list"][0]
    assert item["method"] == "cash"
    assert item["is_cash"] is True, (
        "clasificada como efectivo en by_method pero impresa sin marca"
    )
