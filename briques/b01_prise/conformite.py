"""Le test de conformité : un adaptateur est bon s'il passe ce test.

Toutes les actions passent par la prise ET le gardien, même pendant le test.
Mode « sans_mouvement » (par défaut pour un vrai robot) : lit la carte, l'état, et vérifie l'arrêt d'urgence
sans rien faire bouger. Mode « complet » : essaie chaque capacité avec un petit exemple sûr.
Brique 3 (étape 5) : ajout du chronomètre « robot inconnu » et du rapport lisible.
Brique 3 (relecture) : une action qui bouge et finit « échouée » est un échec ; un refus au départ ne passe que s'il
est expliqué par le robot (ex. « pas encore branché »).
"""
from __future__ import annotations

import asyncio
import math
from typing import Callable

from pydantic import BaseModel, Field

from commun.bus import Bus

from .actions import ACTIONS, ActionDemandee
from .adaptateur import Adaptateur
from .carte import CarteIdentite
from .prise import Prise
from .raisons import ActionRefusee


# Les actions qui font bouger le robot : pour elles, « échouée » est un échec du test (relecture de la brique 3),
# sauf un refus expliqué par le robot AVANT de bouger (codes ci-dessous ; et le robot n'a pas changé de place).
BOUGENT = ("se_deplacer", "saisir", "poser", "rejouer_geste", "montrer", "regarder")
REFUS_EXPLIQUES = {"robot_refuse", "non_branchee", "lieu_non_branche", "geste_inconnu", "lieu_inconnu",
                   "objet_introuvable", "trop_loin", "trop_lourd", "main_vide", "main_pleine"}


class Controle(BaseModel):
    nom: str
    ok: bool
    detail: str = ""


class Rapport(BaseModel):
    robot: str
    mention: str
    controles: list[Controle] = Field(default_factory=list)

    @property
    def reussi(self) -> bool:
        return all(c.ok for c in self.controles)

    def texte(self) -> str:
        lignes = [f"Conformité de {self.robot} ({self.mention}) : {'RÉUSSI' if self.reussi else 'ÉCHEC'}"]
        lignes += [f"  {'✔' if c.ok else '✘'} {c.nom} {('— ' + c.detail) if c.detail else ''}" for c in self.controles]
        return "\n".join(lignes)


def _ou_suis_je(etat) -> dict | None:
    """La position du robot : `position`, sinon l'odomètre de l'adaptateur (`extra["odometrie"]`), sinon None."""
    for p in (etat.position, (etat.extra or {}).get("odometrie")):
        if isinstance(p, dict) and {"x", "y"} <= set(p):
            return p
    return None


async def verifier_conformite(fabrique: Callable[[], Adaptateur], complet: bool = True,
                              delai_action_s: float = 20.0) -> Rapport:
    from briques.b07_gardien.gardien import Gardien  # import ici : le gardien dépend de la prise

    adaptateur = fabrique()
    bus = Bus()
    gardien = Gardien(bus)
    prise = Prise(adaptateur, gardien.verificateur, bus)
    carte: CarteIdentite = prise.carte()
    rapport = Rapport(robot=carte.nom, mention=carte.mention_test())
    ajouter = lambda nom, ok, detail="": rapport.controles.append(Controle(nom=nom, ok=bool(ok), detail=detail))

    ajouter("carte d'identité valide", True, f"{len(carte.capacites)} capacités")
    await prise.connecter()
    try:
        etat = await prise.etat()
        ajouter("état lisible", etat.liaison_ok, f"batterie {etat.batterie_pct}")

        # Une action absente de la carte doit être refusée.
        absente = next((a for a in ACTIONS if not carte.sait(a)), None)
        if absente:
            d, ticket = await gardien.verifier(ActionDemandee(nom=absente, parametres=ACTIONS[absente].exemple), carte)
            ajouter(f"refuse « {absente} » (absente de la carte)", d.verdict == "non" and ticket is None)

        # Une action sans ticket doit être refusée par la prise.
        try:
            await prise.executer(object())  # type: ignore[arg-type]
            ajouter("refuse une action sans ticket", False)
        except ActionRefusee as e:
            ajouter("refuse une action sans ticket", e.raisons[0].code == "sans_ticket")

        if complet:
            for nom in carte.capacites:
                if nom in ("arreter",):
                    continue
                exemple = dict(ACTIONS[nom].exemple)
                if nom == "rejouer_geste" and carte.gestes:
                    exemple["nom"] = carte.gestes[0]
                d, ticket = await gardien.verifier(ActionDemandee(nom=nom, parametres=exemple), carte)
                if ticket is None:
                    ajouter(f"action « {nom} »", False, f"gardien : {[r.code for r in d.raisons]}")
                    continue
                try:
                    suivi = await prise.executer(ticket)
                except ActionRefusee as e:  # le robot refuse au départ : rien n'a bougé ; bon seulement si c'est expliqué
                    r = e.raisons[0]
                    message = r.details.get("message", "")
                    ajouter(f"action « {nom} »", r.code == "robot_refuse" and bool(message), f"refusée : {r.code} {message}")
                    continue
                avant = _ou_suis_je(await prise.etat())
                fin = await prise.attendre(suivi.id, delai_action_s)
                apres = _ou_suis_je(await prise.etat())
                # Position inconnue (ni position ni odomètre) : on ne sait pas s'il a bougé → jamais une excuse.
                a_bouge = (math.dist((avant["x"], avant["y"]), (apres["x"], apres["y"])) > 0.05
                           if avant is not None and apres is not None else True)
                # Une action qui BOUGE et finit « échouée » (robot parti à l'envers, arrêté en route…) n'est pas bonne,
                # sauf un refus expliqué par le robot AVANT de bouger (« hors de portée », « pas encore branché »…).
                bon = fin.statut == "reussie" or (fin.statut == "echouee" and (
                    nom not in BOUGENT or (fin.code_erreur in REFUS_EXPLIQUES and not a_bouge)))
                ajouter(f"action « {nom} »", bon, " ".join(x for x in (fin.statut, fin.code_erreur, fin.message) if x))

            longue = next((n for n in carte.capacites if ACTIONS[n].longue and n == "se_deplacer"), None)
            if longue:
                d, ticket = await gardien.verifier(ActionDemandee(nom=longue, parametres={"dx": 2.0}), carte)
                suivi = await prise.executer(ticket)
                await asyncio.sleep(0.2)
                await prise.annuler(suivi.id)
                fin = await prise.attendre(suivi.id, 5)
                ajouter("une action longue s'annule", fin.statut == "annulee", fin.statut)

                d, ticket = await gardien.verifier(ActionDemandee(nom=longue, parametres={"dx": 2.0}), carte)
                suivi = await prise.executer(ticket)
                await asyncio.sleep(0.2)
                await prise.arret_urgence(raison="test_conformite")
                fin = await prise.attendre(suivi.id, 5)
                etat = await prise.etat()
                ajouter("arrêt d'urgence pendant un mouvement", fin.finie and not etat.en_mouvement, fin.statut)
                d, ticket = await gardien.verifier(ActionDemandee(nom="regarder", parametres={"cible": "devant"}), carte)
                try:
                    if ticket:
                        await prise.executer(ticket)
                    ajouter("bloqué tant que non réarmé", ticket is None)
                except ActionRefusee:
                    ajouter("bloqué tant que non réarmé", True)
                await prise.rearmer()

        # L'arrêt d'urgence doit toujours répondre, même sans rien en cours.
        await prise.arret_urgence(raison="test_conformite")
        ajouter("arrêt d'urgence immédiat", prise.arret_urgence_actif)
        await prise.rearmer()
    finally:
        await prise.deconnecter()
    return rapport
