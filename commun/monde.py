"""Lecture du monde (lieux, objets, noms dans chaque langue)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

CHEMIN_MONDE = Path(__file__).with_name("monde.yaml")


class Position(BaseModel):
    x: float
    y: float
    cap: float = 0.0


class Chose(BaseModel):
    id: str
    position: Position
    poids_kg: float = 0.0
    noms: dict[str, list[str]] = Field(default_factory=dict)

    def tous_les_noms(self) -> list[tuple[str, str]]:
        """(langue, nom) pour chaque nom connu."""
        return [(langue, n) for langue, liste in self.noms.items() for n in liste]


class PersonneSimulee(BaseModel):
    """Une personne imaginaire, pour le faux robot seulement (jamais avec un vrai robot)."""

    id: str
    position: Position


class Monde(BaseModel):
    taille: dict[str, float]
    depart: Position
    lieux: list[Chose]
    objets: list[Chose]
    personnes: list[PersonneSimulee] = Field(default_factory=list)  # simulées : voir monde.yaml

    def lieu(self, ident: str) -> Chose | None:
        return next((l for l in self.lieux if l.id == ident), None)

    def objet(self, ident: str) -> Chose | None:
        return next((o for o in self.objets if o.id == ident), None)

    def vue(self) -> dict[str, Any]:
        return self.model_dump()

    @classmethod
    def charger(cls, chemin: str | Path = CHEMIN_MONDE) -> "Monde":
        with open(chemin, encoding="utf-8") as f:
            return cls.model_validate(yaml.safe_load(f))
