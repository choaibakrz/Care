"""Branchement « rapidocr » : lire un texte, une étiquette, un panneau (RapidOCR 3.10, Apache-2.0 ; décision de Hiba).

Les modèles (PP-OCRv6 small, Apache-2.0, Baidu/PaddleOCR) sont DANS le paquet : rien n'est téléchargé.
Lent (≈ 0,3 s par image sur l'ordinateur de test) : appelé de temps en temps, pas à chaque image (rapide = False).
Fonctions utilisées (lues dans le paquet installé) : rapidocr.RapidOCR(params=…), appel → résultat avec
.boxes (4 coins par texte), .txts, .scores. Accents, allemand, chinois : à vérifier (essayé en majuscules sans accent).
"""
from __future__ import annotations

import logging

import numpy as np

from commun.monde import Monde

from ..prise_yeux import Boite, Branchement, ImageCamera, Texte, Trouvailles, normaliser


class BranchementRapidOCR(Branchement):
    nom = "rapidocr"
    rapide = False

    def __init__(self, monde: Monde, confiance_min: float = 0.6) -> None:
        self.monde = monde
        self.confiance_min = confiance_min
        self._moteur = None
        self._noms = {normaliser(n): lieu.id for lieu in monde.lieux for _, n in lieu.tous_les_noms()}

    def preparer(self) -> str | None:
        try:
            from rapidocr import RapidOCR
        except ImportError as e:
            return f"RapidOCR absent ({e}) : pip install --no-deps -r requirements-yeux.txt"
        self._moteur = RapidOCR(params={"Global.log_level": "error"})
        logging.getLogger("RapidOCR").setLevel(logging.ERROR)
        return None

    def analyser(self, image: ImageCamera) -> Trouvailles:
        bgr = np.ascontiguousarray(image.pixels[:, :, ::-1])  # RapidOCR attend l'ordre d'OpenCV (bleu, vert, rouge)
        return self.lire_resultat(self._moteur(bgr))

    def lire_resultat(self, r) -> Trouvailles:
        t = Trouvailles()
        if r is None or r.txts is None or r.boxes is None:
            return t
        for coins, texte, score in zip(r.boxes, r.txts, r.scores or ()):
            if score is None or float(score) < self.confiance_min or not str(texte).strip():
                continue
            c = np.asarray(coins, dtype=float).reshape(-1, 2)
            x0, y0 = c.min(axis=0)
            x1, y1 = c.max(axis=0)
            t.textes.append(Texte(texte=str(texte), boite=Boite(x=x0, y=y0, largeur=x1 - x0, hauteur=y1 - y0),
                                  confiance=float(score), lieu=self.lieu_du_texte(str(texte))))
        return t

    def lieu_du_texte(self, texte: str) -> str | None:
        """« CUISINE » → cuisine. Une petite faute de lecture est permise pour un mot d'au moins 5 lettres
        (« CUISIHE » → cuisine), jamais pour un mot court (trop de risques de confusion)."""
        import difflib

        n = normaliser(texte)
        if n in self._noms:
            return self._noms[n]
        if len(n) < 5:
            return None
        proches = difflib.get_close_matches(n, [k for k in self._noms if len(k) >= 5], n=1, cutoff=0.8)
        return self._noms[proches[0]] if proches else None
