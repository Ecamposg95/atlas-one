"""Secciones boutique del ticket (2026-09-19).

Pedido del dueño de Eleven Fashion: el ticket debe llevar encabezado propio,
redes sociales, términos y condiciones, y la línea de Atlas como proveedor
tecnológico. Regla de oro de este archivo: **una sección vacía no imprime
nada**, así que una organización que no configure nada recibe exactamente el
ticket de siempre.

Los mocks son `SimpleNamespace` como en tests/test_ticket_layout.py: el
constructor del ticket lee los atributos al vuelo y no necesita base de datos.
"""
from decimal import Decimal
from datetime import datetime, timezone
from types import SimpleNamespace
from pathlib import Path

import pytest

from app.pos_printer import PosPrinter

LEGACY_HEADER = "ATLAS POS - Nota de Venta"


# ─── Helpers (espejo de tests/test_ticket_layout.py) ──────────────────────

def _line(description, quantity, unit_price):
    qty = Decimal(str(quantity))
    unit = Decimal(str(unit_price))
    return SimpleNamespace(
        description=description,
        quantity=qty,
        unit_price=unit,
        total_line=qty * unit,
        variant_id="v1",
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
        created_at=datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc),
        notes=None,
        requires_invoice=False,
    )


def _org(**kwargs):
    """Organización mock. Sin kwargs = ninguna sección boutique configurada."""
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
        ticket_instagram=None,
        ticket_facebook=None,
        ticket_tiktok=None,
        ticket_whatsapp=None,
        ticket_show_vendor=True,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _build(sale, ancho=80, **kwargs):
    p = PosPrinter(paper_width_mm=ancho)
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


def _lineas_visibles(raw: bytes, ancho=80):
    """Líneas tal como salen en el papel: sin los comandos ESC/POS.

    Se borran los comandos exactos del `CMD` de la impresora (no un regex
    goloso de ESC, que se comía el texto que venía después del comando).
    """
    p = PosPrinter(paper_width_mm=ancho)
    for cmd in sorted(p.CMD.values(), key=len, reverse=True):
        if cmd == b"\x0A":
            continue
        raw = raw.replace(cmd, b"")
    return [l.rstrip() for l in raw.decode("latin-1", "replace").split("\n")]


# ─── 1. Sin configurar: el ticket de siempre ──────────────────────────────

def test_sin_campos_configurados_el_ticket_no_cambia():
    """Una org con los campos nuevos en None/True imprime byte por byte lo
    mismo que una org que ni siquiera tiene esos atributos."""
    org_basica = SimpleNamespace(
        name="Eleven Fashion", legal_name=None, tax_id=None, tax_regime=None,
        address=None, phone=None, logo_url=None, website=None,
        price_includes_tax=False,
        ticket_header=None, ticket_footer="Gracias por su compra!",
    )
    sale = _make_sale()
    viejo = _build(_make_sale(), organization=org_basica)
    nuevo = _build(sale, organization=_org())
    assert viejo == nuevo


def test_sin_campos_configurados_no_imprime_titulos_boutique():
    decoded = _decode(_build(_make_sale(), organization=_org()))
    assert "SIGUENOS" not in decoded
    assert "TERMINOS Y CONDICIONES" not in decoded


# ─── 2. Encabezado personalizado ──────────────────────────────────────────

def test_ticket_header_se_imprime_bajo_el_nombre():
    raw = _build(_make_sale(), organization=_org(ticket_header="Boutique de moda"))
    lineas = [l for l in _lineas_visibles(raw) if l]
    assert "Boutique de moda" in lineas
    assert lineas.index("Boutique de moda") == lineas.index("Eleven Fashion") + 1


def test_ticket_header_heredado_no_se_imprime():
    """"ATLAS POS - Nota de Venta" es el seed de todas las orgs: no es un
    encabezado que alguien haya pedido."""
    decoded = _decode(_build(_make_sale(), organization=_org(ticket_header=LEGACY_HEADER)))
    assert "Nota de Venta" not in decoded


def test_ticket_header_de_sucursal_gana():
    branch = SimpleNamespace(
        name="Roma", city=None, phone=None, logo_url=None,
        ticket_header="Sucursal Roma", ticket_footer=None,
    )
    decoded = _decode(_build(_make_sale(), organization=_org(ticket_header="Boutique de moda"),
                             branch=branch))
    assert "Sucursal Roma" in decoded
    assert "Boutique de moda" not in decoded


# ─── 3. Redes sociales ────────────────────────────────────────────────────

def _org_redes(**kwargs):
    base = dict(
        ticket_instagram="@elevenfashion",
        ticket_facebook="Eleven Fashion",
        ticket_tiktok="@eleven",
        ticket_whatsapp="55 1234 5678",
        website="elevenfashion.mx",
    )
    base.update(kwargs)
    return _org(**base)


def test_redes_imprime_titulo_y_una_linea_por_red():
    lineas = _lineas_visibles(_build(_make_sale(), organization=_org_redes()))
    assert "SIGUENOS" in lineas
    assert "Instagram: @elevenfashion" in lineas
    assert "Facebook: Eleven Fashion" in lineas
    assert "TikTok: @eleven" in lineas
    assert "WhatsApp: 55 1234 5678" in lineas
    assert "Web: elevenfashion.mx" in lineas


def test_redes_vacias_no_aparecen():
    lineas = _lineas_visibles(_build(_make_sale(),
                                     organization=_org(ticket_instagram="@elevenfashion")))
    assert "SIGUENOS" in lineas
    assert "Instagram: @elevenfashion" in lineas
    assert not any(l.startswith("Facebook:") for l in lineas)
    assert not any(l.startswith("TikTok:") for l in lineas)
    assert not any(l.startswith("WhatsApp:") for l in lineas)
    assert not any(l.startswith("Web:") for l in lineas)


# ─── 4. Términos y condiciones ────────────────────────────────────────────

TERMINOS = (
    "Cambios y devoluciones dentro de los 15 dias naturales posteriores a la "
    "compra, presentando este ticket y con la etiqueta original adherida a la "
    "prenda. No se aceptan cambios en ropa interior, trajes de bano ni "
    "articulos de liquidacion. La garantia cubre defectos de fabricacion."
)


@pytest.mark.parametrize("ancho", [58, 80])
def test_terminos_se_envuelven_sin_pasarse_del_ancho(ancho):
    p = PosPrinter(paper_width_mm=ancho)
    raw = _build(_make_sale(), ancho=ancho, organization=_org(ticket_terms=TERMINOS))
    lineas = _lineas_visibles(raw, ancho)
    assert "TERMINOS Y CONDICIONES" in lineas
    for l in lineas:
        assert len(l) <= p.cols, f"Linea de {len(l)} > {p.cols}: {l!r}"


def test_terminos_conservan_el_texto_completo():
    raw = _build(_make_sale(), organization=_org(ticket_terms=TERMINOS))
    lineas = _lineas_visibles(raw)
    inicio = lineas.index("TERMINOS Y CONDICIONES")
    cuerpo = " ".join(lineas[inicio + 1:])
    assert TERMINOS.split() == cuerpo.split()[: len(TERMINOS.split())]


def test_terminos_respetan_los_parrafos_del_usuario():
    texto = "Primera regla.\nSegunda regla."
    lineas = _lineas_visibles(_build(_make_sale(), organization=_org(ticket_terms=texto)))
    assert "Primera regla." in lineas
    assert "Segunda regla." in lineas


# ─── 5. Proveedor tecnológico ─────────────────────────────────────────────

def test_proveedor_se_imprime_cuando_esta_encendido():
    decoded = _decode(_build(_make_sale(), organization=_org(ticket_show_vendor=True)))
    assert "Sistema: Atlas One | Atlas Tech" in decoded
    assert "atlasone.com.mx" in decoded


def test_proveedor_apagado_no_imprime_nada_de_atlas():
    decoded = _decode(_build(_make_sale(), organization=_org(ticket_show_vendor=False)))
    assert "Atlas" not in decoded
    assert "atlasone" not in decoded


# ─── 6. Orden del bloque ──────────────────────────────────────────────────

def test_orden_pie_redes_terminos_proveedor_y_corte():
    p = PosPrinter(paper_width_mm=80)
    raw = _build(_make_sale(), organization=_org_redes(ticket_terms=TERMINOS,
                                                      ticket_show_vendor=True))
    i_pie = raw.find(b"Gracias por su compra!")
    i_redes = raw.find(b"SIGUENOS")
    i_terms = raw.find(b"TERMINOS Y CONDICIONES")
    i_prov = raw.find(b"Sistema: Atlas One | Atlas Tech")
    i_cierre = raw.find(p.CMD["LF"] * 3 + p.CMD["CUT"])
    assert -1 < i_pie < i_redes < i_terms < i_prov < i_cierre
    assert raw.endswith(p.CMD["LF"] * 3 + p.CMD["CUT"])


# ─── 7. Reimpresión (ticket reemitido) ────────────────────────────────────

def test_ticket_reemitido_lleva_el_mismo_bloque():
    p = PosPrinter(paper_width_mm=80)
    raw = p.build_reissued_ticket_bytes(
        _make_sale(), cashier="Cajero Test",
        organization=_org_redes(ticket_terms=TERMINOS, ticket_show_vendor=True),
        branch=None, returns=[],
    )
    decoded = _decode(raw)
    assert "SIGUENOS" in decoded
    assert "Instagram: @elevenfashion" in decoded
    assert "TERMINOS Y CONDICIONES" in decoded
    assert "Sistema: Atlas One | Atlas Tech" in decoded


# ─── 8. Ticket HTML (app/templates/print/ticket.html) ─────────────────────

def _render_html(organization):
    from jinja2 import Environment, FileSystemLoader

    raiz = Path(__file__).resolve().parents[1] / "app" / "templates"
    env = Environment(loader=FileSystemLoader(str(raiz)))
    tmpl = env.get_template("print/ticket.html")
    linea = SimpleNamespace(description="Playera", quantity=1.0, unit_price=100.0,
                            variant_id="v1", total_line=100.0)
    sale = SimpleNamespace(
        id="s-1", lines=[linea], series="A", folio=123,
        subtotal=100.0, tax_amount=0.0, total_amount=100.0,
        payments=[SimpleNamespace(method="CASH", amount=100.0, reference=None)],
        created_at=datetime(2026, 9, 19, 12, 0),
        notes=None, requires_invoice=False,
    )
    return tmpl.render(
        sale=sale, organization=organization, branch=None,
        seller=SimpleNamespace(username="cajero"), payments=sale.payments,
        approved_returns=None, cliente_display="Cliente Test",
    )


def test_html_sin_configurar_no_trae_secciones_boutique():
    html = _render_html(_org(ticket_show_vendor=False))
    assert "Síguenos" not in html
    assert "Términos y condiciones" not in html
    assert "Atlas One" not in html


def test_html_trae_redes_terminos_y_proveedor_cuando_estan_configurados():
    html = _render_html(_org_redes(ticket_terms=TERMINOS, ticket_show_vendor=True))
    assert "Síguenos" in html
    assert "@elevenfashion" in html
    assert "Eleven Fashion" in html
    assert "@eleven" in html
    assert "55 1234 5678" in html
    assert "elevenfashion.mx" in html
    assert "Términos y condiciones" in html
    assert "Cambios y devoluciones" in html
    assert "Atlas One" in html
    assert "atlasone.com.mx" in html


def test_html_proveedor_apagado_no_muestra_atlas():
    html = _render_html(_org_redes(ticket_terms=TERMINOS, ticket_show_vendor=False))
    assert "Términos y condiciones" in html
    assert "Atlas One" not in html
    assert "atlasone.com.mx" not in html
