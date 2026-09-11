"""Carga de catalogo desde una exportacion de inventario de Data X POS.

Es el hermano de `import_products.py` (que lee el CSV del propio Atlas ONE):
aqui la entrada es el .xlsx que entrega Data X POS al migrar a un cliente.
Por cada renglon crea el departamento si falta, el producto, su variante con
codigo y precio base, los escalones de precio, el estado del producto en la
sucursal (minimo/maximo) y las existencias iniciales.

Las existencias NO se escriben a mano en `stock_on_hand`: entran como un
movimiento de inventario (ADJUSTMENT_IN) con la referencia
"Carga inicial Data X POS" y el administrador de la organizacion como autor,
para que el kardex explique de donde salio cada pieza.

Es idempotente: la identidad de un renglon es (codigo de barras, descripcion)
dentro de la organizacion. Volver a correrlo refresca precios, escalones y
minimos/maximos, pero no duplica productos ni vuelve a cargar existencias.

Antes de escribir nada valida que la organizacion y la sucursal existan y que
la sucursal sea de esa organizacion, y anuncia a donde va la carga. Todo se
confirma en un solo commit al final: si un renglon revienta a media corrida,
no queda medio catalogo escrito.

Columnas esperadas (fila 1 del archivo):
    Código, Descripción, Costo, Imágen,
    ¿Aplica Precio N?, Cantidad minima - Precio N, Precio N   (N = 1..3)
    ¿Aplica Precio 4?, Precio 4, ¿Aplica Precio 5?, Precio 5
    ¿Aplica inventario?, Stock, Mínimo, Máximo, Departamento

Uso:
    python scripts/import_datax_export.py inventario.xlsx --org 15 --branch 17 --dry-run
    python scripts/import_datax_export.py inventario.xlsx --org 15 --branch 17
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app.models  # noqa: F401  (puebla la metadata)
from app.models.inventory import InventoryMovement, MovementType, StockOnHand
from app.models.products import (
    Department,
    Product,
    ProductBranchStatus,
    ProductPrice,
    ProductVariant,
)
from app.models.organization import Branch, Organization
from app.models.users import Role, User, UserOrganization

# Referencia del kardex: tambien es la marca que hace idempotente la carga de
# existencias — si ya hay un movimiento con esta referencia, no se repite.
REFERENCIA_CARGA = "Carga inicial Data X POS"

# Nombres de los escalones. Data X POS numera sus listas (Precio 1..5); aqui
# se traducen a los nombres que el catalogo muestra en el POS.
# "Caja" queda fuera a proposito: en este repo ese nombre no es una etiqueta,
# es un comportamiento (CartPanel.tsx arma renglones de caja con el tier cuyo
# `price_name` contiene "caja" y trata `min_quantity` como piezas por caja).
# El Precio 3 de Data X POS es un escalon por volumen, no un empaque.
NOMBRES_ESCALON = {1: "Menudeo", 2: "Mayoreo", 3: "Volumen"}

# La exportacion siempre trae este marcador en la columna Imágen.
IMAGEN_MARCADOR = "sin-imagen.png"

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _norm(s: Optional[str]) -> str:
    """Normaliza una cabecera: sin acentos, sin signos, en minusculas."""
    s = (s or "").strip().replace("*", "").replace("¿", "").replace("?", "")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", s).strip()


CAMPOS = {
    "codigo": "codigo",
    "descripcion": "descripcion",
    "costo": "costo",
    "imagen": "imagen",
    "aplica precio 1": "aplica_p1",
    "cantidad minima - precio 1": "min_p1",
    "precio 1": "precio_p1",
    "aplica precio 2": "aplica_p2",
    "cantidad minima - precio 2": "min_p2",
    "precio 2": "precio_p2",
    "aplica precio 3": "aplica_p3",
    "cantidad minima - precio 3": "min_p3",
    "precio 3": "precio_p3",
    "aplica precio 4": "aplica_p4",
    "precio 4": "precio_p4",
    "aplica precio 5": "aplica_p5",
    "precio 5": "precio_p5",
    "aplica inventario": "aplica_inventario",
    "stock": "stock",
    "minimo": "minimo",
    "maximo": "maximo",
    "departamento": "departamento",
}


# --- Lectura del .xlsx ------------------------------------------------------
# Se lee con la biblioteca estandar (zipfile + ElementTree) en vez de openpyxl:
# los archivos de Data X POS traen validaciones de datos con un `errorStyle`
# fuera de la norma que openpyxl rechaza al abrir segun la version. Solo se
# necesitan dos partes del paquete, asi que el lector propio sale barato.

def _columna(ref: str) -> int:
    """'AB12' -> 27 (indice de columna, base 0)."""
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
    """Devuelve (numero de fila, {campo canonico: valor}) por cada renglon."""
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
            if not cabeceras:
                raise ValueError(
                    "la primera fila no tiene las cabeceras de Data X POS "
                    "(se esperaba al menos Código y Descripción)"
                )
            continue

        yield nfila, {campo: crudas.get(i, "") for i, campo in cabeceras.items()}


# --- Conversiones -----------------------------------------------------------

def _si(valor: Optional[str]) -> bool:
    v = _norm(valor)
    return v in {"si", "s", "yes", "y", "true", "1"}


def _num(valor: Optional[str], campo: str, nfila: int) -> Optional[Decimal]:
    v = (valor or "").strip().replace(",", "").replace("$", "")
    if not v:
        return None
    try:
        return Decimal(v)
    except InvalidOperation:
        raise ValueError(f"fila {nfila}: {campo} invalido — {valor!r} no es un numero") from None


def _positivo(valor: Optional[Decimal]) -> Optional[Decimal]:
    """0 y vacio significan lo mismo en la exportacion: 'no configurado'."""
    return valor if valor is not None and valor > 0 else None


def _sku_desde_nombre(nombre: str) -> str:
    base = re.sub(r"[^A-Za-z0-9]", "", unicodedata.normalize("NFKD", nombre).upper())
    return base[:8] or "PROD"


def validar_destino(db, org_id: int, branch_id: int) -> Tuple[Organization, Branch]:
    """Confirma que la organizacion y la sucursal existen y van juntas.

    Un digito mal tecleado en `--branch` escribiria cientos de renglones en la
    sucursal de otro cliente, sin vuelta atras: vale la pena pagar dos consultas
    antes de empezar.
    """
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
    """El administrador de la organizacion, autor de los movimientos de carga."""
    base = (
        db.query(User)
        .join(UserOrganization, UserOrganization.user_id == User.id)
        .filter(
            UserOrganization.organization_id == org_id,
            UserOrganization.is_active.is_(True),
        )
    )
    admin = base.filter(UserOrganization.org_role == "ADMIN").order_by(User.id).first()
    if admin is not None:
        return admin
    return base.filter(User.role == Role.ADMINISTRADOR).order_by(User.id).first()


# --- Carga ------------------------------------------------------------------

def import_datax_export(
    db,
    ruta_xlsx: str,
    org_id: int,
    branch_id: int,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Carga el catalogo exportado. Devuelve conteos e incidencias."""
    resumen: Dict[str, Any] = {
        "creados": 0,
        "actualizados": 0,
        "omitidos": 0,
        "escalones": 0,
        "movimientos": 0,
        "departamentos_creados": 0,
        "codigos_generados": 0,
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

    # SKUs ya usados por la organizacion — el indice unico no admite repetidos.
    usados = {
        s for (s,) in db.query(ProductVariant.sku)
        .filter(
            ProductVariant.organization_id == org_id,
            ProductVariant.deleted_at.is_(None),
        )
        .all()
        if s
    }
    # Descripciones ya vistas en ESTE archivo sin codigo: dos renglones sin
    # codigo y con el mismo nombre son, para la llave de identidad, el mismo
    # producto — el segundo actualiza al primero en vez de crear otro.
    sin_codigo: set = set()
    departamentos: Dict[str, Department] = {}

    def _departamento(nombre: str) -> Optional[Department]:
        clave = (nombre or "").strip()
        if not clave or _norm(clave) == "sin departamento":
            return None
        if clave in departamentos:
            return departamentos[clave]
        d = (
            db.query(Department)
            .filter(Department.organization_id == org_id, Department.name == clave)
            .first()
        )
        if d is None:
            d = Department(name=clave, organization_id=org_id)
            db.add(d)
            db.flush()
            resumen["departamentos_creados"] += 1
        departamentos[clave] = d
        return d

    def _existente(codigo: str, nombre: str) -> Optional[ProductVariant]:
        """Busca el renglon ya cargado. Identidad = (codigo de barras, nombre).

        El codigo de barras no se desambigua nunca (dos renglones pueden traer
        el mismo), asi que junto con la descripcion identifica al renglon de
        forma estable entre corridas — el SKU no sirve porque el segundo
        renglon repetido recibe un sufijo.
        """
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
        q = q.filter(ProductVariant.barcode == codigo) if codigo else q.filter(
            ProductVariant.barcode.is_(None)
        )
        return q.first()

    try:
        for nfila, f in leer_export(ruta_xlsx):
            codigo = (f.get("codigo") or "").strip()
            nombre = (f.get("descripcion") or "").strip()

            if not nombre:
                resumen["omitidos"] += 1
                resumen["incidencias"].append(
                    f"fila {nfila} (codigo {codigo or 'sin codigo'}): sin descripcion, se omite"
                )
                continue
            if codigo == "123" and _norm(nombre) == "prueba":
                resumen["omitidos"] += 1
                resumen["incidencias"].append(
                    f"fila {nfila} (codigo 123 'PRUEBA'): renglon de prueba del POS de origen, se omite"
                )
                continue

            precio_base = _num(f.get("precio_p1"), "Precio 1", nfila)
            costo = _num(f.get("costo"), "Costo", nfila)
            if not _positivo(precio_base):
                resumen["incidencias"].append(
                    f"codigo {codigo or nombre}: sin Precio 1, la variante queda sin precio base"
                )

            imagen = (f.get("imagen") or "").strip()
            if imagen and IMAGEN_MARCADOR not in imagen:
                resumen["incidencias"].append(
                    f"codigo {codigo or nombre}: trae imagen propia ({imagen}) — "
                    f"la carga no descarga imagenes, subela desde el catalogo"
                )

            for n in (4, 5):
                if _si(f.get(f"aplica_p{n}")):
                    resumen["incidencias"].append(
                        f"codigo {codigo or nombre}: Precio {n} viene aplicado pero la "
                        f"exportacion no trae su cantidad minima — cargalo a mano"
                    )

            if not codigo:
                if nombre in sin_codigo:
                    resumen["incidencias"].append(
                        f"'{nombre}': segundo renglon sin codigo con la misma "
                        f"descripcion — sin codigo la identidad es el nombre, "
                        f"asi que actualiza al anterior en vez de crear otro producto"
                    )
                sin_codigo.add(nombre)

            dep = _departamento(f.get("departamento") or "")
            variante = _existente(codigo, nombre)

            if variante is None:
                sku = codigo or _sku_desde_nombre(nombre)
                generado = not codigo
                if sku in usados:
                    base, i = sku, 2
                    while f"{base}-{i}" in usados:
                        i += 1
                    sku = f"{base}-{i}"
                    generado = True
                    resumen["incidencias"].append(
                        f"codigo {codigo or nombre}: repetido en la organizacion, "
                        f"la variante recibio el SKU {sku} (el codigo de barras no cambia)"
                    )
                if generado:
                    resumen["codigos_generados"] += 1
                usados.add(sku)

                producto = Product(
                    name=nombre,
                    organization_id=org_id,
                    department_id=dep.id if dep is not None else None,
                    is_active=True,
                )
                db.add(producto)
                db.flush()

                variante = ProductVariant(
                    product_id=producto.id,
                    sku=sku,
                    barcode=codigo or None,
                    # Toda ruta de creacion de la aplicacion asigna "Estándar";
                    # dejarlo en NULL tumba el cobro al armar el renglon de venta.
                    variant_name="Estándar",
                    price=precio_base,
                    cost=costo,
                    organization_id=org_id,
                )
                db.add(variante)
                db.flush()
                resumen["creados"] += 1
            else:
                producto = variante.product
                producto.department_id = dep.id if dep is not None else None
                # Solo se pisa lo que el archivo trae: un Precio 1 o un Costo
                # vacios no borran lo que ya este capturado en Atlas.
                if precio_base is not None:
                    variante.price = precio_base
                if costo is not None:
                    variante.cost = costo
                resumen["actualizados"] += 1

            _cargar_escalones(db, org_id, variante, f, nfila, resumen)
            _estado_en_sucursal(db, org_id, branch_id, variante, f, nfila)
            _existencias(db, org_id, branch_id, variante, f, nfila, admin, resumen)

        if dry_run:
            db.rollback()
        else:
            db.commit()
    except Exception:
        # Un solo commit al final: si un renglon revienta a media corrida, no
        # queda medio catalogo escrito. No se deja al `close()` implicito.
        db.rollback()
        raise
    return resumen


def _cargar_escalones(db, org_id, variante, f, nfila, resumen) -> None:
    """Crea o refresca un escalon por cada Precio 1..3 aplicado."""
    actuales = {
        p.price_name: p
        for p in db.query(ProductPrice).filter(
            ProductPrice.organization_id == org_id,
            ProductPrice.variant_id == variante.id,
        )
    }
    etiqueta = (f.get("codigo") or "").strip() or (f.get("descripcion") or "").strip()
    for n in (1, 2, 3):
        if not _si(f.get(f"aplica_p{n}")):
            continue
        precio = _positivo(_num(f.get(f"precio_p{n}"), f"Precio {n}", nfila))
        if precio is None:
            resumen["incidencias"].append(
                f"codigo {etiqueta}: Precio {n} viene aplicado pero sin monto "
                f"valido — no se creo el escalon"
            )
            continue
        minimo = _num(f.get(f"min_p{n}"), f"Cantidad minima - Precio {n}", nfila) or Decimal("1")
        nombre = NOMBRES_ESCALON[n]
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


def _estado_en_sucursal(db, org_id, branch_id, variante, f, nfila) -> None:
    """Habilita el producto en la sucursal y guarda su minimo/maximo."""
    minimo = _positivo(_num(f.get("minimo"), "Mínimo", nfila))
    maximo = _positivo(_num(f.get("maximo"), "Máximo", nfila))
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
                min_stock_alert=minimo,
                max_stock_limit=maximo,
            )
        )
    else:
        pbs.min_stock_alert = minimo
        pbs.max_stock_limit = maximo


def _existencias(db, org_id, branch_id, variante, f, nfila, admin, resumen) -> None:
    """Carga el stock inicial como movimiento de inventario, una sola vez."""
    controla = _si(f.get("aplica_inventario"))
    stock = _num(f.get("stock"), "Stock", nfila) or Decimal("0")

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
            is_active=controla,
        )
        db.add(existencias)
        db.flush()
    else:
        existencias.is_active = controla

    if not controla or stock <= 0:
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
            notes=f"Fila {nfila} de la exportacion de Data X POS",
            organization_id=org_id,
        )
    )
    resumen["movimientos"] += 1


def main() -> None:
    p = argparse.ArgumentParser(description="Carga de catalogo desde una exportacion de Data X POS")
    p.add_argument("xlsx")
    p.add_argument("--org", type=int, required=True)
    p.add_argument("--branch", type=int, required=True)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        # El destino se anuncia ANTES de escribir nada: quien corre esto tiene
        # que poder ver, y detener, una carga dirigida al cliente equivocado.
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
        print("=" * 60)

        r = import_datax_export(db, args.xlsx, args.org, args.branch, dry_run=args.dry_run)
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
    print(f"  codigos generados      {r['codigos_generados']}")
    print(f"  incidencias            {len(r['incidencias'])}")
    for inc in r["incidencias"]:
        print("   ·", inc)
    print("=" * 60)


if __name__ == "__main__":
    main()
