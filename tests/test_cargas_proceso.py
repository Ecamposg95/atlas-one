"""Lectura en segundo plano: intento vigente, latido y guardas contra la doble aplicación."""
import io
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from pypdf import PdfWriter

from app.modules.ai.proveedores import (
    ProveedorFalso, ProveedorNoDisponible, RespuestaJSON,
)
from app.modules.cargas import proceso
from app.modules.cargas.aplicar import volver_a_plan
from app.modules.cargas.extraccion_pdf import extraer_pdf
from app.modules.cargas.models import CargaMercancia, CargaRenglon
from tests.conftest import TestSession
from tests.test_cargas_api import _r, _resp_pdf, _subir, _xlsx, falso, tienda  # noqa: F401


def _pdf(paginas: int = 1) -> bytes:
    w = PdfWriter()
    for _ in range(paginas):
        w.add_blank_page(width=200, height=200)
    b = io.BytesIO()
    w.write(b)
    return b.getvalue()


def _nueva(db, org, admin, contenido=None, nombre="f.pdf", tipo="pdf"):
    carga = proceso.crear_carga(db, org.id, admin, nombre, contenido or _pdf(), tipo, "entrada", None)
    db.flush()
    return carga


class _ClienteQueEstorba:
    """Mientras "lee", otra petición cambia la carga (lo que hace la recuperación
    perezosa o un Volver a intentar); luego responde o falla."""

    def __init__(self, db, carga_id, cambios, respuesta=None, error=None):
        self.db, self.carga_id, self.cambios = db, carga_id, cambios
        self.respuesta, self.error = respuesta, error

    def generar_json(self, *, sistema, contenido, esquema, max_tokens=64000, latido=None):
        self.db.query(CargaMercancia).filter_by(id=self.carga_id).update(self.cambios)
        self.db.flush()
        if self.error:
            raise self.error
        return RespuestaJSON(datos=self.respuesta, tokens_entrada=5, tokens_salida=3)


def _renglones(db, carga):
    return db.query(CargaRenglon).filter_by(carga_id=carga.id).count()


# ── intento ───────────────────────────────────────────────────────────────

def test_alta_y_reintento_ponen_intento_nuevo(db, org, admin_a):
    carga = _nueva(db, org, admin_a)
    assert carga.intento and len(carga.intento) == 36
    primero = carga.intento
    carga.estado, carga.error = "error", "x"
    db.flush()
    assert proceso.reintentar(db, carga) is True
    assert carga.estado == "leyendo" and carga.intento and carga.intento != primero


def test_hilo_cuyo_intento_ya_no_es_el_vigente_no_escribe(db, org, admin_a):
    carga = _nueva(db, org, admin_a)
    cliente = _ClienteQueEstorba(db, carga.id, {"intento": "otro-intento"},
                                 respuesta=_resp_pdf([_r()]))
    proceso.procesar_carga(carga.id, cliente, db=db)
    db.expire_all()
    carga = db.get(CargaMercancia, carga.id)
    assert (carga.estado, carga.intento) == ("leyendo", "otro-intento")
    assert _renglones(db, carga) == 0


def test_hilo_que_termina_con_la_carga_en_otro_estado_no_pisa(db, org, admin_a):
    carga = _nueva(db, org, admin_a)
    ahora = datetime.now(timezone.utc)
    cliente = _ClienteQueEstorba(db, carga.id, {"estado": "aplicada", "aplicada_at": ahora},
                                 respuesta=_resp_pdf([_r()]))
    proceso.procesar_carga(carga.id, cliente, db=db)
    db.expire_all()
    carga = db.get(CargaMercancia, carga.id)
    assert carga.estado == "aplicada" and carga.error is None
    assert _renglones(db, carga) == 0


def test_hilo_que_falla_con_la_carga_ya_marcada_no_pisa_el_error(db, org, admin_a):
    carga = _nueva(db, org, admin_a)
    cliente = _ClienteQueEstorba(db, carga.id, {"estado": "error", "error": proceso.LECTURA_INTERRUMPIDA},
                                 error=ProveedorNoDisponible("El proveedor no respondió."))
    proceso.procesar_carga(carga.id, cliente, db=db)
    db.expire_all()
    carga = db.get(CargaMercancia, carga.id)
    assert (carga.estado, carga.error) == ("error", proceso.LECTURA_INTERRUMPIDA)


def test_hilo_vigente_si_escribe(db, org, admin_a):
    carga = _nueva(db, org, admin_a)
    proceso.procesar_carga(carga.id, ProveedorFalso([_resp_pdf([_r()])]), db=db)
    db.expire_all()
    carga = db.get(CargaMercancia, carga.id)
    assert carga.estado == "plan" and _renglones(db, carga) == 1


# ── carga aplicada: nunca vuelve a revisión ───────────────────────────────

def test_volver_a_plan_sobre_carga_aplicada_409(db, org, admin_a):
    carga = _nueva(db, org, admin_a)
    proceso.procesar_carga(carga.id, ProveedorFalso([_resp_pdf([_r()])]), db=db)
    db.expire_all()
    carga = db.get(CargaMercancia, carga.id)
    # Una lectura vieja la dejó en `error` después de aplicada (lo que C1 describía).
    carga.estado, carga.aplicada_at = "error", datetime.now(timezone.utc)
    db.flush()
    with pytest.raises(HTTPException) as e:
        volver_a_plan(db, carga)
    assert e.value.status_code == 409
    with pytest.raises(HTTPException) as e:
        proceso.reintentar(db, carga)
    assert e.value.status_code == 409
    assert carga.estado == "error"


def test_reintentar_por_api_sobre_carga_aplicada_409(client, db, tienda, auth_admin_a, falso):
    falso.guion = [_resp_pdf([_r()])]
    alta = _subir(client, auth_admin_a, "f.pdf", _pdf()).json()
    carga = db.get(CargaMercancia, alta["id"])
    carga.estado, carga.aplicada_at = "error", datetime.now(timezone.utc)
    db.flush()
    r = client.post(f"/api/cargas/{alta['id']}/reintentar", headers=auth_admin_a)
    assert r.status_code == 409
    db.refresh(carga)
    assert carga.estado == "error"


# ── latido ────────────────────────────────────────────────────────────────

def test_el_latido_mueve_updated_at(db, org, admin_a):
    carga = _nueva(db, org, admin_a)
    hace = datetime.now(timezone.utc) - timedelta(minutes=30)
    db.query(CargaMercancia).filter_by(id=carga.id).update({"updated_at": hace})
    db.flush()
    db.expire_all()

    def sesiones():
        return TestSession(bind=db.connection())

    assert proceso.latir(carga.id, "otro", sesiones=sesiones) is False  # intento viejo: no late
    db.expire_all()
    assert proceso._utc(db.get(CargaMercancia, carga.id).updated_at) <= hace + timedelta(seconds=1)

    assert proceso.latir(carga.id, carga.intento, sesiones=sesiones) is True
    db.expire_all()
    movida = proceso._utc(db.get(CargaMercancia, carga.id).updated_at)
    assert movida > datetime.now(timezone.utc) - timedelta(minutes=1)
    # Con el latido al día, la recuperación perezosa ya no la toca.
    assert proceso.recuperar_cargas_colgadas(db, org_id=org.id) == 0


def test_extraer_pdf_avisa_al_terminar_cada_bloque():
    avisos = []
    c = ProveedorFalso([_resp_pdf([_r("A")]), _resp_pdf([_r("B")])])
    extraer_pdf(_pdf(16), c, "", al_terminar_bloque=lambda: avisos.append(1))
    assert len(avisos) == 2


def test_procesar_carga_late_por_bloque_y_por_tabla(db, org, admin_a):
    latidos = []
    pdf = _nueva(db, org, admin_a, _pdf(16))
    proceso.procesar_carga(pdf.id, ProveedorFalso([_resp_pdf([_r("A")]), _resp_pdf([_r("B")])]),
                           db=db, latido=lambda: latidos.append("pdf"))
    assert latidos == ["pdf", "pdf"]

    xlsx = _nueva(db, org, admin_a, _xlsx([["Descripción", "Cantidad"], ["Playera", 2]]),
                  nombre="a.xlsx", tipo="xlsx")
    mapa = {"campos": {"descripcion_original": 0, "marca": None, "tipo": None, "material": None,
                       "color": None, "talla": None, "cantidad": 1, "observacion": None},
            "columnas_dinero": [], "texto_libre": []}
    proceso.procesar_carga(xlsx.id, ProveedorFalso([mapa]), db=db,
                           latido=lambda: latidos.append("xlsx"))
    assert latidos.count("xlsx") == 1
