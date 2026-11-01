"""El ticket del corte imprime "Fiado" y "Abonos a cuenta" solo cuando son > 0
(spec 2026-10-29 §2.3). Así ventas = cobrado + fiado y la cajera cuadra."""
from datetime import datetime
from zoneinfo import ZoneInfo

from app.pos_printer import PosPrinter

MX = ZoneInfo("America/Mexico_City")


def _texto(raw: bytes, p: PosPrinter) -> str:
    out = raw
    for k, c in sorted(p.CMD.items(), key=lambda kv: len(kv[1]), reverse=True):
        if k != "LF" and c:
            out = out.replace(c, b"")
    return out.decode("latin-1", "replace")


def _audit(credit_sales=0.0, customer_payments=0.0):
    return {
        "session": {"id": 1, "opened_at": datetime(2026, 10, 30, 9, 0, tzinfo=MX), "closed_at": None,
                    "opening_balance": 0.0, "closing_balance": 0.0, "last_activity": None,
                    "user_name": "MIRNA", "branch_name": "ROMA", "organization_name": "ELEVEN"},
        "payments": {k: {"total": 0.0, "count": 0} for k in ("cash", "card", "transfer", "store_credit", "check", "others")}
        | {"cash": {"total": 70.0, "count": 2}},
        "movements": {"inflows": 0.0, "outflows": 0.0, "list": []},
        "returns": {"count": 0, "total": 0.0, "cash_refunds": 0.0, "list": [], "by_method": {}},
        "kpis": {"total_sales": 100.0, "total_tickets": 1, "avg_ticket": 100.0, "total_taxes": 0.0,
                 "subtotal": 100.0, "credit_sales": credit_sales, "customer_payments": customer_payments},
        "expected": {"cash_physical": 70.0, "total_system": 40.0},
        "reconciliation": {"reported": 0.0, "difference": 0.0, "diff_percent": 0.0},
    }


def test_imprime_fiado_y_abonos_cuando_los_hay():
    p = PosPrinter("x", paper_width_mm=80)
    lineas = _texto(p.build_cash_cut_bytes(_audit(credit_sales=60.0, customer_payments=30.0)), p).split("\n")
    fiado = next(l for l in lineas if l.strip().startswith("Fiado"))
    abonos = next(l for l in lineas if "Abonos a cuenta" in l)
    assert fiado.rstrip().endswith("$60.00")
    assert abonos.rstrip().endswith("$30.00")
    assert lineas.index(fiado) > lineas.index(next(l for l in lineas if "Ventas Totales" in l))
    assert lineas.index(abonos) < lineas.index(next(l for l in lineas if "Total cobrado" in l))


def test_sin_fiado_ni_abonos_el_ticket_es_el_de_siempre():
    p = PosPrinter("x", paper_width_mm=58)
    t = _texto(p.build_cash_cut_bytes(_audit()), p)
    assert "Fiado" not in t and "Abonos a cuenta" not in t


def test_un_corte_viejo_sin_las_claves_no_truena():
    p = PosPrinter("x", paper_width_mm=80)
    a = _audit()
    del a["kpis"]["credit_sales"]; del a["kpis"]["customer_payments"]
    assert b"CORTE DE CAJA" in p.build_cash_cut_bytes(a)
