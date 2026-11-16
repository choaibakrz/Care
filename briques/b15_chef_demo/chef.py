"""Brique 15 — Le chef de démonstration : jouer un scénario comme une partition.

- Une étape « dire » passe TOUJOURS par la chaîne (cerveau → gardien → prise) : le chef n'a aucun accès au robot.
  Il lit ensuite les événements du bus pour savoir si l'attendu s'est produit.
- Raté, ou pas fini à temps : le plan B de l'étape, dans l'ordre, sans les moyens qui ne peuvent pas aider
  (rejouer la phrase à la tablette ne répare pas un robot en panne).
- L'arrêt d'urgence passe avant tout : le chef s'arrête, le dit, et ne réarme JAMAIS le robot lui-même.
- Répétition : pannes provoquées (robot, voix, réseau), chronomètre ; le compte rendu est écrit par compte_rendu.py.
Testé sur faux robot.
"""
from __future__ import annotations

import asyncio
import contextlib
import math
import random
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.parse import urlparse

import yaml

from briques.b06_cerveau.branchements.cascade import CerveauCascade
from briques.b06_cerveau.prise_cerveau import Cerveau, Decision
from briques.b12_boite_noire.fiche import Fiche, calculer
from commun.evenements import Evenement
from commun.phrases import est_ordre_arret, langue_de_reponse, oui_ou_non
from commun.systeme import Systeme

from .scenario import PANNES_CHEF, Attendu, Etape, Scenario

SOURCE = "chef_demo"
# Avec l'accélération, les limites de temps sont divisées, mais jamais sous ce plancher : le cerveau et le bus,
# eux, ne vont pas plus vite. Choix de conception (pas une mesure).
PLANCHER_S = 2.0
DUREE_MAIN_HUMAINE_S = 5.0  # opérateur automatique (répétition) : temps « simulé » avant de rendre la main
# Ce qu'un moyen de secours ne peut pas réparer.
INUTILES: dict[str, set[str]] = {
    "robot": {"tablette", "mode_local"},
    "gardien": {"tablette", "mode_local", "main_humaine"},  # jamais faire à la main ce que le gardien refuse
    "voix": {"mode_local"},
    "reseau": {"tablette"},
    "inattendu": {"tablette", "mode_local"},  # le robot a déjà agi : rejouer le ferait agir encore
}
CAUSES = {
    "robot": "panne du robot",
    "gardien": "refus du gardien",
    "voix": "mal entendu ou pas compris",
    "reseau": "cerveau en secours ou muet (réseau)",
    "inattendu": "le robot a fait autre chose que prévu",
    "temps": "pas fini à temps",
    "autre": "attendu non obtenu",
}
HOTES_LOCAUX = {"127.0.0.1", "localhost", "::1"}


@lru_cache(maxsize=1)
def _phrases_chef() -> dict:
    return yaml.safe_load(Path(__file__).with_name("phrases_chef.yaml").read_text(encoding="utf-8"))


def dire_chef(cle: str, langue: str | None, **valeurs: Any) -> str:
    """Une phrase du chef dans la langue demandée (allemand pour le suisse allemand), sinon en français."""
    p = _phrases_chef()
    modele = (p.get(langue_de_reponse(langue)) or {}).get(cle) or p["fr"][cle]
    return modele.format(**valeurs)


# ------------------------------------------------------------------------------------------------ résultats
@dataclass
class EssaiPlanB:
    moyen: str
    cause: str
    resultat: str  # reussi, rate, saute, inutile
    detail: str = ""
    duree_s: float = 0.0
    preventif: bool = False  # mode local engagé après une étape réussie mais lente (cerveau en secours)


@dataclass
class ResultatEtape:
    numero: int
    nom: str
    genre: str
    resultat: str = "reussie"  # reussie, rattrapee, ratee, sautee, interrompue, ignoree
    cause: str | None = None
    detail: str = ""
    attendu: str = ""
    duree_s: float = 0.0
    limite_s: float | None = None
    panne: str | None = None
    panne_detail: str = ""
    plans_b: list[EssaiPlanB] = field(default_factory=list)
    travail_fini: bool = False  # l'étape a fini son travail (il ne restait que la pause d'après)


@dataclass
class ResultatScenario:
    titre: str
    fichier: str
    repetition: bool
    acceleration: float
    mention: str
    robot: str
    cerveau: str
    debut: str
    pannes: dict[int, str]
    graine: int | None
    duree_visee_s: float | None
    nb_etapes: int
    operateur: str
    etapes: list[ResultatEtape] = field(default_factory=list)
    duree_s: float = 0.0
    interrompu: str | None = None
    fiche: Fiche | None = None

    def compter(self, resultat: str) -> int:
        return sum(1 for e in self.etapes if e.resultat == resultat)


@dataclass
class Tentative:
    ok: bool
    cause: str | None = None
    detail: str = ""
    confirmation: bool = False  # le robot a demandé « vous confirmez ? »


# ------------------------------------------------------------------------------------------------ remplaçants
class OreilleSimulee:
    """Joue les oreilles (brique 4) : la phrase du scénario arrive à la chaîne comme si elle avait été entendue
    (source « micro »). Voix en panne (répétition) : la phrase arrive brouillée, avec une confiance très basse."""

    TEXTE_BROUILLE = "…"
    CONFIANCE_BROUILLEE = 0.1

    def __init__(self) -> None:
        self.en_panne = False

    def entendre(self, texte: str) -> tuple[str, float]:
        return (self.TEXTE_BROUILLE, self.CONFIANCE_BROUILLEE) if self.en_panne else (texte, 1.0)


class Operateur(Protocol):
    """Celui qui prend la main quand le robot ne peut pas (place prête pour la brique 11, le pilotage)."""

    nom: str

    async def prendre_la_main(self, consigne: str) -> bool: ...


class OperateurAutomatique:
    """Répétition sur faux robot : personne ne pilote vraiment. On attend un moment, puis on rend la main.
    Le compte rendu l'écrit : « main humaine simulée »."""

    nom = "automatique (simulé)"

    def __init__(self, duree_s: float = DUREE_MAIN_HUMAINE_S) -> None:
        self.duree_s = duree_s
        self.consignes: list[str] = []

    async def prendre_la_main(self, consigne: str) -> bool:
        self.consignes.append(consigne)
        await asyncio.sleep(self.duree_s)
        return True


class OperateurClavier:
    """Une personne à côté de l'ordinateur : le chef affiche la consigne et attend la touche Entrée."""

    nom = "clavier"

    async def prendre_la_main(self, consigne: str) -> bool:
        print(f"\n  >>> OPÉRATEUR : {consigne}\n      Entrée = c'est fait · n puis Entrée = pas pu le faire", flush=True)
        reponse = await asyncio.to_thread(input, "      ")
        return reponse.strip().lower() not in ("n", "non", "no", "nein")


class OperateurEcran:
    """Brique 11 : un humain prend la main par l'écran de l'équipe (bouton « Je prends la main »), donne ses ordres par
    les boutons (chacun passe par le gardien), puis la rend (« Fait » ou « Pas pu »). La consigne s'affiche à l'écran.
    `main` : la main humaine de l'écran (app.state.main_humaine), dans le MÊME programme que le chef.
    C'est l'écran qui note `pilotage_humain` (reprise, ordres, rendu) : le chef ne le note pas une deuxième fois."""

    nom = "écran (main humaine)"
    emet_pilotage = True

    def __init__(self, main: Any, attente_s: float | None = None, attente_rendu_s: float | None = None) -> None:
        self.main = main
        self.attente_s = attente_s  # None : l'attente par défaut pour PRENDRE la main (2 minutes)
        # None : l'attente par défaut pour la RENDRE (5 minutes) ; ensuite le chef passe à la suite (l'humain la garde).
        self.attente_rendu_s = attente_rendu_s

    async def prendre_la_main(self, consigne: str) -> bool:
        return await self.main.attendre_un_humain(consigne, par=SOURCE, delai_s=self.attente_s,
                                                  delai_rendu_s=self.attente_rendu_s)


class CerveauInjoignable(Cerveau):
    """Répétition : un cerveau joint par le réseau qui ne répond plus (panne réseau simulée).
    La cascade attend son délai, puis passe au cerveau suivant, comme avec un câble débranché."""

    def __init__(self, original: Cerveau) -> None:
        self.original = original
        self.nom = original.nom
        self.url = getattr(original, "url", "")

    async def decider(self, texte, langue, carte, monde) -> Decision:
        await asyncio.sleep(3600)  # la cascade coupe avant (son délai)
        raise ConnectionError(f"{self.nom} : réseau coupé (panne simulée)")


def _distant(cerveau: Cerveau) -> bool:
    """Un cerveau joint par le réseau (autre ordinateur ou Internet) ? Le cerveau à règles n'a pas d'adresse."""
    url = getattr(cerveau, "url", None)
    if not url:
        return False
    return (urlparse(url).hostname or "") not in HOTES_LOCAUX


def tirer_pagaille(scenario: Scenario, graine: int, taux: float = 0.3) -> dict[int, str]:
    """Mode pagaille : des pannes au hasard sur les étapes « dire ». Même graine = mêmes pannes."""
    hasard = random.Random(graine)
    pannes: dict[int, str] = {}
    for i, e in enumerate(scenario.etapes, 1):
        if e.dire is not None and hasard.random() < taux:
            pannes[i] = hasard.choice(sorted(PANNES_CHEF))
    return pannes


# ------------------------------------------------------------------------------------------------ le chef
class ChefDemo:
    def __init__(self, systeme: Systeme, scenario: Scenario, *, repetition: bool = False, acceleration: float = 1.0,
                 pannes: dict[int, str] | None = None, operateur: Operateur | None = None, fichier: str = "",
                 graine: int | None = None, afficher: Callable[[str], None] | None = None,
                 controles: dict[str, Callable[[], Any]] | None = None) -> None:
        if acceleration <= 0:
            raise ValueError("l'accélération doit être plus grande que zéro")
        self.s = systeme
        self.bus = systeme.bus
        self.sc = scenario
        # Les étapes « controle » (ajoutées le 12.11.2026, H05) : chaque nom doit être donné ici. Une faute se voit avant de jouer.
        self.controles = dict(controles or {})
        inconnus = [e.controle for e in scenario.etapes if e.controle is not None and e.controle not in self.controles]
        if inconnus:
            from .scenario import ScenarioInvalide

            raise ScenarioInvalide(f"contrôle inconnu : {', '.join(inconnus)} (donnés au chef : {', '.join(self.controles) or 'aucun'})")
        self.repetition = repetition
        self.vrai_robot = bool(systeme.prise.carte().vrai_robot) or systeme.simulation is None
        if self.vrai_robot and acceleration != 1:
            raise ValueError("accélération : seulement avec le faux robot")
        if pannes and not repetition:
            raise ValueError("les pannes ne se provoquent qu'en répétition")
        self.acceleration = float(acceleration)
        self.pannes = dict(pannes or {})
        self.fichier = fichier
        self.graine = graine
        self.operateur: Operateur = operateur or (
            OperateurClavier() if self.vrai_robot else OperateurAutomatique(DUREE_MAIN_HUMAINE_S / self.acceleration))
        self.afficher = afficher or (lambda texte: None)
        self.oreille = OreilleSimulee()
        self.source = "micro"  # devient « clavier » après le plan B tablette (jusqu'à la fin)
        self._journal: list[Evenement] = []  # tout ce qui passe sur le bus pendant le scénario
        self._abonne = self._noter  # garder LA MÊME méthode pour pouvoir se désabonner
        self._urgence = asyncio.Event()
        self._raison_urgence = ""
        self._stop_humain = False  # « stop » dit par une personne (pas par le chef) : le scénario s'arrête
        self._mes_conversations: set[str] = set()  # les phrases envoyées par le chef lui-même
        self._en_vol: set[asyncio.Task] = set()  # phrases jamais annulées en route : on attend leur fin
        self._secours_vu = False  # le cerveau est passé au secours pendant l'étape en cours
        self._echoues: set[str] = set()  # cerveaux passés au secours pendant le scénario
        self._pauses: list[tuple[Any, float]] = []  # (étage de la cascade, ancienne pause) : mode local
        self._coupes: list[tuple[Any, Cerveau]] = []  # (étage, cerveau d'origine) : panne réseau simulée
        self._pannes_actives: set[str] = set()
        self._a_confirmer: tuple[str, str] | None = None  # ordre qui attend un « oui » (texte, langue)
        self._derniere: Tentative | None = None

    # ---------------------------------------------------------------- écouter le bus
    def _noter(self, e: Evenement) -> None:
        self._journal.append(e)
        if e.type == "arret_urgence" and not self._urgence.is_set():
            self._raison_urgence = str(e.donnees.get("raison") or "")
            self._urgence.set()
        elif (e.type == "parole_entendue" and e.conversation not in self._mes_conversations
              and est_ordre_arret(str(e.donnees.get("texte") or "")) and not self._urgence.is_set()):
            # Une personne (micro, tablette, agent…) a dit « stop » : la démonstration s'arrête, comme pour l'arrêt
            # d'urgence. Sinon, les étapes suivantes feraient repartir le robot.
            self._stop_humain = True
            self._raison_urgence = f"« stop » dit par une personne ({e.source})"
            self._urgence.set()
        elif e.type == "cerveau_secours":
            self._secours_vu = True
            if e.donnees.get("de"):
                self._echoues.add(str(e.donnees["de"]))

    async def _emettre(self, type_: str, **donnees: Any) -> None:
        await self.bus.emettre(type_, SOURCE, robot=self.s.prise.robot, **donnees)

    async def _annoncer(self, texte: str, langue: str) -> None:
        """Affiché à l'écran et dit par la voix (si la brique 4 tourne). Ce n'est PAS un ordre au robot."""
        await self._emettre("reponse_dite", conversation=uuid.uuid4().hex[:10], texte=texte,
                            langue=langue_de_reponse(langue), langue_entendue=langue, genre="annonce")
        self.afficher(f"          💬 [{langue}] {texte}")

    def _limite(self, duree_max_s: float) -> float:
        if self.acceleration <= 1:
            return duree_max_s
        return max(duree_max_s / self.acceleration, PLANCHER_S)

    async def _pause(self, secondes: float) -> None:
        if secondes > 0:
            await asyncio.sleep(secondes / self.acceleration)

    # ---------------------------------------------------------------- jouer
    async def jouer(self) -> ResultatScenario:
        carte = self.s.prise.carte()
        res = ResultatScenario(
            titre=self.sc.titre, fichier=self.fichier, repetition=self.repetition, acceleration=self.acceleration,
            mention=carte.mention_test(), robot=carte.id, cerveau=self.s.cerveau.nom,
            debut=datetime.now().strftime("%d.%m.%Y à %H:%M:%S"), pannes=dict(self.pannes), graine=self.graine,
            duree_visee_s=self.sc.duree_visee_s, nb_etapes=len(self.sc.etapes), operateur=self.operateur.nom)
        self.bus.abonner(self._abonne)
        t0 = time.monotonic()
        try:
            await self._emettre("scenario_debut", titre=self.sc.titre, fichier=self.fichier, etapes=len(self.sc.etapes),
                                repetition=self.repetition, acceleration=self.acceleration,
                                pannes={str(k): v for k, v in self.pannes.items()}, graine=self.graine,
                                duree_visee_s=self.sc.duree_visee_s, mention=res.mention)
            self.afficher(f"\n  🎬 {self.sc.titre} — {len(self.sc.etapes)} étapes — {res.mention}"
                          + (f" — accéléré ×{self.acceleration:g}" if self.acceleration != 1 else ""))
            if self.s.prise.arret_urgence_actif and not self._urgence.is_set():
                self._raison_urgence = "déjà actif au départ"
                self._urgence.set()
            for i, etape in enumerate(self.sc.etapes, 1):
                if self._urgence.is_set():
                    break
                r = await self._etape_surveillee(i, etape)
                res.etapes.append(r)
            if self._urgence.is_set():
                res.interrompu = (self._raison_urgence if self._stop_humain
                                  else f"arrêt d'urgence ({self._raison_urgence or 'bouton'})")
                cle = "stop_entendu" if self._stop_humain else "arret_urgence"
                await self._annoncer(dire_chef(cle, self.sc.langue), self.sc.langue)
        finally:
            await self._tout_remettre()
            res.duree_s = round(time.monotonic() - t0, 2)
            await self._emettre("scenario_fin", titre=self.sc.titre, duree_s=res.duree_s,
                                reussies=res.compter("reussie"), rattrapees=res.compter("rattrapee"),
                                ratees=res.compter("ratee"), sautees=res.compter("sautee"),
                                jouees=len(res.etapes), etapes=len(self.sc.etapes),
                                interrompu=res.interrompu is not None, raison=res.interrompu)
            res.fiche = self._fiche()
            self.bus.desabonner(self._abonne)
        return res

    async def _etape_surveillee(self, i: int, etape: Etape) -> ResultatEtape:
        """Joue une étape ; un arrêt d'urgence l'interrompt aussitôt."""
        r = ResultatEtape(numero=i, nom=etape.nom, genre=etape.genre, panne=self.pannes.get(i))
        await self._emettre("scenario_etape", quoi="debut", numero=i, nom=etape.nom, genre=etape.genre, panne=r.panne)
        if r.panne:
            r.panne_detail = await self._provoquer(r.panne, etape.nom)
            self.afficher(f"          ⚠ panne provoquée : {r.panne} ({r.panne_detail})")
        self._secours_vu = False
        t0 = time.monotonic()
        tache = asyncio.create_task(self._jouer_etape(etape, r))
        guet = asyncio.create_task(self._urgence.wait())
        try:
            await asyncio.wait({tache, guet}, return_when=asyncio.FIRST_COMPLETED)
        except asyncio.CancelledError:  # quelqu'un arrête le chef lui-même : on range et on s'en va
            guet.cancel()
            tache.cancel()
            with contextlib.suppress(BaseException):
                await tache
            raise
        guet.cancel()
        if not tache.done():
            tache.cancel()
        try:
            await tache
        except asyncio.CancelledError:
            pass
        except Exception as e:  # une erreur du chef ne doit pas arrêter la partition : étape ratée, on continue
            r.resultat, r.cause, r.detail = "ratee", "autre", f"erreur du chef : {e!r}"[:300]
            await self._emettre("note", texte=f"étape « {etape.nom} » : {r.detail}")
        if r.panne:
            await self._reparer(r.panne)
        if tache.cancelled() and not r.travail_fini:  # arrêt pendant le travail (pas seulement pendant la pause)
            r.resultat, r.cause = "interrompue", "stop_humain" if self._stop_humain else "arret_urgence"
            r.detail = self._raison_urgence if self._stop_humain else f"arrêt d'urgence ({self._raison_urgence or 'bouton'})"
            r.duree_s = round(time.monotonic() - t0, 3)
        await self._emettre("scenario_etape", quoi="fin", numero=i, nom=etape.nom, genre=etape.genre,
                            resultat=r.resultat, cause=r.cause, detail=r.detail, duree_s=r.duree_s,
                            limite_s=r.limite_s, plans_b=[p.moyen for p in r.plans_b if p.resultat != "inutile"])
        signe = {"reussie": "✔", "rattrapee": "✔ (plan B)", "ratee": "✘", "sautee": "↷", "interrompue": "🛑",
                 "ignoree": "·"}[r.resultat]
        self.afficher(f"  {i:>3}/{len(self.sc.etapes)} {etape.nom:.<34} {signe} {r.resultat} "
                      f"{r.duree_s:.2f} s{f' — {r.detail}' if r.resultat not in ('reussie', 'ignoree') else ''}")
        return r

    async def _jouer_etape(self, etape: Etape, r: ResultatEtape) -> None:
        t0 = time.monotonic()
        if etape.dire is not None:
            await self._etape_dire(etape, r)
        elif etape.annonce is not None:
            await self._annoncer(etape.annonce.texte, etape.annonce.langue)
        elif etape.attendre_s is not None:
            await self._pause(etape.attendre_s)
        elif etape.provoquer_panne is not None:
            if not self.repetition:
                r.resultat, r.detail = "ignoree", "hors répétition : aucune panne provoquée"
            else:
                r.detail = await self._provoquer(etape.provoquer_panne, etape.nom)
        elif etape.reparer:
            if not self.repetition:
                r.resultat, r.detail = "ignoree", "hors répétition : rien à réparer"
            else:
                for nom in sorted(self._pannes_actives):
                    await self._reparer(nom)
        elif etape.fiche:
            langue = etape.fiche.langue if etape.fiche is not True else self.sc.langue
            await self._annoncer(self._texte_fiche(langue), langue)
        elif etape.controle is not None:
            await self._etape_controle(etape.controle, r)
        r.duree_s = round(time.monotonic() - t0, 3)
        r.travail_fini = True
        await self._pause(etape.pause_apres_s)

    # ---------------------------------------------------------------- un contrôle (ajouté le 12.11.2026, H05)
    async def _etape_controle(self, nom: str, r: ResultatEtape) -> None:
        """Appelle la pièce donnée au chef sous ce nom, à part (dans un fil), et reçoit réussie ou ratée avec un détail."""
        rendu = await asyncio.to_thread(self.controles[nom])
        if isinstance(rendu, tuple):
            reussie, detail = bool(rendu[0]), str(rendu[1]) if len(rendu) > 1 else ""
        else:
            reussie, detail = bool(getattr(rendu, "reussie", False)), str(getattr(rendu, "detail", ""))
        r.detail = detail[:300]
        if not reussie:
            r.resultat, r.cause = "ratee", "controle"

    # ---------------------------------------------------------------- une phrase
    async def _etape_dire(self, etape: Etape, r: ResultatEtape) -> None:
        assert etape.dire is not None
        texte, langue = etape.dire.texte, etape.dire.langue
        attendu = etape.attendu or Attendu(genre="rien")
        limite = self._limite(self.sc.duree_max_de(etape))
        r.attendu, r.limite_s = attendu.decrire(), round(limite, 2)
        # Cette phrase répond-elle à un « vous confirmez ? » de l'étape d'avant ? (utile pour rejouer)
        a_confirmer, self._a_confirmer = self._a_confirmer, None
        if a_confirmer and oui_ou_non(texte, langue) is None:
            a_confirmer = None
        essai = await self._tenter(texte, langue, attendu, limite, self.source, etape.attendre_fin)
        if not essai.ok:
            r.cause, r.detail = essai.cause, essai.detail
            await self._plan_b(etape, r, essai, texte, langue, attendu, limite, a_confirmer)
        if r.resultat in ("reussie", "rattrapee") and self._derniere and self._derniere.ok and self._derniere.confirmation:
            self._a_confirmer = (texte, langue)
        # Le cerveau a dû passer au secours (réseau en panne, ou cerveau trop lent) : mode local tout de suite,
        # même si l'étape a réussi, pour que la suite ne paie pas l'attente à chaque phrase.
        if self._secours_vu and "mode_local" in self.sc.plan_b_de(etape) and r.resultat in ("reussie", "rattrapee"):
            mis = self._passer_en_mode_local()
            if mis:
                detail = f"cerveau en secours pendant l'étape : mis de côté jusqu'à la fin : {', '.join(mis)}"
                await self._emettre("plan_b", etat="essai", moyen="mode_local", cause="reseau", etape=etape.nom,
                                    numero=r.numero, preventif=True)
                await self._annoncer(dire_chef("mode_local", self.sc.langue), self.sc.langue)
                await self._emettre("plan_b", etat="reussi", moyen="mode_local", cause="reseau", etape=etape.nom,
                                    numero=r.numero, preventif=True, detail=detail)
                r.plans_b.append(EssaiPlanB("mode_local", "reseau", "reussi", detail, preventif=True))
                self.afficher(f"          🛟 plan B préventif : mode_local ({detail})")

    async def _tenter(self, texte: str, langue: str, attendu: Attendu, limite: float, source: str,
                      attendre_fin: bool = True) -> Tentative:
        """Envoie la phrase à la chaîne, attend au plus `limite` secondes, puis lit les événements."""
        conv = uuid.uuid4().hex[:10]
        self._mes_conversations.add(conv)
        debut = len(self._journal)
        entendu, confiance = self.oreille.entendre(texte) if source == "micro" else (texte, 1.0)
        if entendu != texte:
            await self._emettre("note", conversation=conv, texte=f"voix en panne (simulée) : « {texte} » arrive brouillé")
        if self._urgence.is_set():  # un stop ou un arrêt d'urgence est déjà là : on n'envoie plus rien
            raise asyncio.CancelledError
        arrets = self.s.chaine.compteur_arrets()  # lu AVANT d'envoyer : un stop arrivé entre-temps fait oublier la phrase
        tache = asyncio.create_task(self.s.chaine.traiter(entendu, langue, confiance_ecoute=confiance, source=source,
                                                          attendre_fin=attendre_fin, conversation=conv,
                                                          arrets_au_depart=arrets))
        trop_long = False
        try:
            await asyncio.wait_for(asyncio.shield(tache), limite)
        except asyncio.TimeoutError:
            trop_long = True
        except asyncio.CancelledError:
            # Arrêt d'urgence ou « stop » : on n'annule JAMAIS la chaîne en route (elle peut être en train de parler
            # au robot) ; l'arrêt est déjà passé par la prise. On attendra sa fin à la fin du scénario.
            self._garder_en_vol(tache)
            raise
        except Exception as e:  # la chaîne ne devrait jamais lever ; on le note et on continue la partition
            await self._emettre("note", conversation=conv, texte=f"chaîne en erreur : {e!r}"[:300])
        a_moi = [e for e in self._journal[debut:] if e.conversation == conv]
        ok = self._verifie(attendu, a_moi)
        if trop_long:
            if ok:  # l'attendu est là ; la chaîne finit juste de parler : on la laisse finir un instant
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(asyncio.shield(tache), 2.0)
            else:
                await self._nettoyer(tache, a_moi, langue)
        tous = self._journal[debut:]
        a_moi = [e for e in tous if e.conversation == conv]
        if trop_long and not ok:
            ok = self._verifie(attendu, a_moi)  # l'action a pu finir pendant le nettoyage : c'est fait, en retard
            trop_long = not ok
        t = Tentative(ok=ok, confirmation=any(e.type == "confirmation_demandee" for e in a_moi))
        if not ok:
            t.cause = self._cause(a_moi, tous, trop_long, source)
            t.detail = self._detail(t.cause, a_moi, tous, trop_long, limite)
        self._derniere = t
        return t

    async def _nettoyer(self, tache: asyncio.Task, a_moi: list[Evenement], langue: str) -> None:
        """Étape pas finie à temps : si le robot bouge encore pour elle, « stop » (par la chaîne), puis on abandonne."""
        # On n'annule jamais la chaîne elle-même. D'abord : une décision encore en réflexion est oubliée par la chaîne
        # (sans ordre au robot). Puis, si une action a démarré pour cette étape : « stop » par la chaîne.
        if not tache.done():
            self.s.chaine.oublier_la_decision_en_cours()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(asyncio.shield(tache), 3.0)
        conv = a_moi[0].conversation if a_moi else None
        a_moi = [e for e in self._journal if conv and e.conversation == conv] or a_moi
        demarrees = {e.donnees.get("id_action") for e in a_moi if e.type == "action_demarree"}
        finies = {e.donnees.get("id_action") for e in a_moi if e.type == "action_terminee"}
        if demarrees - finies:
            await self._emettre("note", texte="étape trop longue : le chef dit « stop » au robot, par la chaîne")
            conv_stop = uuid.uuid4().hex[:10]
            self._mes_conversations.add(conv_stop)
            await self.s.chaine.traiter("stop", langue, source=SOURCE, conversation=conv_stop)
            with contextlib.suppress(Exception):
                await asyncio.wait_for(asyncio.shield(tache), 10.0)
        if not tache.done():
            self._garder_en_vol(tache)

    def _garder_en_vol(self, tache: asyncio.Task) -> None:
        if not tache.done():
            self._en_vol.add(tache)
            tache.add_done_callback(self._en_vol.discard)

    @staticmethod
    def _verifie(attendu: Attendu, evs: list[Evenement]) -> bool:
        def de(type_: str) -> list[dict]:
            return [e.donnees for e in evs if e.type == type_]

        g = attendu.genre
        if g == "rien":
            return True
        if g == "action":
            type_ = "action_demarree" if attendu.statut == "demarree" else "action_terminee"
            for d in de(type_):
                a = d.get("action") or {}
                if a.get("nom") != attendu.action:
                    continue
                if type_ == "action_terminee" and d.get("statut") != "reussie":
                    continue
                if all((a.get("parametres") or {}).get(k) == v for k, v in attendu.parametres.items()):
                    return True
            return False
        if g == "refus":
            return any(d.get("verdict") == "non" for d in de("gardien_decision")) and not de("action_demarree")
        if g == "question":
            return bool(de("question_posee"))
        if g == "aide":  # le GARDIEN demande un humain (verdict « humain ») : rien ne part tant qu'un humain n'a pas accepté.
            # Une main levée pour une autre raison (deux « pas compris », deux échecs) n'est pas cet attendu.
            return any(d.get("verdict") == "humain" for d in de("gardien_decision")) and not de("action_demarree")
        if g == "confirmation":
            return any(not attendu.action or (d.get("action") or {}).get("nom") == attendu.action
                       for d in de("confirmation_demandee"))
        if g == "reponse":
            return any((attendu.contient or "").casefold() in str(d.get("texte", "")).casefold() for d in de("reponse_dite"))
        return False

    @staticmethod
    def _cause(a_moi: list[Evenement], tous: list[Evenement], trop_long: bool, source: str) -> str:
        def de(type_: str) -> list[dict]:
            return [e.donnees for e in a_moi if e.type == type_]

        if de("action_refusee") or any(d.get("statut") != "reussie" for d in de("action_terminee")) \
                or any(e.type == "panne" and e.source == "prise" for e in tous):
            return "robot"
        if any(d.get("verdict") == "non" for d in de("gardien_decision")):
            return "gardien"
        if any(e.type == "cerveau_secours" for e in tous) or (trop_long and not de("demande_comprise")):
            return "reseau"
        if trop_long and de("action_demarree"):
            return "robot"  # le robot n'a pas fini à temps
        if de("action_demarree"):
            return "inattendu"
        if source == "micro" and any(d.get("confiance_basse") or d.get("genre") == "inconnu" for d in de("demande_comprise")):
            return "voix"
        return "temps" if trop_long else "autre"

    @staticmethod
    def _detail(cause: str, a_moi: list[Evenement], tous: list[Evenement], trop_long: bool, limite: float) -> str:
        morceaux = []
        for e in a_moi:
            d = e.donnees
            if e.type == "action_refusee":
                codes = ", ".join(r.get("code", "?") for r in d.get("raisons", []))
                messages = [str((r.get("details") or {}).get("message", "")) for r in d.get("raisons", [])]
                morceaux.append(f"prise : {codes}" + (f" ({'; '.join(m for m in messages if m)})" if any(messages) else ""))
            elif e.type == "action_terminee" and d.get("statut") != "reussie":
                morceaux.append(f"action {d.get('statut')} : {d.get('message') or d.get('code_erreur') or ''}".strip())
            elif e.type == "gardien_decision" and d.get("verdict") == "non":
                morceaux.append("gardien : non (" + ", ".join(r.get("code", "?") for r in d.get("raisons", [])) + ")")
        for e in tous:
            if e.type == "cerveau_secours":
                morceaux.append(f"cerveau {e.donnees.get('de')} → {e.donnees.get('vers')} ({e.donnees.get('raison')})")
            elif e.type == "panne" and e.source == "prise":
                morceaux.append(f"prise : panne {e.donnees.get('quoi')}")
        if trop_long:
            morceaux.append(f"pas fini en {limite:.1f} s")
        dits = [str(e.donnees.get("texte")) for e in a_moi if e.type == "reponse_dite"]
        if dits and cause in ("voix", "autre", "temps"):
            morceaux.append(f"le robot a dit « {dits[-1]} »")
        return f"{CAUSES.get(cause, cause)} — " + " ; ".join(morceaux) if morceaux else CAUSES.get(cause, cause)

    # ---------------------------------------------------------------- plan B
    async def _plan_b(self, etape: Etape, r: ResultatEtape, essai: Tentative, texte: str, langue: str,
                      attendu: Attendu, limite: float, a_confirmer: tuple[str, str] | None) -> None:
        cause = essai.cause or "autre"
        for moyen in self.sc.plan_b_de(etape):
            if self._urgence.is_set():  # stop ou arrêt d'urgence : plus aucun plan B (l'étape sera « interrompue »)
                raise asyncio.CancelledError
            if moyen in INUTILES.get(cause, set()) or (moyen == "tablette" and self.source == "clavier"):
                pourquoi = "déjà sur la tablette" if moyen == "tablette" and self.source == "clavier" \
                    else f"ne répare pas : {CAUSES.get(cause, cause)}"
                r.plans_b.append(EssaiPlanB(moyen, cause, "inutile", pourquoi))
                continue
            t0 = time.monotonic()
            await self._emettre("plan_b", etat="essai", moyen=moyen, cause=cause, etape=etape.nom, numero=r.numero)
            self.afficher(f"          🛟 plan B : {moyen} (cause : {CAUSES.get(cause, cause)})")
            resultat, detail, nouvel = await self._appliquer(moyen, etape, texte, langue, attendu, limite, a_confirmer)
            r.plans_b.append(EssaiPlanB(moyen, cause, resultat, detail, round(time.monotonic() - t0, 3)))
            await self._emettre("plan_b", etat=resultat, moyen=moyen, cause=cause, etape=etape.nom, numero=r.numero,
                                detail=detail)
            if resultat == "reussi":
                r.resultat = "rattrapee"
                return
            if resultat == "saute":
                r.resultat = "sautee"
                return
            if nouvel is not None and nouvel.cause:
                cause = nouvel.cause  # le nouvel essai a raté pour une autre raison : on en tient compte
                r.detail = f"{r.detail} ; puis {nouvel.detail}"
        r.resultat = "ratee"

    async def _appliquer(self, moyen: str, etape: Etape, texte: str, langue: str, attendu: Attendu, limite: float,
                         a_confirmer: tuple[str, str] | None) -> tuple[str, str, Tentative | None]:
        lg = self.sc.langue
        if moyen == "tablette":
            self.source = "clavier"
            await self._annoncer(dire_chef("tablette", lg), lg)
            t = await self._rejouer(texte, langue, attendu, limite, etape.attendre_fin, a_confirmer)
            return ("reussi" if t.ok else "rate"), "phrase retapée au clavier (jusqu'à la fin du scénario)", t
        if moyen == "mode_local":
            mis = self._passer_en_mode_local()
            if not mis:
                return "inutile", "rien à mettre de côté : aucun cerveau par le réseau ou en échec", None
            await self._annoncer(dire_chef("mode_local", lg), lg)
            t = await self._rejouer(texte, langue, attendu, limite, etape.attendre_fin, a_confirmer)
            return ("reussi" if t.ok else "rate"), f"mis de côté jusqu'à la fin : {', '.join(mis)}", t
        if moyen == "main_humaine":
            fait = await self._main_humaine(etape, texte, attendu)
            qui = "simulée (opérateur automatique)" if isinstance(self.operateur, OperateurAutomatique) \
                else f"opérateur {self.operateur.nom}"
            return ("reussi" if fait else "rate"), f"main humaine {qui} : {'fait' if fait else 'pas pu'}", None
        await self._annoncer(dire_chef("sauter", lg), lg)  # sauter
        return "saute", "étape sautée, et dit à voix haute", None

    async def _rejouer(self, texte: str, langue: str, attendu: Attendu, limite: float, attendre_fin: bool,
                       a_confirmer: tuple[str, str] | None) -> Tentative:
        """Rejouer la phrase. Pour un « oui », redemander d'abord l'ordre : la chaîne n'accepte le « oui »
        que de la même source (micro, clavier) que l'ordre, et le premier essai a pu effacer la question."""
        if a_confirmer is not None:
            t = await self._tenter(*a_confirmer, Attendu(genre="confirmation"), limite, self.source)
            if not t.ok:
                return t
        return await self._tenter(texte, langue, attendu, limite, self.source, attendre_fin)

    async def _main_humaine(self, etape: Etape, texte: str, attendu: Attendu) -> bool:
        lg = self.sc.langue
        consigne = (f"étape « {etape.nom} » : faites à la main « {texte} » (attendu : {attendu.decrire()}), "
                    "puis rendez la main.")
        # Brique 11 : l'opérateur de l'écran note lui-même la reprise et le rendu (quand l'humain clique).
        noter = not getattr(self.operateur, "emet_pilotage", False)
        simulee = isinstance(self.operateur, OperateurAutomatique)  # la fiche compte à part une main simulée
        if noter:
            await self._emettre("pilotage_humain", quoi="reprise", etape=etape.nom, consigne=consigne,
                                operateur=self.operateur.nom, par=SOURCE, simulee=simulee)
        await self._annoncer(dire_chef("main_humaine", lg), lg)
        if not isinstance(self.operateur, OperateurClavier):  # l'opérateur clavier affiche lui-même la consigne
            self.afficher(f"          👤 {consigne}")
        fait = False
        try:
            fait = await self.operateur.prendre_la_main(consigne)
        finally:
            if noter:
                await self._emettre("pilotage_humain", quoi="rendu", etape=etape.nom, fait=fait,
                                    operateur=self.operateur.nom, par=SOURCE, simulee=simulee)
        if fait:
            await self._annoncer(dire_chef("main_rendue", lg), lg)
        return fait

    # ---------------------------------------------------------------- cerveau : mode local, panne réseau
    def _cascade(self) -> CerveauCascade | None:
        c = self.s.chaine.cerveau
        return c if isinstance(c, CerveauCascade) else None

    def _passer_en_mode_local(self) -> list[str]:
        """Met de côté (jusqu'à la fin du scénario) les cerveaux joints par le réseau et ceux qui ont échoué.
        Le dernier (le cerveau à règles) n'est jamais mis de côté : la cascade le garde toujours."""
        cascade = self._cascade()
        if cascade is None:
            return []
        mis = []
        for etage in cascade.etages[:-1]:
            if any(e is etage for e, _ in self._pauses):
                continue
            if _distant(etage.cerveau) or etage.cerveau.nom in self._echoues:
                self._pauses.append((etage, etage.en_pause_jusqua))
                etage.en_pause_jusqua = math.inf
                mis.append(etage.cerveau.nom)
        return mis

    def _couper_reseau(self) -> list[str]:
        cascade = self._cascade()
        if cascade is None:
            return []
        coupes = []
        for etage in cascade.etages[:-1]:
            if _distant(etage.cerveau) and not isinstance(etage.cerveau, CerveauInjoignable):
                self._coupes.append((etage, etage.cerveau))
                etage.cerveau = CerveauInjoignable(etage.cerveau)
                coupes.append(etage.cerveau.nom)
        return coupes

    def _retablir_reseau(self) -> None:
        for etage, original in self._coupes:
            etage.cerveau = original
        self._coupes = []

    # ---------------------------------------------------------------- pannes (répétition)
    async def _provoquer(self, nom: str, etape: str) -> str:
        if nom == "voix":
            self.oreille.en_panne = True
            detail = "les oreilles entendent mal (simulé)"
        elif nom == "reseau":
            coupes = self._couper_reseau()
            detail = (f"cerveaux par le réseau coupés : {', '.join(coupes)}" if coupes
                      else "aucun cerveau par le réseau : rien à couper")
        else:
            if self.s.simulation is None:
                await self._emettre("note", texte=f"vrai robot : panne « {nom} » NON provoquée")
                return "vrai robot : aucune panne provoquée"
            faux = "refus" if nom == "robot" else nom
            self.s.simulation.provoquer_panne(faux)
            detail = f"faux robot : panne « {faux} »"
        self._pannes_actives.add(nom)
        await self._emettre("panne", quoi=nom, provoquee=True, etape=etape, detail=detail, par=SOURCE)
        return detail

    async def _reparer(self, nom: str) -> None:
        if nom not in self._pannes_actives:
            return
        if nom == "voix":
            self.oreille.en_panne = False
        elif nom == "reseau":
            self._retablir_reseau()
        elif self.s.simulation is not None:
            self.s.simulation.reparer()  # répare toutes les pannes du faux robot
            self._pannes_actives -= {p for p in self._pannes_actives if p not in PANNES_CHEF or p == "robot"}
        self._pannes_actives.discard(nom)
        await self._emettre("reparation", quoi=nom, provoquee=True, par=SOURCE)

    async def _tout_remettre(self) -> None:
        """Fin du scénario : réparer les pannes provoquées, rendre le cerveau comme on l'a trouvé."""
        if self._en_vol:  # les phrases encore en route finissent seules (le stop est passé) ; au pire, on les coupe
            _, restent = await asyncio.wait(set(self._en_vol), timeout=10.0)
            for t in restent:  # dernier recours, après le stop : plus rien ne bouge pour elles
                await self._emettre("note", texte="une phrase du chef ne finit pas après le stop : coupée")
                t.cancel()
        for nom in sorted(self._pannes_actives):
            try:
                await self._reparer(nom)
            except Exception as e:  # ne jamais bloquer la fin
                await self._emettre("note", texte=f"réparation de « {nom} » impossible : {e!r}"[:300])
        self._retablir_reseau()
        for etage, ancienne in self._pauses:
            etage.en_pause_jusqua = ancienne
        self._pauses = []

    # ---------------------------------------------------------------- fiche
    def _fiche(self) -> Fiche:
        """La fiche de vérité de CETTE démonstration (calculée depuis ses seuls événements)."""
        f = calculer(self._journal)
        f.mention = self.s.prise.carte().mention_test()
        return f

    def _texte_fiche(self, langue: str) -> str:
        f = self._fiche()
        mention = dire_chef("mention_vrai" if f.mention == "testé sur vrai robot" else "mention_faux", langue)
        return dire_chef("fiche", langue, demandes=f.demandes, reussites=f.reussites, refus=f.refus_gardien,
                         questions=f.questions_posees, plans_b=f.plans_b, mention=mention)
