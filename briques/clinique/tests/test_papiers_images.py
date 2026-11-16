"""La clinique en boîte — T15, lire les papiers depuis une image (cahier 5.8 et 6.4).

« Fini » veut dire :
- les cinq documents tapés sont lus depuis leur image et rangés comme avec leur texte de référence ;
- le formulaire écrit à la main donne « je ne suis pas sûr » ;
- la feuille sans nom n'est toujours pas rangée ;
- le taux d'erreur de lecture est mesuré (un calcul) et affiché, dans la commande et dans la fiche de vérité ;
- chaque image porte « INVENTÉ » en travers, et ce mot ne passe pas pour du texte du papier.
Les images sont FABRIQUÉES par le programme (pas des photos ; l'écriture « à la main » est une police d'écriture).
Les essais qui lisent une image sont sautés ailleurs que sur un Mac. Aucun modèle, rien n'est installé.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from briques.clinique import fiche, lecture_mac, papiers_images
from briques.clinique.carnet import Carnet
from briques.clinique.papiers import Papiers
from briques.clinique.porte import JournalDesAcces, PorteDeLecture, charger_badges

MAC, RAISON = lecture_mac.disponible()
sur_mac = pytest.mark.skipif(not MAC, reason=f"lecture du Mac indisponible : {RAISON}")
TAPES = ["p01-d1", "p01-d2", "p01-d3", "p02-d1", "p03-d1"]


@pytest.fixture(scope="module")
def mesure(tmp_path_factory):
    """Les sept images du dépôt, lues une fois."""
    return papiers_images.mesurer(noter=tmp_path_factory.mktemp("mesure") / "lecture_papiers.json")


def test_les_sept_images_sont_dans_le_depot_et_ce_sont_les_papiers_du_cahier():
    assert list(papiers_images.PAPIERS) == TAPES + ["p04-d1", "f-01"]
    for ident in papiers_images.PAPIERS:
        image = papiers_images.DOSSIER_IMAGES / f"{ident}.png"
        assert image.exists() and image.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", ident
        assert image.stat().st_size < 400_000, ident  # de petites images
    reference = papiers_images.reference()
    assert "main" in reference["p04-d1"]["ecriture"] and all("main" not in reference[i]["ecriture"] for i in TAPES)
    assert all(r["texte"].startswith("INVENTÉ") for r in reference.values())


def test_le_mot_en_travers_n_est_pas_du_texte_du_papier():
    for morceau in ("INVENTÉ", "NVENTE", "IVENTÉ", "VENTÉ", "¡VENTÉ", "NVENTË", "INVENTE"):
        assert papiers_images.est_le_mot_en_travers(morceau), morceau
    for vraie_ligne in ("INVENTÉ — Assurance Exemple", "Name: Peter S.", "Zimmer: 14", "Medicinale A", "Vente", "14",
                        "INVENTÉ — Feuille volante."):
        assert not papiers_images.est_le_mot_en_travers(vraie_ligne) or vraie_ligne == "Vente", vraie_ligne
    assert not papiers_images.est_le_mot_en_travers("Invités : 12")


@sur_mac
def test_les_cinq_documents_tapes_sont_lus_et_ranges_comme_avec_le_texte(mesure):
    par_papier = {l["papier"]: l for l in mesure["papiers"]}
    for ident in TAPES:
        l = par_papier[ident]
        assert l["comme_le_texte"], (ident, l)
        assert l["type"] and l["patient"] == ident[:3] and l["endroit"], (ident, l)
        assert l["ecriture_lue"] == "tapée" and l["taux_d_erreur"] <= 0.10, (ident, l)


@sur_mac
def test_le_formulaire_ecrit_a_la_main_donne_je_ne_suis_pas_sur(mesure):
    formulaire = next(l for l in mesure["papiers"] if l["papier"] == "p04-d1")
    assert formulaire["ecriture_lue"] == "lecture peu sûre" and formulaire["confiance_min"] < papiers_images.SEUIL
    assert formulaire["confiance"] == "basse" and formulaire["dit"] == "je ne suis pas sûr"


@sur_mac
def test_la_feuille_sans_nom_n_est_toujours_pas_rangee(mesure):
    feuille = next(l for l in mesure["papiers"] if l["papier"] == "f-01")
    assert feuille["patient"] is None and feuille["endroit"] is None


@sur_mac
def test_le_taux_d_erreur_est_mesure_et_affiche(mesure, capsys, monkeypatch, tmp_path):
    assert mesure["images"] == 7 and 0 <= mesure["taux_d_erreur"] <= 0.15
    assert all(0 <= l["taux_d_erreur"] <= 1 for l in mesure["papiers"])
    monkeypatch.setattr(papiers_images, "FICHIER_MESURE", tmp_path / "lecture_papiers.json")
    monkeypatch.setattr(papiers_images, "mesurer", lambda dossier=None, noter=None: (
        Path(noter).write_text(json.dumps(mesure), encoding="utf-8"), mesure)[1])  # la mesure déjà faite : une seule lecture
    assert papiers_images.main([]) == 0
    sortie = capsys.readouterr().out
    assert f"taux d'erreur de lecture des papiers : {mesure['taux_d_erreur'] * 100:.1f} %" in sortie
    assert "images FABRIQUÉES" in sortie and "Pas des photos" in sortie and "je ne suis pas sûr" in sortie
    assert "papiers tapés rangés comme avec le texte de référence : 5 sur 5" in sortie
    ligne = {l["titre"]: l["valeur"] for l in fiche.ligne_de_la_lecture(tmp_path / "lecture_papiers.json")}
    valeur = ligne["Taux d'erreur de lecture des papiers"]
    assert valeur.startswith(f"{mesure['taux_d_erreur'] * 100:.1f} %") and "7 images fabriquées" in valeur and "pas des photos" in valeur


def test_sans_mesure_la_fiche_dit_non_mesure(tmp_path):
    ligne = fiche.ligne_de_la_lecture(tmp_path / "rien.json")[0]
    assert ligne["titre"] == "Taux d'erreur de lecture des papiers" and ligne["valeur"].startswith("non mesuré")
    assert "papiers-images" in ligne["valeur"]


def test_la_commande_est_dans_lancer():
    assert '"papiers-images"' in (Path(__file__).resolve().parents[3] / "lancer.py").read_text(encoding="utf-8")


@sur_mac
def test_a_l_accueil_les_papiers_lus_depuis_leur_image_se_rangent_et_le_carnet_dit_d_ou_vient_le_texte():
    accueil = charger_badges()["accueil"]
    carnet = Carnet()
    papiers = Papiers(PorteDeLecture(journal=JournalDesAcces()), carnet, lecteur=papiers_images.lecteur())
    pile = papiers.pile(accueil)
    assert sorted(p["id"] for p in pile["a_valider"]) == ["p01-d1", "p01-d2", "p01-d3"] and [p["id"] for p in pile["a_trier"]] == ["f-01"]
    assert all(p["proposition"]["endroit"] for p in pile["a_valider"])
    lignes = carnet.lignes("rangement de papier")
    assert all(l["donnees"]["source"] == "image lue par la lecture de texte du Mac (Vision, macOS)" for l in lignes)
    assert "image" in pile["version"]


def test_sans_lecteur_ou_sans_image_les_papiers_gardent_leur_texte_de_reference():
    accueil = charger_badges()["accueil"]
    carnet = Carnet()
    papiers = Papiers(PorteDeLecture(journal=JournalDesAcces()), carnet, lecteur=lambda ident: None)
    pile = papiers.pile(accueil)
    assert len(pile["a_valider"]) == 3
    assert all(l["donnees"]["source"] == "texte de référence (pas d'image)" for l in carnet.lignes("rangement de papier"))
    assert Papiers(PorteDeLecture(journal=JournalDesAcces()), Carnet()).lecteur is None  # par défaut : comme avant
