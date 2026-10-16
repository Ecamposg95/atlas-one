"""Crear, actualizar y duplicar productos: el cuerpo que antes vivía en
`router/core.py` (create_product, update_product, duplicate_product).

Reglas: sin `commit` (el handler confirma); `HTTPException` con los mismos
textos de siempre; toda consulta acotada a `org_id`.
"""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.crud.products import _is_admin
from app.models import PackagingUnit, Product, ProductPrice, ProductVariant, User
from app.models.platform import PlatformAuditLog
from app.modules.products.schemas import ProductCreate
from app.modules.products.variant_label import variant_label
from app.services.barcodes import AsignadorDeCodigos

from .codigos import asignar_barcode_interno, sku_de_copia, validar_barcode_libre, validar_sku_unico
from .comun import MANAGER_ROLES, variantes_vivas
from .precios import armar_empaques, armar_escalones
from .sucursales import (
    armar_estado_por_sucursal, copiar_estado_por_sucursal, registrar_stock_inicial, resolver_sucursales_destino,
    sucursal_de_existencia_inicial,
)
from .validaciones import (
    atributos_principal, exigir_campos_de_cajero, validar_departamento_y_marca,
    validar_escalones, validar_precio, validar_sucursales_de_la_org,
)
from .variantes import crear_variantes

_AMBIGUO = "Indica en qué sucursal entra la existencia inicial: no se reparte sola entre varias sucursales."


def _validar_destinos_y_rol(db: Session, org_id: int, user: User, datos: ProductCreate, es_admin: bool) -> None:
    """RBAC de sucursales: solo ADMIN/GERENTE/DUEÑO habilitan en varias; un
    usuario con sucursal (no admin) solo en la suya; toda sucursal de la org."""
    objetivo = datos.target_branch_ids or []
    if len(objetivo) > 1 and user.role not in MANAGER_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Solo administradores pueden habilitar productos en múltiples sucursales",
        )
    if not es_admin and user.branch_id and objetivo:
        for bid in objetivo:
            if bid != user.branch_id:
                raise HTTPException(
                    status_code=403,
                    detail="Solo puedes crear productos para tu sucursal asignada.",
                )
    validar_sucursales_de_la_org(db, org_id, objetivo)


def _validar_existencia_inicial(user: User, datos: ProductCreate, destinos: list[int]) -> None:
    """La existencia inicial entra en UNA sucursal. Con varias objetivo y sin
    `branch_id` no hay forma de saber cuál: se rechaza en vez de repartir a
    ciegas. Cuenta también la de las hermanas (`extra_variants`)."""
    total = (datos.initial_stock or Decimal(0)) + sum(
        (v.initial_stock or Decimal(0)) for v in (datos.extra_variants or [])
    )
    if total <= 0:
        return
    objetivo = set(datos.target_branch_ids or [])
    if len(objetivo) > 1 and datos.branch_id not in objetivo:
        raise HTTPException(status_code=422, detail=_AMBIGUO)
    # Usuario sin sucursal y sin destinos: el alta lo habilita en todas las
    # que venden; con piezas y más de una, hay que decir en cuál.
    if not objetivo and not user.branch_id and len(destinos) > 1 and datos.branch_id not in destinos:
        raise HTTPException(status_code=422, detail=_AMBIGUO)


def _auditar_alta_de_cajero(db: Session, user: User, producto: Product, principal: ProductVariant) -> None:
    """D4 — CAJERO/GERENTE creó un producto para su propia sucursal."""
    db.add(PlatformAuditLog(
        actor_user_id=user.id,
        action="PRODUCT_CREATE_CAJERO",
        entity_type="Product",
        entity_id=str(producto.id),
        payload=json.dumps({
            "branch_id": user.branch_id,
            "sku": principal.sku,
            "name": producto.name,
            "variant_id": str(principal.id),
        }),
    ))


def crear_producto(
    db: Session, org_id: int, user: User, datos: ProductCreate, *,
    asignador: Optional[AsignadorDeCodigos] = None,
    is_active_hq: bool = False,
    kardex: tuple[str, str] = ("Alta Inicial", "Creación de producto"),
) -> Product:
    """Alta completa: producto + variante principal (+ hermanas), código
    interno, estado por sucursal, existencia inicial, empaques y escalones.

    `asignador`/`is_active_hq`/`kardex` los pasa la importación (un asignador
    por archivo; HQ cotiza lo que importa; texto del kardex de siempre).
    Sin commit.
    """
    es_admin = _is_admin(user)
    if not es_admin:
        if not user.branch_id:
            raise HTTPException(
                status_code=403,
                detail="Solo usuarios con sucursal asignada pueden crear productos.",
            )
        exigir_campos_de_cajero(datos)
    validar_precio(datos.price)
    validar_escalones(datos.prices)
    sku = validar_sku_unico(db, org_id, datos.sku)
    _validar_destinos_y_rol(db, org_id, user, datos, es_admin)
    destinos = resolver_sucursales_destino(db, org_id, user, datos.target_branch_ids)
    _validar_existencia_inicial(user, datos, destinos)
    validar_departamento_y_marca(db, org_id, datos.department_id, datos.brand_id)
    barcode = validar_barcode_libre(db, org_id, datos.barcode)

    # approval_status: siempre APPROVED. CAJERO/GERENTE ven su producto al
    # instante; el workflow de aprobación está fuera de alcance hoy.
    producto = Product(
        name=datos.name,
        description=datos.description,
        unit=datos.unit or "pza",
        image_url=datos.image_url or None,
        department_id=datos.department_id,
        brand_id=datos.brand_id,
        gender=datos.gender,   # ya normalizado por el schema
        model=(datos.model or "").strip() or None,
        material=(datos.material or "").strip() or None,
        has_variants=True,
        is_active=True,
        approval_status="APPROVED",
        created_by_user_id=user.id,
        organization_id=org_id,
    )
    db.add(producto)
    db.flush()

    # La principal ES la primera combinación color/talla (matriz boutique);
    # sin atributos, "Estándar".
    color, size = atributos_principal(datos.color, datos.size)
    principal = ProductVariant(
        product_id=producto.id,
        sku=sku,
        barcode=barcode,
        color=color,
        size=size,
        variant_name=variant_label(color, size),
        price=datos.price,
        cost=datos.cost,
        has_iva=datos.has_iva,
        tax_rate=datos.tax_rate,
        organization_id=org_id,
    )
    db.add(principal)
    db.flush()
    asignar_barcode_interno(db, org_id, principal, asignador)

    destino_stock = sucursal_de_existencia_inicial(user, datos.branch_id, destinos)
    registrar_stock_inicial(
        db, org_id, principal, destinos, destino_stock, datos.initial_stock or Decimal(0),
        user.id, referencia=kardex[0], notas=kardex[1],
    )
    armar_estado_por_sucursal(db, org_id, principal, destinos, is_active_hq=is_active_hq)
    mapa = armar_empaques(db, org_id, principal, datos.packaging_units)
    armar_escalones(db, org_id, principal, datos.prices, mapa)
    if not es_admin:
        _auditar_alta_de_cajero(db, user, producto, principal)

    if datos.extra_variants:
        crear_variantes(db, org_id, producto, datos.extra_variants,
                        stock_branch_id=destino_stock, user_id=user.id, asignador=asignador)
    db.flush()
    return producto


def duplicar_producto(db: Session, org_id: int, user: User, product_id: str) -> Product:
    """Copia producto + variantes VIVAS (SKU `-COPY-<n>`, código interno
    nuevo, color/talla), empaques (sin barcode), escalones y estado por
    sucursal. NO copia StockOnHand: la copia arranca sin existencias."""
    origen = db.query(Product).filter(
        Product.id == product_id, Product.organization_id == org_id,
    ).first()
    if origen is None:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    vivas = variantes_vivas(origen)
    if not vivas:
        raise HTTPException(status_code=409, detail="El producto no tiene variantes vivas que duplicar.")

    copia = Product(
        name=f"{origen.name} (copia)",
        description=origen.description,
        unit=origen.unit,
        image_url=origen.image_url,
        department_id=origen.department_id,
        brand_id=origen.brand_id,
        # Ficha boutique: la copia es la misma prenda, con su género, modelo
        # y material — si no, su nombre de venta sale distinto.
        gender=origen.gender,
        model=origen.model,
        material=origen.material,
        has_variants=origen.has_variants,
        is_active=True,
        approval_status="APPROVED",
        created_by_user_id=user.id,
        organization_id=org_id,
    )
    db.add(copia)
    db.flush()

    asignador = AsignadorDeCodigos(db, org_id)
    for v in vivas:
        nueva = ProductVariant(
            product_id=copia.id,
            sku=sku_de_copia(db, org_id, v.sku),
            barcode=None,                  # único por org: se genera uno interno abajo
            color=v.color,
            size=v.size,
            variant_name=v.variant_name,
            price=v.price,
            cost=v.cost,
            has_iva=v.has_iva,
            tax_rate=v.tax_rate,
            organization_id=org_id,
        )
        db.add(nueva)
        db.flush()
        asignar_barcode_interno(db, org_id, nueva, asignador)

        mapa_empaques: dict[str, str] = {}
        for pkg in (v.packaging_units or []):
            nuevo_pkg = PackagingUnit(
                variant_id=nueva.id,
                name=pkg.name,
                barcode=None,
                units_per_package=pkg.units_per_package,
                package_price=pkg.package_price,
                weight=pkg.weight,
                dimensions=pkg.dimensions,
                organization_id=org_id,
            )
            db.add(nuevo_pkg)
            db.flush()
            mapa_empaques[pkg.id] = nuevo_pkg.id
        for pr in (v.prices or []):
            db.add(ProductPrice(
                variant_id=nueva.id,
                price_name=pr.price_name,
                min_quantity=pr.min_quantity,
                unit_price=pr.unit_price,
                linked_package_id=mapa_empaques.get(pr.linked_package_id) if pr.linked_package_id else None,
                organization_id=org_id,
            ))
        copiar_estado_por_sucursal(db, org_id, v, nueva)
    db.flush()
    return copia
