"""La descarga del agente redirige al repositorio externo.

El agente dejo de vivir en este repo (2026-09-22): se mantiene en
https://github.com/Ecamposg95/Atlas-Print-Agent para todos los productos.
"""
import os


def test_redirige_al_repositorio_del_agente(client):
    r = client.get("/api/printer/download-agent?platform=mac", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "https://github.com/Ecamposg95/Atlas-Print-Agent/archive/refs/heads/main.zip"


def test_plataforma_invalida(client):
    assert client.get("/api/printer/download-agent?platform=amiga", follow_redirects=False).status_code == 400


def test_url_configurable_por_plataforma(client, monkeypatch):
    monkeypatch.setenv("ATLAS_PRINT_AGENT_URL", "https://ejemplo.mx/agente-{platform}.zip")
    r = client.get("/api/printer/download-agent?platform=linux", follow_redirects=False)
    assert r.headers["location"] == "https://ejemplo.mx/agente-linux.zip"
