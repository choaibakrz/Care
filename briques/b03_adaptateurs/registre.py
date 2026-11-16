"""Brique 3 — Le registre : le SEUL endroit qui fabrique l'adaptateur d'un robot de robots/.

NON TESTÉ SUR VRAI ROBOT. Deux usages, et seulement deux (test_aucun_contournement.py le vérifie) :
- `fabriquer` : appelé par commun/systeme.py (_creer_adaptateur), qui donne l'adaptateur directement à la prise
  (PRISE.md : « un adaptateur ne se fabrique que dans commun/systeme.py ») ;
- `fabrique_pour_conformite` : pour le test de conformité (python3 lancer.py brancher NOM --conformite).

Verrou en plus : un VRAI robot n'est accepté que si son test de conformité complet a réussi sur lui, AVEC les mêmes
fichiers (empreintes de carte.yaml, liaison.py, adaptateur.py gardées dans robots/NOM/conformite.yaml). Changer la
carte ou la liaison après le test = refaire le test. C'est une protection contre l'OUBLI, pas contre quelqu'un (ou un
agent) qui réécrirait conformite.yaml : la vraie garde reste le feu orange (le « oui » de Hiba, le responsable
sécurité, la main sur l'arrêt physique).
"""
from __future__ import annotations

import hashlib
import importlib
import importlib.util
import keyword
import re
import sys
from pathlib import Path
from typing import Any, Callable

import yaml

from briques.b01_prise.adaptateur import Adaptateur

ICI = Path(__file__).resolve().parent
DOSSIER_ROBOTS = ICI / "robots"
FICHIERS_EMPREINTE = ("carte.yaml", "liaison.py", "adaptateur.py")


def nom_valide(nom: str) -> str | None:
    """Rend l'explication du problème, ou None si le nom est bon."""
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,30}", nom or ""):
        return "le nom doit faire 2 à 31 caractères : lettres minuscules sans accent, chiffres, « _ » (ex. unitree_g1)"
    if keyword.iskeyword(nom) or nom in ("tests", "test", "robots"):
        return f"« {nom} » est un mot réservé"
    return None


def charger_robot(nom: str, dossier: Path = DOSSIER_ROBOTS) -> Any:
    """Le module adaptateur.py du robot (sans rien lancer). Hors du projet (tests) : chargé par son chemin."""
    dossier = Path(dossier).resolve()
    if dossier == DOSSIER_ROBOTS.resolve():
        return importlib.import_module(f"briques.b03_adaptateurs.robots.{nom}.adaptateur")
    paquet = f"robot_hors_projet_{hashlib.sha1(str(dossier).encode()).hexdigest()[:8]}_{nom}"
    if paquet not in sys.modules:
        spec = importlib.util.spec_from_file_location(paquet, dossier / nom / "__init__.py",
                                                      submodule_search_locations=[str(dossier / nom)])
        module = importlib.util.module_from_spec(spec)
        sys.modules[paquet] = module
        spec.loader.exec_module(module)
    return importlib.import_module(paquet + ".adaptateur")


def empreintes(ici: Path) -> dict[str, str]:
    """L'empreinte (SHA-256) des fichiers qui décident de ce que fait le robot : la moindre modification la change."""
    return {f: hashlib.sha256((Path(ici) / f).read_bytes()).hexdigest() for f in FICHIERS_EMPREINTE
            if (Path(ici) / f).exists()}


def raison_refus_vrai(ici: Path) -> str | None:
    """Pourquoi le vrai robot n'est pas (encore) accepté ; None s'il l'est."""
    fichier = Path(ici) / "conformite.yaml"
    if not fichier.exists():
        return "aucun test de conformité sur le vrai robot"
    complet = (yaml.safe_load(fichier.read_text(encoding="utf-8")) or {}).get("complet") or {}
    if not complet.get("reussi"):
        return "le test de conformité complet n'a pas réussi"
    if complet.get("empreintes") != empreintes(ici):
        return "la carte, la liaison ou l'adaptateur ont changé depuis le test complet : le refaire"
    return None


def conformite_reussie(ici: Path) -> bool:
    return raison_refus_vrai(ici) is None


def sur_faux_kit(adaptateur: object) -> bool:
    """Vrai SEULEMENT si un adaptateur de la brique 3 tourne sur un faux kit DU PROJET (ses classes, pas un attribut qui
    leur ressemble). Sert au système : personnes simulées et mention « testé sur faux robot » (relecture du lot B)."""
    from .chemins.ros2.faux_ros2 import FauxRclpy
    from .chemins.sdk.faux_sdk import FauxKit
    from .modele_vide.adaptateur import AdaptateurModele

    if type(adaptateur) is not AdaptateurModele and not isinstance(adaptateur, AdaptateurModele):
        return False
    liaison = getattr(adaptateur, "_liaison", None)
    return isinstance(getattr(liaison, "kit", None), FauxKit) or isinstance(getattr(liaison, "rclpy", None), FauxRclpy)


def _verifier(adaptateur: Adaptateur, vrai: bool, nom: str) -> Adaptateur:
    """Après fabrication : ce qui a été fabriqué est-il bien ce qui était demandé (vrai robot ou faux kit) ?"""
    faux = sur_faux_kit(adaptateur)
    if vrai and faux:
        raise ValueError(f"« {nom} » : un vrai robot était demandé, mais l'adaptateur tourne sur le faux kit")
    if not vrai and not faux:
        raise ValueError(f"« {nom} » : le faux kit était demandé (vrai_robot: false), mais l'adaptateur parle à un vrai "
                         f"robot. Corriger reglages.yaml ou adaptateur.py")
    if adaptateur.carte().vrai_robot != vrai:
        raise ValueError(f"« {nom} » : la carte dit vrai_robot={adaptateur.carte().vrai_robot}, attendu {vrai}")
    return adaptateur


def fabriquer(nom: str, reglages: dict, dossier: Path = DOSSIER_ROBOTS, bus: Any = None) -> Adaptateur:
    """reglages.yaml → robot.adaptateur = NOM ; robot.vrai_robot = true pour le vrai robot (sinon le faux kit).
    `bus` (facultatif) : l'adaptateur note dans la boîte noire ce qu'il remarque (arrêt sauté, chien de garde…)."""
    probleme = nom_valide(nom)
    if probleme or not (Path(dossier) / nom / "adaptateur.py").exists():
        raise ValueError(f"Adaptateur inconnu : {nom}. Le créer : python3 lancer.py brancher {nom} --genre … --chemin …")
    vrai = bool(reglages["robot"].get("vrai_robot"))
    refus = raison_refus_vrai(Path(dossier) / nom) if vrai else None
    if refus:
        raise ValueError(f"Le vrai robot « {nom} » n'est pas accepté : {refus}. Test de conformité complet "
                         f"(feu orange) : python3 lancer.py brancher {nom} --conformite --vrai --complet")
    module = charger_robot(nom, dossier)
    adaptateur = module.fabriquer(vrai=vrai, delai_chien_s=float(reglages["securite"]["delai_chien_de_garde_s"]), bus=bus)
    return _verifier(adaptateur, vrai, nom)


def fabrique_pour_conformite(nom: str, dossier: Path = DOSSIER_ROBOTS, vrai: bool = False,
                             lent: bool = False) -> Callable[[], Adaptateur]:
    """Pour le test de conformité seulement : de quoi fabriquer un adaptateur neuf à chaque essai."""
    module = charger_robot(nom, dossier)
    return lambda: _verifier(module.fabriquer(vrai=vrai, lent=lent), vrai, nom)
