"""Regresiones de la auditoría funcional del backend (2026-09-22) — impresión.

* M-1 el `except` del rasterizado del logo referenciaba `final_path`, que solo
  existe en la rama de disco: un fallo con un logo remoto (Cloudinary/CDN, el
  caso de producción) lanzaba NameError → 500 en vez de imprimir sin logo.
* M-14 el corte de caja codificaba sucursal/cajero con `.encode("latin-1")` sin
  `errors="replace"`: un emoji en el nombre reventaba la impresión del corte.
"""
import io
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from PIL import Image

from app.pos_printer import PosPrinter


# ---------------------------------------------------------------- M-1
def _fake_http_response(png_bytes: bytes):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.headers = {"Content-Type": "image/png", "Content-Length": str(len(png_bytes))}
    resp.iter_content.return_value = [png_bytes]
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    return resp


def test_m1_logo_remoto_que_falla_degrada_a_ticket_sin_logo():
    img = Image.new("RGB", (10, 10), (255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    printer = PosPrinter(printer_name="POS-80", paper_width_mm=80)
    fake_resp = _fake_http_response(buf.getvalue())

    with patch("requests.get", return_value=fake_resp), \
         patch("PIL.Image.Image.resize", side_effect=RuntimeError("boom-resize")):
        salida = printer._generate_image_bytes("https://cdn.example.com/logo.png")

    assert salida == b""


# ---------------------------------------------------------------- M-14
def _audit_data(branch_name: str, user_name: str = "cajera1"):
    now = datetime.now(timezone.utc)
    return {
        "session": {
            "organization_name": "Boutique Demo",
            "id": 1,
            "branch_name": branch_name,
            "user_name": user_name,
            "opened_at": now,
            "closed_at": now,
            "opening_balance": 500.0,
        },
        "payments": {
            "cash": {"total": 1000.0, "count": 3},
            "card": {"total": 0.0, "count": 0},
            "transfer": {"total": 0.0, "count": 0},
            "store_credit": {"total": 0.0, "count": 0},
            "check": {"total": 0.0, "count": 0},
            "others": {"total": 0.0, "count": 0},
        },
        "movements": {"inflows": 0.0, "outflows": 0.0, "list": []},
        "kpis": {
            "total_sales": 1000.0,
            "total_tickets": 3,
            "avg_ticket": 333.33,
            "total_taxes": 0.0,
        },
        "reconciliation": {"reported": 1500.0, "difference": 0.0},
        "expected": {"cash_physical": 1500.0},
        "returns": {},
        "card_surcharges": 0,
    }


def test_m14_corte_con_nombre_ascii_sigue_igual():
    printer = PosPrinter(printer_name="POS-80", paper_width_mm=80)
    raw = printer.build_cash_cut_bytes(_audit_data("Sucursal Centro"))
    assert b"SUCURSAL CENTRO" in raw.upper()


def test_m14_corte_con_emoji_en_sucursal_o_cajero_se_imprime_igual():
    printer = PosPrinter(printer_name="POS-80", paper_width_mm=80)
    raw = printer.build_cash_cut_bytes(_audit_data("Sucursal Centro 🛍️", "cajera 🌟"))
    assert isinstance(raw, bytes) and raw
    assert b"SUCURSAL CENTRO" in raw.upper()
