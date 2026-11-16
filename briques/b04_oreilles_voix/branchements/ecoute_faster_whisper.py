"""Écoute avec faster-whisper (licence MIT, SYSTRAN). Tourne sur le processeur ; testé sur Linux."""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from ..ecoute import Ecoute, confiance_depuis

RACINE = Path(__file__).resolve().parents[3]


def dossier_modele(taille: str) -> str:
    local = RACINE / "modeles" / f"whisper-{taille}-fw"
    if local.exists():
        return str(local)
    raise FileNotFoundError(f"Modèle {local} absent. Le télécharger : python3 outils/telecharger.py --seulement whisper-{taille}-fw")


class EcouteFasterWhisper(Ecoute):
    def __init__(self, taille: str = "small", fils: int | None = None) -> None:
        from faster_whisper import WhisperModel

        self.nom = f"faster-whisper {taille}"
        self.modele = WhisperModel(dossier_modele(taille), device="cpu", compute_type="int8",
                                   cpu_threads=fils or max(1, (os.cpu_count() or 4)))

    def _detecter(self, son: np.ndarray) -> dict[str, float]:
        _, _, toutes = self.modele.detect_language(son)
        return dict(toutes)

    def _transcrire(self, son: np.ndarray, langue_moteur: str | None, mots: list[str], contexte: str | None = None):
        segments, info = self.modele.transcribe(
            # temperature=0 : toujours le même résultat pour le même son (pas de nouvel essai au hasard).
            son, language=langue_moteur, beam_size=1, temperature=0.0, vad_filter=False, condition_on_previous_text=False,
            hotwords=", ".join(mots) if mots and not contexte else None, initial_prompt=contexte or None,
            without_timestamps=True,
        )
        segments = list(segments)
        texte = " ".join(s.text.strip() for s in segments)
        probas = dict(info.all_language_probs or []) if langue_moteur is None else {info.language: 1.0}
        conf = confiance_depuis([s.avg_logprob for s in segments], [s.no_speech_prob for s in segments])
        return texte, info.language, probas, conf
