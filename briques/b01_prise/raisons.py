"""Les raisons d'un refus, sous forme de code + détails.

Le code ne dépend d'aucune langue. Les phrases (dans la langue de la personne)
sont fabriquées plus tard, à partir du code, par commun/phrases.py.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Raison(BaseModel):
    code: str
    details: dict[str, Any] = Field(default_factory=dict)

    def __str__(self) -> str:
        if not self.details:
            return self.code
        return f"{self.code} {self.details}"


CODES = {
    "action_inconnue": "Cette action n'existe pas dans la prise universelle.",
    "absente_de_la_carte": "Ce robot ne sait pas faire cette action.",
    "parametre_manquant": "Il manque une précision obligatoire.",
    "parametre_inconnu": "Une précision ne correspond à rien de connu.",
    "parametre_mauvais_type": "Une précision n'a pas le bon format.",
    "valeur_invalide": "La valeur est nulle, négative ou n'est pas un vrai nombre.",
    "au_dessus_de_la_limite": "La valeur dépasse la limite de la carte d'identité.",
    "au_dessus_du_defaut": "La valeur dépasse la limite de sécurité par défaut.",
    "geste_inconnu": "Ce geste n'a pas été enregistré.",
    "sans_ticket": "L'action n'est pas passée par le gardien.",
    "ticket_invalide": "Le ticket du gardien est faux, périmé ou déjà utilisé.",
    "ticket_avant_stop": "Un « stop » est passé après la vérification du gardien : l'action d'avant ne part plus.",
    "arret_urgence_actif": "L'arrêt d'urgence est actif. Un humain doit réarmer le robot.",
    "liaison_perdue": "Plus de liaison avec le robot.",
    "robot_refuse": "Le robot a refusé l'action.",
    "delai_depasse": "Le robot n'a pas répondu à temps.",
    "regle_gardien": "Une règle du gardien interdit cette action.",
    "robot_occupe": "Le robot fait déjà une action longue. Attendre la fin, ou dire « stop ».",
    # Étape 4 — les règles du gardien (briques/b07_gardien/regles.yaml). Verdict « non » :
    "zone_interdite": "Le lieu d'arrivée est dans une zone interdite.",
    "chemin_zone_interdite": "Le chemin (en ligne droite) passe par une zone interdite.",
    "hors_zone_permise": "Le lieu d'arrivée est en dehors de la zone permise (la halle).",
    "trop_pres_personne": "Le robot serait trop près d'une personne (en chemin, ou pendant un geste).",
    "objet_interdit": "Le robot ne doit jamais toucher cet objet.",
    "trop_lourd": "L'objet est plus lourd que la limite (carte d'identité ou règle).",
    "lieu_inconnu": "Le lieu n'est pas dans le monde : le gardien ne peut pas vérifier le chemin.",
    "refuse_par_humain": "Un humain a répondu non à la demande du gardien.",
    "demande_perimee": "La demande à un humain est trop ancienne, ou a été annulée (stop).",
    # Verdict « humain » : l'action attend l'accord d'un humain (écran) :
    "objet_fragile": "L'objet est fragile : un humain doit d'abord donner son accord.",
    "humain_requis": "Une règle demande l'accord d'un humain pour cette action.",
    "accord_agent": "La demande vient d'un agent d'IA : un humain doit d'abord accepter.",
    "position_inconnue": "Le gardien ne sait pas où est le robot : un humain doit d'abord donner son accord.",
    "personnes_inconnues": "Le gardien ne sait pas où sont les personnes : un humain doit d'abord donner son accord.",
    "poids_inconnu": "Le poids de l'objet est inconnu : un humain doit d'abord donner son accord.",
}

# Les codes qui ne disent pas « non » mais « demande à un humain » (verdict « humain » du gardien).
CODES_HUMAIN = {"objet_fragile", "humain_requis", "accord_agent", "position_inconnue", "personnes_inconnues", "poids_inconnu"}


class ActionRefusee(Exception):
    def __init__(self, raisons: list[Raison]):
        self.raisons = raisons
        super().__init__("; ".join(str(r) for r in raisons))
