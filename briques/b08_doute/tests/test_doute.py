"""Brique 8 — « je ne suis pas sûr ». Testé sur faux robot, Internet coupé (conftest.py).

20 demandes floues → 20 questions, aucune action ; la main levée (deux « pas compris », deux échecs) ;
les aides apprises (« frigo » = cuisine) gardées et utilisées la fois suivante ; le filet « deux choix » pour
tous les cerveaux.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from briques.b01_prise.actions import ActionDemandee
from briques.b06_cerveau.branchements.regles import normaliser
from briques.b06_cerveau.prise_cerveau import Cerveau, Decision
from briques.b08_doute.aides_apprises import ANCIEN_CHEMIN_AIDES, CHEMIN_AIDES, AideRefusee, AidesApprises
from commun.monde import Monde
from commun.phrases import dire
from conftest import lancer

ICI = Path(__file__).resolve().parents[1]
DEMANDES = yaml.safe_load((ICI / "demandes_floues.yaml").read_text(encoding="utf-8"))["demandes"]
CODE = {"X-Code-Equipe": "code-de-test"}


@pytest.fixture
def systeme(tmp_path, reglages):
    """Un Système complet (faux robot, cerveau à règles), main levée allumée, mots appris dans tmp_path."""
    from commun.systeme import Systeme

    def fabrique(carte: str = "humanoide", acceleration: float = 20.0, main_levee: bool = True,
                 aides: Path | None = None):
        inter = dict(reglages.get("interrupteurs") or {})
        inter.update(main_levee={"actif": main_levee})
        r = {**reglages, "robot": {**reglages["robot"], "carte": carte},
             "ecran": {**reglages["ecran"], "code_equipe": "code-de-test"},
             "cerveau": {**reglages["cerveau"], "choix": "regles"}, "interrupteurs": inter,
             "doute": {"aides_apprises": str(aides or tmp_path / "aides_apprises.yaml")}}
        return Systeme(r, dossier_journal=tmp_path / "journal", acceleration=acceleration)

    return fabrique


def _traiter(s, phrases):
    async def go():
        await s.demarrer()
        try:
            return [await s.chaine.traiter(t, lg, **kw) for t, lg, *reste in phrases for kw in [reste[0] if reste else {}]]
        finally:
            await s.arreter()

    return lancer(go())


def _evenements(s, type_):
    return [e for e in s.bus.historique if e.type == type_]


def _questions(langue: str) -> tuple[str, ...]:
    choix = dire("question_choix", langue, options="").split("…")[0].split(" ?")[0].rstrip(" :：?？")
    return (dire("question_lieu", langue), dire("question_objet", langue), choix)


# ================================================================ 20 demandes floues
def test_il_y_a_vingt_demandes_floues_dans_les_six_langues():
    assert len(DEMANDES) == 20
    assert {d["langue"] for d in DEMANDES} == {"fr", "de", "gsw", "it", "en", "zh"}


def test_vingt_demandes_floues_le_robot_pose_une_question_et_n_agit_jamais(systeme):
    from briques.b13_ecran.serveur import creer_app

    s = systeme()
    with TestClient(creer_app(s)) as client:
        depart = client.get("/api/etat").json()["position"]
        for d in DEMANDES:
            r = client.post("/api/dire", json={"texte": d["texte"], "langue": d["langue"]}, headers=CODE).json()
            assert r["decision"]["genre"] == "question", d
            assert r["statut_action"] is None and r["verdict"] is None, d
            question = r["reponses"][-1]
            assert question.startswith(_questions(d["langue"])), (d, question)
            assert "…" not in question and "saisir" not in question.replace("saisir un objet", "")
        fiche = client.get("/api/fiche").json()
        assert fiche["questions_posees"] == 20 and fiche["demandes"] == 20
        assert "aides_demandees" in fiche and fiche["aides_demandees"] == 0
        assert client.get("/api/etat").json()["position"] == depart
        # Le robot bute ensuite (deux « pas compris » de suite) : il lève la main, et le compteur le montre.
        client.post("/api/dire", json={"texte": "blabla", "langue": "fr"}, headers=CODE)
        r = client.post("/api/dire", json={"texte": "blublu", "langue": "fr"}, headers=CODE).json()
        assert r["reponses"][-1] == "Je lève la main : j'ai besoin d'aide."
        assert client.get("/api/fiche").json()["aides_demandees"] == 1
    assert not _evenements(s, "action_demarree")


def test_les_options_sont_dites_dans_la_langue(systeme):
    r = _traiter(systeme(), [("Prends et pose", "fr"), ("Nimm und leg", "de"), ("拿杯子还是瓶子", "zh")])
    assert r[0].reponses[-1] == "Vous voulez dire : saisir un objet, poser un objet ?"
    assert r[1].reponses[-1] == "Meinen Sie: etwas greifen, etwas ablegen?"
    assert r[2].reponses[-1] == "您是说：瓶子, 杯子？"  # dans l'ordre du monde (bouteille, puis tasse)


# ================================================================ la main levée
def test_deux_incompris_de_suite_pour_la_meme_personne_le_robot_leve_la_main(systeme):
    s = systeme()
    r = _traiter(s, [("blabla", "de", {"personne": "anna"}), ("Va", "fr", {"personne": "anna"}),  # une question : neutre
                     ("blublu", "de", {"personne": "anna"}), ("bloblo", "en", {"personne": "ben"})])
    assert r[0].reponses[-1] == dire("incompris", "de")
    assert r[2].reponses[-1] == "Ich hebe die Hand: Ich brauche Hilfe."  # 2e « pas compris » d'Anna
    assert r[3].reponses[-1] == dire("incompris", "en")  # Ben : sa première fois
    (aide,) = _evenements(s, "aide_demandee")
    assert aide.donnees["raison"] == "incompris_de_suite" and aide.donnees["phrases"] == ["blabla", "blublu"]
    assert s.compteur.fiche().aides_demandees == 1


def test_une_demande_comprise_remet_le_compteur_a_zero(systeme):
    s = systeme()
    r = _traiter(s, [("blabla", "fr"), ("Regarde la table", "fr"), ("blublu", "fr")])
    assert r[2].reponses[-1] == dire("incompris", "fr") and not _evenements(s, "aide_demandee")


def test_deux_echecs_de_suite_le_robot_leve_la_main(systeme):
    s = systeme()  # la bouteille est loin du robot : « hors de portée », deux fois
    r = _traiter(s, [("Prends la bouteille", "it"), ("sì", "it"), ("Prendi la bottiglia", "it"), ("sì", "it")])
    assert r[1].statut_action == r[3].statut_action == "echouee"
    assert "Alzo la mano: ho bisogno di aiuto." not in r[1].reponses
    assert r[3].reponses[-1] == "Alzo la mano: ho bisogno di aiuto."
    (aide,) = _evenements(s, "aide_demandee")
    assert aide.donnees["raison"] == "echecs_de_suite" and len(aide.donnees["echecs"]) == 2


def test_un_robot_qui_refuse_deux_fois_compte_comme_deux_echecs(systeme):
    s = systeme()

    async def go():
        await s.demarrer()
        s.simulation.provoquer_panne("refus")
        r = [await s.chaine.traiter("Look at the table", "en") for _ in range(2)]
        await s.arreter()
        return r

    r = lancer(go())
    assert r[0].statut_action == r[1].statut_action == "refusee"
    assert r[1].reponses[-1] == "I am raising my hand: I need help."


def test_l_interrupteur_eteint_la_main_levee_mais_pas_le_gardien(systeme):
    s = systeme("bras", main_levee=False)
    r = _traiter(s, [("blabla", "fr"), ("blublu", "fr"), ("Prends la tasse", "fr")])
    assert r[1].reponses[-1] == dire("incompris", "fr")
    assert r[2].verdict == "humain" and r[2].reponses[-1].startswith("Je lève la main")  # la sécurité reste
    assert [e.donnees["raison"] for e in _evenements(s, "aide_demandee")] == ["gardien"]


# ================================================================ les aides apprises
def test_un_humain_apprend_un_mot_le_robot_le_comprend_tout_de_suite_et_la_fois_suivante(systeme, tmp_path):
    from briques.b13_ecran.serveur import creer_app

    fichier = tmp_path / "mots.yaml"
    s = systeme(aides=fichier)
    with TestClient(creer_app(s)) as client:
        def dire_(texte):
            return client.post("/api/dire", json={"texte": texte, "langue": "fr"}, headers=CODE).json()

        assert dire_("Va au frigo")["decision"]["genre"] == "question"  # « Où dois-je aller ? »
        mot = {"mot": "frigo", "langue": "fr", "sens": "cuisine", "qui": "Hiba"}
        assert client.post("/api/aide/apprendre", json=mot).status_code == 403  # sans le code d'équipe
        reponse = client.post("/api/aide/apprendre", json=mot, headers=CODE).json()
        assert reponse["ok"] and reponse["mot"]["genre"] == "lieu" and reponse["mot"]["nouveau"]
        r = dire_("Va au frigo")
        assert r["decision"]["genre"] == "action" and r["action"]["parametres"]["lieu"] == "cuisine"
        assert client.get("/api/aides").json()["mots_appris"][0]["mot"] == "frigo"
        assert client.get("/api/fiche").json()["aides_recues"] == 1
        assert client.post("/api/aide/apprendre", json={**mot, "mot": "table"}, headers=CODE).status_code == 400
    aide = [e for e in s.bus.historique if e.type == "aide_recue"][0]
    assert aide.donnees["mot"] == "frigo" and aide.donnees["qui"] == "Hiba"
    garde = yaml.safe_load(fichier.read_text(encoding="utf-8"))["mots"]
    assert garde == [{"mot": "frigo", "langue": "fr", "sens": "cuisine", "genre": "lieu", "appris_le": garde[0]["appris_le"]}]
    assert "Hiba" not in fichier.read_text(encoding="utf-8")  # pas de prénom dans le fichier (il est dans le dépôt)

    # La fois suivante (nouveau démarrage) : il n'a plus besoin de demander.
    (r,) = _traiter(systeme(aides=fichier), [("Va au frigo", "fr")])
    assert r.action.parametres["lieu"] == "cuisine" and r.statut_action == "reussie"


@pytest.mark.parametrize("mot,langue,sens,pourquoi", [
    ("stop", "fr", "cuisine", "stop"), ("arrête", "fr", "table", "stop"), ("aller", "fr", "cuisine", "mot d'action"),
    ("oui", "fr", "cuisine", "« oui »"), ("pas", "fr", "cuisine", "négation"),
    ("table", "fr", "cuisine", "autre chose"), ("frigo", "fr", "lune", "ni un lieu"), ("frigo", "xx", "cuisine", "langue"),
    ("箱", "zh", "caisse", "deux caractères"), ("", "fr", "cuisine", "entre 1 et 40"), ("a", "fr", "cuisine", "trois lettres"),
    # Relecture sécurité du lot B : caractères, longueur, « contient ou est contenu ».
    ("frigo‮", "fr", "cuisine", "U\\+202E"),  # inverse le sens du texte à l'écran
    ("fri​go", "fr", "cuisine", "U\\+200B"),  # invisible
    ("<b>frigo</b>", "fr", "cuisine", "« < », « > »"), ("frigo2", "fr", "cuisine", "« 2 »"),
    ("frigo frigo frigo frigo frigo", "fr", "cuisine", "4 mots au plus"), ("f" * 41, "fr", "cuisine", "entre 1 et 40"),
    ("la table", "fr", "cuisine", "touche le nom « table »"),  # contient le nom d'un autre lieu
    ("objet", "fr", "caisse", "touche le nom « objet de test »"),  # se cache dans le nom d'un autre objet
    ("李箱", "zh", "caisse", "行李箱"),  # chinois : morceau du nom de la valise
    ("stop box", "fr", "caisse", "stop"), ("停车场", "zh", "cuisine", "stop"),  # contient un mot d'arrêt
    ("ne bouge", "fr", "cuisine", "stop"),  # se cache dans « ne bouge pas » (arrêt)
    ("oui table", "fr", "cuisine", "« oui »"), ("bene", "it", "cuisine", "« oui »"),  # « va bene »
    ("non merci", "fr", "cuisine", "« non »"), ("好地方", "zh", "cuisine", "« oui »"),
])
def test_les_mots_qui_preteraient_a_confusion_sont_refuses(tmp_path, mot, langue, sens, pourquoi):
    aides = AidesApprises(tmp_path / "mots.yaml")
    with pytest.raises(AideRefusee, match=pourquoi):
        aides.apprendre(mot, langue, sens, Monde.charger())
    assert not (tmp_path / "mots.yaml").exists()


@pytest.mark.parametrize("mot,langue,sens", [
    ("frigo", "fr", "cuisine"), ("l'évier", "fr", "cuisine"), ("l’évier", "fr", "cuisine"), ("Kühlschrank", "de", "cuisine"),
    ("pomme-de-terre", "fr", "caisse"), ("冰箱", "zh", "cuisine"), ("salle de bain", "fr", "cuisine"), ("Theke", "de", "table"),
])
def test_les_mots_utiles_restent_permis(tmp_path, mot, langue, sens):
    appris, nouveau = AidesApprises(tmp_path / "mots.yaml").apprendre(mot, langue, sens, Monde.charger())
    assert nouveau and appris.mot == mot


def test_les_mots_appris_sont_gardes_hors_du_depot_suivi_par_git():
    """Relecture du lot B : le fichier des mots appris est dans journal/ (ignoré par git), plus dans le dépôt."""
    racine = Path(__file__).resolve().parents[3]
    assert CHEMIN_AIDES == racine / "journal" / "aides_apprises.yaml"
    assert "journal/" in (racine / ".gitignore").read_text(encoding="utf-8").split()
    exemple = yaml.safe_load((racine / "reglages.exemple.yaml").read_text(encoding="utf-8"))
    assert exemple["doute"]["aides_apprises"] == "journal/aides_apprises.yaml"
    # L'ancien fichier du dépôt reste là, vide, avec un commentaire qui dit où sont les mots maintenant.
    ancien = ANCIEN_CHEMIN_AIDES.read_text(encoding="utf-8")
    assert yaml.safe_load(ancien) == {"mots": []} and "journal/aides_apprises.yaml" in ancien
    # Un vieux reglages.yaml qui montre encore le fichier du dépôt : les mots vont quand même dans journal/.
    assert AidesApprises(ANCIEN_CHEMIN_AIDES).chemin == CHEMIN_AIDES


def test_les_mots_de_l_ancien_fichier_sont_repris_une_fois_puis_l_ancien_est_vide(tmp_path):
    ancien = tmp_path / "ancien.yaml"
    ancien.write_text("mots:\n  - {mot: frigo, langue: fr, sens: cuisine, genre: lieu, appris_le: '2026-11-01'}\n",
                      encoding="utf-8")
    nouveau = tmp_path / "journal" / "aides_apprises.yaml"  # le dossier n'existe pas encore
    aides = AidesApprises(nouveau, ancien=ancien)
    assert [m.mot for m in aides.mots] == ["frigo"]
    assert yaml.safe_load(nouveau.read_text(encoding="utf-8"))["mots"][0]["mot"] == "frigo"
    vide = ancien.read_text(encoding="utf-8")
    assert yaml.safe_load(vide) == {"mots": []} and vide.startswith("# ANCIEN emplacement")
    assert [m.mot for m in AidesApprises(nouveau, ancien=ancien).mots] == ["frigo"]  # pas de double au 2e démarrage


def test_un_mot_du_fichier_qui_ne_passe_plus_la_verification_est_ignore_au_demarrage(tmp_path):
    """Fichier écrit à la main (ou avec d'anciennes règles) : chaque mot est revérifié avant d'aller dans le monde."""
    fichier = tmp_path / "mots.yaml"
    fichier.write_text("mots:\n"
                       "  - {mot: frigo, langue: fr, sens: cuisine, genre: lieu}\n"
                       "  - {mot: \"la table\", langue: fr, sens: cuisine, genre: lieu}\n"
                       "  - {mot: \"sto​p\", langue: fr, sens: cuisine, genre: lieu}\n", encoding="utf-8")
    monde = Monde.charger()
    aides = AidesApprises(fichier)
    assert aides.appliquer(monde) == 1
    assert [m.mot for m in aides.mots] == ["frigo"]
    noms = monde.lieu("cuisine").noms["fr"]
    assert "frigo" in noms and "la table" not in noms and "sto​p" not in noms


def test_le_fichier_des_aides_du_depot_se_lit_et_ne_contient_que_des_mots():
    aides = AidesApprises(CHEMIN_AIDES)
    monde = Monde.charger()
    aides.appliquer(monde)
    for m in aides.mots:
        assert m.genre in ("lieu", "objet") and (monde.lieu(m.sens) or monde.objet(m.sens))


def test_aucun_nom_du_monde_ne_veut_dire_deux_choses():
    """Accents enlevés, « Stäge » (escalier, suisse allemand) devenait « stage » (scène, en anglais) : interdit."""
    monde = Monde.charger()
    AidesApprises(CHEMIN_AIDES).appliquer(monde)
    sens: dict[str, str] = {}
    for chose in monde.lieux + monde.objets:
        for _, n in chose.tous_les_noms():
            cle = normaliser(n).strip()
            assert sens.setdefault(cle, chose.id) == chose.id, f"« {n} » = {sens[cle]} et {chose.id}"


# ================================================================ deux choix : une question, quel que soit le cerveau
class CerveauQuiParie(Cerveau):
    """Un « modèle » qui choisit au hasard l'un des deux lieux nommés, avec beaucoup d'assurance."""

    nom = "parieur"

    def __init__(self, action: ActionDemandee):
        self.action = action

    async def decider(self, texte, langue, carte, monde):
        return Decision(genre="action", action=self.action, confiance=0.95, cerveau=self.nom)


@pytest.mark.parametrize("texte,langue,action", [
    ("Va à la cuisine ou à la table", "fr", ActionDemandee(nom="se_deplacer", parametres={"lieu": "cuisine"})),
    ("Take the cup or the bottle", "en", ActionDemandee(nom="saisir", parametres={"objet": "tasse"})),
    ("Wink und klatsch", "de", ActionDemandee(nom="rejouer_geste", parametres={"nom": "saluer"})),
])
def test_deux_choix_possibles_une_question_meme_avec_un_cerveau_qui_parie(systeme, texte, langue, action):
    s = systeme()
    s.chaine.cerveau = CerveauQuiParie(action)
    (r,) = _traiter(s, [(texte, langue)])
    assert r.decision.genre == "question" and len(r.decision.options) == 2 and r.statut_action is None
    assert not _evenements(s, "action_demarree") and _evenements(s, "question_posee")


def test_un_seul_lieu_nomme_le_cerveau_qui_parie_agit(systeme):
    s = systeme()
    s.chaine.cerveau = CerveauQuiParie(ActionDemandee(nom="se_deplacer", parametres={"lieu": "table"}))
    (r,) = _traiter(s, [("Va à la table", "fr")])
    assert r.statut_action == "reussie"
