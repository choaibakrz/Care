"""Les directions que la tête du robot connaît, ajoutées au monde pour que le cerveau entende leurs noms.

NON TESTÉ SUR VRAI ROBOT. Testé sur faux robot.

Le cerveau ne choisit une cible (« regarde la patiente ») que parmi les lieux et les objets du monde. Un robot posé sur
une table, comme le Reachy Mini, a ses propres directions : patient, collègue, soignant (son fichier directions.yaml).
Cette pièce les ajoute au monde, SEULEMENT quand ce robot est le robot du système. Avec un autre robot : rien ne change.
Elle n'envoie rien au robot et ne décide rien : elle donne des mots au cerveau. L'ordre, lui, suit le chemin de tout
le monde : cerveau → gardien (ticket) → prise → adaptateur.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from briques.b03_adaptateurs.registre import DOSSIER_ROBOTS, nom_valide
from commun.monde import Chose, Monde, Position

LIEU_DE_LA_TABLE = "table"  # les directions sont rangées là dans le plan : le robot est posé sur la table


def ajouter_les_directions(monde: Monde, adaptateur: str, dossier: Path = DOSSIER_ROBOTS) -> Monde:
    """Rend le même monde, avec les directions nommées du robot `adaptateur` (s'il en a). Jamais d'erreur :
    un fichier absent ou abîmé = aucun nom ajouté (la tête saura quand même regarder « devant »)."""
    if nom_valide(adaptateur) is not None:
        return monde
    fichier = Path(dossier) / adaptateur / "directions.yaml"
    try:
        lu = yaml.safe_load(fichier.read_text(encoding="utf-8")) or {}
        noms, directions = dict(lu.get("noms") or {}), dict(lu.get("directions") or {})
    except (OSError, yaml.YAMLError, AttributeError, TypeError, ValueError):
        return monde
    table = monde.lieu(LIEU_DE_LA_TABLE)
    position = table.position if table else Position(x=0.0, y=0.0)
    connus = {chose.id for chose in monde.lieux + monde.objets}
    for nom, par_langue in noms.items():
        if nom not in directions or nom in connus or not isinstance(par_langue, dict):
            continue  # un nom sans angle ne sert à rien ; un lieu déjà connu n'est jamais remplacé
        mots = {str(langue): [str(mot) for mot in liste] for langue, liste in par_langue.items() if isinstance(liste, list)}
        monde.lieux.append(Chose(id=str(nom), position=position.model_copy(), noms=mots))
    return monde
