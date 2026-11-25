"""Endpoints /api/cargas y la lectura en segundo plano (en línea en las pruebas)."""
import io
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from openpyxl import Workbook
from pypdf import PdfWriter

from app.models.modules import Module, OrganizationModule
from app.models.organization import Organization
from app.modules.ai.proveedores import ProveedorFalso, ProveedorNoDisponible
from app.modules.ai.uso import registrar_uso
from app.modules.cargas.models import CargaArchivo, CargaMercancia, CargaRenglon
from app.modules.cargas.proceso import recuperar_cargas_colgadas
from app.modules.cargas.router import obtener_proveedor
from tests.conftest import _auth_header, _make_user
from app.models.users import Role
from app.modules.products.models import Department


# ── utilidades ────────────────────────────────────────────────────────────

def _pdf(paginas: int = 1) -> bytes:
    w = PdfWriter()
    for _ in range(paginas):
        w.add_blank_page(width=200, height=200)
    b = io.BytesIO()
    w.write(b)
    return b.getvalue()


def _xlsx(filas) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Hoja1"
    for f in filas:
        ws.append(f)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def _r(desc="Playera Marca Uno", cantidad="3", **kw):
    base = {"descripcion_original": desc, "marca": "Marca Uno", "tipo": "Playera", "material": None,
            "color": None, "talla": "M", "cantidad": cantidad, "costo_unitario": None,
            "precio": None, "moneda": None, "observacion": None, "duda": None, "pagina": 1}
    base.update(kw)
    return base


def _resp_pdf(renglones, monedas=()):
    return {"renglones": list(renglones), "monedas": list(monedas), "continua_en_siguiente": False}


def _habilitar_ai(db, org):
    if not db.query(Module).filter_by(key="ai").first():
        db.add(Module(key="ai", name="Asistente IA"))
        db.flush()
    db.add(OrganizationModule(organization_id=org.id, module_key="ai", is_enabled=True))
    db.flush()


@pytest.fixture()
def falso(app, monkeypatch):
    monkeypatch.setenv("CARGAS_PROCESO_EN_LINEA", "1")
    cliente = ProveedorFalso()
    app.dependency_overrides[obtener_proveedor] = lambda: cliente
    yield cliente
    app.dependency_overrides.pop(obtener_proveedor, None)


@pytest.fixture()
def tienda(db, org, branch_a):
    _habilitar_ai(db, org)
    org.reglas_carga = {
        "costo_si_falta": "fraccion_precio", "fraccion": "0.5",
        "escala_ropa": ["Ch", "M", "G"],
        "tipos": {"Playera": {"codigo_sku": "PLAY", "departamento": "Playeras"}},
        "genero_por_omision": "UNISEX", "sucursal_recibe": branch_a.id,
    }
    org.ai_instrucciones = "Tienda de ropa de prueba"
    db.add(Department(name="Playeras", organization_id=org.id))
    db.flush()
    return org


def _subir(client, headers, nombre, contenido, proposito="entrada", **extra):
    data = {"proposito": proposito, **extra}
    return client.post("/api/cargas", headers=headers, data=data,
                       files={"archivo": (nombre, contenido, "application/octet-stream")})


def _detalle(client, headers, carga_id):
    r = client.get(f"/api/cargas/{carga_id}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _abiertas(det):
    return [d for d in det["dudas"] if d["estado"] == "abierta"]


# ── flujo PDF ─────────────────────────────────────────────────────────────

def test_flujo_completo_pdf(client, db, tienda, auth_admin_a, falso):
    falso.guion = [_resp_pdf([_r(), _r(talla="G", cantidad="2")])]
    r = _subir(client, auth_admin_a, "factura.pdf", _pdf())
    assert r.status_code == 202, r.text
    alta = r.json()
    assert alta["folio"] == 1 and alta["estado"] == "plan"
    # El original queda guardado en la base, con su huella.
    carga = db.get(CargaMercancia, alta["id"])
    assert carga.archivo_tipo == "pdf" and len(carga.archivo_sha256) == 64
    assert db.query(CargaArchivo).filter_by(carga_id=carga.id).one().contenido[:4] == b"%PDF"
    # Las instrucciones de la tienda llegan al modelo.
    assert "Tienda de ropa de prueba" in falso.llamadas[0]["sistema"]

    det = _detalle(client, auth_admin_a, alta["id"])
    assert det["carga"]["piezas"] == "5"
    assert det["contadores"]["NUEVO"] == 2 and det["contadores"]["piezas"] == "5"
    assert det["puede_autorizar"] is False
    grupo = det["grupos"][0]
    assert grupo["titulo"] == "Marca Uno · Playera"
    assert [x["orden"] for x in grupo["renglones"]] == [1, 2]
    assert grupo["renglones"][0]["cantidad"] == "3" and grupo["renglones"][0]["origen"] == "pág. 1"
    assert grupo["renglones"][0]["descripcion"] == "Playera Marca Uno"
    precio = next(d for d in _abiertas(det) if d["tipo"] == "precio_faltante")
    assert precio["acepta_texto"] is True

    # Respuesta escrita: el modelo la traduce y un punto no lo entiende.
    falso.guion = [{"operaciones": [{"op": "resolver_duda", "numero": precio["numero"],
                                     "opcion": "", "valor": "350"}],
                    "no_entendido": [{"numero": None, "texto": "lo demás"}]}]
    r = client.post(f"/api/cargas/{alta['id']}/respuestas", headers=auth_admin_a,
                    json={"texto": "a 350 y lo demás"})
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["rechazos"] == ["No entendí: lo demás"]
    assert cuerpo["cambio"]["puede_deshacer"] is True
    assert precio["numero"] in cuerpo["cambio"]["resumen"]["dudas_resueltas"]
    assert cuerpo["cambio"]["resumen"]["grupos"][0]["titulo"] == "Marca Uno · Playera"

    # El resto, con botones (la recomendada).
    for _ in range(10):
        abiertas = _abiertas(_detalle(client, auth_admin_a, alta["id"]))
        if not abiertas:
            break
        d = abiertas[0]
        assert d["recomendada"], d
        r = client.post(f"/api/cargas/{alta['id']}/dudas/{d['numero']}", headers=auth_admin_a,
                        json={"opcion": d["recomendada"]})
        assert r.status_code == 200 and r.json()["rechazos"] == [], r.text
    det = _detalle(client, auth_admin_a, alta["id"])
    assert det["puede_autorizar"] is True
    assert det["grupos"][0]["renglones"][0]["precio"] == "350.00"

    r = client.post(f"/api/cargas/{alta['id']}/autorizar", headers=auth_admin_a)
    assert r.status_code == 200, r.text
    resumen = r.json()
    assert resumen["piezas"] == "5" and resumen["productos_nuevos"] == 1
    assert {(e["talla"], e["piezas"], e["precio"]) for e in resumen["etiquetas"]} == {
        ("M", "3", "350.00"), ("G", "2", "350.00")}

    r = client.get(f"/api/cargas/{alta['id']}/etiquetas", headers=auth_admin_a)
    assert r.status_code == 200
    assert r.json() == resumen["etiquetas"]
    det = _detalle(client, auth_admin_a, alta["id"])
    assert det["carga"]["estado"] == "aplicada" and det["puede_autorizar"] is False
    assert all(c["puede_deshacer"] is False for c in det["cambios"])

    lista = client.get("/api/cargas", headers=auth_admin_a).json()
    assert [(c["folio"], c["estado"], c["archivo_tipo"]) for c in lista] == [(1, "aplicada", "pdf")]


def test_respuesta_escrita_a_duda_con_opcion_vacia(client, db, tienda, auth_admin_a, falso):
    falso.guion = [_resp_pdf([_r()])]
    alta = _subir(client, auth_admin_a, "f.pdf", _pdf()).json()
    precio = next(d for d in _abiertas(_detalle(client, auth_admin_a, alta["id"]))
                  if d["tipo"] == "precio_faltante")
    r = client.post(f"/api/cargas/{alta['id']}/dudas/{precio['numero']}", headers=auth_admin_a,
                    json={"opcion": "", "valor": "$1,250.50"})
    assert r.status_code == 200, r.text
    assert r.json()["rechazos"] == [] and r.json()["cambio"] is not None
    det = _detalle(client, auth_admin_a, alta["id"])
    assert det["grupos"][0]["renglones"][0]["precio"] == "1250.50"
    # Una clave que no es de la duda se rechaza con un mensaje legible.
    otra = _abiertas(det)[0]
    r = client.post(f"/api/cargas/{alta['id']}/dudas/{otra['numero']}", headers=auth_admin_a,
                    json={"opcion": "texto", "valor": "x"})
    assert r.json()["cambio"] is None
    assert r.json()["rechazos"][0].startswith("Pregunta")


def test_deshacer_devuelve_el_detalle(client, db, tienda, auth_admin_a, falso):
    falso.guion = [_resp_pdf([_r()])]
    alta = _subir(client, auth_admin_a, "f.pdf", _pdf()).json()
    precio = next(d for d in _abiertas(_detalle(client, auth_admin_a, alta["id"]))
                  if d["tipo"] == "precio_faltante")
    cambio = client.post(f"/api/cargas/{alta['id']}/dudas/{precio['numero']}", headers=auth_admin_a,
                         json={"opcion": "", "valor": "300"}).json()["cambio"]
    r = client.post(f"/api/cargas/{alta['id']}/cambios/{cambio['id']}/deshacer", headers=auth_admin_a)
    assert r.status_code == 200, r.text
    det = r.json()
    assert det["grupos"][0]["renglones"][0]["precio"] is None
    assert det["cambios"][0]["deshecho"] is True and det["cambios"][0]["puede_deshacer"] is False
    # La llave del grupo del cambio (con el precio 300) ya no existe: el título sigue siendo humano.
    assert det["cambios"][0]["resumen"]["grupos"][0]["titulo"] == "Marca Uno · Playera"
    assert not any("|" in g["titulo"] for g in det["grupos"])
    assert not any("|" in g["titulo"] for c in det["cambios"] for g in c["resumen"]["grupos"])
    assert "|" not in cambio["resumen"]["grupos"][0]["titulo"]
    assert any(d["numero"] == precio["numero"] and d["estado"] == "abierta" for d in det["dudas"])


# ── flujo Excel ───────────────────────────────────────────────────────────

def _mapa(dinero=(3, 4)):
    return {"campos": {"descripcion_original": 0, "marca": 1, "tipo": 0, "material": None,
                       "color": None, "talla": 2, "cantidad": 5, "observacion": None},
            "columnas_dinero": list(dinero), "texto_libre": []}


_FILAS = [["Descripción", "Marca", "Talla", "Costo", "Precio", "Piezas"],
          ["Playera", "Marca Uno", "M", 150, 350, 3],
          ["Playera", "Marca Uno", "G", 150, 350, 2]]


def test_flujo_excel_pide_columnas_dinero_primero(client, db, tienda, auth_admin_a, falso):
    falso.guion = [_mapa()]
    r = _subir(client, auth_admin_a, "lista.xlsx", _xlsx(_FILAS))
    assert r.status_code == 202, r.text
    carga_id = r.json()["id"]
    carga = db.get(CargaMercancia, carga_id)
    tabla = carga.lectura["tablas"][0]
    assert tabla["pestana"] == "Hoja1" and tabla["rol_dinero"] == {}
    assert "filas" not in tabla  # las celdas se quedan en el archivo guardado

    det = _detalle(client, auth_admin_a, carga_id)
    assert det["grupos"] == []
    assert [d["tipo"] for d in _abiertas(det)] == ["columnas_dinero", "columnas_dinero"]

    primera, segunda = _abiertas(det)
    r = client.post(f"/api/cargas/{carga_id}/dudas/{primera['numero']}", headers=auth_admin_a,
                    json={"opcion": "costo"})
    assert r.status_code == 200 and r.json()["rechazos"] == []
    assert db.query(CargaRenglon).filter_by(carga_id=carga_id).count() == 0  # falta un rol

    r = client.post(f"/api/cargas/{carga_id}/dudas/{segunda['numero']}", headers=auth_admin_a,
                    json={"opcion": "precio"})
    assert r.status_code == 200, r.text
    cambio = r.json()["cambio"]
    det = _detalle(client, auth_admin_a, carga_id)
    renglones = det["grupos"][0]["renglones"]
    assert [(x["talla"], x["cantidad"], x["precio"], x["costo"]) for x in renglones] == [
        ("M", "3", "350.00", "150.00"), ("G", "2", "350.00", "150.00")]
    assert renglones[0]["origen"] == "Hoja1!R2"

    # Deshacer quita los renglones y vuelve a abrir la pregunta.
    r = client.post(f"/api/cargas/{carga_id}/cambios/{cambio['id']}/deshacer", headers=auth_admin_a)
    assert r.status_code == 200, r.text
    assert r.json()["grupos"] == []
    assert [d["numero"] for d in _abiertas(r.json())] == [segunda["numero"]]
    assert db.query(CargaRenglon).filter_by(carga_id=carga_id).count() == 0

    # Otro rol vuelve a armarlos de forma consistente.
    client.post(f"/api/cargas/{carga_id}/dudas/{segunda['numero']}", headers=auth_admin_a,
                json={"opcion": "ignorar"})
    det = _detalle(client, auth_admin_a, carga_id)
    assert [x["precio"] for x in det["grupos"][0]["renglones"]] == [None, None]


def test_excel_sin_columnas_de_dinero_arma_renglones_de_una(client, db, tienda, auth_admin_a, falso):
    falso.guion = [_mapa(dinero=())]
    r = _subir(client, auth_admin_a, "lista.csv",
               b"Descripcion,Marca,Talla,x,y,Piezas\nPlayera,Marca Uno,M,,,4\n")
    assert r.status_code == 202, r.text
    det = _detalle(client, auth_admin_a, r.json()["id"])
    assert det["carga"]["archivo_tipo"] == "csv"
    assert det["contadores"]["piezas"] == "4"


def test_excel_de_mas_de_2000_renglones_queda_en_error(client, db, tienda, auth_admin_a, falso):
    filas = [_FILAS[0]] + [["Playera", "Marca Uno", "M", 1, 2, 1]] * 2001
    r = _subir(client, auth_admin_a, "grande.xlsx", _xlsx(filas))
    assert r.status_code == 202
    det = _detalle(client, auth_admin_a, r.json()["id"])
    assert det["carga"]["estado"] == "error"
    assert "2,000" in det["carga"]["error"]
    assert falso.llamadas == []  # no se gastaron tokens


# ── validaciones de la subida ─────────────────────────────────────────────

def test_archivo_grande_413(client, tienda, auth_admin_a, falso):
    contenido = b"%PDF" + b"0" * (20 * 1024 * 1024)
    r = _subir(client, auth_admin_a, "enorme.pdf", contenido)
    assert r.status_code == 413
    assert "20 MB" in r.json()["detail"]


@pytest.mark.parametrize("nombre,contenido", [
    ("foto.jpg", b"\xff\xd8\xff\xe0imagen"),
    ("falso.pdf", b"no soy un pdf"),          # extensión sin el contenido
    ("falso.xlsx", b"texto plano"),
    ("binario.csv", b"a,b\x00\x01\x02"),
])
def test_tipo_no_soportado_415(client, tienda, auth_admin_a, falso, nombre, contenido):
    r = _subir(client, auth_admin_a, nombre, contenido)
    assert r.status_code == 415
    assert "PDF" in r.json()["detail"]


def test_cajero_403(client, tienda, auth_cajero_a, falso):
    r = _subir(client, auth_cajero_a, "f.pdf", _pdf())
    assert r.status_code == 403
    assert client.get("/api/cargas", headers=auth_cajero_a).status_code == 403


def test_gerente_usa_pero_no_autoriza(client, tienda, auth_gerente_a, falso):
    falso.guion = [_resp_pdf([_r(precio="350")])]
    alta = _subir(client, auth_gerente_a, "f.pdf", _pdf()).json()
    assert _detalle(client, auth_gerente_a, alta["id"])["puede_autorizar"] is False
    r = client.post(f"/api/cargas/{alta['id']}/autorizar", headers=auth_gerente_a)
    assert r.status_code == 403


def test_org_sin_modulo_ai_403(client, org, auth_admin_a, falso):
    r = _subir(client, auth_admin_a, "f.pdf", _pdf())
    assert r.status_code == 403
    assert client.get("/api/cargas", headers=auth_admin_a).status_code == 403


def test_carga_de_otra_org_404(client, db, tienda, auth_admin_a, falso):
    otra = Organization(name="Otra Org", status="ACTIVE")
    db.add(otra)
    db.flush()
    _habilitar_ai(db, otra)
    ajena = CargaMercancia(organization_id=otra.id, folio=1, estado="plan", proposito="entrada",
                           archivo_nombre="x.pdf", archivo_tipo="pdf")
    db.add(ajena)
    db.flush()
    base = f"/api/cargas/{ajena.id}"
    assert client.get(base, headers=auth_admin_a).status_code == 404
    assert client.get(f"{base}/etiquetas", headers=auth_admin_a).status_code == 404
    for ruta, cuerpo in [("/respuestas", {"texto": "hola"}), ("/dudas/1", {"opcion": "x"}),
                         ("/autorizar", None), ("/descartar", None), ("/reintentar", None),
                         ("/cambios/abc/deshacer", None)]:
        assert client.post(base + ruta, headers=auth_admin_a, json=cuerpo).status_code == 404, ruta
    assert client.get("/api/cargas", headers=auth_admin_a).json() == []
    db.refresh(ajena)
    assert ajena.estado == "plan"


# ── fallas, reintento y recuperación ──────────────────────────────────────

def test_proveedor_caido_deja_error_y_reintentar_funciona(client, db, tienda, auth_admin_a, falso):
    falso.guion = [ProveedorNoDisponible("No se pudo contactar al proveedor de IA. Intenta de nuevo.")]
    alta = _subir(client, auth_admin_a, "f.pdf", _pdf()).json()
    assert alta["estado"] == "error"
    det = _detalle(client, auth_admin_a, alta["id"])
    assert det["carga"]["error"] == "No se pudo contactar al proveedor de IA. Intenta de nuevo."
    assert det["grupos"] == []

    falso.guion = [_resp_pdf([_r()])]
    r = client.post(f"/api/cargas/{alta['id']}/reintentar", headers=auth_admin_a)
    assert r.status_code == 200, r.text
    assert r.json() == {"id": alta["id"], "folio": alta["folio"], "estado": "plan"}
    assert _detalle(client, auth_admin_a, alta["id"])["contadores"]["NUEVO"] == 1
    # Fuera de `error` no se reintenta.
    assert client.post(f"/api/cargas/{alta['id']}/reintentar", headers=auth_admin_a).status_code == 409


def test_falla_inesperada_no_muestra_traceback(client, db, tienda, auth_admin_a, falso):
    falso.guion = [RuntimeError("Traceback: KeyError 'x' en algo interno")]
    alta = _subir(client, auth_admin_a, "f.pdf", _pdf()).json()
    error = _detalle(client, auth_admin_a, alta["id"])["carga"]["error"]
    assert "Traceback" not in error and "KeyError" not in error
    assert error.startswith("No se pudo leer el archivo")


def test_cupo_agotado_deja_error(client, db, tienda, auth_admin_a, falso, monkeypatch):
    monkeypatch.setenv("AI_TOKENS_DIA_ORG", "100")
    registrar_uso(db, tienda.id, 60, 40)
    alta = _subir(client, auth_admin_a, "f.pdf", _pdf()).json()
    det = _detalle(client, auth_admin_a, alta["id"])
    assert det["carga"]["estado"] == "error"
    assert "límite diario" in det["carga"]["error"]


def test_reintentar_tras_falla_al_aplicar_vuelve_a_plan(client, db, tienda, auth_admin_a, falso):
    falso.guion = [_resp_pdf([_r(precio="350")])]
    alta = _subir(client, auth_admin_a, "f.pdf", _pdf()).json()
    carga = db.get(CargaMercancia, alta["id"])
    carga.estado, carga.error = "error", "No se aplicó nada"
    db.flush()
    r = client.post(f"/api/cargas/{alta['id']}/reintentar", headers=auth_admin_a)
    assert r.json()["estado"] == "plan"
    assert falso.guion == []  # no se volvió a leer


def test_descartar(client, db, tienda, auth_admin_a, falso):
    falso.guion = [_resp_pdf([_r()])]
    alta = _subir(client, auth_admin_a, "f.pdf", _pdf()).json()
    r = client.post(f"/api/cargas/{alta['id']}/descartar", headers=auth_admin_a)
    assert r.status_code == 200 and r.json()["estado"] == "descartada"
    assert client.post(f"/api/cargas/{alta['id']}/descartar", headers=auth_admin_a).status_code == 409
    assert client.get(f"/api/cargas/{alta['id']}/etiquetas", headers=auth_admin_a).status_code == 409


def _colgadas(db, org, minutos_atras):
    hace = datetime.now(timezone.utc) - timedelta(minutes=minutos_atras)
    leyendo = CargaMercancia(organization_id=org.id, folio=next(_folios), estado="leyendo",
                             proposito="entrada")
    aplicando = CargaMercancia(organization_id=org.id, folio=next(_folios), estado="aplicando",
                               proposito="entrada")
    db.add_all([leyendo, aplicando])
    db.flush()
    for c in (leyendo, aplicando):
        db.query(CargaMercancia).filter_by(id=c.id).update({"updated_at": hace})
    db.flush()
    db.expire_all()
    return leyendo, aplicando


_folios = iter(range(100, 10_000))
LEYENDO = "La lectura se interrumpió. Vuelve a intentar."
APLICANDO = "La aplicación se interrumpió y no se escribió nada. Vuelve a intentar."


def test_recuperar_colgadas_marca_error(db, org):
    colgada, aplicando = _colgadas(db, org, 15)
    reciente, _ = _colgadas(db, org, 1)
    assert recuperar_cargas_colgadas(db) == 2
    assert (colgada.estado, colgada.error) == ("error", LEYENDO)
    assert (aplicando.estado, aplicando.error) == ("error", APLICANDO)
    assert reciente.estado == "leyendo"


def test_al_arrancar_se_marcan_todas_aunque_sean_recientes(db, org):
    """Tras un despliegue ningún hilo sigue leyendo: minutos=0 marca también las recientes."""
    leyendo, aplicando = _colgadas(db, org, 0)
    assert recuperar_cargas_colgadas(db, minutos=0) == 2
    assert (leyendo.estado, leyendo.error) == ("error", LEYENDO)
    assert (aplicando.estado, aplicando.error) == ("error", APLICANDO)


def test_al_arrancar_main_llama_con_minutos_cero():
    import inspect
    import app.main as principal
    assert "recuperar_cargas_colgadas(db, minutos=0)" in inspect.getsource(principal.startup_event)


def test_consultas_recuperan_las_colgadas_de_su_org(client, db, tienda, auth_admin_a, falso):
    leyendo, aplicando = _colgadas(db, tienda, 15)
    reciente, _ = _colgadas(db, tienda, 1)
    otra = Organization(name="Otra Org", status="ACTIVE")
    db.add(otra)
    db.flush()
    ajena, _ = _colgadas(db, otra, 15)

    lista = {c["id"]: c for c in client.get("/api/cargas", headers=auth_admin_a).json()}
    assert (lista[leyendo.id]["estado"], lista[leyendo.id]["error"]) == ("error", LEYENDO)
    assert (lista[aplicando.id]["estado"], lista[aplicando.id]["error"]) == ("error", APLICANDO)
    assert lista[reciente.id]["estado"] == "leyendo"
    db.expire_all()
    assert ajena.estado == "leyendo"  # otra org: no se toca

    # El detalle también la destraba (y ya se puede reintentar).
    db.query(CargaMercancia).filter_by(id=reciente.id).update(
        {"updated_at": datetime.now(timezone.utc) - timedelta(minutes=11)})
    db.flush()
    det = _detalle(client, auth_admin_a, reciente.id)
    assert (det["carga"]["estado"], det["carga"]["error"]) == ("error", LEYENDO)


def test_folio_consecutivo_por_org(client, db, tienda, auth_admin_a, falso):
    falso.guion = [_resp_pdf([_r()]), _resp_pdf([_r()])]
    folios = [_subir(client, auth_admin_a, "f.pdf", _pdf()).json()["folio"] for _ in range(2)]
    assert folios == [1, 2]
    # Otra organización empieza en 1.
    otra = Organization(name="Otra Org", status="ACTIVE")
    db.add(otra)
    db.flush()
    _habilitar_ai(db, otra)
    jefa = _make_user(db, otra, None, "admin_otra", Role.ADMINISTRADOR)
    falso.guion = [_resp_pdf([_r()])]
    assert _subir(client, _auth_header(jefa), "f.pdf", _pdf()).json()["folio"] == 1
    lista = client.get("/api/cargas", headers=auth_admin_a).json()
    assert [c["folio"] for c in lista] == [2, 1]


# ── respuestas: el cupo se cuenta y no se gasta en balde ──────────────────

def test_respuesta_fuera_de_plan_no_llama_al_modelo(client, db, tienda, auth_admin_a, falso):
    falso.guion = [_resp_pdf([_r()])]
    alta = _subir(client, auth_admin_a, "f.pdf", _pdf()).json()
    client.post(f"/api/cargas/{alta['id']}/descartar", headers=auth_admin_a)
    llamadas = len(falso.llamadas)
    r = client.post(f"/api/cargas/{alta['id']}/respuestas", headers=auth_admin_a,
                    json={"texto": "a 350"})
    assert r.status_code == 409
    assert len(falso.llamadas) == llamadas


def test_uso_del_modelo_se_guarda_antes_de_aplicar(client, db, tienda, auth_admin_a, falso,
                                                    monkeypatch):
    from fastapi import HTTPException
    from sqlalchemy import event

    from app.modules.ai.models import AiUsoDiario
    from app.modules.cargas import router as modulo_router

    falso.guion = [_resp_pdf([_r()])]
    alta = _subir(client, auth_admin_a, "f.pdf", _pdf()).json()
    precio = next(d for d in _abiertas(_detalle(client, auth_admin_a, alta["id"]))
                  if d["tipo"] == "precio_faltante")
    commits = []
    event.listen(db, "after_commit", lambda s: commits.append(1))
    vistos = {}

    def aplicar_que_choca(*a, **kw):
        vistos["commits"] = len(commits)
        raise HTTPException(status_code=409, detail="otro envío ganó")

    monkeypatch.setattr(modulo_router, "aplicar_operaciones", aplicar_que_choca)
    falso.guion = [{"operaciones": [{"op": "resolver_duda", "numero": precio["numero"],
                                     "opcion": "", "valor": "350"}], "no_entendido": []}]
    r = client.post(f"/api/cargas/{alta['id']}/respuestas", headers=auth_admin_a,
                    json={"texto": "a 350"})
    assert r.status_code == 409
    assert vistos["commits"] >= 1  # el uso ya estaba confirmado cuando aplicar falló
    # Dos llamadas al modelo: la lectura del PDF y la respuesta escrita.
    assert db.query(AiUsoDiario).filter_by(organization_id=tienda.id).one().llamadas == 2


def test_respuesta_toda_rechazada_cuenta_el_uso(client, db, tienda, auth_admin_a, falso):
    from app.modules.ai.models import AiUsoDiario

    falso.guion = [_resp_pdf([_r()])]
    alta = _subir(client, auth_admin_a, "f.pdf", _pdf()).json()
    falso.guion = [{"operaciones": [], "no_entendido": [{"numero": None, "texto": "eso"}]}]
    r = client.post(f"/api/cargas/{alta['id']}/respuestas", headers=auth_admin_a,
                    json={"texto": "eso"})
    assert r.status_code == 200
    assert r.json() == {"cambio": None, "rechazos": ["No entendí: eso"]}
    # Dos llamadas al modelo: la lectura del PDF y la respuesta escrita.
    assert db.query(AiUsoDiario).filter_by(organization_id=tienda.id).one().llamadas == 2
    # Cada una queda a nombre de quien la pidió, con su rol, la tarea y el modelo.
    from app.modules.ai.models import AiLlamada
    filas = db.query(AiLlamada).filter_by(organization_id=tienda.id).order_by(AiLlamada.id).all()
    assert [(f.rol, f.tarea, f.proveedor, f.modelo) for f in filas] == [
        ("ADMINISTRADOR", "captura", "falso", "modelo-falso")] * 2
    assert all(f.user_id is not None for f in filas)


# ── etiquetas con prendas que ya existían ─────────────────────────────────

def test_etiquetas_incluyen_lo_que_suma_a_existentes(client, db, tienda, auth_admin_a, falso):
    from app.models import ProductBranchStatus, StockOnHand
    from app.modules.products.models import Brand, Product, ProductVariant

    branch_id = tienda.reglas_carga["sucursal_recibe"]
    depto = db.query(Department).filter_by(organization_id=tienda.id, name="Playeras").one()
    marca = Brand(name="Marca Uno", organization_id=tienda.id)
    db.add(marca)
    db.flush()
    p = Product(name="Playera", brand_id=marca.id, department_id=depto.id,
                organization_id=tienda.id, is_active=True, has_variants=True)
    db.add(p)
    db.flush()
    v = ProductVariant(product_id=p.id, sku="PLAY", size="M", variant_name="M",
                       barcode="7500000000017", price=Decimal("350"), cost=Decimal("175"),
                       organization_id=tienda.id)
    db.add(v)
    db.flush()
    db.add(ProductBranchStatus(variant_id=v.id, branch_id=branch_id, organization_id=tienda.id,
                               is_active_pos=True, is_visible=True))
    db.add(StockOnHand(variant_id=v.id, branch_id=branch_id, qty_on_hand=Decimal("2"),
                       organization_id=tienda.id))
    db.flush()

    falso.guion = [_resp_pdf([_r(precio="350", cantidad="4"),
                              _r(talla="G", precio="350", cantidad="1")])]
    alta = _subir(client, auth_admin_a, "f.pdf", _pdf()).json()
    det = _detalle(client, auth_admin_a, alta["id"])
    clases = {x["talla"]: x["clase"] for g in det["grupos"] for x in g["renglones"]}
    assert clases["M"] == "SUMA", det
    for _ in range(10):
        abiertas = _abiertas(_detalle(client, auth_admin_a, alta["id"]))
        if not abiertas:
            break
        d = abiertas[0]
        client.post(f"/api/cargas/{alta['id']}/dudas/{d['numero']}", headers=auth_admin_a,
                    json={"opcion": d["recomendada"]})
    r = client.post(f"/api/cargas/{alta['id']}/autorizar", headers=auth_admin_a)
    assert r.status_code == 200, r.text

    etiquetas = client.get(f"/api/cargas/{alta['id']}/etiquetas", headers=auth_admin_a).json()
    por_sku = {e["sku"]: e for e in etiquetas}
    assert por_sku["PLAY"]["piezas"] == "4"  # lo que entró, no la existencia total
    assert por_sku["PLAY"]["barcode"] == "7500000000017" and por_sku["PLAY"]["talla"] == "M"
    assert any(e["talla"] == "G" and e["piezas"] == "1" for e in etiquetas)
    assert etiquetas == r.json()["etiquetas"]


def test_dudas_sin_tipo_y_sin_marca_aceptan_texto(client, db, tienda, auth_admin_a, falso):
    falso.guion = [_resp_pdf([_r(tipo=None, precio="100"), _r(marca=None, precio="100")])]
    alta = _subir(client, auth_admin_a, "f.pdf", _pdf()).json()
    det = _detalle(client, auth_admin_a, alta["id"])
    por_tipo = {d["tipo"]: d for d in _abiertas(det)}
    assert por_tipo["sin_tipo"]["acepta_texto"] is True
    assert por_tipo["sin_marca"]["acepta_texto"] is True
    r = client.post(f"/api/cargas/{alta['id']}/dudas/{por_tipo['sin_tipo']['numero']}",
                    headers=auth_admin_a, json={"opcion": "", "valor": "Playera"})
    assert r.status_code == 200 and r.json()["rechazos"] == []
