"""Brique 14 — petits outils communs aux tests de la porte des agents (pas un fichier de tests)."""
from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from briques.b14_porte_agents.porte import PorteDesAgents, ReglagesPorte
from briques.b14_porte_agents.serveur_mcp import creer_serveur


@pytest.fixture
def systeme(reglages, fabrique_systeme):
    """systeme(accord_humain=False) : un système sur le faux humanoïde (cerveau à règles), réglages de la porte donnés."""
    def fabrique(carte: str = "humanoide", **porte_agents):
        reglages["porte_agents"] = {**(reglages.get("porte_agents") or {}), **porte_agents}
        return fabrique_systeme(carte)

    return fabrique


@asynccontextmanager
async def session(s, nom: str = "test", **reglages_porte):
    """Un agent branché par MCP : le client officiel du paquet `mcp`, en mémoire, avec la poignée de main JSON-RPC
    « initialize » (mode « legacy »), comme un client de bureau. Le système démarre et s'arrête avec la session."""
    from mcp import Client

    porte = PorteDesAgents(s, nom=nom, reglages=ReglagesPorte(**reglages_porte) if reglages_porte else None)

    @asynccontextmanager
    async def cycle():
        await s.demarrer()
        await porte.ouvrir("memoire")
        try:
            yield
        finally:
            await s.arreter()

    async with Client(creer_serveur(porte, cycle), mode="legacy") as client:
        yield client, porte


async def appeler(client, outil: str, **arguments) -> dict:
    r = await client.call_tool(outil, arguments)
    assert not r.is_error, r.content
    return r.structured_content


def evenements(s, type_: str, conversation: str | None = None) -> list:
    return [e for e in s.bus.historique if e.type == type_ and (conversation is None or e.conversation == conversation)]


async def preparer(s, avant: dict | None) -> None:
    """Comme les tests du gardien : ce que des HUMAINS préparent avant l'ordre (règle allumée, personne, vote)."""
    from briques.b07_gardien.vote import appliquer_vote

    avant = avant or {}
    if "allumer" in avant:
        await s.gardien.changer_regle(avant["allumer"], active=True, qui="test")
    if "personne" in avant:
        s.gardien.perception.placer_personne("essai", avant["personne"]["x"], avant["personne"]["y"])
    if "vote" in avant:
        await appliquer_vote(s.gardien, avant["vote"]["vote"], avant["vote"]["resultats"], qui="test")
