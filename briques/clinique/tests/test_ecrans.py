"""La clinique en boîte — T05, les quatre écrans (cahier 5.4), plus la page du thérapeute et la page du journal.

« Fini » veut dire :
- les pages répondent à l'adresse du réseau local, celle qu'un téléphone utiliserait ;
- on choisit son badge en haut de l'écran ;
- le bandeau « DONNÉES INVENTÉES — DÉMONSTRATION », l'heure de l'horloge, le badge et les étiquettes sont là ;
- aucun écran ne lit les fichiers sans passer par la porte.
Internet coupé, aucun modèle, aucun robot.
"""
from __future__ import annotations

import ast
import asyncio
import builtins
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique import dossier as faux_dossier
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.porte import JournalDesAcces, PorteDeLecture, charger_badges

RACINE = Path(__file__).resolve().parents[3]
BANDEAU = "DONNÉES INVENTÉES — DÉMONSTRATION"
PAGES = {"patient": "patient-p01", "soignant": "soignant-etage-2", "medecin": "medecin-exemple",
         "accueil": "accueil", "therapeute": "therapeute-exemple"}


def _clinique():
    from briques.clinique.ecrans import brancher_ecrans

    horloge = HorlogeDeDemonstration()
    porte = PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour)
    app = FastAPI()
    brancher_ecrans(app, porte=porte, horloge=horloge)
    return TestClient(app), porte, horloge


# ---------------------------------------------------------------- les pages
def test_il_y_a_cinq_ecrans_et_une_page_d_entree():
    from briques.clinique.ecrans import ECRANS

    assert set(ECRANS) == set(PAGES)
    client, _, _ = _clinique()
    entree = client.get("/clinique")
    assert entree.status_code == 200 and BANDEAU in entree.text
    for ecran in PAGES:
        assert f'href="/clinique/{ecran}"' in entree.text
    assert 'href="/clinique/journal"' in entree.text


@pytest.mark.parametrize("ecran", sorted(PAGES))
def test_chaque_ecran_porte_le_bandeau_l_heure_le_badge_et_les_etiquettes(ecran):
    client, _, _ = _clinique()
    page = client.get(f"/clinique/{ecran}")
    assert page.status_code == 200
    assert BANDEAU in page.text
    assert "Jour 1 — 9 h 00" in page.text  # l'heure de l'horloge de démonstration
    assert charger_badges()[PAGES[ecran]].libelle in page.text  # le badge choisi
    for etiquette in ("RÉEL", "FAUX ROBOT", "SIMULÉ", "JOUÉ"):
        assert etiquette in page.text
    assert 'name="viewport"' in page.text  # lisible sur un téléphone
    assert "http://" not in page.text and "https://" not in page.text  # rien ne vient d'Internet


def test_on_choisit_son_badge_en_haut_de_l_ecran():
    client, porte, _ = _clinique()
    page = client.get("/clinique/soignant")
    assert "<select" in page.text and 'value="soignant-etage-2"' in page.text
    # un badge d'un autre métier n'est pas proposé sur cet écran
    assert 'value="medecin-exemple"' not in page.text
    # le badge choisi décide de ce qu'on voit
    soignant = client.get("/api/clinique/ecran/soignant", params={"badge": "soignant-etage-2"}).json()
    assert soignant["badge"]["id"] == "soignant-etage-2"
    assert {p["id"] for p in soignant["donnees"]["patients"]} == {p["id"] for p in porte.patients(
        charger_badges()["soignant-etage-2"])}


def test_un_badge_qui_n_est_pas_du_bon_metier_est_refuse_et_note():
    client, porte, _ = _clinique()
    avant = len(porte.journal.lignes())
    reponse = client.get("/api/clinique/ecran/medecin", params={"badge": "soignant-etage-2"}).json()
    assert reponse["refuse"] is True and "donnees" not in reponse
    page = client.get("/clinique/medecin", params={"badge": "soignant-etage-2"})
    assert page.status_code == 200 and BANDEAU in page.text
    assert "réadaptation" not in page.text  # la raison du séjour ne sort pas
    refus = [l for l in porte.journal.lignes()[avant:] if l["resultat"] == "refusé"]
    assert len(refus) == 2 and all(l["qui"] == "soignant-etage-2" for l in refus)
    assert client.get("/api/clinique/ecran/medecin", params={"badge": "inconnu"}).status_code == 404
    assert client.get("/clinique/nulle-part").status_code == 404


# ---------------------------------------------------------------- ce que chaque écran montre
def test_le_soignant_voit_ses_patients_sans_la_raison_du_sejour():
    client, _, _ = _clinique()
    texte = client.get("/clinique/soignant/contenu", params={"badge": "soignant-etage-2"}).text
    assert "Madame Giulia B." in texte and "aime qu&#x27;on frappe deux fois avant d&#x27;entrer" in texte
    assert "réadaptation" not in texte


def test_le_medecin_voit_la_raison_l_accueil_non():
    client, _, _ = _clinique()
    assert "réadaptation après une opération de la hanche" in client.get("/clinique/medecin/contenu").text
    accueil = client.get("/clinique/accueil/contenu").text
    assert "Madame Giulia B." in accueil and "réadaptation" not in accueil and "déambulateur" not in accueil


def test_le_patient_ne_voit_que_lui_dans_sa_langue():
    client, _, _ = _clinique()
    texte = client.get("/clinique/patient/contenu").text  # p01 parle italien
    assert "Madame Giulia B." in texte and "Il mio programma di oggi" in texte
    assert "fisioterapia" in texte and "visita del medico" not in texte  # le programme du jour 1 seulement (en italien : Q25, H03b)
    for langue, titre in {"fr": "Mon programme du jour", "de": "Mein Programm heute", "en": "My programme today"}.items():
        assert titre in client.get("/clinique/patient/contenu", params={"langue": langue}).text
    autres = [p["Patient"]["nom_affiche"] for p in faux_dossier.charger().patients if p["Patient"]["id"] != "p01"]
    assert not any(nom in texte for nom in autres)


def test_soignant_et_medecin_en_francais_et_en_allemand():
    client, _, _ = _clinique()
    assert "Mes patients" in client.get("/clinique/soignant/contenu").text
    assert "Meine Patienten" in client.get("/clinique/soignant/contenu", params={"langue": "de"}).text
    assert "Meine Patienten" in client.get("/clinique/medecin/contenu", params={"langue": "de"}).text


def test_le_therapeute_voit_le_programme_de_ses_patients():
    client, _, _ = _clinique()
    texte = client.get("/clinique/therapeute/contenu").text
    assert "Madame Giulia B." in texte and "physiothérapie" in texte and "déambulateur" not in texte


# ---------------------------------------------------------------- l'horloge
def test_l_ecran_suit_l_horloge_et_montre_temps_accelere():
    client, _, horloge = _clinique()
    assert "TEMPS ACCÉLÉRÉ" not in client.get("/clinique/accueil").text
    assert "Madame Giulia B." in client.get("/clinique/accueil/contenu").text  # elle arrive le jour 1
    asyncio.run(horloge.sauter("le lendemain matin"))
    page = client.get("/clinique/accueil")
    assert "Jour 2 — 7 h 30" in page.text and "TEMPS ACCÉLÉRÉ" in page.text
    assert "Madame Giulia B." not in client.get("/clinique/accueil/contenu").text  # plus une arrivée du jour
    etat = client.get("/api/clinique/horloge").json()
    assert etat["jour"] == 2 and etat["temps_accelere"] is True
    assert "visita del medico" in client.get("/clinique/patient/contenu").text  # le programme du jour 2 (en italien : Q25, H03b)


def test_la_page_se_rafraichit_toute_seule_toutes_les_deux_secondes():
    client, _, _ = _clinique()
    page = client.get("/clinique/soignant").text
    assert "/clinique/soignant/contenu" in page and "2000" in page and "setInterval" in page


# ---------------------------------------------------------------- tout passe par la porte
def test_le_code_des_ecrans_ne_touche_ni_au_faux_dossier_ni_aux_fichiers():
    """Lecture du code : les écrans n'importent que la porte et l'horloge, et n'ouvrent aucun fichier."""
    arbre = ast.parse((RACINE / "briques/clinique/ecrans.py").read_text(encoding="utf-8"))
    importes, appels, noms = set(), set(), set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            importes |= {a.name for a in noeud.names}
        elif isinstance(noeud, ast.ImportFrom):
            importes |= {f"{'.' * noeud.level}{noeud.module or ''}:{a.name}" for a in noeud.names}
        elif isinstance(noeud, ast.Call):
            f = noeud.func
            appels.add(f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", ""))
        elif isinstance(noeud, ast.Attribute):
            noms.add(noeud.attr)
        elif isinstance(noeud, ast.Name):
            noms.add(noeud.id)
    assert not any("dossier" in i or "yaml" in i or "pathlib" in i or i in ("os", "io", "glob") for i in importes), importes
    assert not appels & {"open", "read_text", "read_bytes", "safe_load", "charger", "glob", "iterdir"}, appels
    assert not noms & {"dossier", "faux_dossier", "_visibles", "_vue"}, "les écrans ne fouillent pas dans la porte"


def test_les_ecrans_marchent_alors_que_les_fichiers_du_faux_dossier_sont_interdits(monkeypatch):
    """Une fois la porte ouverte, on interdit toute lecture des fichiers du faux dossier : les écrans marchent encore."""
    client, porte, _ = _clinique()
    interdit = str(RACINE / "briques/clinique/faux_dossier")
    lectures_interdites: list[str] = []
    open_original, read_text_original = builtins.open, Path.read_text

    def open_surveille(fichier, *a, **k):
        if str(fichier).startswith(interdit):
            lectures_interdites.append(str(fichier))
            raise AssertionError(f"lecture directe du faux dossier : {fichier}")
        return open_original(fichier, *a, **k)

    def read_text_surveille(self, *a, **k):
        if str(self).startswith(interdit):
            lectures_interdites.append(str(self))
            raise AssertionError(f"lecture directe du faux dossier : {self}")
        return read_text_original(self, *a, **k)

    def charger_interdit(*a, **k):
        lectures_interdites.append("dossier.charger")
        raise AssertionError("les écrans n'ont pas le droit de charger le faux dossier")

    monkeypatch.setattr(builtins, "open", open_surveille)
    monkeypatch.setattr(Path, "read_text", read_text_surveille)
    monkeypatch.setattr(faux_dossier, "charger", charger_interdit)
    for ecran, badge in PAGES.items():
        avant = len(porte.journal.lignes())
        assert client.get(f"/clinique/{ecran}", params={"badge": badge}).status_code == 200
        assert client.get(f"/clinique/{ecran}/contenu", params={"badge": badge}).status_code == 200
        assert client.get(f"/api/clinique/ecran/{ecran}", params={"badge": badge}).status_code == 200
        lus = [l for l in porte.journal.lignes()[avant:] if l["qui"] == badge and l["resultat"] == "lu"]
        assert len(lus) >= 3, f"l'écran « {ecran} » n'a pas laissé de trace au journal des accès"
    assert lectures_interdites == []


def test_l_ecran_montre_ce_que_la_porte_donne_et_rien_d_autre(monkeypatch):
    """On remplace la réponse de la porte par une personne qui n'existe dans aucun fichier : c'est elle qu'on voit."""
    client, porte, _ = _clinique()
    sentinelle = {"id": "p99", "nom": "Madame Sentinelle Z.", "langue": "fr", "chambre": 99, "etage": 2, "programme": []}
    monkeypatch.setattr(porte, "patients", lambda badge: [dict(sentinelle)])
    for ecran in ("soignant", "medecin", "accueil", "therapeute"):
        texte = client.get(f"/clinique/{ecran}/contenu").text
        assert "Madame Sentinelle Z." in texte and "Giulia" not in texte


# ---------------------------------------------------------------- la page du journal des accès
def test_une_page_montre_le_journal_des_acces():
    client, _, _ = _clinique()
    client.get("/clinique/soignant/contenu")
    client.get("/api/clinique/ecran/medecin", params={"badge": "soignant-etage-2"})  # un refus
    page = client.get("/clinique/journal")
    assert page.status_code == 200 and BANDEAU in page.text
    assert "soignant-etage-2" in page.text and "lu" in page.text and "refusé" in page.text
    assert "Giulia" not in page.text  # des numéros de dossier, pas de noms
    lignes = client.get("/api/clinique/journal").json()["lignes"]
    assert lignes and {"quand", "qui", "quoi", "resultat"} <= set(lignes[-1])


# ---------------------------------------------------------------- branché sur l'écran de l'ossature
def test_les_ecrans_sont_servis_avec_l_ecran_du_jury_et_les_sauts_vont_dans_la_boite_noire(fabrique_systeme):
    from briques.b13_ecran.serveur import creer_app
    from briques.clinique.ecrans import brancher_ecrans

    systeme = fabrique_systeme()
    app = creer_app(systeme)
    horloge = HorlogeDeDemonstration(bus=systeme.bus)  # comme dans lancer.py : les sauts partent sur le bus
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge)
    with TestClient(app) as client:
        assert client.get("/jury").status_code == 200  # l'écran du jury est toujours là
        assert BANDEAU in client.get("/clinique/soignant").text
        client.portal.call(clinique.horloge.sauter, "le soir")
        assert "TEMPS ACCÉLÉRÉ" in client.get("/clinique/soignant").text
    assert any(e.type == "note" and e.donnees.get("quoi") == "saut_horloge" for e in systeme.bus.historique)


# ---------------------------------------------------------------- l'adresse du réseau local
def test_les_pages_repondent_a_l_adresse_du_reseau_local():
    """Dans un programme à part (ici, Internet est coupé pour les essais, et l'adresse du Wi-Fi n'est pas « locale »
    au sens de conftest.py). Le programme lance le serveur sur un port libre et demande les pages à l'adresse que
    cet ordinateur a sur le réseau local, celle qu'un téléphone utiliserait. Rien ne sort de l'ordinateur."""
    sortie = subprocess.run([sys.executable, "-m", "briques.clinique.essai_reseau"], cwd=RACINE,
                            capture_output=True, text=True, timeout=60)
    if sortie.returncode == 3:
        pytest.skip("cet ordinateur n'a pas d'adresse sur un réseau local en ce moment : " + sortie.stdout.strip())
    assert sortie.returncode == 0, sortie.stdout + sortie.stderr
    assert "ESSAI RÉSEAU : 7 pages sur 7" in sortie.stdout
    assert "127.0.0.1" not in sortie.stdout and "localhost" not in sortie.stdout
