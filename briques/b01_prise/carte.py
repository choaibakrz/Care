"""Brique 1 — La carte d'identité d'un robot : ce qu'il sait faire et ses limites."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator

from .actions import ACTIONS, CAPACITES_OBLIGATOIRES


class Limites(BaseModel):
    vitesse_max_m_s: float = Field(0.0, ge=0, description="Vitesse de déplacement maximale")
    portee_max_m: float = Field(0.0, ge=0, description="Distance maximale pour saisir ou montrer")
    charge_max_kg: float = Field(0.0, ge=0, description="Poids maximal d'un objet tenu")
    force_max_n: float = Field(0.0, ge=0, description="Force de serrage maximale")


class CarteIdentite(BaseModel):
    id: str
    nom: str
    genre: Literal["humanoide", "chien", "bras", "roues", "autre"]
    fabricant: str = "inconnu"
    modele: str = "inconnu"
    capacites: list[str]
    limites: Limites = Field(default_factory=Limites)
    gestes: list[str] = Field(default_factory=list)  # gestes enregistrés, rejouables par leur nom
    vrai_robot: bool = False  # False = faux robot (simulation). Affiché partout.
    position_fixe: str | None = None  # pour un robot qui ne bouge pas (bras) : le lieu où il est posé
    remarques: str = ""

    @field_validator("capacites")
    @classmethod
    def _capacites_connues(cls, v: list[str]) -> list[str]:
        inconnues = [c for c in v if c not in ACTIONS]
        if inconnues:
            raise ValueError(f"Capacités absentes de la prise universelle : {inconnues}")
        manquantes = [c for c in CAPACITES_OBLIGATOIRES if c not in v]
        if manquantes:
            raise ValueError(f"Toute carte doit contenir {list(CAPACITES_OBLIGATOIRES)} ; il manque {manquantes}")
        return v

    def sait(self, action: str) -> bool:
        return action in self.capacites

    def mention_test(self) -> str:
        return "testé sur vrai robot" if self.vrai_robot else "testé sur faux robot"

    def resume(self) -> dict[str, Any]:
        """Ce que le robot sait faire, et ce qu'il ne sait pas faire (idée 3 : la carte parlée)."""
        return {
            "sait_faire": list(self.capacites),
            "ne_sait_pas_faire": [a for a in ACTIONS if a not in self.capacites],
            "limites": self.limites.model_dump(),
            "gestes": list(self.gestes),
        }

    @classmethod
    def charger(cls, chemin: str | Path) -> "CarteIdentite":
        with open(chemin, encoding="utf-8") as f:
            return cls.model_validate(yaml.safe_load(f))
