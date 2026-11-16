"""La clinique en boîte — K02a, toute aide humaine se compte (avenant 2, K02 ; première moitié).

K02 est coupée en deux. Ici, K02a. « Fini » veut dire :
- un événement AIDE HUMAINE s'écrit dans la boîte noire quand quelqu'un appuie sur « J'ai aidé », quand un humain reprend
  une tâche de robot, quand une tâche est relancée à la main ;
- chaque essai va dans UNE case sur quatre : du premier coup ; après une reprise automatique ; avec une aide humaine ; raté ;
- un essai où « J'ai aidé » a été pressé tombe dans « avec aide », jamais dans « du premier coup » ;
- deux chiffres s'affichent avec leur niveau de preuve, leur nombre d'essais et leur date : « réussis du premier coup »
  et « une aide humaine pour tant de tâches » ; le troisième (durée sans arrêt) dit « non mesuré » ;
- la ligne RÉEL dit « aucun essai compté » tant que l'équipe n'a rien compté.
K02b fera : la commande « endurance », le troisième chiffre, le geste télécommandé, le protocole, le bouton « réussi avec aide ».
Les vérifications de J01 ne sont pas changées.
"""
from __future__ import annotations

import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.b12_boite_noire.journal import lire
from briques.clinique import aide_humaine, essais, repetition
from briques.clinique.carnet import Carnet
from briques.clinique.ecrans import brancher_ecrans
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.listes import ListesDeSoin
from briques.clinique.porte import JournalDesAcces, PorteDeLecture, charger_badges
from briques.clinique.taches import TableauDesTaches


def _ok(etiquette="SIMULÉ"):
    return lambda: repetition.Resultat(True, etiquette, "essai")


def _faux_controles():
    return {n: _ok() for n in range(1, 15)}


def _jouer(controles, tmp_path, liste=None, reels=None):
    lignes: list[str] = []
    bilan = essais.jouer_les_essais(liste or essais.charger(), controles, ecrire=lignes.append, dossier=tmp_path,
                                    compteur_reel=reels or essais.CompteurReel(tmp_path / "essais_reels.jsonl"))
    return bilan, lignes


def _tableau():
    horloge = HorlogeDeDemonstration()
    carnet = Carnet(horloge=horloge)
    listes = ListesDeSoin(PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), carnet)
    return TableauDesTaches(listes.porte, carnet, listes), charger_badges()


# ---------------------------------------------------------------------------------------------- les quatre cases
@pytest.mark.parametrize("reussi, aides, reprises, case", [
    (True, 0, 0, "du premier coup"),
    (True, 0, 2, "après une reprise automatique"),
    (True, 1, 0, "avec une aide humaine"),
    (True, 1, 3, "avec une aide humaine"),   # l'aide humaine passe avant la reprise automatique
    (False, 0, 0, "raté"),
    (False, 2, 1, "raté"),                    # raté reste raté, même avec de l'aide
])
def test_un_essai_ne_va_que_dans_une_case(reussi, aides, reprises, case):
    assert aide_humaine.classer(reussi, aides, reprises) == case
    assert case in aide_humaine.CASES and len(aide_humaine.CASES) == 4


def test_un_essai_ou_j_ai_aide_a_ete_presse_tombe_dans_avec_aide(tmp_path):
    controles = _faux_controles()
    appels = {"n": 0}

    def avec_le_bouton():
        appels["n"] += 1
        if appels["n"] == 3:  # pendant l'essai 3, quelqu'un appuie sur « J'ai aidé »
            aide_humaine.signaler("bouton", qui="chef de démonstration")
        return repetition.Resultat(True, "SIMULÉ", "essai")

    controles[5] = avec_le_bouton
    bilan, lignes = _jouer(controles, tmp_path)
    cases = bilan["fiche"]["cases"]
    assert cases == {"du premier coup": 19, "après une reprise automatique": 0, "avec une aide humaine": 1, "raté": 0}
    assert bilan["fiche"]["par_essai"][3]["case"] == "avec une aide humaine"
    assert any("réussis du premier coup : 19 sur 20" in l for l in lignes)
    # dans la boîte noire : l'événement AIDE HUMAINE, avec l'essai
    aides = [e for e in lire(bilan["boite_noire"]) if e.type == "note" and e.donnees.get("quoi") == "AIDE HUMAINE"]
    assert len(aides) == 1 and aides[0].donnees["essai"] == 3 and aides[0].donnees["sorte"] == "bouton"


def test_un_essai_rate_va_dans_rate_et_les_cases_font_le_total(tmp_path):
    controles = _faux_controles()
    appels = {"n": 0}

    def rate_parfois():
        appels["n"] += 1
        return repetition.Resultat(appels["n"] not in (2, 9), "SIMULÉ", "essai")

    controles[4] = rate_parfois
    bilan, _ = _jouer(controles, tmp_path)
    cases = bilan["fiche"]["cases"]
    assert cases["raté"] == 2 and cases["du premier coup"] == 18 and sum(cases.values()) == 20


def test_une_reprise_imprevue_compte_mais_pas_la_panne_provoquee_du_scenario(tmp_path):
    controles = _faux_controles()
    appels = {"n": 0}

    def avec_reprises():
        appels["n"] += 1
        aide_humaine.signaler_reprise(prevue=True)        # la panne provoquée de la scène 6 : dans le scénario
        if appels["n"] == 7:
            aide_humaine.signaler_reprise(prevue=False)   # une vraie reprise, que personne n'avait prévue
        return repetition.Resultat(True, "SIMULÉ", "essai")

    controles[12] = avec_reprises
    bilan, lignes = _jouer(controles, tmp_path)
    assert bilan["fiche"]["cases"]["après une reprise automatique"] == 1 and bilan["fiche"]["cases"]["du premier coup"] == 19
    assert bilan["fiche"]["reprises_prevues"] == 20
    assert any("font partie du scénario" in l and "20" in l for l in lignes)


# ---------------------------------------------------------------------------------------------- les chiffres
def test_les_chiffres_s_affichent_avec_niveau_nombre_et_date(tmp_path):
    bilan, lignes = _jouer(_faux_controles(), tmp_path)
    chiffres = [l for l in lignes if l.startswith("CHIFFRE ")]
    assert len(chiffres) == 3
    for l in chiffres[:2]:
        assert "[FAUX ROBOT" in l and "20 essais" in l and re.search(r"\d\d\.\d\d\.\d{4}", l), l
    assert "réussis du premier coup : 20 sur 20" in chiffres[0]
    assert "aucune tâche de robot" in chiffres[1]  # de faux contrôles : aucune tâche, donc pas de chiffre inventé
    assert "plus longue durée sans arrêt : non mesuré" in chiffres[2]
    assert any(l.strip() == "RÉEL : aucun essai compté" for l in lignes)
    assert len([l for l in lignes if re.match(r"\s*\d+\. ", l)]) == 14  # le tableau de J01 n'a pas bougé


def test_une_aide_humaine_pour_tant_de_taches(tmp_path):
    controles = _faux_controles()
    appels = {"n": 0}

    def des_taches():
        appels["n"] += 1
        aide_humaine.tache_de_robot()
        aide_humaine.tache_de_robot()
        if appels["n"] in (1, 2, 3, 4):
            aide_humaine.signaler("main", qui="robot-r1", tache="t1")
        return repetition.Resultat(True, "SIMULÉ", "essai")

    controles[8] = des_taches
    bilan, lignes = _jouer(controles, tmp_path)
    ligne = next(l for l in lignes if l.startswith("CHIFFRE 2"))
    assert "4 aides humaines pour 40 tâches de robot" in ligne and "une aide pour 10 tâches" in ligne
    assert bilan["fiche"]["aides_humaines"] == 4 and bilan["fiche"]["taches_de_robot"] == 40


def test_aucune_aide_sur_tant_de_taches(tmp_path):
    controles = _faux_controles()
    controles[8] = lambda: (aide_humaine.tache_de_robot(), repetition.Resultat(True, "FAUX ROBOT", "essai"))[1]
    _, lignes = _jouer(controles, tmp_path, liste=essais.charger()[:5])
    assert "aucune aide sur 5 tâches de robot" in next(l for l in lignes if l.startswith("CHIFFRE 2"))


def test_la_ligne_reel_montre_les_essais_de_l_equipe_quand_il_y_en_a(tmp_path):
    reels = essais.CompteurReel(tmp_path / "essais_reels.jsonl")
    reels.compter("robot d'essai", "poser le coussin", True)
    reels.compter("robot d'essai", "poser le coussin", False)
    _, lignes = _jouer(_faux_controles(), tmp_path, liste=essais.charger()[:2], reels=reels)
    assert any(l.strip() == "RÉEL : 1 sur 2" for l in lignes)


# ---------------------------------------------------------------------------------------------- avec les vraies pièces
def test_un_objet_absent_passe_a_un_humain_c_est_une_aide_humaine(tmp_path):
    """Les essais 2 (objet livré) et 4 (objet absent : un humain reprend) par la vraie pièce de l'étape 8."""
    liste = [e for e in essais.charger() if e["numero"] in (2, 4)]
    controles = _faux_controles()
    controles[8] = repetition.CONTROLES[8]
    bilan, lignes = _jouer(controles, tmp_path, liste=liste)
    par_essai = bilan["fiche"]["par_essai"]
    assert par_essai[2]["case"] == "du premier coup" and par_essai[2]["aides"] == 0 and par_essai[2]["taches_de_robot"] == 1
    assert par_essai[4]["case"] == "avec une aide humaine" and par_essai[4]["aides"] == 1
    aides = [e.donnees for e in lire(bilan["boite_noire"]) if e.type == "note" and e.donnees.get("quoi") == "AIDE HUMAINE"]
    assert len(aides) == 1 and aides[0]["essai"] == 4 and aides[0]["sorte"] == "main"


def test_un_humain_qui_reprend_une_tache_de_robot_est_note_sur_le_tableau():
    tableau, badges = _tableau()
    with aide_humaine.compter() as compte:
        tache = tableau.demander(badges["soignant-etage-2"], "p01", "la couverture")["tache"]
        assert tache["sorte"] == "robot" and compte.taches_de_robot == 1 and compte.aides == []
        tableau.changer_etat(badges["robot-r1"], tache["id"], "demandée", sorte="humain", pourquoi_un_humain="essai")
        tableau.changer_etat(badges["robot-r1"], tache["id"], "demandée", sorte="humain", pourquoi_un_humain="encore")
    assert len(compte.aides) == 1 and compte.aides[0]["sorte"] == "main" and compte.aides[0]["tache"] == tache["id"]
    assert len(tableau.aides) == 1  # la deuxième fois, la tâche était déjà chez un humain : pas comptée deux fois


def test_une_tache_demandee_a_un_humain_n_est_pas_une_aide():
    tableau, badges = _tableau()
    with aide_humaine.compter() as compte:
        tableau.pour_un_humain(badges["medecin-exemple"], "p01", "voir la patiente", pour="soignant")
    assert compte.aides == [] and compte.taches_de_robot == 0 and tableau.aides == []


def test_hors_d_un_essai_signaler_ne_casse_rien():
    aide = aide_humaine.signaler("bouton", qui="x")
    assert aide["sorte"] == "bouton" and aide["quoi"] == "AIDE HUMAINE"
    with pytest.raises(ValueError):
        aide_humaine.signaler("magie", qui="x")


# ---------------------------------------------------------------------------------------------- le bouton « J'ai aidé »
@pytest.fixture
def client():
    app = FastAPI()
    horloge = HorlogeDeDemonstration()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge), code_equipe="code-d-essai")
    return TestClient(app), clinique


def test_le_bouton_j_ai_aide_ecrit_une_aide_humaine(client):
    c, clinique = client
    page = c.get("/clinique/aide-humaine")
    assert page.status_code == 200 and "J'ai aidé" in page.text.replace("&#x27;", "'") and "données inventées" in page.text.lower()
    assert "aucune aide humaine" in page.text
    r = c.post("/api/clinique/aide-humaine", json={"qui": "Chef de démonstration", "note": "j'ai redressé le coussin"},
               headers={"X-Code-Equipe": "code-d-essai"})
    assert r.status_code == 200 and r.json()["aide"]["sorte"] == "bouton"
    assert len(clinique.taches.aides) == 1 and clinique.taches.aides[0]["detail"] == "j'ai redressé le coussin"
    assert c.get("/api/clinique/aide-humaine").json()["aides"] == 1
    assert "1 aide humaine" in c.get("/clinique/aide-humaine").text


def test_le_bouton_demande_le_code_d_equipe_depuis_un_autre_ordinateur():
    app = FastAPI()
    horloge = HorlogeDeDemonstration()
    brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                    carnet=Carnet(horloge=horloge), code_equipe="secret-d-essai")
    c = TestClient(app)
    assert c.post("/api/clinique/aide-humaine", json={"qui": "x"}).status_code == 403
    assert c.post("/api/clinique/aide-humaine", json={"qui": "x"}, headers={"X-Code-Equipe": "faux"}).status_code == 403
