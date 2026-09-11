"""Registro de la duración de cada petición.

Portado de Atlas-Rmazh (`tests/test_request_timing.py`, commits `4c35b24` y
`425bf78`) y adaptado a este repo: el campo de duración se llama `ms` (no
`duration_ms`), y `branch`/`user` se leen del JWT (`Authorization: Bearer …`)
en vez de un header `X-Branch-ID` que aquí no existe.

Sin esto, los logs solo traen el código de respuesta y nadie puede contestar
"¿qué tardó, en qué organización/sucursal y a qué hora?" — ver memoria
`atlas-one-logs-efimeros` (cada redespliegue en Railway borra el historial).

POR QUÉ NO ES UN MIDDLEWARE: `@app.middleware("http")` (BaseHTTPMiddleware)
envuelve toda la petición con `call_next` y, si el cliente se desconecta a
media request —terminales POS en redes inestables—, impide que corra el
`finally: db.close()` de `get_db()`. Se usa un middleware ASGI puro, que solo
observa y no interpone tareas, así que no puede romper el teardown de las
dependencias. El test `test_la_sesion_de_bd_se_cierra_igual` es el candado de
esa regresión.
"""
import json
import logging

import pytest
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.observability.timing import TimingMiddleware


def _app_con_ruta(handler, path="/prueba", **kw):
    app = FastAPI()
    router = APIRouter()
    router.add_api_route(path, handler, **kw)
    app.include_router(router)
    app.add_middleware(TimingMiddleware)
    return app


class TestRegistroDeDuracion:
    def test_registra_metodo_ruta_estado_y_duracion(self, caplog):
        app = _app_con_ruta(lambda: {"ok": True})
        with caplog.at_level(logging.INFO, logger="atlas.timing"):
            TestClient(app).get("/prueba")

        assert caplog.records, "no se registró nada"
        d = json.loads(caplog.records[-1].getMessage())
        assert d["method"] == "GET"
        assert d["path"] == "/prueba"
        assert d["status"] == 200
        assert isinstance(d["ms"], (int, float))
        assert d["ms"] >= 0

    def test_el_mensaje_es_json_de_una_linea(self, caplog):
        # Railway parsea líneas JSON para poder filtrar; un mensaje multilínea
        # se vuelve ilegible ahí.
        app = _app_con_ruta(lambda: {"ok": True})
        with caplog.at_level(logging.INFO, logger="atlas.timing"):
            TestClient(app).get("/prueba")
        msg = caplog.records[-1].getMessage()
        assert "\n" not in msg
        json.loads(msg)

    def test_registra_la_ruta_CON_PLANTILLA_no_el_id_concreto(self, caplog):
        # `/api/sales/abc-123` y `/api/sales/def-456` tienen que agruparse. Con
        # el id concreto cada peticion seria su propia serie y no se podria
        # promediar nada.
        app = _app_con_ruta(lambda item_id: {"id": item_id}, path="/cosa/{item_id}")
        with caplog.at_level(logging.INFO, logger="atlas.timing"):
            TestClient(app).get("/cosa/abc-123")
        d = json.loads(caplog.records[-1].getMessage())
        assert d["path"] == "/cosa/{item_id}", f"se registró el id concreto: {d['path']}"

    def test_una_ruta_que_falla_tambien_se_registra(self, caplog):
        def boom():
            raise HTTPException(status_code=422, detail="no")

        app = _app_con_ruta(boom)
        with caplog.at_level(logging.INFO, logger="atlas.timing"):
            TestClient(app).get("/prueba")
        d = json.loads(caplog.records[-1].getMessage())
        assert d["status"] == 422

    def test_una_excepcion_no_controlada_se_registra_y_se_propaga(self, caplog):
        def boom():
            raise ValueError("revento")

        app = _app_con_ruta(boom)
        with caplog.at_level(logging.INFO, logger="atlas.timing"):
            with pytest.raises(ValueError):
                TestClient(app).get("/prueba")
        d = json.loads(caplog.records[-1].getMessage())
        assert d["status"] == 500, "un fallo no controlado debe quedar registrado, no perderse"

    def test_registrar_NUNCA_puede_tumbar_la_peticion(self, caplog, monkeypatch):
        # Si el registro falla, la venta debe cobrarse igual. Failsafe, como
        # `audit_cash_event`.
        import app.observability.timing as T

        def revienta(*a, **k):
            raise RuntimeError("el logger murió")

        monkeypatch.setattr(T.logger, "info", revienta)
        app = _app_con_ruta(lambda: {"ok": True})
        r = TestClient(app).get("/prueba")
        assert r.status_code == 200, "un fallo al registrar no puede afectar la respuesta"


class TestNoReintroduceLaFuga:
    """Candado del riesgo que describe la advertencia de `timing.py`: el
    teardown de las dependencias tiene que seguir corriendo. Este es el
    motivo de no usar BaseHTTPMiddleware."""

    def test_la_sesion_de_bd_se_cierra_igual(self, caplog):
        cerradas = []

        def fake_db():
            try:
                yield "sesion"
            finally:
                cerradas.append(True)

        def handler(db=Depends(fake_db)):
            return {"db": db}

        app = _app_con_ruta(handler)
        with caplog.at_level(logging.INFO, logger="atlas.timing"):
            TestClient(app).get("/prueba")
        assert cerradas == [True], "el finally de la dependencia NO corrió — fuga de conexiones"

    def test_se_cierra_tambien_cuando_la_ruta_falla(self):
        cerradas = []

        def fake_db():
            try:
                yield "sesion"
            finally:
                cerradas.append(True)

        def handler(db=Depends(fake_db)):
            raise HTTPException(status_code=400, detail="no")

        app = _app_con_ruta(handler)
        TestClient(app).get("/prueba")
        assert cerradas == [True], "el finally NO corrió en el camino de error"


class TestCamposParaMedirImpacto:
    def test_registra_org_desde_el_header(self, caplog):
        app = _app_con_ruta(lambda: {"ok": True})
        with caplog.at_level(logging.INFO, logger="atlas.timing"):
            TestClient(app).get("/prueba", headers={"X-Organization-ID": "7"})
        d = json.loads(caplog.records[-1].getMessage())
        assert d["org"] == 7

    def test_registra_branch_y_user_desde_el_token(self, caplog):
        # `ctx_id` es la sucursal activa (o None para contexto HQ — ver
        # app/modules/auth/router.py). `sub` es el username.
        token = create_access_token({"sub": "cajera1", "ctx_id": 23, "ctx_type": "BRANCH"})
        app = _app_con_ruta(lambda: {"ok": True})
        with caplog.at_level(logging.INFO, logger="atlas.timing"):
            TestClient(app).get("/prueba", headers={"Authorization": f"Bearer {token}"})
        d = json.loads(caplog.records[-1].getMessage())
        assert d["branch"] == 23
        assert d["user"] == "cajera1"

    def test_sin_headers_ni_token_org_branch_y_user_son_null(self, caplog):
        app = _app_con_ruta(lambda: {"ok": True})
        with caplog.at_level(logging.INFO, logger="atlas.timing"):
            TestClient(app).get("/prueba")
        d = json.loads(caplog.records[-1].getMessage())
        assert d["org"] is None
        assert d["branch"] is None
        assert d["user"] is None

    def test_header_org_no_numerico_no_tumba_ni_registra_basura(self, caplog):
        app = _app_con_ruta(lambda: {"ok": True})
        with caplog.at_level(logging.INFO, logger="atlas.timing"):
            r = TestClient(app).get("/prueba", headers={"X-Organization-ID": "abc"})
        assert r.status_code == 200
        d = json.loads(caplog.records[-1].getMessage())
        assert d["org"] is None

    def test_token_invalido_no_tumba_ni_registra_basura(self, caplog):
        app = _app_con_ruta(lambda: {"ok": True})
        with caplog.at_level(logging.INFO, logger="atlas.timing"):
            r = TestClient(app).get("/prueba", headers={"Authorization": "Bearer basura-no-jwt"})
        assert r.status_code == 200
        d = json.loads(caplog.records[-1].getMessage())
        assert d["branch"] is None
        assert d["user"] is None

    @pytest.mark.parametrize("path", ["/assets/index-abc123.js", "/icons/icon-192.png", "/static/app.css"])
    def test_ignora_assets_icons_y_static(self, caplog, path):
        app = _app_con_ruta(lambda: {"ok": True}, path=path)
        with caplog.at_level(logging.INFO, logger="atlas.timing"):
            TestClient(app).get(path)
        assert not [r for r in caplog.records if r.name == "atlas.timing"]

    def test_el_record_lleva_los_campos_como_dict_para_el_formateador_json(self, caplog):
        # Railway filtra por campos de primer nivel; un JSON dentro de "message"
        # no se puede filtrar. El formateador JSON de app/main.py fusiona
        # record.atlas al payload cuando LOG_JSON=true.
        app = _app_con_ruta(lambda: {"ok": True})
        with caplog.at_level(logging.INFO, logger="atlas.timing"):
            TestClient(app).get("/prueba")
        rec = caplog.records[-1]
        assert isinstance(getattr(rec, "atlas", None), dict)
        assert rec.atlas["path"] == "/prueba"


class TestFormateadorJson:
    def test_fusiona_los_campos_atlas_al_primer_nivel(self):
        from app.main import _JsonLogFormatter
        rec = logging.LogRecord("atlas.timing", logging.INFO, __file__, 1, "x", None, None)
        rec.atlas = {"path": "/p", "ms": 12.5, "slow": False}
        out = json.loads(_JsonLogFormatter().format(rec))
        assert out["path"] == "/p" and out["ms"] == 12.5
        assert out["message"] == "x"
