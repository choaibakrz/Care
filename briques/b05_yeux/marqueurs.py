"""Brique 5 — Les marqueurs ArUco du défi : lire marqueurs.yaml, fabriquer les images à imprimer.

    .venv/bin/python -m briques.b05_yeux.marqueurs --imprimer marqueurs_a_imprimer/

Fabriquer les images demande OpenCV (requirements-yeux.txt). Lire le fichier, non.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import yaml
from pydantic import BaseModel, Field

CHEMIN_MARQUEURS = Path(__file__).with_name("marqueurs.yaml")


class PositionXY(BaseModel):
    x: float
    y: float


class MarqueurLieu(BaseModel):
    numero: int
    lieu: str
    taille_m: float = Field(gt=0)
    position: PositionXY | None = None


class MarqueurObjet(BaseModel):
    numero: int
    objet: str
    taille_m: float = Field(gt=0)


class MarqueurCalibration(BaseModel):
    numeros: list[int] = Field(default_factory=lambda: [0, 1, 2])
    taille_m: float = Field(0.28, gt=0)


class ListeMarqueurs(BaseModel):
    dictionnaire: str = "DICT_4X4_50"
    calibration: MarqueurCalibration = Field(default_factory=MarqueurCalibration)
    lieux: list[MarqueurLieu] = Field(default_factory=list)
    objets: list[MarqueurObjet] = Field(default_factory=list)

    def sorte(self, numero: int) -> tuple[str, str | None]:
        """(sorte, nom) d'un numéro : ("lieu", "cuisine"), ("calibration", None), ("inconnu", None)…"""
        if numero in self.calibration.numeros:
            return "calibration", None
        for m in self.lieux:
            if m.numero == numero:
                return "lieu", m.lieu
        for m in self.objets:
            if m.numero == numero:
                return "objet", m.objet
        return "inconnu", None

    def verifier(self) -> list[str]:
        """Les fautes du fichier : numéro en double, numéro hors du dictionnaire."""
        fautes = []
        numeros = list(self.calibration.numeros) + [m.numero for m in self.lieux] + [m.numero for m in self.objets]
        doubles = sorted({n for n in numeros if numeros.count(n) > 1})
        if doubles:
            fautes.append(f"numéros en double : {doubles}")
        maximum = int(self.dictionnaire.rsplit("_", 1)[-1]) if self.dictionnaire.rsplit("_", 1)[-1].isdigit() else None
        if maximum is not None and any(n < 0 or n >= maximum for n in numeros):
            fautes.append(f"numéros hors de 0…{maximum - 1} pour {self.dictionnaire}")
        return fautes

    @classmethod
    def charger(cls, chemin: str | Path = CHEMIN_MARQUEURS) -> "ListeMarqueurs":
        liste = cls.model_validate(yaml.safe_load(Path(chemin).read_text(encoding="utf-8")))
        fautes = liste.verifier()
        if fautes:
            raise ValueError(f"{chemin} : " + " ; ".join(fautes))
        return liste


def dictionnaire_aruco(nom: str):
    """Les familles permises, écrites en toutes lettres (pas d'accès par un nom calculé)."""
    import cv2

    familles = {"DICT_4X4_50": cv2.aruco.DICT_4X4_50, "DICT_4X4_100": cv2.aruco.DICT_4X4_100,
                "DICT_5X5_50": cv2.aruco.DICT_5X5_50, "DICT_5X5_100": cv2.aruco.DICT_5X5_100,
                "DICT_6X6_50": cv2.aruco.DICT_6X6_50, "DICT_6X6_100": cv2.aruco.DICT_6X6_100}
    if nom not in familles:
        raise ValueError(f"Dictionnaire ArUco inconnu : {nom} (permis : {', '.join(familles)})")
    return cv2.aruco.getPredefinedDictionary(familles[nom])


def image_marqueur(numero: int, dictionnaire: str = "DICT_4X4_50", cote_px: int = 120, marge_cases: int = 1) -> np.ndarray:
    """L'image d'un marqueur (gris, 0 = noir) avec une marge blanche d'une case tout autour (nécessaire pour le voir)."""
    import cv2

    d = dictionnaire_aruco(dictionnaire)
    m = cv2.aruco.generateImageMarker(d, int(numero), cote_px)
    cases = d.markerSize + 2  # le carré noir compte un bord d'une case de chaque côté
    marge = int(round(cote_px / cases * marge_cases))
    return cv2.copyMakeBorder(m, marge, marge, marge, marge, cv2.BORDER_CONSTANT, value=255)


def imprimer(dossier: str | Path, chemin: str | Path = CHEMIN_MARQUEURS) -> list[Path]:
    """Une image PNG par marqueur, avec son numéro et son nom écrits dessous (pour l'impression)."""
    import cv2

    liste = ListeMarqueurs.charger(chemin)
    dossier = Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    a_faire = [(n, "calibration", liste.calibration.taille_m) for n in liste.calibration.numeros]
    a_faire += [(m.numero, f"lieu {m.lieu}", m.taille_m) for m in liste.lieux]
    a_faire += [(m.numero, f"objet {m.objet}", m.taille_m) for m in liste.objets]
    faits = []
    for numero, quoi, taille in a_faire:
        img = image_marqueur(numero, liste.dictionnaire, cote_px=600)
        bas = np.full((90, img.shape[1]), 255, np.uint8)
        texte = f"n {numero} - {quoi} - cote du carre noir : {taille * 100:.0f} cm"
        cv2.putText(bas, texte, (20, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.8, 0, 2, cv2.LINE_AA)
        f = dossier / f"aruco_{numero:02d}.png"
        cv2.imwrite(str(f), np.vstack([img, bas]))
        faits.append(f)
    return faits


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Les marqueurs ArUco du défi (brique 5).")
    p.add_argument("--imprimer", metavar="DOSSIER", help="écrire une image PNG par marqueur dans ce dossier")
    args = p.parse_args(argv)
    liste = ListeMarqueurs.charger()
    print(f"Dictionnaire : {liste.dictionnaire}. Calibration : n° {liste.calibration.numeros} ({liste.calibration.taille_m} m).")
    for m in liste.lieux:
        print(f"  n° {m.numero:2d}  lieu   {m.lieu:12} {m.taille_m} m")
    for m in liste.objets:
        print(f"  n° {m.numero:2d}  objet  {m.objet:12} {m.taille_m} m")
    if args.imprimer:
        faits = imprimer(args.imprimer)
        print(f"{len(faits)} images écrites dans {args.imprimer}. Mesurer le carré noir après impression (taille_m).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
