"""Voix Piper lues par sherpa-onnx (licence Apache-2.0, k2-fsa).

- Chinois (chaowen) : lexique fourni, aucun phonémiseur → marche tel quel. Testé sur Linux.
- Français, allemand, italien, anglais : les voix Piper ont besoin d'espeak-ng (GPL-3.0) pour transformer le texte
  en sons. sherpa-onnx 2.x ne l'inclut plus. Tant que Hiba n'a pas décidé, ces langues ne sont PAS proposées ici :
  la cascade passe à la voix du Mac. Voir DECISIONS.md.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ..voix import Voix

RACINE = Path(__file__).resolve().parents[3]


class VoixSherpaPiper(Voix):
    nom = "piper (sherpa-onnx)"

    def __init__(self, fils: int = 2) -> None:
        import sherpa_onnx

        self._sherpa = sherpa_onnx
        self.fils = fils
        self._moteurs: dict[str, object] = {}
        self._dispo: dict[str, Path] = {}
        zh = RACINE / "modeles" / "voix-zh-sherpa"
        if (zh / "lexicon.txt").exists():
            self._dispo["zh"] = zh
        if not self._dispo:
            raise FileNotFoundError("Aucune voix sherpa-onnx prête (outils/telecharger.py --seulement voix-zh-sherpa).")

    def langues(self) -> set[str]:
        return set(self._dispo)

    def _moteur(self, langue: str):
        if langue not in self._moteurs:
            d = self._dispo[langue]
            onnx = next(d.glob("*.onnx"))
            s = self._sherpa
            fsts = ",".join(str(d / f) for f in ("phone.fst", "date.fst", "number.fst") if (d / f).exists())
            cfg = s.OfflineTtsConfig(
                model=s.OfflineTtsModelConfig(
                    vits=s.OfflineTtsVitsModelConfig(model=str(onnx), tokens=str(d / "tokens.txt"), lexicon=str(d / "lexicon.txt")),
                    num_threads=self.fils),
                rule_fsts=fsts)
            self._moteurs[langue] = s.OfflineTts(cfg)
        return self._moteurs[langue]

    def _synthetiser(self, texte: str, langue: str, lent: bool):
        audio = self._moteur(langue).generate(texte, sid=0, speed=0.8 if lent else 1.0)
        return np.asarray(audio.samples, dtype="float32"), int(audio.sample_rate)
