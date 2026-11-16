"""Garde-fou du 15.11.2026 : pendant les essais, les réglages chargés ont toujours le FAUX robot.

Le fichier reglages.yaml de cet ordinateur peut désigner un vrai robot (la main, la tête) pour la démonstration.
Aucun essai ne doit alors s'y connecter : conftest.py remplace le chargement des réglages pour toute la durée des essais.
"""
import os

import yaml

from commun import systeme
from commun.systeme import charger_reglages


def test_les_reglages_charges_pendant_les_essais_ont_toujours_le_faux_robot(tmp_path):
    reglages = charger_reglages()
    assert reglages["robot"]["adaptateur"] == "faux_robot" and reglages["robot"]["vrai_robot"] is False
    # même avec un fichier qui désigne un vrai robot, donné exprès
    vrai = yaml.safe_load(systeme.REGLAGES_EXEMPLE.read_text(encoding="utf-8"))
    vrai["robot"].update({"adaptateur": "leadtron_dh116", "vrai_robot": True})
    fichier = tmp_path / "reglages_vrai_robot.yaml"
    fichier.write_text(yaml.safe_dump(vrai, allow_unicode=True), encoding="utf-8")
    charge = systeme.charger_reglages(fichier)
    assert charge["robot"]["adaptateur"] == "faux_robot" and charge["robot"]["vrai_robot"] is False
    assert charge["robot"]["carte"]  # une carte de faux robot est toujours là


def test_le_kit_de_la_main_pointe_vers_un_dossier_vide_pendant_les_essais():
    assert os.environ.get("LEADTRON_KIT") == "/var/empty"
