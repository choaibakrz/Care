"""La clinique en boîte — L04b, la pré-admission : la boucle fermée, et les boutons (avenant 4, L04 ; seconde moitié).

« Fini » veut dire, par le vrai serveur :
- le bouton du chef « Faire arriver deux papiers » ; sans lui, rien ne change ;
- dans « à trier », le bouton « Préparer une pré-admission » ; l'écran montre la proposition, ses sources, et la phrase
  « L'assistant prépare. Une personne décide. » ;
- sans validation, le dossier « de nous vers le logiciel » reste vide ;
- après validation, le message part et s'affiche dans la liste « pré-admissions reçues » du faux logiciel ;
- « admettre » fait revenir une admission ; le traducteur la lit ; l'accueil du hall connaît la personne ;
- le numéro de la pré-admission relie la demande et la réponse ; le carnet marque la proposition « admise » ;
- la remise à zéro retire les papiers et la demande.
"""
from __future__ import annotations

import html

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique import pre_admission
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
    return TestClient(app), clinique, bus, tmp_path / "faux_logiciel" / logiciel.VERS_LUI


def _poster(client, chemin, corps=None, code=True, attendu=200):
    r = client.post(chemin, json=corps or {}, headers=CODE if code else {})
    assert r.status_code == attendu, (chemin, r.status_code, r.text)
    return r.json()


def _jusqu_a_la_validation(client):
    _poster(client, "/api/clinique/pre-admission/arriver")
    _poster(client, "/api/clinique/pre-admission/preparer", {"badge": "accueil"}, code=False)
    _poster(client, "/api/clinique/pre-admission/corriger", {"badge": "accueil", "numero": "PA-0001", "champ": "langue", "valeur": "it"}, code=False)
    return _poster(client, "/api/clinique/pre-admission/valider", {"badge": "accueil", "numero": "PA-0001"}, code=False)


# ---------------------------------------------------------------------------------------------- les boutons
def test_faire_arriver_deux_papiers_est_un_bouton_du_chef(banc):
    client, clinique, _, _ = banc
    avant = client.get("/api/clinique/papiers", params={"badge": "accueil"}).json()
    assert not set(pre_admission.IDS_DES_PAPIERS) & {p["id"] for p in avant["a_trier"]}
    _poster(client, "/api/clinique/pre-admission/arriver", code=False, attendu=403)  # sans le code d'équipe : refusé
    _poster(client, "/api/clinique/pre-admission/arriver")
    apres = client.get("/api/clinique/papiers", params={"badge": "accueil"}).json()
    assert set(pre_admission.IDS_DES_PAPIERS) <= {p["id"] for p in apres["a_trier"]}
    page = html.unescape(client.get("/clinique/accueil/papiers?badge=accueil").text)
    assert "Préparer une pré-admission" in page and "/clinique/pre-admission?badge=accueil" in page


def test_sans_les_deux_papiers_le_bouton_preparer_n_est_pas_la(banc):
    client, _, _, _ = banc
    assert "Préparer une pré-admission" not in html.unescape(client.get("/clinique/accueil/papiers?badge=accueil").text)
    _poster(client, "/api/clinique/pre-admission/preparer", {"badge": "accueil"}, code=False, attendu=400)


def test_l_ecran_montre_la_proposition_ses_sources_et_la_phrase_fixe(banc):
    client, _, _, _ = banc
    _poster(client, "/api/clinique/pre-admission/arriver")
    vide = html.unescape(client.get("/clinique/pre-admission?badge=accueil").text)
    assert "L'assistant prépare. Une personne décide." in vide and "Préparer une pré-admission" in vide and "SIMULÉ" in vide
    _poster(client, "/api/clinique/pre-admission/preparer", {"badge": "accueil"}, code=False)
    page = html.unescape(client.get("/clinique/pre-admission?badge=accueil").text)
    for mot in ("L'assistant prépare. Une personne décide.", "PA-0001", "Elena", "1950-02-02", "Assurance Exemple — EXEMPLE-0001",
                "2026-11-15", "pa-lettre", "pa-carte", "confiance : haute", "confiance : moyenne", "je ne suis pas sûr",
                "Valider", "Rien n'est encore parti"):
        assert mot in page, mot
    assert "Motif" not in page and "réadaptation" not in page  # rien de médical à l'écran
    autre = html.unescape(client.get("/clinique/pre-admission?badge=soignant-etage-2").text)
    assert "Elena" not in autre and "refus" in autre.lower()  # la pré-admission est pour l'accueil


def test_seul_un_badge_accueil_prepare_et_valide_par_le_serveur(banc):
    client, _, _, dossier = banc
    _poster(client, "/api/clinique/pre-admission/arriver")
    _poster(client, "/api/clinique/pre-admission/preparer", {"badge": "soignant-etage-2"}, code=False, attendu=403)
    _poster(client, "/api/clinique/pre-admission/preparer", {"badge": "accueil"}, code=False)
    _poster(client, "/api/clinique/pre-admission/valider", {"badge": "robot-r1", "numero": "PA-0001"}, code=False, attendu=403)
    assert not dossier.exists() or list(dossier.iterdir()) == []  # sans validation, rien n'est parti


# ---------------------------------------------------------------------------------------------- la boucle
def test_apres_validation_le_message_part_et_s_affiche_dans_le_faux_logiciel(banc):
    client, clinique, _, dossier = banc
    assert "Pré-admissions reçues" in html.unescape(client.get("/faux-logiciel", headers=CODE).text)
    validee = _jusqu_a_la_validation(client)
    assert validee["proposition"]["etat"] == "validée" and [f.name for f in dossier.iterdir()] == ["0001_A05_PA-0001.hl7"]
    recues = clinique.faux_logiciel.pre_admissions_recues()
    assert len(recues) == 1 and recues[0]["numero"] == "PA-0001" and recues[0]["statut"] == "reçue"
    assert recues[0]["prenom"] == "Elena" and recues[0]["nom"] == "C." and recues[0]["langue"] == "it"
    page = html.unescape(client.get("/faux-logiciel", headers=CODE).text)
    assert "PA-0001" in page and "Elena" in page and "Admettre la pré-admission" in page


def test_admettre_fait_revenir_une_admission_et_l_accueil_connait_la_personne(banc):
    client, clinique, bus, _ = banc
    _jusqu_a_la_validation(client)
    avant = clinique.accueil.entendre("Bonjour, je suis Elena C.")
    assert avant["cas"] == "inconnu" and avant["appel"]  # validée, mais pas encore admise : un humain vient
    r = _poster(client, "/api/faux-logiciel/admettre", {"numero": "PA-0001", "chambre": "14"})
    message = r["message"]
    assert message["sorte"] == "A01" and message["numero_patient"] == "p16" and message["numero_sejour"] == "s16"
    pv1 = next(l for l in message["texte"].splitlines() if l.startswith("PV1")).split("|")
    assert pv1[5] == "PA-0001" and pv1[3].endswith("^14")  # le numéro de la pré-admission relie la demande et la réponse
    apres = clinique.accueil.entendre("Bonjour, je suis Elena C.")
    assert apres["cas"] == "arrivée" and apres["chambre"] == 14 and apres["prenom"] == "Elena"
    assert clinique.faux_logiciel.pre_admissions_recues()[0]["statut"] == "admise"
    # le carnet marque la proposition « admise », avec le numéro de patient donné par le logiciel
    proposition = client.get("/api/clinique/pre-admission", params={"badge": "accueil"}).json()["propositions"][0]
    assert proposition["etat"] == "admise" and proposition["admise"]["numero_patient"] == "p16"
    assert "admise" in html.unescape(client.get("/clinique/pre-admission?badge=accueil").text)
    lus = [e.donnees for e in bus.historique if e.type == "note" and e.donnees.get("quoi") == "message_lu"]
    assert lus and lus[-1]["sorte"] == "A01" and lus[-1]["numero_patient"] == "p16"


def test_on_n_admet_pas_deux_fois_ni_une_demande_inconnue(banc):
    client, _, _, _ = banc
    _jusqu_a_la_validation(client)
    _poster(client, "/api/faux-logiciel/admettre", {"numero": "PA-0001", "chambre": "14"})
    _poster(client, "/api/faux-logiciel/admettre", {"numero": "PA-0001", "chambre": "13"}, attendu=400)
    _poster(client, "/api/faux-logiciel/admettre", {"numero": "PA-9999", "chambre": "13"}, attendu=400)
    _poster(client, "/api/faux-logiciel/admettre", {"numero": "PA-0001", "chambre": "14"}, code=False, attendu=403)


def test_le_faux_logiciel_ne_prend_que_des_lignes_administratives(banc):
    client, clinique, _, dossier = banc
    _jusqu_a_la_validation(client)
    recue = clinique.faux_logiciel.pre_admissions_recues()[0]
    assert set(recue) == {"numero", "statut", "nom", "prenom", "date_naissance", "langue", "assurance", "date_arrivee_prevue",
                          "fichier", "numero_patient"}
    (dossier / "9999_abime.hl7").write_text("pas un message\n", encoding="utf-8")
    assert len(clinique.faux_logiciel.pre_admissions_recues()) == 1  # un fichier abîmé n'arrête rien


def test_la_remise_a_zero_retire_les_papiers_et_la_demande(banc):
    client, clinique, _, dossier = banc
    _jusqu_a_la_validation(client)
    _poster(client, "/api/faux-logiciel/admettre", {"numero": "PA-0001", "chambre": "14"})
    _poster(client, "/api/faux-logiciel/zero")
    assert list(dossier.iterdir()) == [] and clinique.faux_logiciel.pre_admissions_recues() == []
    pile = client.get("/api/clinique/papiers", params={"badge": "accueil"}).json()
    assert not set(pre_admission.IDS_DES_PAPIERS) & {p["id"] for p in pile["a_trier"]}
    assert clinique.accueil.entendre("Bonjour, je suis Elena C.")["cas"] == "inconnu"
    assert len(clinique.faux_logiciel.liste()) == 15
