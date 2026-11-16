"""Branchement « aruco » : retrouver les marqueurs ArUco (OpenCV, Apache-2.0).

Un marqueur ArUco est un carré noir et blanc imprimé avec un numéro. OpenCV le retrouve sûrement et donne ses
4 coins : on sait quel lieu ou quel objet c'est (marqueurs.yaml), et, posé au sol, où il est (calibration).
Fonctions d'OpenCV utilisées : cv2.aruco.getPredefinedDictionary, DetectorParameters, ArucoDetector.detectMarkers
(OpenCV ≥ 4.7 ; essayé avec 5.0.0, sur Linux).
Coins affinés au sous-pixel (CORNER_REFINE_SUBPIX).
"""
from __future__ import annotations

import numpy as np

from ..marqueurs import ListeMarqueurs, dictionnaire_aruco
from ..prise_yeux import Branchement, ImageCamera, Marqueur, Trouvailles


class BranchementAruco(Branchement):
    nom = "aruco"

    def __init__(self, marqueurs: ListeMarqueurs) -> None:
        self.marqueurs = marqueurs
        self._detecteur = None
        self._cv2 = None

    def preparer(self) -> str | None:
        try:
            import cv2
        except ImportError:
            return "OpenCV absent (pip install --no-deps -r requirements-yeux.txt)"
        self._cv2 = cv2
        reglages = cv2.aruco.DetectorParameters()
        reglages.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX  # coins au dixième de pixel : calibration plus juste
        self._detecteur = cv2.aruco.ArucoDetector(dictionnaire_aruco(self.marqueurs.dictionnaire), reglages)
        return None

    def analyser(self, image: ImageCamera) -> Trouvailles:
        gris = self._cv2.cvtColor(image.pixels, self._cv2.COLOR_RGB2GRAY)
        return Trouvailles(marqueurs=self.trouver(gris))

    def trouver(self, gris: np.ndarray) -> list[Marqueur]:
        coins, numeros, _ = self._detecteur.detectMarkers(gris)
        sortie = []
        if numeros is None:
            return sortie
        for c, n in zip(coins, numeros.ravel()):
            sorte, nom = self.marqueurs.sorte(int(n))
            sortie.append(Marqueur(numero=int(n), coins=[(float(u), float(v)) for u, v in c.reshape(-1, 2)],
                                   sorte=sorte, nom=nom))
        return sortie
