"""Herramientas de solo lectura del asistente: siempre dentro de la
organización y, para quien no es admin/dueño, dentro de su sucursal."""
from conftest import _make_product
from app.models import Brand, Department
from app.models.organization import Branch, BranchType, Organization
from app.modules.ai.contexto import Contexto
from app.modules.ai.herramientas import definiciones, ejecutar
from app.modules.ai.models import AiConversation


def _ctx(db, org, user):
    conv = AiConversation(organization_id=org.id, user_id=user.id)
    db.add(conv)
    db.flush()
    return Contexto(db=db, org_id=org.id, user=user, conversacion=conv)


def _otra_org(db):
    otra = Organization(name="Otra", status="ACTIVE")
    db.add(otra)
    db.flush()
    ajena = Branch(name="Ajena", branch_type=BranchType.STORE, can_sell=True, is_active=True, organization_id=otra.id)
    db.add(ajena)
    db.flush()
    return otra, ajena


class TestRegistro:
    def test_definiciones_en_formato_openai(self):
        defs = definiciones()
        nombres = {d["function"]["name"] for d in defs}
        assert {"listar_departamentos", "listar_marcas", "buscar_producto", "sugerir_sku",
                "consultar_existencias"} <= nombres
        for d in defs:
            assert d["type"] == "function"
            assert d["function"]["parameters"]["type"] == "object"
            assert d["function"]["description"]

    def test_herramienta_desconocida(self, db, org, admin_user):
        assert ejecutar("borrar_todo", {}, _ctx(db, org, admin_user)) == {"error": "Herramienta desconocida: borrar_todo"}

    def test_argumentos_que_no_son_objeto(self, db, org, admin_user):
        assert "objeto" in ejecutar("buscar_producto", ["x"], _ctx(db, org, admin_user))["error"]


class TestCatalogo:
    def test_departamentos_y_marcas_solo_de_la_org(self, db, org, admin_user):
        otra, _ = _otra_org(db)
        db.add_all([
            Department(name="Playeras", organization_id=org.id), Department(name="Ajeno", organization_id=otra.id),
            Brand(name="Versace", organization_id=org.id), Brand(name="Ajena", organization_id=otra.id),
        ])
        db.flush()
        ctx = _ctx(db, org, admin_user)
        assert [d["nombre"] for d in ejecutar("listar_departamentos", {}, ctx)["departamentos"]] == ["Playeras"]
        assert [m["nombre"] for m in ejecutar("listar_marcas", {}, ctx)["marcas"]] == ["Versace"]

    def test_buscar_por_marca_y_color(self, db, org, admin_user, branch_a):
        marca = Brand(name="Versace", organization_id=org.id)
        db.add(marca)
        db.flush()
        p, v = _make_product(db, org, "Playera cuello redondo", "VER-PLAY-CR-NEG-M", 1200, [(branch_a.id, True)])
        p.brand_id, v.color, v.size = marca.id, "Negro", "M"
        db.flush()
        _make_product(db, org, "Camisa", "GUC-CAMI", 900, [(branch_a.id, True)])
        r = ejecutar("buscar_producto", {"q": "versace negro"}, _ctx(db, org, admin_user))
        assert [x["nombre"] for x in r["productos"]] == ["Playera cuello redondo"]
        assert r["productos"][0]["marca"] == "Versace"
        assert r["productos"][0]["variantes"] == [
            {"id": v.id, "sku": "VER-PLAY-CR-NEG-M", "color": "Negro", "talla": "M", "precio": 1200.0},
        ]

    def test_cajero_no_ve_lo_de_otra_sucursal(self, db, org, admin_user, cajero_a, products_setup):
        del_cajero = [x["nombre"] for x in ejecutar("buscar_producto", {"q": "Producto B"}, _ctx(db, org, cajero_a))["productos"]]
        del_admin = [x["nombre"] for x in ejecutar("buscar_producto", {"q": "Producto B"}, _ctx(db, org, admin_user))["productos"]]
        assert "Producto B" not in del_cajero and "Producto Ambos" in del_cajero
        assert "Producto B" in del_admin

    def test_buscar_sin_texto_es_error(self, db, org, admin_user):
        assert "(q)" in ejecutar("buscar_producto", {"q": "  "}, _ctx(db, org, admin_user))["error"]

    def test_sugerir_sku_y_alternativa(self, db, org, admin_user, branch_a):
        args = {"nombre": "Playera cuello redondo", "marca": "Versace", "color": "Negro", "talla": "M"}
        ctx = _ctx(db, org, admin_user)
        assert ejecutar("sugerir_sku", args, ctx) == {"sku": "VER-PLAY-CR-NEG-M", "disponible": True}
        _make_product(db, org, "Playera", "VER-PLAY-CR-NEG-M", 1200, [(branch_a.id, True)])
        assert ejecutar("sugerir_sku", args, ctx) == {
            "sku": "VER-PLAY-CR-NEG-M", "disponible": False, "alternativa": "VER-PLAY-CR-NEG-M-2",
        }


class TestExistencias:
    def test_cajero_solo_su_sucursal(self, db, org, cajero_a, branch_a, branch_b, products_setup):
        ctx = _ctx(db, org, cajero_a)
        r = ejecutar("consultar_existencias", {"q": "Producto Ambos"}, ctx)
        assert [(f["sucursal_id"], f["existencia"]) for f in r["filas"]] == [(branch_a.id, 100.0)]
        assert ejecutar("consultar_existencias", {"q": "Ambos", "sucursal_id": branch_b.id}, ctx) == {
            "error": "Solo puedes consultar tu sucursal.",
        }

    def test_admin_ve_toda_la_org_o_una_sucursal(self, db, org, admin_user, branch_a, branch_b, products_setup):
        ctx = _ctx(db, org, admin_user)
        r = ejecutar("consultar_existencias", {"q": "Producto Ambos"}, ctx)
        assert sorted(f["sucursal_id"] for f in r["filas"]) == sorted([branch_a.id, branch_b.id])
        assert r["total_piezas"] == 200.0 and r["truncado"] is False
        solo_b = ejecutar("consultar_existencias", {"q": "Producto Ambos", "sucursal_id": branch_b.id}, ctx)
        assert [f["sucursal_id"] for f in solo_b["filas"]] == [branch_b.id]

    def test_sucursal_de_otra_org_no_existe(self, db, org, admin_user, products_setup):
        _, ajena = _otra_org(db)
        r = ejecutar("consultar_existencias", {"q": "Producto", "sucursal_id": ajena.id}, _ctx(db, org, admin_user))
        assert r == {"error": f"La sucursal {ajena.id} no existe."}
