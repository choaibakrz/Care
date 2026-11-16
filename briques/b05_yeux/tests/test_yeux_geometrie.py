"""Brique 5 — du pixel au sol (numpy seulement) : homographie, calibration, champ de la caméra."""
from __future__ import annotations

import math

import numpy as np
import pytest

from briques.b05_yeux.camera_simulee import CameraSimulee, _Cam
from briques.b05_yeux.geometrie import (Calibration, PlacementMarqueur, appliquer, homographie, monde_vers_robot,
                                        robot_vers_monde)
from commun.monde import Monde

MONDE = Monde.charger()


def test_homographie_retrouve_une_transformation_connue():
    vraie = np.array([[0.02, 0.001, -1.0], [0.0005, 0.03, -2.0], [0.0001, 0.002, 1.0]])
    pixels = [(10, 20), (300, 25), (310, 230), (5, 220), (160, 120), (80, 200)]
    sol, _ = appliquer(vraie, pixels)
    h = homographie(pixels, sol)
    retour, ok = appliquer(h, pixels)
    assert ok.all() and np.allclose(retour, sol, atol=1e-6)


def test_homographie_refuse_les_points_mal_places():
    with pytest.raises(ValueError, match="au moins 4"):
        homographie([(0, 0), (1, 0), (0, 1)], [(0, 0), (1, 0), (0, 1)])
    with pytest.raises(ValueError, match="alignés"):
        homographie([(0, 0), (1, 1), (2, 2), (3, 3)], [(0, 0), (1, 0), (2, 0), (3, 0)])
    with pytest.raises(ValueError, match="nombre"):
        homographie([(0, 0), (1, 0), (0, 1), (float("nan"), 1)], [(0, 0), (1, 0), (0, 1), (1, 1)])


def test_un_pixel_au_dessus_de_l_horizon_ne_touche_pas_le_sol():
    cam = CameraSimulee(MONDE, genre="humanoide")
    cal = Calibration(homographie=cam.homographie_exacte().tolist(), largeur=320, hauteur=240)
    assert cal.vers_sol(160, 2) is None  # tout en haut de l'image : au-dessus de l'horizon (le mur)
    p = cal.vers_sol(160, 200)
    assert p is not None and 1.0 < p.x < 2.5 and abs(p.y) < 0.05  # droit devant, entre 1 et 2,5 m


def test_les_coins_d_un_marqueur_au_sol_dans_l_ordre_d_aruco():
    m = PlacementMarqueur(numero=0, x=2.0, y=0.0, taille_m=0.2)  # le haut du marqueur vers l'avant du robot
    assert np.allclose(m.coins(), [(2.1, 0.1), (2.1, -0.1), (1.9, -0.1), (1.9, 0.1)])
    m = PlacementMarqueur(numero=0, x=0.0, y=1.0, taille_m=0.2, cap_deg=90)  # le haut vers la gauche du robot
    assert np.allclose(m.coins(), [(-0.1, 1.1), (0.1, 1.1), (0.1, 0.9), (-0.1, 0.9)], atol=1e-9)


def test_robot_et_monde_aller_retour():
    pose = (3.0, 2.0, 30.0)
    x, y = robot_vers_monde(pose, 1.5, -0.4)
    assert np.allclose(monde_vers_robot(pose, x, y), (1.5, -0.4))
    assert np.allclose(robot_vers_monde((1, 1, 90), 2, 0), (1, 3))  # tourné vers la gauche : 2 m devant = +y


def test_la_calibration_s_enregistre_et_se_relit(tmp_path):
    cam = CameraSimulee(MONDE)
    cal = Calibration(homographie=cam.homographie_exacte().tolist(), largeur=320, hauteur=240, source="essai")
    f = cal.enregistrer(tmp_path / "cal.yaml")
    relue = Calibration.charger(f)
    assert relue.source == "essai" and np.allclose(relue.matrice(), cal.matrice())
    (tmp_path / "abimee.yaml").write_text("repere: robot\nhomographie: [[0,0,0],[0,0,0],[0,0,0]]\nlargeur: 1\nhauteur: 1\n")
    with pytest.raises(ValueError, match="abîmée"):
        Calibration.charger(tmp_path / "abimee.yaml")


def test_une_image_plus_grande_garde_les_memes_points_au_sol():
    cal = Calibration(homographie=CameraSimulee(MONDE).homographie_exacte().tolist(), largeur=320, hauteur=240)
    a, b = cal.vers_sol(100, 180), cal.vers_sol(200, 360, 640, 480)
    assert a is not None and b is not None and math.isclose(a.x, b.x, abs_tol=1e-6) and math.isclose(a.y, b.y, abs_tol=1e-6)


def test_le_champ_de_la_camera_ne_voit_ni_derriere_ni_trop_loin_ni_a_cote():
    """Ce que la caméra NE voit PAS : utile pour dire honnêtement la limite au gardien (voir NOTES)."""
    cal = Calibration(homographie=CameraSimulee(MONDE).homographie_exacte().tolist(), largeur=320, hauteur=240)
    assert cal.voit(2.0, 0.0) and cal.voit(3.0, 0.8)
    assert not cal.voit(-1.0, 0.0)  # derrière le robot
    assert not cal.voit(0.5, 0.0)  # trop près : sous la caméra, hors de l'image
    assert not cal.voit(1.0, 2.5)  # à côté
    assert not cal.voit(8.0, 0.0)  # plus loin que la portée (6 m)


def test_la_projection_de_la_camera_simulee_et_son_homographie_vont_ensemble():
    cam = CameraSimulee(MONDE, genre="chien")
    c: _Cam = cam._cam((0.0, 0.0, 0.0))
    points = np.array([[1.2, 0.3, 0.0], [2.0, -0.5, 0.0], [3.5, 1.0, 0.0]])
    pix, z = c.projeter(points)
    assert (z > 0).all()
    sol, ok = appliquer(cam.homographie_exacte(), pix)
    assert ok.all() and np.allclose(sol, points[:, :2], atol=1e-6)
