# tests/test_presupuesto_bundle.py
"""scripts/presupuesto_bundle.py: mide la ruta crítica del frontend y falla al pasarse."""
import json
from pathlib import Path

import pytest

from scripts import presupuesto_bundle as pb


def _dist(tmp_path: Path, precarga=("vendor-abc.js", "store-def.js"), pos=True) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    links = "".join(f'<link rel="modulepreload" crossorigin href="/assets/{p}">' for p in precarga)
    (dist / "index.html").write_text(
        "<!doctype html><html><head>"
        '<script type="module" crossorigin src="/assets/index-xyz.js"></script>'
        f'{links}<link rel="stylesheet" crossorigin href="/assets/index-q.css">'
        "</head><body></body></html>",
        encoding="utf-8",
    )
    (dist / "assets" / "index-xyz.js").write_bytes(b"x" * 1000)
    for p in precarga:
        (dist / "assets" / p).write_bytes(b"y" * 500)
    if pos:
        (dist / "assets" / "POS-123.js").write_bytes(b"z" * 300)
    (dist / "assets" / "Reportes-999.js").write_bytes(b"w" * 9000)  # lazy: no cuenta
    (dist / "assets" / "index-q.css").write_bytes(b"c" * 700)       # CSS: no cuenta
    return dist


def _presupuesto(tmp_path: Path, tope=2300, prohibidos=("charts-",)) -> Path:
    f = tmp_path / "presupuesto_bundle.json"
    f.write_text(json.dumps({"tope_bytes": tope, "prohibidos_en_precarga": list(prohibidos)}), encoding="utf-8")
    return f


def test_suma_entrada_precarga_y_pos(tmp_path):
    m = pb.medir(_dist(tmp_path))
    assert dict(m.archivos) == {
        "assets/index-xyz.js": 1000, "assets/vendor-abc.js": 500,
        "assets/store-def.js": 500, "assets/POS-123.js": 300,
    }
    assert m.total == 2300
    assert m.precargados == ["assets/vendor-abc.js", "assets/store-def.js"]


def test_pasa_en_el_tope_exacto(tmp_path):
    assert pb.main(["--dist", str(_dist(tmp_path)), "--presupuesto", str(_presupuesto(tmp_path))]) == 0


def test_falla_un_byte_arriba(tmp_path, capsys):
    pres = _presupuesto(tmp_path, tope=2299, prohibidos=())
    assert pb.main(["--dist", str(_dist(tmp_path)), "--presupuesto", str(pres)]) == 1
    assert "> tope" in capsys.readouterr().err


def test_falla_si_precarga_un_prefijo_prohibido(tmp_path, capsys):
    dist = _dist(tmp_path, precarga=("vendor-abc.js", "charts-777.js"))
    pres = _presupuesto(tmp_path, tope=10_000, prohibidos=("charts-",))
    assert pb.main(["--dist", str(dist), "--presupuesto", str(pres)]) == 1
    assert "charts-" in capsys.readouterr().err


def test_sin_precarga_ni_pos_mide_lo_que_hay(tmp_path):
    m = pb.medir(_dist(tmp_path, precarga=(), pos=False))
    assert m.total == 1000


def test_archivo_referenciado_que_no_existe_es_error_claro(tmp_path):
    dist = _dist(tmp_path)
    (dist / "assets" / "vendor-abc.js").unlink()
    with pytest.raises(SystemExit, match="vendor-abc.js"):
        pb.medir(dist)


def test_index_sin_entrada_es_error_claro(tmp_path):
    dist = _dist(tmp_path)
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")
    with pytest.raises(SystemExit, match="entrada"):
        pb.medir(dist)


def test_el_presupuesto_del_repo_es_valido():
    datos = json.loads(Path("frontend/presupuesto_bundle.json").read_text(encoding="utf-8"))
    assert isinstance(datos["tope_bytes"], int) and datos["tope_bytes"] > 0
    assert all(isinstance(p, str) for p in datos["prohibidos_en_precarga"])
