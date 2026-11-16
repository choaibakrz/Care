"""Brique 2 — Le faux robot.

Un robot imaginaire qui respecte la prise universelle, pour travailler sans matériel.
- Il simule ses gestes dans le temps (un déplacement prend du temps, peut être suivi et annulé).
- Il peut tomber en panne sur commande : lenteur, refus, perte de liaison, batterie faible.
- Il a son propre chien de garde : sans signe de vie de la prise, il s'arrête seul.
"""
from __future__ import annotations

import asyncio
import math
import time
import uuid
from pathlib import Path

from briques.b01_prise.actions import ActionDemandee
from briques.b01_prise.adaptateur import (
    ActionImpossible,
    Adaptateur,
    EtatRobot,
    LiaisonPerdue,
    SuiviAction,
)
from briques.b01_prise.carte import CarteIdentite
from commun.monde import Monde

DOSSIER_CARTES = Path(__file__).with_name("cartes")
PANNES = {
    "lenteur": "Le robot répond et bouge 4 fois plus lentement.",
    "refus": "Le robot refuse toutes les nouvelles actions.",
    "perte_liaison": "Le robot ne répond plus du tout.",
    "batterie_faible": "La batterie tombe à 5 %.",
    "arret_ignore": "Le robot ignore l'arrêt d'urgence logiciel (seul le bouton physique marcherait).",
}
LONGUES = {"se_deplacer", "saisir", "poser", "rejouer_geste"}
DUREES_S = {"regarder": 0.6, "ecouter": 0.5, "parler": 0.8, "saisir": 1.2, "poser": 1.0, "montrer": 0.8,
            "rejouer_geste": 1.5, "etat": 0.0, "arreter": 0.0}


def cartes_disponibles() -> list[str]:
    return sorted(p.stem for p in DOSSIER_CARTES.glob("*.yaml"))


class FauxRobot(Adaptateur):
    def __init__(self, genre: str = "humanoide", monde: Monde | None = None, acceleration: float = 1.0,
                 delai_chien_de_garde_s: float = 0.6, suffixe_id: str = "") -> None:
        self._carte = CarteIdentite.charger(DOSSIER_CARTES / f"{genre}.yaml")
        if suffixe_id:
            self._carte = self._carte.model_copy(update={"id": self._carte.id + suffixe_id,
                                                          "nom": f"{self._carte.nom} {suffixe_id.strip('-')}"})
        self.monde = monde or Monde.charger()
        self.acceleration = acceleration  # >1 pour accélérer les tests
        self.delai_chien = delai_chien_de_garde_s
        depart = self.monde.depart
        if self._carte.position_fixe and self.monde.lieu(self._carte.position_fixe):
            p = self.monde.lieu(self._carte.position_fixe).position
            depart = p.model_copy(update={"y": p.y - 0.4})
        self.x, self.y, self.cap = depart.x, depart.y, depart.cap
        self.objets = {o.id: [o.position.x, o.position.y] for o in self.monde.objets}
        self.objet_tenu: str | None = None
        self.batterie = 100.0
        self.erreurs: list[str] = []
        self.pannes: set[str] = set()
        self.arret_urgence_actif = False
        self._numero_arret = 0
        self.dernier_battement = time.monotonic()
        self.dernier_geste = ""
        self.trace: list[tuple[float, float]] = [(self.x, self.y)]
        self._suivis: dict[str, SuiviAction] = {}
        self._taches: dict[str, asyncio.Task] = {}
        self._chien: asyncio.Task | None = None

    # ---------- pannes provoquées ----------
    def provoquer_panne(self, nom: str) -> None:
        if nom not in PANNES:
            raise ValueError(f"Panne inconnue : {nom}. Connues : {list(PANNES)}")
        self.pannes.add(nom)
        if nom == "batterie_faible":
            self.batterie = 5.0

    def reparer(self, nom: str | None = None) -> None:
        self.pannes = set() if nom is None else self.pannes - {nom}
        self.dernier_battement = time.monotonic()

    async def _reseau(self) -> None:
        """Simule le temps de réponse et la perte de liaison."""
        if "perte_liaison" in self.pannes:
            raise LiaisonPerdue("faux robot : liaison coupée (panne provoquée)")
        if "lenteur" in self.pannes:
            await asyncio.sleep(0.3)

    # ---------- prise universelle ----------
    def carte(self) -> CarteIdentite:
        return self._carte

    async def connecter(self) -> None:
        self.dernier_battement = time.monotonic()
        self._chien = asyncio.create_task(self._chien_de_garde())

    async def deconnecter(self) -> None:
        try:
            await self.arret_urgence()
        except LiaisonPerdue:
            self._tout_annuler("déconnexion")  # le programme s'arrête : la simulation s'arrête aussi
        finally:
            if self._chien:
                self._chien.cancel()

    async def battement(self) -> None:
        await self._reseau()
        self.dernier_battement = time.monotonic()

    async def demarrer(self, action: ActionDemandee) -> str:
        await self._reseau()
        if self.arret_urgence_actif and action.nom != "arreter":
            raise ActionImpossible("arret_urgence_actif", "arrêt d'urgence actif")
        if "refus" in self.pannes and action.nom not in ("arreter", "etat"):
            raise ActionImpossible("robot_refuse", "le faux robot refuse (panne provoquée)")
        if action.nom == "arreter":  # arrêt normal : le robot arrête lui-même tout ce qu'il fait
            self._tout_annuler("arrêt demandé")
        elif action.nom in LONGUES and self._occupe():
            raise ActionImpossible("robot_occupe", "le faux robot fait déjà une action longue")
        ident = uuid.uuid4().hex[:8]
        suivi = SuiviAction(id=ident, action=action, statut="en_cours")
        self._suivis[ident] = suivi
        self._taches[ident] = asyncio.create_task(self._jouer(suivi))
        return ident

    async def suivre(self, ident: str) -> SuiviAction:
        await self._reseau()
        return self._suivis[ident]

    async def annuler(self, ident: str) -> None:
        await self._reseau()
        tache = self._taches.get(ident)
        if tache and not tache.done():
            tache.cancel()
        s = self._suivis.get(ident)
        if s and not s.finie:
            s.statut, s.message = "annulee", "annulée"

    async def arret_urgence(self) -> None:
        # Comme un vrai robot : l'ordre passe par le réseau. Liaison coupée = l'ordre n'arrive pas
        # (le chien de garde du robot l'arrêtera quand même, faute de signe de vie).
        if "perte_liaison" in self.pannes:
            raise LiaisonPerdue("faux robot : arrêt d'urgence non reçu (liaison coupée)")
        if "arret_ignore" in self.pannes:
            return
        self.arret_urgence_actif = True
        self._numero_arret += 1
        self._tout_annuler("arrêt d'urgence", "arret_urgence")

    async def rearmer(self) -> None:
        numero = self._numero_arret
        await self._reseau()
        if numero == self._numero_arret:  # pas de nouvel arrêt pendant le réarmement
            self.arret_urgence_actif = False

    def _occupe(self) -> bool:
        return any(not t.done() and self._suivis[i].action.nom in LONGUES for i, t in self._taches.items())

    def _tout_annuler(self, message: str, code: str | None = None) -> None:
        for ident, tache in list(self._taches.items()):
            if not tache.done():
                tache.cancel()
            s = self._suivis[ident]
            if not s.finie:
                s.statut, s.message, s.code_erreur = "annulee", message, code

    async def etat_robot(self) -> EtatRobot:
        await self._reseau()
        en_mouvement = any(not t.done() for t in self._taches.values())
        return EtatRobot(
            batterie_pct=round(self.batterie, 1), erreurs=list(self.erreurs),
            position={"x": round(self.x, 3), "y": round(self.y, 3), "cap": round(self.cap, 1)},
            objet_tenu=self.objet_tenu, en_mouvement=en_mouvement, liaison_ok=True,
            arret_urgence_actif=self.arret_urgence_actif,
            extra={"pannes": sorted(self.pannes), "dernier_geste": self.dernier_geste,
                   "objets": {k: [round(v[0], 2), round(v[1], 2)] for k, v in self.objets.items()},
                   "genre": self._carte.genre, "simulation": True},
        )

    # ---------- simulation ----------
    async def _chien_de_garde(self) -> None:
        while True:
            await asyncio.sleep(0.1)
            if time.monotonic() - self.dernier_battement > self.delai_chien:
                if any(not t.done() for t in self._taches.values()):
                    for ident, t in list(self._taches.items()):
                        if not t.done():
                            t.cancel()
                            s = self._suivis[ident]
                            s.statut, s.code_erreur = "echouee", "chien_de_garde"
                            s.message = "plus de nouvelles de la prise : arrêt par le chien de garde"
                    self.erreurs.append("chien de garde : arrêt faute de signe de vie")

    def _facteur(self) -> float:
        return self.acceleration * (0.25 if "lenteur" in self.pannes else 1.0)

    async def _attendre(self, suivi: SuiviAction, duree_s: float) -> None:
        pas = 0.02
        ecoule = 0.0
        while ecoule < duree_s:
            await asyncio.sleep(pas)
            ecoule += pas * self._facteur()
            suivi.progression = min(1.0, ecoule / duree_s) if duree_s else 1.0

    def _distance(self, x: float, y: float) -> float:
        return math.hypot(x - self.x, y - self.y)

    def _trouver_lieu(self, nom: str) -> tuple[float, float] | None:
        if nom == "ici":
            return (self.x, self.y)
        lieu = self.monde.lieu(nom)
        return (lieu.position.x, lieu.position.y) if lieu else None

    async def _jouer(self, s: SuiviAction) -> None:
        a, p = s.action, s.action.parametres
        try:
            if a.nom == "se_deplacer":
                await self._deplacer(s, p)
            elif a.nom == "saisir":
                obj = self.monde.objet(p["objet"])
                if obj is None or p["objet"] not in self.objets:
                    return self._echec(s, "objet_introuvable", f"je ne trouve pas « {p['objet']} »")
                ox, oy = self.objets[p["objet"]]
                if self._distance(ox, oy) > self._carte.limites.portee_max_m:
                    return self._echec(s, "trop_loin", f"« {p['objet']} » est hors de portée")
                if obj.poids_kg > self._carte.limites.charge_max_kg:
                    return self._echec(s, "trop_lourd", f"« {p['objet']} » est trop lourd ({obj.poids_kg} kg)")
                if self.objet_tenu:
                    return self._echec(s, "main_pleine", f"je tiens déjà « {self.objet_tenu} »")
                await self._attendre(s, DUREES_S["saisir"])
                if self.objet_tenu:  # revérifier à la fin : la main a pu se remplir entre-temps
                    return self._echec(s, "main_pleine", f"je tiens déjà « {self.objet_tenu} »")
                self.objet_tenu = p["objet"]
            elif a.nom == "poser":
                if not self.objet_tenu:
                    return self._echec(s, "main_vide", "je ne tiens rien")
                cible = self._trouver_lieu(p.get("lieu", "ici"))
                if cible is None:
                    return self._echec(s, "lieu_inconnu", f"lieu inconnu « {p.get('lieu')} »")
                if self._distance(*cible) > self._carte.limites.portee_max_m + 0.3:
                    return self._echec(s, "trop_loin", "le lieu est hors de portée")
                await self._attendre(s, DUREES_S["poser"])
                self.objets[self.objet_tenu] = [cible[0], cible[1]]
                self.objet_tenu = None
            elif a.nom in ("arreter", "etat"):
                s.progression = 1.0
            else:
                self.dernier_geste = f"{a.nom} {p.get('cible') or p.get('nom') or p.get('texte') or ''}".strip()
                await self._attendre(s, DUREES_S.get(a.nom, 0.5))
            if s.statut == "echouee":
                return
            s.statut, s.progression = "reussie", 1.0
            s.message = s.message or "fait"
        except asyncio.CancelledError:
            if not s.finie:
                s.statut, s.message = "annulee", s.message or "annulée"
            raise

    def _echec(self, s: SuiviAction, code: str, message: str) -> None:
        s.statut, s.code_erreur, s.message = "echouee", code, message

    async def _deplacer(self, s: SuiviAction, p: dict) -> None:
        if "lieu" in p and p["lieu"] is not None:
            cible = self._trouver_lieu(p["lieu"])
            if cible is None:
                return self._echec(s, "lieu_inconnu", f"lieu inconnu « {p['lieu']} »")
        else:
            rad = math.radians(self.cap)
            dx, dy = p.get("dx") or 0.0, p.get("dy") or 0.0
            if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (dx, dy)):
                return self._echec(s, "valeur_invalide", "déplacement invalide")
            cible = (self.x + dx * math.cos(rad) - dy * math.sin(rad), self.y + dx * math.sin(rad) + dy * math.cos(rad))
        vitesse = p.get("vitesse")
        if vitesse is None:
            vitesse = self._carte.limites.vitesse_max_m_s
        if not isinstance(vitesse, (int, float)) or not math.isfinite(vitesse) or vitesse <= 0:
            return self._echec(s, "valeur_invalide", f"vitesse invalide : {vitesse}")
        vitesse = min(vitesse, self._carte.limites.vitesse_max_m_s)
        depart = (self.x, self.y)
        total = math.dist(depart, cible)
        if total < 1e-6:
            return
        self.cap = math.degrees(math.atan2(cible[1] - depart[1], cible[0] - depart[0]))
        parcouru = 0.0
        while parcouru < total:
            await asyncio.sleep(0.02)
            parcouru = min(total, parcouru + vitesse * 0.02 * self._facteur())
            f = parcouru / total
            self.x = depart[0] + (cible[0] - depart[0]) * f
            self.y = depart[1] + (cible[1] - depart[1]) * f
            self.batterie = max(0.0, self.batterie - 0.001)
            s.progression = f
            if self.objet_tenu:
                self.objets[self.objet_tenu] = [self.x, self.y]
            if len(self.trace) > 500:
                self.trace = self.trace[-400:]
            self.trace.append((round(self.x, 2), round(self.y, 2)))
