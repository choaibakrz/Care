"""La clinique en boîte — L02b, la page du faux logiciel administratif et les deux liens (avenant 4, L02 ; seconde moitié).

« Fini » veut dire :
- la page « Faux logiciel administratif » porte l'étiquette SIMULÉ ; elle montre la liste et un bouton par sorte de message ;
- chaque bouton écrit un message de la bonne sorte ; un patient verrouillé ne bouge pas ;
- « Remettre le faux logiciel à zéro » vide les messages et remet les trois personnes en attente ;
- « Ouvrir l'assistant » ouvre notre écran sur le bon patient, avec seulement le numéro du patient et le numéro du séjour,
  jamais un nom ; on choisit son badge, et la porte décide de ce qu'on voit ;
- sur notre écran de l'accueil, un bouton ouvre la fiche du patient dans le faux logiciel ;
- chaque message envoyé est noté dans la boîte noire, avec l'étiquette SIMULÉ.
Le faux logiciel reste à part : sa page est dans son dossier, et n'importe aucune pièce de la clinique.
"""
from __future__ import annotations

import html
import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique.carnet import Carnet
from briques.clinique.ecrans import brancher_ecrans
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.porte import JournalDesAcces, PorteDeLecture
from commun.bus import Bus
from faux_logiciel_admin import logiciel

CODE = {"X-Code-Equipe": "code-d-essai"}


@pytest.fixture
def banc(tmp_path):
    bus = Bus()
    horloge, app = HorlogeDeDemonstration(bus=bus), FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge), code_equipe="code-d-essai")
    clinique.faux_logiciel.dossier = tmp_path / "faux_logiciel"  # jamais le vrai dossier du journal
    clinique.faux_logiciel.remettre_a_zero()
    return TestClient(app), clinique, bus


def _page(client, chemin, **plus):
    return html.unescape(client.get(chemin, headers=CODE, **plus).text)


# ---------------------------------------------------------------------------------------------- la page
def test_la_page_porte_l_etiquette_simule_et_montre_la_liste(banc):
    client, clinique, _ = banc
    page = _page(client, "/faux-logiciel")
    assert "Faux logiciel administratif" in page and page.count("SIMULÉ") >= 2 and "DONNÉES INVENTÉES" in page
    for mot in ("p01", "s01", "Madame Giulia B.", "verrouillé", "p13", "en attente", "Assurance Exemple",
                "Remettre le faux logiciel à zéro", "Ouvrir l'assistant", "Ce n'est pas un vrai logiciel de clinique"):
        assert mot in page, mot
    for sorte in logiciel.SORTES.values():
        assert sorte["bouton"] in page, sorte["bouton"]
    assert "raison" not in page.lower() and "compatible" not in page.lower()


def test_la_page_n_est_pas_un_de_nos_ecrans_et_ne_s_ouvre_pas_sans_le_code_depuis_ailleurs(banc):
    client, _, _ = banc
    assert client.get("/faux-logiciel").status_code == 403  # la liste porte des noms : pas sans le code d'équipe
    import ast

    page = Path(logiciel.__file__).parent / "page.py"  # la page est dans le dossier du faux logiciel, pas dans le nôtre
    for noeud in ast.walk(ast.parse(page.read_text(encoding="utf-8"))):
        modules = [a.name for a in noeud.names] if isinstance(noeud, ast.Import) else \
            [noeud.module or ""] if isinstance(noeud, ast.ImportFrom) and noeud.level == 0 else []
        assert not any(m.startswith(("briques", "commun")) for m in modules), modules
    assert "Tous les écrans" not in client.get("/faux-logiciel", headers=CODE).text  # ni notre pied de page, ni notre style


# ---------------------------------------------------------------------------------------------- les boutons
def test_chaque_bouton_ecrit_un_message_de_la_bonne_sorte(banc):
    client, clinique, _ = banc
    suite = [("A05", {}), ("A01", {"chambre": "11"}), ("A02", {"chambre": "13"}), ("A08", {"champ": "langue", "valeur": "de"}),
             ("A21", {}), ("A22", {}), ("A03", {}), ("A13", {}), ("A11", {})]
    for sorte, plus in suite:
        r = client.post("/api/faux-logiciel/evenement", json={"sorte": sorte, "numero_patient": "p13", **plus}, headers=CODE)
        assert r.status_code == 200, (sorte, r.text)
        assert r.json()["message"]["sorte"] == sorte and r.json()["message"]["etiquette"] == "SIMULÉ"
    fichiers = clinique.faux_logiciel.messages()
    assert [f.name.split("_")[1] for f in fichiers] == [s for s, _ in suite]
    assert "0009_A11_p13.hl7" in _page(client, "/faux-logiciel")  # la page montre les messages écrits


def test_un_patient_verrouille_ne_bouge_pas_et_la_page_le_dit(banc):
    client, clinique, _ = banc
    r = client.post("/api/faux-logiciel/evenement", json={"sorte": "A03", "numero_patient": "p01"}, headers=CODE)
    assert r.status_code == 400 and "verrouillé" in r.json()["detail"]
    assert clinique.faux_logiciel.messages() == []
    assert client.post("/api/faux-logiciel/evenement", json={"sorte": "A03", "numero_patient": "p13"}).status_code == 403


def test_remettre_a_zero(banc):
    client, clinique, _ = banc
    client.post("/api/faux-logiciel/evenement", json={"sorte": "A01", "numero_patient": "p14", "chambre": "12"}, headers=CODE)
    assert len(clinique.faux_logiciel.messages()) == 1
    assert client.post("/api/faux-logiciel/zero", headers=CODE).status_code == 200
    assert clinique.faux_logiciel.messages() == []
    assert sum(1 for p in clinique.faux_logiciel.liste() if p["statut"] == "en attente") == 3


def test_l_heure_des_messages_est_celle_de_l_horloge_de_demonstration(banc):
    client, clinique, _ = banc
    etat = clinique.horloge.etat()
    r = client.post("/api/faux-logiciel/evenement", json={"sorte": "A05", "numero_patient": "p15"}, headers=CODE)
    msh = r.json()["message"]["texte"].splitlines()[0].split("|")
    assert msh[6].endswith(etat["heure"].replace(":", ""))


# ---------------------------------------------------------------------------------------------- la boîte noire
def test_chaque_message_est_note_dans_la_boite_noire_avec_simule(banc):
    client, _, bus = banc
    client.post("/api/faux-logiciel/evenement", json={"sorte": "A01", "numero_patient": "p13", "chambre": "11"}, headers=CODE)
    notes = [e.donnees for e in bus.historique if e.type == "note" and e.donnees.get("quoi") == "message_du_faux_logiciel"]
    assert len(notes) == 1
    note = notes[0]
    assert note["etiquette"] == "SIMULÉ" and note["sorte"] == "A01" and note["numero_patient"] == "p13" and note["numero_sejour"] == "s13"
    assert note["fichier"] == "0001_A01_p13.hl7" and "Paolo" not in str(note)  # des numéros, pas de nom


# ---------------------------------------------------------------------------------------------- les deux liens
def test_ouvrir_l_assistant_passe_seulement_les_deux_numeros(banc):
    client, _, _ = banc
    page = client.get("/faux-logiciel", headers=CODE).text
    liens = re.findall(r"href=['\"](/clinique/ouvrir\?[^'\"]+)['\"]", page)
    assert len(liens) == 15
    for lien in liens:
        assert re.fullmatch(r"/clinique/ouvrir\?patient=p\d\d&(amp;)?sejour=s\d\d", lien), lien  # jamais un nom


def test_ouvrir_l_assistant_ouvre_le_bon_patient_et_la_porte_decide(banc):
    client, _, _ = banc
    choix = _page(client, "/clinique/ouvrir?patient=p01&sejour=s01")
    assert "Choisissez votre badge" in choix and "Giulia" not in choix  # sans badge : aucun nom
    assert "numéro de patient p01" in choix and "numéro de séjour s01" in choix
    soignant = _page(client, "/clinique/ouvrir?patient=p01&sejour=s01&badge=soignant-etage-2")
    assert "Madame Giulia B." in soignant and "Chambre 12" in soignant.replace("chambre", "Chambre")
    assert "Monsieur Hans K." not in soignant  # le bon patient, lui seul
    robot = _page(client, "/clinique/ouvrir?patient=p01&sejour=s01&badge=robot-r1")
    assert "Giulia" not in robot and "refus" in robot.lower()
    therapeute = _page(client, "/clinique/ouvrir?patient=p02&sejour=s02&badge=therapeute-exemple")
    assert ("Hans" in therapeute) or ("refus" in therapeute.lower())  # la porte décide, selon ses patients
    inconnu = _page(client, "/clinique/ouvrir?patient=p13&sejour=s13&badge=soignant-etage-2")
    assert "Paolo" not in inconnu and "ne la connaît pas" in inconnu  # notre système ne connaît pas encore cette personne


def test_l_ecran_de_l_accueil_ouvre_la_fiche_dans_le_faux_logiciel(banc):
    client, _, _ = banc
    accueil = client.get("/clinique/accueil").text
    liens = re.findall(r"href=['\"](/faux-logiciel/fiche\?patient=p\d\d)['\"]", accueil)
    assert liens and all("Giulia" not in l for l in liens)
    fiche = _page(client, liens[0])
    assert "SIMULÉ" in fiche and "numéro du séjour" in fiche.lower() and "Assurance Exemple" in fiche
    assert "raison" not in fiche.lower()
    assert client.get("/faux-logiciel/fiche?patient=p99", headers=CODE).status_code == 404
