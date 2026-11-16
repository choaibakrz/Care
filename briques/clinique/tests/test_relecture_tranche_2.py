"""La clinique en boîte — T21, la relecture de la tranche 2 : les points d'un relecteur neuf, corrigés (12.11.2026).

Chaque essai reprend un exemple que le relecteur a fait passer à travers nos contrôles. « Fini » veut dire : ces
exemples ne passent plus, et ce que les écrans et les commandes disent est vrai.
"""
from __future__ import annotations

import pytest

from briques.clinique import resume_apertus
from briques.clinique.papiers import CerveauDeTest as CerveauDesPapiers
from briques.clinique.papiers import proposer_avec_cerveau
from briques.clinique.tests.test_resume_medecin import MEDECIN, _client, _ligne, _pieces

# Les six phrases fausses que le relecteur a fait passer dans le résumé de Madame Giulia B. (point 1).
FAUSSES = [
    ("Pourquoi il est là", "Pas de réadaptation après une opération de la hanche. Séjour de 19 jours, sortie le jour 18."),
    ("Ce qui a changé depuis hier", "Sortie le jour 1 à 09:00, chambre 12."),
    ("Ce qui a changé depuis hier", "Arrivée à 12:00 le jour 09, chambre 1."),
    ("Prévu aujourd'hui", "14:00 installation en chambre (Chambre 12) ; 10:00 physiothérapie (Salle 2) ; 11:00 bain accompagné (Bassin)."),
    ("Prévu aujourd'hui", "10:00 installation en chambre (Chambre 12) ; 11:00 pas de physiothérapie (Salle 2) ; 14:00 bain accompagné (Bassin) annulé."),
    ("Ce qui a changé depuis hier", "Arrivée le jour 1 à 09:00, chambre 12. Elle va mal."),
]
POINT = {"Pourquoi il est là": "pourquoi", "Ce qui a changé depuis hier": "change", "Prévu aujourd'hui": "aujourdhui"}


@pytest.mark.parametrize("titre, fausse", FAUSSES)
def test_le_resume_n_accepte_plus_une_negation_un_echange_de_chiffres_ni_une_phrase_sur_la_sante(titre, fausse):
    resume, badges, *_ = _pieces()
    simple = _ligne(resume.resume(badges[MEDECIN], "p01"), POINT[titre])["texte"]
    menteur, badges2, *_ = _pieces()

    def repondre(t, sources):
        if t == titre:
            return {"sur": True, "phrases": [{"texte": fausse, "sources": list(sources)[:1]}]}
        return {"sur": False, "phrases": []}

    menteur.cerveau = resume_apertus.CerveauDeTest(repondre)
    ligne = _ligne(menteur.resume(badges2[MEDECIN], "p01"), POINT[titre])
    assert ligne["texte"] == simple and ligne["ecrit_par"] == "règles simples" and "je ne suis pas sûr" in ligne["pas_sur"]


def test_une_phrase_juste_ecrite_autrement_passe_encore():
    resume, badges, *_ = _pieces()

    def repondre(titre, sources):
        if titre == "Ce qui a changé depuis hier":
            return {"sur": True, "phrases": [{"texte": "Arrivée le jour 1 à 09:00 ; chambre 12.", "sources": ["sejour"]}]}
        return {"sur": False, "phrases": []}

    resume.cerveau = resume_apertus.CerveauDeTest(repondre)
    assert _ligne(resume.resume(badges[MEDECIN], "p01"), "change")["ecrit_par"] == "cerveau"


def test_les_phrases_ecartees_du_cerveau_ne_sont_pas_comptees_comme_retirees_faute_de_source():
    """Point 10 : la fiche de vérité compte les phrases « retirées faute de source ». Une phrase du cerveau écartée pour
    un chiffre ou un mot est comptée à part."""
    resume, badges, *_ = _pieces()
    resume.cerveau = resume_apertus.CerveauDeTest(
        lambda titre, sources: {"sur": True, "phrases": [{"texte": "Séjour de 81 jours.", "sources": list(sources)[:1]}]})
    r = resume.resume(badges[MEDECIN], "p01")
    assert r["retirees"] == 0 and r["retirees_detail"] == []
    assert len(r["ecartees_du_cerveau"]) >= 1 and all(d["raison"] for d in r["ecartees_du_cerveau"])


# ---------------------------------------------------------------------------------------------- les papiers (point 2)
def _lettre():
    from briques.clinique import papiers_apertus

    return next(p for p in papiers_apertus.papiers_du_faux_dossier() if p["id"] == "p01-d1")


@pytest.mark.parametrize("auteur, patient", [("Giulia B.", "."), ("e", "a"), ("", "Madame"), ("paziente", "Madame Giulia B.")])
def test_un_auteur_ou_un_patient_qui_n_est_qu_un_bout_de_texte_n_est_plus_dit_sur(auteur, patient):
    papier = _lettre()
    cerveau = CerveauDesPapiers(lambda texte: {"type": papier["vrai_type"], "date": None, "auteur": auteur, "patient": patient,
                                               "confiance": "haute"})
    p = proposer_avec_cerveau(papier["texte"], "tapée", papier["attendus"], cerveau)
    assert p["confiance"] == "basse" and p["raisons"]
    assert p["auteur"] in (None, "Studio medico Exemple, Dott. Exemple.")  # jamais un auteur faux affiché
    assert p["patient"] == "p01"  # le patient rangé reste celui de la règle


def test_le_bon_auteur_et_le_bon_patient_restent_surs():
    papier = _lettre()
    cerveau = CerveauDesPapiers(lambda texte: {"type": papier["vrai_type"], "date": None, "auteur": "Studio medico Exemple, Dott. Exemple",
                                               "patient": "Madame Giulia B.", "confiance": "haute"})
    p = proposer_avec_cerveau(papier["texte"], "tapée", papier["attendus"], cerveau)
    assert p["confiance"] == "haute" and p["raisons"] == [] and p["auteur"]


# ---------------------------------------------------------------------------------------------- cocher à la voix (point 13)
@pytest.mark.parametrize("phrase", ["la sonnette n'est jamais faite", "sonnette, fait ?", "die Klingel wurde nie gemacht",
                                    "il campanello non è mai fatto", "the bell was never done"])
def test_jamais_et_une_question_ne_cochent_rien(phrase):
    from briques.clinique.listes import NEGATIONS, _contient, _simple_voix

    assert phrase.rstrip().endswith("?") or _contient(_simple_voix(phrase), NEGATIONS)


@pytest.mark.parametrize("phrase", ["sonnette, fait ?", "la sonnette n'est jamais faite", "Klingel nie gemacht", "bell never done"])
def test_une_question_ou_un_jamais_ne_coche_pas_la_sonnette(phrase):
    from briques.clinique.tests import test_cocher_a_la_voix as voix

    listes = voix._listes()
    assert listes.entendre(voix.SOIGNANT, "p01", "installation", phrase)["compris"] == "rien"
    assert voix._etats(listes)[3]["etat"] != "fait"


# ---------------------------------------------------------------------------------------------- ce que les écrans disent (points 11, 12)
def test_l_ecran_du_soir_ne_dit_plus_sans_traduction():
    from briques.clinique import ecrans_soir, soir

    assert "sans traduction" not in open(ecrans_soir.__file__, encoding="utf-8").read()
    assert "Pas de traduction ici" not in (soir.__doc__ or "")


def test_la_commande_de_l_accueil_a_la_voix_ne_dit_plus_que_le_chemin_est_affiche_sur_un_ecran():
    from briques.clinique import accueil_voix

    source = open(accueil_voix.__file__, encoding="utf-8").read()
    assert "affiché sur l'écran du hall" not in source and "l'écran du hall le dessine" not in source
    assert "aucun écran n'est ouvert par cette commande" in source


def test_la_mesure_de_la_chaine_dit_que_la_langue_etait_donnee_d_avance():
    from briques.clinique import chaine_mesure

    assert "la langue de chaque phrase est donnée à l'écoute" in open(chaine_mesure.__file__, encoding="utf-8").read()
