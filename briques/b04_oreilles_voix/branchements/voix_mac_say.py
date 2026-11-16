"""La voix intégrée du Mac (commande `say`) : rien à télécharger, aucune licence à ajouter (fait partie de macOS).

NON TESTÉ (pas de Mac ici). Les noms de voix varient selon les Mac : `say -v '?'` donne la liste.
On cherche la première voix disponible dans l'ordre ci-dessous ; sinon la langue n'est pas proposée.
Voix suisse allemande : à vérifier sur le Mac (`say -v '?' | grep de_CH`).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

from ..audio import lire
from ..voix import Voix

PREFERENCES = {
    "fr": ["Thomas", "Amélie", "Aurélie"],
    "de": ["Anna", "Markus", "Petra", "Yannick"],
    "it": ["Alice", "Luca", "Federica"],
    "en": ["Samantha", "Daniel", "Karen"],
    "zh": ["Tingting", "Ting-Ting", "Lili"],
    "gsw": [],  # pas de voix connue : la réponse se fait en allemand (de)
}


class VoixMacSay(Voix):
    nom = "voix du Mac (say)"

    def __init__(self) -> None:
        if sys.platform != "darwin" or not shutil.which("say"):
            raise OSError("La commande « say » n'existe que sur Mac.")
        liste = subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout
        noms = {ligne.split("  ")[0].strip() for ligne in liste.splitlines() if ligne.strip()}
        self.voix = {lg: next((v for v in prefs if v in noms), None) for lg, prefs in PREFERENCES.items()}

    def langues(self) -> set[str]:
        return {lg for lg, v in self.voix.items() if v}

    def _synthetiser(self, texte: str, langue: str, lent: bool):
        with tempfile.TemporaryDirectory() as d:
            sortie = Path(d) / "voix.wav"
            subprocess.run(["say", "-v", self.voix[langue], "-r", "140" if lent else "185", "--file-format=WAVE",
                            "--data-format=LEI16@22050", "-o", str(sortie), texte], check=True)
            son = lire(sortie, 22050)
        return np.asarray(son, dtype="float32"), 22050
