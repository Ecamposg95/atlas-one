"""``/api/labels/*`` — etiquetas de mostrador para la Zebra.

El backend compone el ZPL y lo entrega en base64; **no imprime**. El navegador
se lo pasa al agente local (`POST https://localhost:9100/print` con
`{printer_name, content_base64}`), el mismo transporte que el ticket de venta.

Diseño: `docs/superpowers/specs/2026-09-22-etiquetas-en-atlas-one-design.md`.
"""
from __future__ import annotations

import base64
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import require_module
from app.core.security import get_current_user
from app.core.tenant_context import get_current_active_organization
from app.models import User
from app.modules.labels import services
from app.modules.labels.schemas import (
    MAX_ETIQUETAS,
    BarcodeElement,
    CandidatesResponse,
    JobRequest,
    JobResponse,
    PreviewRequest,
    PreviewResponse,
    TestLabelResponse,
    TextElement,
)
from app.modules.products.sale_name import normalizar_genero
from app.services.labels import (
    LABEL_HEIGHT,
    LABEL_WIDTH,
    Bars,
    DatosEtiqueta,
    build_batch,
    build_label,
    build_test_label,
    detect,
    layout,
    parse_price,
)

# El módulo entero está gateado: sin `labels` habilitado no hay ni vista previa.
router = APIRouter(dependencies=[Depends(require_module("labels"))])


def _b64(zpl: str) -> str:
    """ZPL a base64. UTF-8 porque la etiqueta manda `^CI28` (acentos)."""
    return base64.b64encode(zpl.encode("utf-8")).decode("ascii")


def _serializar(elementos) -> List[dict]:
    """`layout()` tal cual, para que el frontend lo dibuje en SVG."""
    salida: List[dict] = []
    for el in elementos:
        if isinstance(el, Bars):
            salida.append(BarcodeElement(
                x=el.x, y=el.y, height=el.height, bits=el.bits,
                module_width=el.module_width, kind=el.kind, data=el.data,
                interpretation=el.interpretation,
            ).model_dump())
        else:
            salida.append(TextElement(
                x=el.x, y=el.y, height=el.height, text=el.text,
                width=el.width, align=el.align,
            ).model_dump())
    return salida


@router.get("/candidates", response_model=CandidatesResponse)
def listar_candidatos(
    search: Optional[str] = None,
    department_id: Optional[str] = None,
    brand_id: Optional[str] = None,
    gender: Optional[str] = None,
    only_with_stock: bool = False,
    product_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Variantes vivas que este usuario puede etiquetar.

    Las que no se pueden imprimir vienen con `printable=false` y su `reason`:
    esconderlas dejaría a la tienda buscando una prenda que nunca aparece.
    """
    try:
        genero = normalizar_genero(gender)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"gender {exc}")

    filas = services.candidatos(
        db, current_user, org_id,
        search=(search or None), product_id=product_id,
        department_id=department_id, brand_id=brand_id, gender=genero,
        only_with_stock=only_with_stock,
    )
    return {"items": filas, "total": len(filas)}


@router.post("/preview", response_model=PreviewResponse)
def vista_previa(
    body: PreviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Elementos del layout + ZPL de UNA etiqueta.

    Con `variant_id` se arma desde el catálogo; sin él, desde los datos sueltos
    del cuerpo (sirve para ver cómo cae un texto antes de capturarlo).
    """
    if body.variant_id:
        encontradas = services.resolver_variantes(db, current_user, org_id, [body.variant_id])
        par = encontradas.get(body.variant_id)
        if par is None:
            raise HTTPException(status_code=404, detail="Variante no encontrada")
        datos = services.datos_de_variante(*par)
    else:
        precio, precio_texto = parse_price(body.price or "")
        datos = DatosEtiqueta(
            sku=(body.sku or "").strip(), name=(body.name or "").strip(),
            brand=(body.brand or "").strip(), barcode=(body.barcode or "").strip(),
            price=precio, price_text=precio_texto,
            size=(body.size or "").strip(), color=(body.color or "").strip(),
        )

    motivo = services.motivo_no_imprimible(datos)
    if motivo:
        raise HTTPException(status_code=422, detail=f"{datos.sku or datos.name}: {motivo.lower()}")

    spec = detect(datos.barcode)
    return {
        "width": LABEL_WIDTH,
        "height": LABEL_HEIGHT,
        "kind": spec.kind,
        "warning": spec.warning,
        "elements": _serializar(layout(datos, spec)),
        "zpl": build_label(datos, 1, spec),
    }


@router.post("/jobs", response_model=JobResponse)
def crear_trabajo(
    body: JobRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Compone el lote y lo devuelve en base64. No manda nada a la impresora.

    Los renglones que no se pueden imprimir no tumban el trabajo: salen en
    `skipped` con su motivo y el resto se imprime.
    """
    total = sum(item.copies for item in body.items)
    if total > MAX_ETIQUETAS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"El lote suma {total} etiquetas y el máximo es {MAX_ETIQUETAS}. "
                "Quita renglones o baja las copias."
            ),
        )

    encontradas = services.resolver_variantes(
        db, current_user, org_id, [item.variant_id for item in body.items]
    )

    lote: List[tuple] = []
    omitidas: List[dict] = []
    impresas = 0
    for item in body.items:
        par = encontradas.get(item.variant_id)
        if par is None:
            omitidas.append({
                "variant_id": item.variant_id, "sku": "", "reason": services.NO_VISIBLE,
            })
            continue
        datos = services.datos_de_variante(*par)
        motivo = services.motivo_no_imprimible(datos)
        if motivo:
            omitidas.append({
                "variant_id": item.variant_id, "sku": datos.sku, "reason": motivo,
            })
            continue
        lote.append((datos, item.copies))
        impresas += item.copies

    return {
        "content_base64": _b64(build_batch(lote)) if lote else "",
        "labels": impresas,
        "skipped": omitidas,
    }


@router.get("/test", response_model=TestLabelResponse)
def etiqueta_de_prueba(
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Etiqueta de calibración: la misma del agente, para ajustar la Zebra
    antes de gastar rollo."""
    return {"content_base64": _b64(build_test_label())}
