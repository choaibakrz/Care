"""La clinique en boîte — T17, demander au robot à la voix, AU NIVEAU DU TEXTE RECONNU (cahier 5.6).

« Fini » veut dire :
- « il manque un coussin » fait demander lequel : le grand, ou celui pour la nuque ;
- la réponse (« le grand », « celui pour la nuque ») lance la bonne livraison, sur le faux robot, sous le gardien ;
- une réponse qui ne choisit pas fait reposer la question ; « annule » l'oublie ; rien ne part sur une phrase mal
  entendue ; un objet absent de la réserve passe à un humain ;
- la voix ne donne aucun droit de plus que le bouton.
DIRE VRAI : ni micro ni modèle d'écoute sur l'iMac (R4). La « phrase entendue » est un texte tapé. Le robot comprend
les demandes en français seulement (les noms des objets de la réserve sont en français).
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique.carnet import Carnet
from briques.clinique.coursier import monde_de_la_clinique
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.listes import ListesDeSoin
from briques.clinique.porte import JournalDesAcces, PorteDeLecture, charger_badges
from briques.clinique.taches import TableauDesTaches
from conftest import lancer

BADGES = charger_badges()
SOIGNANT = BADGES["soignant-etage-2"]
QUESTION = "Lequel : le grand coussin, ou le coussin de nuque ?"


def _tableau():
    porte, carnet = PorteDeLecture(journal=JournalDesAcces()), Carnet()
    return TableauDesTaches(porte, carnet, ListesDeSoin(porte, carnet))


def _taches(tableau):
    return [l["donnees"] for l in tableau.carnet.lignes("tâche")]


def test_il_manque_un_coussin_fait_demander_lequel_et_rien_ne_part():
    tableau = _tableau()
    r = tableau.entendre(SOIGNANT, "p01", "il manque un coussin")
    assert r["compris"] == "question" and r["dit"] == QUESTION and r["choix"] == ["grand coussin", "coussin de nuque"]
    assert _taches(tableau) == []


@pytest.mark.parametrize("reponse, objet", [("le grand", "grand coussin"), ("le grand coussin", "grand coussin"),
                                            ("celui pour la nuque", "coussin de nuque"), ("la nuque", "coussin de nuque"),
                                            ("Le GRAND, s'il vous plaît.", "grand coussin")])
def test_la_reponse_choisit_le_bon_objet(reponse, objet):
    tableau = _tableau()
    tableau.entendre(SOIGNANT, "p01", "il manque un coussin")
    r = tableau.entendre(SOIGNANT, "p01", reponse)
    assert r["compris"] == "tâche" and r["tache"]["quoi"] == objet and r["tache"]["sorte"] == "robot"
    assert r["tache"]["ou"] == "Chambre 12" and r["tache"]["par_la_voix"] is True
    assert [t["quoi"] for t in _taches(tableau)] == [objet]
    assert tableau.entendre(SOIGNANT, "p01", "le grand")["compris"] == "rien"  # la question est finie : plus rien n'attend


@pytest.mark.parametrize("reponse", ["le coussin", "oui", "les deux", "euh", "le grand ou la nuque"])
def test_une_reponse_qui_ne_choisit_pas_fait_reposer_la_question(reponse):
    tableau = _tableau()
    tableau.entendre(SOIGNANT, "p01", "il manque un coussin")
    r = tableau.entendre(SOIGNANT, "p01", reponse)
    assert r["compris"] == "question" and QUESTION in r["dit"] and _taches(tableau) == []
    assert tableau.entendre(SOIGNANT, "p01", "la nuque")["tache"]["quoi"] == "coussin de nuque"  # elle attend toujours


def test_annule_oublie_la_question_et_rien_ne_part():
    tableau = _tableau()
    tableau.entendre(SOIGNANT, "p01", "il manque un coussin")
    r = tableau.entendre(SOIGNANT, "p01", "annule")
    assert r["compris"] == "rien" and "annul" in r["dit"].lower() and _taches(tableau) == []
    assert tableau.entendre(SOIGNANT, "p01", "le grand")["compris"] == "rien"


def test_une_demande_precise_part_sans_question():
    tableau = _tableau()
    r = tableau.entendre(SOIGNANT, "p01", "il manque une couverture")
    assert r["compris"] == "tâche" and r["tache"]["quoi"] == "couverture" and r["tache"]["sorte"] == "robot"
    r = tableau.entendre(SOIGNANT, "p01", "apporte la bouteille d'eau")
    assert r["tache"]["quoi"] == "bouteille d'eau"


def test_un_objet_absent_de_la_reserve_passe_a_un_humain_et_le_dit():
    tableau = _tableau()
    r = tableau.entendre(SOIGNANT, "p01", "il manque un fauteuil roulant")
    assert r["compris"] == "tâche" and r["tache"]["sorte"] == "humain" and "Je ne trouve pas cet objet" in r["dit"]


@pytest.mark.parametrize("phrase", ["bonjour", "un coussin", "sonnette, fait", "", "le grand"])
def test_sans_demande_reconnue_rien_ne_part(phrase):
    tableau = _tableau()
    r = tableau.entendre(SOIGNANT, "p01", phrase)
    assert r["compris"] == "rien" and r["dit"] and _taches(tableau) == []


def test_une_phrase_mal_entendue_ne_fait_rien_partir_et_ne_repond_pas_a_la_question():
    tableau = _tableau()
    assert tableau.entendre(SOIGNANT, "p01", "il manque un coussin", confiance=0.2)["compris"] == "rien"
    tableau.entendre(SOIGNANT, "p01", "il manque un coussin")
    r = tableau.entendre(SOIGNANT, "p01", "le grand", confiance=0.2)
    assert r["compris"] == "rien" and "doigt" in r["dit"] and _taches(tableau) == []
    assert tableau.entendre(SOIGNANT, "p01", "le grand")["compris"] == "tâche"  # bien entendue, la réponse compte


def test_la_question_d_une_personne_n_est_pas_celle_d_une_autre_et_la_voix_ne_donne_aucun_droit():
    tableau = _tableau()
    tableau.entendre(SOIGNANT, "p01", "il manque un coussin")
    with pytest.raises(Exception):
        tableau.entendre(BADGES["patient-p01"], "p01", "le grand")
    with pytest.raises(Exception):
        tableau.entendre(BADGES["robot-r1"], "p01", "il manque un coussin")
    assert _taches(tableau) == []


# ---------------------------------------------------------------------------------------------- jusqu'au robot
def test_la_reponse_lance_la_bonne_livraison_sur_le_faux_robot_sous_le_gardien(tmp_path, reglages):
    from briques.clinique.ecrans import brancher_ecrans
    from commun.systeme import Systeme

    r = {**reglages, "ecran": dict(reglages["ecran"]), "cerveau": {**reglages["cerveau"], "choix": "regles"}}
    systeme = Systeme(r, dossier_journal=tmp_path / "journal", acceleration=20.0, monde=monde_de_la_clinique())
    horloge = HorlogeDeDemonstration(bus=systeme.bus)
    app = FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge), systeme=systeme, code_equipe="x")

    async def scene():
        await systeme.demarrer()
        try:
            question = clinique.entendre(SOIGNANT, "p01", "installation", "il manque un coussin")
            reponse = clinique.entendre(SOIGNANT, "p01", "installation", "celui pour la nuque")
            for _ in range(2000):
                if clinique.taches.tache(reponse["tache"]["id"])["etat"] in ("livrée", "échouée"):
                    break
                await asyncio.sleep(0.005)
            return question, reponse
        finally:
            await systeme.arreter()

    question, reponse = lancer(scene())
    assert question["compris"] == "question" and question["dit"] == QUESTION
    fin = clinique.taches.tache(reponse["tache"]["id"])
    assert fin["etat"] == "livrée" and fin["quoi"] == "coussin de nuque" and fin["etiquette"] == "FAUX ROBOT"
    saisis = [e.donnees["action"]["parametres"].get("objet") for e in systeme.bus.historique
              if e.type == "action_demarree" and e.donnees["action"]["nom"] == "saisir"]
    assert saisis == ["coussin de nuque"]  # le bon objet, pas l'autre
    oui = [e for e in systeme.bus.historique if e.type == "gardien_decision" and e.donnees["verdict"] == "oui"]
    assert len(oui) == 4


def test_le_meme_champ_de_l_ecran_coche_un_point_ou_demande_au_robot():
    from briques.clinique.ecrans import brancher_ecrans

    horloge = HorlogeDeDemonstration()
    app = FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge), code_equipe="x")
    client = TestClient(app)
    corps = {"badge": SOIGNANT.id, "patient": "p01", "liste": "installation"}
    assert client.post("/api/clinique/liste/voix", json={**corps, "phrase": "sonnette, fait"}).json()["compris"] == "coche"
    r = client.post("/api/clinique/liste/voix", json={**corps, "phrase": "il manque un coussin"}).json()
    assert r["compris"] == "question" and r["dit"] == QUESTION
    r = client.post("/api/clinique/liste/voix", json={**corps, "phrase": "le grand"}).json()
    assert r["compris"] == "tâche" and r["tache"]["quoi"] == "grand coussin"
    assert "grand coussin" in client.get("/clinique/soignant", params={"badge": SOIGNANT.id}).text
    r = client.post("/api/clinique/liste/voix", json={**corps, "phrase": "bonjour"}).json()
    assert r["compris"] == "rien"
