"""La clinique en boîte — T07b, la course du faux robot (cahier 5.6, 6.5, 6.7). Testé sur faux robot.

« Fini » veut dire :
- pour une tâche « pour un robot », le faux robot va à la réserve, prend l'objet, va à la chambre, le pose ;
- la tâche passe par ses états : demandée, attribuée, en route, livrée ;
- la livraison coche le point de liste en attente, et le carnet note que c'est la livraison qui l'a coché ;
- rien ne contourne le gardien : chaque geste du robot a d'abord reçu un « oui » du gardien ; si le robot est à
  l'arrêt d'urgence, rien ne part, la tâche est « échouée » et le point reste en attente.
Avec T07a, cela finit T07. Internet coupé, aucun modèle.
"""
from __future__ import annotations

import pytest

from briques.clinique.carnet import Carnet
from briques.clinique.coursier import Coursier, monde_de_la_clinique
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.listes import ListesDeSoin
from briques.clinique.porte import JournalDesAcces, PorteDeLecture, charger_badges
from briques.clinique.taches import TableauDesTaches
from commun.monde import Monde
from conftest import lancer, robot

BADGES = charger_badges()
SOIGNANT, ROBOT = BADGES["soignant-etage-2"], BADGES["robot-r1"]
ETAGE_2 = ("Poste de soins", "Réserve", "Chambre 11", "Chambre 12", "Chambre 13", "Chambre 14", "Salon")


@pytest.fixture
def clinique(tmp_path, reglages):
    from commun.systeme import Systeme

    r = {**reglages, "ecran": dict(reglages["ecran"]), "cerveau": {**reglages["cerveau"], "choix": "regles"}}
    systeme = Systeme(r, dossier_journal=tmp_path / "journal", acceleration=20.0, monde=monde_de_la_clinique())
    horloge = HorlogeDeDemonstration(bus=systeme.bus)
    porte = PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour)
    carnet = Carnet(horloge=horloge)
    listes = ListesDeSoin(porte, carnet)
    tableau = TableauDesTaches(porte, carnet, listes)
    return systeme, tableau, listes, carnet, Coursier(systeme, tableau, listes, ROBOT)


def _jouer(systeme, coroutine_factory):
    async def tout():
        await systeme.demarrer()
        try:
            return await coroutine_factory()
        finally:
            await systeme.arreter()

    return lancer(tout())


def _actions(systeme, genre):
    return [e.donnees["action"]["nom"] for e in systeme.bus.historique if e.type == genre and e.donnees.get("action")]


# ---------------------------------------------------------------- le plan
def test_le_plan_de_la_clinique_s_ajoute_au_monde_du_faux_robot():
    monde, porte = monde_de_la_clinique(), PorteDeLecture(journal=JournalDesAcces())
    lieux = {l["nom"]: l for l in porte.lieux(ROBOT)["lieux"]}
    for nom in ETAGE_2:
        assert lieux[nom]["etage"] == 2 and monde.lieu(nom) is not None, nom
    assert monde.lieu("Hall") is None  # le robot de l'étage ne prend pas l'ascenseur : pas de rez-de-chaussée sur son plan
    for objet in porte.reserve(ROBOT):
        chose = monde.objet(objet["nom"])
        assert chose is not None and 0 < chose.poids_kg <= 2.0, objet["nom"]
        assert chose.noms == {}  # sans nom dans les langues : le cerveau de l'ossature ne les confond avec rien
    assert monde.lieu("cuisine") is not None and monde.objet("bouteille") is not None  # le monde de l'ossature est toujours là
    assert Monde.charger().lieu("Réserve") is None  # et il n'est pas modifié quand la clinique ne tourne pas


# ---------------------------------------------------------------- la course
def test_le_faux_robot_va_de_la_reserve_a_la_chambre_et_la_livraison_coche_le_point(clinique):
    systeme, tableau, listes, carnet, coursier = clinique
    tache = tableau.demander(SOIGNANT, "p01", "la feuille d'exercices", liste="avant_physio", numero=3)["tache"]

    fin = _jouer(systeme, lambda: coursier.faire(tache["id"]))

    assert fin["etat"] == "livrée" and fin["robot"] == "robot-r1" and fin["etiquette"] == "FAUX ROBOT"
    etats = [l["donnees"]["etat"] for l in carnet.lignes("tâche") if l["donnees"]["id"] == tache["id"]]
    assert etats == ["demandée", "attribuée", "en route", "livrée"]
    # le faux robot est vraiment allé là-bas, et l'objet y est
    faux_robot, chambre = robot(systeme), systeme.monde.lieu("Chambre 12").position
    assert abs(faux_robot.x - chambre.x) < 0.3 and abs(faux_robot.y - chambre.y) < 0.3
    ox, oy = faux_robot.objets["feuille d'exercices"]
    assert abs(ox - chambre.x) < 0.3 and abs(oy - chambre.y) < 0.3 and faux_robot.objet_tenu is None
    # la livraison a coché le point, et le carnet le dit
    point = {p["numero"]: p for p in listes.liste(SOIGNANT, "p01", "avant_physio")["points"]}[3]
    assert point["etat"] == "fait" and point["comment"] == "livraison du robot" and point["par"] == "robot-r1"
    ligne = [l for l in carnet.lignes("point de liste")][-1]
    assert ligne["valide_par_un_humain"] is False and ligne["donnees"]["tache"] == tache["id"]
    assert [l["qui"] for l in carnet.lignes("tâche")] == ["soignant-etage-2", "robot-r1", "robot-r1", "robot-r1"]


def test_rien_ne_contourne_le_gardien(clinique):
    systeme, tableau, _, _, coursier = clinique
    tache = tableau.demander(SOIGNANT, "p01", "une couverture")["tache"]
    _jouer(systeme, lambda: coursier.faire(tache["id"]))
    gestes = ["se_deplacer", "saisir", "se_deplacer", "poser"]
    oui = [e.donnees["action"]["nom"] for e in systeme.bus.historique
           if e.type == "gardien_decision" and e.donnees["verdict"] == "oui"]
    assert oui == gestes  # quatre demandes au gardien, quatre « oui »
    assert _actions(systeme, "action_demarree") == gestes  # et pas un geste de plus que les « oui »
    assert not [e for e in systeme.bus.historique if e.type == "action_refusee"]
    # chaque geste part APRÈS son « oui »
    ordre = [e.type for e in systeme.bus.historique if e.type in ("gardien_decision", "action_demarree")]
    assert ordre == ["gardien_decision", "action_demarree"] * 4


def test_a_l_arret_d_urgence_rien_ne_part_la_tache_echoue_et_le_point_reste_en_attente(clinique):
    systeme, tableau, listes, _, coursier = clinique
    tache = tableau.demander(SOIGNANT, "p01", "la feuille d'exercices", liste="avant_physio", numero=3)["tache"]

    async def course_a_l_arret():
        await systeme.prise.arret_urgence(raison="essai")
        return await coursier.faire(tache["id"])

    fin = _jouer(systeme, course_a_l_arret)
    assert fin["etat"] == "échouée" and "arret_urgence" in fin["pourquoi"]
    assert _actions(systeme, "action_demarree") == []  # le robot n'a rien fait
    depart = systeme.monde.depart
    assert (robot(systeme).x, robot(systeme).y) == (depart.x, depart.y)
    point = {p["numero"]: p for p in listes.liste(SOIGNANT, "p01", "avant_physio")["points"]}[3]
    assert point["etat"] == "en attente d'un objet"


def test_le_gardien_dit_non_la_tache_echoue_sans_geste(clinique):
    """Une tâche écrite à la main, qui part d'un lieu interdit par le gardien (l'escalier) : rien ne part."""
    systeme, tableau, _, carnet, coursier = clinique
    carnet.ecrire(SOIGNANT, "tâche", {"id": "t1", "etat": "demandée", "sorte": "robot", "qui_demande": SOIGNANT.id,
                                      "pour_qui": "p01", "quoi": "couverture", "de": "escalier", "ou": "Chambre 12",
                                      "pour_quand": "dès que possible"}, valide_par_un_humain=True)
    fin = _jouer(systeme, lambda: coursier.faire("t1"))
    assert fin["etat"] == "échouée" and "le gardien a dit non" in fin["pourquoi"]
    assert _actions(systeme, "action_demarree") == []
    non = [e for e in systeme.bus.historique if e.type == "gardien_decision" and e.donnees["verdict"] == "non"]
    assert len(non) == 1  # le refus est dans la boîte noire ; le coursier n'a pas réessayé autrement


def test_le_coursier_ne_prend_que_les_taches_pour_un_robot(clinique):
    systeme, tableau, _, carnet, coursier = clinique
    humaine = tableau.demander(SOIGNANT, "p01", "un fauteuil roulant")["tache"]
    avant = len(carnet.lignes())
    with pytest.raises(ValueError):
        _jouer(systeme, lambda: coursier.faire(humaine["id"]))
    with pytest.raises(ValueError):
        lancer(coursier.faire("t99"))
    assert len(carnet.lignes()) == avant and _actions(systeme, "action_demarree") == []


def test_une_tache_deja_livree_ne_repart_pas(clinique):
    systeme, tableau, _, _, coursier = clinique
    tache = tableau.demander(SOIGNANT, "p01", "une couverture")["tache"]

    async def deux_fois():
        await coursier.faire(tache["id"])
        with pytest.raises(ValueError):
            await coursier.faire(tache["id"])

    _jouer(systeme, deux_fois)
    assert len(_actions(systeme, "action_demarree")) == 4


# ---------------------------------------------------------------- à l'écran : la demande fait partir le robot
def test_avec_le_serveur_la_demande_fait_partir_le_faux_robot_et_l_ecran_suit(tmp_path, reglages):
    import time

    from fastapi.testclient import TestClient

    from briques.b13_ecran.serveur import creer_app
    from briques.clinique.ecrans import brancher_ecrans
    from commun.systeme import Systeme

    r = {**reglages, "ecran": dict(reglages["ecran"]), "cerveau": {**reglages["cerveau"], "choix": "regles"}}
    systeme = Systeme(r, dossier_journal=tmp_path / "journal", acceleration=20.0, monde=monde_de_la_clinique())
    app = creer_app(systeme)
    horloge = HorlogeDeDemonstration(bus=systeme.bus)
    brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                    carnet=Carnet(horloge=horloge), systeme=systeme)
    with TestClient(app) as client:
        reponse = client.post("/api/clinique/demande", json={"badge": "soignant-etage-2", "patient": "p01",
                                                             "texte": "une couverture"}).json()
        assert reponse["tache"]["sorte"] == "robot"
        fin = time.monotonic() + 20
        while time.monotonic() < fin:
            tache = client.get("/api/clinique/taches", params={"badge": "soignant-etage-2"}).json()["taches"][0]
            if tache["etat"] in ("livrée", "échouée"):
                break
            time.sleep(0.05)
        assert tache["etat"] == "livrée" and tache["etiquette"] == "FAUX ROBOT"
        texte = client.get("/clinique/soignant/contenu").text
        assert "livrée" in texte and "[FAUX ROBOT]" in texte and "Aucun robot n'est branché" not in texte
        assert client.get("/jury").status_code == 200  # l'écran du jury marche toujours, avec le plan de la clinique en plus
    assert [e.donnees["action"]["nom"] for e in systeme.bus.historique if e.type == "action_demarree"] == \
        ["se_deplacer", "saisir", "se_deplacer", "poser"]


# ---------------------------------------------------------------- la grande répétition, étape 8
def test_l_etape_8_de_la_grande_repetition_question_livraison_point_coche():
    from briques.clinique import repetition

    resultat = repetition.CONTROLES[8]()
    assert resultat.reussie is True and resultat.etiquette == "FAUX ROBOT"
    assert "Lequel" in resultat.detail and "livrée" in resultat.detail
