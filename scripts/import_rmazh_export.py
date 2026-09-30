"""Carga de catalogo desde la exportacion de rmazh (Data X POS, repo Atlas-Rmazh).

Hermano de `import_datax_export.py` (xlsx de Data X POS) e `import_products.py`
(CSV propio de Atlas ONE). Aqui la entrada es el xlsx que produce el boton
"Exportar" de rmazh — `export_products_template` — o el script
`scripts/adhoc/2026-09-01/coqueta/export_coq2.py` de ese repo, que llama al
mismo codigo. Ojo: exportar con la SUCURSAL QUE TIENE EXISTENCIAS, no con el HQ,
o el Stock viene en cero.

Columnas que se leen (fila 1, hoja "Plantilla"):
    SKU, Nombre, Descripcion, Departamento, Marca, Codigo Barras,
    Precio Base, Costo, Stock, Incluye IVA,
    Pn Nombre, Pn Min, Pn Precio            (n = 1..5, escalones)
Se ignora Unidad (sin aviso: siempre viene 'pza'). Pn Empaque y E1..E3 (empaques)
se ignoran con aviso si vienen llenos.

Por cada renglon: departamento (si aplica), producto, variante con codigo,
precio, costo e IVA, un `ProductPrice` por cada escalon CON SU NOMBRE ORIGINAL
(Mayoreo, Caja, Precio 1… — "Caja" es un comportamiento del POS, igual que en
rmazh), el estado en la sucursal y las existencias como movimiento
ADJUSTMENT_IN con referencia "Carga inicial rmazh".

Identidad de un renglon: (Codigo Barras, Nombre) dentro de la organizacion.
Re-correr refresca precios, costo, IVA, escalones y estado; no duplica
productos ni vuelve a cargar existencias.

Departamento y marca de rmazh: la exportacion de Coqueta trae un unico
departamento "Ncoqueta" y una unica marca "Rmazh" que no dicen nada; por
omision no se crean (todo queda sin departamento, que el POS muestra como
"General"). `--conservar-departamentos` / `--conservar-marcas` los respetan.

Existencias: entran tal cual. Las mayores a 500 se listan al final para que
la duena las revise (en Coqueta hay 30 renglones con exactamente 10,000, que
es relleno). `--tope N` las recorta a N si se decide asi.

Todo se confirma en un solo commit al final.

Uso:
    python scripts/import_rmazh_export.py catalogo.xlsx --org 18 --branch 21 --dry-run
    python scripts/import_rmazh_export.py catalogo.xlsx --org 18 --branch 21
    python scripts/import_rmazh_export.py catalogo.xlsx --org 18 --branch 21 --tope 50
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app.models  # noqa: F401  (puebla la metadata)
from app.models.inventory import InventoryMovement, MovementType, StockOnHand
from app.models.organization import Branch, Organization
from app.models.products import (
    Brand,
    Department,
    Product,
    ProductBranchStatus,
    ProductPrice,
    ProductVariant,
)
from app.models.users import Role, User, UserOrganization

# Referencia del kardex y marca de idempotencia de las existencias.
REFERENCIA_CARGA = "Carga inicial rmazh"

# Por encima de esto, la existencia se reporta para revision humana.
UMBRAL_EXISTENCIAS_ALTAS = Decimal("500")

# Departamentos que no se crean salvo `--conservar-departamentos` (normalizados).
# "general" y "sin departamento" son lo que rmazh escribe cuando no hay ninguno.
DEPARTAMENTOS_EXCLUIDOS = {"ncoqueta", "general", "sin departamento"}

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _norm(s: Optional[str]) -> str:
    """Normaliza una cabecera o un valor: sin acentos, sin signos, en minusculas."""
    s = (s or "").strip().replace("*", "").replace("¿", "").replace("?", "")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", s).strip()


CAMPOS: Dict[str, str] = {
    "sku": "sku",
    "nombre": "nombre",
    "descripcion": "descripcion",
    "unidad": "unidad",
    "departamento": "departamento",
    "marca": "marca",
    "codigo barras": "codigo",
    "precio base": "precio",
    "costo": "costo",
    "stock": "stock",
    "incluye iva": "iva",
}
for _n in range(1, 6):
    CAMPOS[f"p{_n} nombre"] = f"p{_n}_nombre"
    CAMPOS[f"p{_n} min"] = f"p{_n}_min"
    CAMPOS[f"p{_n} precio"] = f"p{_n}_precio"
    CAMPOS[f"p{_n} empaque"] = f"p{_n}_empaque"
for _n in range(1, 4):
    CAMPOS[f"e{_n} nombre"] = f"e{_n}_nombre"
    CAMPOS[f"e{_n} barcode"] = f"e{_n}_barcode"
    CAMPOS[f"e{_n} cantidad"] = f"e{_n}_cantidad"
    CAMPOS[f"e{_n} precio"] = f"e{_n}_precio"

CABECERAS_MINIMAS = {"sku", "nombre", "precio"}


# --- Lectura del .xlsx (stdlib, igual que import_datax_export.py) -----------

def _columna(ref: str) -> int:
    n = 0
    for ch in ref:
        if not ch.isalpha():
            break
        n = n * 26 + (ord(ch.upper()) - 64)
    return n - 1


def _cadenas_compartidas(z: zipfile.ZipFile) -> List[str]:
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    raiz = ET.fromstring(z.read("xl/sharedStrings.xml"))
    return ["".join(t.text or "" for t in si.iter(_NS + "t")) for si in raiz]


def _ruta_hoja(z: zipfile.ZipFile) -> str:
    # La primera hoja es "Plantilla"; la segunda, "Listas_Validacion", no se lee.
    if "xl/worksheets/sheet1.xml" in z.namelist():
        return "xl/worksheets/sheet1.xml"
    hojas = sorted(n for n in z.namelist() if n.startswith("xl/worksheets/") and n.endswith(".xml"))
    if not hojas:
        raise ValueError("el archivo no trae ninguna hoja de calculo")
    return hojas[0]


def _valor(celda: ET.Element, compartidas: List[str]) -> str:
    tipo = celda.get("t")
    if tipo == "s":
        v = celda.find(_NS + "v")
        if v is None or v.text is None:
            return ""
        return compartidas[int(v.text)]
    if tipo == "inlineStr":
        el = celda.find(_NS + "is")
        return "".join(t.text or "" for t in el.iter(_NS + "t")) if el is not None else ""
    v = celda.find(_NS + "v")
    return (v.text or "") if v is not None else ""


def leer_export(ruta: str) -> Iterator[Tuple[int, Dict[str, str]]]:
    """Devuelve (numero de fila, {campo canonico: valor}) por cada renglon con datos."""
    with zipfile.ZipFile(ruta) as z:
        compartidas = _cadenas_compartidas(z)
        hoja = ET.fromstring(z.read(_ruta_hoja(z)))

    cabeceras: Dict[int, str] = {}
    for nfila, fila in enumerate(hoja.iter(_NS + "row"), start=1):
        crudas: Dict[int, str] = {}
        for i, celda in enumerate(fila.iter(_NS + "c")):
            ref = celda.get("r")
            idx = _columna(ref) if ref else i
            crudas[idx] = (_valor(celda, compartidas) or "").strip()

        if not cabeceras:
            cabeceras = {i: CAMPOS[_norm(v)] for i, v in crudas.items() if _norm(v) in CAMPOS}
            if not CABECERAS_MINIMAS <= set(cabeceras.values()):
                raise ValueError(
                    "la primera fila no tiene las cabeceras de la exportacion de rmazh "
                    "(se esperaba al menos SKU, Nombre y Precio Base)"
                )
            continue

        f = {campo: crudas.get(i, "") for i, campo in cabeceras.items()}
        if any(v for v in f.values()):
            yield nfila, f


# --- Conversiones -----------------------------------------------------------

def _si(valor: Optional[str]) -> bool:
    return _norm(valor) in {"si", "s", "yes", "y", "true", "1"}


def _num(valor: Optional[str], campo: str, nfila: int) -> Optional[Decimal]:
    v = (valor or "").strip().replace(",", "").replace("$", "")
    if not v:
        return None
    try:
        return Decimal(v)
    except InvalidOperation:
        raise ValueError(f"fila {nfila}: {campo} invalido — {valor!r} no es un numero") from None


def _positivo(valor: Optional[Decimal]) -> Optional[Decimal]:
    return valor if valor is not None and valor > 0 else None


def _sku_desde_nombre(nombre: str) -> str:
    base = re.sub(r"[^A-Za-z0-9]", "", unicodedata.normalize("NFKD", nombre).upper())
    return base[:8] or "PROD"


def validar_destino(db, org_id: int, branch_id: int) -> Tuple[Organization, Branch]:
    """La organizacion y la sucursal existen y van juntas."""
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if org is None:
        raise ValueError(f"la organizacion {org_id} no existe")
    sucursal = db.query(Branch).filter(Branch.id == branch_id).first()
    if sucursal is None:
        raise ValueError(f"la sucursal {branch_id} no existe")
    if sucursal.organization_id != org_id:
        raise ValueError(
            f"la sucursal {branch_id} ('{sucursal.name}') pertenece a la "
            f"organizacion {sucursal.organization_id}, no a la {org_id} "
            f"('{org.name}') — revisa --org y --branch"
        )
    return org, sucursal


def _admin_de_org(db, org_id: int) -> Optional[User]:
    base = (
        db.query(User)
        .join(UserOrganization, UserOrganization.user_id == User.id)
        .filter(UserOrganization.organization_id == org_id, UserOrganization.is_active.is_(True))
    )
    admin = base.filter(UserOrganization.org_role == "ADMIN").order_by(User.id).first()
    if admin is not None:
        return admin
    return base.filter(User.role == Role.ADMINISTRADOR).order_by(User.id).first()


# --- Carga ------------------------------------------------------------------

def import_rmazh_export(
    db,
    ruta_xlsx: str,
    org_id: int,
    branch_id: int,
    dry_run: bool = False,
    tope: Optional[Decimal] = None,
    conservar_departamentos: bool = False,
    conservar_marcas: bool = False,
) -> Dict[str, Any]:
    """Carga el catalogo exportado por rmazh. Devuelve conteos e incidencias."""
    resumen: Dict[str, Any] = {
        "creados": 0,
        "actualizados": 0,
        "omitidos": 0,
        "escalones": 0,
        "movimientos": 0,
        "departamentos_creados": 0,
        "marcas_creadas": 0,
        "codigos_generados": 0,
        "existencias_altas": [],
        "incidencias": [],
    }

    org, sucursal = validar_destino(db, org_id, branch_id)
    resumen["organizacion"] = org.name
    resumen["sucursal"] = sucursal.name

    admin = _admin_de_org(db, org_id)
    if admin is None:
        resumen["incidencias"].append(
            "la organizacion no tiene administrador: los movimientos de carga quedan sin autor"
        )

    usados = {
        s for (s,) in db.query(ProductVariant.sku)
        .filter(ProductVariant.organization_id == org_id, ProductVariant.deleted_at.is_(None))
        .all()
        if s
    }
    departamentos: Dict[str, Department] = {}
    marcas: Dict[str, Brand] = {}

    def _departamento(nombre: str) -> Optional[Department]:
        clave = (nombre or "").strip()
        if not clave:
            return None
        if not conservar_departamentos and _norm(clave) in DEPARTAMENTOS_EXCLUIDOS:
            return None
        if clave in departamentos:
            return departamentos[clave]
        d = db.query(Department).filter(Department.organization_id == org_id, Department.name == clave).first()
        if d is None:
            d = Department(name=clave, organization_id=org_id)
            db.add(d)
            db.flush()
            resumen["departamentos_creados"] += 1
        departamentos[clave] = d
        return d

    def _marca(nombre: str) -> Optional[Brand]:
        clave = (nombre or "").strip()
        if not clave or not conservar_marcas:
            return None
        if clave in marcas:
            return marcas[clave]
        b = db.query(Brand).filter(Brand.organization_id == org_id, Brand.name == clave).first()
        if b is None:
            b = Brand(name=clave, organization_id=org_id)
            db.add(b)
            db.flush()
            resumen["marcas_creadas"] += 1
        marcas[clave] = b
        return b

    def _existente(codigo: str, nombre: str) -> Optional[ProductVariant]:
        """Identidad = (codigo de barras, nombre). El SKU no sirve: el repetido recibe sufijo."""
        q = (
            db.query(ProductVariant)
            .join(Product, Product.id == ProductVariant.product_id)
            .filter(
                ProductVariant.organization_id == org_id,
                ProductVariant.deleted_at.is_(None),
                Product.deleted_at.is_(None),
                Product.name == nombre,
            )
        )
        q = q.filter(ProductVariant.barcode == codigo) if codigo else q.filter(ProductVariant.barcode.is_(None))
        return q.first()

    try:
        for nfila, f in leer_export(ruta_xlsx):
            sku_archivo = (f.get("sku") or "").strip()
            nombre = (f.get("nombre") or "").strip()
            codigo = (f.get("codigo") or "").strip()
            etiqueta = sku_archivo or codigo or f"fila {nfila}"

            if not nombre:
                resumen["omitidos"] += 1
                resumen["incidencias"].append(f"fila {nfila} ({etiqueta}): sin nombre, se omite")
                continue

            precio = _num(f.get("precio"), "Precio Base", nfila)
            if not _positivo(precio):
                resumen["incidencias"].append(
                    f"{etiqueta}: sin Precio Base, la variante se carga con precio 0 — corrigelo antes de venderla"
                )
            try:
                costo = _num(f.get("costo"), "Costo", nfila)
            except ValueError:
                resumen["incidencias"].append(
                    f"{etiqueta}: Costo ilegible ({(f.get('costo') or '').strip()!r}), se carga como 0"
                )
                costo = None
            iva = _si(f.get("iva"))

            empaques = [k for k in f if (k.startswith("e") and k[1:2].isdigit() or k.endswith("_empaque")) and f[k]]
            if empaques:
                resumen["incidencias"].append(
                    f"{etiqueta}: trae empaques ({', '.join(sorted(empaques))}) — la carga no crea empaques, capturalos a mano"
                )

            dep = _departamento(f.get("departamento") or "")
            marca = _marca(f.get("marca") or "")
            variante = _existente(codigo, nombre)

            if variante is None:
                if codigo:
                    otra = (
                        db.query(ProductVariant)
                        .filter(
                            ProductVariant.organization_id == org_id,
                            ProductVariant.deleted_at.is_(None),
                            ProductVariant.barcode == codigo,
                        )
                        .first()
                    )
                    if otra is not None:
                        resumen["incidencias"].append(
                            f"{etiqueta}: el codigo de barras {codigo} ya lo usa otra variante ({otra.sku}) — al escanearlo el POS sera ambiguo"
                        )
                sku = sku_archivo or codigo or _sku_desde_nombre(nombre)
                generado = not sku_archivo
                if sku in usados:
                    base, i = sku, 2
                    while f"{base}-{i}" in usados:
                        i += 1
                    sku = f"{base}-{i}"
                    generado = True
                    resumen["incidencias"].append(
                        f"{etiqueta}: SKU repetido en la organizacion, la variante recibio {sku} (el codigo de barras no cambia)"
                    )
                if generado:
                    resumen["codigos_generados"] += 1
                usados.add(sku)

                producto = Product(
                    name=nombre,
                    description=(f.get("descripcion") or "").strip() or None,
                    organization_id=org_id,
                    department_id=dep.id if dep is not None else None,
                    brand_id=marca.id if marca is not None else None,
                    is_active=True,
                )
                db.add(producto)
                db.flush()

                variante = ProductVariant(
                    product_id=producto.id,
                    sku=sku,
                    barcode=codigo or None,
                    variant_name="Estándar",
                    price=precio if precio is not None else Decimal("0"),
                    cost=costo if costo is not None else Decimal("0"),
                    has_iva=iva,
                    organization_id=org_id,
                )
                db.add(variante)
                db.flush()
                resumen["creados"] += 1
            else:
                producto = variante.product
                producto.department_id = dep.id if dep is not None else None
                if marca is not None:
                    producto.brand_id = marca.id
                if f.get("descripcion"):
                    producto.description = f["descripcion"].strip()
                if precio is not None:
                    variante.price = precio
                elif variante.price is None:
                    variante.price = Decimal("0")
                if costo is not None:
                    variante.cost = costo
                elif variante.cost is None:
                    variante.cost = Decimal("0")
                variante.has_iva = iva
                resumen["actualizados"] += 1

            _cargar_escalones(db, org_id, variante, f, nfila, etiqueta, resumen)
            _estado_en_sucursal(db, org_id, branch_id, variante)
            _existencias(db, org_id, branch_id, variante, f, nfila, etiqueta, admin, tope, resumen)

        if dry_run:
            db.rollback()
        else:
            db.commit()
    except Exception:
        db.rollback()
        raise
    return resumen


def _cargar_escalones(db, org_id, variante, f, nfila, etiqueta, resumen) -> None:
    """Un ProductPrice por cada Pn con nombre, CON SU NOMBRE ORIGINAL.

    En este repo "Caja" no es una etiqueta sino un comportamiento (el carrito
    arma renglones de caja con el escalon cuyo nombre contiene "caja" y trata
    `min_quantity` como piezas por caja). rmazh comparte ese flujo, asi que
    respetar el nombre es respetar la intencion de la tienda.
    """
    actuales = {
        p.price_name: p
        for p in db.query(ProductPrice).filter(
            ProductPrice.organization_id == org_id,
            ProductPrice.variant_id == variante.id,
        )
    }
    precio_base = Decimal(str(variante.price or 0))
    for n in range(1, 6):
        nombre = (f.get(f"p{n}_nombre") or "").strip()
        if not nombre:
            continue
        precio = _positivo(_num(f.get(f"p{n}_precio"), f"P{n} Precio", nfila))
        if precio is None:
            resumen["incidencias"].append(
                f"{etiqueta}: escalon {nombre} sin precio valido — no se creo"
            )
            continue
        if precio_base and precio > precio_base:
            resumen["incidencias"].append(
                f"{etiqueta}: escalon {nombre} (${precio}) mayor que el Precio Base (${precio_base}) — se carga igual, revisalo"
            )
        minimo = _num(f.get(f"p{n}_min"), f"P{n} Min", nfila) or Decimal("1")

        escalon = actuales.get(nombre)
        if escalon is None:
            db.add(
                ProductPrice(
                    variant_id=variante.id,
                    price_name=nombre,
                    min_quantity=minimo,
                    unit_price=precio,
                    organization_id=org_id,
                )
            )
        else:
            escalon.min_quantity = minimo
            escalon.unit_price = precio
        resumen["escalones"] += 1


def _estado_en_sucursal(db, org_id, branch_id, variante) -> None:
    """Habilita el producto en la sucursal (rmazh no exporta minimo/maximo)."""
    pbs = (
        db.query(ProductBranchStatus)
        .filter(
            ProductBranchStatus.organization_id == org_id,
            ProductBranchStatus.variant_id == variante.id,
            ProductBranchStatus.branch_id == branch_id,
        )
        .first()
    )
    if pbs is None:
        db.add(
            ProductBranchStatus(
                variant_id=variante.id,
                branch_id=branch_id,
                organization_id=org_id,
                is_active_pos=True,
                is_visible=True,
            )
        )


def _existencias(db, org_id, branch_id, variante, f, nfila, etiqueta, admin, tope, resumen) -> None:
    """Carga el stock inicial como movimiento de inventario, una sola vez."""
    stock = _num(f.get("stock"), "Stock", nfila) or Decimal("0")
    if tope is not None and stock > tope:
        resumen["incidencias"].append(
            f"{etiqueta}: existencias {stock} recortadas al tope {tope}"
        )
        stock = tope
    if stock > UMBRAL_EXISTENCIAS_ALTAS:
        resumen["existencias_altas"].append((variante.sku, variante.product.name, stock))

    existencias = (
        db.query(StockOnHand)
        .filter(
            StockOnHand.organization_id == org_id,
            StockOnHand.variant_id == variante.id,
            StockOnHand.branch_id == branch_id,
        )
        .first()
    )
    if existencias is None:
        existencias = StockOnHand(
            variant_id=variante.id,
            branch_id=branch_id,
            organization_id=org_id,
            qty_on_hand=Decimal("0"),
            is_active=True,
        )
        db.add(existencias)
        db.flush()
    else:
        # La fila de existencias siempre queda activa.
        existencias.is_active = True

    if stock <= 0:
        return

    ya_cargado = (
        db.query(InventoryMovement)
        .filter(
            InventoryMovement.organization_id == org_id,
            InventoryMovement.branch_id == branch_id,
            InventoryMovement.variant_id == variante.id,
            InventoryMovement.reference == REFERENCIA_CARGA,
        )
        .first()
    )
    if ya_cargado is not None:
        return

    antes = Decimal(str(existencias.qty_on_hand or 0))
    existencias.qty_on_hand = antes + stock
    db.add(
        InventoryMovement(
            branch_id=branch_id,
            variant_id=variante.id,
            user_id=admin.id if admin is not None else None,
            movement_type=MovementType.ADJUSTMENT_IN,
            qty_change=stock,
            qty_before=antes,
            qty_after=existencias.qty_on_hand,
            reference=REFERENCIA_CARGA,
            notes=f"Fila {nfila} de la exportacion de rmazh",
            organization_id=org_id,
        )
    )
    # Sin autoflush, el renglon repetido del mismo archivo no veria este movimiento.
    db.flush()
    resumen["movimientos"] += 1


def main() -> None:
    p = argparse.ArgumentParser(description="Carga de catalogo desde la exportacion de rmazh")
    p.add_argument("xlsx")
    p.add_argument("--org", type=int, required=True)
    p.add_argument("--branch", type=int, required=True)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--tope", type=Decimal, default=None, help="recorta las existencias a este maximo")
    p.add_argument("--conservar-departamentos", action="store_true")
    p.add_argument("--conservar-marcas", action="store_true")
    args = p.parse_args()

    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        try:
            org, sucursal = validar_destino(db, args.org, args.branch)
        except ValueError as e:
            print(f"ABORTADO: {e}", file=sys.stderr)
            raise SystemExit(2)
        print("=" * 60)
        print("ENSAYO (nada se guarda)" if args.dry_run else "CARGA REAL")
        print(f"  organizacion  {org.name} (id={org.id})")
        print(f"  sucursal      {sucursal.name} (id={sucursal.id})")
        print(f"  archivo       {args.xlsx}")
        if args.tope is not None:
            print(f"  tope          {args.tope}")
        print("=" * 60)

        r = import_rmazh_export(
            db, args.xlsx, args.org, args.branch,
            dry_run=args.dry_run, tope=args.tope,
            conservar_departamentos=args.conservar_departamentos,
            conservar_marcas=args.conservar_marcas,
        )
    finally:
        db.close()

    print("=" * 60)
    print("ENSAYO — nada se guardo" if args.dry_run else "CARGA APLICADA")
    print(f"  organizacion           {r['organizacion']}")
    print(f"  sucursal               {r['sucursal']}")
    print(f"  productos creados      {r['creados']}")
    print(f"  productos actualizados {r['actualizados']}")
    print(f"  renglones omitidos     {r['omitidos']}")
    print(f"  escalones de precio    {r['escalones']}")
    print(f"  movimientos de stock   {r['movimientos']}")
    print(f"  departamentos creados  {r['departamentos_creados']}")
    print(f"  marcas creadas         {r['marcas_creadas']}")
    print(f"  codigos generados      {r['codigos_generados']}")
    print(f"  incidencias            {len(r['incidencias'])}")
    for inc in r["incidencias"]:
        print("   ·", inc)
    if r["existencias_altas"]:
        print("-" * 60)
        print(f"EXISTENCIAS MAYORES A {UMBRAL_EXISTENCIAS_ALTAS} ({len(r['existencias_altas'])} renglones) — para revisar con la duena:")
        for sku, nombre, qty in sorted(r["existencias_altas"], key=lambda t: -t[2]):
            print(f"   {qty:>10}  {sku:<16} {nombre}")
    print("=" * 60)


if __name__ == "__main__":
    main()
