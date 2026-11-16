"""Le faux logiciel administratif — SIMULÉ (clinique en boîte, avenant 4, tâche L02).

Un petit programme À PART. Ce n'est pas un écran de la clinique en boîte, et ce n'est pas un vrai logiciel de clinique :
il n'est relié à rien. Il tient une liste administrative (numéro du patient, numéro du séjour, nom inventé, date de
naissance, langue, chambre, dates, assurance « Exemple »). À chaque événement, il écrit UN message, un fichier texte,
dans le dossier « du_logiciel_vers_nous ».

    faux = FauxLogiciel(heure=...)                 # heure() rend {"jour": 1, "heure": "09:10"} : l'horloge de démonstration
    faux.evenement("A01", "p13", chambre="11")     # l'admission ; rend {"sorte", "fichier", "texte"}
    faux.remettre_a_zero()                         # vide les messages, remet les trois personnes en attente

Les neuf sortes de messages (les codes sont ceux du standard public HL7 version 2.5, famille ADT) : A05 pré-admission,
A01 admission, A02 changement de chambre, A03 sortie, A08 correction, A11 annulation d'une admission, A13 annulation
d'une sortie, A21 départ en congé, A22 retour de congé. Chaque message a ses lignes MSH (en-tête), EVN (événement),
PID (patient), PV1 (séjour), et IN1 (assurance « Exemple »).

DIRE VRAI : ces messages sont fabriqués par nous, d'après ce que nous savons du standard ; jamais essayés avec un vrai
logiciel. Une ligne par segment, avec une fin de ligne simple (le standard dit « retour chariot ») : à vérifier.
Rien de médical : ni raison du séjour, ni nom de soignant, ni numéro d'assurance sociale.
Ce programme ne connaît pas la clinique en boîte : il n'importe aucune de ses pièces.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

import yaml

ETIQUETTE = "SIMULÉ"
LISTE = Path(__file__).resolve().parent / "liste_administrative.yaml"
DOSSIER_DEFAUT = Path(__file__).resolve().parents[1] / "journal" / "faux_logiciel_admin"
VERS_NOUS, VERS_LUI = "du_logiciel_vers_nous", "de_nous_vers_le_logiciel"
SYSTEME, DESTINATAIRE, VERSION = "FAUX_LOGICIEL_ADMIN", "CLINIQUE_EN_BOITE", "2.5"
SORTES: dict[str, dict[str, str]] = {
    "A05": {"nom": "la pré-admission", "bouton": "Pré-admettre"},
    "A01": {"nom": "l'admission", "bouton": "Admettre"},
    "A02": {"nom": "le changement de chambre", "bouton": "Changer de chambre"},
    "A03": {"nom": "la sortie", "bouton": "Faire sortir"},
    "A08": {"nom": "la correction d'une information", "bouton": "Corriger"},
    "A11": {"nom": "l'annulation d'une admission", "bouton": "Annuler l'admission"},
    "A13": {"nom": "l'annulation d'une sortie", "bouton": "Annuler la sortie"},
    "A21": {"nom": "le départ en congé", "bouton": "Départ en congé"},
    "A22": {"nom": "le retour de congé", "bouton": "Retour de congé"},
}
CORRIGEABLES = ("nom", "langue", "date_naissance")
LANGUES = ("fr", "de", "it", "en", "pt")


class Refus(ValueError):
    """Le faux logiciel refuse cet événement. Le message dit pourquoi."""


def _horloge_absente() -> dict[str, Any]:
    return {"jour": 1, "heure": "09:00"}


class FauxLogiciel:
    def __init__(self, dossier: str | Path = DOSSIER_DEFAUT, heure: Callable[[], dict[str, Any]] = _horloge_absente,
                 liste: str | Path = LISTE) -> None:
        self.dossier, self.heure = Path(dossier), heure
        depart = yaml.safe_load(Path(liste).read_text(encoding="utf-8"))
        if depart.get("marque") != "inventé":
            raise ValueError("liste administrative : la marque « inventé » manque")
        self._depart = depart
        self.chambres = [str(c) for c in depart["chambres"]]
        self._jour_1 = date.fromisoformat(depart["jour_1"])
        self._charger()

    # ------------------------------------------------------------------ l'état
    @property
    def _etat_fichier(self) -> Path:
        return Path(self.dossier) / "etat.json"

    def _personnes_de_depart(self) -> list[dict[str, Any]]:
        return [{**p, "chambre": str(p["chambre"] or ""), "date_naissance": str(p["date_naissance"] or ""),
                 "assurance": self._depart["assurance"], "chambre_d_avant": ""} for p in self._depart["personnes"]]

    def _charger(self) -> None:
        if self._etat_fichier.exists():
            etat = json.loads(self._etat_fichier.read_text(encoding="utf-8"))
            self._personnes, self._numero = etat["personnes"], etat["numero"]
            self._admises: dict[str, str] = etat.get("admises", {})  # numéro de pré-admission → numéro de patient donné
        else:
            self._personnes, self._numero, self._admises = self._personnes_de_depart(), 0, {}

    def _garder(self) -> None:
        Path(self.dossier).mkdir(parents=True, exist_ok=True)
        self._etat_fichier.write_text(json.dumps({"personnes": self._personnes, "numero": self._numero, "admises": self._admises},
                                                 ensure_ascii=False, indent=1),
                                      encoding="utf-8")

    def liste(self) -> list[dict[str, Any]]:
        return [{c: v for c, v in p.items() if c != "chambre_d_avant"} for p in self._personnes]

    # ------------------------------------------------------------------ les pré-admissions reçues (avenant 4, L04)
    def pre_admissions_recues(self) -> list[dict[str, Any]]:
        """Les demandes de pré-admission écrites par l'autre système dans « de nous vers le logiciel ». Seulement des
        lignes administratives. Un fichier illisible est laissé de côté : il n'arrête rien."""
        dossier = Path(self.dossier) / VERS_LUI
        recues = []
        for fichier in sorted(dossier.glob("*.hl7")) if dossier.exists() else []:
            try:
                s = {l.split("|")[0]: l.split("|") for l in fichier.read_text(encoding="utf-8").splitlines() if l.strip()}
                champ = lambda nom, n: s[nom][n] if nom in s and len(s[nom]) > n else ""  # noqa: E731
                numero, nom = champ("PV1", 5), (champ("PID", 5).split("^") + [""])[:2]
                if champ("MSH", 8) != "ADT^A05" or not numero or not nom[0]:
                    continue
                naissance, arrivee = champ("PID", 7), champ("PV2", 8)
            except (OSError, UnicodeDecodeError):
                continue
            jour = lambda t: f"{t[:4]}-{t[4:6]}-{t[6:8]}" if len(t) >= 8 else ""  # noqa: E731
            recues.append({"numero": numero, "statut": "admise" if numero in self._admises else "reçue", "nom": nom[0],
                           "prenom": nom[1], "date_naissance": jour(naissance), "langue": champ("PID", 15),
                           "assurance": champ("IN1", 4), "date_arrivee_prevue": jour(arrivee), "fichier": fichier.name,
                           "numero_patient": self._admises.get(numero, "")})
        return recues

    def admettre_pre_admission(self, numero: str, chambre: str | None) -> dict[str, Any]:
        """Une personne du logiciel appuie sur « admettre » : la personne reçoit un numéro de patient et un numéro de
        séjour, et un message d'admission repart, avec le numéro de la pré-admission."""
        recue = next((r for r in self.pre_admissions_recues() if r["numero"] == numero), None)
        if recue is None:
            raise Refus(f"pré-admission inconnue « {numero} »")
        if recue["statut"] == "admise":
            raise Refus(f"la pré-admission {numero} est déjà admise")
        chambre = self._chambre(chambre)
        rang = max(int(p["numero_patient"][1:]) for p in self._personnes) + 1
        self._personnes.append({"numero_patient": f"p{rang:02d}", "numero_sejour": f"s{rang:02d}",
                                "nom": f"{recue['prenom']} {recue['nom']}".strip(), "date_naissance": recue["date_naissance"],
                                "langue": recue["langue"], "chambre": "", "jour_entree": None, "jour_sortie_prevue": None,
                                "statut": "pré-admis", "verrouille": False, "assurance": self._depart["assurance"],
                                "chambre_d_avant": "", "pre_admission": numero})
        self._admises[numero] = f"p{rang:02d}"
        return self.evenement("A01", f"p{rang:02d}", chambre=chambre)

    def personne(self, numero: str) -> dict[str, Any]:
        for p in self._personnes:
            if p["numero_patient"] == numero:
                return p
        raise Refus(f"numéro de patient inconnu « {numero} »")

    def messages(self) -> list[Path]:
        dossier = Path(self.dossier) / VERS_NOUS
        return sorted(dossier.glob("*.hl7")) if dossier.exists() else []

    def remettre_a_zero(self) -> None:
        """Vide les deux dossiers de messages et remet les trois personnes en attente. Ne touche à rien d'autre."""
        for nom in (VERS_NOUS, VERS_LUI):
            dossier = Path(self.dossier) / nom
            if dossier.exists():
                for fichier in dossier.iterdir():
                    if fichier.is_file():
                        fichier.unlink()
        if self._etat_fichier.exists():
            self._etat_fichier.unlink()
        self._charger()

    # ------------------------------------------------------------------ les événements
    def evenement(self, sorte: str, numero: str, chambre: str | None = None, champ: str | None = None,
                  valeur: str | None = None) -> dict[str, Any]:
        """Un événement administratif sur une personne : l'état change, et UN message est écrit."""
        if sorte not in SORTES:
            raise Refus(f"sorte de message inconnue « {sorte} » (connues : {', '.join(SORTES)})")
        p = self.personne(numero)
        if p["verrouille"]:
            raise Refus(f"{p['nom']} est verrouillé : c'est une personne du faux dossier, le faux logiciel ne la change pas")
        statut, jour = p["statut"], int(self.heure()["jour"])
        change: dict[str, Any] = {}
        if sorte == "A05":
            self._exiger(statut == "en attente", p, "est déjà pré-admise ou admise")
            change = {"statut": "pré-admis"}
        elif sorte == "A01":
            self._exiger(statut in ("en attente", "pré-admis"), p, "est déjà admise")
            change = {"statut": "admis", "chambre": self._chambre(chambre), "jour_entree": jour}
        elif sorte == "A02":
            self._exiger(statut == "admis", p, "n'est pas admise")
            change = {"chambre_d_avant": p["chambre"], "chambre": self._chambre(chambre)}
        elif sorte == "A03":
            self._exiger(statut == "admis", p, "n'est pas admise")
            change = {"statut": "sorti", "jour_sortie": jour}
        elif sorte == "A08":
            if champ not in CORRIGEABLES:
                raise Refus(f"on corrige seulement : {', '.join(CORRIGEABLES)}")
            valeur = " ".join(str(valeur or "").split())[:60]
            if not valeur or (champ == "langue" and valeur not in LANGUES):
                raise Refus(f"valeur refusée pour « {champ} »")
            if champ == "date_naissance":
                try:
                    date.fromisoformat(valeur)
                except ValueError:
                    raise Refus("la date de naissance s'écrit AAAA-MM-JJ") from None
            change = {champ: valeur}
        elif sorte == "A11":
            self._exiger(statut == "admis", p, "n'est pas admise")
        elif sorte == "A13":
            self._exiger(statut == "sorti", p, "n'est pas sortie")
            change = {"statut": "admis", "jour_sortie": None}
        elif sorte == "A21":
            self._exiger(statut == "admis", p, "n'est pas admise")
            change = {"statut": "en congé"}
        elif sorte == "A22":
            self._exiger(statut == "en congé", p, "n'est pas en congé")
            change = {"statut": "admis"}
        p.update(change)
        texte = self._message(sorte, p)
        if sorte == "A11":  # le message porte encore la chambre annulée ; ensuite la personne attend de nouveau
            p.update(statut="en attente", chambre="", chambre_d_avant="", jour_entree=None)
        self._numero += 1
        dossier = Path(self.dossier) / VERS_NOUS
        dossier.mkdir(parents=True, exist_ok=True)
        fichier = dossier / f"{self._numero:04d}_{sorte}_{numero}.hl7"
        fichier.write_text(texte, encoding="utf-8")
        self._garder()
        return {"sorte": sorte, "nom": SORTES[sorte]["nom"], "fichier": str(fichier), "texte": texte, "etiquette": ETIQUETTE,
                "numero_patient": numero, "numero_sejour": p["numero_sejour"]}

    @staticmethod
    def _exiger(condition: bool, p: dict[str, Any], pourquoi: str) -> None:
        if not condition:
            raise Refus(f"{p['nom']} {pourquoi} (elle est « {p['statut']} »)")

    def _chambre(self, chambre: str | None) -> str:
        if str(chambre) not in self.chambres:
            raise Refus(f"choisir une chambre parmi : {', '.join(self.chambres)}")
        return str(chambre)

    # ------------------------------------------------------------------ écrire un message
    def _quand(self, jour: int | None, heure: str = "00:00") -> str:
        if jour is None:
            return ""
        return (self._jour_1 + timedelta(days=int(jour) - 1)).strftime("%Y%m%d") + heure.replace(":", "")

    @staticmethod
    def _segment(nom: str, champs: dict[int, str], longueur: int) -> str:
        """Un segment : chaque renseignement à sa place numérotée, les autres places vides."""
        return "|".join([nom] + [champs.get(n, "") for n in range(1, longueur + 1)])

    def _message(self, sorte: str, p: dict[str, Any]) -> str:
        maintenant = self.heure()
        quand = self._quand(maintenant["jour"], str(maintenant["heure"]))
        etablissement = self._depart["etablissement"]
        morceaux = p["nom"].split()  # « Madame Giulia B. » : civilité, prénom, initiale
        if len(morceaux) >= 3:
            nom = f"{morceaux[-1]}^{' '.join(morceaux[1:-1])}^^^{morceaux[0]}"
        else:  # une personne venue d'une pré-admission : prénom et nom, pas de civilité
            nom = f"{morceaux[-1]}^{' '.join(morceaux[:-1])}"
        lieu = f"{etablissement}^{p['chambre']}" if p["chambre"] else ""
        avant = f"{etablissement}^{p['chambre_d_avant']}" if sorte == "A02" and p["chambre_d_avant"] else ""
        msh = "|".join(["MSH", "^~\\&", SYSTEME, etablissement, DESTINATAIRE, etablissement, quand, "", f"ADT^{sorte}",
                        f"{SYSTEME}-{self._numero + 1:06d}", "P", VERSION])
        evn = self._segment("EVN", {1: sorte, 2: quand}, 2)
        pid = self._segment("PID", {1: "1", 3: f"{p['numero_patient']}^^^{SYSTEME}", 5: nom,
                                    7: p["date_naissance"].replace("-", ""), 15: p["langue"]}, 15)
        pv1 = self._segment("PV1", {1: "1", 2: "P" if p["statut"] in ("en attente", "pré-admis") else "I", 3: lieu, 6: avant,
                                    5: p.get("pre_admission", ""),  # le numéro de la pré-admission relie la demande et la réponse
                                    19: p["numero_sejour"], 44: self._quand(p.get("jour_entree"), "0900"),
                                    45: self._quand(p.get("jour_sortie"), str(maintenant["heure"])) if p["statut"] == "sorti" else ""}, 45)
        in1 = self._segment("IN1", {1: "1", 2: "EXEMPLE", 3: "EXEMPLE", 4: p["assurance"]}, 4)
        return "\n".join([msh, evn, pid, pv1, in1]) + "\n"
