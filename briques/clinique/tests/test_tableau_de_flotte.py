"""La clinique en boîte — T25, le tableau de flotte (cahier 5.10 ; avenant 2, K03 et K04).

« Une page : le plan des lieux, les robots, leur carte, leur batterie, leur tâche, avec l'étiquette RÉEL, FAUX ROBOT ou
SIMULÉ sur chacun. »
« Fini » veut dire :
- la page montre le plan (les lieux, par étage, et où est chaque robot), et pour chaque robot : sa carte, sa batterie,
  son état, sa tâche, son étiquette ;
- elle dit combien de robots sont simulés, et qu'un robot simulé ne bouge pas ;
- on voit l'âge de l'information (K03), et le bouton « Pourquoi ? » d'une tâche attribuée ouvre le choix du répartiteur (K04) ;
- de la page, on peut faire avancer le temps du monde simulé, provoquer une panne et lancer la reprise : la tâche passe
  « reprise », puis au robot libre le plus proche, et le tableau le montre ;
- ces boutons demandent le code d'équipe depuis un autre ordinateur ; un robot inconnu ou le robot branché sont refusés ;
- aucun nom de patient sur cette page.
Robots simulés : rien ne bouge. Aucun vrai robot.
"""
from __future__ import annotations

import html
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique.carnet import Carnet
from briques.clinique.ecrans import brancher_ecrans
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.porte import JournalDesAcces, PorteDeLecture

CODE = {"X-Code-Equipe": "code-d-essai"}
PAGE = "/clinique/tableau-de-flotte"


@pytest.fixture
def banc():
    horloge, app = HorlogeDeDemonstration(), FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge), code_equipe="code-d-essai")
    return TestClient(app), clinique


def _texte(client) -> str:
    return html.unescape(client.get(PAGE).text)


def _demander(client, texte="la couverture"):
    r = client.post("/api/clinique/demande", json={"badge": "soignant-etage-2", "patient": "p01", "texte": texte})
    assert r.status_code == 200, r.text
    return r.json()["tache"]["id"]


def test_la_page_montre_le_plan_les_robots_leur_carte_leur_batterie_et_leur_etiquette(banc):
    client, _ = banc
    brut = client.get(PAGE)
    page = html.unescape(brut.text)
    assert brut.status_code == 200 and "DONNÉES INVENTÉES" in page and "Tableau de flotte" in page
    assert "3 robots simulés sur 4" in page and "rien ne bouge" in page
    for lieu in ("Réserve", "Poste de soins", "Chambre 12", "Salon", "Hall"):  # le plan : les lieux, par étage
        assert lieu in page, lieu
    assert "Étage 2" in page and "Rez-de-chaussée" in page
    for robot, carte in (("R1", "Étage"), ("R2", "Étage"), ("R3", "Thérapie"), ("R4", "Nuit")):
        assert re.search(rf"<td><b>{robot}</b></td><td>{carte}</td>", brut.text), robot
    assert page.count("FAUX ROBOT — SIMULÉ") >= 3 and "100 %" in page
    assert re.search(r"<td><b>R1</b></td><td>Étage</td><td>FAUX ROBOT</td>", brut.text)  # le robot branché : jamais « SIMULÉ »
    assert "Les trois étiquettes" in page and "RÉEL" in page
    assert PAGE in client.get("/clinique").text


def test_la_page_dit_l_age_de_l_information_et_se_met_a_jour(banc):
    client, _ = banc
    brut = client.get(PAGE).text
    assert "id='age'" in brut and f"{PAGE}/contenu" in brut and "setInterval" in brut
    assert client.get(f"{PAGE}/contenu").status_code == 200


def test_une_tache_attribuee_se_voit_avec_son_robot_et_le_bouton_pourquoi(banc):
    client, clinique = banc
    ident = _demander(client)
    r = client.post("/api/clinique/flotte/attribuer", json={"tache": ident}, headers=CODE)
    assert r.status_code == 200 and r.json()["robot"] == "robot-r2", r.text
    brut = client.get(PAGE).text
    page = html.unescape(brut)
    assert "couverture → Chambre 12" in page and "J'envoie R2" in page
    assert f"/clinique/flotte/pourquoi?tache={ident}" in brut and "Pourquoi ?" in page
    pourquoi = html.unescape(client.get(f"/clinique/flotte/pourquoi?tache={ident}").text)
    assert "J'envoie R2" in pourquoi and "le plus proche" in pourquoi
    for nom in ("R1", "R2", "R3", "R4"):  # les robots regardés, un par un
        assert nom in pourquoi


def test_de_la_page_une_panne_puis_la_reprise_par_le_plus_proche(banc):
    client, clinique = banc
    ident = _demander(client)
    client.post("/api/clinique/flotte/attribuer", json={"tache": ident}, headers=CODE)
    assert client.post("/api/clinique/flotte/pas", headers=CODE).status_code == 200
    panne = client.post("/api/clinique/flotte/panne", json={"robot": "robot-r2", "raison": "batterie basse"}, headers=CODE)
    assert panne.status_code == 200 and panne.json()["tache"]["etat"] == "reprise"
    page = _texte(client)
    assert "en panne" in page and "batterie basse (panne provoquée)" in page and "reprise" in page
    assert f"data-reprendre=\"{ident}\"" in client.get(PAGE).text
    reprise = client.post("/api/clinique/flotte/reprendre", json={"tache": ident}, headers=CODE)
    assert reprise.status_code == 200 and reprise.json()["robot"] == "robot-r4" and reprise.json()["etat"] == "en route"
    page = _texte(client)
    assert "J'envoie R4" in page and "reprise de R2" in page
    for _ in range(40):
        client.post("/api/clinique/flotte/pas", headers=CODE)
    assert "arrivé dans le monde simulé" in _texte(client)
    assert clinique.taches.tache(ident)["etat"] == "en route"  # un robot simulé ne livre jamais
    assert len(clinique.carnet.lignes("panne de robot")) == 1


def test_les_boutons_demandent_le_code_d_equipe_et_refusent_ce_qui_n_a_pas_de_sens(banc):
    client, _ = banc
    ident = _demander(client)
    for chemin, corps in (("pas", None), ("panne", {"robot": "robot-r2", "raison": "x"}), ("attribuer", {"tache": ident}),
                          ("reprendre", {"tache": ident})):
        assert client.post(f"/api/clinique/flotte/{chemin}", json=corps).status_code == 403, chemin
    assert client.post("/api/clinique/flotte/panne", json={"robot": "robot-r9", "raison": "x"}, headers=CODE).status_code == 400
    r1 = client.post("/api/clinique/flotte/panne", json={"robot": "robot-r1", "raison": "x"}, headers=CODE)
    assert r1.status_code == 400 and "robot branché" in r1.json()["detail"]
    assert client.post("/api/clinique/flotte/reprendre", json={"tache": ident}, headers=CODE).status_code == 400  # pas en reprise


def test_aucun_nom_de_patient_sur_le_tableau_de_flotte(banc):
    client, _ = banc
    ident = _demander(client)
    client.post("/api/clinique/flotte/attribuer", json={"tache": ident}, headers=CODE)
    page = _texte(client) + html.unescape(client.get(f"/clinique/flotte/pourquoi?tache={ident}").text)
    for nom in ("Giulia", "Madame", "Monsieur", "Hans", "Claire"):
        assert nom not in page, nom


def test_la_page_simple_de_la_flotte_n_est_pas_changee(banc):
    client, _ = banc
    assert "Pas de plan, pas de batterie." in html.unescape(client.get("/clinique/flotte").text)


# --- Dans un vrai navigateur (Chrome sans fenêtre) : les boutons marchent avec de vrais gestes de souris --------------------------
from briques.clinique.tests.test_clic_dans_le_navigateur import CHROME, Pilote, chrome, serveur  # noqa: E402,F401


@pytest.mark.skipif(not CHROME.exists(), reason="Chrome n'est pas sur cet ordinateur : les boutons ne sont pas essayés dans un navigateur")
def test_dans_chrome_les_boutons_du_tableau_marchent_avec_un_vrai_clic(serveur, chrome):  # noqa: F811
    import asyncio

    import httpx
    import websockets

    async def bouton(pilote, texte):
        point = None
        for _ in range(50):
            point = await pilote.lire(
                "(() => { const b = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === " + repr(texte) + ");"
                " if (!b) return null; b.scrollIntoView({block: 'center'}); const r = b.getBoundingClientRect();"
                " return {x: r.left + r.width / 2, y: r.top + r.height / 2}; })()")
            if point:
                break
            await asyncio.sleep(0.1)
        assert point, f"le bouton « {texte} » n'est pas sur la page"
        await pilote.cliquer(point, 0.08)

    async def attendre(pilote, mot):
        for _ in range(60):
            texte = await pilote.lire("document.getElementById('contenu').innerText")
            if mot in texte:
                return texte
            await asyncio.sleep(0.1)
        raise AssertionError(f"« {mot} » n'apparaît pas : {texte[-600:]}")

    async def jouer():
        r = httpx.post(f"{serveur}/api/clinique/demande", headers={"origin": serveur},
                       json={"badge": "soignant-etage-2", "patient": "p01", "texte": "la couverture"})
        assert r.status_code == 200, r.text
        async with websockets.connect(chrome, max_size=None) as ws:
            pilote = Pilote(ws)
            await pilote.ouvrir(f"{serveur}/clinique/tableau-de-flotte")
            await bouton(pilote, "Attribuer (le plus proche)")
            await attendre(pilote, "J'envoie R2")
            await bouton(pilote, "Avancer d'un pas")
            await attendre(pilote, "pas n° 1")
            await bouton(pilote, "Panne : batterie basse")  # le premier bouton de panne : celui de R2
            await attendre(pilote, "en panne")
            await bouton(pilote, "Reprendre (le plus proche)")
            return await attendre(pilote, "J'envoie R4")

    fin = asyncio.run(jouer())
    assert "reprise de R2" in fin and "FAUX ROBOT — SIMULÉ" in fin
