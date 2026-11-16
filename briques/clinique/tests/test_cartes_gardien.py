"""La clinique en boîte — T22b, le gardien applique la carte de rôle de R1, sur le faux robot (cahier 5.10 et 6.6).

« Fini » veut dire :
- la carte de R1 devient des règles que le VRAI gardien de l'ossature lit (lieux interdits, vitesse la plus haute) ;
- avec la carte Accueil, le gardien dit non pour quitter le hall ; il dit oui pour aller dans le hall ;
- avec la carte Nuit, le robot va plus lentement, et personne ne peut remonter sa vitesse en direct ;
- changer la carte de R1 change ce que le gardien permet, sans toucher au code ;
- ce que le gardien ne sait pas refuser (une action hors de la carte) est refusé AVANT lui : rien ne part ;
- une course que la carte ne permet pas passe à un humain, et c'est écrit ;
- la page de la flotte montre la carte de R1 et son changement.
Tout est sur le FAUX ROBOT. Aucune brique de l'ossature n'est modifiée : le gardien lit un fichier de règles, comme toujours.
"""
from __future__ import annotations

import pytest

from briques.b01_prise.actions import ActionDemandee
from briques.b07_gardien.regles import charger_regles
from briques.clinique import cartes, cartes_gardien
from briques.clinique.carnet import Carnet
from briques.clinique.coursier import Coursier, monde_de_la_clinique
from briques.clinique.flotte import Flotte, dessiner_flotte
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.listes import ListesDeSoin
from briques.clinique.porte import JournalDesAcces, PorteDeLecture, charger_badges
from briques.clinique.taches import TableauDesTaches
from commun.systeme import REGLAGES_EXEMPLE, Systeme, charger_reglages
from conftest import lancer


class Banc:
    """Un faux robot branché, avec la carte de rôle de R1 donnée au gardien."""

    def __init__(self, dossier, carte: str) -> None:
        reglages = charger_reglages(REGLAGES_EXEMPLE)
        reglages["cerveau"] = {**reglages["cerveau"], "choix": "regles"}
        self.systeme = Systeme(reglages, dossier_journal=str(dossier), acceleration=20.0,
                               monde=monde_de_la_clinique(rez_de_chaussee=True))  # la même salle joue le hall et l'étage
        self.cartes = cartes.CartesDeLaFlotte()
        if carte != "Étage":
            self.cartes.changer("robot-r1", carte, qui="essai")
        self.carte_r1 = cartes_gardien.CarteDuRobotBranche(self.systeme, self.cartes, dossier / "regles_r1.yaml")
        horloge = HorlogeDeDemonstration(bus=self.systeme.bus)
        self.carnet = Carnet(horloge=horloge)
        self.listes = ListesDeSoin(PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), self.carnet)
        self.tableau = TableauDesTaches(self.listes.porte, self.carnet, self.listes)
        self.badges = charger_badges()
        self.coursier = Coursier(self.systeme, self.tableau, self.listes, self.badges["robot-r1"])
        self.coursier.carte_de_role = self.carte_r1

    async def demander(self, nom: str, **parametres):
        verdict, ticket = await self.systeme.gardien.verifier(ActionDemandee(nom=nom, parametres=parametres),
                                                              self.systeme.prise.carte(), conversation="essai", demandeur="cerveau")
        return verdict, ticket

    def evenements(self, genre: str):
        return [e for e in self.systeme.bus.historique if e.type == genre]


def _jouer(tmp_path, carte, scene):
    async def tout():
        banc = Banc(tmp_path, carte)
        await banc.systeme.demarrer()
        try:
            await banc.carte_r1.appliquer(qui="essai")
            return await scene(banc)
        finally:
            await banc.systeme.arreter()

    return lancer(tout())


# ---------------------------------------------------------------------------------------------- la carte devient des règles
@pytest.mark.parametrize("nom", ["Accueil", "Étage", "Thérapie", "Visite", "Nuit"])
def test_chaque_carte_donne_un_fichier_que_le_vrai_gardien_accepte(tmp_path, nom):
    monde, carte = monde_de_la_clinique(rez_de_chaussee=True), cartes.charger_cartes()[nom]
    fichier = cartes_gardien.ecrire_les_regles(carte, monde, tmp_path / "regles.yaml")
    regles = charger_regles(fichier, monde)  # le contrôle du gardien lui-même : une phrase fausse serait refusée
    ids = [r.id for r in regles.regles]
    for garde in ("vitesse_max", "force_max", "distance_personnes", "escalier", "rester_dans_la_halle", "valise"):
        assert garde in ids  # les règles de l'ossature sont toutes là : la carte ne fait qu'en ajouter
    vitesse = regles.regle("carte_vitesse")
    assert vitesse.valeurs["m_s"] == carte.vitesse_max_m_s and vitesse.en_direct is False and nom in vitesse.phrase
    interdits = {r.valeurs["lieu"] for r in regles.regles if r.id.startswith("carte_lieu_")}
    du_plan = {l.id for l in monde.lieux} & set(cartes_gardien.lieux_du_plan())
    assert interdits == du_plan - set(carte.lieux_permis) and interdits
    assert "FICHIER FABRIQUÉ" in fichier.read_text(encoding="utf-8")


def test_le_hall_n_est_dans_le_monde_du_faux_robot_que_si_on_le_demande():
    assert monde_de_la_clinique().lieu("Hall") is None  # le plan du robot de l'étage ne change pas
    monde = monde_de_la_clinique(rez_de_chaussee=True)
    assert monde.lieu("Hall") is not None and monde.lieu("Accueil") is not None and monde.lieu("Chambre 12") is not None


def test_sans_le_hall_dans_son_monde_le_robot_de_l_etage_n_y_va_pas_non_plus(tmp_path):
    """Le monde par défaut (sans rez-de-chaussée) : le gardien ne connaît pas le hall, il dit non."""
    async def tout():
        reglages = charger_reglages(REGLAGES_EXEMPLE)
        reglages["cerveau"] = {**reglages["cerveau"], "choix": "regles"}
        systeme = Systeme(reglages, dossier_journal=str(tmp_path), acceleration=20.0, monde=monde_de_la_clinique())
        carte_r1 = cartes_gardien.CarteDuRobotBranche(systeme, cartes.CartesDeLaFlotte(), tmp_path / "r.yaml")
        await systeme.demarrer()
        try:
            await carte_r1.appliquer()
            verdict, _ = await systeme.gardien.verifier(ActionDemandee(nom="se_deplacer", parametres={"lieu": "Hall"}),
                                                        systeme.prise.carte(), conversation="essai", demandeur="cerveau")
            return verdict
        finally:
            await systeme.arreter()

    verdict = lancer(tout())
    assert verdict.verdict == "non" and "lieu_inconnu" in [r.code for r in verdict.raisons]


# ---------------------------------------------------------------------------------------------- le gardien applique les lieux
def test_carte_accueil_le_gardien_refuse_de_quitter_le_hall(tmp_path):
    async def scene(banc):
        oui, ticket = await banc.demander("se_deplacer", lieu="Hall")
        non, pas_de_ticket = await banc.demander("se_deplacer", lieu="Chambre 12")
        return oui, ticket, non, pas_de_ticket

    oui, ticket, non, pas_de_ticket = _jouer(tmp_path, "Accueil", scene)
    assert oui.verdict == "oui" and ticket is not None
    assert non.verdict == "non" and pas_de_ticket is None
    assert "zone_interdite" in [r.code for r in non.raisons]


def test_carte_etage_c_est_l_inverse(tmp_path):
    async def scene(banc):
        return (await banc.demander("se_deplacer", lieu="Chambre 12"))[0], (await banc.demander("se_deplacer", lieu="Hall"))[0]

    chambre, hall = _jouer(tmp_path, "Étage", scene)
    assert chambre.verdict == "oui" and hall.verdict == "non"


def test_changer_la_carte_de_r1_change_ce_que_le_gardien_permet(tmp_path):
    async def scene(banc):
        avant = (await banc.demander("se_deplacer", lieu="Chambre 12"))[0]
        note = await banc.carte_r1.changer("Étage", qui="soignant-etage-2")
        apres = (await banc.demander("se_deplacer", lieu="Chambre 12"))[0]
        hall = (await banc.demander("se_deplacer", lieu="Hall"))[0]
        notes = [e.donnees for e in banc.evenements("note") if e.donnees.get("quoi") == "carte_changee"]
        return avant, note, apres, hall, notes, len(banc.evenements("regle_changee"))

    avant, note, apres, hall, notes, regles_changees = _jouer(tmp_path, "Accueil", scene)
    assert avant.verdict == "non" and apres.verdict == "oui" and hall.verdict == "non"
    assert note == {"robot": "robot-r1", "avant": "Accueil", "apres": "Étage", "qui": "soignant-etage-2"}
    assert len(notes) == 1 and notes[0]["apres"] == "Étage"  # dans la boîte noire
    assert regles_changees >= 2  # le gardien a noté ses règles changées


# ---------------------------------------------------------------------------------------------- le gardien applique la vitesse
def test_carte_nuit_le_robot_va_plus_lentement_et_on_ne_remonte_pas_sa_vitesse(tmp_path):
    async def scene(banc):
        plafond = banc.systeme.gardien.plafonds()["vitesse"]
        sans = (await banc.demander("se_deplacer", lieu="Réserve"))[0]
        trop = (await banc.demander("se_deplacer", lieu="Réserve", vitesse=0.3))[0]
        await banc.systeme.gardien.changer_regle("vitesse_max", valeurs={"m_s": 0.3}, qui="vote")  # le vote du public
        return plafond, sans, trop, banc.systeme.gardien.plafonds()["vitesse"]

    plafond, sans, trop, apres_le_vote = _jouer(tmp_path, "Nuit", scene)
    assert plafond == 0.15 and apres_le_vote == 0.15
    assert sans.verdict == "oui" and sans.action.parametres["vitesse"] == 0.15
    assert trop.verdict == "non"


# ---------------------------------------------------------------------------------------------- avant le gardien : les actions
def test_une_action_hors_de_la_carte_est_refusee_avant_le_gardien_rien_ne_part(tmp_path):
    async def scene(banc):
        raison = await banc.coursier._geste(ActionDemandee(nom="saisir", parametres={"objet": "couverture"}), "essai")
        refus = [e.donnees for e in banc.evenements("note") if e.donnees.get("quoi") == "refus_de_la_carte"]
        return raison, refus, len(banc.evenements("gardien_decision")), len(banc.evenements("action_demarree"))

    raison, refus, decisions, parties = _jouer(tmp_path, "Accueil", scene)
    assert raison == "la carte de rôle a dit non (la carte Accueil ne permet pas l'action « saisir »)"
    assert len(refus) == 1 and refus[0]["action"] == "saisir"
    assert decisions == 0 and parties == 0


def test_s_arreter_est_toujours_permis_quelle_que_soit_la_carte(tmp_path):
    async def scene(banc):
        return banc.carte_r1.refus(ActionDemandee(nom="arreter")), banc.carte_r1.refus(ActionDemandee(nom="etat"))

    assert _jouer(tmp_path, "Accueil", scene) == (None, None)


# ---------------------------------------------------------------------------------------------- la course
def test_une_course_que_la_carte_ne_permet_pas_passe_a_un_humain(tmp_path):
    async def scene(banc):
        tache = banc.tableau.demander(banc.badges["soignant-etage-2"], "p01", "la couverture")["tache"]
        fin = await banc.coursier.faire(tache["id"])
        return fin, len(banc.evenements("action_demarree"))

    fin, parties = _jouer(tmp_path, "Accueil", scene)
    assert fin["sorte"] == "humain" and "la carte Accueil ne permet pas" in fin["pourquoi_un_humain"]
    assert fin["etat"] != "livrée" and parties == 0


def test_avec_la_carte_etage_la_course_est_livree_sous_le_gardien(tmp_path):
    async def scene(banc):
        tache = banc.tableau.demander(banc.badges["soignant-etage-2"], "p01", "la couverture")["tache"]
        fin = await banc.coursier.faire(tache["id"])
        oui = [e for e in banc.evenements("gardien_decision") if e.donnees["verdict"] == "oui"]
        return fin, len(oui)

    fin, oui = _jouer(tmp_path, "Étage", scene)
    assert fin["etat"] == "livrée" and oui == 4


def test_le_coursier_donne_la_carte_au_gardien_tout_seul_avant_le_premier_geste(tmp_path):
    async def tout():
        banc = Banc(tmp_path, "Accueil")
        await banc.systeme.demarrer()
        try:  # personne n'a appelé « appliquer » : le premier geste le fait
            raison = await banc.coursier._geste(ActionDemandee(nom="se_deplacer", parametres={"lieu": "Chambre 12"}), "essai")
            return raison, banc.systeme.gardien.regles.regle("carte_vitesse") is not None
        finally:
            await banc.systeme.arreter()

    raison, appliquee = lancer(tout())
    assert appliquee and raison.startswith("la carte de rôle a dit non")


def test_si_la_carte_ne_peut_pas_etre_donnee_au_gardien_rien_ne_part(tmp_path):
    async def tout():
        banc = Banc(tmp_path, "Étage")
        banc.carte_r1.fichier = tmp_path / "pas_de_dossier" / "regles.yaml"  # on ne peut pas écrire là
        await banc.systeme.demarrer()
        try:
            raison = await banc.coursier._geste(ActionDemandee(nom="se_deplacer", parametres={"lieu": "Réserve"}), "essai")
            return raison, len(banc.evenements("action_demarree"))
        finally:
            await banc.systeme.arreter()

    raison, parties = lancer(tout())
    assert "la carte de rôle n'a pas pu être donnée au gardien" in raison and parties == 0


# ---------------------------------------------------------------------------------------------- l'écran
def test_la_page_de_la_flotte_montre_la_carte_de_r1_et_son_changement(tmp_path):
    async def scene(banc):
        flotte = Flotte(banc.tableau, banc.carnet, banc.coursier, cartes=banc.cartes, carte_r1=banc.carte_r1)
        avant = dessiner_flotte(flotte)
        await flotte.changer_carte("robot-r1", "Étage", qui="soignant-etage-2")
        await flotte.changer_carte("robot-r4", "Étage", qui="soignant-etage-2")  # un robot simulé : sa carte change aussi
        return avant, dessiner_flotte(flotte), flotte.robots(), (await banc.demander("se_deplacer", lieu="Chambre 12"))[0]

    avant, apres, robots, chambre = _jouer(tmp_path, "Accueil", scene)
    assert robots[0]["carte"] == "Étage" and robots[3]["carte"] == "Étage" and chambre.verdict == "oui"
    # avant : le banc d'essai a déjà donné la carte Accueil à R1, et la page le dit ; le retour à Étage n'y est pas encore
    assert "<td>Accueil</td>" in avant and "R1 : carte Étage → Accueil (par essai)" in avant and "Accueil → Étage" not in avant
    assert "R1 : carte Accueil → Étage" in apres and "R4 : carte Nuit → Étage" in apres
    assert "appliquée par le gardien" in apres and "pas encore appliquée" not in apres


def test_sans_robot_branche_la_page_dit_que_la_carte_n_est_pas_appliquee_par_le_gardien():
    horloge = HorlogeDeDemonstration()
    carnet = Carnet(horloge=horloge)
    listes = ListesDeSoin(PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), carnet)
    page = dessiner_flotte(Flotte(TableauDesTaches(listes.porte, carnet, listes), carnet, None, cartes=cartes.CartesDeLaFlotte()))
    import html

    assert "aucun robot n'est branché" in html.unescape(page) and "leur carte est affichée" in page
