"""Le résumé du médecin, version simple : des règles, aucun modèle (cahier 5.7, tâche T08).

    resume = ResumeDuMedecin(porte, carnet, horloge)
    resume.preparer(badge_medecin)                 # « pendant la nuit » : un résumé par patient, noté au carnet
    resume.resume(badge_medecin, "p01")            # cinq lignes au plus, chacune avec ses sources
    resume.source(badge_medecin, "p01", "p01-d1")  # un doigt sur une source : elle s'ouvre
    resume.chercher(badge_medecin, "la lettre du médecin de Madame B.")

- Cinq lignes : pourquoi il est là ; ce qui a changé depuis hier ; ce qui attend une décision ; ses questions ;
  ce qui est prévu aujourd'hui.
- Chaque phrase porte la référence de sa source : un document, la fiche du séjour, le programme, une ligne du carnet.
  Une phrase sans source est retirée. S'il ne reste rien : « rien de nouveau ».
- Les chiffres : chaque suite de chiffres d'une phrase doit se trouver dans une de ses sources, sinon la phrase est
  retirée. Contrôle simple (voir garder_les_phrases_sures) : il ne regarde ni l'ordre, ni les mots.
  (Le verrou des chiffres de l'ossature, commun/chaine.py, recopie les vitesses, distances et forces dans un ordre au
  robot. Ici, même idée pour un texte : voir DECISIONS.md.)
- Deux sources pas d'accord : le résumé le dit et montre les deux. Il ne choisit pas.
- Tout est lu par la porte de lecture. Le résumé est pour le médecin (et pour l'assistant qui travaille pour lui).
- Le résumé ne dit rien de médical : il recopie, il ne conclut pas.
La version écrite par Apertus (T13) est dans resume_apertus.py ; celle-ci reste le secours.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from .carnet import Carnet
from .porte import AccesRefuse, Badge, PorteDeLecture

GENRE = "résumé du médecin"
VERSION = "règles simples, sans modèle"
MARQUE = "données inventées"
RIEN = "rien de nouveau"
POINTS = (("pourquoi", "Pourquoi il est là"), ("change", "Ce qui a changé depuis hier"),
          ("decision", "Ce qui attend une décision"), ("questions", "Ses questions"),
          ("aujourdhui", "Prévu aujourd'hui"))
NECESSAIRES = ("id", "nom", "chambre", "raison", "arrivee", "duree_jours", "sortie_jour", "programme", "documents")
MOTS_VIDES = {"dernier", "derniere", "derniers", "dernieres", "madame", "monsieur", "pour", "ouvre", "ouvrir",
              "montre", "montrer", "cherche", "chercher", "avec", "dans", "document", "documents"}


# ---------------------------------------------------------------------- pas de phrase sans source
def _nombres(texte: str) -> list[str]:
    return re.findall(r"\d+", texte)


def garder_les_phrases_sures(phrases: list[dict[str, Any]], textes: dict[str, str]) -> list[dict[str, Any]]:
    """Ne garde que les phrases dont toutes les sources sont connues, dont chaque suite de chiffres se trouve dans une
    de ces sources, et dont chaque « citation » y est écrite telle quelle.
    Limite connue : ce contrôle ne regarde ni l'ordre des chiffres, ni à quoi un chiffre se rapporte, ni les nombres en
    lettres, ni les mots. Il suffit pour des phrases faites par des règles ; pour un modèle (T13), il faudra plus."""
    gardees = []
    for phrase in phrases:
        sources = [ref for ref in phrase.get("sources") or [] if ref in textes]
        if not sources or len(sources) != len(phrase["sources"]):
            continue
        permis = {n for ref in sources for n in _nombres(textes[ref])}
        citees = all(any(c in textes[ref] for ref in sources) for c in phrase.get("citations") or ())
        if citees and all(n in permis for n in _nombres(phrase["texte"])):
            gardees.append(phrase)
    return gardees


def _simple(texte: str) -> str:
    """En minuscules, sans accents : pour comparer des mots."""
    sans = unicodedata.normalize("NFD", str(texte).lower().replace("’", "'"))
    return "".join(c for c in sans if unicodedata.category(c) != "Mn")


def _mots(texte: str) -> list[str]:
    return re.findall(r"[a-z]+", _simple(texte))


def _meme_mot(a: str, b: str) -> bool:
    return a == b or (min(len(a), len(b)) >= 5 and (a.startswith(b) or b.startswith(a)))


class ResumeDuMedecin:
    def __init__(self, porte: PorteDeLecture, carnet: Carnet, horloge=None) -> None:
        self.porte, self.carnet, self.horloge = porte, carnet, horloge
        self.muet = False  # vrai pendant la panne « le cerveau ne répond plus » (pannes.py)
        self.badge_du_cerveau: Badge | None = None  # H09 : le badge « assistant » ; sans lui, celui de badges.yaml
        self.cerveau = None  # T13 : un cerveau qui écrit les lignes (resume_apertus.py) ; sans lui, les règles simples
        self.montre = None  # pour les vérifications : une fausse montre (sinon, celle de l'ordinateur)
        self._prets: dict[str, tuple[Any, dict[str, Any]]] = {}  # patient → (ce qui a servi, le résumé)

    # ------------------------------------------------------------------ qui a le droit
    def _lire(self, badge: Badge, patient: str, quoi: str) -> dict[str, Any]:
        """La fiche du patient, par la porte. Refuse (et note) tout badge qui n'est pas celui d'un médecin."""
        personne = badge.pour if badge.role == "assistant" else badge
        if personne is None or personne.role != "médecin":
            self.porte.refuser(badge, quoi, "le résumé est pour le médecin")
        return self.porte.patient(badge, patient)

    def _jour(self) -> int:
        return self.horloge.jour() if self.horloge is not None else self.porte.jour()

    # ------------------------------------------------------------------ les sources
    def _lignes_du_carnet(self, patient: str) -> list[dict[str, Any]]:
        return [l for l in self.carnet.lignes() if l["genre"] != GENRE
                and patient in (l["donnees"].get("patient"), l["donnees"].get("pour_qui"))]

    @staticmethod
    def _texte_sejour(vue: dict[str, Any]) -> str:
        arrivee = vue["arrivee"]
        return (f"Séjour de {vue['nom']} : arrivée le jour {arrivee['jour']} à {arrivee['heure']} ; chambre {vue['chambre']} ; "
                f"pour {vue['duree_jours']} jours ; sortie prévue le jour {vue['sortie_jour']} ; "
                f"raison du séjour : {vue['raison']}.")

    @staticmethod
    def _texte_programme(vue: dict[str, Any]) -> str:
        lignes = [f"Jour {r['jour']}, {r['heure']} : {r['quoi']} ({r['lieu']})" for r in vue["programme"]]
        return "\n".join(lignes) or "Aucun rendez-vous."

    @staticmethod
    def _texte_carnet(ligne: dict[str, Any]) -> str:
        quand = ligne["quand"]
        moment = f"jour {quand['jour']}, {quand['heure']}" if quand.get("jour") is not None else "heure non notée"
        details = " ; ".join(f"{cle} : {valeur}" for cle, valeur in ligne["donnees"].items()
                             if valeur is not None and not isinstance(valeur, (dict, list)))
        valide = "oui" if ligne["valide_par_un_humain"] else "non"
        return (f"Ligne {ligne['numero']} du carnet — {moment} — écrite par {ligne['qui']} ({ligne['role']}) — "
                f"{ligne['genre']} — {details} — validée par un humain : {valide}.")

    def _sources(self, vue: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Toutes les sources possibles pour ce patient : référence → genre, titre, texte."""
        sources = {"sejour": {"genre": "fiche du séjour", "titre": "Fiche du séjour", "texte": self._texte_sejour(vue)},
                   "programme": {"genre": "programme", "titre": "Programme", "texte": self._texte_programme(vue)}}
        for d in vue["documents"]:
            notes = "".join(f"\nNoté dans le faux dossier pour ce document : {f['evenement']} — {f['date']}."
                            for f in d.get("faits") or ())
            sources[d["id"]] = {"genre": d["genre"], "titre": d.get("titre") or d["genre"], "texte": d["texte"] + notes,
                                "langue": d.get("langue")}
        for ligne in self._lignes_du_carnet(vue["id"]):
            sources[f"carnet-{ligne['numero']}"] = {"genre": "ligne du carnet", "titre": f"Carnet, ligne {ligne['numero']}",
                                                    "texte": self._texte_carnet(ligne)}
        return sources

    def source(self, badge: Badge, patient: str, ref: str) -> dict[str, Any]:
        """Ouvre une source. Elle doit appartenir à ce patient, et le badge doit avoir le droit de le voir."""
        quoi = f"source du résumé : {ref}"
        vue = self._lire(badge, patient, quoi)
        sources = self._sources(vue)
        if ref not in sources:
            self.porte.refuser(badge, quoi, "cette source n'est pas dans le dossier de cette personne")
        self.porte.noter(badge, quoi, [patient])  # le journal des accès dit quelle source a été ouverte
        return {"ref": ref, "patient": patient, "nom": vue["nom"], **sources[ref], "marque": MARQUE}

    # ------------------------------------------------------------------ les cinq lignes
    def _phrases(self, vue: dict[str, Any], jour: int) -> dict[str, list[dict[str, Any]]]:
        arrivee, carnet = vue["arrivee"], self._lignes_du_carnet(vue["id"])
        phrases: dict[str, list[dict[str, Any]]] = {point: [] for point, _ in POINTS}

        phrases["pourquoi"].append({"texte": f"Raison du séjour : {vue['raison']}. Séjour de "
                                             f"{vue['duree_jours']} jours, sortie prévue le jour {vue['sortie_jour']}.",
                                    "sources": ["sejour"]})

        if arrivee["jour"] >= jour - 1:
            phrases["change"].append({"texte": f"Arrivée le jour {arrivee['jour']} à {arrivee['heure']}, chambre {vue['chambre']}.",
                                      "sources": ["sejour"]})
        recentes = [l for l in carnet if l["quand"].get("jour") is None or l["quand"]["jour"] >= jour - 1]
        points: dict[tuple, dict[str, Any]] = {}
        taches: dict[str, dict[str, Any]] = {}
        for ligne in recentes:  # l'état d'une chose est sa dernière ligne
            d = ligne["donnees"]
            if ligne["genre"] == "point de liste":
                points[(d.get("liste"), d.get("numero"))] = ligne
            elif ligne["genre"] == "tâche":
                taches[str(d.get("id"))] = ligne
        groupes: dict[tuple, list[dict[str, Any]]] = {}
        for ligne in points.values():
            groupes.setdefault((ligne["donnees"].get("liste"), ligne["donnees"].get("etat")), []).append(ligne)
        for (liste, etat), lignes in groupes.items():
            noms = ", ".join(str(l["donnees"].get("nom") or f"point {l['donnees'].get('numero')}") for l in lignes)
            phrases["change"].append({"texte": f"Liste « {liste} », {etat} : {noms}.",
                                      "sources": [f"carnet-{l['numero']}" for l in lignes]})
        for ligne in taches.values():
            d = ligne["donnees"]
            phrases["change"].append({"texte": f"Demande : {d.get('quoi', '?')} — {d.get('etat', '?')}.",
                                      "sources": [f"carnet-{ligne['numero']}"]})

        phrases["decision"] += self._desaccords(vue)

        for ligne in carnet:
            if ligne["genre"].startswith("question") and ligne["donnees"].get("texte"):
                d = ligne["donnees"]  # T19 : la traduction d'abord, le texte d'origine à côté ; sinon « non traduite »
                langue = {"it": "l'italien", "de": "l'allemand", "en": "l'anglais", "pt": "le portugais"}.get(d.get("langue"))
                if d.get("traduction"):
                    texte = (f"« {d['traduction']} » (traduit de {langue or 'sa langue'} ; texte d'origine : « {d['texte']} »)")
                elif langue:
                    texte = f"« {d['texte']} » (non traduite ; langue : {langue})"
                else:
                    texte = f"« {d['texte']} »"
                phrases["questions"].append({"texte": texte, "sources": [f"carnet-{ligne['numero']}"]})

        du_jour = [r for r in vue["programme"] if r["jour"] == jour]
        if du_jour:
            phrases["aujourdhui"].append({"texte": " ; ".join(f"{r['heure']} {r['quoi']} ({r['lieu']})" for r in du_jour) + ".",
                                          "sources": ["programme"]})
        return phrases

    @staticmethod
    def _desaccords(vue: dict[str, Any]) -> list[dict[str, Any]]:
        """Deux documents qui ne donnent pas la même date pour le même événement (champ « faits » du faux dossier)."""
        trouves: list[dict[str, Any]] = []
        faits: dict[str, list[tuple[str, str]]] = {}
        for document in vue["documents"]:
            for fait in document.get("faits") or ():
                faits.setdefault(fait["evenement"], []).append((str(fait["date"]), document["id"]))
        for evenement, dits in faits.items():
            if len({date for date, _ in dits}) > 1:
                montre = " et ".join(f"« {date} »" for date, _ in dits)  # dans l'ordre des sources affichées
                refs = [ref for _, ref in dits]
                trouves.append({"texte": f"Deux sources ne sont pas d'accord sur « {evenement} » : {montre}. "
                                                     f"Le résumé ne choisit pas.", "citations": [date for date, _ in dits],
                                            "sources": refs, "desaccord": True,
                                            # si la phrase ci-dessus est retirée par le contrôle, celle-ci la remplace
                                            "secours": {"texte": f"Deux sources ne sont pas d'accord sur « {evenement} ». "
                                                                 f"Ouvrir les deux. Le résumé ne choisit pas.",
                                                        "sources": refs, "desaccord": True}})
        return trouves

    def _assistant(self, badge: Badge) -> Badge:
        """H09 (cahier 5.2) : le cerveau lit par la porte avec SON badge, au service de la personne. Jamais plus qu'elle."""
        if badge.role == "assistant":
            return badge
        from .porte import charger_badges

        return (self.badge_du_cerveau or charger_badges()["assistant"]).travaille_pour(badge)

    def _faire(self, vue: dict[str, Any], jour: int, badge: Badge | None = None) -> dict[str, Any]:
        sources = self._sources(vue)
        textes = {ref: s["texte"] for ref, s in sources.items()}
        lignes, retirees = [], []
        for (point, titre), brutes in zip(POINTS, self._phrases(vue, jour).values()):
            phrases = []
            for brute in brutes:  # un désaccord ne disparaît jamais sans rien dire : il a une phrase de secours, sans chiffre
                gardees = garder_les_phrases_sures([brute], textes) or garder_les_phrases_sures(
                    [brute["secours"]] if "secours" in brute else [], textes)
                if not gardees:  # comptée pour la fiche de vérité, et gardée pour la page « Moments »
                    retirees.append({"point": point, "texte": str(brute.get("texte", ""))[:200]})
                phrases += gardees
            refs = list(dict.fromkeys(ref for p in phrases for ref in p["sources"]))
            lignes.append({"point": point, "titre": titre, "texte": " ".join(p["texte"] for p in phrases) or RIEN,
                           "phrases": phrases, "desaccord": any(p.get("desaccord") for p in phrases),
                           "sources": [{"ref": ref, "genre": sources[ref]["genre"], "titre": sources[ref]["titre"]} for ref in refs]})
        resume = {"patient": vue["id"], "nom": vue["nom"], "chambre": vue["chambre"], "lignes": lignes, "version": VERSION, "retirees": len(retirees), "retirees_detail": retirees,
                  "marque": MARQUE}
        if self.cerveau is not None:  # T13 : le cerveau écrit, puis chaque ligne est contrôlée ; au pire, ce résumé-ci
            from .resume_apertus import reecrire

            if badge is None:
                return {**resume, "version": f"{VERSION} (le cerveau n'a pas de badge : il ne lit rien)"}
            assistant, patient = self._assistant(badge), vue["id"]
            pour_le_cerveau = self._sources(self.porte.patient(assistant, patient))  # lu par la porte, sous son badge : au journal

            def noter(titre: str, refs: list[str]) -> None:  # une ligne du journal par texte donné au cerveau
                self.porte.noter(assistant, f"texte donné au cerveau — résumé, ligne « {titre} » : {', '.join(refs)}", [patient])

            resume = reecrire(resume, pour_le_cerveau, self.cerveau, noter=noter, **({"montre": self.montre} if self.montre else {}))
        return resume

    def resume(self, badge: Badge, patient: str) -> dict[str, Any]:
        """Le résumé d'un patient. Préparé une fois ; refait seulement si une source a changé (ou si le jour a changé)."""
        return self._pour(badge, self._lire(badge, patient, "résumé du médecin"))

    def _pour(self, badge: Badge, vue: dict[str, Any]) -> dict[str, Any]:
        patient, jour = vue["id"], self._jour()
        servi = (jour, tuple(d["id"] for d in vue["documents"]), tuple(l["numero"] for l in self._lignes_du_carnet(patient)))
        pret = self._prets.get(patient)
        if self.muet:  # panne « le cerveau ne répond plus » : rien n'est refait, et on le dit
            if pret:
                return {**pret[1], "fige": "le cerveau ne répond plus : ce résumé a été préparé avant la panne, il peut être vieux"}
            return {"patient": patient, "nom": vue["nom"], "chambre": vue["chambre"], "lignes": [], "version": VERSION,
                    "marque": MARQUE, "retirees": 0, "prepare": {},
                    "fige": "le cerveau ne répond plus : aucun résumé n'était prêt avant la panne"}
        if pret and pret[0] == servi:
            return dict(pret[1])
        resume = self._faire(vue, jour, badge)
        etat = self.horloge.etat() if self.horloge is not None else {}
        resume["prepare"] = {"jour": etat.get("jour", jour), "heure": etat.get("heure"), "texte": etat.get("texte", f"Jour {jour}")}
        resume["refait"] = pret is not None
        self.carnet.ecrire(badge, GENRE, {"patient": patient, "version": resume["version"], "refait": resume["refait"],
                                          "retirees": resume.get("retirees_detail") or [],
                                          "lignes": [{"point": l["point"], "texte": l["texte"],
                                                      "sources": [s["ref"] for s in l["sources"]],
                                                      **({"ecrit_par": l["ecrit_par"]} if l.get("ecrit_par") else {})} for l in resume["lignes"]]},
                           valide_par_un_humain=False)
        self._prets[patient] = (servi, resume)
        return dict(resume)

    def tous(self, badge: Badge) -> list[dict[str, Any]]:
        """Un résumé par patient du médecin."""
        personne = badge.pour if badge.role == "assistant" else badge
        if personne is None or personne.role != "médecin":
            self.porte.refuser(badge, "résumés du médecin", "le résumé est pour le médecin")
        # On part de ce que la porte donne, tel quel. Une fiche où il manque de quoi faire un résumé n'en a pas.
        return [self._pour(badge, vue) for vue in self.porte.patients(badge) if all(cle in vue for cle in NECESSAIRES)]

    def preparer(self, badge: Badge) -> list[dict[str, Any]]:
        """« Pendant la nuit » de l'horloge : tous les résumés du médecin sont prêts avant la visite."""
        return self.tous(badge)

    # ------------------------------------------------------------------ la recherche d'un document
    def chercher(self, badge: Badge, phrase: str) -> dict[str, Any]:
        """« le dernier rapport de radiologie de Madame B. » → le bon document, parmi les patients de ce médecin.
        Par des règles : le nom de la personne, puis les mots du genre et du titre. Rien ne s'ouvre si ce n'est pas sûr."""
        personne = badge.pour if badge.role == "assistant" else badge
        if personne is None or personne.role != "médecin":
            self.porte.refuser(badge, "recherche d'un document", "la recherche de documents est pour le médecin")
        phrase = " ".join(str(phrase).split())[:200]
        simple, mots = " ".join(_mots(phrase)), _mots(phrase)
        trouves = []
        for p in self.porte.patients(badge):
            morceaux = _mots(p["nom"])  # « madame », « giulia », « b »
            civilite, prenom, initiale = morceaux[0], morceaux[1], morceaux[-1]
            if prenom in mots or re.search(rf"\b{civilite} {initiale}\b", simple):
                trouves.append((p, {civilite, prenom}))
        if not trouves:
            return {"trouve": False, "marque": MARQUE, "dit": "Je ne trouve pas cette personne parmi vos patients."}
        if len(trouves) > 1:
            noms = ", ".join(p["nom"] for p, _ in trouves)
            return {"trouve": False, "marque": MARQUE, "dit": f"Plusieurs personnes correspondent : {noms}. Laquelle ?"}
        patient, du_nom = trouves[0]
        cherches = [m for m in mots if len(m) >= 4 and m not in MOTS_VIDES and m not in du_nom]
        notes = []
        for d in patient["documents"]:
            du_document = _mots(f"{d['genre']} {d.get('titre', '')}")
            notes.append((sum(any(_meme_mot(m, autre) for autre in du_document) for m in cherches), d))
        meilleure = max((note for note, _ in notes), default=0)
        candidats = [d for note, d in notes if note == meilleure and note > 0]
        if not candidats:
            a_elle = ", ".join(d["genre"] for d in patient["documents"]) or "aucun document"
            return {"trouve": False, "marque": MARQUE, "patient": patient["id"],
                    "dit": f"Je ne trouve pas ce document pour {patient['nom']}. Dans son dossier : {a_elle}."}
        if len(candidats) > 1:  # les documents n'ont pas de date : on ne devine pas lequel est « le dernier »
            return {"trouve": False, "marque": MARQUE, "patient": patient["id"],
                    "candidats": [{"ref": d["id"], "genre": d["genre"], "titre": d.get("titre", "")} for d in candidats],
                    "dit": f"Plusieurs documents correspondent pour {patient['nom']}. Lequel ?"}
        document = self.source(badge, patient["id"], candidats[0]["id"])
        return {"trouve": True, "marque": MARQUE, "patient": patient["id"], "ref": document["ref"], "document": document,
                "dit": f"{document['genre']} de {patient['nom']}"}


__all__ = ["AccesRefuse", "GENRE", "POINTS", "RIEN", "ResumeDuMedecin", "VERSION", "garder_les_phrases_sures"]
