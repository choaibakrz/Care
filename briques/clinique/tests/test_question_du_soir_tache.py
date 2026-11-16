"""La clinique en boîte — H02, chaque question du soir crée aussi une tâche pour le médecin.

Réponse de Hiba à la question Q15 (12.11.2026) : « B, en version la plus petite : chaque question du soir crée aussi
une tâche pour le médecin. » Cahier 2.6 : à toute question de santé, le prototype transmet et crée une tâche pour un humain.
« Fini » veut dire :
- une question du soir = une ligne au carnet (comme avant) ET une tâche « pour un humain », pour le médecin ;
- la tâche renvoie à la ligne du carnet ; elle ne recopie pas la question et ne dit rien de la santé ;
- elle n'est pas « validée par un humain » : c'est le prototype qui la crée, à la demande de la patiente ;
- seul le médecin la voit, sur son écran et dans son tableau ; ni le soignant, ni le thérapeute, ni l'accueil ;
- le prototype ne répond toujours pas ; le résumé du lendemain porte toujours la question ;
- un patient ne peut créer aucune autre tâche par ce chemin.
"""
from __future__ import annotations

import asyncio

import pytest

from briques.clinique.porte import AccesRefuse
from briques.clinique.tests.test_soir_et_dictee import MEDECIN, PATIENTE, Q1, Q2, SOIGNANT, THERAPEUTE, _clinique


def _poser(client, *questions):
    return [client.post("/api/clinique/soir/question", json={"badge": PATIENTE, "texte": q}) for q in questions]


def _taches_du_soir(clinique):
    return [l for l in clinique.carnet.lignes("tâche") if l["donnees"].get("origine") == "question du soir"]


def test_chaque_question_du_soir_cree_une_tache_pour_le_medecin_qui_renvoie_au_carnet():
    client, clinique, _ = _clinique("le soir")
    reponses = _poser(client, Q1, Q2)
    assert all(r.status_code == 200 for r in reponses)
    questions = clinique.carnet.lignes("question du soir")
    taches = _taches_du_soir(clinique)
    assert len(questions) == 2 and len(taches) == 2
    for question, ligne in zip(questions, taches):
        t = ligne["donnees"]
        assert (t["sorte"], t["pour"], t["pour_qui"], t["etat"]) == ("humain", "médecin", "p01", "demandée")
        assert t["question"] == question["numero"] and f"ligne {question['numero']} du carnet" in t["quoi"]
        assert t["pour_quand"] == "jour 2" and t["ou"] == "Chambre 12" and t["qui_demande"] == PATIENTE
        assert ligne["valide_par_un_humain"] is False  # créée par le prototype, pas validée par une personne
    assert len({l["donnees"]["id"] for l in taches}) == 2


def test_la_tache_ne_recopie_pas_la_question_et_le_prototype_ne_repond_toujours_pas():
    client, clinique, _ = _clinique("le soir")
    dit = _poser(client, Q1)[0].json()["dit"]
    assert "trasmessa al medico" in dit and "Non rispondo" in dit and "deambulatore" not in dit
    tache = _taches_du_soir(clinique)[0]["donnees"]
    assert "deambulatore" not in str(tache) and "camminare" not in str(tache)


def test_seul_le_medecin_voit_la_tache_dans_son_tableau_et_sur_son_ecran():
    client, clinique, _ = _clinique("le soir")
    _poser(client, Q1)
    asyncio.run(clinique.horloge.sauter("le lendemain matin"))
    du_medecin = [t for t in clinique.taches.tableau(clinique.badges[MEDECIN]) if t.get("origine") == "question du soir"]
    assert len(du_medecin) == 1 and du_medecin[0]["nom_du_patient"] == "Madame Giulia B."
    for autre in (SOIGNANT, THERAPEUTE):
        assert not [t for t in clinique.taches.tableau(clinique.badges[autre]) if t.get("origine") == "question du soir"]
    page = client.get("/clinique/medecin", params={"badge": MEDECIN}).text
    assert "Tâches pour moi (1)" in page and "Répondre à la question du soir" in page
    assert Q1 in page  # la question elle-même reste dans le résumé, avec sa source
    for ecran, badge in (("soignant", SOIGNANT), ("therapeute", THERAPEUTE)):
        assert "Répondre à la question du soir" not in client.get(f"/clinique/{ecran}", params={"badge": badge}).text
    assert "Répondre à la question du soir" not in client.get("/api/clinique/taches", params={"badge": SOIGNANT}).text


def test_le_resume_du_lendemain_porte_toujours_les_questions():
    client, clinique, _ = _clinique("le soir")
    _poser(client, Q1, Q2)
    asyncio.run(clinique.horloge.sauter("le lendemain matin"))
    ligne = next(l for l in clinique.resume.resume(clinique.badges[MEDECIN], "p01")["lignes"] if l["titre"] == "Ses questions")
    assert Q1 in ligne["texte"] and Q2 in ligne["texte"]


def test_un_patient_ne_cree_aucune_autre_tache_par_ce_chemin():
    _, clinique, _ = _clinique("le soir")
    patiente, soignant = clinique.badges[PATIENTE], clinique.badges[SOIGNANT]
    with pytest.raises(AccesRefuse):  # la tâche d'une question : seulement pour la patiente elle-même, par la pièce du soir
        clinique.taches.pour_la_question_du_soir(soignant, "p01", 1, "jour 2")
    with pytest.raises(AccesRefuse):
        clinique.taches.pour_la_question_du_soir(patiente, "p02", 1, "jour 2")
    with pytest.raises(AccesRefuse):  # et un patient ne crée toujours pas de tâche pour un collègue
        clinique.taches.pour_un_humain(patiente, "p01", "apporter un café", pour="soignant")
    assert _taches_du_soir(clinique) == []


def test_une_question_refusee_ne_cree_aucune_tache():
    client, clinique, _ = _clinique()  # le matin : la question du soir n'est pas posée
    assert _poser(client, Q1)[0].status_code != 200
    client2, clinique2, _ = _clinique("le soir")
    assert _poser(client2, "   ")[0].status_code != 200
    assert _taches_du_soir(clinique) == [] and _taches_du_soir(clinique2) == []
