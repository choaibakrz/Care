"""La clinique en boîte — H09, le cerveau lit par la porte, avec son propre badge (cahier 5.2 ; relecture de la tranche 2).

« Fini » veut dire :
- quand un cerveau écrit le résumé, la fiche qu'il reçoit est lue par la porte avec le badge « assistant », au service
  du médecin : le journal des accès a une ligne « assistant, pour medecin-exemple », et une ligne par texte donné ;
- quand un cerveau range un papier, le journal dit, sous le badge « assistant » au service de l'accueil, quel papier
  il a reçu ;
- le cerveau ne voit jamais plus que la personne pour qui il travaille ; sans personne, il ne reçoit rien ;
- sans cerveau branché, le journal n'a aucune ligne « assistant » : rien ne change ;
- la mesure des images des papiers et la mesure du rangement lisent le faux dossier par la porte, jamais directement.
Cerveaux de test : aucun modèle.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from briques.clinique import papiers_apertus, papiers_images, resume_apertus
from briques.clinique.carnet import Carnet
from briques.clinique.papiers import CerveauDeTest, Papiers
from briques.clinique.porte import AccesRefuse, JournalDesAcces, PorteDeLecture, charger_badges
from briques.clinique.tests.test_resume_medecin import MEDECIN, _pieces

BADGES = charger_badges()


def _du_cerveau(porte):
    return [l for l in porte.journal.lignes() if l["role"] == "assistant"]


# ---------------------------------------------------------------------------------------------- le résumé
def _sage(titre, sources):
    return {"sur": False, "phrases": []}


def test_sans_cerveau_le_journal_n_a_aucune_ligne_de_l_assistant():
    resume, badges, _, porte, _ = _pieces()
    resume.resume(badges[MEDECIN], "p01")
    assert _du_cerveau(porte) == []


def test_le_cerveau_du_resume_lit_par_la_porte_avec_son_badge_au_service_du_medecin():
    resume, badges, _, porte, _ = _pieces()
    vus = []
    resume.cerveau = resume_apertus.CerveauDeTest(lambda titre, sources: vus.append((titre, sorted(sources))) or _sage(titre, sources))
    resume.resume(badges[MEDECIN], "p01")
    lignes = _du_cerveau(porte)
    assert lignes and all(l["qui"] == "assistant" and l["pour"] == MEDECIN and l["patients"] == ["p01"] for l in lignes)
    assert any(l["quoi"] == "patient" and l["resultat"] == "lu" for l in lignes)  # la fiche, lue par la porte
    donnes = [l["quoi"] for l in lignes if l["quoi"].startswith("texte donné au cerveau")]
    assert len(donnes) == len(vus) == 3  # une ligne du journal par appel au cerveau
    for (titre, refs), quoi in zip(vus, donnes):
        assert titre in quoi and all(ref in quoi for ref in refs)


def test_le_cerveau_ne_recoit_rien_d_un_patient_que_son_medecin_ne_voit_pas():
    resume, badges, _, porte, _ = _pieces()
    appels = []
    resume.cerveau = resume_apertus.CerveauDeTest(lambda titre, sources: appels.append(titre) or _sage(titre, sources))
    with pytest.raises(AccesRefuse):
        resume.resume(badges[MEDECIN], "p02")  # p02 n'est pas un patient de ce médecin
    assert appels == [] and not [l for l in _du_cerveau(porte) if l["resultat"] == "lu"]


def test_un_assistant_qui_ne_travaille_pour_personne_ne_recoit_rien():
    resume, badges, _, porte, _ = _pieces()
    with pytest.raises(AccesRefuse, match="ne travaille pour personne"):
        porte.patient(badges["assistant"], "p01")


# ---------------------------------------------------------------------------------------------- les papiers
def _reponse(texte):
    return {"type": "carte d'assurance", "date": None, "auteur": None, "patient": "Madame Giulia B.", "confiance": "haute"}


def test_le_cerveau_des_papiers_a_une_ligne_au_journal_par_papier_recu_au_service_de_l_accueil():
    porte = PorteDeLecture(journal=JournalDesAcces())
    recus = []
    papiers = Papiers(porte, Carnet(), cerveau=CerveauDeTest(lambda texte: recus.append(texte) or _reponse(texte)))
    pile = papiers.pile(BADGES["accueil"])
    assert all(l["qui"] == "assistant" and l["pour"] == "accueil" and l["resultat"] == "lu" for l in _du_cerveau(porte))
    # depuis H01, la pièce qui range lit aussi le texte sous ce badge (« papiers à ranger ») ; ici : ce qui va au cerveau
    donnes = lambda: [l for l in _du_cerveau(porte) if l["quoi"].startswith("texte d'un papier donné au cerveau")]  # noqa: E731
    lignes = donnes()
    assert len(recus) == 4 and len(lignes) == 4  # les trois papiers de Madame B. et la feuille sans nom
    connus = {p["id"] for groupe in ("a_valider", "a_trier", "valides") for p in pile[groupe]}
    assert {re.search(r"« (.+?) »", l["quoi"]).group(1) for l in lignes} == connus
    papiers.pile(BADGES["accueil"])  # deuxième lecture de la pile : rien n'est redonné au cerveau
    assert len(recus) == 4 and len(donnes()) == 4


def test_sans_cerveau_aucun_texte_n_est_donne_a_un_cerveau():
    """Depuis H01, la pièce qui range lit le texte sous le badge de l'assistant, même sans cerveau : c'est sa lecture.
    Mais rien n'est « donné au cerveau »."""
    porte = PorteDeLecture(journal=JournalDesAcces())
    Papiers(porte, Carnet()).pile(BADGES["accueil"])
    assert {l["quoi"] for l in _du_cerveau(porte)} == {"papiers à ranger"}


# ---------------------------------------------------------------------------------------------- les mesures
def test_les_mesures_ne_lisent_plus_le_faux_dossier_sans_la_porte():
    for module in (papiers_images, papiers_apertus, resume_apertus):
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert "faux_dossier.charger" not in source and "dossier.charger" not in source, module.__name__
        assert not re.search(r"^from \. import dossier|^from \.dossier import", source, flags=re.M), module.__name__


def test_la_reference_des_images_est_lue_par_la_porte_et_donne_les_memes_textes():
    journal = JournalDesAcces()
    reference = papiers_images.reference(journal=journal)
    assert set(reference) == set(papiers_images.PAPIERS) and all(r["texte"].startswith("INVENTÉ") for r in reference.values())
    assert reference["f-01"]["patient"] is None and reference["p02-d1"]["patient"] == "p02"
    lus = [l for l in journal.lignes() if l["resultat"] == "lu"]
    # des badges qui ont le droit de voir ces papiers ; depuis H01, la feuille sans nom : la pièce qui range (assistant)
    assert lus and {l["role"] for l in lus} <= {"soignant", "assistant"}


def test_la_mesure_du_rangement_donne_les_papiers_au_cerveau_sous_le_badge_de_l_assistant():
    journal = JournalDesAcces()
    papiers = papiers_apertus.papiers_du_faux_dossier(journal=journal)
    assert len(papiers) >= 6
    lus = [l for l in journal.lignes() if l["resultat"] == "lu"]
    assert lus and all(l["role"] == "assistant" and l["pour"] in (MEDECIN, "accueil") for l in lus)
