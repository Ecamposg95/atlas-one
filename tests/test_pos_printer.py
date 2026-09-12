# tests/test_pos_printer.py
import pytest
from unittest.mock import MagicMock
from decimal import Decimal
from app.pos_printer import PosPrinter


def _make_org(**kwargs):
    org = MagicMock()
    org.name = kwargs.get("name", "Tienda Demo")
    org.legal_name = kwargs.get("legal_name", None)
    org.tax_id = kwargs.get("tax_id", None)
    org.tax_regime = kwargs.get("tax_regime", None)
    org.address = kwargs.get("address", None)
    org.phone = kwargs.get("phone", None)
    org.logo_url = None
    org.ticket_header = kwargs.get("ticket_header", None)
    org.ticket_footer = kwargs.get("ticket_footer", None)
    # Modo de precio (app/services/tax.py). Explicito porque en un MagicMock
    # cualquier atributo no declarado sale truthy, y eso pondria los tickets en
    # modo "precio con IVA incluido" sin que ninguna prueba lo pidiera.
    org.price_includes_tax = kwargs.get("price_includes_tax", False)
    return org


def _make_branch(**kwargs):
    b = MagicMock()
    b.name = kwargs.get("name", "Sucursal Norte")
    b.address = kwargs.get("address", None)
    b.address_line1 = kwargs.get("address_line1", None)
    b.neighborhood = kwargs.get("neighborhood", None)
    b.city = kwargs.get("city", None)
    b.state = kwargs.get("state", None)
    b.postal_code = kwargs.get("postal_code", None)
    b.phone = kwargs.get("phone", None)
    b.ticket_header = kwargs.get("ticket_header", None)
    b.ticket_footer = kwargs.get("ticket_footer", None)
    return b


def _make_line(description, quantity, unit_price, total_line, variant_id="v1"):
    line = MagicMock()
    line.description = description
    line.quantity = quantity
    line.unit_price = Decimal(str(unit_price))
    line.total_line = Decimal(str(total_line))
    line.variant_id = variant_id
    return line


def _make_sale(**kwargs):
    sale = MagicMock()
    sale.id = "sale-001"
    sale.series = "A"
    sale.folio = 1001
    sale.customer_name = kwargs.get("customer_name", "Cliente Ejemplo")
    sale.subtotal = Decimal(kwargs.get("subtotal", "86.21"))
    sale.tax_amount = Decimal(kwargs.get("tax_amount", "13.79"))
    sale.total_amount = Decimal(kwargs.get("total_amount", "100.00"))
    sale.requires_invoice = kwargs.get("requires_invoice", False)
    sale.notes = kwargs.get("notes", None)
    sale.customer = None
    sale.payments = []

    import datetime, zoneinfo
    sale.created_at = datetime.datetime(2026, 4, 8, 10, 0, 0,
                                        tzinfo=zoneinfo.ZoneInfo("America/Mexico_City"))

    lines = kwargs.get("lines", [
        _make_line("Producto Normal", 2, "43.10", "86.21"),
    ])
    sale.lines = lines
    return sale


def _make_payment(method="CASH", amount="100.00", reference=None):
    p = MagicMock()
    p.method = method
    p.amount = Decimal(amount)
    p.reference = reference
    return p


class TestWrapText:
    def test_normal_wrapping(self):
        p = PosPrinter(paper_width_mm=80)
        result = p._wrap_text("Hola mundo prueba", 10)
        assert result == ["Hola mundo", "prueba"]

    def test_word_longer_than_width_is_split(self):
        p = PosPrinter(paper_width_mm=58)
        # "ABCDEFGHIJKLMNOPQRSTUVWXYZ" = 26 chars, width = 18
        result = p._wrap_text("ABCDEFGHIJKLMNOPQRSTUVWXYZ", 18)
        assert len(result) == 2
        assert result[0] == "ABCDEFGHIJKLMNOPQR"  # 18 chars
        assert result[1] == "STUVWXYZ"            # 8 chars
        for line in result:
            assert len(line) <= 18

    def test_mixed_long_and_short_words(self):
        p = PosPrinter(paper_width_mm=58)
        result = p._wrap_text("A BCDEFGHIJKLMNOPQRSTUVWXYZ fin", 18)
        for line in result:
            assert len(line) <= 18

    def test_empty_string(self):
        p = PosPrinter(paper_width_mm=80)
        assert p._wrap_text("", 26) == []

    def test_exactly_width(self):
        p = PosPrinter(paper_width_mm=80)
        result = p._wrap_text("ABCDEFGHIJ", 10)
        assert result == ["ABCDEFGHIJ"]


class TestColumnLayout:
    def _extract_plain_text(self, raw_bytes):
        """Remove ESC/POS control sequences and return plain text"""
        import re
        text = raw_bytes.decode("latin-1", errors="replace")
        # Remove ESC sequences: \x1B followed by any char and optional params
        text = re.sub(r'\x1B\[[0-9;]*[a-zA-Z]', '', text)
        text = re.sub(r'\x1B[^\x1B\n]*', '', text)
        # Remove other control chars except LF
        text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F]', '', text)
        return text

    def test_80mm_product_line_fits_56_cols(self):
        p = PosPrinter(paper_width_mm=80)
        org = _make_org()
        sale = _make_sale()
        sale.payments = [_make_payment()]
        raw = p.build_ticket_bytes(
            sale=sale, paid=100.0, change=0.0, method="CASH",
            cashier="test", is_reprint=False, organization=org
        )
        text = self._extract_plain_text(raw)
        lines = text.split("\n")
        # Every non-empty line must fit the paper width
        for l in lines:
            stripped = l.rstrip()
            assert len(stripped) <= 56, f"Line too long for 80mm: '{stripped}' ({len(stripped)} chars)"

    def test_58mm_product_line_fits_32_cols(self):
        p = PosPrinter(paper_width_mm=58)
        org = _make_org()
        sale = _make_sale(lines=[
            _make_line("Producto Muy Largo con Nombre Extra", 2, "43.10", "86.21"),
        ])
        sale.payments = [_make_payment()]
        raw = p.build_ticket_bytes(
            sale=sale, paid=100.0, change=0.0, method="CASH",
            cashier="test", is_reprint=False, organization=org
        )
        text = self._extract_plain_text(raw)
        lines = text.split("\n")
        for l in lines:
            stripped = l.rstrip()
            assert len(stripped) <= 32, f"Line too long for 58mm: '{stripped}' ({len(stripped)} chars)"


class TestOrgDataAndNotes:
    def _build(self, **kwargs):
        p = PosPrinter(paper_width_mm=80)
        org = _make_org(**kwargs.get("org", {}))
        sale = _make_sale(**kwargs.get("sale", {}))
        sale.payments = [_make_payment()]
        raw = p.build_ticket_bytes(
            sale=sale, paid=100.0, change=0.0, method="CASH",
            cashier="test", is_reprint=False, organization=org
        )
        return raw.decode("latin-1", errors="replace")

    def test_legal_name_shown_when_different(self):
        text = self._build(org={
            "name": "Tienda Demo",
            "legal_name": "Comercializadora Demo SA de CV"
        })
        assert "Comercializadora Demo SA de CV" in text

    def test_legal_name_not_shown_when_same(self):
        text = self._build(org={"name": "Demo SA", "legal_name": "Demo SA"})
        assert text.count("Demo SA") == 1

    # NOTE: post-redesign (2026-04-29 OXXO compact) the ticket dropped
    # tax_regime, sale notes, and "FACTURA SOLICITADA" from the printed
    # body to save paper. Those flows survive on screen / PDF; the printer
    # tests for them were retired.

    def test_requires_invoice_not_shown_when_false(self):
        text = self._build(sale={"requires_invoice": False})
        assert "FACTURA SOLICITADA" not in text


class TestReissuedTicket:
    def _build_reissued(self, **kwargs):
        p = PosPrinter(paper_width_mm=80)
        org = _make_org(**kwargs.get("org", {}))
        branch = _make_branch(**kwargs.get("branch", {}))
        sale = _make_sale(**kwargs.get("sale", {}))
        raw = p.build_reissued_ticket_bytes(
            sale=sale, cashier="test", organization=org, branch=branch, returns=[]
        )
        return raw.decode("latin-1", errors="replace")

    def test_branch_footer_overrides_org_footer(self):
        text = self._build_reissued(
            org={"ticket_footer": "Gracias org"},
            branch={"ticket_footer": "Gracias sucursal"}
        )
        assert "Gracias sucursal" in text
        assert "Gracias org" not in text

    def test_org_footer_used_when_no_branch_footer(self):
        text = self._build_reissued(
            org={"ticket_footer": "Gracias org"},
            branch={}
        )
        assert "Gracias org" in text

    def _totales(self, text):
        """Devuelve {'SUBTOTAL': float, 'IVA': float, 'TOTAL': float} del ticket.

        El renglon de TOTAL va envuelto en los ESC de negritas, asi que se
        busca por patron y no por inicio de linea; el lookbehind evita que
        'SUBTOTAL:' se lea tambien como 'TOTAL:'.
        """
        import re
        out = {}
        for etiqueta in ("SUBTOTAL", "IVA", "TOTAL"):
            m = re.search(rf"(?<![A-Z]){etiqueta}:\s+(-?\d+\.\d{{2}})", text)
            if m:
                out[etiqueta] = float(m.group(1))
        return out

    def test_modo_neto_suma_el_iva_sobre_lo_remanente(self):
        """Precio neto (modo por defecto): la linea remanente es la base y el
        IVA se suma encima, a la tasa efectiva de la venta."""
        lines = [_make_line("Producto", 2, "100.00", "200.00", variant_id="v1")]
        text = self._build_reissued(
            sale={"lines": lines, "subtotal": "200.00", "tax_amount": "32.00",
                  "total_amount": "232.00"},
        )
        t = self._totales(text)
        assert t["SUBTOTAL"] == 200.00
        assert t["IVA"] == 32.00
        assert t["TOTAL"] == 232.00

    def test_modo_iva_incluido_descompone_en_vez_de_inflar(self):
        """Con `price_includes_tax`, `unit_price` YA trae el IVA: sumarselo
        encima inflaba el ticket reemitido ~16% (auditoria Rmazh §3)."""
        lines = [_make_line("Producto", 2, "116.00", "232.00", variant_id="v1")]
        text = self._build_reissued(
            org={"price_includes_tax": True},
            sale={"lines": lines, "subtotal": "200.00", "tax_amount": "32.00",
                  "total_amount": "232.00"},
        )
        t = self._totales(text)
        assert t["SUBTOTAL"] == 200.00
        assert t["IVA"] == 32.00
        assert t["TOTAL"] == 232.00, "el total reemitido no puede exceder lo cobrado"

    def test_venta_sin_iva_reemite_sin_iva(self):
        lines = [_make_line("Producto", 1, "50.00", "50.00", variant_id="v1")]
        text = self._build_reissued(
            sale={"lines": lines, "subtotal": "50.00", "tax_amount": "0.00",
                  "total_amount": "50.00"},
        )
        t = self._totales(text)
        assert t["IVA"] == 0.00
        assert t["TOTAL"] == 50.00

    def test_reissued_marker_shown(self):
        """Reissued ticket must carry the *** TICKET REEMITIDO *** banner."""
        text = self._build_reissued(sale={
            "lines": [_make_line("Prod A", 3, "10.00", "30.00")]
        })
        assert "TICKET REEMITIDO" in text
