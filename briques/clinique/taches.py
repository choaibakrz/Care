"""Le tableau des tâches et les demandes au robot (cahier 5.6).

    tableau = TableauDesTaches(porte, carnet, listes)
    tableau.demander(badge, "p01", "il manque un coussin en chambre 12")
        → une question courte : « Lequel : le grand coussin, ou le coussin de nuque ? »
    tableau.demander(badge, "p01", "il manque un coussin en chambre 12", choix="grand coussin")
        → une tâche pour un robot : grand coussin, de la Réserve à la Chambre 12, état « demandée »
    tableau.demander(badge, "p01", "il manque un fauteuil roulant")
        → l'objet n'est pas dans la réserve : le prototype le dit, et la tâche passe à un humain

- Toutes les demandes arrivent ici. Une tâche a : qui demande, pour qui, quoi, d'où, où, pour quand, et un état.
- Deux sortes de tâches : pour un robot (apporter un objet de la réserve) et pour un humain.
- Demande floue : une question courte. Le prototype ne devine pas.
- La réserve et le plan sont lus par la porte. Les tâches s'écrivent dans le carnet, jamais dans le faux dossier.
- Aucun conseil de santé : ce qui n'est pas un objet de la réserve passe à un humain, sans commentaire.
- ICI, AUCUN ROBOT NE BOUGE. La course du faux robot, sous le gardien, vient avec la tâche T07b.
"""
from __future__ import annotations

import re
from typing import Any

from .carnet import Carnet
from .listes import HUMAINS, ListesDeSoin
from .listes import ChoixRefuse
from .porte import Badge, PorteDeLecture

GENRE = "tâche"
ETATS = ("demandée", "attribuée", "en route", "livrée", "échouée", "reprise")
LIEU_RESERVE = "Réserve"
MOTS_VIDES = {"grand", "grande", "petit", "petite", "pour", "avec", "dans", "manque", "chambre", "plait", "plaît", "vous"}


def _mots(texte: str) -> set[str]:
    return {m for m in re.findall(r"[a-zà-ÿœ]+", texte.lower().replace("’", "'")) if len(m) >= 4 and m not in MOTS_VIDES}


def _avec_article(objet: dict[str, Any]) -> str:
    article = objet.get("article", "")
    return f"{article}{objet['nom']}" if article.endswith("'") else f"{article} {objet['nom']}".strip()


def mots_partages(reserve: list[dict[str, Any]]) -> list[str]:
    """Les mots qui désignent plusieurs objets de la réserve (« coussin ») : les dire seuls donne une demande floue."""
    compte: dict[str, int] = {}
    for objet in reserve:
        for mot in _mots(objet["nom"]):
            compte[mot] = compte.get(mot, 0) + 1
    return sorted(mot for mot, n in compte.items() if n > 1)


def trouver(reserve: list[dict[str, Any]], texte: str) -> list[dict[str, Any]]:
    """Les objets de la réserve que la phrase peut désigner. Zéro, un, ou plusieurs (demande floue)."""
    phrase = " ".join(texte.lower().replace("’", "'").split())
    en_stock = [o for o in reserve if o.get("quantite", 0) > 0]
    exacts = [o for o in en_stock if o["nom"].lower() in phrase]
    if exacts:
        return exacts
    dits = _mots(phrase)
    return [o for o in en_stock if _mots(o["nom"]) & dits]


SEUIL_ECOUTE_DEMANDE = 0.6  # sous cette confiance d'écoute, rien n'est demandé au robot
# Ce qui fait d'une phrase une demande d'objet (français seulement : les objets de la réserve ont des noms français).
DEMANDE = r"\b(il manque|il me manque|manque|apporte|apportez|apporter|il faut|j'ai besoin|besoin d)"


def _simple_demande(texte: str) -> str:
    return " ".join(re.sub(r"[^a-zà-ÿœ0-9' ]", " ", texte.lower().replace("’", "'")).split())


def _dit_ce_choix(dite: str, choix: str, tous: list[str]) -> bool:
    """La réponse nomme-t-elle ce choix ? Par les mots qui le distinguent des autres (« grand », « nuque »)."""
    communs = set.intersection(*(set(_simple_demande(c).split()) for c in tous)) if len(tous) > 1 else set()
    propres = [m for m in _simple_demande(choix).split() if m not in communs and len(m) >= 4]
    return any(re.search(rf"\b{re.escape(m)}\b", dite) for m in propres)


class TableauDesTaches:
    def __init__(self, porte: PorteDeLecture, carnet: Carnet, listes: ListesDeSoin | None = None) -> None:
        self.porte, self.carnet, self.listes = porte, carnet, listes
        self._questions: dict[tuple[str, str], dict[str, Any]] = {}  # (badge, patient) → la question posée à la voix, qui attend
        self.aides: list[dict[str, Any]] = []  # les aides humaines de la séance (aide_humaine.py, avenant 2, K02)

    def noter_aide(self, sorte: str, qui: str, tache: str | None = None, detail: str = "", **plus: Any) -> dict[str, Any]:
        """Une aide humaine : notée ici, comptée dans l'essai en cours, écrite ensuite dans la boîte noire."""
        from . import aide_humaine

        aide = aide_humaine.signaler(sorte, qui, tache, detail, **plus)
        self.aides.append(aide)
        return aide

    # ------------------------------------------------------------------ lire
    def _taches(self) -> list[dict[str, Any]]:
        """Toutes les tâches, dans l'ordre où elles ont été créées. L'état d'une tâche est sa dernière ligne."""
        taches: dict[str, dict[str, Any]] = {}
        for ligne in self.carnet.lignes(GENRE):
            taches[ligne["donnees"]["id"]] = {**ligne["donnees"], "quand": ligne["quand"]}
        return list(taches.values())

    def tache(self, ident: str) -> dict[str, Any]:
        for t in self._taches():
            if t["id"] == ident:
                return t
        raise ValueError(f"tâche inconnue « {ident} »")

    def changer_etat(self, badge: Badge, ident: str, etat: str, **plus: Any) -> dict[str, Any]:
        """Une nouvelle ligne dans le carnet pour cette tâche, avec son nouvel état. Par un robot ou par l'équipe."""
        if etat not in ETATS:
            raise ValueError(f"état inconnu « {etat} »")
        if badge.role != "robot" and badge.role not in HUMAINS:
            self.porte.refuser(badge, "état d'une tâche", "seuls les robots et l'équipe changent l'état d'une tâche")
        tache = {cle: valeur for cle, valeur in self.tache(ident).items() if cle != "quand"}
        if etat == "livrée" and "SIMULÉ" in str({**tache, **plus}.get("etiquette", "")):
            self.porte.refuser(badge, "état d'une tâche", "un robot simulé ne livre rien : il n'existe que dans l'ordinateur")
        if tache.get("sorte") == "robot" and plus.get("sorte") == "humain":  # un humain reprend une tâche de robot
            self.noter_aide("main", qui=badge.id, tache=ident, detail=plus.get("pourquoi_un_humain") or "")
        if etat == "reprise" and tache.get("etat") != "reprise":
            from . import aide_humaine

            # aujourd'hui toutes les pannes sont provoquées : la reprise est prévue par le scénario, et c'est dit
            aide_humaine.signaler_reprise(prevue=bool(plus.get("panne")) or "provoqu" in str(plus.get("pourquoi", "")))
        return self._ecrire(badge, {**tache, **plus, "etat": etat})

    def constater(self, badge: Badge, ident: str) -> dict[str, Any]:
        """« Je l'ai vu » (avenant 2, K03) : une personne de l'équipe constate une livraison que le robot a confirmée.
        L'état du cahier ne change pas ; « constaté : oui » s'écrit à côté, avec le badge."""
        if badge.role not in HUMAINS:
            self.porte.refuser(badge, "constater une livraison", "seule une personne de l'équipe constate : pas le robot lui-même")
        tache = self.tache(ident)
        if tache["etat"] != "livrée" or tache.get("constate") != "pas encore":
            raise ChoixRefuse("cette tâche n'attend pas de constat (elle n'est pas « livrée », ou elle est déjà constatée)")
        return self.changer_etat(badge, ident, "livrée", constate="oui", constat=f"une personne l'a vu ({badge.id})")

    def c_est_bien_ca(self, badge: Badge, ident: str) -> dict[str, Any]:
        """H16 (réponse de Hiba à Q23 : B) : la personne qui a parlé confirme d'un doigt que la phrase entendue est la
        bonne. Une ligne de plus au carnet, « validée par un humain : oui » ; la tâche elle-même ne change pas."""
        if badge.role not in HUMAINS:
            self.porte.refuser(badge, "confirmer une phrase", "seule la personne qui a parlé confirme sa phrase")
        tache = {cle: valeur for cle, valeur in self.tache(ident).items() if cle != "quand"}
        if tache.get("qui_demande") != badge.id:  # d'abord : est-ce sa phrase ? (le refus est écrit au journal des accès)
            self.porte.refuser(badge, "confirmer une phrase", "seule la personne qui a parlé confirme sa phrase")
        if tache.get("phrase_confirmee") != "pas encore":
            raise ChoixRefuse("cette tâche n'attend pas de confirmation (elle n'est pas venue de la voix, ou c'est déjà fait)")
        return self._ecrire(badge, {**tache, "phrase_confirmee": "oui"}, valide=True)

    def tableau(self, badge: Badge) -> list[dict[str, Any]]:
        """Les tâches des personnes que mon badge me montre."""
        if badge.role not in HUMAINS:
            self.porte.refuser(badge, "tableau des tâches", "le tableau des tâches est pour les soignants, thérapeutes, médecins et l'accueil")
        visibles = {p["id"]: p for p in self.porte.patients(badge)}
        # Une tâche écrite pour un métier (la dictée du médecin) peut parler de santé : seuls ce métier et le médecin la lisent.
        return [{**t, "nom_du_patient": visibles[t["pour_qui"]]["nom"], "chambre": visibles[t["pour_qui"]]["chambre"]}
                for t in self._taches()
                if t["pour_qui"] in visibles and (not t.get("pour") or badge.role in (t["pour"], "médecin"))]

    def pour_le_robot(self, badge: Badge) -> list[dict[str, Any]]:
        """Ce qu'un robot voit : le lieu, la tâche, le prénom et la langue de la personne. Rien sur la santé."""
        if badge.role != "robot":
            self.porte.refuser(badge, "tâches du robot", "cette vue est pour les robots")
        vues = []
        for t in self._taches():
            if t["sorte"] != "robot":
                continue
            personne = self.porte.patient(badge, t["pour_qui"])
            vues.append({"id": t["id"], "quoi": t["quoi"], "de": t["de"], "ou": t["ou"], "pour_quand": t["pour_quand"],
                         "etat": t["etat"], "prenom": personne["prenom"], "langue": personne["langue"]})
        return vues

    # ------------------------------------------------------------------ demander
    def _ecrire(self, badge: Badge, tache: dict[str, Any], valide: bool | None = None) -> dict[str, Any]:
        """`valide` : None = un humain de l'équipe valide par son geste ; False = la phrase vient de la voix (H16)."""
        valide = badge.role in HUMAINS if valide is None else valide
        ligne = self.carnet.ecrire(badge, GENRE, tache, valide_par_un_humain=valide)
        return {**ligne["donnees"], "quand": ligne["quand"]}

    # ------------------------------------------------------------------ demander à la voix (T17), au niveau du texte reconnu
    def entendre(self, badge: Badge, patient: str, phrase: str, confiance: float = 1.0, liste: str | None = None,
                 numero: int | None = None) -> dict[str, Any]:
        """« Il manque un coussin » → « Lequel : le grand coussin, ou le coussin de nuque ? » → « le grand » → la tâche.
        Rend {"compris": "tâche" | "question" | "rien", "dit": …}. Rien ne part sur une phrase mal entendue. Une réponse
        qui ne choisit pas fait reposer la question ; « annule » l'oublie. Mêmes droits que le bouton."""
        if badge.role not in HUMAINS:
            self.porte.refuser(badge, "demande au robot", "seul un humain de l'équipe demande quelque chose au robot")
        phrase = " ".join(str(phrase).split())[:200]
        cle = (badge.id, patient)
        attente = self._questions.get(cle)
        if confiance < SEUIL_ECOUTE_DEMANDE:
            return {"compris": "rien", "dit": "Je n'ai pas bien entendu. Rien n'est demandé : répétez, ou demandez au doigt."}
        dite = _simple_demande(phrase)
        if attente is not None:  # une question attend : la phrase est une réponse
            if re.search(r"\b(annule|annuler|laisse|rien|non)\b", dite):
                del self._questions[cle]
                return {"compris": "rien", "dit": "Demande annulée. Rien n'est parti."}
            choisis = [c for c in attente["choix"] if _dit_ce_choix(dite, c, attente["choix"])]
            if len(choisis) != 1:
                return {"compris": "question", "dit": "Je n'ai pas compris. " + attente["dit"], "choix": attente["choix"]}
            del self._questions[cle]
            reponse = self.demander(badge, patient, attente["texte"], choix=choisis[0], liste=attente["liste"],
                                    numero=attente["numero"],
                                    plus={"par_la_voix": True, "entendu": f"{attente['texte']} → {phrase}"})
        else:
            if not re.search(DEMANDE, dite):
                return {"compris": "rien", "dit": "Je n'ai pas compris. Pour demander un objet, dites : « il manque … »."}
            reponse = self.demander(badge, patient, phrase, liste=liste, numero=numero,
                                    plus={"par_la_voix": True, "entendu": phrase})
        if reponse["genre"] == "question":
            self._questions[cle] = {"texte": phrase, "choix": reponse["choix"], "dit": reponse["phrase"], "liste": liste,
                                    "numero": numero}
            return {"compris": "question", "dit": reponse["phrase"], "choix": reponse["choix"]}
        return {"compris": "tâche", "dit": reponse["phrase"], "tache": reponse["tache"]}

    def pour_un_humain(self, badge: Badge, patient: str, quoi: str, pour: str, pour_quand: str = "dès que possible",
                       **plus: Any) -> dict[str, Any]:
        """Une tâche pour un humain d'un métier donné (« évaluer la marche demain », pour le thérapeute)."""
        if badge.role not in HUMAINS:
            self.porte.refuser(badge, "tâche pour un humain", "seul un humain de l'équipe crée une tâche pour un collègue")
        if pour not in HUMAINS:
            raise ValueError(f"métier inconnu « {pour} »")
        personne = self.porte.patient(badge, patient)
        return self._ecrire(badge, {"id": f"t{len(self._taches()) + 1}", "etat": ETATS[0], "qui_demande": badge.id,
                                    "pour_qui": patient, "ou": f"Chambre {personne['chambre']}", "pour_quand": pour_quand,
                                    "sorte": "humain", "quoi": quoi, "pour": pour, **plus})

    def pour_la_question_du_soir(self, badge: Badge, patient: str, ligne_du_carnet: int, pour_quand: str) -> dict[str, Any]:
        """H02 (réponse de Hiba à Q15 ; cahier 2.6) : une question du soir crée une tâche pour le médecin.
        Seulement pour la patiente elle-même. La tâche renvoie à la ligne du carnet : elle ne recopie pas la question.
        Écrite avec le badge de la patiente, donc « validée par un humain : non » : c'est le prototype qui la crée."""
        quoi = "tâche pour le médecin (question du soir)"
        if badge.role != "patient" or badge.patient != patient:
            self.porte.refuser(badge, quoi, "seule la question du soir du patient lui-même crée cette tâche")
        personne = self.porte.patient(badge, patient)
        return self._ecrire(badge, {"id": f"t{len(self._taches()) + 1}", "etat": ETATS[0], "qui_demande": badge.id,
                                    "pour_qui": patient, "ou": f"Chambre {personne['chambre']}", "pour_quand": pour_quand,
                                    "sorte": "humain", "pour": "médecin", "origine": "question du soir",
                                    "question": ligne_du_carnet,
                                    "quoi": f"Répondre à la question du soir (ligne {ligne_du_carnet} du carnet)"})

    def demander(self, badge: Badge, patient: str, texte: str, choix: str | None = None, liste: str | None = None,
                 numero: int | None = None, plus: dict[str, Any] | None = None) -> dict[str, Any]:
        """Une demande, dite ou tapée. Rend une question (demande floue) ou une tâche (pour un robot, ou pour un humain)."""
        if badge.role not in HUMAINS:
            self.porte.refuser(badge, "demande au robot", "seul un humain de l'équipe demande quelque chose au robot")
        personne = self.porte.patient(badge, patient)
        reserve = self.porte.reserve(badge)
        lieux = {lieu["nom"]: lieu for lieu in self.porte.lieux(badge)["lieux"]}
        texte = " ".join(str(texte).split())[:200]
        if liste is not None and self.listes is not None:
            self.listes.verifier_point(badge, patient, liste, numero)  # avant d'écrire quoi que ce soit

        candidats = trouver(reserve, texte)
        if choix is not None and choix in [o["nom"] for o in candidats]:
            candidats = [o for o in candidats if o["nom"] == choix]
        if len(candidats) > 1:
            noms = [_avec_article(o) for o in candidats]
            return {"genre": "question", "choix": [o["nom"] for o in candidats],
                    "phrase": "Lequel : " + ", ".join(noms[:-1]) + f", ou {noms[-1]} ?"}

        chambre = f"Chambre {personne['chambre']}"
        tache = {"id": f"t{len(self._taches()) + 1}", "etat": ETATS[0], "qui_demande": badge.id, "pour_qui": patient,
                 "ou": chambre, "pour_quand": "dès que possible", "demande": texte}
        if not candidats:
            tache.update(sorte="humain", quoi=texte, pourquoi_un_humain="objet absent de la réserve")
            phrase = "Je ne trouve pas cet objet dans la réserve. Je passe la demande à un humain."
        elif chambre not in lieux or LIEU_RESERVE not in lieux:
            tache.update(sorte="humain", quoi=candidats[0]["nom"], pourquoi_un_humain="lieu absent du plan du robot")
            phrase = f"La chambre {personne['chambre']} n'est pas sur le plan du robot. Je passe la demande à un humain."
        elif lieux[chambre]["etage"] != lieux[LIEU_RESERVE]["etage"]:
            tache.update(sorte="humain", quoi=candidats[0]["nom"], pourquoi_un_humain="les robots ne prennent pas l'ascenseur")
            phrase = "La réserve n'est pas au même étage. Je passe la demande à un humain."
        else:
            tache.update(sorte="robot", quoi=candidats[0]["nom"], de=LIEU_RESERVE)
            phrase = f"Demande notée : {_avec_article(candidats[0])}, pour la chambre {personne['chambre']}."
            if liste is not None and self.listes is not None:
                tache["point"] = {"liste": liste, "numero": numero}
        plus = dict(plus or {})
        a_la_voix = bool(plus.get("par_la_voix"))
        if a_la_voix:  # H16 (Q23 : B) : la machine a compris la phrase ; personne ne l'a encore confirmée
            plus["phrase_confirmee"] = "pas encore"
        tache = self._ecrire(badge, {**tache, **plus}, valide=False if a_la_voix else None)  # `plus` : demande à la voix…
        from . import aide_humaine

        aide_humaine.tache_de_robot()  # une demande faite au robot, qu'il la fasse ou non
        if tache["sorte"] == "humain":  # le robot ne peut pas : un humain le fera, et cela se compte
            self.noter_aide("main", qui=badge.id, tache=tache["id"], detail=tache.get("pourquoi_un_humain") or "")
        if tache.get("point"):
            self.listes.attendre_objet(badge, patient, liste, numero, tache["id"])
        return {"genre": "tâche", "tache": tache, "phrase": phrase}
