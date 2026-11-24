"""Herramientas de solo lectura del catálogo: búsqueda de productos con el
precio de la sucursal, existencias, "hay o no hay" en otras sucursales,
departamentos, marcas y SKU sugerido. Ninguna escribe.

Tres reglas que se repiten en todas:

- **Qué producto ve cada quien** lo decide `query_visible_products` (la misma
  política del POS y de Productos) más `is_active_pos` en la sucursal.
- **El precio** es el que cobra la sucursal (`precio_en_sucursal`): su
  `price_override` o, sin él, el precio base.
- **Costo y cantidades de otras sucursales** dependen del perfil del rol
  (`matriz.py`), no de lo que pida el modelo.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, or_, select

from app.crud.products import query_visible_products
from app.models import Brand, Department, Product, ProductVariant, StockOnHand
from app.models.organization import Branch
from app.modules.products.models import ProductBranchStatus
from app.modules.products.sale_name import sku_sugerido
from app.modules.products.services import sku_en_uso
from app.modules.products.services.precio_sucursal import precio_en_sucursal, precios_de_sucursal

from .contexto import Contexto, ErrorHerramienta, Herramienta, ambito_sucursal, sucursal_propia, tabla
from .datos import dato
from .matriz import CAJA, DIRECCION

TOPE_PALABRAS = 6
TOPE_EXISTENCIAS = 60
TOPE_PRODUCTOS_VISIBLES = 200
TOPE_VARIANTES_OTRAS = 25
SIN_PARAMETROS = {"type": "object", "properties": {}}


def _texto(args: dict, clave: str) -> str:
    valor = args.get(clave)
    return str(valor).strip() if valor is not None else ""


def _num(valor) -> float:
    return round(float(valor or 0), 2)


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


def _visibles(ctx: Contexto, q: str, sucursal: Optional[int]):
    """Productos que el usuario puede ver y que casan con `q` (Query[Product]).

    `sucursal` solo cuenta para dirección (drill-down a una sucursal); a los
    demás `query_visible_products` les impone la suya."""
    return query_visible_products(
        ctx.db, ctx.user, ctx.org_id, join_variants=True,
        branch_id_override=sucursal if ctx.perfil == DIRECCION else None,
    ).filter(
        Product.deleted_at.is_(None),
        ProductVariant.deleted_at.is_(None),
        filtro_palabras(q, ctx.org_id),
    )


def _ids_visibles(ctx: Contexto, q: str, sucursal: Optional[int]) -> list[str]:
    return [fila[0] for fila in _visibles(ctx, q, sucursal).with_entities(Product.id)
            .limit(TOPE_PRODUCTOS_VISIBLES).all()]


def _habilitadas(ctx: Contexto, sucursal: int, ids: list[str]) -> set[str]:
    """Tallas vendibles en la sucursal (`is_active_pos`), igual que el POS."""
    if not ids:
        return set()
    return {
        vid for (vid,) in ctx.db.query(ProductBranchStatus.variant_id).filter(
            ProductBranchStatus.organization_id == ctx.org_id,
            ProductBranchStatus.branch_id == sucursal,
            ProductBranchStatus.is_active_pos.is_(True),
            ProductBranchStatus.variant_id.in_(ids),
        )
    }


def _nombre(producto: Product) -> str:
    marca = producto.brand.name if producto.brand else ""
    return dato(f"{marca} · {producto.name}" if marca else producto.name) or ""


def _detalle(variante: ProductVariant) -> str:
    return " ".join(x for x in (dato(variante.color), dato(variante.size)) if x)


# ── departamentos y marcas ───────────────────────────────────────────────────

def listar_departamentos(ctx: Contexto, args: dict) -> dict:
    filas = (
        ctx.db.query(Department)
        .filter(Department.organization_id == ctx.org_id, Department.deleted_at.is_(None))
        .order_by(Department.name).all()
    )
    return {"departamentos": [{"id": d.id, "nombre": dato(d.name)} for d in filas]}


def listar_marcas(ctx: Contexto, args: dict) -> dict:
    filas = (
        ctx.db.query(Brand)
        .filter(Brand.organization_id == ctx.org_id, Brand.deleted_at.is_(None))
        .order_by(Brand.name).all()
    )
    return {"marcas": [{"id": m.id, "nombre": dato(m.name)} for m in filas]}


# ── buscar producto ──────────────────────────────────────────────────────────

def _margen(precio: Decimal, costo) -> Optional[float]:
    if costo is None or costo <= 0 or precio <= 0:
        return None
    return round(float((precio - costo) / precio * 100), 1)


def buscar_producto(ctx: Contexto, args: dict) -> dict:
    """Productos con el precio que cobra la sucursal. Costo y margen solo para
    gerencia y dirección: la caja no los recibe ni pidiéndolos."""
    try:
        limite = int(args.get("limite") or 10)
    except (TypeError, ValueError):
        limite = 10
    limite = max(1, min(limite, 20))
    con_costo = ctx.perfil != CAJA
    sucursal = ambito_sucursal(ctx, args.get("sucursal_id"))
    productos = _visibles(ctx, _texto(args, "q"), sucursal).order_by(Product.name).limit(limite).all()

    ids = [v.id for p in productos for v in p.variants if v.deleted_at is None]
    habilitadas = _habilitadas(ctx, sucursal, ids) if sucursal is not None else None
    propios = precios_de_sucursal(ctx.db, ctx.org_id, sucursal, ids)
    # Dirección sin sucursal ve el precio base y, aparte, quién cobra distinto.
    distintos: dict[str, list[dict]] = {}
    if sucursal is None and ids:
        for vid, precio, nombre in ctx.db.query(
            ProductBranchStatus.variant_id, ProductBranchStatus.price_override, Branch.name,
        ).join(Branch, Branch.id == ProductBranchStatus.branch_id).filter(
            ProductBranchStatus.organization_id == ctx.org_id, Branch.organization_id == ctx.org_id,
            ProductBranchStatus.variant_id.in_(ids), ProductBranchStatus.price_override.isnot(None),
        ).order_by(Branch.name):
            distintos.setdefault(vid, []).append({"sucursal": dato(nombre), "precio": _num(precio)})

    salida, filas = [], []
    for p in productos:
        variantes = []
        for v in p.variants:
            if v.deleted_at is not None or (habilitadas is not None and v.id not in habilitadas):
                continue
            precio = precio_en_sucursal(v, propios)
            fila = {"sku": dato(v.sku), "color": dato(v.color), "talla": dato(v.size), "precio": _num(precio)}
            renglon = [_nombre(p), _detalle(v), fila["sku"], fila["precio"]]
            if con_costo:
                tiene_costo = v.cost is not None and v.cost > 0
                fila["costo"] = _num(v.cost) if tiene_costo else None
                fila["margen_pct"] = _margen(precio, v.cost)
                renglon += [fila["costo"], fila["margen_pct"]]
            if v.id in distintos:
                fila["precio_en_sucursales"] = distintos[v.id]
            variantes.append(fila)
            filas.append(renglon)
        if not variantes:
            continue
        salida.append({
            "nombre": dato(p.name),
            "marca": dato(p.brand.name) if p.brand else None,
            "departamento": dato(p.department.name) if p.department else None,
            "modelo": dato(p.model),
            "variantes": variantes,
        })
    columnas = ["Producto", "Color / talla", "SKU", "Precio"] + (["Costo", "Margen %"] if con_costo else [])
    return {
        "productos": salida,
        "precio": "el de la sucursal" if sucursal is not None else "el base (sin sucursal elegida)",
        "_tabla": tabla("Productos", columnas, filas),
    }


# ── existencias ──────────────────────────────────────────────────────────────

def consultar_existencias(ctx: Contexto, args: dict) -> dict:
    """Existencia por talla. Caja y gerencia: su sucursal y solo lo habilitado
    ahí. Dirección: una sucursal o, sin `sucursal_id`, todas (fila por sucursal)."""
    sucursal = ambito_sucursal(ctx, args.get("sucursal_id"))
    q = _texto(args, "q")
    ids = _ids_visibles(ctx, q, sucursal)
    comunes = (
        Product.organization_id == ctx.org_id,
        Product.id.in_(ids or ["-"]),
        ProductVariant.deleted_at.is_(None),
        filtro_palabras(q, ctx.org_id),
    )
    if sucursal is not None:
        rama = ctx.db.query(Branch).filter(Branch.id == sucursal, Branch.organization_id == ctx.org_id).first()
        consulta = (
            ctx.db.query(ProductVariant, Product, StockOnHand.qty_on_hand)
            .join(Product, Product.id == ProductVariant.product_id)
            .join(ProductBranchStatus, and_(
                ProductBranchStatus.variant_id == ProductVariant.id,
                ProductBranchStatus.branch_id == sucursal,
                ProductBranchStatus.organization_id == ctx.org_id,
                ProductBranchStatus.is_active_pos.is_(True),
            ))
            .outerjoin(StockOnHand, and_(
                StockOnHand.variant_id == ProductVariant.id, StockOnHand.branch_id == sucursal,
            ))
            .filter(*comunes)
            .order_by(Product.name, ProductVariant.color, ProductVariant.size)
        )
        crudas = [(v, p, rama, cant) for v, p, cant in consulta.limit(TOPE_EXISTENCIAS + 1).all()]
    else:
        consulta = (
            ctx.db.query(ProductVariant, Product, Branch, StockOnHand.qty_on_hand)
            .join(Product, Product.id == ProductVariant.product_id)
            .join(StockOnHand, StockOnHand.variant_id == ProductVariant.id)
            .join(Branch, Branch.id == StockOnHand.branch_id)
            .filter(*comunes, Branch.organization_id == ctx.org_id)
            .order_by(Product.name, ProductVariant.color, ProductVariant.size, Branch.name)
        )
        crudas = consulta.limit(TOPE_EXISTENCIAS + 1).all()

    truncado = len(crudas) > TOPE_EXISTENCIAS
    salida, filas = [], []
    for variante, producto, rama, cantidad in crudas[:TOPE_EXISTENCIAS]:
        fila = {
            "producto": _nombre(producto),
            "sku": dato(variante.sku),
            "color": dato(variante.color),
            "talla": dato(variante.size),
            "sucursal_id": rama.id if rama else sucursal,
            "sucursal": dato(rama.name) if rama else None,
            "existencia": _num(cantidad),
        }
        salida.append(fila)
        filas.append([fila["producto"], _detalle(variante), fila["sucursal"], fila["existencia"]])
    return {
        "filas": salida, "total_piezas": sum(f["existencia"] for f in salida), "truncado": truncado,
        "_tabla": tabla("Existencias", ["Producto", "Color / talla", "Sucursal", "Existencia"], filas),
    }


def disponibilidad_otras_sucursales(ctx: Contexto, args: dict) -> dict:
    """¿Hay en otra sucursal? Para la caja, un sí o un no por sucursal, sin
    cantidades. Para gerencia, con cantidades. Solo de productos que el usuario
    ya ve en SU sucursal."""
    propia = sucursal_propia(ctx)
    con_cantidad = ctx.perfil != CAJA
    q = _texto(args, "q")
    ids = _ids_visibles(ctx, q, None)
    variantes = (
        ctx.db.query(ProductVariant, Product)
        .join(Product, Product.id == ProductVariant.product_id)
        .join(ProductBranchStatus, and_(
            ProductBranchStatus.variant_id == ProductVariant.id,
            ProductBranchStatus.branch_id == propia,
            ProductBranchStatus.organization_id == ctx.org_id,
            ProductBranchStatus.is_active_pos.is_(True),
        ))
        .filter(
            Product.organization_id == ctx.org_id, Product.id.in_(ids or ["-"]),
            ProductVariant.deleted_at.is_(None), filtro_palabras(q, ctx.org_id),
        )
        .order_by(Product.name, ProductVariant.color, ProductVariant.size)
        .limit(TOPE_VARIANTES_OTRAS + 1).all()
    )
    truncado = len(variantes) > TOPE_VARIANTES_OTRAS
    variantes = variantes[:TOPE_VARIANTES_OTRAS]
    otras = (
        ctx.db.query(Branch)
        .filter(Branch.organization_id == ctx.org_id, Branch.is_active.is_(True), Branch.id != propia)
        .order_by(Branch.name).all()
    )
    cantidades: dict[tuple[str, int], Decimal] = {}
    if variantes and otras:
        for vid, bid, cant in ctx.db.query(
            StockOnHand.variant_id, StockOnHand.branch_id, StockOnHand.qty_on_hand,
        ).filter(
            StockOnHand.variant_id.in_([v.id for v, _ in variantes]),
            StockOnHand.branch_id.in_([b.id for b in otras]),
        ):
            cantidades[(vid, bid)] = cant or Decimal(0)

    salida, filas = [], []
    for variante, producto in variantes:
        sucursales = []
        for rama in otras:
            cantidad = cantidades.get((variante.id, rama.id), Decimal(0))
            hay = cantidad > 0
            celda = {"sucursal": dato(rama.name), "hay": hay}
            if con_cantidad:
                celda["existencia"] = _num(cantidad)
            sucursales.append(celda)
            filas.append([_nombre(producto), _detalle(variante), celda["sucursal"],
                          _num(cantidad) if con_cantidad else ("Sí hay" if hay else "No hay")])
        salida.append({
            "producto": _nombre(producto), "sku": dato(variante.sku),
            "color": dato(variante.color), "talla": dato(variante.size),
            "otras_sucursales": sucursales,
        })
    return {
        "filas": salida, "truncado": truncado,
        "_tabla": tabla("En otras sucursales", ["Producto", "Color / talla", "Sucursal",
                                                "Existencia" if con_cantidad else "¿Hay?"], filas),
    }


# ── SKU sugerido (altas: fase A2, ningún rol la recibe todavía) ──────────────

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


_BUSQUEDA = {"type": "object", "properties": {
    "q": {"type": "string", "description": "Palabras a buscar (prenda, marca, modelo, SKU, color o talla)."},
}, "required": ["q"]}

HERRAMIENTAS: dict[str, Herramienta] = {
    "listar_departamentos": Herramienta(
        "Departamentos de la tienda con su id.", SIN_PARAMETROS, listar_departamentos,
    ),
    "listar_marcas": Herramienta("Marcas de la tienda con su id.", SIN_PARAMETROS, listar_marcas),
    "buscar_producto": Herramienta(
        "Busca productos por palabras y da el precio que cobra la sucursal por cada color y talla.",
        {"type": "object", "properties": {
            **_BUSQUEDA["properties"],
            "limite": {"type": "integer", "description": "Máximo de productos (1-20, por defecto 10)."},
        }, "required": ["q"]},
        buscar_producto, elige_sucursal=True,
    ),
    "consultar_existencias": Herramienta(
        "Existencias por producto, color y talla.", _BUSQUEDA, consultar_existencias, elige_sucursal=True,
    ),
    "disponibilidad_otras_sucursales": Herramienta(
        "Dice si un producto de tu sucursal lo hay en las otras sucursales.",
        _BUSQUEDA, disponibilidad_otras_sucursales,
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
}
