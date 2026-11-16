"""La clinique en boîte — T06b, les listes de soin à l'écran (cahier 5.4 et 5.5).

« Fini » veut dire :
- sur l'écran du soignant, on ouvre une liste : elle s'affiche avec les habitudes ; on coche au doigt ;
- « je sors » : cinq points cochés sur six donnent « Il reste un point : la sonnette. » ;
- la page de fin de poste montre ce qui reste, et les trois choix marchent ;
- le point de prise de poste montre mes patients, ce qui a changé, ce qui reste, ce que le poste d'avant n'a pas fini ;
- la direction a une page : des comptes par étage, aucun nom.
Avec T06a, cela finit T06. Internet coupé, aucun modèle, aucun robot.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique.carnet import Carnet
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.porte import JournalDesAcces, PorteDeLecture

RACINE = Path(__file__).resolve().parents[3]
BANDEAU = "DONNÉES INVENTÉES — DÉMONSTRATION"
SOIGNANT = "soignant-etage-2"
P01 = {"badge": SOIGNANT, "patient": "p01", "liste": "installation"}


def _clinique():
    from briques.clinique.ecrans import brancher_ecrans

    horloge = HorlogeDeDemonstration()
    porte = PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour)
    app = FastAPI()
    clinique = brancher_ecrans(app, porte=porte, horloge=horloge, carnet=Carnet(horloge=horloge))
    return TestClient(app), clinique


def _cocher(client, numero, **autres):
    return client.post("/api/clinique/liste/cocher", json={**P01, "numero": numero, **autres})


# ---------------------------------------------------------------- ouvrir une liste, cocher au doigt
def test_l_ecran_du_soignant_mene_aux_listes_de_ses_patients():
    client, _ = _clinique()
    texte = client.get("/clinique/soignant/contenu").text
    assert 'href="/clinique/soignant/liste?badge=soignant-etage-2&amp;patient=p01&amp;liste=installation"' in texte
    assert "Installation à l&#x27;arrivée" in texte  # le titre de la liste, pas son nom de code
    assert 'href="/clinique/soignant/fin-de-poste?badge=soignant-etage-2"' in texte


def test_la_liste_s_affiche_avec_les_habitudes_et_ses_six_points():
    client, _ = _clinique()
    page = client.get("/clinique/soignant/liste", params=P01)
    assert page.status_code == 200 and BANDEAU in page.text and "Jour 1 — 9 h 00" in page.text
    assert "exemple inventé, non médical, à remplacer par les listes de la clinique" in page.text
    assert "Madame Giulia B." in page.text and "entend mal de l&#x27;oreille gauche" in page.text
    assert "Montrer la sonnette et la laisser à portée de main." in page.text
    assert page.text.count("data-cocher=") == 6 and "Je sors" in page.text
    assert "http://" not in page.text and "https://" not in page.text


def test_cinq_coches_au_doigt_puis_je_sors_il_reste_la_sonnette():
    client, clinique = _clinique()
    for numero in (1, 2, 4, 5, 6):
        reponse = _cocher(client, numero)
        assert reponse.status_code == 200 and reponse.json()["etat"] == "fait"
    sortie = client.post("/api/clinique/je_sors", json={"badge": SOIGNANT, "patient": "p01"}).json()
    assert sortie["phrase"] == "Il reste un point : la sonnette."
    contenu = client.get("/clinique/soignant/liste/contenu", params=P01).text
    assert contenu.count("data-cocher=") == 1 and contenu.count("✓") == 5  # il ne reste qu'un bouton
    lignes = clinique.carnet.lignes("point de liste")
    assert len(lignes) == 5 and all(l["qui"] == SOIGNANT and l["valide_par_un_humain"] for l in lignes)
    etats = [p["etat"] for p in client.get("/api/clinique/liste", params=P01).json()["points"]]
    assert etats == ["fait", "fait", "à faire", "fait", "fait", "fait"]


def test_ce_qui_est_refuse_dit_pourquoi_et_n_ecrit_rien():
    client, clinique = _clinique()
    autre_metier = _cocher(client, 1, badge="medecin-exemple")
    assert autre_metier.status_code == 400 and "soignant" in autre_metier.json()["detail"]  # ce point est pour le soignant
    assert _cocher(client, 1, badge="direction").status_code == 403
    assert _cocher(client, 1, badge="patient-p01").status_code == 403
    assert _cocher(client, 1, patient="p05").status_code == 403  # pas à son étage
    assert _cocher(client, 9).status_code == 400  # la liste a six points : on n'en invente pas
    assert _cocher(client, 1, badge="personne").status_code == 404
    venu_d_ailleurs = client.post("/api/clinique/liste/cocher", json={**P01, "numero": 1},
                                  headers={"Origin": "http://autre-site.example"})
    assert venu_d_ailleurs.status_code == 403  # une page d'un autre site ne coche pas à notre place
    assert clinique.carnet.lignes() == []


# ---------------------------------------------------------------- la fin de poste
def test_la_page_de_fin_de_poste_montre_ce_qui_reste_et_les_trois_choix_marchent():
    client, _ = _clinique()
    for numero in (1, 2, 4):
        _cocher(client, numero)
    page = client.get("/clinique/soignant/fin-de-poste", params={"badge": SOIGNANT})
    assert page.status_code == 200 and BANDEAU in page.text
    for choix in ("Le faire", "Le reporter", "Le passer à la relève"):
        assert choix in page.text
    restants = client.get("/api/clinique/fin_de_poste", params={"badge": SOIGNANT}).json()["restants"]
    assert [r["numero"] for r in restants if r["patient"] == "p01" and r["liste"] == "installation"] == [3, 5, 6]

    def choisir(numero, choix, **autres):
        return client.post("/api/clinique/liste/choisir", json={**P01, "numero": numero, "choix": choix, **autres})

    assert choisir(5, "le reporter").status_code == 400  # il faut une raison
    assert choisir(3, "le faire").json()["etat"] == "fait"
    assert choisir(5, "le reporter", raison="la patiente dort").json()["etat"] == "reporté"
    assert choisir(6, "le passer à la relève").json()["etat"] == "passé à la relève"
    restants = client.get("/api/clinique/fin_de_poste", params={"badge": SOIGNANT}).json()["restants"]
    assert not [r for r in restants if r["patient"] == "p01" and r["liste"] == "installation"]
    contenu = client.get("/clinique/soignant/liste/contenu", params=P01).text
    assert "reporté : la patiente dort" in contenu and "passé à la relève" in contenu


# ---------------------------------------------------------------- le point de prise de poste
def test_le_point_de_prise_de_poste():
    client, clinique = _clinique()
    point = client.get("/api/clinique/prise_de_poste", params={"badge": SOIGNANT}).json()
    assert point["mes_patients"] == 4
    assert [c["patient"] for c in point["ce_qui_a_change"]] == ["p01"]  # elle arrive aujourd'hui
    assert point["ce_qui_reste"] > 0 and point["du_poste_d_avant"] == []
    for numero in (1, 2, 4):
        _cocher(client, numero)
    client.post("/api/clinique/liste/choisir", json={**P01, "numero": 5, "choix": "le reporter", "raison": "la patiente dort"})
    client.post("/api/clinique/liste/choisir", json={**P01, "numero": 6, "choix": "le passer à la relève"})
    asyncio.run(clinique.horloge.sauter("le lendemain matin"))
    point = client.get("/api/clinique/prise_de_poste", params={"badge": SOIGNANT}).json()
    avant = {p["numero"]: p for p in point["du_poste_d_avant"]}
    assert set(avant) == {5, 6} and avant[5]["raison"] == "la patiente dort" and avant[6]["etat"] == "passé à la relève"
    assert point["ce_qui_a_change"] == []  # plus d'arrivée du jour
    texte = client.get("/clinique/soignant/contenu").text
    assert "Point de prise de poste" in texte and "Ce que le poste d&#x27;avant n&#x27;a pas fini" in texte
    assert "la salle de bain" in texte and "la patiente dort" in texte and "le déambulateur" in texte
    # la relève fait le point : il quitte la liste du poste d'avant
    _cocher(client, 6)
    point = client.get("/api/clinique/prise_de_poste", params={"badge": SOIGNANT}).json()
    assert [p["numero"] for p in point["du_poste_d_avant"]] == [5]


# ---------------------------------------------------------------- la direction
def test_la_page_de_la_direction_ne_montre_que_des_comptes():
    client, _ = _clinique()
    for numero in (1, 2, 4, 5, 6):
        _cocher(client, numero)
    client.post("/api/clinique/liste/choisir", json={**P01, "numero": 3, "choix": "le reporter", "raison": "la patiente dort"})
    page = client.get("/clinique/direction")
    assert page.status_code == 200 and BANDEAU in page.text and "Direction" in page.text
    assert re.search(r"<td>2</td><td>4</td>.*<td>5</td><td>1</td><td>0</td>", page.text), "étage 2 : 4 patients, 5 faits, 1 reporté"
    for interdit in ("Giulia", "p01", SOIGNANT, "la patiente dort", "sonnette", "Madame", "Monsieur"):
        assert interdit not in page.text, f"« {interdit} » ne doit pas sortir chez la direction"
    assert 'href="/clinique/direction"' in client.get("/clinique").text
    assert client.get("/api/clinique/comptes", params={"badge": SOIGNANT}).status_code == 403
    comptes = client.get("/api/clinique/comptes", params={"badge": "direction"}).json()
    assert {"patients", "listes"} <= set(comptes)


# ---------------------------------------------------------------- tout passe par la porte
def test_les_pages_des_listes_ne_touchent_pas_au_faux_dossier():
    source = (RACINE / "briques/clinique/ecrans_listes.py").read_text(encoding="utf-8")
    for interdit in ("import yaml", "pathlib", "faux_dossier", "from . import dossier", "from .dossier", "open(", "read_text"):
        assert interdit not in source, interdit
    client, clinique = _clinique()
    avant = len(clinique.porte.journal.lignes())
    client.get("/clinique/soignant/liste", params=P01)
    client.get("/clinique/direction")
    lus = [l for l in clinique.porte.journal.lignes()[avant:] if l["resultat"] == "lu"]
    assert {l["qui"] for l in lus} == {SOIGNANT, "direction"}


# ---------------------------------------------------------------- la grande répétition, étape 6
def test_l_etape_6_de_la_grande_repetition_passe_par_la_vraie_page():
    from briques.clinique import repetition

    resultat = repetition.CONTROLES[6]()
    assert resultat.reussie is True and resultat.etiquette == "SIMULÉ"
    assert "habitudes" in resultat.detail
