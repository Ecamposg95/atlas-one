"""Tablas del asistente IA, `organization.ai_instrucciones` y el historial que
se le manda al modelo (SP4, 2026-10)."""
import pytest
from sqlalchemy.exc import IntegrityError

from conftest import _make_user
from app.core.fechas import hoy_negocio
from app.models.organization import Organization
from app.models.users import Role
from app.modules.ai.historial import guardar_mensaje, historial_para_llm, recortar_historial
from app.modules.ai.limpieza import borrar_datos_ai_de_org
from app.modules.ai.models import AiConversation, AiMessage, AiPropuesta, AiUsoDiario
from scripts import railway_init

LLAMADA = {"id": "c1", "type": "function", "function": {"name": "listar_marcas", "arguments": "{}"}}


def _conv(db, org, user):
    c = AiConversation(organization_id=org.id, user_id=user.id, titulo="Prueba")
    db.add(c)
    db.flush()
    return c


class TestEsquema:
    def test_fks_a_uuid_son_string_36(self):
        assert AiConversation.__table__.c.id.type.length == 36
        assert AiMessage.__table__.c.conversation_id.type.length == 36
        assert AiPropuesta.__table__.c.conversation_id.type.length == 36

    def test_uso_diario_unico_por_org_y_fecha(self, db, org):
        db.add(AiUsoDiario(organization_id=org.id, fecha=hoy_negocio()))
        db.flush()
        with pytest.raises(IntegrityError):
            with db.begin_nested():
                db.add(AiUsoDiario(organization_id=org.id, fecha=hoy_negocio()))
                db.flush()

    def test_el_arranque_migra_ai_instrucciones(self):
        declaradas = {(t, c) for t, c, _ in railway_init.COLUMN_MIGRATIONS}
        assert ("organization", "ai_instrucciones") in declaradas


class TestInstruccionesDeLaOrg:
    def test_admin_las_guarda_y_las_lee(self, client, db, org, auth_admin):
        texto = "Tallas Ch, M, G, XL. MAM = Maison Margiela."
        r = client.put("/api/organization/", json={"ai_instrucciones": texto}, headers=auth_admin)
        assert r.status_code == 200, r.text
        assert r.json()["ai_instrucciones"] == texto
        db.refresh(org)
        assert org.ai_instrucciones == texto
        assert client.get("/api/organization/", headers=auth_admin).json()["ai_instrucciones"] == texto

    def test_cajero_no_las_cambia(self, client, auth_cajero_a):
        r = client.put("/api/organization/", json={"ai_instrucciones": "x"}, headers=auth_cajero_a)
        assert r.status_code == 403

    def test_tope_de_4000_caracteres(self, client, auth_admin):
        r = client.put("/api/organization/", json={"ai_instrucciones": "x" * 4001}, headers=auth_admin)
        assert r.status_code == 422


class TestHistorial:
    def test_orden_crece_por_conversacion(self, db, org, admin_user):
        c = _conv(db, org, admin_user)
        a = guardar_mensaje(db, c, "user", "hola")
        b = guardar_mensaje(db, c, "assistant", "qué tal")
        assert (a.orden, b.orden) == (1, 2)
        assert a.organization_id == org.id

    def test_recorte_no_empieza_en_tool_huerfano(self, db, org, admin_user):
        c = _conv(db, org, admin_user)
        guardar_mensaje(db, c, "user", "busca marcas")
        guardar_mensaje(db, c, "assistant", "", tool_calls=[LLAMADA])
        guardar_mensaje(db, c, "tool", '{"marcas": []}', tool_call_id="c1")
        guardar_mensaje(db, c, "assistant", "No hay marcas.")
        todos = db.query(AiMessage).filter(AiMessage.conversation_id == c.id).order_by(AiMessage.orden).all()
        # Los dos últimos son tool + assistant: el tool quedaría huérfano.
        assert [m.rol for m in recortar_historial(todos, tope=2)] == ["assistant"]
        assert [m.rol for m in recortar_historial(todos, tope=30)] == ["user", "assistant", "tool", "assistant"]

    def test_formato_llm(self, db, org, admin_user):
        c = _conv(db, org, admin_user)
        guardar_mensaje(db, c, "user", "hola")
        guardar_mensaje(db, c, "assistant", "", tool_calls=[LLAMADA])
        guardar_mensaje(db, c, "tool", "{}", tool_call_id="c1")
        guardar_mensaje(db, c, "evento", "Propuesta aplicada: Alta VER-1")
        h = historial_para_llm(db, c)
        assert h[0] == {"role": "user", "content": "hola"}
        assert h[1]["role"] == "assistant" and h[1]["tool_calls"] == [LLAMADA]
        assert h[2] == {"role": "tool", "tool_call_id": "c1", "content": "{}"}
        assert h[3] == {"role": "user", "content": "[Aviso del sistema] Propuesta aplicada: Alta VER-1"}


class TestLimpieza:
    def test_borra_solo_la_org_indicada(self, db, org, admin_user):
        otra = Organization(name="Otra", status="ACTIVE")
        db.add(otra)
        db.flush()
        dueno = _make_user(db, otra, None, "dueno_otra", Role.DUEÑO)
        mia, ajena = _conv(db, org, admin_user), _conv(db, otra, dueno)
        for c in (mia, ajena):
            guardar_mensaje(db, c, "user", "hola")
            db.add(AiPropuesta(
                organization_id=c.organization_id, conversation_id=c.id, tipo="ajustar_existencias",
                datos={}, avisos=[], resumen="r", confirmada_por=c.user_id,
            ))
        db.add(AiUsoDiario(organization_id=otra.id, fecha=hoy_negocio(), tokens_entrada=5))
        db.flush()

        borrados = borrar_datos_ai_de_org(db, otra.id)

        assert borrados == {"ai_propuestas": 1, "ai_messages": 1, "ai_conversations": 1, "ai_uso_diario": 1}
        assert db.query(AiConversation).filter(AiConversation.organization_id == otra.id).count() == 0
        assert db.query(AiConversation).filter(AiConversation.organization_id == org.id).count() == 1
