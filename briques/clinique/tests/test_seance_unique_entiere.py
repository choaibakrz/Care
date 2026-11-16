"""La clinique en boîte — N03b, la répétition « d'un seul trait » : les sept scènes dans la même séance (Q14, Q20).

« Une répétition d'un seul trait, les sept scènes dans une seule séance, sans repartir d'une clinique neuve, avec la durée
mesurée et affichée. » Jouée par le chef de démonstration (brique 15), avec l'étape « contrôle » (H05).
« Fini » veut dire :
- les quatorze étapes, sur UNE clinique, UN faux robot, UNE horloge : rien d'autre n'est monté pendant la séance ;
- ce qu'une scène laisse sert à la suivante : les questions du soir (étape 9) arrivent dans le résumé du lendemain
  (étape 10) ; la panne de l'étape 12 est reprise par le faux robot de la même séance ;
- la fiche de vérité (13) est calculée sur CETTE séance ; « rien n'est sorti de l'ordinateur » (14) est surveillé depuis
  le début de la séance ;
- la durée de chaque scène et de toute la séance est mesurée et affichée.
Faux robot et robots simulés. Arrivée et questions tapées, pas dites.
"""
from __future__ import annotations

import re

import pytest

from briques.clinique import seance_unique


@pytest.fixture(scope="module")
def jouee(tmp_path_factory):
    lignes: list[str] = []
    bilan = seance_unique.jouer(ecrire=lignes.append, dossier=tmp_path_factory.mktemp("seance"), acceleration=20.0,
                                scenes=tuple(range(1, 8)))
    return bilan, lignes


def test_les_sept_scenes_et_les_quatorze_etapes_reussissent_dans_une_seule_seance(jouee):
    bilan, lignes = jouee
    texte = "\n".join(lignes)
    assert bilan["reussi"], texte
    assert [e["etape"] for e in bilan["etapes"]] == list(range(1, 15))
    assert all(e["resultat"] == "reussie" for e in bilan["etapes"]), texte
    assert bilan["annonces"] == 7 and bilan["cliniques"] == 1 and bilan["robots"] == 1 and bilan["horloges"] == 1
    assert lignes[-1] == "SÉANCE UNIQUE (scènes 1 à 7) : RÉUSSIE"
    assert "N03b" not in texte  # plus rien à faire plus tard


def test_ce_qu_une_scene_laisse_sert_a_la_suivante(jouee):
    bilan, _ = jouee
    detail = {e["etape"]: e["detail"] for e in bilan["etapes"]}
    assert "les deux questions de l'étape 9" in detail[10]
    assert "R3" in detail[12] and "R1" in detail[12] and "livrée" in detail[12]
    assert "cette séance" in detail[13] and "0 essai de connexion vers l'extérieur" in detail[14]
    assert bilan["heures"] == sorted(bilan["heures"], key=lambda h: (int(h.split("-")[0]), h.split("-")[1]))


def test_la_duree_de_chaque_scene_et_de_la_seance_est_affichee(jouee):
    _, lignes = jouee
    texte = "\n".join(lignes)
    for n in range(1, 8):
        assert re.search(rf"scène {n} — .* : \d+(,\d)? s", texte), n
    assert re.search(r"durée de la séance : \d+(,\d)? s", texte)


def test_la_fiche_de_l_equipe_n_est_pas_remplacee(jouee):
    from briques.clinique import fiche

    gardee = fiche.derniere()
    assert gardee is None or "séance unique" not in str(gardee)  # la page montre la dernière RÉPÉTITION, pas cette séance
