"""La clinique en boîte — T14, le rangement proposé par le cerveau (cahier 5.8).

« Fini » veut dire :
- type, date, auteur, patient et endroit sont proposés par le cerveau, avec un niveau de confiance ;
- une confiance basse donne « je ne suis pas sûr », et l'humain choisit ;
- la feuille sans nom n'est toujours pas rangée, même si le cerveau invente un patient ;
- un cerveau peut se tromper ou inventer : ce qu'il propose est vérifié contre le papier (type connu, patient écrit sur
  le papier et attendu aujourd'hui, date et auteur recopiés tels quels). Ce qui ne tient pas est retiré, et la
  confiance tombe ;
- si le cerveau ne répond pas, ou répond n'importe quoi, on retombe sur les règles simples, et on le dit.
Ici : un cerveau de TEST, qui donne des réponses fixes (cahier 2.8). Le vrai Apertus n'est pas sur l'iMac (R2, Q17) :
rien n'est mesuré avec lui. Internet coupé, aucun modèle.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique import papiers as piece
from briques.clinique.carnet import Carnet
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.papiers import CerveauDeTest, Papiers, proposer_avec_cerveau
from briques.clinique.porte import JournalDesAcces, PorteDeLecture, charger_badges

ACCUEIL = charger_badges()["accueil"]
PATIENTS = [{"id": "p01", "nom": "Madame Giulia B."}]
LETTRE = ("INVENTÉ — Studio medico Exemple, Dott. Exemple.\nLettera per la signora Giulia B.\n"
          "La signora inizia un soggiorno. Data: 3 novembre 2026.")
FEUILLE = "INVENTÉ — Feuille volante.\nRappel : apporter des chaussures fermées pour la séance.\nAucun nom sur cette feuille."
BONNE = {"type": "lettre du médecin traitant", "date": "3 novembre 2026", "auteur": "Studio medico Exemple, Dott. Exemple.",
         "patient": "Giulia B.", "confiance": "haute"}


def _proposer(reponse, texte=LETTRE, ecriture="tapée", patients=PATIENTS):
    return proposer_avec_cerveau(texte, ecriture, patients, CerveauDeTest(lambda t: reponse))


# ---------------------------------------------------------------------------------------------- le cerveau propose
def test_le_cerveau_propose_type_date_auteur_patient_endroit_avec_une_confiance():
    p = _proposer(BONNE)
    assert p["type"] == "lettre du médecin traitant" and p["endroit"] == "Courrier médical"
    assert p["date"] == "3 novembre 2026" and p["auteur"] == "Studio medico Exemple, Dott. Exemple."
    assert p["patient"] == "p01" and p["nom_du_patient"] == "Madame Giulia B."
    assert p["confiance"] == "haute" and p["dit"] == "" and p["raisons"] == []
    assert "cerveau de test" in p["version"] and "vérifié" in p["version"]


@pytest.mark.parametrize("niveau", ["basse", "moyenne"])
def test_une_confiance_qui_n_est_pas_haute_donne_je_ne_suis_pas_sur(niveau):
    p = _proposer({**BONNE, "confiance": niveau})
    assert p["confiance"] == "basse" and p["dit"] == "je ne suis pas sûr"
    assert any("cerveau" in r and niveau in r for r in p["raisons"])
    assert p["type"] == "lettre du médecin traitant"  # la proposition reste montrée : l'humain choisit


def test_un_papier_ecrit_a_la_main_n_est_jamais_sur_meme_si_le_cerveau_le_dit():
    p = _proposer(BONNE, ecriture="à la main")
    assert p["confiance"] == "basse" and p["dit"] == "je ne suis pas sûr"


# ---------------------------------------------------------------------------------------------- les verrous
def test_la_feuille_sans_nom_n_est_pas_rangee_meme_si_le_cerveau_invente_un_patient():
    p = _proposer({**BONNE, "patient": "Giulia B.", "type": "ordonnance de physiothérapie"}, texte=FEUILLE)
    assert p["patient"] is None and p["endroit"] is None and p["confiance"] == "basse"
    assert any("n'est pas écrit sur le papier" in r for r in p["raisons"])


def test_un_patient_ecrit_sur_le_papier_mais_pas_attendu_aujourd_hui_n_est_pas_range():
    p = _proposer({**BONNE, "patient": "Hans K."}, texte=LETTRE.replace("Giulia B.", "Hans K."))
    assert p["patient"] is None and any("aucun patient" in r for r in p["raisons"])


def test_un_type_que_la_liste_ne_connait_pas_est_retire():
    p = _proposer({**BONNE, "type": "diagnostic de la hanche"})
    assert p["type"] != "diagnostic de la hanche" and p["confiance"] == "basse"
    assert any("type" in r and "liste" in r for r in p["raisons"])


def test_une_date_ou_un_auteur_absents_du_papier_sont_retires():
    p = _proposer({**BONNE, "date": "12 mars 1999", "auteur": "Clinique du Lac"})
    assert p["date"] is None and p["auteur"] is None and p["confiance"] == "basse"
    assert sum("absent du papier" in r or "absente du papier" in r for r in p["raisons"]) == 2


def test_si_le_cerveau_et_les_regles_ne_sont_pas_d_accord_sur_le_type_ce_n_est_pas_sur():
    p = _proposer({**BONNE, "type": "carte d'assurance"})
    assert p["confiance"] == "basse" and any("pas d'accord" in r for r in p["raisons"])
    assert p["type"] == "carte d'assurance" and "lettre du médecin traitant" in " ".join(p["raisons"])  # les deux sont dits


# ---------------------------------------------------------------------------------------------- le cerveau ne répond pas
@pytest.mark.parametrize("reponse", [None, "n'importe quoi", {"type": 3}, [], {"confiance": "haute"}])
def test_une_reponse_illisible_fait_retomber_sur_les_regles_et_le_dit(reponse):
    p = _proposer(reponse)
    regles = piece.proposer(LETTRE, "tapée", PATIENTS)
    assert {c: p[c] for c in ("type", "patient", "date", "auteur", "endroit", "confiance")} == \
           {c: regles[c] for c in ("type", "patient", "date", "auteur", "endroit", "confiance")}
    assert "règles simples" in p["version"] and "le cerveau n'a pas répondu" in p["version"]


def test_un_cerveau_qui_casse_fait_retomber_sur_les_regles():
    def casse(texte):
        raise TimeoutError("trop long")

    p = proposer_avec_cerveau(LETTRE, "tapée", PATIENTS, CerveauDeTest(casse))
    assert "règles simples" in p["version"] and "TimeoutError" in p["version"]
    assert p["type"] == "lettre du médecin traitant"


def test_le_cerveau_ne_recoit_que_le_texte_les_types_et_les_noms_possibles():
    recu = {}

    class Espion:
        nom = "espion"

        def lire(self, texte, types, patients):
            recu.update(texte=texte, types=types, patients=patients)
            return BONNE

    proposer_avec_cerveau(LETTRE, "tapée", PATIENTS, Espion())
    assert recu["texte"] == LETTRE and recu["types"] == list(piece.TYPES) and recu["patients"] == ["Madame Giulia B."]


# ---------------------------------------------------------------------------------------------- dans la pile et à l'écran
def _reponses_fixes(texte):
    """Le cerveau de test : des réponses fixes pour les papiers du scénario, d'après leur première ligne."""
    if "Studio medico" in texte:
        return {"type": "lettre du médecin traitant", "date": None, "auteur": "Studio medico Exemple, Dott. Exemple.",
                "patient": "Giulia B.", "confiance": "haute"}
    if "Elenco dei medicinali" in texte:
        return {"type": "liste de médicaments", "date": None, "auteur": None, "patient": "Giulia B.", "confiance": "basse"}
    if "Assurance Exemple" in texte:
        return {"type": "carte d'assurance", "date": None, "auteur": "Assurance Exemple", "patient": "Giulia B.", "confiance": "haute"}
    return {"type": "ordonnance de physiothérapie", "date": None, "auteur": None, "patient": "Giulia B.", "confiance": "haute"}


def test_avec_un_cerveau_la_pile_range_comme_avant_et_la_feuille_sans_nom_reste_a_trier():
    carnet = Carnet()
    papiers = Papiers(PorteDeLecture(journal=JournalDesAcces()), carnet, cerveau=CerveauDeTest(_reponses_fixes))
    pile = papiers.pile(ACCUEIL)
    assert [p["id"] for p in pile["a_trier"]] == ["f-01"]  # le cerveau lui a inventé un patient : refusé
    propositions = {p["id"]: p["proposition"] for p in pile["a_valider"]}
    assert propositions["p01-d1"]["confiance"] == "haute" and propositions["p01-d1"]["endroit"] == "Courrier médical"
    assert propositions["p01-d2"]["confiance"] == "basse" and propositions["p01-d2"]["dit"] == "je ne suis pas sûr"
    assert "cerveau de test" in pile["version"]
    valide = papiers.valider(ACCUEIL, "p01-d1")
    assert valide["etat"] == "validé" and "validée par" in valide["valide"]
    with pytest.raises(piece.PapierRefuse):
        papiers.valider(ACCUEIL, "p01-d2")  # pas sûr : l'humain doit choisir le type
    assert papiers.valider(ACCUEIL, "p01-d2", type="liste de médicaments")["choisi_par_un_humain"] is True
    with pytest.raises(piece.PapierRefuse):
        papiers.valider(ACCUEIL, "f-01", type="ordonnance de physiothérapie")
    assert all("cerveau de test" in l["donnees"]["version"] for l in carnet.lignes("rangement de papier"))


def test_sans_cerveau_rien_ne_change_les_regles_simples_et_l_ecran_le_dit():
    from briques.clinique.ecrans import brancher_ecrans

    horloge = HorlogeDeDemonstration()
    app = FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge), code_equipe="x")
    assert clinique.papiers.cerveau is None
    page = TestClient(app).get("/clinique/accueil/papiers", params={"badge": "accueil"}).text
    assert "règles simples, sans modèle" in page
    clinique.papiers.cerveau = CerveauDeTest(_reponses_fixes)
    clinique.carnet._lignes.clear()
    page = TestClient(app).get("/clinique/accueil/papiers", params={"badge": "accueil"}).text
    assert "cerveau de test" in page and "je ne suis pas sûr" in page
