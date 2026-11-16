"""La clinique en boîte — R4, l'écoute sur l'iMac : le modèle d'écoute, et un essai avec une vraie voix du dépôt.

« Fini » veut dire :
- le modèle d'écoute est sur l'ordinateur, et c'est le bon fichier (taille du catalogue) ;
- une vraie voix du dépôt est écoutée et le texte rendu ressemble à la phrase de référence ;
- le taux d'erreur de la voix, par langue, est un calcul, et la fiche de vérité l'affiche ;
- sans modèle ou sans outil, la pièce dit pourquoi, et la fiche dit « non mesuré ».
Les essais qui écoutent sont sautés là où le modèle ou l'outil manquent. Aucune voix de la clinique : les phrases FLEURS.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from briques.clinique import ecoute, fiche

LA, RAISON = ecoute.disponible()
avec_ecoute = pytest.mark.skipif(not LA, reason=f"écoute indisponible : {RAISON}")


def test_le_taux_d_erreur_par_mot_est_un_calcul():
    assert ecoute.taux_d_erreur_mots("La sonnette, c'est fait.", "la sonnette c'est fait") == 0.0  # ni ponctuation ni majuscules
    assert ecoute.taux_d_erreur_mots("ben oltre a giornata", "ben oltre la giornata") == 0.25
    assert ecoute.taux_d_erreur_mots("", "un deux trois") == 1.0 and ecoute.taux_d_erreur_mots("a b c d e f g", "x") == 1.0
    assert ecoute.taux_d_erreur_mots("", "") == 0.0


def test_la_mesure_compte_par_langue_avec_ce_que_l_ecoute_rend(tmp_path):
    def fausse_ecoute(son, langue):  # tout est bien entendu, sauf un mot par phrase en italien
        reference = next(p["texte"] for p in ecoute.phrases(langue) if p["son"] == son)
        texte = reference if langue != "it" else "XXX " + reference.split(" ", 1)[1]
        return {"texte": texte, "duree_s": 1.0}

    bilan = ecoute.mesurer(("fr", "it"), par_langue=2, noter=tmp_path / "m.json", ecouter_un=fausse_ecoute)
    assert bilan["par_langue"]["fr"] == {**bilan["par_langue"]["fr"], "phrases": 2, "taux_d_erreur": 0.0}
    it = bilan["par_langue"]["it"]
    assert it["phrases"] == 2 and it["taux_d_erreur"] == round(2 / it["mots"], 4) and len(it["exemples_d_erreurs"]) == 2
    assert json.loads((tmp_path / "m.json").read_text(encoding="utf-8"))["par_langue"]["it"]["taux_d_erreur"] == it["taux_d_erreur"]
    assert "pas des phrases de la clinique" in bilan["marque"]


def test_la_fiche_affiche_le_taux_par_langue_ou_non_mesure(tmp_path):
    ligne = fiche.ligne_de_la_voix(tmp_path / "rien.json")[0]
    assert ligne["titre"] == "Taux d'erreur de la voix, par langue" and ligne["valeur"].startswith("non mesuré")
    (tmp_path / "m.json").write_text(json.dumps({"outil": "whisper.cpp", "date": "2026-11-12T05:10:00", "par_langue": {
        "fr": {"phrases": 12, "taux_d_erreur": 0.081}, "it": {"phrases": 12, "taux_d_erreur": 0.05}}}), encoding="utf-8")
    valeur = fiche.ligne_de_la_voix(tmp_path / "m.json")[0]["valeur"]
    assert "fr 8.1 %" in valeur and "it 5.0 %" in valeur and "12 vraies voix par langue" in valeur
    assert "pas des phrases de la clinique" in valeur and "12.11.2026" in valeur


def test_sans_modele_la_piece_dit_pourquoi(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(ecoute, "MODELE", tmp_path / "absent.bin")
    oui, raison = ecoute.disponible()
    assert oui is False and ("modèle" in raison or "whisper-cli" in raison)
    with pytest.raises(ecoute.EcouteImpossible):
        ecoute.ecouter(__file__)
    assert ecoute.main([]) == 2 and "indisponible" in capsys.readouterr().out


def test_la_commande_est_dans_lancer_et_les_voix_du_depot_sont_la():
    assert '"ecoute-mesure"' in (Path(__file__).resolve().parents[3] / "lancer.py").read_text(encoding="utf-8")
    for langue in ecoute.LANGUES:
        assert len(ecoute.phrases(langue)) == 12, langue


@avec_ecoute
def test_le_modele_d_ecoute_est_le_bon_fichier():
    assert ecoute.MODELE.stat().st_size == 487601967  # la taille écrite dans outils/catalogue.yaml


@avec_ecoute
def test_une_vraie_voix_du_depot_est_ecoutee():
    phrase = ecoute.phrases("it")[0]
    entendu = ecoute.ecouter(phrase["son"], "it")
    assert entendu["outil"].startswith("whisper.cpp") and entendu["texte"]
    assert ecoute.taux_d_erreur_mots(entendu["texte"], phrase["texte"]) <= 0.25, entendu["texte"]
    with pytest.raises(ecoute.EcouteImpossible, match="absent"):
        ecoute.ecouter("pas_de_son.wav", "it")
