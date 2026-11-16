"""La clinique en boîte — N02, les pages vues dans un vrai navigateur, dernier passage (message de Hiba du 12.11.2026).

« Le même contrôle que N01 », sur toutes les pages, y compris celles faites après N01 (tours 80 à 99).
Ici : la mesure en largeur de téléphone (375 points) dans Chrome, la même que l'essai établi `test_pages_sur_telephone.py`
(réutilisée telle quelle, pas changée), pour les pages nouvelles. Le passage complet (images, boutons pressés, erreurs du
navigateur) est fait par `outils/pages_vues_chrome.py --n02` et écrit dans docs/projet/PAGES_VUES.md.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique.carnet import Carnet
from briques.clinique.ecrans import brancher_ecrans
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.porte import JournalDesAcces, PorteDeLecture
from briques.clinique.tests.test_pages_sur_telephone import CHROME, LARGEUR, PAGES as PAGES_N01, _mesurer

NOUVELLES = ["/clinique/tableau-de-flotte", "/clinique/fiche-de-verite", "/clinique/invite", "/clinique/telephones",
             "/clinique/preuves", "/clinique/preuves/essais", "/clinique/preuves/brancher", "/clinique/ou-tourne-quoi",
             "/clinique/capacites", "/clinique/concours", "/clinique/avis", "/clinique/avis/donner"]

pytestmark = pytest.mark.skipif(not CHROME.exists(), reason="Chrome n'est pas sur cet ordinateur : les pages ne sont pas mesurées")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    horloge, app = HorlogeDeDemonstration(), FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge), code_equipe="")
    clinique.faux_logiciel.dossier = tmp_path_factory.mktemp("faux_logiciel")
    clinique.avis.fichier = tmp_path_factory.mktemp("avis") / "avis.jsonl"
    return TestClient(app), clinique


def test_les_pages_nouvelles_ne_sont_pas_deja_mesurees_ailleurs():
    assert not set(NOUVELLES) & set(PAGES_N01)


def test_aucune_page_nouvelle_ne_depasse_en_largeur_de_telephone(client, tmp_path):
    http, clinique = client
    tache = clinique.taches.demander(clinique.badges["soignant-etage-2"], "p01", "la couverture")["tache"]
    clinique.tableau_de_flotte.repartiteur.attribuer(clinique.taches, tache["id"])  # pour que le tableau et « Pourquoi ? » aient une course
    chemins = NOUVELLES + [f"/clinique/flotte/pourquoi?tache={tache['id']}"]
    pages = {}
    for chemin in chemins:
        reponse = http.get(chemin)
        assert reponse.status_code == 200, chemin
        assert "DONNÉES INVENTÉES" in reponse.text, chemin
        pages[chemin] = reponse.text
    mesures = _mesurer(pages, tmp_path)
    assert set(mesures) == set(chemins)
    trop_larges = {c: m for c, m in mesures.items() if m["depassent"] or m["page"] > LARGEUR}
    assert not trop_larges, trop_larges
