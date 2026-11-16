"""La clinique en boîte — T23, le répartiteur et le relais (cahier 5.10 et 6.6).

« Fini » veut dire :
- de deux robots libres, le plus proche est choisi ;
- un robot sans la bonne carte n'est jamais choisi ;
- l'arrivée dans le hall produit le message pour l'étage.
Et aussi : un robot occupé, en panne ou sans assez de batterie n'est pas choisi ; si aucun robot ne convient, la tâche
passe à un humain, et c'est écrit ; un robot ne sort pas de ses lieux permis : il passe la main (le relais).
Les robots R2 à R4 sont SIMULÉS (le monde des robots, sans physique) ; R1 est le robot branché : s'il est choisi, la
course se fait par le coursier, sous le gardien.
"""
from __future__ import annotations

import shutil

import pytest

from briques.clinique import cartes, repartiteur
from briques.clinique.accueil import AccueilDuHall
from briques.clinique.carnet import Carnet
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.listes import ListesDeSoin
from briques.clinique.monde_robots import MondeDesRobots
from briques.clinique.porte import JournalDesAcces, PorteDeLecture, charger_badges
from briques.clinique.taches import TableauDesTaches

BADGES = charger_badges()
TACHE = {"id": "t1", "quoi": "couverture", "de": "Réserve", "ou": "Chambre 12"}


def _banc(dossier_des_cartes=None):
    flotte = cartes.CartesDeLaFlotte(**({"dossier_des_cartes": dossier_des_cartes} if dossier_des_cartes else {}))
    monde = MondeDesRobots(cartes=flotte)
    monde.placer("robot-r1", "Salon")  # R1 est au deuxième étage, loin de la réserve
    return repartiteur.Repartiteur(monde, flotte), monde, flotte


# ---------------------------------------------------------------------------------------------- le plus proche
def test_de_deux_robots_libres_le_plus_proche_est_choisi():
    rep, monde, _ = _banc()
    choix = rep.choisir(TACHE)  # R2 est à la réserve (0 m), R4 au poste de soins (4 m)
    assert choix["robot"] == "robot-r2" and choix["metres"] == 0.0
    monde.placer("robot-r2", "Chambre 14")  # R2 s'éloigne : 22 m ; R4 devient le plus proche
    choix = rep.choisir(TACHE)
    assert choix["robot"] == "robot-r4" and choix["metres"] == 4.0
    assert "le plus proche" in choix["pourquoi"] and "R4" in choix["pourquoi"]


def test_la_liste_des_robots_regardes_dit_tout_pour_chacun():
    rep, _, _ = _banc()
    regardes = {r["nom"]: r for r in rep.choisir(TACHE)["regardes"]}
    assert set(regardes) == {"R1", "R2", "R3", "R4"}
    for r in regardes.values():
        assert set(r) >= {"nom", "carte", "etiquette", "libre", "metres", "batterie", "carte_permet", "convient", "raison"}
    assert regardes["R2"]["convient"] and regardes["R2"]["metres"] == 0.0 and regardes["R2"]["etiquette"] == "FAUX ROBOT — SIMULÉ"
    assert regardes["R1"]["etiquette"] == "FAUX ROBOT" and regardes["R3"]["carte"] == "Thérapie"


# ---------------------------------------------------------------------------------------------- la bonne carte
def test_un_robot_sans_la_bonne_carte_n_est_jamais_choisi():
    rep, monde, flotte = _banc()
    flotte.changer("robot-r2", "Accueil", qui="essai")  # le plus proche, mais sa carte ne permet ni la réserve ni de saisir
    choix = rep.choisir(TACHE)
    assert choix["robot"] == "robot-r4"
    r2 = next(r for r in choix["regardes"] if r["nom"] == "R2")
    assert r2["convient"] is False and "carte Accueil" in r2["raison"]
    for _ in range(3):  # même si tous les autres sont pris, il n'est jamais choisi
        suivant = rep.choisir(TACHE)["robot"]
        if suivant is None:
            break
        assert suivant != "robot-r2"
        monde.envoyer(suivant, "Chambre 13") if suivant != "robot-r1" else monde.panne("robot-r1", "essai")
    assert rep.choisir(TACHE)["robot"] is None


def test_la_carte_therapie_ne_va_pas_au_poste_de_soins():
    rep, _, _ = _banc()
    depuis_le_poste = rep.choisir({"id": "t2", "quoi": "couverture", "de": "Poste de soins", "ou": "Chambre 12"})
    r3 = next(r for r in depuis_le_poste["regardes"] if r["nom"] == "R3")
    assert r3["convient"] is False and "Poste de soins" in r3["raison"]
    assert depuis_le_poste["robot"] == "robot-r4"  # R4 y est déjà


# ---------------------------------------------------------------------------------------------- libre, batterie
def test_un_robot_occupe_en_panne_ou_sans_batterie_n_est_pas_choisi():
    rep, monde, _ = _banc()
    monde.envoyer("robot-r2", "Chambre 11")  # occupé
    monde.panne("robot-r4", "roue bloquée")  # en panne
    choix = rep.choisir(TACHE)
    raisons = {r["nom"]: r["raison"] for r in choix["regardes"]}
    assert "occupé" in raisons["R2"] and "en panne" in raisons["R4"]
    assert choix["robot"] in ("robot-r1", "robot-r3")
    monde._robot("robot-r1")["batterie"] = 18.0
    monde._robot("robot-r3")["batterie"] = 24.0  # pas assez pour 28 m puis 14 m (0,5 % par mètre) en restant au-dessus du seuil
    choix = rep.choisir(TACHE)
    raisons = {r["nom"]: r["raison"] for r in choix["regardes"]}
    assert choix["robot"] is None and "batterie" in raisons["R1"] and "batterie" in raisons["R3"]
    assert "aucun robot ne convient" in choix["pourquoi"]


# ---------------------------------------------------------------------------------------------- attribuer
def _tableau():
    horloge = HorlogeDeDemonstration()
    carnet = Carnet(horloge=horloge)
    listes = ListesDeSoin(PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), carnet)
    return TableauDesTaches(listes.porte, carnet, listes), carnet


def test_attribuer_ecrit_le_robot_choisi_et_pourquoi_et_le_robot_simule_part():
    rep, monde, _ = _banc()
    tableau, _ = _tableau()
    tache = tableau.demander(BADGES["soignant-etage-2"], "p01", "la couverture")["tache"]
    attribuee = rep.attribuer(tableau, tache["id"])
    assert attribuee["etat"] == "attribuée" and attribuee["robot"] == "robot-r2" and attribuee["etiquette"] == "FAUX ROBOT — SIMULÉ"
    assert "le plus proche" in attribuee["pourquoi_ce_robot"]
    r2 = next(r for r in monde.etat() if r["id"] == "robot-r2")
    assert r2["tache"] == tache["id"] and r2["etat"] == "en route"  # dans le monde simulé, il part


def test_si_r1_est_choisi_la_course_reste_au_coursier_sous_le_gardien():
    rep, monde, _ = _banc()
    for ident in ("robot-r2", "robot-r3", "robot-r4"):
        monde.panne(ident, "essai")
    tableau, _ = _tableau()
    tache = tableau.demander(BADGES["soignant-etage-2"], "p01", "la couverture")["tache"]
    attribuee = rep.attribuer(tableau, tache["id"])
    assert attribuee["robot"] == "robot-r1" and attribuee["etat"] == "demandée"  # elle attend le coursier : rien ne bouge ici
    assert "coursier" in attribuee["pourquoi_ce_robot"] and "gardien" in attribuee["pourquoi_ce_robot"]
    assert next(r for r in monde.etat() if r["id"] == "robot-r1")["etat"] == "libre"


def test_si_aucun_robot_ne_convient_la_tache_passe_a_un_humain_et_c_est_ecrit():
    rep, monde, _ = _banc()
    for ident in ("robot-r1", "robot-r2", "robot-r3", "robot-r4"):
        monde.panne(ident, "essai")
    tableau, carnet = _tableau()
    tache = tableau.demander(BADGES["soignant-etage-2"], "p01", "la couverture")["tache"]
    passee = rep.attribuer(tableau, tache["id"])
    assert passee["sorte"] == "humain" and "aucun robot ne convient" in passee["pourquoi_un_humain"]
    assert len(tableau.aides) == 1 and tableau.aides[0]["sorte"] == "main"  # c'est une aide humaine, et elle est comptée


# ---------------------------------------------------------------------------------------------- le relais
def test_un_robot_ne_sort_pas_de_ses_lieux_permis_il_passe_la_main(tmp_path):
    copie = tmp_path / "cartes"
    shutil.copytree(cartes.DOSSIER, copie)
    etage, nuit = copie / "etage.yaml", copie / "nuit.yaml"
    # deux métiers d'essai : la carte Étage ne va plus que du poste à la chambre 11 ; la carte Nuit, de la chambre 11 au salon
    etage.write_text(etage.read_text(encoding="utf-8").replace(
        "[Poste de soins, Réserve, Chambre 11, Chambre 12, Chambre 13, Chambre 14, Salon]", "[Poste de soins, Réserve, Chambre 11]"), encoding="utf-8")
    nuit.write_text(nuit.read_text(encoding="utf-8").replace(
        "[Poste de soins, Réserve, Chambre 11, Chambre 12, Chambre 13, Chambre 14, Salon]", "[Chambre 11, Chambre 12, Chambre 13, Chambre 14, Salon]"), encoding="utf-8")
    rep, monde, _ = _banc(copie)
    monde.panne("robot-r3", "essai")  # la carte Thérapie ferait tout le trajet : on l'écarte pour voir le relais
    choix = rep.choisir(TACHE)
    assert choix["robot"] is None and choix["relais"] is not None
    relais = choix["relais"]
    assert relais["point"] == "Chambre 11"
    assert [(e["robot"], e["de"], e["ou"]) for e in relais["etapes"]] == [("robot-r2", "Réserve", "Chambre 11"),
                                                                           ("robot-r4", "Chambre 11", "Chambre 12")]
    assert "passe la main" in choix["pourquoi"] and "Chambre 11" in choix["pourquoi"]
    # personne ne sort de ses lieux permis
    for etape in relais["etapes"]:
        carte = rep.cartes.carte_de(etape["robot"])
        assert carte.refus_lieu(etape["de"]) is None and carte.refus_lieu(etape["ou"]) is None


def test_sans_point_de_passage_commun_pas_de_relais_un_humain(tmp_path):
    rep, monde, flotte = _banc()
    for ident in ("robot-r1", "robot-r2", "robot-r3", "robot-r4"):
        flotte.changer(ident, "Accueil", qui="essai")
    choix = rep.choisir(TACHE)
    assert choix["robot"] is None and choix["relais"] is None and "aucun robot ne convient" in choix["pourquoi"]


# ---------------------------------------------------------------------------------------------- le hall
def test_l_arrivee_dans_le_hall_produit_le_message_pour_l_etage():
    horloge = HorlogeDeDemonstration()
    carnet = Carnet(horloge=horloge)
    porte = PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour)
    accueil = AccueilDuHall(porte, carnet, BADGES["robot-r1"])
    reponse = accueil.entendre("Buongiorno, sono Giulia B.")
    assert reponse["cas"] == "arrivée" and reponse["etage_prevenu"] is True
    messages = accueil.messages_pour_l_etage(BADGES["soignant-etage-2"])
    assert len(messages) == 1 and "12" in str(messages[0])
    # le robot du hall passe la main par un message : sa carte ne lui permet pas de monter
    assert cartes.charger_cartes()["Accueil"].refus_lieu("Chambre 12") is not None
