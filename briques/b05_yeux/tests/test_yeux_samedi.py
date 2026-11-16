"""Brique 5 — les outils du samedi : calibrer (essai sur caméra simulée), banc de mesure, téléchargement du modèle."""
from __future__ import annotations

import hashlib

import pytest

from briques.b05_yeux import banc_yeux, calibrer, telecharger_modele
from briques.b05_yeux.prise_yeux import Marqueur

from aides_yeux import OPENCV


def test_lire_la_place_d_un_marqueur():
    p = calibrer.lire_placement("1:2,5:-0.8", 0.28)
    assert (p.numero, p.x, p.y, p.cap_deg, p.taille_m) == (1, 2.5, -0.8, 0.0, 0.28)
    assert calibrer.lire_placement("0:1.5:0:90", 0.2).cap_deg == 90
    with pytest.raises(ValueError, match="NUMÉRO:X:Y"):
        calibrer.lire_placement("0:1.5", 0.2)


def test_les_coins_sont_moyennes_sur_plusieurs_images():
    a = Marqueur(numero=0, coins=[(0, 0), (10, 0), (10, 10), (0, 10)])
    b = Marqueur(numero=0, coins=[(2, 0), (12, 0), (12, 10), (2, 10)])
    m = calibrer.coins_moyens([[a], [b]])
    assert len(m) == 1 and m[0].coins[0] == (1.0, 0.0)


@pytest.mark.skipif(not OPENCV, reason="OpenCV absent (requirements-yeux.txt)")
def test_calibrer_en_essai_sur_la_camera_simulee(capsys, tmp_path):
    assert calibrer.main(["--essai", "--images", "2", "--sortie", str(tmp_path / "c.yaml")]) == 0
    sortie = capsys.readouterr().out
    assert "SIMULÉE" in sortie and "(bien)" in sortie and not (tmp_path / "c.yaml").exists()  # un essai n'écrit rien


@pytest.mark.skipif(not OPENCV, reason="OpenCV absent (requirements-yeux.txt)")
def test_calibrer_une_photo_sans_marqueur_le_dit(capsys, tmp_path):
    import cv2
    import numpy as np

    photo = tmp_path / "vide.png"
    cv2.imwrite(str(photo), np.full((240, 320, 3), 180, np.uint8))
    assert calibrer.main(["--camera", f"fichier:{photo}", "--images", "1", "--sortie", str(tmp_path / "c.yaml")]) == 1
    assert "Aucun marqueur" in capsys.readouterr().out and not (tmp_path / "c.yaml").exists()


def test_le_banc_dit_sur_quelle_machine_il_a_mesure():
    r = banc_yeux.mesurer(n_images=2)
    assert r["machine"] and "camera_simulee (dessin)" in r["outils"] and r["outils"]["simule"]["mesure"]
    tableau = banc_yeux.en_tableau(r)
    assert "pas sur Mac" in tableau and "| simule |" in tableau


def test_le_modele_est_verifie_par_son_empreinte(tmp_path, monkeypatch):
    destination = tmp_path / "modele.tflite"
    monkeypatch.setattr(telecharger_modele, "DESTINATION", destination)
    faux = tmp_path / "faux.tflite"
    faux.write_bytes(b"pas un modele")
    with pytest.raises(ValueError, match="Empreinte"):
        telecharger_modele.installer(faux)
    assert not destination.exists()  # un fichier faux est supprimé
    contenu = b"x" * 10
    monkeypatch.setattr(telecharger_modele, "OCTETS", len(contenu))
    monkeypatch.setattr(telecharger_modele, "SHA256", hashlib.sha256(contenu).hexdigest())
    bon = tmp_path / "bon.tflite"
    bon.write_bytes(contenu)
    assert telecharger_modele.installer(bon) == destination and telecharger_modele.empreinte_ok(destination)
    # Relecture, point 11 : l'empreinte est vérifiée sur le fichier PARTIEL, avant de le mettre en place. Un mauvais
    # téléchargement ne remplace donc jamais un bon modèle, et ne laisse rien traîner.
    with pytest.raises(ValueError, match="Empreinte"):
        telecharger_modele.installer(faux)
    assert telecharger_modele.empreinte_ok(destination) and destination.read_bytes() == contenu
    assert not list(tmp_path.glob("*.partiel"))


def test_mediapipe_reverifie_le_modele_au_chargement(tmp_path):
    """Relecture, point 11 : un modèle abîmé ou changé après le téléchargement n'est jamais chargé."""
    from briques.b05_yeux.branchements.mediapipe_objets import BranchementMediaPipe
    from commun.monde import Monde

    change = tmp_path / "efficientdet_lite0.tflite"
    change.write_bytes(b"un autre fichier")
    raison = BranchementMediaPipe(Monde.charger(), modele=str(change)).preparer()
    assert raison is not None and "empreinte" in raison


def test_sans_oui_rien_n_est_telecharge(tmp_path, monkeypatch):
    monkeypatch.setattr(telecharger_modele, "DESTINATION", tmp_path / "modele.tflite")
    monkeypatch.setattr("builtins.input", lambda _q: "non")
    assert telecharger_modele.main([]) == 1 and not (tmp_path / "modele.tflite").exists()


@pytest.mark.skipif(not OPENCV, reason="OpenCV absent (requirements-yeux.txt)")
def test_une_photo_pour_verifier_le_cadrage(capsys, tmp_path):
    import cv2
    import numpy as np

    from briques.b05_yeux.marqueurs import image_marqueur

    img = np.full((240, 320), 200, np.uint8)
    m = image_marqueur(0, cote_px=96)
    img[40:40 + m.shape[0], 100:100 + m.shape[1]] = m
    source, sortie = tmp_path / "source.png", tmp_path / "vue.png"
    cv2.imwrite(str(source), img)
    assert calibrer.main(["--camera", f"fichier:{source}", "--photo", str(sortie)]) == 0
    assert sortie.exists() and "Marqueurs vus : [0]" in capsys.readouterr().out
