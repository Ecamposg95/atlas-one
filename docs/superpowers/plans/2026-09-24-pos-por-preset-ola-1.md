# Punto de venta por giro — ola 1

> **Para trabajadores agénticos:** SUB-HABILIDAD REQUERIDA: usa superpowers:subagent-driven-development (recomendado) o superpowers:executing-plans para implementar tarea por tarea. Los pasos usan casillas (`- [ ]`) para seguimiento.

**Meta:** que una boutique deje de ver la propina y la casilla de factura, y que Eleven y Kaory tengan color propio, todo sobre un catálogo de capacidades que después sostiene las olas 2 a 4.

**Arquitectura:** un archivo JSON declara qué funciones se pueden apagar y de qué módulo dependen. Python lo lee para resolver las capacidades de la organización y entregarlas en `/api/users/me/context`; la pantalla pregunta `puede('propina')` sin saber nada de módulos. La apariencia va aparte, por CSS, con el atributo `data-preset` que ya existe.

**Tecnologías:** FastAPI + SQLAlchemy + pytest (Python 3.11) · React + TypeScript + Zustand + vitest (Node 20).

**Spec:** `docs/superpowers/specs/2026-09-24-pos-por-preset-design.md`

## Restricciones globales

- **El comportamiento se decide por módulo, nunca por preset.** Ningún componente ni endpoint mira `preset` para decidir si una función existe.
- **El catálogo es una lista blanca:** solo se puede apagar lo que esté en él. Lo que no está, siempre está encendido. Administrar usuarios NUNCA entra al catálogo.
- **La apariencia sí va por preset**, y solo color de acento. Nada de tipografía ni iconos.
- Comentarios y nombres en español, siguiendo el código circundante.
- La suite de backend se corre siempre con `--ignore=tests/test_cash_complete.py` (ese archivo hace `sys.exit(1)` al importar).
- vitest solo recoge `src/**/*.test.ts`: la lógica que se quiera probar va en un `.ts` puro, no en un `.tsx`.
- Cada commit termina con la línea `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- **No** se toca el acomodo del punto de venta ni se le pone candado a routers que no representen una función del catálogo.

## Estructura de archivos

| Archivo | Responsabilidad |
|---|---|
| `app/capacidades/catalogo.json` | **Única fuente de verdad.** Declara cada función apagable y su módulo. |
| `app/capacidades/__init__.py` | Carga el JSON, expone `CATALOGO`, `modulo_de(clave)` y `resolver(modulos)`. |
| `app/core/permissions.py` | Se le suma `require_capability(clave)` junto al `require_module` que ya vive ahí. |
| `app/modules/users/router.py` | `/me/context` agrega `capacidades` a lo que ya devuelve. |
| `scripts/init_presets_v2.py` | Registra el módulo `tips` y lo siembra en los cuatro presets gastro. |
| `app/routers/sales.py` | Rechaza `tip_amount` y `requires_invoice` sin su capacidad. |
| `frontend/src/utils/capacidades.ts` | `puede(capacidades, clave)` puro, para poder probarlo. |
| `frontend/src/store/enabledModulesStore.ts` | Guarda `capacidades` y expone el selector. |
| `frontend/src/components/pos/CartPanel.tsx` | Esconde propina y factura. |
| `frontend/src/index.css` | Color para `ATLAS_POS`, `ATLAS_POS_BOUTIQUE` y `CUSTOM`. |

---

### Tarea 1: El catálogo de capacidades

**Archivos:**
- Crear: `app/capacidades/catalogo.json`
- Crear: `app/capacidades/__init__.py`
- Probar: `tests/test_catalogo_capacidades.py`

**Interfaces:**
- Produce: `CATALOGO: list[dict]`, `modulo_de(clave: str) -> str | None`, `resolver(modulos: set[str] | list[str]) -> list[str]`, `CLAVES: set[str]`.

- [ ] **Paso 1: escribir la prueba que falla**

```python
# tests/test_catalogo_capacidades.py
"""El catálogo declara qué funciones se pueden apagar y de qué módulo dependen.

Es una LISTA BLANCA: lo que no está aquí está siempre encendido. Por eso
administrar usuarios no aparece — el módulo `users` está apagado en las cuatro
tiendas reales y nadie puede quedarse sin dar de alta cajeras.
"""
from app.capacidades import CATALOGO, CLAVES, modulo_de, resolver


def test_cada_funcion_apunta_a_un_modulo_que_existe():
    from scripts.init_presets_v2 import MODULES_CATALOG
    claves_reales = {m[0] for m in MODULES_CATALOG}
    for f in CATALOGO:
        assert f["modulo"] in claves_reales, (
            f"la función '{f['clave']}' exige el módulo '{f['modulo']}', que no existe "
            f"en el catálogo de módulos"
        )


def test_cada_entrada_trae_los_campos_obligatorios():
    for f in CATALOGO:
        for campo in ("clave", "modulo", "nombre", "donde", "ayuda"):
            assert f.get(campo), f"a '{f.get('clave', '?')}' le falta '{campo}'"
        assert isinstance(f["donde"], list) and f["donde"]


def test_no_hay_claves_repetidas():
    claves = [f["clave"] for f in CATALOGO]
    assert len(claves) == len(set(claves))


def test_administrar_usuarios_no_es_apagable():
    """Lista blanca: si `users` entrara al catálogo, las cuatro tiendas reales
    —que lo tienen apagado— se quedarían sin poder dar de alta una cajera."""
    assert all(f["modulo"] != "users" for f in CATALOGO)


def test_modulo_de_responde_la_clave_correcta():
    assert modulo_de("propina") == "tips"
    assert modulo_de("no-existe") is None


def test_resolver_devuelve_solo_lo_que_la_tienda_puede():
    assert resolver({"core", "pos", "tips"}) == ["propina"]
    assert resolver({"core", "pos"}) == []
    assert resolver({"core", "pos", "tips", "invoicing"}) == ["factura", "propina"]


def test_claves_es_el_conjunto_de_claves():
    assert CLAVES == {f["clave"] for f in CATALOGO}
```

- [ ] **Paso 2: correrla y ver que falla**

Correr: `python3 -m pytest -q -p no:warnings tests/test_catalogo_capacidades.py`
Se espera: FAIL con `ModuleNotFoundError: No module named 'app.capacidades'`

- [ ] **Paso 3: escribir el catálogo**

```json
[
  {
    "clave": "propina",
    "modulo": "tips",
    "nombre": "Propina",
    "donde": ["pos.carrito"],
    "ayuda": "Botones de 10 % y 15 % al cobrar"
  },
  {
    "clave": "factura",
    "modulo": "invoicing",
    "nombre": "Factura con IVA",
    "donde": ["pos.carrito"],
    "ayuda": "Casilla que suma el 16 % al cobro"
  }
]
```

- [ ] **Paso 4: escribir el lector**

```python
# app/capacidades/__init__.py
"""Catálogo de capacidades: qué funciones se pueden apagar y de qué módulo dependen.

Es una LISTA BLANCA a propósito. Solo se puede apagar lo que está declarado aquí;
todo lo demás está siempre encendido. La alternativa —ponerle candado a todo y ver
qué se rompe— dejaría sin dar de alta cajeras a las cuatro tiendas reales, que
tienen el módulo `users` apagado.

El archivo JSON es la única fuente de verdad: lo lee este módulo para resolver y
lo lee una prueba de vitest para comprobar que la pantalla no invente claves.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Optional

_ARCHIVO = Path(__file__).with_name("catalogo.json")

CATALOGO: list[dict] = json.loads(_ARCHIVO.read_text(encoding="utf-8"))
CLAVES: set[str] = {f["clave"] for f in CATALOGO}
_POR_CLAVE: dict[str, str] = {f["clave"]: f["modulo"] for f in CATALOGO}


def modulo_de(clave: str) -> Optional[str]:
    """Módulo que exige esa función, o None si la función no está en el catálogo."""
    return _POR_CLAVE.get(clave)


def resolver(modulos: Iterable[str]) -> list[str]:
    """Funciones que una organización con esos módulos puede usar, ordenadas."""
    prendidos = set(modulos)
    return sorted(f["clave"] for f in CATALOGO if f["modulo"] in prendidos)
```

- [ ] **Paso 5: correr la prueba y verla pasar**

Correr: `python3 -m pytest -q -p no:warnings tests/test_catalogo_capacidades.py`
Se espera: 7 passed

- [ ] **Paso 6: commit**

```bash
git add app/capacidades tests/test_catalogo_capacidades.py
git commit -m "feat(capacidades): catalogo de funciones apagables como lista blanca

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Tarea 2: El contexto entrega las capacidades resueltas

**Archivos:**
- Modificar: `app/modules/users/router.py:108-119`
- Probar: `tests/test_contexto_capacidades.py`

**Interfaces:**
- Consume: `resolver()` de la tarea 1.
- Produce: `GET /api/users/me/context` devuelve `capacidades: list[str]` junto a `enabled_modules` y `preset`.

- [ ] **Paso 1: escribir la prueba que falla**

```python
# tests/test_contexto_capacidades.py
"""El servidor resuelve las capacidades; la pantalla no hace cuentas de módulos."""
from app.models.modules import Module, OrganizationModule


def _prender(db, org, clave):
    if db.query(Module).filter(Module.key == clave).first() is None:
        db.add(Module(key=clave, name=clave))
        db.flush()
    fila = db.query(OrganizationModule).filter(
        OrganizationModule.organization_id == org.id,
        OrganizationModule.module_key == clave,
    ).first()
    if fila is None:
        db.add(OrganizationModule(organization_id=org.id, module_key=clave, is_enabled=True))
    else:
        fila.is_enabled = True
    db.commit()


def test_sin_el_modulo_no_hay_capacidad(client, auth_admin, org):
    r = client.get("/api/users/me/context",
                   headers={**auth_admin, "X-Organization-ID": str(org.id)})
    assert r.status_code == 200, r.text
    assert "propina" not in r.json()["capacidades"]


def test_con_el_modulo_aparece_la_capacidad(client, db, auth_admin, org):
    _prender(db, org, "tips")
    r = client.get("/api/users/me/context",
                   headers={**auth_admin, "X-Organization-ID": str(org.id)})
    assert r.status_code == 200, r.text
    assert "propina" in r.json()["capacidades"]


def test_el_contexto_sigue_trayendo_modulos_y_preset(client, auth_admin, org):
    cuerpo = client.get("/api/users/me/context",
                        headers={**auth_admin, "X-Organization-ID": str(org.id)}).json()
    assert "enabled_modules" in cuerpo and "preset" in cuerpo
```

- [ ] **Paso 2: correrla y ver que falla**

Correr: `python3 -m pytest -q -p no:warnings tests/test_contexto_capacidades.py`
Se espera: FAIL con `KeyError: 'capacidades'`

- [ ] **Paso 3: resolver en el contexto**

En `app/modules/users/router.py`, justo después de la línea que asigna
`ctx["enabled_modules"] = sorted({"core", *(row[0] for row in enabled)})` y antes del
`return ctx`, agregar:

```python
    # Capacidades resueltas: la pantalla pregunta `puede('propina')` y no hace
    # cuentas de módulos. Si mañana una función exige dos módulos o un permiso,
    # cambia `resolver()` y ningún componente se entera.
    from app.capacidades import resolver
    ctx["capacidades"] = resolver(ctx["enabled_modules"])
```

- [ ] **Paso 4: correr la prueba y verla pasar**

Correr: `python3 -m pytest -q -p no:warnings tests/test_contexto_capacidades.py`
Se espera: 3 passed

- [ ] **Paso 5: commit**

```bash
git add app/modules/users/router.py tests/test_contexto_capacidades.py
git commit -m "feat(capacidades): el contexto entrega las capacidades ya resueltas

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Tarea 3: El módulo `tips`, sembrado solo en gastronomía

**Archivos:**
- Modificar: `scripts/init_presets_v2.py` (catálogo de módulos y los cuatro presets gastro)
- Probar: `tests/test_modulo_tips.py`

**Interfaces:**
- Produce: la clave `"tips"` en `MODULES_CATALOG` y dentro de `"mods"` de `ATLAS_ONE_GASTRO`, `ATLAS_ONE_RESTAURANT`, `ATLAS_ONE_CAFE` y `ATLAS_ONE_BAR`.

- [ ] **Paso 1: escribir la prueba que falla**

```python
# tests/test_modulo_tips.py
"""La propina es de gastronomía: el preset la siembra, el módulo la manda.

El dueño lo pidió así el 24/09/26. Se implementa con un módulo, no mirando el
preset, para que una cafetería de otra cartera pueda prenderla sin tocar código.
"""
from scripts.init_presets_v2 import MODULES_CATALOG, PRESETS

GASTRO = {"ATLAS_ONE_GASTRO", "ATLAS_ONE_RESTAURANT", "ATLAS_ONE_CAFE", "ATLAS_ONE_BAR"}


def _mods(preset_id):
    return next(p["mods"] for p in PRESETS if p["id"] == preset_id)


def test_tips_existe_en_el_catalogo_de_modulos():
    assert "tips" in {m[0] for m in MODULES_CATALOG}


def test_los_presets_gastro_nacen_con_propina():
    for pid in GASTRO:
        assert "tips" in _mods(pid), f"{pid} debería traer propina"


def test_mostrador_y_boutique_no_nacen_con_propina():
    for pid in ("ATLAS_POS", "ATLAS_POS_BOUTIQUE"):
        assert "tips" not in _mods(pid), f"{pid} no es un giro con propina"
```

- [ ] **Paso 2: correrla y ver que falla**

Correr: `python3 -m pytest -q -p no:warnings tests/test_modulo_tips.py`
Se espera: FAIL en `test_tips_existe_en_el_catalogo_de_modulos`

- [ ] **Paso 3: registrar el módulo**

En `scripts/init_presets_v2.py`, dentro de `MODULES_CATALOG`, junto a las demás entradas:

```python
    ("tips", "Propina", "Propina en el cobro: botones de porcentaje y su reporte por mesero", ModuleScope.GLOBAL, ModuleStatus.STABLE),
```

- [ ] **Paso 4: sembrarlo en los cuatro presets gastro**

Agregar `"tips",` a la lista `"mods"` de `ATLAS_ONE_GASTRO`, `ATLAS_ONE_RESTAURANT`, `ATLAS_ONE_CAFE` y `ATLAS_ONE_BAR`. No tocar ningún otro preset.

- [ ] **Paso 5: correr la prueba y la del seed**

Correr: `python3 -m pytest -q -p no:warnings tests/test_modulo_tips.py tests/test_seed_presets.py`
Se espera: todo en verde

- [ ] **Paso 6: commit**

```bash
git add scripts/init_presets_v2.py tests/test_modulo_tips.py
git commit -m "feat(propina): modulo tips sembrado solo en los presets de gastronomia

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Tarea 4: El servidor rechaza propina y factura sin su capacidad

**Archivos:**
- Modificar: `app/core/permissions.py` (agregar `require_capability`)
- Modificar: `app/routers/sales.py:827-836` (propina) y donde se lee `requires_invoice`
- Probar: `tests/test_capacidades_en_venta.py`

**Interfaces:**
- Consume: `modulo_de()` de la tarea 1.
- Produce: `tiene_capacidad(db, org_id, clave) -> bool` en `app/core/permissions.py`.

- [ ] **Paso 1: escribir la prueba que falla**

```python
# tests/test_capacidades_en_venta.py
"""Cobrar propina o marcar factura exige la capacidad, no solo la pantalla.

Antes del 24/09/26 el servidor aceptaba propina de cualquier tienda y lo unico
que validaba era que no fuera negativa, asi que esconder el boton no bastaba.

Se reusan los helpers y fixtures de tests/test_checkout_atribuye_caja.py:
`products_setup["product_a"]` es una variante de $100 habilitada en la sucursal A.
"""
from decimal import Decimal

from app.models.cash import CashSession
from app.models.modules import Module, OrganizationModule


def _prender(db, org, clave):
    if db.query(Module).filter(Module.key == clave).first() is None:
        db.add(Module(key=clave, name=clave))
        db.flush()
    fila = db.query(OrganizationModule).filter(
        OrganizationModule.organization_id == org.id,
        OrganizationModule.module_key == clave,
    ).first()
    if fila is None:
        db.add(OrganizationModule(organization_id=org.id, module_key=clave, is_enabled=True))
    else:
        fila.is_enabled = True
    db.commit()


def _preparar(db, org, branch, user):
    """Habilita el POS y abre caja, igual que test_checkout_atribuye_caja.py."""
    _prender(db, org, "pos")
    s = CashSession(user_id=user.id, branch_id=branch.id, organization_id=org.id,
                    opening_balance=Decimal("0"), status="OPEN")
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _vender(client, auth, org, variant, total, **extra):
    cuerpo = {
        "doc_type": "ORDER",
        "items": [{"sku": variant.sku, "quantity": 1}],
        "payments": [{"method": "CASH", "amount": str(total)}],
    }
    cuerpo.update(extra)
    return client.post("/api/sales/", json=cuerpo,
                       headers={**auth, "X-Organization-ID": str(org.id)})


def test_sin_el_modulo_la_propina_se_rechaza(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    _preparar(db, org, branch_a, cajero_a)
    _, variant = products_setup["product_a"]
    r = _vender(client, auth_cajero_a, org, variant, "150.00", tip_amount=50)
    assert r.status_code == 403, r.text
    assert "propina" in r.json()["detail"].lower()


def test_con_el_modulo_la_propina_pasa(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    _preparar(db, org, branch_a, cajero_a)
    _prender(db, org, "tips")
    _, variant = products_setup["product_a"]
    r = _vender(client, auth_cajero_a, org, variant, "150.00", tip_amount=50)
    assert r.status_code in (200, 201), r.text


def test_una_venta_sin_propina_no_se_estorba(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    _preparar(db, org, branch_a, cajero_a)
    _, variant = products_setup["product_a"]
    r = _vender(client, auth_cajero_a, org, variant, "100.00")
    assert r.status_code in (200, 201), r.text


def test_sin_el_modulo_la_factura_se_rechaza(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    _preparar(db, org, branch_a, cajero_a)
    _, variant = products_setup["product_a"]
    r = _vender(client, auth_cajero_a, org, variant, "100.00", requires_invoice=True)
    assert r.status_code == 403, r.text
    assert "factura" in r.json()["detail"].lower()
```

- [ ] **Paso 2: correrla y ver que falla**

Correr: `python3 -m pytest -q -p no:warnings tests/test_capacidades_en_venta.py`
Se espera: FAIL — la propina hoy responde 200

- [ ] **Paso 3: el ayudante en permissions.py**

```python
def tiene_capacidad(db: Session, org_id: int, clave: str) -> bool:
    """¿La organización puede usar esa función del catálogo?

    Lista blanca: una clave que no esté en el catálogo se considera siempre
    disponible. Así, agregar un candado nuevo exige declararlo primero.
    """
    from app.capacidades import modulo_de

    modulo = modulo_de(clave)
    if modulo is None:
        return True
    return db.query(
        db.query(OrganizationModule).filter(
            OrganizationModule.organization_id == org_id,
            OrganizationModule.module_key == modulo,
            OrganizationModule.is_enabled == True,  # noqa: E712
        ).exists()
    ).scalar()
```

- [ ] **Paso 4: usarlo en el checkout**

En `app/routers/sales.py`, donde hoy se valida la propina (`# --- Gastro: propina ---`),
sustituir el bloque por:

```python
    # --- Propina: solo donde el giro la contrató ---
    # Antes se aceptaba de cualquier tienda y lo único que se miraba era el signo,
    # así que una boutique podía cobrar propina que ni siquiera sale en su ticket.
    tip_amount = Decimal(str(sale_in.tip_amount or 0))
    if tip_amount < 0:
        raise HTTPException(status_code=400, detail="La propina no puede ser negativa")
    if tip_amount > 0 and not tiene_capacidad(db, org_id, "propina"):
        raise HTTPException(
            status_code=403,
            detail="Esta tienda no tiene propina habilitada.",
        )
    total_sale += tip_amount
```

Y donde se lee `sale_in.requires_invoice`, antes de usarlo:

```python
    if sale_in.requires_invoice and not tiene_capacidad(db, org_id, "factura"):
        raise HTTPException(
            status_code=403,
            detail="Esta tienda no tiene facturación habilitada.",
        )
```

Importar `tiene_capacidad` desde `app.core.permissions` en la cabecera del archivo.

- [ ] **Paso 5: correr la prueba y la suite completa**

Correr: `python3 -m pytest -q --ignore=tests/test_cash_complete.py -p no:warnings`
Se espera: todo en verde, sin que baje el conteo respecto a main

- [ ] **Paso 6: commit**

```bash
git add app/core/permissions.py app/routers/sales.py tests/test_capacidades_en_venta.py
git commit -m "feat(capacidades): el checkout exige la capacidad para propina y factura

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Tarea 5: La pantalla pregunta `puede()` y esconde lo que no aplica

**Archivos:**
- Crear: `frontend/src/utils/capacidades.ts`
- Crear: `frontend/src/utils/capacidades.test.ts`
- Crear: `frontend/src/utils/capacidadesDeclaradas.test.ts`
- Modificar: `frontend/src/store/enabledModulesStore.ts`
- Modificar: `frontend/src/components/pos/CartPanel.tsx`

**Interfaces:**
- Consume: `capacidades` del contexto (tarea 2).
- Produce: `puede(capacidades: string[], clave: string): boolean` y `useCapacidad(clave: string): boolean`.

- [ ] **Paso 1: escribir las pruebas que fallan**

```ts
// frontend/src/utils/capacidades.test.ts
import { describe, expect, it } from 'vitest'
import { puede } from './capacidades'

describe('puede', () => {
  it('deja pasar lo que la tienda tiene', () => {
    expect(puede(['propina', 'factura'], 'propina')).toBe(true)
  })

  it('bloquea lo que la tienda no tiene', () => {
    expect(puede(['factura'], 'propina')).toBe(false)
  })

  it('con la lista vacía no deja pasar nada', () => {
    // La lista vacía es una respuesta legítima del servidor: la tienda no tiene
    // ninguna función apagable encendida. No es "todavía no cargó".
    expect(puede([], 'propina')).toBe(false)
  })
})
```

```ts
// frontend/src/utils/capacidadesDeclaradas.test.ts
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

/** Toda clave que la pantalla use tiene que existir en el catálogo del servidor.
 *  Sin esta red, alguien inventa una clave, `puede()` devuelve false para siempre
 *  y la función queda escondida sin que nadie sepa por qué. */
function archivos(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n)
    return statSync(p).isDirectory() ? archivos(p) : p.match(/\.tsx?$/) ? [p] : []
  })
}

describe('claves de capacidad usadas en la pantalla', () => {
  it('todas existen en app/capacidades/catalogo.json', () => {
    const catalogo = JSON.parse(readFileSync('../app/capacidades/catalogo.json', 'utf-8'))
    const declaradas = new Set(catalogo.map((f: { clave: string }) => f.clave))
    const usadas = new Set<string>()
    for (const f of archivos('src')) {
      for (const m of readFileSync(f, 'utf-8').matchAll(/useCapacidad\(\s*['"]([a-z_]+)['"]/g)) {
        usadas.add(m[1])
      }
    }
    const inventadas = [...usadas].filter((c) => !declaradas.has(c))
    expect(inventadas).toEqual([])
  })
})
```

- [ ] **Paso 2: correrlas y ver que fallan**

Correr: `cd frontend && npx vitest run src/utils/capacidades.test.ts src/utils/capacidadesDeclaradas.test.ts`
Se espera: FAIL, no existe `./capacidades`

- [ ] **Paso 3: escribir el ayudante**

```ts
// frontend/src/utils/capacidades.ts
/**
 * Funciones que la tienda puede usar. El servidor las resuelve en
 * `/users/me/context`; aquí solo se consultan.
 *
 * A diferencia del gateo por módulo del menú, la lista vacía NO significa
 * "todavía no cargó": significa que la tienda no tiene ninguna función apagable
 * encendida, que es una respuesta legítima. Quien necesite distinguir "cargando"
 * usa `loaded` del store.
 */
export function puede(capacidades: string[], clave: string): boolean {
  return capacidades.includes(clave)
}
```

- [ ] **Paso 4: guardar las capacidades en el store**

En `frontend/src/store/enabledModulesStore.ts`:
- agregar `capacidades?: string[]` a `ContextResponse`;
- agregar `capacidades: string[]` a `EnabledModulesStore` y a su estado inicial (`[]`);
- en `load()`, guardar `capacidades: Array.isArray(r.data?.capacidades) ? r.data!.capacidades! : []`;
- en `reset()`, volverlas a `[]`;
- exportar el selector:

```ts
/** `useCapacidad('propina')` — true si la tienda tiene esa función. */
export const useCapacidad = (clave: string): boolean =>
  useEnabledModulesStore((s) => puede(s.capacidades, clave))
```

con `import { puede } from '../utils/capacidades'` en la cabecera.

- [ ] **Paso 5: esconder propina y factura en el carrito**

En `frontend/src/components/pos/CartPanel.tsx`:
- importar `useCapacidad` del store;
- dentro del componente: `const hayPropina = useCapacidad('propina')` y `const hayFactura = useCapacidad('factura')`;
- envolver el bloque que hoy empieza con el comentario `{/* Propina (gastro): ... */}` en `{hayPropina && ( ... )}`, y cambiar ese comentario por `{/* Propina: solo donde el giro la contrató (módulo tips) */}`;
- envolver el bloque del botón `Factura (IVA)` en `{hayFactura && ( ... )}`.

No tocar nada más del archivo: el acomodo se queda como está.

- [ ] **Paso 6: verificar todo el frontend**

Correr: `cd frontend && npx tsc --noEmit && npx vitest run && npm run build`
Se espera: tipos limpios, todas las pruebas en verde, build correcto

- [ ] **Paso 7: commit**

```bash
git add frontend/src/utils/capacidades.ts frontend/src/utils/capacidades.test.ts \
        frontend/src/utils/capacidadesDeclaradas.test.ts \
        frontend/src/store/enabledModulesStore.ts frontend/src/components/pos/CartPanel.tsx
git commit -m "feat(pos): el carrito esconde propina y factura sin su capacidad

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Tarea 6: Color propio para los tres presets que no lo tienen

**Archivos:**
- Modificar: `frontend/src/index.css` (bloque `data-preset`, a partir de la línea 144)
- Crear: `frontend/src/utils/coloresDePreset.test.ts`

**Interfaces:**
- Consume: el atributo `data-preset` que `enabledModulesStore.ts` ya pone en `<html>`.

- [ ] **Paso 1: escribir la prueba que falla**

```ts
// frontend/src/utils/coloresDePreset.test.ts
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

/** Todo preset que exista tiene color propio. Sin esto, Eleven y Kaory caían al
 *  color por defecto y se veían idénticas entre sí y que un restaurante. */
describe('color por preset', () => {
  it('ningún preset se queda sin acento', () => {
    const css = readFileSync('src/index.css', 'utf-8')
    const conColor = new Set(
      [...css.matchAll(/\[data-preset="([A-Z_0-9]+)"\]/g)].map((m) => m[1]),
    )
    const seed = readFileSync('../scripts/init_presets_v2.py', 'utf-8')
    const todos = [...seed.matchAll(/"id":\s*"([A-Z_0-9]+)"/g)].map((m) => m[1])
    const sinColor = todos.filter((p) => !conColor.has(p))
    expect(sinColor).toEqual([])
  })
})
```

- [ ] **Paso 2: correrla y ver que falla**

Correr: `cd frontend && npx vitest run src/utils/coloresDePreset.test.ts`
Se espera: FAIL — sobran `ATLAS_POS`, `ATLAS_POS_BOUTIQUE` y `CUSTOM`

- [ ] **Paso 3: agregar los tres bloques**

En `frontend/src/index.css`, dentro del mismo bloque donde viven los demás presets:

```css
  /* Mostrador: azul sobrio, el giro más común y el que no debe llamar la atención. */
  [data-preset="ATLAS_POS"] {
    --p-accent:        #2563eb;
    --p-accent-hover:  #1d4ed8;
    --p-accent-soft:   rgba(37, 99, 235, 0.12);
    --p-accent-line:   rgba(37, 99, 235, 0.32);
    --p-teal:          #2563eb;
    --p-cyan:          #2563eb;
  }
  /* Boutique: ciruela, para que la dueña de Eleven no vea la misma pantalla
     que una tienda de novedades. */
  [data-preset="ATLAS_POS_BOUTIQUE"] {
    --p-accent:        #8a4b6d;
    --p-accent-hover:  #6f3b57;
    --p-accent-soft:   rgba(138, 75, 109, 0.14);
    --p-accent-line:   rgba(138, 75, 109, 0.32);
    --p-teal:          #8a4b6d;
    --p-cyan:          #8a4b6d;
  }
  /* Personalizado: gris grafito, deliberadamente neutro. */
  [data-preset="CUSTOM"] {
    --p-accent:        #52525b;
    --p-accent-hover:  #3f3f46;
    --p-accent-soft:   rgba(82, 82, 91, 0.12);
    --p-accent-line:   rgba(82, 82, 91, 0.32);
    --p-teal:          #52525b;
    --p-cyan:          #52525b;
  }
```

- [ ] **Paso 4: correr la prueba y el build**

Correr: `cd frontend && npx vitest run && npm run build`
Se espera: todo en verde

- [ ] **Paso 5: commit**

```bash
git add frontend/src/index.css frontend/src/utils/coloresDePreset.test.ts
git commit -m "feat(ui): color propio para mostrador, boutique y personalizado

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Al terminar la ola

1. Correr las dos suites completas: `python3 -m pytest -q --ignore=tests/test_cash_complete.py -p no:warnings` y `cd frontend && npx tsc --noEmit && npx vitest run && npm run build`.
2. Fusionar a `main` y empujar: el despliegue a producción es automático desde el CI.
3. **Correr el seed después de desplegar**: `docker exec atlas-one-prod python scripts/init_presets_v2.py`. No corre solo, y sin él el módulo `tips` no existe en la base.
4. Comprobar en producción que Eleven (org 17) no trae `propina` ni `factura` en sus capacidades, y que su pantalla se ve en ciruela.

## Lo que NO entra en esta ola

Queda para las olas 2 a 4, cada una con su propio plan: quitar el atajo de administrador de `require_module`, la pantalla donde la dueña prende y apaga módulos, los módulos `bulk_pricing` y `multi_currency`, y el resto de la aplicación.
