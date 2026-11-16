"""La clinique en boîte — T01, le squelette. Internet coupé (conftest.py), aucun modèle.

On vérifie : la grande répétition a ses quatorze étapes ; elle ne dit jamais « RÉUSSIE » si une étape manque, rate
ou est sautée ; la vérification rapide finit par sa ligne de bilan ; la liste des essais longs ne cite que des essais
qui existent ; les deux commandes sont dans lancer.py.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from briques.clinique import repetition, verif_rapide
from briques.clinique.tests.la_vraie_repetition import la_vraie_repetition  # noqa: F401 (une aide d'essai)

RACINE = Path(__file__).resolve().parents[3]


def _ok(etiquette="FAUX ROBOT"):
    return lambda: repetition.Resultat(True, etiquette, "essai")


def _tout_ok():
    return {e.numero: _ok() for e in repetition.ETAPES}


def _jouer(controles):
    lignes: list[str] = []
    code = repetition.jouer(controles, ecrire=lignes.append)
    return code, lignes


def test_les_quatorze_etapes_du_cahier():
    assert [e.numero for e in repetition.ETAPES] == list(range(1, 15))
    assert "italien" in repetition.ETAPES[0].titre
    assert "rien envoyé hors de l'ordinateur" in repetition.ETAPES[13].titre
    assert all(e.titre and e.piece for e in repetition.ETAPES)


def test_rien_de_construit_quatorze_etapes_manquantes():
    code, lignes = _jouer({})
    assert code == 1
    assert lignes[-1] == "RÉPÉTITION : RATÉE — 14 étapes manquantes"
    assert len([l for l in lignes if "pas encore construite" in l]) == 14


def test_une_ligne_par_etape_avec_son_etiquette():
    code, lignes = _jouer(_tout_ok())
    etapes = [l for l in lignes if re.match(r"\s*\d+\. ", l)]
    assert len(etapes) == 14 and all("[FAUX ROBOT]" in l for l in etapes)
    assert code == 0 and lignes[-1] == "RÉPÉTITION : RÉUSSIE"


def test_une_piece_cassee_expres_la_repetition_dit_ratee():
    controles = _tout_ok()

    def cassee():
        raise RuntimeError("pièce cassée exprès")

    controles[7] = cassee
    code, lignes = _jouer(controles)
    assert code == 1 and lignes[-1].startswith("RÉPÉTITION : RATÉE — ")
    assert "7" in lignes[-1] and "RÉUSSIE" not in lignes[-1]
    assert any("pièce cassée exprès" in l for l in lignes)


def test_une_etape_qui_repond_non_la_repetition_dit_ratee():
    controles = _tout_ok()
    controles[3] = lambda: repetition.Resultat(False, "FAUX ROBOT", "l'étage n'a rien reçu")
    code, lignes = _jouer(controles)
    assert code == 1 and "étape ratée : 3" in lignes[-1]


def test_une_etape_sautee_ne_donne_jamais_reussie():
    for reponse in (None, True, "ok", repetition.Resultat(True, "", "sans étiquette")):
        controles = _tout_ok()
        controles[12] = lambda r=reponse: r
        code, lignes = _jouer(controles)
        assert code == 1 and lignes[-1].startswith("RÉPÉTITION : RATÉE — "), reponse


def test_une_etiquette_inconnue_est_refusee():
    controles = _tout_ok()
    controles[1] = _ok("VRAI DE VRAI")
    code, lignes = _jouer(controles)
    assert code == 1


def test_l_etat_reel_ne_triche_pas():
    """Avec les vraies pièces du dépôt : « RÉUSSIE » seulement si les quatorze étapes ont une pièce."""
    code, lignes = _jouer(repetition.CONTROLES)
    manquantes = [e for e in repetition.ETAPES if e.numero not in repetition.CONTROLES]
    if manquantes:
        assert code == 1 and lignes[-1].startswith("RÉPÉTITION : RATÉE — ")
        assert f"{len(manquantes)} étape" in lignes[-1]


def test_la_commande_repetition_tourne(la_vraie_repetition):
    sortie = la_vraie_repetition  # la même commande, lancée une seule fois pour tous les essais (la_vraie_repetition.py)
    derniere = sortie.stdout.strip().splitlines()[-1]
    assert derniere.startswith("RÉPÉTITION : ")
    assert (sortie.returncode == 0) == (derniere == "RÉPÉTITION : RÉUSSIE")


def test_le_bilan_de_la_verification_rapide():
    b = verif_rapide.lire_bilan("709 passed, 30 skipped, 34 deselected in 80.10s (0:01:20)")
    assert (b.reussies, b.ratees, b.sautees, b.laissees) == (709, 0, 30, 34)
    assert verif_rapide.ligne_finale(b) == "VÉRIFICATION RAPIDE : 709 réussies, 0 ratée"
    b = verif_rapide.lire_bilan("3 failed, 700 passed, 2 errors in 9.00s")
    assert b.ratees == 5
    assert verif_rapide.ligne_finale(b) == "VÉRIFICATION RAPIDE : 700 réussies, 5 ratées"
    b = verif_rapide.lire_bilan("1 failed, 1 passed in 0.10s")
    assert verif_rapide.ligne_finale(b) == "VÉRIFICATION RAPIDE : 1 réussie, 1 ratée"


def test_sans_bilan_la_verification_rapide_est_ratee():
    b = verif_rapide.lire_bilan("Traceback (most recent call last): ...")
    assert b.ratees >= 1 and b.reussies == 0


def test_les_essais_longs_existent_tous():
    essais = verif_rapide.essais_longs()
    assert essais, "la liste des essais longs est vide"
    for essai in essais:
        fichier, nom = essai.split("::", 1)
        chemin = RACINE / fichier
        assert chemin.exists(), essai
        assert f"def {nom.split('[')[0]}(" in chemin.read_text(encoding="utf-8"), essai
        assert not fichier.startswith("briques/clinique/"), "les essais de la clinique restent dans la vérification rapide"


def test_les_deux_commandes_sont_dans_lancer():
    texte = (RACINE / "lancer.py").read_text(encoding="utf-8")
    assert '"verif-rapide"' in texte and '"repetition"' in texte
