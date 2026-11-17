"""Subida a Cloudinary: las fotos de producto llevan transformación de entrada."""
import sys
import types

from app.utils import image_storage


def _cloudinary_falso(monkeypatch):
    llamadas = []
    uploader = types.SimpleNamespace(
        upload=lambda content, **kw: llamadas.append(kw) or {"secure_url": "https://res.cloudinary.com/x/y.jpg"})
    mod = types.ModuleType("cloudinary")
    mod.uploader = uploader
    monkeypatch.setitem(sys.modules, "cloudinary", mod)
    monkeypatch.setitem(sys.modules, "cloudinary.uploader", uploader)
    monkeypatch.setattr(image_storage, "_USE_CLOUDINARY", True)
    return llamadas


def test_foto_de_producto_se_guarda_reducida(monkeypatch):
    llamadas = _cloudinary_falso(monkeypatch)
    url = image_storage.upload_image(b"x", public_id="p1", folder=image_storage.PRODUCTS_FOLDER)
    assert url.startswith("https://res.cloudinary.com/")
    t = llamadas[0]["transformation"][0]
    assert t["crop"] == "limit" and t["width"] == 2000 and t["quality"].startswith("auto")


def test_logos_sin_transformacion(monkeypatch):
    llamadas = _cloudinary_falso(monkeypatch)
    image_storage.upload_image(b"x", public_id="b1", folder=image_storage.BRANCH_LOGOS_FOLDER)
    assert "transformation" not in llamadas[0]
