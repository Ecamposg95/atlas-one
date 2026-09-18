"""
Tests: Ticket layout regression (compact OXXO-style — 2026-04-29).

Verifies the post-redesign defaults in app/pos_printer.py:
  1. Unit price always rendered inline (consistent OXXO column alignment).
  2. SUBTOTAL / IVA / TOTAL block is 3 lines, no item count.
  3. TOTAL line is wrapped in BOLD_ON / BOLD_OFF.
  4. Pre-cut margin is exactly LF*3 (no dedicated branding line).
  5. Default width 80mm = 56 cols with FONT_B.

Uses SimpleNamespace mocks so the tests don't need a DB — build_ticket_bytes
reads attributes off the sale/lines/branch/organization duck-style.
"""
from decimal import Decimal
from datetime import datetime, timezone
from types import SimpleNamespace

from app.pos_printer import PosPrinter


def _line(description, quantity, unit_price):
    qty = Decimal(str(quantity))
    unit = Decimal(str(unit_price))
    return SimpleNamespace(
        description=description,
        quantity=qty,
        unit_price=unit,
        total_line=qty * unit,
    )


def _make_sale(lines, *, subtotal=None, tax=0, series="A", folio=123):
    if subtotal is None:
        subtotal = sum((l.total_line for l in lines), Decimal("0"))
    tax_dec = Decimal(str(tax))
    return SimpleNamespace(
        lines=lines,
        series=series,
        folio=folio,
        subtotal=subtotal,
        tax_amount=tax_dec,
        total_amount=subtotal + tax_dec,
        customer_name="Cliente Test",
        customer=None,
        created_at=datetime(2026, 4, 20, 12, 0, tzinfo=timezone.utc),
        notes=None,
        requires_invoice=False,
    )


def _build(sale, **kwargs):
    p = PosPrinter(paper_width_mm=80)
    defaults = dict(
        paid=Decimal("0"),
        change=Decimal("0"),
        method="CASH",
        cashier="Cajero Test",
        is_reprint=False,
        organization=None,
        branch=None,
        returns=None,
        payments_detail=None,
    )
    defaults.update(kwargs)
    return p.build_ticket_bytes(sale, **defaults)


def _decode(raw: bytes) -> str:
    return raw.decode("latin-1", "replace")


class TestUnitPriceFusion:
    def test_qty_not_one_shows_at_price_inline(self):
        """qty != 1 → '@X.XX' appears in the same product line, no separate c/u line."""
        sale = _make_sale([_line("Manzana Roja", 3, 50)])
        raw = _build(sale)
        decoded = _decode(raw)
        # The unit price is fused inline on the product row
        assert "MANZANA ROJA" in decoded
        assert "@50.00" in decoded
        # The old Font B "c/u" line is gone
        assert "c/u" not in decoded
        assert "@ $" not in decoded

    def test_qty_one_still_shows_at_price(self):
        """OXXO style: @PRICE is always shown for consistent column alignment,
        even when qty == 1 (pre-redesign omitted it)."""
        sale = _make_sale([_line("Pan Integral", 1, 25)])
        raw = _build(sale)
        decoded = _decode(raw)
        assert "PAN INTEGRAL" in decoded
        assert "@25.00" in decoded

    def test_mixed_qty_items(self):
        sale = _make_sale([
            _line("ProductoA", 1, 10),
            _line("ProductoB", 2, 15),
        ])
        raw = _build(sale)
        decoded = _decode(raw)
        assert "PRODUCTOA" in decoded
        assert "@10.00" in decoded
        assert "PRODUCTOB" in decoded
        assert "@15.00" in decoded


class TestTotalsBlock:
    def test_subtotal_iva_total_block(self):
        """Compact totals: SUBTOTAL / IVA / TOTAL — no item count, no Pagado/Cambio."""
        sale = _make_sale([
            _line("A", 2, 10),
            _line("B", 3, 5),
        ])
        raw = _build(sale)
        decoded = _decode(raw)
        assert "SUBTOTAL:" in decoded
        assert "IVA:" in decoded
        assert "TOTAL:" in decoded
        # Old labels are gone
        assert "Subtotal (5 art.)" not in decoded
        assert "Articulos:" not in decoded
        assert "Pagado" not in decoded
        assert "Cambio" not in decoded

    def test_total_line_is_bold(self):
        """The TOTAL row must be wrapped in BOLD_ON / BOLD_OFF.
        Use rfind to skip the 'TOTAL' substring inside 'SUBTOTAL:'."""
        sale = _make_sale([_line("X", 1, 10)])
        raw = _build(sale)
        p = PosPrinter(paper_width_mm=80)
        idx = raw.rfind(b"TOTAL:")
        assert idx > 0, "TOTAL: line not found"
        bold_on = p.CMD["BOLD_ON"]
        bold_off = p.CMD["BOLD_OFF"]
        prefix = raw[:idx]
        last_on = prefix.rfind(bold_on)
        last_off = prefix.rfind(bold_off)
        assert last_on > last_off, (
            f"TOTAL: must be inside a BOLD_ON region (last_on={last_on}, last_off={last_off})"
        )


class TestPaymentLine:
    def test_single_payment_one_line(self):
        sale = _make_sale([_line("Item", 1, 100)])
        raw = _build(sale, paid=Decimal("150"), change=Decimal("50"), method="CASH",
                     payments_detail=[{"method": "CASH", "amount": 150.0, "reference": ""}])
        decoded = _decode(raw)
        assert "EFECTIVO" in decoded
        assert "REC:150.00" in decoded
        assert "CAM:50.00" in decoded

    def test_mixed_payment_stacked(self):
        sale = _make_sale([_line("Item", 1, 100)])
        raw = _build(sale, paid=Decimal("100"), change=Decimal("0"), method="MIXTO",
                     payments_detail=[
                         {"method": "CASH", "amount": 50.0, "reference": ""},
                         {"method": "CARD", "amount": 50.0, "reference": ""},
                     ])
        decoded = _decode(raw)
        assert "EFECTIVO" in decoded
        assert "TARJETA" in decoded
        # Last method carries CAM
        assert "REC:50.00" in decoded
        assert "CAM:0.00" in decoded


class TestPreCutMargin:
    def test_pre_cut_block_is_three_lf(self):
        """Pre-cut margin: exactly LF*3 (legacy branding line removed).
        The footer's own \\n is not part of the trailing run because a LEFT
        command (3 non-LF bytes) sits between them."""
        sale = _make_sale([_line("Item", 1, 10)])
        raw = _build(sale)
        p = PosPrinter(paper_width_mm=80)
        assert raw.endswith(p.CMD["CUT"])
        tail = raw[:-len(p.CMD["CUT"])]
        trailing = 0
        for b in reversed(tail):
            if b == 0x0A:
                trailing += 1
            else:
                break
        assert trailing == 3, f"Expected 3 trailing LF margin, got {trailing}"


class TestOverallCompaction:
    def test_ten_item_ticket_line_count_under_threshold(self):
        """10-item ticket should fit under the post-redesign ceiling.
        Pre-redesign: ~46 lines. Post-redesign target: <= 22.
        Ceiling bumped to 23: `_make_sale` fija `customer_name="Cliente Test"`,
        y ahora el encabezado agrega una línea `Cliente: ...` cuando hay nombre
        (2026-09-17, task-1 de "Cliente en el POS")."""
        lines = [_line(f"Producto {i}", 2, 10) for i in range(10)]
        sale = _make_sale(lines)
        raw = _build(sale)
        line_count = raw.count(b"\n")
        assert line_count <= 23, f"Ticket grew to {line_count} lines; regression"


class TestDefaultWidthAndFont:
    """Defaults post-context/contexto_agente_impresion_linux.md."""

    def test_80mm_defaults_to_56_cols(self):
        p = PosPrinter(paper_width_mm=80)
        assert p.cols == 56
        assert p.cols == PosPrinter.DEFAULT_COLS_80MM

    def test_58mm_defaults_to_32_cols(self):
        p = PosPrinter(paper_width_mm=58)
        assert p.cols == 32
        assert p.cols == PosPrinter.DEFAULT_COLS_58MM

    def test_80mm_emits_font_b_right_after_reset(self):
        """For 80mm + 56 cols we need compact font (ESC M 1) right after ESC @."""
        sale = _make_sale([_line("X", 1, 10)])
        raw = _build(sale)
        reset_idx = raw.find(b"\x1b\x40")  # ESC @
        assert reset_idx >= 0
        # La siguiente secuencia ESC (x1B) después del RESET debe ser ESC M 1 (FONT_B).
        next_esc = raw.find(b"\x1b", reset_idx + 2)
        assert next_esc >= 0
        assert raw[next_esc : next_esc + 3] == b"\x1b\x4d\x01", (
            "Se esperaba FONT_B (compact) después de RESET para 80mm/56cols"
        )

    def test_58mm_emits_font_a_right_after_reset(self):
        """58mm mantiene FONT_A como default."""
        sale = _make_sale([_line("X", 1, 10)])
        p = PosPrinter(paper_width_mm=58)
        raw = p.build_ticket_bytes(
            sale,
            paid=Decimal("0"), change=Decimal("0"),
            method="CASH", cashier="Test",
            is_reprint=False, organization=None, branch=None,
            returns=None, payments_detail=None,
        )
        reset_idx = raw.find(b"\x1b\x40")
        assert reset_idx >= 0
        next_esc = raw.find(b"\x1b", reset_idx + 2)
        assert raw[next_esc : next_esc + 3] == b"\x1b\x4d\x00", (
            "Se esperaba FONT_A (regular) después de RESET para 58mm"
        )


class TestClienteEnEncabezado:
    def test_imprime_cliente_cuando_hay_nombre(self):
        sale = _make_sale([_line("Playera", 1, 100)])
        sale.customer_name = "Patricio Pérez"
        decoded = _decode(_build(sale))
        assert "Cliente: Patricio P" in decoded  # latin-1 conserva la é; se busca el prefijo por si el ancho recorta

    def test_no_imprime_publico_general(self):
        sale = _make_sale([_line("Playera", 1, 100)])
        sale.customer_name = " público general "
        decoded = _decode(_build(sale))
        assert "Cliente:" not in decoded

    def test_no_imprime_publico_general_sin_acento(self):
        """"PUBLICO GENERAL" (sin tilde) debe tratarse igual que "Público General"."""
        sale = _make_sale([_line("Playera", 1, 100)])
        sale.customer_name = "PUBLICO GENERAL"
        decoded = _decode(_build(sale))
        assert "Cliente:" not in decoded

    def test_sin_nombre_no_agrega_linea(self):
        sale = _make_sale([_line("Playera", 1, 100)])
        sale.customer_name = None
        decoded = _decode(_build(sale))
        assert "Cliente:" not in decoded
