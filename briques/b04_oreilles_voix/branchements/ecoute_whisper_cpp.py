"""Écoute avec whisper.cpp (licence MIT), par pywhispercpp (licence MIT), avec la puce graphique Apple.

NON TESTÉ : écrit d'après la documentation de pywhispercpp, à vérifier sur Mac (preparer_mac.sh le mesure).
La confiance n'est pas fournie de la même façon : à vérifier, en attendant on met 0,8 si du texte est reconnu.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ..ecoute import Ecoute

RACINE = Path(__file__).resolve().parents[3]


class EcouteWhisperCpp(Ecoute):
    def __init__(self, taille: str = "small") -> None:
        from pywhispercpp.model import Model

        nom = {"small": "whisper-small-cpp", "large-v3-turbo": "whisper-turbo-cpp"}.get(taille, f"whisper-{taille}-cpp")
        fichiers = sorted((RACINE / "modeles" / nom).rglob("ggml-*.bin"))
        if not fichiers:
            raise FileNotFoundError(f"Modèle absent (outils/telecharger.py --seulement {nom}).")
        self.modele = Model(str(fichiers[0]), print_progress=False, print_realtime=False)
        self.nom = f"whisper.cpp {taille}"

    def _transcrire(self, son: np.ndarray, langue_moteur: str | None, mots: list[str], contexte: str | None = None):
        segs = self.modele.transcribe(son.astype("float32"), language=langue_moteur or "auto",
                                      initial_prompt=contexte or (", ".join(mots) if mots else ""))
        texte = " ".join(s.text for s in segs).strip()
        langue = langue_moteur or "?"  # à vérifier : lire la langue détectée par whisper.cpp
        return texte, langue, {langue: 1.0}, (0.8 if texte else 0.0)
