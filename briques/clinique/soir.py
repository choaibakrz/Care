"""Le soir et la dictée, version simple et tapée (cahier 4.2, 5.6, 5.7, 6.1 ; tâche T11b).

    soir = LeSoir(porte, carnet, horloge, taches)
    soir.invitation(badge_patiente)            → à 19 h : « Ha domande per il medico domani? », dans sa langue
    soir.poser(badge_patiente, "Mia figlia può venire domenica?")
        → une ligne « question du soir » au carnet ; le prototype dit qu'il transmet, et rien d'autre
    soir.dicter(badge_medecin, "p01", "Physio, évaluer la marche demain.")
        → un brouillon (« brouillon, pas dans le dossier ») et une tâche pour un humain : le thérapeute

- Le prototype ne répond à AUCUNE question de la patiente. Il transmet. Pas de médecine (cahier 2.6).
- Chaque question crée aussi une tâche pour le médecin (H02) : elle renvoie à la ligne du carnet, sans recopier la question.
- La question reste dans la langue de la patiente, telle qu'elle l'a tapée. Depuis T19 : les deux questions du scénario portent une traduction fixe ; toute autre arrive « non traduite ».
- Le médecin lit les questions dans son résumé (resume.py lit les lignes « question… » du carnet).
- La dictée est tapée, pas dite (la voix : tâche T18). Le premier mot dit pour qui : « Physio, … » → le thérapeute.
  Un premier mot inconnu : la tâche va à l'équipe de soin, et le prototype le dit.
- Tout s'écrit dans le carnet. Rien n'entre au faux dossier.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml
from typing import Any

from . import horloge as horloge_clinique
from .carnet import Carnet
from .listes import ChoixRefuse
from .porte import Badge, PorteDeLecture
from .taches import TableauDesTaches

GENRE_QUESTION = "question du soir"
GENRE_BROUILLON = "brouillon"
MENTION_BROUILLON = "brouillon, pas dans le dossier"
LONGUEUR_MAX = 200
SEUIL_ECOUTE_DICTEE = 0.6  # sous cette confiance d'écoute, une dictée n'écrit rien

# Les phrases de l'écran de la patiente. Allemand, italien, anglais : écrits par l'agent, pas relus.
PHRASES: dict[str, dict[str, str]] = {
    "fr": {"invitation": "Avez-vous des questions pour le médecin demain ?", "bouton": "Écrire une question",
           "envoyer": "Envoyer au médecin", "deja": "Vos questions pour le médecin",
           "transmis": "Votre question est transmise au médecin. Je ne réponds pas aux questions : le médecin le fera."},
    "it": {"invitation": "Ha domande per il medico domani?", "bouton": "Scrivere una domanda",
           "envoyer": "Inviare al medico", "deja": "Le sue domande per il medico",
           "transmis": "La sua domanda è trasmessa al medico. Non rispondo alle domande: lo farà il medico."},
    "de": {"invitation": "Haben Sie Fragen an den Arzt für morgen?", "bouton": "Eine Frage schreiben",
           "envoyer": "An den Arzt senden", "deja": "Ihre Fragen an den Arzt",
           "transmis": "Ihre Frage wird dem Arzt weitergegeben. Ich beantworte keine Fragen: Das macht der Arzt."},
    "en": {"invitation": "Do you have questions for the doctor tomorrow?", "bouton": "Write a question",
           "envoyer": "Send to the doctor", "deja": "Your questions for the doctor",
           "transmis": "Your question is passed on to the doctor. I do not answer questions: the doctor will."},
}

# Le premier mot d'une dictée dit pour qui est la tâche. Liste courte, inventée pour la démonstration.
DESTINATAIRES = {"physio": "thérapeute", "physiothérapie": "thérapeute", "physiotherapie": "thérapeute",
                 "thérapeute": "thérapeute", "therapeute": "thérapeute", "ergo": "thérapeute",
                 "soins": "soignant", "soignant": "soignant"}
# Jamais l'accueil : une phrase libre du médecin peut parler de santé, et l'accueil ne lit rien sur la santé.
PAR_DEFAUT = "soignant"


NOMS_DES_LANGUES = {"it": "l'italien", "de": "l'allemand", "en": "l'anglais", "fr": "le français", "pt": "le portugais"}
FICHIER_TRADUCTIONS = Path(__file__).resolve().parent / "traductions_scenario.yaml"


def _cle(texte: str) -> str:
    return re.sub(r"[^a-zà-ÿ0-9 ]", " ", " ".join(str(texte).lower().split())).replace("  ", " ").strip()


class TraducteurDuScenario:
    """Pas un traducteur : les traductions FIXES des deux questions du scénario (traductions_scenario.yaml).
    Pour toute autre phrase, il rend None : la question reste « non traduite ». Un vrai cerveau (Apertus) aura la même
    porte : `traduire(texte, de, vers)`."""

    nom = "traduction fixe du scénario (un fichier, pas un modèle)"

    def __init__(self) -> None:
        donnees = yaml.safe_load(FICHIER_TRADUCTIONS.read_text(encoding="utf-8"))
        if donnees.get("marque") != "inventé":
            raise ValueError("traductions_scenario.yaml : la marque « inventé » manque")
        self._paires = {(de, vers): {_cle(k): v for k, v in phrases.items()}
                        for de, cibles in donnees.items() if isinstance(cibles, dict) for vers, phrases in cibles.items()}

    def traduire(self, texte: str, de: str, vers: str) -> str | None:
        return self._paires.get((de, vers), {}).get(_cle(texte))


def phrases(langue: str) -> dict[str, str]:
    return PHRASES.get(langue, PHRASES["fr"])


def _propre(texte: Any) -> str:
    return " ".join(str(texte).split())[:LONGUEUR_MAX]


class LeSoir:
    def __init__(self, porte: PorteDeLecture, carnet: Carnet, horloge, taches: TableauDesTaches,
                 badges: dict[str, Badge] | None = None) -> None:
        self.porte, self.carnet, self.horloge, self.taches = porte, carnet, horloge, taches
        self.badges = badges or {}
        self.traducteur: Any = TraducteurDuScenario()  # de quoi traduire une question pour le médecin (T19)
        self.langue_du_medecin = "fr"

    def _quelqu_un_la_verra(self, metier: str, personne: dict[str, Any]) -> bool:
        """Y a-t-il un badge de ce métier qui voit cette personne ? Sinon la tâche ne s'affiche chez personne."""
        for badge in self.badges.values():
            if badge.role != metier:
                continue
            if metier == "soignant" and badge.etage == personne.get("etage"):
                return True
            if metier != "soignant" and personne["id"] in badge.patients:
                return True
        return False

    # ------------------------------------------------------------------ le soir
    def _c_est_le_soir(self) -> bool:
        return self.horloge.etat()["heure"] >= horloge_clinique._heures()["le_soir"]  # « 19:00 » ≥ « 19:00 »

    def _patiente(self, badge: Badge, quoi: str) -> dict[str, Any]:
        if badge.role != "patient" or not badge.patient:
            self.porte.refuser(badge, quoi, "seul le patient pose ses questions du soir, sur son écran")
        return self.porte.patient(badge, badge.patient)

    def invitation(self, badge: Badge) -> dict[str, Any]:
        """Ce que l'écran de la patiente montre : le soir, la question, dans sa langue ; et ce qu'elle a déjà demandé."""
        personne = self._patiente(badge, "question du soir")
        langue = personne["langue"] if personne["langue"] in PHRASES else "fr"
        deja = [l["donnees"]["texte"] for l in self.carnet.lignes(GENRE_QUESTION)
                if l["donnees"]["patient"] == personne["id"] and l["quand"]["jour"] == self.horloge.etat()["jour"]]
        return {"a_poser": self._c_est_le_soir(), "langue": langue, "phrase": phrases(langue)["invitation"],
                "deja": deja, "marque": "données inventées"}

    def poser(self, badge: Badge, texte: str) -> dict[str, Any]:
        """La patiente tape une question. Elle va au carnet, telle quelle. Le prototype transmet, il ne répond pas."""
        personne = self._patiente(badge, "question du soir")
        if not self._c_est_le_soir():
            raise ChoixRefuse("la question du soir se pose le soir, à partir de "
                              + horloge_clinique._heures()["le_soir"].replace(":", " h "))
        texte = _propre(texte)
        if not texte:
            raise ChoixRefuse("la question est vide")
        langue = personne["langue"] if personne["langue"] in PHRASES else "fr"
        traduction = self._traduire(texte, personne["langue"])
        ligne = self.carnet.ecrire(badge, GENRE_QUESTION, {
            "patient": personne["id"], "texte": texte, "langue": personne["langue"], "traduction": traduction,
            "traduit_par": getattr(self.traducteur, "nom", "?") if traduction else None}, valide_par_un_humain=False)
        # H02 (réponse de Hiba à Q15) : chaque question du soir crée aussi une tâche pour le médecin, pour le lendemain.
        tache = self.taches.pour_la_question_du_soir(badge, personne["id"], ligne["numero"],
                                                     f"jour {self.horloge.etat()['jour'] + 1}")
        return {"dit": phrases(langue)["transmis"], "langue": langue, "ligne": ligne["numero"], "tache": tache["id"],
                "marque": "données inventées"}

    def _traduire(self, texte: str, langue: str) -> str | None:
        """La question, pour le médecin. Rien n'est inventé : pas de traducteur, une erreur, une réponse vide ou qui ne
        traduit rien → None (« non traduite »). La question part de toute façon, telle quelle."""
        if self.traducteur is None or langue == self.langue_du_medecin:
            return None
        try:
            rendu = self.traducteur.traduire(texte, langue, self.langue_du_medecin)
        except Exception:
            return None
        if not isinstance(rendu, str) or not rendu.strip() or _cle(rendu) == _cle(texte):
            return None
        return " ".join(rendu.split())[:LONGUEUR_MAX]

    # ------------------------------------------------------------------ la dictée
    def dicter(self, badge: Badge, patient: str, texte: str, confiance: float = 1.0) -> dict[str, Any]:
        """Le médecin dicte (aujourd'hui : il tape) sa phrase. Elle devient un brouillon et une tâche pour un humain.
        Rien n'entre au dossier. `confiance` : celle de l'écoute ; une phrase mal entendue n'écrit rien (T18)."""
        if badge.role != "médecin":
            self.porte.refuser(badge, "dictée", "seul le médecin dicte")
        personne = self.porte.patient(badge, patient)  # refuse si ce n'est pas un de ses patients
        if confiance < SEUIL_ECOUTE_DICTEE:
            raise ChoixRefuse("je n'ai pas bien entendu : rien n'est noté. Répétez, ou tapez la phrase")
        texte = _propre(texte)
        if not texte:
            raise ChoixRefuse("la dictée est vide")
        premier, virgule, reste = texte.partition(",")
        pour = DESTINATAIRES.get(premier.strip().lower()) if virgule else None
        quoi = (reste if pour else texte).strip().rstrip(".").strip() or texte
        jour = self.horloge.etat()["jour"]
        pour_quand = f"jour {jour + 1}" if re.search(r"\bdemain\b", texte.lower()) else "dès que possible"
        brouillon = self.carnet.ecrire(badge, GENRE_BROUILLON, {"patient": patient, "texte": texte, "origine": "dictée du médecin",
                                                                "mention": MENTION_BROUILLON}, valide_par_un_humain=True)
        tache = self.taches.pour_un_humain(badge, patient, quoi, pour=pour or PAR_DEFAUT, pour_quand=pour_quand,
                                           demande=texte, origine="dictée", brouillon=brouillon["numero"],
                                           mention=MENTION_BROUILLON)
        dit = f"Brouillon noté. Tâche pour le {tache['pour']} : {quoi} ({personne['nom']}, {pour_quand})."
        if pour is None:
            dit += " Je n'ai pas reconnu pour qui c'est : la tâche va à l'équipe de soin."
        if self.badges and not self._quelqu_un_la_verra(tache["pour"], personne):
            dit += (f" Attention : aucun badge « {tache['pour']} » ne suit cette personne : la tâche ne s'affichera sur "
                    f"aucun écran. Prévenez quelqu'un vous-même.")
        return {"brouillon": {"numero": brouillon["numero"], **brouillon["donnees"]}, "tache": tache, "dit": dit,
                "marque": "données inventées"}

    def pour_moi(self, badge: Badge) -> list[dict[str, Any]]:
        """Les tâches pour un humain de mon métier (l'écran du thérapeute), parmi les personnes que je vois."""
        return [t for t in self.taches.tableau(badge) if t.get("sorte") == "humain" and t.get("pour") == badge.role]
