"""Brique 11 — La main humaine (idée 13 : « pilotage affiché »).

Un humain prend la main depuis l'écran de l'équipe (bouton protégé par le code d'équipe), puis la rend.
En la prenant : un arrêt normal part TOUJOURS (par le gardien), et la tablette reçoit un jeton, exigé pour donner
des ordres et rendre la main (une autre tablette peut seulement « Libérer la main », noté dans la boîte noire).
À chaque changement de main, les demandes à un humain de l'autre camp sont oubliées (voir `Chaine.changer_de_main`).
Pendant ce temps :
- la voix, les agents et la tablette ne commandent plus le robot : la chaîne répond poliment « un humain pilote »
  (commun/chaine.py). « Stop » passe toujours ; l'arrêt d'urgence reste ouvert à tous ;
- l'humain donne des ordres simples par des boutons (les actions de la carte d'identité, avec leurs précisions).
  Chacun suit le même chemin que tout le monde : formulaire → gardien (ticket) → prise. Jamais d'appel direct au
  robot. Un refus du gardien est expliqué à l'écran ;
- tout est noté dans la boîte noire, événement `pilotage_humain`, champ `quoi` :
    reprise (qui), ordre (qui, action), rendu (qui, duree_s, ordres, fait),
    demande (le chef de démonstration demande qu'un humain prenne la main : consigne),
    demande_retiree (personne ne l'a prise à temps, ou le chef s'est arrêté).
  La fiche de vérité en tire la part de l'humain (temps entre reprise et rendu) et les ordres de l'humain.
Rendre la main remet tout comme avant. Testé sur faux robot.
"""
from __future__ import annotations

import asyncio
import hmac
import math
import secrets
import time
import uuid
from typing import Any

from briques.b01_prise.actions import ACTIONS, ActionDemandee
from commun.evenements import Evenement, maintenant_iso
from commun.phrases import dire, expliquer_refus, langues

SOURCE = "main_humaine"
ATTENTE_CHEF_S = 120.0  # le chef attend au plus 2 minutes qu'un humain prenne la main (choix, pas une mesure)
ATTENTE_RENDU_S = 300.0  # … puis au plus 5 minutes qu'il la rende ; ensuite il passe à la suite (choix, pas une mesure)
QUI_MAX = 40


class Refus(Exception):
    """Ce que la main humaine refuse avant même le gardien (expliqué en français à l'écran). Réponse HTTP 409, même
    pour un jeton faux : le 403 est réservé au code d'équipe (la page redemande alors le code)."""


def nom_propre(qui: str | None) -> str:
    """Un prénom ou un rôle, écrit tel quel dans la boîte noire. Pas vérifié : ce n'est pas un mot de passe."""
    return " ".join(str(qui or "").split())[:QUI_MAX] or "équipe"


def nettoyer(nom: str, parametres: dict[str, Any] | None) -> dict[str, Any]:
    """Les précisions venues des boutons : les vides sont retirées, les nombres lus (« 0,5 » = 0.5).
    Le reste est laissé tel quel : le gardien refuse et explique (précision inconnue, pas claire, trop grande…)."""
    definition = ACTIONS.get(nom)
    types = {p.nom: p.type for p in definition.parametres} if definition else {}
    propre: dict[str, Any] = {}
    for cle, v in (parametres or {}).items():
        if v is None or (isinstance(v, str) and not v.strip()):
            continue
        if isinstance(v, str):
            v = v.strip()
            if types.get(cle) == "nombre":
                try:
                    n = float(v.replace(",", "."))
                    v = n if math.isfinite(n) else v
                except ValueError:
                    pass  # le gardien dira « une précision n'est pas claire »
        propre[cle] = v
    return propre


def _nom_fr(chose) -> str:
    noms = chose.noms.get("fr") or [chose.id]
    return noms[0]


def decrire(action: ActionDemandee | dict | None, monde) -> str:
    """L'action en français simple, pour l'écran (« aller à : cuisine », « prendre : tasse »)."""
    if action is None:
        return ""
    if isinstance(action, dict):
        action = ActionDemandee(**action)
    p = action.parametres

    def nom(ident) -> str:
        chose = monde.lieu(str(ident)) or monde.objet(str(ident)) if ident is not None else None
        return _nom_fr(chose) if chose else str(ident or "?")

    vitesse = f" à {p['vitesse']} m/s" if p.get("vitesse") is not None else ""
    if action.nom == "se_deplacer":
        if p.get("lieu"):
            return f"aller à : {nom(p['lieu'])}{vitesse}"
        try:
            d = math.hypot(float(p.get("dx") or 0), float(p.get("dy") or 0))
            return f"se déplacer de {round(d, 2):g} m{vitesse}"
        except (TypeError, ValueError):
            return f"se déplacer{vitesse}"
    textes = {
        "saisir": lambda: f"prendre : {nom(p.get('objet'))}" + (f" ({p['force']} N)" if p.get("force") is not None else ""),
        "poser": lambda: "poser l'objet" + (f" à : {nom(p['lieu'])}" if p.get("lieu") and p["lieu"] != "ici" else " ici"),
        "regarder": lambda: f"regarder : {nom(p.get('cible'))}",
        "montrer": lambda: f"montrer : {nom(p.get('cible'))}",
        "rejouer_geste": lambda: f"faire le geste : {p.get('nom', '?')}",
        "parler": lambda: f"dire : « {p.get('texte', '')} »",
        "ecouter": lambda: "écouter",
        "arreter": lambda: "s'arrêter",
        "etat": lambda: "dire son état (batterie)",
    }
    return textes[action.nom]() if action.nom in textes else action.resume()


class MainHumaine:
    """Qui a la main, ses ordres, et la demande du chef de démonstration. Un seul humain à la fois."""

    def __init__(self, systeme: Any, attente_chef_s: float = ATTENTE_CHEF_S,
                 attente_rendu_s: float = ATTENTE_RENDU_S) -> None:
        self.s = systeme
        self.attente_chef_s = attente_chef_s
        self.attente_rendu_s = attente_rendu_s
        self.qui: str | None = None
        self._jeton: str | None = None  # remis à la tablette qui a pris la main (jamais dans l'état ni la boîte noire)
        self.depuis: str | None = None  # heure (UTC, lisible)
        self._t0: float | None = None
        self.ordres = 0  # ordres envoyés pendant cette main humaine
        self.dernier: dict | None = None  # réponse au dernier ordre (pour l'écran)
        self.consigne: dict | None = None  # ce que le chef de démonstration demande (plan B « main humaine »)
        self._quand_prise: asyncio.Future | None = None
        self._quand_rendue: asyncio.Future | None = None
        self.annoncee: dict | None = None  # main humaine annoncée par un autre (chef, opérateur simulé ou clavier)
        systeme.bus.abonner(self._sur_pilotage, "pilotage_humain")

    # ---------------------------------------------------------------- lire
    def etat(self, court: bool = False, jeton: str | None = None) -> dict[str, Any]:
        """`a_moi` : la tablette qui demande (son jeton) est-elle celle qui a la main ?"""
        e: dict[str, Any] = {
            "qui": self.qui, "depuis": self.depuis, "ordres": self.ordres,
            "duree_s": round(time.monotonic() - self._t0, 1) if self._t0 is not None else None,
            "consigne": self.consigne, "annoncee": self.annoncee, "a_moi": self.a_le_jeton(jeton),
            "mention": self.s.prise.carte().mention_test(),
        }
        if court:
            return e
        interrupteur = (self.s.reglages.get("interrupteurs") or {}).get("vote_public") or {}
        vote = bool(interrupteur.get("actif", False))
        return {**e, "dernier": self.dernier, "actions": self.formulaire(),
                "demandes": self.demandes(), "mots_appris": self.s.doute.aides.liste(),
                "sens_possibles": [{"valeur": c.id, "texte": _nom_fr(c)} for c in [*self.s.monde.lieux, *self.s.monde.objets]],
                "langues": {code: info["nom"] for code, info in langues()["langues"].items()},
                "vote_public": vote, "votes": [v.model_dump() for v in self.s.gardien.regles.votes] if vote else []}

    def demandes(self) -> list[dict[str, Any]]:
        """Les demandes du gardien qui attendent un humain, avec l'action et les raisons en français."""
        res = []
        for d in self.s.gardien.demandes_en_attente():
            demandeur = str(d.get("demandeur") or "")
            res.append({**d, "action_texte": decrire(d.get("action"), self.s.monde),
                        "raisons_texte": expliquer_refus(d.get("raisons") or [], "fr", intro="").strip(),
                        "demandeur_texte": _demandeur(demandeur)})
        return res

    def formulaire(self) -> list[dict[str, Any]]:
        """Les boutons : les actions de la carte d'identité, et le choix possible pour chaque précision."""
        carte, monde = self.s.prise.carte(), self.s.monde
        lieux = [{"valeur": c.id, "texte": _nom_fr(c)} for c in monde.lieux]
        objets = [{"valeur": c.id, "texte": _nom_fr(c)} for c in monde.objets]
        res = []
        for nom in carte.capacites:
            definition = ACTIONS[nom]
            parametres = []
            for p in definition.parametres:
                choix = None
                if p.nom == "lieu":
                    choix = lieux + ([{"valeur": "ici", "texte": "ici"}] if nom == "poser" else [])
                elif p.nom == "objet":
                    choix = objets
                elif p.nom == "cible":
                    choix = lieux + objets
                elif nom == "rejouer_geste" and p.nom == "nom":
                    choix = [{"valeur": g, "texte": g} for g in carte.gestes]
                elif p.type == "langue":
                    choix = [{"valeur": c, "texte": i["nom"]} for c, i in langues()["langues"].items()]
                parametres.append({"nom": p.nom, "type": p.type, "unite": p.unite, "obligatoire": p.obligatoire,
                                   "explication": p.explication, "choix": choix})
            res.append({"nom": nom, "texte": dire(f"actions.{nom}", "fr"), "longue": definition.longue,
                        "parametres": parametres, "un_parmi": definition.un_parmi})
        return res

    def a_le_jeton(self, jeton: str | None) -> bool:
        """Le jeton remis à la tablette qui a pris la main (comparé sans fuite de temps)."""
        return bool(self._jeton and jeton) and hmac.compare_digest(str(jeton), self._jeton)

    # ---------------------------------------------------------------- prendre, rendre
    async def prendre(self, qui: str | None) -> dict[str, Any]:
        """Rend l'état ET le jeton : seule la tablette qui l'a reçu peut donner des ordres et rendre la main."""
        qui = nom_propre(qui)
        if self.qui is not None:
            raise Refus(f"{self.qui} a déjà la main : il faut d'abord la rendre (ou « Libérer la main »).")
        self.qui, self.depuis, self._t0, self.ordres, self.dernier = qui, maintenant_iso(), time.monotonic(), 0, None
        self._jeton = secrets.token_urlsafe(18)
        oubliees = self.s.chaine.changer_de_main(qui)  # d'abord fermer la porte aux phrases, puis le dire
        conv_arret = uuid.uuid4().hex[:10]  # la conversation de l'arrêt envoyé en prenant la main
        await self._emettre("reprise", conversation=conv_arret, qui=qui, consigne=(self.consigne or {}).get("texte"),
                            par="ecran", mention=self.s.prise.carte().mention_test(), demandes_oubliees=oubliees,
                            arret_envoye=True)
        # TOUJOURS un arrêt normal en prenant la main, par le même chemin que tout le monde (gardien → ticket → prise) :
        # ce que le robot faisait seul s'arrête, et une action de la voix en train de partir est refusée par la prise
        # (ticket d'avant l'arrêt) ou arrêtée par le robot. La fiche ne le compte pas comme une réussite du robot.
        await self.s.chaine.ordre_humain(ActionDemandee(nom="arreter"), qui, conversation=conv_arret)
        if self._quand_prise is not None and not self._quand_prise.done():
            self._quand_prise.set_result(qui)
        return {**self.etat(jeton=self._jeton), "jeton": self._jeton}

    async def rendre(self, jeton: str | None = None, qui: str | None = None, fait: bool | None = None,
                     forcer: bool = False) -> dict[str, Any]:
        """Avec le jeton : rendre normalement. Sans le jeton : seulement `forcer` (« Libérer la main », depuis une
        autre tablette, par exemple si celle du pilote est éteinte) — noté dans la boîte noire (`force`)."""
        if self.qui is None:
            return self.etat()  # personne n'avait la main : rien à rendre
        force = not self.a_le_jeton(jeton)
        if force and not forcer:
            raise Refus("Seule la tablette qui a pris la main peut la rendre. Depuis une autre tablette : "
                        "« Libérer la main » (noté dans la boîte noire).")
        tenu, duree = self.qui, round(time.monotonic() - (self._t0 or time.monotonic()), 1)
        self.qui = self.depuis = self._t0 = self._jeton = None
        oubliees = self.s.chaine.changer_de_main(None)  # la voix et les agents commandent de nouveau, comme avant
        await self._emettre("rendu", qui=tenu, rendu_par=nom_propre(qui) if qui else tenu, duree_s=duree,
                            ordres=self.ordres, fait=fait, consigne=(self.consigne or {}).get("texte"), par="ecran",
                            force=force, demandes_oubliees=oubliees)
        if self._quand_rendue is not None and not self._quand_rendue.done():
            self._quand_rendue.set_result(fait)
        return self.etat()

    # ---------------------------------------------------------------- un ordre de l'humain
    async def ordre(self, nom: str, parametres: dict[str, Any] | None, jeton: str | None = None,
                    qui: str | None = None, langue: str | None = None) -> dict[str, Any]:
        """Un bouton : l'ordre part vers le gardien, par la chaîne (`Chaine.ordre_humain`). Seulement avec la main, et
        seulement depuis la tablette qui l'a prise (jeton)."""
        if self.qui is None:
            raise Refus("Prenez d'abord la main (bouton « Je prends la main »). Pour arrêter le robot : ARRÊT.")
        if not self.a_le_jeton(jeton):
            raise Refus(f"{self.qui} a la main sur une autre tablette : seule celle-ci donne des ordres. "
                        "Pour arrêter le robot : ARRÊT, ou « stop ».")
        if langue is not None and langue not in langues()["langues"]:
            raise Refus(f"Langue inconnue : {langue}")
        action = ActionDemandee(nom=str(nom), parametres=nettoyer(str(nom), parametres))
        conv = uuid.uuid4().hex[:10]
        self.ordres += 1
        pilote = self.qui
        await self._emettre("ordre", conversation=conv, qui=pilote, action=action.model_dump(),
                            envoye_par=nom_propre(qui) if qui else pilote)
        res = await self.s.chaine.ordre_humain(action, pilote, langue, conversation=conv)
        numero = next((d["numero"] for d in self.s.gardien.demandes_en_attente() if d.get("conversation") == conv), None)
        if not res.reponses:
            sorte = "oublie"  # la main a changé, ou un stop est passé, pendant la vérification : rien n'est parti
        elif res.verdict == "oui" and res.statut_action != "refusee":
            sorte = "parti"
        elif res.verdict == "humain":
            sorte = "humain"
        else:
            sorte = "refuse"
        self.dernier = {"sorte": sorte, "action": action.model_dump(), "action_texte": decrire(action, self.s.monde),
                        "verdict": res.verdict, "reponses": res.reponses, "numero_demande": numero,
                        "conversation": conv, "heure": maintenant_iso()}
        return {"ok": sorte == "parti", **self.dernier}

    # ---------------------------------------------------------------- le chef de démonstration (brique 15)
    async def attendre_un_humain(self, consigne: str, etape: str | None = None, par: str = "chef_demo",
                                 delai_s: float | None = None, delai_rendu_s: float | None = None) -> bool:
        """Plan B « main humaine » : la consigne s'affiche sur l'écran de l'équipe ; on attend qu'un humain prenne la
        main (au plus `delai_s`), puis qu'il la rende (au plus `delai_rendu_s` : ensuite le chef passe à la suite, et
        l'humain GARDE la main — on ne la lui retire jamais). Rend True seulement s'il dit « fait » en la rendant.
        Une deuxième demande pendant qu'une autre attend : refusée (False), notée."""
        if self.consigne is not None:
            await self.s.bus.emettre("note", SOURCE, robot=self.s.prise.robot,
                                     texte=f"deuxième demande de main humaine refusée (une autre attend déjà) : {consigne}")
            return False
        boucle = asyncio.get_running_loop()
        rendue: asyncio.Future = boucle.create_future()
        prise: asyncio.Future | None = boucle.create_future() if self.qui is None else None
        self.consigne = {"texte": consigne, "etape": etape, "par": par, "depuis": maintenant_iso()}
        self._quand_prise, self._quand_rendue = prise, rendue
        await self._emettre("demande", consigne=consigne, etape=etape, par=par, deja_prise=self.qui)
        retiree = "le chef de démonstration s'est arrêté"
        try:
            if prise is not None:
                try:
                    await asyncio.wait_for(asyncio.shield(prise), self.attente_chef_s if delai_s is None else delai_s)
                except asyncio.TimeoutError:
                    retiree = "personne n'a pris la main à temps"
                    return False
            limite = self.attente_rendu_s if delai_rendu_s is None else delai_rendu_s
            try:
                fait = await asyncio.wait_for(asyncio.shield(rendue), limite)
            except asyncio.TimeoutError:
                retiree = f"main pas rendue à temps ({limite:g} s) : le chef passe à la suite, l'humain garde la main"
                return False
            retiree = ""
            return fait is True
        finally:
            self.consigne, self._quand_prise, self._quand_rendue = None, None, None
            for f in (prise, rendue):
                if f is not None and not f.done():
                    f.cancel()
            if retiree:
                await self._emettre("demande_retiree", consigne=consigne, etape=etape, par=par, raison=retiree,
                                    qui=self.qui)

    # ---------------------------------------------------------------- outils
    async def _emettre(self, quoi: str, conversation: str | None = None, **donnees: Any) -> None:
        await self.s.bus.emettre("pilotage_humain", SOURCE, robot=self.s.prise.robot, conversation=conversation,
                                 quoi=quoi, **donnees)

    def _sur_pilotage(self, ev: Evenement) -> None:
        """Une main humaine annoncée par un autre que l'écran (chef de démonstration avec l'opérateur simulé ou le
        clavier) : rien ne change pour la voix, mais l'écran du jury le montre aussi (honnêteté)."""
        if ev.source == SOURCE:
            return
        d = ev.donnees
        if d.get("quoi") == "reprise":
            self.annoncee = {"qui": d.get("qui") or d.get("operateur") or ev.source, "par": d.get("par") or ev.source,
                            "consigne": d.get("consigne"), "depuis": ev.heure}
        elif d.get("quoi") == "rendu":
            self.annoncee = None


def _demandeur(demandeur: str) -> str:
    if demandeur.startswith("agent:"):
        return f"l'agent d'IA « {demandeur.split(':', 1)[1]} »"
    if demandeur.startswith("humain:"):
        return f"l'humain qui pilote ({demandeur.split(':', 1)[1]})"
    return "une phrase (voix ou tablette)" if demandeur in ("", "cerveau") else demandeur
