# Infraestructura — VPS IONOS `atlas-prod-01`

> Última actualización: 2026-09-22 — corte de producción de Railway a este servidor.

**Este servidor es producción desde el 2026-09-22** (`app.atlasone.com.mx`, cliente
real cobrando — Kaory, Ginebra, Imaltzin, Eleven Fashion). También aloja la landing de
Atlas ONE y el espacio reservado para RMAZH. Railway ya no sirve producción de Atlas
One — ver [`deployment-map.md`](deployment-map.md) para el estado de ese proyecto
(sigue existiendo, sin despliegue automático activo desde `main`).

## El servidor

```
host    atlas-prod-01
ip      74.208.190.44
so      Ubuntu 24.04 LTS
specs   12 vCore · 24 GB RAM · 720 GB NVMe
acceso  ssh ionos     (llave ~/.ssh/id_ed25519_ionos, sin passphrase)
```

Acceso solo por llave pública: `PasswordAuthentication no` en
`/etc/ssh/sshd_config.d/01-hardening.conf`. `ufw` abierto únicamente en 22, 80 y
443; `fail2ban` vigilando sshd.

> **El prefijo `01-` del archivo de hardening no es cosmético.** sshd resuelve
> por *primera coincidencia* y el `50-cloud-init.conf` de Ubuntu fuerza
> `PasswordAuthentication yes`. Un archivo `99-` no tendría ningún efecto y
> creerías estar protegido sin estarlo.

## Qué corre ahí

```
                       ┌──────────────────────────┐
      :443 ───────────▶│  caddy  (TLS automático) │
                       └────────────┬─────────────┘
                                    │  red docker "edge"
        ┌───────────────────────────┼───────────────────────────┐
        ▼                           ▼                           ▼
  /srv/landing              atlas-one-prod              /srv/placeholder
  atlasone.com.mx           app.atlasone.com.mx          rmazh.atlasone.com.mx
                                    │                    PRODUCCIÓN — cliente real
                                    ▼
                            postgres (18-alpine)
                            └ atlas_one_prod  ← main, datos reales (Kaory + clientes VPS)
```

| Ruta | Contenido |
|---|---|
| `/srv/caddy/` | `Caddyfile` + compose del proxy |
| `/srv/apps/postgres/` | Postgres compartido, volumen `pgdata_v18` |
| `/srv/apps/atlas-one-prod/` | **Producción.** `src/` recibe el código por push de CI/CD (ver abajo); `docker-compose.yml` con `context: ./src` |
| `/srv/landing/` | Landing estática de `atlasone.com.mx` |
| `/srv/backups/` | Dumps + `pg_backup.sh` (cron diario 03:30, retención 14 días) |

El entorno demo/beta (`atlas-one-beta`, base `atlas_one_beta`) que corrió aquí hasta el
2026-09-22 se retiró en el corte de producción — `app.atlasone.com.mx` sirve hoy
`atlas-one-prod`, no una demo. El contenedor `atlas-one` con la copia congelada de
Kaory del 2026-07-28 (usada como semilla de la migración) puede seguir vivo sin
dominio apuntando; ya no es necesario para operar, solo para auditoría del corte.

## Redesplegar

**Automático:** cada push a `main` dispara `.github/workflows/ci.yml`, job
`deploy-ionos` — ver [`../DEPLOY.md`](../DEPLOY.md) para el pipeline completo (envía el
código por `tar`+SSH con una llave de despliegue dedicada, construye, levanta, verifica
el commit desplegado y el `/health`). Ya no se usa `git archive`/`scp` manual ni una
llave de despliegue de GitHub *en* el servidor: el código entra por push desde el
runner de CI, no por `git pull` local.

**Manual (rollback o depuración), mismo destino que usa CI:**

```bash
git archive --format=tar HEAD | ssh ionos 'tar -x -C /srv/apps/atlas-one-prod/src'
ssh ionos 'cd /srv/apps/atlas-one-prod && docker compose build && docker compose up -d'
```

El `build` y el `up -d` van **juntos**: construir sin levantar deja el contenedor
corriendo la imagen vieja, y `docker inspect -f "{{.State.StartedAt}}"` lo delata
sin necesidad de adivinar. Verifica siempre contra el contenedor, no contra el
`src/` del servidor:

```bash
ssh ionos 'docker exec atlas-one-prod cat /app/.commit_desplegado'
ssh ionos 'docker exec atlas-one-prod grep -c "<algo del cambio>" /app/app/routers/<archivo>.py'
```

El `.env` **no** entra en la imagen: lo aporta `env_file:` del `docker-compose.yml` del
servidor en tiempo de ejecución.

## TLS

Caddy pide y renueva los certificados de Let's Encrypt solo. Los registros DNS
viven en Cloudflare y **deben estar en modo "DNS only" (nube gris)**: con el
proxy naranja, Cloudflare termina el TLS y Caddy nunca completa el desafío.

## Base de datos

Postgres **18**, no 17. Producción corre 18-alpine y el `docker-compose.yml` de
desarrollo aún dice `postgres:17-alpine`.

> Postgres 18 monta el volumen en `/var/lib/postgresql`, **no** en
> `/var/lib/postgresql/data`. Con la ruta antigua el contenedor entra en bucle de
> reinicio con un mensaje sobre "unused mount/volume".

Respaldos automáticos de todas las bases a `/srv/backups`, diarios a las 03:30,
con 14 días de retención.

## Monitoreo

Los eventos de Docker (`die`, `oom`, `health_status`) son la señal de caída.
En Docker 29 el campo de la plantilla es `{{.Action}}`; `{{.Status}}` fue
eliminado y hace que `docker events` falle al instante — un monitor construido
así queda mudo, y el silencio se ve igual que "todo bien".

```bash
docker events --filter event=die --filter event=oom --filter event=health_status \
  --format "{{.Actor.Attributes.name}} :: {{.Action}} :: exit={{.Actor.Attributes.exitCode}}"
```

## Pendientes

- ~~Llave de despliegue de GitHub en el servidor para hacer `git pull` en el propio
  VPS~~ — resuelto distinto de lo previsto: el código llega por `tar`+SSH desde el
  runner de CI (una llave de despliegue en GitHub Actions, no en el servidor), ver
  `docs/DEPLOY.md`.
- Reverse DNS (PTR) de la IP hacia `atlas-prod-01.atlasone.com.mx`
- `rmazh.mx` (servidor **74.208.195.59**, distinto a este) tiene el certificado
  vencido desde el 2026-07-19 y ese dominio se imprime en cada ticket
- Apagar (o decidir el destino de) el proyecto `atlas-bos` en Railway, que sigue
  encendido como rollback tras el corte del 2026-09-22 (ver `deployment-map.md`).
