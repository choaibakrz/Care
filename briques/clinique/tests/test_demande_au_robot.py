"""La clinique en boîte — T07a, la demande au robot : le tableau des tâches et la demande (cahier 5.6, 6.5, 6.7).

« Fini » veut dire :
- « il manque un coussin en chambre 12 » : la demande est floue, le prototype pose une question courte ; une fois
  le coussin choisi, une tâche pour un robot est créée (qui demande, pour qui, quoi, d'où, où, pour quand, état) ;
- un objet absent de la réserve : le prototype le dit et la tâche passe à un humain ;
- un point de liste peut passer « en attente d'un objet », et la tâche le sait ;
- tout est dans le carnet ; la réserve et le plan sont lus par la porte.
Le faux robot ne bouge pas encore : la course, sous le gardien, vient avec T07b. Internet coupé, aucun modèle.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique import dossier as faux_dossier
from briques.clinique.carnet import Carnet
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.listes import ListesDeSoin
from briques.clinique.porte import AccesRefuse, JournalDesAcces, PorteDeLecture, charger_badges
from briques.clinique.taches import ETATS, TableauDesTaches

BADGES = charger_badges()
SOIGNANT, MEDECIN, DIRECTION, ROBOT = (BADGES[b] for b in ("soignant-etage-2", "medecin-exemple", "direction", "robot-r1"))


def _tableau():
    horloge = HorlogeDeDemonstration()
    porte = PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour)
    carnet = Carnet(horloge=horloge)
    listes = ListesDeSoin(porte, carnet)
    return TableauDesTaches(porte, carnet, listes), carnet, listes, porte


# ---------------------------------------------------------------- la demande
def test_il_manque_un_coussin_la_demande_est_floue_le_prototype_pose_une_question():
    tableau, carnet, _, _ = _tableau()
    reponse = tableau.demander(SOIGNANT, "p01", "il manque un coussin en chambre 12")
    assert reponse["genre"] == "question"
    assert reponse["choix"] == ["grand coussin", "coussin de nuque"]
    assert reponse["phrase"] == "Lequel : le grand coussin, ou le coussin de nuque ?"
    assert carnet.lignes("tâche") == []  # tant qu'on ne sait pas lequel, aucune tâche : le prototype ne devine pas


def test_une_fois_le_coussin_choisi_une_tache_pour_un_robot_est_creee():
    tableau, carnet, _, _ = _tableau()
    reponse = tableau.demander(SOIGNANT, "p01", "il manque un coussin en chambre 12", choix="grand coussin")
    assert reponse["genre"] == "tâche"
    tache = reponse["tache"]
    assert tache["sorte"] == "robot" and tache["etat"] == "demandée"
    assert (tache["quoi"], tache["de"], tache["ou"]) == ("grand coussin", "Réserve", "Chambre 12")
    assert tache["qui_demande"] == "soignant-etage-2" and tache["pour_qui"] == "p01" and tache["pour_quand"] == "dès que possible"
    assert reponse["phrase"] == "Demande notée : le grand coussin, pour la chambre 12."
    ligne = carnet.lignes("tâche")[-1]
    assert ligne["qui"] == "soignant-etage-2" and ligne["valide_par_un_humain"] is True
    assert ligne["donnees"]["id"] == tache["id"] and ligne["quand"]["jour"] == 1


@pytest.mark.parametrize("phrase,objet", [("il manque le coussin de nuque", "coussin de nuque"),
                                          ("une couverture, s'il vous plaît", "couverture"),
                                          ("Il manque une bouteille d'eau.", "bouteille d'eau"),
                                          ("la feuille pour les exercices", "feuille d'exercices"),
                                          ("le GRAND coussin", "grand coussin")])
def test_une_demande_claire_donne_tout_de_suite_une_tache(phrase, objet):
    tableau, _, _, _ = _tableau()
    reponse = tableau.demander(SOIGNANT, "p01", phrase)
    assert reponse["genre"] == "tâche" and reponse["tache"]["quoi"] == objet and reponse["tache"]["sorte"] == "robot"


def test_un_objet_absent_de_la_reserve_le_prototype_le_dit_et_la_tache_passe_a_un_humain():
    tableau, _, _, _ = _tableau()
    reponse = tableau.demander(SOIGNANT, "p01", "il manque un fauteuil roulant")
    tache = reponse["tache"]
    assert tache["sorte"] == "humain" and tache["etat"] == "demandée" and tache["ou"] == "Chambre 12"
    assert tache["quoi"] == "il manque un fauteuil roulant"  # les mots de la personne, tels quels
    assert reponse["phrase"] == "Je ne trouve pas cet objet dans la réserve. Je passe la demande à un humain."
    assert "réserve" in tache["pourquoi_un_humain"]


def test_un_choix_qui_n_est_pas_dans_la_reserve_n_est_pas_cru():
    tableau, _, _, _ = _tableau()
    reponse = tableau.demander(SOIGNANT, "p01", "il manque un coussin", choix="coussin en or")
    assert reponse["genre"] == "question"  # on repose la question, on n'invente pas un objet


def test_une_chambre_hors_du_plan_passe_a_un_humain():
    tableau, _, _, _ = _tableau()
    reponse = tableau.demander(MEDECIN, "p05", "une couverture")  # p05 : chambre 15, pas sur le plan du robot
    assert reponse["tache"]["sorte"] == "humain" and "plan" in reponse["tache"]["pourquoi_un_humain"]
    assert reponse["phrase"] == "La chambre 15 n'est pas sur le plan du robot. Je passe la demande à un humain."


def test_une_question_de_sante_n_est_pas_une_demande_d_objet():
    tableau, _, _, _ = _tableau()
    reponse = tableau.demander(SOIGNANT, "p01", "elle a mal, il lui faut quelque chose contre la douleur")
    assert reponse["tache"]["sorte"] == "humain"  # rien dans la réserve : un humain s'en occupe, sans conseil
    assert "douleur" not in reponse["phrase"] and "médicament" not in reponse["phrase"]


# ---------------------------------------------------------------- qui a le droit
def test_qui_peut_demander():
    tableau, carnet, _, _ = _tableau()
    with pytest.raises(AccesRefuse):
        tableau.demander(SOIGNANT, "p05", "une couverture")  # pas à son étage
    with pytest.raises(AccesRefuse):
        tableau.demander(DIRECTION, "p01", "une couverture")
    with pytest.raises(AccesRefuse):
        tableau.demander(ROBOT, "p01", "une couverture")  # un robot ne se donne pas de tâche
    with pytest.raises(AccesRefuse):
        tableau.demander(BADGES["patient-p01"], "p01", "une couverture")  # la porte ne donne pas la réserve au patient
    assert carnet.lignes() == []


# ---------------------------------------------------------------- le tableau
def test_le_tableau_montre_les_taches_de_mes_patients_et_leurs_etats():
    tableau, _, _, _ = _tableau()
    assert ETATS == ("demandée", "attribuée", "en route", "livrée", "échouée", "reprise")
    tableau.demander(SOIGNANT, "p01", "une couverture")
    tableau.demander(SOIGNANT, "p01", "il manque un fauteuil roulant")
    tableau.demander(MEDECIN, "p05", "une couverture")
    du_soignant = tableau.tableau(SOIGNANT)
    assert [(t["sorte"], t["quoi"]) for t in du_soignant] == [("robot", "couverture"), ("humain", "il manque un fauteuil roulant")]
    assert all(t["etat"] == "demandée" and t["nom_du_patient"] == "Madame Giulia B." for t in du_soignant)
    assert [t["pour_qui"] for t in tableau.tableau(MEDECIN)] == ["p01", "p01", "p05"]
    with pytest.raises(AccesRefuse):
        tableau.tableau(DIRECTION)


def test_le_robot_ne_voit_que_le_lieu_la_tache_le_prenom_et_la_langue():
    tableau, _, _, _ = _tableau()
    tableau.demander(SOIGNANT, "p01", "une couverture")
    tableau.demander(SOIGNANT, "p01", "il manque un fauteuil roulant")
    pour_le_robot = tableau.pour_le_robot(ROBOT)
    assert len(pour_le_robot) == 1  # seulement les tâches pour un robot
    assert set(pour_le_robot[0]) == {"id", "quoi", "de", "ou", "pour_quand", "etat", "prenom", "langue"}
    assert pour_le_robot[0]["prenom"] == "Giulia" and pour_le_robot[0]["langue"] == "it"
    with pytest.raises(AccesRefuse):
        tableau.pour_le_robot(SOIGNANT)


# ---------------------------------------------------------------- le point de liste en attente d'un objet
def test_un_point_de_liste_passe_en_attente_d_un_objet_et_devient_une_demande():
    tableau, carnet, listes, _ = _tableau()
    reponse = tableau.demander(SOIGNANT, "p01", "la feuille d'exercices", liste="avant_physio", numero=3)
    tache = reponse["tache"]
    assert tache["point"] == {"liste": "avant_physio", "numero": 3}
    points = {p["numero"]: p for p in listes.liste(SOIGNANT, "p01", "avant_physio")["points"]}
    assert points[3]["etat"] == "en attente d'un objet" and points[3]["tache"] == tache["id"]
    listes.cocher(SOIGNANT, "p01", "avant_physio", 1)
    assert listes.je_sors(SOIGNANT, "p01")["phrase"].startswith("Il reste 3 points")  # 2, 4, 5 ; le 3 attend le robot
    assert [l["genre"] for l in carnet.lignes()][:2] == ["tâche", "point de liste"]


def test_une_question_ou_un_objet_absent_ne_met_pas_le_point_en_attente():
    tableau, _, listes, _ = _tableau()
    tableau.demander(SOIGNANT, "p01", "il manque un coussin", liste="installation", numero=4)  # floue : question
    tableau.demander(SOIGNANT, "p01", "un fauteuil roulant", liste="installation", numero=4)  # absent : humain
    points = {p["numero"]: p for p in listes.liste(SOIGNANT, "p01", "installation")["points"]}
    assert points[4]["etat"] == "à faire"


# ---------------------------------------------------------------- tout par la porte, rien dans le faux dossier
def test_la_reserve_et_le_plan_sont_lus_par_la_porte_et_le_faux_dossier_ne_change_pas():
    avant = faux_dossier.empreinte()
    tableau, _, _, porte = _tableau()
    tableau.demander(SOIGNANT, "p01", "une couverture")
    quoi = [l["quoi"] for l in porte.journal.lignes() if l["qui"] == "soignant-etage-2" and l["resultat"] == "lu"]
    assert "réserve" in quoi and "lieux" in quoi and "patient" in quoi
    assert faux_dossier.empreinte() == avant
    assert faux_dossier.charger().reserve[2]["quantite"] == 3  # la réserve du faux dossier n'est pas décomptée


# ---------------------------------------------------------------- à l'écran : par un bouton d'abord
def _client():
    from briques.clinique.ecrans import brancher_ecrans

    horloge = HorlogeDeDemonstration()
    app = FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge))
    return TestClient(app), clinique


def test_la_demande_par_un_bouton_sur_la_page_de_la_liste():
    client, clinique = _client()
    P01 = {"badge": "soignant-etage-2", "patient": "p01"}
    page = client.get("/clinique/soignant/liste", params={**P01, "liste": "installation"}).text
    assert "Il manque un objet" in page and 'data-objet="grand coussin"' in page and 'data-objet="coussin"' in page
    question = client.post("/api/clinique/demande", json={**P01, "texte": "il manque un coussin en chambre 12"}).json()
    assert question["genre"] == "question" and question["choix"] == ["grand coussin", "coussin de nuque"]
    reponse = client.post("/api/clinique/demande", json={**P01, "texte": "il manque un coussin en chambre 12",
                                                         "choix": "grand coussin"}).json()
    assert reponse["tache"]["sorte"] == "robot" and reponse["tache"]["ou"] == "Chambre 12"
    absent = client.post("/api/clinique/demande", json={**P01, "texte": "un fauteuil roulant"}).json()
    assert absent["tache"]["sorte"] == "humain"
    assert client.post("/api/clinique/demande", json={"badge": "direction", "patient": "p01", "texte": "une couverture"}).status_code == 403
    assert client.post("/api/clinique/demande", json={**P01, "texte": "une couverture"},
                       headers={"Origin": "http://autre-site.example"}).status_code == 403
    taches = client.get("/api/clinique/taches", params={"badge": "soignant-etage-2"}).json()["taches"]
    assert [(t["sorte"], t["etat"]) for t in taches] == [("robot", "demandée"), ("humain", "demandée")]
    contenu = client.get("/clinique/soignant/contenu").text
    assert "Demandes" in contenu and "grand coussin" in contenu and "pour un humain" in contenu and "demandée" in contenu
    assert len(clinique.carnet.lignes("tâche")) == 2
