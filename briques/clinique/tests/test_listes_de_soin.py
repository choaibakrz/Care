"""La clinique en boîte — T06a, les listes de soin : le carnet et la logique (cahier 5.5, 6.3, et 5.1 pour le carnet).

« Fini » veut dire :
- cinq points cochés sur six donnent « Il reste un point : la sonnette. » ;
- en fin de poste, les trois choix marchent : le faire, le reporter avec une raison, le passer à la relève ;
- la direction ne voit que des comptes par étage, jamais par personne ;
- tout ce que le prototype crée va dans le carnet (qui, quand, validé par un humain) ; le faux dossier ne change pas.
Les boutons sur l'écran viennent avec T06b. Internet coupé, aucun modèle, aucun robot.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from briques.clinique import dossier as faux_dossier
from briques.clinique.carnet import Carnet
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.listes import ChoixRefuse, ListesDeSoin
from briques.clinique.porte import AccesRefuse, JournalDesAcces, PorteDeLecture, charger_badges

BADGES = charger_badges()
SOIGNANT, MEDECIN, ACCUEIL, DIRECTION = (BADGES[b] for b in ("soignant-etage-2", "medecin-exemple", "accueil", "direction"))


def _listes(fichier=None):
    horloge = HorlogeDeDemonstration()
    porte = PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour)
    carnet = Carnet(horloge=horloge, fichier=fichier)
    return ListesDeSoin(porte, carnet), carnet, horloge, porte


def _cocher_sauf(listes, oublie: int):
    for numero in range(1, 7):
        if numero != oublie:
            listes.cocher(SOIGNANT, "p01", "installation", numero)


# ---------------------------------------------------------------- les données
def test_chaque_point_a_un_nom_court_et_des_mots_proches():
    for liste in faux_dossier.charger().listes:
        assert 5 <= len(liste["points"]) <= 9
        noms = [point["nom"] for point in liste["points"]]
        assert len(set(noms)) == len(noms), "deux points ont le même nom court"
        for point in liste["points"]:
            assert point["nom"] and len(point["nom"]) <= 40 and len(point["mots"]) >= 1
    installation = faux_dossier.charger().liste("installation")
    assert installation["points"][2]["nom"] == "la sonnette"


def test_la_liste_s_affiche_avec_ses_points_tous_a_faire():
    listes, _, _, _ = _listes()
    vue = listes.liste(SOIGNANT, "p01", "installation")
    assert vue["marque"] == "exemple inventé, non médical, à remplacer par les listes de la clinique"
    assert [p["etat"] for p in vue["points"]] == ["à faire"] * 6
    assert vue["points"][2]["texte"] == "Montrer la sonnette et la laisser à portée de main."


# ---------------------------------------------------------------- cocher, « je sors »
def test_cinq_points_coches_sur_six_il_reste_la_sonnette():
    listes, carnet, _, _ = _listes()
    _cocher_sauf(listes, oublie=3)
    sortie = listes.je_sors(SOIGNANT, "p01")
    assert sortie["phrase"] == "Il reste un point : la sonnette."
    assert [p["numero"] for p in sortie["restent"]] == [3]
    etats = [p["etat"] for p in listes.liste(SOIGNANT, "p01", "installation")["points"]]
    assert etats == ["fait", "fait", "à faire", "fait", "fait", "fait"]
    coches = [l for l in carnet.lignes() if l["genre"] == "point de liste"]
    assert len(coches) == 5 and all(l["qui"] == "soignant-etage-2" and l["valide_par_un_humain"] for l in coches)
    assert all(l["donnees"]["comment"] == "au doigt" for l in coches)


@pytest.mark.parametrize("oublie,nom", [(1, "la présentation"), (4, "le lit"), (6, "le déambulateur")])
def test_un_autre_point_oublie_marche_sans_toucher_au_code(oublie, nom):
    listes, _, _, _ = _listes()
    _cocher_sauf(listes, oublie)
    assert listes.je_sors(SOIGNANT, "p01")["phrase"] == f"Il reste un point : {nom}."


def test_je_sors_plusieurs_points_tout_fait_rien_commence():
    listes, _, _, _ = _listes()
    assert listes.je_sors(SOIGNANT, "p01")["phrase"] == ""  # aucune liste commencée : la tablette ne dit rien
    listes.cocher(SOIGNANT, "p01", "installation", 1)
    listes.cocher(SOIGNANT, "p01", "installation", 2)
    listes.cocher(SOIGNANT, "p01", "installation", 4)
    assert listes.je_sors(SOIGNANT, "p01")["phrase"] == \
        "Il reste 3 points : la sonnette, la salle de bain, le déambulateur."
    for numero in (3, 5, 6):
        listes.cocher(SOIGNANT, "p01", "installation", numero)
    sortie = listes.je_sors(SOIGNANT, "p01")
    assert sortie["phrase"] == "Tout est fait." and sortie["restent"] == []
    phrase = "Il reste un point : la sonnette."
    assert "!" not in phrase and "oubli" not in phrase.lower()  # pas d'alarme, pas de reproche


def test_cocher_deux_fois_ne_compte_qu_une_fois_et_un_point_inconnu_est_refuse():
    listes, carnet, _, _ = _listes()
    listes.cocher(SOIGNANT, "p01", "installation", 3)
    listes.cocher(SOIGNANT, "p01", "installation", 3)
    assert len([l for l in carnet.lignes() if l["genre"] == "point de liste"]) == 1
    with pytest.raises(ChoixRefuse):
        listes.cocher(SOIGNANT, "p01", "installation", 7)  # le cerveau n'invente jamais un point : la liste en a six
    with pytest.raises(ChoixRefuse):
        listes.cocher(SOIGNANT, "p01", "sortie", 4)  # cette liste n'est pas prévue pour cette patiente


def test_qui_a_le_droit_de_cocher():
    listes, carnet, _, _ = _listes()
    with pytest.raises(AccesRefuse):
        listes.cocher(BADGES["patient-p01"], "p01", "installation", 1)  # la porte ne donne pas les listes au patient
    with pytest.raises(AccesRefuse):
        listes.cocher(DIRECTION, "p01", "installation", 1)
    with pytest.raises(AccesRefuse):
        listes.cocher(BADGES["robot-r1"], "p01", "installation", 1)
    with pytest.raises(AccesRefuse):
        listes.cocher(BADGES["assistant"].travaille_pour(SOIGNANT), "p01", "installation", 1)  # seul un humain coche
    with pytest.raises(ChoixRefuse):
        listes.cocher(MEDECIN, "p01", "installation", 1)  # ce point est pour le soignant
    with pytest.raises(AccesRefuse):
        listes.cocher(SOIGNANT, "p05", "installation", 1)  # p05 n'est pas à son étage
    assert carnet.lignes() == []


# ---------------------------------------------------------------- la fin de poste : trois choix
def test_en_fin_de_poste_les_trois_choix_marchent():
    listes, carnet, _, _ = _listes()
    for numero in (1, 2, 4):
        listes.cocher(SOIGNANT, "p01", "installation", numero)
    restants = [r for r in listes.fin_de_poste(SOIGNANT) if r["patient"] == "p01" and r["liste"] == "installation"]
    assert [r["numero"] for r in restants] == [3, 5, 6]
    assert all(r["choix"] == ["le faire", "le reporter", "le passer à la relève"] for r in restants)

    listes.choisir(SOIGNANT, "p01", "installation", 3, "le faire")
    listes.choisir(SOIGNANT, "p01", "installation", 5, "le reporter", raison="la patiente dort")
    listes.choisir(SOIGNANT, "p01", "installation", 6, "le passer à la relève")
    points = {p["numero"]: p for p in listes.liste(SOIGNANT, "p01", "installation")["points"]}
    assert points[3]["etat"] == "fait"
    assert points[5]["etat"] == "reporté" and points[5]["raison"] == "la patiente dort"
    assert points[6]["etat"] == "passé à la relève"
    assert not [r for r in listes.fin_de_poste(SOIGNANT) if r["patient"] == "p01" and r["liste"] == "installation"]
    derniere = carnet.lignes()[-1]
    assert derniere["qui"] == "soignant-etage-2" and derniere["valide_par_un_humain"] is True
    assert derniere["quand"]["jour"] == 1 and derniere["quand"]["heure"] == "09:00" and derniere["quand"]["reel"]


def test_reporter_sans_raison_est_refuse_et_un_choix_inconnu_aussi():
    listes, carnet, _, _ = _listes()
    for raison in (None, "", "   "):
        with pytest.raises(ChoixRefuse):
            listes.choisir(SOIGNANT, "p01", "installation", 3, "le reporter", raison=raison)
    with pytest.raises(ChoixRefuse):
        listes.choisir(SOIGNANT, "p01", "installation", 3, "l'effacer")
    assert carnet.lignes() == []


def test_la_fin_de_poste_montre_tout_ce_qui_reste_pour_mon_metier_chez_mes_patients():
    listes, _, _, porte = _listes()
    restants = listes.fin_de_poste(SOIGNANT)
    miens = {p["id"] for p in porte.patients(SOIGNANT)}
    assert restants and {r["patient"] for r in restants} <= miens
    assert all("soignant" in r["pour"] for r in restants)
    assert all(r["etat"] in ("à faire", "en attente d'un objet") for r in restants)
    assert {"nom_du_patient", "chambre", "titre", "nom", "texte", "liste_commencee"} <= set(restants[0])


def test_la_releve_peut_faire_le_point_le_lendemain():
    listes, _, horloge, _ = _listes()
    listes.cocher(SOIGNANT, "p01", "installation", 1)
    listes.choisir(SOIGNANT, "p01", "installation", 3, "le passer à la relève")
    asyncio.run(horloge.sauter("le lendemain matin"))
    listes.cocher(SOIGNANT, "p01", "installation", 3)
    points = {p["numero"]: p for p in listes.liste(SOIGNANT, "p01", "installation")["points"]}
    assert points[3]["etat"] == "fait" and points[3]["quand"]["jour"] == 2


# ---------------------------------------------------------------- la direction : des comptes, jamais par personne
def test_la_direction_ne_voit_que_des_comptes_par_etage():
    listes, carnet, _, _ = _listes()
    _cocher_sauf(listes, oublie=3)
    listes.choisir(SOIGNANT, "p01", "installation", 3, "le reporter", raison="la patiente dort")
    listes.choisir(SOIGNANT, "p02", "avant_physio", 1, "le passer à la relève")
    comptes = listes.comptes(DIRECTION)
    etage_2 = next(e for e in comptes["etages"] if e["etage"] == 2)
    assert (etage_2["faits"], etage_2["reportes"], etage_2["passes_a_la_releve"]) == (5, 1, 1)
    texte = json.dumps(comptes, ensure_ascii=False)
    for interdit in ("p01", "p02", "Giulia", "soignant-etage-2", "Soignant", "la patiente dort", "sonnette"):
        assert interdit not in texte, f"« {interdit} » ne doit pas sortir chez la direction"
    with pytest.raises(AccesRefuse):
        listes.comptes(SOIGNANT)  # les comptes sont pour la direction
    with pytest.raises(AccesRefuse):
        listes.liste(DIRECTION, "p01", "installation")
    with pytest.raises(AccesRefuse):
        listes.fin_de_poste(DIRECTION)


# ---------------------------------------------------------------- le carnet
def test_le_carnet_s_ecrit_dans_un_fichier_et_ne_s_efface_pas(tmp_path):
    fichier = tmp_path / "carnet.jsonl"
    listes, carnet, _, _ = _listes(fichier)
    listes.cocher(SOIGNANT, "p01", "installation", 1)
    listes.choisir(SOIGNANT, "p01", "installation", 3, "le reporter", raison="la patiente dort")
    ecrites = [json.loads(l) for l in fichier.read_text(encoding="utf-8").splitlines()]
    assert ecrites == carnet.lignes() and [l["numero"] for l in ecrites] == [1, 2]
    assert all({"numero", "quand", "qui", "role", "genre", "donnees", "valide_par_un_humain", "marque"} <= set(l) for l in ecrites)
    carnet.lignes()[0]["qui"] = "quelqu'un d'autre"  # modifier une copie ne change pas le carnet
    assert carnet.lignes()[0]["qui"] == "soignant-etage-2"
    assert not hasattr(carnet, "effacer") and not hasattr(carnet, "supprimer")


def test_le_faux_dossier_ne_change_pas_et_tout_passe_par_la_porte():
    avant = faux_dossier.empreinte()
    listes, _, _, porte = _listes()
    _cocher_sauf(listes, oublie=3)
    listes.je_sors(SOIGNANT, "p01")
    listes.fin_de_poste(SOIGNANT)
    assert faux_dossier.empreinte() == avant
    lus = [l for l in porte.journal.lignes() if l["qui"] == "soignant-etage-2" and l["resultat"] == "lu"]
    assert len(lus) >= 5  # chaque geste a lu par la porte, et c'est au journal des accès
    assert not [l for l in porte.journal.lignes() if "écri" in l["resultat"]]


# ---------------------------------------------------------------- la grande répétition, étape 7
def test_l_etape_7_de_la_grande_repetition_est_jouee_par_les_vraies_pieces():
    from briques.clinique import repetition

    resultat = repetition.CONTROLES[7]()
    assert resultat.reussie is True and resultat.etiquette == "SIMULÉ"
    assert "Il reste un point : la sonnette." in resultat.detail
