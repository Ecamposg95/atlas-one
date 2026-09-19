"""Guardas del bundle del agente de impresión: nombres de archivo y contenido del ZIP.

Contexto: en el repo de origen un renombrado de los launchers al español
(`run_agent_linux.sh` → `impresora_linux.sh`, `install_systemd.sh` →
`core/instalar-servicio-linux.sh`) **no actualizó la pantalla** que se los
dicta a la cajera. Durante dos meses `/printer-settings` instruyó correr
archivos inexistentes, así que la ruta al autoarranque quedó inalcanzable y
las cajas siguieron arrancando el agente a mano.

Dos guardas baratas:

1. Todo `.sh`/`.bat` nombrado en `PrinterSettings.tsx` existe en el bundle.
2. El ZIP de cada plataforma lleva su instalador de servicio y su plantilla
   de unidad — sin ellos el autoarranque no se puede instalar aunque las
   instrucciones estén bien escritas.
"""
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
AGENT_DIR = REPO / "tools" / "print_agent"
PRINTER_SETTINGS = REPO / "frontend" / "src" / "pages" / "pos" / "PrinterSettings.tsx"

# Nombres de script citados en la UI. Se buscan en todo el árbol del agente
# porque unos viven en la raíz (impresora_linux.sh) y otros en core/.
SCRIPT_RE = re.compile(r"[\w.-]+\.(?:sh|bat)\b")


def _bundle_filenames() -> set[str]:
    return {p.name for p in AGENT_DIR.rglob("*") if p.is_file()}


def test_ui_solo_nombra_scripts_que_existen_en_el_bundle():
    """Cada script citado en /printer-settings debe existir en tools/print_agent.

    Este es el test que habría atrapado el renombrado silencioso.
    """
    texto = PRINTER_SETTINGS.read_text(encoding="utf-8")
    citados = set(SCRIPT_RE.findall(texto))
    assert citados, "La pantalla dejó de citar scripts — ¿se reescribió la pestaña?"

    existentes = _bundle_filenames()
    faltantes = sorted(n for n in citados if n not in existentes)
    assert not faltantes, (
        f"PrinterSettings.tsx nombra scripts que no existen en el bundle: {faltantes}. "
        f"Disponibles: {sorted(n for n in existentes if n.endswith(('.sh', '.bat')))}"
    )


def _nombres_del_zip(plataforma: str) -> set[str]:
    """Nombres de archivo (sin ruta) que trae el ZIP de esa plataforma."""
    import asyncio
    import io
    import zipfile

    from app.routers.printer import download_print_agent

    class _U:  # el endpoint solo usa el usuario como gate de auth
        pass

    resp = download_print_agent(platform=plataforma, current_user=_U())

    async def _drain():
        return b"".join([chunk async for chunk in resp.body_iterator])

    payload = asyncio.run(_drain())
    return {Path(n).name for n in zipfile.ZipFile(io.BytesIO(payload)).namelist()}


def test_zip_linux_incluye_instalador_de_servicio_y_unidad_systemd():
    """El ZIP de Linux debe permitir instalar el autoarranque, no solo el modo manual."""
    nombres = _nombres_del_zip("linux")

    for requerido in (
        "impresora_linux.sh",
        "instalar-servicio-linux.sh",
        "atlas-print-agent.service",
        "INSTALL_LINUX.txt",
    ):
        assert requerido in nombres, f"El ZIP de Linux no incluye {requerido}"

    # Y no debe arrastrar los launchers ni el autoarranque de otras plataformas.
    assert "impresora_win.bat" not in nombres
    assert "impresora_mac.sh" not in nombres
    for ajeno in ("instalar-servicio-mac.sh", "com.atlasone.print-agent.plist", "INSTALL_MAC.txt"):
        assert ajeno not in nombres, f"El ZIP de Linux arrastra {ajeno}, que no puede correr ahí"


def test_zip_mac_incluye_el_launchagent_y_su_instalador():
    """El ZIP de mac debe permitir instalar el autoarranque de launchd.

    Eleven Fashion opera sobre Mac: sin estos archivos en el ZIP, la única
    manera de convertir esa caja sería copiarle archivos a mano.
    """
    nombres = _nombres_del_zip("mac")

    for requerido in (
        "impresora_mac.sh",
        "instalar-servicio-mac.sh",
        "com.atlasone.print-agent.plist",
        "INSTALL_MAC.txt",
        "requirements_mac.txt",
    ):
        assert requerido in nombres, f"El ZIP de mac no incluye {requerido}"

    # Ni los launchers ni el autoarranque de otras plataformas.
    assert "impresora_win.bat" not in nombres
    assert "impresora_linux.sh" not in nombres
    for ajeno in ("instalar-servicio-linux.sh", "atlas-print-agent.service", "INSTALL_LINUX.txt"):
        assert ajeno not in nombres, f"El ZIP de mac arrastra {ajeno}, que no puede correr ahí"


def test_zip_windows_no_arrastra_el_autoarranque_de_unix():
    nombres = _nombres_del_zip("windows")
    assert "impresora_win.bat" in nombres
    for ajeno in (
        "instalar-servicio-linux.sh", "atlas-print-agent.service", "INSTALL_LINUX.txt",
        "instalar-servicio-mac.sh", "com.atlasone.print-agent.plist", "INSTALL_MAC.txt",
    ):
        assert ajeno not in nombres, f"El ZIP de Windows arrastra {ajeno}"


def test_el_launchagent_conserva_los_placeholders_y_el_origen_cors():
    """La plantilla del plist y su instalador deben seguir casando.

    Si la plantilla pierde un marcador, launchd arrancaría con una ruta
    literal "{WORKDIR}" y el agente no existiría. Si el instalador deja de
    sustituirlo, lo mismo.
    """
    import plistlib

    plist = (AGENT_DIR / "core" / "com.atlasone.print-agent.plist").read_text(encoding="utf-8")
    for marca in ("{WORKDIR}", "{ORIGINS}", "{PORT}", "{LOGDIR}"):
        assert marca in plist, f"La plantilla perdió el marcador {marca}"
    assert "ATLAS_AGENT_ORIGINS" in plist

    instalador = (AGENT_DIR / "core" / "instalar-servicio-mac.sh").read_text(encoding="utf-8")
    for marca in ("{WORKDIR}", "{ORIGINS}", "{PORT}", "{LOGDIR}"):
        assert marca in instalador, f"El instalador no sustituye {marca}"

    # Renderizada, la plantilla tiene que ser un plist válido con lo que
    # launchd necesita para revivir el agente.
    render = (plist
              .replace("{WORKDIR}", "/Users/x/Library/Application Support/AtlasPrintAgent")
              .replace("{ORIGINS}", "https://app.atlasone.com.mx")
              .replace("{PORT}", "9100")
              .replace("{LOGDIR}", "/Users/x/Library/Logs/AtlasPrintAgent"))
    d = plistlib.loads(render.encode())
    assert d["Label"] == "com.atlasone.print-agent"
    assert d["KeepAlive"] is True, "launchd debe revivir el agente si se cae"
    assert d["RunAtLoad"] is True, "el agente debe arrancar al iniciar sesión"
    # El agente llama lp/lpstat/lpadmin/lpinfo y launchd no hereda el PATH.
    for ruta in ("/usr/bin", "/usr/sbin"):
        assert ruta in d["EnvironmentVariables"]["PATH"]


def test_el_instalador_mac_no_corre_con_sudo_ni_fuera_de_macos():
    """Dos guardas que, si se caen, rompen la instalación en silencio.

    Con sudo el LaunchAgent acabaría en el home de root y la cajera nunca
    lo vería arrancar. Y el instalador de Linux no sirve en una Mac.
    """
    instalador = (AGENT_DIR / "core" / "instalar-servicio-mac.sh").read_text(encoding="utf-8")
    assert 'uname -s' in instalador and "Darwin" in instalador
    assert "SUDO_USER" in instalador
    assert "gui/$(id -u)" in instalador, "launchctl debe apuntar al dominio gui del usuario"
    # El destino lleva un espacio: llamar al binario con -m pip evita el
    # shebang de venv/bin/pip, que se parte en ese espacio.
    assert '"$VENV_PY" -m pip install' in instalador
    ejecutables = [l for l in instalador.splitlines() if not l.lstrip().startswith("#")]
    assert not [l for l in ejecutables if "venv/bin/pip" in l], (
        "Ninguna línea ejecutable debe invocar venv/bin/pip: su shebang se parte "
        "en el espacio de 'Application Support'."
    )


def test_unidad_systemd_conserva_los_placeholders_y_el_origen_cors():
    """La unidad debe exponer ATLAS_AGENT_ORIGINS y los placeholders del instalador.

    Sin `ATLAS_AGENT_ORIGINS` una caja servida desde un dominio ajeno a los de
    fábrica **vende pero no imprime**: el navegador manda ese Origin y el
    agente lo rechaza en el preflight. En Atlas One el regex de fábrica ya
    cubre `(*.)atlasone.com.mx` y `*.up.railway.app`; cualquier otro dominio
    propio solo entra por esta variable.
    """
    unit = (AGENT_DIR / "core" / "atlas-print-agent.service").read_text(encoding="utf-8")

    assert "Environment=ATLAS_AGENT_ORIGINS={ORIGINS}" in unit
    for placeholder in ("{WORKDIR}", "{ORIGINS}", "{PORT}"):
        assert placeholder in unit, f"La unidad perdió el placeholder {placeholder}"

    # El instalador es quien los sustituye; si deja de hacerlo, systemd
    # arrancaría con rutas literales "{WORKDIR}".
    installer = (AGENT_DIR / "core" / "instalar-servicio-linux.sh").read_text(encoding="utf-8")
    for placeholder in ("{WORKDIR}", "{ORIGINS}", "{PORT}"):
        assert placeholder in installer, f"El instalador no sustituye {placeholder}"

    assert "Restart=always" in unit, "El servicio debe revivir si el agente se cae"


def test_launcher_manual_avisa_cuando_el_servicio_ya_esta_activo():
    """En una caja convertida, el doble clic de siempre debe tranquilizar, no fallar.

    La cajera seguirá buscando el .sh por costumbre durante semanas después de
    la conversión. Sin esta guarda vería un error de puerto ocupado.
    """
    launcher = (AGENT_DIR / "impresora_linux.sh").read_text(encoding="utf-8")
    assert "systemctl is-active --quiet atlas-print-agent" in launcher
    assert "systemctl --user is-active --quiet atlas-print-agent" in launcher
    # La guarda tiene que salir ANTES de tocar CUPS/venv/puerto.
    guarda = launcher.index("is-active --quiet atlas-print-agent")
    primer_paso = launcher.index("Iniciando agente de impresion")
    assert guarda < primer_paso, "La guarda debe ir antes del arranque normal"


def test_launcher_mac_avisa_cuando_el_servicio_ya_esta_activo():
    """Igual que en Linux: en una Mac convertida el doble clic debe tranquilizar.

    Pero `launchctl print` devuelve 0 también con el servicio CARGADO PERO
    CAÍDO. Si la guarda saliera ahí, la cajera cerraría la ventana creyendo que
    todo está bien y se quedaría sin imprimir: hay que exigir `state = running`
    y que /health conteste.
    """
    launcher = (AGENT_DIR / "impresora_mac.sh").read_text(encoding="utf-8")
    assert 'launchctl print "gui/$(id -u)/$AGENTE_LABEL"' in launcher
    assert 'grep -q "state = running"' in launcher, (
        "La guarda no puede conformarse con que launchctl print devuelva 0"
    )
    assert "/health" in launcher, "La guarda debe confirmar con /health"
    # Cargado-pero-caído: avisa y NO sale, para que la caja imprima hoy.
    assert "El servicio esta instalado pero NO responde" in launcher
    assert "agent.err.log" in launcher

    guarda = launcher.index("com.atlasone.print-agent")
    primer_paso = launcher.index("Iniciando agente de impresion")
    assert guarda < primer_paso, "La guarda debe ir antes del arranque normal"


def test_el_instalador_mac_acepta_el_python_de_las_herramientas_de_xcode():
    """El gate no puede ser 3.10: las Command Line Tools traen 3.9.6.

    Con 3.10 el instalador abortaba en una Mac de fábrica y el mensaje mandaba
    de vuelta a `xcode-select --install`, que vuelve a dar 3.9.6 — un bucle.
    """
    instalador = (AGENT_DIR / "core" / "instalar-servicio-mac.sh").read_text(encoding="utf-8")
    assert "sys.version_info >= (3, 9)" in instalador
    assert "(3, 10)" not in instalador, "El gate volvió a 3.10 y rompe una Mac de fábrica"
    # El remedio que se le ofrece al usuario no puede ser xcode-select.
    assert "python.org" in instalador and "brew install python" in instalador
    version = instalador.split("sys.version_info >= (3, 9)")[1].split("\n\n")[0]
    assert "xcode-select" not in version, (
        "El mensaje del gate de versión no debe mandar a xcode-select: da 3.9.6 otra vez"
    )


@pytest.mark.parametrize(
    "script,envoltorio",
    [
        ("instalar-servicio-mac.sh", "impresora_mac"),
        ("instalar-servicio-linux.sh", "impresora_linux"),
    ],
)
def test_los_instaladores_matan_el_envoltorio_ademas_del_agente(script, envoltorio):
    """El modo manual es un `while true` que relanza el agente cada 5 s.

    Matando solo el python, el envoltorio lo resucita y le pelea el 9100 al
    servicio: /health puede responder desde el agente manual mientras el
    servicio se reinicia en bucle.
    """
    instalador = (AGENT_DIR / "core" / script).read_text(encoding="utf-8")
    assert f"{envoltorio}\\.sh" in instalador, "El instalador no mata el envoltorio del modo manual"
    assert "PAT_ENVOLTORIO" in instalador and "PAT_AGENTE" in instalador
    # El envoltorio se mata ANTES que el agente, o lo relanza.
    cuerpo = instalador[instalador.index("_matar() {"):]
    assert cuerpo.index("PAT_ENVOLTORIO") < cuerpo.index("PAT_AGENTE")


@pytest.mark.parametrize(
    "script", ["instalar-servicio-mac.sh", "instalar-servicio-linux.sh"]
)
def test_los_instaladores_no_se_cuelgan_con_una_opcion_sin_valor(script):
    """`shift 2` con un solo argumento no desplaza nada: bucle infinito."""
    instalador = (AGENT_DIR / "core" / script).read_text(encoding="utf-8")
    assert instalador.count("[ $# -ge 2 ] || die") >= 2, (
        "--origins y --certs-from deben exigir su valor antes del shift 2"
    )
    # Y `warn` a stderr: se le llama desde funciones cuyo resultado se captura.
    assert 'warn()  { echo "[AVISO] $*" >&2; }' in instalador


def test_el_instalador_mac_explica_el_fallo_de_bootstrap_por_ssh():
    """Un LaunchAgent no carga por SSH; el mensaje tiene que decirlo."""
    instalador = (AGENT_DIR / "core" / "instalar-servicio-mac.sh").read_text(encoding="utf-8")
    assert "Bootstrap failed: 5" in instalador
    assert "SSH" in instalador
    assert "Compartir pantalla" in instalador
    # --dry-run --uninstall no puede desinstalar de verdad.
    bloque = instalador[instalador.index('if [ "$UNINSTALL" -eq 1 ]; then'):]
    bloque = bloque[: bloque.index("\nfi\n")]
    assert 'if [ "$DRY_RUN" -eq 1 ]; then' in bloque


def test_los_launchers_no_dicen_rmazh():
    """El bundle se le entrega a clientes de Atlas One, no de Rmazh."""
    for nombre in ("impresora_mac.sh", "impresora_linux.sh", "impresora_win.bat"):
        texto = (AGENT_DIR / nombre).read_text(encoding="utf-8")
        assert "RMAZH" not in texto.upper(), f"{nombre} sigue con el banner de Rmazh"
        assert "ATLAS ONE" in texto.upper()


# ── macOS 14+ ya no admite colas raw ─────────────────────────────────────────
# Hallazgo de campo (Mac del dueño, 2026-09-19): `lpadmin … -m raw` responde
# "Raw queues are no longer supported on macOS". La cola pasa a crearse con un
# PPD genérico y el raw se fuerza en cada impresión con `lp -o raw`.
#
# Estos tests leen el FUENTE del agente en vez de importarlo. Importar
# `main.py` instancia FastAPI y, de paso, abre un RotatingFileHandler que
# crearía `tools/print_agent/core/agent.log` dentro del repo en cada corrida de
# la suite. Es el mismo enfoque que `tests/test_print_agent_origins.py`.
AGENT_MAIN = AGENT_DIR / "core" / "main.py"


def test_en_macos_lp_lleva_o_raw_y_en_linux_no():
    """En macOS el PPD genérico filtraría los ESC/POS; `-o raw` lo evita.

    Las tres rutas de impresión (/print, /printers/test-print, /drawer/open)
    pasan por `_print_unix`, así que basta con esta forma de comando.
    """
    codigo = AGENT_MAIN.read_text(encoding="utf-8")

    assert '["lp", "-d", printer_name, "-o", "raw", "-"] if _IS_MAC' in codigo, (
        "macOS necesita `lp -o raw`: sin él el PPD genérico reinterpreta el ticket"
    )
    assert 'else ["lp", "-d", printer_name, "-"]' in codigo, (
        "Linux no debe cambiar: ahí la cola sí se crea en modo raw"
    )

    # Y las tres rutas siguen pasando por _print_unix (si alguna dejara de
    # hacerlo, se saltaría el -o raw sin que nada lo avise).
    assert codigo.count("_print_unix(") >= 4


def test_en_macos_la_cola_se_crea_con_ppd_generico():
    """`-m raw` está prohibido en macOS 14+; `-m raw` se queda solo en Linux."""
    codigo = AGENT_MAIN.read_text(encoding="utf-8")

    assert "_mac_generic_ppd_args" in codigo
    assert "PrintCore.framework" in codigo and "Generic.ppd" in codigo
    assert "drv:///sample.drv/generic.ppd" in codigo, "Falta el respaldo del PPD"
    # El mensaje de fallo tiene que ser accionable.
    assert "lpinfo -m | grep -i generic" in codigo

    bloque = codigo[codigo.index("# 1. lpadmin -p NAME"):]
    bloque = bloque[: bloque.index("ok1 = _run_step")]
    assert 'modelo = ["-m", "raw"]' in bloque, "Linux debe seguir usando -m raw"
    assert "if _IS_MAC:" in bloque


def test_en_macos_las_colas_no_se_marcan_como_driver():
    """En macOS el raw no es propiedad de la cola sino del envío.

    Marcarlas como "driver" en el diagnóstico asustaría al usuario con un
    problema que no tiene y lo mandaría a re-crear la cola con `-m raw`, que
    es justo lo que macOS rechaza.
    """
    codigo = AGENT_MAIN.read_text(encoding="utf-8")
    bloque = codigo[codigo.index('# lpoptions -p NAME -l'):]
    bloque = bloque[: bloque.index("return list(queues.values())")]
    assert "if _IS_MAC:" in bloque and 'q["is_raw"] = True' in bloque

    assert '"lp -o raw (macOS sin colas raw)"' in codigo, (
        "El diagnóstico debe explicar de dónde sale el raw en macOS"
    )
