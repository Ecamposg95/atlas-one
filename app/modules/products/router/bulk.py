"""``POST /api/products/batch-action`` — bulk activate / deactivate / approve.

Sprint 5b split — extracted verbatim from the original ``products.py``.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.tenant_context import get_current_active_organization
from app.models import Product, User
from app.core.security import get_current_user
from app.core.security.channel_keys import canal_activo
from app.crud.products import _is_admin, query_visible_products
from app.modules.products.schemas import BatchActionRequest
from app.modules.products.services import web as web_svc

router = APIRouter()


# -----------------------------
# 5. Batch Actions
# -----------------------------
@router.post("/batch-action")
def batch_products_action(
    req: BatchActionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    """
    Handles bulk operations on products: delete, activate, deactivate, approve.
    Strictly scoped to current organization.

    Track 3 (POS bug-fix): el cajero tiene control avanzado del catálogo en
    su tienda. La invariante multi-tenant (Product.organization_id == org_id)
    sigue intacta — un cajero solo puede afectar productos de su organización.
    """
    from ._shared import _PRODUCT_ADVANCED_ROLES
    if current_user.role not in _PRODUCT_ADVANCED_ROLES:
        raise HTTPException(
            status_code=403,
            detail="No autorizado para acciones masivas",
        )

    q = db.query(Product).filter(
        Product.id.in_(req.ids),
        Product.organization_id == org_id
    )

    # ATS-27: Filter to rows that actually need changing so processed == real count
    if req.action == 'delete' or req.action == 'deactivate':
        processed = q.filter(Product.is_active == True).update({"is_active": False}, synchronize_session=False)

    elif req.action == 'activate':
        processed = q.filter(Product.is_active == False).update({"is_active": True}, synchronize_session=False)

    elif req.action == 'approve':
        processed = q.filter(Product.approval_status != 'APPROVED').update({"approval_status": 'APPROVED'}, synchronize_session=False)

    else:
        raise HTTPException(status_code=400, detail="Acción no válida")

    db.commit()
    if processed == 0:
        return {"status": "ok", "processed": 0, "message": "Ningún producto fue modificado (ya tenían ese estado)."}
    return {"status": "ok", "processed": processed}


# -----------------------------
# Publicar en la tienda web (canal tienda_en_linea)
# -----------------------------
class FiltroPublicacion(BaseModel):
    search: Optional[str] = None
    brand_id: Optional[str] = None
    department_id: Optional[str] = None


class WebPublishRequest(BaseModel):
    ids: Optional[List[str]] = None
    filtro: Optional[FiltroPublicacion] = None
    published: bool


@router.post("/web-publish")
def web_publish(
    req: WebPublishRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Publica o despublica productos en la tienda en línea, por `ids` o por
    `filtro` (mismas reglas que `GET /api/products/`: search/marca/departamento,
    solo productos activos de la org). Solo ADMINISTRADOR/DUEÑO."""
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Solo administración puede publicar en la tienda en línea")
    if not canal_activo(db, org_id):
        raise HTTPException(status_code=404, detail="El canal Tienda en línea no está activo")

    if req.ids is not None:
        ids = list(dict.fromkeys(req.ids))
    elif req.filtro is not None:
        f = req.filtro
        q = query_visible_products(db, current_user, org_id, search=f.search or None)
        if f.department_id:
            q = q.filter(Product.department_id == f.department_id)
        if f.brand_id:
            q = q.filter(Product.brand_id == f.brand_id)
        ids = [r[0] for r in q.with_entities(Product.id).distinct().all()]
    else:
        raise HTTPException(status_code=422, detail="Indica `ids` o `filtro`")

    processed = web_svc.publicar_en_web(db, org_id, ids, req.published)
    db.commit()
    return {"processed": processed}
