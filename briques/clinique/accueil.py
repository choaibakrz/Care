"""L'accueil du hall, version écrite : la phrase d'arrivée est tapée au clavier (cahier 5.9, tâche T10).

    accueil = AccueilDuHall(porte, carnet, badge_du_robot)
    accueil.entendre("Buongiorno, sono Giulia B.")     # la réponse en italien, le chemin, le message à l'étage
    accueil.messages_pour_l_etage(badge_soignant)      # ce que l'étage a reçu
    accueil.appels(badge_accueil)                      # les fois où le robot a appelé un humain

- La langue : devinée par les mots de la phrase tapée (accueil_hall.yaml). On répond dans la langue entendue, pas
  dans celle du dossier. Langue pas reconnue : français, et la réponse le note (langue_sure = False).
  À la voix, c'est la brique 4 qui reconnaîtra la langue (T20).
- La personne dit son nom. Le robot la cherche dans les arrivées du jour, par la porte. Pas de visage.
- Le robot ne donne une chambre que pour une SIMPLE ARRIVÉE : saluer, « je suis », le prénom et le nom (ou son
  initiale), rien d'autre, pas de question. « Où est Giulia ? », « je cherche Giulia B. », « je ne suis pas… » : il
  appelle un humain et ne dit rien. Limite : quelqu'un qui dit le nom d'un autre comme si c'était le sien reçoit la
  chambre (le cahier ne demande pas de preuve d'identité ; voir NON_TESTE.md).
  Ce qui compte comme « le nom » après le prénom (resserré le 14.11.2026) : l'initiale seule, ou un mot qui commence
  par l'initiale, écrit avec une majuscule au milieu d'une phrase, qui n'est ni un mot courant ni un mot de santé.
  Avant, « Is Giulia better » ou « Hallo Giulia, bitte » recevaient la chambre.
  CE QUI REÇOIT ENCORE LA CHAMBRE sans être la personne (trouvé par les relecteurs, pas corrigé) :
  (1) la demande d'un visiteur faite seulement de mots permis : « Frau Giulia B., bitte », « Madame Giulia B. »,
      « C'est Giulia B. », « Is Giulia B. there » ; (2) une question dite sans « ? » : « Ist Giulia B. » ;
  (3) un mot inconnu écrit avec une majuscule au milieu d'une phrase : « Is Giulia Better », « Giulia Blumen ».
  Le hall ne prouve pas qui parle : c'est la limite de fond, écrite dans NON_TESTE.md.
- Pour une simple arrivée, il dit la chambre, l'étage et la première heure du programme, et montre le chemin. Il
  n'accompagne pas : il prévient l'étage (une ligne du carnet, que l'écran du soignant de l'étage affiche).
- Étage inconnu, ou pas d'ascenseur connu pour cet étage : il ne promet pas « on vous attend » ; il appelle un humain.
- Dans le hall, il ne dit rien sur la santé : la règle est écrite en clair dans accueil_hall.yaml. À « pourquoi
  Madame B. est-elle ici ? », il ne dit même pas si elle est là. La liste de mots ne voit pas toutes les questions
  de santé : celles qu'elle manque appellent quand même un humain (ce ne sont pas de simples arrivées).
  De toute façon, la porte ne donne au robot du hall rien sur la santé.
- Nom inconnu : il n'insiste pas, il appelle un humain. Ni la phrase, ni le nom dit ne sont gardés.
- Aucun robot ne bouge ici : pas d'ordre, donc pas de ticket du gardien. Étiquette : SIMULÉ (phrase tapée, pas de voix).
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from .carnet import Carnet
from .porte import Badge, PorteDeLecture

FICHIER = Path(__file__).resolve().parent / "accueil_hall.yaml"
GENRE_MESSAGE, GENRE_APPEL = "message pour l'étage", "appel d'un humain"
MARQUE, ETIQUETTE = "données inventées", "SIMULÉ"
LANGUE_PAR_DEFAUT = "fr"
HALL = "Hall"


@lru_cache(maxsize=1)
def _reglages() -> dict[str, Any]:
    return yaml.safe_load(FICHIER.read_text(encoding="utf-8"))


def _simple(texte: str) -> str:
    sans = unicodedata.normalize("NFD", str(texte).lower().replace("’", "'").replace("ß", "ss"))
    return "".join(c for c in sans if unicodedata.category(c) != "Mn")


def _mots(texte: str) -> list[str]:
    return re.findall(r"[a-z]+", _simple(texte))


def deviner_langue(texte: str) -> tuple[str, bool]:
    """La langue d'une phrase tapée, par ses mots courants. Rend (langue, sûre ?). Égalité ou aucun mot : pas sûre."""
    mots = set(_mots(texte))
    votes = {langue: len(mots & set(connus)) for langue, connus in _reglages()["mots_des_langues"].items()}
    meilleure = max(votes, key=votes.get)
    if votes[meilleure] == 0 or sum(v == votes[meilleure] for v in votes.values()) > 1:
        return LANGUE_PAR_DEFAUT, False
    return meilleure, True


def parle_de_sante(texte: str, prenoms: tuple[str, ...] = ()) -> bool:
    """La règle du hall : la phrase touche-t-elle à la santé ? `prenoms` : ceux des arrivées du jour, pour
    « pourquoi Giulia… ». Cette règle choisit la réponse ; la sûreté vient de simple_arrivee()."""
    regle, mots = _reglages()["regle_sante"], set(_mots(texte))
    if mots & set(regle["entiers"]) or any(mot.startswith(debut) for mot in mots for debut in regle["debuts"]):
        return True
    quelqu_un = set(regle["personne"]) | {m for p in prenoms for m in _mots(p)}
    return bool(mots & set(regle["pourquoi"])) and bool(mots & quelqu_un)


def _mots_tels_qu_ecrits(texte: str) -> list[tuple[str, bool]]:
    """Les mêmes mots que _mots(), avec leurs majuscules, et pour chacun : commence-t-il une phrase ?
    (le premier mot, ou un mot juste après « . ! : ; … »). Une majuscule en début de phrase ne dit rien sur un nom."""
    sans = unicodedata.normalize("NFD", str(texte).replace("’", "'").replace("ß", "ss").replace("ẞ", "SS"))
    sans = "".join(c for c in sans if unicodedata.category(c) != "Mn")
    rendus = []
    for trouve in re.finditer(r"[A-Za-z]+", sans):
        avant = sans[:trouve.start()].rstrip()
        rendus.append((trouve.group(), not avant or avant[-1] in ".!:;…"))
    return rendus


def _mots_ordinaires() -> frozenset[str]:
    """Tous les mots courants que le fichier connaît (saluer, se présenter, les mots des langues, ceux de la règle
    sur la santé). Un mot courant n'est jamais pris pour un nom de famille : « bitte », « buenos », « bonsoir »…"""
    reglages = _reglages()
    mots = set(reglages["mots_d_arrivee"])
    for connus in reglages["mots_des_langues"].values():
        mots |= set(connus)
    regle = reglages["regle_sante"]
    mots |= set(regle["entiers"]) | set(regle["pourquoi"]) | set(regle["personne"])
    return frozenset(mot for mot in mots if isinstance(mot, str))


def _est_le_nom(mot: str, ecrit: str, debut_de_phrase: bool, initiale: str, tout_en_majuscules: bool) -> bool:
    """Le mot dit juste après le prénom est-il le nom de famille ? (resserré le 14.11.2026)
    Oui pour l'initiale seule (« Giulia B. »). Oui pour un mot qui commence par l'initiale, ÉCRIT AVEC UNE MAJUSCULE au
    milieu d'une phrase, qui n'est ni un mot courant ni un mot de la règle sur la santé (« Giulia Bianchi »).
    Non pour tout le reste : « Giulia better », « Giulia, bitte », « Giulia. Bis morgen », « Giulia Brustkrebs »,
    « giulia bianchi » (sans majuscule : on ne devine pas, un humain est appelé).
    Dans une phrase écrite TOUT EN MAJUSCULES, seule l'initiale seule compte.
    Le robot du hall ne connaît que l'initiale du nom : il ne peut pas vérifier le nom entier. Les limites qui
    restent sont écrites en tête de ce fichier et dans NON_TESTE.md."""
    if mot == initiale:
        return True
    return (mot.startswith(initiale) and not tout_en_majuscules and ecrit[:1].isupper() and not debut_de_phrase
            and mot not in _mots_ordinaires() and not parle_de_sante(mot))


def simple_arrivee(texte: str, arrivees: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Rend (les arrivées du jour dont le prénom est dit, celles pour qui la phrase est une simple arrivée).
    Simple arrivée : pas de question ; le prénom, suivi du nom ou de son initiale (voir _est_le_nom) ; autour,
    seulement des mots pour saluer et dire « je suis ». Tout le reste n'en est pas une.
    Si deux personnes sont possibles avec l'ancienne règle large, on n'en choisit aucune (comme avant le 14.11.2026)."""
    mots, permis = _mots(texte), set(_reglages()["mots_d_arrivee"])
    ecrits = _mots_tels_qu_ecrits(texte)
    if len(ecrits) != len(mots):
        ecrits = [(mot, True) for mot in mots]  # on ne sait pas où sont les majuscules : aucune ne compte (le sens sûr)
    lettres = [c for c in str(texte) if c.isalpha()]
    tout_en_majuscules = bool(lettres) and all(c.isupper() for c in lettres)
    nommees, larges, serrees = [], [], []
    for a in arrivees:
        prenom, initiale = _mots(a.get("prenom") or ""), _simple(a.get("initiale") or "")[:1]
        if not prenom or not initiale:
            continue  # une fiche sans prénom ou sans initiale : on ne devine pas
        for i in range(len(mots) - len(prenom) + 1):
            if mots[i:i + len(prenom)] != prenom:
                continue
            nommees.append(a)
            apres = i + len(prenom)
            suite = mots[apres:]
            if (suite and suite[0].startswith(initiale) and "?" not in texte
                    and all(m in permis for m in mots[:i] + suite[1:])):
                larges.append(a)  # la règle d'avant : un mot qui commence par l'initiale
                if _est_le_nom(suite[0], *ecrits[apres], initiale, tout_en_majuscules):
                    serrees.append(a)
            break
    if len(larges) != 1:
        return nommees, larges  # personne (0), ou plusieurs personnes possibles : le robot n'en choisit aucune
    return nommees, serrees


class AccueilDuHall:
    def __init__(self, porte: PorteDeLecture, carnet: Carnet, robot: Badge) -> None:
        if robot.role != "robot":
            raise ValueError("l'accueil du hall est tenu par un robot : il faut un badge de robot")
        self.porte, self.carnet, self.robot = porte, carnet, robot

    # ------------------------------------------------------------------ dire
    @staticmethod
    def _dire(cle: str, langue: str, **valeurs: Any) -> str:
        phrases = _reglages()["phrases"]
        modele = phrases.get(langue, {}).get(cle) or phrases[LANGUE_PAR_DEFAUT][cle]
        return modele.format(**valeurs)

    def _reponse(self, cas: str, langue: str, sure: bool, phrases: list[str], **plus: Any) -> dict[str, Any]:
        return {"cas": cas, "langue": langue, "langue_sure": sure, "dit": " ".join(phrases), "phrases": phrases,
                "chemin": [], "etage_prevenu": False, "appel": None, "etiquette": ETIQUETTE, "marque": MARQUE, **plus}

    def _appeler_un_humain(self, raison: str, langue: str) -> dict[str, Any]:
        """Le robot n'insiste pas : il appelle. Ni la phrase dite, ni le nom dit ne sont gardés."""
        return self.carnet.ecrire(self.robot, GENRE_APPEL, {"ou": HALL, "raison": raison, "langue": langue},
                                  valide_par_un_humain=False)["donnees"]

    # ------------------------------------------------------------------ le chemin
    def _chemin(self, chambre: Any, etage: Any) -> list[dict[str, Any]] | None:
        """Du hall à la chambre, sur le plan lu par la porte. L'ascenseur : aucune distance inventée.
        None si on ne sait pas y aller (étage inconnu, pas d'ascenseur connu pour cet étage)."""
        plan = self.porte.lieux(self.robot)
        etages = {lieu["nom"]: lieu.get("etage") for lieu in plan["lieux"]}
        voisins: dict[str, list[tuple[str, float]]] = {}
        for v in plan["voisins"]:
            voisins.setdefault(v["de"], []).append((v["a"], v["metres"]))
            voisins.setdefault(v["a"], []).append((v["de"], v["metres"]))

        def troncon(depart: str, arrivee: str) -> list[dict[str, Any]] | None:
            """Le plus court chemin sur un même étage, lieu par lieu, avec les mètres de chaque pas."""
            a_voir, vus = [(0.0, [(depart, 0)])], set()
            while a_voir:
                a_voir.sort(key=lambda c: c[0])
                total, pas = a_voir.pop(0)
                ici = pas[-1][0]
                if ici == arrivee:
                    return [{"lieu": lieu, "metres": metres} for lieu, metres in pas]
                if ici in vus:
                    continue
                vus.add(ici)
                a_voir += [(total + m, pas + [(suivant, m)]) for suivant, m in voisins.get(ici, ()) if suivant not in vus]
            return None

        def ascenseur(niveau: Any) -> str | None:
            return next((nom for nom, e in etages.items() if nom.startswith("Ascenseur") and e == niveau), None)

        but = f"Chambre {chambre}"
        if etage is None:
            return None
        if etage == etages.get(HALL):  # même étage que le hall : pas d'ascenseur
            return troncon(HALL, but) if but in etages else None
        bas, haut_depart = troncon(HALL, ascenseur(etages.get(HALL)) or ""), ascenseur(etage)
        if not bas or haut_depart is None:
            return None  # on ne montre pas un faux chemin
        haut = troncon(haut_depart, but) if but in etages else None
        haut = haut or [{"lieu": haut_depart, "metres": 0}]  # chambre hors du plan : on s'arrête à l'ascenseur de l'étage
        haut[0] = {"lieu": haut_depart, "metres": None}  # on change d'étage : pas de mètres inventés
        return bas + haut

    # ------------------------------------------------------------------ entendre une phrase tapée
    def entendre(self, texte: str, langue: str | None = None) -> dict[str, Any]:
        """Une phrase d'arrivée, tapée. Rend ce que le robot dit, le chemin, et s'il a prévenu l'étage ou appelé un humain.
        La réponse va à l'écran du hall, que tout le monde voit : ni numéro de dossier, ni nom de famille."""
        texte = " ".join(str(texte).split())[:200]
        if langue in _reglages()["phrases"]:
            sure = True
        else:
            langue, sure = deviner_langue(texte)

        arrivees = self.porte.arrivees_pour_le_hall(self.robot)
        nommees, simples = simple_arrivee(texte, arrivees)
        if len(simples) != 1:  # pas une simple arrivée : le robot ne donne aucune chambre, il appelle un humain
            if parle_de_sante(texte, tuple(a["prenom"] for a in arrivees)):
                appel = self._appeler_un_humain("question de santé dans le hall", langue)
                return self._reponse("santé", langue, sure, [self._dire("sante", langue)], appel=appel,
                                     regle=_reglages()["regle_sante"]["phrase"])
            if nommees:  # un nom connu, mais autre chose qu'une simple arrivée (« je cherche… », « où est… »)
                appel = self._appeler_un_humain("phrase pas comprise dans le hall", langue)
                return self._reponse("inconnu", langue, sure, [self._dire("pas_compris", langue)], appel=appel)
            appel = self._appeler_un_humain("nom inconnu dans le hall", langue)
            return self._reponse("inconnu", langue, sure, [self._dire("inconnu", langue)], appel=appel)

        a = simples[0]
        if not sure and a.get("par_message") and a.get("langue") in _reglages()["phrases"]:
            langue = a["langue"]  # arrivée par message, langue de la phrase pas sûre : la langue de sa fiche administrative (L03)
        chemin = self._chemin(a["chambre"], a["etage"])
        if chemin is None:  # on ne sait pas à quel étage l'envoyer : pas de « on vous attend », un humain vient
            appel = self._appeler_un_humain("étage inconnu pour une arrivée", langue)
            return self._reponse("arrivée", langue, sure, [self._dire("sans_etage", langue, prenom=a["prenom"])],
                                 appel=appel, prenom=a["prenom"], chambre=None, etage=None, premiere_heure=None)
        phrases = [self._dire("arrivee", langue, prenom=a["prenom"], chambre=a["chambre"], etage=a["etage"])]
        if a["premiere_heure"]:
            phrases.append(self._dire("programme", langue, heure=a["premiere_heure"]))
        phrases += [self._dire("seul", langue), self._dire("chemin", langue)]
        self._prevenir_l_etage(a, langue)
        return self._reponse("arrivée", langue, sure, phrases, chemin=chemin, etage_prevenu=True, prenom=a["prenom"],
                             chambre=a["chambre"], etage=a["etage"], premiere_heure=a["premiere_heure"])

    def _prevenir_l_etage(self, a: dict[str, Any], langue: str) -> None:
        """Le message à l'étage : une ligne du carnet. Une seule fois par personne."""
        if any(l["qui"] == self.robot.id and l["donnees"].get("patient") == a["id"] for l in self.carnet.lignes(GENRE_MESSAGE)):
            return
        nom_de_la_langue = _reglages()["noms_des_langues"].get(langue, langue)
        texte = (f"{a['nom']} arrive. Chambre {a['chambre']}. Langue parlée dans le hall : {nom_de_la_langue}. "
                 f"Le robot ne l'accompagne pas : à attendre à la sortie de l'ascenseur.")
        self.carnet.ecrire(self.robot, GENRE_MESSAGE, {"etage": a["etage"], "patient": a["id"], "texte": texte,
                                                      "langue": langue}, valide_par_un_humain=False)

    # ------------------------------------------------------------------ ce que les humains reçoivent
    def messages_pour_l_etage(self, badge: Badge) -> list[dict[str, Any]]:
        """Pour un soignant : les messages du robot du hall pour son étage."""
        if badge.role != "soignant":
            self.porte.refuser(badge, "messages du hall", "les messages du hall sont pour les soignants de l'étage")
        return [{**l["donnees"], "quand": l["quand"]} for l in self.carnet.lignes(GENRE_MESSAGE)
                if l["qui"] == self.robot.id and badge.etage is not None and l["donnees"].get("etage") == badge.etage]

    def appels(self, badge: Badge) -> list[dict[str, Any]]:
        """Pour l'accueil : les fois où le robot du hall a appelé un humain."""
        if badge.role != "accueil":
            self.porte.refuser(badge, "appels du hall", "les appels du hall sont pour l'accueil")
        return [{**l["donnees"], "quand": l["quand"]} for l in self.carnet.lignes(GENRE_APPEL) if l["qui"] == self.robot.id]
