"""Brique 12 — La fiche de vérité : dire la vérité en chiffres.

Calculée UNIQUEMENT à partir des événements de la boîte noire, un par un (`Compteur.ajouter`).
Donc la même fiche sort en direct, après coup, ou après un rejeu. Le compteur ne garde que des totaux :
il ne se remet jamais à zéro, même après des jours de fonctionnement.
"""
from __future__ import annotations

import statistics
from typing import Iterable

from pydantic import BaseModel, Field

from commun.evenements import Evenement

MAX_TEMPS = 2000  # on garde les 2000 derniers temps pour les médianes


class ParLangue(BaseModel):
    demandes: int = 0
    non_comprises: int = 0  # le robot a dû faire répéter (incompris ou écoute peu sûre)
    questions: int = 0
    taux_non_compris_pct: float = 0.0


class Temps(BaseModel):
    nb: int = 0
    mediane_ms: float | None = None
    max_ms: float | None = None


class Fiche(BaseModel):
    mention: str = "testé sur faux robot"
    robots: list[str] = Field(default_factory=list)
    demandes: int = 0
    reussites: int = 0
    rates: int = 0
    annulees: int = 0
    refus_gardien: int = 0
    refus_prise: int = 0
    questions_posees: int = 0
    aides_demandees: int = 0
    aides_recues: int = 0  # brique 8 : un humain a accepté, refusé, ou appris un mot au robot
    arrets_urgence: int = 0
    pannes: int = 0  # constatées par le système
    pannes_provoquees: int = 0  # provoquées exprès pour s'entraîner
    part_humain_pct: float = 0.0
    temps_premiere_reponse: Temps = Field(default_factory=Temps)
    temps_cerveau: Temps = Field(default_factory=Temps)
    temps_action: Temps = Field(default_factory=Temps)
    temps_fin_de_phrase_a_reponse: Temps = Field(default_factory=Temps)  # voix : fin de la phrase → début du son
    temps_ecoute: Temps = Field(default_factory=Temps)  # calcul de l'écoute (parole → texte)
    interruptions: int = 0
    confirmations_demandees: int = 0
    plans_b: int = 0  # moyens de secours essayés par le chef de démonstration (brique 15)
    plans_b_reussis: int = 0  # ceux qui ont sauvé l'étape
    demandes_agents: int = 0  # brique 14 : phrases venues d'un agent d'IA (source « agent:… »), comptées aussi dans « demandes »
    refus_porte_agents: int = 0  # brique 14 : ordres d'un agent refusés avant le cerveau (trop d'ordres par minute…)
    ordres_humains: int = 0  # brique 11 : ordres donnés par l'humain qui a la main (boutons de l'écran)
    reussites_pilotees: int = 0  # brique 11 : réussites venues d'un ordre de l'humain (comptées aussi dans « reussites »)
    part_humain_simulee_pct: float = 0.0  # brique 11 : main humaine SIMULÉE par le chef (répétition), à part de l'autre
    par_langue: dict[str, ParLangue] = Field(default_factory=dict)
    duree_session_s: float = 0.0
    remarque: str = ("« non compris » = le robot a fait répéter. Le vrai taux d'erreur par langue "
                     "se mesure au banc d'essai (brique 6).")


def _temps(valeurs: list[float], nb: int) -> Temps:
    if not valeurs:
        return Temps()
    return Temps(nb=nb, mediane_ms=round(statistics.median(valeurs), 1), max_ms=round(max(valeurs), 1))


class Compteur:
    """Tient la fiche à jour, événement par événement."""

    def __init__(self) -> None:
        self.f = Fiche()
        self._vrai = False
        self._t0: float | None = None
        self._t_fin = 0.0
        self._debut_conv: dict[str, float] = {}
        self._langue_conv: dict[str, str] = {}
        self._t_premiere: list[float] = []
        self._t_cerveau: list[float] = []
        self._t_action: list[float] = []
        self._t_voix: list[float] = []
        self._t_ecoute: list[float] = []
        self._nb = {"premiere": 0, "cerveau": 0, "action": 0, "voix": 0, "ecoute": 0}
        self._debut_humain: float | None = None
        self._temps_humain = 0.0
        self._max_t = 0.0
        self._conv_pilotees: dict[str, str] = {}  # brique 11 : conversation → « ordre » ou « arret_reprise » (1000 dernières)
        self._debut_simule: float | None = None  # brique 11 : main humaine simulée par le chef (répétition)
        self._temps_simule = 0.0

    def _garder(self, liste: list[float], cle: str, valeur: float) -> None:
        liste.append(valeur)
        self._nb[cle] += 1
        if len(liste) > MAX_TEMPS:
            del liste[0]

    @staticmethod
    def _nom_cerveau(e: Evenement) -> str:
        """Le temps du cerveau ne compte que les vraies décisions du cerveau (pas « oui », pas « stop » prioritaire)."""
        return e.source if e.source not in ("confirmation", "arret_prioritaire") else "-"

    def ajouter(self, e: Evenement) -> None:
        f, d = self.f, e.donnees
        self._t0 = e.t if self._t0 is None else min(self._t0, e.t)
        self._max_t = max(self._max_t, e.t)
        if e.robot and e.robot not in f.robots:
            f.robots.append(e.robot)
        if e.type == "session_debut" and d.get("vrai_robot"):
            self._vrai = True
        elif e.type == "parole_entendue":
            f.demandes += 1
            f.demandes_agents += e.source.startswith("agent:")
            if e.conversation:
                self._debut_conv[e.conversation] = e.t
        elif e.type == "demande_comprise":
            lg = d.get("langue") or "?"
            if e.conversation:
                self._langue_conv[e.conversation] = lg
            pl = f.par_langue.setdefault(lg, ParLangue())
            pl.demandes += 1
            if d.get("genre") == "inconnu":
                pl.non_comprises += 1
            if d.get("duree_ms") is not None and d.get("genre") != "confirmation" and e.source == self._nom_cerveau(e):
                self._garder(self._t_cerveau, "cerveau", float(d["duree_ms"]))
        elif e.type == "question_posee":
            f.questions_posees += 1
            lg = d.get("langue") or self._langue_conv.get(e.conversation or "", "?")
            f.par_langue.setdefault(lg, ParLangue()).questions += 1
        elif e.type == "reponse_dite":
            c = e.conversation
            if c in self._debut_conv:
                self._garder(self._t_premiere, "premiere", (e.t - self._debut_conv.pop(c)) * 1000)
        elif e.type == "gardien_decision" and d.get("verdict") == "non":
            f.refus_gardien += 1
        elif e.type == "action_refusee":
            f.refus_prise += 1
        elif e.type == "action_terminee":
            statut = d.get("statut")
            sorte = self._conv_pilotees.pop(e.conversation or "", "")  # brique 11 : ordre de l'humain ? arrêt de reprise ?
            if statut == "reussie":
                if sorte != "arret_reprise":  # brique 11 : l'arrêt envoyé en prenant la main n'est pas une réussite du robot
                    f.reussites += 1
                    f.reussites_pilotees += sorte == "ordre"
            elif statut == "annulee":
                f.annulees += 1
            else:
                f.rates += 1
            if d.get("duree_ms") is not None:
                self._garder(self._t_action, "action", float(d["duree_ms"]))
        elif e.type == "voix_debut" and d.get("latence_ms") is not None:
            self._garder(self._t_voix, "voix", float(d["latence_ms"]))
        elif e.type == "transcription" and d.get("calcul_ms") is not None:
            self._garder(self._t_ecoute, "ecoute", float(d["calcul_ms"]))
        elif e.type == "interruption":
            f.interruptions += 1
        elif e.type == "confirmation_demandee":
            f.confirmations_demandees += 1
        elif e.type == "plan_b" and d.get("etat") in ("reussi", "rate", "saute") and not d.get("preventif"):
            # un mode local « préventif » (le chef l'allume avant l'étape) n'a rien rattrapé : pas compté
            f.plans_b += 1
            f.plans_b_reussis += d["etat"] == "reussi"
        elif e.type == "porte_agents" and d.get("quoi") == "ordre_refuse":
            f.refus_porte_agents += 1
        elif e.type == "aide_demandee":
            f.aides_demandees += 1
        elif e.type == "aide_recue":
            f.aides_recues += 1
        elif e.type == "arret_urgence":
            f.arrets_urgence += 1
        elif e.type == "panne":
            if d.get("provoquee"):
                f.pannes_provoquees += 1
            else:
                f.pannes += 1
        elif e.type == "pilotage_humain":
            quoi = d.get("quoi")
            # Brique 11 : une main humaine SIMULÉE (opérateur automatique du chef, en répétition) est comptée à part.
            if bool(d.get("simulee")) or "simul" in str(d.get("operateur") or ""):
                if quoi == "reprise" and self._debut_simule is None:
                    self._debut_simule = e.t
                elif quoi == "rendu" and self._debut_simule is not None:
                    self._temps_simule += e.t - self._debut_simule
                    self._debut_simule = None
            elif quoi == "reprise" and self._debut_humain is None:
                self._debut_humain = e.t
            elif quoi == "rendu" and self._debut_humain is not None:
                self._temps_humain += e.t - self._debut_humain
                self._debut_humain = None
            if quoi == "reprise" and d.get("arret_envoye") and e.conversation:  # brique 11 : l'arrêt de la reprise
                self._noter_conversation(e.conversation, "arret_reprise")
            elif quoi == "ordre":  # brique 11 : un ordre de l'humain qui a la main
                f.ordres_humains += 1
                if e.conversation:
                    self._noter_conversation(e.conversation, "ordre")

    def _noter_conversation(self, conversation: str, sorte: str) -> None:
        """Brique 11 : retenir d'où vient l'action de cette conversation (les 1000 dernières seulement)."""
        self._conv_pilotees[conversation] = sorte
        if len(self._conv_pilotees) > 1000:
            del self._conv_pilotees[next(iter(self._conv_pilotees))]

    def fiche(self) -> Fiche:
        f = self.f.model_copy(deep=True)
        if self._t0 is None:
            return f
        humain = self._temps_humain + ((self._max_t - self._debut_humain) if self._debut_humain is not None else 0.0)
        f.duree_session_s = round(self._max_t - self._t0, 2)
        f.part_humain_pct = round(100 * humain / f.duree_session_s, 1) if f.duree_session_s > 0 else 0.0
        simule = self._temps_simule + ((self._max_t - self._debut_simule) if self._debut_simule is not None else 0.0)
        f.part_humain_simulee_pct = round(100 * simule / f.duree_session_s, 1) if f.duree_session_s > 0 else 0.0
        f.mention = "testé sur vrai robot" if self._vrai else "testé sur faux robot"
        f.temps_premiere_reponse = _temps(self._t_premiere, self._nb["premiere"])
        f.temps_cerveau = _temps(self._t_cerveau, self._nb["cerveau"])
        f.temps_action = _temps(self._t_action, self._nb["action"])
        f.temps_fin_de_phrase_a_reponse = _temps(self._t_voix, self._nb["voix"])
        f.temps_ecoute = _temps(self._t_ecoute, self._nb["ecoute"])
        for pl in f.par_langue.values():
            pl.taux_non_compris_pct = round(100 * pl.non_comprises / pl.demandes, 1) if pl.demandes else 0.0
        return f


def calculer(evenements: Iterable[Evenement]) -> Fiche:
    c = Compteur()
    for e in sorted(evenements, key=lambda e: (e.t, e.numero)):
        c.ajouter(e)
    return c.fiche()
