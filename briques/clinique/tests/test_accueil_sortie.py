"""H17 — L'accueil voit et coche SEULEMENT ses trois points de la liste « Préparation de la sortie »
(réponse de Hiba à Q24 : B).

Les trois points (cahier, liste de sortie) : la liste des rendez-vous (2), le transport (3), les documents à envoyer (7).
« Fini » veut dire :
- par une porte étroite, l'accueil reçoit, pour chaque personne qui a une liste de sortie : son nom, sa chambre, le jour
  de sortie, et ces trois points — rien d'autre (ni les autres points, ni les habitudes, ni le programme, ni la raison) ;
- la règle H01 (Q18) ne change pas : `liste_de_soin` reste refusée à l'accueil, pour toutes les listes ;
- l'accueil coche ses trois points, et seulement eux ; la coche va au carnet, et le médecin la voit dans sa liste ;
- l'écran de l'accueil montre ces trois points avec un bouton « Fait ».
Données inventées. Testé sur faux robot (ici, sans robot).
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique.carnet import Carnet
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.listes import ChoixRefuse, ListesDeSoin
from briques.clinique.porte import AccesRefuse, JournalDesAcces, PorteDeLecture, charger_badges

BADGES = charger_badges()
ACCUEIL, MEDECIN, SOIGNANT = BADGES["accueil"], BADGES["medecin-exemple"], BADGES["soignant-etage-2"]
TROIS = [(2, "la liste des rendez-vous"), (3, "le transport"), (7, "les documents à envoyer")]
AUTRES_POINTS = ("lettre de sortie", "Lettre de sortie", "les aides", "Aides commandées", "les proches", "Proches prévenus",
                 "les affaires", "Affaires rassemblées")
DU_DOSSIER = ("épaule", "réadaptation", "café", "sa fille", "habitudes", "programme")


def _listes():
    horloge = HorlogeDeDemonstration()
    porte = PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour)
    return ListesDeSoin(porte, Carnet(horloge=horloge))


# ------------------------------------------------------------------------------------------------ la porte étroite
def test_la_porte_donne_a_l_accueil_ses_trois_points_et_rien_d_autre():
    porte = PorteDeLecture(journal=JournalDesAcces())
    sorties = porte.points_de_sortie_pour_l_accueil(ACCUEIL)
    assert [s["id"] for s in sorties] == ["p09"]
    (sophie,) = sorties
    assert sophie["nom"] == "Madame Sophie L." and sophie["chambre"] == 19 and sophie["sortie_jour"] == 2
    assert set(sophie) == {"id", "nom", "chambre", "etage", "sortie_jour", "liste", "titre", "points"}
    assert [(p["numero"], p["nom"]) for p in sophie["points"]] == TROIS
    assert all(set(p) == {"numero", "nom", "texte"} for p in sophie["points"])
    texte = str(sorties)
    assert not any(mot in texte for mot in AUTRES_POINTS + DU_DOSSIER), texte
    ligne = porte.journal.lignes()[-1]
    assert (ligne["qui"], ligne["quoi"], ligne["resultat"], ligne["patients"]) == ("accueil", "points de sortie de l'accueil", "lu", ["p09"])


@pytest.mark.parametrize("badge", ["soignant-etage-2", "medecin-exemple", "direction", "robot-r1", "patient-p01", "assistant"])
def test_cette_porte_est_pour_l_accueil_seulement(badge):
    porte = PorteDeLecture(journal=JournalDesAcces())
    with pytest.raises(AccesRefuse):
        porte.points_de_sortie_pour_l_accueil(BADGES[badge])
    assert porte.journal.lignes()[-1]["resultat"] == "refusé"


def test_la_regle_h01_ne_change_pas_aucune_liste_entiere_pour_l_accueil():
    porte = PorteDeLecture(journal=JournalDesAcces())
    porte.points_de_sortie_pour_l_accueil(ACCUEIL)
    for liste in ("installation", "avant_physio", "sortie"):
        with pytest.raises(AccesRefuse):
            porte.liste_de_soin(ACCUEIL, liste)
    assert all("listes" not in p for p in porte.patients(ACCUEIL))


# ------------------------------------------------------------------------------------------------ cocher
def test_l_accueil_coche_le_transport_et_le_medecin_le_voit_dans_sa_liste():
    listes = _listes()
    avant = listes.sorties_pour_l_accueil(ACCUEIL)
    assert [p["etat"] for p in avant[0]["points"]] == ["à faire"] * 3
    listes.cocher_pour_l_accueil(ACCUEIL, "p09", 3)
    ligne = listes.carnet.lignes("point de liste")[-1]
    assert ligne["qui"] == "accueil" and ligne["valide_par_un_humain"] is True
    assert (ligne["donnees"]["patient"], ligne["donnees"]["liste"], ligne["donnees"]["numero"], ligne["donnees"]["etat"]) == ("p09", "sortie", 3, "fait")
    apres = listes.sorties_pour_l_accueil(ACCUEIL)
    assert [p["etat"] for p in apres[0]["points"]] == ["à faire", "fait", "à faire"]
    vue_du_medecin = {p["numero"]: p for p in listes.liste(MEDECIN, "p09", "sortie")["points"]}
    assert vue_du_medecin[3]["etat"] == "fait" and vue_du_medecin[3]["par"] == "accueil"
    assert vue_du_medecin[1]["etat"] == "à faire"


@pytest.mark.parametrize("numero", [1, 4, 5, 6, 8])
def test_l_accueil_ne_coche_aucun_autre_point(numero):
    listes = _listes()
    with pytest.raises((AccesRefuse, ChoixRefuse)):
        listes.cocher_pour_l_accueil(ACCUEIL, "p09", numero)
    assert listes.carnet.lignes("point de liste") == []


def test_l_accueil_ne_coche_rien_pour_une_personne_sans_liste_de_sortie_ni_avec_un_autre_badge():
    listes = _listes()
    with pytest.raises((AccesRefuse, ChoixRefuse)):
        listes.cocher_pour_l_accueil(ACCUEIL, "p01", 3)
    with pytest.raises(AccesRefuse):
        listes.cocher_pour_l_accueil(SOIGNANT, "p09", 3)
    with pytest.raises(AccesRefuse):  # un assistant au service de l'accueil ne coche pas : seul un humain coche
        listes.cocher_pour_l_accueil(BADGES["assistant"].travaille_pour(ACCUEIL), "p09", 3)
    assert listes.carnet.lignes("point de liste") == []


# ------------------------------------------------------------------------------------------------ l'écran
def test_l_ecran_de_l_accueil_montre_les_trois_points_et_un_bouton():
    from briques.clinique.ecrans import brancher_ecrans

    horloge = HorlogeDeDemonstration()
    app = FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge), code_equipe="x")
    client = TestClient(app)
    page = client.get("/clinique/accueil", params={"badge": "accueil"}).text
    assert "Préparation de la sortie" in page and "Madame Sophie L." in page
    assert all(nom in page for _, nom in TROIS)
    assert not any(mot in page for mot in AUTRES_POINTS + DU_DOSSIER)
    contenu = client.get("/clinique/accueil/contenu", params={"badge": "accueil"}).text  # la page qui se recharge
    assert "le transport" in contenu and not any(mot in contenu for mot in AUTRES_POINTS + DU_DOSSIER)
    action = "/clinique/accueil/sortie/cocher?badge=accueil&amp;patient=p09&amp;numero=3"
    assert action in page
    r = client.post("/clinique/accueil/sortie/cocher?badge=soignant-etage-2&patient=p09&numero=3", follow_redirects=False)
    assert r.status_code == 403
    r = client.post("/clinique/accueil/sortie/cocher?badge=accueil&patient=p09&numero=3", follow_redirects=False)
    assert r.status_code == 303
    page = client.get("/clinique/accueil", params={"badge": "accueil"}).text
    assert action not in page  # coché : plus de bouton pour ce point
    assert clinique.carnet.lignes("point de liste")[-1]["qui"] == "accueil"
