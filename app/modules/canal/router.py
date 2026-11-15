"""API de catálogo de solo lectura del canal «Tienda en línea».

Prefijo ``/api/channel/v1``; autentica con llave de servidor (scope
``catalog:read``). Paginación por cursor ``(updated_at, id)``; ``server_time``
se toma antes de consultar. Detalle: docs/API_REFERENCE.md.
"""
from datetime import datetime, timezone
from typing import Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.security.channel_keys import ChannelContext, require_channel_key
from app.models.products import Product, ProductVariant
from app.modules.canal.cursor import codificar_cursor, decodificar_cursor
from app.modules.canal.models import ChannelAvailability
from app.modules.canal.schemas import (
    CanalBaja, CanalDepartamento, CanalDisponibilidad, CanalImagen, CanalMarca,
    CanalProducto, CanalVariante, Pagina,
)
from app.modules.products.imagenes import ProductImage
from app.modules.products.models import Brand, Department

router = APIRouter()

_auth = require_channel_key("catalog:read")


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    """SQLite devuelve fechas sin zona; todo se emite en UTC explícito."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _pagina(db: Session, q, ts_col, id_col, limit: int, cursor: Optional[str],
            updated_since: Optional[datetime]):
    """Aplica `updated_since`, cursor, orden y limit+1. Devuelve (filas, hay_mas)."""
    if updated_since is not None:
        q = q.filter(ts_col >= _utc(updated_since))
    if cursor:
        t, i = decodificar_cursor(cursor)
        q = q.filter(or_(ts_col > t, and_(ts_col == t, id_col > i)))
    filas = q.order_by(ts_col, id_col).limit(limit + 1).all()
    return filas[:limit], len(filas) > limit


def _siguiente(filas, hay_mas: bool, ts_attr: str, id_attr: str) -> Optional[str]:
    if not hay_mas or not filas:
        return None
    ult = filas[-1]
    return codificar_cursor(_utc(getattr(ult, ts_attr)), getattr(ult, id_attr))


def _parametros(updated_since: Optional[datetime] = Query(None),
                cursor: Optional[str] = Query(None),
                limit: int = Query(100, ge=1, le=200)):
    return updated_since, cursor, limit


# ── Marcas y departamentos ───────────────────────────────────────────────────
def _catalogo_simple(db, ctx, modelo, params, fabrica):
    updated_since, cursor, limit = params
    server_time = _ahora()
    q = db.query(modelo).filter(modelo.organization_id == ctx.organization_id)
    if updated_since is None:
        q = q.filter(modelo.deleted_at.is_(None))
    filas, hay_mas = _pagina(db, q, modelo.updated_at, modelo.id, limit, cursor, updated_since)
    items = [
        CanalBaja(id=f.id, updated_at=_utc(f.updated_at)) if f.deleted_at is not None else fabrica(f)
        for f in filas
    ]
    return Pagina(items=items, next_cursor=_siguiente(filas, hay_mas, "updated_at", "id"),
                  server_time=server_time)


@router.get("/brands", response_model=Pagina[Union[CanalMarca, CanalBaja]])
def listar_marcas(params=Depends(_parametros), ctx: ChannelContext = Depends(_auth),
                  db: Session = Depends(get_db)):
    return _catalogo_simple(db, ctx, Brand, params, lambda b: CanalMarca(
        id=b.id, name=b.name, logo_url=b.logo_url, is_premium=bool(b.is_premium),
        updated_at=_utc(b.updated_at)))


@router.get("/departments", response_model=Pagina[Union[CanalDepartamento, CanalBaja]])
def listar_departamentos(params=Depends(_parametros), ctx: ChannelContext = Depends(_auth),
                         db: Session = Depends(get_db)):
    return _catalogo_simple(db, ctx, Department, params, lambda d: CanalDepartamento(
        id=d.id, name=d.name, parent_id=d.parent_id, updated_at=_utc(d.updated_at)))


# ── Productos ────────────────────────────────────────────────────────────────
def _vivo(p: Product) -> bool:
    return bool(p.web_published) and p.is_active is not False and p.deleted_at is None \
        and (p.approval_status or "APPROVED") == "APPROVED"


def _armar(db: Session, ctx: ChannelContext, productos: list[Product]) -> list:
    """CanalProducto / CanalBaja por producto, con consultas en lote
    (imágenes, disponibilidad) sin N+1."""
    vivos = [p for p in productos if _vivo(p)]
    ids = [p.id for p in vivos]
    imagenes: dict[str, list] = {}
    disp: dict[str, bool] = {}
    if ids:
        for img in (db.query(ProductImage)
                    .filter(ProductImage.product_id.in_(ids),
                            ProductImage.organization_id == ctx.organization_id,
                            ProductImage.deleted_at.is_(None))
                    .order_by(ProductImage.position, ProductImage.id)):
            imagenes.setdefault(img.product_id, []).append(img)
        vids = [v.id for p in vivos for v in p.variants]
        if vids:
            for vid, a in (db.query(ChannelAvailability.variant_id, ChannelAvailability.available)
                           .filter(ChannelAvailability.organization_id == ctx.organization_id,
                                   ChannelAvailability.variant_id.in_(vids))):
                disp[vid] = bool(a)
            faltan = {v for v in vids if v not in disp}
            if faltan:
                # Sin fila: cálculo en vivo en lote (una consulta por tabla, no por variante).
                from app.services.canal_disponibilidad import _calcular, sucursales_web
                web = sucursales_web(db, ctx.organization_id)
                with db.no_autoflush:
                    for vid, (_pid, d) in _calcular(db, ctx.organization_id, faltan, web).items():
                        disp[vid] = d
    salida = []
    for p in productos:
        if not _vivo(p):
            salida.append(CanalBaja(id=p.id, updated_at=_utc(p.updated_at)))
            continue
        variantes = [CanalVariante(id=v.id, sku=v.sku, color=v.color, size=v.size,
                                   available=disp.get(v.id, False)) for v in p.variants]
        salida.append(CanalProducto(
            id=p.id, name=p.name, description=p.description, brand_id=p.brand_id,
            department_id=p.department_id, gender=p.gender, model=p.model,
            material=p.material, available=any(v.available for v in variantes),
            images=_imagenes(p, imagenes.get(p.id, [])),
            variants=variantes, updated_at=_utc(p.updated_at),
            web_published_at=_utc(p.web_published_at)))
    return salida


def _imagenes(p: Product, galeria: list) -> list[CanalImagen]:
    """Galería del producto; sin galería, la foto suelta `image_url` como principal."""
    if galeria:
        return [CanalImagen(url=i.url, alt=i.alt, position=i.position or 0,
                            is_primary=bool(i.is_primary)) for i in galeria]
    if p.image_url:
        return [CanalImagen(url=p.image_url, alt=None, position=0, is_primary=True)]
    return []


def _consulta_productos(db: Session, ctx: ChannelContext):
    return (db.query(Product)
            .options(selectinload(Product.variants.and_(ProductVariant.deleted_at.is_(None))))
            .filter(Product.organization_id == ctx.organization_id))


@router.get("/products", response_model=Pagina[Union[CanalProducto, CanalBaja]])
def listar_productos(params=Depends(_parametros), ctx: ChannelContext = Depends(_auth),
                     db: Session = Depends(get_db)):
    updated_since, cursor, limit = params
    server_time = _ahora()
    q = _consulta_productos(db, ctx)
    if updated_since is None:
        q = q.filter(Product.web_published.is_(True), Product.is_active.isnot(False),
                     Product.deleted_at.is_(None),
                     or_(Product.approval_status.is_(None), Product.approval_status == "APPROVED"))
    else:
        # Alguna vez publicado: vivo -> completo, ya no -> baja. Nunca publicado: no existe.
        q = q.filter(Product.web_published_at.isnot(None))
    filas, hay_mas = _pagina(db, q, Product.updated_at, Product.id, limit, cursor, updated_since)
    return Pagina(items=_armar(db, ctx, filas),
                  next_cursor=_siguiente(filas, hay_mas, "updated_at", "id"),
                  server_time=server_time)


@router.get("/products/{product_id}", response_model=Union[CanalProducto, CanalBaja])
def obtener_producto(product_id: str, ctx: ChannelContext = Depends(_auth),
                     db: Session = Depends(get_db)):
    p = _consulta_productos(db, ctx).filter(Product.id == product_id).first()
    if p is None or p.web_published_at is None:
        raise HTTPException(404, "Producto no encontrado")
    return _armar(db, ctx, [p])[0]


# ── Disponibilidad ───────────────────────────────────────────────────────────
@router.get("/availability", response_model=Pagina[CanalDisponibilidad])
def listar_disponibilidad(params=Depends(_parametros), ctx: ChannelContext = Depends(_auth),
                          db: Session = Depends(get_db)):
    updated_since, cursor, limit = params
    server_time = _ahora()
    # Solo productos alguna vez publicados de esta org.
    q = (db.query(ChannelAvailability)
         .join(Product, Product.id == ChannelAvailability.product_id)
         .filter(ChannelAvailability.organization_id == ctx.organization_id,
                 Product.organization_id == ctx.organization_id,
                 Product.web_published_at.isnot(None)))
    filas, hay_mas = _pagina(db, q, ChannelAvailability.changed_at,
                             ChannelAvailability.variant_id, limit, cursor, updated_since)
    items = [CanalDisponibilidad(product_id=f.product_id, variant_id=f.variant_id,
                                 available=bool(f.available), changed_at=_utc(f.changed_at))
             for f in filas]
    return Pagina(items=items, next_cursor=_siguiente(filas, hay_mas, "changed_at", "variant_id"),
                  server_time=server_time)
