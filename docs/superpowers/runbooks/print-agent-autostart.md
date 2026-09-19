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
| Si el agente se cae | Vuelve a abrir el `.sh` | systemd (Linux) o launchd (macOS) lo revive en 5 s |
| Su mañana | Prender → navegador → POS → **módulo impresora** → vender | Prender → navegador → POS → vender |

Si por costumbre vuelve a abrir el `.sh`, ve *"El agente YA ESTA ACTIVO,
puedes cerrar esta ventana"*. No es un error y no rompe nada.

## Antes de salir

- [ ] **Linux:** saber la contraseña de sudo de esa PC. **macOS:** NO hace falta —
      y NO se debe usar sudo, el LaunchAgent es del usuario de la caja.
- [ ] Saber con qué dominio entra esa caja al POS. Por omisión el instalador
      graba `https://app.atlasone.com.mx`, que además ya está cubierto por el
      regex de fábrica del agente. Si esa caja entra por un dominio propio
      distinto, pásalo con `--origins`. Si vas a cambiar el dominio en la misma
      visita, hazlo **antes** de instalar el servicio.
- [ ] Llevar el ZIP del agente actualizado, o ubicar la carpeta que esa caja
      ya venía usando (mejor: el certificado ya aceptado está ahí).
- [ ] **Cerrar la ventana de Terminal del modo manual antes de instalar.** Esa
      ventana no es el agente: es un `while true` que lo relanza cada 5 s. Si
      sigue viva, le pelea el 9100 al servicio y `/health` puede acabar
      respondiendo desde el agente manual mientras el servicio se reinicia en
      bucle. El instalador intenta cerrarla (mata el envoltorio y después el
      agente), pero es más limpio hacerlo a mano.
- [ ] **macOS: hay que estar frente a la Mac.** El instalador tiene que correr
      desde la sesión gráfica (Terminal en la Mac o Compartir pantalla). Por SSH
      launchd rechaza el LaunchAgent con `Bootstrap failed: 5: Input/output
      error`.
- [ ] **macOS: Python.** Basta el 3.9.6 que traen las herramientas de Xcode. Si
      el instalador se queja de la versión, se instala desde
      <https://python.org/downloads/macos/> o con `brew install python@3.12` —
      **nunca** `xcode-select --install`, que vuelve a dar 3.9.6.

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

## Procedimiento por caja — macOS (launchd)

Mismo espíritu que Linux; cambian el instalador y los comandos de verificación.
**Nunca con sudo:** el LaunchAgent vive en el home del usuario de la caja; con
sudo se instalaría en el de root y la cajera nunca lo vería arrancar.

**1. Ubicar la carpeta que ya usan.** Es la que contiene `impresora_mac.sh`;
típicamente `~/Downloads/print_agent` (o `~/Descargas/print_agent` si el macOS
está en español). Abre Terminal ahí.

```bash
cd ~/Downloads/print_agent      # ajustar a la ruta real
```

**2. Ensayo en seco.**

```bash
bash core/instalar-servicio-mac.sh --dry-run
```

Verifica dos líneas:
- `Certificado existente encontrado: …` → **bien**, no habrá que re-aceptar nada.
  Si dice *"No se encontró certificado previo"*, busca la carpeta correcta antes
  de seguir; instalar así obliga a re-aceptar el certificado en el navegador.
- `Orígenes: …` → debe incluir el dominio con el que esa caja entra al POS.

**3. Instalar (sin sudo).**

```bash
bash core/instalar-servicio-mac.sh
```

Toma unos minutos (crea el entorno Python). Termina con `✓ Agente instalado y
respondiendo` y el JSON de `/health`. **Si termina en rojo, no sigas** — corre
`tail -n 50 ~/Library/Logs/AtlasPrintAgent/agent.err.log` y resuelve antes de
irte.

Si esa caja entra por un dominio propio distinto y el dry-run no lo mostró:

```bash
bash core/instalar-servicio-mac.sh --origins "https://pos.micliente.com"
```

**4. La prueba que importa: cerrar sesión o reiniciar.**

```bash
sudo reboot
```

Al volver a iniciar sesión, **antes de abrir nada**:

```bash
launchctl print gui/$(id -u)/com.atlasone.print-agent   # state = running
curl -k https://127.0.0.1:9100/health
ls ~/Library/LaunchAgents | grep -i atlas               # solo com.atlasone.print-agent.plist
```

`launchctl print` devuelve 0 también con el servicio **cargado pero caído**; lo
que hay que leer es `state = running`. El propio `impresora_mac.sh` aplica ese
mismo criterio: si el servicio está instalado pero no responde, avisa y arranca
el modo manual para que la caja pueda imprimir hoy.

Si `ls` muestra algún otro plist de Atlas, es de una instalación vieja y sobra:
`launchctl bootout gui/$(id -u)/<label>` y borrarlo.

**macOS 15 (Sequoia) o posterior** muestra una notificación de *Elementos de
inicio* la primera vez que se carga el LaunchAgent. Es lo esperado. **No lo
desactives** en Ajustes → General → Elementos de inicio: si se desactiva, el
agente deja de arrancar solo y la caja vuelve al modo manual sin avisar a nadie.

**Si `launchctl bootstrap` falla** (`Bootstrap failed: 5: Input/output error`)
es que estás por SSH. Entra a la Mac en persona o por Compartir pantalla, corre
`launchctl bootout gui/$(id -u)/com.atlasone.print-agent` y reintenta. El plist
ya quedó escrito, así que el agente arrancará solo en el próximo inicio de
sesión gráfico aunque el comando haya fallado.

**5. Dar de alta la impresora**, si esa Mac aún no la tiene. **No es como en
Linux:** desde macOS 14 CUPS rechaza las colas raw (`Raw queues are no longer
supported on macOS`). La cola se crea con un **PPD genérico** y el modo raw lo
fuerza el agente en cada impresión con `lp -o raw`, que salta los filtros de
ese PPD.

```bash
lpinfo -v                                 # ver los URIs disponibles
sudo lpadmin -p ticket -E -v "<uri de lpinfo -v>" \
  -P /System/Library/Frameworks/ApplicationServices.framework/Versions/A/Frameworks/PrintCore.framework/Versions/A/Resources/Generic.ppd
lpstat -p ticket                          # debe decir "idle"

# Prueba a mano, sin pasar por el POS:
printf 'PRUEBA\n\n\n\n' | lp -d ticket -o raw
```

Si ese PPD no existe en esa versión de macOS: `lpinfo -m | grep -i generic` y
usar `-m <modelo>` en vez de `-P <ruta>`. El wizard del POS hace lo mismo solo.

En el panel de diagnóstico del agente, en macOS **todas** las colas salen
marcadas como `raw`: es correcto, ahí el raw no es propiedad de la cola sino
del envío (`raw_mode: "lp -o raw (macOS sin colas raw)"`).

**6. Prueba de punta a punta desde el POS.** Entra al POS como la cajera, ve al
módulo de impresora, confirma que aparece la impresora y **manda una impresión
de prueba**. Que `/health` responda no garantiza que salga papel.

**7. Cerrar el ciclo con la cajera.** Enséñale que ya no tiene que abrir nada y
que si abre `impresora_mac.sh` por costumbre verá el aviso. Deja la carpeta
vieja donde está — el servicio ya corre desde
`~/Library/Application Support/AtlasPrintAgent`, no desde ahí.

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

Linux:

```bash
sudo systemctl disable --now atlas-print-agent
```

macOS (sin sudo):

```bash
bash core/instalar-servicio-mac.sh --dry-run --uninstall   # solo enseña qué haría
bash core/instalar-servicio-mac.sh --uninstall
# equivale a: launchctl bootout gui/$(id -u)/com.atlasone.print-agent
#             rm -f ~/Library/LaunchAgents/com.atlasone.print-agent.plist
```

La carpeta vieja y el `impresora_*.sh` siguen intactos: con el servicio
detenido, el doble clic de siempre vuelve a funcionar igual que antes.

## Bitácora de conversión

| Tienda | SO | Fecha | Usuario | Dominio | Cert conservado | Reboot verificado |
|---|---|---|---|---|---|---|
| _(pendiente)_ | | | | | | |
