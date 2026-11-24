"""
Image storage abstraction — Cloudinary cuando hay `CLOUDINARY_URL`, fallback a
disco local.

Modelo híbrido: el frontend sigue subiendo el archivo igual; este módulo decide
dónde guardar y devuelve la URL final que se persiste en `Product.image_url`,
`Branch.logo_url`, etc.

Backwards-compat: imágenes legacy con paths `/static/product_images/...` siguen
funcionando vía el mount de StaticFiles en `app/main.py` aunque `CLOUDINARY_URL`
esté configurada — solo las nuevas subidas van al CDN.

Configuración:
- Set `CLOUDINARY_URL=cloudinary://<api_key>:<api_secret>@<cloud_name>` en
  Railway. Sin esa env var, sigue el comportamiento previo (disco local).
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Detectar Cloudinary una vez al importar; si la env var cambia hay que reiniciar.
_CLOUDINARY_URL = os.getenv("CLOUDINARY_URL", "").strip()
_USE_CLOUDINARY = bool(_CLOUDINARY_URL)

if _USE_CLOUDINARY:
    try:
        import cloudinary
        import cloudinary.uploader
        # cloudinary auto-lee CLOUDINARY_URL al primer call si no lo configuramos
        # explícitamente; lo hacemos para validar el formato early.
        cloudinary.config(secure=True)
        logger.info("Image storage: Cloudinary (cloud_name=%s)", cloudinary.config().cloud_name)
    except Exception as e:  # pragma: no cover
        logger.warning("CLOUDINARY_URL set but SDK init failed (%s) — fallback a disco local", e)
        _USE_CLOUDINARY = False


_EXT_BY_CONTENT_TYPE = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


def _ext_from_content_type(content_type: str) -> str:
    return _EXT_BY_CONTENT_TYPE.get(content_type, "jpg")


def upload_image(
    content: bytes,
    *,
    public_id: str,
    folder: str,
    content_type: str = "image/jpeg",
) -> str:
    """Sube `content` y devuelve la URL pública.

    `public_id` es el identificador estable del recurso (ej. "<product_id>" o
    "<branch_id>") — al re-subir reemplaza la imagen anterior.

    `folder` es el bucket lógico (ej. "atlas/products", "atlas/branch_logos").
    """
    if _USE_CLOUDINARY:
        import cloudinary.uploader
        extra = {}
        if folder == PRODUCTS_FOLDER:
            # Transformación de entrada: Cloudinary guarda la foto ya reducida
            # (lado mayor ≤ 2000 px, calidad automática). El teléfono ya la manda
            # chica; esto cubre las que llegan de escritorio o por API y mantiene
            # el almacenamiento del plan Free bajo control.
            extra["transformation"] = [{"width": 2000, "height": 2000, "crop": "limit", "quality": "auto:good"}]
        result = cloudinary.uploader.upload(
            content,
            public_id=public_id,
            folder=folder,
            overwrite=True,
            resource_type="image",
            format=_ext_from_content_type(content_type),
            invalidate=True,  # purga el CDN cache de la URL anterior
            **extra,
        )
        # Cloudinary regresa secure_url con esquema https.
        return result.get("secure_url") or result.get("url")

    # Fallback disco local — mismo layout que antes.
    base = Path("app/static") / folder.replace("atlas/", "")
    base.mkdir(parents=True, exist_ok=True)
    # Borrar versiones previas (cualquier extensión) para este public_id.
    for old in base.glob(f"{public_id}.*"):
        try:
            old.unlink(missing_ok=True)
        except OSError:
            pass
    ext = _ext_from_content_type(content_type)
    dest = base / f"{public_id}.{ext}"
    dest.write_bytes(content)
    ts = int(time.time())
    return f"/static/{folder.replace('atlas/', '')}/{public_id}.{ext}?v={ts}"


def delete_image(public_id: str, *, folder: str) -> None:
    """Elimina la imagen. Idempotente — no falla si no existe."""
    if _USE_CLOUDINARY:
        import cloudinary.uploader
        try:
            cloudinary.uploader.destroy(
                f"{folder}/{public_id}",
                resource_type="image",
                invalidate=True,
            )
        except Exception as e:  # pragma: no cover
            logger.warning("Cloudinary destroy failed for %s/%s: %s", folder, public_id, e)
        return

    base = Path("app/static") / folder.replace("atlas/", "")
    for old in base.glob(f"{public_id}.*"):
        try:
            old.unlink(missing_ok=True)
        except OSError:
            pass


def is_cdn_enabled() -> bool:
    """Devuelve True si Cloudinary está activo. Útil para diagnostics endpoint."""
    return _USE_CLOUDINARY


# Folders reservados (constantes para evitar typos en callers)
PRODUCTS_FOLDER = "atlas/product_images"
BRANCH_LOGOS_FOLDER = "atlas/branch_logos"
ORG_LOGOS_FOLDER = "atlas/org_logos"
BRAND_LOGOS_FOLDER = "atlas/brands"
