"""Le bus : un tableau d'affichage interne.

Une brique publie un événement ; toutes les briques abonnées le reçoivent.
Tout tourne dans un seul programme (asyncio), sans serveur de messages à installer.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Union

from .evenements import Evenement

log = logging.getLogger("bus")

Abonne = Callable[[Evenement], Union[None, Awaitable[None]]]


class Bus:
    def __init__(self) -> None:
        self._abonnes: list[tuple[str | None, Abonne]] = []
        self.historique: list[Evenement] = []  # utile aux tests et à l'écran
        self.taille_max_historique = 5000

    def abonner(self, fonction: Abonne, type_: str | None = None) -> None:
        """S'abonner à un type d'événement, ou à tous (type_=None)."""
        self._abonnes.append((type_, fonction))

    def desabonner(self, fonction: Abonne) -> None:
        # « != » et non « is not » : une méthode liée (self.fonction) est un nouvel objet à chaque lecture.
        self._abonnes = [(t, f) for (t, f) in self._abonnes if f != fonction]

    async def publier(self, ev: Evenement) -> Evenement:
        self.historique.append(ev)
        if len(self.historique) > self.taille_max_historique:
            del self.historique[: len(self.historique) - self.taille_max_historique]
        for type_, fonction in list(self._abonnes):
            if type_ is not None and type_ != ev.type:
                continue
            try:
                resultat = fonction(ev)
                if asyncio.iscoroutine(resultat):
                    await resultat
            except Exception:  # un abonné en panne ne doit jamais bloquer les autres
                log.exception("Abonné en erreur pour %s", ev.type)
        return ev

    async def emettre(self, type_: str, source: str, **donnees) -> Evenement:
        """Raccourci : fabrique l'événement et le publie."""
        robot = donnees.pop("robot", None)
        conversation = donnees.pop("conversation", None)
        return await self.publier(
            Evenement(type=type_, source=source, donnees=donnees, robot=robot, conversation=conversation)
        )
