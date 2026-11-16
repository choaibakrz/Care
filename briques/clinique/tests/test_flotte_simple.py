"""La clinique en boîte — T11c, la flotte, version simple (cahier 4.2 scène 6, 5.10, 6.6). Testé sur faux robot.

« Fini » veut dire :
- quatre robots sont décrits, dont trois simulés ; chacun porte son étiquette ;
- R3 (simulé) part faire une course, tombe en panne en route : la tâche passe « reprise », et c'est écrit ;
- un autre robot la finit : R1, le faux robot, par le coursier, donc sous le gardien (quatre gestes, quatre « oui ») ;
- si aucun robot ne peut la reprendre, un humain reprend la main, et c'est écrit ;
- un robot simulé ne fait jamais semblant de livrer : le programme n'écrit « livrée » que par le coursier.
Version simple : pas de cartes de rôle appliquées, pas de choix du plus proche, pas de batterie (T22 à T25, R5).
Internet coupé, aucun modèle.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique import repetition
from briques.clinique.carnet import Carnet
from briques.clinique.coursier import Coursier, monde_de_la_clinique
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.listes import ListesDeSoin
from briques.clinique.porte import JournalDesAcces, PorteDeLecture, charger_badges
from briques.clinique.taches import TableauDesTaches
from conftest import lancer

BADGES = charger_badges()
SOIGNANT = BADGES["soignant-etage-2"]
SIMULE = "FAUX ROBOT — SIMULÉ"


@pytest.fixture
def pieces(tmp_path, reglages):
    from briques.clinique.flotte import Flotte
    from commun.systeme import Systeme

    r = {**reglages, "ecran": dict(reglages["ecran"]), "cerveau": {**reglages["cerveau"], "choix": "regles"}}
    systeme = Systeme(r, dossier_journal=tmp_path / "journal", acceleration=20.0, monde=monde_de_la_clinique())
    horloge = HorlogeDeDemonstration(bus=systeme.bus)
    porte = PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour)
    carnet = Carnet(horloge=horloge)
    listes = ListesDeSoin(porte, carnet)
    tableau = TableauDesTaches(porte, carnet, listes)
    coursier = Coursier(systeme, tableau, listes, BADGES["robot-r1"])
    return systeme, tableau, carnet, coursier, Flotte(tableau, carnet, coursier)


def _jouer(systeme, fabrique):
    async def tout():
        await systeme.demarrer()
        try:
            return await fabrique()
        finally:
            await systeme.arreter()

    return lancer(tout())


def _etats(carnet, ident):
    return [l["donnees"]["etat"] for l in carnet.lignes("tâche") if l["donnees"]["id"] == ident]


def _tache(tableau):
    return tableau.demander(SOIGNANT, "p01", "la feuille d'exercices")["tache"]


# ---------------------------------------------------------------------------------------------- les quatre robots
def test_quatre_robots_dont_trois_simules_chacun_avec_son_etiquette(pieces):
    *_, flotte = pieces
    robots = {r["id"]: r for r in flotte.robots()}
    assert list(robots) == ["robot-r1", "robot-r2", "robot-r3", "robot-r4"]
    assert robots["robot-r1"]["etiquette"] == "FAUX ROBOT" and not robots["robot-r1"]["simule"]
    assert all(robots[i]["etiquette"] == SIMULE and robots[i]["simule"] for i in ("robot-r2", "robot-r3", "robot-r4"))
    assert [robots[i]["carte"] for i in robots] == ["Étage", "Étage", "Thérapie", "Nuit"]
    assert flotte.compte() == {"robots": 4, "simules": 3, "texte": "3 robots simulés sur 4"}
    assert all(r["etat"] == "libre" for r in robots.values())


def test_sans_robot_branche_r1_le_dit(pieces):
    from briques.clinique.flotte import Flotte

    _, tableau, carnet, _, _ = pieces
    r1 = Flotte(tableau, carnet, None).robots()[0]
    assert r1["etiquette"] == "FAUX ROBOT" and r1["etat"] == "pas branché"


# ---------------------------------------------------------------------------------------------- la panne
def test_r3_part_puis_tombe_en_panne_la_tache_passe_reprise_et_c_est_ecrit(pieces):
    systeme, tableau, carnet, _, flotte = pieces
    tache = _tache(tableau)
    partie = flotte.partir("robot-r3", tache["id"])
    assert partie["etat"] == "en route" and partie["robot"] == "robot-r3" and partie["etiquette"] == SIMULE
    assert {r["id"]: r for r in flotte.robots()}["robot-r3"]["etat"] == "en course"
    apres = flotte.panne("robot-r3", "batterie basse")
    assert apres["etat"] == "reprise" and apres["repris_de"] == "robot-r3"
    assert "R3" in apres["pourquoi"] and "batterie basse" in apres["pourquoi"] and "provoquée" in apres["pourquoi"]
    assert _etats(carnet, tache["id"]) == ["demandée", "attribuée", "en route", "reprise"]
    pannes = carnet.lignes("panne de robot")
    assert len(pannes) == 1 and pannes[0]["donnees"] == {**pannes[0]["donnees"], "robot": "robot-r3",
                                                         "raison": "batterie basse", "provoquee": True,
                                                         "etiquette": SIMULE, "tache": tache["id"]}
    assert {r["id"]: r for r in flotte.robots()}["robot-r3"]["etat"] == "en panne"
    # un robot simulé n'a rien demandé au gardien et n'a fait bouger aucun robot
    assert not [e for e in systeme.bus.historique if e.type in ("gardien_decision", "action_demarree")]


def test_un_robot_simule_ne_livre_jamais(pieces):
    _, tableau, carnet, _, flotte = pieces
    tache = _tache(tableau)
    flotte.partir("robot-r2", tache["id"])
    assert "livrée" not in _etats(carnet, tache["id"])
    assert not hasattr(flotte, "livrer")


def test_r1_ne_part_pas_par_la_flotte_simulee_et_un_robot_inconnu_est_refuse(pieces):
    _, tableau, carnet, _, flotte = pieces
    tache = _tache(tableau)
    with pytest.raises(ValueError, match="coursier"):
        flotte.partir("robot-r1", tache["id"])
    with pytest.raises(ValueError, match="inconnu"):
        flotte.partir("robot-r9", tache["id"])
    with pytest.raises(ValueError, match="inconnu"):
        flotte.panne("robot-r9", "x")
    assert _etats(carnet, tache["id"]) == ["demandée"]


def test_un_robot_en_panne_ne_repart_pas(pieces):
    _, tableau, _, _, flotte = pieces
    flotte.panne("robot-r3", "bloqué")
    with pytest.raises(ValueError, match="en panne"):
        flotte.partir("robot-r3", _tache(tableau)["id"])


# ---------------------------------------------------------------------------------------------- la reprise
def test_r1_le_faux_robot_finit_la_course_sous_le_gardien(pieces):
    systeme, tableau, carnet, _, flotte = pieces
    tache = _tache(tableau)
    flotte.partir("robot-r3", tache["id"])
    flotte.panne("robot-r3", "batterie basse")

    fin = _jouer(systeme, lambda: flotte.reprendre(tache["id"]))

    assert fin["etat"] == "livrée" and fin["robot"] == "robot-r1" and fin["etiquette"] == "FAUX ROBOT"
    assert fin["repris_de"] == "robot-r3"
    assert _etats(carnet, tache["id"]) == ["demandée", "attribuée", "en route", "reprise", "attribuée", "en route", "livrée"]
    gestes = ["se_deplacer", "saisir", "se_deplacer", "poser"]
    oui = [e.donnees["action"]["nom"] for e in systeme.bus.historique
           if e.type == "gardien_decision" and e.donnees["verdict"] == "oui"]
    faits = [e.donnees["action"]["nom"] for e in systeme.bus.historique if e.type == "action_demarree" and e.donnees.get("action")]
    assert oui == gestes and faits == gestes


def test_a_l_arret_d_urgence_aucun_robot_ne_reprend_un_humain_reprend_la_main_et_c_est_ecrit(pieces):
    systeme, tableau, carnet, _, flotte = pieces
    tache = _tache(tableau)
    flotte.partir("robot-r3", tache["id"])
    flotte.panne("robot-r3", "batterie basse")

    async def reprise_a_l_arret():
        await systeme.prise.arret_urgence(raison="essai")
        return await flotte.reprendre(tache["id"])

    fin = _jouer(systeme, reprise_a_l_arret)
    assert fin["etat"] == "reprise" and fin["sorte"] == "humain"
    assert "aucun robot" in fin["pourquoi_un_humain"] and "arret_urgence" in fin["pourquoi_un_humain"]
    assert not [e for e in systeme.bus.historique if e.type == "action_demarree"]
    derniere = carnet.lignes("tâche")[-1]
    assert derniere["donnees"]["sorte"] == "humain" and derniere["donnees"]["etat"] == "reprise"


def test_sans_robot_branche_un_humain_reprend_la_main(pieces):
    from briques.clinique.flotte import Flotte

    _, tableau, carnet, _, _ = pieces
    flotte = Flotte(tableau, carnet, None)
    tache = _tache(tableau)
    flotte.partir("robot-r3", tache["id"])
    flotte.panne("robot-r3", "bloqué")
    fin = lancer(flotte.reprendre(tache["id"]))
    assert fin["sorte"] == "humain" and fin["etat"] == "reprise" and "aucun robot" in fin["pourquoi_un_humain"]


def test_on_ne_reprend_que_une_tache_en_reprise(pieces):
    _, tableau, _, _, flotte = pieces
    with pytest.raises(ValueError, match="reprise"):
        lancer(flotte.reprendre(_tache(tableau)["id"]))


def test_le_coursier_refuse_toujours_une_tache_deja_livree(pieces):
    systeme, tableau, _, coursier, _ = pieces
    tache = _tache(tableau)
    _jouer(systeme, lambda: coursier.faire(tache["id"]))
    with pytest.raises(ValueError, match="déjà"):
        lancer(coursier.faire(tache["id"]))


# ---------------------------------------------------------------------------------------------- l'écran
def test_la_page_de_la_flotte_montre_les_quatre_robots_et_leur_etiquette():
    from briques.clinique.ecrans import brancher_ecrans

    horloge = HorlogeDeDemonstration()
    app = FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge))
    client = TestClient(app)
    page = client.get("/clinique/flotte")
    assert page.status_code == 200 and "DONNÉES INVENTÉES" in page.text
    for mot in ("R1", "R2", "R3", "R4", "3 robots simulés sur 4", SIMULE, "Thérapie", "Nuit", "pas branché"):
        assert mot in page.text, mot
    assert "Madame" not in page.text and "Giulia" not in page.text  # aucun nom de patient sur cette page
    tache = clinique.taches.demander(SOIGNANT, "p01", "la feuille d'exercices")["tache"]
    clinique.flotte.partir("robot-r3", tache["id"])
    clinique.flotte.panne("robot-r3", "batterie basse")
    page = client.get("/clinique/flotte/contenu").text
    assert "en panne" in page and "batterie basse" in page and "reprise" in page
    assert "/clinique/flotte" in client.get("/clinique").text


# ---------------------------------------------------------------------------------------------- la grande répétition
def test_l_etape_12_reussit_et_dit_ce_qui_est_simule():
    resultat = repetition.CONTROLES[12]()
    assert resultat.reussie is True, resultat.detail
    assert resultat.etiquette == "SIMULÉ"
    for mot in ("R3", "simulé", "faux robot", "gardien", "panne provoquée"):
        assert mot in resultat.detail, mot


def test_l_etape_12_rate_si_aucun_robot_ne_reprend(monkeypatch):
    from briques.clinique import coursier

    async def rate(self, ident):
        return self.tableau.changer_etat(self.badge, ident, "échouée", pourquoi="raté exprès")

    monkeypatch.setattr(coursier.Coursier, "faire", rate)
    resultat = repetition.CONTROLES[12]()
    assert resultat.reussie is False and "humain" in resultat.detail
