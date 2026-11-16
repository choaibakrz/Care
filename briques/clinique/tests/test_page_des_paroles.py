"""La clinique en boîte — J06b-b, la page « Ce qu'on nous a dit » lit le fichier de l'équipe (réponse de Hiba à Q26 : A).

« Fini » veut dire :
- la page lit le fichier de l'équipe (`journal/clinique/PAROLES_DES_SOIGNANTS.md`), et seulement lui, par la pièce de
  lecture (paroles_fichier.py) ; la page elle-même n'ouvre aucun fichier ;
- une parole complète, avec accord, s'affiche avec l'étiquette DIT PAR UN SOIGNANT, son métier et sa date ; une ligne qui
  nomme une personne ou parle d'un patient est mise de côté, sans son texte ;
- tant que l'équipe n'a rien écrit : « Aucune parole recueillie pour l'instant. »
- une parole recueillie ne fait pas passer les listes de soin en « DIT PAR UN SOIGNANT » : elles restent HYPOTHÈSE, parce
  qu'aucun soignant ne les a validées.
Ici, uniquement des paroles d'ESSAI, dans un fichier provisoire : ce programme n'écrit jamais une parole réelle.
"""
from __future__ import annotations

import html
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique import paroles, paroles_fichier
from briques.clinique.carnet import Carnet
from briques.clinique.ecrans import brancher_ecrans
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.porte import JournalDesAcces, PorteDeLecture

BONNE = "- « (phrase d'essai du programme, pas une parole) » — métier : soignante — date : 14.11.2026 — accord : oui"
NOMME = "- « (essai) Madame Dupont dit que… » — métier : soignante — date : 14.11.2026 — accord : oui"


def _page() -> str:
    horloge, app = HorlogeDeDemonstration(), FastAPI()
    brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                    carnet=Carnet(horloge=horloge), code_equipe="")
    client = TestClient(app)
    sans_balises = re.sub(r"<[^>]+>", "", client.get("/clinique/ce-qu-on-nous-a-dit").text)
    return (html.unescape(sans_balises),
            client.get("/clinique/soignant/liste", params={"badge": "soignant-etage-2", "patient": "p01", "liste": "installation"}).text)


@pytest.fixture
def fichier(tmp_path, monkeypatch):
    chemin = tmp_path / "PAROLES_DES_SOIGNANTS.md"
    monkeypatch.setattr(paroles_fichier, "FICHIER", chemin)  # jamais le vrai fichier de l'équipe
    return chemin


def test_sans_fichier_la_page_dit_aucune_parole(fichier):
    page, _ = _page()
    assert paroles.paroles_recueillies() == 0 and "Aucune parole recueillie pour l'instant." in page
    assert "Paroles recueillies : 0" in page


def test_une_parole_complete_s_affiche_avec_son_etiquette_et_une_ligne_qui_nomme_une_personne_est_mise_de_cote(fichier):
    fichier.write_text("# Paroles (essai)\n\n" + BONNE + "\n" + NOMME + "\n", encoding="utf-8")
    page, liste = _page()
    assert paroles.paroles_recueillies() == 1
    assert "DIT PAR UN SOIGNANT — « (phrase d'essai du programme, pas une parole) »" in page
    assert "soignante, 14.11.2026" in page and "Paroles recueillies : 1" in page
    assert "Dupont" not in page and "1 ligne mise de côté" in page
    assert "Aucune parole recueillie pour l'instant." not in page
    assert "HYPOTHÈSE" in liste and "DIT PAR UN SOIGNANT" not in liste  # la liste n'a été validée par aucun soignant


def test_la_page_ne_lit_que_le_fichier_de_l_equipe_par_la_piece_de_lecture():
    import inspect

    source = inspect.getsource(paroles)
    assert "paroles_fichier" in source and "open(" not in source and "read_text" not in source
