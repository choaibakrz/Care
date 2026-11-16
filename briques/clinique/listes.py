"""Les listes de soin : cocher, « je sors », la fin de poste, les comptes de la direction (cahier 5.5).

    listes = ListesDeSoin(porte, carnet)
    listes.cocher(badge, "p01", "installation", 3)          # au doigt
    listes.je_sors(badge, "p01")["phrase"]                  # « Il reste un point : la sonnette. »
    listes.fin_de_poste(badge)                              # tout ce qui reste ; pour chaque point, trois choix
    listes.choisir(badge, "p01", "installation", 5, "le reporter", raison="…")
    listes.comptes(badge_direction)                         # des nombres par étage, jamais par personne

- Les listes viennent des données, lues par la porte. Aucun point n'est inventé : un numéro inconnu est refusé.
- Rien ne s'écrit dans le faux dossier : chaque geste ajoute une ligne au carnet (qui, quand, validé par un humain).
- Seul un humain coche, et seulement les points de son métier, chez les personnes que son badge lui montre.
- Pas d'alarme, pas de reproche : « Il reste un point : la sonnette. »
- EXEMPLES INVENTÉS, NON MÉDICAUX : les listes sont à remplacer par celles de la clinique.
La voix (T16), l'objet qui manque (T07) et les boutons de l'écran (T06b) viennent après.
"""
from __future__ import annotations

import re
import unicodedata
import yaml
from pathlib import Path

from typing import Any

from .carnet import Carnet
from .porte import Badge, PorteDeLecture

GENRE = "point de liste"
A_FAIRE, FAIT, REPORTE, RELEVE, EN_ATTENTE = "à faire", "fait", "reporté", "passé à la relève", "en attente d'un objet"
CHOIX = ("le faire", "le reporter", "le passer à la relève")  # les trois choix de la fin de poste
HUMAINS = ("soignant", "thérapeute", "médecin", "accueil")


SEUIL_ECOUTE = 0.6  # sous cette confiance d'écoute, une phrase ne coche rien
NEGATIONS = ("pas", "non", "nicht", "kein", "keine", "not", "no",  # « pas fait » : on ne coche pas
             "jamais", "nie", "niemals", "never")  # relecture de la tranche 2 : « jamais faite » cochait le point
FICHIER_MOTS = Path(__file__).resolve().parent / "mots_des_points.yaml"


def _simple_voix(texte: str) -> str:
    """Minuscules, sans accents, sans ponctuation : « La Sonnette, c'est FAIT. » → « la sonnette c'est fait »."""
    sans = unicodedata.normalize("NFD", str(texte).lower().replace("’", "'"))
    sans = "".join(c for c in sans if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^a-z0-9' ]", " ", sans).split())


def _sans_article(mot: str) -> str:
    return re.sub(r"^(le |la |les |l')", "", mot)


def _contient(phrase: str, mots) -> bool:
    """Un de ces mots (ou groupes de mots) est-il dans la phrase, en mots entiers ?"""
    return any(m and re.search(rf"(?<![a-z0-9']){re.escape(m)}(?![a-z0-9])", phrase) for m in mots)


_MOTS: dict[str, Any] = {}


def _mots_a_la_voix() -> dict[str, Any]:
    if not _MOTS:
        donnees = yaml.safe_load(FICHIER_MOTS.read_text(encoding="utf-8"))
        if donnees.get("marque") != "inventé":
            raise ValueError("mots_des_points.yaml : la marque « inventé » manque")
        _MOTS.update(donnees)
    return _MOTS


class ChoixRefuse(ValueError):
    """Le geste demandé n'est pas possible. Le message dit pourquoi, en mots simples."""


class ListesDeSoin:
    def __init__(self, porte: PorteDeLecture, carnet: Carnet) -> None:
        self.porte, self.carnet = porte, carnet

    # ------------------------------------------------------------------ lire
    def _etats(self) -> dict[tuple[str, str, int], dict[str, Any]]:
        """L'état de chaque point touché : sa dernière ligne dans le carnet."""
        etats = {}
        for ligne in self.carnet.lignes(GENRE):
            d = ligne["donnees"]
            etats[(d["patient"], d["liste"], d["numero"])] = ligne
        return etats

    def _lire(self, badge: Badge, patient: str, liste: str) -> tuple[dict[str, Any], dict[str, Any]]:
        """La personne et la liste, par la porte. La porte refuse (et note) si le badge n'y a pas droit."""
        if badge.role == "assistant":
            self.porte.refuser(badge, f"liste de soin : {liste}", "seul un humain ouvre et coche une liste de soin")
        personne = self.porte.patient(badge, patient)
        modele = self.porte.liste_de_soin(badge, liste)
        if liste not in personne.get("listes", ()):
            raise ChoixRefuse("cette liste n'est pas prévue pour cette personne, ou ce badge ne voit pas ses listes")
        return personne, modele

    @staticmethod
    def _point(personne: dict[str, Any], modele: dict[str, Any], point: dict[str, Any], ligne: dict[str, Any] | None) -> dict[str, Any]:
        vue = {"patient": personne["id"], "nom_du_patient": personne["nom"], "chambre": personne["chambre"],
               "liste": modele["id"], "titre": modele["titre"], "numero": point["numero"], "nom": point["nom"],
               "texte": point["texte"], "pour": point["pour"], "etat": A_FAIRE}
        if ligne:
            d = ligne["donnees"]
            vue.update(etat=d["etat"], quand=ligne["quand"], par=ligne["qui"], comment=d.get("comment"))
            for cle in ("raison", "tache"):
                if d.get(cle):
                    vue[cle] = d[cle]
        return vue

    def liste(self, badge: Badge, patient: str, liste: str) -> dict[str, Any]:
        """Une liste pour une personne, avec l'état de chaque point."""
        personne, modele = self._lire(badge, patient, liste)
        etats = self._etats()
        points = [self._point(personne, modele, p, etats.get((patient, liste, p["numero"]))) for p in modele["points"]]
        return {"marque": modele["marque"], "patient": patient, "liste": liste, "titre": modele["titre"],
                "commencee": any((patient, liste, p["numero"]) in etats for p in modele["points"]), "points": points}

    # ------------------------------------------------------------------ écrire dans le carnet
    def verifier_point(self, badge: Badge, patient: str, liste: str, numero: int | None):
        """Ce badge peut-il toucher ce point ? Rend la personne, la liste et le point, ou refuse en disant pourquoi."""
        personne, modele = self._lire(badge, patient, liste)
        point = next((p for p in modele["points"] if p["numero"] == numero), None)
        if point is None:
            raise ChoixRefuse(f"la liste « {modele['titre']} » n'a pas de point numéro {numero}")
        if badge.role not in HUMAINS or badge.role not in point["pour"]:
            raise ChoixRefuse(f"ce point est pour : {point['pour']}")
        return personne, modele, point

    def attendre_objet(self, badge: Badge, patient: str, liste: str, numero: int, tache: str) -> dict[str, Any]:
        """Un objet manque : le point attend la livraison de cette tâche (cahier 5.5)."""
        return self._noter(badge, patient, liste, numero, EN_ATTENTE, tache=tache)

    def livraison(self, badge: Badge, tache: dict[str, Any]) -> dict[str, Any] | None:
        """Le robot a livré : le point qui attendait cet objet se coche, et le carnet note que c'est la livraison."""
        if badge.role != "robot" or tache.get("etat") != "livrée" or not tache.get("point"):
            raise ChoixRefuse("seule une tâche livrée par un robot coche un point en attente")
        cle = (tache["pour_qui"], tache["point"]["liste"], tache["point"]["numero"])
        actuelle = self._etats().get(cle)
        if not actuelle or actuelle["donnees"]["etat"] != EN_ATTENTE or actuelle["donnees"].get("tache") != tache["id"]:
            return None  # le point n'attend plus cette tâche (déjà fait à la main, par exemple) : on ne touche à rien
        donnees = {**actuelle["donnees"], "etat": FAIT, "comment": "livraison du robot"}
        return self.carnet.ecrire(badge, GENRE, donnees, valide_par_un_humain=False)

    def _noter(self, badge: Badge, patient: str, liste: str, numero: int, etat: str, raison: str | None = None,
               comment: str = "au doigt", tache: str | None = None, hors_ligne_a: str | None = None,
               entendu: str | None = None) -> dict[str, Any]:
        personne, modele, point = self.verifier_point(badge, patient, liste, numero)
        actuelle = self._etats().get((patient, liste, numero))
        if actuelle and actuelle["donnees"]["etat"] == etat == FAIT:
            return self._point(personne, modele, point, actuelle)  # déjà coché : on ne compte pas deux fois
        donnees = {"patient": patient, "liste": liste, "numero": numero, "nom": point["nom"], "etat": etat,
                   "comment": comment, "etage": personne.get("etage")}
        if raison:
            donnees["raison"] = raison
        if tache:
            donnees["tache"] = tache
        if entendu is not None:  # cochée à la voix : la phrase entendue est gardée
            donnees["entendu"] = entendu
        if hors_ligne_a:  # cochée sur une tablette sans lien, renvoyée au retour : l'heure de la tablette est gardée
            donnees["hors_ligne_a"] = hors_ligne_a
        return self._point(personne, modele, point, self.carnet.ecrire(badge, GENRE, donnees, valide_par_un_humain=True))

    def cocher(self, badge: Badge, patient: str, liste: str, numero: int, hors_ligne_a: str | None = None) -> dict[str, Any]:
        """Cocher un point au doigt. `hors_ligne_a` : l'heure de la tablette, si la coche a été faite sans lien."""
        if hors_ligne_a:
            return self._noter(badge, patient, liste, numero, FAIT, comment="au doigt, hors ligne", hors_ligne_a=hors_ligne_a)
        return self._noter(badge, patient, liste, numero, FAIT)

    # ------------------------------------------------------------------ l'accueil et la liste de sortie (H17, Q24 : B)
    def sorties_pour_l_accueil(self, badge: Badge) -> list[dict[str, Any]]:
        """Les trois points de l'accueil, pour chaque personne qui a une liste de sortie, avec leur état."""
        etats = self._etats()
        vues = self.porte.points_de_sortie_pour_l_accueil(badge)  # la porte refuse tout autre badge, et le note
        for v in vues:
            for pt in v["points"]:
                ligne = etats.get((v["id"], v["liste"], pt["numero"]))
                pt["etat"] = ligne["donnees"]["etat"] if ligne else A_FAIRE
                if ligne:
                    pt.update(par=ligne["qui"], quand=ligne["quand"])
        return vues

    def cocher_pour_l_accueil(self, badge: Badge, patient: str, numero: int) -> dict[str, Any]:
        """L'accueil coche l'un de SES trois points (et rien d'autre). La coche va au carnet, comme une coche au doigt."""
        if badge.role != "accueil":  # un humain de l'accueil lui-même : pas un assistant à son service
            self.porte.refuser(badge, "liste de soin : sortie", "seul un humain de l'accueil coche ses points de sortie")
        vues = {v["id"]: v for v in self.sorties_pour_l_accueil(badge)}
        if patient not in vues:
            raise ChoixRefuse("cette personne n'a pas de liste de sortie")
        v = vues[patient]
        point = next((pt for pt in v["points"] if pt["numero"] == numero), None)
        if point is None:
            raise ChoixRefuse("ce point n'est pas pour l'accueil : il est pour le médecin ou le soignant")
        if point["etat"] == FAIT:
            return point  # déjà coché : on ne compte pas deux fois
        donnees = {"patient": patient, "liste": v["liste"], "numero": numero, "nom": point["nom"], "etat": FAIT,
                   "comment": "au doigt, à l'accueil", "etage": v.get("etage")}
        ligne = self.carnet.ecrire(badge, GENRE, donnees, valide_par_un_humain=True)
        return {**point, "etat": FAIT, "par": ligne["qui"], "quand": ligne["quand"]}

    # ------------------------------------------------------------------ cocher à la voix (T16), au niveau du texte reconnu
    def entendre(self, badge: Badge, patient: str, liste: str, phrase: str, confiance: float = 1.0) -> dict[str, Any]:
        """« Sonnette, fait » : coche le point nommé, en français, allemand, italien ou anglais.
        - sans le mot « fait », ou si la phrase dit « pas » : rien n'est coché ;
        - si la phrase peut désigner deux points : une question, rien n'est coché (le prototype ne devine pas) ;
        - si la phrase a été mal entendue (confiance basse) : rien n'est coché, on passe au doigt.
        Rend {"compris": "coche" | "question" | "rien", "dit": …}. La voix ne donne aucun droit de plus que le doigt."""
        personne, modele = self._lire(badge, patient, liste)
        if badge.role not in HUMAINS:
            raise ChoixRefuse("seul un humain de l'équipe coche une liste de soin")
        phrase = " ".join(str(phrase).split())[:200]
        if confiance < SEUIL_ECOUTE:
            return {"compris": "rien", "dit": "Je n'ai pas bien entendu. Rien n'est coché : répétez, ou cochez au doigt."}
        mots = _mots_a_la_voix()
        dite = _simple_voix(phrase)
        if phrase.rstrip().endswith("?") or _contient(dite, NEGATIONS):  # une question ne coche rien non plus
            return {"compris": "rien", "dit": "Je n'ai rien coché. Pour cocher un point, dites son nom, puis « fait »."}
        trouves = []
        for point in modele["points"]:
            connus = [point["nom"], *point.get("mots", ()),
                      *(m for ms in (mots["listes"].get(liste, {}).get(point["numero"], {}) or {}).values() for m in ms)]
            if _contient(dite, [_sans_article(_simple_voix(m)) for m in connus]):
                trouves.append(point)
        if not _contient(dite, [_simple_voix(m) for ms in mots["fait"].values() for m in ms]):
            return {"compris": "rien", "dit": "Je n'ai pas compris. Dites le nom du point, puis « fait »."}
        if not trouves:
            return {"compris": "rien", "dit": f"Je ne trouve pas ce point dans la liste « {modele['titre']} ». Rien n'est coché."}
        if len(trouves) > 1:
            noms = [p["nom"] for p in trouves]
            return {"compris": "question", "dit": "Lequel : " + ", ".join(noms[:-1]) + f", ou {noms[-1]} ?",
                    "choix": [{"numero": p["numero"], "nom": p["nom"]} for p in trouves]}
        point = trouves[0]
        actuelle = self._etats().get((patient, liste, point["numero"]))
        deja = bool(actuelle and actuelle["donnees"]["etat"] == FAIT)
        vue = self._noter(badge, patient, liste, point["numero"], FAIT, comment="à la voix", entendu=phrase)
        return {"compris": "coche", "point": vue,
                "dit": f"{point['nom'].capitalize()} : déjà coché." if deja else f"Coché : {point['nom']}."}

    def choisir(self, badge: Badge, patient: str, liste: str, numero: int, choix: str, raison: str | None = None) -> dict[str, Any]:
        """La fin de poste : le faire, le reporter (avec une raison), ou le passer à la relève."""
        if choix not in CHOIX:
            raise ChoixRefuse("trois choix seulement : " + ", ".join(CHOIX))
        if choix == "le faire":
            return self._noter(badge, patient, liste, numero, FAIT)
        if choix == "le passer à la relève":
            return self._noter(badge, patient, liste, numero, RELEVE)
        raison = (raison or "").strip()
        if not raison:
            raise ChoixRefuse("pour reporter un point, il faut une raison")
        return self._noter(badge, patient, liste, numero, REPORTE, raison=raison[:200])

    # ------------------------------------------------------------------ « je sors » et la fin de poste
    def _restants(self, badge: Badge, personne: dict[str, Any], commencees_seulement: bool,
                  voulus: tuple[str, ...] = (A_FAIRE, EN_ATTENTE), modeles: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Les points de mon métier qui sont dans un des états voulus. `modeles` évite de relire dix fois la même liste."""
        etats, restants, modeles = self._etats(), [], {} if modeles is None else modeles
        for identifiant in personne.get("listes", ()):
            if identifiant not in modeles:
                modeles[identifiant] = self.porte.liste_de_soin(badge, identifiant)
            modele = modeles[identifiant]
            commencee = any((personne["id"], identifiant, p["numero"]) in etats for p in modele["points"])
            if commencees_seulement and not commencee:
                continue
            for p in modele["points"]:
                vue = self._point(personne, modele, p, etats.get((personne["id"], identifiant, p["numero"])))
                if vue["etat"] in voulus and badge.role in p["pour"]:
                    restants.append({**vue, "liste_commencee": commencee, "choix": list(CHOIX)})
        return restants

    def je_sors(self, badge: Badge, patient: str) -> dict[str, Any]:
        """En sortant de la chambre : ce qui reste dans les listes commencées. Doucement, sans reproche."""
        if badge.role == "assistant":
            self.porte.refuser(badge, "je sors", "seul un humain ouvre et coche une liste de soin")
        personne = self.porte.patient(badge, patient)
        etats = self._etats()
        commencees = [l for l in personne.get("listes", ()) if any(cle[:2] == (patient, l) for cle in etats)]
        restent = [r for r in self._restants(badge, personne, commencees_seulement=True) if r["etat"] == A_FAIRE]
        if not commencees:
            phrase = ""
        elif not restent:
            phrase = "Tout est fait."
        elif len(restent) == 1:
            phrase = f"Il reste un point : {restent[0]['nom']}."
        else:
            phrase = f"Il reste {len(restent)} points : " + ", ".join(r["nom"] for r in restent) + "."
        return {"patient": patient, "phrase": phrase, "restent": restent, "listes_commencees": commencees}

    def fin_de_poste(self, badge: Badge) -> list[dict[str, Any]]:
        """Tout ce qui reste pour mon métier, chez les personnes que mon badge me montre. Trois choix par point."""
        if badge.role not in HUMAINS:
            self.porte.refuser(badge, "fin de poste", "la fin de poste est pour les soignants, thérapeutes, médecins et l'accueil")
        restants, modeles = [], {}
        for personne in self.porte.patients(badge):
            restants += self._restants(badge, personne, commencees_seulement=False, modeles=modeles)
        return restants

    def prise_de_poste(self, badge: Badge) -> dict[str, Any]:
        """Le point de prise de poste : mes patients, ce qui a changé, ce qui reste, ce que le poste d'avant n'a pas fini."""
        if badge.role not in HUMAINS:
            self.porte.refuser(badge, "prise de poste", "le point de prise de poste est pour les soignants, thérapeutes, médecins et l'accueil")
        patients, jour, modeles = self.porte.patients(badge), self.porte.jour(), {}
        change, reste, avant = [], 0, []
        for p in patients:
            if (p.get("arrivee") or {}).get("jour") == jour:
                change.append({"patient": p["id"], "nom": p["nom"], "chambre": p["chambre"], "quoi": "arrive aujourd'hui"})
            if p.get("sortie_jour") == jour + 1:
                change.append({"patient": p["id"], "nom": p["nom"], "chambre": p["chambre"], "quoi": "sort demain"})
            reste += len(self._restants(badge, p, commencees_seulement=False, modeles=modeles))
            avant += self._restants(badge, p, commencees_seulement=False, voulus=(REPORTE, RELEVE), modeles=modeles)
        return {"marque": "données inventées", "jour": jour, "mes_patients": len(patients), "ce_qui_a_change": change,
                "ce_qui_reste": reste, "du_poste_d_avant": avant}

    # ------------------------------------------------------------------ la direction
    def comptes(self, badge: Badge) -> dict[str, Any]:
        """Pour la direction : des nombres par étage. Aucun nom, aucun numéro de dossier, aucun soignant, aucune raison."""
        if badge.role != "direction":
            self.porte.refuser(badge, "comptes des listes de soin", "les comptes par étage sont pour la direction")
        cles = {FAIT: "faits", REPORTE: "reportes", RELEVE: "passes_a_la_releve", EN_ATTENTE: "en_attente_d_un_objet"}
        etages: dict[Any, dict[str, Any]] = {}
        for ligne in self._etats().values():
            d = ligne["donnees"]
            e = etages.setdefault(d.get("etage"), {"etage": d.get("etage"), **{cle: 0 for cle in cles.values()}})
            if d["etat"] in cles:
                e[cles[d["etat"]]] += 1
        self.porte.comptes(badge)  # la lecture de la direction passe par la porte, et reste au journal des accès
        return {"marque": "données inventées", "note": "points de listes touchés, par étage ; jamais par personne",
                "etages": sorted(etages.values(), key=lambda e: (e["etage"] is None, e["etage"] or 0))}


# ---------------------------------------------------------------------- la grande répétition
def etape_7():
    """Étape 7 : cinq points cochés, puis « Il reste un point : la sonnette. » À travers les vraies pièces.
    Dans un essai compté, le point oublié change : la phrase doit nommer ce point-là."""
    from .horloge import HorlogeDeDemonstration
    from .porte import JournalDesAcces, charger_badges
    from .repetition import Resultat, changement

    oublie = changement("point_oublie", 3)
    horloge = HorlogeDeDemonstration()
    listes = ListesDeSoin(PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), Carnet(horloge=horloge))
    soignant = charger_badges()["soignant-etage-2"]
    points = {p["numero"]: p["nom"] for p in listes.liste(soignant, "p01", "installation")["points"]}
    for numero in points:
        if numero != oublie:
            listes.cocher(soignant, "p01", "installation", numero)
    phrase = listes.je_sors(soignant, "p01")["phrase"]
    attendue = f"Il reste un point : {points.get(oublie, '?')}."
    return Resultat(phrase == attendue, "SIMULÉ",
                    f"{len(points) - 1} coches faites par le programme, pas par une soignante, sans écran ; point oublié : "
                    f"le {oublie} ; la pièce des listes répond : « {phrase} »"
                    + ("" if phrase == attendue else f" ; attendu : « {attendue} »"))
