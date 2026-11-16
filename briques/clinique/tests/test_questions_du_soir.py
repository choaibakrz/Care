"""La clinique en boîte — T19, les questions du soir (cahier 4.2 et 6.1).

« Fini » veut dire :
- à l'heure du soir, l'écran de la patiente pose la question dans sa langue ;
- ses deux questions arrivent chez le médecin, traduites, avec le texte d'origine à côté ;
- une question de santé ne reçoit pas de réponse du prototype.
DIRE VRAI : il n'y a pas de modèle sur l'iMac (R2, Q17). La « traduction » est ici une traduction FIXE des deux questions
du scénario, écrite dans un fichier (le cahier donne leur français). Une autre question n'est PAS traduite : elle
arrive telle quelle, marquée « non traduite ». Le prototype n'invente jamais une traduction.
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique import soir
from briques.clinique.carnet import Carnet
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.porte import JournalDesAcces, PorteDeLecture

PATIENTE, MEDECIN, SOIGNANT = "patient-p01", "medecin-exemple", "soignant-etage-2"
Q1, Q2 = "Quando potrò camminare senza deambulatore?", "Mia figlia può venire domenica?"
F1, F2 = "Quand pourrai-je marcher sans déambulateur ?", "Ma fille peut-elle venir dimanche ?"
SANTE = "Posso prendere due compresse invece di una?"


def _clinique(*sauts, traducteur="défaut"):
    from briques.clinique.ecrans import brancher_ecrans

    horloge = HorlogeDeDemonstration(temps=lambda: 0.0)
    for saut in sauts:
        asyncio.run(horloge.sauter(saut))
    app = FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge), code_equipe="x")
    if traducteur != "défaut":
        clinique.soir.traducteur = traducteur
    return TestClient(app), clinique


def _poser(client, *questions):
    return [client.post("/api/clinique/soir/question", json={"badge": PATIENTE, "texte": q}) for q in questions]


def _ligne_questions(clinique):
    resume = clinique.resume.resume(clinique.badges[MEDECIN], "p01")
    return next(l for l in resume["lignes"] if l["point"] == "questions")


def test_a_l_heure_du_soir_l_ecran_de_la_patiente_pose_la_question_dans_sa_langue():
    client, _ = _clinique()
    assert "Ha domande" not in client.get("/clinique/patient", params={"badge": PATIENTE}).text  # le matin : rien
    client, _ = _clinique("le soir")
    page = client.get("/clinique/patient", params={"badge": PATIENTE}).text
    assert "Ha domande per il medico domani?" in page


def test_les_deux_questions_arrivent_chez_le_medecin_traduites_avec_le_texte_d_origine_a_cote():
    client, clinique = _clinique("le soir")
    assert all(r.status_code == 200 for r in _poser(client, Q1, Q2))
    lignes = clinique.carnet.lignes("question du soir")
    assert [(l["donnees"]["texte"], l["donnees"]["traduction"]) for l in lignes] == [(Q1, F1), (Q2, F2)]
    assert all("traduction fixe du scénario" in l["donnees"]["traduit_par"] for l in lignes)
    asyncio.run(clinique.horloge.sauter("le lendemain matin"))
    ligne = _ligne_questions(clinique)
    for traduite, origine in ((F1, Q1), (F2, Q2)):
        assert traduite in ligne["texte"] and origine in ligne["texte"]
        assert ligne["texte"].index(traduite) < ligne["texte"].index(origine)  # la traduction, puis le texte d'origine à côté
    assert "traduit de l'italien" in ligne["texte"] and len(ligne["sources"]) == 2
    page = client.get("/clinique/medecin", params={"badge": MEDECIN}).text
    assert "Quand pourrai-je marcher sans déambulateur ?" in page and "Quando potrò camminare senza deambulatore?" in page
    # chaque question ouvre sa source : la ligne du carnet, avec les deux textes
    source = clinique.resume.source(clinique.badges[MEDECIN], "p01", ligne["sources"][0]["ref"])
    assert Q1 in source["texte"] and F1 in source["texte"]


def test_une_question_que_personne_ne_sait_traduire_arrive_telle_quelle_marquee_non_traduite():
    client, clinique = _clinique("le soir")
    _poser(client, "Posso avere un altro cuscino?")
    ligne = clinique.carnet.lignes("question du soir")[0]
    assert ligne["donnees"]["traduction"] is None and ligne["donnees"]["traduit_par"] is None
    asyncio.run(clinique.horloge.sauter("le lendemain matin"))
    texte = _ligne_questions(clinique)["texte"]
    assert "Posso avere un altro cuscino?" in texte and "non traduite" in texte and "italien" in texte


def test_une_traduction_inventee_ou_vide_n_est_jamais_montree():
    class Bavard:  # un traducteur qui rend n'importe quoi : vide, pas du texte, ou le texte d'origine lui-même
        nom = "bavard"

        def __init__(self, rendu):
            self.rendu = rendu

        def traduire(self, texte, de, vers):
            return self.rendu

    for rendu in ("", "   ", None, 42, Q1):
        client, clinique = _clinique("le soir", traducteur=Bavard(rendu))
        _poser(client, Q1)
        assert clinique.carnet.lignes("question du soir")[0]["donnees"]["traduction"] is None, rendu

    class Casse:
        nom = "cassé"

        def traduire(self, texte, de, vers):
            raise TimeoutError("trop long")

    client, clinique = _clinique("le soir", traducteur=Casse())
    assert _poser(client, Q1)[0].status_code == 200  # la question part quand même, non traduite
    assert clinique.carnet.lignes("question du soir")[0]["donnees"]["traduction"] is None


def test_un_autre_traducteur_se_branche_et_son_nom_est_dit():
    class DeTest:
        nom = "traducteur de test (réponses fixes)"

        def traduire(self, texte, de, vers):
            return "Puis-je avoir un autre coussin ?" if (de, vers) == ("it", "fr") else None

    client, clinique = _clinique("le soir", traducteur=DeTest())
    _poser(client, "Posso avere un altro cuscino?")
    d = clinique.carnet.lignes("question du soir")[0]["donnees"]
    assert d["traduction"] == "Puis-je avoir un autre coussin ?" and d["traduit_par"] == "traducteur de test (réponses fixes)"


def test_une_question_de_sante_ne_recoit_pas_de_reponse_du_prototype():
    client, clinique = _clinique("le soir")
    r = _poser(client, SANTE)[0]
    dit = r.json()["dit"]
    assert r.status_code == 200 and "trasmessa al medico" in dit and "Non rispondo" in dit
    for mot in ("compress", "due", "sì", "no,", "può", "prenda"):
        assert mot not in dit.lower().replace("non rispondo", ""), mot  # ni conseil, ni oui, ni non
    assert len(clinique.carnet.lignes("question du soir")) == 1  # elle part chez le médecin, telle quelle
    assert clinique.carnet.lignes("question du soir")[0]["donnees"]["traduction"] is None  # et personne ne la traduit ici


def test_les_questions_ne_sont_lues_que_par_le_medecin():
    client, clinique = _clinique("le soir")
    _poser(client, Q1)
    for ecran, badge in (("soignant", SOIGNANT), ("accueil", "accueil"), ("therapeute", "therapeute-exemple")):
        page = client.get(f"/clinique/{ecran}", params={"badge": badge}).text
        assert "deambulatore" not in page and "marcher sans déambulateur" not in page, ecran


def test_le_traducteur_du_scenario_ne_connait_que_les_deux_questions_du_cahier():
    t = soir.TraducteurDuScenario()
    assert t.traduire(Q1, "it", "fr") == F1 and t.traduire("  mia figlia può venire DOMENICA ? ", "it", "fr") == F2
    assert t.traduire("Buongiorno", "it", "fr") is None and t.traduire(Q1, "de", "fr") is None and t.traduire(Q1, "it", "de") is None
    assert "fixe" in t.nom and "pas un modèle" in t.nom
