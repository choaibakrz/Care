"""La clinique en boîte — T11b, le soir et la dictée, version simple et tapée (cahier 4.2, 5.6, 5.7, 6.1).

« Fini » veut dire :
- avant le soir, l'écran de la patiente ne pose pas la question ; à 19 h, il la pose dans sa langue (italien) ;
- ses deux questions, tapées, sont au carnet et arrivent chez le médecin le lendemain, avec leur source ;
- le prototype ne répond à aucune question : il transmet, c'est tout ;
- « Physio, évaluer la marche demain », tapé par le médecin, devient un brouillon marqué « brouillon, pas dans le
  dossier » et une tâche pour un humain, visible sur l'écran du thérapeute ;
- rien n'entre au faux dossier ; seuls la patiente et le médecin peuvent faire ces gestes.
Pas de voix, pas de modèle, pas de traduction (elles viennent avec T18 et T19). Internet coupé, aucun robot.
"""
from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique import repetition
from briques.clinique.carnet import Carnet
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.porte import AccesRefuse, JournalDesAcces, PorteDeLecture

PATIENTE, MEDECIN, THERAPEUTE, SOIGNANT = "patient-p01", "medecin-exemple", "therapeute-exemple", "soignant-etage-2"
Q1, Q2 = "Quando potrò camminare senza deambulatore?", "Mia figlia può venire domenica?"
DICTEE = "Physio, évaluer la marche demain."
FAUX_DOSSIER = Path(__file__).resolve().parents[1] / "faux_dossier"


def _empreinte() -> str:
    h = hashlib.sha256()
    for f in sorted(FAUX_DOSSIER.rglob("*")):
        if f.is_file():
            h.update(f.name.encode() + f.read_bytes())
    return h.hexdigest()


def _clinique(*sauts: str):
    from briques.clinique.ecrans import brancher_ecrans

    horloge = HorlogeDeDemonstration(temps=lambda: 0.0)
    for saut in sauts:
        asyncio.run(horloge.sauter(saut))
    app = FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge))
    return TestClient(app), clinique, horloge


# ---------------------------------------------------------------------------------------------- le soir
def test_le_matin_la_question_du_soir_n_est_pas_posee():
    client, clinique, _ = _clinique()
    invitation = clinique.soir.invitation(clinique.badges[PATIENTE])
    assert invitation["a_poser"] is False
    assert "Ha domande" not in client.get("/clinique/patient", params={"badge": PATIENTE}).text
    r = client.post("/api/clinique/soir/question", json={"badge": PATIENTE, "texte": Q1})
    assert r.status_code == 400 and not clinique.carnet.lignes("question du soir")


def test_le_soir_l_ecran_de_la_patiente_pose_la_question_en_italien():
    client, clinique, _ = _clinique("le soir")
    invitation = clinique.soir.invitation(clinique.badges[PATIENTE])
    assert invitation == {**invitation, "a_poser": True, "langue": "it",
                          "phrase": "Ha domande per il medico domani?"}
    page = client.get("/clinique/patient", params={"badge": PATIENTE}).text
    assert "Ha domande per il medico domani?" in page and "/clinique/patient/soir?badge=patient-p01" in page
    assert "TEMPS ACCÉLÉRÉ" in page  # l'horloge a sauté : la marque est là
    soir = client.get("/clinique/patient/soir", params={"badge": PATIENTE})
    assert soir.status_code == 200 and "Ha domande per il medico domani?" in soir.text
    assert "DONNÉES INVENTÉES" in soir.text


def test_les_deux_questions_sont_au_carnet_telles_quelles_et_le_prototype_ne_repond_pas():
    client, clinique, _ = _clinique("le soir")
    avant = _empreinte()
    for question in (Q1, Q2):
        r = client.post("/api/clinique/soir/question", json={"badge": PATIENTE, "texte": question})
        assert r.status_code == 200
        dit = r.json()["dit"]
        assert "trasmessa al medico" in dit and "Non rispondo" in dit
        assert "deambulatore" not in dit and "domenica" not in dit  # il ne commente pas, il transmet
    lignes = clinique.carnet.lignes("question du soir")
    assert [l["donnees"]["texte"] for l in lignes] == [Q1, Q2]
    assert all(l["donnees"]["patient"] == "p01" and l["donnees"]["langue"] == "it" and l["qui"] == PATIENTE
               and l["quand"]["heure"] == "19:00" for l in lignes)
    assert _empreinte() == avant


def test_le_lendemain_les_deux_questions_sont_chez_le_medecin_avec_leur_source():
    client, clinique, _ = _clinique("le soir")
    for question in (Q1, Q2):
        client.post("/api/clinique/soir/question", json={"badge": PATIENTE, "texte": question})
    asyncio.run(clinique.horloge.sauter("le lendemain matin"))
    medecin = clinique.badges[MEDECIN]
    resume = clinique.resume.resume(medecin, "p01")
    ligne = next(l for l in resume["lignes"] if l["titre"] == "Ses questions")
    assert Q1 in ligne["texte"] and Q2 in ligne["texte"] and len(ligne["sources"]) == 2
    for ref in ligne["sources"]:
        source = clinique.resume.source(medecin, "p01", ref if isinstance(ref, str) else ref["ref"])
        assert "question du soir" in str(source)
    page = client.get("/clinique/medecin", params={"badge": MEDECIN}).text
    assert "Quando potrò camminare senza deambulatore?" in page


def test_un_patient_sans_question_reste_rien_de_nouveau():
    _, clinique, _ = _clinique("le soir", "le lendemain matin")
    resume = clinique.resume.resume(clinique.badges[MEDECIN], "p01")
    assert next(l for l in resume["lignes"] if l["titre"] == "Ses questions")["texte"] == "rien de nouveau"


@pytest.mark.parametrize("badge", [MEDECIN, SOIGNANT, "robot-r1", "direction", "assistant"])
def test_seule_la_patiente_pose_sa_question(badge):
    client, clinique, _ = _clinique("le soir")
    r = client.post("/api/clinique/soir/question", json={"badge": badge, "texte": Q1})
    assert r.status_code == 403 and not clinique.carnet.lignes("question du soir")


def test_une_question_vide_ou_un_badge_inconnu_est_refuse():
    client, clinique, _ = _clinique("le soir")
    assert client.post("/api/clinique/soir/question", json={"badge": PATIENTE, "texte": "   "}).status_code == 400
    assert client.post("/api/clinique/soir/question", json={"badge": "personne", "texte": Q1}).status_code == 404
    assert not clinique.carnet.lignes("question du soir")


def test_une_balise_dans_une_question_ne_passe_pas_a_l_ecran():
    client, clinique, _ = _clinique("le soir")
    client.post("/api/clinique/soir/question", json={"badge": PATIENTE, "texte": "<script>alert(1)</script>"})
    assert "<script>alert(1)" not in client.get("/clinique/patient/soir", params={"badge": PATIENTE}).text
    asyncio.run(clinique.horloge.sauter("le lendemain matin"))
    assert "<script>alert(1)" not in client.get("/clinique/medecin", params={"badge": MEDECIN}).text


# ---------------------------------------------------------------------------------------------- la dictée
def test_la_dictee_devient_un_brouillon_et_une_tache_pour_le_therapeute():
    client, clinique, _ = _clinique("le soir", "le lendemain matin", "visite")
    avant = _empreinte()
    r = client.post("/api/clinique/dictee", json={"badge": MEDECIN, "patient": "p01", "texte": DICTEE})
    assert r.status_code == 200
    reponse = r.json()
    assert reponse["brouillon"]["mention"] == "brouillon, pas dans le dossier"
    assert reponse["brouillon"]["texte"] == DICTEE
    tache = reponse["tache"]
    assert tache["sorte"] == "humain" and tache["pour"] == "thérapeute" and tache["pour_qui"] == "p01"
    assert tache["quoi"] == "évaluer la marche demain" and tache["pour_quand"] == "jour 3" and tache["etat"] == "demandée"
    brouillons = clinique.carnet.lignes("brouillon")
    assert len(brouillons) == 1 and brouillons[0]["qui"] == MEDECIN and brouillons[0]["valide_par_un_humain"] is True
    assert tache["brouillon"] == brouillons[0]["numero"]
    assert _empreinte() == avant  # rien n'entre au faux dossier


def test_la_tache_se_voit_sur_l_ecran_du_therapeute():
    client, clinique, _ = _clinique("le soir", "le lendemain matin", "visite")
    avant = client.get("/clinique/therapeute", params={"badge": THERAPEUTE}).text
    client.post("/api/clinique/dictee", json={"badge": MEDECIN, "patient": "p01", "texte": DICTEE})
    page = client.get("/clinique/therapeute", params={"badge": THERAPEUTE}).text
    assert "évaluer la marche demain" not in avant
    assert "évaluer la marche demain" in page and "Madame Giulia B." in page and "jour 3" in page
    assert "demandé par" in page.lower() and "brouillon, pas dans le dossier" in page


def test_une_demande_d_objet_ne_va_pas_sur_l_ecran_du_therapeute():
    client, clinique, _ = _clinique()
    clinique.taches.demander(clinique.badges[SOIGNANT], "p01", "il manque un grand coussin")
    assert "grand coussin" not in client.get("/clinique/therapeute", params={"badge": THERAPEUTE}).text


def test_une_dictee_sans_destinataire_connu_va_a_l_equipe_de_soin_et_le_dit():
    client, clinique, _ = _clinique()
    r = client.post("/api/clinique/dictee", json={"badge": MEDECIN, "patient": "p01", "texte": "Revoir demain."}).json()
    assert r["tache"]["pour"] == "soignant" and r["tache"]["quoi"] == "Revoir demain"
    assert "pas reconnu" in r["dit"]


@pytest.mark.parametrize("badge", [PATIENTE, SOIGNANT, THERAPEUTE, "accueil", "robot-r1", "direction"])
def test_seul_le_medecin_dicte(badge):
    client, clinique, _ = _clinique()
    r = client.post("/api/clinique/dictee", json={"badge": badge, "patient": "p01", "texte": DICTEE})
    assert r.status_code == 403
    assert not clinique.carnet.lignes("brouillon") and not clinique.carnet.lignes("tâche")


def test_le_medecin_ne_dicte_pas_pour_un_patient_qu_il_ne_suit_pas():
    client, clinique, _ = _clinique()
    r = client.post("/api/clinique/dictee", json={"badge": MEDECIN, "patient": "p02", "texte": DICTEE})
    assert r.status_code == 403
    assert not clinique.carnet.lignes("brouillon") and not clinique.carnet.lignes("tâche")
    with pytest.raises(AccesRefuse):
        clinique.soir.dicter(clinique.badges[MEDECIN], "p02", DICTEE)


def test_une_dictee_vide_est_refusee():
    client, clinique, _ = _clinique()
    r = client.post("/api/clinique/dictee", json={"badge": MEDECIN, "patient": "p01", "texte": " "})
    assert r.status_code == 400 and not clinique.carnet.lignes("brouillon")


def test_la_page_de_dictee_s_ouvre_depuis_l_ecran_du_medecin():
    client, _, _ = _clinique()
    page = client.get("/clinique/medecin", params={"badge": MEDECIN}).text
    assert "/clinique/medecin/dictee?badge=medecin-exemple&amp;patient=p01" in page
    dictee = client.get("/clinique/medecin/dictee", params={"badge": MEDECIN, "patient": "p01"})
    assert dictee.status_code == 200 and "Madame Giulia B." in dictee.text and "tapée" in dictee.text
    refus = client.get("/clinique/medecin/dictee", params={"badge": MEDECIN, "patient": "p02"})
    assert "Accès refusé" in refus.text and "Hans" not in refus.text


# ---------------------------------------------------------------------------------------------- la grande répétition
def test_les_etapes_9_et_11_de_la_repetition_reussissent_et_disent_ce_qui_est_simule():
    for numero in (9, 11):
        resultat = repetition.CONTROLES[numero]()
        assert resultat.reussie is True, resultat.detail
        assert resultat.etiquette == "SIMULÉ" and "tapé" in resultat.detail
    assert "2 traduites par les traductions fixes du scénario" in repetition.CONTROLES[9]().detail  # depuis T19


def test_l_etape_9_rate_si_une_question_se_perd(monkeypatch):
    from briques.clinique import soir

    monkeypatch.setattr(soir.LeSoir, "poser", lambda self, badge, texte: {"dit": "", "ligne": None})
    assert repetition.CONTROLES[9]().reussie is False


def test_l_etape_11_rate_si_la_tache_ne_part_pas(monkeypatch):
    from briques.clinique import taches

    monkeypatch.setattr(taches.TableauDesTaches, "tableau", lambda self, badge: [])
    assert repetition.CONTROLES[11]().reussie is False
