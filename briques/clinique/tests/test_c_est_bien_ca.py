"""H16a — Une demande au robot arrivée à la voix est écrite « validée : non » ; la personne confirme d'un doigt
(« C'est bien ça ») (réponse de Hiba à Q23 : B).

Pourquoi : le jour où une vraie écoute sera branchée, c'est la machine qui aura compris la phrase, pas une personne.
Le carnet ne doit donc pas dire « validée par un humain : oui » tant que la personne n'a pas confirmé.
Ce qui ne change pas : la demande au doigt (validée : oui, comme avant) ; la course du robot part comme avant (la
confirmation concerne le carnet, pas le départ du robot — voir NON_TESTE.md).
Les coches à la voix (H16b) attendent une réponse de Hiba (question Q32) : un essai établi dit l'inverse.
DIRE VRAI : pas de micro ; la « phrase entendue » est tapée. Testé sur faux robot (ici, sans robot du tout).
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique.carnet import Carnet
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.listes import HUMAINS, ChoixRefuse, ListesDeSoin
from briques.clinique.porte import AccesRefuse, JournalDesAcces, PorteDeLecture, charger_badges
from briques.clinique.taches import TableauDesTaches

BADGES = charger_badges()
SOIGNANT = BADGES["soignant-etage-2"]
AUTRE = next(b for b in BADGES.values() if b.role in HUMAINS and b.id != SOIGNANT.id)
ROBOT = next(b for b in BADGES.values() if b.role == "robot")


def _tableau():
    porte, carnet = PorteDeLecture(journal=JournalDesAcces()), Carnet()
    return TableauDesTaches(porte, carnet, ListesDeSoin(porte, carnet))


def _lignes(tableau):
    return tableau.carnet.lignes("tâche")


def _a_la_voix(tableau):
    tableau.entendre(SOIGNANT, "p01", "il manque un coussin")
    r = tableau.entendre(SOIGNANT, "p01", "le grand")
    assert r["compris"] == "tâche"
    return r["tache"]


def test_une_demande_a_la_voix_est_ecrite_validee_non_et_attend_c_est_bien_ca():
    tableau = _tableau()
    tache = _a_la_voix(tableau)
    (ligne,) = _lignes(tableau)
    assert ligne["valide_par_un_humain"] is False and ligne["qui"] == SOIGNANT.id
    assert tache["phrase_confirmee"] == "pas encore" and ligne["donnees"]["entendu"] == "il manque un coussin → le grand"


def test_la_meme_demande_au_doigt_reste_validee_oui_sans_bouton():
    tableau = _tableau()
    tache = tableau.demander(SOIGNANT, "p01", "il manque un coussin", choix="grand coussin")["tache"]
    (ligne,) = _lignes(tableau)
    assert ligne["valide_par_un_humain"] is True and "phrase_confirmee" not in tache


def test_c_est_bien_ca_ecrit_une_ligne_validee_oui_sans_changer_la_tache():
    tableau = _tableau()
    tache = _a_la_voix(tableau)
    apres = tableau.c_est_bien_ca(SOIGNANT, tache["id"])
    premiere, seconde = _lignes(tableau)
    assert premiere["valide_par_un_humain"] is False  # la première ligne n'est jamais réécrite
    assert seconde["valide_par_un_humain"] is True and seconde["qui"] == SOIGNANT.id
    assert apres["phrase_confirmee"] == "oui" and tableau.tache(tache["id"])["phrase_confirmee"] == "oui"
    for cle in ("quoi", "de", "ou", "pour_qui", "etat", "sorte"):
        assert apres[cle] == tache[cle], cle


@pytest.mark.parametrize("qui", [AUTRE, ROBOT])
def test_seule_la_personne_qui_a_parle_confirme_sa_phrase(qui):
    tableau = _tableau()
    tache = _a_la_voix(tableau)
    with pytest.raises(AccesRefuse):
        tableau.c_est_bien_ca(qui, tache["id"])
    assert len(_lignes(tableau)) == 1 and tableau.tache(tache["id"])["phrase_confirmee"] == "pas encore"


def test_on_ne_confirme_pas_deux_fois_ni_une_demande_au_doigt():
    tableau = _tableau()
    tache = _a_la_voix(tableau)
    tableau.c_est_bien_ca(SOIGNANT, tache["id"])
    with pytest.raises(ChoixRefuse):
        tableau.c_est_bien_ca(SOIGNANT, tache["id"])
    au_doigt = tableau.demander(SOIGNANT, "p01", "il manque un coussin", choix="coussin de nuque")["tache"]
    with pytest.raises(ChoixRefuse):
        tableau.c_est_bien_ca(SOIGNANT, au_doigt["id"])


def test_une_ligne_du_robot_apres_ne_fait_pas_croire_a_une_confirmation():
    tableau = _tableau()
    tache = _a_la_voix(tableau)
    tableau.changer_etat(ROBOT, tache["id"], "en route")
    assert tableau.tache(tache["id"])["phrase_confirmee"] == "pas encore"
    assert _lignes(tableau)[-1]["valide_par_un_humain"] is False
    apres = tableau.c_est_bien_ca(SOIGNANT, tache["id"])  # confirmer après une ligne du robot : l'état reste
    assert apres["etat"] == "en route" and apres["phrase_confirmee"] == "oui"


def test_une_demande_a_la_voix_passee_a_un_humain_attend_aussi_la_confirmation():
    tableau = _tableau()
    r = tableau.entendre(SOIGNANT, "p01", "il manque une couverture chauffante")
    if r["compris"] != "tâche":
        pytest.skip("cet objet ne fait pas une tâche ici : " + r["dit"])
    assert r["tache"]["phrase_confirmee"] == "pas encore" and _lignes(tableau)[-1]["valide_par_un_humain"] is False


def test_l_ecran_de_la_liste_montre_le_bouton_et_l_api_confirme():
    from briques.clinique.ecrans import brancher_ecrans

    horloge = HorlogeDeDemonstration()
    app = FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge), code_equipe="x")
    client = TestClient(app)
    page = client.get("/clinique/soignant/liste", params={"badge": SOIGNANT.id, "patient": "p01", "liste": "installation"}).text
    assert "C'est bien ça" in page and "/api/clinique/demande/c-est-bien-ca" in page
    corps = {"badge": SOIGNANT.id, "patient": "p01", "liste": "installation"}
    client.post("/api/clinique/liste/voix", json={**corps, "phrase": "il manque un coussin"})
    tache = client.post("/api/clinique/liste/voix", json={**corps, "phrase": "le grand"}).json()["tache"]
    assert tache["phrase_confirmee"] == "pas encore"
    r = client.post("/api/clinique/demande/c-est-bien-ca", json={"badge": AUTRE.id, "tache": tache["id"]})
    assert r.status_code == 403
    r = client.post("/api/clinique/demande/c-est-bien-ca", json={"badge": SOIGNANT.id, "tache": tache["id"]})
    assert r.status_code == 200 and r.json()["phrase_confirmee"] == "oui"
    assert clinique.carnet.lignes("tâche")[-1]["valide_par_un_humain"] is True


def test_le_tableau_du_soignant_garde_le_bouton_tant_que_ce_n_est_pas_confirme():
    from briques.clinique.ecrans import brancher_ecrans

    horloge = HorlogeDeDemonstration()
    app = FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge), code_equipe="x")
    client = TestClient(app)
    corps = {"badge": SOIGNANT.id, "patient": "p01", "liste": "installation"}
    client.post("/api/clinique/liste/voix", json={**corps, "phrase": "il manque un coussin"})
    tache = client.post("/api/clinique/liste/voix", json={**corps, "phrase": "le grand"}).json()["tache"]
    action = f"/clinique/soignant/tache/c-est-bien-ca?badge={SOIGNANT.id}&amp;tache={tache['id']}"
    page = client.get("/clinique/soignant", params={"badge": SOIGNANT.id}).text
    assert "à confirmer" in page and action in page
    r = client.post(f"/clinique/soignant/tache/c-est-bien-ca?badge={AUTRE.id}&tache={tache['id']}", follow_redirects=False)
    assert r.status_code == 403
    r = client.post(f"/clinique/soignant/tache/c-est-bien-ca?badge={SOIGNANT.id}&tache={tache['id']}", follow_redirects=False)
    assert r.status_code == 303
    page = client.get("/clinique/soignant", params={"badge": SOIGNANT.id}).text
    assert "à confirmer" not in page and action not in page
    assert clinique.carnet.lignes("tâche")[-1]["valide_par_un_humain"] is True
