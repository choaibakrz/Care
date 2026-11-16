"""La clinique en boîte — K04, le choix expliqué, et dire avant de faire (avenant 2).

« Fini » veut dire :
- la même demande, jouée dans deux situations (un robot occupé, puis une batterie basse), donne deux choix différents
  et deux phrases différentes ;
- dans la boîte noire, chaque départ du robot est précédé de son annonce ;
- le bouton « Pourquoi ? » montre les robots regardés, le choix, et le feu du gardien ;
- quand aucun robot ne convient, la tâche passe à un humain et la phrase le dit.
Des règles simples, pas de nouveau modèle. Le gardien n'est pas changé : l'annonce est faite par la clinique, juste avant
de lui envoyer l'ordre. Tout est sur le FAUX ROBOT ; R2 à R4 sont SIMULÉS.
"""
from __future__ import annotations

import html

from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique import cartes, repartiteur
from briques.clinique.carnet import Carnet
from briques.clinique.coursier import Coursier, monde_de_la_clinique
from briques.clinique.ecrans import brancher_ecrans
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.listes import ListesDeSoin
from briques.clinique.monde_robots import MondeDesRobots
from briques.clinique.porte import JournalDesAcces, PorteDeLecture, charger_badges
from briques.clinique.taches import TableauDesTaches
from commun.systeme import REGLAGES_EXEMPLE, Systeme, charger_reglages
from conftest import lancer

BADGES = charger_badges()
SOIGNANT = BADGES["soignant-etage-2"]
TACHE = {"id": "t1", "quoi": "couverture", "de": "Réserve", "ou": "Chambre 12"}


def _repartiteur():
    flotte = cartes.CartesDeLaFlotte()
    monde = MondeDesRobots(cartes=flotte)
    monde.placer("robot-r1", "Salon")
    return repartiteur.Repartiteur(monde, flotte), monde


# ---------------------------------------------------------------------------------------------- deux situations, deux choix
def test_la_meme_demande_dans_deux_situations_donne_deux_choix_et_deux_phrases():
    rep, monde = _repartiteur()
    monde.envoyer("robot-r2", "Chambre 11")  # première situation : le robot le plus proche est occupé
    occupe = rep.choisir(TACHE)
    monde._robot("robot-r4")["batterie"] = 16.0  # seconde situation : en plus, la batterie de R4 est basse
    batterie = rep.choisir(TACHE)
    assert occupe["robot"] == "robot-r4" and batterie["robot"] in ("robot-r1", "robot-r3")
    assert occupe["robot"] != batterie["robot"] and occupe["pourquoi"] != batterie["pourquoi"]
    assert "J'envoie R4" in occupe["pourquoi"] and "R2 : occupé" in occupe["pourquoi"]
    assert "R4 : pas assez de batterie" in batterie["pourquoi"] and "R2 : occupé" in batterie["pourquoi"]
    for choix in (occupe, batterie):  # la phrase est fabriquée à partir des faits : libre, le plus proche, la carte
        assert "il est libre" in choix["pourquoi"] and "le plus proche" in choix["pourquoi"] and "sa carte" in choix["pourquoi"]


def test_pour_une_vraie_livraison_un_robot_simule_est_ecarte_et_la_phrase_le_dit():
    rep, monde = _repartiteur()
    monde.placer("robot-r1", "Poste de soins")
    choix = rep.choisir(TACHE, pour_de_vrai=True)
    assert choix["robot"] == "robot-r1"
    ecartes = {r["nom"]: r["raison"] for r in choix["regardes"] if not r["convient"]}
    assert set(ecartes) == {"R2", "R3", "R4"} and all("simulé" in raison for raison in ecartes.values())
    assert "simulé" in choix["pourquoi"] and "robot branché" in choix["pourquoi"]


def test_quand_aucun_robot_ne_convient_la_phrase_le_dit():
    rep, monde = _repartiteur()
    for ident in ("robot-r1", "robot-r2", "robot-r3", "robot-r4"):
        monde.panne(ident, "essai")
    choix = rep.choisir(TACHE)
    assert choix["robot"] is None and "aucun robot ne convient" in choix["pourquoi"] and "passe à un humain" in choix["pourquoi"]


# ---------------------------------------------------------------------------------------------- avec le robot branché
class Banc:
    def __init__(self, dossier) -> None:
        reglages = charger_reglages(REGLAGES_EXEMPLE)
        reglages["cerveau"] = {**reglages["cerveau"], "choix": "regles"}
        self.systeme = Systeme(reglages, dossier_journal=str(dossier), acceleration=20.0, monde=monde_de_la_clinique())
        horloge = HorlogeDeDemonstration(bus=self.systeme.bus)
        self.carnet = Carnet(horloge=horloge)
        self.listes = ListesDeSoin(PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), self.carnet)
        self.tableau = TableauDesTaches(self.listes.porte, self.carnet, self.listes)
        self.coursier = Coursier(self.systeme, self.tableau, self.listes, BADGES["robot-r1"])
        flotte = cartes.CartesDeLaFlotte()
        self.monde = MondeDesRobots(cartes=flotte)
        self.coursier.repartiteur = repartiteur.Repartiteur(self.monde, flotte)


def _jouer(tmp_path, scene):
    async def tout():
        banc = Banc(tmp_path)
        await banc.systeme.demarrer()
        try:
            return await scene(banc)
        finally:
            await banc.systeme.arreter()

    return lancer(tout())


def test_dans_la_boite_noire_chaque_depart_est_precede_de_son_annonce(tmp_path):
    async def scene(banc):
        tache = banc.tableau.demander(SOIGNANT, "p01", "la couverture")["tache"]
        fin = await banc.coursier.faire(tache["id"])
        return fin, list(banc.systeme.bus.historique)

    fin, historique = _jouer(tmp_path, scene)
    assert fin["etat"] == "livrée"
    suite = [("annonce", e.donnees["texte"]) if e.type == "note" and e.donnees.get("quoi") == "annonce"
             else ("départ", e.donnees["action"]["parametres"]["lieu"]) for e in historique
             if (e.type == "note" and e.donnees.get("quoi") == "annonce")
             or (e.type == "action_demarree" and (e.donnees.get("action") or {}).get("nom") == "se_deplacer")]
    assert [genre for genre, _ in suite] == ["annonce", "départ", "annonce", "départ"]  # chaque départ a son annonce, juste avant
    assert suite[0][1] == "Je vais chercher la couverture à la réserve." and suite[1][1] == "Réserve"
    assert suite[2][1] == "J'apporte la couverture en chambre 12." and suite[3][1] == "Chambre 12"
    assert all(len(texte) < 80 for genre, texte in suite if genre == "annonce")  # courte et calme
    assert fin["annonce"] == "J'apporte la couverture en chambre 12."  # le dernier texte, pour l'écran


def test_le_choix_du_repartiteur_est_ecrit_sur_la_tache_et_dans_la_boite_noire(tmp_path):
    async def scene(banc):
        tache = banc.tableau.demander(SOIGNANT, "p01", "la couverture")["tache"]
        fin = await banc.coursier.faire(tache["id"])
        choix = [e.donnees for e in banc.systeme.bus.historique if e.type == "note" and e.donnees.get("quoi") == "choix_du_repartiteur"]
        return fin, choix

    fin, choix = _jouer(tmp_path, scene)
    assert fin["etat"] == "livrée" and "J'envoie R1" in fin["pourquoi_ce_robot"]
    assert {r["nom"] for r in fin["regardes"]} == {"R1", "R2", "R3", "R4"}
    assert len(choix) == 1 and choix[0]["robot_choisi"] == "robot-r1" and choix[0]["tache"] == fin["id"] and len(choix[0]["regardes"]) == 4


def test_si_le_robot_branche_ne_convient_pas_la_tache_passe_a_un_humain_et_rien_ne_part(tmp_path):
    async def scene(banc):
        banc.monde.panne("robot-r1", "essai")
        tache = banc.tableau.demander(SOIGNANT, "p01", "la couverture")["tache"]
        fin = await banc.coursier.faire(tache["id"])
        parties = [e for e in banc.systeme.bus.historique if e.type == "action_demarree"]
        return fin, len(parties)

    fin, parties = _jouer(tmp_path, scene)
    assert fin["sorte"] == "humain" and "aucun robot ne convient" in fin["pourquoi_un_humain"] and parties == 0
    assert "R1 : en panne" in fin["pourquoi_un_humain"]


# ---------------------------------------------------------------------------------------------- le bouton « Pourquoi ? »
def test_le_bouton_pourquoi_montre_les_robots_regardes_le_choix_et_le_feu_du_gardien(tmp_path):
    async def tout():
        reglages = charger_reglages(REGLAGES_EXEMPLE)
        reglages["cerveau"] = {**reglages["cerveau"], "choix": "regles"}
        systeme = Systeme(reglages, dossier_journal=str(tmp_path), acceleration=20.0, monde=monde_de_la_clinique())
        horloge, app = HorlogeDeDemonstration(bus=systeme.bus), FastAPI()
        clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                                   carnet=Carnet(horloge=horloge), systeme=systeme, code_equipe="")
        await systeme.demarrer()
        try:
            tache = clinique.taches.demander(SOIGNANT, "p01", "la couverture")["tache"]
            fin = await clinique.coursier.faire(tache["id"])
        finally:
            await systeme.arreter()
        client = TestClient(app)
        return fin, client.get("/clinique/soignant", params={"badge": SOIGNANT.id}).text, \
            client.get("/clinique/pourquoi", params={"badge": SOIGNANT.id, "tache": tache["id"]}), \
            client.get("/clinique/pourquoi", params={"badge": "patient-p01", "tache": tache["id"]})

    fin, ecran, page, refus = lancer(tout())
    assert fin["etat"] == "livrée"
    assert "Pourquoi ?" in ecran and f"/clinique/pourquoi?badge={SOIGNANT.id}&amp;tache={fin['id']}" in ecran
    texte = html.unescape(page.text)
    assert page.status_code == 200
    for mot in ("Pourquoi ce robot", "J'envoie R1", "R2", "R3", "R4", "simulé", "FAUX ROBOT", "Le feu du gardien", "4 oui, 0 non",
                "Ce que le robot a annoncé", "J'apporte la couverture en chambre 12."):
        assert mot in texte, mot
    assert "Giulia" not in texte  # la page parle des robots, pas de la personne
    assert refus.status_code == 403  # un patient ne lit pas le tableau des tâches
