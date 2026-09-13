"""
CRUD y helpers de visibilidad de productos.

Este módulo centraliza la política de visibilidad CAJERO/GERENTE
descrita en `docs/audits/cajero-visibility/00-policy.md`:

- ADMINISTRADOR / DUEÑO ven todo el catálogo de la organización
  (sin filtro de sucursal).
- CAJERO / GERENTE / VENDEDOR / SOPORTE_OPERATIVO con `branch_id`
  solo ven productos con `ProductBranchStatus(variant_id, branch_id=user.branch_id,
  is_active_pos=True)` + `Product.is_active=True` + tenant.
- Sin `ProductBranchStatus` para la sucursal del usuario → **OCULTO**
  (anula explícitamente la política antigua ATS-11).
- Si `Branch.can_sell == False` para su sucursal, la lista es vacía.
"""

from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import and_
from sqlalchemy.orm import Query, Session, selectinload

from app.models import (
    Branch,
    Product,
    ProductBranchStatus,
    ProductVariant,
    StockOnHand,
)
from app.models.users import Role, User
from app.schemas.products import ProductCreate

# ─────────────────────────────────────────────────────────────────────────────
# Roles que ven todo el catálogo (sin filtro de sucursal)
# ─────────────────────────────────────────────────────────────────────────────
ADMIN_ROLES = frozenset({Role.ADMINISTRADOR, Role.DUEÑO})


def _role_str(user: User) -> str:
    """
    Devuelve el rol del usuario como string, normalizado.

    Defensa contra el bug recurrente `user.role in ["ADMINISTRADOR", ...]`:
    `user.role` es un `Enum` (Role), no string. La comparación contra
    literales rompe silenciosamente. Usar este helper para comparaciones
    contra strings.
    """
    role = getattr(user, "role", None)
    if role is None:
        return ""
    return role.value if hasattr(role, "value") else str(role)


def _is_admin(user: User) -> bool:
    """True si el usuario ve todo el catálogo sin filtro de sucursal."""
    return getattr(user, "role", None) in ADMIN_ROLES


# ─────────────────────────────────────────────────────────────────────────────
# Query principal — única fuente de verdad para listar productos visibles
# ─────────────────────────────────────────────────────────────────────────────
def query_visible_products(
    db: Session,
    user: User,
    org_id: int,
    *,
    include_inactive: bool = False,
    search: Optional[str] = None,
    branch_id_override: Optional[int] = None,
    eager_variants: bool = False,
    join_variants: bool = False,
) -> Query:
    """
    Construye un Query[Product] aplicando la política de visibilidad.

    Args:
        db: sesión SQLAlchemy.
        user: usuario autenticado.
        org_id: organización activa.
        include_inactive: si True, incluye `Product.is_active=False`.
            Solo válido para ADMIN/DUEÑO; ignorado para otros roles.
        search: texto ILIKE sobre nombre + SKU + descripción.
        branch_id_override: si el caller es admin y quiere filtrar por una
            sucursal específica. Ignorado para roles no-admin (siempre
            se usa `user.branch_id`).
        eager_variants: `selectinload(Product.variants)` para evitar N+1.
        join_variants: pide el `outerjoin` a `ProductVariant` SIN aplicar
            `search`, para callers que arman su propio predicado sobre la
            variante (el scanner de tienda busca por igualdad y también
            necesita alcanzar `PackagingUnit`, que cuelga de la variante).
            Sin esto, un admin sin `branch_id_override` y sin `search` no
            trae la tabla unida y el caller revienta con "ON clause
            references tables to its right".

    Returns:
        `Query[Product]` con `.distinct()`. El caller añade `.order_by()`
        y `.offset().limit()`.

    Short-circuit:
        Si el usuario no es admin y su `Branch.can_sell == False`, la query
        retorna 0 filas.
    """
    is_admin = _is_admin(user)

    q: Query = db.query(Product).filter(Product.organization_id == org_id)

    # Activos por default; admins pueden pedir include_inactive
    if not (is_admin and include_inactive):
        q = q.filter(Product.is_active.is_(True))

    # Aprobación forzada para no-admins
    if not is_admin:
        q = q.filter(Product.approval_status == "APPROVED")

    if eager_variants:
        q = q.options(selectinload(Product.variants))

    if is_admin:
        # Admin: sin filtro de sucursal. Override opcional para drill-down.
        if branch_id_override is not None:
            q = (
                q.join(ProductVariant, ProductVariant.product_id == Product.id)
                .join(
                    ProductBranchStatus,
                    and_(
                        ProductBranchStatus.variant_id == ProductVariant.id,
                        ProductBranchStatus.branch_id == branch_id_override,
                        ProductBranchStatus.is_active_pos.is_(True),
                    ),
                )
            )
    else:
        branch_id = getattr(user, "branch_id", None)
        if branch_id is None:
            # Cero filas, pero con ProductVariant unida: los callers (el POS
            # hace outerjoin a PackagingUnit sobre la variante) la referencian
            # y sin ella Postgres revienta con "missing FROM-clause entry".
            # Visto en produccion el 2026-09-13: sucursal con can_sell=False
            # daba 500 en vez de lista vacia.
            return (
                q.outerjoin(ProductVariant, ProductVariant.product_id == Product.id)
                .filter(Product.id.is_(None))
            )

        branch = db.query(Branch).filter(Branch.id == branch_id).first()
        if branch is None or not branch.can_sell:
            # Cero filas, pero con ProductVariant unida: los callers (el POS
            # hace outerjoin a PackagingUnit sobre la variante) la referencian
            # y sin ella Postgres revienta con "missing FROM-clause entry".
            # Visto en produccion el 2026-09-13: sucursal con can_sell=False
            # daba 500 en vez de lista vacia.
            return (
                q.outerjoin(ProductVariant, ProductVariant.product_id == Product.id)
                .filter(Product.id.is_(None))
            )

        # INNER JOIN a PBS — sin registro = oculto (anti-ATS-11).
        q = (
            q.join(ProductVariant, ProductVariant.product_id == Product.id)
            .join(
                ProductBranchStatus,
                and_(
                    ProductBranchStatus.variant_id == ProductVariant.id,
                    ProductBranchStatus.branch_id == branch_id,
                    ProductBranchStatus.is_active_pos.is_(True),
                ),
            )
        )

    # `join_variants` sin `search`: mismo join que abajo, pero sin filtrar.
    if join_variants and not search and is_admin and branch_id_override is None:
        q = q.outerjoin(ProductVariant, ProductVariant.product_id == Product.id)

    # Search tras los joins (admin sin override necesita joinear variants)
    if search:
        pattern = f"%{search.strip()}%"
        if is_admin and branch_id_override is None:
            q = q.outerjoin(ProductVariant, ProductVariant.product_id == Product.id)
        q = q.filter(
            (Product.name.ilike(pattern))
            | (Product.description.ilike(pattern))
            | (ProductVariant.sku.ilike(pattern))
            | (ProductVariant.barcode.ilike(pattern))
        )

    return q.distinct()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers complementarios
# ─────────────────────────────────────────────────────────────────────────────
def get_product_if_visible(
    db: Session,
    user: User,
    org_id: int,
    product_id: str,
) -> Optional[Product]:
    """
    Devuelve el Product si el usuario puede verlo según la policy, o None.

    Pensado para endpoints `GET /api/products/{id}` (previene IDOR).
    """
    return (
        query_visible_products(db, user, org_id)
        .filter(Product.id == product_id)
        .first()
    )


def get_variant_if_visible(
    db: Session,
    user: User,
    org_id: int,
    *,
    variant_id: Optional[str] = None,
    sku: Optional[str] = None,
    require_pos_active: bool = True,
) -> Optional[ProductVariant]:
    """
    Resuelve un ProductVariant por `variant_id` o `sku` si es visible.

    Para CAJERO/GERENTE requiere PBS(is_active_pos=True) en su sucursal
    cuando `require_pos_active=True` (default). Defensa contra IDOR
    cross-tenant y cross-branch al resolver items en venta/cotización.

    Returns None si no existe o si el usuario no puede verlo.
    """
    if variant_id is None and sku is None:
        raise ValueError("Debes pasar variant_id o sku")

    q: Query = (
        db.query(ProductVariant)
        .join(Product, Product.id == ProductVariant.product_id)
        .filter(Product.organization_id == org_id)
    )

    if variant_id is not None:
        q = q.filter(ProductVariant.id == variant_id)
    if sku is not None:
        q = q.filter(ProductVariant.sku == sku)

    if not _is_admin(user) and require_pos_active:
        q = q.filter(Product.is_active.is_(True))
        branch_id = getattr(user, "branch_id", None)
        if branch_id is None:
            return None
        branch = db.query(Branch).filter(Branch.id == branch_id).first()
        if branch is None or not branch.can_sell:
            return None
        q = q.join(
            ProductBranchStatus,
            and_(
                ProductBranchStatus.variant_id == ProductVariant.id,
                ProductBranchStatus.branch_id == branch_id,
                ProductBranchStatus.is_active_pos.is_(True),
            ),
        )

    return q.first()


def assert_product_visible(
    db: Session,
    user: User,
    org_id: int,
    product_id: str,
) -> Product:
    """Devuelve el Product o levanta HTTPException 404."""
    product = get_product_if_visible(db, user, org_id, product_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Producto no encontrado",
        )
    return product


# ─────────────────────────────────────────────────────────────────────────────
# Bulk-op tenancy guards — defensa anti-IDOR en endpoints que reciben listas
# de variant_ids / branch_ids desde el cliente.
# ─────────────────────────────────────────────────────────────────────────────
def assert_variants_belong_to_org(
    db: Session,
    variant_ids,
    org_id: int,
):
    """
    Valida que todos los `variant_ids` pertenezcan a la organización `org_id`.

    Defensa contra IDOR en endpoints bulk: sin esta verificación, un payload
    con IDs de variantes de otra org haría que el loop las mute.

    Returns la lista deduplicada de ids válidos.
    Raises HTTPException 403 si alguno no existe en la org.
    """
    uniq = list({v for v in (variant_ids or []) if v is not None})
    if not uniq:
        return []
    rows = (
        db.query(ProductVariant.id)
        .join(Product, Product.id == ProductVariant.product_id)
        .filter(
            Product.organization_id == org_id,
            ProductVariant.id.in_(uniq),
        )
        .all()
    )
    valid = {r[0] for r in rows}
    missing = set(uniq) - valid
    if missing:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Variantes fuera del tenant: {list(missing)[:5]}",
        )
    return uniq


def assert_branches_belong_to_org(
    db: Session,
    branch_ids,
    org_id: int,
):
    """
    Valida que todos los `branch_ids` pertenezcan a la organización `org_id`.

    Defensa contra IDOR cross-tenant en endpoints bulk sobre PBS / Stock.
    """
    uniq = list({b for b in (branch_ids or []) if b is not None})
    if not uniq:
        return []
    rows = (
        db.query(Branch.id)
        .filter(
            Branch.organization_id == org_id,
            Branch.id.in_(uniq),
        )
        .all()
    )
    valid = {r[0] for r in rows}
    missing = set(uniq) - valid
    if missing:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Sucursales fuera del tenant: {list(missing)[:5]}",
        )
    return uniq


# ─────────────────────────────────────────────────────────────────────────────
# PBS audit logging — un helper para dejar registro uniforme de cambios en
# ProductBranchStatus desde cualquier endpoint (PATCH, PUT, POST bulk).
# ─────────────────────────────────────────────────────────────────────────────
def log_pbs_change(
    db: Session,
    actor_user_id: int,
    action: str,
    pbs_id,
    variant_id,
    branch_id,
    before: dict | None = None,
    after: dict | None = None,
    extra: dict | None = None,
) -> None:
    """
    Apila un `PlatformAuditLog` row con el diff de un PBS.

    El caller es responsable del `db.commit()` (para que todo el cambio
    viva en la misma transacción que la mutación).

    action: una cadena estable como 'PBS_UPDATE', 'PBS_BULK_TOGGLE',
    'PBS_BULK_CREATE'. before/after son subsets del PBS (solo los campos
    que cambiaron).
    """
    import json as _json
    from app.models.platform import PlatformAuditLog

    payload = {
        "variant_id": str(variant_id) if variant_id is not None else None,
        "branch_id": branch_id,
    }
    if before is not None:
        payload["before"] = {k: (str(v) if v is not None else None) for k, v in before.items()}
    if after is not None:
        payload["after"] = {k: (str(v) if v is not None else None) for k, v in after.items()}
    if extra:
        payload.update(extra)

    db.add(PlatformAuditLog(
        actor_user_id=actor_user_id,
        action=action,
        entity_type="ProductBranchStatus",
        entity_id=str(pbs_id) if pbs_id is not None else None,
        payload=_json.dumps(payload),
    ))


# ─────────────────────────────────────────────────────────────────────────────
# CRUD legacy (mantenido por compatibilidad)
# ─────────────────────────────────────────────────────────────────────────────
def create_simple_product(db: Session, product_in: ProductCreate, branch_id: int):
    """Crea Producto -> Variante -> Stock en 0."""
    db_product = Product(
        name=product_in.name,
        department_id=product_in.department_id,
        brand_id=product_in.brand_id,
        has_variants=False,
    )
    db.add(db_product)
    db.flush()

    db_variant = ProductVariant(
        product_id=db_product.id,
        sku=product_in.sku,
        barcode=product_in.barcode,
        variant_name="Default",
        price=product_in.price,
        cost=product_in.cost,
    )
    db.add(db_variant)
    db.flush()

    db_stock = StockOnHand(
        branch_id=branch_id,
        variant_id=db_variant.id,
        qty_on_hand=0.0,
    )
    db.add(db_stock)

    db.commit()
    db.refresh(db_product)
    return db_product


def get_product_by_sku(db: Session, sku: str):
    """Busca un ProductVariant por SKU (sin filtro de tenant — legacy)."""
    return db.query(ProductVariant).filter(ProductVariant.sku == sku).first()


# ─────────────────────────────────────────────────────────────────────────────
# D0 — PBS upsert helper for PATCH /api/products/variants/{variant_id}/branch-status
# ─────────────────────────────────────────────────────────────────────────────
_PBS_EDITABLE_FIELDS = frozenset({
    "price_override",
    "min_stock_alert",
    "max_stock_limit",
    "is_active_pos",
    "is_active_hq",
    "is_visible",
})


def resolve_pbs_target_branch(user: User, requested_branch_id: Optional[int]) -> int:
    """
    Resolves the branch_id to act on for a PBS write.

    - ADMIN/DUEÑO: `requested_branch_id` is required (400 if missing).
    - Non-admin: forced to `user.branch_id`. If `requested_branch_id` is
      passed and differs, raise 403.

    Raises HTTPException(400) or HTTPException(403) on guard violations.
    """
    if _is_admin(user):
        if requested_branch_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "ADMIN/DUEÑO debe especificar ?branch_id=N al modificar "
                    "ProductBranchStatus."
                ),
            )
        return int(requested_branch_id)

    # Non-admin path (CAJERO / GERENTE / VENDEDOR / SOPORTE_OPERATIVO)
    branch_id = getattr(user, "branch_id", None)
    if branch_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario sin sucursal no puede modificar ProductBranchStatus.",
        )
    if requested_branch_id is not None and int(requested_branch_id) != int(branch_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo puedes modificar la habilitación comercial de tu propia sucursal.",
        )
    return int(branch_id)


def update_branch_override(
    db: Session,
    user: User,
    org_id: int,
    variant_id: str,
    updates: dict,
    target_branch_id: int,
) -> "ProductBranchStatus":
    """
    Upsert ProductBranchStatus(variant_id, target_branch_id) applying only
    the keys in `updates`. Returns the persisted row (not committed — caller
    commits).

    Assumes guards (role + variant visibility + branch resolution) were run
    by the caller. Ignores unknown keys silently (only `_PBS_EDITABLE_FIELDS`
    are applied).

    Returns a tuple-like side-effect via the returned PBS:
        pbs, changes = ... — callers that need a diff for audit logging
        should inspect before/after manually. This helper does NOT emit
        audit events; the router layer handles that.
    """
    pbs = (
        db.query(ProductBranchStatus)
        .filter(
            ProductBranchStatus.variant_id == variant_id,
            ProductBranchStatus.branch_id == target_branch_id,
        )
        .first()
    )

    filtered = {k: v for k, v in updates.items() if k in _PBS_EDITABLE_FIELDS}

    if pbs is None:
        pbs = ProductBranchStatus(
            variant_id=variant_id,
            branch_id=target_branch_id,
            organization_id=org_id,
        )
        # Apply overrides on top of model defaults (is_active_pos=True, etc).
        for key, value in filtered.items():
            setattr(pbs, key, value)
        db.add(pbs)
        db.flush()
    else:
        for key, value in filtered.items():
            setattr(pbs, key, value)
        db.flush()

    return pbs
