"""La clinique en boîte — T09, les papiers, version simple (cahier 5.8 et 6.4).

« Fini » veut dire :
- les trois papiers de la patiente sont proposés au bon endroit (type, patient, endroit du dossier, confiance) ;
- un doigt valide ; la proposition validée est au carnet, « validée par (badge), à (heure) », pas au faux dossier ;
- la feuille sans nom reste dans « à trier » : on ne peut pas la ranger ;
- une confiance basse dit « je ne suis pas sûr », et l'humain choisit.
À partir des textes de référence, par des règles simples. Aucun modèle, aucune image (T14, T15). Internet coupé.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique import dossier as faux_dossier
from briques.clinique.carnet import Carnet
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.porte import AccesRefuse, JournalDesAcces, PorteDeLecture, charger_badges

BANDEAU = "DONNÉES INVENTÉES — DÉMONSTRATION"
GIULIA = [{"id": "p01", "nom": "Madame Giulia B."}]
ATTENDUS = {"p01-d1": ("lettre du médecin traitant", "Courrier médical"),
            "p01-d2": ("liste de médicaments", "Médicaments"),
            "p01-d3": ("carte d'assurance", "Assurance et administratif")}


def _pieces():
    from briques.clinique.papiers import Papiers

    horloge = HorlogeDeDemonstration()
    porte = PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour)
    carnet = Carnet(horloge=horloge)
    return Papiers(porte, carnet), charger_badges(), carnet, porte


def _client():
    from briques.clinique.ecrans import brancher_ecrans

    horloge = HorlogeDeDemonstration()
    app = FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge))
    return TestClient(app), clinique


def _texte(patient: str, document: str) -> dict:
    return next(dict(d) for d in faux_dossier.charger().patient(patient)["DocumentReference"] if d["id"] == document)


# ---------------------------------------------------------------- la proposition, à partir du texte seulement
def test_les_trois_papiers_de_la_patiente_sont_proposes_au_bon_endroit():
    papiers, badges, *_ = _pieces()
    pile = papiers.pile(badges["accueil"])
    assert [p["id"] for p in pile["a_valider"]] == ["p01-d1", "p01-d2", "p01-d3"]
    for papier in pile["a_valider"]:
        proposition = papier["proposition"]
        genre, endroit = ATTENDUS[papier["id"]]
        assert (proposition["type"], proposition["endroit"]) == (genre, endroit)
        assert proposition["patient"] == "p01" and proposition["nom_du_patient"] == "Madame Giulia B."
        assert proposition["confiance"] == "haute" and papier["etat"] == "proposé"
        assert {"type", "date", "auteur", "patient", "endroit", "confiance"} <= set(proposition)


def test_la_proposition_vient_du_texte_pas_de_l_etiquette_du_dossier():
    from briques.clinique.papiers import proposer

    lettre = _texte("p01", "p01-d1")
    proposition = proposer(lettre["texte"], "tapée", GIULIA)  # ni genre, ni titre, ni identifiant : le texte seul
    assert proposition["type"] == "lettre du médecin traitant" and proposition["patient"] == "p01"
    assert proposition["auteur"] == "Studio medico Exemple, Dott. Exemple."  # recopié tel quel
    assert proposition["date"] is None  # aucune date dans cette lettre : on n'en invente pas


def test_une_date_ecrite_dans_le_papier_est_recopiee_telle_quelle():
    from briques.clinique.papiers import proposer

    brief = _texte("p07", "p07-d1")
    proposition = proposer(brief["texte"], "tapée", [{"id": "p07", "nom": "Madame Ursula W."}])
    assert proposition["date"] == "20. November" and proposition["type"] == "lettre du médecin traitant"


def test_les_autres_documents_du_cahier_sont_reconnus_par_leur_texte():
    from briques.clinique.papiers import proposer

    radio = proposer(_texte("p02", "p02-d1")["texte"], "tapée", [{"id": "p02", "nom": "Monsieur Hans K."}])
    assert (radio["type"], radio["endroit"], radio["confiance"]) == ("rapport de radiologie", "Imagerie", "haute")
    ordonnance = proposer(_texte("p03", "p03-d1")["texte"], "tapée", [{"id": "p03", "nom": "Madame Claire D."}])
    assert (ordonnance["type"], ordonnance["endroit"]) == ("ordonnance de physiothérapie", "Ordonnances")


def test_le_formulaire_ecrit_a_la_main_donne_je_ne_suis_pas_sur():
    from briques.clinique.papiers import proposer

    formulaire = _texte("p04", "p04-d1")
    proposition = proposer(formulaire["texte"], formulaire["ecriture"], [{"id": "p04", "nom": "Monsieur Peter S."}])
    assert proposition["confiance"] == "basse" and proposition["dit"] == "je ne suis pas sûr"
    assert proposition["patient"] == "p04" and proposition["raisons"]


def test_un_texte_qu_on_ne_reconnait_pas_donne_je_ne_suis_pas_sur():
    from briques.clinique.papiers import proposer

    proposition = proposer("INVENTÉ — Bonjour pour Giulia B. Rien de plus.", "tapée", GIULIA)
    assert proposition["type"] is None and proposition["endroit"] is None and proposition["dit"] == "je ne suis pas sûr"


def test_aucun_patient_ne_correspond_pas_de_rangement():
    from briques.clinique.papiers import proposer

    proposition = proposer(_texte("p02", "p02-d1")["texte"], "tapée", GIULIA)  # Hans K. n'est pas dans la liste donnée
    assert proposition["patient"] is None and proposition["endroit"] is None and "Hans" not in str(proposition["nom_du_patient"])


# ---------------------------------------------------------------- la feuille sans nom reste « à trier »
def test_la_feuille_sans_nom_reste_dans_a_trier_et_ne_peut_pas_etre_rangee():
    from briques.clinique.papiers import PapierRefuse

    papiers, badges, carnet, _ = _pieces()
    accueil = badges["accueil"]
    pile = papiers.pile(accueil)
    assert [p["id"] for p in pile["a_trier"]] == ["f-01"] and pile["a_trier"][0]["etat"] == "à trier"
    assert pile["a_trier"][0]["proposition"]["patient"] is None
    with pytest.raises(PapierRefuse):
        papiers.valider(accueil, "f-01")
    with pytest.raises(PapierRefuse):
        papiers.valider(accueil, "f-01", type="carte d'assurance")
    assert [p["id"] for p in papiers.pile(accueil)["a_trier"]] == ["f-01"]
    assert not [l for l in carnet.lignes("rangement de papier") if l["donnees"]["etat"] == "validé"]


# ---------------------------------------------------------------- un doigt valide ; au carnet, pas au faux dossier
def test_un_doigt_valide_et_la_proposition_validee_est_au_carnet_pas_au_faux_dossier():
    avant = faux_dossier.empreinte()
    papiers, badges, carnet, _ = _pieces()
    accueil = badges["accueil"]
    papiers.pile(accueil)
    valide = papiers.valider(accueil, "p01-d1")
    assert valide["etat"] == "validé" and valide["valide"] == "validée par Accueil, à Jour 1 — 9 h 00"
    lignes = [l for l in carnet.lignes("rangement de papier") if l["donnees"]["etat"] == "validé"]
    assert len(lignes) == 1 and lignes[0]["valide_par_un_humain"] is True and lignes[0]["qui"] == "accueil"
    assert lignes[0]["donnees"]["papier"] == "p01-d1" and lignes[0]["donnees"]["endroit"] == "Courrier médical"
    pile = papiers.pile(accueil)
    assert [p["id"] for p in pile["a_valider"]] == ["p01-d2", "p01-d3"] and [p["id"] for p in pile["valides"]] == ["p01-d1"]
    assert faux_dossier.empreinte() == avant


def test_les_propositions_sont_au_carnet_une_seule_fois_et_pas_validees_par_un_humain():
    papiers, badges, carnet, _ = _pieces()
    for _ in range(3):
        papiers.pile(badges["accueil"])
    lignes = carnet.lignes("rangement de papier")
    assert sorted(l["donnees"]["papier"] for l in lignes) == ["f-01", "p01-d1", "p01-d2", "p01-d3"]
    assert all(l["valide_par_un_humain"] is False for l in lignes)


def test_valider_deux_fois_ne_compte_qu_une_fois():
    papiers, badges, carnet, _ = _pieces()
    papiers.valider(badges["accueil"], "p01-d3")
    papiers.valider(badges["accueil"], "p01-d3")
    assert len([l for l in carnet.lignes("rangement de papier") if l["donnees"]["etat"] == "validé"]) == 1


def test_l_humain_peut_corriger_le_type_et_un_type_inconnu_est_refuse():
    from briques.clinique.papiers import PapierRefuse

    papiers, badges, *_ = _pieces()
    with pytest.raises(PapierRefuse):
        papiers.valider(badges["accueil"], "p01-d2", type="recette de cuisine")
    corrige = papiers.valider(badges["accueil"], "p01-d2", type="lettre du médecin traitant")
    assert corrige["type"] == "lettre du médecin traitant" and corrige["endroit"] == "Courrier médical"
    assert corrige["choisi_par_un_humain"] is True


def test_confiance_basse_l_humain_doit_choisir():
    from briques.clinique.papiers import PapierRefuse

    papiers, badges, _, porte = _pieces()
    porte.jour = lambda: 0  # le jour où Monsieur Peter S. arrive, avec son formulaire écrit à la main
    accueil = badges["accueil"]
    papier = next(p for p in papiers.pile(accueil)["a_valider"] if p["id"] == "p04-d1")
    assert papier["proposition"]["dit"] == "je ne suis pas sûr"
    with pytest.raises(PapierRefuse):
        papiers.valider(accueil, "p04-d1")  # pas de validation d'un doigt quand le prototype n'est pas sûr
    valide = papiers.valider(accueil, "p04-d1", type="formulaire d'admission")
    assert valide["etat"] == "validé" and valide["choisi_par_un_humain"] is True


def test_seul_l_accueil_range_les_papiers():
    papiers, badges, *_ = _pieces()
    for autre in ("soignant-etage-2", "medecin-exemple", "direction", "robot-r1", "patient-p01", "therapeute-exemple", "assistant"):
        with pytest.raises(AccesRefuse):
            papiers.pile(badges[autre])
        with pytest.raises(AccesRefuse):
            papiers.valider(badges[autre], "p01-d1")


def test_un_papier_inconnu_est_refuse():
    from briques.clinique.papiers import PapierRefuse

    papiers, badges, *_ = _pieces()
    with pytest.raises(PapierRefuse):
        papiers.valider(badges["accueil"], "p02-d1")  # pas dans la pile de l'accueil aujourd'hui


# ---------------------------------------------------------------- ce que le relecteur a trouvé
@pytest.mark.parametrize("texte", [
    "INVENTÉ — Klinik Exemple.\nAustrittsbericht für Frau Giulia B.",
    "INVENTÉ — Elenco degli appuntamenti della signora Giulia B.",
    "INVENTÉ — Hôtel Exemple.\nLettre de bienvenue pour Giulia B.",
    "INVENTÉ — Praxis Exemple\nRechnung für Giulia B.",
    "INVENTÉ — Briefkasten Giulia B.",
])
def test_un_seul_mot_ne_suffit_pas_pour_etre_sur(texte):
    from briques.clinique.papiers import proposer

    proposition = proposer(texte, "tapée", GIULIA)
    assert proposition["confiance"] == "basse" and proposition["dit"] == "je ne suis pas sûr"


def test_le_nom_se_lit_en_entier_sur_une_ligne():
    from briques.clinique.papiers import proposer

    lettre = "INVENTÉ — Studio medico Exemple.\nLettera per {} dal medico curante."
    assert proposer(lettre.format("Jean-Giulia B."), "tapée", GIULIA)["patient"] is None
    assert proposer(lettre.format("Giulia Bianchi"), "tapée", GIULIA)["patient"] is None
    assert proposer(lettre.format("Giulia\nB."), "tapée", GIULIA)["patient"] is None
    compose = [{"id": "p90", "nom": "Madame Anne-Marie D."}]
    assert proposer(lettre.format("Anne-Marie D."), "tapée", compose)["patient"] == "p90"
    assert proposer(lettre.format("Giulia B."), "tapée", [{"id": "p91", "nom": "Giulia"}])["patient"] is None  # pas d'erreur


def test_une_ligne_qui_nomme_un_patient_n_est_pas_un_auteur():
    from briques.clinique.papiers import proposer

    texte = "INVENTÉ — Lettera per la signora Giulia B., Clinica Exemple.\nStudio medico, medico curante."
    assert proposer(texte, "tapée", GIULIA)["auteur"] is None


def test_une_autre_piece_ne_peut_pas_faire_ranger_la_feuille_sans_nom():
    from briques.clinique.papiers import PapierRefuse

    papiers, badges, carnet, _ = _pieces()
    accueil = badges["accueil"]
    papiers.pile(accueil)
    fausse = {"papier": "f-01", "etat": "proposé", "type": "carte d'assurance", "patient": "p01", "texte": "x",
              "nom_du_patient": "Madame Giulia B.", "endroit": "Assurance et administratif", "confiance": "haute"}
    carnet.ecrire(badges["soignant-etage-2"], "rangement de papier", fausse, valide_par_un_humain=False)
    carnet.ecrire(badges["robot-r1"], "rangement de papier", {"papier": "f-01", "etat": "validé"}, valide_par_un_humain=False)
    carnet.ecrire(badges["robot-r1"], "rangement de papier", {"etat": "bizarre"}, valide_par_un_humain=False)
    with pytest.raises(PapierRefuse):
        papiers.valider(accueil, "f-01")
    assert [p["id"] for p in papiers.pile(accueil)["a_trier"]] == ["f-01"]  # et la pile ne casse pas


def test_un_papier_pas_valide_attend_encore_le_lendemain():
    papiers, badges, _, porte = _pieces()
    accueil = badges["accueil"]
    papiers.valider(accueil, "p01-d1")
    porte.jour = lambda: 2  # le lendemain : Madame Giulia B. n'est plus une « arrivée du jour »
    pile = papiers.pile(accueil)
    assert [p["id"] for p in pile["a_valider"]] == ["p01-d2", "p01-d3"] and [p["id"] for p in pile["valides"]] == ["p01-d1"]
    assert papiers.valider(accueil, "p01-d2")["etat"] == "validé"


# ---------------------------------------------------------------- à l'écran de l'accueil
def test_l_ecran_de_l_accueil_mene_aux_papiers_a_valider():
    client, _ = _client()
    texte = client.get("/clinique/accueil/contenu").text
    assert 'href="/clinique/accueil/papiers?badge=accueil"' in texte and "Papiers à valider" in texte


def test_la_page_des_papiers_montre_les_propositions_et_un_doigt_valide():
    client, clinique = _client()
    page = client.get("/clinique/accueil/papiers", params={"badge": "accueil"})
    assert page.status_code == 200 and BANDEAU in page.text and "Jour 1 — 9 h 00" in page.text
    assert page.text.count("data-valider=") == 3 and "À trier" in page.text and "Papier à trier" in page.text
    assert "Courrier médical" in page.text and "Madame Giulia B." in page.text
    # Adapté au tour 70 (H01, réponse de Hiba à Q18) : la page ne montre plus aucune ligne du papier. Avant, cet essai
    # demandait « Feuille volante » et « Lettera per la signora » (le début du papier) à l'écran.
    assert "Feuille volante" not in page.text and "Lettera per la signora" not in page.text
    assert "intervento" not in page.text and "riabilitazione" not in page.text  # l'accueil ne lit pas la raison du séjour
    assert "riabilitazione" not in client.get("/api/clinique/papiers", params={"badge": "accueil"}).text
    reponse = client.post("/api/clinique/papiers/valider", json={"badge": "accueil", "papier": "p01-d1"})
    assert reponse.status_code == 200 and reponse.json()["etat"] == "validé"
    apres = client.get("/clinique/accueil/papiers/contenu", params={"badge": "accueil"}).text
    assert apres.count("data-valider=") == 2 and "validée par Accueil, à Jour 1 — 9 h 00" in apres
    assert len([l for l in clinique.carnet.lignes("rangement de papier") if l["donnees"]["etat"] == "validé"]) == 1


def test_a_l_ecran_les_refus_disent_pourquoi():
    client, _ = _client()
    feuille = client.post("/api/clinique/papiers/valider", json={"badge": "accueil", "papier": "f-01"})
    assert feuille.status_code == 400 and "à trier" in feuille.json()["detail"]
    autre = client.post("/api/clinique/papiers/valider", json={"badge": "soignant-etage-2", "papier": "p01-d1"})
    assert autre.status_code == 403
    ailleurs = client.post("/api/clinique/papiers/valider", json={"badge": "accueil", "papier": "p01-d1"},
                           headers={"origin": "http://ailleurs.example"})
    assert ailleurs.status_code == 403
    page = client.get("/clinique/accueil/papiers", params={"badge": "soignant-etage-2"})
    assert "Accès refusé" in page.text and "Lettera" not in page.text


# ---------------------------------------------------------------- la grande répétition
def test_les_etapes_4_et_5_de_la_grande_repetition():
    from briques.clinique import repetition

    quatre, cinq = repetition.CONTROLES[4](), repetition.CONTROLES[5]()
    assert quatre.reussie is True and quatre.etiquette == "SIMULÉ" and "texte" in quatre.detail
    assert cinq.reussie is True and cinq.etiquette == "SIMULÉ" and "à trier" in cinq.detail
