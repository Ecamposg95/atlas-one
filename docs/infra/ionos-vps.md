# Infraestructura — VPS IONOS `atlas-prod-01`

> Última actualización: 2026-11-18 — revisión del servidor en vivo (lo que corre, respaldos,
> acceso). Corte de producción de Railway a este servidor: 2026-09-22.

**Este servidor es producción desde el 2026-09-22** (`app.atlasone.com.mx`, cliente
real cobrando — Kaory, Ginebra, Imaltzin, Eleven Fashion, Novedades America, entre
otras). También aloja la landing de Atlas ONE y otros proyectos con repositorio propio
(rmazh, hrflow, cortex-agent — ver "Qué corre ahí"). Railway ya no sirve producción de Atlas
One — ver [`deployment-map.md`](deployment-map.md): el proyecto `atlas-bos` ya no
existe en la cuenta de Railway (comprobado el 2026-11-18).

## El servidor

```
host    atlas-prod-01
ip      74.208.190.44
so      Ubuntu 24.04 LTS
specs   12 vCore · 24 GB RAM · 720 GB NVMe
acceso  ssh ionos     (alias en ~/.ssh/config de cada máquina → root@74.208.190.44)
```

El alias `ionos` no viene con el repo: cada máquina de trabajo lo define en su
`~/.ssh/config` con su propia llave, y esa llave pública debe estar en
`/root/.ssh/authorized_keys` del servidor.

```
Host ionos
    HostName 74.208.190.44
    User root
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
```

**Dar acceso a una máquina nueva** (hecho así el 2026-11-18): desde una máquina que ya
entra, agregar la llave pública de la nueva con `>>` (nunca `>`: ese archivo también tiene
la llave de despliegue del CI y borrarla deja sin deploy a `main`):

```bash
ssh ionos 'echo "<contenido de id_ed25519.pub de la máquina nueva>" >> ~/.ssh/authorized_keys'
```

Si ninguna máquina entra, la consola KVM del panel de IONOS acepta la contraseña de root
aunque sshd no (la restricción de abajo es de sshd, no de la consola). Huella ED25519 del
servidor, para comprobar el primer contacto:
`SHA256:S8yZEYcvwfy9nzVsooXLMHQA1dx5wUDNgttiYyFAgRs`.

Acceso solo por llave pública: `PasswordAuthentication no` en
`/etc/ssh/sshd_config.d/01-hardening.conf`. `ufw` abierto únicamente en 22, 80 y
443 (tcp, más 443/udp para HTTP/3); `fail2ban` vigilando sshd.

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
        ┌──────────────────┬────────┴─────────┬──────────────────────┐
        ▼                  ▼                  ▼                      ▼
  /srv/landing       atlas-one-prod         rmazh                  hrflow-*
  atlasone.com.mx    app.atlasone.com.mx    rmazh.atlasone.com.mx  hrflow.atlasone.com.mx
                     PRODUCCIÓN             (otro repositorio)     (otro repositorio)
                           │                  │                      │
                           └──────────────────┼──────────────────────┘
                                              ▼
                                    postgres (18-alpine), compartido
                                    ├ atlas_one_prod  ← main, datos reales de las tiendas
                                    ├ rmazh_prod
                                    └ hrflow_*
```

De este repositorio solo es `atlas-one-prod`. `rmazh`, `hrflow` (web, api, face, redis) y
`cortex-agent` son otros proyectos que comparten el servidor, el Caddy y el Postgres; su
operación (incluido si `rmazh` ya atiende tráfico real aquí o sigue en Railway) se
documenta en sus repositorios, no en este. Lo que importa desde Atlas One: **un reinicio
del servidor, de `caddy` o de `postgres` los tumba a todos a la vez.**

| Ruta | Contenido |
|---|---|
| `/srv/caddy/` | `Caddyfile` + compose del proxy |
| `/srv/apps/postgres/` | Postgres compartido (Atlas One, rmazh, hrflow), volumen `pgdata_v18` |
| `/srv/apps/atlas-one-prod/` | **Producción.** `src/` recibe el código por push de CI/CD (ver abajo); `docker-compose.yml` con `context: ./src` |
| `/srv/landing/` | Landing estática de `atlasone.com.mx` |
| `/srv/apps/{rmazh,hrflow,cortex-agent}/` | Otros proyectos (repositorios propios) |
| `/srv/backups/` | Dumps + `pg_backup.sh` (cron diario 03:30 en `/etc/cron.d/pg-backup`, retención 14 días) |

El entorno demo/beta (`atlas-one-beta`, base `atlas_one_beta`) que corrió aquí hasta el
2026-09-22 se retiró en el corte de producción — `app.atlasone.com.mx` sirve hoy
`atlas-one-prod`, no una demo. El 2026-10-22 se bajaron y borraron los contenedores
`atlas-one` (copia congelada de Kaory del 2026-07-28, semilla de la migración) y
`atlas-one-beta`, junto con sus imágenes y las imágenes sin contenedor (4.4 GB
recuperados): llevaban dos meses sin una sola petición que no fuera su propio
healthcheck y sin ruta en Caddy. Quedan en disco, por si hacen falta, sus carpetas
`/srv/apps/atlas-one{,-beta}/` (compose + `.env` + `src/`), sus volúmenes de fotos
(`atlas-one_*`, `atlas-one-beta_*`) y las bases `atlas_one` (26 MB) y `atlas_one_beta`
(14 MB, cuentas QA). Para revivir un demo: `docker compose up -d --build` en esa carpeta
y una ruta nueva en el `Caddyfile`. De Atlas One solo corre `atlas-one-prod`.

**No hay QA ni beta en marcha** (comprobado el 2026-11-18), aunque el servidor lo
aparente: las carpetas `/srv/apps/atlas-one{,-beta}/` no se tocan desde el 2026-07-29,
`atlas_one_beta` tiene 13 organizaciones de prueba y cero conexiones, y el encabezado del
`Caddyfile` conserva un comentario viejo ("rama staging … base demo atlas_one_beta") que
ya no describe la ruta de `app.atlasone.com.mx`. Lo único vivo de ese entorno es su dump
nocturno. Un cambio se prueba hoy en local o contra una base de ensayo, no en un beta.

## Redesplegar

**Automático:** cada push a `main` dispara `.github/workflows/ci.yml`, job
`deploy-ionos` — ver [`../DEPLOY.md`](../DEPLOY.md) para el pipeline completo (envía el
código por `tar`+SSH con una llave de despliegue dedicada, construye, levanta, verifica
el commit desplegado y el `/health`). Ya no se usa `git archive`/`scp` manual ni una
llave de despliegue de GitHub *en* el servidor: el código entra por push desde el
runner de CI, no por `git pull` local.

**Manual (rollback o depuración), mismo destino que usa CI:**

```bash
# Vaciar el código fuente antes (app/static se respeta): tar -x no borra lo que
# el repo dejó de tener y un archivo huérfano puede tirar el build de tsc.
ssh ionos 'cd /srv/apps/atlas-one-prod/src && rm -rf frontend/src frontend/public scripts && find app -mindepth 1 -maxdepth 1 ! -name static -exec rm -rf {} +'
git archive --format=tar HEAD | ssh ionos 'tar -x -C /srv/apps/atlas-one-prod/src'
# El job de CI escribe este archivo; a mano hay que escribirlo o el contenedor seguirá
# anunciando el commit anterior.
git rev-parse HEAD | ssh ionos 'cat > /srv/apps/atlas-one-prod/src/.commit_desplegado'
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
con 14 días de retención. El cron no está en el `crontab` de root sino en
`/etc/cron.d/pg-backup` (bitácora en `/var/log/pg-backup.log`); `crontab -l` vacío no
significa que no haya respaldo. Comprobar el de hoy:

```bash
ssh ionos 'ls -lht /srv/backups | grep atlas_one_prod | head -3'
```

La retención solo borra `*.dump`. Los respaldos manuales previos a una escritura
(`atlas_one_prod_antes_de_<qué>_<fecha>.sql.gz`, ver
[`../playbooks/altas-de-clientes.md`](../playbooks/altas-de-clientes.md)) **no caducan
solos**: hay que borrarlos a mano cuando ya no sirvan.

El script respalda **todas** las bases del Postgres, también las de ensayo. Al
2026-11-18 seguían vivas `atlas_one_ensayo_taza`, `atlas_one_ensayo_taza2`,
`rmazh_ensayo` y `rmazh_ensayo2` (~1.5 GB entre las cuatro, más su dump de cada noche);
una base de ensayo se borra al terminar el ensayo.

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
- ~~Apagar el proyecto `atlas-bos` en Railway~~ — al 2026-11-18 ya no aparece en la
  cuenta y `atlas-one.up.railway.app` responde 404. **Ya no hay rollback a Railway**: el
  único camino de vuelta es el de `docs/DEPLOY.md §4` más los respaldos de `/srv/backups`.
- **Actualizaciones y reinicio del servidor.** Al 2026-11-18: 112 días encendido, 57
  actualizaciones por aplicar y `/var/run/reboot-required` presente. Hacerlo fuera del
  horario de las tiendas; reinicia también rmazh y hrflow.
- Borrar las bases de ensayo que ya cumplieron (ver "Base de datos") y decidir el destino
  de los restos del demo: bases `atlas_one` y `atlas_one_beta`, sus carpetas, sus
  volúmenes y el comentario viejo del `Caddyfile`.
