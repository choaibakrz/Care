"""Micro et haut-parleur.

- `MicroMac` / `HautParleurMac` : le vrai micro et le vrai haut-parleur (paquet sounddevice). Non testés ici (pas de Mac).
- `MicroFichier` / `HautParleurFactice` : pour les tests et le banc d'essai. Ils jouent des enregistrements comme
  s'ils arrivaient par le micro, au rythme réel ou plus vite. Tout ce qui est mesuré avec eux est « testé sur faux robot ».
"""
from __future__ import annotations

import asyncio
import time
from typing import AsyncIterator

import numpy as np

from .audio import TAUX
from .fin_de_parole import MORCEAU


class Micro:
    async def morceaux(self) -> AsyncIterator[np.ndarray]:  # pragma: no cover - interface
        raise NotImplementedError
        yield

    def fermer(self) -> None:
        pass


class MicroFichier(Micro):
    """Envoie un son morceau par morceau. vitesse=1 : temps réel ; 10 : dix fois plus vite."""

    def __init__(self, son: np.ndarray, vitesse: float = 1.0, silence_final_s: float = 2.0) -> None:
        self.son = np.concatenate([son, np.zeros(int(silence_final_s * TAUX), dtype="float32")])
        self.vitesse = vitesse
        self.position_s = 0.0

    async def morceaux(self):
        debut = time.monotonic()
        for i in range(0, len(self.son) - MORCEAU + 1, MORCEAU):
            self.position_s = (i + MORCEAU) / TAUX
            attente = debut + self.position_s / self.vitesse - time.monotonic()
            if attente > 0:
                await asyncio.sleep(attente)
            else:
                await asyncio.sleep(0)
            yield self.son[i: i + MORCEAU]


class MicroMac(Micro):
    """Le micro de l'ordinateur. NON TESTÉ ici."""

    def __init__(self, appareil: int | str | None = None) -> None:
        import sounddevice as sd

        self._file: asyncio.Queue = asyncio.Queue()
        self._boucle = asyncio.get_running_loop()

        def rappel(indata, frames, temps, statut):
            self._boucle.call_soon_threadsafe(self._file.put_nowait, indata[:, 0].copy())

        self._flux = sd.InputStream(samplerate=TAUX, channels=1, dtype="float32", blocksize=MORCEAU,
                                    device=appareil, callback=rappel)
        self._flux.start()

    async def morceaux(self):
        while True:
            yield await self._file.get()

    def fermer(self) -> None:
        self._flux.stop()
        self._flux.close()


class HautParleur:
    """Joue un son et peut être coupé à tout moment (interruption)."""

    parle = False

    async def jouer(self, echantillons: np.ndarray, taux: int) -> bool:  # pragma: no cover - interface
        """Rend True si le son a été joué jusqu'au bout, False s'il a été coupé."""
        raise NotImplementedError

    def couper(self) -> None:
        pass


class HautParleurFactice(HautParleur):
    """Fait « comme si » : attend la durée du son (divisée par la vitesse), coupable."""

    def __init__(self, vitesse: float = 1.0) -> None:
        self.vitesse = vitesse
        self._coupe = asyncio.Event()
        self.joues: list[float] = []  # durées jouées (s)

    async def jouer(self, echantillons: np.ndarray, taux: int) -> bool:
        self.parle = True
        self._coupe.clear()
        duree = len(echantillons) / taux if taux else 0.0
        debut = time.monotonic()
        try:
            await asyncio.wait_for(self._coupe.wait(), duree / self.vitesse)
            self.joues.append((time.monotonic() - debut) * self.vitesse)
            return False
        except asyncio.TimeoutError:
            self.joues.append(duree)
            return True
        finally:
            self.parle = False

    def couper(self) -> None:
        self._coupe.set()


class HautParleurMac(HautParleur):
    """Le haut-parleur de l'ordinateur. NON TESTÉ ici."""

    def __init__(self) -> None:
        import sounddevice as sd

        self._sd = sd
        self._coupe = asyncio.Event()

    async def jouer(self, echantillons: np.ndarray, taux: int) -> bool:
        self.parle = True
        self._coupe.clear()
        self._sd.play(echantillons, taux)
        duree = len(echantillons) / taux
        try:
            await asyncio.wait_for(self._coupe.wait(), duree)
            self._sd.stop()
            return False
        except asyncio.TimeoutError:
            return True
        finally:
            self.parle = False

    def couper(self) -> None:
        self._coupe.set()
