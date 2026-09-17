"""``/api/products/*`` router package.

Split from a single 3.4k-line ``products.py`` in Sprint 5b. The aggregator
preserves the original parent-router contract — ``main.py`` continues to
mount this package via
``include_router(products.router, prefix="/api/products", tags=["Catálogo"])``.

Python prefers the package over a sibling ``products.py``, so existing
imports (``from app.routers import products``, ``from app.routers.products
import list_departments``) keep working unchanged.

This module also re-exports the historical ``departments_router`` and
``brands_router`` instances. They live under the bounded context of
products (Department/Brand FK → Product) but are mounted at
``/api/departments`` and ``/api/brands`` for backwards compatibility with
the frontend (Fase A cleanup).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List

from app.core.database import get_db
from app.core.tenant_context import get_current_active_organization
from app.models import Product, Department, Brand, User
from app.core.security import get_current_user
from app.schemas.departments import (
    DepartmentCreate, DepartmentUpdate, DepartmentResponse,
)
from app.schemas.brands import BrandCreate, BrandUpdate, BrandResponse

from . import (
    core,
    departments,
    stats,
    search,
    packaging,
    branch_status,
    bulk,
    import_export,
    reports,
    audit,
    variants,
)

router = APIRouter()
router.include_router(core.router)
router.include_router(departments.router)
router.include_router(stats.router)
router.include_router(search.router)
router.include_router(packaging.router)
router.include_router(branch_status.router)
router.include_router(bulk.router)
router.include_router(import_export.router)
router.include_router(reports.router)
router.include_router(audit.router)
router.include_router(variants.router)


# ═════════════════════════════════════════════════════════════════════════════
# DEPARTMENTS — consolidado desde app/routers/departments.py (Fase A cleanup).
# Viven bajo el bounded context de productos (Department FK → Product). El
# montaje en main.py preserva el prefix histórico /api/departments para no
# romper al frontend.
# ═════════════════════════════════════════════════════════════════════════════

departments_router = APIRouter()


@departments_router.get("/", response_model=List[DepartmentResponse])
def list_departments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    return db.query(Department).filter(Department.organization_id == org_id).all()


@departments_router.post("/", response_model=DepartmentResponse)
def create_department(
    dept: DepartmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    new_dept = Department(
        name=dept.name,
        description=dept.description,
        organization_id=org_id,
    )
    db.add(new_dept)
    db.commit()
    db.refresh(new_dept)
    return new_dept


@departments_router.put("/{dept_id}", response_model=DepartmentResponse)
def update_department(
    dept_id: str,
    dept_in: DepartmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    dept = db.query(Department).filter(
        Department.id == dept_id,
        Department.organization_id == org_id,
    ).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Departamento no encontrado")
    if dept_in.name is not None:
        dept.name = dept_in.name
    if dept_in.description is not None:
        dept.description = dept_in.description
    db.commit()
    db.refresh(dept)
    return dept


@departments_router.delete("/{dept_id}")
def delete_department(
    dept_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    dept = db.query(Department).filter(
        Department.id == dept_id,
        Department.organization_id == org_id,
    ).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Departamento no encontrado")
    db.delete(dept)
    db.commit()
    return {"status": "ok"}


# ═════════════════════════════════════════════════════════════════════════════
# BRANDS — consolidado desde app/routers/brands.py (Fase A cleanup).
# Viven bajo el bounded context de productos (Brand FK → Product). El
# montaje en main.py preserva el prefix histórico /api/brands para no
# romper al frontend.
# ═════════════════════════════════════════════════════════════════════════════

brands_router = APIRouter()


@brands_router.get("/", response_model=List[BrandResponse])
def list_brands(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    brands = db.query(Brand).filter(Brand.organization_id == org_id).all()

    counts = dict(
        db.query(Product.brand_id, func.count(Product.id))
        .filter(Product.organization_id == org_id, Product.brand_id != None)
        .group_by(Product.brand_id)
        .all()
    )

    return [
        BrandResponse(
            id=str(b.id),
            name=b.name,
            logo_url=b.logo_url,
            product_count=counts.get(str(b.id), 0),
        )
        for b in brands
    ]


@brands_router.post("/", response_model=BrandResponse)
def create_brand(
    brand: BrandCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    new_brand = Brand(name=brand.name, logo_url=brand.logo_url, organization_id=org_id)
    db.add(new_brand)
    db.commit()
    db.refresh(new_brand)
    return BrandResponse(
        id=str(new_brand.id),
        name=new_brand.name,
        logo_url=new_brand.logo_url,
        product_count=0,
    )


@brands_router.put("/{brand_id}", response_model=BrandResponse)
def update_brand(
    brand_id: str,
    brand_in: BrandUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    brand = db.query(Brand).filter(
        Brand.id == brand_id,
        Brand.organization_id == org_id,
    ).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Marca no encontrada")

    brand.name = brand_in.name
    if brand_in.logo_url is not None:
        brand.logo_url = brand_in.logo_url

    db.commit()
    db.refresh(brand)

    count = db.query(func.count(Product.id)).filter(
        Product.organization_id == org_id,
        Product.brand_id == brand_id,
    ).scalar() or 0

    return BrandResponse(
        id=str(brand.id),
        name=brand.name,
        logo_url=brand.logo_url,
        product_count=count,
    )


@brands_router.delete("/{brand_id}")
def delete_brand(
    brand_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    brand = db.query(Brand).filter(
        Brand.id == brand_id,
        Brand.organization_id == org_id,
    ).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Marca no encontrada")

    db.delete(brand)
    db.commit()
    return {"status": "ok"}
