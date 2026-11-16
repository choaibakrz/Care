"""OPTION ÉTEINTE — voix Piper avec espeak-ng (paquet `piper-tts`, licence GPL-3.0). Décision de Hiba : pas maintenant.

Pour l'allumer : `pip install -r requirements-piper-gpl.txt`, puis ajouter `piper_gpl` dans reglages.yaml
(voix.parole.moteurs). Les voix (licences vérifiées) sont celles du catalogue : voix-fr, voix-de, voix-it, voix-en.
NON TESTÉ : écrit d'après la documentation de piper-tts 1.x (à vérifier : `PiperVoice.load`, `synthesize`).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ..voix import Voix

RACINE = Path(__file__).resolve().parents[3]
VOIX = {"fr": "voix-fr", "de": "voix-de", "it": "voix-it", "en": "voix-en"}


class VoixPiperGPL(Voix):
    nom = "piper (GPL, espeak-ng)"

    def __init__(self) -> None:
        from piper import PiperVoice  # paquet piper-tts : absent tant que l'option est éteinte

        self._piper = PiperVoice
        self._dispo = {lg: next((RACINE / "modeles" / d).rglob("*.onnx"), None) for lg, d in VOIX.items()}
        self._dispo = {lg: p for lg, p in self._dispo.items() if p}
        self._voix: dict[str, object] = {}

    def langues(self) -> set[str]:
        return set(self._dispo)

    def _synthetiser(self, texte: str, langue: str, lent: bool):
        if langue not in self._voix:
            self._voix[langue] = self._piper.load(str(self._dispo[langue]))
        morceaux = list(self._voix[langue].synthesize(texte))
        son = np.concatenate([m.audio_float_array for m in morceaux]) if morceaux else np.zeros(0, dtype="float32")
        return son.astype("float32"), int(morceaux[0].sample_rate) if morceaux else 22050
