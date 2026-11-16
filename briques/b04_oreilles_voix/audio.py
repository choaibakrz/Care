"""Petits outils pour le son : lire, écrire, mélanger du bruit, fabriquer un bruit de foule.

Partout dans la brique, un son = un tableau numpy de nombres entre -1 et 1, à 16 000 échantillons par seconde, mono.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

TAUX = 16000  # échantillons par seconde pour l'écoute


def lire(chemin: str | Path, taux: int = TAUX) -> np.ndarray:
    import soundfile as sf

    son, t = sf.read(str(chemin), dtype="float32", always_2d=False)
    if son.ndim > 1:
        son = son.mean(axis=1)
    return reechantillonner(son, t, taux)


def ecrire(chemin: str | Path, son: np.ndarray, taux: int = TAUX) -> None:
    import soundfile as sf

    Path(chemin).parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(chemin), np.clip(son, -1, 1), taux, subtype="PCM_16")


def reechantillonner(son: np.ndarray, de: int, vers: int = TAUX) -> np.ndarray:
    """Changement de fréquence simple (interpolation linéaire) : suffisant pour la parole."""
    son = np.asarray(son, dtype="float32")
    if de == vers or len(son) == 0:
        return son
    n = int(round(len(son) * vers / de))
    return np.interp(np.linspace(0, len(son) - 1, n), np.arange(len(son)), son).astype("float32")


def silence(ms: float, taux: int = TAUX) -> np.ndarray:
    return np.zeros(int(taux * ms / 1000), dtype="float32")


def puissance(son: np.ndarray) -> float:
    return float(np.mean(np.square(son))) + 1e-12


def melanger(parole: np.ndarray, bruit: np.ndarray, rsb_db: float) -> np.ndarray:
    """Ajoute du bruit à la parole avec un « rapport signal sur bruit » donné (en décibels).
    10 dB = la voix est nettement plus forte que le bruit ; 0 dB = aussi forte que le bruit."""
    if len(bruit) < len(parole):
        bruit = np.tile(bruit, int(np.ceil(len(parole) / len(bruit))))
    bruit = bruit[: len(parole)]
    gain = np.sqrt(puissance(parole) / (puissance(bruit) * 10 ** (rsb_db / 10)))
    mix = parole + gain * bruit
    pic = np.max(np.abs(mix))
    return (mix / pic * 0.95 if pic > 0.95 else mix).astype("float32")


def bruit_de_foule(sons: list[np.ndarray], duree_s: float, nb_voix: int = 8, graine: int = 0) -> np.ndarray:
    """Un « brouhaha » : plusieurs personnes qui parlent en même temps, décalées, mélangées.
    C'est la méthode classique pour simuler une foule (« babble noise »)."""
    rng = np.random.default_rng(graine)
    n = int(duree_s * TAUX)
    total = np.zeros(n, dtype="float32")
    for k in range(nb_voix):
        s = sons[k % len(sons)]
        s = s / (np.sqrt(puissance(s)) + 1e-9)
        debut = int(rng.integers(0, max(1, len(s))))
        piste = np.roll(np.tile(s, int(np.ceil(n / len(s))) + 1), -debut)[:n]
        total += piste
    return (total / (np.max(np.abs(total)) + 1e-9) * 0.5).astype("float32")
