"""Les directions de la tête ont des noms que le cerveau entend (15.11.2026).

NON TESTÉ SUR VRAI ROBOT. Testé sur faux robot (la doublure du Reachy Mini, cerveau à règles).
« Fini » veut dire :
- avec le Reachy Mini comme robot du système, « guarda la paziente », « regarde ton collègue », « look at the nurse »
  font tourner la tête vers la bonne direction du fichier directions.yaml, par le gardien et la prise ;
- « prendi il cuscino » est refusé dans la langue de la personne (une tête n'a pas de bras) et rien ne bouge ;
- « scuoti la testa » est compris, mais le gardien demande un humain (un geste près d'une personne) : rien ne bouge ;
- les seuls mots « non » et « oui » ne lancent jamais un geste ;
- avec un autre robot, le monde ne change pas ; un fichier absent ou abîmé ne casse rien ; un lieu connu n'est pas remplacé.
"""
import asyncio
import copy

import pytest

from briques.b03_adaptateurs.robots.reachy_mini.doublure import DoublureReachyMini  # noqa: F401  (la doublure existe)
from briques.clinique.coursier import monde_de_la_clinique
from briques.clinique.table_des_robots import ajouter_les_directions
from commun.systeme import Systeme, charger_reglages


def _jouer(tmp_path, phrases):
    r = copy.deepcopy(charger_reglages())
    r["robot"].update({"adaptateur": "reachy_mini", "vrai_robot": False})
    r["cerveau"]["choix"] = "regles"

    async def scenario():
        s = Systeme(r, dossier_journal=tmp_path, acceleration=10,
                    monde=ajouter_les_directions(monde_de_la_clinique(), "reachy_mini"))
        evenements = []
        s.bus.abonner(evenements.append)
        await s.demarrer()
        try:
            suites = []
            for texte, langue in phrases:
                debut = len(evenements)
                await asyncio.wait_for(s.chaine.traiter(texte, langue, confiance_ecoute=1.0, source="tablette"), 30)
                suites.append(evenements[debut:])
            return suites, s.prise.carte().mention_test()
        finally:
            await s.arreter()

    return asyncio.run(scenario())


def _de(evenements, type_):
    return [e.donnees for e in evenements if e.type == type_]


@pytest.mark.parametrize("texte, langue, cible", [("Guarda la paziente", "it", "patient"), ("Regarde ton collègue", "fr", "collegue"),
                                                   ("Look at the nurse", "en", "soignant"), ("Regarde devant", "fr", "devant"),
                                                   # les phrases de la scène de la présentation, mot pour mot :
                                                   ("Look at the patient.", "en", "patient"),
                                                   ("Allora guarda il tuo collega.", "it", "collegue")])
def test_la_tete_regarde_la_direction_nommee_par_le_gardien_et_la_prise(tmp_path, texte, langue, cible):
    (suite,), mention = _jouer(tmp_path, [(texte, langue)])
    assert mention == "testé sur faux robot"
    (comprise,) = _de(suite, "demande_comprise")
    assert comprise["action"] == {"nom": "regarder", "parametres": {"cible": cible}}
    assert len(_de(suite, "gardien_decision")) == 1  # le gardien a donné son avis avant la prise
    (fin,) = _de(suite, "action_terminee")
    assert fin["statut"] == "reussie" and fin["action"]["parametres"]["cible"] == cible


@pytest.mark.parametrize("texte, langue, debut", [("Prendi il cuscino", "it", "Non posso"),
                                                   ("Buongiorno. Prendi il mio orsetto, per favore.", "it", "Non posso"),
                                                   ("Robot, squeeze harder!", "en", "I cannot"),
                                                   ("Serre plus fort", "fr", "Je ne peux pas")])
def test_prendre_ou_serrer_est_refuse_dans_la_langue_de_la_personne_et_rien_ne_bouge(tmp_path, texte, langue, debut):
    """Les phrases de la scène de Petit Suisse : une tête n'a ni bras ni main, et le système le dit."""
    (suite,), _ = _jouer(tmp_path, [(texte, langue)])
    assert _de(suite, "action_demarree") == [] and _de(suite, "demande_comprise")[0]["genre"] == "hors_carte"
    (dite,) = _de(suite, "reponse_dite")
    assert dite["genre"] == "refus" and dite["texte"].startswith(debut)


def test_secouer_la_tete_est_compris_mais_le_gardien_demande_un_humain(tmp_path):
    (suite, seul_non, seul_oui), _ = _jouer(tmp_path, [("Scuoti la testa", "it"), ("non", "fr"), ("oui", "fr")])
    assert _de(suite, "demande_comprise")[0]["action"] == {"nom": "rejouer_geste", "parametres": {"nom": "non"}}
    assert _de(suite, "gardien_decision")[0]["verdict"] == "humain" and _de(suite, "action_demarree") == []
    for reponse in (seul_non, seul_oui):  # les seuls mots « non » et « oui » sont des réponses, jamais un geste
        assert _de(reponse, "demande_comprise")[0]["action"] is None and _de(reponse, "action_demarree") == []


def test_un_autre_robot_un_fichier_absent_ou_abime_ne_changent_rien(tmp_path):
    reference = [lieu.id for lieu in monde_de_la_clinique().lieux]
    for adaptateur in ("faux_robot", "agilex_piper", "robot_qui_n_existe_pas", "../ailleurs", ""):
        assert [lieu.id for lieu in ajouter_les_directions(monde_de_la_clinique(), adaptateur).lieux] == reference
    dossier = tmp_path / "robots" / "tete"
    dossier.mkdir(parents=True)
    (dossier / "directions.yaml").write_text("ceci n'est pas : [du yaml", encoding="utf-8")
    assert [lieu.id for lieu in ajouter_les_directions(monde_de_la_clinique(), "tete", tmp_path / "robots").lieux] == reference
    (dossier / "directions.yaml").write_text(
        "directions:\n  table: {lacet_deg: 0, tangage_deg: 0}\n  ami: {lacet_deg: 10, tangage_deg: 0}\n"
        "noms:\n  table: {fr: [ailleurs]}\n  ami: {fr: [ami]}\n  sans_angle: {fr: [fantôme]}\n  casse: 3\n", encoding="utf-8")
    monde = ajouter_les_directions(monde_de_la_clinique(), "tete", tmp_path / "robots")
    assert [lieu.id for lieu in monde.lieux] == reference + ["ami"]  # ni « table » (déjà connue), ni un nom sans angle
    assert monde.lieu("table").noms.get("fr") != ["ailleurs"]


def test_avec_le_reachy_mini_trois_directions_s_ajoutent_avec_leurs_mots():
    avant = {lieu.id for lieu in monde_de_la_clinique().lieux}
    monde = ajouter_les_directions(monde_de_la_clinique(), "reachy_mini")
    assert {lieu.id for lieu in monde.lieux} - avant == {"patient", "collegue", "soignant"}
    for nom in ("patient", "collegue", "soignant"):
        assert {"fr", "de", "gsw", "it", "en", "zh"} <= set(monde.lieu(nom).noms)


@pytest.mark.parametrize("texte, langue", [("Ça me serre la poitrine", "fr"), ("Mon pansement me serre trop", "fr"),
                                           ("It feels like a squeeze in my chest", "en"), ("Mi stringi la mano?", "it"),
                                           ("我有点头疼", "zh"), ("有一点头晕", "zh")])
def test_une_phrase_ordinaire_de_la_clinique_ne_declenche_ni_prise_ni_geste(tmp_path, texte, langue):
    """Relecture du 15.11.2026 : « serre », « squeeze », « stringi » seuls et « 点头 » se déclenchaient à tort."""
    (suite,), _ = _jouer(tmp_path, [(texte, langue)])
    comprise = _de(suite, "demande_comprise")[0]
    assert comprise["action"] is None and comprise["genre"] != "hors_carte" and _de(suite, "action_demarree") == []
    assert not [dite for dite in _de(suite, "reponse_dite") if dite.get("genre") == "refus"]  # pas de refus dit à voix haute


def test_regarder_a_gauche_fait_regarder_devant_et_le_robot_le_dit(tmp_path):
    """Limite connue : pas de mots pour « gauche » et « droite ». Le robot dit ce qu'il fait vraiment."""
    (suite,), _ = _jouer(tmp_path, [("Regarde à gauche", "fr")])
    assert _de(suite, "demande_comprise")[0]["action"] == {"nom": "regarder", "parametres": {"cible": "devant"}}
    assert "devant" in _de(suite, "reponse_dite")[0]["texte"]


@pytest.mark.parametrize("texte, langue, geste", [("Réveille-toi", "fr", "lever_la_tete"), ("Svegliati", "it", "lever_la_tete"),
                                                   ("Wake up now", "en", "lever_la_tete"), ("Endors-toi", "fr", "coucher_la_tete"),
                                                   ("Sleep now", "en", "coucher_la_tete")])
def test_se_reveiller_et_s_endormir_sont_compris_et_le_gardien_demande_un_humain(tmp_path, texte, langue, geste):
    """Notre réveil lent passe par le cerveau ET par le gardien : un humain donne son accord avant que la tête se lève."""
    (suite,), _ = _jouer(tmp_path, [(texte, langue)])
    assert _de(suite, "demande_comprise")[0]["action"] == {"nom": "rejouer_geste", "parametres": {"nom": geste}}
    assert _de(suite, "gardien_decision")[0]["verdict"] == "humain" and _de(suite, "action_demarree") == []


@pytest.mark.parametrize("texte, langue", [("Je me réveille la nuit", "fr"), ("I wake up at night", "en"),
                                           ("Ho dormito male", "it"), ("Je dors mal", "fr")])
def test_parler_de_son_sommeil_ne_reveille_ni_n_endort_le_robot(tmp_path, texte, langue):
    (suite,), _ = _jouer(tmp_path, [(texte, langue)])
    assert _de(suite, "demande_comprise")[0]["action"] is None and _de(suite, "action_demarree") == []

