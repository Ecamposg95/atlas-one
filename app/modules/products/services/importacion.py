"""Importación de catálogo fila por fila (POST /api/products/upload).

Cada fila es un "upsert" por SKU dentro de un SAVEPOINT que abre el router:
  * SKU nuevo                  -> `crear_producto` (mismas validaciones que el alta manual);
  * SKU nuevo con Color/Talla y un producto de ESTA carga con el mismo
    Nombre + Departamento      -> `crear_variantes` (variante hermana);
  * SKU existente (vivo)       -> `_actualizar_desde_fila`.
Después, para las tres ramas: habilitación por sucursal, existencia absoluta
("Stock" es lo que HAY, no lo que entra), empaques y escalones por columnas.

Cambios deliberados respecto al upload anterior: SKU sin distinguir mayúsculas,
filas nuevas con precio <= 0 se rechazan (misma regla que el alta manual),
fila nueva = alta manual (código interno, existencia 0 en cada sucursal
habilitada) y `Tasa IVA` opcional.

Cualquier `HTTPException` del servicio o `FilaInvalida` revierte la fila
completa (ROLLBACK TO SAVEPOINT) y el router la reporta con su `detail`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    Brand, Department, PackagingUnit, Product, ProductPrice, ProductVariant, User,
)
from app.modules.products.schemas import ProductCreate, ProductVariantCreate
from app.modules.products.variant_label import COLOR_MAX, SIZE_MAX, clean_attr, variant_label
from app.services.barcodes import AsignadorDeCodigos, barcode_en_uso

from .comun import celda_decimal, celda_texto, celda_vacia, variante_principal
from .productos import crear_producto
from .sucursales import armar_estado_por_sucursal, fijar_existencia
from .variantes import crear_variantes, pareja_repetida

TASA_IVA_DEFAULT = Decimal("16.0")
KARDEX_UPLOAD = ("Excel Upload", "Carga Masiva (Inicial)")


class FilaInvalida(Exception):
    """Fila rechazada por una validación de negocio.

    Se lanza en vez de `continue`: salir del `with db.begin_nested()` por la
    puerta buena hace RELEASE SAVEPOINT (confirma lo ya escrito en esa fila);
    la excepción hace ROLLBACK TO SAVEPOINT.
    """


@dataclass
class ContextoImportacion:
    org_id: int
    user: User
    target_branch_id: Optional[int]        # dónde cae el "Stock" del archivo
    sucursales: list[int]                  # dónde queda habilitado (scope)
    dept_map: dict[str, str]
    brand_map: dict[str, str]
    has_pkg_cols: bool
    has_tier_cols: bool
    asignador: AsignadorDeCodigos
    # (nombre_lower, department_id) -> (Product, id de su variante principal)
    # creado en esta misma carga con Color/Talla; solo se registra cuando la
    # fila entera terminó bien (si no, apuntaría a un objeto ya revertido).
    productos_cargados: dict = field(default_factory=dict)


@dataclass
class ResultadoFila:
    accion: str              # "NEW" | "UPDATE" | "SKIP"
    sku: str
    nombre: str
    precio: Optional[float]


def _sku_de_la_fila(fila: dict) -> str:
    sku = celda_texto(fila.get("sku")).strip()
    if sku.endswith(".0"):   # Excel convierte "1001" en 1001.0
        sku = sku[:-2]
    return sku


def _variante_viva_por_sku(db: Session, org_id: int, sku: str) -> Optional[ProductVariant]:
    return (
        db.query(ProductVariant)
        .join(Product, Product.id == ProductVariant.product_id)
        .filter(
            func.lower(ProductVariant.sku) == sku.lower(),
            Product.organization_id == org_id,
            ProductVariant.deleted_at.is_(None),
        )
        .order_by((ProductVariant.sku == sku).desc())   # la de mayúsculas exactas primero
        .first()
    )


def _id_de_catalogo(db: Session, ctx: ContextoImportacion, modelo, mapa: dict[str, str],
                    nuevos: dict[str, str], nombre: str) -> Optional[str]:
    """Departamento/marca por nombre; se crea en la org si no existe (el
    upload siempre lo hizo así: el archivo ES el catálogo).

    Lo creado va a `nuevos`, no a `mapa`: si la fila falla, su SAVEPOINT
    revierte el registro y el mapa no debe quedarse con un id fantasma.
    """
    if not nombre:
        return None
    clave = nombre.lower()
    if clave in mapa:
        return mapa[clave]
    if clave not in nuevos:
        nuevo = modelo(name=nombre, organization_id=ctx.org_id)
        db.add(nuevo)
        db.flush()
        nuevos[clave] = nuevo.id
    return nuevos[clave]


def _tasa_iva(fila: dict, sku: str) -> Optional[Decimal]:
    """Columna opcional `Tasa IVA` (0–100). None = celda ausente o vacía."""
    cruda = fila.get("tasa iva")
    if celda_vacia(cruda) or celda_texto(cruda) == "":
        return None
    tasa = celda_decimal(cruda, Decimal(-1))
    if tasa < 0 or tasa > 100:
        raise FilaInvalida(f"'{sku}': la tasa de IVA debe estar entre 0 y 100.")
    return tasa


def _atributos(fila: dict, sku: str) -> tuple[Optional[str], Optional[str]]:
    try:
        return (clean_attr(celda_texto(fila.get("color")), COLOR_MAX),
                clean_attr(celda_texto(fila.get("talla")), SIZE_MAX))
    except ValueError as e:
        raise FilaInvalida(f"'{sku}': color/talla {e}")


def _validar_barcode_de_fila(db: Session, ctx: ContextoImportacion, sku: str,
                             barcode: Optional[str], excepto_id: Optional[str] = None) -> None:
    """Mismo texto de siempre (sin acento en "codigo": hay pruebas que lo buscan así)."""
    if barcode and barcode_en_uso(db, ctx.org_id, barcode, excepto_id=excepto_id):
        raise FilaInvalida(f"'{sku}': el codigo de barras '{barcode}' ya lo tiene otra variante.")


def _crear_desde_fila(db: Session, ctx: ContextoImportacion, fila: dict, sku: str, nombre: str,
                      dept_id: Optional[str], brand_id: Optional[str], precio: Decimal, costo: Decimal,
                      has_iva: bool, tasa_iva: Decimal, barcode: Optional[str],
                      color: Optional[str], talla: Optional[str]) -> Product:
    """Fila nueva = alta manual. La sucursal de existencias queda también
    habilitada, y la existencia inicial entra ahí (`branch_id`)."""
    stock = celda_decimal(fila.get("stock", -1))
    destinos = set(ctx.sucursales)
    if ctx.target_branch_id:
        destinos.add(ctx.target_branch_id)
    datos = ProductCreate(
        name=nombre,
        description=celda_texto(fila.get("descripcion", "")),
        unit=celda_texto(fila.get("unidad", "pza")) or "pza",
        sku=sku,
        barcode=barcode,
        color=color,
        size=talla,
        price=precio,
        cost=costo,
        has_iva=has_iva,
        tax_rate=tasa_iva,
        department_id=dept_id,
        brand_id=brand_id,
        initial_stock=stock if (stock > 0 and ctx.target_branch_id) else Decimal(0),
        branch_id=ctx.target_branch_id,
        target_branch_ids=sorted(destinos) or None,
    )
    return crear_producto(
        db, ctx.org_id, ctx.user, datos,
        asignador=ctx.asignador, is_active_hq=not ctx.user.branch_id, kardex=KARDEX_UPLOAD,
    )


def _actualizar_desde_fila(db: Session, ctx: ContextoImportacion, variante: ProductVariant, fila: dict,
                           nombre: str, dept_id: Optional[str], brand_id: Optional[str],
                           precio: Decimal, costo: Decimal, has_iva: bool, tasa_iva: Optional[Decimal],
                           barcode: Optional[str], color: Optional[str], talla: Optional[str]) -> ProductVariant:
    """Celda vacía NO borra (descripción, unidad, código, color/talla): un
    archivo que viene del export trae las columnas pero no siempre el dato."""
    producto = variante.product
    if nombre:
        producto.name = nombre
    producto.department_id = dept_id
    if brand_id:
        producto.brand_id = brand_id
    descripcion = celda_texto(fila.get("descripcion", ""))
    if descripcion:
        producto.description = descripcion
    unidad = celda_texto(fila.get("unidad", ""))
    if unidad:
        producto.unit = unidad
    variante.has_iva = has_iva
    variante.price = precio
    variante.cost = costo
    if tasa_iva is not None:   # sin la columna no se pisa un 0 % ya guardado
        variante.tax_rate = tasa_iva
    if barcode and barcode != (variante.barcode or ""):
        # Un código nunca se sobrescribe con uno que ya tiene otra talla: el
        # escáner cobraría la equivocada.
        _validar_barcode_de_fila(db, ctx, variante.sku, barcode, excepto_id=variante.id)
        variante.barcode = barcode
    if color or talla:
        nueva = ((color or "").lower(), (talla or "").lower())
        actual = ((variante.color or "").lower(), (variante.size or "").lower())
        if nueva != actual and pareja_repetida(producto, color, talla, excepto_id=variante.id):
            raise FilaInvalida(
                f"'{variante.sku}': ya existe la variante {variant_label(color, talla)} en este producto"
            )
        variante.color, variante.size = color, talla
        variante.variant_name = variant_label(color, talla)
    return variante


def _habilitar_y_surtir(db: Session, ctx: ContextoImportacion, variante: ProductVariant,
                        fila: dict, es_nueva: bool) -> None:
    if ctx.sucursales:
        armar_estado_por_sucursal(db, ctx.org_id, variante, ctx.sucursales,
                                  is_active_hq=not ctx.user.branch_id)
    stock = celda_decimal(fila.get("stock", -1))   # -1 = la columna no viene
    if stock >= 0 and ctx.target_branch_id:
        fijar_existencia(
            db, ctx.org_id, variante, ctx.target_branch_id, stock, ctx.user.id,
            notas="Carga Masiva (Inicial)" if es_nueva else "Carga Masiva (Ajuste)",
        )


def _empaques_y_escalones(db: Session, ctx: ContextoImportacion, variante: ProductVariant, fila: dict) -> None:
    """Columnas E1..E3 (empaques) y P1..P5 (escalones): reemplazo completo de
    lo que haya, respetando la FK escalón -> empaque."""
    if ctx.has_tier_cols:
        # Validar antes de borrar nada: un escalón a $0 lo elegiría el POS
        # como el más barato (create/update ya lo rechazan igual).
        for i in range(1, 6):
            p_nombre = fila.get(f"p{i} nombre")
            p_val = fila.get(f"p{i} precio")
            if p_nombre and not celda_vacia(p_nombre) and p_val and not celda_vacia(p_val):
                if celda_decimal(p_val, Decimal(0)) <= 0:
                    raise FilaInvalida(
                        f"'{variante.sku}': el precio del escalón '{p_nombre}' debe ser mayor a cero.")
    if ctx.has_pkg_cols:
        if ctx.has_tier_cols:
            db.query(ProductPrice).filter(ProductPrice.variant_id == variante.id).delete(synchronize_session=False)
        else:
            db.query(ProductPrice).filter(ProductPrice.variant_id == variante.id).update(
                {ProductPrice.linked_package_id: None}, synchronize_session=False,
            )
        db.query(PackagingUnit).filter(PackagingUnit.variant_id == variante.id).delete(synchronize_session=False)
    elif ctx.has_tier_cols:
        db.query(ProductPrice).filter(ProductPrice.variant_id == variante.id).delete(synchronize_session=False)
    db.flush()

    empaques: dict[str, PackagingUnit] = {}
    if ctx.has_pkg_cols:
        for i in range(1, 4):
            e_nombre = fila.get(f"e{i} nombre")
            e_barcode = fila.get(f"e{i} barcode")
            e_qty = fila.get(f"e{i} cantidad")
            e_precio = fila.get(f"e{i} precio")
            if e_nombre and not celda_vacia(e_nombre) and e_precio and not celda_vacia(e_precio):
                pkg = PackagingUnit(
                    variant_id=variante.id,
                    name=str(e_nombre),
                    barcode=str(e_barcode) if not celda_vacia(e_barcode) else None,
                    units_per_package=celda_decimal(e_qty, Decimal(1)),
                    package_price=celda_decimal(e_precio, Decimal(0)),
                    organization_id=ctx.org_id,
                )
                db.add(pkg)
                empaques[str(e_nombre).lower()] = pkg
        db.flush()

    if ctx.has_tier_cols:
        for i in range(1, 6):
            p_nombre = fila.get(f"p{i} nombre")
            p_min = fila.get(f"p{i} min")
            p_val = fila.get(f"p{i} precio")
            p_link = fila.get(f"p{i} empaque")
            if p_nombre and not celda_vacia(p_nombre) and p_val and not celda_vacia(p_val):
                enlace = str(p_link).lower() if p_link and not celda_vacia(p_link) else None
                linked_id = None
                if enlace and enlace in empaques:
                    linked_id = empaques[enlace].id
                elif str(p_nombre).lower() in empaques:
                    linked_id = empaques[str(p_nombre).lower()].id
                db.add(ProductPrice(
                    variant_id=variante.id,
                    price_name=str(p_nombre),
                    min_quantity=celda_decimal(p_min, Decimal(1)),
                    unit_price=celda_decimal(p_val, Decimal(0)),
                    linked_package_id=linked_id,
                    organization_id=ctx.org_id,
                ))
        db.flush()


def importar_fila(db: Session, ctx: ContextoImportacion, fila: dict) -> ResultadoFila:
    """Una fila del archivo, de principio a fin. Ver docstring del módulo."""
    sku = _sku_de_la_fila(fila)
    nombre = celda_texto(fila.get("nombre"))
    if not sku:
        return ResultadoFila("SKIP", "", nombre, None)

    precio = celda_decimal(fila.get("precio base", fila.get("precio", 0)))
    # Antes de cualquier escritura: el mismo texto para filas nuevas y existentes.
    if precio <= 0:
        raise FilaInvalida(f"'{sku}': el precio debe ser mayor a cero.")
    costo = celda_decimal(fila.get("costo", 0))
    has_iva = celda_texto(fila.get("incluye iva", "no")).strip().lower() in ("si", "sí", "yes", "1", "true")
    tasa_celda = _tasa_iva(fila, sku)
    tasa_iva = TASA_IVA_DEFAULT if tasa_celda is None else tasa_celda
    nuevos_dept: dict[str, str] = {}
    nuevos_brand: dict[str, str] = {}
    dept_id = _id_de_catalogo(db, ctx, Department, ctx.dept_map, nuevos_dept,
                              celda_texto(fila.get("departamento", "General")))
    brand_id = _id_de_catalogo(db, ctx, Brand, ctx.brand_map, nuevos_brand, celda_texto(fila.get("marca", "")))
    color, talla = _atributos(fila, sku)
    con_variante = bool(color or talla)
    clave_padre = (nombre.lower(), dept_id)
    barcode = celda_texto(fila.get("codigo barras")) or None

    registrar_grupo = False
    existente = _variante_viva_por_sku(db, ctx.org_id, sku)
    if existente is not None:
        producto = existente.product
        variante = _actualizar_desde_fila(db, ctx, existente, fila, nombre, dept_id, brand_id,
                                          precio, costo, has_iva, tasa_celda, barcode, color, talla)
        accion, es_nueva = "UPDATE", False
    elif con_variante and clave_padre in ctx.productos_cargados:
        producto, principal_id = ctx.productos_cargados[clave_padre]
        # `crear_variantes` lee `producto.variants` y el PBS de la principal:
        # hay que flushear lo pendiente y refrescar la colección cacheada.
        db.flush()
        db.expire(producto, ["variants"])
        _validar_barcode_de_fila(db, ctx, sku, barcode)
        nuevas = crear_variantes(
            db, ctx.org_id, producto,
            [ProductVariantCreate(color=color, size=talla, sku=sku, barcode=barcode, price=precio, cost=costo)],
            principal_id=principal_id, asignador=ctx.asignador,
        )
        variante = nuevas[0]
        variante.has_iva = has_iva
        variante.tax_rate = tasa_iva
        accion, es_nueva = "NEW", True
    else:
        _validar_barcode_de_fila(db, ctx, sku, barcode)
        producto = _crear_desde_fila(db, ctx, fila, sku, nombre or "Producto sin Nombre", dept_id, brand_id,
                                     precio, costo, has_iva, tasa_iva, barcode, color, talla)
        variante = variante_principal(producto)
        accion, es_nueva = "NEW", True
        registrar_grupo = con_variante

    _habilitar_y_surtir(db, ctx, variante, fila, es_nueva)
    _empaques_y_escalones(db, ctx, variante, fila)
    # Recién ahora (fila sin excepciones) el catálogo creado pasa a los mapas.
    ctx.dept_map.update(nuevos_dept)
    ctx.brand_map.update(nuevos_brand)
    if registrar_grupo:
        # Recién ahora: la fila entera terminó sin excepciones.
        ctx.productos_cargados[clave_padre] = (producto, variante.id)
    return ResultadoFila(accion, variante.sku, nombre or producto.name, float(precio))
