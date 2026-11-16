"""La porte de lecture : le seul chemin vers le faux dossier, pour les écrans, le cerveau et les robots (cahier 5.2).

    from briques.clinique.porte import PorteDeLecture, charger_badges
    porte, badges = PorteDeLecture(), charger_badges()
    porte.patients(badges["soignant-etage-2"])      # les patients de son étage, et seulement ce qu'il a le droit de voir

- On entre avec un badge. Ce n'est pas un vrai contrôle d'identité (pas de mot de passe) : voir NON_TESTE.md.
- La porte ne fait que lire. Toute demande d'écriture est refusée et notée.
- Chaque accès est au journal : qui, quoi, quand, lu ou refusé.
- Le cerveau lit par la même porte, avec le badge « assistant » : il voit ce que voit la personne pour qui il
  travaille, pas plus (brancher_sur_la_porte_des_agents, pour la brique 14).

| Badge | Ce qu'il voit |
| patient | seulement lui : son programme, ses documents |
| soignant | les patients de son étage : habitudes, programme, listes de soin, documents |
| thérapeute | ses patients : programme |
| médecin | ses patients : tout |
| accueil | les arrivées du jour, et le fait qu'un papier attend (sans son texte : H01) ; ni programme, ni habitudes, ni raison du séjour, ni liste de soin |
| direction | des comptes par étage ; aucun nom |
| assistant | ce que voit la personne pour qui il travaille |
| robot | le lieu, le prénom et la langue de la personne ; rien sur la santé |
| robot du hall | les arrivées du jour : nom, langue, chambre, étage, première heure ; rien sur la santé |
"""
from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

from . import dossier as faux_dossier

ROLES = ("patient", "soignant", "thérapeute", "médecin", "accueil", "direction", "assistant", "robot")
FICHIER_BADGES = Path(__file__).resolve().parent / "badges.yaml"
DOSSIER_JOURNAL = Path(__file__).resolve().parents[2] / "journal" / "clinique"


class AccesRefuse(PermissionError):
    """La porte dit non. Le message dit pourquoi, en mots simples."""


class EcritureRefusee(AccesRefuse):
    """La porte ne fait que lire : aucune écriture dans le faux dossier."""


@dataclass(frozen=True)
class Badge:
    id: str
    role: str
    libelle: str
    etage: int | None = None  # soignant : son étage
    patient: str | None = None  # patient : lui-même
    patients: tuple[str, ...] = ()  # thérapeute, médecin : leurs patients
    pour: "Badge | None" = None  # assistant : la personne pour qui il travaille

    def travaille_pour(self, personne: "Badge") -> "Badge":
        """Le badge de l'assistant, au service d'une personne : il verra ce qu'elle voit, pas plus."""
        if self.role != "assistant":
            raise ValueError("seul l'assistant peut travailler pour quelqu'un")
        if personne.role == "assistant":
            raise ValueError("l'assistant ne travaille pas pour un autre assistant")
        return replace(self, pour=personne)


def charger_badges(fichier: Path = FICHIER_BADGES) -> dict[str, Badge]:
    donnees = yaml.safe_load(fichier.read_text(encoding="utf-8"))
    badges = {}
    for b in donnees["badges"]:
        if b["role"] not in ROLES:
            raise ValueError(f"badges.yaml : rôle inconnu « {b['role']} »")
        badges[b["id"]] = Badge(id=b["id"], role=b["role"], libelle=b["libelle"], etage=b.get("etage"),
                                patient=b.get("patient"), patients=tuple(b.get("patients", ())))
    return badges


class JournalDesAcces:
    """Qui a lu quoi, quand. Une ligne JSON par accès, écrite tout de suite si un fichier est donné."""

    def __init__(self, fichier: str | Path | None = None) -> None:
        self.fichier = Path(fichier) if fichier else None
        self._lignes: list[dict[str, Any]] = []
        if self.fichier:
            self.fichier.parent.mkdir(parents=True, exist_ok=True)

    def noter(self, ligne: dict[str, Any]) -> None:
        self._lignes.append(ligne)
        if self.fichier:
            with open(self.fichier, "a", encoding="utf-8") as f:
                f.write(json.dumps(ligne, ensure_ascii=False) + "\n")

    def lignes(self) -> list[dict[str, Any]]:
        return [dict(ligne) for ligne in self._lignes]


def _copie(objet):
    """Une copie ordinaire (dictionnaires, listes) : la modifier ne change jamais le faux dossier."""
    if hasattr(objet, "items"):
        return {cle: _copie(valeur) for cle, valeur in objet.items()}
    if isinstance(objet, (list, tuple)):
        return [_copie(valeur) for valeur in objet]
    return objet


class PorteDeLecture:
    def __init__(self, dossier: faux_dossier.FauxDossier | None = None, journal: JournalDesAcces | None = None,
                 jour: Callable[[], int] = lambda: 1) -> None:
        self.dossier = dossier or faux_dossier.charger()
        if journal is None:
            nom = datetime.now().strftime("acces_%Y-%m-%d_%H%M%S.jsonl")
            journal = JournalDesAcces(DOSSIER_JOURNAL / nom)
        self.journal = journal
        self.jour = jour  # le jour de la démonstration (l'horloge le donnera)
        # Avenant 4, L03 : la vue administrative (les personnes arrivées par message du faux logiciel, SIMULÉ). Une fonction
        # qui rend ces personnes, ou None. Sans elle, ou sans aucun message, la porte donne exactement ce qu'elle donnait.
        self.vue_admin: Callable[[], list[dict[str, Any]]] | None = None

    def _tous(self) -> list:
        """Les patients du faux dossier, plus les personnes présentes arrivées par message (des fiches sans rien de médical).
        Le faux dossier garde la main : un message ne change jamais une de ses fiches."""
        patients = list(self.dossier.patients)
        if self.vue_admin is None:
            return patients
        connus = {p["Patient"]["id"] for p in patients}
        etages = {l["nom"]: l["etage"] for l in self.dossier.lieux["lieux"]}
        for a in self.vue_admin():
            if a["etat"] not in ("présent", "en congé") or a["numero_patient"] in connus:
                continue
            chambre = int(a["chambre"]) if str(a["chambre"]).isdigit() else a["chambre"]
            entree = a.get("entree") or {}
            # une personne venue d'une pré-admission n'a pas de civilité : « M./Mme Elena C. » (le reste de la porte attend trois mots)
            nom = a["nom"] if len(a["nom"].split()) >= 3 else f"M./Mme {a['nom']}"
            patients.append({
                "Patient": {"id": a["numero_patient"], "nom_affiche": nom, "nom_complet_affiche": nom, "age": None,
                            "langue": a["langue"], "comprend_un_peu": ()},
                "Encounter": {"chambre": chambre, "etage": etages.get(f"Chambre {chambre}"), "raison": None, "duree_jours": None,
                              "sortie_jour": None, "arrivee": {"jour": entree.get("jour"), "heure": entree.get("heure")}},
                "Appointment": (), "DocumentReference": (), "CarePlan": (), "habitudes": (), "par_message": True})
        return patients

    # ------------------------------------------------------------------ le journal
    def _noter(self, badge: Badge, quoi: str, resultat: str, patients: list[str] | None = None, raison: str = "") -> None:
        self.journal.noter({"quand": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), "qui": badge.id,
                            "role": badge.role, "pour": badge.pour.id if badge.pour else None, "quoi": quoi,
                            "patients": patients or [], "resultat": resultat, "raison": raison})

    def _refuser(self, badge: Badge, quoi: str, raison: str, patients: list[str] | None = None):
        self._noter(badge, quoi, "refusé", patients, raison)
        raise AccesRefuse(raison)

    def refuser(self, badge: Badge, quoi: str, raison: str):
        """Pour les écrans : dire non à un badge (par exemple un badge qui n'ouvre pas cet écran), et le noter."""
        self._refuser(badge, quoi, raison)

    def noter(self, badge: Badge, quoi: str, patients: list[str] | None = None) -> None:
        """Pour les pièces qui lisent par la porte : noter au journal ce qui a été ouvert (une source, par exemple)."""
        self._noter(badge, quoi, "lu", patients)

    # ------------------------------------------------------------------ qui voit quoi
    def _personne(self, badge: Badge, quoi: str) -> Badge:
        """Le badge dont on applique la vue. Pour l'assistant : celui de la personne pour qui il travaille."""
        if badge.role not in ROLES:
            self._refuser(badge, quoi, f"badge inconnu « {badge.role} »")
        if badge.role == "assistant":
            if badge.pour is None or badge.pour.role == "assistant":
                self._refuser(badge, quoi, "l'assistant ne travaille pour personne : il ne voit rien")
            return badge.pour
        return badge

    def _visibles(self, personne: Badge) -> list:
        tous = self._tous()
        if personne.role == "patient":
            return [p for p in tous if p["Patient"]["id"] == personne.patient]
        if personne.role == "soignant":
            return [p for p in tous if personne.etage is not None and p["Encounter"]["etage"] == personne.etage]
        if personne.role in ("thérapeute", "médecin"):
            return [p for p in tous if p["Patient"]["id"] in personne.patients]
        if personne.role == "accueil":
            return [p for p in tous if p["Encounter"]["arrivee"]["jour"] == self.jour()]
        if personne.role == "robot":
            return list(tous)
        return []  # direction : aucun patient, seulement des comptes

    @staticmethod
    def _vue(personne: Badge, p) -> dict[str, Any]:
        identite, sejour = p["Patient"], p["Encounter"]
        if personne.role == "robot":
            return {"id": identite["id"], "prenom": identite["nom_affiche"].split()[1], "langue": identite["langue"],
                    "chambre": sejour["chambre"], "etage": sejour["etage"]}
        vue = {"id": identite["id"], "nom": identite["nom_affiche"], "langue": identite["langue"],
               "chambre": sejour["chambre"], "etage": sejour["etage"], "programme": _copie(p["Appointment"])}
        if personne.role == "thérapeute":
            return vue
        if personne.role == "patient":
            vue["documents"] = [{"id": d["id"], "genre": d["genre"], "titre": d["titre"]} for d in p["DocumentReference"]]
            return vue
        vue.update(nom_complet=identite["nom_complet_affiche"], comprend_un_peu=_copie(identite["comprend_un_peu"]),
                   arrivee=_copie(sejour["arrivee"]), sortie_jour=sejour["sortie_jour"],
                   documents=_copie(p["DocumentReference"]))
        if personne.role == "accueil":
            # H01 (réponse de Hiba à Q18, 12.11.2026) : l'accueil ne reçoit plus le texte d'un papier (il peut être
            # médical), ni le programme (cahier 5.2 : les arrivées du jour et les papiers à ranger). Il sait seulement
            # qu'un papier attend. Le texte : papiers_a_ranger(), pour la pièce qui range, avec son propre badge.
            vue["documents"] = [{"id": d["id"]} for d in p["DocumentReference"]]
            del vue["programme"]
            return vue
        vue.update(habitudes=_copie(p["habitudes"]), listes=_copie(p["CarePlan"]))
        if personne.role == "médecin":
            vue.update(raison=sejour["raison"], age=identite["age"], duree_jours=sejour["duree_jours"])
        if p.get("par_message"):  # arrivée par message : que de l'administratif (avenant 4, L03)
            vue["dossier_de_soins"] = "rien pour ce patient"
        return vue

    # ------------------------------------------------------------------ les lectures
    def patients(self, badge: Badge) -> list[dict[str, Any]]:
        quoi = "patients"
        personne = self._personne(badge, quoi)
        if personne.role == "direction":
            self._refuser(badge, quoi, "la direction ne voit aucun nom de patient, seulement des comptes")
        visibles = self._visibles(personne)
        self._noter(badge, quoi, "lu", [p["Patient"]["id"] for p in visibles])
        return [self._vue(personne, p) for p in visibles]

    def patient(self, badge: Badge, identifiant: str) -> dict[str, Any]:
        quoi = "patient"
        personne = self._personne(badge, quoi)
        for p in self._visibles(personne):
            if p["Patient"]["id"] == identifiant:
                self._noter(badge, quoi, "lu", [identifiant])
                return self._vue(personne, p)
        self._refuser(badge, quoi, "ce badge ne donne pas accès à cette personne", [identifiant])

    def comptes(self, badge: Badge) -> dict[str, Any]:
        """Pour la direction : des nombres par étage. Aucun nom, aucun identifiant."""
        quoi = "comptes par étage"
        personne = self._personne(badge, quoi)
        if personne.role != "direction":
            self._refuser(badge, quoi, "les comptes par étage sont pour la direction")
        etages: dict[Any, dict[str, Any]] = {}
        for p in self._tous():
            sejour = p["Encounter"]
            e = etages.setdefault(sejour["etage"], {"etage": sejour["etage"], "patients": 0, "arrivees_du_jour": 0,
                                                    "sorties_demain": 0})
            e["patients"] += 1
            e["arrivees_du_jour"] += sejour["arrivee"]["jour"] == self.jour()
            e["sorties_demain"] += sejour["sortie_jour"] == self.jour() + 1
        self._noter(badge, quoi, "lu")
        return {"marque": "données inventées", "jour": self.jour(),
                "etages": sorted(etages.values(), key=lambda e: (e["etage"] is None, e["etage"] or 0))}

    def _pour_les_roles(self, badge: Badge, quoi: str, roles: tuple[str, ...]) -> None:
        personne = self._personne(badge, quoi)
        if personne.role not in roles:
            self._refuser(badge, quoi, f"le badge « {personne.role} » ne donne pas accès à : {quoi}")

    def lieux(self, badge: Badge) -> dict[str, Any]:
        self._pour_les_roles(badge, "lieux", ("soignant", "thérapeute", "médecin", "accueil", "robot"))
        self._noter(badge, "lieux", "lu")
        return _copie(self.dossier.lieux)

    def reserve(self, badge: Badge) -> list[dict[str, Any]]:
        self._pour_les_roles(badge, "réserve", ("soignant", "thérapeute", "médecin", "accueil", "robot"))
        self._noter(badge, "réserve", "lu")
        return _copie(self.dossier.reserve)

    def arrivees_pour_le_hall(self, badge: Badge) -> list[dict[str, Any]]:
        """Pour le robot du hall : les arrivées du jour. Le nom, la langue, la chambre, l'étage et la première heure
        du programme. Rien sur la santé : ni raison du séjour, ni habitudes, ni documents, ni ce qui est au programme."""
        quoi = "arrivées pour le hall"
        if badge.role != "robot":
            self._refuser(badge, quoi, "les arrivées pour le hall sont pour le robot du hall")
        jour = self.jour()
        arrivees = [p for p in self._tous() if p["Encounter"]["arrivee"]["jour"] == jour]
        self._noter(badge, quoi, "lu", [p["Patient"]["id"] for p in arrivees])
        vues = []
        for p in arrivees:
            morceaux = p["Patient"]["nom_affiche"].split()  # « Madame Giulia B. »
            heures = sorted(str(r["heure"]) for r in p["Appointment"] if r["jour"] == jour)
            vues.append({"id": p["Patient"]["id"], "nom": p["Patient"]["nom_affiche"], "prenom": " ".join(morceaux[1:-1]),
                         "initiale": morceaux[-1].rstrip("."), "langue": p["Patient"]["langue"],
                         "chambre": p["Encounter"]["chambre"], "etage": p["Encounter"]["etage"],
                         "premiere_heure": heures[0] if heures else None,
                         **({"par_message": True} if p.get("par_message") else {})})
        return vues

    def feuilles_sans_patient(self, badge: Badge) -> list[dict[str, Any]]:
        """Les feuilles volantes, sans nom de patient. Pour l'accueil, qui trie les papiers : il sait qu'elles attendent.
        Sans leur texte (H01) : on ne sait pas ce qu'une feuille sans nom contient."""
        self._pour_les_roles(badge, "feuilles sans patient", ("accueil",))
        self._noter(badge, "feuilles sans patient", "lu")
        return [{cle: _copie(v) for cle, v in f.items() if cle != "texte"} for f in self.dossier.feuilles_sans_patient]

    def papiers_a_ranger(self, badge: Badge) -> list[dict[str, Any]]:
        """Le TEXTE des papiers à ranger aujourd'hui : ceux des personnes qui arrivent, et les feuilles sans nom.
        Seulement pour la pièce qui range les papiers, avec son propre badge : l'assistant, au service de l'accueil
        (H01, réponse de Hiba à Q18). Elle prépare une proposition ; l'écran de l'accueil ne montre jamais ce texte."""
        quoi = "papiers à ranger"
        if badge.role != "assistant" or badge.pour is None or badge.pour.role != "accueil":
            self._refuser(badge, quoi, "le texte des papiers à ranger est pour la pièce qui range, au service de l'accueil")
        jour = self.jour()
        arrivees = [p for p in self._tous() if p["Encounter"]["arrivee"]["jour"] == jour]
        self._noter(badge, quoi, "lu", [p["Patient"]["id"] for p in arrivees])
        cles = ("id", "texte", "langue", "ecriture")
        papiers = [{cle: d.get(cle, "tapée" if cle == "ecriture" else None) for cle in cles}
                   for p in arrivees for d in p["DocumentReference"]]
        return papiers + [{cle: f.get(cle, "tapée" if cle == "ecriture" else None) for cle in cles}
                          for f in self.dossier.feuilles_sans_patient]

    def liste_de_soin(self, badge: Badge, identifiant: str) -> dict[str, Any]:
        quoi = f"liste de soin : {identifiant}"
        self._pour_les_roles(badge, quoi, ("soignant", "thérapeute", "médecin"))  # H01 : plus l'accueil
        try:
            liste = self.dossier.liste(identifiant)
        except KeyError:
            self._refuser(badge, quoi, "cette liste de soin n'existe pas")
        self._noter(badge, quoi, "lu")
        return _copie(liste)

    def points_de_sortie_pour_l_accueil(self, badge: Badge) -> list[dict[str, Any]]:
        """H17 (réponse de Hiba à Q24 : B) : une porte étroite, pour l'accueil seulement. Pour chaque personne qui a la
        liste « Préparation de la sortie » : son nom, sa chambre, le jour de sortie, et SEULEMENT les points de la liste
        marqués « pour : accueil ». Rien d'autre : la règle H01 (`liste_de_soin` refusée à l'accueil) ne change pas."""
        quoi = "points de sortie de l'accueil"
        personne = self._personne(badge, quoi)
        if personne.role != "accueil":
            self._refuser(badge, quoi, "cette vue est pour l'accueil (ses trois points de la liste de sortie)")
        try:
            modele = self.dossier.liste("sortie")
        except KeyError:
            self._noter(badge, quoi, "lu")
            return []
        points = [{"numero": pt["numero"], "nom": pt["nom"], "texte": pt["texte"]} for pt in modele["points"]
                  if pt["pour"] == "accueil"]
        vues = []
        for p in self._tous():
            if "sortie" not in (p.get("CarePlan") or ()):
                continue
            identite, sejour = p["Patient"], p["Encounter"]
            vues.append({"id": identite["id"], "nom": identite["nom_affiche"], "chambre": sejour["chambre"],
                         "etage": sejour["etage"], "sortie_jour": sejour.get("sortie_jour"), "liste": modele["id"],
                         "titre": modele["titre"], "points": _copie(points)})
        self._noter(badge, quoi, "lu", [v["id"] for v in vues])
        return vues

    # ------------------------------------------------------------------ jamais d'écriture
    def ecrire(self, badge: Badge, quoi: str, identifiant: str | None = None, **donnees: Any):
        """Toujours refusé, pour tous les badges, et noté. Ce que le prototype crée va dans le carnet, pas ici."""
        raison = "la porte ne fait que lire : le faux dossier ne change jamais"
        self._noter(badge, f"écrire : {quoi}", "écriture refusée", [identifiant] if identifiant else [], raison)
        raise EcritureRefusee(raison)


def brancher_sur_la_porte_des_agents(serveur, porte: PorteDeLecture, badge: Badge) -> None:
    """Ajoute au serveur de la porte des agents (brique 14, MCP) UN outil, qui lit par cette porte avec ce badge.

    Le badge est fixé ici, par l'équipe : l'agent ne peut pas en changer. Aucun outil pour écrire.
    """
    from mcp_types import ToolAnnotations

    @serveur.tool(title="Lire le faux dossier de la clinique",
                  annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
    def lire_dossier(quoi: str, identifiant: str | None = None) -> dict[str, Any]:
        """Lire le faux dossier (DONNÉES INVENTÉES) par la porte de lecture. quoi : « patients », « patient »
        (avec identifiant), « lieux », « reserve », « liste » (avec identifiant) ou « comptes ». Vous voyez ce que
        voit la personne pour qui vous travaillez, pas plus. Chaque lecture est notée au journal des accès."""
        lectures = {"patients": lambda: porte.patients(badge), "patient": lambda: porte.patient(badge, identifiant or ""),
                    "lieux": lambda: porte.lieux(badge), "reserve": lambda: porte.reserve(badge),
                    "liste": lambda: porte.liste_de_soin(badge, identifiant or ""), "comptes": lambda: porte.comptes(badge)}
        if quoi not in lectures:
            return {"refuse": True, "raison": f"lecture inconnue « {quoi} »", "marque": "données inventées"}
        try:
            return {"refuse": False, "resultat": lectures[quoi](), "marque": "données inventées"}
        except AccesRefuse as refus:
            return {"refuse": True, "raison": str(refus), "marque": "données inventées"}
