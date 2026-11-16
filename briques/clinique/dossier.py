"""Le faux dossier : il tient lieu de logiciel de la clinique (cahier 5.1). DONNÉES INVENTÉES.

    from briques.clinique import dossier
    d = dossier.charger()            # tout, contrôlé, et impossible à modifier
    d.patient("p01")                 # Madame Giulia B. (personnage inventé)
    d.distance("Réserve", "Chambre 12")

Les mots viennent du langage commun des dossiers de santé (FHIR R4) : Patient, Encounter (le séjour), Appointment
(le rendez-vous), DocumentReference (le document), CarePlan (les listes de soin prévues). Inspiré de FHIR, non validé.
Ce module LIT seulement. Le faux dossier ne change jamais pendant une démonstration : ce que le prototype crée ira
dans le carnet (une autre pièce). Les écrans ne lisent pas ce module directement : ils passeront par la porte de lecture.
"""
from __future__ import annotations

import hashlib
import heapq
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

import yaml

DOSSIER = Path(__file__).resolve().parent / "faux_dossier"
LANGUES = ("fr", "de", "it", "en", "pt")
MARQUE_LISTE = "exemple inventé, non médical, à remplacer par les listes de la clinique"


class DossierInvalide(ValueError):
    """Le faux dossier n'a pas la forme attendue. Le message dit quoi, en clair."""


def _geler(objet):
    if isinstance(objet, dict):
        return MappingProxyType({cle: _geler(valeur) for cle, valeur in objet.items()})
    if isinstance(objet, list):
        return tuple(_geler(valeur) for valeur in objet)
    return objet


def _lire(fichier: Path):
    try:
        return yaml.safe_load(fichier.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as erreur:
        raise DossierInvalide(f"{fichier.name} : illisible ({erreur})") from erreur


def _exiger(condition: bool, message: str) -> None:
    if not condition:
        raise DossierInvalide(message)


@dataclass(frozen=True)
class FauxDossier:
    patients: tuple
    listes: tuple
    lieux: MappingProxyType
    reserve: tuple
    reserve_marque: str
    feuilles_sans_patient: tuple

    def patient(self, identifiant: str):
        for p in self.patients:
            if p["Patient"]["id"] == identifiant:
                return p
        raise KeyError(identifiant)

    def liste(self, identifiant: str):
        for liste in self.listes:
            if liste["id"] == identifiant:
                return liste
        raise KeyError(identifiant)

    def distance(self, depart: str, arrivee: str) -> float | None:
        """Mètres par le plus court chemin entre deux lieux ; None s'il n'y a pas de chemin (pas d'ascenseur pour les robots)."""
        voisins: dict[str, list[tuple[str, float]]] = {}
        for v in self.lieux["voisins"]:
            voisins.setdefault(v["de"], []).append((v["a"], v["metres"]))
            voisins.setdefault(v["a"], []).append((v["de"], v["metres"]))
        file, vus = [(0.0, depart)], set()
        while file:
            metres, lieu = heapq.heappop(file)
            if lieu == arrivee:
                return metres
            if lieu in vus:
                continue
            vus.add(lieu)
            for suivant, pas in voisins.get(lieu, ()):
                if suivant not in vus:
                    heapq.heappush(file, (metres + pas, suivant))
        return None


def fichiers(dossier: Path = DOSSIER) -> list[Path]:
    return sorted(dossier.rglob("*.yaml"))


def empreinte(dossier: Path = DOSSIER) -> str:
    """Une signature de tous les fichiers : si elle change, le faux dossier a changé."""
    h = hashlib.sha256()
    for fichier in fichiers(dossier):
        h.update(fichier.relative_to(dossier).as_posix().encode())
        h.update(fichier.read_bytes())
    return h.hexdigest()


def _controler_patient(p, nom: str) -> None:
    _exiger(isinstance(p, dict), f"{nom} : fiche vide")
    _exiger(p.get("marque") == "inventé", f"{nom} : la fiche ne porte pas la marque « inventé »")
    for cle in ("Patient", "Encounter", "habitudes", "Appointment", "DocumentReference", "CarePlan"):
        _exiger(cle in p, f"{nom} : il manque « {cle} »")
    identite, sejour = p["Patient"], p["Encounter"]
    for cle in ("id", "nom_affiche", "nom_complet_affiche", "age", "langue"):
        _exiger(cle in identite, f"{nom} : il manque Patient.{cle}")
    _exiger("inventé" in identite["nom_complet_affiche"], f"{nom} : le nom affiché ne dit pas « inventé »")
    _exiger(identite["langue"] in LANGUES, f"{nom} : langue inconnue « {identite['langue']} »")
    for cle in ("chambre", "arrivee", "duree_jours", "sortie_jour", "raison"):
        _exiger(cle in sejour, f"{nom} : il manque Encounter.{cle}")
    for document in p["DocumentReference"]:
        for cle in ("id", "genre", "langue", "ecriture", "marque", "texte"):
            _exiger(cle in document, f"{nom} : il manque « {cle} » dans un document")
        _exiger(document["marque"] == "INVENTÉ" and "INVENTÉ" in document["texte"],
                f"{nom} : le document {document['id']} ne porte pas « INVENTÉ »")


def charger(dossier: Path = DOSSIER) -> FauxDossier:
    """Charge et contrôle tout le faux dossier. Lève DossierInvalide si quelque chose manque."""
    patients = []
    for fichier in sorted((dossier / "patients").glob("*.yaml")):
        p = _lire(fichier)
        _controler_patient(p, fichier.name)
        patients.append(p)
    _exiger(len(patients) == 12, f"il faut 12 patients, il y en a {len(patients)}")
    _exiger(len({p["Patient"]["id"] for p in patients}) == 12, "deux patients ont le même identifiant")
    _exiger(len({p["Encounter"]["chambre"] for p in patients}) == 12, "deux patients ont la même chambre")

    listes = _lire(dossier / "listes_de_soin.yaml")
    _exiger(isinstance(listes, dict) and listes.get("listes"), "listes_de_soin.yaml : pas de listes")
    for liste in listes["listes"]:
        _exiger(liste.get("marque") == MARQUE_LISTE, f"liste « {liste.get('id')} » : la marque « exemple inventé » manque")
        _exiger(liste.get("points"), f"liste « {liste.get('id')} » : aucun point")
    connues = {liste["id"] for liste in listes["listes"]}
    for p in patients:
        for prevue in p["CarePlan"]:
            _exiger(prevue in connues, f"{p['Patient']['id']} : liste de soin inconnue « {prevue} »")

    lieux = _lire(dossier / "lieux.yaml")
    _exiger(lieux.get("marque") == "inventé", "lieux.yaml : la marque « inventé » manque")
    noms = {lieu["nom"] for lieu in lieux["lieux"]}
    for v in lieux["voisins"]:
        _exiger(v["de"] in noms and v["a"] in noms and v["metres"] > 0, f"lieux.yaml : voisinage incorrect {v}")

    reserve = _lire(dossier / "reserve.yaml")
    _exiger(reserve.get("marque") == "inventé", "reserve.yaml : la marque « inventé » manque")
    feuilles = _lire(dossier / "feuilles_sans_patient.yaml")
    for feuille in feuilles["feuilles"]:
        _exiger(feuille.get("marque") == "INVENTÉ" and "INVENTÉ" in feuille.get("texte", ""),
                "feuilles_sans_patient.yaml : une feuille ne porte pas « INVENTÉ »")

    return FauxDossier(patients=_geler(patients), listes=_geler(listes["listes"]), lieux=_geler(lieux),
                       reserve=_geler(reserve["objets"]), reserve_marque=reserve["marque"],
                       feuilles_sans_patient=_geler(feuilles["feuilles"]))
