"""La clinique en boîte — H04, sur scène on demande aussi le rapport de radiologie (réponse de Hiba à Q11 : B).

« Sur scène, nous demanderons aussi le rapport de radiologie, pour montrer la réponse vraie « Je ne trouve pas ce
document ». » Madame Giulia B. n'a pas de rapport de radiologie dans le faux dossier.
« Fini » veut dire :
- le scénario de scène annonce les deux demandes : la lettre du médecin, qui s'ouvre ; le rapport de radiologie ;
- par la vraie page de recherche, le rapport de radiologie reçoit la réponse vraie, et RIEN ne s'ouvre : ni un autre
  document de Madame B., ni le rapport de radiologie d'un autre patient ;
- le journal des accès ne garde aucune ouverture de source pour cette demande ;
- l'étape 10 de la répétition joue les deux demandes, et rate si le rapport de radiologie « s'ouvre » quand même, ou si
  la lettre ne s'ouvre plus.
"""
from __future__ import annotations

import yaml

from briques.clinique import ecrans_resume, repetition
from briques.clinique.tests.test_resume_medecin import MEDECIN, _client

LETTRE, RADIOLOGIE = "la lettre du médecin de Madame B.", "le dernier rapport de radiologie de Madame B."
VRAI = "Je ne trouve pas ce document pour Madame Giulia B."


def test_le_scenario_de_scene_annonce_les_deux_demandes():
    from briques.clinique import chef_clinique

    scenes = yaml.safe_load(chef_clinique.FICHIER.read_text(encoding="utf-8"))["scenes"]
    medecin = next(s for s in scenes if s["numero"] == 5)
    assert "lettre du médecin" in medecin["annonce"] and "rapport de radiologie" in medecin["annonce"]
    assert "Je ne trouve pas ce document" in medecin["annonce"]


def test_par_la_vraie_page_le_rapport_de_radiologie_recoit_la_reponse_vraie_et_rien_ne_s_ouvre():
    client, clinique = _client()
    page = client.get("/clinique/medecin/recherche", params={"badge": MEDECIN, "q": RADIOLOGIE})
    assert page.status_code == 200 and VRAI in page.text
    assert "Dans son dossier :" in page.text and "lettre du médecin traitant" in page.text  # ce qu'elle a vraiment
    assert "référence " not in page.text  # aucun document ouvert
    assert "Radiologiebericht" not in page.text and "Hans" not in page.text  # celui d'un autre patient : jamais
    ouvertures = [l for l in clinique.porte.journal.lignes() if l["quoi"].startswith("source du résumé")]
    assert ouvertures == []


def test_la_lettre_du_medecin_s_ouvre_et_c_est_au_journal():
    client, clinique = _client()
    page = client.get("/clinique/medecin/recherche", params={"badge": MEDECIN, "q": LETTRE})
    assert "référence " in page.text and "Lettera" in page.text and VRAI not in page.text
    assert [l["quoi"] for l in clinique.porte.journal.lignes() if l["quoi"].startswith("source du résumé")] == ["source du résumé : p01-d1"]


def test_l_etape_10_joue_les_deux_demandes_et_le_dit():
    resultat = repetition.CONTROLES[10]()
    assert resultat.reussie is True, resultat.detail
    assert "la lettre du médecin de Madame B. s'ouvre" in resultat.detail
    assert "rapport de radiologie" in resultat.detail and "Je ne trouve pas ce document" in resultat.detail


def test_l_etape_10_rate_si_le_rapport_de_radiologie_s_ouvre_quand_meme(monkeypatch):
    from briques.clinique.resume import ResumeDuMedecin

    vraie = ResumeDuMedecin.chercher

    def menteuse(self, badge, phrase):
        if "radiologie" in phrase:  # une recherche qui ouvrirait n'importe quoi plutôt que de dire vrai
            return vraie(self, badge, "la carte d'assurance de Madame B.")
        return vraie(self, badge, phrase)

    monkeypatch.setattr(ResumeDuMedecin, "chercher", menteuse)
    resultat = repetition.CONTROLES[10]()
    assert resultat.reussie is False and "rapport de radiologie" in resultat.detail


def test_l_etape_10_rate_si_la_lettre_ne_s_ouvre_plus(monkeypatch):
    from briques.clinique.resume import ResumeDuMedecin

    monkeypatch.setattr(ResumeDuMedecin, "chercher", lambda self, badge, phrase: {
        "trouve": False, "marque": "données inventées", "dit": "Je ne trouve pas ce document pour Madame Giulia B. Dans son dossier : rien."})
    resultat = repetition.CONTROLES[10]()
    assert resultat.reussie is False and "la lettre du médecin" in resultat.detail


def test_les_phrases_de_scene_sont_celles_de_l_etape():
    assert ecrans_resume.DEMANDE_QUI_S_OUVRE == LETTRE and ecrans_resume.DEMANDE_SANS_DOCUMENT == RADIOLOGIE
