"""La clinique en boîte — T10, l'accueil, version écrite (cahier 5.9).

« Fini » veut dire :
- la même arrivée en italien, allemand, français et anglais donne la bonne réponse dans la bonne langue :
  la chambre, l'étage, la première heure du programme, « je ne vous accompagne pas », le chemin ;
- l'étage reçoit le message ;
- la question sur la santé est refusée, poliment, et un humain est appelé ;
- un nom inconnu appelle un humain, sans insister.
La phrase d'arrivée est tapée au clavier. Pas de voix (T20), pas de robot, pas de visage. Internet coupé.
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
ARRIVEES = {"it": ("Buongiorno, sono Giulia B.", "Non la accompagno"),
            "de": ("Guten Tag, ich bin Giulia B.", "Ich begleite Sie nicht"),
            "fr": ("Bonjour, je suis Giulia B.", "Je ne vous accompagne pas"),
            "en": ("Hello, my name is Giulia B.", "I am not coming with you")}
SANTE = {"fr": "Pourquoi Madame B. est-elle ici ?", "de": "Warum ist Frau B. hier?",
         "it": "Perché la signora B. è qui?", "en": "Why is Mrs B. here?"}


def _pieces():
    from briques.clinique.accueil import AccueilDuHall

    horloge = HorlogeDeDemonstration()
    porte = PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour)
    carnet = Carnet(horloge=horloge)
    badges = charger_badges()
    return AccueilDuHall(porte, carnet, badges["robot-r1"]), badges, carnet, porte


def _client():
    from briques.clinique.ecrans import brancher_ecrans

    horloge = HorlogeDeDemonstration()
    app = FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge))
    return TestClient(app), clinique


# ---------------------------------------------------------------- la même arrivée, en quatre langues
@pytest.mark.parametrize("langue", ["it", "de", "fr", "en"])
def test_la_meme_arrivee_donne_la_bonne_reponse_dans_la_bonne_langue(langue):
    accueil, *_ = _pieces()
    phrase, je_n_accompagne_pas = ARRIVEES[langue]
    reponse = accueil.entendre(phrase)
    assert reponse["cas"] == "arrivée" and reponse["langue"] == langue
    assert "Giulia" in reponse["dit"] and "12" in reponse["dit"] and "10:00" in reponse["dit"]  # chambre, première heure
    assert je_n_accompagne_pas in reponse["dit"]
    assert reponse["chambre"] == 12 and reponse["etage"] == 2 and reponse["premiere_heure"] == "10:00"
    assert reponse["etiquette"] == "SIMULÉ" and reponse["marque"] == "données inventées"


def test_les_quatre_reponses_sont_differentes_et_la_langue_du_dossier_ne_decide_pas():
    accueil, *_ = _pieces()
    dits = {langue: accueil.entendre(phrase)["dit"] for langue, (phrase, _) in ARRIVEES.items()}
    assert len(set(dits.values())) == 4  # le dossier dit « italien », mais on répond dans la langue entendue


def test_le_robot_montre_le_chemin_sans_changer_d_etage_lui_meme():
    accueil, *_ = _pieces()
    chemin = accueil.entendre(ARRIVEES["it"][0])["chemin"]
    assert [pas["lieu"] for pas in chemin] == ["Hall", "Ascenseur (rez-de-chaussée)", "Ascenseur (étage 2)",
                                               "Poste de soins", "Chambre 11", "Chambre 12"]
    assert chemin[1]["metres"] == 10 and chemin[2]["metres"] is None  # l'ascenseur : pas de distance inventée


def test_la_reponse_ne_dit_rien_sur_la_sante():
    accueil, *_ = _pieces()
    for phrase, _ in ARRIVEES.values():
        texte = str(accueil.entendre(phrase)).lower()
        for interdit in ("hanche", "réadaptation", "anca", "hüfte", "hip", "déambulateur", "medicinale"):
            assert interdit not in texte


# ---------------------------------------------------------------- l'étage reçoit le message
def test_l_etage_recoit_le_message():
    accueil, badges, carnet, _ = _pieces()
    accueil.entendre(ARRIVEES["it"][0])
    messages = accueil.messages_pour_l_etage(badges["soignant-etage-2"])
    assert len(messages) == 1 and messages[0]["etage"] == 2 and messages[0]["patient"] == "p01"
    assert "Madame Giulia B." in messages[0]["texte"] and "12" in messages[0]["texte"] and "italien" in messages[0]["texte"]
    ligne = carnet.lignes("message pour l'étage")[0]
    assert ligne["qui"] == "robot-r1" and ligne["valide_par_un_humain"] is False


def test_la_meme_arrivee_dite_deux_fois_ne_previent_l_etage_qu_une_fois():
    accueil, badges, *_ = _pieces()
    accueil.entendre(ARRIVEES["it"][0])
    accueil.entendre(ARRIVEES["de"][0])
    assert len(accueil.messages_pour_l_etage(badges["soignant-etage-2"])) == 1


def test_le_message_est_pour_les_soignants_de_cet_etage():
    from dataclasses import replace

    accueil, badges, *_ = _pieces()
    accueil.entendre(ARRIVEES["it"][0])
    assert accueil.messages_pour_l_etage(replace(badges["soignant-etage-2"], etage=1)) == []
    for autre in ("patient-p01", "direction", "robot-r1", "accueil"):
        with pytest.raises(AccesRefuse):
            accueil.messages_pour_l_etage(badges[autre])


# ---------------------------------------------------------------- dans le hall, rien sur la santé
@pytest.mark.parametrize("langue", ["fr", "de", "it", "en"])
def test_la_question_sur_la_sante_est_refusee_poliment(langue):
    accueil, badges, carnet, _ = _pieces()
    reponse = accueil.entendre(SANTE[langue])
    assert reponse["cas"] == "santé" and reponse["langue"] == langue
    for fuite in ("Giulia", "12", "hanche", "10:00"):
        assert fuite not in reponse["dit"]  # ni « elle est ici », ni sa chambre, ni pourquoi
    assert reponse["chemin"] == [] and reponse["regle"] == "Dans le hall, le robot ne dit rien sur la santé."
    assert carnet.lignes("message pour l'étage") == []
    appels = accueil.appels(badges["accueil"])
    assert len(appels) == 1 and appels[0]["raison"] == "question de santé dans le hall" and appels[0]["langue"] == langue


def test_d_autres_questions_de_sante_sont_refusees_aussi():
    accueil, *_ = _pieces()
    for phrase in ("Quelle est la maladie de Giulia B. ?", "Bonjour, je suis Giulia B., quel médicament dois-je prendre ?",
                   "Was ist ihre Diagnose?", "Is she sick?", "Che malattia ha la signora?"):
        reponse = accueil.entendre(phrase)
        assert reponse["cas"] == "santé", phrase
        assert "12" not in reponse["dit"]


def test_en_francais_le_refus_dit_je_transmets_a_l_equipe():
    accueil, *_ = _pieces()
    assert "Je transmets à l'équipe" in accueil.entendre(SANTE["fr"])["dit"]


# ---------------------------------------------------------------- un nom inconnu appelle un humain
@pytest.mark.parametrize("phrase,langue", [("Buongiorno, sono Marco T.", "it"), ("Guten Tag, ich bin Hans K.", "de"),
                                           ("Bonjour, je suis Paolo R.", "fr"), ("Hello", "en")])
def test_un_nom_inconnu_appelle_un_humain_sans_insister(phrase, langue):
    accueil, badges, carnet, _ = _pieces()
    reponse = accueil.entendre(phrase)
    assert reponse["cas"] == "inconnu" and reponse["langue"] == langue and reponse["chemin"] == []
    assert "?" not in reponse["dit"] and "12" not in reponse["dit"]  # il ne redemande pas, il ne donne aucune chambre
    appels = accueil.appels(badges["accueil"])
    assert len(appels) == 1 and appels[0]["raison"] == "nom inconnu dans le hall" and appels[0]["ou"] == "Hall"
    assert "Marco" not in str(carnet.lignes()) and "Hans" not in str(carnet.lignes())  # le nom dit n'est pas gardé
    assert carnet.lignes("message pour l'étage") == []


def test_un_prenom_connu_avec_un_autre_nom_de_famille_n_est_pas_la_personne():
    accueil, badges, *_ = _pieces()
    reponse = accueil.entendre("Bonjour, je suis Giulia Rossi.")
    assert reponse["cas"] == "inconnu" and "12" not in str(reponse) and "?" not in reponse["dit"]
    assert accueil.appels(badges["accueil"])[0]["raison"] == "phrase pas comprise dans le hall"


def test_hans_k_existe_mais_n_arrive_pas_aujourd_hui_le_robot_ne_dit_rien_de_lui():
    accueil, *_ = _pieces()
    reponse = accueil.entendre("Guten Tag, ich bin Hans K.")
    assert reponse["cas"] == "inconnu" and "Hans" not in reponse["dit"]


def test_une_langue_non_reconnue_repond_en_francais_et_le_dit():
    accueil, *_ = _pieces()
    reponse = accueil.entendre("Giulia B.")
    assert reponse["cas"] == "arrivée" and reponse["langue"] == "fr" and reponse["langue_sure"] is False


# ---------------------------------------------------------------- ce que le relecteur a trouvé
@pytest.mark.parametrize("phrase", [
    "Où est Giulia ?", "Je cherche Giulia B.", "Is Giulia B. a patient here?", "Je suis le mari de Giulia B.",
    "Je ne suis pas Giulia B.", "Bonjour, je suis Marco, je viens voir Giulia B.", "giulia", "Giulia",
    "Ich bin nicht Giulia B.", "Non sono Giulia B.", "C'est Giulia B. ?", "je suis giulia rossi", "giulia r.",
    "De quoi souffre Giulia ?", "Giulia a-t-elle un cancer ?", "Pourquoi Giulia est-elle là ?", "Was hat Giulia?",
    "Was fehlt Giulia B.?", "Wieso ist Giulia da?", "Che cos'ha Giulia?", "Come mai Giulia B. è qui?",
    "Giulia sta male?", "What's wrong with Giulia?", "Is Giulia ill?", "Why was Giulia B. admitted?",
])
def test_seule_une_simple_arrivee_recoit_la_chambre(phrase):
    accueil, badges, carnet, _ = _pieces()
    reponse = accueil.entendre(phrase)
    assert reponse["cas"] in ("santé", "inconnu"), phrase
    assert "12" not in str(reponse) and reponse["chemin"] == [] and reponse["etage_prevenu"] is False
    assert carnet.lignes("message pour l'étage") == [] and len(accueil.appels(badges["accueil"])) == 1


@pytest.mark.parametrize("phrase", ["De quoi souffre Giulia ?", "Pourquoi Giulia est-elle là ?", "Was fehlt Giulia B.?",
                                    "Wieso ist Giulia da?", "Giulia sta male?", "Is Giulia ill?", "Why was Giulia B. admitted?"])
def test_ces_questions_de_sante_recoivent_le_refus_sur_la_sante(phrase):
    accueil, *_ = _pieces()
    assert accueil.entendre(phrase)["cas"] == "santé"


@pytest.mark.parametrize("phrase", ["giulia b", "GIULIA B.", "Buon giorno, Giulia B.", "Hi, it's Giulia B.",
                                    "Guten Tag, mein Name ist Giulia Bianchi", "Salve, mi chiamo Giulia B., grazie"])
def test_une_simple_arrivee_marche_aussi_sans_majuscules_ni_formule_exacte(phrase):
    accueil, *_ = _pieces()
    reponse = accueil.entendre(phrase)
    assert reponse["cas"] == "arrivée" and reponse["chambre"] == 12, phrase


def test_la_reponse_du_hall_ne_rend_ni_numero_de_dossier_ni_texte_du_message():
    accueil, *_ = _pieces()
    reponse = accueil.entendre(ARRIVEES["it"][0])
    assert "p01" not in str(reponse) and "Madame" not in str(reponse) and reponse["etage_prevenu"] is True


def test_etage_inconnu_pas_de_promesse_un_humain_est_appele():
    accueil, badges, carnet, porte = _pieces()
    porte.jour = lambda: -1  # le jour où Madame Jeanne M. arrive : chambre 15, étage pas noté dans le faux dossier
    reponse = accueil.entendre("Bonjour, je suis Jeanne M.")
    assert reponse["cas"] == "arrivée" and reponse["etage_prevenu"] is False and reponse["chemin"] == []
    assert "on vous attend" not in reponse["dit"] and "15" not in reponse["dit"]
    assert carnet.lignes("message pour l'étage") == []
    assert accueil.appels(badges["accueil"])[0]["raison"] == "étage inconnu pour une arrivée"


def test_un_soignant_sans_etage_ne_lit_aucun_message():
    from dataclasses import replace

    accueil, badges, *_ = _pieces()
    accueil.entendre(ARRIVEES["it"][0])
    assert accueil.messages_pour_l_etage(replace(badges["soignant-etage-2"], etage=None)) == []


def test_un_autre_robot_ne_peut_pas_fausser_les_messages_du_hall():
    from briques.clinique.porte import Badge

    accueil, badges, carnet, _ = _pieces()
    autre = Badge(id="robot-r2", role="robot", libelle="Robot R2")
    carnet.ecrire(autre, "message pour l'étage", {"etage": 2, "patient": "p01", "texte": "FAUX"}, valide_par_un_humain=False)
    carnet.ecrire(autre, "appel d'un humain", {"ou": "Hall", "raison": "FAUX"}, valide_par_un_humain=False)
    accueil.entendre(ARRIVEES["it"][0])
    messages = accueil.messages_pour_l_etage(badges["soignant-etage-2"])
    assert len(messages) == 1 and "FAUX" not in str(messages) and accueil.appels(badges["accueil"]) == []


def test_le_chemin_d_une_chambre_hors_du_plan_s_arrete_a_l_ascenseur_de_l_etage():
    accueil, *_ = _pieces()
    assert [p["lieu"] for p in accueil._chemin(20, 2)] == ["Hall", "Ascenseur (rez-de-chaussée)", "Ascenseur (étage 2)"]
    assert accueil._chemin(31, 3) is None  # pas d'ascenseur connu pour l'étage 3 : pas de faux chemin


# ---------------------------------------------------------------- par la porte, sans rien écrire au faux dossier
def test_le_robot_du_hall_ne_recoit_de_la_porte_rien_sur_la_sante():
    _, badges, _, porte = _pieces()
    arrivees = porte.arrivees_pour_le_hall(badges["robot-r1"])
    assert [a["id"] for a in arrivees] == ["p01"]
    assert set(arrivees[0]) == {"id", "nom", "prenom", "initiale", "langue", "chambre", "etage", "premiere_heure"}
    for autre in ("soignant-etage-2", "medecin-exemple", "patient-p01", "direction"):
        with pytest.raises(AccesRefuse):
            porte.arrivees_pour_le_hall(badges[autre])


def test_rien_ne_s_ecrit_dans_le_faux_dossier_et_tout_est_au_journal_des_acces():
    avant = faux_dossier.empreinte()
    accueil, _, _, porte = _pieces()
    for phrase in (ARRIVEES["it"][0], SANTE["fr"], "Buongiorno, sono Marco T."):
        accueil.entendre(phrase)
    assert faux_dossier.empreinte() == avant
    assert any(l["quoi"] == "arrivées pour le hall" and l["qui"] == "robot-r1" for l in porte.journal.lignes())


def test_seul_un_robot_tient_l_accueil_du_hall():
    from briques.clinique.accueil import AccueilDuHall

    _, badges, carnet, porte = _pieces()
    with pytest.raises(ValueError):
        AccueilDuHall(porte, carnet, badges["soignant-etage-2"])


# ---------------------------------------------------------------- à l'écran
def test_la_page_du_hall_la_phrase_tapee_recoit_sa_reponse():
    client, _ = _client()
    page = client.get("/clinique/hall")
    assert page.status_code == 200 and BANDEAU in page.text and "SIMULÉ" in page.text and "Jour 1 — 9 h 00" in page.text
    assert 'href="/clinique/hall"' in client.get("/clinique").text
    reponse = client.post("/api/clinique/hall/entendre", json={"texte": ARRIVEES["it"][0]})
    assert reponse.status_code == 200 and reponse.json()["langue"] == "it" and "Non la accompagno" in reponse.json()["dit"]
    ailleurs = client.post("/api/clinique/hall/entendre", json={"texte": "x"}, headers={"origin": "http://ailleurs.example"})
    assert ailleurs.status_code == 403
    assert client.post("/api/clinique/hall/entendre", json={"texte": "x" * 500}).status_code == 422


def test_le_message_s_affiche_sur_l_ecran_du_soignant_de_l_etage():
    client, _ = _client()
    assert "Messages du hall" not in client.get("/clinique/soignant/contenu").text
    client.post("/api/clinique/hall/entendre", json={"texte": ARRIVEES["de"][0]})
    texte = client.get("/clinique/soignant/contenu").text
    assert "Messages du hall" in texte and "Madame Giulia B. arrive" in texte and "allemand" in texte


def test_l_appel_s_affiche_sur_l_ecran_de_l_accueil():
    client, _ = _client()
    client.post("/api/clinique/hall/entendre", json={"texte": "<b>Hello</b>, I am Marco T."})
    texte = client.get("/clinique/accueil/contenu").text
    assert "Appels du hall" in texte and "nom inconnu dans le hall" in texte and "<b>Hello" not in texte


# ---------------------------------------------------------------- la grande répétition
def test_les_etapes_1_2_et_3_de_la_grande_repetition():
    from briques.clinique import repetition

    for numero, mot in ((1, "italien"), (2, "santé"), (3, "étage")):
        resultat = repetition.CONTROLES[numero]()
        assert resultat.reussie is True and resultat.etiquette == "SIMULÉ" and mot in resultat.detail, numero
