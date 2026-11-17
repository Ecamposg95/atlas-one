"""``/api/canal/config`` — configuración del canal «Tienda en línea».

Las sucursales que alimentan la tienda viven en
``organization_modules.config_json["sucursales_web"]``: lista de ids, o ausente
/ ``null`` = todas las que venden.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.security.channel_keys import MODULO_CANAL, canal_activo
from app.core.tenant_context import get_current_active_organization
from app.crud.products import _is_admin
from app.models import User
from app.models.modules import OrganizationModule
from app.models.organization import Branch
from app.modules.canal.services import al_cambiar_sucursales

router = APIRouter()


class ConfigUpdate(BaseModel):
    sucursales_web: Optional[List[int]] = None


def _solo_admin(user: User) -> None:
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Solo administración puede configurar el canal")


def _fila_modulo(db: Session, org_id: int) -> Optional[OrganizationModule]:
    return db.query(OrganizationModule).filter(
        OrganizationModule.organization_id == org_id,
        OrganizationModule.module_key == MODULO_CANAL,
    ).first()


def _sucursales(db: Session, org_id: int) -> list[Branch]:
    return (
        db.query(Branch)
        .filter(Branch.organization_id == org_id, Branch.is_active.is_(True))
        .order_by(Branch.id)
        .all()
    )


@router.get("/config")
def leer_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    _solo_admin(current_user)
    if not canal_activo(db, org_id):
        return {"activo": False, "sucursales_web": None, "sucursales": []}
    fila = _fila_modulo(db, org_id)
    cfg = (fila.config_json if fila else None) or {}
    return {
        "activo": True,
        "sucursales_web": cfg.get("sucursales_web"),
        "sucursales": [
            {"id": b.id, "name": b.name, "can_sell": bool(b.can_sell)}
            for b in _sucursales(db, org_id)
        ],
    }


@router.put("/config")
def guardar_config(
    body: ConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    _solo_admin(current_user)
    if not canal_activo(db, org_id):
        raise HTTPException(status_code=404, detail="El canal Tienda en línea no está activo")
    fila = _fila_modulo(db, org_id)
    if fila is None:
        raise HTTPException(status_code=404, detail="El canal Tienda en línea no está activo")

    ids = None
    if body.sucursales_web is not None:
        ids = sorted(set(body.sucursales_web))
        propias = {b.id for b in db.query(Branch.id).filter(Branch.organization_id == org_id).all()}
        ajenas = [i for i in ids if i not in propias]
        if ajenas:
            raise HTTPException(status_code=422, detail=f"Sucursales que no son de la organización: {ajenas}")

    cfg = dict(fila.config_json or {})
    cfg["sucursales_web"] = ids
    fila.config_json = cfg
    flag_modified(fila, "config_json")
    al_cambiar_sucursales(db, org_id)
    db.commit()
    return {"activo": True, "sucursales_web": ids}
