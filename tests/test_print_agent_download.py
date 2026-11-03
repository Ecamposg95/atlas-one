"""La descarga del agente redirige al repositorio externo.

El agente dejo de vivir en este repo (2026-09-22): se mantiene en
https://github.com/Ecamposg95/Atlas-Print-Agent para todos los productos. Por
omision se baja el instalador de la version publicada; `formato=zip`, el codigo
para el modo manual.
"""
import pytest

REL = "https://github.com/Ecamposg95/Atlas-Print-Agent/releases/download/v3.1.0/"


@pytest.mark.parametrize("plataforma,archivo", [
    ("windows", "atlas-print-agent-setup-3.1.0.exe"),
    ("linux", "atlas-print-agent_3.1.0_amd64.deb"),
    ("mac", "atlas-print-agent-3.1.0-arm64.pkg"),
    ("mac-intel", "atlas-print-agent-3.1.0-x86_64.pkg"),
])
def test_baja_el_instalador_de_cada_sistema(client, plataforma, archivo):
    r = client.get(f"/api/printer/download-agent?platform={plataforma}", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == REL + archivo


def test_zip_del_modo_manual(client):
    r = client.get("/api/printer/download-agent?platform=windows&formato=zip", follow_redirects=False)
    assert r.headers["location"] == "https://github.com/Ecamposg95/Atlas-Print-Agent/archive/refs/heads/main.zip"


def test_plataforma_o_formato_invalidos(client):
    assert client.get("/api/printer/download-agent?platform=amiga", follow_redirects=False).status_code == 400
    assert client.get("/api/printer/download-agent?formato=rar", follow_redirects=False).status_code == 400


def test_url_configurable_por_plataforma(client, monkeypatch):
    monkeypatch.setenv("ATLAS_PRINT_AGENT_URL", "https://ejemplo.mx/agente-{platform}.zip")
    r = client.get("/api/printer/download-agent?platform=linux", follow_redirects=False)
    assert r.headers["location"] == "https://ejemplo.mx/agente-linux.zip"
