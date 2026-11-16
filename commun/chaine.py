"""La chaîne : de la phrase entendue jusqu'à la réponse.

parole → cerveau → gardien → (annonce) → prise → robot → réponse, tout noté dans la boîte noire.
Cette chaîne ne connaît ni la marque du robot, ni le modèle du cerveau.

Étape 4 (briques 7 et 8), ajouts limités, marqués « brique 7 » ou « brique 8 » :
- verdict « humain » du gardien : l'action ne part pas, le robot lève la main ; `reponse_humaine` = la suite
  quand un humain répond depuis l'écran (le gardien revérifie tout avant le ticket) ;
- le robot bute (deux « pas compris » de suite, deux échecs de suite) : il lève la main ;
- deux lieux ou deux objets nommés pour une seule action : une question (pour tous les cerveaux).
Inchangés : stop prioritaire, confirmation, verrou des chiffres, négation, annulation par stop.

Brique 11 (la main humaine), ajouts marqués « brique 11 » : quand un humain a « la main » (écran), les phrases
(voix, agents, clavier) ne commandent plus le robot — réponse polie, rien ne part — sauf « stop », qui passe avant.
L'humain donne ses ordres par `ordre_humain` : un formulaire au lieu du cerveau, puis le même chemin (gardien → prise).
"""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from pydantic import BaseModel, Field

from briques.b01_prise.actions import ActionDemandee
from briques.b01_prise.prise import Prise
from briques.b01_prise.raisons import ActionRefusee, Raison
from briques.b06_cerveau.prise_cerveau import Cerveau, Decision
from briques.b07_gardien.gardien import PREFIXE_AGENT, Gardien
from briques.b08_doute.doute import Doute, filet_plusieurs_choix
from commun.bus import Bus
from commun.monde import Monde
from commun.phrases import dire, est_ordre_arret, expliquer_refus, langue_de_reponse, langues, oui_ou_non

SOURCE_HUMAIN = "humain:"  # brique 11 : un ordre de l'humain qui a la main s'écrit « humain:qui » (boîte noire, gardien)


class Resultat(BaseModel):
    conversation: str
    langue: str
    decision: Decision
    verdict: str | None = None
    statut_action: str | None = None
    reponses: list[str] = Field(default_factory=list)
    action: ActionDemandee | None = None


def verrou_des_chiffres(action: ActionDemandee, texte: str) -> ActionDemandee:
    """Les chiffres dits par la personne sont recopiés dans l'action. Un cerveau peut oublier « à 5 mètres par
    seconde » : on le recopie, et le gardien refusera en l'expliquant. Si le cerveau et la phrase relue ne disent pas
    le même chiffre, on garde le PLUS GRAND (le gardien refuse s'il dépasse ; sinon la chaîne pose une question)."""
    from briques.b06_cerveau.branchements.regles import (lire_distance, lire_force, lire_vitesse,
                                                         petit_deplacement_demande)

    import math

    p = dict(action.parametres)
    if action.nom == "se_deplacer":
        v = lire_vitesse(texte)
        if v is not None:
            p["vitesse"] = max(v, float(p["vitesse"])) if p.get("vitesse") is not None else v
        d = lire_distance(texte)
        if d is None and "lieu" not in p and petit_deplacement_demande(texte):
            d = 0.5  # « avance un peu » : un petit pas de 50 cm, quel que soit le chiffre choisi par le cerveau
            dx, dy = float(p.get("dx") or 0), float(p.get("dy") or 0)
            n = math.hypot(dx, dy)
            p["dx"], p["dy"] = (d, 0.0) if n == 0 else (round(dx / n * d, 3), round(dy / n * d, 3))
        elif d is not None and "lieu" not in p:
            # On garde l'axe et le sens choisis par le cerveau (reculer, à gauche…) ; la longueur : la plus grande.
            dx, dy = float(p.get("dx") or 0), float(p.get("dy") or 0)
            n = math.hypot(dx, dy)
            if n == 0:
                p["dx"], p["dy"] = d, 0.0
            elif d > n:
                p["dx"], p["dy"] = round(dx / n * d, 3), round(dy / n * d, 3)
            else:
                p["dx"], p["dy"] = dx, dy
    if action.nom == "saisir":
        f = lire_force(texte)
        if f is not None:
            p["force"] = max(f, float(p["force"])) if p.get("force") is not None else f
    return action if p == action.parametres else ActionDemandee(nom=action.nom, parametres=p)


def chiffres_en_desaccord(action: ActionDemandee, texte: str) -> bool:
    """Le cerveau a compris un chiffre (vitesse, force, distance) qui ne va pas avec celui de la phrase : on ne
    choisit pas entre les deux, on demande. Exemple : le cerveau lit « 5,000 meters » = 5000 m, la phrase relue donne
    un autre nombre. (Le cerveau à règles lit avec les mêmes fonctions : jamais en désaccord avec lui-même.)"""
    from briques.b06_cerveau.branchements.regles import chiffre_vague, lire_distance, lire_force, lire_vitesse

    import math

    if action.nom in ("se_deplacer", "saisir") and chiffre_vague(texte):
        return True  # « plus de 5 mètres », « at least 2 m » : le chiffre n'est pas sûr

    def differents(a: float, b: float) -> bool:
        return abs(a - b) > 0.05 * max(abs(a), abs(b)) + 0.01

    p = action.parametres
    if action.nom == "se_deplacer":
        v = lire_vitesse(texte)
        if v is not None and p.get("vitesse") is not None and differents(v, float(p["vitesse"])):
            return True
        d = lire_distance(texte)
        n = math.hypot(float(p.get("dx") or 0), float(p.get("dy") or 0))
        if d is not None and "lieu" not in p and n > 0 and differents(d, n):
            return True
    if action.nom == "saisir":
        f = lire_force(texte)
        if f is not None and p.get("force") is not None and differents(f, float(p["force"])):
            return True
    return False


# « ne … pas » : « n' » est cherché avec son apostrophe (sinon « 20 N » serait une négation). En chinois, « 不 » seul
# n'est une négation que devant un verbe d'ordre (« 不去 ») : « 对不起 », « 不好意思 » sont des politesses.
NEGATIONS = {"fr": ["ne", "pas", "jamais"], "de": ["nicht", "kein", "keine", "nie"], "gsw": ["nöd", "nid", "nie"],
             "it": ["non", "mai"], "en": ["don't", "do not", "not", "never"],
             "zh": ["不要", "别", "不用", "不许", "不能", "不准"]}


def contient_negation(texte: str) -> bool:
    import re

    from briques.b06_cerveau.branchements.regles import _lexique, contient, normaliser

    brut = texte.lower().replace("’", "'")
    if re.search(r"(?<![\w])n'", brut):
        return True
    t = normaliser(brut)
    if any(contient(t, m) for lg, mots in NEGATIONS.items() if lg != "zh" for m in mots):
        return True
    if any(m in texte for m in NEGATIONS["zh"]):
        return True
    verbes_zh = [m for v in _lexique()["verbes"].values() for m in (v.get("zh") or [])]
    return any(f"不{m}" in texte for m in verbes_zh)


class Chaine:
    def __init__(self, bus: Bus, cerveau: Cerveau, gardien: Gardien, prise: Prise, monde: Monde,
                 seuil_confiance: float = 0.5, actions_a_confirmer: list[str] | None = None,
                 delai_confirmation_s: float = 20.0, doute: Doute | None = None) -> None:
        self.bus, self.cerveau, self.gardien, self.prise, self.monde = bus, cerveau, gardien, prise, monde
        self.seuil_confiance = seuil_confiance
        self.actions_a_confirmer = set(actions_a_confirmer or [])
        self.delai_confirmation_s = delai_confirmation_s
        self._en_attente: dict | None = None  # action à risque qui attend un « oui »
        self._arrets = 0  # augmente à chaque « stop » et à chaque arrêt d'urgence
        self._oublis = 0  # augmente quand on demande d'oublier la décision en cours (chef : étape trop longue)
        bus.abonner(self._sur_arret_urgence, "arret_urgence")
        bus.abonner(self._sur_reparation, "reparation")
        self._repli_annonce: set[str] = set()  # langues dont on a déjà dit « je réponds en allemand »
        self._taches: set[asyncio.Task] = set()  # garder une référence, sinon Python peut les jeter
        self.doute = doute or Doute(bus, monde)  # brique 8 : la main levée
        self._attente_humain: dict[str, dict] = {}  # brique 7 : n° de demande du gardien → langue, conversation
        self.pilote_humain: str | None = None  # brique 11 : qui a « la main » (écran) ; None = les phrases commandent
        self._main = 0  # brique 11 : numéro de main, augmente à chaque changement (humain ↔ robot)

    def _sur_arret_urgence(self, _ev=None) -> None:
        self._arrets += 1
        self._en_attente = None  # un arrêt d'urgence efface toute question en attente
        self._attente_humain.clear()  # … et toute demande à un humain (le gardien les efface aussi)

    def _sur_reparation(self, ev=None) -> None:
        """Un réarmement fait oublier tout ordre encore en route : il avait été donné pendant l'arrêt d'urgence."""
        if ev is not None and (ev.donnees or {}).get("quoi") == "rearmement":
            self._arrets += 1

    async def repondre(self, texte: str, langue: str, conversation: str, cle: str | None = None,
                       valeurs: dict | None = None, **extra: Any) -> str:
        """`cle` et `valeurs` (facultatifs) : la phrase connue de phrases.yaml qui a donné `texte`.
        Ils sont ajoutés à l'événement, pour que l'écran du jury redise la même phrase dans une autre langue
        (voir `redire`). Une valeur {"monde": id} est un lieu ou un objet (son nom change avec la langue),
        {"liste": [...]} une liste, {"cle": ..., "valeurs": ...} une phrase dans la phrase. cle "refus" :
        valeurs {"raisons": [...]}, redites par expliquer_refus. Sans clé (phrase écrite par un modèle) : rien de plus."""
        if cle:
            extra["cle"], extra["valeurs"] = cle, valeurs or {}
        await self.bus.emettre("reponse_dite", "chaine", robot=self.prise.robot, conversation=conversation,
                               texte=texte, langue=langue_de_reponse(langue), langue_entendue=langue, **extra)
        return texte

    def redire(self, cle: str, valeurs: dict | None, langue: str | None) -> str:
        """Refaire une réponse connue (champs `cle` et `valeurs` de « reponse_dite ») dans une autre langue.
        Pour l'écran : ne dit rien, n'envoie rien au robot, rend seulement le texte."""
        valeurs = valeurs or {}
        if cle == "refus":
            return expliquer_refus(valeurs.get("raisons") or [], langue)
        if cle == "main_levee" and valeurs.get("raisons"):  # le gardien demande un humain : la main levée + pourquoi
            return expliquer_refus(valeurs["raisons"], langue, intro="main_levee")
        return dire(cle, langue, **{k: self._valeur(v, langue) for k, v in valeurs.items()})

    def _valeur(self, v: Any, langue: str | None) -> Any:
        if isinstance(v, dict):
            if "monde" in v:
                return self._nom_local(v["monde"], langue)
            if "liste" in v:
                return ", ".join(str(self._valeur(x, langue)) for x in v["liste"])
            if "cle" in v:
                return self.redire(v["cle"], v.get("valeurs"), langue)
            if "nombre" in v:
                texte = f"{float(v['nombre']):.2f}".rstrip("0").rstrip(".")
                return texte.replace(".", ",") if langue_de_reponse(langue) in ("fr", "de", "it") else texte
        return v

    async def traiter(self, texte: str, langue: str | None = None, confiance_ecoute: float = 1.0,
                      source: str = "clavier", attendre_fin: bool = True, personne: str | None = None,
                      conversation: str | None = None, arrets_au_depart: int | None = None) -> Resultat:
        """`arrets_au_depart` (facultatif) : le compteur de « stop » lu par l'appelant AVANT d'envoyer la phrase
        (`compteur_arrets()`). Un stop arrivé entre-temps fait alors oublier la phrase (chef de démonstration)."""
        conv = conversation or uuid.uuid4().hex[:10]
        base_arrets = self._arrets if arrets_au_depart is None else arrets_au_depart
        t0 = time.monotonic()
        robot = self.prise.robot
        await self.bus.emettre("parole_entendue", source, robot=robot, conversation=conv, texte=texte,
                               langue=langue, confiance=confiance_ecoute, personne=personne)

        # « Stop » passe avant tout : avant la confirmation, avant le cerveau, quelle que soit la confiance.
        if est_ordre_arret(texte):
            self._en_attente = None
            self._attente_humain.clear()  # brique 7 : « stop » annule aussi ce qui attendait un humain
            self._arrets += 1
            langue = langue or langues()["defaut"]
            decision = Decision(genre="action", action=ActionDemandee(nom="arreter"), confiance=1.0, cerveau="arret_prioritaire")
            await self.bus.emettre("demande_comprise", "arret_prioritaire", robot=robot, conversation=conv, genre="action",
                                   action={"nom": "arreter", "parametres": {}}, confiance=1.0, langue=langue,
                                   confiance_ecoute=confiance_ecoute, duree_ms=self._ms(t0))
            return await self._agir(decision.action, langue, conv, Resultat(conversation=conv, langue=langue, decision=decision),
                                    t0, attendre_fin, source=source)  # brique 14 : le gardien note qui a dit « stop »

        # Brique 11 : un humain pilote depuis l'écran. « Stop » vient de passer juste au-dessus ; le reste reçoit une
        # réponse polie, et rien ne part (ni cerveau, ni gardien, ni « oui » d'une question d'avant).
        if self.pilote_humain is not None:
            langue = langue or langues()["defaut"]
            res = Resultat(conversation=conv, langue=langue, decision=Decision(genre="inconnu"))
            res.reponses.append(await self.repondre(dire("humain_pilote", langue), langue, conv, genre="humain_pilote",
                                                    temps_ms=self._ms(t0), cle="humain_pilote"))
            return res
        main_depart = self._main  # brique 11 : si la main change avant le ticket, rien ne part (voir _agir)

        # Une action à risque attend-elle un « oui » ? Seulement de la même source (micro, clavier, agent), à temps.
        attente, self._en_attente = self._en_attente, None
        if attente and attente["source"] != source and time.monotonic() < attente["expire"]:
            self._en_attente = attente  # la phrase d'une AUTRE source (agent, tablette) n'efface pas le « vous confirmez ? »
            attente = None
        if attente and time.monotonic() < attente["expire"] and attente["source"] == source:
            reponse = oui_ou_non(texte, attente["langue"])
            if reponse is not None:
                langue = langue or attente["langue"]
                if reponse and confiance_ecoute < self.seuil_confiance:
                    self._en_attente = attente  # « oui » mal entendu : on garde la question et on fait répéter
                    res = Resultat(conversation=conv, langue=langue, decision=Decision(genre="inconnu"))
                    res.reponses.append(await self.repondre(dire("incompris", langue), langue, conv, genre="inconnu",
                                                            cle="incompris"))
                    return res
                origine = attente["conversation"]  # noté dans la boîte noire : relie le « oui » à la demande d'origine
                decision = Decision(genre="action" if reponse else "inconnu", action=attente["action"], confiance=1.0,
                                    cerveau="confirmation")
                await self.bus.emettre("demande_comprise", "confirmation", robot=robot, conversation=conv,
                                       genre="confirmation", action=attente["action"].model_dump(), confiance=1.0,
                                       confirme=reponse, langue=langue, conversation_origine=origine, duree_ms=self._ms(t0))
                res = Resultat(conversation=conv, langue=langue, decision=decision)
                if not reponse:
                    res.reponses.append(await self.repondre(dire("confirmation_annulee", langue), langue, conv, genre="refus",
                                                            cle="confirmation_annulee"))
                    return res
                return await self._agir(attente["action"], langue, conv, res, t0, attendre_fin, confirme=True, source=source,
                                        arrets_base=base_arrets, main_base=main_depart)

        carte = self.prise.carte()
        arrets_avant = (base_arrets, self._oublis)
        decision = await self.cerveau.decider(texte, langue, carte, self.monde)
        duree_cerveau = round((time.monotonic() - t0) * 1000, 1)
        if (self._arrets, self._oublis) != arrets_avant and decision.genre == "action":
            # Un « stop » (ou un arrêt d'urgence) est arrivé pendant que le cerveau réfléchissait : on oublie sa réponse.
            await self.bus.emettre("note", "chaine", robot=robot, conversation=conv,
                                   texte="décision du cerveau annulée : un stop est arrivé pendant qu'il réfléchissait")
            return Resultat(conversation=conv, langue=langue or langues()["defaut"], decision=Decision(genre="inconnu"))
        langue = langue or decision.langue_devinee or langues()["defaut"]
        # Confiance trop basse (cerveau ou écoute) : on fait répéter au lieu de deviner. Jamais pour « s'arrêter ».
        confiance_basse = (decision.genre == "action" and decision.action is not None and decision.action.nom != "arreter"
                           and min(decision.confiance, confiance_ecoute) < self.seuil_confiance)
        if confiance_basse:
            decision = decision.model_copy(update={"genre": "inconnu"})
        elif decision.genre == "action" and decision.action and decision.action.nom != "arreter" and contient_negation(texte):
            # « Ne va surtout pas à la cuisine » : on ne devine pas, on demande.
            decision = decision.model_copy(update={"genre": "inconnu"})
        # Brique 8 : deux lieux (ou objets, gestes) nommés pour une seule action → une question, quel que soit le cerveau.
        decision = filet_plusieurs_choix(decision, texte, self.monde, carte)
        await self.bus.emettre("demande_comprise", self.cerveau.nom, robot=robot, conversation=conv,
                               genre=decision.genre, action=decision.action.model_dump() if decision.action else None,
                               options=[o.model_dump() for o in decision.options], confiance=decision.confiance,
                               confiance_ecoute=confiance_ecoute, confiance_basse=confiance_basse,
                               langue=langue, duree_ms=duree_cerveau)
        res = Resultat(conversation=conv, langue=langue, decision=decision)
        # Brique 8 : deux « pas compris » de suite pour la même personne → le robot lève la main (signal + phrase).
        main_levee = await self.doute.apres_decision(decision.genre, personne or source, texte, langue, conv, robot)

        # Le suisse allemand : on comprend, on répond en allemand, et on le dit une fois.
        info = langues()["langues"].get(langue, {})
        if info.get("reponse", langue) != langue and langue not in self._repli_annonce:
            note = dire("repli_langue", langue)
            if note:
                self._repli_annonce.add(langue)
                res.reponses.append(await self.repondre(note, langue, conv, genre="repli_langue", cle="repli_langue"))

        if decision.genre in ("inconnu", "discussion"):
            ecrit = decision.genre == "discussion" and bool(decision.texte)  # écrit par le cerveau : pas de clé
            texte_rep = decision.texte if ecrit else dire("incompris", langue)
            if main_levee:  # brique 8 : au lieu de « répétez », « je lève la main : j'ai besoin d'aide »
                res.reponses.append(await self.repondre(main_levee, langue, conv, genre="main_levee", temps_ms=self._ms(t0),
                                                        cle="main_levee"))
                return res
            res.reponses.append(await self.repondre(texte_rep, langue, conv, genre=decision.genre,
                                                    temps_ms=self._ms(t0), cle=None if ecrit else "incompris"))
            return res

        if decision.genre == "question":
            options = ", ".join(self._nommer(o, langue) for o in decision.options)
            # Question écrite par le cerveau (modèle de langue) : telle quelle. Sinon : une phrase toute prête.
            q = decision.texte if decision.texte else dire(decision.question or "incompris", langue, options=options)
            await self.bus.emettre("question_posee", "chaine", robot=robot, conversation=conv, question=q,
                                   options=[o.model_dump() for o in decision.options], langue=langue)
            res.reponses.append(await self.repondre(
                q, langue, conv, genre="question", temps_ms=self._ms(t0),
                cle=None if decision.texte else decision.question or "incompris",
                valeurs={"options": {"liste": [self._nommer_cle(o) for o in decision.options]}}))
            return res

        if decision.genre == "hors_carte":
            raisons = [{"code": "absente_de_la_carte", "details": {"action": decision.action_hors_carte}}]
            r = expliquer_refus(raisons, langue)
            res.reponses.append(await self.repondre(r, langue, conv, genre="refus", temps_ms=self._ms(t0),
                                                    cle="refus", valeurs={"raisons": raisons}))
            res.verdict = "non"
            return res

        assert decision.action is not None
        if (self._arrets, self._oublis) != arrets_avant:  # même filet juste avant d'agir
            return res
        doute_chiffre = chiffres_en_desaccord(decision.action, texte)
        if decision.action.nom == "parler":
            # H14 (réponse de Hiba à Q21 : C) : sur un ordre au robot, une parole proposée par le cerveau ne part jamais.
            # Le robot dit une phrase fixe ; rien ne va au gardien ni au robot. La boîte noire garde ce qui était proposé.
            await self.bus.emettre("note", "chaine", robot=robot, conversation=conv, quoi="parole_du_cerveau_refusee",
                                   texte="parole proposée par le cerveau : pas dite (phrase fixe à la place)",
                                   texte_propose=str(decision.action.parametres.get("texte", "")), cerveau=decision.cerveau)
            res.reponses.append(await self.repondre(dire("parole_refusee", langue), langue, conv, genre="refus",
                                                    temps_ms=self._ms(t0), cle="parole_refusee"))
            res.verdict = "non"
            return res
        action = verrou_des_chiffres(decision.action, texte)
        if action != decision.action:
            await self.bus.emettre("note", "chaine", robot=robot, conversation=conv,
                                   texte="chiffres dits par la personne recopiés dans l'action", action=action.model_dump())
        return await self._agir(action, langue, conv, res, t0, attendre_fin, source=source, doute_chiffre=doute_chiffre,
                                arrets_base=base_arrets, main_base=main_depart)

    def compteur_arrets(self) -> int:
        """Le nombre de « stop » et d'arrêts d'urgence vus : à lire avant d'envoyer une phrase (voir `traiter`)."""
        return self._arrets

    def oublier_la_decision_en_cours(self) -> None:
        """Une décision encore en réflexion ne partira pas (comme après un « stop », mais sans ordre au robot)."""
        self._oublis += 1

    # ---------- brique 11 : la main humaine ----------
    def changer_de_main(self, qui: str | None) -> int:
        """`qui` prend la main (None : il la rend). Le numéro de main augmente : tout ce qui était en route pour
        l'autre camp est oublié — une décision du cerveau en réflexion, un « vous confirmez ? », une action pas encore
        partie (voir `_agir`), et les demandes à un humain de l'autre camp (ici ET chez le gardien) : celles de la voix
        et des agents quand l'humain prend la main, celles de l'humain quand il la rend. Rend le nombre de demandes
        oubliées chez le gardien. Les événements `pilotage_humain` sont émis par la brique 11, pas ici."""
        self.pilote_humain = qui
        self._main += 1
        self._en_attente = None
        self._oublis += 1
        self._attente_humain.clear()
        humain = qui is not None
        return self.gardien.oublier_demandes(lambda d: d.demandeur.startswith(SOURCE_HUMAIN) != humain)

    async def ordre_humain(self, action: ActionDemandee, qui: str, langue: str | None = None,
                           conversation: str | None = None, attendre_fin: bool = False) -> Resultat:
        """Un ordre de l'humain qui a la main (boutons de l'écran) : un formulaire remplace le cerveau, puis le même
        chemin que tout le monde — gardien (ticket) → prise. Jamais d'appel direct au robot. Pas de « vous
        confirmez ? » (un bouton ne s'entend pas de travers) ; le gardien, lui, vérifie tout, comme pour la voix.
        Sans la main, seul « arreter » part (s'arrêter est toujours permis)."""
        conv = conversation or uuid.uuid4().hex[:10]
        langue = langue or langues()["defaut"]
        t0 = time.monotonic()
        main_depart = self._main
        source = f"{SOURCE_HUMAIN}{qui}"
        decision = Decision(genre="action", action=action, confiance=1.0, cerveau=source)
        res = Resultat(conversation=conv, langue=langue, decision=decision)
        if action.nom != "arreter" and self.pilote_humain is None:
            await self.bus.emettre("note", "chaine", robot=self.prise.robot, conversation=conv,
                                   texte="ordre de l'humain oublié : personne n'a la main")
            return res
        return await self._agir(action, langue, conv, res, t0, attendre_fin, confirme=True, source=source,
                                main_base=main_depart)

    async def _agir(self, action: ActionDemandee, langue: str, conv: str, res: Resultat, t0: float,
                    attendre_fin: bool, confirme: bool = False, source: str = "clavier",
                    doute_chiffre: bool = False, arrets_base: int | None = None,
                    main_base: int | None = None) -> Resultat:
        # Une action : le gardien d'abord (même après un « oui » : on revérifie tout).
        base = self._arrets if arrets_base is None else arrets_base
        main = self._main if main_base is None else main_base  # brique 11 : le numéro de main au départ
        if action.nom != "arreter" and self.prise.arret_urgence_actif:
            # Arrêt d'urgence actif : refusé tout de suite, sans gardien (rien ne doit attendre le réarmement).
            raisons = [Raison(code="arret_urgence_actif")]
            res.verdict, res.action = "non", action
            res.reponses.append(await self.repondre(expliquer_refus(raisons, langue), langue, conv, genre="refus",
                                                    temps_ms=self._ms(t0), cle="refus",
                                                    valeurs={"raisons": [x.model_dump() for x in raisons]}))
            return res
        # Brique 14 : le gardien sait si la demande vient d'un agent d'IA (source « agent:nom ») ; sinon « cerveau ».
        # Brique 11 : ou de l'humain qui a la main (source « humain:qui »).
        humain = source.startswith(SOURCE_HUMAIN)
        demandeur = source if source.startswith(PREFIXE_AGENT) or humain else "cerveau"
        verdict, ticket = await self.gardien.verifier(action, self.prise.carte(), conversation=conv, demandeur=demandeur)
        res.verdict, res.action = verdict.verdict, verdict.action
        if action.nom != "arreter" and self._arrets != base:
            # Un « stop » est passé pendant que le gardien vérifiait (il lit l'état du robot : une attente) : rien ne part.
            # (La prise refuse aussi tout ticket fabriqué avant le dernier stop.)
            await self.bus.emettre("note", "chaine", robot=self.prise.robot, conversation=conv,
                                   texte="action oubliée : un stop est arrivé pendant la vérification du gardien")
            res.statut_action = None
            return res
        if action.nom != "arreter" and (self._main != main or (self.pilote_humain is not None) != humain):
            # Brique 11 : la main a changé (numéro de main) depuis le départ de cet ordre, ou il vient de l'autre camp :
            # il n'est plus le bon. Rien ne part ; une demande à un humain qu'il vient de créer est oubliée aussi.
            if verdict.verdict == "humain" and verdict.numero_demande:
                self.gardien.oublier_demandes(lambda d: d.numero == verdict.numero_demande)
            await self.bus.emettre("note", "chaine", robot=self.prise.robot, conversation=conv,
                                   texte="action oubliée : la main a changé (humain / robot) avant le départ")
            res.statut_action = None
            return res
        if verdict.verdict not in ("oui", "humain") or (verdict.verdict == "oui" and ticket is None):
            r = expliquer_refus(verdict.raisons, langue)
            res.reponses.append(await self.repondre(r, langue, conv, genre="refus", temps_ms=self._ms(t0), cle="refus",
                                                    valeurs={"raisons": [x.model_dump() for x in verdict.raisons]}))
            return res
        if doute_chiffre:  # avant de demander à un humain : il accepterait un chiffre que la personne n'a peut-être pas dit
            # Le cerveau et la phrase ne disent pas le même chiffre, et même le plus grand est permis : on ne choisit
            # pas, on demande (le ticket non utilisé expire seul ; rien ne part).
            q = dire("question_chiffre", langue)
            await self.bus.emettre("question_posee", "chaine", robot=self.prise.robot, conversation=conv, question=q,
                                   options=[], langue=langue, raison="chiffres_en_desaccord")
            res.reponses.append(await self.repondre(q, langue, conv, genre="question", temps_ms=self._ms(t0),
                                                    cle="question_chiffre"))
            return res
        if verdict.verdict == "humain":
            return await self._attendre_un_humain(verdict, langue, conv, res, t0)

        # Action à risque : on répète l'ordre et on attend un « oui » (le ticket non utilisé expire seul).
        if verdict.action.nom in self.actions_a_confirmer and not confirme:
            self._en_attente = {"action": action, "langue": langue, "expire": time.monotonic() + self.delai_confirmation_s,
                                "source": source, "conversation": conv}
            question = dire("confirmer", langue, annonce=self._annonce(verdict.action, langue))
            await self.bus.emettre("confirmation_demandee", "chaine", robot=self.prise.robot, conversation=conv,
                                   action=verdict.action.model_dump(), langue=langue, question=question)
            cle_annonce, valeurs_annonce = self._annonce_cle(verdict.action)
            res.reponses.append(await self.repondre(question, langue, conv, genre="question", temps_ms=self._ms(t0),
                                                    cle="confirmer", valeurs={"annonce": {"cle": cle_annonce,
                                                                                         "valeurs": valeurs_annonce}}))
            return res
        return await self._lancer(verdict.action, ticket, langue, conv, res, t0, attendre_fin)

    async def _lancer(self, action: ActionDemandee, ticket, langue: str, conv: str, res: Resultat, t0: float,
                      attendre_fin: bool) -> Resultat:
        """La fin de `_agir`, telle quelle (séparée pour servir aussi après l'accord d'un humain) : annonce, prise, fin."""
        # On annonce avant d'agir — sauf « arreter » : la prise d'abord, l'annonce ensuite (rien ne doit retarder un stop).
        cle_annonce, valeurs_annonce = self._annonce_cle(action)
        arret = action.nom == "arreter"
        if not arret:
            res.reponses.append(await self.repondre(self._annonce(action, langue), langue, conv,
                                                    genre="annonce", temps_ms=self._ms(t0), cle=cle_annonce,
                                                    valeurs=valeurs_annonce))
        try:
            suivi = await self.prise.executer(ticket, conversation=conv)
            if arret:
                res.reponses.append(await self.repondre(self._annonce(action, langue), langue, conv,
                                                        genre="annonce", temps_ms=self._ms(t0), cle=cle_annonce,
                                                        valeurs=valeurs_annonce))
        except ActionRefusee as e:
            res.statut_action = "refusee"
            res.reponses.append(await self.repondre(expliquer_refus(e.raisons, langue), langue, conv, genre="refus",
                                                    cle="refus", valeurs={"raisons": [x.model_dump() for x in e.raisons]}))
            # Brique 8 : un robot qui refuse ou ne répond plus compte comme un échec (« occupé » ou arrêt d'urgence : non).
            if {r.code for r in e.raisons} & {"robot_refuse", "liaison_perdue", "delai_depasse"}:
                await self._apres_action(action, False, langue, conv, res, ", ".join(r.code for r in e.raisons))
            return res

        if attendre_fin:
            await self._conclure(suivi.id, langue, conv, res)
        else:
            t = asyncio.create_task(self._conclure(suivi.id, langue, conv, res))
            self._taches.add(t)
            t.add_done_callback(self._taches.discard)
        return res

    async def _conclure(self, ident: str, langue: str, conv: str, res: Resultat) -> None:
        fin = await self.prise.attendre(ident)
        res.statut_action = fin.statut
        if fin.action.nom == "etat":
            etat = await self.prise.etat()
            cle, valeurs = "etat", {"batterie": etat.batterie_pct, "erreurs": " ".join(etat.erreurs)}
        elif fin.statut == "reussie":
            cle, valeurs = "fait", {}
        else:
            # La raison dite dans la langue de la personne (le message du robot peut être dans une autre langue).
            cle_raison = f"echecs.{fin.code_erreur}" if fin.code_erreur else ""
            if cle_raison and dire(cle_raison, langue) != cle_raison:
                cle, valeurs = "echec", {"message": {"cle": cle_raison, "valeurs": {}}}
            else:
                cle, valeurs = "echec", {"message": fin.message or fin.statut}
        texte = self.redire(cle, valeurs, langue)
        res.reponses.append(await self.repondre(texte, langue, conv, genre="fin", statut=fin.statut, cle=cle,
                                                valeurs=valeurs))
        # Brique 8 : deux échecs de suite → le robot lève la main. Une action annulée (stop) ne compte pas.
        reussie = {"reussie": True, "echouee": False}.get(fin.statut)
        await self._apres_action(fin.action, reussie, langue, conv, res, fin.message or "")

    async def _apres_action(self, action: ActionDemandee, reussie: bool | None, langue: str, conv: str,
                            res: Resultat, message: str) -> None:
        main_levee = await self.doute.apres_action(action, reussie, langue, conv, self.prise.robot, message)
        if main_levee:
            res.reponses.append(await self.repondre(main_levee, langue, conv, genre="main_levee", cle="main_levee"))

    # ---------- brique 7 : « demande à un humain » ----------
    async def _attendre_un_humain(self, verdict, langue: str, conv: str, res: Resultat, t0: float) -> Resultat:
        """L'action ne part pas. Le robot lève la main et dit pourquoi ; l'écran montre la demande (événement
        `aide_demandee`, envoyé par le gardien). Un humain répondra par `reponse_humaine`."""
        en_cours = {d["numero"] for d in self.gardien.demandes_en_attente()}  # oublier les demandes périmées
        self._attente_humain = {n: c for n, c in self._attente_humain.items() if n in en_cours}
        self._attente_humain[verdict.numero_demande] = {"langue": langue, "conversation": conv, "arrets": self._arrets,
                                                        "main": self._main}  # brique 11 : valable pour CETTE main
        r = expliquer_refus(verdict.raisons, langue, intro="main_levee")
        res.reponses.append(await self.repondre(r, langue, conv, genre="main_levee", temps_ms=self._ms(t0),
                                                numero_demande=verdict.numero_demande, cle="main_levee",
                                                valeurs={"raisons": [x.model_dump() for x in verdict.raisons]}))
        return res

    async def reponse_humaine(self, numero: str, accepte: bool, qui: str = "humain",
                              attendre_fin: bool = False) -> Resultat | None:
        """Un humain répond depuis l'écran. Le gardien revérifie TOUT avant de délivrer le ticket : si entre-temps
        une personne s'est approchée, c'est « non ». Pas de deuxième « vous confirmez ? » : l'humain vient de dire oui.
        Rend None si la demande ne vient pas de cette chaîne, ou a été annulée par un stop."""
        ctx = self._attente_humain.pop(numero, None)
        if ctx is not None and ctx["arrets"] != self._arrets:
            ctx = None  # un stop est passé depuis : rien ne part (le gardien a déjà oublié la demande)
        if ctx is not None and ctx.get("main") != self._main:
            ctx = None  # brique 11 : la main a changé depuis la demande (humain ↔ robot) : rien ne part
        arrets, main = self._arrets, self._main
        verdict, ticket = await self.gardien.reponse_humaine(numero, accepte, self.prise.carte(), qui=qui)
        if ctx is not None and (self._arrets != arrets or self._main != main):
            ctx = None  # un stop, ou un changement de main, PENDANT la revérification du gardien : rien ne part non plus
        if ctx is None:
            return None
        langue, conv, t0 = ctx["langue"], ctx["conversation"], time.monotonic()
        res = Resultat(conversation=conv, langue=langue, verdict=verdict.verdict, action=verdict.action,
                       decision=Decision(genre="action", action=verdict.action, confiance=1.0, cerveau=f"humain:{qui}"))
        if verdict.verdict == "oui" and ticket is not None:
            return await self._lancer(verdict.action, ticket, langue, conv, res, t0, attendre_fin)
        if verdict.verdict == "humain":  # une NOUVELLE raison est apparue (ex. on ne sait plus où est le robot)
            return await self._attendre_un_humain(verdict, langue, conv, res, t0)
        res.reponses.append(await self.repondre(expliquer_refus(verdict.raisons, langue), langue, conv, genre="refus",
                                                cle="refus", valeurs={"raisons": [x.model_dump() for x in verdict.raisons]}))
        return res

    # ---------- petits outils ----------
    @staticmethod
    def _ms(t0: float) -> float:
        return round((time.monotonic() - t0) * 1000, 1)

    def _nom_local(self, ident: str | None, langue: str) -> str:
        if not ident:
            return ""
        chose = self.monde.lieu(ident) or self.monde.objet(ident)
        if chose is None:
            return ident
        lr = langue_de_reponse(langue)
        noms = chose.noms.get(lr) or chose.noms.get("fr") or [ident]
        nom = noms[0]
        return nom[:1].upper() + nom[1:] if lr == "de" else nom  # en allemand, les noms prennent une majuscule

    def _annonce(self, action: ActionDemandee, langue: str) -> str:
        return self.redire(*self._annonce_cle(action), langue)

    @staticmethod
    def _annonce_cle(action: ActionDemandee) -> tuple[str, dict]:
        """L'annonce en clé + valeurs : les lieux et objets restent des identifiants (nommés dans chaque langue)."""
        p = action.parametres
        cle = action.nom
        distance, sens = "", ""
        if action.nom == "se_deplacer" and not p.get("lieu"):
            cle = "se_deplacer_relatif"
            import math
            d = math.hypot(float(p.get('dx') or 0), float(p.get('dy') or 0))
            distance = {"nombre": round(d, 2)}  # écrit dans chaque langue (0,04 reste 0,04 ; virgule en fr, de, it)
            dx, dy = float(p.get('dx') or 0), float(p.get('dy') or 0)
            sens = {"cle": "sens." + (("avant" if dx >= 0 else "arriere") if abs(dx) >= abs(dy)
                                      else ("gauche" if dy > 0 else "droite")), "valeurs": {}}  # le sens est dit
        return f"annonce.{cle}", {"distance": distance, "sens": sens, "lieu": {"monde": p.get("lieu")},
                                  "objet": {"monde": p.get("objet")}, "cible": {"monde": p.get("cible")},
                                  "geste": p.get("nom", "")}

    @staticmethod
    def _nommer_cle(action: ActionDemandee) -> Any:
        """Comme _nommer, mais sans langue : {"monde": id} (redit dans chaque langue) ou le nom de l'action."""
        p = action.parametres
        quoi = p.get("lieu") or p.get("objet") or p.get("cible") or p.get("nom")
        return {"monde": quoi} if quoi else action.nom

    def _nommer(self, action: ActionDemandee, langue: str) -> str:
        p = action.parametres
        quoi = p.get("lieu") or p.get("objet") or p.get("cible") or p.get("nom")
        # Brique 8 : une option sans cible (« prends ou pose ? ») est dite dans la langue, pas avec son nom de code.
        return self._nom_local(quoi, langue) if quoi else dire(f"actions.{action.nom}", langue)
