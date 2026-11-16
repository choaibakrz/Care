"""Quand Iris dit non, la tête du petit robot fait « non ». Une RÉACTION, pas un ordre de plus donné par quelqu'un.

NON TESTÉ SUR VRAI ROBOT. Testé sur faux robot (la doublure du Reachy Mini).

Demande de Hiba (15.11.2026) : que les robots travaillent vraiment, sans personne pour les manipuler.
Ce que fait cette pièce, et rien d'autre :
- elle écoute le bus (le fil où chaque brique écrit ce qu'elle fait) ;
- quand la chaîne DIT UN REFUS à quelqu'un (« Je ne peux pas… », le gardien qui dit non), elle demande UN geste « non » ;
- cette demande suit le chemin de tout le monde : gardien (ticket) → prise → adaptateur. Elle ne touche jamais le robot.
  Si le gardien ou la prise refusent (arrêt d'urgence, robot occupé…), il ne se passe rien, et c'est noté dans le journal.

ÉTEINTE PAR DÉFAUT. Pourquoi : la règle n° 1 du gardien (regles.yaml, « distance_personnes ») dit que le robot reste à
1 mètre des personnes quand il fait un geste, et que, s'il ne sait pas où sont les gens, il demande à un humain. Posée
sur une table à côté d'une personne, la tête ne peut donc faire « non » qu'avec l'accord d'un humain. Cette pièce ne
contourne pas le gardien : si le gardien ne dit pas « oui » tout de suite, elle abandonne (et retire sa demande, pour
ne pas encombrer l'écran). Elle ne sert que si Hiba et le responsable sécurité décident un jour que ce petit geste de
tête est permis sans accord. Changer cette règle n'est PAS le travail de cette pièce.
Pour l'allumer : reglages.yaml → interrupteurs → non_de_la_tete → actif: true (c'est un réglage : décision de Hiba).

Elle ne fait rien du tout si la carte du robot n'a pas le geste « non » (le faux robot, un bras, un chien : rien ne change).
Elle ne réagit jamais à ses propres demandes (pas de boucle), ni pendant un arrêt d'urgence, ni quand un humain a pris
la main sur l'écran (c'est lui qui commande), ni quand c'est la personne qui a dit « non » à « vous confirmez ? ».

Limites connues, vues par le relecteur du 15.11.2026 (interrupteur allumé) :
- avec les règles du projet, chaque refus laisse UNE trace à l'écran : le gardien annonce « aide demandée » avant
  que la demande soit retirée (une carte « en attente d'un humain » peut apparaître, et le compteur d'aides monte) ;
- pendant le geste (quatre secondes), une autre demande de mouvement de la personne échoue (« robot occupé »).
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

from briques.b01_prise.actions import ActionDemandee
from briques.b01_prise.raisons import ActionRefusee

GESTE_DU_REFUS = "non"  # le nom du geste dans la carte du robot
PREFIXE = "reaction-"  # le début du numéro de conversation de chaque réaction : on les reconnaît dans le journal
VITESSE = 1.0  # la vitesse demandée ; la liaison ne fait jamais plus vite que sa propre limite


class ReactionsDeLaTete:
    def __init__(self, bus: Any, gardien: Any, prise: Any, actif: bool = False, humain_a_la_main: Any = None) -> None:
        self.bus, self.gardien, self.prise, self.actif = bus, gardien, prise, actif
        self.humain_a_la_main = humain_a_la_main or (lambda: False)  # brique 11 : quelqu'un commande par l'écran ?
        self.faites = 0  # pour les essais et la fiche : combien de « non » ont vraiment été lancés
        self._taches: set[asyncio.Task] = set()
        bus.abonner(self._sur_reponse, "reponse_dite")

    def _concernee(self) -> bool:
        carte = self.prise.carte()
        return self.actif and "rejouer_geste" in carte.capacites and GESTE_DU_REFUS in carte.gestes

    def _sur_reponse(self, ev: Any) -> None:
        """Appelée pour chaque phrase dite. Ne fait qu'une chose : préparer la réaction À CÔTÉ, sans retarder la chaîne."""
        if ev.donnees.get("genre") != "refus" or str(ev.conversation or "").startswith(PREFIXE):
            return
        if ev.donnees.get("cle") == "confirmation_annulee":  # c'est la PERSONNE qui a dit non : le robot n'a rien refusé
            return
        if not self._concernee() or self.prise.arret_urgence_actif or self.humain_a_la_main():
            return
        tache = asyncio.get_running_loop().create_task(self._dire_non(str(ev.conversation or "")))
        self._taches.add(tache)
        tache.add_done_callback(self._taches.discard)

    async def _dire_non(self, apres: str) -> None:
        conv = f"{PREFIXE}{uuid.uuid4().hex[:8]}"
        action = ActionDemandee(nom="rejouer_geste", parametres={"nom": GESTE_DU_REFUS, "vitesse_relative": VITESSE})
        try:
            _, ticket = await self.gardien.verifier(action, self.prise.carte(), conversation=conv)
            if ticket is None:  # le gardien dit non, ou demande un humain : on abandonne, et on retire la demande
                self.gardien.oublier_demandes(lambda demande: demande.conversation == conv)
                raise ActionRefusee([])
            await self.prise.executer(ticket, conversation=conv)
            self.faites += 1
            await self.bus.emettre("note", "reactions_tete", robot=self.prise.robot, conversation=conv,
                                   texte=f"la tête fait « non » après un refus (conversation {apres})")
        except ActionRefusee as refus:
            await self.bus.emettre("note", "reactions_tete", robot=self.prise.robot, conversation=conv,
                                   texte=f"pas de « non » de la tête : le gardien ou la prise ne le permettent pas ({refus})")

    async def attendre(self) -> None:
        """Pour les essais : attendre que les réactions en cours soient lancées."""
        while self._taches:
            await asyncio.gather(*list(self._taches), return_exceptions=True)
