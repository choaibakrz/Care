"""La clinique en boîte — H12 : la place de R1 est lue sur le robot, pas inventée (relecture de la tranche 3, points 3, 4, 6).

Avant : dans le monde des robots, R1 était écrit au « Hall » au départ, sans rien lire sur le robot. Au début d'une séance,
la reprise par R1 partait donc à un humain (« pas de chemin »). Et quand R1 reprenait, la tâche disait « le robot va
d'abord chercher l'objet là où la panne a eu lieu », alors que R1 allait à la Réserve.
« Fini » veut dire :
- avant de choisir qui reprend, la place de R1 est lue sur la prise (le lieu du plan le plus proche de sa position) ;
- au début d'une séance, sans rien placer à la main, R1 reprend la course d'un robot simulé en panne et la livre ;
- la phrase de la reprise dit vrai : un robot simulé n'a jamais vraiment pris l'objet, R1 le prend à la Réserve ;
- après une course, le monde des robots sait où R1 est arrivé ;
- si la lecture rate, rien n'est changé et rien n'est inventé.
Le tableau de flotte n'affiche PAS encore cette place : un essai du tour 81 dit le contraire (question Q28 à Hiba).
Testé sur faux robot. Robots R2, R3, R4 simulés. Aucun vrai robot.
"""
from __future__ import annotations

import asyncio
import html

from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique import cartes, panne_reprise, repartiteur
from briques.clinique.carnet import Carnet
from briques.clinique.coursier import Coursier, monde_de_la_clinique
from briques.clinique.ecrans import brancher_ecrans
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.listes import ListesDeSoin
from briques.clinique.monde_robots import MondeDesRobots
from briques.clinique.porte import JournalDesAcces, PorteDeLecture, charger_badges
from briques.clinique.taches import TableauDesTaches
from commun.systeme import REGLAGES_EXEMPLE, Systeme, charger_reglages

BADGES = charger_badges()


def _systeme(dossier):
    reglages = charger_reglages(REGLAGES_EXEMPLE)
    reglages["cerveau"] = {**reglages["cerveau"], "choix": "regles"}
    return Systeme(reglages, dossier_journal=str(dossier), acceleration=20.0, monde=monde_de_la_clinique())


def _jouer(tmp_path, scene, pas_avant_la_panne=0):
    """Début de séance : R1 n'est placé nulle part à la main. R2 (simulé) prend une course, tombe en panne."""
    async def tout():
        systeme = _systeme(tmp_path)
        horloge = HorlogeDeDemonstration(bus=systeme.bus)
        carnet = Carnet(horloge=horloge)
        listes = ListesDeSoin(PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), carnet)
        tableau = TableauDesTaches(listes.porte, carnet, listes)
        coursier = Coursier(systeme, tableau, listes, BADGES["robot-r1"])
        flotte = cartes.CartesDeLaFlotte()
        monde = MondeDesRobots(cartes=flotte)
        pr = panne_reprise.PanneEtReprise(monde, repartiteur.Repartiteur(monde, flotte), tableau, carnet, coursier=coursier)
        ident = tableau.demander(BADGES["soignant-etage-2"], "p01", "la couverture")["tache"]["id"]
        assert pr.repartiteur.attribuer(tableau, ident)["robot"] == "robot-r2"
        for _ in range(pas_avant_la_panne):
            pr.avancer()
        pr.provoquer("robot-r2", "batterie basse")
        await systeme.demarrer()
        try:
            return await scene(pr, monde, systeme, tableau, ident)
        finally:
            await systeme.arreter()

    return asyncio.run(tout())


def test_au_debut_de_la_seance_r1_reprend_la_course_sans_etre_place_a_la_main(tmp_path):
    async def scene(pr, monde, systeme, tableau, ident):
        assert monde._robot("robot-r1")["lieu"] == "Hall"  # le départ écrit dans flotte.yaml : inventé, pas lu
        fin = await pr.reprendre(ident)
        oui = [e for e in systeme.bus.historique if e.type == "gardien_decision" and e.donnees["verdict"] == "oui"]
        return fin, len(oui), monde._robot("robot-r1")["lieu"]

    fin, oui, lieu = _jouer(tmp_path, scene)
    assert fin["etat"] == "livrée" and fin["robot"] == "robot-r1" and fin.get("sorte") == "robot", fin
    assert oui == 4
    assert lieu == "Chambre 12"  # après la course, le monde des robots sait où R1 est arrivé (lu sur la prise)


def test_la_phrase_de_la_reprise_par_r1_dit_vrai_sur_l_objet(tmp_path):
    """R2 était « passé chercher » l'objet dans le monde simulé. Mais un robot simulé ne prend rien pour de vrai."""
    async def scene(pr, monde, systeme, tableau, ident):
        avant = tableau.tache(ident)
        fin = await pr.reprendre(ident)
        lieux = [e.donnees["action"]["parametres"].get("lieu") for e in systeme.bus.historique
                 if e.type == "gardien_decision" and e.donnees["action"]["nom"] == "se_deplacer"]
        return avant, fin, lieux

    avant, fin, lieux = _jouer(tmp_path, scene, pas_avant_la_panne=3)
    assert avant.get("objet_ou") and avant["objet_ou"] != "Réserve", avant  # le monde simulé dit : l'objet est resté ailleurs
    assert fin["etat"] == "livrée" and lieux[0] == "Réserve", (fin, lieux)
    assert "va d'abord le chercher là" not in fin["pourquoi_ce_robot"]
    note = fin["note_de_reprise"]  # gardée à part : le coursier peut récrire sa propre phrase de choix
    assert "n'a jamais vraiment pris" in note and "« Réserve »" in note
    assert not fin.get("objet_ou") and not fin.get("objet_avec")


def test_la_place_lue_est_le_lieu_du_plan_le_plus_proche_et_rien_ne_change_si_la_lecture_rate(tmp_path):
    async def tout():
        systeme = _systeme(tmp_path)
        horloge = HorlogeDeDemonstration(bus=systeme.bus)
        carnet = Carnet(horloge=horloge)
        listes = ListesDeSoin(PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), carnet)
        coursier = Coursier(systeme, TableauDesTaches(listes.porte, carnet, listes), listes, BADGES["robot-r1"])
        monde = MondeDesRobots(cartes=cartes.CartesDeLaFlotte())
        await systeme.demarrer()
        try:
            lu = await coursier.placer_dans(monde)
            etat = await systeme.prise.etat()
        finally:
            await systeme.arreter()
        place = monde._robot("robot-r1")["lieu"]

        async def rate():
            raise RuntimeError("le robot ne répond pas")

        coursier._lire_le_monde = rate
        monde.placer("robot-r1", "Salon")
        return lu, etat, place, await coursier.placer_dans(monde), monde._robot("robot-r1")["lieu"], systeme.monde

    lu, etat, place, lu_rate, place_apres, monde_du_robot = asyncio.run(tout())
    attendu = min((l for l in monde_du_robot.lieux if l.id in MondeDesRobots(cartes=cartes.CartesDeLaFlotte())._lieux),
                  key=lambda l: (l.position.x - etat.position["x"]) ** 2 + (l.position.y - etat.position["y"]) ** 2).id
    assert lu["lieu"] == attendu == place and place != "Hall"
    assert lu_rate is None and place_apres == "Salon"  # lecture ratée : on ne touche à rien, on n'invente rien


def test_sans_robot_branche_le_tableau_ne_montre_toujours_aucune_place_pour_r1():
    horloge, app = HorlogeDeDemonstration(), FastAPI()
    brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                    carnet=Carnet(horloge=horloge), code_equipe="code-d-essai")
    ligne = TestClient(app).get("/clinique/tableau-de-flotte").text.split("<td><b>R1</b></td>")[1].split("</tr>")[0]
    assert "pas branché" in ligne and "près de" not in ligne
