"""Brique 3 — Le MODÈLE D'ADAPTATEUR : la mécanique commune à tous les vrais robots.

NON TESTÉ SUR VRAI ROBOT. Testé sur faux robot (faux kit SDK et faux ROS 2, dossier chemins/).

Un adaptateur traduit la prise universelle vers un robot. Il NE DÉCIDE RIEN : il ne reçoit que des actions déjà
vérifiées par le gardien (ticket) puis par la prise. Seule la prise l'appelle (test_aucun_contournement.py le vérifie).

Ce fichier est la partie qui ne change pas d'un robot à l'autre : chaque méthode du modèle commun
(briques/b01_prise/adaptateur.py) est écrite ici, avec ce qu'elle DOIT faire et ce qu'elle REFUSE.
La partie propre au robot est la « liaison » (liaison.py : tout y est « à brancher »).
Nouveau robot : python3 lancer.py brancher NOM --genre … --chemin sdk|ros2 (BRANCHER_UN_ROBOT.md).

Ce que cette mécanique garantit, quel que soit le robot (en plus du gardien et de la prise : défense en profondeur) :
1. L'arrêt d'urgence passe avant tout : drapeau levé d'abord, nos boucles coupées, puis l'ordre au robot dans un fil
   (thread) NEUF à chaque tentative — il ne fait jamais la queue derrière un autre appel, même coincé. En plus, un arrêt
   normal est mis dans la file du fil habituel : il part juste après l'ordre qui était peut-être déjà en route.
2. Chaque ordre (vitesse, geste…) est revérifié juste avant de partir : un arrêt passé entre-temps l'annule.
   Après un arrêt d'urgence, tout est refusé (sauf « arreter ») jusqu'au réarmement par un humain.
3. Une seule action longue à la fois.
4. Vitesse bridée : jamais plus que la carte ; en mode « lent » (essais sur vrai robot) 0,1 m/s. Les gestes sont
   DEMANDÉS à mi-vitesse, mais beaucoup de kits n'ont pas de vitesse pour un geste enregistré : à vérifier par kit.
5. Les ordres de vitesse sont courts et répétés toutes les 0,1 s : si ce programme se fige, ils cessent, et le chien de
   garde du FABRICANT doit arrêter le robot (à vérifier pour chaque robot : fiches/).
6. Notre chien de garde : sans signe de vie de la prise pendant `delai_chien_s`, le robot est arrêté.
7. Un déplacement s'arrête si le robot s'écarte du trajet, va trop loin, ou recule au lieu d'avancer (odomètre).
8. Une capacité de la carte pas encore branchée dans la liaison est refusée, avec une explication.
9. Un appel au robot sans réponse en `delai_appel_s` = liaison perdue (la prise déclenche alors l'arrêt d'urgence).
   Un état illisible = liaison perdue aussi (jamais une erreur qui ferait taire la vérification de l'arrêt).
10. « Vrai robot » ou « faux robot » vient de la liaison, jamais du fichier de la carte.
11. La position de l'odomètre n'est donnée au gardien que si elle est dans le repère du monde (sinon il ne sait pas
    où est le robot, et demande l'accord d'un humain avant de bouger).
"""
from __future__ import annotations

import asyncio
import logging
import math
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from briques.b01_prise.actions import ACTIONS, CAPACITES_OBLIGATOIRES, ActionDemandee
from briques.b01_prise.adaptateur import ActionImpossible, Adaptateur, EtatRobot, LiaisonPerdue, SuiviAction
from briques.b01_prise.carte import CarteIdentite, Limites

from .liaison import ABrancher, LiaisonVide

log = logging.getLogger("adaptateur")

PERIODE_S = 0.1  # la petite boucle : chien de garde, ordres de vitesse répétés
VITESSE_LENTE_M_S = 0.1  # mode « lent » : premiers essais sur un vrai robot
VITESSE_RELATIVE_LENTE = 0.5
ATTENTE_DEBUT_S = 0.5  # un geste lancé : si le robot ne dit jamais « occupé », on le croit fini après 0,5 s
DELAI_MAX_TACHE_S = 30.0
CONTACT_PERDU_S = 0.8  # aucune réponse du robot depuis 0,8 s pendant une action : liaison perdue
TOLERANCE_M = 0.02
MARGE_TRAJET_M = 0.15  # écart permis au trajet en ligne droite (et au-delà du but)
MARGE_RECUL_M = 0.05  # le robot recule de plus de 5 cm : mauvais sens
DELAI_URGENCE_S = 0.3
MAX_FILS_ARRET = 4  # appels d'arrêt coincés en même temps ; au-delà, la tentative est sautée (et notée)
# Ce que la liaison peut encore faire pendant un arrêt. Tout le reste est un ORDRE, revérifié juste avant de partir.
PERMIS_PENDANT_ARRET = {"ouvrir", "fermer", "tic", "signe_de_vie", "lire_etat", "arreter_mouvement", "arret_urgence",
                        "rearmer", "infos_simulation"}


class _OrdrePerime(Exception):
    """Un arrêt est passé entre le moment où l'ordre a été préparé et le moment où il allait partir."""


def carte_honnete(carte: CarteIdentite, liaison: LiaisonVide) -> CarteIdentite:
    """La carte vue par la prise. « vrai_robot » vient de la liaison, pas du fichier.

    Faux robot : on garde les capacités de la carte que la fausse liaison sait jouer, et les chiffres laissés à 0
    (« à vérifier ») sont remplacés par ceux de la simulation (inventés), pour que les essais tournent."""
    if liaison.vrai_robot:
        return carte.model_copy(update={"vrai_robot": True})
    infos = liaison.infos_simulation() or {}
    limites = carte.limites.model_dump()
    for cle, valeur in (infos.get("limites") or {}).items():
        if not limites.get(cle):
            limites[cle] = valeur
    capacites = [c for c in carte.capacites if c in liaison.branchees or c in CAPACITES_OBLIGATOIRES]
    return carte.model_copy(update={
        "vrai_robot": False, "nom": f"{carte.nom} (simulation)", "capacites": capacites,
        "limites": Limites(**limites), "gestes": list(carte.gestes or infos.get("gestes") or [])})


def _nombre(v: Any) -> float | None:
    """Un vrai nombre fini, sinon None (un état bizarre ne doit jamais faire planter la lecture)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    try:
        v = float(v)
    except (OverflowError, ValueError):
        return None
    return v if math.isfinite(v) else None


class AdaptateurModele(Adaptateur):
    """La mécanique commune. `liaison` : les appels propres au robot (liaison.py). Seule la prise appelle ces méthodes.
    `bus` (facultatif) : pour noter dans la boîte noire ce que l'adaptateur remarque (arrêt sauté, chien de garde…)."""

    def __init__(self, carte: str | Path | CarteIdentite, liaison: LiaisonVide, lent: bool = False,
                 delai_chien_s: float = 0.6, delai_appel_s: float = 1.0, bus: Any = None) -> None:
        carte = carte if isinstance(carte, CarteIdentite) else CarteIdentite.charger(carte)
        self._liaison = liaison
        self._carte = carte_honnete(carte, liaison)
        self.lent = lent
        self.delai_chien_s = delai_chien_s
        self.delai_appel_s = delai_appel_s
        self._bus = bus
        self._notes: set[asyncio.Task] = set()
        self._fil: ThreadPoolExecutor | None = None
        self._fils_arret: list[tuple[float, asyncio.Future]] = []  # (heure de départ, appel d'arrêt en cours)
        self._arret_en_file: Any = None  # l'arrêt normal mis dans la file du fil habituel (un seul à la fois)
        self.arrets_sautes = 0
        self._suivis: dict[str, SuiviAction] = {}
        self._taches: dict[str, asyncio.Task] = {}
        self._veille: asyncio.Task | None = None
        self._arret_actif = False
        self._numero_arret = 0
        self._generation = 0  # augmente à chaque arrêt (normal, annulation, urgence) : les ordres d'avant ne partent plus
        self._dernier_battement = time.monotonic()
        self._dernier_contact = time.monotonic()
        self.journal: list[str] = []  # ce que l'adaptateur a remarqué (chien de garde, arrêt non reçu…)

    # ================================================================ informations (sans appel au robot)
    def carte(self) -> CarteIdentite:
        """DOIT : rendre la carte d'identité, tout de suite, sans parler au robot."""
        return self._carte

    def capacites_branchees(self) -> list[str]:
        """Les actions vraiment branchées dans la liaison (le test de conformité les compare à la carte)."""
        return sorted(self._liaison.branchees)

    # ================================================================ cycle de vie
    async def connecter(self) -> None:
        """DOIT : ouvrir la liaison, puis lancer la petite boucle (chien de garde).
        NE DOIT JAMAIS faire bouger le robot. Liaison pas branchée : erreur « à brancher », claire."""
        self._fil = ThreadPoolExecutor(max_workers=1, thread_name_prefix="liaison")
        try:
            await self._appel(self._liaison.ouvrir, delai=1.8)
        except BaseException:
            self._fil.shutdown(wait=False, cancel_futures=True)
            raise
        self._dernier_battement = self._dernier_contact = time.monotonic()
        self._veille = asyncio.create_task(self._veiller())

    async def deconnecter(self) -> None:
        """DOIT : d'abord arrêter le robot (arrêt NORMAL : vitesse nulle, il reste debout), puis fermer.
        NE DOIT PAS utiliser l'arrêt d'urgence du fabricant : sur un robot à jambes il peut couper les moteurs."""
        self._tout_couper("déconnexion")
        try:
            await self._appel(self._liaison.arreter_mouvement)
        except Exception as e:  # on continue : fermer quand même
            self._noter(f"déconnexion : arrêt normal non confirmé ({e})")
        try:
            await self._appel(self._liaison.fermer)
        except Exception as e:
            self._noter(f"déconnexion : fermeture incomplète ({e})")
        finally:
            if self._veille:
                self._veille.cancel()
            if self._fil:
                self._fil.shutdown(wait=False, cancel_futures=True)

    async def battement(self) -> None:
        """Signe de vie envoyé par la prise toutes les 0,2 s. DOIT : noter l'heure (notre chien de garde) et vérifier
        que le robot répond. Robot muet : lever LiaisonPerdue (la prise le note et l'écran le montre)."""
        self._dernier_battement = time.monotonic()
        try:
            await self._appel(self._liaison.signe_de_vie)
        except ActionImpossible as e:
            raise LiaisonPerdue(str(e)) from e

    # ================================================================ agir
    async def demarrer(self, action: ActionDemandee) -> str:
        """DOIT : lancer l'action et rendre TOUT DE SUITE un identifiant de suivi (l'action continue à côté).
        REFUSE (ActionImpossible, avec une explication) : pendant un arrêt d'urgence (sauf « arreter ») ;
        une action absente de la carte ; une action pas encore branchée ; une 2e action longue ;
        un lieu nommé si le robot ne sait pas y aller seul. « arreter » n'est jamais refusé."""
        if action.nom == "arreter":
            return await self._arreter()
        if self._arret_actif:
            raise ActionImpossible("arret_urgence_actif", "arrêt d'urgence actif : un humain doit réarmer le robot")
        if not self._carte.sait(action.nom):
            raise ActionImpossible("absente_de_la_carte", f"« {action.nom} » n'est pas dans la carte de ce robot")
        if action.nom not in self._liaison.branchees:
            raise ActionImpossible("non_branchee", f"« {action.nom} » n'est pas encore branché pour ce robot")
        if action.nom == "se_deplacer" and action.parametres.get("lieu") is not None and not self._liaison.sait_aller_au_lieu:
            raise ActionImpossible("lieu_non_branche", "ce robot ne sait aller qu'à quelques mètres devant lui (dx, dy)")
        if ACTIONS[action.nom].longue and self._long_en_cours():
            raise ActionImpossible("robot_occupe", "le robot fait déjà une action longue")
        return self._lancer(action)

    async def suivre(self, ident: str) -> SuiviAction:
        """DOIT : rendre l'avancement tout de suite (0 à 1, statut). Robot muet pendant une action : LiaisonPerdue
        (la prise déclenche alors l'arrêt d'urgence après 1 s)."""
        suivi = self._suivis.get(ident)
        if suivi is None:
            raise ActionImpossible("inconnue", f"action inconnue : {ident}")
        if not suivi.finie and time.monotonic() - self._dernier_contact > CONTACT_PERDU_S:
            raise LiaisonPerdue("plus de nouvelles du robot")
        return suivi.model_copy()

    async def annuler(self, ident: str) -> None:
        """DOIT : arrêter CETTE action (le robot s'immobilise) et la marquer « annulée ». Déjà finie : rien.
        Robot muet : LiaisonPerdue (la prise déclenche alors l'arrêt d'urgence)."""
        tache, suivi = self._taches.get(ident), self._suivis.get(ident)
        if tache and not tache.done():
            tache.cancel()
        if suivi and not suivi.finie:
            self._generation += 1  # un ordre déjà préparé pour cette action ne part plus
            suivi.statut, suivi.message = "annulee", "annulée"
            try:
                await self._appel(self._liaison.arreter_mouvement)
            except Exception as e:  # arrêt refusé ou non confirmé (None) : la prise passera à l'arrêt d'urgence
                raise LiaisonPerdue(f"arrêt non confirmé pendant l'annulation ({e})") from e

    async def arret_urgence(self) -> None:
        """PASSE AVANT TOUT. DOIT : tout arrêter tout de suite. Ne lève JAMAIS d'erreur, n'attend jamais plus de 0,3 s.
        Dans l'ordre : 1) drapeau levé (plus rien ne démarre, les ordres préparés ne partent plus) ; 2) nos boucles
        coupées ; 3) un arrêt normal dans la file du fil habituel (il passe juste après l'ordre peut-être déjà en route) ;
        4) l'arrêt du fabricant, dans un fil neuf (secours : un arrêt normal, dans un autre fil neuf).
        Ne remplace JAMAIS le bouton d'arrêt PHYSIQUE du robot."""
        try:
            self._arret_actif = True
            self._numero_arret += 1
            self._tout_couper("arrêt d'urgence", "arret_urgence")
            self._arret_dans_la_file()
            await self._appel_urgent(self._liaison.arret_urgence, secours=self._liaison.arreter_mouvement)
        except Exception as e:  # jamais d'erreur ici
            self._noter(f"arrêt d'urgence : {e!r}")

    async def rearmer(self) -> None:
        """Décision d'un HUMAIN après un arrêt d'urgence. DOIT : lever le blocage.
        NE DOIT JAMAIS faire bouger le robot (ni le relever : à la main, feu orange).
        Un nouvel arrêt d'urgence pendant le réarmement l'annule, et l'arrêt est RENVOYÉ au robot (le réarmement du
        kit a pu effacer l'arrêt qui venait d'arriver)."""
        numero = self._numero_arret
        await self._appel(self._liaison.rearmer)
        if numero != self._numero_arret:
            self._noter("arrêt d'urgence pendant le réarmement : réarmement annulé, arrêt renvoyé au robot")
            self._arret_dans_la_file()
            await self._appel_urgent(self._liaison.arret_urgence, secours=self._liaison.arreter_mouvement)
            return
        self._arret_actif = False

    async def etat_robot(self) -> EtatRobot:
        """DOIT : lire l'état sans rien faire bouger. Robot muet OU état illisible : LiaisonPerdue, jamais une autre
        erreur (la prise lit l'état pour vérifier que le robot s'est bien arrêté)."""
        brut = await self._appel(self._liaison.lire_etat)
        try:
            return self._etat(brut)
        except Exception as e:
            raise LiaisonPerdue(f"état illisible : {type(e).__name__} : {e}") from e

    # ================================================================ outils internes
    async def _appel(self, fonction: Callable[..., Any], *args: Any, delai: float | None = None, contact: bool = True) -> Any:
        """Un appel au robot, dans le fil de la liaison, avec un délai. Pas de réponse : LiaisonPerdue.
        Un ORDRE (vitesse, geste…) est revérifié dans le fil, juste avant de partir : un arrêt passé entre-temps l'annule."""
        if self._fil is None:
            raise LiaisonPerdue("pas connecté")
        nom = getattr(fonction, "__name__", "")
        ordre, generation = nom not in PERMIS_PENDANT_ARRET, self._generation

        def envoyer() -> Any:
            if ordre and (self._arret_actif or generation != self._generation):
                raise _OrdrePerime(nom)
            return fonction(*args)

        boucle = asyncio.get_running_loop()
        try:
            resultat = await asyncio.wait_for(boucle.run_in_executor(self._fil, envoyer), delai or self.delai_appel_s)
        except _OrdrePerime as e:
            raise ActionImpossible("ordre_perime", f"un arrêt est passé avant l'ordre « {e} » : il n'est pas envoyé") from e
        except ABrancher as e:
            raise ActionImpossible("a_brancher", str(e)) from e
        except ActionImpossible:
            raise
        except asyncio.TimeoutError as e:
            raise LiaisonPerdue(f"le robot n'a pas répondu en {delai or self.delai_appel_s} s") from e
        except RuntimeError as e:
            if "shutdown" in str(e):  # déjà déconnecté
                raise LiaisonPerdue("pas connecté") from e
            raise LiaisonPerdue(f"RuntimeError : {e}") from e
        except Exception as e:  # ConnectionError, erreur du kit… : liaison perdue
            raise LiaisonPerdue(f"{type(e).__name__} : {e}") from e
        if contact:
            self._dernier_contact = time.monotonic()
        return resultat

    def _arret_dans_la_file(self) -> None:
        """Un arrêt normal dans la file du fil habituel, sans l'attendre : il passe juste après l'appel en cours."""
        if self._fil is None or (self._arret_en_file is not None and not self._arret_en_file.done()):
            return  # un arrêt attend déjà dans la file : inutile d'en empiler d'autres (le fil resterait bouché)
        try:
            self._arret_en_file = self._fil.submit(self._liaison.arreter_mouvement)
            self._arret_en_file.add_done_callback(lambda f: f.cancelled() or f.exception())
        except RuntimeError:  # déjà déconnecté
            pass

    def _fil_neuf(self, fonction: Callable[[], Any]) -> asyncio.Future:
        """Lancer `fonction` dans un fil NEUF (thread « démon » : il n'empêche pas le programme de se fermer)."""
        boucle = asyncio.get_running_loop()
        futur = boucle.create_future()
        futur.add_done_callback(lambda f: f.cancelled() or f.exception())  # l'erreur éventuelle est lue (pas d'alerte)

        def poser(erreur: BaseException | None, resultat: Any) -> None:
            if not futur.done():
                futur.set_exception(erreur) if erreur is not None else futur.set_result(resultat)

        def corps() -> None:
            try:
                reponse: tuple = (None, fonction())
            except BaseException as e:  # noqa: BLE001 — rapportée au programme principal
                reponse = (e, None)
            try:
                boucle.call_soon_threadsafe(poser, *reponse)
            except RuntimeError:  # le programme principal est déjà fermé
                pass

        threading.Thread(target=corps, name="arret-urgence", daemon=True).start()
        return futur

    def _coinces(self) -> int:
        """Appels d'arrêt toujours en cours après le délai : le robot n'a peut-être rien reçu."""
        maintenant = time.monotonic()
        self._fils_arret = [(h, f) for h, f in self._fils_arret if not f.done()]
        return sum(1 for h, _ in self._fils_arret if maintenant - h > DELAI_URGENCE_S)

    async def _appel_urgent(self, fonction: Callable[[], Any], secours: Callable[[], Any] | None = None) -> bool:
        """Un appel d'arrêt dans un fil neuf, attendu 0,3 s au plus. Raté ou coincé : `secours` dans un autre fil neuf.
        Trop d'appels coincés : la tentative est sautée, et c'est noté (journal, boîte noire, état du robot)."""
        self._coinces()
        if len(self._fils_arret) >= MAX_FILS_ARRET:
            self.arrets_sautes += 1
            self._noter(f"tentative d'arrêt SAUTÉE : {len(self._fils_arret)} appels d'arrêt toujours coincés dans le "
                        f"kit — utiliser le bouton d'arrêt PHYSIQUE")
            return False
        futur = self._fil_neuf(fonction)
        self._fils_arret.append((time.monotonic(), futur))
        try:
            await asyncio.wait_for(asyncio.shield(futur), DELAI_URGENCE_S)
            return True
        except Exception as e:
            self._noter(f"arrêt non confirmé par le robot ({getattr(fonction, '__name__', '?')}) : {e!r}")
        if secours is not None and len(self._fils_arret) < MAX_FILS_ARRET:
            self._fils_arret.append((time.monotonic(), self._fil_neuf(secours)))
        return False

    def _noter(self, texte: str) -> None:
        """Garder ce que l'adaptateur remarque : journal, et boîte noire si l'adaptateur a reçu le bus."""
        self.journal.append(texte)
        del self.journal[:-200]
        log.warning(texte)
        if self._bus is not None:
            try:
                tache = asyncio.get_running_loop().create_task(
                    self._bus.emettre("note", "adaptateur", robot=self._carte.id, texte=texte))
                self._notes.add(tache)
                tache.add_done_callback(self._notes.discard)
            except RuntimeError:
                pass

    def _lancer(self, action: ActionDemandee) -> str:
        ident = uuid.uuid4().hex[:8]
        suivi = SuiviAction(id=ident, action=action, statut="en_cours")
        self._suivis[ident] = suivi
        self._taches[ident] = asyncio.create_task(self._jouer(suivi))
        if len(self._suivis) > 200:  # garder la mémoire petite : on oublie les plus vieilles actions finies
            for vieux in [i for i, s in self._suivis.items() if s.finie][:100]:
                self._suivis.pop(vieux, None)
                self._taches.pop(vieux, None)
        return ident

    async def _arreter(self) -> str:
        """« arreter » (arrêt normal) : jamais refusé. Arrêt non confirmé : l'action est « échouée », et le dit."""
        self._tout_couper("arrêt demandé")
        suivi = SuiviAction(id=uuid.uuid4().hex[:8], action=ActionDemandee(nom="arreter"), statut="reussie",
                            progression=1.0, message="arrêté")
        try:
            await self._appel(self._liaison.arreter_mouvement)
        except Exception as e:
            await self._appel_urgent(self._liaison.arreter_mouvement)
            suivi.statut, suivi.code_erreur = "echouee", "arret_non_confirme"
            suivi.message = f"arrêt non confirmé ({e}) : utiliser le bouton d'arrêt PHYSIQUE"
            self._suivis[suivi.id] = suivi
            # La prise voit l'erreur et passe à l'arrêt d'urgence (l'arrêt du fabricant, avec tous ses secours).
            raise ActionImpossible("arret_non_confirme", "arrêt non confirmé : arrêt d'urgence") from e
        self._suivis[suivi.id] = suivi
        return suivi.id

    def _long_en_cours(self) -> bool:
        return any(not s.finie and ACTIONS[s.action.nom].longue for s in self._suivis.values())

    def _tout_couper(self, message: str, code: str | None = None, statut: str = "annulee") -> None:
        self._generation += 1  # tout ordre déjà préparé ne partira plus
        for ident, tache in list(self._taches.items()):
            if not tache.done():
                tache.cancel()
            s = self._suivis.get(ident)
            if s and not s.finie:
                s.statut, s.message, s.code_erreur = statut, message, code

    async def _veiller(self) -> None:
        """Toutes les 0,1 s : laisser le kit travailler (tic) et surveiller les signes de vie de la prise."""
        while True:
            await asyncio.sleep(PERIODE_S)
            try:
                await self._appel(self._liaison.tic, contact=False)
            except asyncio.CancelledError:
                raise
            except Exception:
                pass  # une liaison perdue se voit ailleurs (battement, suivre)
            en_cours = any(not s.finie for s in self._suivis.values())
            if en_cours and time.monotonic() - self._dernier_battement > self.delai_chien_s:
                self._tout_couper("plus de signe de vie de la prise : arrêt par le chien de garde de l'adaptateur",
                                  "chien_de_garde", statut="echouee")
                self._noter("chien de garde : arrêt faute de signe de vie")
                self._arret_dans_la_file()
                await self._appel_urgent(self._liaison.arreter_mouvement)

    def _etat(self, brut: Any) -> EtatRobot:
        """L'état, nettoyé : un type inattendu devient « inconnu », jamais une erreur."""
        if not isinstance(brut, dict):
            raise TypeError(f"l'état n'est pas un dictionnaire ({type(brut).__name__})")
        odometrie = {k: v for k in ("x", "y", "cap") if (v := _nombre(brut.get(k))) is not None}
        erreurs = brut.get("erreurs")
        erreurs = [str(e) for e in erreurs] if isinstance(erreurs, (list, tuple)) else ([str(erreurs)] if erreurs else [])
        coinces = self._coinces()
        if coinces:
            erreurs.append(f"arrêt d'urgence non confirmé : {coinces} appel(s) d'arrêt coincé(s) dans le kit")
        objet = brut.get("objet_tenu")
        en_cours = any(not s.finie and s.action.nom != "etat" for s in self._suivis.values())
        return EtatRobot(
            batterie_pct=_nombre(brut.get("batterie_pct")), erreurs=erreurs,
            position=odometrie if (self._liaison.repere_du_monde and len(odometrie) == 3) else {},
            objet_tenu=objet if isinstance(objet, str) and objet else None,
            en_mouvement=bool(brut.get("en_mouvement")) or en_cours,
            liaison_ok=not coinces,  # un arrêt coincé : on ne sait pas si le robot l'a reçu
            arret_urgence_actif=self._arret_actif or bool(brut.get("arret_urgence")),
            extra={"chemin": self._liaison.chemin, "simulation": not self._liaison.vrai_robot, "odometrie": odometrie,
                   "occupe": bool(brut.get("occupe")), "branchees": self.capacites_branchees(), "lent": self.lent,
                   "arrets_sautes": self.arrets_sautes, "journal": self.journal[-5:]},
        )

    def _vitesse(self, demandee: Any) -> float:
        """La vitesse vraiment envoyée : jamais plus que la carte ; 0,1 m/s en mode lent."""
        maxi = self._carte.limites.vitesse_max_m_s
        v = float(demandee) if isinstance(demandee, (int, float)) and not isinstance(demandee, bool) else maxi
        v = min(v, maxi, VITESSE_LENTE_M_S if self.lent else math.inf)
        if not math.isfinite(v) or v <= 0:
            raise ActionImpossible("vitesse_nulle", "vitesse nulle : la carte ne permet pas de bouger (chiffre à vérifier)")
        return v

    # ================================================================ jouer une action (à côté)
    async def _jouer(self, s: SuiviAction) -> None:
        a, p = s.action, s.action.parametres
        try:
            if a.nom == "etat":
                etat = self._etat(await self._appel(self._liaison.lire_etat))
                s.message = f"batterie {etat.batterie_pct} %" if etat.batterie_pct is not None else "état lu"
            elif a.nom == "se_deplacer":
                await self._deplacer(s, p)
            elif a.nom == "parler":
                await self._appel(self._liaison.parler, str(p["texte"]), str(p.get("langue") or "fr"))
                await self._attendre_fin(s)
            elif a.nom == "ecouter":
                duree = float(p.get("duree_s") or 3.0)
                await self._appel(self._liaison.ecouter, duree)
                etat = await self._attendre_fin(s, delai_max=duree + 5.0)
                s.message = str(etat.get("entendu") or "")
            elif a.nom in ("regarder", "montrer"):
                fonction = self._liaison.regarder if a.nom == "regarder" else self._liaison.montrer
                await self._appel(fonction, str(p["cible"]))
                await self._attendre_fin(s)
            elif a.nom == "rejouer_geste":
                vr = float(p.get("vitesse_relative") or 1.0)
                vr = min(vr, 1.0, VITESSE_RELATIVE_LENTE if self.lent else 1.0)  # demandée ; tenue ? à vérifier par kit
                await self._appel(self._liaison.geste, str(p["nom"]), vr)
                await self._attendre_fin(s)
            elif a.nom == "saisir":
                maxi = self._carte.limites.force_max_n
                force = min(float(p.get("force") or maxi), maxi)
                await self._appel(self._liaison.saisir, str(p["objet"]), force)
                etat = await self._attendre_fin(s)
                if etat.get("objet_tenu") != p["objet"]:
                    return self._echec(s, "objet_non_saisi", f"« {p['objet']} » n'est pas dans la main")
            elif a.nom == "poser":
                await self._appel(self._liaison.poser, str(p.get("lieu") or "ici"))
                etat = await self._attendre_fin(s)
                if etat.get("objet_tenu"):
                    return self._echec(s, "objet_toujours_tenu", "l'objet est toujours dans la main")
            if s.statut == "en_cours":
                s.statut, s.progression, s.message = "reussie", 1.0, s.message or "fait"
        except asyncio.CancelledError:
            if not s.finie:
                s.statut, s.message = "annulee", s.message or "annulée"
            raise
        except ActionImpossible as e:
            self._echec(s, e.code, str(e))
            if e.code == "action_interrompue":  # la liaison dit que l'action s'est arrêtée en route : rien ne doit continuer
                self._noter(f"« {a.nom} » interrompue en route : arrêt demandé")
                self._arret_dans_la_file()
                await self._appel_urgent(self._liaison.arreter_mouvement)
        except LiaisonPerdue as e:
            self._echec(s, "liaison_perdue", str(e))
            # L'appel a pu arriver au robot quand même (une réponse trop lente n'est pas un ordre perdu) : une action
            # dite « échouée » ne doit pas continuer. Un arrêt normal part donc, comme pour une erreur imprévue (15.11.2026).
            if a.nom not in ("etat", "arreter"):
                self._noter(f"liaison perdue pendant « {a.nom} » : arrêt demandé")
                self._arret_dans_la_file()
                await self._appel_urgent(self._liaison.arreter_mouvement)
        except Exception as e:  # une erreur imprévue (liaison mal branchée…) : on arrête le robot et on le dit
            self._echec(s, "erreur_adaptateur", f"{type(e).__name__} : {e}")
            self._noter(f"erreur pendant « {a.nom} » : {e!r}")
            self._arret_dans_la_file()
            await self._appel_urgent(self._liaison.arreter_mouvement)

    def _echec(self, s: SuiviAction, code: str, message: str) -> None:
        if not s.finie:
            s.statut, s.code_erreur, s.message = "echouee", code, message

    async def _attendre_fin(self, s: SuiviAction, delai_max: float = DELAI_MAX_TACHE_S) -> dict[str, Any]:
        """Attendre que le robot ne soit plus « occupé ». S'il ne le dit jamais : fini après 0,5 s (à vérifier par robot)."""
        debut, vu_occupe = time.monotonic(), False
        while True:
            etat = await self._appel(self._liaison.lire_etat)
            ecoule = time.monotonic() - debut
            if etat.get("echec_action"):
                # La liaison dit que l'action lancée s'est arrêtée en route (clé facultative « echec_action », un texte) :
                # elle est comptée RATÉE, jamais « réussie » parce que le robot n'est plus occupé (15.11.2026).
                raise ActionImpossible("action_interrompue", str(etat["echec_action"]))
            if etat.get("occupe"):
                vu_occupe = True
            elif vu_occupe or ecoule >= ATTENTE_DEBUT_S:
                return etat
            if ecoule > delai_max:
                await self._appel(self._liaison.arreter_mouvement)
                raise ActionImpossible("trop_long", f"pas fini après {delai_max:.0f} s : arrêté")
            s.progression = min(0.9, ecoule / delai_max)
            await asyncio.sleep(0.05)

    async def _deplacer(self, s: SuiviAction, p: dict[str, Any]) -> None:
        v = self._vitesse(p.get("vitesse"))
        if p.get("lieu") is not None:
            await self._appel(self._liaison.aller_au_lieu, str(p["lieu"]), v)
            await self._attendre_fin(s, delai_max=120.0)
            return
        dx, dy = float(p.get("dx") or 0.0), float(p.get("dy") or 0.0)
        d = math.hypot(dx, dy)
        if d < TOLERANCE_M:
            return
        ux, uy = dx / d, dy / d
        depart = await self._appel(self._liaison.lire_etat)
        odometre = all(_nombre(depart.get(k)) is not None for k in ("x", "y", "cap"))
        if odometre:  # direction dans le repère de l'odomètre
            c, sn = math.cos(math.radians(depart["cap"])), math.sin(math.radians(depart["cap"]))
            wx, wy = ux * c - uy * sn, ux * sn + uy * c
        t0, delai_max, meilleur = time.monotonic(), 2.0 * d / v + 2.0, 0.0
        try:
            while True:
                if odometre:
                    etat = await self._appel(self._liaison.lire_etat)
                    ex, ey = etat["x"] - depart["x"], etat["y"] - depart["y"]
                    fait, ecart = ex * wx + ey * wy, abs(ey * wx - ex * wy)
                    if fait < d - TOLERANCE_M:
                        # Le plafond de distance (gardien, prise) ne vaut que si le robot va où on lui dit : on vérifie.
                        if math.hypot(ex, ey) > d + MARGE_TRAJET_M or ecart > MARGE_TRAJET_M:
                            raise ActionImpossible("hors_trajet", f"le robot s'écarte du trajet prévu ({ecart:.2f} m "
                                                   f"de côté, {math.hypot(ex, ey):.2f} m du départ) : arrêté")
                        if fait < meilleur - MARGE_RECUL_M:
                            raise ActionImpossible("mauvais_sens", "le robot recule au lieu d'avancer : arrêté "
                                                   "(sens des vitesses à vérifier dans la liaison)")
                    meilleur = max(meilleur, fait)
                else:  # pas d'odomètre : estimation au temps (moins sûr)
                    fait = v * (time.monotonic() - t0)
                s.progression = max(0.0, min(1.0, fait / d))
                if fait >= d - TOLERANCE_M:
                    break
                if time.monotonic() - t0 > delai_max:
                    raise ActionImpossible("trop_long", "le robot n'avance pas comme prévu : arrêté")
                await self._appel(self._liaison.vitesse, v * ux, v * uy, 0.0)
                await asyncio.sleep(PERIODE_S)
            await self._appel(self._liaison.arreter_mouvement)
        except (ActionImpossible, LiaisonPerdue):
            self._arret_dans_la_file()
            await self._appel_urgent(self._liaison.arreter_mouvement)
            raise
