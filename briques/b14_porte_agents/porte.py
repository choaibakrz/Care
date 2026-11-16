"""Brique 14 — La porte des agents : un agent d'IA (par exemple un assistant d'IA) parle au robot comme une personne.

L'agent n'a AUCUN accès direct au robot. Il a cinq outils (voir serveur_mcp.py) :
- dire_au_robot : la phrase passe par la même chaîne que la voix : cerveau → gardien (ticket) → prise → robot ;
- voir_carte, voir_etat, voir_fiche : lire seulement ;
- arreter : l'arrêt d'urgence, toujours permis (comme le bouton ARRÊT de l'écran). Un humain réarme ensuite.
Rien pour changer une règle, réarmer, provoquer une panne ou parler à la prise : cela reste aux humains.

Sur la prise, la porte n'utilise que `carte()`, `etat()` (lire) et `arret_urgence()` (s'arrêter) : exactement
les boutons ouverts de l'écran. Un test le vérifie (tests/test_sans_contournement.py).

Limites propres aux agents (reglages.yaml → porte_agents) :
- ordres_par_minute : au-delà, l'ordre est refusé AVANT le cerveau (événement `porte_agents`, compté dans la fiche) ;
- accord_humain : chaque action d'un agent attend l'accord d'un humain (verdict « humain » du gardien, sauf
  « etat »). C'est le GARDIEN qui l'applique (briques/b07_gardien/gardien.py), pas la porte.
« stop » passe toujours : jamais compté, jamais bloqué, jamais en attente.
"""
from __future__ import annotations

import asyncio
import re
import time
import uuid
from collections import deque
from contextlib import nullcontext
from typing import Any

from pydantic import BaseModel, Field

from briques.b07_gardien.gardien import PREFIXE_AGENT
from commun.evenements import Evenement
from commun.phrases import est_ordre_arret, langues

NOM_PERMIS = re.compile(r"^[a-z0-9][a-z0-9_-]{0,29}$")
TEXTE_MAX = 300
OUTILS = ("dire_au_robot", "voir_carte", "voir_etat", "voir_fiche", "arreter")

EXPLICATIONS = {
    "reussie": "C'est fait ({mention}).",
    "echouee": "Le robot a essayé, mais n'a pas réussi : lisez « reponses ».",
    "annulee": "L'action a été annulée (stop ou arrêt d'urgence).",
    "refusee": ("Refusé, pour la sécurité : lisez « raisons ». Ne cherchez pas à contourner la règle ; "
                "proposez autre chose, ou demandez à un humain."),
    "en_cours": "L'action continue. Suivez-la avec voir_etat.",
    "attend_un_humain": ("Le gardien demande l'accord d'un humain (demande n° {numero}). Un humain répond sur "
                         "l'écran ; vous ne pouvez pas répondre à sa place. Suivez avec voir_etat."),
    "attend_confirmation": "Le robot répète l'ordre et attend « oui » ou « non » : répondez avec dire_au_robot.",
    "question": "Le robot pose une question : répondez avec dire_au_robot, en une phrase simple.",
    "pas_compris": "Le robot n'a pas compris. Une phrase simple, comme à une personne : « Va à la table ».",
    "discussion": "Le robot a répondu, sans agir.",
    "rien": "Rien n'a été fait.",
    "humain_pilote": ("Un humain pilote le robot depuis l'écran (brique 11) : votre ordre n'est pas pris. N'insistez pas ; "
                      "réessayez plus tard. « stop » et l'outil arreter marchent toujours."),
    "trop_d_ordres": ("Trop d'ordres : au plus {n} par minute pour un agent. Réessayez dans {attendre_s} s. "
                      "« stop » et l'outil arreter marchent toujours."),
    "ordre_invalide": "Ordre refusé avant le cerveau : {detail}",
}


class ReglagesPorte(BaseModel):
    """reglages.yaml → porte_agents (accord_humain est lu par le gardien, voir commun/systeme.py)."""

    ordres_par_minute: int = Field(10, ge=1, le=60)
    attente_fin_s: float = Field(30.0, gt=0, le=120)
    port_ecran: int = Field(8001, ge=1, le=65535)

    @classmethod
    def depuis(cls, reglages: dict) -> "ReglagesPorte":
        r = dict(reglages.get("porte_agents") or {})
        r.pop("accord_humain", None)
        return cls(**r)


class Limite:
    """Au plus `n` ordres pendant les dernières `fenetre_s` secondes (fenêtre glissante)."""

    def __init__(self, n: int, fenetre_s: float = 60.0) -> None:
        self.n, self.fenetre_s = n, fenetre_s
        self._heures: deque[float] = deque()

    def essayer(self) -> float | None:
        """None : l'ordre passe (et il est compté). Sinon : combien de secondes attendre."""
        t = time.monotonic()
        while self._heures and t - self._heures[0] >= self.fenetre_s:
            self._heures.popleft()
        if len(self._heures) >= self.n:
            return round(self.fenetre_s - (t - self._heures[0]), 1)
        self._heures.append(t)
        return None


class PorteDesAgents:
    """Un agent = une porte (un nom, une limite). Le système (robot, gardien, chaîne) est celui de commun/systeme.py."""

    def __init__(self, systeme, nom: str = "agent", reglages: ReglagesPorte | None = None) -> None:
        if not NOM_PERMIS.match(nom):
            raise ValueError(f"nom d'agent « {nom} » : lettres minuscules, chiffres, - ou _ (30 au plus)")
        self.systeme = systeme
        self.nom = nom
        self.source = f"{PREFIXE_AGENT}{nom}"  # le gardien reconnaît un agent à ce préfixe
        self.reglages = reglages or ReglagesPorte.depuis(systeme.reglages)
        self.limite = Limite(self.reglages.ordres_par_minute)
        self._verrou = asyncio.Lock()  # les ordres d'un agent passent l'un après l'autre (jamais « stop »)
        self._conversations: deque[str] = deque(maxlen=30)
        self._taches: set[asyncio.Task] = set()  # garder une référence, sinon Python peut les jeter

    # ---------------------------------------------------------------- petits outils
    @property
    def accord_humain(self) -> bool:
        """La vérité, lue chez le gardien (c'est lui qui l'applique)."""
        return bool(self.systeme.gardien.accord_humain_agents)

    def _mention(self) -> str:
        return self.systeme.prise.carte().mention_test()

    async def _noter(self, quoi: str, **donnees: Any) -> None:
        await self.systeme.bus.emettre("porte_agents", "porte_agents", robot=self.systeme.prise.robot, quoi=quoi,
                                       agent=self.source, **donnees)

    async def ouvrir(self, transport: str = "stdio") -> None:
        """Noté dans la boîte noire : quel agent, quelles limites."""
        await self._noter("ouverte", transport=transport, ordres_par_minute=self.reglages.ordres_par_minute,
                          accord_humain=self.accord_humain, outils=list(OUTILS))

    async def _refuser(self, statut: str, texte: str, **valeurs: Any) -> dict[str, Any]:
        await self._noter("ordre_refuse", raison=statut, texte=texte[:80], **valeurs)
        return {"mention": self._mention(), "statut": statut, "verdict_gardien": None, "reponses": [], "raisons": [],
                "explication": EXPLICATIONS[statut].format(**valeurs)}

    # ---------------------------------------------------------------- dire_au_robot
    async def dire(self, texte: str, langue: str | None = None) -> dict[str, Any]:
        """Une phrase pour le robot, comme si une personne la disait. Rend la réponse du robot, le verdict du
        gardien et le statut de l'action (avec une explication simple pour l'agent)."""
        texte = " ".join(str(texte or "").split())
        langue = (langue or "").strip().lower() or None
        stop = bool(texte) and len(texte) <= TEXTE_MAX and est_ordre_arret(texte)
        if not stop:  # « stop » n'est jamais compté ni bloqué ; un ordre invalide COMPTE (sinon il inonde le journal)
            attendre_s = self.limite.essayer()
            if attendre_s is not None:
                return await self._refuser("trop_d_ordres", texte[:TEXTE_MAX], n=self.reglages.ordres_par_minute,
                                           attendre_s=attendre_s)
        if not texte or len(texte) > TEXTE_MAX:
            return await self._refuser("ordre_invalide", texte,
                                       detail=f"texte vide ou trop long ({TEXTE_MAX} signes au plus).")
        if stop and langue is not None and langue not in langues()["langues"]:
            langue = None  # « stop » avec une langue mal écrite (« fr-CH », « es ») : on arrête quand même
        if langue is not None and langue not in langues()["langues"]:
            return await self._refuser("ordre_invalide", texte,
                                       detail=f"langue « {langue} » inconnue ({', '.join(langues()['langues'])}).")

        conv = f"agent-{uuid.uuid4().hex[:10]}"
        self._conversations.append(conv)
        evenements: list[Evenement] = []
        fini = asyncio.Event()

        def garder(ev: Evenement) -> None:  # les événements de CETTE phrase, pour le compte rendu
            if ev.conversation == conv:
                evenements.append(ev)
                if ev.type == "reponse_dite" and ev.donnees.get("genre") == "fin":
                    fini.set()

        bus = self.systeme.bus
        bus.abonner(garder)
        try:
            async with nullcontext() if stop else self._verrou:
                # « shield » : si l'agent abandonne son appel, la chaîne finit quand même son travail (jamais coupée
                # entre le ticket du gardien et la prise) ; l'agent ne reçoit simplement pas la réponse.
                tache = asyncio.create_task(self.systeme.chaine.traiter(
                    texte, langue, source=self.source, attendre_fin=False, personne=self.source, conversation=conv))
                self._taches.add(tache)
                tache.add_done_callback(self._taches.discard)
                res = await asyncio.shield(tache)
            lance = any(e.type == "action_demarree" for e in evenements)
            if lance and not fini.is_set():
                try:
                    await asyncio.wait_for(fini.wait(), self.reglages.attente_fin_s)
                except asyncio.TimeoutError:
                    pass
        finally:
            bus.desabonner(garder)
        return self._compte_rendu(res, evenements, lance)

    def _compte_rendu(self, res, evenements: list[Evenement], lance: bool) -> dict[str, Any]:
        reponses = [e.donnees.get("texte", "") for e in evenements if e.type == "reponse_dite"]
        decisions = [e for e in evenements if e.type == "gardien_decision"]
        raisons: list[dict] = []
        for e in evenements:
            if (e.type == "gardien_decision" and e.donnees.get("verdict") != "oui") or e.type == "action_refusee":
                raisons += e.donnees.get("raisons") or []
            elif e.type == "reponse_dite" and e.donnees.get("cle") == "refus" and not decisions:
                raisons += (e.donnees.get("valeurs") or {}).get("raisons") or []  # « ce robot ne sait pas faire cela »
        numero = next((e.donnees.get("numero_demande") for e in decisions if e.donnees.get("numero_demande")), None)
        if res.statut_action:
            statut = res.statut_action  # reussie, echouee, annulee (robot) ou refusee (prise)
        elif lance:
            statut = "en_cours"  # pas fini à temps : l'agent suit avec voir_etat
        elif res.verdict == "humain":
            statut = "attend_un_humain"
        elif res.verdict == "non":
            statut = "refusee"
        elif any(e.type == "confirmation_demandee" for e in evenements):
            statut = "attend_confirmation"
        elif res.decision.genre in ("question", "discussion"):
            statut = res.decision.genre
        elif any(e.donnees.get("cle") == "humain_pilote" for e in evenements if e.type == "reponse_dite"):
            statut = "humain_pilote"  # brique 11 : un humain a la main à l'écran
        elif res.decision.genre == "inconnu" and any(
                e.donnees.get("cle") == "incompris" or e.donnees.get("genre") == "main_levee"
                for e in evenements if e.type == "reponse_dite"):
            statut = "pas_compris"  # (un « non » à « Vous confirmez ? » : « rien »)
        else:
            statut = "rien"
        mention = self._mention()
        return {
            "mention": mention,
            "statut": statut,
            "verdict_gardien": res.verdict,
            "reponses": reponses,
            "raisons": raisons,
            "action": res.action.model_dump() if res.action else None,
            "compris": res.decision.genre,
            "numero_demande": numero,
            "langue": res.langue,
            "conversation": res.conversation,
            "explication": EXPLICATIONS.get(statut, "").format(mention=mention, numero=numero),
        }

    # ---------------------------------------------------------------- lire seulement
    def carte(self) -> dict[str, Any]:
        """La carte d'identité : ce que le robot sait faire, ses limites, les lieux et objets connus, les règles."""
        c = self.systeme.prise.carte()
        monde = self.systeme.monde

        def noms(chose) -> dict[str, str]:
            return {lg: liste[0] for lg, liste in chose.noms.items() if liste}

        return {
            "mention": c.mention_test(),
            "robot": c.id,
            "vrai_robot": c.vrai_robot,
            "carte": c.resume(),
            "limites_de_securite": self.systeme.gardien.plafonds(),
            "lieux": {l.id: noms(l) for l in monde.lieux},
            "objets": {o.id: noms(o) for o in monde.objets},
            "langues": list(langues()["langues"]),
            "regles_du_gardien": [r["phrase"] for r in self.systeme.gardien.regles_lisibles() if r["active"]],
            "porte": {"agent": self.source, "outils": list(OUTILS), "ordres_par_minute": self.reglages.ordres_par_minute,
                      "accord_humain": self.accord_humain},
            "comment_parler": ("Une phrase simple, comme à une personne : « Va à la table », « Prends la bouteille », "
                               "« Batterie ? ». « stop » arrête tout. Chaque ordre passe par le gardien."),
        }

    async def etat(self) -> dict[str, Any]:
        """L'état du robot, les demandes de cet agent qui attendent un humain, ses dernières actions."""
        e = await self.systeme.prise.etat()
        mes_demandes = [{k: d[k] for k in ("numero", "action", "raisons", "reste_s")}
                        for d in self.systeme.gardien.demandes_en_attente() if d.get("demandeur") == self.source]
        miennes = set(self._conversations)
        actions: dict[str, dict] = {}
        for ev in list(self.systeme.bus.historique):
            if ev.conversation in miennes and ev.type in ("action_demarree", "action_terminee"):
                ident = ev.donnees.get("id_action") or ""
                actions[ident] = {"action": ev.donnees.get("action"), "conversation": ev.conversation,
                                  "statut": ev.donnees.get("statut", "en_cours"), "message": ev.donnees.get("message")}
        return {
            "mention": self._mention(),
            "robot": self.systeme.prise.robot,
            "etat": e.model_dump(),
            "arret_urgence_actif": e.arret_urgence_actif,
            "mes_demandes_en_attente": mes_demandes,
            "mes_dernieres_actions": list(actions.values())[-5:],
            "explication": ("Lire seulement. Arrêt d'urgence actif : un humain doit réarmer le robot depuis l'écran."
                            if e.arret_urgence_actif else "Lire seulement."),
        }

    def fiche(self) -> dict[str, Any]:
        """La fiche de vérité, calculée depuis la boîte noire (brique 12)."""
        return self.systeme.compteur.fiche().model_dump()

    # ---------------------------------------------------------------- s'arrêter : toujours permis
    async def arreter(self) -> dict[str, Any]:
        """L'arrêt d'urgence, comme le bouton ARRÊT de l'écran : sans limite, sans attente, sans accord."""
        try:
            await self.systeme.prise.arret_urgence(raison="demande_d_un_agent", qui=self.source)
        except Exception as e:  # ne devrait pas arriver : la prise n'empêche jamais l'arrêt
            return {"ok": False, "mention": self._mention(), "erreur": repr(e),
                    "explication": "Arrêt logiciel incertain : utiliser le bouton d'arrêt PHYSIQUE du robot."}
        return {"ok": True, "mention": self._mention(), "arret_urgence_actif": True,
                "explication": ("Arrêt d'urgence fait : le robot ne bouge plus. Un humain doit le réarmer depuis "
                                "l'écran ; un agent ne peut pas réarmer.")}
