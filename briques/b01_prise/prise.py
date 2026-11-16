"""Brique 1 — La prise universelle.

Le seul endroit du code qui parle à un adaptateur. Elle :
- refuse toute action sans ticket valide du gardien (pour CE robot) ;
- refuse toute action absente de la carte, hors limites de la carte ou au-dessus des plafonds de sécurité ;
- n'accepte qu'UNE action longue à la fois ;
- suit et annule les actions longues ; si elle perd le fil d'une action, elle déclenche l'arrêt d'urgence ;
- laisse TOUJOURS passer l'arrêt d'urgence, sans ticket, et vérifie ensuite que le robot s'est bien arrêté ;
- n'accepte jamais de refuser « arreter » ;
- envoie un signe de vie régulier au robot (chien de garde côté robot).
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable

from commun.bus import Bus

from .actions import ACTIONS, ActionDemandee
from .adaptateur import ActionImpossible, Adaptateur, EtatRobot, LiaisonPerdue, SuiviAction
from .carte import CarteIdentite
from .raisons import ActionRefusee, Raison
from .ticket import Ticket
from .validation import valider

log = logging.getLogger("prise")
DELAI_PERTE_SUIVI_S = 1.0  # sans nouvelles d'une action pendant 1 s : on la déclare perdue (arrêt d'urgence)


class Prise:
    def __init__(
        self,
        adaptateur: Adaptateur,
        verificateur: Callable[[object, str], str | None],
        bus: Bus,
        delai_reponse_s: float = 2.0,
        periode_battement_s: float = 0.2,
        plafonds: dict[str, float] | None = None,
    ) -> None:
        self.__adaptateur = adaptateur  # nom « privé » : personne d'autre ne doit l'utiliser
        self._verifier_ticket = verificateur
        self.bus = bus
        self.delai = delai_reponse_s
        self.periode_battement = periode_battement_s
        self.plafonds = plafonds or {}
        self._suivis: dict[str, SuiviAction] = {}
        self._taches: dict[str, asyncio.Task] = {}
        self._fond: set[asyncio.Task] = set()
        self._demarrage_long = False  # place réservée pour une action longue en train de démarrer
        self._battement: asyncio.Task | None = None
        self.arret_urgence_actif = False
        self._numero_arret = 0  # augmente à chaque arrêt d'urgence (protège le réarmement)
        # Heure du dernier « arreter » ou arrêt d'urgence : un ticket fabriqué AVANT ne vaut plus rien (un « stop »
        # passé entre le gardien et la prise ne doit jamais être doublé par l'action d'avant).
        self._dernier_arret_a = float("-inf")
        self.liaison_ok = True
        self._carte = adaptateur.carte()

    # ---------- informations ----------
    def carte(self) -> CarteIdentite:
        return self._carte

    @property
    def robot(self) -> str:
        return self._carte.id

    def action_longue_en_cours(self) -> SuiviAction | None:
        return next((s for s in self._suivis.values() if not s.finie and ACTIONS[s.action.nom].longue), None)

    def _occupe(self) -> str | None:
        if self._demarrage_long:
            return "demarrage"
        en_cours = self.action_longue_en_cours()
        return en_cours.action.nom if en_cours else None

    # ---------- cycle de vie ----------
    async def connecter(self) -> None:
        await self._appel(self.__adaptateur.connecter())
        self._battement = asyncio.create_task(self._boucle_battement())

    async def deconnecter(self) -> None:
        if self._battement:
            self._battement.cancel()
        for t in list(self._taches.values()) + list(self._fond):
            t.cancel()
        try:
            await asyncio.wait_for(self.__adaptateur.deconnecter(), self.delai)
        except Exception:
            log.warning("Déconnexion incomplète", exc_info=True)

    async def _boucle_battement(self) -> None:
        while True:
            try:
                await asyncio.wait_for(self.__adaptateur.battement(), self.delai)
                if not self.liaison_ok:
                    self.liaison_ok = True
                    await self.bus.emettre("reparation", "prise", robot=self.robot, quoi="liaison")
            except (LiaisonPerdue, asyncio.TimeoutError):
                if self.liaison_ok:
                    self.liaison_ok = False
                    await self.bus.emettre("panne", "prise", robot=self.robot, quoi="liaison_perdue")
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Battement en erreur")
            await asyncio.sleep(self.periode_battement)

    # ---------- agir ----------
    async def executer(self, ticket: Ticket, conversation: str | None = None) -> SuiviAction:
        """Lancer une action. Seul chemin pour faire agir le robot (hors arrêt d'urgence)."""
        # « arreter » : on arrête d'abord tout, quoi qu'il arrive ensuite (même ticket faux).
        if type(ticket) is Ticket and ticket.action.nom == "arreter":
            self._dernier_arret_a = time.monotonic()
            await self.arreter_tout(conversation=conversation)

        # On travaille sur une COPIE : modifier le ticket ou l'action après coup ne change rien.
        copie = ticket.copie() if type(ticket) is Ticket else ticket
        code = self._verifier_ticket(copie, self.robot)
        action = copie.action if type(copie) is Ticket else None
        if code:
            await self._refuser(action, [Raison(code=code)], conversation)
        assert action is not None

        if action.nom == "arreter":
            action = ActionDemandee(nom="arreter")  # les précisions éventuelles sont ignorées, jamais refusées
        else:
            if copie.emis_a <= self._dernier_arret_a:  # vérifié par le guichet : emis_a est signé
                await self._refuser(action, [Raison(code="ticket_avant_stop")], conversation)
            if self.arret_urgence_actif:
                await self._refuser(action, [Raison(code="arret_urgence_actif")], conversation)
            raisons = valider(action, self._carte, self.plafonds)
            if raisons:
                await self._refuser(action, raisons, conversation)
            occupe = self._occupe()
            if ACTIONS[action.nom].longue and occupe:
                await self._refuser(action, [Raison(code="robot_occupe", details={"en_cours": occupe})], conversation)

        # Réserver la place AVANT d'attendre le robot (aucune attente entre le contrôle et la réservation).
        reserve = ACTIONS[action.nom].longue
        if reserve:
            self._demarrage_long = True
        try:
            try:
                ident = await self._appel(self.__adaptateur.demarrer(action.model_copy(deep=True)))
            except Exception:
                if action.nom == "arreter":
                    # Un « stop » que le robot refuse ou ne confirme pas : on passe à l'arrêt d'urgence (jamais d'erreur
                    # inexpliquée sur le chemin de l'arrêt). La raison est ensuite donnée comme pour un refus.
                    await self.arret_urgence(raison="arret_non_confirme", qui="prise")
                raise
        except ActionImpossible as e:
            await self._refuser(action, [Raison(code="robot_refuse", details={"message": str(e), "code": e.code})], conversation)
        except LiaisonPerdue:
            await self._refuser(action, [Raison(code="liaison_perdue")], conversation)
        except asyncio.TimeoutError:
            # Le robot est peut-être parti sans qu'on puisse le suivre : on l'arrête.
            await self.arret_urgence(raison="demarrage_sans_reponse", qui="prise")
            await self._refuser(action, [Raison(code="delai_depasse")], conversation)
        finally:
            if reserve:
                self._demarrage_long = False

        suivi = SuiviAction(id=ident, action=action, statut="en_cours")
        self._suivis[ident] = suivi
        await self.bus.emettre(
            "action_demarree", "prise", robot=self.robot, conversation=conversation,
            id_action=ident, action=action.model_dump(), longue=ACTIONS[action.nom].longue,
        )
        self._taches[ident] = asyncio.create_task(self._suivre_jusquau_bout(ident, conversation))
        return suivi

    async def _suivre_jusquau_bout(self, ident: str, conversation: str | None) -> None:
        derniere_progression = -1.0
        debut = time.monotonic()
        sans_nouvelles_depuis: float | None = None
        while True:
            try:
                suivi = await self._appel(self.__adaptateur.suivre(ident))
                sans_nouvelles_depuis = None
            except (LiaisonPerdue, asyncio.TimeoutError):
                maintenant = time.monotonic()
                sans_nouvelles_depuis = sans_nouvelles_depuis or maintenant
                if maintenant - sans_nouvelles_depuis < DELAI_PERTE_SUIVI_S:
                    await asyncio.sleep(0.05)  # une coupure courte du Wi-Fi : on patiente
                    continue
                # On a perdu le fil d'une action en cours : par sécurité, arrêt d'urgence (s'il n'est pas déjà actif).
                if not self.arret_urgence_actif:
                    await self.arret_urgence(raison="action_perdue_de_vue", qui="prise")
                suivi = self._suivis[ident].model_copy(update={
                    "statut": "echouee", "code_erreur": "liaison_perdue",
                    "message": "liaison perdue pendant l'action : arrêt d'urgence déclenché"})
            except asyncio.CancelledError:
                raise
            # Le robot ne doit pas pouvoir changer l'action suivie : on garde notre copie.
            suivi = suivi.model_copy(update={"action": self._suivis[ident].action})
            self._suivis[ident] = suivi
            if suivi.progression - derniere_progression >= 0.25 and not suivi.finie:
                derniere_progression = suivi.progression
                await self.bus.emettre("action_progression", "prise", robot=self.robot, conversation=conversation,
                                       id_action=ident, progression=round(suivi.progression, 2))
            if suivi.finie:
                await self.bus.emettre(
                    "action_terminee", "prise", robot=self.robot, conversation=conversation, id_action=ident,
                    action=suivi.action.model_dump(), statut=suivi.statut, message=suivi.message,
                    code_erreur=suivi.code_erreur, duree_ms=round((time.monotonic() - debut) * 1000),
                )
                self._taches.pop(ident, None)
                return
            await asyncio.sleep(0.05)

    async def suivre(self, ident: str) -> SuiviAction:
        return self._suivis[ident]

    async def attendre(self, ident: str, delai_max_s: float = 30.0) -> SuiviAction:
        tache = self._taches.get(ident)
        if tache:
            try:
                await asyncio.wait_for(asyncio.shield(tache), delai_max_s)
            except asyncio.TimeoutError:
                await self.annuler(ident)
                try:
                    await asyncio.wait_for(asyncio.shield(tache), 2.0)
                except asyncio.TimeoutError:
                    await self.arret_urgence(raison="action_trop_longue", qui="prise")
        return self._suivis[ident]

    async def annuler(self, ident: str) -> None:
        try:
            await self._appel(self.__adaptateur.annuler(ident))
        except asyncio.CancelledError:
            raise
        except Exception as e:  # liaison perdue, délai, arrêt refusé ou non confirmé par le kit : arrêt d'urgence
            log.warning("Annulation impossible (%r). Arrêt d'urgence.", e)
            await self.arret_urgence(raison="annulation_impossible", qui="prise")

    async def arreter_tout(self, conversation: str | None = None) -> None:
        """Arrêt normal : annule toutes les actions que la prise connaît, finies ou non à ses yeux."""
        for ident, suivi in list(self._suivis.items()):
            if not suivi.finie or ident in self._taches:
                await self.annuler(ident)

    # ---------- arrêt d'urgence : passe avant tout ----------
    async def arret_urgence(self, raison: str = "bouton", qui: str = "humain") -> None:
        self.arret_urgence_actif = True
        self._dernier_arret_a = time.monotonic()
        self._numero_arret += 1
        erreur = None
        try:
            await asyncio.wait_for(self.__adaptateur.arret_urgence(), 0.5)
        except Exception as e:  # on note, mais on ne bloque jamais l'arrêt
            erreur = repr(e)
        await self.bus.emettre("arret_urgence", "prise", robot=self.robot, raison=raison, qui=qui, erreur=erreur)
        t = asyncio.create_task(self._verifier_arret(self._numero_arret))
        self._fond.add(t)
        t.add_done_callback(self._fond.discard)

    async def _verifier_arret(self, numero: int, duree_s: float = 3.0) -> None:
        """Le robot s'est-il vraiment arrêté ? Sinon on réessaie toutes les 0,1 s, et on le dit très fort."""
        debut = time.monotonic()
        signale = False
        while time.monotonic() - debut < duree_s:
            await asyncio.sleep(0.1)
            if numero != self._numero_arret or not self.arret_urgence_actif:
                return  # déjà réarmé, ou un arrêt plus récent fait sa propre vérification
            etat = await self.etat()
            if not etat.en_mouvement and etat.liaison_ok:
                return  # arrêt confirmé
            try:
                await asyncio.wait_for(self.__adaptateur.arret_urgence(), 0.5)
            except Exception:
                pass
            if not signale and time.monotonic() - debut >= 0.4:
                signale = True
                await self.bus.emettre("panne", "prise", robot=self.robot, quoi="arret_urgence_non_confirme",
                                       en_mouvement=etat.en_mouvement, liaison_ok=etat.liaison_ok,
                                       consigne="Utiliser le bouton d'arrêt PHYSIQUE du robot.")

    async def rearmer(self, qui: str = "humain") -> bool:
        """Lever l'arrêt d'urgence. Échoue si un nouvel arrêt a été demandé pendant le réarmement."""
        numero = self._numero_arret
        try:
            await self._appel(self.__adaptateur.rearmer())
        except (LiaisonPerdue, asyncio.TimeoutError, ActionImpossible) as e:
            await self.bus.emettre("note", "prise", robot=self.robot, texte=f"réarmement impossible : {e!r}")
            return False
        if numero != self._numero_arret:
            await self.bus.emettre("note", "prise", robot=self.robot, texte="réarmement annulé : nouvel arrêt d'urgence")
            return False
        self.arret_urgence_actif = False
        self._dernier_arret_a = time.monotonic()  # un ordre vérifié PENDANT l'arrêt d'urgence ne part pas au réarmement
        await self.bus.emettre("reparation", "prise", robot=self.robot, quoi="rearmement", qui=qui)
        return True

    async def etat(self) -> EtatRobot:
        try:
            etat = await self._appel(self.__adaptateur.etat_robot())
        except (LiaisonPerdue, asyncio.TimeoutError):
            etat = EtatRobot(liaison_ok=False, erreurs=["liaison perdue"])
        etat.arret_urgence_actif = etat.arret_urgence_actif or self.arret_urgence_actif
        return etat

    # ---------- outils internes ----------
    async def _appel(self, coroutine):
        return await asyncio.wait_for(coroutine, self.delai)

    async def _refuser(self, action: ActionDemandee | None, raisons: list[Raison], conversation: str | None):
        await self.bus.emettre(
            "action_refusee", "prise", robot=self.robot, conversation=conversation,
            action=action.model_dump() if action else None, raisons=[r.model_dump() for r in raisons],
        )
        raise ActionRefusee(raisons)
