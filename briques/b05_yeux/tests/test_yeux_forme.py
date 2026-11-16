"""Brique 5 — la prise des yeux : une forme commune, des branchements qui peuvent manquer sans rien casser.

Sans paquet en option : numpy seulement. Les résultats de MediaPipe et de RapidOCR sont imités (même forme que dans
leurs paquets) pour tester NOTRE lecture ; les vrais outils sont essayés dans test_yeux_outils.py (sautés s'ils manquent).
"""
from __future__ import annotations

import time
from types import SimpleNamespace as N

import numpy as np
import pytest

from briques.b05_yeux.branchements import CONNUS, fabriquer, nom_du_monde
from briques.b05_yeux.branchements.mediapipe_objets import BranchementMediaPipe
from briques.b05_yeux.branchements.rapidocr_textes import BranchementRapidOCR
from briques.b05_yeux.branchements.simule import BranchementSimule
from briques.b05_yeux.marqueurs import ListeMarqueurs
from briques.b05_yeux.prise_yeux import (Boite, Branchement, ImageCamera, Personne, Trouvailles, Yeux,
                                         normaliser)
from commun.monde import Monde

MONDE = Monde.charger()


def _image(verite=None, largeur=320, hauteur=240) -> ImageCamera:
    return ImageCamera(pixels=np.zeros((hauteur, largeur, 3), np.uint8), heure=time.monotonic(), source="test",
                       verite=verite)


class _Absent(Branchement):
    nom = "absent"
    voit_les_personnes = True

    def preparer(self):
        return "paquet pas installé"


class _Casse(Branchement):
    nom = "casse"
    voit_les_personnes = True

    def analyser(self, image):
        raise RuntimeError("boum")


class _CasseAuDemarrage(Branchement):
    nom = "casse_au_demarrage"

    def preparer(self):
        raise OSError("libEGL.so.1: cannot open shared object file")


class _UnePersonne(Branchement):
    nom = "une_personne"
    voit_les_personnes = True

    def analyser(self, image):
        return Trouvailles(personnes=[Personne(boite=Boite(x=10, y=20, largeur=30, hauteur=200), confiance=0.9,
                                               source="test")])


def test_un_branchement_absent_ou_casse_est_dit_et_les_autres_continuent():
    yeux = Yeux([_Absent(), _Casse(), _CasseAuDemarrage(), _UnePersonne()])
    assert set(yeux.preparer()) == {"absent", "casse_au_demarrage"}
    vue = yeux.voir(_image())
    etats = {b.nom: b.etat for b in vue.branchements}
    assert etats == {"absent": "absent", "casse": "en_panne", "casse_au_demarrage": "absent", "une_personne": "ok"}
    assert "libEGL" in vue.etat("casse_au_demarrage").raison and "boum" in vue.etat("casse").raison
    assert len(vue.personnes) == 1 and vue.personnes_fiables  # l'outil qui marche a vu la personne
    assert vue.personnes[0].pieds_coupes is False and vue.calibree is False and vue.personnes[0].sol is None


def test_sans_outil_qui_marche_pour_les_personnes_la_vue_ne_dit_pas_personne():
    """« Aucune personne vue » ne veut rien dire si aucun outil ne sait voir les personnes : personnes_fiables=False."""
    vue = Yeux([_Absent(), _Casse()]).voir(_image())
    assert vue.personnes == [] and vue.personnes_fiables is False


def test_les_pieds_hors_de_l_image_sont_signales():
    class Proche(Branchement):
        nom = "proche"
        voit_les_personnes = True

        def analyser(self, image):
            return Trouvailles(personnes=[Personne(boite=Boite(x=100, y=30, largeur=80, hauteur=210), confiance=1,
                                                   source="test")])

    assert Yeux([Proche()]).voir(_image()).personnes[0].pieds_coupes is True


def test_la_verite_du_dessin_ne_sert_qu_avec_la_camera_simulee():
    b = BranchementSimule(MONDE)
    vue = Yeux([b]).voir(_image(verite=None))  # une vraie caméra : pas de vérité
    assert vue.etat("simule").etat == "sans_objet" and vue.personnes_fiables is False
    verite = [{"sorte": "personne", "id": "p", "boite": (1, 2, 3, 4), "monde": (9, 9)},
              {"sorte": "objet", "id": "bouteille", "etiquette": "bottle", "boite": (5, 6, 7, 8), "monde": (9, 9)}]
    vue = Yeux([b]).voir(_image(verite=verite))
    assert vue.personnes_fiables and vue.simulee
    assert vue.personnes[0].boite.x == 1 and vue.personnes[0].source == "camera_simulee"
    assert vue.objets[0].nom == "bouteille" and vue.objets[0].etiquette == "bottle"
    # La position dans le monde n'est jamais recopiée : elle se recalcule par la calibration, comme en vrai.
    assert vue.personnes[0].sol is None and vue.objets[0].sol is None


def test_branchements_connus_et_nom_inconnu():
    assert fabriquer(["simule"], MONDE, ListeMarqueurs.charger())[0].nom == "simule"
    with pytest.raises(ValueError, match="inconnu"):
        fabriquer(["owlv2"], MONDE, ListeMarqueurs.charger())
    assert set(CONNUS) == {"simule", "aruco", "mediapipe", "rapidocr"}


def test_les_noms_des_objets_du_detecteur_vers_le_monde():
    assert nom_du_monde("bottle", MONDE) == "bouteille"
    assert nom_du_monde("Flasche", MONDE) == "bouteille"
    assert nom_du_monde("cup", MONDE) == "tasse" and nom_du_monde("suitcase", MONDE) == "valise"
    assert nom_du_monde("chair", MONDE) is None


def test_lecture_d_un_resultat_de_mediapipe_sans_mediapipe():
    """Même forme que mediapipe.tasks (DetectionResult → detections → bounding_box, categories)."""
    def det(nom, score, x, y, w, h):
        return N(bounding_box=N(origin_x=x, origin_y=y, width=w, height=h),
                 categories=[N(category_name=nom, display_name=None, score=score, index=0)])

    b = BranchementMediaPipe(MONDE, confiance_min=0.4)
    t = b.lire_resultat(N(detections=[det("person", 0.9, 10, 20, 50, 150), det("bottle", 0.7, 200, 100, 12, 30),
                                      det("chair", 0.5, 0, 0, 5, 5), det("person", 0.2, 0, 0, 9, 9)]))
    assert len(t.personnes) == 1 and t.personnes[0].boite.hauteur == 150 and t.personnes[0].source == "mediapipe"
    assert [(o.etiquette, o.nom) for o in t.objets] == [("bottle", "bouteille"), ("chair", None)]


def test_mediapipe_sans_modele_dit_comment_le_telecharger(tmp_path):
    b = BranchementMediaPipe(MONDE, modele=str(tmp_path / "absent.tflite"))
    assert "telecharger_modele" in b.preparer()


def test_lecture_d_un_resultat_de_rapidocr_et_lieux_reconnus():
    b = BranchementRapidOCR(MONDE, confiance_min=0.6)
    coins = [[[0, 0], [10, 0], [10, 5], [0, 5]]] * 5
    r = N(boxes=np.array(coins, float), txts=("CUISINE", "Küche", "CUISIHE", "tabl", "flou"),
          scores=(0.99, 0.95, 0.9, 0.9, 0.3))
    textes = b.lire_resultat(r).textes
    assert [(t.texte, t.lieu) for t in textes] == [("CUISINE", "cuisine"), ("Küche", "cuisine"),
                                                    ("CUISIHE", "cuisine"), ("tabl", None)]  # « flou » : trop peu sûr
    assert b.lire_resultat(N(boxes=None, txts=None, scores=None)).textes == []
    assert b.lieu_du_texte("ENTRÉE") == "entree" and b.lieu_du_texte("门口") == "entree"


def test_normaliser():
    assert normaliser("Entrée !") == "entree" and normaliser("Küche") == "kuche"
