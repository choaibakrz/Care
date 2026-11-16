"""La clinique en boîte — J05b, la page « Qui décide », et aucune promesse non mesurée (avenant jury, J05 ; seconde moitié).

« Qu'est-ce qui change pour les soignants, et qui l'a décidé ? » « Fini » veut dire :
- la page « Qui décide » dit, pour chaque chose que fait le système (accueillir, orienter, livrer, rappeler un point,
  résumer pour le médecin, poser les questions du soir, ranger un papier) : qui peut l'allumer, qui peut la mettre en
  pause, qui est prévenu, et ce que le système ne fait jamais seul ;
- elle se fabrique à partir des réglages réels (les cartes de rôle, les droits des badges) : une vérification change un
  réglage, et la page change ;
- une vérification cherche les promesses de la règle 4 dans les textes des écrans et n'en trouve aucune.
"""
from __future__ import annotations

import html
import re
import shutil
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique import cartes, qui_decide
from briques.clinique.carnet import Carnet
from briques.clinique.ecrans import brancher_ecrans
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.porte import JournalDesAcces, PorteDeLecture

RACINE = Path(__file__).resolve().parents[3]
CHOSES = ["accueillir", "orienter", "livrer", "rappeler un point", "résumer pour le médecin", "poser les questions du soir",
          "ranger un papier"]


def _ligne(table, chose):
    return next(l for l in table if l["chose"] == chose)


# ---------------------------------------------------------------------------------------------- les droits, demandés aux vraies pièces
def test_les_droits_des_badges_sont_demandes_aux_vraies_pieces():
    droits = qui_decide.droits()
    assert droits["mettre une pause"] == ["soignant"]
    assert droits["ranger un papier"] == ["accueil"]
    assert droits["lire le résumé du matin"] == ["médecin"]
    assert droits["poser une question du soir"] == ["patient"]
    assert droits["voir les messages du hall pour l'étage"] == ["soignant"]
    assert {"soignant", "médecin"} <= set(droits["demander une livraison"])
    assert set(droits["cocher un point d'une liste"]) >= {"soignant"}
    for roles in droits.values():  # un robot, la direction ou l'assistant ne décident de rien
        assert not {"robot", "direction", "assistant"} & set(roles), roles


# ---------------------------------------------------------------------------------------------- la table
def test_la_table_dit_les_quatre_choses_pour_chacune_des_sept():
    table = qui_decide.table()
    assert [l["chose"] for l in table] == CHOSES
    for ligne in table:
        assert ligne["allume"] and ligne["pause"] and ligne["prevenu"] and ligne["jamais_seul"], ligne["chose"]
    livrer = _ligne(table, "livrer")
    assert "R1" in livrer["allume"] and "soignant" in livrer["allume"] and "soignant" in livrer["pause"]
    assert "sans le « oui » du gardien" in livrer["jamais_seul"]
    accueillir = _ligne(table, "accueillir")
    assert "aucun robot n'a aujourd'hui" in accueillir["allume"]  # R1 a la carte Étage : personne ne tient le hall
    assert "Dans le hall, le robot ne dit rien sur la santé." in accueillir["jamais_seul"]  # la règle, lue dans le réglage
    assert "accueil" in _ligne(table, "ranger un papier")["allume"] and "sans la validation" in _ligne(table, "ranger un papier")["jamais_seul"]
    assert "médecin" in _ligne(table, "résumer pour le médecin")["allume"]
    assert "patient" in _ligne(table, "poser les questions du soir")["allume"] and "médecin" in _ligne(table, "poser les questions du soir")["prevenu"]


def test_on_change_la_carte_d_un_robot_et_la_table_change():
    flotte = cartes.CartesDeLaFlotte()
    avant = qui_decide.table(flotte=flotte)
    flotte.changer("robot-r1", "Accueil", qui="essai")
    apres = qui_decide.table(flotte=flotte)
    assert "aucun robot n'a aujourd'hui" in _ligne(avant, "accueillir")["allume"]
    assert "R1 (carte Accueil)" in _ligne(apres, "accueillir")["allume"] and "R1 (carte Accueil)" in _ligne(apres, "orienter")["allume"]
    assert "R1" in _ligne(avant, "livrer")["allume"] and "R1" not in _ligne(apres, "livrer")["allume"]


def test_on_change_un_fichier_de_carte_et_la_table_change(tmp_path):
    copie = tmp_path / "cartes"
    shutil.copytree(cartes.DOSSIER, copie)
    etage = copie / "etage.yaml"
    etage.write_text(etage.read_text(encoding="utf-8").replace("saisir, poser, ", ""), encoding="utf-8")  # la carte Étage ne saisit plus
    apres = qui_decide.table(flotte=cartes.CartesDeLaFlotte(dossier_des_cartes=copie))
    avant = qui_decide.table()
    assert "R2" in _ligne(avant, "livrer")["allume"] and "R2" not in _ligne(apres, "livrer")["allume"]
    assert "R4 (carte Nuit)" in _ligne(apres, "livrer")["allume"]  # la carte Nuit, elle, n'a pas changé


def test_on_change_la_regle_du_hall_et_la_table_change(monkeypatch):
    from briques.clinique import accueil

    vrais = accueil._reglages()
    monkeypatch.setattr(accueil, "_reglages", lambda: {**vrais, "regle_sante": {**vrais["regle_sante"], "phrase": "Phrase d'essai changée."}})
    assert "Phrase d'essai changée." in _ligne(qui_decide.table(), "accueillir")["jamais_seul"]


# ---------------------------------------------------------------------------------------------- la page
@pytest.fixture
def client():
    horloge, app = HorlogeDeDemonstration(), FastAPI()
    brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                    carnet=Carnet(horloge=horloge), code_equipe="")
    return TestClient(app)


def test_la_page_qui_decide_s_affiche(client):
    page = html.unescape(client.get("/clinique/qui-decide").text)
    for mot in ("Qui décide", "Qui peut l'allumer", "Qui peut la mettre en pause", "Qui est prévenu",
                "Ce que le système ne fait jamais seul", "fabriquée à partir des réglages", "Données inventées", *CHOSES):
        assert mot in page, mot
    assert "/clinique/qui-decide" in client.get("/clinique").text
    assert client.get("/api/clinique/qui-decide").json()["table"][2]["chose"] == "livrer"


# ---------------------------------------------------------------------------------------------- aucune promesse non mesurée
PROMESSES = re.compile(
    r"ne remplace (personne|pas (les|le|la|l'|un|une|des))|remplace personne|gagner du temps|gagne du temps|gain de temps|soulage|"
    r"spart zeit|entlastet|ersetzt niemanden|risparmia tempo|non sostituisce nessuno|saves time|replaces no one|"
    r"relieves? (the )?(staff|team)", re.IGNORECASE)


def test_la_recherche_sait_trouver_une_promesse():
    for phrase in ("Le robot ne remplace personne.", "Il fait gagner du temps.", "Cela soulage les équipes.", "It saves time."):
        assert PROMESSES.search(phrase), phrase
    assert not PROMESSES.search("Une carte ne remplace jamais le gardien.")  # pas une promesse sur les personnes


def test_aucune_promesse_non_mesuree_dans_les_textes_des_ecrans(client):
    pages = ["/clinique", "/clinique/soignant?badge=soignant-etage-2", "/clinique/medecin", "/clinique/accueil", "/clinique/patient",
             "/clinique/therapeute", "/clinique/direction", "/clinique/hall", "/clinique/flotte", "/clinique/journal",
             "/clinique/accueil/papiers?badge=accueil", "/clinique/aide-humaine", "/clinique/ce-qu-on-nous-a-dit",
             "/clinique/essais-reels", "/clinique/etageres", "/clinique/epreuve-etageres", "/clinique/protocole-essais-reels",
             "/clinique/moments", "/clinique/pannes", "/clinique/patient/soir?badge=patient-p01", "/clinique/pre-admission?badge=accueil",
             "/clinique/soignant/pauses?badge=soignant-etage-2", "/clinique/sources", "/clinique/tirage", "/clinique/qui-decide",
             "/clinique/soignant/fin-de-poste?badge=soignant-etage-2", "/faux-logiciel"]
    lues = 0
    for chemin in pages:
        reponse = client.get(chemin)
        if reponse.status_code != 200:
            continue
        lues += 1
        trouve = PROMESSES.search(html.unescape(reponse.text))
        assert trouve is None, (chemin, trouve.group(0))
    assert lues >= 22, lues  # presque toutes les pages ont bien été lues


def test_aucune_promesse_non_mesuree_dans_les_textes_du_programme():
    fichiers = [f for dossier in (RACINE / "briques" / "clinique", RACINE / "faux_logiciel_admin")
                for f in dossier.rglob("*") if f.suffix in (".py", ".yaml", ".md") and "tests" not in f.parts]
    assert len(fichiers) > 60
    for fichier in fichiers:
        for numero, ligne in enumerate(fichier.read_text(encoding="utf-8").splitlines(), 1):
            trouve = PROMESSES.search(ligne)
            assert trouve is None, (fichier.name, numero, ligne.strip()[:120])
