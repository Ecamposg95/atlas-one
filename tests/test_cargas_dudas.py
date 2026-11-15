"""Dudas por regla: qué se le pregunta al dueño antes de escribir nada."""
from decimal import Decimal

import pytest

from app.modules.cargas.dudas import (
    TIPOS_DUDA, DudaNueva, generar_dudas, levenshtein, opcion_a_operaciones,
)
from app.modules.cargas.models import CargaDuda, CargaMercancia, CargaRenglon
from app.modules.cargas.normalizar import agrupar, normalizar_renglon
from app.modules.cargas.reglas import RangoPrecio, ReglasCarga, TipoPrenda
from app.modules.cargas.tipos import RenglonCrudo
from app.modules.cargas.cruce import Coincidencia
from app.modules.products.models import Brand, Department, Product, ProductVariant

REGLAS = ReglasCarga(
    costo_si_falta="fraccion_precio",
    escala_ropa=["Ch", "M", "G"],
    tipos={"Playera": TipoPrenda(codigo_sku="PLAY", departamento="Playeras")},
    genero_por_omision="UNISEX",
)


def _crudo(**kw):
    base = dict(descripcion_original="Playera Marca Uno", marca="Marca Uno", tipo="Playera",
                talla="M", cantidad=Decimal("2"), precio=Decimal("100"), origen="Hoja1!R2")
    base.update(kw)
    return RenglonCrudo(**base)


def _plan(crudos, reglas=REGLAS, monedas=None, clases=None):
    """Renglones del plan (CargaRenglon con `normalizado`) y sus grupos."""
    cambio = {k: (None if v is None else Decimal(str(v))) for k, v in (monedas or {}).items()}
    norm = [normalizar_renglon(c, reglas, cambio) for c in crudos]
    filas = []
    for i, n in enumerate(norm):
        filas.append(CargaRenglon(orden=i + 1, normalizado=n.model_dump(mode="json"),
                                  clase=(clases or {}).get(i, "NUEVO"), cantidad=n.cantidad))
    return filas, agrupar(norm)


def _carga(proposito="entrada", lectura=None, monedas=None):
    return CargaMercancia(folio=1, proposito=proposito, lectura=lectura, monedas=monedas)


def _marca(db, org, nombre="Marca Uno"):
    b = Brand(name=nombre, organization_id=org.id)
    db.add(b)
    db.flush()
    return b


def _dudas(db, org, crudos, *, reglas=REGLAS, carga=None, coincidencias=None, clases=None):
    carga = carga or _carga()
    filas, grupos = _plan(crudos, reglas, carga.monedas, clases)
    return generar_dudas(db, org.id, carga, filas, grupos,
                         coincidencias or {g.llave: None for g in grupos}, reglas)


def _guardada(d: DudaNueva) -> CargaDuda:
    return CargaDuda(numero=1, tipo=d.tipo, texto=d.texto, opciones=d.opciones,
                     recomendada=d.recomendada, renglones=d.renglones, clave=d.clave,
                     contexto=d.contexto)


def _claves(d):
    return [o["clave"] for o in d.opciones]


def test_levenshtein():
    assert levenshtein("casa dos", "casa do") == 1
    assert levenshtein("", "abc") == 3
    assert levenshtein("gato", "gato") == 0
    assert levenshtein("kitten", "sitting") == 3


def test_sin_dudas_cuando_todo_cuadra(db, org):
    _marca(db, org)
    db.add(Department(name="Playeras", organization_id=org.id))
    db.flush()
    assert _dudas(db, org, [_crudo(), _crudo(talla="G")]) == []


def test_columnas_dinero_recomendacion_por_proposito(db, org):
    _marca(db, org)
    lectura = {"tablas": [{
        "pestana": "Hoja1", "encabezados": ["Modelo", "Talla", "Importe", "Público"],
        "mapa": {"campos": {}, "columnas_dinero": [2, 3], "texto_libre": []},
        "rol_dinero": {"3": "precio"},
    }]}
    for proposito, recomendada in (("entrada", "costo"), ("migracion", "precio")):
        dudas = [d for d in _dudas(db, org, [_crudo()], carga=_carga(proposito, lectura))
                 if d.tipo == "columnas_dinero"]
        assert len(dudas) == 1  # la columna 3 ya tiene papel
        d = dudas[0]
        assert _claves(d) == ["costo", "precio", "ignorar"]
        assert d.recomendada == recomendada
        assert d.clave == "columnas_dinero|0|2"
        assert d.contexto == {"tabla": 0, "columna": 2, "encabezado": "Importe"}
        assert '"Importe"' in d.texto and '"Hoja1"' in d.texto
    assert opcion_a_operaciones(_guardada(d), "costo", None) == [
        {"op": "rol_columna", "tabla": 0, "columna": 2, "rol": "costo"}]


def test_columnas_dinero_pendientes_callan_precio_y_costo(db, org):
    _marca(db, org)
    lectura = {"tablas": [{"pestana": "H", "encabezados": ["A", "B"],
                           "mapa": {"campos": {}, "columnas_dinero": [1], "texto_libre": []},
                           "rol_dinero": {}}]}
    reglas = REGLAS.model_copy(update={"costo_si_falta": "preguntar"})
    tipos = [d.tipo for d in _dudas(db, org, [_crudo(precio=None)], reglas=reglas,
                                    carga=_carga(lectura=lectura))]
    assert "precio_faltante" not in tipos and "sin_costo" not in tipos
    assert "columnas_dinero" in tipos


def test_tipo_cambio(db, org):
    _marca(db, org)
    carga = _carga(monedas={"USD": None})
    dudas = _dudas(db, org, [_crudo(costo_unitario=Decimal("5"), moneda="USD")], carga=carga)
    d = next(d for d in dudas if d.tipo == "tipo_cambio")
    assert d.opciones == [] and d.recomendada is None
    assert d.clave == "tipo_cambio|USD" and d.contexto == {"moneda": "USD"}
    assert d.renglones == [1]
    assert "USD" in d.texto
    assert opcion_a_operaciones(_guardada(d), "", "18,40") == [
        {"op": "tipo_cambio", "moneda": "USD", "valor": "18.40"}]
    # Con el tipo de cambio ya puesto, la duda desaparece sola.
    assert not [d for d in _dudas(db, org, [_crudo(costo_unitario=Decimal("5"), moneda="USD")],
                                  carga=_carga(monedas={"USD": 18.4}))
                if d.tipo == "tipo_cambio"]


def test_marca_nueva(db, org):
    _marca(db, org, "Otra Cosa")
    dudas = _dudas(db, org, [_crudo(marca="Casa Tres")])
    d = next(d for d in dudas if d.tipo == "marca_nueva")
    assert _claves(d) == ["crear"] and d.recomendada == "crear"
    assert d.clave == "marca_nueva|casa tres" and d.contexto == {"marca": "Casa Tres"}
    assert "Casa Tres" in d.texto
    assert opcion_a_operaciones(_guardada(d), "crear", None) == []
    assert opcion_a_operaciones(_guardada(d), "", "Casa Treinta") == [
        {"op": "fijar_campo", "renglones": [1], "campo": "marca", "valor": "Casa Treinta"}]


def test_marca_parecida_recomienda_existente(db, org):
    existente = _marca(db, org, "Casa Dos")
    _marca(db, org, "Marca Uno")
    dudas = _dudas(db, org, [_crudo(marca="Casa Do"), _crudo(marca="Casa Do", talla="G")])
    d = next(d for d in dudas if d.tipo == "marca_parecida")
    assert _claves(d) == [f"usar:{existente.id}", "crear"]
    assert d.recomendada == f"usar:{existente.id}"
    assert d.contexto == {"marca": "Casa Do"}
    assert '"Casa Do"' in d.texto and '"Casa Dos"' in d.texto
    assert not [x for x in dudas if x.tipo == "marca_nueva"]
    assert opcion_a_operaciones(_guardada(d), f"usar:{existente.id}", None) == [
        {"op": "fijar_campo", "renglones": [1, 2], "campo": "marca", "valor": "Casa Dos"}]


def test_marca_parecida_por_prefijo(db, org):
    b = _marca(db, org, "Bordados Finos")
    d = next(d for d in _dudas(db, org, [_crudo(marca="Bordados del Sur")])
             if d.tipo == "marca_parecida")
    assert d.recomendada == f"usar:{b.id}"


def test_casi_igual(db, org):
    b = _marca(db, org)
    d1 = Department(name="Básicos", organization_id=org.id)
    db.add(d1)
    db.flush()
    p = Product(name="Playera lisa", organization_id=org.id, brand_id=b.id,
                department_id=d1.id, material="Algodón")
    db.add(p)
    db.flush()
    reglas = REGLAS.model_copy(update={"material_normal": "Algodón"})
    dudas = _dudas(db, org, [_crudo(material="Algodón")], reglas=reglas)
    d = next(d for d in dudas if d.tipo == "casi_igual")
    assert _claves(d) == [f"usar:{p.id}", "nuevo"]
    assert d.recomendada == f"usar:{p.id}"
    assert "Playera lisa" in d.texto
    g = d.contexto["grupo"]
    assert d.clave == f"casi_igual|{g}"
    assert opcion_a_operaciones(_guardada(d), f"usar:{p.id}", None) == [
        {"op": "usar_existente", "grupo": g, "product_id": p.id}]
    assert opcion_a_operaciones(_guardada(d), "nuevo", None) == [
        {"op": "nuevo_producto", "grupo": g}]


def test_casi_igual_con_material_aparte_recomienda_nuevo(db, org):
    b = _marca(db, org)
    p = Product(name="Playera lisa", organization_id=org.id, brand_id=b.id, material="Algodón")
    db.add(p)
    db.flush()
    reglas = REGLAS.model_copy(update={"material_normal": "Algodón", "materiales_aparte": ["Lino"]})
    d = next(d for d in _dudas(db, org, [_crudo(material="Lino")], reglas=reglas)
             if d.tipo == "casi_igual")
    assert d.recomendada == "nuevo"


def test_precio_faltante_y_nunca_se_copia_de_otro_renglon(db, org):
    _marca(db, org)
    filas, grupos = _plan([_crudo(talla="M"), _crudo(talla="G", precio=None)])
    assert len(grupos) == 1  # mismo producto, una talla sin precio
    dudas = generar_dudas(db, org.id, _carga(), filas, grupos, {grupos[0].llave: None}, REGLAS)
    d = next(d for d in dudas if d.tipo == "precio_faltante")
    assert d.opciones == [] and d.renglones == [2]
    assert "talla G" in d.texto and "Marca Uno" in d.texto and "Playera" in d.texto
    assert d.clave == f"precio_faltante|{grupos[0].llave}"
    assert filas[1].normalizado["precio"] is None
    assert grupos[0].tallas["G"] is None
    assert opcion_a_operaciones(_guardada(d), "", "$350") == [
        {"op": "fijar_campo", "renglones": [2], "campo": "precio", "valor": "350"}]
    # Con el precio puesto, la duda se va sola.
    assert not [d for d in _dudas(db, org, [_crudo(talla="M"), _crudo(talla="G")])
                if d.tipo == "precio_faltante"]


def test_precio_fuera_familia(db, org):
    _marca(db, org)
    reglas = REGLAS.model_copy(update={"precios_familia": [
        RangoPrecio(tipo="Playera", precios=[Decimal("299"), Decimal("399")])]})
    d = next(d for d in _dudas(db, org, [_crudo(precio=Decimal("350"))], reglas=reglas)
             if d.tipo == "precio_fuera_familia")
    assert _claves(d) == ["mantener"] and d.recomendada == "mantener"
    assert "$350.00" in d.texto and "$299.00" in d.texto and "$399.00" in d.texto
    assert opcion_a_operaciones(_guardada(d), "mantener", None) == []
    assert opcion_a_operaciones(_guardada(d), "", "399") == [
        {"op": "fijar_campo", "renglones": [1], "campo": "precio", "valor": "399"}]
    assert not [x for x in _dudas(db, org, [_crudo(precio=Decimal("399"))], reglas=reglas)
                if x.tipo == "precio_fuera_familia"]


def test_precio_fuera_familia_prefiere_regla_de_la_marca(db, org):
    _marca(db, org)
    reglas = REGLAS.model_copy(update={"precios_familia": [
        RangoPrecio(tipo="Playera", precios=[Decimal("299")]),
        RangoPrecio(tipo="Playera", marca="Marca Uno", precios=[Decimal("350")]),
    ]})
    assert not [x for x in _dudas(db, org, [_crudo(precio=Decimal("350"))], reglas=reglas)
                if x.tipo == "precio_fuera_familia"]


def _existente(db, org, precio="100"):
    b = _marca(db, org)
    d = Department(name="Playeras", organization_id=org.id)
    db.add(d)
    db.flush()
    p = Product(name="Playera", organization_id=org.id, brand_id=b.id, department_id=d.id)
    db.add(p)
    db.flush()
    v = ProductVariant(product_id=p.id, sku="UNO-PLAY", size="M", organization_id=org.id,
                       price=Decimal(precio))
    db.add(v)
    db.flush()
    return p, v


def test_precio_distinto_existente(db, org):
    p, v = _existente(db, org)
    filas, grupos = _plan([_crudo(precio=Decimal("120"))])
    g = grupos[0]
    coinc = {g.llave: Coincidencia(product_id=p.id, variante_por_talla={"M": v.id},
                                   precio_actual=Decimal("100"), exacta=False)}
    dudas = generar_dudas(db, org.id, _carga(), filas, grupos, coinc, REGLAS)
    d = next(d for d in dudas if d.tipo == "precio_distinto_existente")
    assert _claves(d) == ["mantener", "actualizar", "aparte"]
    assert d.recomendada == "mantener"
    assert "$100.00" in d.texto and "$120.00" in d.texto
    assert d.contexto == {"grupo": g.llave}


def test_opcion_a_operaciones_actualizar_precio(db, org):
    p, v = _existente(db, org)
    filas, grupos = _plan([_crudo(precio=Decimal("120"))])
    g = grupos[0]
    coinc = {g.llave: Coincidencia(product_id=p.id, variante_por_talla={"M": v.id},
                                   precio_actual=Decimal("100"), exacta=False)}
    d = next(d for d in generar_dudas(db, org.id, _carga(), filas, grupos, coinc, REGLAS)
             if d.tipo == "precio_distinto_existente")
    assert opcion_a_operaciones(_guardada(d), "actualizar", None) == [
        {"op": "fijar_campo", "grupo": g.llave, "campo": "accion_precio", "valor": "actualizar"}]


def test_precio_igual_al_existente_no_pregunta(db, org):
    p, v = _existente(db, org)
    filas, grupos = _plan([_crudo()])
    g = grupos[0]
    coinc = {g.llave: Coincidencia(product_id=p.id, variante_por_talla={"M": v.id},
                                   precio_actual=Decimal("100"), exacta=True)}
    assert generar_dudas(db, org.id, _carga(), filas, grupos, coinc, REGLAS) == []


def test_departamento(db, org):
    _marca(db, org)
    d1 = Department(name="Sudaderas", organization_id=org.id)
    d2 = Department(name="Accesorios", organization_id=org.id)
    db.add_all([d1, d2])
    db.flush()
    crudos = [_crudo(tipo="Sudadera"), _crudo(tipo="Sudadera", marca="Marca Uno", talla="G")]
    for proposito in ("entrada", "migracion"):
        dudas = [d for d in _dudas(db, org, crudos, carga=_carga(proposito))
                 if d.tipo == "departamento"]
        assert len(dudas) == 1
        d = dudas[0]
        esperadas = sorted([f"depto:{d1.id}", f"depto:{d2.id}"],
                           key=lambda c: {f"depto:{d2.id}": 0, f"depto:{d1.id}": 1}[c])
        assert _claves(d) == esperadas + (["crear"] if proposito == "migracion" else [])
        assert d.recomendada == f"depto:{d1.id}"  # "Sudaderas" se parece a "Sudadera"
        assert '"Sudadera"' in d.texto
        assert d.renglones == [1, 2]
    assert opcion_a_operaciones(_guardada(d), f"depto:{d1.id}", None) == [
        {"op": "fijar_campo", "renglones": [1, 2], "campo": "departamento", "valor": "Sudaderas"}]
    assert opcion_a_operaciones(_guardada(d), "crear", None) == [
        {"op": "fijar_campo", "renglones": [1, 2], "campo": "departamento", "valor": "Sudadera"}]


def test_genero(db, org):
    _marca(db, org)
    db.add(Department(name="Playeras", organization_id=org.id))
    db.flush()
    reglas = REGLAS.model_copy(update={"genero_por_omision": None})
    d = next(d for d in _dudas(db, org, [_crudo()], reglas=reglas) if d.tipo == "genero")
    assert _claves(d) == ["HOMBRE", "MUJER", "UNISEX", "NINO"]
    assert [o["etiqueta"] for o in d.opciones] == ["Hombre", "Mujer", "Unisex", "Niño"]
    assert opcion_a_operaciones(_guardada(d), "MUJER", None) == [
        {"op": "fijar_campo", "renglones": [1], "campo": "genero", "valor": "MUJER"}]


def test_sin_costo_solo_si_se_pregunta(db, org):
    _marca(db, org)
    db.add(Department(name="Playeras", organization_id=org.id))
    db.flush()
    assert not [d for d in _dudas(db, org, [_crudo()]) if d.tipo == "sin_costo"]
    reglas = REGLAS.model_copy(update={"costo_si_falta": "preguntar"})
    d = next(d for d in _dudas(db, org, [_crudo()], reglas=reglas) if d.tipo == "sin_costo")
    assert d.opciones == [] and d.renglones == [1]
    assert opcion_a_operaciones(_guardada(d), "", "45.50") == [
        {"op": "fijar_campo", "renglones": [1], "campo": "costo", "valor": "45.50"}]


def test_extraccion(db, org):
    _marca(db, org)
    db.add(Department(name="Playeras", organization_id=org.id))
    db.flush()
    dudas = _dudas(db, org, [_crudo(), _crudo(talla="G", duda="no se lee la talla",
                                              origen="pág. 2")])
    d = next(d for d in dudas if d.tipo == "extraccion")
    assert _claves(d) == ["confirmar", "ignorar"] and d.recomendada == "confirmar"
    assert d.clave == "extraccion|2" and d.contexto == {"renglon": 2}
    assert "pág. 2" in d.texto and "no se lee la talla" in d.texto
    assert opcion_a_operaciones(_guardada(d), "ignorar", None) == [
        {"op": "ignorar", "renglones": [2]}]
    assert opcion_a_operaciones(_guardada(d), "confirmar", None) == []


def test_ya_cargado_e_ignorado_no_generan_dudas(db, org):
    dudas = _dudas(db, org, [_crudo(marca="Casa Tres", precio=None, duda="?"),
                             _crudo(marca="Casa Tres", talla="G", precio=None)],
                   clases={0: "YA_CARGADO", 1: "IGNORADO"})
    assert dudas == []


def test_orden_por_tipo(db, org):
    reglas = REGLAS.model_copy(update={"genero_por_omision": None})
    dudas = _dudas(db, org, [_crudo(marca="Casa Tres", precio=None, duda="?")], reglas=reglas)
    tipos = [d.tipo for d in dudas]
    assert tipos == sorted(tipos, key=TIPOS_DUDA.index)
    assert {"marca_nueva", "precio_faltante", "genero", "extraccion"} <= set(tipos)
    assert all(d.tipo in TIPOS_DUDA for d in dudas)


def test_opcion_desconocida_da_error(db, org):
    _marca(db, org)
    db.add(Department(name="Playeras", organization_id=org.id))
    db.flush()
    d = next(d for d in _dudas(db, org, [_crudo(duda="?")]) if d.tipo == "extraccion")
    with pytest.raises(ValueError):
        opcion_a_operaciones(_guardada(d), "otra", None)


@pytest.mark.parametrize("texto,esperado", [
    ("1.234,50", "1234.50"), ("1,234.50", "1234.50"), ("18,40", "18.40"),
    ("$2,500", "2500"), ("$350", "350"),
])
def test_montos_con_separadores(db, org, texto, esperado):
    _marca(db, org)
    d = next(d for d in _dudas(db, org, [_crudo(precio=None)]) if d.tipo == "precio_faltante")
    assert opcion_a_operaciones(_guardada(d), "", texto)[0]["valor"] == esperado


@pytest.mark.parametrize("texto", ["1e3", "Infinity", "NaN", "abc", "0", "-5"])
def test_montos_invalidos_se_rechazan(db, org, texto):
    _marca(db, org)
    d = next(d for d in _dudas(db, org, [_crudo(precio=None)]) if d.tipo == "precio_faltante")
    with pytest.raises(ValueError):
        opcion_a_operaciones(_guardada(d), "", texto)


def test_precio_distinto_con_existente_sin_precio_no_truena(db, org):
    p, v = _existente(db, org)
    v.price = None
    db.flush()
    filas, grupos = _plan([_crudo(precio=Decimal("120"))])
    g = grupos[0]
    coinc = {g.llave: Coincidencia.model_construct(
        product_id=p.id, variante_por_talla={"M": v.id}, precio_actual=None, exacta=False)}
    d = next(d for d in generar_dudas(db, org.id, _carga(), filas, grupos, coinc, REGLAS)
             if d.tipo == "precio_distinto_existente")
    assert "sin precio" in d.texto and "$120.00" in d.texto


def test_sin_tipo_pregunta_la_prenda_antes_que_el_departamento(db, org):
    _marca(db, org)
    db.add(Department(name="Varios", organization_id=org.id))
    db.flush()
    dudas = _dudas(db, org, [_crudo(tipo=None)], carga=_carga("migracion"))
    assert "departamento" not in [d.tipo for d in dudas]
    assert "sin_tipo" in [d.tipo for d in dudas]


def test_departamento_de_las_reglas_que_no_existe(db, org):
    """`reglas.tipos` dice "Playeras", pero la org no tiene ese departamento."""
    _marca(db, org)
    otro = Department(name="Accesorios", organization_id=org.id)
    db.add(otro)
    db.flush()
    for proposito in ("entrada", "migracion"):
        [d] = [d for d in _dudas(db, org, [_crudo(), _crudo(talla="G")], carga=_carga(proposito))
               if d.tipo == "departamento"]
        assert d.clave == "departamento|playera" and d.renglones == [1, 2]
        assert '"Playeras"' in d.texto
        if proposito == "entrada":
            assert _claves(d) == [f"depto:{otro.id}"] and d.recomendada is None
        else:
            assert _claves(d) == [f"depto:{otro.id}", "crear"] and d.recomendada == "crear"
            assert opcion_a_operaciones(_guardada(d), "crear", None) == [
                {"op": "fijar_campo", "renglones": [1, 2], "campo": "departamento",
                 "valor": "Playeras"}]


def test_entrada_en_tienda_sin_departamentos_dice_que_cree_uno(db, org):
    _marca(db, org)
    crudos = [_crudo(tipo="Sudadera"), _crudo(tipo="Gorra")]
    [d] = [d for d in _dudas(db, org, crudos) if d.tipo == "departamento"]
    assert d.texto == ("Esta tienda no tiene departamentos. Crea uno en Catálogo y vuelve a "
                       "esta carga.")
    assert d.opciones == [] and d.recomendada is None and d.renglones == [1, 2]
    # En migración sí se puede crear desde la carga.
    dudas = [d for d in _dudas(db, org, crudos, carga=_carga("migracion")) if d.tipo == "departamento"]
    assert len(dudas) == 2 and all(_claves(x) == ["crear"] for x in dudas)
