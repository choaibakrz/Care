"""H20 — Mesurer l'interprète avec un plus gros modèle d'écoute, à côté de « small » (réponse de Hiba à Q27 : B ;
« medium complet (1,53 Go) » à Q30).

    python3 lancer.py interprete-mesure --modele medium

« Fini » veut dire : on choisit le modèle par son nom ; « small » reste le choix par défaut (rien ne change sans le
dire) ; un modèle absent donne une phrase claire, pas un plantage ; la mesure « medium » s'écrit dans son propre
fichier, à côté de celle de « small » ; la mémoire libre au plus bas est notée (Q22).
"""
from __future__ import annotations

import pytest

from briques.clinique import ecoute, interprete


def test_small_reste_le_choix_par_defaut():
    assert interprete.MODELES["small"] == ecoute.MODELE
    assert interprete.fichier_de_mesure("small") == interprete.FICHIER_MESURE


def test_medium_est_le_fichier_du_catalogue_et_sa_mesure_a_son_propre_fichier():
    assert interprete.MODELES["medium"].name == "ggml-medium.bin"
    assert interprete.fichier_de_mesure("medium").name == "MESURE_INTERPRETE_MEDIUM.md"
    assert interprete.fichier_de_mesure("medium") != interprete.FICHIER_MESURE


def test_un_modele_inconnu_ou_absent_est_dit_clairement(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="inconnu"):
        interprete.choisir_modele("géant")
    monkeypatch.setitem(interprete.MODELES, "medium", tmp_path / "absent.bin")
    with pytest.raises(ecoute.EcouteImpossible, match="absent"):
        interprete.choisir_modele("medium")


def test_le_modele_choisi_est_celui_qu_utilise_l_ecoute_puis_on_remet_small(tmp_path, monkeypatch):
    faux = tmp_path / "ggml-medium.bin"
    faux.write_bytes(b"x")
    monkeypatch.setitem(interprete.MODELES, "medium", faux)
    avant = ecoute.MODELE
    with interprete.avec_le_modele("medium"):
        assert ecoute.MODELE == faux
    assert ecoute.MODELE == avant


def test_on_remet_le_modele_d_avant_meme_si_la_mesure_plante(tmp_path, monkeypatch):
    faux = tmp_path / "ggml-medium.bin"
    faux.write_bytes(b"x")
    monkeypatch.setitem(interprete.MODELES, "medium", faux)
    avant = (ecoute.MODELE, ecoute.OUTIL)
    with pytest.raises(RuntimeError):
        with interprete.avec_le_modele("medium"):
            assert "medium" in ecoute.OUTIL  # le nom de l'outil suit le modèle
            raise RuntimeError("panne au milieu")
    assert (ecoute.MODELE, ecoute.OUTIL) == avant


def test_la_memoire_garde_le_plus_bas_des_lectures(monkeypatch):
    import psutil

    lues = iter([5.0, 3.0, 4.0, 2.5, 6.0] + [6.0] * 1000)

    class Memoire:
        def __init__(self, go):
            self.available = go * 1e9

    monkeypatch.setattr(psutil, "virtual_memory", lambda: Memoire(next(lues)))
    import time

    with interprete.SuiviMemoire(pas_s=0.01) as suivi:
        time.sleep(0.2)
    assert suivi.plus_bas_go == pytest.approx(2.5)


def test_la_commande_choisit_small_par_defaut_et_ecrit_le_bon_fichier(tmp_path, monkeypatch, capsys):
    vus = []
    monkeypatch.setattr(interprete, "_mesurer_tout", lambda nom, *a: (vus.append(nom) or (0, [f"mesure {nom}"])))
    for nom in ("small", "medium"):
        faux = tmp_path / f"ggml-{nom}.bin"
        faux.write_bytes(b"x")
        monkeypatch.setitem(interprete.MODELES, nom, faux)
    monkeypatch.setattr(interprete, "FICHIER_MESURE", tmp_path / "MESURE_INTERPRETE.md")
    monkeypatch.setattr(interprete, "RACINE", tmp_path)
    assert interprete.main([]) == 0 and interprete.main(["--modele", "medium"]) == 0
    assert vus == ["small", "medium"]
    assert "« small »" in (tmp_path / "MESURE_INTERPRETE.md").read_text(encoding="utf-8")
    assert "« medium »" in (tmp_path / "MESURE_INTERPRETE_MEDIUM.md").read_text(encoding="utf-8")
    assert "pas la mémoire du modèle d'écoute seul" in (tmp_path / "MESURE_INTERPRETE_MEDIUM.md").read_text(encoding="utf-8")


def test_un_modele_absent_rend_2_sans_ecrire_de_fichier(tmp_path, monkeypatch):
    monkeypatch.setitem(interprete.MODELES, "medium", tmp_path / "absent.bin")
    monkeypatch.setattr(interprete, "RACINE", tmp_path)
    assert interprete.main(["--modele", "medium"]) == 2
    assert not (tmp_path / "MESURE_INTERPRETE_MEDIUM.md").exists()
