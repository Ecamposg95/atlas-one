import io
from decimal import Decimal

import pytest
from pypdf import PdfWriter

from app.modules.ai.cliente_anthropic import ClienteEstructuradoFalso
from app.modules.cargas.extraccion_pdf import extraer_pdf, ESQUEMA_PDF


def _pdf(paginas: int) -> bytes:
    w = PdfWriter()
    for _ in range(paginas):
        w.add_blank_page(width=200, height=200)
    b = io.BytesIO()
    w.write(b)
    return b.getvalue()


def _r(desc="Camisa", cantidad="2", pagina=None, **kw):
    base = {"descripcion_original": desc, "marca": "Marca Uno", "tipo": None, "material": None,
            "color": None, "talla": None, "cantidad": cantidad, "costo_unitario": None,
            "precio": None, "moneda": None, "observacion": None, "duda": None, "pagina": pagina}
    base.update(kw)
    return base


def _resp(renglones, monedas=(), cont=False):
    return {"renglones": list(renglones), "monedas": list(monedas), "continua_en_siguiente": cont}


def test_pdf_corto_una_llamada():
    c = ClienteEstructuradoFalso([_resp([_r(pagina=2, costo_unitario="3.50"), _r("Pantalon")])])
    ex = extraer_pdf(_pdf(3), c, "Tienda de ropa")
    assert len(c.llamadas) == 1
    assert len(ex.renglones) == 2
    assert ex.renglones[0].origen == "pág. 2"
    assert ex.renglones[0].costo_unitario == Decimal("3.50")
    assert ex.renglones[1].origen == "págs. 1-3"
    assert "Tienda de ropa" in c.llamadas[0]["sistema"]
    assert c.llamadas[0]["contenido"][0]["type"] == "document"


def test_pdf_largo_se_parte_en_bloques():
    c = ClienteEstructuradoFalso([_resp([_r("A", pagina=1)]), _resp([_r("B", pagina=1)]),
                                  _resp([_r("C")])])
    ex = extraer_pdf(_pdf(31), c, "")
    assert len(c.llamadas) == 3
    assert [r.origen for r in ex.renglones] == ["pág. 1", "pág. 16", "pág. 31"]


def test_renglon_partido_entre_bloques_no_se_duplica():
    c = ClienteEstructuradoFalso([_resp([_r("Bolsa roja", "4")], cont=True),
                                  _resp([_r("bolsa  roja ", "4", costo_unitario="9"), _r("Otra")])])
    ex = extraer_pdf(_pdf(20), c, "")
    assert [r.descripcion_original for r in ex.renglones] == ["Bolsa roja", "Otra"]
    assert ex.renglones[0].costo_unitario == Decimal("9")
    textos = [x.get("text", "") for x in c.llamadas[1]["contenido"]]
    assert any("Bolsa roja" in t for t in textos)


def test_sin_continuacion_se_conservan_repetidos():
    c = ClienteEstructuradoFalso([_resp([_r("Bolsa")]), _resp([_r("Bolsa")])])
    assert len(extraer_pdf(_pdf(20), c, "").renglones) == 2


def test_tipo_cambio_contradictorio_queda_none():
    c = ClienteEstructuradoFalso([
        _resp([], [{"codigo": "USD", "tipo_cambio": "17.5"}, {"codigo": "EUR", "tipo_cambio": "19"}]),
        _resp([], [{"codigo": "USD", "tipo_cambio": "18"}, {"codigo": "EUR", "tipo_cambio": "19.0"},
                   {"codigo": "CNY", "tipo_cambio": None}])])
    ex = extraer_pdf(_pdf(20), c, "")
    assert ex.monedas == {"USD": None, "EUR": Decimal("19"), "CNY": None}


def test_tokens_se_suman():
    class C(ClienteEstructuradoFalso):
        def generar(self, **kw):
            r = super().generar(**kw)
            r.tokens_entrada, r.tokens_salida = 10, 5
            return r
    c = C([_resp([]), _resp([])])
    ex = extraer_pdf(_pdf(20), c, "")
    assert (ex.tokens_entrada, ex.tokens_salida) == (20, 10)


def test_numero_ilegible_marca_duda():
    c = ClienteEstructuradoFalso([_resp([_r(cantidad="abc", precio="x")])])
    r = extraer_pdf(_pdf(1), c, "").renglones[0]
    assert r.duda and r.precio is None


def test_pdf_ilegible_error_claro():
    with pytest.raises(ValueError, match="PDF"):
        extraer_pdf(b"no es pdf", ClienteEstructuradoFalso([]), "")


def test_pdf_cifrado_error_claro():
    w = PdfWriter()
    w.add_blank_page(width=10, height=10)
    w.encrypt("clave")
    b = io.BytesIO()
    w.write(b)
    with pytest.raises(ValueError, match="protegido|cifrado|contraseña"):
        extraer_pdf(b.getvalue(), ClienteEstructuradoFalso([]), "")


def test_esquema_estricto():
    def rec(n):
        if isinstance(n, dict):
            if n.get("type") == "object":
                assert n["additionalProperties"] is False
                assert set(n["properties"]) == set(n["required"])
            for v in n.values():
                rec(v)
        elif isinstance(n, list):
            for v in n:
                rec(v)
    rec(ESQUEMA_PDF)
