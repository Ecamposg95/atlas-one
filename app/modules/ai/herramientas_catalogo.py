"""Herramientas de solo lectura del catálogo: departamentos, marcas, búsqueda
de productos, SKU sugerido y existencias. Ninguna escribe."""
from __future__ import annotations

from sqlalchemy import and_, or_, select

from app.crud.products import query_visible_products
from app.models import Brand, Department, Product, ProductVariant, StockOnHand
from app.models.organization import Branch
from app.modules.products.sale_name import sku_sugerido
from app.modules.products.services import sku_en_uso

from .contexto import Contexto, ErrorHerramienta, Herramienta, ambito_sucursal

TOPE_PALABRAS = 6
TOPE_EXISTENCIAS = 60
SIN_PARAMETROS = {"type": "object", "properties": {}}


def _texto(args: dict, clave: str) -> str:
    valor = args.get(clave)
    return str(valor).strip() if valor is not None else ""


def filtro_palabras(q: str, org_id: int):
    """Cada palabra debe aparecer en nombre, modelo, descripción, SKU, color,
    talla o marca ("zegna 42" encuentra la talla 42 de Zegna)."""
    palabras = q.split()[:TOPE_PALABRAS]
    if not palabras:
        raise ErrorHerramienta("Indica qué buscar (q).")
    condiciones = []
    for palabra in palabras:
        patron = f"%{palabra}%"
        condiciones.append(or_(
            Product.name.ilike(patron),
            Product.model.ilike(patron),
            Product.description.ilike(patron),
            ProductVariant.sku.ilike(patron),
            ProductVariant.color.ilike(patron),
            ProductVariant.size.ilike(patron),
            Product.brand_id.in_(select(Brand.id).where(Brand.organization_id == org_id, Brand.name.ilike(patron))),
        ))
    return and_(*condiciones)


def listar_departamentos(ctx: Contexto, args: dict) -> dict:
    filas = (
        ctx.db.query(Department)
        .filter(Department.organization_id == ctx.org_id, Department.deleted_at.is_(None))
        .order_by(Department.name).all()
    )
    return {"departamentos": [{"id": d.id, "nombre": d.name} for d in filas]}


def listar_marcas(ctx: Contexto, args: dict) -> dict:
    filas = (
        ctx.db.query(Brand)
        .filter(Brand.organization_id == ctx.org_id, Brand.deleted_at.is_(None))
        .order_by(Brand.name).all()
    )
    return {"marcas": [{"id": m.id, "nombre": m.name} for m in filas]}


def _producto(p: Product) -> dict:
    return {
        "id": p.id,
        "nombre": p.name,
        "marca": p.brand.name if p.brand else None,
        "departamento": p.department.name if p.department else None,
        "modelo": p.model,
        "genero": p.gender,
        "variantes": [
            {"id": v.id, "sku": v.sku, "color": v.color, "talla": v.size, "precio": float(v.price or 0)}
            for v in p.variants if v.deleted_at is None
        ],
    }


def buscar_producto(ctx: Contexto, args: dict) -> dict:
    """Misma visibilidad que la pantalla de Productos (`query_visible_products`)."""
    try:
        limite = int(args.get("limite") or 10)
    except (TypeError, ValueError):
        limite = 10
    limite = max(1, min(limite, 20))
    productos = (
        query_visible_products(ctx.db, ctx.user, ctx.org_id, join_variants=True)
        .filter(
            Product.deleted_at.is_(None),
            ProductVariant.deleted_at.is_(None),
            filtro_palabras(_texto(args, "q"), ctx.org_id),
        )
        .order_by(Product.name)
        .limit(limite)
        .all()
    )
    return {"productos": [_producto(p) for p in productos]}


def sugerir_sku(ctx: Contexto, args: dict) -> dict:
    nombre = _texto(args, "nombre")
    if not nombre:
        raise ErrorHerramienta("Indica el nombre de la prenda (nombre).")
    sku = sku_sugerido(
        _texto(args, "marca") or None, nombre, _texto(args, "modelo") or None,
        _texto(args, "color") or None, _texto(args, "talla") or None, gender=_texto(args, "genero") or None,
    )
    if not sku:
        raise ErrorHerramienta("Faltan datos para sugerir un SKU.")
    if not sku_en_uso(ctx.db, ctx.org_id, sku):
        return {"sku": sku, "disponible": True}
    # Convención boutique: si ya existe para otra pieza, se numera (-2).
    for n in range(2, 21):
        alternativa = f"{sku}-{n}"
        if not sku_en_uso(ctx.db, ctx.org_id, alternativa):
            return {"sku": sku, "disponible": False, "alternativa": alternativa}
    return {"sku": sku, "disponible": False}


def consultar_existencias(ctx: Contexto, args: dict) -> dict:
    sucursal = ambito_sucursal(ctx, args.get("sucursal_id"))
    q = (
        ctx.db.query(StockOnHand, ProductVariant, Product, Branch)
        .join(ProductVariant, ProductVariant.id == StockOnHand.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .join(Branch, Branch.id == StockOnHand.branch_id)
        .filter(
            Product.organization_id == ctx.org_id,
            Branch.organization_id == ctx.org_id,
            Product.deleted_at.is_(None),
            ProductVariant.deleted_at.is_(None),
            Product.is_active.is_(True),
            filtro_palabras(_texto(args, "q"), ctx.org_id),
        )
    )
    if sucursal is not None:
        q = q.filter(StockOnHand.branch_id == sucursal)
    filas = (
        q.order_by(Product.name, ProductVariant.color, ProductVariant.size, Branch.name)
        .limit(TOPE_EXISTENCIAS + 1).all()
    )
    truncado = len(filas) > TOPE_EXISTENCIAS
    salida = []
    for soh, variante, producto, rama in filas[:TOPE_EXISTENCIAS]:
        marca = producto.brand.name if producto.brand else ""
        salida.append({
            "producto": f"{marca} · {producto.name}" if marca else producto.name,
            "sku": variante.sku,
            "color": variante.color,
            "talla": variante.size,
            "sucursal_id": rama.id,
            "sucursal": rama.name,
            "existencia": float(soh.qty_on_hand or 0),
        })
    return {"filas": salida, "total_piezas": sum(f["existencia"] for f in salida), "truncado": truncado}


HERRAMIENTAS: dict[str, Herramienta] = {
    "listar_departamentos": Herramienta(
        "Departamentos de la tienda con su id.", SIN_PARAMETROS, listar_departamentos,
    ),
    "listar_marcas": Herramienta("Marcas de la tienda con su id.", SIN_PARAMETROS, listar_marcas),
    "buscar_producto": Herramienta(
        "Busca productos del catálogo por palabras (prenda, marca, modelo, SKU, color o talla).",
        {"type": "object", "properties": {
            "q": {"type": "string", "description": "Palabras a buscar."},
            "limite": {"type": "integer", "description": "Máximo de productos (1-20, por defecto 10)."},
        }, "required": ["q"]},
        buscar_producto,
    ),
    "sugerir_sku": Herramienta(
        "SKU sugerido por la convención MARCA-PRENDA-MODELO-GENERO-COLOR-TALLA y si está libre.",
        {"type": "object", "properties": {
            "nombre": {"type": "string", "description": "Nombre de la prenda, sin marca."},
            "marca": {"type": "string"},
            "modelo": {"type": "string"},
            "color": {"type": "string"},
            "talla": {"type": "string"},
            "genero": {"type": "string", "description": "HOMBRE, MUJER, UNISEX o NINO."},
        }, "required": ["nombre"]},
        sugerir_sku,
    ),
    "consultar_existencias": Herramienta(
        "Existencias por producto, talla y sucursal. Sin sucursal_id: la del usuario (o toda la tienda si es admin).",
        {"type": "object", "properties": {
            "q": {"type": "string", "description": "Palabras a buscar (marca, prenda, SKU, talla)."},
            "sucursal_id": {"type": "integer"},
        }, "required": ["q"]},
        consultar_existencias,
    ),
}
