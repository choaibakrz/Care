"""H18 — Le tableau de flotte montre la place de R1 lue sur le robot (réponse de Hiba à Q28 : A).

« Fini » veut dire :
- robot branché : la ligne de R1 dit « près de « LIEU » (lu sur le robot) » et « batterie lue sur le robot » ; le lieu
  est le lieu du plan le plus proche de la position lue sur la prise (la même règle que pour la reprise, H12) ;
- afficher la page ne déplace rien : lire la place n'écrit pas dans le monde des robots ;
- si la lecture échoue, la page le dit et n'invente rien ;
- sans robot branché : rien ne change (« pas suivie », « pas lue », R1 absent du plan).
Le chiffre de la batterie n'est pas montré : l'essai établi du tour 81 interdit « 100 % » sur cette ligne (question Q34).
Testé sur faux robot (système pas démarré : aucun geste ne part).
"""
from __future__ import annotations

import html

from fastapi.testclient import TestClient

from briques.clinique.tests.test_relecture_tranche_3 import PAGE, banc, banc_branche  # noqa: F401 (les mêmes bancs)


def _ligne_de_r1(app):
    return TestClient(app).get(PAGE).text.split("<td><b>R1</b></td>")[1].split("</tr>")[0]


def test_robot_branche_la_ligne_de_r1_dit_ou_il_est_lu_sur_le_robot(banc_branche):
    app, clinique, systeme = banc_branche
    ligne = html.unescape(_ligne_de_r1(app))
    import asyncio

    # le lieu le plus proche de la position du faux robot, calculé ici à part
    lue = asyncio.run(systeme.prise.etat()).position
    proche = min((l for l in systeme.monde.lieux if l.id in clinique.tableau_de_flotte.monde._lieux),
                 key=lambda l: (l.position.x - lue["x"]) ** 2 + (l.position.y - lue["y"]) ** 2)
    assert clinique.coursier is not None
    assert f"près de « {proche.id} » (lu sur le robot)" in ligne
    assert "batterie lue sur le robot" in ligne and "pas lue" not in ligne and "pas suivie" not in ligne


def test_afficher_la_page_ne_deplace_pas_r1_dans_le_monde_des_robots(banc_branche):
    app, clinique, _ = banc_branche
    monde = clinique.tableau_de_flotte.monde
    avant = dict(monde._robot(clinique.coursier.badge.id))
    _ligne_de_r1(app)
    TestClient(app).get(PAGE + "/contenu")
    assert dict(monde._robot(clinique.coursier.badge.id)) == avant


def test_si_la_lecture_echoue_la_page_le_dit_et_n_invente_rien(banc_branche):
    app, clinique, _ = banc_branche

    async def casse():
        raise ConnectionError("prise coupée")

    clinique.coursier._lire_le_monde = casse
    ligne = _ligne_de_r1(app)
    assert "place pas lue" in ligne and "batterie pas lue" in ligne and "près de" not in ligne


def test_sans_robot_branche_rien_ne_change(banc):
    client, _ = banc
    ligne = client.get(PAGE).text.split("<td><b>R1</b></td>")[1].split("</tr>")[0]
    assert "pas suivie" in ligne and "pas lue" in ligne and "lu sur le robot" not in ligne


def test_un_robot_sans_position_ni_batterie_ne_fait_rien_croire(banc_branche):
    app, clinique, systeme = banc_branche

    async def vide():
        etat = await systeme.prise.etat()
        return etat.model_copy(update={"position": None, "batterie_pct": None})

    clinique.coursier._lire_le_monde = vide
    ligne = _ligne_de_r1(app)
    assert "place pas lue" in ligne and "batterie pas lue" in ligne and "près de" not in ligne


def test_une_place_lue_sans_batterie_ne_dit_pas_batterie_lue(banc_branche):
    app, clinique, systeme = banc_branche

    async def sans_batterie():
        etat = await systeme.prise.etat()
        return etat.model_copy(update={"batterie_pct": None})

    clinique.coursier._lire_le_monde = sans_batterie
    ligne = html.unescape(_ligne_de_r1(app))
    assert "(lu sur le robot)" in ligne and "batterie pas lue" in ligne and "batterie lue sur le robot" not in ligne


def test_le_faux_robot_deplace_ailleurs_est_vu_pres_d_un_autre_lieu(banc_branche):
    app, clinique, systeme = banc_branche
    lieux = [l for l in systeme.monde.lieux if l.id in clinique.tableau_de_flotte.monde._lieux]
    depart = html.unescape(_ligne_de_r1(app))
    autre = next(l for l in lieux if f"« {l.id} »" not in depart)

    async def ailleurs():
        etat = await systeme.prise.etat()
        return etat.model_copy(update={"position": {"x": autre.position.x, "y": autre.position.y, "cap": 0.0}})

    clinique.coursier._lire_le_monde = ailleurs
    import time

    time.sleep(1.6)  # la page garde une lecture 1,5 s
    assert f"près de « {autre.id} » (lu sur le robot)" in html.unescape(_ligne_de_r1(app))
