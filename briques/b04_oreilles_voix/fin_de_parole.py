"""Savoir quand une personne commence et finit de parler (« détection d'activité vocale »).

On utilise le petit modèle Silero VAD (licence MIT, 1,2 Mo), déjà fourni avec faster-whisper.
Le son arrive par petits morceaux de 32 ms. Pour chaque morceau, le modèle dit la probabilité qu'il y ait de la voix.
- début de parole : assez de morceaux « voix » d'affilée ;
- fin de parole : assez de silence après la voix (600 ms par défaut, réglable).
Idée et format du modèle repris de faster-whisper (MIT, SYSTRAN) et de Silero VAD (MIT, Silero Team).
Le fichier du modèle est inclus : modeles_inclus/silero_vad_v6.onnx (voir modeles_inclus/SOURCE.md).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import numpy as np

from .audio import TAUX

MORCEAU = 512  # échantillons par morceau (32 ms à 16 kHz)
CONTEXTE = 64  # le modèle regarde aussi les 64 derniers échantillons du morceau précédent


def chemin_modele() -> str:
    """Le modèle est inclus dans le dépôt (modeles_inclus/, licence MIT) : pas besoin de faster-whisper."""
    return os.path.join(os.path.dirname(__file__), "modeles_inclus", "silero_vad_v6.onnx")


class ModeleVoix:
    """Le modèle Silero, utilisé morceau par morceau en gardant sa mémoire d'un appel à l'autre."""

    def __init__(self, chemin: str | None = None) -> None:
        import onnxruntime as ort

        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        opts.log_severity_level = 4
        self.session = ort.InferenceSession(chemin or chemin_modele(), providers=["CPUExecutionProvider"], sess_options=opts)
        self.remettre_a_zero()

    def remettre_a_zero(self) -> None:
        self.h = np.zeros((1, 1, 128), dtype="float32")
        self.c = np.zeros((1, 1, 128), dtype="float32")
        self.contexte = np.zeros(CONTEXTE, dtype="float32")

    def probabilite(self, morceau: np.ndarray) -> float:
        assert len(morceau) == MORCEAU
        entree = np.concatenate([self.contexte, morceau]).astype("float32")[None, :]
        sortie, self.h, self.c = self.session.run(None, {"input": entree, "h": self.h, "c": self.c})
        self.contexte = morceau[-CONTEXTE:].astype("float32")
        return float(np.asarray(sortie).ravel()[0])


@dataclass
class Enonce:
    """Une phrase complète : le son, et quand elle a commencé et fini (en secondes de son reçu)."""

    son: np.ndarray
    debut_s: float
    fin_parole_s: float  # fin réelle de la voix (dernier morceau « voix »)
    detection_s: float  # moment où l'on a décidé que c'était fini
    coupee: bool = False  # True si la phrase a été coupée parce que trop longue


@dataclass
class DetecteurParole:
    seuil: float = 0.5
    debut_ms: int = 96  # voix d'affilée pour dire « ça commence » (3 morceaux)
    silence_fin_ms: int = 600  # silence pour dire « c'est fini »
    marge_avant_ms: int = 300  # on garde un peu de son avant le début
    duree_max_s: float = 15.0
    modele: ModeleVoix = field(default_factory=ModeleVoix)

    def __post_init__(self) -> None:
        self.reinitialiser()

    def reinitialiser(self) -> None:
        self._tampon = np.zeros(0, dtype="float32")
        self._avant: list[np.ndarray] = []
        self._phrase: list[np.ndarray] = []
        self._en_parole = False
        self._voix_daffilee = 0
        self._silence_daffilee = 0
        self._t = 0.0  # secondes de son reçues
        self._debut = 0.0
        self._derniere_voix = 0.0
        self.parle_depuis_ms = 0.0  # utile pour l'interruption
        self.modele.remettre_a_zero()

    @property
    def en_parole(self) -> bool:
        return self._en_parole

    def ajouter(self, son: np.ndarray) -> list[Enonce]:
        """Donner du son (n'importe quelle longueur). Rend les phrases terminées."""
        finies: list[Enonce] = []
        self._tampon = np.concatenate([self._tampon, np.asarray(son, dtype="float32")])
        ms = MORCEAU / TAUX * 1000
        while len(self._tampon) >= MORCEAU:
            m, self._tampon = self._tampon[:MORCEAU], self._tampon[MORCEAU:]
            p = self.modele.probabilite(m)
            self._t += MORCEAU / TAUX
            voix = p >= self.seuil
            if not self._en_parole:
                self._avant.append(m)
                if len(self._avant) > int(self.marge_avant_ms / ms):
                    self._avant.pop(0)
                self._voix_daffilee = self._voix_daffilee + 1 if voix else 0
                self.parle_depuis_ms = self._voix_daffilee * ms
                if self._voix_daffilee * ms >= self.debut_ms:
                    self._en_parole = True
                    self._phrase = list(self._avant)
                    self._debut = self._t - len(self._phrase) * MORCEAU / TAUX
                    self._derniere_voix = self._t
                    self._silence_daffilee = 0
            else:
                self._phrase.append(m)
                if voix:
                    self._silence_daffilee = 0
                    self._derniere_voix = self._t
                    self.parle_depuis_ms += ms
                else:
                    self._silence_daffilee += 1
                trop_long = self._t - self._debut >= self.duree_max_s
                if self._silence_daffilee * ms >= self.silence_fin_ms or trop_long:
                    finies.append(Enonce(son=np.concatenate(self._phrase), debut_s=self._debut,
                                         fin_parole_s=self._derniere_voix, detection_s=self._t, coupee=trop_long))
                    self._en_parole = False
                    self._phrase, self._avant = [], []
                    self._voix_daffilee = 0
                    self.parle_depuis_ms = 0.0
        return finies

    def forcer_fin(self) -> Enonce | None:
        """Bouton « je parle » relâché : la phrase est finie maintenant, même sans silence."""
        if not self._phrase:
            return None
        e = Enonce(son=np.concatenate(self._phrase), debut_s=self._debut, fin_parole_s=self._derniere_voix,
                   detection_s=self._t)
        self._en_parole = False
        self._phrase, self._avant = [], []
        return e
