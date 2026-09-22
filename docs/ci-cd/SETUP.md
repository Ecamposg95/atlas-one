# CI/CD — Setup y operación

> Actualizado 2026-09-22: el workflow ganó un quinto job, `deploy-ionos`, que despliega
> a producción. Detalle del deploy en [`../DEPLOY.md`](../DEPLOY.md); este documento
> cubre el workflow completo y cómo operarlo.

Este documento describe el workflow de GitHub Actions (`.github/workflows/ci.yml`) y cómo operarlo en el día a día.

## ¿Qué corre el CI?

Cada push (a cualquier rama) y cada PR contra `main` dispara cuatro jobs en paralelo:

| Job                  | Qué hace                                  | Falla si…                                  |
| -------------------- | ----------------------------------------- | ------------------------------------------ |
| `backend-tests`      | `pytest tests/ -v --tb=short` (Python 3.11) | Cualquier test del backend falla           |
| `frontend-typecheck` | `npx tsc --noEmit` dentro de `frontend/` | Hay errores de TypeScript                  |
| `frontend-tests`     | `npx vitest run` dentro de `frontend/`   | Cualquier test de Vitest falla              |
| `frontend-build`     | `npm run build` dentro de `frontend/`    | Build de Vite rompe (imports, loaders, …) |

Concurrency está activado: si pusheás dos veces seguidas a la misma rama, el run
anterior se cancela — **excepto en `main`**, donde `cancel-in-progress: false` evita
cancelar un despliegue a mitad de construcción.

**Solo en push a `main`**, y solo si los cuatro jobs de arriba pasaron
(`needs: [backend-tests, frontend-tests, frontend-typecheck, frontend-build]`), corre un
quinto job:

| Job | Qué hace | Falla si… |
| --- | --- | --- |
| `deploy-ionos` | Construye la imagen Docker y la despliega al VPS IONOS por SSH; verifica el commit desplegado y `/health` | El build falla, el contenedor no arranca con el commit nuevo, o `/health` no responde 200 en ~2.5 min |

Es decir: **el deploy a producción ya no corre si el CI está rojo** — el `needs` del job
es el gate, no una convención de branch protection. Detalle completo del job en
[`../DEPLOY.md`](../DEPLOY.md).

## Branch protection (recomendado, manual)

El `needs` de `deploy-ionos` ya impide que un push a `main` con CI rojo dispare el
deploy. Branch protection sigue siendo útil para lo que el `needs` no cubre: impedir
que un PR se **mergee** a `main` con checks rojos (el deploy solo se dispara en push,
pero un mergeo ya es un push). Para exigirlo:

1. GitHub → **Settings** → **Branches** → **Branch protection rules** → **Add rule**.
2. Branch name pattern: `main`.
3. Activar:
   - **Require a pull request before merging**.
   - **Require status checks to pass before merging**.
   - En “Status checks that are required”, agregar:
     - `Backend tests (pytest)`
     - `Frontend typecheck (tsc --noEmit)`
     - `Frontend tests (vitest)`
     - `Frontend build (vite)`
   - **Require branches to be up to date before merging** (opcional pero recomendado).
4. Guardar.

A partir de ahí, ningún PR puede mergear a `main` con un check rojo.

## Correr el workflow localmente (act)

Para iterar sin pushear, podés usar [`act`](https://github.com/nektos/act) (Docker required):

```bash
# Instalar (macOS): brew install act
# Linux: curl https://raw.githubusercontent.com/nektos/act/master/install.sh | bash

# Correr todo el workflow
act push

# Correr solo un job
act -j backend-tests
```

`act` usa imágenes Docker que emulan `ubuntu-latest`. Nota: el cache de pip/npm no se reusa entre runs locales.

## Qué hacer cuando el CI rompe en `main`

Dos opciones, según el caso:

- **Fix-forward** (preferido cuando el fix es chico y obvio): abrí un PR con la corrección, dejá que el CI valide, mergeá.
- **Revertir** (cuando el fix no es obvio o urge un main verde): `git revert <sha>` del commit ofensor y pushealo. Después tomate tiempo de investigar y volver a aplicar el cambio bien.

Regla práctica: si el fix toma más de 15 minutos, revertí primero y arreglá en una rama aparte.

## Próximos pasos (no implementados todavía)

- Job de lint (ruff/eslint) cuando definamos la config.
- Coverage report subiendo a Codecov o similar.
- ~~Bloquear el deploy con un check `SAFE_TO_DEPLOY` que dependa del CI verde~~ — hecho
  vía `needs` en `deploy-ionos` (ver arriba), sin necesidad de un check aparte.
