"""Écoute avec mlx-whisper (licence MIT, Apple ml-explore), sur la puce Apple.

NON TESTÉ : écrit d'après la documentation de mlx-whisper, à vérifier sur Mac (preparer_mac.sh le mesure).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ..ecoute import Ecoute, confiance_depuis

RACINE = Path(__file__).resolve().parents[3]


class EcouteMlxWhisper(Ecoute):
    def __init__(self, taille: str = "small") -> None:
        import mlx_whisper  # noqa: F401  (vérifie qu'il est installé)

        nom = {"small": "whisper-small-mlx", "large-v3-turbo": "whisper-turbo-mlx",
               "flix-gsw": "whisper-flix-gsw-mlx"}.get(taille, f"whisper-{taille}-mlx")
        self.dossier = RACINE / "modeles" / nom
        if not self.dossier.exists():
            raise FileNotFoundError(f"Modèle {self.dossier} absent (outils/telecharger.py --seulement {nom}).")
        self.nom = f"mlx-whisper {taille}"

    def _transcrire(self, son: np.ndarray, langue_moteur: str | None, mots: list[str], contexte: str | None = None):
        import mlx_whisper

        r = mlx_whisper.transcribe(son.astype("float32"), path_or_hf_repo=str(self.dossier), language=langue_moteur,
                                   condition_on_previous_text=False, initial_prompt=contexte or (", ".join(mots) if mots else None))
        segs = r.get("segments", [])
        conf = confiance_depuis([s.get("avg_logprob", -1.0) for s in segs], [s.get("no_speech_prob", 0.0) for s in segs])
        langue = r.get("language") or (langue_moteur or "")
        # mlx-whisper ne rend pas toutes les probabilités de langue : à vérifier ; on donne la langue choisie.
        return r.get("text", ""), langue, {langue: 1.0}, conf
