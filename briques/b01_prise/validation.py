"""Vérifier qu'une action respecte la prise universelle, la carte d'identité ET les plafonds de sécurité.

Utilisé deux fois : par le gardien (avant de délivrer le ticket) et par la prise (juste avant d'agir).
Un nombre doit être un vrai nombre fini ; une vitesse, une force ou une durée doit être strictement positive.
"""
from __future__ import annotations

import math
from typing import Any

from .actions import ACTIONS, ActionDemandee
from .carte import CarteIdentite
from .raisons import Raison

# Plafonds de sécurité par défaut (remplacés par reglages.yaml → securite). Toujours appliqués, même si la carte permet plus.
PLAFONDS_DEFAUT: dict[str, float] = {"vitesse": 0.3, "force": 15.0, "vitesse_relative": 1.0, "distance": 5.0}
# Paramètres qui doivent être strictement positifs.
STRICTEMENT_POSITIFS = {"vitesse", "force", "vitesse_relative", "duree_s"}
# Paramètres de distance relative, bornés par le plafond « distance ».
DISTANCES = {"dx", "dy"}
UNITES = {"vitesse": "m/s", "force": "N", "distance": "m"}


def est_fini(v: Any) -> bool:
    """Vrai nombre fini (rejette NaN, l'infini, et les entiers trop grands pour être des nombres à virgule)."""
    try:
        return math.isfinite(float(v))
    except (OverflowError, ValueError, TypeError):
        return False


def valider(action: ActionDemandee, carte: CarteIdentite, plafonds: dict[str, float] | None = None) -> list[Raison]:
    """Rend la liste des problèmes. Liste vide = action conforme."""
    plafonds = {**PLAFONDS_DEFAUT, **(plafonds or {})}
    definition = ACTIONS.get(action.nom)
    if definition is None:
        return [Raison(code="action_inconnue", details={"action": action.nom})]
    if not carte.sait(action.nom):
        return [Raison(code="absente_de_la_carte", details={"action": action.nom, "robot": carte.nom})]

    raisons: list[Raison] = []
    connus = {p.nom: p for p in definition.parametres}
    for nom in action.parametres:
        if nom not in connus:
            raisons.append(Raison(code="parametre_inconnu", details={"action": action.nom, "parametre": nom}))
    for p in definition.parametres:
        valeur = action.parametres.get(p.nom)
        if valeur is None:
            if p.obligatoire:
                raisons.append(Raison(code="parametre_manquant", details={"action": action.nom, "parametre": p.nom}))
            continue
        if p.type == "nombre":
            if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
                raisons.append(Raison(code="parametre_mauvais_type", details={"parametre": p.nom, "attendu": "nombre"}))
                continue
            if not est_fini(valeur) or (p.nom in STRICTEMENT_POSITIFS and valeur <= 0):
                raisons.append(Raison(code="valeur_invalide", details={"parametre": p.nom, "valeur": str(valeur)}))
                continue
            if p.limite:
                maxi = carte.limites.model_dump()[p.limite]
                if abs(valeur) > maxi:
                    raisons.append(Raison(code="au_dessus_de_la_limite",
                                          details={"parametre": p.nom, "valeur": valeur, "limite": maxi, "unite": p.unite}))
            plafond = plafonds.get("distance") if p.nom in DISTANCES else plafonds.get(p.nom)
            if plafond is not None and abs(valeur) > plafond:
                nom_limite = "distance" if p.nom in DISTANCES else p.nom
                raisons.append(Raison(code="au_dessus_du_defaut", details={
                    "parametre": nom_limite, "valeur": valeur, "limite": plafond, "unite": UNITES.get(nom_limite, "")}))
        elif not isinstance(valeur, str) or not valeur.strip():
            raisons.append(Raison(code="parametre_mauvais_type", details={"parametre": p.nom, "attendu": "texte"}))

    # Distance totale d'un déplacement relatif (dx et dy ensemble), bornée par le plafond.
    dx, dy = action.parametres.get("dx"), action.parametres.get("dy")
    if action.nom == "se_deplacer" and all(v is None or (not isinstance(v, bool) and est_fini(v)) for v in (dx, dy)):
        total = math.hypot(float(dx or 0), float(dy or 0))
        if total > plafonds["distance"] and not any(r.details.get("parametre") == "distance" for r in raisons):
            raisons.append(Raison(code="au_dessus_du_defaut", details={
                "parametre": "distance", "valeur": round(total, 2), "limite": plafonds["distance"], "unite": "m"}))

    if definition.un_parmi:
        presents = {k for k, v in action.parametres.items() if v is not None}
        # Il suffit qu'un groupe ait au moins une valeur (ex. un lieu, OU dx/dy).
        if not any(any(n in presents for n in groupe) for groupe in definition.un_parmi):
            raisons.append(Raison(code="parametre_manquant", details={"action": action.nom, "un_parmi": definition.un_parmi}))

    if action.nom == "rejouer_geste":
        nom = action.parametres.get("nom")
        if isinstance(nom, str) and nom not in carte.gestes:
            raisons.append(Raison(code="geste_inconnu", details={"geste": nom, "connus": carte.gestes}))

    # Si le plafond de sécurité est dépassé, inutile de citer aussi la limite de la carte pour le même paramètre.
    trop = {r.details.get("parametre") for r in raisons if r.code == "au_dessus_du_defaut"}
    return [r for r in raisons if not (r.code == "au_dessus_de_la_limite" and r.details.get("parametre") in trop)]
