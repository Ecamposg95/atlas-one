"""Soporte de catálogo para la tienda web (canal tienda_en_linea)."""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.modules.products.imagenes import ProductImage, adoptar_imagen_heredada
from app.modules.products.models import Department, Product


def tocar_producto(db: Session, product_id: str) -> None:
    """Sube `products.updated_at` a ahora. La tienda web sincroniza por
    `updated_at`: editar una variante (precio, talla…) debe mover al padre.
    Sin commit. UPDATE directo: no depende de que el producto esté cargado."""
    db.query(Product).filter(Product.id == product_id).update(
        {Product.updated_at: datetime.now(timezone.utc)}, synchronize_session=False,
    )


def validar_padre(db: Session, org_id: int, dept_id: Optional[str], parent_id: Optional[str]) -> None:
    """Valida `parent_id` de un departamento (máx. dos niveles). 422 si el padre
    es de otra org o no existe, si es el mismo departamento o un descendiente
    (ciclo), si el padre ya tiene padre (tercer nivel) o si el departamento ya
    tiene hijos (se volvería de nivel 2 con hijos)."""
    if not parent_id:
        return
    if dept_id and parent_id == dept_id:
        raise HTTPException(status_code=422, detail="Un departamento no puede ser su propio padre")
    padre = db.query(Department).filter(
        Department.id == parent_id, Department.organization_id == org_id,
    ).first()
    if padre is None:
        raise HTTPException(status_code=422, detail="El departamento padre no existe")
    if padre.parent_id:
        if dept_id and padre.parent_id == dept_id:
            raise HTTPException(status_code=422, detail="El departamento padre es hijo de este: sería un ciclo")
        raise HTTPException(status_code=422, detail="Solo se permiten dos niveles de departamentos")
    if dept_id:
        tiene_hijos = db.query(Department.id).filter(
            Department.parent_id == dept_id, Department.organization_id == org_id,
        ).first()
        if tiene_hijos:
            raise HTTPException(status_code=422, detail="Este departamento ya tiene subdepartamentos: no puede tener padre")


# ── Galería de imágenes ──────────────────────────────────────────────────────
def imagenes_vivas(db: Session, org_id: int, product_id: str) -> list[ProductImage]:
    """Imágenes no borradas del producto, en orden de galería."""
    return (
        db.query(ProductImage)
        .filter(ProductImage.product_id == product_id,
                ProductImage.organization_id == org_id,
                ProductImage.deleted_at.is_(None))
        .order_by(ProductImage.position, ProductImage.created_at)
        .all()
    )


def sincronizar_image_url(db: Session, product: Product) -> None:
    """Deja `products.image_url` = URL de la imagen primaria (o NULL si no hay)
    y sube `updated_at`. Garantiza una sola primaria: si ninguna lo es, la
    primera de la galería pasa a serlo. Sin commit."""
    db.flush()  # la sesión no hace autoflush: que la consulta vea lo recién agregado
    imgs = imagenes_vivas(db, product.organization_id, product.id)
    primaria = next((i for i in imgs if i.is_primary), None)
    if primaria is None and imgs:
        primaria = imgs[0]
        primaria.is_primary = True
    for i in imgs:
        if i is not primaria and i.is_primary:
            i.is_primary = False
    product.image_url = primaria.url if primaria else None
    db.flush()
    tocar_producto(db, product.id)


def agregar_imagen(db: Session, product: Product, url: str, alt: Optional[str] = None) -> ProductImage:
    """Agrega una imagen al final de la galería; la primera queda primaria.
    Una `image_url` heredada se adopta antes y sigue siendo la primaria."""
    adoptar_imagen_heredada(db, product)
    imgs = imagenes_vivas(db, product.organization_id, product.id)
    img = ProductImage(
        id=str(uuid.uuid4()), organization_id=product.organization_id,
        product_id=product.id, url=url, alt=alt,
        position=(max((i.position for i in imgs), default=-1) + 1),
        is_primary=not imgs,
    )
    db.add(img)
    sincronizar_image_url(db, product)
    return img


def fijar_imagen_primaria(db: Session, product: Product, url: str) -> None:
    """Camino legacy (`POST /{id}/image`): crea o reemplaza la primaria."""
    adoptar_imagen_heredada(db, product)
    imgs = imagenes_vivas(db, product.organization_id, product.id)
    primaria = next((i for i in imgs if i.is_primary), None)
    if primaria is not None:
        primaria.url = url
    else:
        db.add(ProductImage(
            id=str(uuid.uuid4()), organization_id=product.organization_id,
            product_id=product.id, url=url,
            position=(min((i.position for i in imgs), default=1) - 1), is_primary=True,
        ))
        for i in imgs:
            i.is_primary = False
    sincronizar_image_url(db, product)


def borrar_imagen(db: Session, product: Product, image_id: str) -> None:
    """Soft delete; si era la primaria, la siguiente toma su lugar."""
    adoptar_imagen_heredada(db, product)
    img = next((i for i in imagenes_vivas(db, product.organization_id, product.id)
                if i.id == image_id), None)
    if img is None:
        raise HTTPException(status_code=404, detail="Imagen no encontrada")
    img.deleted_at = datetime.now(timezone.utc)
    img.is_primary = False
    db.flush()
    sincronizar_image_url(db, product)


def ordenar_imagenes(db: Session, product: Product, ids: list[str], primary_id: str) -> None:
    """Reordena la galería. `ids` debe ser exactamente el conjunto de imágenes
    vivas del producto (422 si trae ajenas o faltan) y `primary_id` una de ellas."""
    adoptar_imagen_heredada(db, product)
    imgs = {i.id: i for i in imagenes_vivas(db, product.organization_id, product.id)}
    if len(set(ids)) != len(ids) or set(ids) != set(imgs):
        raise HTTPException(status_code=422, detail="La lista debe traer todas las imágenes del producto, sin repetir")
    if primary_id not in imgs:
        raise HTTPException(status_code=422, detail="La imagen principal no pertenece al producto")
    for pos, iid in enumerate(ids):
        imgs[iid].position = pos
        imgs[iid].is_primary = iid == primary_id
    db.flush()
    sincronizar_image_url(db, product)


# ── Publicación ──────────────────────────────────────────────────────────────
LOTE_PUBLICACION = 500


def publicar_en_web(db: Session, org_id: int, ids: list[str], published: bool) -> int:
    """Publica/despublica productos de la org en lotes. `web_published_at` se
    fija solo al pasar de no publicado a publicado. Siempre sube `updated_at`
    (la tienda sincroniza por ahí). Devuelve cuántos productos propios tocó.
    Sin commit."""
    ahora = datetime.now(timezone.utc)
    procesados = 0
    for i in range(0, len(ids), LOTE_PUBLICACION):
        lote = ids[i:i + LOTE_PUBLICACION]
        q = db.query(Product).filter(Product.id.in_(lote), Product.organization_id == org_id)
        propios = [r[0] for r in q.with_entities(Product.id).all()]
        if not propios:
            continue
        base = db.query(Product).filter(Product.id.in_(propios))
        if published:
            base.filter(Product.web_published.is_(False) | Product.web_published_at.is_(None)).update(
                {Product.web_published: True, Product.web_published_at: ahora},
                synchronize_session=False)
        else:
            base.update({Product.web_published: False}, synchronize_session=False)
        base.update({Product.updated_at: ahora}, synchronize_session=False)
        procesados += len(propios)
    return procesados
