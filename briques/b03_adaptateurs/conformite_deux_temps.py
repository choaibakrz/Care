"""Brique 3 — Le test de conformité en DEUX TEMPS : d'abord « sans mouvement », puis « complet ».

Réutilise briques/b01_prise/conformite.py (verifier_conformite, sans le recopier) et ajoute des contrôles qui ne font
rien bouger. Toutes les actions passent par le gardien (ticket) puis par la prise, comme en vrai.

1. Sans mouvement : connexion, carte, état, arrêt d'urgence logiciel (et blocage jusqu'au réarmement), refus de tout
   ce qui dépasse les limites. Un « témoin » prouve que les refus DU GARDIEN n'ont rien envoyé au robot (il ne voit
   que ce chemin-là) ; la prise, elle, est essayée par le ticket d'un autre robot et par le blocage après l'arrêt.
2. Complet : chaque capacité de la carte avec un petit exemple sûr, puis deux déplacements de 2 m demandés et coupés
   après 0,2 s (une annulation, un arrêt d'urgence). Sur un vrai robot : mode lent (0,1 m/s ; gestes DEMANDÉS à
   mi-vitesse, tenu ou non : à vérifier par kit) et seulement si le temps 1 a réussi.

Sur un VRAI robot, les deux temps sont FEU ORANGE : le programme rappelle les consignes et attend une phrase tapée au
clavier, avec un nombre tiré au hasard. Pas d'option pour sauter la question ; sans clavier, il refuse.
HONNÊTEMENT : c'est une protection contre l'OUBLI, PAS contre un agent ou un script (un faux clavier se fabrique).
La vraie garde est le feu orange : le « oui » de Hiba, le responsable sécurité, la main sur l'arrêt physique.
"""
from __future__ import annotations

import math
import secrets
import sys
from typing import Callable

from briques.b01_prise.actions import ACTIONS, ActionDemandee
from briques.b01_prise.adaptateur import Adaptateur
from briques.b01_prise.carte import CarteIdentite
from briques.b01_prise.conformite import Controle, Rapport, verifier_conformite
from briques.b01_prise.prise import Prise
from briques.b01_prise.raisons import ActionRefusee
from commun.bus import Bus

PHRASE_SANS_MOUVEMENT = "sans mouvement"


def phrase_complet(robot: str) -> str:
    return f"mouvement lent {robot}"


CONSIGNES = [
    "FEU ORANGE — VRAI ROBOT. Avant de continuer, vérifier à voix haute :",
    "  1. Hiba a dit « oui » pour CET essai.",
    "  2. Le responsable sécurité est là, à côté du robot.",
    "  3. Le bouton d'arrêt PHYSIQUE est trouvé, essayé robot immobile, et une main est dessus.",
    "  4. La zone autour du robot est vide (distance : règles du lieu, à vérifier).",
    "  5. Robot à jambes : suspendu (portique) ou posé de façon stable, comme le dit sa fiche (fiches/).",
    "  6. L'écran (python3 lancer.py) est arrêté : une seule liaison avec le robot.",
    "La phrase à taper protège contre l'OUBLI, pas contre un agent ou un script : la vraie garde, c'est ce feu orange.",
]
AVERTISSEMENT_SANS_MOUVEMENT = (
    "Ce temps ne commande aucun mouvement, MAIS il envoie l'arrêt d'urgence logiciel de la liaison : sur certains "
    "robots à jambes, l'arrêt du fabricant coupe les moteurs (le robot tombe). Vérifier ce que fait arret_urgence().")
AVERTISSEMENT_COMPLET = (
    "Ce temps FAIT BOUGER le robot, lentement (0,1 m/s) : 20 cm devant lui, chaque capacité de la carte (gestes DEMANDÉS "
    "à mi-vitesse : beaucoup de kits n'ont pas de vitesse pour un geste enregistré, à vérifier par kit), puis DEUX "
    "déplacements de 2 m demandés et coupés après 0,2 s (une annulation, un arrêt d'urgence).")

# Pour un robot qui ne se déplace pas (une tête, une main posée sur une table) : l'autre texte n'aurait pas de sens.
AVERTISSEMENT_COMPLET_SUR_PLACE = (
    "Ce temps FAIT BOUGER le robot, sur place : chaque capacité de sa carte une fois, dont le PREMIER geste de la carte, "
    "puis l'arrêt d'urgence (qui peut couper les moteurs : ce que le robot tient ou porte peut retomber). La vitesse "
    "peut être celle du FABRICANT, pas la nôtre : lire la liste exacte dans la fiche du robot (fiches/) avant de taper.")
PHRASE_SENS, PHRASE_SUR_PLACE = "le robot est allé dans le bon sens", "le robot a fait le mouvement prévu"


# ---------------------------------------------------------------- le témoin
class Temoin(Adaptateur):
    """Enveloppe transparente autour d'un adaptateur : note ce qui arrive VRAIMENT à l'adaptateur.
    Sert à prouver que les refus DU GARDIEN (demandes hors limites) n'ont rien envoyé : il ne voit que ce chemin-là.
    Seule la prise l'appelle."""

    def __init__(self, interne: Adaptateur) -> None:
        self._interne = interne
        self.demarrages: list[str] = []

    def carte(self) -> CarteIdentite:
        return self._interne.carte()

    async def connecter(self) -> None:
        await self._interne.connecter()

    async def deconnecter(self) -> None:
        await self._interne.deconnecter()

    async def demarrer(self, action: ActionDemandee) -> str:
        self.demarrages.append(action.nom)
        return await self._interne.demarrer(action)

    async def suivre(self, ident: str):
        return await self._interne.suivre(ident)

    async def annuler(self, ident: str) -> None:
        await self._interne.annuler(ident)

    async def arret_urgence(self) -> None:
        await self._interne.arret_urgence()

    async def rearmer(self) -> None:
        await self._interne.rearmer()

    async def etat_robot(self):
        return await self._interne.etat_robot()

    async def battement(self) -> None:
        await self._interne.battement()


def actions_hors_limites(carte: CarteIdentite) -> list[ActionDemandee]:
    """Des demandes qui dépassent les limites, pour les capacités de CETTE carte. Toutes doivent être refusées."""
    a = []
    if carte.sait("se_deplacer"):
        a += [ActionDemandee(nom="se_deplacer", parametres={"dx": 0.2, "vitesse": 5.0}),
              ActionDemandee(nom="se_deplacer", parametres={"dx": 50.0}),
              ActionDemandee(nom="se_deplacer", parametres={"dx": math.nan}),
              ActionDemandee(nom="se_deplacer", parametres={"dx": 0.2, "vitesse": -0.2})]
    if carte.sait("saisir"):
        a.append(ActionDemandee(nom="saisir", parametres={"objet": "objet_test", "force": 1000.0}))
    if carte.sait("rejouer_geste"):
        a.append(ActionDemandee(nom="rejouer_geste", parametres={"nom": "geste_qui_n_existe_pas"}))
        if carte.gestes:
            a.append(ActionDemandee(nom="rejouer_geste", parametres={"nom": carte.gestes[0], "vitesse_relative": 3.0}))
    if carte.sait("ecouter"):
        a.append(ActionDemandee(nom="ecouter", parametres={"duree_s": -1.0}))
    a.append(ActionDemandee(nom="etat", parametres={"ordre_moteur": 1}))  # précision inconnue : refusée
    return a


async def controles_sans_mouvement(fabrique: Callable[[], Adaptateur], vrai_attendu: bool | None = None) -> list[Controle]:
    """Les contrôles en plus de conformite.py, sans aucun mouvement. Un adaptateur neuf (fabrique), comme en vrai."""
    from briques.b07_gardien.gardien import Gardien  # import ici : le gardien dépend de la prise

    adaptateur = fabrique()
    temoin = Temoin(adaptateur)
    bus = Bus()
    gardien = Gardien(bus)
    prise = Prise(temoin, gardien.verificateur, bus)
    carte = prise.carte()
    c: list[Controle] = []
    ajouter = lambda nom, ok, detail="": c.append(Controle(nom=nom, ok=bool(ok), detail=detail))

    if vrai_attendu is not None:
        ajouter("mention honnête (vrai ou faux robot)", carte.vrai_robot == vrai_attendu, carte.mention_test())
    branchees = adaptateur.capacites_branchees() if hasattr(adaptateur, "capacites_branchees") else None
    if branchees is not None:
        manque = [x for x in carte.capacites if x not in branchees]
        ajouter("la carte ne promet que ce qui est branché", not manque,
                f"pas encore branché : {manque} — le brancher, ou l'enlever de la carte" if manque else
                f"{len(carte.capacites)} capacités branchées")

    await prise.connecter()
    try:
        etat = await prise.etat()
        ajouter("connexion sans mouvement", etat.liaison_ok and not etat.en_mouvement and not temoin.demarrages,
                f"liaison {'ok' if etat.liaison_ok else 'perdue'}, en mouvement : {etat.en_mouvement}")

        refus = []
        for action in actions_hors_limites(carte):
            d, ticket = await gardien.verifier(action, carte)
            ok = d.verdict == "non" and ticket is None
            refus.append(ok)
            if not ok:
                ajouter(f"refuse {action.resume()}", False, f"verdict {d.verdict}")
        ajouter("refuse ce qui dépasse les limites (gardien)", all(refus), f"{sum(refus)}/{len(refus)} demandes refusées")

        autre = carte.model_copy(update={"id": carte.id + "-autre"})
        _, ticket = await gardien.verifier(ActionDemandee(nom="etat"), autre)
        try:
            await prise.executer(ticket)
            ajouter("refuse le ticket d'un autre robot", False)
        except ActionRefusee as e:
            ajouter("refuse le ticket d'un autre robot", e.raisons[0].code == "ticket_invalide")

        await prise.arret_urgence(raison="conformite_sans_mouvement")
        _, ticket = await gardien.verifier(ActionDemandee(nom="etat"), carte)
        try:
            await prise.executer(ticket)
            ajouter("arrêt d'urgence : tout est bloqué", False)
        except ActionRefusee as e:
            ajouter("arrêt d'urgence : tout est bloqué", e.raisons[0].code == "arret_urgence_actif")
        etat = await prise.etat()
        ajouter("arrêt d'urgence : robot immobile et joignable", etat.liaison_ok and not etat.en_mouvement)
        rearme = await prise.rearmer()
        _, ticket = await gardien.verifier(ActionDemandee(nom="etat"), carte)
        fin = await prise.attendre((await prise.executer(ticket)).id, 5) if rearme and ticket else None
        ajouter("réarmé par un humain : l'état se lit de nouveau", fin is not None and fin.statut == "reussie",
                fin.statut if fin else "réarmement refusé")
        ajouter("aucun ordre de mouvement envoyé", set(temoin.demarrages) <= {"etat"},
                f"reçu par l'adaptateur : {temoin.demarrages}")
        sautes = getattr(adaptateur, "arrets_sautes", 0)
        ajouter("aucune tentative d'arrêt sautée", not sautes, f"{sautes} sautée(s)" if sautes else "")
    finally:
        await prise.deconnecter()
    return c


async def sans_mouvement(fabrique: Callable[[], Adaptateur], vrai_attendu: bool | None = None) -> Rapport:
    """Temps 1. conformite.py en mode sans mouvement, puis les contrôles en plus."""
    try:
        rapport = await verifier_conformite(fabrique, complet=False)
        rapport.controles += await controles_sans_mouvement(fabrique, vrai_attendu)
    except Exception as e:  # un adaptateur pas branché, un robot muet… : le dire clairement, sans planter
        rapport = _rapport_interrompu(fabrique, e)
    return rapport


async def complet(fabrique: Callable[[], Adaptateur], vrai_attendu: bool | None = None,
                  delai_action_s: float = 20.0) -> Rapport:
    """Temps 1 puis temps 2. Le temps 2 ne part que si le temps 1 a réussi."""
    rapport = await sans_mouvement(fabrique, vrai_attendu)
    if not rapport.reussi:
        rapport.controles.append(Controle(nom="temps 2 (complet) non lancé", ok=False, detail="le temps 1 a échoué"))
        return rapport
    try:
        deux = await verifier_conformite(fabrique, complet=True, delai_action_s=delai_action_s)
        rapport.controles += [c.model_copy(update={"nom": f"[complet] {c.nom}"}) for c in deux.controles]
    except Exception as e:
        rapport.controles.append(Controle(nom="[complet] le test est allé au bout", ok=False, detail=_raison(e)))
    return rapport


def _raison(e: Exception) -> str:
    if isinstance(e, ActionRefusee):
        return "refus : " + ", ".join(f"{r.code} {r.details.get('message', '')}".strip() for r in e.raisons)
    return f"{type(e).__name__} : {e}"


def _rapport_interrompu(fabrique: Callable[[], Adaptateur], e: Exception) -> Rapport:
    try:
        carte = fabrique().carte()
        robot, mention = carte.nom, carte.mention_test()
    except Exception:
        robot, mention = "robot inconnu", "non testé"
    return Rapport(robot=robot, mention=mention,
                   controles=[Controle(nom="le test est allé au bout", ok=False, detail=_raison(e))])


# ---------------------------------------------------------------- la confirmation tapée (feu orange)
def confirmer(phrase: str, avertissement: str, lire: Callable[[str], str] | None = None,
              ecrire: Callable[[str], None] = print, nombre: int | None = None) -> bool:
    """Feu orange : rappeler les consignes, puis attendre la phrase exacte suivie d'un nombre tiré au hasard.
    `lire` et `nombre` ne servent qu'aux tests. Sans clavier : refus.
    Protection contre l'OUBLI, pas contre un agent ou un script (un faux clavier se fabrique) : la vraie garde reste
    le feu orange (le « oui » de Hiba, le responsable sécurité, la main sur l'arrêt physique)."""
    phrase = f"{phrase} {nombre if nombre is not None else 1000 + secrets.randbelow(9000)}"
    for ligne in CONSIGNES:
        ecrire(ligne)
    ecrire(avertissement)
    if lire is None:
        if not sys.stdin.isatty():
            ecrire("REFUSÉ : pas de clavier. Cette commande se lance à la main, par un humain, dans un terminal.")
            return False
        lire = input
    try:
        reponse = lire(f"Tapez exactement « {phrase} » pour continuer (autre chose = annuler) : ")
    except (EOFError, KeyboardInterrupt):
        reponse = ""
    if reponse.strip() != phrase:
        ecrire("Annulé : rien n'a été envoyé au robot.")
        return False
    return True
