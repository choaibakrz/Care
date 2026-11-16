"""La clinique en boîte — H13 (relecture de la tranche 3, points 7, 9, 13).

« Fini » veut dire :
- la panne d'un robot simulé et le passage d'une course à un humain sont écrits dans la boîte noire (le « fini quand »
  de T24 le demande), sans nom de patient ; avant : dans le carnet seulement ;
- la page « Pourquoi ? » du tableau de flotte montre le feu du gardien (K04) : pour un robot simulé, elle dit qu'aucun
  geste n'est demandé au gardien ; pour le robot branché, elle compte les « oui » et les « non » ;
- un changement de carte se voit sur le tableau de flotte : la nouvelle carte dans la ligne du robot, et la trace du changement.
Robots SIMULÉS et faux robot. Aucun vrai robot.
"""
from __future__ import annotations

import asyncio
import html

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique.carnet import Carnet
from briques.clinique.coursier import monde_de_la_clinique
from briques.clinique.ecrans import brancher_ecrans
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.porte import JournalDesAcces, PorteDeLecture
from commun.systeme import REGLAGES_EXEMPLE, Systeme, charger_reglages

CODE = {"X-Code-Equipe": "code-d-essai"}
PAGE = "/clinique/tableau-de-flotte"


class Boite:
    """Une fausse boîte noire : elle garde ce qu'on lui écrit."""

    def __init__(self) -> None:
        self.notes: list[dict] = []

    async def emettre(self, genre, source, **donnees):
        self.notes.append({"genre": genre, "source": source, **donnees})


def _banc(bus=None):
    horloge, app = HorlogeDeDemonstration(bus=bus), FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge), code_equipe="code-d-essai")
    return TestClient(app), clinique


def _demander(client):
    r = client.post("/api/clinique/demande", json={"badge": "soignant-etage-2", "patient": "p01", "texte": "la couverture"})
    return r.json()["tache"]["id"]


def test_la_panne_et_le_passage_a_un_humain_sont_dans_la_boite_noire_sans_nom_de_patient():
    boite = Boite()
    client, _ = _banc(bus=boite)
    ident = _demander(client)
    client.post("/api/clinique/flotte/attribuer", json={"tache": ident}, headers=CODE)
    for robot in ("robot-r2", "robot-r3", "robot-r4"):
        assert client.post("/api/clinique/flotte/panne", json={"robot": robot, "raison": "batterie basse"}, headers=CODE).status_code == 200
    pannes = [n for n in boite.notes if n.get("quoi") == "panne_de_robot"]
    assert [p["robot"] for p in pannes] == ["robot-r2", "robot-r3", "robot-r4"]
    assert pannes[0]["tache"] == ident and pannes[0]["provoquee"] is True and "SIMULÉ" in pannes[0]["etiquette"]
    assert pannes[0]["genre"] == "note" and "batterie basse" in pannes[0]["raison"]
    assert client.post("/api/clinique/flotte/reprendre", json={"tache": ident}, headers=CODE).json()["sorte"] == "humain"
    humain = [n for n in boite.notes if n.get("quoi") == "course_a_un_humain"]
    assert len(humain) == 1 and humain[0]["tache"] == ident and "un humain reprend la main" in humain[0]["pourquoi"]
    assert "p01" not in str(boite.notes) and "Giulia" not in str(boite.notes)


def test_une_panne_en_route_non_provoquee_est_aussi_dans_la_boite_noire():
    boite = Boite()
    client, clinique = _banc(bus=boite)
    ident = _demander(client)
    client.post("/api/clinique/flotte/attribuer", json={"tache": ident}, headers=CODE)
    clinique.tableau_de_flotte.monde._robots["robot-r2"]["batterie"] = clinique.tableau_de_flotte.monde.seuil + 1
    for _ in range(6):
        client.post("/api/clinique/flotte/pas", headers=CODE)
    pannes = [n for n in boite.notes if n.get("quoi") == "panne_de_robot"]
    assert len(pannes) == 1 and pannes[0]["provoquee"] is False and pannes[0]["robot"] == "robot-r2"


def test_sans_boite_noire_rien_ne_casse():
    client, _ = _banc()
    ident = _demander(client)
    client.post("/api/clinique/flotte/attribuer", json={"tache": ident}, headers=CODE)
    assert client.post("/api/clinique/flotte/panne", json={"robot": "robot-r2", "raison": "x"}, headers=CODE).status_code == 200


def test_pourquoi_du_tableau_pour_un_robot_simule_dit_qu_aucun_geste_n_est_demande_au_gardien():
    client, _ = _banc()
    ident = _demander(client)
    client.post("/api/clinique/flotte/attribuer", json={"tache": ident}, headers=CODE)
    page = html.unescape(client.get(f"/clinique/flotte/pourquoi?tache={ident}").text)
    assert "Le feu du gardien" in page and "aucun geste n'est demandé au gardien" in page and "rien ne bouge" in page
    assert "Feu vert" not in page and "Feu <b>vert" not in page


def test_pourquoi_du_tableau_pour_le_robot_branche_compte_les_oui_du_gardien(tmp_path):
    reglages = charger_reglages(REGLAGES_EXEMPLE)
    reglages["cerveau"] = {**reglages["cerveau"], "choix": "regles"}
    systeme = Systeme(reglages, dossier_journal=str(tmp_path), acceleration=20.0, monde=monde_de_la_clinique())
    horloge, app = HorlogeDeDemonstration(bus=systeme.bus), FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge), systeme=systeme, code_equipe="code-d-essai")

    async def jouer():
        await systeme.demarrer()
        try:
            tache = clinique.taches.demander(clinique.badges["soignant-etage-2"], "p01", "la couverture")["tache"]
            fin = await clinique.coursier.faire(tache["id"])
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
                return fin, (await client.get(f"/clinique/flotte/pourquoi?tache={tache['id']}")).text
        finally:
            await systeme.arreter()

    fin, brut = asyncio.run(jouer())
    page = html.unescape(brut)
    assert fin["etat"] == "livrée", fin
    assert "Le feu du gardien" in page and "Feu <b>vert</b>" in brut and "4 oui, 0 non" in page


def test_un_changement_de_carte_se_voit_sur_le_tableau_de_flotte():
    client, clinique = _banc()
    assert "Changements de carte" not in client.get(PAGE).text
    clinique.tableau_de_flotte.cartes.changer("robot-r3", "Nuit", qui="essai")
    brut = client.get(PAGE).text
    page = html.unescape(brut)
    assert "<td><b>R3</b></td><td>Nuit</td>" in brut
    assert "Changements de carte" in page and "R3 : carte Thérapie → Nuit (par essai)" in page
