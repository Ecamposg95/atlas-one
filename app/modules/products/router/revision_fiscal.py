"""``GET /api/products/revision-fiscal`` y su CSV: productos sin tasa de IVA
del SAT o con discrepancia contra sus banderas de cobro, por sucursal.

Solo lectura. Administrador y dueño ven todas las sucursales (y pueden acotar
a una con `branch_id`); cualquier otro rol, solo la suya. La regla vive en
`app/modules/products/services/revision_fiscal.py`.
"""
from __future__ import annotations

import csv
import io
from dataclasses import asdict
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.tenant_context import get_current_active_organization
from app.crud.products import _is_admin
from app.models import User
from app.modules.products.services.revision_fiscal import (
    DISCREPANCIA,
    PROBLEMAS,
    revisar_catalogo,
    resumen_por_sucursal,
)

router = APIRouter()

ENCABEZADOS_CSV = [
    "Sucursal", "Producto", "SKU", "Problema", "Qué ajustar",
    "Tasa de IVA (datos fiscales)", "Objeto de impuesto", "Aplica IVA", "Tasa IVA (%)",
]


def _sucursales_del_usuario(user: User, branch_id: Optional[int]) -> Optional[set[int]]:
    if _is_admin(user):
        return {branch_id} if branch_id is not None else None
    if not user.branch_id:
        raise HTTPException(status_code=403, detail="Tu usuario no tiene sucursal asignada.")
    if branch_id is not None and branch_id != user.branch_id:
        raise HTTPException(status_code=403, detail="Solo puedes revisar los productos de tu sucursal.")
    return {user.branch_id}


def _validar_problema(problema: Optional[str]) -> Optional[str]:
    if problema is None:
        return None
    valor = problema.strip().upper()
    if valor not in PROBLEMAS:
        raise HTTPException(status_code=422, detail="El problema debe ser SIN_CLASIFICACION o DISCREPANCIA.")
    return valor


@router.get("/revision-fiscal")
def revision_fiscal(
    branch_id: Optional[int] = None,
    problema: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Resumen por sucursal (siempre completo) y renglones paginados."""
    hallazgos = revisar_catalogo(db, org_id, _sucursales_del_usuario(current_user, branch_id))
    filtro = _validar_problema(problema)
    filtrados = [h for h in hallazgos if filtro is None or h.problema == filtro]
    return {
        "resumen": resumen_por_sucursal(hallazgos),
        "items": [asdict(h) for h in filtrados[offset:offset + limit]],
        "total": len(filtrados),
        "limit": limit,
        "offset": offset,
    }


@router.get("/export/revision-fiscal.csv")
def revision_fiscal_csv(
    branch_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """La lista completa para abrirla en Excel y repartirla a las tiendas."""
    hallazgos = revisar_catalogo(db, org_id, _sucursales_del_usuario(current_user, branch_id))
    salida = io.StringIO()
    escritor = csv.writer(salida)
    escritor.writerow(ENCABEZADOS_CSV)
    for h in hallazgos:
        escritor.writerow([
            h.branch_name, h.producto, h.sku,
            "Discrepancia" if h.problema == DISCREPANCIA else "Sin clasificar",
            h.detalle, h.iva_tratamiento or "", h.sat_objeto_imp or "",
            "Sí" if h.has_iva else "No", h.tax_rate or "",
        ])
    # BOM: Excel en español abre el UTF-8 con acentos solo si lo trae.
    return Response(
        content="﻿" + salida.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="revision_fiscal_{date.today().isoformat()}.csv"'},
    )
