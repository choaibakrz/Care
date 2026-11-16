"""Brique 6 — La prise du cerveau : une seule forme, plusieurs modèles possibles.

Un cerveau reçoit une demande (texte + langue), la carte d'identité du robot et le monde.
Il rend une Décision. Il ne commande JAMAIS les moteurs : au mieux, il propose une action
de la prise universelle, que le gardien vérifiera ensuite.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel, Field

from briques.b01_prise.actions import ActionDemandee
from briques.b01_prise.carte import CarteIdentite
from commun.monde import Monde

Genre = Literal["action", "question", "hors_carte", "inconnu", "discussion"]


class Decision(BaseModel):
    genre: Genre
    action: ActionDemandee | None = None  # seulement si genre == "action"
    options: list[ActionDemandee] = Field(default_factory=list)  # si plusieurs actions possibles
    question: str | None = None  # clé de phrase (ex. "question_lieu") ou texte libre
    action_hors_carte: str | None = None  # ce qui a été compris mais que le robot ne sait pas faire
    texte: str | None = None  # réponse libre (discussion)
    langue_devinee: str | None = None
    confiance: float = 0.0
    cerveau: str = ""


class Cerveau(ABC):
    nom: str = "cerveau"

    @abstractmethod
    async def decider(self, texte: str, langue: str | None, carte: CarteIdentite, monde: Monde) -> Decision: ...

    async def demarrer(self) -> None:
        """Charger le modèle si besoin."""

    async def arreter(self) -> None: ...


def garde_fou_carte(decision: Decision, carte: CarteIdentite) -> Decision:
    """Filet de sécurité commun à tous les cerveaux : jamais d'action absente de la carte."""
    if decision.genre == "action" and decision.action and not carte.sait(decision.action.nom):
        return decision.model_copy(update={"genre": "hors_carte", "action_hors_carte": decision.action.nom, "action": None})
    if decision.options:
        gardees = [o for o in decision.options if carte.sait(o.nom)]
        decision = decision.model_copy(update={"options": gardees})
    return decision
