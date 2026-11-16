"""Les événements : chaque chose qui se passe devient un petit message daté.

Tout passe par le bus (commun/bus.py) et tout finit dans la boîte noire (brique 12).
Ajouter un type d'événement : l'ajouter à TYPES ci-dessous, avec une phrase d'explication.
"""
from __future__ import annotations

import itertools
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

# Liste fermée des types d'événements. Un type inconnu est refusé : on évite les fautes de frappe.
TYPES: dict[str, str] = {
    "session_debut": "Le programme démarre ; on note le robot et les réglages.",
    "session_fin": "Le programme s'arrête proprement.",
    "parole_entendue": "Une personne a dit quelque chose (texte, langue, confiance).",
    "demande_comprise": "Le cerveau a choisi quoi faire (action, question ou discussion).",
    "question_posee": "Le robot pose une question au lieu d'agir (brique 8).",
    "aide_demandee": "Le robot lève la main : il a besoin d'un humain.",
    "gardien_decision": "Le gardien a dit oui, non ou « demande à un humain ».",
    "action_demarree": "Une action est partie vers le robot.",
    "action_progression": "Une action longue avance (0 à 100 %).",
    "action_terminee": "Une action est finie : réussie, ratée ou annulée.",
    "action_refusee": "La prise a refusé une action (absente de la carte, hors limites, sans ticket).",
    "reponse_dite": "Le robot répond à la personne (texte, langue).",
    "arret_urgence": "Arrêt d'urgence demandé. Passe avant tout.",
    "panne": "Une panne a été provoquée ou constatée.",
    "reparation": "La panne est réparée.",
    "etat_robot": "Le robot donne son état (batterie, erreurs, position).",
    "pilotage_humain": "Un humain reprend ou rend la main (brique 11).",
    "regle_changee": "Une règle du gardien a été changée en direct.",
    "note": "Remarque libre (répétition, test, commentaire).",
    "parole_finie": "Les oreilles ont détecté la fin d'une phrase (durée, attente du silence).",
    "transcription": "L'écoute a transformé la phrase en texte (langue, confiance, temps de calcul).",
    "mot_d_appel": "Le mot d'appel a été entendu : le robot écoute pendant un moment.",
    "interruption": "La personne a parlé pendant que le robot parlait : le robot se tait.",
    "voix_debut": "Le robot commence à dire sa réponse (temps depuis la fin de la phrase).",
    "cerveau_secours": "Le cerveau est trop lent, éteint ou hors formulaire : on passe au cerveau suivant.",
    "cerveau_serveur": "Un cerveau de secours est lancé ou arrêté sur cet ordinateur (pas une panne).",
    "confirmation_demandee": "Avant une action à risque, le robot répète l'ordre et attend un « oui ».",
    "scenario_debut": "Le chef de démonstration commence un scénario (titre, étapes, répétition, pannes prévues).",
    "scenario_etape": "Une étape du scénario commence ou finit (nom, résultat, cause d'un raté, durée).",
    "plan_b": "Une étape a raté : le chef essaie un moyen de secours (tablette, main humaine, mode local, sauter).",
    "scenario_fin": "Le scénario est fini ou interrompu (durée, étapes réussies, rattrapées, ratées).",
    "aide_recue": "Un humain a aidé le robot : demande acceptée ou refusée, ou mot appris (brique 8).",
    "internet_coupe": "Bouton « Internet coupé » de l'écran : sorties vers Internet coupées, ou rétablies (brique 13).",
    "mode_silence": "Mode silence de l'écran : la voix passe en sous-titres seulement, ou revient (brique 13).",
    "porte_agents": "Porte des agents (brique 14) : un agent d'IA se branche, ou son ordre est refusé avant le cerveau.",
    "yeux": "Les yeux (brique 5) : démarrage, caméra en panne ou revenue, personnes données ou non au gardien, objet cherché vu ou pas.",
}

_compteur = itertools.count(1)


def maintenant_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class Evenement(BaseModel):
    """Un événement. `donnees` contient le détail, propre à chaque type."""

    type: str
    source: str  # qui l'envoie : "cerveau", "gardien", "prise", "faux_robot", "ecran"...
    donnees: dict[str, Any] = Field(default_factory=dict)
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    numero: int = Field(default_factory=lambda: next(_compteur))
    heure: str = Field(default_factory=maintenant_iso)  # heure lisible (UTC)
    t: float = Field(default_factory=time.monotonic)  # horloge interne, pour mesurer les durées
    robot: str | None = None
    conversation: str | None = None  # relie une demande à toutes ses suites

    def model_post_init(self, __context: Any) -> None:
        if self.type not in TYPES:
            raise ValueError(f"Type d'événement inconnu : {self.type!r}. Ajoute-le dans commun/evenements.py")
