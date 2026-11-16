"""Brique 7 — Le gardien.

Il vérifie chaque action AVANT qu'elle parte, sans dépendre du cerveau.
Seul le gardien possède le guichet qui fabrique les tickets ; la prise refuse toute action sans ticket.

Dans l'ordre :
1. « arreter » : toujours oui. Les demandes qui attendaient un humain sont effacées.
2. Carte d'identité, nombres, limites : `valider` (le même contrôle que la prise refait juste avant d'agir).
   Limites = la plus stricte entre reglages.yaml (securite) et regles.yaml (vitesse_max, force_max).
3. Les règles en phrases simples (regles.yaml) : objets interdits, poids, zones, chemin en ligne droite,
   distance aux personnes, actions qui demandent un humain.

Réponse : « oui » (avec un ticket), « non » (raisons codées, expliquées dans la langue de la personne),
ou « humain » : l'action ne part pas, le robot lève la main (événement `aide_demandee`). Si un humain accepte
(écran), le gardien revérifie TOUT (positions, personnes, règles) avant de délivrer le ticket.
"""
from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field

from briques.b01_prise.actions import ActionDemandee
from briques.b01_prise.carte import CarteIdentite
from briques.b01_prise.raisons import Raison
from briques.b01_prise.ticket import Guichet, Ticket
from briques.b01_prise.validation import valider
from commun.bus import Bus
from commun.evenements import maintenant_iso
from commun.monde import Monde

from .geometrie import arrivee_relative, distance_point_segment
from .perception import Perception, zone_couvre
from .regles import (ACTIONS_PRES_DES_PERSONNES, CHEMIN_REGLES, Regle, Regles, changer, charger_regles, forme_zone,
                     garder_le_plus_strict, noms_par_langue, noms_zone)

Verdict = Literal["oui", "non", "humain"]
ATTENTE_HUMAIN_S = 120.0  # une demande « demande à un humain » reste ouverte 2 minutes
PREFIXE_AGENT = "agent:"  # brique 14 : le demandeur d'une action venue d'un agent d'IA s'écrit « agent:nom »


class LimitesParDefaut(BaseModel):
    """Sécurité des personnes : vitesse, force et distance limitées par défaut, quelle que soit la carte."""

    vitesse_m_s: float = 0.3
    force_n: float = 15.0
    distance_m: float = 5.0
    vitesse_relative_geste: float = 1.0

    def plafonds(self) -> dict[str, float]:
        return {"vitesse": self.vitesse_m_s, "force": self.force_n, "distance": self.distance_m,
                "vitesse_relative": self.vitesse_relative_geste}


class DecisionGardien(BaseModel):
    verdict: Verdict
    action: ActionDemandee | None = None
    raisons: list[Raison] = Field(default_factory=list)
    numero_demande: str | None = None  # verdict « humain » : le numéro de la demande (écran : accepter / refuser)
    non_verifie: list[str] = Field(default_factory=list)  # ce que le gardien n'a pas pu vérifier (sans perception)


class DemandeHumain(BaseModel):
    """Une action qui attend l'accord d'un humain."""

    numero: str
    robot: str
    action: ActionDemandee
    raisons: list[Raison]
    conversation: str | None = None
    demandeur: str = "cerveau"
    heure: str = Field(default_factory=maintenant_iso)


class Gardien:
    def __init__(self, bus: Bus, limites: LimitesParDefaut | None = None, monde: Monde | None = None,
                 regles: str | Path | None = None, perception: Perception | None = None,
                 attente_humain_s: float = ATTENTE_HUMAIN_S, accord_humain_agents: bool = True) -> None:
        self.bus = bus
        # Brique 14 : chaque action demandée par un agent d'IA attend l'accord d'un humain (verdict « humain »),
        # sauf « etat » (lire seulement) ; « arreter » reste toujours permis. reglages.yaml → porte_agents → accord_humain.
        self.accord_humain_agents = accord_humain_agents
        self.limites = limites or LimitesParDefaut()
        self.monde = monde or Monde.charger()
        self.chemin_regles = Path(regles) if regles else CHEMIN_REGLES
        self.regles: Regles = charger_regles(self.chemin_regles, self.monde)  # fichier faux = pas de démarrage
        self._changees_en_direct: set[str] = set()  # règles changées en direct (écran, vote) depuis le démarrage
        # Sans perception (banc d'essai, test de conformité) : ni position ni personnes ; c'est noté à chaque décision.
        self.perception = perception
        self.attente_humain_s = attente_humain_s
        self._demandes: dict[str, tuple[DemandeHumain, float]] = {}
        self.__guichet = Guichet()
        bus.abonner(self._sur_arret_urgence, "arret_urgence")

    @property
    def verificateur(self):
        """La seule chose que la prise reçoit : de quoi vérifier un ticket, pas en fabriquer."""
        return self.__guichet.verifier

    # ---------------------------------------------------------------- limites
    def _maxima(self) -> dict[str, float]:
        """Une règle ne dépasse jamais reglages.yaml (securite), même changée en direct."""
        return {"vitesse_max": self.limites.vitesse_m_s, "force_max": self.limites.force_n}

    def plafonds(self) -> dict[str, float]:
        """Les limites appliquées : la plus stricte entre reglages.yaml (securite) et regles.yaml."""
        p = self.limites.plafonds()
        for r in self.regles.actives("vitesse_max"):
            p["vitesse"] = min(p["vitesse"], float(r.valeurs["m_s"]))
        for r in self.regles.actives("force_max"):
            p["force"] = min(p["force"], float(r.valeurs["n"]))
        return p

    def _completer(self, action: ActionDemandee, carte: CarteIdentite) -> ActionDemandee:
        """Si vitesse ou force manquent, on met la plus petite des deux limites (plafond, carte)."""
        p = dict(action.parametres)
        plafonds = self.plafonds()
        if action.nom == "se_deplacer" and p.get("vitesse") is None:
            p["vitesse"] = min(plafonds["vitesse"], carte.limites.vitesse_max_m_s)
        if action.nom == "saisir" and p.get("force") is None:
            p["force"] = min(plafonds["force"], carte.limites.force_max_n)
        return ActionDemandee(nom=action.nom, parametres=p)

    # ---------------------------------------------------------------- vérifier
    async def verifier(self, action: ActionDemandee, carte: CarteIdentite, conversation: str | None = None,
                       demandeur: str = "cerveau") -> tuple[DecisionGardien, Ticket | None]:
        return await self.__verifier(action, carte, conversation, demandeur, frozenset())

    async def __verifier(self, action: ActionDemandee, carte: CarteIdentite, conversation: str | None,
                         demandeur: str, accordes: frozenset[str]) -> tuple[DecisionGardien, Ticket | None]:
        """accordes : codes « humain » déjà acceptés par un humain pour CETTE demande (jamais un « non »)."""
        if action.nom == "arreter":  # s'arrêter est toujours permis ; les précisions sont ignorées
            self.oublier_demandes()
            decision = DecisionGardien(verdict="oui", action=ActionDemandee(nom="arreter"))
        else:
            complete = self._completer(action, carte)
            raisons = valider(complete, carte, self.plafonds())
            humain: list[Raison] = []
            non_verifie: list[str] = []
            if not raisons:
                raisons, humain, non_verifie = await self._regles(complete, carte)
                if self.accord_humain_agents and demandeur.startswith(PREFIXE_AGENT) and complete.nom != "etat":
                    humain = _sans_doublon(humain + [Raison(code="accord_agent",  # brique 14 : code à part
                                                            details={"action": complete.nom, "demandeur": demandeur})])
                humain = [r for r in humain if r.code not in accordes]
            verdict: Verdict = "non" if raisons else ("humain" if humain else "oui")
            decision = DecisionGardien(verdict=verdict, action=complete, raisons=raisons or humain, non_verifie=non_verifie)
            if verdict == "humain":
                decision.numero_demande = self._noter_demande(decision, carte, conversation, demandeur)

        await self._publier(decision, carte, conversation, demandeur)
        if decision.verdict == "humain":
            await self.bus.emettre("aide_demandee", "gardien", robot=carte.id, conversation=conversation, raison="gardien",
                                   numero=decision.numero_demande, action=decision.action.model_dump(),
                                   raisons=[r.model_dump() for r in decision.raisons], demandeur=demandeur)
        ticket = self.__guichet.emettre(decision.action, carte.id) if decision.verdict == "oui" else None
        return decision, ticket

    async def _publier(self, decision: DecisionGardien, carte: CarteIdentite, conversation: str | None,
                       demandeur: str) -> None:
        await self.bus.emettre(
            "gardien_decision", "gardien", robot=carte.id, conversation=conversation, verdict=decision.verdict,
            action=decision.action.model_dump() if decision.action else None,
            raisons=[r.model_dump() for r in decision.raisons], demandeur=demandeur,
            numero_demande=decision.numero_demande, non_verifie=decision.non_verifie,
        )

    async def _regles(self, action: ActionDemandee, carte: CarteIdentite) -> tuple[list[Raison], list[Raison], list[str]]:
        """Les règles de regles.yaml. Rend (raisons « non », raisons « humain », ce qui n'a pas pu être vérifié)."""
        non: list[Raison] = []
        humain: list[Raison] = []
        non_verifie: list[str] = []
        p, nom, R = action.parametres, action.nom, self.regles

        def noter(liste: list[Raison], code: str, regle: Regle, **details: Any) -> None:
            liste.append(Raison(code=code, details={**details, "regle": regle.id}))

        # ---- les objets
        if nom == "saisir":
            ident = p.get("objet")
            chose = self.monde.objet(ident)
            noms = noms_par_langue(chose) if chose else {}
            for r in R.actives("objets_interdits"):
                if ident in r.valeurs["objets"]:
                    noter(non, "objet_interdit", r, objet=ident, objet_noms=noms)
            for r in R.actives("poids_max"):
                kg = r.valeurs["kg"]
                limite = carte.limites.charge_max_kg if kg == "carte" else min(float(kg), carte.limites.charge_max_kg)
                if chose is None or chose.poids_kg <= 0:
                    noter(humain, "poids_inconnu", r, objet=ident, objet_noms=noms)
                elif chose.poids_kg > limite:
                    noter(non, "trop_lourd", r, objet=ident, objet_noms=noms, poids=chose.poids_kg, limite=limite)
            for r in R.actives("objets_fragiles"):
                if ident in r.valeurs["objets"]:
                    noter(humain, "objet_fragile", r, objet=ident, objet_noms=noms)

        # ---- les actions et gestes qui demandent un humain
        for r in R.actives("demander_humain"):
            geste = p.get("nom") if nom == "rejouer_geste" else None
            if nom in r.valeurs.get("actions", []) or (geste is not None and geste in r.valeurs.get("gestes", [])):
                noter(humain, "humain_requis", r, action=nom, **({"geste": geste} if geste else {}))

        # ---- ce qui demande de savoir où sont le robot et les personnes
        regles_personnes = [r for r in R.actives("distance_personnes")
                            if nom in r.valeurs.get("actions", ACTIONS_PRES_DES_PERSONNES)]
        zones = R.actives("zone_interdite") + R.actives("zone_permise") if nom == "se_deplacer" else []
        if not regles_personnes and not zones:
            return non, _sans_doublon(humain), non_verifie

        arrivee_lieu = None  # vers un lieu nommé : l'arrivée est connue par le monde, même sans perception
        if nom == "se_deplacer" and p.get("lieu") is not None:
            lieu = self.monde.lieu(p["lieu"])
            if lieu is None:
                return non + [Raison(code="lieu_inconnu", details={"lieu": p["lieu"]})], _sans_doublon(humain), non_verifie
            arrivee_lieu = (lieu.position.x, lieu.position.y)

        vue = None
        if self.perception is None:
            non_verifie.append("position du robot et personnes : pas de perception (banc d'essai, test de conformité)")
        else:
            vue = await self.perception.vue()
            if not vue.liaison_ok:
                return non + [Raison(code="liaison_perdue")], _sans_doublon(humain), non_verifie
        depart_cap = vue.position if vue else None
        depart = depart_cap[:2] if depart_cap else None
        if nom == "se_deplacer":
            if arrivee_lieu is not None:
                arrivee = arrivee_lieu
            elif depart_cap is not None:
                arrivee = arrivee_relative(depart_cap, float(p.get("dx") or 0), float(p.get("dy") or 0))
            else:
                arrivee = None
        else:
            arrivee = depart  # le robot ne se déplace pas : seul compte l'endroit où il est

        position_inconnue = False
        for r in zones:
            forme, zone, noms = forme_zone(r, self.monde), r.valeurs.get("lieu") or r.id, noms_zone(r, self.monde)
            if arrivee is None:  # déplacement relatif, position inconnue
                if vue is None:
                    non_verifie.append(f"zone « {r.id} » : déplacement relatif sans position du robot")
                else:
                    position_inconnue = True
                continue
            if r.sorte == "zone_permise":
                if not forme.contient(arrivee):
                    noter(non, "hors_zone_permise", r, zone=zone, zone_noms=noms)
                continue
            if forme.contient(arrivee):
                noter(non, "zone_interdite", r, zone=zone, zone_noms=noms)
            elif depart is None:
                if vue is None:
                    non_verifie.append(f"zone « {r.id} » : chemin non vérifié (position du robot inconnue)")
                else:
                    position_inconnue = True
            elif not forme.contient(depart) and forme.coupe(depart, arrivee):
                # (un robot déjà DANS la zone a le droit d'en sortir : la zone est convexe, il ne repasse pas dedans)
                noter(non, "chemin_zone_interdite", r, zone=zone, zone_noms=noms)

        for r in regles_personnes:
            if vue is None:
                non_verifie.append(f"règle « {r.id} » : pas de perception")
                continue
            if vue.personnes is None:  # pas de nouvelles des yeux
                if r.valeurs.get("si_personnes_inconnues", "humain") == "humain":
                    noter(humain, "personnes_inconnues", r)
                continue
            zone = vue.zone_vue  # brique 5 : le sol vu par la caméra (None : personnes simulées, connues partout)
            if not vue.personnes and zone is None:
                continue
            if depart is None:
                position_inconnue = True
                continue
            fin = arrivee if arrivee is not None else depart
            m = float(r.valeurs["m"])
            if zone is not None and not zone_couvre(zone, depart, fin, m):
                # « pas vue » n'est pas « pas là » : une personne peut être hors du champ (derrière, à côté, tout près)
                noter(humain, "personnes_inconnues", r, hors_du_champ=True)
            if vue.personnes:
                distances = [(distance_point_segment((q.x, q.y), depart, fin), q.id) for q in vue.personnes]
                d, qui = min(distances)
                if d < m:
                    noter(non, "trop_pres_personne", r, distance=round(d, 2), limite=m, personne=qui)

        if position_inconnue:
            humain.append(Raison(code="position_inconnue"))
        return non, _sans_doublon(humain), non_verifie

    # ---------------------------------------------------------------- demander à un humain
    def _noter_demande(self, decision: DecisionGardien, carte: CarteIdentite, conversation: str | None,
                       demandeur: str) -> str:
        self._nettoyer()
        numero = uuid.uuid4().hex[:8]
        # Une COPIE de l'action : la modifier après coup ne change pas ce que l'humain a vu et accepté.
        d = DemandeHumain(numero=numero, robot=carte.id, action=decision.action.model_copy(deep=True),
                          raisons=[r.model_copy(deep=True) for r in decision.raisons],
                          conversation=conversation, demandeur=demandeur)
        self._demandes[numero] = (d, time.monotonic() + self.attente_humain_s)
        return numero

    def _nettoyer(self) -> None:
        maintenant = time.monotonic()
        for numero, (_, expire) in list(self._demandes.items()):
            if expire < maintenant:
                del self._demandes[numero]

    def demandes_en_attente(self) -> list[dict[str, Any]]:
        """Pour l'écran : les actions qui attendent un humain."""
        self._nettoyer()
        maintenant = time.monotonic()
        return [{**d.model_dump(), "reste_s": round(expire - maintenant)} for d, expire in self._demandes.values()]

    def oublier_demandes(self, lesquelles: Callable[[DemandeHumain], bool] | None = None) -> int:
        """« Stop », « arreter » ou arrêt d'urgence : plus aucune demande en attente ne peut partir.
        Brique 11 : `lesquelles(demande)` → seulement ces demandes (quand la main change de camp : humain / robot)."""
        if lesquelles is None:
            n = len(self._demandes)
            self._demandes.clear()
            return n
        oubliees = [numero for numero, (d, _) in self._demandes.items() if lesquelles(d)]
        for numero in oubliees:
            del self._demandes[numero]
        return len(oubliees)

    def _sur_arret_urgence(self, _ev=None) -> None:
        self.oublier_demandes()

    async def reponse_humaine(self, numero: str, accepte: bool, carte: CarteIdentite,
                              qui: str = "humain") -> tuple[DecisionGardien, Ticket | None]:
        """Un humain accepte ou refuse une demande. S'il accepte, le gardien revérifie TOUT avant le ticket :
        seules les raisons « humain » de CETTE demande sont levées ; un « non » reste un « non »."""
        self._nettoyer()
        entree = self._demandes.pop(numero, None)
        d = entree[0] if entree else None
        if d is not None:  # une aide comptée seulement pour une vraie demande (pas un double clic, pas un faux numéro)
            await self.bus.emettre("aide_recue", "gardien", robot=carte.id, conversation=d.conversation,
                                   sorte="demande_du_gardien", numero=numero, accepte=bool(accepte), qui=qui)
        if d is None or d.robot != carte.id:
            decision = DecisionGardien(verdict="non", action=d.action if d else None,
                                       raisons=[Raison(code="demande_perimee", details={"numero": numero})])
            await self._publier(decision, carte, d.conversation if d else None, f"humain:{qui}")
            return decision, None
        if not accepte:
            decision = DecisionGardien(verdict="non", action=d.action, raisons=[Raison(code="refuse_par_humain")])
            await self._publier(decision, carte, d.conversation, f"humain:{qui}")
            return decision, None
        return await self.__verifier(d.action, carte, d.conversation, f"humain:{qui}", frozenset(r.code for r in d.raisons))

    # ---------------------------------------------------------------- changer les règles en direct
    def regles_lisibles(self) -> list[dict[str, Any]]:
        return self.regles.lisibles()

    async def changer_regle(self, ident: str, active: bool | None = None, valeurs: dict[str, Any] | None = None,
                            qui: str = "humain", comment: str = "en direct", vote: dict | None = None) -> Regle:
        """Allumer, éteindre, ou changer le chiffre d'une règle. Noté dans la boîte noire (`regle_changee`).
        Le changement dure jusqu'à l'arrêt du programme (ou « relire les règles ») : le fichier ne change pas."""
        regle = self.regles.regle(ident)
        if regle is None:
            raise ValueError(f"règle inconnue « {ident} »")
        nouvelle = changer(regle, active, valeurs, self._maxima())
        self.regles = self.regles.model_copy(update={"regles": [nouvelle if r.id == ident else r for r in self.regles.regles]})
        self._changees_en_direct.add(ident)
        await self.bus.emettre("regle_changee", "gardien", regle=ident, avant=regle.lisible(), apres=nouvelle.lisible(),
                               qui=qui, comment=comment, **({"vote": vote} if vote else {}))
        return nouvelle

    async def recharger(self, qui: str = "humain") -> dict[str, Any]:
        """Relire regles.yaml. Fichier faux : erreur, et les règles d'avant restent en place.

        Ce qui a été rendu PLUS STRICT en direct (règle allumée, vitesse ou force plus basse, distance plus grande)
        est GARDÉ, jamais annulé en silence : c'est le choix le plus sûr (relire le fichier ne doit pas rendre le
        robot moins prudent sans que personne le voie). Ce qui est gardé est écrit dans la réponse (`gardees`) et
        dans la boîte noire. Pour revenir au fichier tel quel : redémarrer le programme (ou changer la règle en
        direct, si elle le permet). Rend {"changees": [ids], "gardees": [{regle, garde: [...]}]}."""
        fichier = charger_regles(self.chemin_regles, self.monde)
        regles: list[Regle] = []
        gardees: list[dict[str, Any]] = []
        for r in fichier.regles:
            direct = self.regles.regle(r.id)
            if r.id in self._changees_en_direct and direct is not None:
                if direct.sorte != r.sorte:  # même nom, autre sorte : rien à comparer, et c'est dit
                    gardees.append({"regle": r.id, "garde": [], "perdu": "la sorte a changé dans le fichier : "
                                    "le changement fait en direct n'est pas gardé"})
                else:
                    r, garde = garder_le_plus_strict(r, direct)
                    if garde:
                        gardees.append({"regle": r.id, "garde": garde})
            regles.append(r)
        dans_le_fichier = {r.id for r in fichier.regles}
        for ident in sorted(self._changees_en_direct - dans_le_fichier):  # changée en direct, enlevée du fichier
            direct = self.regles.regle(ident)
            if direct is not None and direct.active:
                regles.append(direct)
                gardees.append({"regle": ident, "garde": ["absente du fichier, mais allumée en direct : gardée telle quelle"]})
        nouvelles = fichier.model_copy(update={"regles": regles})
        avant = {r.id: r.lisible() for r in self.regles.regles}
        apres = {r.id: r.lisible() for r in nouvelles.regles}
        changees = sorted(i for i in avant.keys() | apres.keys() if avant.get(i) != apres.get(i))
        self.regles = nouvelles
        self._changees_en_direct = {g["regle"] for g in gardees if g["garde"]}  # le reste vient du fichier, tel quel
        notes = {g["regle"]: g for g in gardees}
        for i in changees:
            await self.bus.emettre("regle_changee", "gardien", regle=i, avant=avant.get(i), apres=apres.get(i),
                                   qui=qui, comment="fichier relu",
                                   **({"garde_du_direct": notes[i]} if i in notes else {}))
        if gardees:
            resume = " ; ".join(f"{g['regle']} : {', '.join(g['garde']) or g.get('perdu', '')}" for g in gardees)
            await self.bus.emettre("note", "gardien", qui=qui, gardees=gardees,
                                   texte=f"règles relues ; changements faits en direct (plus stricts, gardés) : {resume}")
        return {"changees": changees, "gardees": gardees}


def _sans_doublon(raisons: list[Raison]) -> list[Raison]:
    vus: set[str] = set()
    garde = []
    for r in raisons:
        if r.code not in vus:
            vus.add(r.code)
            garde.append(r)
    return garde
