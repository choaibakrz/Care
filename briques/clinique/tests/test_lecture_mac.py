"""La clinique en boîte — R3, lire une image sur l'iMac (lecture de texte du Mac, autorisation B).

« Fini » veut dire :
- sur l'iMac, une image d'un texte tapé est lue, ligne par ligne, de haut en bas, avec une confiance par ligne ;
- le taux d'erreur de lecture est calculé (jamais tapé) ;
- une image absente ou illisible donne une erreur claire, pas un texte inventé ;
- rien n'est installé : l'outil est déjà dans le Mac ; ailleurs que sur un Mac, la pièce dit pourquoi elle ne sert pas.
Les essais qui lisent une image sont sautés sur une machine sans la lecture du Mac. Aucun vrai papier : des textes inventés.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from briques.clinique import lecture_mac

MAC, RAISON = lecture_mac.disponible()
sur_mac = pytest.mark.skipif(not MAC, reason=f"lecture du Mac indisponible : {RAISON}")
TEXTE = ("INVENTÉ — Studio medico Exemple, Dott. Exemple.\nLettera per la signora Giulia B.\n"
         "Numéro inventé : EX-0000-0012\nAucun nom sur cette feuille.")


def test_le_taux_d_erreur_est_un_calcul():
    assert lecture_mac.taux_d_erreur("Giulia B.", "Giulia B.") == 0.0
    assert lecture_mac.taux_d_erreur("Giulia  B.\n", "Giulia B.") == 0.0  # espaces et retours à la ligne comptés une fois
    assert lecture_mac.taux_d_erreur("Giulla B.", "Giulia B.") == round(1 / 9, 4)
    assert lecture_mac.taux_d_erreur("", "Giulia B.") == 1.0 and lecture_mac.taux_d_erreur("xxxxxxxxxxxxxxxxxxxx", "ab") == 1.0
    assert lecture_mac.taux_d_erreur("", "") == 0.0


def test_ailleurs_que_sur_un_mac_la_piece_dit_pourquoi(monkeypatch):
    monkeypatch.setattr(lecture_mac.sys, "platform", "linux")
    assert lecture_mac.disponible() == (False, "cet ordinateur n'est pas un Mac")
    with pytest.raises(lecture_mac.LectureImpossible, match="Mac"):
        lecture_mac.lire_image(__file__)
    assert lecture_mac.main(["--essai"]) == 2


def test_rien_n_est_installe_pour_lire():
    source = (Path(lecture_mac.__file__)).read_text(encoding="utf-8") + lecture_mac.SOURCE.read_text(encoding="utf-8")
    for interdit in ("pip install", "brew install", "http://", "https://", "URLSession", "curl"):
        assert interdit not in source, interdit
    assert "import Vision" in lecture_mac.SOURCE.read_text(encoding="utf-8")


@sur_mac
def test_une_image_d_un_texte_tape_est_lue_ligne_par_ligne_de_haut_en_bas(tmp_path):
    image = lecture_mac.dessiner_texte(TEXTE, tmp_path / "papier_invente.png")
    assert image.exists() and image.stat().st_size > 1000
    lu = lecture_mac.lire_image(image)
    assert lu["outil"] == "lecture de texte du Mac (Vision, macOS)"
    assert [l["texte"] for l in lu["lignes"]][0].startswith("INVENTÉ") and "feuille" in lu["lignes"][-1]["texte"]
    assert "Giulia B." in lu["texte"] and "EX-0000-0012" in lu["texte"]
    assert all(0 <= l["confiance"] <= 1 for l in lu["lignes"]) and lu["confiance_min"] is not None
    erreur = lecture_mac.taux_d_erreur(lu["texte"], TEXTE)
    assert erreur <= 0.05, (erreur, lu["texte"])  # un texte tapé, net, noir sur blanc : presque parfait


@sur_mac
def test_une_image_absente_ou_illisible_donne_une_erreur_claire(tmp_path):
    with pytest.raises(lecture_mac.LectureImpossible, match="absente"):
        lecture_mac.lire_image(tmp_path / "rien.png")
    faux = tmp_path / "pas_une_image.png"
    faux.write_text("ceci n'est pas une image", encoding="utf-8")
    with pytest.raises(lecture_mac.LectureImpossible, match="illisible"):
        lecture_mac.lire_image(faux)


@sur_mac
def test_la_commande_d_essai_mesure_et_affiche_le_taux_d_erreur(capsys):
    assert lecture_mac.main(["--essai"]) == 0
    sortie = capsys.readouterr().out
    assert "taux d'erreur de lecture : " in sortie and "%" in sortie and "texte inventé" in sortie
    assert "pas écrit à la main" in sortie
