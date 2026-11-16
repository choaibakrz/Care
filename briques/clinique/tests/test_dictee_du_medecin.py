"""La clinique en boîte — T18, la dictée du médecin, AU NIVEAU DU TEXTE RECONNU (cahier 5.6 et 5.7).

« Fini » veut dire :
- « Physio, évaluer la marche demain » devient un brouillon marqué « brouillon, pas dans le dossier » et une tâche pour
  le thérapeute, visible sur sa page ;
- rien n'entre au faux dossier ;
- une dictée mal entendue (écoute peu sûre, ou micro en panne) n'écrit rien : ni brouillon, ni tâche ;
- le brouillon dit d'où il vient (une dictée), et le médecin voit ce que le prototype a compris.
La pièce a été construite au tour 15 (T11b), phrase tapée. DIRE VRAI : ni micro ni modèle d'écoute sur l'iMac (R4) :
personne n'a dicté à voix haute.
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique import dossier as faux_dossier
from briques.clinique.carnet import Carnet
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.listes import ChoixRefuse
from briques.clinique.porte import JournalDesAcces, PorteDeLecture
from conftest import lancer

MEDECIN, THERAPEUTE = "medecin-exemple", "therapeute-exemple"
DICTEE = "Physio, évaluer la marche demain"


def _clinique(*sauts):
    from briques.clinique.ecrans import brancher_ecrans

    horloge = HorlogeDeDemonstration(temps=lambda: 0.0)
    for saut in sauts:
        asyncio.run(horloge.sauter(saut))
    app = FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge), code_equipe="x")
    return TestClient(app), clinique


def test_la_dictee_du_cahier_devient_un_brouillon_marque_et_une_tache_visible_chez_le_therapeute():
    client, clinique = _clinique("le soir", "le lendemain matin", "visite")
    empreinte = faux_dossier.empreinte()
    r = client.post("/api/clinique/dictee", json={"badge": MEDECIN, "patient": "p01", "texte": DICTEE})
    assert r.status_code == 200
    reponse = r.json()
    assert reponse["brouillon"]["mention"] == "brouillon, pas dans le dossier" and reponse["brouillon"]["texte"] == DICTEE
    assert reponse["brouillon"]["origine"] == "dictée du médecin"
    assert reponse["tache"]["pour"] == "thérapeute" and reponse["tache"]["quoi"] == "évaluer la marche demain"
    assert "évaluer la marche demain" in reponse["dit"] and "thérapeute" in reponse["dit"]  # ce que le prototype a compris
    page = client.get("/clinique/therapeute", params={"badge": THERAPEUTE}).text
    assert "évaluer la marche demain" in page and "brouillon, pas dans le dossier" in page and "Madame Giulia B." in page
    assert faux_dossier.empreinte() == empreinte  # rien n'entre au faux dossier
    assert len(clinique.carnet.lignes("brouillon")) == 1 and len(clinique.carnet.lignes("tâche")) == 1


def test_une_dictee_mal_entendue_n_ecrit_rien():
    _, clinique = _clinique()
    medecin = clinique.badges[MEDECIN]
    with pytest.raises(ChoixRefuse, match="pas bien entendu"):
        clinique.soir.dicter(medecin, "p01", DICTEE, confiance=0.3)
    assert clinique.carnet.lignes("brouillon") == [] and clinique.carnet.lignes("tâche") == []
    assert clinique.soir.dicter(medecin, "p01", DICTEE, confiance=0.9)["tache"]["pour"] == "thérapeute"


def test_micro_en_panne_la_dictee_n_ecrit_rien_et_le_medecin_peut_la_taper_apres():
    client, clinique = _clinique()
    lancer(clinique.pannes.provoquer("micro_bruit"))
    r = client.post("/api/clinique/dictee", json={"badge": MEDECIN, "patient": "p01", "texte": DICTEE})
    assert r.status_code == 400 and "pas bien entendu" in r.json()["detail"]
    assert clinique.carnet.lignes("brouillon") == [] and clinique.carnet.lignes("tâche") == []
    lancer(clinique.pannes.finir("micro_bruit"))
    assert client.post("/api/clinique/dictee", json={"badge": MEDECIN, "patient": "p01", "texte": DICTEE}).status_code == 200


def test_la_page_de_dictee_dit_que_la_phrase_est_tapee_et_ce_qui_arrivera():
    client, _ = _clinique()
    page = client.get("/clinique/medecin/dictee", params={"badge": MEDECIN, "patient": "p01"}).text
    assert "SIMULÉ" in page and "tapée" in page and "brouillon, pas dans le dossier" in page
