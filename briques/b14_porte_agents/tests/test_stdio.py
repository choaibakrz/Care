"""Brique 14 — la vraie commande « python3 lancer.py porte-agents », dans un autre programme, parlée par stdio.

Le client MCP officiel lance la commande (comme le ferait un agent de bureau) et lui parle par l'entrée et la sortie
standard. Internet est coupé dans l'autre programme dès son démarrage (sitecustomize). L'écran tourne dans le même
programme : un « humain » (ce test) accepte la demande du gardien par l'écran, comme Hiba le ferait. Faux robot.
"""
from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path

import httpx

from conftest import lancer

RACINE = Path(__file__).resolve().parents[3]
GARDE = """\
import pathlib, socket
_c = socket.socket.connect
def _connect(self, a):
    if isinstance(a, tuple) and a[0] not in ('127.0.0.1', '::1', 'localhost'):
        raise ConnectionRefusedError('Internet coupé pour ce test')
    return _c(self, a)
socket.socket.connect = _connect
_g = socket.getaddrinfo
def _getaddrinfo(h, *a, **k):
    if h not in (None, 'localhost', '127.0.0.1', '::1', '0.0.0.0'):
        raise socket.gaierror('Internet coupé pour ce test')
    return _g(h, *a, **k)
socket.getaddrinfo = _getaddrinfo
"""


def _port_libre() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_la_commande_porte_agents_parle_mcp_sur_stdio_et_l_humain_accepte_par_l_ecran(tmp_path):
    import anyio
    from mcp import Client, StdioServerParameters

    garde = tmp_path / "garde"
    garde.mkdir()
    (garde / "sitecustomize.py").write_text(GARDE, encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(garde), os.environ.get("PYTHONPATH", "")]).rstrip(os.pathsep),
           "LEUKERBAD_CODE_EQUIPE": "code-de-test-stdio"}  # relecture du lot C : l'écran de la porte exige le code
    port = _port_libre()
    journal = tmp_path / "journal"
    parametres = StdioServerParameters(
        command=sys.executable, cwd=str(tmp_path), env=env,
        args=[str(RACINE / "lancer.py"), "porte-agents", "--agent", "jury", "--cerveau", "regles",
              "--acceleration", "20", "--port", str(port), "--journal", str(journal)])
    reglages, existait = RACINE / "reglages.yaml", (RACINE / "reglages.yaml").exists()

    async def jouer():
        with anyio.fail_after(120):
            async with Client(parametres, mode="legacy", read_timeout_seconds=60) as c:
                assert c.server_info.name == "leukerbad-porte-des-agents"
                assert {t.name for t in (await c.list_tools()).tools} == {
                    "dire_au_robot", "voir_carte", "voir_etat", "voir_fiche", "arreter"}
                carte = (await c.call_tool("voir_carte", {})).structured_content
                assert carte["mention"] == "testé sur faux robot" and carte["porte"]["accord_humain"] is True
                # Réglages par défaut : l'accord d'un humain est allumé.
                r = (await c.call_tool("dire_au_robot", {"texte": "Va à la table", "langue": "fr"})).structured_content
                assert r["statut"] == "attend_un_humain", r
                async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=10) as sans_code:
                    # L'agent tourne sur cet ordinateur : sans le code, il ne peut pas accepter sa propre demande.
                    refus = await sans_code.post("/api/aide/repondre", json={"numero": r["numero_demande"],
                                                                             "accepte": True, "qui": "Hiba"})
                    assert refus.status_code == 403
                    assert (await sans_code.post("/api/rearmer")).status_code == 403
                async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=10,
                                             headers={"X-Code-Equipe": "code-de-test-stdio"}) as ecran:
                    aides = (await ecran.get("/api/aides")).json()["en_attente"]
                    assert [a["demandeur"] for a in aides] == ["agent:jury"]
                    rep = await ecran.post("/api/aide/repondre", json={"numero": r["numero_demande"], "accepte": True,
                                                                         "qui": "Hiba"})
                    assert rep.json()["ok"] is True
                for _ in range(100):
                    etat = (await c.call_tool("voir_etat", {})).structured_content
                    if etat["mes_dernieres_actions"] and etat["mes_dernieres_actions"][-1]["statut"] == "reussie":
                        break
                    await anyio.sleep(0.1)
                assert etat["mes_dernieres_actions"][-1]["action"]["parametres"]["lieu"] == "table"
                r = (await c.call_tool("dire_au_robot", {"texte": "Take the suitcase", "langue": "en"})).structured_content
                assert r["statut"] == "refusee" and "not allowed to touch: suitcase" in r["reponses"][0]
                assert (await c.call_tool("arreter", {})).structured_content["ok"] is True
                fiche = (await c.call_tool("voir_fiche", {})).structured_content
                assert fiche["demandes_agents"] == 2 and fiche["arrets_urgence"] == 1

    try:
        lancer(jouer())
    finally:
        # lancer.py crée reglages.yaml depuis l'exemple au premier lancement : on ne laisse pas de trace.
        exemple = (RACINE / "reglages.exemple.yaml").read_text(encoding="utf-8")
        if not existait and reglages.exists() and reglages.read_text(encoding="utf-8") == exemple:
            reglages.unlink()
    lignes = [json.loads(l) for f in journal.glob("*.jsonl") for l in f.read_text(encoding="utf-8").splitlines() if l]
    types = [(l["type"], l["source"]) for l in lignes]
    assert ("porte_agents", "porte_agents") in types and ("parole_entendue", "agent:jury") in types
    assert any(l["type"] == "aide_recue" and l["donnees"]["qui"] == "Hiba" for l in lignes)
    assert any(l["type"] == "session_fin" for l in lignes), "la porte s'est fermée proprement"
