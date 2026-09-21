"""Estilo de línea "detallado" del ticket (2026-09-21).

El renglón compacto de hoy mete marca, prenda y talla en una sola columna de
32 caracteres y recorta: "LOUIS VUITTON · CHAMARRA MEZC". La boutique quiere el
bloque de tres líneas:

    1x  LOUIS VUITTON
        Chamarra mezclilla
        Talla M                          @4,000.00    4,000.00

Se enciende por organización (`ticket_line_style = "detailed"`). Regla de oro:
sin configurarlo — o con "compact" — el ticket sale **byte por byte** como hoy.

Mocks `SimpleNamespace` como en tests/test_ticket_layout.py: el constructor lee
los atributos al vuelo y no necesita base de datos.
"""
import re
from decimal import Decimal
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.pos_printer import PosPrinter


# ─── Helpers ──────────────────────────────────────────────────────────────

def _variant(nombre, *, marca=None, modelo=None, color=None, talla=None):
    producto = SimpleNamespace(
        name=nombre,
        model=modelo,
        brand=SimpleNamespace(name=marca) if marca else None,
    )
    return SimpleNamespace(product=producto, color=color, size=talla)


def _line(description, quantity, unit_price, variant=None):
    qty = Decimal(str(quantity))
    unit = Decimal(str(unit_price))
    return SimpleNamespace(
        description=description,
        quantity=qty,
        unit_price=unit,
        total_line=qty * unit,
        variant_id="v1",
        variant=variant,
    )


def _make_sale(lines=None, *, subtotal=None, tax=0, series="A", folio=123):
    lines = lines or [_line("Playera", 1, 100)]
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
        created_at=datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc),
        notes=None,
        requires_invoice=False,
    )


def _org(**kwargs):
    """Organización mock. Sin kwargs = estilo de línea sin configurar."""
    base = dict(
        name="Eleven Fashion",
        legal_name=None,
        tax_id=None,
        tax_regime=None,
        address=None,
        phone=None,
        logo_url=None,
        website=None,
        price_includes_tax=False,
        ticket_header=None,
        ticket_footer="Gracias por su compra!",
        ticket_terms=None,
        ticket_terms_url=None,
        ticket_instagram=None,
        ticket_facebook=None,
        ticket_tiktok=None,
        ticket_whatsapp=None,
        ticket_show_vendor=False,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _build(sale, ancho=80, organization=None, **kwargs):
    p = PosPrinter(paper_width_mm=ancho)
    defaults = dict(
        paid=Decimal("0"),
        change=Decimal("0"),
        method="CASH",
        cashier="Cajero Test",
        is_reprint=False,
        organization=organization,
        branch=None,
        returns=None,
        payments_detail=None,
    )
    defaults.update(kwargs)
    return p.build_ticket_bytes(sale, **defaults)


# Comandos ESC/POS que aparecen en estos tickets (sin logo ni QR): RESET,
# fuente, alineación, negritas, tamaño y corte. Se quitan para poder contar
# columnas de TEXTO.
_COMANDOS = re.compile(r"\x1b@|\x1b[aMEp!\-].|\x1d!.|\x1dV..")


def _renglones(raw: bytes) -> list[str]:
    """Líneas de texto del ticket, sin comandos ESC/POS."""
    return _COMANDOS.sub("", raw.decode("latin-1", "replace")).split("\n")


def _bloque_producto(raw: bytes) -> list[str]:
    """Las líneas entre el primer separador y el segundo (los productos)."""
    lineas = _renglones(raw)
    seps = [i for i, l in enumerate(lineas) if set(l) == {"-"} and l]
    return lineas[seps[0] + 1:seps[1]]


CHAMARRA = _variant("Chamarra", marca="Louis Vuitton", modelo="mezclilla", talla="M")


# ─── 1. El bloque de tres líneas ──────────────────────────────────────────
class TestBloqueDetallado:
    def test_tres_lineas_marca_nombre_y_talla(self):
        sale = _make_sale([_line("Louis Vuitton · Chamarra mezclilla · Talla M",
                                 1, 4000, CHAMARRA)])
        raw = _build(sale, organization=_org(ticket_line_style="detailed"))
        bloque = _bloque_producto(raw)
        assert len(bloque) == 3, bloque
        assert bloque[0] == "1x  LOUIS VUITTON"
        assert bloque[1].startswith("    Chamarra mezclilla")
        assert bloque[2].startswith("    Talla M")
        assert "@4,000.00" in bloque[2]
        assert bloque[2].endswith("4,000.00")
        assert all(len(l) <= 56 for l in bloque), bloque

    def test_color_y_talla_en_la_linea_de_precio(self):
        v = _variant("Chamarra", marca="Louis Vuitton", color="Beige", talla="M")
        sale = _make_sale([_line("x", 1, 100, v)])
        bloque = _bloque_producto(_build(sale, organization=_org(ticket_line_style="detailed")))
        assert bloque[2].startswith("    Beige, Talla M")

    def test_sin_marca_son_dos_lineas(self):
        v = _variant("Playera", talla="M")
        sale = _make_sale([_line("Playera (M)", 2, 150, v)])
        bloque = _bloque_producto(_build(sale, organization=_org(ticket_line_style="detailed")))
        assert len(bloque) == 2, bloque
        assert bloque[0].startswith("2x  PLAYERA")
        assert bloque[1].startswith("    Talla M")
        assert "@150.00" in bloque[1] and bloque[1].endswith("300.00")

    def test_sin_talla_ni_color_la_linea_de_precio_va_sin_atributos(self):
        v = _variant("Gorra", marca="Gucci")
        sale = _make_sale([_line("Gucci · Gorra", 1, 500, v)])
        bloque = _bloque_producto(_build(sale, organization=_org(ticket_line_style="detailed")))
        assert len(bloque) == 3, bloque
        assert bloque[2].strip().startswith("@500.00")

    def test_sin_variante_usa_la_descripcion_congelada(self):
        sale = _make_sale([_line("Servicio de ajuste", 1, 200, None)])
        bloque = _bloque_producto(_build(sale, organization=_org(ticket_line_style="detailed")))
        assert bloque[0].startswith("1x  SERVICIO DE AJUSTE")
        assert bloque[-1].strip().startswith("@200.00")


# ─── 2. Papel de 58 mm: envuelve, no recorta ──────────────────────────────
class TestPapelAngosto:
    def test_nombre_largo_envuelve_sin_exceder_las_columnas(self):
        v = _variant("Chamarra de mezclilla azul con forro de borrego",
                     marca="Louis Vuitton", modelo="edición limitada", talla="M")
        sale = _make_sale([_line("x", 1, 4000, v)])
        bloque = _bloque_producto(_build(sale, ancho=58,
                                         organization=_org(ticket_line_style="detailed")))
        assert all(len(l) <= 32 for l in bloque), bloque
        assert len(bloque) > 3, "el nombre largo ocupa varias líneas"
        cuerpo = " ".join(l.strip() for l in bloque[1:-1])
        # Nada se recorta: el nombre completo (con modelo) sigue legible.
        assert cuerpo == "Chamarra de mezclilla azul con forro de borrego edición limitada"
        assert bloque[0] == "1x  LOUIS VUITTON"

    def test_atributos_largos_bajan_a_su_propio_renglon(self):
        """A 58 mm "Beige, Talla CH" no cabe junto a "@1,250.50 2,501.00":
        la talla se va a su renglon antes que recortarse."""
        v = _variant("Playera", marca="Gucci", color="Beige", talla="CH")
        sale = _make_sale([_line("x", 2, 1250.50, v)])
        bloque = _bloque_producto(_build(sale, ancho=58,
                                         organization=_org(ticket_line_style="detailed")))
        assert all(len(l) <= 32 for l in bloque), bloque
        assert "    Beige, Talla CH" in bloque
        assert bloque[-1].strip() == "@1,250.50 2,501.00"

    def test_marca_larga_se_trunca_al_ancho(self):
        v = _variant("Playera", marca="Marca Con Un Nombre Larguisimo De Verdad", talla="S")
        sale = _make_sale([_line("x", 1, 100, v)])
        bloque = _bloque_producto(_build(sale, ancho=58,
                                         organization=_org(ticket_line_style="detailed")))
        assert all(len(l) <= 32 for l in bloque), bloque


# ─── 3. Nadie cambia sin configurarlo ─────────────────────────────────────
class TestCompactoIntacto:
    def _ticket(self, organization, ancho=80):
        sale = _make_sale([_line("Louis Vuitton · Chamarra mezclilla · Talla M",
                                 1, 4000, CHAMARRA)])
        return _build(sale, ancho=ancho, organization=organization)

    @pytest.mark.parametrize("ancho", [80, 58])
    def test_sin_atributo_y_con_compact_son_el_mismo_ticket(self, ancho):
        sin_configurar = self._ticket(_org(), ancho)
        compacto = self._ticket(_org(ticket_line_style="compact"), ancho)
        assert sin_configurar == compacto

    def test_compacto_sigue_imprimiendo_la_descripcion_en_una_linea(self):
        bloque = _bloque_producto(self._ticket(_org()))
        assert len(bloque) == 1
        assert bloque[0].startswith("1x  LOUIS VUITTON")
        assert bloque[0].endswith("4000.00")

    def test_sin_organizacion_es_compacto(self):
        sale = _make_sale([_line("Playera", 1, 100, CHAMARRA)])
        assert len(_bloque_producto(_build(sale, organization=None))) == 1


# ─── 4. Reimpresión y reemisión ───────────────────────────────────────────
class TestReemision:
    def _reemitido(self, organization):
        sale = _make_sale([_line("Louis Vuitton · Chamarra mezclilla · Talla M",
                                 2, 4000, CHAMARRA)])
        p = PosPrinter(paper_width_mm=80)
        return p.build_reissued_ticket_bytes(sale, cashier="Cajero Test",
                                             organization=organization, branch=None,
                                             returns=None)

    def test_reemitido_detallado(self):
        bloque = _bloque_producto(self._reemitido(_org(ticket_line_style="detailed")))
        assert len(bloque) == 3, bloque
        assert bloque[0].startswith("2x  LOUIS VUITTON")
        assert bloque[2].startswith("    Talla M")

    def test_reemitido_compacto_intacto(self):
        assert self._reemitido(_org()) == self._reemitido(_org(ticket_line_style="compact"))
        assert len(_bloque_producto(self._reemitido(_org()))) == 1

    def test_reimpresion_detallada(self):
        sale = _make_sale([_line("x", 1, 4000, CHAMARRA)])
        raw = _build(sale, organization=_org(ticket_line_style="detailed"), is_reprint=True)
        assert "*** REIMPRESION ***" in raw.decode("latin-1")
        assert len(_bloque_producto(raw)) == 3
