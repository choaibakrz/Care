"""La clinique en boîte — T26, la relecture de la tranche 3 (T22 à T25, K04) par un relecteur neuf.

Un essai par défaut de justesse trouvé et corrigé au tour 81. Robots SIMULÉS et faux robot : aucun vrai robot.
Les points du relecteur qui ne sont PAS corrigés ici sont écrits dans NON_TESTE.md et dans la tâche H11.
"""
from __future__ import annotations

import html

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique.carnet import Carnet
from briques.clinique.cartes import CartesDeLaFlotte
from briques.clinique.ecrans import brancher_ecrans
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.monde_robots import MondeDesRobots
from briques.clinique.porte import JournalDesAcces, PorteDeLecture
from briques.clinique.repartiteur import Repartiteur

CODE = {"X-Code-Equipe": "code-d-essai"}
PAGE = "/clinique/tableau-de-flotte"
COURSE = {"de": "Réserve", "ou": "Chambre 12"}


@pytest.fixture
def banc():
    horloge, app = HorlogeDeDemonstration(), FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge), code_equipe="code-d-essai")
    return TestClient(app), clinique


@pytest.fixture
def banc_branche(tmp_path):
    """Avec le faux robot branché (un système de l'ossature, pas démarré : aucun geste ne part dans ces essais)."""
    from commun.systeme import REGLAGES_EXEMPLE, Systeme, charger_reglages

    from briques.clinique.coursier import monde_de_la_clinique

    reglages = charger_reglages(REGLAGES_EXEMPLE)
    reglages["cerveau"] = {**reglages["cerveau"], "choix": "regles"}
    systeme = Systeme(reglages, dossier_journal=str(tmp_path), acceleration=20.0, monde=monde_de_la_clinique())
    horloge, app = HorlogeDeDemonstration(bus=systeme.bus), FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge), systeme=systeme, code_equipe="code-d-essai")
    return app, clinique, systeme


def _demander(client, texte="la couverture"):
    r = client.post("/api/clinique/demande", json={"badge": "soignant-etage-2", "patient": "p01", "texte": texte})
    assert r.status_code == 200, r.text
    return r.json()["tache"]["id"]


def _repartiteur():
    cartes = CartesDeLaFlotte()
    return Repartiteur(MondeDesRobots(cartes=cartes), cartes)


# ------------------------------------------------------------------------------------------------ le répartiteur
def test_point_11_un_robot_qui_a_juste_la_batterie_qu_il_faut_n_est_pas_choisi():
    """Avant : choisi avec « < », puis en panne de batterie à l'arrivée (le monde dit « <= »)."""
    rep = _repartiteur()
    vu = next(r for r in rep.choisir(COURSE)["regardes"] if r["id"] == "robot-r2")
    trajet = rep.monde.chemin("Réserve", "Chambre 12")[1]
    rep.monde._robots["robot-r2"]["batterie"] = (vu["metres"] + trajet) * rep.monde.conso + rep.monde.seuil
    vu = next(r for r in rep.choisir(COURSE)["regardes"] if r["id"] == "robot-r2")
    assert not vu["convient"] and "pas assez de batterie" in vu["raison"]


def test_point_5_un_robot_dont_la_carte_interdit_un_lieu_du_trajet_n_est_pas_choisi():
    """Avant : R3 (carte Thérapie) était choisi pour aller à la Réserve, puis bloqué devant le Poste de soins."""
    rep = _repartiteur()
    for robot in ("robot-r2", "robot-r4"):
        rep.monde.panne(robot, "panne d'essai", provoquee=True)
    choix = rep.choisir(COURSE)
    r3 = next(r for r in choix["regardes"] if r["id"] == "robot-r3")
    assert choix["robot"] != "robot-r3" and not r3["convient"] and not r3["carte_permet"]
    assert "Poste de soins" in r3["raison"] and "trajet" in r3["raison"]


def test_point_5_le_choix_habituel_ne_change_pas():
    choix = _repartiteur().choisir(COURSE)
    assert choix["robot"] == "robot-r2" and "J'envoie R2" in choix["pourquoi"]


# ------------------------------------------------------------------------------------------------ le tableau de flotte
def test_point_3_sans_robot_branche_le_tableau_dit_que_r1_n_est_pas_branche_et_n_invente_ni_place_ni_batterie(banc):
    client, _ = banc
    brut = client.get(PAGE).text
    ligne = brut.split("<td><b>R1</b></td>")[1].split("</tr>")[0]
    assert "pas branché" in ligne and "100 %" not in ligne and "Hall" not in ligne and "libre" not in ligne
    assert "pas lue" in ligne and "pas suivie" in ligne
    plan = html.unescape(brut.split("<h2>Le plan</h2>")[1].split("</article>")[0])
    assert "R1" not in plan.split("Plan inventé")[0]  # R1 n'est pas posé sur le plan : sa place n'est pas lue sur le robot


def test_point_3_avec_le_faux_robot_branche_la_place_et_la_batterie_de_r1_ne_sont_pas_inventees(banc_branche):
    app, _, _ = banc_branche
    ligne = TestClient(app).get(PAGE).text.split("<td><b>R1</b></td>")[1].split("</tr>")[0]
    assert "FAUX ROBOT" in ligne and "100 %" not in ligne and "lue sur le robot" in ligne and "lu sur le robot" in ligne  # H18, Q28 : A
    assert "pas branché" not in ligne


def test_point_9_la_page_pourquoi_donne_a_r1_la_meme_etiquette_que_le_tableau(banc, monkeypatch):
    client, clinique = banc
    ident = _demander(client)
    client.post("/api/clinique/flotte/attribuer", json={"tache": ident}, headers=CODE)
    tf = clinique.tableau_de_flotte
    monkeypatch.setattr(tf, "etiquette", lambda robot: "FAUX ROBOT — SIMULÉ" if robot["simule"] else "ÉTIQUETTE D'ESSAI")
    assert "<td>ÉTIQUETTE D'ESSAI</td>" in html.unescape(client.get(PAGE).text)
    assert "<td>ÉTIQUETTE D'ESSAI</td>" in html.unescape(client.get(f"/clinique/flotte/pourquoi?tache={ident}").text)


def test_point_12_une_tache_passee_a_un_humain_ne_montre_plus_l_ancien_robot_ni_son_ancienne_phrase(banc):
    client, clinique = banc
    ident = _demander(client)
    client.post("/api/clinique/flotte/attribuer", json={"tache": ident}, headers=CODE)
    for robot in ("robot-r2", "robot-r3", "robot-r4"):
        client.post("/api/clinique/flotte/panne", json={"robot": robot, "raison": "batterie basse"}, headers=CODE)
    rendu = client.post("/api/clinique/flotte/reprendre", json={"tache": ident}, headers=CODE).json()
    assert rendu["sorte"] == "humain"
    assert "le robot va d'abord" not in rendu["pourquoi_un_humain"]  # point 4 : plus de phrase qui se contredit
    ligne = html.unescape(client.get(PAGE).text).split("<h2>Courses</h2>")[1]
    assert "pour un humain" in ligne and "J'envoie" not in ligne and "robot : R" not in ligne
    assert "avant : R2" in ligne  # l'histoire reste dite, sans faire croire qu'un robot a la course


def test_point_8_avec_un_robot_branche_le_tableau_n_attribue_rien_a_un_robot_simule(banc_branche):
    """Avec un robot branché, une demande part tout de suite par le coursier. Le tableau ne doit pas pouvoir la donner
    à un robot simulé : pas de bouton « Attribuer », et le chemin répond non avant de regarder la tâche."""
    app, _, _ = banc_branche
    client = TestClient(app)
    assert 'data-attribuer="' not in client.get(PAGE).text
    r = client.post("/api/clinique/flotte/attribuer", json={"tache": "t1"}, headers=CODE)
    assert r.status_code == 400 and "robot branché" in r.json()["detail"]


# ------------------------------------------------------------------------------------------------ la page simple
def test_point_10_la_page_simple_ne_dit_pas_provoquee_pour_une_panne_qui_ne_l_est_pas(banc):
    client, clinique = banc
    clinique.tableau_de_flotte.reprise._traiter({"robot": "robot-r3", "nom": "R3", "quoi": "panne", "raison": "batterie basse",
                                                 "provoquee": False, "tache": None})
    page = html.unescape(client.get("/clinique/flotte").text)
    assert "batterie basse" in page and "panne provoquée" not in page.split("batterie basse")[1][:40]
    clinique.tableau_de_flotte.reprise._traiter({"robot": "robot-r4", "nom": "R4", "quoi": "panne", "raison": "robot bloqué",
                                                 "provoquee": True, "tache": None})
    page = html.unescape(client.get("/clinique/flotte").text)
    assert "robot bloqué (panne provoquée)" in page


# ------------------------------------------------------------------------------------------------ la carte et le gardien
def test_point_1_la_page_ne_dit_appliquee_par_le_gardien_que_quand_le_gardien_a_la_carte(banc_branche):
    import asyncio

    app, clinique, _ = banc_branche
    carte = clinique.flotte.carte_r1
    assert not carte.appliquee()
    avant = clinique.flotte.ou_en_est_la_carte()
    assert "est appliquée par le gardien" not in avant and "pas encore" in avant and "premier geste" in avant
    asyncio.run(carte.appliquer())
    assert carte.appliquee() and "est appliquée par le gardien" in clinique.flotte.ou_en_est_la_carte()


def test_point_1_au_demarrage_du_serveur_de_pages_la_carte_va_tout_de_suite_chez_le_gardien(banc_branche):
    app, clinique, systeme = banc_branche
    with TestClient(app):  # le démarrage de l'application, comme avec le vrai serveur
        assert clinique.flotte.carte_r1.appliquee()
        assert "regles_avec_la_carte_de_r1" in str(systeme.gardien.chemin_regles)
