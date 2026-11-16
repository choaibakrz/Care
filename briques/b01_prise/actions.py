"""Brique 1 — La liste des actions de la prise universelle.

C'est LA liste que tout robot peut savoir faire, dite de la même façon pour tous.
Le cerveau ne choisit que dans cette liste, et seulement ce que la carte d'identité du robot permet.
Toute modification ici doit être recopiée dans PRISE.md (un test le vérifie).
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

TypeParam = Literal["texte", "nombre", "langue"]


class Parametre(BaseModel):
    nom: str
    type: TypeParam
    obligatoire: bool = False
    unite: str | None = None
    # Nom de la limite de la carte d'identité à ne pas dépasser (ex. "vitesse_max_m_s").
    limite: str | None = None
    explication: str = ""


class DefinitionAction(BaseModel):
    nom: str
    explication: str
    longue: bool = False  # une action longue peut être suivie et annulée
    parametres: list[Parametre] = Field(default_factory=list)
    # Au moins un de ces groupes doit être rempli (ex. un lieu OU un déplacement relatif).
    un_parmi: list[list[str]] = Field(default_factory=list)
    exemple: dict[str, Any] = Field(default_factory=dict)  # sert au test de conformité


def _p(nom, type_, obligatoire=False, unite=None, limite=None, explication=""):
    return Parametre(nom=nom, type=type_, obligatoire=obligatoire, unite=unite, limite=limite, explication=explication)


ACTIONS: dict[str, DefinitionAction] = {
    a.nom: a
    for a in [
        DefinitionAction(
            nom="se_deplacer",
            explication="Aller à un lieu nommé, ou avancer de quelques mètres.",
            longue=True,
            parametres=[
                _p("lieu", "texte", explication="Nom d'un lieu connu (voir commun/monde.yaml)."),
                _p("dx", "nombre", unite="m", explication="Déplacement vers l'avant (relatif)."),
                _p("dy", "nombre", unite="m", explication="Déplacement vers la gauche (relatif)."),
                _p("vitesse", "nombre", unite="m/s", limite="vitesse_max_m_s"),
            ],
            un_parmi=[["lieu"], ["dx", "dy"]],
            exemple={"dx": 0.2, "dy": 0.0},
        ),
        DefinitionAction(
            nom="regarder",
            explication="Tourner la tête ou la caméra vers une cible.",
            parametres=[_p("cible", "texte", obligatoire=True, explication="Lieu, objet, personne ou direction.")],
            exemple={"cible": "devant"},
        ),
        DefinitionAction(
            nom="ecouter",
            explication="Écouter avec les micros du robot pendant un moment.",
            parametres=[_p("duree_s", "nombre", unite="s")],
            exemple={"duree_s": 0.5},
        ),
        DefinitionAction(
            nom="parler",
            explication="Dire un texte par le haut-parleur du robot.",
            parametres=[_p("texte", "texte", obligatoire=True), _p("langue", "langue")],
            exemple={"texte": "test", "langue": "fr"},
        ),
        DefinitionAction(
            nom="saisir",
            explication="Prendre un objet nommé.",
            longue=True,
            parametres=[
                _p("objet", "texte", obligatoire=True),
                _p("force", "nombre", unite="N", limite="force_max_n"),
            ],
            exemple={"objet": "objet_test"},
        ),
        DefinitionAction(
            nom="poser",
            explication="Poser l'objet tenu à un lieu (ou ici).",
            longue=True,
            parametres=[_p("lieu", "texte", explication="Lieu nommé, ou « ici ».")],
            exemple={"lieu": "ici"},
        ),
        DefinitionAction(
            nom="montrer",
            explication="Montrer du doigt (ou du corps) une cible.",
            parametres=[_p("cible", "texte", obligatoire=True)],
            exemple={"cible": "devant"},
        ),
        DefinitionAction(
            nom="rejouer_geste",
            explication="Rejouer un geste enregistré, par son nom.",
            longue=True,
            parametres=[
                _p("nom", "texte", obligatoire=True),
                _p("vitesse_relative", "nombre", explication="1 = vitesse enregistrée ; jamais plus que 1 par défaut."),
            ],
            exemple={"nom": "saluer"},
        ),
        DefinitionAction(
            nom="arreter",
            explication="S'arrêter tout de suite (arrêt normal). Toujours permis.",
        ),
        DefinitionAction(
            nom="etat",
            explication="Dire son état : batterie, erreurs, position, objet tenu.",
        ),
    ]
}

# Toute carte d'identité doit contenir ces deux capacités.
CAPACITES_OBLIGATOIRES = ("arreter", "etat")


class ActionDemandee(BaseModel):
    """Ce que le cerveau (ou un agent, ou un humain) demande. Jamais un ordre direct aux moteurs."""

    nom: str
    parametres: dict[str, Any] = Field(default_factory=dict)

    def resume(self) -> str:
        if not self.parametres:
            return self.nom
        details = ", ".join(f"{k}={v}" for k, v in self.parametres.items())
        return f"{self.nom}({details})"
