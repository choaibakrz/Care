"""La clinique en boîte — T24, la panne et la reprise (cahier 5.10).

« Batterie basse ou robot bloqué : la tâche passe « reprise » et un autre robot la prend. Si aucun ne peut : un humain
reprend la main, et c'est écrit. »
« Fini » veut dire :
- un robot en course dont la batterie tombe trop bas, ou qui est bloqué : sa tâche passe « reprise », la panne est
  écrite au carnet, avec le robot, la raison, et si elle est provoquée ;
- la reprise est donnée par le répartiteur : le robot libre le plus proche, avec la bonne carte et assez de batterie ;
  jamais le robot en panne ; la phrase qui dit pourquoi est écrite sur la tâche ;
- si le robot en panne avait déjà pris l'objet, le robot suivant va d'abord le chercher là où la panne a eu lieu ;
- un robot simulé qui arrive ne « livre » jamais : la tâche le dit (« arrivé dans le monde simulé ») ;
- si un robot est branché, c'est lui qui reprend, par le coursier, sous le gardien — ou personne ;
- si aucun robot ne peut : la tâche passe à un humain, c'est écrit, et c'est compté comme une aide humaine.
R2 à R4 sont SIMULÉS : rien ne bouge. R1 est le faux robot.
"""
from __future__ import annotations

import asyncio

import pytest

from briques.clinique import cartes, panne_reprise, repartiteur
from briques.clinique.carnet import Carnet
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.listes import ListesDeSoin
from briques.clinique.monde_robots import MondeDesRobots
from briques.clinique.porte import JournalDesAcces, PorteDeLecture, charger_badges
from briques.clinique.taches import TableauDesTaches

BADGES = charger_badges()


def _banc(coursier=None, tableau=None, carnet=None):
    flotte = cartes.CartesDeLaFlotte()
    monde = MondeDesRobots(cartes=flotte)
    monde.placer("robot-r1", "Salon")
    if tableau is None:
        horloge = HorlogeDeDemonstration()
        carnet = Carnet(horloge=horloge)
        listes = ListesDeSoin(PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), carnet)
        tableau = TableauDesTaches(listes.porte, carnet, listes)
    rep = repartiteur.Repartiteur(monde, flotte)
    pr = panne_reprise.PanneEtReprise(monde, rep, tableau, carnet, coursier=coursier)
    return pr, monde, tableau, carnet, rep


def _course(pr, tableau, quoi="la couverture"):
    """Une demande d'un soignant, attribuée par le répartiteur : R2, à la réserve, part."""
    tache = tableau.demander(BADGES["soignant-etage-2"], "p01", quoi)["tache"]
    attribuee = pr.repartiteur.attribuer(tableau, tache["id"])
    assert attribuee["robot"] == "robot-r2"
    return tache["id"]


def _etats(carnet, ident):
    return [l["donnees"]["etat"] for l in carnet.lignes("tâche") if l["donnees"]["id"] == ident]


# ---------------------------------------------------------------------------------------------- la panne
def test_batterie_basse_en_route_la_tache_passe_reprise_et_la_panne_est_ecrite():
    pr, monde, tableau, carnet, _ = _banc()
    ident = _course(pr, tableau)
    monde._robot("robot-r2")["batterie"] = monde.seuil + 0.5  # presque vide : la panne viendra d'elle-même en route
    for _ in range(10):
        pr.avancer()
        if tableau.tache(ident)["etat"] == "reprise":
            break
    tache = tableau.tache(ident)
    assert tache["etat"] == "reprise" and tache["repris_de"] == "robot-r2" and "batterie basse" in tache["pourquoi"]
    panne = carnet.lignes("panne de robot")[-1]["donnees"]
    assert (panne["robot"], panne["raison"], panne["provoquee"], panne["tache"]) == ("robot-r2", "batterie basse", False, ident)
    assert panne["etiquette"] == "FAUX ROBOT — SIMULÉ"
    assert next(r for r in monde.etat() if r["id"] == "robot-r2")["etat"] == "en panne"


def test_un_robot_bloque_expres_la_tache_passe_reprise():
    pr, monde, tableau, carnet, _ = _banc()
    ident = _course(pr, tableau)
    pr.avancer()
    rendue = pr.provoquer("robot-r2", "robot bloqué")
    assert rendue["id"] == ident and rendue["etat"] == "reprise" and "panne provoquée" in rendue["pourquoi"]
    assert carnet.lignes("panne de robot")[-1]["donnees"]["provoquee"] is True
    assert pr.provoquer("robot-r3", "robot bloqué") is None  # R3 n'avait pas de tâche : la panne est écrite, rien à reprendre
    assert len(carnet.lignes("panne de robot")) == 2


# ---------------------------------------------------------------------------------------------- la reprise par le plus proche
def test_le_robot_libre_le_plus_proche_reprend_et_la_tache_dit_pourquoi():
    pr, monde, tableau, carnet, _ = _banc()
    ident = _course(pr, tableau)
    pr.provoquer("robot-r2", "batterie basse")
    fin = asyncio.run(pr.reprendre(ident))
    assert fin["etat"] == "en route" and fin["robot"] == "robot-r4" and fin["repris_de"] == "robot-r2"
    assert fin["etiquette"] == "FAUX ROBOT — SIMULÉ"
    assert "J'envoie R4" in fin["pourquoi_ce_robot"] and "R2 : en panne" in fin["pourquoi_ce_robot"]
    assert next(r for r in monde.etat() if r["id"] == "robot-r4")["tache"] == ident
    assert _etats(carnet, ident)[-4:] == ["attribuée", "reprise", "attribuée", "en route"]


def test_si_l_objet_etait_deja_pris_le_robot_suivant_va_le_chercher_la_ou_la_panne_a_eu_lieu():
    pr, monde, tableau, _, _ = _banc()
    ident = _course(pr, tableau)  # R2 est déjà à la réserve : au premier pas, il a l'objet et part vers la chambre
    for _ in range(3):
        pr.avancer()
    ou_est_r2 = monde._robot("robot-r2")["lieu"]
    rendue = pr.provoquer("robot-r2", "robot bloqué")
    assert rendue["objet_avec"] == "robot-r2" and rendue["objet_ou"] == ou_est_r2 and ou_est_r2 != "Réserve"
    fin = asyncio.run(pr.reprendre(ident))
    assert fin["robot"] == "robot-r4" and fin["de"] == ou_est_r2  # il ne retourne pas à la réserve : l'objet n'y est plus
    assert ou_est_r2 in fin["pourquoi_ce_robot"]


def test_un_robot_simule_qui_arrive_ne_livre_jamais():
    pr, monde, tableau, carnet, _ = _banc()
    ident = _course(pr, tableau)
    pr.provoquer("robot-r2", "batterie basse")
    asyncio.run(pr.reprendre(ident))
    for _ in range(40):
        pr.avancer()
    tache = tableau.tache(ident)
    assert tache["etat"] == "en route" and "arrivé dans le monde simulé" in tache["arrive_simule"]
    assert "livrée" not in _etats(carnet, ident)
    assert next(r for r in monde.etat() if r["id"] == "robot-r4")["etat"] == "libre"  # il est de nouveau libre


# ---------------------------------------------------------------------------------------------- personne ne peut : un humain
def test_si_aucun_robot_ne_peut_un_humain_reprend_la_main_et_c_est_ecrit_et_compte():
    pr, monde, tableau, carnet, _ = _banc()
    ident = _course(pr, tableau)
    pr.provoquer("robot-r2", "batterie basse")
    for autre in ("robot-r3", "robot-r4"):
        monde.panne(autre, "robot bloqué")
    avant = len(tableau.aides)
    fin = asyncio.run(pr.reprendre(ident))
    assert fin["etat"] == "reprise" and fin["sorte"] == "humain"
    assert "aucun robot ne peut reprendre la course" in fin["pourquoi_un_humain"] and "en panne" in fin["pourquoi_un_humain"]
    assert len(tableau.aides) == avant + 1 and tableau.aides[-1]["sorte"] == "main"


def test_on_ne_reprend_qu_une_tache_de_robot_a_l_etat_reprise():
    pr, _, tableau, _, _ = _banc()
    ident = _course(pr, tableau)
    with pytest.raises(ValueError, match="reprise"):
        asyncio.run(pr.reprendre(ident))


# ---------------------------------------------------------------------------------------------- avec le robot branché
def test_avec_un_robot_branche_c_est_lui_qui_reprend_par_le_coursier_sous_le_gardien(tmp_path):
    """R2 (simulé) tombe en panne ; un robot est branché (le faux robot) : la reprise doit être une vraie livraison,
    donc R1, par le coursier. Chaque geste a d'abord un « oui » du gardien. Testé sur faux robot."""
    from commun.systeme import REGLAGES_EXEMPLE, Systeme, charger_reglages

    from briques.clinique.coursier import Coursier, monde_de_la_clinique

    reglages = charger_reglages(REGLAGES_EXEMPLE)
    reglages["cerveau"] = {**reglages["cerveau"], "choix": "regles"}

    async def jouer():
        systeme = Systeme(reglages, dossier_journal=str(tmp_path), acceleration=20.0, monde=monde_de_la_clinique())
        horloge = HorlogeDeDemonstration(bus=systeme.bus)
        carnet = Carnet(horloge=horloge)
        listes = ListesDeSoin(PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), carnet)
        tableau = TableauDesTaches(listes.porte, carnet, listes)
        coursier = Coursier(systeme, tableau, listes, BADGES["robot-r1"])
        pr, monde, *_ = _banc(coursier=coursier, tableau=tableau, carnet=carnet)
        ident = _course(pr, tableau, "la feuille d'exercices")
        pr.provoquer("robot-r2", "batterie basse")
        await systeme.demarrer()
        try:
            fin = await pr.reprendre(ident)
        finally:
            await systeme.arreter()
        oui = [e for e in systeme.bus.historique if e.type == "gardien_decision" and e.donnees["verdict"] == "oui"]
        return fin, len(oui), _etats(carnet, ident)

    fin, oui, etats = asyncio.run(jouer())
    assert fin["etat"] == "livrée" and fin["robot"] == "robot-r1" and fin["repris_de"] == "robot-r2", fin
    assert oui == 4 and "reprise" in etats
    assert "simulé" in fin["pourquoi_ce_robot"] and "R1" in fin["pourquoi_ce_robot"]


def test_la_commande_d_essai_raconte_la_panne_et_la_reprise():
    lignes: list[str] = []
    code = panne_reprise.essai(ecrire=lignes.append)
    texte = "\n".join(lignes)
    assert code == 0 and "FAUX ROBOT — SIMULÉ" in lignes[0] and "rien ne bouge" in texte
    assert "panne" in texte and "reprise" in texte and "J'envoie R4" in texte and "arrivé dans le monde simulé" in texte
    assert "un humain reprend la main" in texte
