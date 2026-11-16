"""H14 — Une parole proposée par le cerveau ne part jamais seule (réponse de Hiba à Q21 : « C »).

Ce qui se passait (mesure du tour 61 et tirage du tour 64, testé sur faux robot avec le vrai Apertus) : à « Merci
beaucoup ! », Apertus proposait de faire répéter la phrase par le robot ; à un robot sans bras, il lui faisait dire
« je vais prendre le coussin ». La règle C : sur un ordre au robot, une action « parler » proposée par le cerveau ne
part jamais ; le robot dit à la place une phrase fixe, « Je ne peux pas faire cela. », et rien ne va au gardien ni au
robot. Le reste ne change pas : les autres actions du cerveau, les phrases du robot lui-même (annonces, refus,
questions), les réponses de discussion, les gestes du coursier et les ordres d'un humain qui a la main.
Ici, le cerveau est un faux cerveau qui « parie » (testé sur faux robot, sans Apertus).
"""
from __future__ import annotations

import pytest

from briques.b01_prise.actions import ActionDemandee
from briques.b06_cerveau.prise_cerveau import Cerveau, Decision
from commun.phrases import _chercher, dire
from conftest import lancer

PHRASE_FR = "Je ne peux pas faire cela."
LANGUES = ("fr", "de", "it", "en", "zh")


class CerveauQuiFaitParler(Cerveau):
    """Comme Apertus au tour 61 : très sûr de lui, il propose une action « parler »."""

    nom = "parleur"

    def __init__(self, action: ActionDemandee, confiance: float = 0.95):
        self.action, self.confiance = action, confiance

    async def decider(self, texte, langue, carte, monde):
        return Decision(genre="action", action=self.action, confiance=self.confiance, cerveau=self.nom)


@pytest.fixture
def systeme(tmp_path, reglages):
    from commun.systeme import Systeme

    def fabrique(carte: str = "humanoide"):
        r = {**reglages, "robot": {**reglages["robot"], "carte": carte},
             "ecran": {**reglages["ecran"], "code_equipe": "code-de-test"},
             "cerveau": {**reglages["cerveau"], "choix": "regles"}}
        return Systeme(r, dossier_journal=tmp_path / "journal", acceleration=20.0)

    return fabrique


def _traiter(s, texte, langue="fr", avant=None):
    async def go():
        await s.demarrer()
        try:
            if avant:
                avant(s)
            return await s.chaine.traiter(texte, langue)
        finally:
            await s.arreter()

    return lancer(go())


def _types(s, type_):
    return [e for e in s.bus.historique if e.type == type_]


def _parler(texte, langue="fr"):
    return ActionDemandee(nom="parler", parametres={"texte": texte, "langue": langue})


# ------------------------------------------------------------------------------------------- la phrase fixe
def test_la_phrase_fixe_existe_dans_les_cinq_langues_du_robot():
    assert dire("parole_refusee", "fr") == PHRASE_FR
    for langue in LANGUES:
        phrase = _chercher(langue, "parole_refusee")
        assert phrase and "{" not in phrase, f"phrases.yaml : parole_refusee manque en {langue}"


# ------------------------------------------------------------------------------------------- les deux cas mesurés
@pytest.mark.parametrize("carte,texte,dit", [
    ("humanoide", "Merci beaucoup !", "Merci beaucoup !"),               # tour 61 : la phrase entendue, recopiée
    ("humanoide", "Il fait beau", "Il fait beau"),
    ("plateau", "Prends le coussin", "Je vais prendre le coussin."),    # tour 64 : un robot sans bras
])
def test_une_parole_du_cerveau_ne_part_pas_le_robot_dit_la_phrase_fixe(systeme, carte, texte, dit):
    s = systeme(carte)
    s.chaine.cerveau = CerveauQuiFaitParler(_parler(dit))
    r = _traiter(s, texte)
    assert r.reponses == [PHRASE_FR]
    assert r.statut_action is None and r.action is None and r.verdict == "non"
    assert not _types(s, "gardien_decision") and not _types(s, "action_demarree")  # rien chez le gardien, rien au robot
    dites = [e.donnees for e in _types(s, "reponse_dite")]
    assert [d.get("cle") for d in dites] == ["parole_refusee"]  # une seule phrase dite : la phrase fixe
    assert all(dit not in (d.get("texte") or "") for d in dites)  # la phrase du cerveau n'est jamais dite
    notes = [e.donnees for e in _types(s, "note") if e.donnees.get("quoi") == "parole_du_cerveau_refusee"]
    assert len(notes) == 1 and notes[0]["texte_propose"] == dit  # la boîte noire garde ce qui a été proposé


@pytest.mark.parametrize("langue", LANGUES)
def test_la_phrase_fixe_est_dite_dans_la_langue_de_la_personne(systeme, langue):
    s = systeme()
    s.chaine.cerveau = CerveauQuiFaitParler(_parler("Danke", langue))
    r = _traiter(s, "Danke schön", langue)
    assert r.reponses == [dire("parole_refusee", langue)]
    assert not _types(s, "action_demarree")


def test_meme_avec_une_confiance_parfaite_la_parole_ne_part_pas(systeme):
    s = systeme()
    s.chaine.cerveau = CerveauQuiFaitParler(_parler("Bonjour à tous"), confiance=1.0)
    r = _traiter(s, "Dis bonjour à tout le monde")
    assert r.reponses == [PHRASE_FR] and not _types(s, "action_demarree")


# ------------------------------------------------------------------------------------------- ce qui ne change pas
def test_les_autres_actions_du_cerveau_partent_comme_avant(systeme):
    s = systeme()
    s.chaine.cerveau = CerveauQuiFaitParler(ActionDemandee(nom="se_deplacer", parametres={"lieu": "table"}))
    r = _traiter(s, "Va à la table")
    assert r.statut_action == "reussie" and PHRASE_FR not in r.reponses
    assert [e.donnees["action"]["nom"] for e in _types(s, "action_demarree")] == ["se_deplacer"]


def test_stop_passe_toujours_avant(systeme):
    s = systeme()
    s.chaine.cerveau = CerveauQuiFaitParler(_parler("stop"))
    r = _traiter(s, "Stop")
    assert r.decision.action.nom == "arreter" and PHRASE_FR not in r.reponses


def test_un_oui_apres_une_parole_refusee_ne_relance_rien(systeme):
    s = systeme()
    s.chaine.cerveau = CerveauQuiFaitParler(_parler("Merci beaucoup !"))

    async def go():
        await s.demarrer()
        try:
            premier = await s.chaine.traiter("Merci beaucoup !", "fr")
            s.chaine.cerveau = CerveauQuiFaitParler(ActionDemandee(nom="etat"), confiance=0.1)  # « oui » : pas compris
            return premier, await s.chaine.traiter("oui", "fr")
        finally:
            await s.arreter()

    premier, second = lancer(go())
    assert premier.reponses == [PHRASE_FR] and second.statut_action is None
    assert not _types(s, "action_demarree") and not _types(s, "gardien_decision")


def test_une_phrase_d_un_agent_suit_la_meme_regle(systeme):
    s = systeme()
    s.chaine.cerveau = CerveauQuiFaitParler(_parler("Bonjour"))

    async def go():
        await s.demarrer()
        try:
            return await s.chaine.traiter("Dis bonjour", "fr", source="agent:essai")
        finally:
            await s.arreter()

    r = lancer(go())
    assert r.reponses == [PHRASE_FR] and not _types(s, "action_demarree")


def test_une_reponse_de_discussion_du_cerveau_reste_une_reponse(systeme):
    class Bavard(Cerveau):
        nom = "bavard"

        async def decider(self, texte, langue, carte, monde):
            return Decision(genre="discussion", texte="Avec plaisir.", confiance=0.9, cerveau=self.nom)

    s = systeme()
    s.chaine.cerveau = Bavard()
    r = _traiter(s, "Merci beaucoup !")
    assert r.reponses == ["Avec plaisir."] and not _types(s, "action_demarree")


def test_un_humain_qui_a_la_main_peut_toujours_faire_parler_le_robot(systeme):
    s = systeme()

    async def go():
        await s.demarrer()
        try:
            s.chaine.changer_de_main("Hiba")
            return await s.chaine.ordre_humain(_parler("Bonjour"), "Hiba", "fr", attendre_fin=True)
        finally:
            await s.arreter()

    r = lancer(go())
    assert PHRASE_FR not in r.reponses
    assert [e.donnees["action"]["nom"] for e in _types(s, "action_demarree")] == ["parler"]
