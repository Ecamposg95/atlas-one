"""``GET /api/products/facets`` — opciones de los filtros avanzados del catálogo.

Las tallas y los colores salen del catálogo de la organización (no de la
página cargada), para que el filtro ofrezca todo lo que existe aunque la lista
sea paginada. Mismo alcance de visibilidad que la lista: un rol de sucursal
solo ve las tallas de lo que su sucursal vende.

Va en su propio sub-router, registrado ANTES de `core.router`: al revés,
`GET /{product_id}` capturaría "facets" y respondería 404.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.tenant_context import get_current_active_organization
from app.crud.products import query_visible_products
from app.models import Product, User
from app.modules.products.filtros_avanzados import facetas

router = APIRouter()


@router.get("/facets")
def leer_facetas(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """`{"sizes": [...], "colors": [...]}`: tallas en orden de escala (CH, M,
    G…, luego números) y colores en orden alfabético, cada uno una sola vez."""
    # include_inactive: para admin incluye archivados (el filtro también se usa
    # con "Incluir archivados"); `query_visible_products` lo ignora para el resto.
    visibles = (
        query_visible_products(db, current_user, org_id, include_inactive=True)
        .with_entities(Product.id)
        .subquery()
    )
    return facetas(db, org_id, visibles.select())
