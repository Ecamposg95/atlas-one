"""`product_variants.color` y `.size` existen y `Product.variants` sale en
orden de creacion: `variants[0]` deja de ser aleatorio."""
from decimal import Decimal

from app.models.products import Product, ProductVariant


def test_columnas_color_y_size(db, org):
    p = Product(name="Playera", organization_id=org.id, is_active=True)
    db.add(p); db.flush()
    v = ProductVariant(product_id=p.id, sku="PLY-ROJO-M", price=Decimal("10"), cost=Decimal("5"),
                       color="Rojo", size="M", variant_name="Rojo / M", organization_id=org.id)
    db.add(v); db.flush()
    db.refresh(v)
    assert (v.color, v.size) == ("Rojo", "M")


def test_variants_en_orden_de_creacion(db, org):
    p = Product(name="Playera", organization_id=org.id, is_active=True)
    db.add(p); db.flush()
    for i, talla in enumerate(["S", "M", "L"]):
        db.add(ProductVariant(product_id=p.id, sku=f"PLY-{talla}", price=Decimal("10"),
                              cost=Decimal("5"), size=talla, organization_id=org.id))
        db.flush()
    db.expire(p)
    assert [v.size for v in p.variants] == ["S", "M", "L"]
