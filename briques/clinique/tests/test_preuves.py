"""La clinique en boîte — J07a, la page des preuves (avenant jury, J07).

« Une page « Preuves », que le chef de démonstration ouvre après la scène 7. Huit boutons, écrits comme des questions. »
« Fini quand : les huit boutons ouvrent chacun une preuve qui marche, sans toucher au code. » (la commande des preuves et la
pièce cassée exprès : J07b).
Preuve 8 « Où tourne quoi ? » : un tableau fabriqué par le système. Ce qui n'est pas mesuré s'écrit « non mesuré » ; la
consommation électrique s'écrit « non mesurée ». Aucun chiffre tapé à la main : les mesures viennent des fichiers gardés.
Faux robot et robots simulés. Aucun vrai robot.
"""
from __future__ import annotations

import html
import json
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique import preuves
from briques.clinique.ecrans import brancher_ecrans

CODE = {"X-Code-Equipe": "code-d-essai"}
QUESTIONS = ("Sur vingt essais, combien réussissent ?", "Montrez-moi le moment où ça a raté.", "Coupez le lien.",
             "Comment sait-il qu'il se trompe ?", "Branchez un autre robot.", "Qui décide ?", "Qu'en disent les soignants ?",
             "Où tourne quoi ?")
PIECES = ("cerveau", "écoute", "voix", "yeux", "gardien", "écrans", "boîte noire")


@pytest.fixture
def client(tmp_path):
    app = FastAPI()
    clinique = brancher_ecrans(app, code_equipe="code-d-essai")
    clinique.faux_logiciel.dossier = tmp_path / "faux_logiciel"
    return TestClient(app, headers=CODE)


def test_la_page_a_huit_boutons_ecrits_comme_des_questions(client):
    brut = client.get("/clinique/preuves")
    page = html.unescape(brut.text)
    assert brut.status_code == 200 and "DONNÉES INVENTÉES" in page and "Preuves" in page
    boutons = re.findall(r"<a class='bouton preuve' href=\"([^\"]+)\">([^<]+)</a>", page)
    assert [q for _, q in boutons] == [f"{i}. {q}" for i, q in enumerate(QUESTIONS, 1)]
    assert "/clinique/preuves" in client.get("/clinique").text


def test_chaque_bouton_ouvre_une_preuve_qui_marche(client):
    page = html.unescape(client.get("/clinique/preuves").text)
    for lien, question in re.findall(r"<a class='bouton preuve' href=\"([^\"]+)\">([^<]+)</a>", page):
        r = client.get(lien)
        assert r.status_code == 200, (question, lien, r.status_code)
        assert "DONNÉES INVENTÉES" in r.text, lien
    for lien in re.findall(r"<a class='aussi' href=\"([^\"]+)\"", page):  # les liens en plus (la panne de T24, une pause)
        assert client.get(lien).status_code == 200, lien


def test_preuve_1_le_tableau_des_essais_et_les_essais_reels_a_part(client):
    page = html.unescape(client.get("/clinique/preuves/essais").text)
    assert "Essais comptés sur le faux robot" in page and "Essais réels, comptés par l'équipe" in page
    assert "python3 lancer.py essais" in page


def test_preuve_5_le_branchement_et_son_chronometre(client):
    page = html.unescape(client.get("/clinique/preuves/brancher").text)
    assert "python3 lancer.py brancher-carte" in page and "Brancher un robot inconnu" in page and "RÉEL" in page


def test_preuve_8_le_tableau_ou_tourne_quoi_a_chaque_piece_et_n_invente_rien(client):
    page = html.unescape(client.get("/clinique/ou-tourne-quoi").text)
    for piece in PIECES:
        assert f"<td><b>{piece}</b></td>" in page, piece
    assert page.count("a besoin d'internet : non") == len(PIECES)
    assert "consommation électrique : non mesurée" in page
    assert "non mesuré" in page


def test_preuve_8_les_chiffres_viennent_des_mesures_gardees(tmp_path):
    (tmp_path / "apertus_essai.json").write_text(json.dumps({"quand": "2026-11-12T13:59:55+01:00", "temps_median_ms": 1234,
                                                              "temps_max_ms": 4000, "memoire_go": 4.2}), encoding="utf-8")
    (tmp_path / "chaine.json").write_text(json.dumps({"quand": "2026-11-12T14:02:34+01:00", "ecoute_median_ms": 111,
                                                       "voix_median_ms": 222, "cerveau_median_ms": 333}), encoding="utf-8")
    lignes = {l["piece"]: l for l in preuves.ou_tourne_quoi(tmp_path)}
    assert "1234 ms" in lignes["cerveau"]["temps"] and "4.2 Go" in lignes["cerveau"]["memoire"].replace(",", ".")
    assert "111 ms" in lignes["écoute"]["temps"] and "222 ms" in lignes["voix"]["temps"]
    assert "12.11.2026" in lignes["cerveau"]["temps"]
    vide = {l["piece"]: l for l in preuves.ou_tourne_quoi(tmp_path / "rien")}
    for piece in PIECES:
        assert vide[piece]["temps"] == "non mesuré" and vide[piece]["memoire"] == "non mesuré", piece


def test_preuve_8_la_machine_vient_des_reglages():
    lignes = {l["piece"]: l for l in preuves.ou_tourne_quoi(reglages={"cerveau": {"cascade": [
        {"nom": "apertus_8b", "url": "http://192.168.1.20:8089"}]}, "yeux": {"actif": False}})}
    assert "192.168.1.20" in lignes["cerveau"]["machine"] and "autre ordinateur" in lignes["cerveau"]["machine"]
    assert "éteints" in lignes["yeux"]["machine"]
    lignes = {l["piece"]: l for l in preuves.ou_tourne_quoi(reglages={"cerveau": {"cascade": [
        {"nom": "apertus_8b", "url": "http://127.0.0.1:8089"}]}, "yeux": {"actif": True}})}
    assert lignes["cerveau"]["machine"].startswith("cet ordinateur") and "éteints" not in lignes["yeux"]["machine"]


def test_aucune_promesse_non_mesuree_sur_les_pages_des_preuves(client):
    for lien in ("/clinique/preuves", "/clinique/ou-tourne-quoi", "/clinique/preuves/essais", "/clinique/preuves/brancher"):
        texte = html.unescape(client.get(lien).text).lower()
        for mot in ("compatible", "garanti", "toujours fiable", "100 %"):
            assert mot not in texte, (lien, mot)
