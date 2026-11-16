"""K07b — Les quatre boutons de l'invité, dans six ordres, avec une remise à zéro entre chaque (avenant 2, K07).

    python3 lancer.py invite-essai                  les six ordres, le scénario rejoué, la taille du texte (si Chrome est là)
    python3 lancer.py invite-essai --sans-lisibilite

1. Une clinique est branchée (comme le serveur des écrans), avec une boîte noire qui garde tout. Le faux logiciel
   administratif travaille dans un dossier à part, le temps de l'essai : jamais celui de l'équipe.
2. Six ordres différents des quatre boutons (tirer, langue, objet, panne). Après chaque ordre : « Remettre à zéro »,
   chronométrée. Un ordre est réussi si chaque bouton a répondu, si la panne était bien en cours avant la remise à zéro
   et finie après, et si le faux logiciel est vide après.
3. Chaque action doit porter la marque INVITÉ dans la boîte noire.
4. Puis le scénario se rejoue : la grande répétition.
5. Puis, si Chrome est là, la taille du texte des écrans Invité et Patient (lisibilite.py).
Faux robot et robots simulés. Rien ne part de l'ordinateur. Aucun vrai robot.
"""
from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Any, Callable

BOUTONS = ("tirage", "langue", "objet", "panne")
ORDRES = (("tirage", "langue", "objet", "panne"), ("panne", "objet", "langue", "tirage"), ("langue", "panne", "tirage", "objet"),
          ("objet", "tirage", "panne", "langue"), ("panne", "tirage", "langue", "objet"), ("objet", "langue", "tirage", "panne"))
CODE = "code-de-l-essai-invite"  # un code pour cet essai seulement : le client d'essai n'est pas « cet ordinateur »
CHOIX = {"tirage": {}, "langue": {"choix": "de"}, "objet": {"choix": "un fauteuil roulant"}, "panne": {}}


class Boite:
    """Une boîte noire pour l'essai : elle garde ce qu'on lui écrit, dans l'ordre."""

    def __init__(self) -> None:
        self.notes: list[dict[str, Any]] = []

    async def emettre(self, genre, source, **donnees):
        self.notes.append({"genre": genre, "source": source, **donnees})


def _banc(dossier: Path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from .carnet import Carnet
    from .ecrans import brancher_ecrans
    from .horloge import HorlogeDeDemonstration
    from .porte import JournalDesAcces, PorteDeLecture

    boite = Boite()
    horloge, app = HorlogeDeDemonstration(bus=boite), FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge), code_equipe=CODE)
    clinique.faux_logiciel.dossier = dossier / "faux_logiciel"  # jamais le vrai dossier de l'équipe
    return TestClient(app, headers={"X-Code-Equipe": CODE}), clinique, boite


def _remettre_a_zero(client) -> tuple[float, int]:
    debut = time.monotonic()
    r = client.post("/api/clinique/invite/zero", json={})
    return time.monotonic() - debut, r.status_code


def essayer(ecrire: Callable[[str], None] = print, avec_lisibilite: bool = True) -> dict[str, Any]:
    from . import chef_clinique

    ecrire("L'INVITÉ AUX COMMANDES — six ordres des quatre boutons — DONNÉES INVENTÉES — FAUX ROBOT")
    bilan: dict[str, Any] = {"ordres_reussis": 0, "remises": [], "actions_invite": 0, "sans_marque": 0}
    with tempfile.TemporaryDirectory() as dossier:
        client, clinique, boite = _banc(Path(dossier))
        for rang, ordre in enumerate(ORDRES, 1):
            problemes = []
            for bouton in ordre:
                r = client.post(f"/api/clinique/invite/{bouton}", json=CHOIX[bouton])
                if r.status_code != 200:
                    problemes.append(f"{bouton} : refusé ({r.status_code})")
                elif bouton != "panne" and not r.json().get("reussi"):
                    problemes.append(f"{bouton} : pas réussi ({str(r.json().get('dit'))[:120]})")
            if not clinique.pannes.active("lien_robot"):
                problemes.append("la panne n'est pas en cours avant la remise à zéro")
            en_attente = next(p for p in clinique.faux_logiciel.liste() if not p["verrouille"])
            clinique.faux_logiciel.evenement("A05", en_attente["numero_patient"])  # le faux logiciel a bougé, lui aussi
            secondes, code = _remettre_a_zero(client)
            bilan["remises"].append(round(secondes, 2))
            if code != 200 or secondes >= 10:
                problemes.append(f"remise à zéro : code {code}, {secondes:.1f} s")
            if clinique.pannes.actives():
                problemes.append(f"après la remise à zéro, panne encore en cours : {', '.join(clinique.pannes.actives())}")
            if clinique.faux_logiciel.messages():
                problemes.append("après la remise à zéro, le faux logiciel a encore des messages")
            bilan["ordres_reussis"] += not problemes
            ecrire(f"  ordre {rang} : {' → '.join(ordre)} → remise à zéro ({secondes:.2f} s) — "
                   + ("réussi" if not problemes else "RATÉ : " + " ; ".join(problemes)))
        actions = [n for n in boite.notes if n.get("quoi") == "action_de_l_invite"]
        bilan["actions_invite"] = len(actions)
        bilan["sans_marque"] = sum(1 for n in actions if n.get("marque") != "INVITÉ")
        bilan["etat_propre"] = not clinique.pannes.actives() and not clinique.faux_logiciel.messages()
    ecrire(f"  boîte noire : {bilan['actions_invite']} actions de l'invité, {bilan['sans_marque']} sans la marque INVITÉ ; "
           f"remise à zéro la plus longue : {max(bilan['remises']):.2f} s (limite : 10 s)")
    sortie: list[str] = []
    code = chef_clinique.jouer(ecrire=sortie.append)
    bilan["scenario"] = "RÉUSSIE" if code == 0 else "RATÉE"
    ecrire(f"  puis le scénario rejoué : {sortie[-1] if sortie else 'rien'}")
    if avec_lisibilite:
        bilan["lisibilite"] = _lisibilite(ecrire)
    reussi = (bilan["ordres_reussis"] == len(ORDRES) and bilan["sans_marque"] == 0
              and bilan["actions_invite"] == 5 * len(ORDRES) and bilan["scenario"] == "RÉUSSIE" and bilan["etat_propre"]
              and bilan.get("lisibilite") is not False)
    ecrire("INVITÉ — SIX ORDRES : RÉUSSI" if reussi else
           f"INVITÉ — SIX ORDRES : RATÉ ({bilan['ordres_reussis']} ordres réussis sur {len(ORDRES)})")
    bilan["reussi"] = reussi
    return bilan


def _lisibilite(ecrire: Callable[[str], None]) -> bool | None:
    """True : les deux écrans atteignent le seuil ; False : non ; None : Chrome absent, pas mesuré (et on le dit)."""
    import asyncio
    import socket
    import subprocess
    import threading

    import httpx
    import uvicorn
    from fastapi import FastAPI

    from . import lisibilite
    from .ecrans import brancher_ecrans
    from .tests.test_clic_dans_le_navigateur import CHROME

    seuil = lisibilite.seuil_px()
    if not CHROME.exists():
        ecrire(f"  taille du texte : PAS MESURÉE — Chrome n'est pas sur cet ordinateur (seuil des réglages : {seuil:g} px)")
        return None

    def port_libre() -> int:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    app = FastAPI()
    clinique = brancher_ecrans(app)
    with tempfile.TemporaryDirectory() as dossier:
        clinique.faux_logiciel.dossier = Path(dossier) / "faux_logiciel"
        port, port_chrome = port_libre(), port_libre()
        service = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
        threading.Thread(target=service.run, daemon=True).start()
        chrome = subprocess.Popen([str(CHROME), "--headless=new", "--disable-gpu", "--no-first-run",
                                   f"--remote-debugging-port={port_chrome}", f"--user-data-dir={Path(dossier) / 'profil'}",
                                   "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            adresse = None
            for _ in range(100):
                try:
                    httpx.get(f"http://127.0.0.1:{port}/clinique", timeout=0.5)
                    pages = [x for x in httpx.get(f"http://127.0.0.1:{port_chrome}/json", timeout=0.5).json()
                             if x.get("type") == "page"]
                    if pages:
                        adresse = pages[0]["webSocketDebuggerUrl"]
                        break
                except (httpx.HTTPError, ValueError):
                    pass
                time.sleep(0.1)
            if adresse is None:
                ecrire("  taille du texte : PAS MESURÉE — Chrome ne s'ouvre pas avec sa porte de pilotage")
                return None
            bons = True
            for nom, chemin in lisibilite.ECRANS.items():
                m = asyncio.run(lisibilite.mesurer(adresse, f"http://127.0.0.1:{port}{chemin}"))
                ok = m["plus_petite_px"] is not None and m["plus_petite_px"] >= seuil
                bons = bons and ok
                ecrire(f"  taille du texte, écran {nom} : la plus petite est {m['plus_petite_px']:g} px sur {m['textes']} textes "
                       f"(seuil des réglages : {seuil:g} px) — "
                       + ("atteint" if ok else "PAS ATTEINT : " + str(m["les_plus_petits"][:2])))
            ecrire("  (mesuré dans Chrome sans fenêtre ; le contraste et « une idée par ligne » ne sont pas mesurés)")
            return bons
        finally:
            chrome.terminate()
            try:
                chrome.wait(timeout=10)
            except subprocess.TimeoutExpired:
                chrome.kill()
            service.should_exit = True


def main(reste: list[str] | None = None) -> int:
    return 0 if essayer(avec_lisibilite="--sans-lisibilite" not in (reste or []))["reussi"] else 1
