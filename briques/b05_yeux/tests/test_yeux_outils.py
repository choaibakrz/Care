"""Brique 5 — les vrais outils (OpenCV/ArUco, RapidOCR, MediaPipe) sur des images FABRIQUÉES ici (marqueurs générés,
texte écrit, image dessinée par la caméra simulée). Chaque test saute proprement si son paquet manque.
Aucune image téléchargée. Mesuré sur Linux seulement.
"""
from __future__ import annotations

import time

import numpy as np
import pytest

from briques.b05_yeux.branchements import fabriquer
from briques.b05_yeux.camera_simulee import CameraSimulee
from briques.b05_yeux.geometrie import Calibration, appliquer, calibrer
from briques.b05_yeux.marqueurs import ListeMarqueurs, imprimer
from briques.b05_yeux.prise_yeux import ImageCamera, Yeux
from commun.monde import Monde

from aides_yeux import OPENCV, RAPIDOCR, etat_simule

MONDE = Monde.charger()
MARQUEURS = ListeMarqueurs.charger()
sans_opencv = pytest.mark.skipif(not OPENCV, reason="OpenCV absent (pip install --no-deps -r requirements-yeux.txt)")
sans_rapidocr = pytest.mark.skipif(not (OPENCV and RAPIDOCR), reason="RapidOCR absent (requirements-yeux.txt)")


def test_le_fichier_des_marqueurs_est_juste():
    assert MARQUEURS.verifier() == []
    assert MARQUEURS.sorte(10) == ("lieu", "cuisine") and MARQUEURS.sorte(0) == ("calibration", None)
    assert MARQUEURS.sorte(30) == ("objet", "bouteille") and MARQUEURS.sorte(49) == ("inconnu", None)
    lieux = {m.lieu for m in MARQUEURS.lieux}
    assert lieux <= {l.id for l in MONDE.lieux}, "un marqueur parle d'un lieu absent de monde.yaml"
    assert {m.objet for m in MARQUEURS.objets} <= {o.id for o in MONDE.objets}


def test_un_numero_en_double_est_refuse(tmp_path):
    f = tmp_path / "m.yaml"
    f.write_text("dictionnaire: DICT_4X4_50\ncalibration: {numeros: [0]}\nlieux: [{numero: 0, lieu: cuisine, taille_m: 0.3}]\n")
    with pytest.raises(ValueError, match="double"):
        ListeMarqueurs.charger(f)


@sans_opencv
def test_aruco_retrouve_un_marqueur_genere_et_sait_ce_que_c_est():
    from briques.b05_yeux.marqueurs import image_marqueur

    img = np.full((300, 400), 200, np.uint8)
    m = image_marqueur(10, cote_px=120)
    img[50:50 + m.shape[0], 120:120 + m.shape[1]] = m
    rgb = np.repeat(img[:, :, None], 3, axis=2)
    vue = Yeux(fabriquer(["aruco"], MONDE, MARQUEURS)).voir(ImageCamera(pixels=rgb, heure=time.monotonic(), source="test"))
    assert vue.etat("aruco").etat == "ok"
    assert [(k.numero, k.sorte, k.nom) for k in vue.marqueurs] == [(10, "lieu", "cuisine")]
    coins = np.asarray(vue.marqueurs[0].coins)
    marge = m.shape[0] / 8  # une case de marge blanche
    assert np.allclose(coins[0], (120 + marge, 50 + marge), atol=1.5)  # premier coin = haut-gauche du carré noir


@sans_opencv
@pytest.mark.parametrize("genre", ["humanoide", "chien", "bras"])
def test_calibrer_avec_trois_marqueurs_au_sol_comme_samedi(genre):
    """La caméra simulée dessine 3 marqueurs posés au sol à des places connues ; OpenCV les retrouve ; on compare la
    calibration obtenue à la vraie (connue parce que la caméra est simulée). Mesuré : 1 à 3 cm d'erreur jusqu'à 3 m."""
    cam = CameraSimulee(MONDE, genre=genre)
    places = cam.placements_de_calibration(MARQUEURS.calibration.numeros, MARQUEURS.calibration.taille_m)
    image = cam.image_de_calibration(places)
    vue = Yeux(fabriquer(["aruco"], MONDE, MARQUEURS)).voir(image)
    assert {m.numero for m in vue.marqueurs} == {0, 1, 2}
    cal = calibrer(vue.marqueurs, places, image.largeur, image.hauteur)
    assert cal.erreur_m is not None and cal.erreur_m < 0.02
    pixels = [(u, v) for u in np.linspace(20, 300, 10) for v in np.linspace(60, 235, 10)]
    a, ok_a = appliquer(cal.matrice(), pixels)
    b, ok_b = appliquer(cam.homographie_exacte(), pixels)
    ok = ok_a & ok_b
    proches = np.hypot(*b[ok].T) < 3.0
    erreurs = np.hypot(*(a[ok] - b[ok]).T)[proches]
    assert erreurs.mean() < 0.03 and erreurs.max() < 0.15, (erreurs.mean(), erreurs.max())


@sans_opencv
def test_un_seul_marqueur_suffit_mais_sans_controle_d_erreur():
    cam = CameraSimulee(MONDE)
    places = cam.placements_de_calibration([0], 0.28)
    image = cam.image_de_calibration(places)
    vue = Yeux(fabriquer(["aruco"], MONDE, MARQUEURS)).voir(image)
    cal = calibrer(vue.marqueurs, places, image.largeur, image.hauteur)
    assert cal.erreur_m is None and cal.vers_sol(160, 200) is not None
    with pytest.raises(ValueError, match="Aucun marqueur"):
        calibrer([], places, 320, 240)


@sans_opencv
def test_les_marqueurs_des_lieux_sont_vus_et_mis_au_sol_dans_le_faux_monde():
    """Le robot près de la cuisine : le marqueur n° 10 posé au sol est retrouvé, à peu près à sa vraie place."""
    from briques.b05_yeux.geometrie import robot_vers_monde

    cam = CameraSimulee(MONDE)
    cal = Calibration(homographie=cam.homographie_exacte().tolist(), largeur=320, hauteur=240)
    pose = (6.5, 3.5, 40.0)
    vue = Yeux(fabriquer(["aruco"], MONDE, MARQUEURS), cal).voir(cam.lire(etat_simule(*pose)))
    cuisine = [m for m in vue.marqueurs if m.nom == "cuisine"]
    assert cuisine and cuisine[0].sol is not None
    x, y = robot_vers_monde(pose, cuisine[0].sol.x, cuisine[0].sol.y)
    assert abs(x - 8.0) < 0.1 and abs(y - 4.5) < 0.1


@sans_opencv
def test_imprimer_les_marqueurs(tmp_path):
    faits = imprimer(tmp_path)
    n = len(MARQUEURS.calibration.numeros) + len(MARQUEURS.lieux) + len(MARQUEURS.objets)
    assert len(faits) == n and all(f.stat().st_size > 1000 for f in faits)


@sans_rapidocr
def test_rapidocr_lit_un_panneau_ecrit_et_reconnait_le_lieu():
    import cv2

    img = np.full((120, 360, 3), 255, np.uint8)
    cv2.putText(img, "CUISINE", (30, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.8, (0, 0, 0), 4, cv2.LINE_AA)
    vue = Yeux(fabriquer(["rapidocr"], MONDE, MARQUEURS)).voir(ImageCamera(pixels=img, heure=time.monotonic(), source="test"))
    assert vue.etat("rapidocr").etat == "ok", vue.branchements
    assert [(t.texte, t.lieu) for t in vue.textes] == [("CUISINE", "cuisine")]


@sans_rapidocr
def test_rapidocr_lit_le_panneau_de_la_camera_simulee():
    """Le panneau « ENTREE » dessiné en perspective dans le faux monde, vu de près."""
    cam = CameraSimulee(MONDE)
    image = cam.lire(etat_simule(2.0, 3.6, 135.0))
    vue = Yeux(fabriquer(["rapidocr"], MONDE, MARQUEURS)).voir(image)
    assert "entree" in {t.lieu for t in vue.textes}, [t.texte for t in vue.textes]


def test_mediapipe_essai_reel_ou_saute_proprement(tmp_path):
    """MediaPipe sur une image dessinée : il ne doit rien casser. Saute s'il ne peut pas démarrer ICI (paquet ou
    modèle absent, ou bibliothèque libEGL du système absente sur ce Linux) — la raison est dite."""
    from briques.b05_yeux.branchements.mediapipe_objets import BranchementMediaPipe

    b = BranchementMediaPipe(MONDE)
    raison = b.preparer()
    if raison:
        pytest.skip(f"MediaPipe non essayé ici : {raison}")
    image = CameraSimulee(MONDE).lire(etat_simule())
    t = b.analyser(image)  # sur un dessin, il peut ne rien trouver : on vérifie seulement la forme
    assert all(p.source == "mediapipe" for p in t.personnes)
