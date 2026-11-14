"""Soporte de catálogo para la tienda web (canal tienda_en_linea)."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

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
