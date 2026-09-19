# Runbook — Convertir una caja al autoarranque del agente (Linux y macOS)

**Estado:** ninguna caja convertida al 2026-09-19. La conversión la hace el
dueño en persona, caja por caja. Hasta entonces las cajas siguen con el modo
manual y **nada en su rutina cambia**.

Linux usa systemd (servicio de sistema o de usuario); macOS usa un LaunchAgent
de launchd. El procedimiento es el mismo en espíritu: ensayo en seco →
instalar → verificar tras reiniciar.

## Qué cambia para la cajera

| | Hoy (manual) | Después de convertir |
|---|---|---|
| Al prender la PC | Buscar el `.sh`, doble clic, esperar el OK verde | Nada |
| Ventana del agente | Debe quedar abierta toda la jornada | No existe |
| Módulo de impresora | Entra, acepta protocolo, selecciona impresora, prueba | No entra; la impresora ya está guardada |
| Si el agente se cae | Vuelve a abrir el `.sh` | systemd lo revive en 5 s |
| Su mañana | Prender → navegador → POS → **módulo impresora** → vender | Prender → navegador → POS → vender |

Si por costumbre vuelve a abrir el `.sh`, ve *"El agente YA ESTA ACTIVO,
puedes cerrar esta ventana"*. No es un error y no rompe nada.

## Antes de salir

- [ ] Saber la contraseña de sudo de esa PC (todas usan el usuario administrador).
- [ ] Saber con qué dominio entra esa caja al POS. Por omisión el instalador
      graba `https://app.atlasone.com.mx`, que además ya está cubierto por el
      regex de fábrica del agente. Si esa caja entra por un dominio propio
      distinto, pásalo con `--origins`. Si vas a cambiar el dominio en la misma
      visita, hazlo **antes** de instalar el servicio.
- [ ] Llevar el ZIP del agente actualizado, o ubicar la carpeta que esa caja
      ya venía usando (mejor: el certificado ya aceptado está ahí).

## Procedimiento por caja — Linux (systemd)

**1. Ubicar la carpeta que ya usan.** Es la que contiene `impresora_linux.sh`;
típicamente `~/Descargas/print_agent`. Abre una terminal ahí.

```bash
cd ~/Descargas/print_agent      # ajustar a la ruta real
```

**2. Ensayo en seco.**

```bash
bash core/instalar-servicio-linux.sh --dry-run
```

Verifica dos líneas:
- `Certificado existente encontrado: …` → **bien**, no habrá que re-aceptar nada.
  Si dice *"No se encontró certificado previo"*, busca la carpeta correcta antes
  de seguir; instalar así obliga a re-aceptar el certificado en el navegador.
- `Orígenes: …` → debe incluir el dominio con el que esa tienda entra al POS.

**3. Instalar.**

```bash
sudo bash core/instalar-servicio-linux.sh
```

Toma unos minutos (crea el entorno Python). Termina con `✓ Agente instalado y
respondiendo` y el JSON de `/health`. **Si termina en rojo, no sigas** — corre
`journalctl -u atlas-print-agent -n 50 --no-pager` y resuelve antes de irte.

Si esa tienda entra por el dominio propio y el dry-run no lo mostró:

```bash
sudo bash core/instalar-servicio-linux.sh --origins "https://pos.micliente.com"
```

**4. La prueba que importa: reiniciar la PC.**

```bash
sudo reboot
```

Al volver, **antes de abrir nada**:

```bash
systemctl status atlas-print-agent      # active (running) + enabled
curl -k https://127.0.0.1:9100/health
```

**5. Prueba de punta a punta desde el POS.** Entra al POS como la cajera,
ve al módulo de impresora, confirma que aparece la impresora y **manda una
impresión de prueba**. Que `/health` responda no garantiza que salga papel.

**6. Cerrar el ciclo con la cajera.** Enséñale que ya no tiene que abrir nada y
que si abre el `.sh` por costumbre verá el aviso. Deja la carpeta vieja donde
está — el servicio ya corre desde `/opt/atlas-print-agent`, no desde ahí.

## Lo que el autoarranque NO resuelve

- **Permiso "Acceso a la red local" de Chrome.** Se concede por sitio y por PC.
  Si cambias el dominio del POS en la misma visita, hay que concederlo de nuevo
  en esa terminal o la caja vende pero no imprime.
- **Aceptación del certificado autofirmado.** Se conserva si el instalador
  encontró el certificado viejo; si generó uno nuevo, hay que abrir
  `https://127.0.0.1:9100/health` y aceptarlo.
- **Que salga papel.** El agente responde 200 cuando el spooler acepta el
  trabajo, no cuando imprime (hallazgo C-06 de la auditoría 2026-09-07).

## Revertir

```bash
sudo systemctl disable --now atlas-print-agent
```

La carpeta vieja y `impresora_linux.sh` siguen intactas: con el servicio
detenido, el doble clic de siempre vuelve a funcionar igual que antes.

## Bitácora de conversión

| Tienda | Fecha | Usuario | Dominio | Cert conservado | Reboot verificado |
|---|---|---|---|---|---|
| _(pendiente)_ | | | | | |
