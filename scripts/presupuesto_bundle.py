#!/usr/bin/env python3
"""Presupuesto de descarga de la ruta crítica del frontend (login → POS).

Lee `frontend/dist/` después de `vite build` y suma, en bytes sin comprimir,
lo que el navegador baja antes de poder cobrar:

  * el módulo de entrada (`<script type="module" src="/assets/index-*.js">`)
    y todo lo que `index.html` precarga con `<link rel="modulepreload">`;
  * `assets/POS-*.js`, la pantalla de cobro.

Falla (código 1) si la suma supera `tope_bytes` de
`frontend/presupuesto_bundle.json`, o si alguno de los prefijos de
`prohibidos_en_precarga` aparece entre los precargados (chart.js no debe
viajar con el login). Solo biblioteca estándar: en CI corre en el job de
frontend, que no instala requirements.txt.

Uso:
    python3 scripts/presupuesto_bundle.py [--dist frontend/dist]
                                          [--presupuesto frontend/presupuesto_bundle.json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

RE_ENTRADA = re.compile(r'<script[^>]+type="module"[^>]+src="/?([^"]+\.js)"')
RE_PRECARGA = re.compile(r'<link[^>]+rel="modulepreload"[^>]+href="/?([^"]+\.js)"')


@dataclass
class Medicion:
    archivos: List[Tuple[str, int]] = field(default_factory=list)
    precargados: List[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(b for _, b in self.archivos)


def medir(dist: Path) -> Medicion:
    html = (dist / "index.html").read_text(encoding="utf-8")
    entrada = RE_ENTRADA.findall(html)
    precarga = RE_PRECARGA.findall(html)
    if not entrada:
        raise SystemExit(f"{dist / 'index.html'}: no encontré el <script type=\"module\"> de entrada")
    rutas = list(dict.fromkeys(entrada + precarga))  # sin duplicados, en orden de aparición
    rutas += sorted(p.relative_to(dist).as_posix() for p in (dist / "assets").glob("POS-*.js"))
    m = Medicion(precargados=precarga)
    for r in rutas:
        f = dist / r
        if not f.exists():
            raise SystemExit(f"{f}: index.html lo referencia pero no existe en dist/")
        m.archivos.append((r, f.stat().st_size))
    return m


def evaluar(m: Medicion, presupuesto: dict) -> List[str]:
    """Violaciones del presupuesto; lista vacía = pasa."""
    errores: List[str] = []
    tope = int(presupuesto["tope_bytes"])
    if m.total > tope:
        errores.append(f"ruta crítica = {m.total:,} B > tope {tope:,} B (+{m.total - tope:,} B)")
    for prefijo in presupuesto.get("prohibidos_en_precarga", []):
        for ruta in m.precargados:
            if Path(ruta).name.startswith(prefijo):
                errores.append(f"{ruta} se precarga desde index.html; '{prefijo}' no va en la ruta crítica")
    return errores


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dist", type=Path, default=Path("frontend/dist"))
    ap.add_argument("--presupuesto", type=Path, default=Path("frontend/presupuesto_bundle.json"))
    args = ap.parse_args(argv)
    presupuesto = json.loads(args.presupuesto.read_text(encoding="utf-8"))
    m = medir(args.dist)
    for ruta, b in m.archivos:
        print(f"{b:>10,} B  {ruta}")
    print(f"{m.total:>10,} B  TOTAL ruta crítica (tope {int(presupuesto['tope_bytes']):,} B)")
    errores = evaluar(m, presupuesto)
    for e in errores:
        print(f"ERROR: {e}", file=sys.stderr)
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
