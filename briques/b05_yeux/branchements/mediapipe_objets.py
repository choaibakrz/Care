"""Branchement « mediapipe » : personnes et objets courants (MediaPipe, Apache-2.0 ; décision de Hiba).

Modèle : EfficientDet-Lite0 (80 sortes d'objets du jeu COCO, dont « person », « bottle », « cup », « suitcase »),
fichier de 4,6 Mo téléchargé à part (telecharger_modele.py), jamais pendant les tests.
Fonctions de MediaPipe utilisées (lues dans le paquet 1.2.2 installé) : tasks.python.vision.ObjectDetector,
ObjectDetectorOptions(base_options, score_threshold, max_results), BaseOptions(model_asset_path), mediapipe.Image,
ImageFormat.SRGB ; résultat : detections[].bounding_box (origin_x, origin_y, width, height),
detections[].categories[].category_name et .score.

ATTENTION : jamais lancé avec succès sur l'ordinateur de test (Linux du nuage) : la bibliothèque de MediaPipe y
demande libEGL.so.1 (bibliothèque du système, absente ; l'installer = feu orange). À vérifier sur Mac.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from commun.monde import Monde

from ..prise_yeux import Boite, Branchement, ImageCamera, Objet, Personne, Trouvailles
from . import nom_du_monde

RACINE = Path(__file__).resolve().parents[3]
MODELE_DEFAUT = "modeles/mediapipe-efficientdet-lite0/efficientdet_lite0.tflite"


class BranchementMediaPipe(Branchement):
    nom = "mediapipe"
    voit_les_personnes = True
    voit_les_objets = True

    def __init__(self, monde: Monde, modele: str | None = None, confiance_min: float = 0.4) -> None:
        self.monde = monde
        p = Path(modele or MODELE_DEFAUT)
        self.modele = p if p.is_absolute() else RACINE / p
        self.confiance_min = confiance_min
        self._detecteur = None
        self._mp = None

    def preparer(self) -> str | None:
        if not self.modele.exists():
            return f"modèle absent : {self.modele} (python -m briques.b05_yeux.telecharger_modele)"
        from ..telecharger_modele import empreinte_ok

        if not empreinte_ok(self.modele):  # revérifié à chaque chargement : un fichier abîmé ou changé n'est pas lu
            return (f"modèle refusé : empreinte différente de celle relevée ({self.modele.name}) ; "
                    "le retélécharger : python -m briques.b05_yeux.telecharger_modele")
        try:
            import mediapipe as mp
            from mediapipe.tasks.python import vision
            from mediapipe.tasks.python.core.base_options import BaseOptions
        except ImportError as e:
            return f"MediaPipe absent ({e}) : pip install --no-deps -r requirements-yeux.txt"
        options = vision.ObjectDetectorOptions(base_options=BaseOptions(model_asset_path=str(self.modele)),
                                               score_threshold=self.confiance_min, max_results=20)
        try:
            self._detecteur = vision.ObjectDetector.create_from_options(options)
        except Exception as e:  # noqa: BLE001 - ex. « libEGL.so.1: cannot open shared object file » (Linux sans affichage)
            return f"MediaPipe ne démarre pas sur cet ordinateur : {e}"
        self._mp = mp
        return None

    def analyser(self, image: ImageCamera) -> Trouvailles:
        mp = self._mp
        img = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(image.pixels))
        return self.lire_resultat(self._detecteur.detect(img))

    def lire_resultat(self, resultat) -> Trouvailles:
        """Le résultat de MediaPipe → nos personnes et objets (séparé pour être testé sans MediaPipe)."""
        t = Trouvailles()
        for d in resultat.detections or []:
            if not d.categories:
                continue
            cat = max(d.categories, key=lambda c: c.score or 0.0)
            score = float(cat.score or 0.0)
            if score < self.confiance_min:
                continue
            b = d.bounding_box
            boite = Boite(x=float(b.origin_x), y=float(b.origin_y), largeur=float(b.width), hauteur=float(b.height))
            etiquette = (cat.category_name or cat.display_name or "").strip()
            if etiquette == "person":
                t.personnes.append(Personne(boite=boite, confiance=score, source="mediapipe"))
            elif etiquette:
                t.objets.append(Objet(etiquette=etiquette, nom=nom_du_monde(etiquette, self.monde), boite=boite,
                                      confiance=score, source="mediapipe"))
        return t
