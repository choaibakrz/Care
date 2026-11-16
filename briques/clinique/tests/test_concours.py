"""La clinique en boîte — KC, la commande du concours (avenant 2, partie 6).

« Une nouvelle commande, à côté de la grande répétition et de la commande des preuves. Les sept contrôles, joués sur le faux
robot. La commande affiche une ligne par contrôle, avec son étiquette. Quand les sept existent : CONCOURS : RÉUSSI ou
CONCOURS : RATÉ — (ce qui manque). Mêmes garde-fous que la grande répétition : jamais « RÉUSSI » si un contrôle est sauté ;
une vérification casse exprès une pièce et contrôle que la commande dit bien « RATÉ ». Un contrôle dont la tâche est BLOQUÉ
compte comme raté. »
Ici : la version courte (un tirage au lieu de trois, une endurance de dix secondes au lieu d'une minute), et la ligne le dit.
Faux robot et robots simulés. Aucun vrai robot.
"""
from __future__ import annotations

import re

import pytest

from briques.clinique import concours

ETIQUETTES = ("RÉEL", "FAUX ROBOT", "SIMULÉ", "JOUÉ")


@pytest.fixture(scope="module")
def joue(tmp_path_factory):
    lignes: list[str] = []
    code = concours.jouer(ecrire=lignes.append, court=True, dossier=tmp_path_factory.mktemp("concours"))
    return code, lignes


def test_les_sept_controles_sont_joues_et_le_concours_reussit(joue):
    code, lignes = joue
    texte = "\n".join(lignes)
    assert code == 0 and lignes[-1] == "CONCOURS : RÉUSSI", texte
    for numero in range(1, 8):
        ligne = next((l for l in lignes if re.match(rf"\s*{numero}\. \[", l)), None)
        assert ligne is not None and "réussi" in ligne, (numero, texte)
        etiquette = re.search(r"\[([^\]]+)\]", ligne).group(1)
        assert all(e in ETIQUETTES for e in etiquette.split(" ET ")), ligne
        assert concours.CONTROLES[numero][0] in ligne


def test_chaque_ligne_dit_ce_qu_elle_a_vu_et_la_version_courte(joue):
    _, lignes = joue
    texte = "\n".join(lignes)
    assert "gestes interdits exécutés : 0" in texte and "1 tirage (version courte" in texte
    assert "avec une aide humaine" in texte and "aucun arrêt" in texte and "10 s (version courte" in texte
    assert "grisée à" in texte and "constaté : pas encore" in texte
    assert "deux choix" in texte and "annonce" in texte
    assert "aucune capacité dans la colonne du vrai robot sans essai réel" in texte
    assert "aucun avis d'essai ne reste" in texte
    assert re.search(r"remise à zéro la plus longue : [0-9.,]+ s", texte)


def test_un_controle_saute_ne_donne_jamais_reussi(tmp_path):
    controles = dict(concours.CONTROLES)
    del controles[5]
    lignes: list[str] = []
    code = concours.jouer(controles=controles, ecrire=lignes.append, court=True, dossier=tmp_path, seulement=(5, 6))
    assert code == 1 and lignes[-1].startswith("CONCOURS : RATÉ") and "5" in lignes[-1]


def test_une_piece_cassee_expres_donne_rate(monkeypatch, tmp_path):
    """Le gardien est cassé exprès pour le tirage : il ne retient plus les gestes interdits. Le contrôle 1 doit rater."""
    from briques.clinique import tirage

    vrai = tirage.jouer
    monkeypatch.setattr(tirage, "jouer", lambda numero, **k: {**vrai(numero, **k), "interdits_executes": 1})
    lignes: list[str] = []
    code = concours.jouer(ecrire=lignes.append, court=True, dossier=tmp_path, seulement=(1,))
    assert code == 1 and lignes[-1].startswith("CONCOURS : RATÉ") and "1" in lignes[-1]


def test_un_controle_dont_la_tache_est_bloquee_compte_comme_rate(tmp_path):
    lignes: list[str] = []
    suivi = "| K06 | L'avis des personnes | T28, J07 | BLOQUÉ (essai) | ... |\n"
    code = concours.jouer(ecrire=lignes.append, court=True, dossier=tmp_path, seulement=(6,), suivi=suivi)
    assert code == 1 and any("BLOQUÉ" in l and "K06" in l for l in lignes) and lignes[-1].startswith("CONCOURS : RATÉ")


def test_seulement_une_partie_ne_dit_jamais_concours_reussi(tmp_path):
    lignes: list[str] = []
    concours.jouer(ecrire=lignes.append, court=True, dossier=tmp_path, seulement=(6,))
    assert lignes[-1] != "CONCOURS : RÉUSSI" and "INCOMPLET" in lignes[-1]


def test_la_commande_est_dans_lancer_et_la_page_concours_la_cite():
    import lancer
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from briques.clinique.ecrans import brancher_ecrans

    assert "concours" in lancer.__doc__
    app = FastAPI()
    brancher_ecrans(app)
    assert "python3 lancer.py concours" in TestClient(app).get("/clinique/concours").text
