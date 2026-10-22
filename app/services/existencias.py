"""Umbral único de "poca existencia" (SP6 vista del dueño, 2026-10).

Antes convivían tres criterios: ≤ 5 fijo en `/reports/dashboard` y en
`/reports/command-center/stats` (y en los KPIs del catálogo), y
`organization.umbral_poca_existencia` en el Inicio básico. La dueña capturaba
su tope en Empresa y el tablero seguía marcando otra cosa. Ahora todos leen de
aquí: el tope de la empresa, o 3 piezas si nunca lo capturó.
"""
from sqlalchemy.orm import Session

from app.models.organization import Organization

UMBRAL_POR_DEFECTO = 3


def umbral_poca_existencia(db: Session, org_id: int) -> int:
    """Tope de piezas (inclusive) bajo el cual una variante "se está acabando"."""
    valor = db.query(Organization.umbral_poca_existencia).filter(Organization.id == org_id).scalar()
    return int(valor) if valor is not None else UMBRAL_POR_DEFECTO
