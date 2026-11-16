"""La clinique en boîte — N03a, la répétition « d'un seul trait », jouée par le chef de démonstration (scènes 1 à 3).

Réponse de Hiba à Q14 : « une répétition d'un seul trait, les sept scènes dans une seule séance, sans repartir d'une
clinique neuve, avec la durée mesurée et affichée. » Et à Q20 : « puis fais jouer N03 par le chef de démonstration ».
N03 est coupée en deux. N03a : la séance unique et les scènes 1 à 3 (étapes 1 à 8). N03b : les scènes 4 à 7.
« Fini » veut dire, pour N03a :
- une seule clinique, un seul faux robot, une seule horloge, du début à la fin : l'étape 3 voit le message laissé par
  l'arrivée de l'étape 1 ; l'étape 8 trouve la liste cochée à l'étape 7 ; l'horloge avance de scène en scène ;
- le chef de démonstration (brique 15) joue la partition : une annonce par scène, une étape « contrôle » par étape ;
- la durée de chaque étape et de la séance est mesurée et affichée ;
- la commande le dit : les scènes 4 à 7 ne sont pas encore dans la séance unique.
Faux robot. Aucun vrai robot. Arrivée tapée, pas dite.
"""
from __future__ import annotations

import re

import pytest

from briques.clinique import seance_unique


@pytest.fixture(scope="module")
def jouee(tmp_path_factory):
    lignes: list[str] = []
    bilan = seance_unique.jouer(ecrire=lignes.append, dossier=tmp_path_factory.mktemp("seance"), acceleration=20.0)
    return bilan, lignes


def test_le_chef_de_demonstration_joue_les_scenes_1_a_3_et_tout_reussit(jouee):
    bilan, lignes = jouee
    texte = "\n".join(lignes)
    assert bilan["reussi"], texte
    assert [e["etape"] for e in bilan["etapes"]] == list(range(1, 9))
    assert all(e["resultat"] == "reussie" for e in bilan["etapes"]), texte
    assert bilan["chef"] == "brique 15" and bilan["annonces"] == 3  # une annonce par scène, dite par le chef
    assert "SÉANCE UNIQUE (scènes 1 à 3) : RÉUSSIE" in lignes[-1]


def test_une_seule_clinique_du_debut_a_la_fin(jouee):
    bilan, _ = jouee
    assert bilan["cliniques"] == 1 and bilan["robots"] == 1 and bilan["horloges"] == 1
    detail = {e["etape"]: e["detail"] for e in bilan["etapes"]}
    assert "laissé par l'arrivée de l'étape 1" in detail[3]
    assert "la liste de l'étape 7" in detail[8] and "livrée" in detail[8]
    assert bilan["heures"][0] < bilan["heures"][-1]  # l'horloge du scénario a avancé de scène en scène


def test_la_duree_est_mesuree_et_affichee(jouee):
    bilan, lignes = jouee
    texte = "\n".join(lignes)
    assert bilan["duree_s"] > 0 and all(e["duree_s"] >= 0 for e in bilan["etapes"])
    assert re.search(r"durée de la séance : \d+(,\d)? s", texte)
    assert re.search(r"scène 1 .* : \d+(,\d)? s", texte) and "faux robot accéléré 20 fois" in texte


def test_la_commande_dit_ce_qui_n_est_pas_encore_dans_la_seance_unique(jouee):
    _, lignes = jouee
    assert any("scènes 4 à 7" in l and "N03b" in l for l in lignes)


def test_rien_n_est_ecrit_hors_du_dossier_donne(jouee, tmp_path):
    from faux_logiciel_admin.logiciel import DOSSIER_DEFAUT

    assert not list(DOSSIER_DEFAUT.glob("du_logiciel_vers_nous/*.hl7"))


def test_la_commande_est_dans_lancer():
    import lancer

    assert "seance-unique" in lancer.__doc__
