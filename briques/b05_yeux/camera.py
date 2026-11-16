"""Brique 5 — Les caméras : une seule forme, `lire(etat) -> ImageCamera`.

Réglage `reglages.yaml → yeux.camera` :
- `auto`        : la caméra SIMULÉE avec le faux robot ; aucune avec un vrai robot (à choisir samedi) ;
- `simulee`     : la caméra simulée (faux robot seulement) ;
- `opencv:0`    : une caméra USB (0 = la première ; 1, 2… les suivantes) ;
- `opencv:URL`  : un flux vidéo, ex. `opencv:rtsp://192.168.123.161:8554/video` (adresse : dans la doc du robot,
                  à vérifier samedi) ;
- `fichier:CHEMIN` : toujours la même image (essais) : une PHOTO FIXE, jamais de personnes pour le gardien ;
- `simulee_fixe` : une caméra fixe simulée qui voit toute la halle (faux robot seulement) ;
- `aucune`      : pas de caméra (les yeux le disent ; le gardien demande un humain).

Une caméra ne fait que LIRE des images : elle n'envoie jamais rien au robot.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

import numpy as np

from .camera_simulee import FIXE_HALLE, MONTAGE_FIXE, CameraEnPanne, CameraRefusee, CameraSimulee
from .prise_yeux import ImageCamera

RACINE = Path(__file__).resolve().parents[2]


class CameraOpenCV:
    """Une vraie caméra lue par OpenCV (USB ou flux réseau). Testé sur Linux SANS caméra : à vérifier samedi."""

    def __init__(self, adresse: str, largeur: int | None = None, hauteur: int | None = None) -> None:
        self.adresse = adresse
        self.source = f"opencv:{adresse}"
        self.largeur, self.hauteur = largeur, hauteur
        self._capture = None
        self._verrou = threading.Lock()
        self._echecs = 0

    def ouvrir(self) -> None:
        try:
            import cv2
        except ImportError as e:
            raise CameraEnPanne("OpenCV absent : pip install --no-deps -r requirements-yeux.txt") from e
        with self._verrou:
            if self._capture is not None:
                return
            source = int(self.adresse) if self.adresse.isdigit() else self.adresse
            capture = cv2.VideoCapture(source)
            if not capture.isOpened():
                capture.release()
                raise CameraEnPanne(f"caméra {self.adresse} : impossible de l'ouvrir (branchée ? bon numéro ? bonne adresse ?)")
            if self.largeur and self.hauteur:
                capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.largeur)
                capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.hauteur)
            self._capture = capture

    def fermer(self) -> None:
        with self._verrou:
            if self._capture is not None:
                self._capture.release()
                self._capture = None

    def lire(self, etat=None) -> ImageCamera:
        import cv2

        if self._capture is None:
            self.ouvrir()
        with self._verrou:
            ok, image = self._capture.read() if self._capture is not None else (False, None)
            heure = time.monotonic()
        if not ok or image is None:
            self._echecs += 1
            if self._echecs >= 3:  # câble débranché, flux coupé : on rouvrira à la prochaine lecture
                self.fermer()
                self._echecs = 0
            raise CameraEnPanne(f"caméra {self.adresse} : pas d'image")
        self._echecs = 0
        return ImageCamera(pixels=cv2.cvtColor(image, cv2.COLOR_BGR2RGB), heure=heure, source=self.source,
                           pose=_pose(etat))


class CameraFichier:
    """Toujours la même image, lue dans un fichier (PNG, JPG). Pour essayer les yeux sans caméra.
    Une PHOTO FIXE : elle ne dit jamais ce qui est là maintenant (ni personnes au gardien, ni « je ne vois pas »)."""

    photo_fixe = True

    def __init__(self, chemin: str | Path) -> None:
        p = Path(chemin)
        self.chemin = p if p.is_absolute() else RACINE / p
        self.source = f"fichier:{self.chemin.name}"
        self._pixels: np.ndarray | None = None
        self.en_panne = False

    def ouvrir(self) -> None:
        try:
            import cv2
        except ImportError as e:
            raise CameraEnPanne("OpenCV absent : pip install --no-deps -r requirements-yeux.txt") from e
        image = cv2.imread(str(self.chemin))
        if image is None:
            raise CameraEnPanne(f"image illisible : {self.chemin}")
        self._pixels = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    def fermer(self) -> None:
        self._pixels = None

    def lire(self, etat=None) -> ImageCamera:
        if self.en_panne:
            raise CameraEnPanne("fichier : panne provoquée")
        if self._pixels is None:
            self.ouvrir()
        return ImageCamera(pixels=self._pixels.copy(), heure=time.monotonic(), source=self.source, pose=_pose(etat),
                           photo_fixe=True)  # une vieille photo : jamais de personnes pour le gardien


def _pose(etat) -> tuple[float, float, float] | None:
    p = (getattr(etat, "position", None) or {}) if etat is not None else {}
    x, y, cap = p.get("x"), p.get("y"), p.get("cap", 0.0)
    if all(isinstance(v, (int, float)) for v in (x, y, cap)):
        return (float(x), float(y), float(cap))
    return None


def ouvrir_camera(reglage: str, monde, genre: str, faux_robot: bool):
    """La caméra décrite par `reglage` (voir en haut du fichier), ou None pour « aucune ».
    La caméra simulée est REFUSÉE avec un vrai robot (elle inventerait des personnes)."""
    reglage = (reglage or "auto").strip()
    if reglage == "auto":
        reglage = "simulee" if faux_robot else "aucune"
    if reglage == "aucune":
        return None
    if reglage == "simulee":
        if not faux_robot:
            raise CameraRefusee("caméra simulée demandée avec un vrai robot : refusé (choisir opencv:0, une adresse, ou aucune)")
        return CameraSimulee(monde, genre=genre)
    if reglage == "simulee_fixe":  # caméra fixe simulée qui voit toute la halle (faux robot seulement)
        if not faux_robot:
            raise CameraRefusee("caméra simulée demandée avec un vrai robot : refusé")
        return CameraSimulee(monde, genre=genre, fixe=FIXE_HALLE, montage=MONTAGE_FIXE, source="camera_simulee_fixe")
    if reglage.startswith("opencv:"):
        return CameraOpenCV(reglage.split(":", 1)[1])
    if reglage.startswith("fichier:"):
        return CameraFichier(reglage.split(":", 1)[1])
    raise ValueError(f"Caméra inconnue : {reglage!r} (auto, simulee, opencv:0, opencv:URL, fichier:CHEMIN, aucune)")
