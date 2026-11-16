"""Brique 5 — la caméra simulée du faux robot, et le choix de la caméra. Numpy seulement (OpenCV : marqueurs et
panneaux en plus, s'il est là). Tout ici est « caméra simulée »."""
from __future__ import annotations

import pytest

from briques.b05_yeux.camera import CameraFichier, ouvrir_camera
from briques.b05_yeux.camera_simulee import CameraEnPanne, CameraRefusee, CameraSimulee
from commun.monde import Monde

from aides_yeux import etat_simule

MONDE = Monde.charger()


def _vus(image) -> dict[str, tuple]:
    return {v["id"]: v["boite"] for v in image.verite}


def test_l_image_du_depart_montre_le_visiteur_et_les_objets_de_la_table():
    image = CameraSimulee(MONDE).lire(etat_simule(1.0, 1.0, 0.0))
    assert image.pixels.shape == (240, 320, 3) and image.simulee and image.source == "camera_simulee"
    assert image.pose == (1.0, 1.0, 0.0)
    vus = _vus(image)
    assert {"visiteur", "bouteille", "tasse"} <= set(vus)  # monde.yaml : devant le robot (vers +x)
    assert "valise" not in vus and "caisse" not in vus  # derrière ou à côté (y = 4,8 et 5,3) : hors du champ
    x, y, lg, ht = vus["visiteur"]
    assert 0 <= x and x + lg <= 320 and 0 <= y and y + ht <= 240


def test_dos_tourne_le_robot_ne_voit_plus_le_visiteur():
    assert "visiteur" not in _vus(CameraSimulee(MONDE).lire(etat_simule(1.0, 1.0, 180.0)))


def test_les_objets_suivent_l_etat_du_faux_robot():
    cam = CameraSimulee(MONDE)
    objets = {o.id: [o.position.x, o.position.y] for o in MONDE.objets}
    objets["bouteille"] = [1.2, 5.5]  # posée ailleurs, hors du champ
    assert "bouteille" not in _vus(cam.lire(etat_simule(objets=objets)))
    assert "tasse" not in _vus(cam.lire(etat_simule(tenu="tasse")))  # dans la main du robot : pas dessinée devant
    cam.caches.add("tasse")
    assert "tasse" not in _vus(cam.lire(etat_simule()))


def test_placer_une_personne_dans_le_faux_monde():
    cam = CameraSimulee(MONDE)
    cam.placer_personne("proche", 3.0, 1.3)
    assert "proche" in _vus(cam.lire(etat_simule()))
    cam.retirer_personne("proche")
    assert "proche" not in _vus(cam.lire(etat_simule()))


def test_panne_position_inconnue_et_vrai_robot_refuses():
    cam = CameraSimulee(MONDE)
    cam.provoquer_panne()
    with pytest.raises(CameraEnPanne):
        cam.lire(etat_simule())
    cam.reparer()
    with pytest.raises(CameraRefusee, match="SIMULÉE"):
        cam.lire(etat_simule(simulation=False))  # un vrai robot : jamais de personnes inventées
    sans_position = etat_simule()
    sans_position.position = {}
    with pytest.raises(CameraEnPanne, match="position"):
        cam.lire(sans_position)


def test_choisir_la_camera():
    assert isinstance(ouvrir_camera("auto", MONDE, "humanoide", faux_robot=True), CameraSimulee)
    assert ouvrir_camera("auto", MONDE, "humanoide", faux_robot=False) is None  # vrai robot : à choisir samedi
    assert ouvrir_camera("aucune", MONDE, "chien", faux_robot=True) is None
    with pytest.raises(CameraRefusee):
        ouvrir_camera("simulee", MONDE, "humanoide", faux_robot=False)
    with pytest.raises(ValueError, match="inconnue"):
        ouvrir_camera("webcam", MONDE, "humanoide", faux_robot=True)
    assert isinstance(ouvrir_camera("fichier:photo.png", MONDE, "humanoide", faux_robot=False), CameraFichier)
    assert ouvrir_camera("opencv:0", MONDE, "humanoide", faux_robot=False).source == "opencv:0"  # pas ouverte ici


def test_une_image_absente_est_une_panne(tmp_path):
    pytest.importorskip("cv2", reason="OpenCV absent (requirements-yeux.txt)")
    with pytest.raises(CameraEnPanne, match="illisible"):
        CameraFichier(tmp_path / "rien.png").lire()


def test_le_bras_regarde_la_table():
    cam = CameraSimulee(MONDE, genre="bras")
    vus = _vus(cam.lire(etat_simule(5.0, 2.6, 0.0)))
    assert {"bouteille", "tasse"} <= set(vus)
