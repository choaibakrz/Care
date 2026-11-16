"""La clinique en boîte — K01b, le bouton « Demande au hasard » (avenant 2, K01 ; seconde moitié).

« Fini » veut dire :
- sur l'écran du chef de démonstration, un bouton « Demande au hasard » : il tire une demande, l'affiche, et la joue ;
- la page dit quel cerveau a servi (le cerveau de test), l'étiquette FAUX ROBOT, la réponse attendue et la réponse obtenue ;
- le numéro du tirage et le rang de la demande sont affichés : on peut refaire exactement la même ;
- l'option du vrai Apertus dit vrai : tant qu'Apertus n'est pas sur l'ordinateur, elle ne joue rien et le dit.
"""
from __future__ import annotations

import html

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique import tirage
from briques.clinique.carnet import Carnet
from briques.clinique.ecrans import brancher_ecrans
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.porte import JournalDesAcces, PorteDeLecture

CODE = {"X-Code-Equipe": "code-d-essai"}


@pytest.fixture
def client():
    horloge, app = HorlogeDeDemonstration(), FastAPI()
    brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                    carnet=Carnet(horloge=horloge), code_equipe="code-d-essai")
    return TestClient(app)


def test_la_page_du_chef_a_le_bouton_et_dit_vrai(client):
    page = html.unescape(client.get("/clinique/tirage").text)
    for mot in ("Demande au hasard", "cerveau de test", "FAUX ROBOT", "pas ce que le cerveau comprend",
                "Aucune demande tirée pour l'instant", "à part de la séance"):
        assert mot in page, mot
    assert "/clinique/tirage" in client.get("/clinique").text


def test_le_bouton_tire_une_demande_l_affiche_et_la_joue(client):
    assert client.post("/api/clinique/tirage/au-hasard").status_code == 403  # un bouton du chef : code d'équipe
    r = client.post("/api/clinique/tirage/au-hasard", headers=CODE)
    assert r.status_code == 200, r.text
    d = r.json()["demande"]
    assert d["sorte"] in tirage.SORTES and d["texte"] and d["attendu"] and d["obtenu"] and d["phrase"]
    assert isinstance(d["bonne"], bool) and d["interdit_execute"] is False  # la demande est tirée au hasard : on ne présume pas de la réponse
    assert r.json()["cerveau"].startswith("cerveau de test") and r.json()["etiquette"] == "FAUX ROBOT"
    # on peut refaire exactement la même : le numéro du tirage et le rang
    meme = next(x for x in tirage.tirer(r.json()["numero"]) if x["rang"] == d["rang"])
    assert meme["texte"] == d["texte"] and meme["sorte"] == d["sorte"]
    page = html.unescape(client.get("/clinique/tirage").text)
    for mot in (d["texte"], d["attendu"], d["phrase"], f"tirage n° {r.json()['numero']}", f"demande {d['rang']}",
                "bonne réponse" if d["bonne"] else "mauvaise réponse", "gestes interdits exécutés : 0"):
        assert mot in page, mot
    assert "Aucune demande tirée" not in page


def test_on_peut_rejouer_un_numero_et_un_rang_choisis(client):
    r = client.post("/api/clinique/tirage/au-hasard", json={"numero": 7, "rang": 3}, headers=CODE)
    attendu = next(x for x in tirage.tirer(7) if x["rang"] == 3)
    assert r.status_code == 200 and r.json()["numero"] == 7 and r.json()["demande"]["texte"] == attendu["texte"]
    assert client.post("/api/clinique/tirage/au-hasard", json={"numero": 7, "rang": 99}, headers=CODE).status_code == 400


def test_l_option_apertus_dit_vrai(capsys):
    assert tirage.main(["--apertus", "1"]) == 2
    sortie = capsys.readouterr().out
    assert "pas encore possible" in sortie and "Apertus" in sortie and "cerveau de test" in sortie
    assert "bonnes réponses" not in sortie  # rien n'est joué, aucun chiffre n'est affiché
