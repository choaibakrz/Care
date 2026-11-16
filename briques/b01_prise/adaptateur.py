"""Brique 1 — Ce que tout adaptateur doit savoir faire.

Un adaptateur traduit la prise universelle vers le kit d'un fabricant (ou vers le faux robot).
Il ne décide rien : il exécute ce que la prise lui transmet, après le gardien.
Règle absolue : seule la prise (prise.py) appelle ces méthodes. Un test le vérifie.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel, Field

from .actions import ActionDemandee
from .carte import CarteIdentite

Statut = Literal["en_attente", "en_cours", "reussie", "echouee", "annulee"]
STATUTS_FINAUX = ("reussie", "echouee", "annulee")


class SuiviAction(BaseModel):
    id: str
    action: ActionDemandee
    statut: Statut = "en_attente"
    progression: float = 0.0  # de 0 à 1
    message: str = ""
    code_erreur: str | None = None

    @property
    def finie(self) -> bool:
        return self.statut in STATUTS_FINAUX


class EtatRobot(BaseModel):
    batterie_pct: float | None = None
    erreurs: list[str] = Field(default_factory=list)
    position: dict[str, float] = Field(default_factory=dict)  # x, y (m), cap (degrés), si connus
    objet_tenu: str | None = None
    en_mouvement: bool = False
    liaison_ok: bool = True
    arret_urgence_actif: bool = False
    extra: dict[str, Any] = Field(default_factory=dict)


class LiaisonPerdue(Exception):
    """Le robot ne répond plus."""


class ActionImpossible(Exception):
    """Le robot refuse ou ne peut pas faire l'action (avec une explication)."""

    def __init__(self, code: str, message: str = ""):
        self.code = code
        super().__init__(message or code)


class Adaptateur(ABC):
    """Modèle commun. Copier briques/b03_adaptateurs/modele_vide pour un nouveau robot."""

    @abstractmethod
    def carte(self) -> CarteIdentite: ...

    async def connecter(self) -> None:
        """Ouvrir la liaison avec le robot. Ne doit jamais faire bouger le robot."""

    async def deconnecter(self) -> None:
        """Fermer la liaison. Doit d'abord arrêter le robot."""

    @abstractmethod
    async def demarrer(self, action: ActionDemandee) -> str:
        """Lancer l'action et rendre tout de suite un identifiant de suivi."""

    @abstractmethod
    async def suivre(self, ident: str) -> SuiviAction: ...

    @abstractmethod
    async def annuler(self, ident: str) -> None: ...

    @abstractmethod
    async def arret_urgence(self) -> None:
        """Tout arrêter, immédiatement. Ne doit JAMAIS lever d'erreur ni attendre."""

    @abstractmethod
    async def rearmer(self) -> None:
        """Après un arrêt d'urgence : autoriser à nouveau les actions (décision humaine)."""

    @abstractmethod
    async def etat_robot(self) -> EtatRobot: ...

    async def battement(self) -> None:
        """Signe de vie envoyé régulièrement par la prise (chien de garde).
        Si le robot n'en reçoit plus, il doit s'arrêter seul."""
