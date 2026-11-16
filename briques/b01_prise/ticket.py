"""Le ticket d'action : la preuve qu'une action est passée par le gardien.

Le gardien possède le guichet (et sa clé secrète, tirée au hasard à chaque démarrage).
La prise ne reçoit que la fonction `verifier` : elle peut contrôler un ticket, pas en fabriquer.
Un ticket vaut pour UNE action, sur UN robot, une seule fois, pendant 5 secondes.
La prise vérifie une COPIE de l'action et n'utilise que cette copie : modifier l'action après coup ne sert à rien.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid
from dataclasses import dataclass

from .actions import ActionDemandee

DUREE_VALIDITE_S = 5.0


@dataclass(frozen=True)
class Ticket:
    action: ActionDemandee
    robot: str
    numero: str
    emis_a: float
    signature: str

    def copie(self) -> "Ticket":
        """Même ticket, avec une copie indépendante de l'action."""
        return Ticket(action=self.action.model_copy(deep=True), robot=self.robot, numero=self.numero,
                      emis_a=self.emis_a, signature=self.signature)


def _contenu(action: ActionDemandee, robot: str, numero: str, emis_a: float) -> bytes:
    return json.dumps([action.nom, action.parametres, robot, numero, round(emis_a, 6)], sort_keys=True, default=str).encode()


class Guichet:
    def __init__(self) -> None:
        self.__cle = os.urandom(32)
        self._utilises: set[str] = set()

    def emettre(self, action: ActionDemandee, robot: str) -> Ticket:
        numero = uuid.uuid4().hex
        emis_a = time.monotonic()
        copie = action.model_copy(deep=True)
        sig = hmac.new(self.__cle, _contenu(copie, robot, numero, emis_a), hashlib.sha256).hexdigest()
        return Ticket(action=copie, robot=robot, numero=numero, emis_a=emis_a, signature=sig)

    def verifier(self, ticket: object, robot: str) -> str | None:
        """Rend None si le ticket est bon pour ce robot, sinon le code de la raison."""
        if type(ticket) is not Ticket:  # pas de sous-classe déguisée
            return "sans_ticket"
        attendu = hmac.new(self.__cle, _contenu(ticket.action, ticket.robot, ticket.numero, ticket.emis_a),
                           hashlib.sha256).hexdigest()
        if not hmac.compare_digest(attendu, ticket.signature) or ticket.robot != robot:
            return "ticket_invalide"
        if time.monotonic() - ticket.emis_a > DUREE_VALIDITE_S or ticket.numero in self._utilises:
            return "ticket_invalide"
        self._utilises.add(ticket.numero)
        return None
