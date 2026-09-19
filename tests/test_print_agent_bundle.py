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


def test_zip_linux_incluye_instalador_de_servicio_y_unidad_systemd():
    """El ZIP de Linux debe permitir instalar el autoarranque, no solo el modo manual."""
    from app.routers.printer import download_print_agent

    class _U:  # el endpoint solo usa el usuario como gate de auth
        pass

    resp = download_print_agent(platform="linux", current_user=_U())
    import asyncio
    import io
    import zipfile

    async def _drain():
        return b"".join([chunk async for chunk in resp.body_iterator])

    payload = asyncio.run(_drain())
    nombres = {Path(n).name for n in zipfile.ZipFile(io.BytesIO(payload)).namelist()}

    for requerido in (
        "impresora_linux.sh",
        "instalar-servicio-linux.sh",
        "atlas-print-agent.service",
        "INSTALL_LINUX.txt",
    ):
        assert requerido in nombres, f"El ZIP de Linux no incluye {requerido}"

    # Y no debe arrastrar los launchers de otras plataformas.
    assert "impresora_win.bat" not in nombres
    assert "impresora_mac.sh" not in nombres


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
