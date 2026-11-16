"""La clinique en boîte — J05a, la pause : la main des soignants (avenant jury, J05 ; première moitié).

J05 est coupée en deux. Ici, J05a. « Fini » veut dire :
- un soignant met en pause une chose que font les robots à son étage (rouler dans le couloir, parler, livrer, entrer
  dans une chambre), pour une durée, avec une raison prise dans une courte liste ;
- une action mise en pause est refusée tout de suite par le gardien, et le refus dit qui a mis la pause et jusqu'à quand ;
- la pause finit seule à l'heure dite, ou quand le soignant la lève ;
- le robot qui devait agir dit pourquoi il attend ; chaque pause est dans la boîte noire.
J05b fera : la page « Qui décide », et la recherche des promesses non mesurées dans les textes des écrans.
Tout est sur le FAUX ROBOT. La brique 7 (le gardien) n'est pas modifiée : il lit des règles, comme toujours.
"""
from __future__ import annotations

import pytest

from briques.b01_prise.actions import ActionDemandee
from briques.b07_gardien.regles import charger_regles
from briques.clinique import cartes, cartes_gardien, pauses
from briques.clinique.carnet import Carnet
from briques.clinique.coursier import Coursier, monde_de_la_clinique
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.listes import ListesDeSoin
from briques.clinique.porte import AccesRefuse, JournalDesAcces, PorteDeLecture, charger_badges
from briques.clinique.taches import TableauDesTaches
from commun.systeme import REGLAGES_EXEMPLE, Systeme, charger_reglages
from conftest import lancer

BADGES = charger_badges()
SOIGNANT, ROBOT = BADGES["soignant-etage-2"], BADGES["robot-r1"]


class Banc:
    def __init__(self, dossier) -> None:
        reglages = charger_reglages(REGLAGES_EXEMPLE)
        reglages["cerveau"] = {**reglages["cerveau"], "choix": "regles"}
        self.systeme = Systeme(reglages, dossier_journal=str(dossier), acceleration=20.0, monde=monde_de_la_clinique())
        self.secondes = 0.0  # la montre de l'essai : on l'avance à la main
        self.horloge = HorlogeDeDemonstration(bus=self.systeme.bus, temps=lambda: self.secondes)
        self.carnet = Carnet(horloge=self.horloge)
        self.listes = ListesDeSoin(PorteDeLecture(journal=JournalDesAcces(), jour=self.horloge.jour), self.carnet)
        self.tableau = TableauDesTaches(self.listes.porte, self.carnet, self.listes)
        self.pauses = pauses.Pauses(self.listes.porte, self.carnet, self.horloge, bus=self.systeme.bus)
        self.carte_r1 = cartes_gardien.CarteDuRobotBranche(self.systeme, cartes.CartesDeLaFlotte(), dossier / "regles_r1.yaml")
        self.carte_r1.pauses = self.pauses
        self.coursier = Coursier(self.systeme, self.tableau, self.listes, ROBOT)
        self.coursier.carte_de_role = self.carte_r1

    async def geste(self, nom, **parametres):
        return await self.coursier._geste(ActionDemandee(nom=nom, parametres=parametres), "essai")

    def minutes(self, n):
        self.secondes += n * 60

    def notes(self, quoi):
        return [e.donnees for e in self.systeme.bus.historique if e.type == "note" and e.donnees.get("quoi") == quoi]


def _jouer(tmp_path, scene):
    async def tout():
        banc = Banc(tmp_path)
        await banc.systeme.demarrer()
        try:
            return await scene(banc)
        finally:
            await banc.systeme.arreter()

    return lancer(tout())


# ---------------------------------------------------------------------------------------------- mettre une pause
def test_un_soignant_met_en_pause_une_chose_pour_une_duree_avec_une_raison(tmp_path):
    async def scene(banc):
        return banc.pauses.mettre(SOIGNANT, "rouler", 30, "soin en cours"), banc.pauses.actives()

    pause, actives = _jouer(tmp_path, scene)
    assert pause["chose"] == "rouler" and pause["par"] == "soignant-etage-2" and pause["etage"] == 2
    assert pause["raison"] == "soin en cours" and pause["jusqu_a"] == {"jour": 1, "heure": "09:30"}
    assert pause["dit"] == "en pause : rouler dans le couloir, étage 2 — mise par soignant-etage-2 jusqu'à 9 h 30 (soin en cours)"
    assert [p["numero"] for p in actives] == [pause["numero"]]
    assert set(pauses.CHOSES) == {"rouler", "parler", "livrer", "chambre"}
    assert pauses.RAISONS == ("soin en cours", "repos", "visite", "autre")


def test_seul_un_soignant_met_une_pause_et_seulement_ce_qui_est_prevu(tmp_path):
    async def scene(banc):
        for badge in (ROBOT, BADGES["patient-p01"], BADGES["direction"], BADGES["accueil"]):
            with pytest.raises(AccesRefuse):
                banc.pauses.mettre(badge, "rouler", 10, "repos")
        for chose, minutes, raison in (("voler", 10, "repos"), ("rouler", 0, "repos"), ("rouler", 10, "envie"), ("rouler", 999, "repos")):
            with pytest.raises(pauses.Refus):
                banc.pauses.mettre(SOIGNANT, chose, minutes, raison)
        return banc.pauses.actives()

    assert _jouer(tmp_path, scene) == []


@pytest.mark.parametrize("chose", ["rouler", "parler", "livrer", "chambre"])
def test_chaque_pause_donne_des_regles_que_le_vrai_gardien_accepte(tmp_path, chose):
    monde = monde_de_la_clinique()
    porte = PorteDeLecture(journal=JournalDesAcces())
    p = pauses.Pauses(porte, Carnet(horloge=HorlogeDeDemonstration()), HorlogeDeDemonstration())
    p.mettre(SOIGNANT, chose, 20, "visite")
    fichier = cartes_gardien.ecrire_les_regles(cartes.charger_cartes()["Étage"], monde, tmp_path / "r.yaml", en_plus=p.regles(monde))
    regles = charger_regles(fichier, monde)  # le contrôle du gardien lui-même
    de_la_pause = [r for r in regles.regles if r.id.startswith("pause_")]
    assert de_la_pause and all("soignant-etage-2" in r.phrase and "9 h 20" in r.phrase and r.en_direct is False for r in de_la_pause)


# ---------------------------------------------------------------------------------------------- le gardien applique
def test_une_action_en_pause_est_refusee_tout_de_suite_par_le_gardien_et_le_refus_dit_qui_et_jusqu_a_quand(tmp_path):
    async def scene(banc):
        avant = await banc.geste("se_deplacer", lieu="Réserve")
        banc.pauses.mettre(SOIGNANT, "rouler", 30, "soin en cours")
        refus = await banc.geste("se_deplacer", lieu="Chambre 12")
        decisions = [e.donnees for e in banc.systeme.bus.historique if e.type == "gardien_decision"]
        parties = [e for e in banc.systeme.bus.historique if e.type == "action_demarree"]
        return avant, refus, decisions, len(parties)

    avant, refus, decisions, parties = _jouer(tmp_path, scene)
    assert avant == ""  # sans pause, le robot y va
    assert refus == "en pause : rouler dans le couloir, étage 2 — mise par soignant-etage-2 jusqu'à 9 h 30 (soin en cours)"
    assert [d["verdict"] for d in decisions] == ["oui", "non"]  # c'est le gardien qui a dit non
    assert parties == 1  # rien n'est parti pour l'action en pause


def test_la_pause_finit_seule_a_l_heure_dite(tmp_path):
    async def scene(banc):
        banc.pauses.mettre(SOIGNANT, "rouler", 30, "repos")
        pendant = await banc.geste("se_deplacer", lieu="Réserve")
        banc.minutes(29)
        encore = await banc.geste("se_deplacer", lieu="Réserve")
        banc.minutes(2)  # 9 h 31 : l'heure dite est passée
        apres = await banc.geste("se_deplacer", lieu="Réserve")
        return pendant, encore, apres, banc.pauses.actives(), banc.notes("pause")

    pendant, encore, apres, actives, notes = _jouer(tmp_path, scene)
    assert pendant.startswith("en pause") and encore.startswith("en pause") and apres == "" and actives == []
    assert [n["evenement"] for n in notes] == ["mise", "finie seule"]
    assert notes[1]["heure"] == "jour 1, 09:31" and notes[0]["jusqu_a"] == "jour 1, 09:30"


def test_le_soignant_leve_la_pause_et_le_robot_repart(tmp_path):
    async def scene(banc):
        pause = banc.pauses.mettre(SOIGNANT, "rouler", 30, "visite")
        refus = await banc.geste("se_deplacer", lieu="Réserve")
        with pytest.raises(AccesRefuse):
            banc.pauses.lever(ROBOT, pause["numero"])  # un robot ne lève pas une pause
        banc.pauses.lever(SOIGNANT, pause["numero"])
        return refus, await banc.geste("se_deplacer", lieu="Réserve"), banc.notes("pause")

    refus, apres, notes = _jouer(tmp_path, scene)
    assert refus.startswith("en pause") and apres == ""
    assert [n["evenement"] for n in notes] == ["mise", "levée"] and notes[1]["par"] == "soignant-etage-2"


def test_chaque_chose_en_pause_bloque_ce_qu_elle_dit_et_rien_d_autre(tmp_path):
    async def scene(banc):
        vus = {}
        chambre = banc.pauses.mettre(SOIGNANT, "chambre", 10, "soin en cours")
        vus["chambre"] = (await banc.geste("se_deplacer", lieu="Réserve"), await banc.geste("se_deplacer", lieu="Chambre 12"))
        banc.pauses.lever(SOIGNANT, chambre["numero"])
        livrer = banc.pauses.mettre(SOIGNANT, "livrer", 10, "repos")
        vus["livrer"] = (await banc.geste("se_deplacer", lieu="Réserve"), await banc.geste("saisir", objet="couverture"))
        banc.pauses.lever(SOIGNANT, livrer["numero"])
        banc.pauses.mettre(SOIGNANT, "parler", 10, "repos")
        vus["parler"] = (await banc.geste("se_deplacer", lieu="Poste de soins"), await banc.geste("parler", texte="Bonjour", langue="fr"))
        return vus

    vus = _jouer(tmp_path, scene)
    assert vus["chambre"][0] == "" and vus["chambre"][1].startswith("en pause : entrer dans une chambre")
    assert vus["livrer"][0] == "" and vus["livrer"][1].startswith("en pause : livrer")
    assert vus["parler"][0] == "" and vus["parler"][1].startswith("en pause : parler")


# ---------------------------------------------------------------------------------------------- le robot dit pourquoi il attend
def test_la_course_attend_et_dit_pourquoi_puis_se_fait_apres_la_pause(tmp_path):
    async def scene(banc):
        banc.pauses.mettre(SOIGNANT, "rouler", 15, "soin en cours")
        tache = banc.tableau.demander(SOIGNANT, "p01", "la couverture")["tache"]
        attend = await banc.coursier.faire(tache["id"])
        parties = len([e for e in banc.systeme.bus.historique if e.type == "action_demarree"])
        banc.minutes(16)
        fin = await banc.coursier.faire(tache["id"])
        return attend, parties, fin

    attend, parties, fin = _jouer(tmp_path, scene)
    assert attend["etat"] == "demandée" and parties == 0
    assert attend["en_attente"] == "en pause : rouler dans le couloir, étage 2 — mise par soignant-etage-2 jusqu'à 9 h 15 (soin en cours)"
    assert fin["etat"] == "livrée" and fin.get("en_attente") is None


def test_chaque_pause_est_dans_le_carnet_et_dans_la_boite_noire(tmp_path):
    async def scene(banc):
        pause = banc.pauses.mettre(SOIGNANT, "parler", 20, "repos")
        await banc.pauses.ecrire_dans_la_boite()
        return pause, banc.carnet.lignes(pauses.GENRE), banc.notes("pause")

    pause, lignes, notes = _jouer(tmp_path, scene)
    assert len(lignes) == 1 and lignes[0]["qui"] == "soignant-etage-2" and lignes[0]["valide_par_un_humain"] is True
    assert notes == [{"quoi": "pause", "evenement": "mise", "numero": pause["numero"], "chose": "parler", "etage": 2,
                      "par": "soignant-etage-2", "raison": "repos", "jusqu_a": "jour 1, 09:20", "heure": "jour 1, 09:00"}]


# ---------------------------------------------------------------------------------------------- la tablette du soignant
def test_la_tablette_du_soignant_met_et_leve_une_pause():
    import html

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from briques.clinique.ecrans import brancher_ecrans
    from commun.bus import Bus

    bus = Bus()
    horloge, app = HorlogeDeDemonstration(bus=bus), FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge), code_equipe="")
    client = TestClient(app)
    page = html.unescape(client.get("/clinique/soignant/pauses?badge=soignant-etage-2").text)
    for mot in ("rouler dans le couloir", "parler", "livrer", "entrer dans une chambre", "soin en cours", "repos", "visite",
                "autre", "Mettre en pause", "Aucune pause en cours", "Aucun robot n'est branché"):
        assert mot in page, mot
    assert client.get("/clinique/soignant/pauses?badge=accueil").status_code == 403
    corps = {"badge": "soignant-etage-2", "chose": "rouler", "minutes": 30, "raison": "soin en cours"}
    assert client.post("/api/clinique/pause", json={**corps, "badge": "robot-r1"}).status_code == 403
    assert client.post("/api/clinique/pause", json={**corps, "raison": "envie"}).status_code == 400
    r = client.post("/api/clinique/pause", json=corps)
    assert r.status_code == 200 and r.json()["pause"]["dit"].startswith("en pause : rouler dans le couloir")
    apres = html.unescape(client.get("/clinique/soignant/pauses?badge=soignant-etage-2").text)
    assert "mise par soignant-etage-2 jusqu'à 9 h 30" in apres and "Lever la pause" in apres
    assert client.post("/api/clinique/pause/lever", json={"badge": "soignant-etage-2", "numero": r.json()["pause"]["numero"]}).status_code == 200
    assert clinique.pauses_des_soignants.actives() == []
    notes = [e.donnees["evenement"] for e in bus.historique if e.type == "note" and e.donnees.get("quoi") == "pause"]
    assert notes == ["mise", "levée"]
