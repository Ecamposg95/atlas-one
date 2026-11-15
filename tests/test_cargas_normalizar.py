from decimal import Decimal as D

from app.modules.cargas.normalizar import (
    agrupar, normalizar_renglon, prefijo_de_marca, sku_para,
)
from app.modules.cargas.reglas import ReglasCarga, TipoPrenda
from app.modules.cargas.tipos import RenglonCrudo


def reglas(**kw):
    base = dict(
        mapa_tallas={"S": "Ch", "L": "G"},
        escala_ropa=["Ch", "M", "G", "XL"],
        tipos={"Camisa": TipoPrenda(codigo_sku="CAMI", departamento="Camisas")},
        materiales_aparte=["Pana"],
        material_normal="Algodón",
        genero_por_marca={"Marca Uno": "HOMBRE"},
        genero_por_omision="UNISEX",
    )
    base.update(kw)
    return ReglasCarga(**base)


def crudo(**kw):
    d = dict(descripcion_original="x", marca="Marca Uno", tipo="Camisa", cantidad=D(1), origen="H!1")
    d.update(kw)
    return RenglonCrudo(**d)


def norm(r, rg=None, monedas=None):
    return normalizar_renglon(r, rg or reglas(), monedas or {})


def test_mapa_tallas_normaliza():
    assert norm(crudo(talla="s ")).talla == "Ch"
    assert norm(crudo(talla="l")).talla == "G"
    assert norm(crudo(talla="M")).talla == "M"


def test_departamento_y_genero():
    n = norm(crudo(tipo=" camisa "))
    assert n.departamento == "Camisas" and n.genero == "HOMBRE"
    assert norm(crudo(marca="Casa Dos")).genero == "UNISEX"


def test_costo_por_tipo_de_cambio():
    n = norm(crudo(costo_unitario=D(10), moneda="USD"), monedas={"USD": D("18.5")})
    assert n.costo_mxn == D("185.00")
    assert norm(crudo(costo_unitario=D(10), moneda="EUR"), monedas={"USD": D(18)}).costo_mxn is None
    assert norm(crudo(costo_unitario=D(10), moneda="USD"), monedas={"USD": None}).costo_mxn is None


def test_costo_fraccion_cuando_falta():
    rg = reglas(costo_si_falta="fraccion_precio", fraccion=D("0.5"))
    assert norm(crudo(precio=D(3000)), rg).costo_mxn == D("1500.00")


def test_costo_none_y_regla_preguntar():
    assert norm(crudo(precio=D(3000))).costo_mxn is None


def test_material_aparte_separa_grupo():
    a = norm(crudo(material="Algodón", precio=D(100)))
    b = norm(crudo(material="Pana", precio=D(100)))
    c = norm(crudo(material=None, precio=D(100)))
    assert a.llave_grupo == c.llave_grupo
    assert a.llave_grupo != b.llave_grupo
    assert len(agrupar([a, b, c])) == 2


def test_mismo_tipo_precio_distinto_misma_talla_da_sufijos():
    rs = [norm(crudo(talla="M", precio=D(100))), norm(crudo(talla="M", precio=D(120)))]
    g = agrupar(rs)
    assert [x.sufijo for x in g] == ["", "-2"]
    assert g[1].renglones == [1]


def test_precio_distinto_tallas_distintas_un_grupo():
    rs = [norm(crudo(talla="M", precio=D(100))), norm(crudo(talla="G", precio=D(120)))]
    g = agrupar(rs)
    assert len(g) == 1 and g[0].tallas == {"M": D("100.00"), "G": D("120.00")}


def test_sin_precio_no_copia_precio():
    rs = [norm(crudo(talla="M", precio=D(100))), norm(crudo(talla="G"))]
    g = agrupar(rs)
    assert "sin-precio" in rs[1].llave_grupo
    assert len(g) == 1 and g[0].tallas == {"M": D("100.00"), "G": None}


def test_prefijo_de_marca_mas_comun():
    assert prefijo_de_marca(["MU-PLAY", "MU-CAMI-M", "X1"]) == "MU"
    assert prefijo_de_marca(["X1"]) is None


def test_sku_principal_y_tallas():
    rg = reglas()
    rs = [norm(crudo(talla="M")), norm(crudo(talla="Ch"))]
    g = agrupar(rs)[0]
    assert sku_para(g, "Ch", rg, "MU") == "MU-CAMI"
    assert sku_para(g, "M", rg, "MU") == "MU-CAMI-M"
    # sin ninguna talla de la escala: la primera en orden de entrada
    g2 = agrupar([norm(crudo(talla="7")), norm(crudo(talla="8"))])[0]
    assert sku_para(g2, "7", rg, "MU") == "MU-CAMI"
    assert sku_para(g2, "8", rg, "MU") == "MU-CAMI-8"


def test_sku_material_sufijo_y_sin_talla():
    rg = reglas()
    g = agrupar([norm(crudo(material="Pana", precio=D(1))), norm(crudo(material="Pana", precio=D(2)))])
    assert sku_para(g[1], None, rg, "MU") == "MU-CAMI-PAN-2"
    assert sku_para(g[0], None, rg, "MU") == "MU-CAMI-PAN"


def test_tipo_desconocido_cae_en_sku_sugerido():
    g = agrupar([norm(crudo(tipo="Bufanda", talla="M"))])[0]
    s = sku_para(g, "M", reglas(), "MU")
    assert s == "MU-BUFA"
