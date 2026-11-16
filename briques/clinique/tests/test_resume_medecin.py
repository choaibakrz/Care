"""La clinique en boîte — T08, le résumé du médecin, version simple (cahier 5.7).

« Fini » veut dire :
- cinq lignes au plus pour chaque patient du médecin ;
- chaque ligne qui dit quelque chose porte sa source, et la source s'ouvre ;
- le patient aux deux dates (p07) donne « deux sources ne sont pas d'accord », et montre les deux ;
- le patient sans document (p05) donne « rien de nouveau » ;
- une phrase sans source est retirée ; un chiffre absent de la source fait retirer la phrase ;
- la recherche ouvre le bon document.
Par des règles, sans modèle. Internet coupé, aucun robot.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import replace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique import dossier as faux_dossier
from briques.clinique.carnet import Carnet
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.porte import AccesRefuse, JournalDesAcces, PorteDeLecture, charger_badges

BANDEAU = "DONNÉES INVENTÉES — DÉMONSTRATION"
MEDECIN = "medecin-exemple"
POINTS = ["pourquoi", "change", "decision", "questions", "aujourdhui"]
RIEN = "rien de nouveau"


def _pieces(jour_2: bool = False):
    from briques.clinique.resume import ResumeDuMedecin

    horloge = HorlogeDeDemonstration()
    if jour_2:
        asyncio.run(horloge.sauter("le lendemain matin"))
    porte = PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour)
    carnet = Carnet(horloge=horloge)
    badges = charger_badges()
    return ResumeDuMedecin(porte, carnet, horloge), badges, carnet, porte, horloge


def _ligne(resume, point):
    return next(l for l in resume["lignes"] if l["point"] == point)


def _client(jour_2: bool = False):
    from briques.clinique.ecrans import brancher_ecrans

    horloge = HorlogeDeDemonstration()
    if jour_2:
        asyncio.run(horloge.sauter("le lendemain matin"))
    app = FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge))
    return TestClient(app), clinique


# ---------------------------------------------------------------- cinq lignes au plus, pour chaque patient
def test_cinq_lignes_au_plus_pour_chaque_patient_du_medecin():
    resume, badges, *_ = _pieces()
    tous = resume.tous(badges[MEDECIN])
    assert [r["patient"] for r in tous] == ["p01", "p03", "p05", "p07", "p09", "p12"]
    for r in tous:
        assert [l["point"] for l in r["lignes"]] == POINTS and len(r["lignes"]) <= 5
        assert r["marque"] == "données inventées" and "sans modèle" in r["version"]


def test_chaque_ligne_qui_dit_quelque_chose_porte_sa_source_et_la_source_s_ouvre():
    resume, badges, *_ = _pieces()
    medecin = badges[MEDECIN]
    for r in resume.tous(medecin):
        for ligne in r["lignes"]:
            if ligne["texte"] == RIEN:
                assert ligne["sources"] == []
                continue
            assert ligne["sources"], f"{r['patient']} / {ligne['point']} : une ligne sans source"
            for phrase in ligne["phrases"]:
                assert phrase["sources"], f"phrase sans source : {phrase['texte']}"
            for source in ligne["sources"]:
                ouverte = resume.source(medecin, r["patient"], source["ref"])
                assert ouverte["texte"].strip() and ouverte["marque"] == "données inventées"


def test_la_patiente_du_scenario_pourquoi_elle_est_la_et_son_programme():
    resume, badges, *_ = _pieces()
    r = resume.resume(badges[MEDECIN], "p01")
    pourquoi = _ligne(r, "pourquoi")
    assert "réadaptation après une opération de la hanche" in pourquoi["texte"]
    assert [s["ref"] for s in pourquoi["sources"]] == ["sejour"]
    aujourdhui = _ligne(r, "aujourdhui")
    assert "11:00 physiothérapie" in aujourdhui["texte"] and [s["ref"] for s in aujourdhui["sources"]] == ["programme"]
    assert "Arrivée" in _ligne(r, "change")["texte"]  # arrivée le jour même : c'est nouveau


def test_le_lendemain_le_programme_est_celui_du_jour_2():
    resume, badges, *_ = _pieces(jour_2=True)
    texte = _ligne(resume.resume(badges[MEDECIN], "p01"), "aujourdhui")["texte"]
    assert "08:00 visite du médecin" in texte and "10:00 physiothérapie" in texte and "bain" not in texte


# ---------------------------------------------------------------- deux sources pas d'accord ; rien de nouveau
def test_le_patient_aux_deux_dates_le_resume_le_dit_et_montre_les_deux():
    resume, badges, *_ = _pieces()
    decision = _ligne(resume.resume(badges[MEDECIN], "p07"), "decision")
    assert "deux sources ne sont pas d'accord" in decision["texte"].lower()
    assert "20 novembre" in decision["texte"] and "22 novembre" in decision["texte"]  # il ne choisit pas
    assert [s["ref"] for s in decision["sources"]] == ["p07-d1", "p07-d2"] and decision["desaccord"] is True


def test_un_desaccord_ne_disparait_jamais_sans_rien_dire():
    from briques.clinique.resume import ResumeDuMedecin

    vue = {"id": "p07", "documents": [
        {"id": "a", "genre": "lettre", "texte": "Kontrolle 20.", "faits": [{"evenement": "contrôle", "date": "20 novembre"}]},
        {"id": "b", "genre": "liste", "texte": "Kontrolle 22.", "faits": [{"evenement": "contrôle", "date": "22 novembre 2026"}]}]}
    textes = {"a": "Kontrolle 20. — 20 novembre", "b": "Kontrolle 22."}  # « 22 novembre 2026 » n'est écrit nulle part
    resume, *_ = _pieces()
    brutes = resume._desaccords(vue)
    from briques.clinique.resume import garder_les_phrases_sures
    assert garder_les_phrases_sures(brutes, textes) == []  # la phrase avec les dates est retirée…
    gardee = garder_les_phrases_sures([brutes[0]["secours"]], textes)  # … mais pas le désaccord
    assert gardee and "ne sont pas d'accord" in gardee[0]["texte"] and gardee[0]["sources"] == ["a", "b"]
    assert isinstance(resume, ResumeDuMedecin)


def test_une_date_citee_doit_etre_ecrite_telle_quelle_dans_la_source():
    from briques.clinique.resume import garder_les_phrases_sures

    phrase = {"texte": "Contrôle : « 20 décembre ».", "citations": ["20 décembre"], "sources": ["a"]}
    assert garder_les_phrases_sures([phrase], {"a": "Die Kontrolle ist am 20. November."}) == []
    assert garder_les_phrases_sures([phrase], {"a": "Noté : contrôle — 20 décembre."}) == [phrase]


def test_une_question_au_carnet_arrive_dans_ses_questions_avec_sa_source():
    resume, badges, carnet, *_ = _pieces()
    carnet.ecrire(badges["patient-p01"], "question du soir", {"patient": "p01", "texte": "Ma fille peut-elle venir dimanche ?"},
                  valide_par_un_humain=False)
    questions = _ligne(resume.resume(badges[MEDECIN], "p01"), "questions")
    assert "Ma fille peut-elle venir dimanche ?" in questions["texte"] and [s["ref"] for s in questions["sources"]] == ["carnet-1"]


def test_le_journal_des_acces_dit_quelle_source_a_ete_ouverte():
    resume, badges, _, porte, _ = _pieces()
    resume.source(badges[MEDECIN], "p01", "p01-d1")
    derniere = porte.journal.lignes()[-1]
    assert derniere["quoi"] == "source du résumé : p01-d1" and derniere["resultat"] == "lu" and derniere["patients"] == ["p01"]


def test_le_patient_sans_document_donne_rien_de_nouveau():
    resume, badges, *_ = _pieces(jour_2=True)  # jour 2 : rien au programme non plus
    r = resume.resume(badges[MEDECIN], "p05")
    for point in ("change", "decision", "questions", "aujourdhui"):
        assert _ligne(r, point)["texte"] == RIEN and _ligne(r, point)["sources"] == []
    assert _ligne(r, "pourquoi")["texte"] != RIEN  # la raison du séjour a une source : la fiche du séjour


# ---------------------------------------------------------------- pas de phrase sans source, pas de chiffre changé
def test_une_phrase_sans_source_est_retiree():
    from briques.clinique.resume import garder_les_phrases_sures

    textes = {"sejour": "Séjour : pour 18 jours."}
    phrases = [{"texte": "Séjour de 18 jours.", "sources": ["sejour"]}, {"texte": "Elle va mieux.", "sources": []},
               {"texte": "Suite.", "sources": ["inconnue"]}]
    assert [p["texte"] for p in garder_les_phrases_sures(phrases, textes)] == ["Séjour de 18 jours."]


def test_un_chiffre_absent_de_la_source_fait_retirer_la_phrase():
    from briques.clinique.resume import garder_les_phrases_sures

    textes = {"sejour": "Séjour : pour 18 jours."}
    assert garder_les_phrases_sures([{"texte": "Séjour de 81 jours.", "sources": ["sejour"]}], textes) == []
    assert garder_les_phrases_sures([{"texte": "Séjour de 1 jour.", "sources": ["sejour"]}], textes) == []  # « 1 » n'est pas « 18 »


def test_les_chiffres_du_resume_sont_ceux_des_sources():
    resume, badges, *_ = _pieces()
    medecin = badges[MEDECIN]
    for r in resume.tous(medecin):
        for ligne in r["lignes"]:
            for phrase in ligne["phrases"]:
                sources = " ".join(resume.source(medecin, r["patient"], ref)["texte"] for ref in phrase["sources"])
                for nombre in re.findall(r"\d+", phrase["texte"]):
                    assert nombre in re.findall(r"\d+", sources), f"« {nombre} » n'est pas dans la source : {phrase['texte']}"


# ---------------------------------------------------------------- ce que le carnet apporte
def test_une_coche_de_la_veille_est_dans_ce_qui_a_change_avec_la_ligne_du_carnet_pour_source():
    from briques.clinique.listes import ListesDeSoin

    resume, badges, carnet, porte, horloge = _pieces()
    ListesDeSoin(porte, carnet).cocher(badges["soignant-etage-2"], "p01", "installation", 1)
    asyncio.run(horloge.sauter("le lendemain matin"))
    change = _ligne(resume.resume(badges[MEDECIN], "p01"), "change")
    refs = [s["ref"] for s in change["sources"]]
    assert "carnet-1" in refs and "fait" in change["texte"]
    ouverte = resume.source(badges[MEDECIN], "p01", "carnet-1")
    assert "installation" in ouverte["texte"] and ouverte["genre"] == "ligne du carnet"


def test_la_source_d_un_autre_patient_ne_s_ouvre_pas():
    from briques.clinique.listes import ListesDeSoin

    resume, badges, carnet, porte, _ = _pieces()
    ListesDeSoin(porte, carnet).cocher(badges["soignant-etage-2"], "p01", "installation", 1)
    with pytest.raises(AccesRefuse):
        resume.source(badges[MEDECIN], "p03", "carnet-1")  # la ligne parle de p01
    with pytest.raises(AccesRefuse):
        resume.source(badges[MEDECIN], "p03", "p01-d1")
    with pytest.raises(AccesRefuse):
        resume.source(badges[MEDECIN], "p02", "sejour")  # p02 n'est pas son patient


def test_le_resume_est_pour_le_medecin_seulement():
    resume, badges, *_ = _pieces()
    for autre in ("soignant-etage-2", "accueil", "direction", "robot-r1", "patient-p01", "therapeute-exemple"):
        with pytest.raises(AccesRefuse):
            resume.resume(badges[autre], "p01")
    assistant = badges["assistant"].travaille_pour(badges[MEDECIN])
    assert resume.resume(assistant, "p01")["patient"] == "p01"  # le cerveau voit ce que voit le médecin


# ---------------------------------------------------------------- préparé à l'avance, refait si une source change
def test_le_resume_est_prepare_a_l_avance_et_refait_quand_une_source_arrive():
    from briques.clinique.listes import ListesDeSoin

    resume, badges, carnet, porte, horloge = _pieces()
    medecin = badges[MEDECIN]
    prets = resume.preparer(medecin)
    assert len(prets) == 6 and len(carnet.lignes("résumé du médecin")) == 6
    premier = resume.resume(medecin, "p01")
    assert premier["prepare"]["jour"] == 1 and premier["refait"] is False
    assert len(carnet.lignes("résumé du médecin")) == 6  # relire ne refait rien
    ListesDeSoin(porte, carnet).cocher(badges["soignant-etage-2"], "p01", "installation", 2)
    second = resume.resume(medecin, "p01")
    assert second["refait"] is True and len(carnet.lignes("résumé du médecin")) == 7
    assert all(l["valide_par_un_humain"] is False for l in carnet.lignes("résumé du médecin"))


def test_rien_ne_s_ecrit_dans_le_faux_dossier():
    avant = faux_dossier.empreinte()
    resume, badges, *_ = _pieces()
    resume.preparer(badges[MEDECIN])
    resume.chercher(badges[MEDECIN], "la lettre du médecin de Madame B.")
    assert faux_dossier.empreinte() == avant


# ---------------------------------------------------------------- la recherche d'un document
def test_la_recherche_ouvre_le_bon_document():
    resume, badges, *_ = _pieces()
    medecin = badges[MEDECIN]
    trouve = resume.chercher(medecin, "la lettre du médecin de Madame B.")
    assert trouve["trouve"] is True and (trouve["patient"], trouve["ref"]) == ("p01", "p01-d1")
    assert "Lettera per la signora Giulia B." in trouve["document"]["texte"]
    assert resume.chercher(medecin, "la liste de médicaments de Giulia")["ref"] == "p01-d2"
    assert resume.chercher(medecin, "carte d'assurance de madame b")["ref"] == "p01-d3"


def test_le_dernier_rapport_de_radiologie_ouvre_le_bon_document():
    resume, badges, *_ = _pieces()
    medecin_de_p02 = replace(badges[MEDECIN], patients=("p01", "p02"))  # un médecin qui suit aussi Monsieur Hans K.
    trouve = resume.chercher(medecin_de_p02, "le dernier rapport de radiologie de Monsieur K.")
    assert trouve["trouve"] is True and trouve["ref"] == "p02-d1" and "Radiologie Exemple" in trouve["document"]["texte"]


def test_la_recherche_dit_vrai_quand_il_n_y_a_rien():
    resume, badges, *_ = _pieces()
    medecin = badges[MEDECIN]
    rien = resume.chercher(medecin, "le dernier rapport de radiologie de Madame B.")  # elle n'en a pas
    assert rien["trouve"] is False and "Madame Giulia B." in rien["dit"] and "ref" not in rien
    autre = resume.chercher(medecin, "le rapport de radiologie de Monsieur K.")  # pas son patient : rien ne s'ouvre
    assert autre["trouve"] is False and "Hans" not in autre["dit"]
    assert resume.chercher(medecin, "bonjour")["trouve"] is False


# ---------------------------------------------------------------- à l'écran du médecin
def test_l_ecran_du_medecin_montre_le_resume_et_un_doigt_ouvre_la_source():
    client, _ = _client()
    page = client.get("/clinique/medecin")
    assert page.status_code == 200 and BANDEAU in page.text
    assert "Résumé" in page.text and "règles simples, sans modèle" in page.text
    assert "deux sources ne sont pas d&#x27;accord" in page.text.lower() and RIEN in page.text
    liens = re.findall(r'href="(/clinique/medecin/source\?[^"]+)"', page.text)
    assert liens, "aucune source à ouvrir sur l'écran du médecin"
    for lien in sorted(set(liens)):
        source = client.get(lien.replace("&amp;", "&"))
        assert source.status_code == 200 and BANDEAU in source.text, lien
        assert "Accès refusé" not in source.text and "référence " in source.text, lien  # elle s'ouvre vraiment
    lettre = client.get("/clinique/medecin/source", params={"badge": MEDECIN, "patient": "p01", "ref": "p01-d1"})
    assert "Lettera per la signora Giulia B." in lettre.text


def test_a_l_ecran_un_autre_badge_n_ouvre_pas_la_source():
    client, _ = _client()
    refus = client.get("/clinique/medecin/source", params={"badge": "soignant-etage-2", "patient": "p01", "ref": "p01-d1"})
    assert "Accès refusé" in refus.text and "Lettera" not in refus.text
    ailleurs = client.get("/clinique/medecin/source", params={"badge": MEDECIN, "patient": "p02", "ref": "p02-d1"})
    assert "Accès refusé" in ailleurs.text and "Radiologie" not in ailleurs.text


def test_a_l_ecran_la_recherche_ouvre_le_bon_document():
    client, _ = _client()
    assert 'action="/clinique/medecin/recherche"' in client.get("/clinique/medecin").text
    page = client.get("/clinique/medecin/recherche", params={"badge": MEDECIN, "q": "la lettre du médecin de Madame B."})
    assert page.status_code == 200 and BANDEAU in page.text and "Lettera per la signora Giulia B." in page.text
    rien = client.get("/clinique/medecin/recherche", params={"badge": MEDECIN, "q": "<b>radiologie</b> de Madame B."})
    assert "<b>radiologie" not in rien.text and "Lettera" not in rien.text


# ---------------------------------------------------------------- la grande répétition
def test_l_etape_10_de_la_grande_repetition_le_resume_chaque_ligne_avec_sa_source():
    from briques.clinique import repetition

    resultat = repetition.CONTROLES[10]()
    assert resultat.reussie is True and resultat.etiquette == "SIMULÉ"
    assert "source" in resultat.detail
