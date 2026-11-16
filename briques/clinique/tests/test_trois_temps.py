"""La clinique en boîte — K03a, demandé, confirmé, constaté (avenant 2, K03 ; première moitié).

K03 est coupée en deux. Ici, K03a. « Fini » veut dire :
- pour une livraison normale, la boîte noire contient les trois temps dans l'ordre : DEMANDÉ (par quel badge, pour qui),
  CONFIRMÉ (le robot dit qu'il a fini), CONSTATÉ (autre chose que la parole du robot : l'état du monde simulé, SIMULÉ) ;
- un faux robot qui confirme sans que le monde change laisse la tâche à « constaté : pas encore », et l'essai n'entre pas
  dans « réussis et constatés » ;
- les états du cahier ne changent pas : la tâche est toujours « livrée » ; « constaté : oui / pas encore » s'ajoute à côté ;
- une ligne de plus dans les chiffres : « réussis et constatés : tant sur tant » ; les lignes de K02 ne changent pas.
K03b fera : l'âge de l'information sur les écrans (la zone qui se grise), et « qui a donné l'accord ».
"""
from __future__ import annotations

import re

from briques.clinique import aide_humaine, essais, repetition
from briques.clinique.carnet import Carnet
from briques.clinique.coursier import Coursier, monde_de_la_clinique
from briques.clinique.ecrans_listes import dessiner_taches
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.listes import ListesDeSoin
from briques.clinique.porte import JournalDesAcces, PorteDeLecture, charger_badges
from briques.clinique.taches import TableauDesTaches
from commun.systeme import REGLAGES_EXEMPLE, Systeme, charger_reglages
from conftest import lancer

BADGES = charger_badges()


def _jouer(tmp_path, scene, carte=None):
    async def tout():
        reglages = charger_reglages(REGLAGES_EXEMPLE)
        reglages["cerveau"] = {**reglages["cerveau"], "choix": "regles"}
        if carte:
            reglages["robot"] = {**reglages["robot"], "carte": carte}
        systeme = Systeme(reglages, dossier_journal=str(tmp_path), acceleration=20.0, monde=monde_de_la_clinique())
        horloge = HorlogeDeDemonstration(bus=systeme.bus)
        carnet = Carnet(horloge=horloge)
        listes = ListesDeSoin(PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), carnet)
        tableau = TableauDesTaches(listes.porte, carnet, listes)
        coursier = Coursier(systeme, tableau, listes, BADGES["robot-r1"], attente_humain_s=2.0)
        await systeme.demarrer()
        try:
            return await scene(systeme, tableau, coursier)
        finally:
            await systeme.arreter()

    return lancer(tout())


def _temps(systeme, tache):
    return [e for e in systeme.bus.historique if e.type == "note" and e.donnees.get("quoi") == "temps_d_un_geste"
            and e.donnees.get("tache") == tache]


# ---------------------------------------------------------------------------------------------- une livraison normale
def test_pour_une_livraison_normale_la_boite_noire_a_les_trois_temps_dans_l_ordre(tmp_path):
    async def scene(systeme, tableau, coursier):
        tache = tableau.demander(BADGES["soignant-etage-2"], "p01", "la couverture")["tache"]
        fin = await coursier.faire(tache["id"])
        return fin, _temps(systeme, tache["id"])

    fin, temps = _jouer(tmp_path, scene)
    assert fin["etat"] == "livrée" and fin["constate"] == "oui"  # l'état du cahier ne change pas ; le constat est à côté
    assert [t.donnees["temps"] for t in temps] == ["DEMANDÉ", "CONFIRMÉ", "CONSTATÉ"]
    assert [str(t.heure) for t in temps] == sorted(str(t.heure) for t in temps) and all(t.heure for t in temps)
    demande, confirme, constate = (t.donnees for t in temps)
    assert demande["par"] == "soignant-etage-2" and demande["pour"] == "p01"  # par qui (le badge), et pour qui
    assert confirme["par"] == "robot-r1" and "le robot dit qu'il a fini" in confirme["comment"]
    assert constate["etiquette"] == "SIMULÉ" and "monde simulé" in constate["comment"] and "couverture" in constate["comment"]
    assert "Giulia" not in str([t.donnees for t in temps])  # des numéros, pas de nom


def test_un_robot_qui_confirme_sans_que_le_monde_change_reste_a_constate_pas_encore(tmp_path, monkeypatch):
    async def scene(systeme, tableau, coursier):
        vrai_etat = systeme.prise.etat

        async def etat_ou_rien_n_a_bouge():
            etat = await vrai_etat()
            objets = dict(etat.extra["objets"])
            objets["couverture"] = [3.4, 4.5]  # la couverture est toujours à la réserve : le monde n'a pas changé
            return etat.model_copy(update={"extra": {**etat.extra, "objets": objets}})

        tache = tableau.demander(BADGES["soignant-etage-2"], "p01", "la couverture")["tache"]
        monkeypatch.setattr(coursier, "_lire_le_monde", etat_ou_rien_n_a_bouge)
        with aide_humaine.compter() as compte:
            fin = await coursier.faire(tache["id"])
        return fin, _temps(systeme, tache["id"]), compte

    fin, temps, compte = _jouer(tmp_path, scene)
    assert fin["etat"] == "livrée" and fin["constate"] == "pas encore"  # le robot a confirmé ; rien d'autre ne le montre
    assert [t.donnees["temps"] for t in temps] == ["DEMANDÉ", "CONFIRMÉ"]  # pas de CONSTATÉ dans la boîte noire
    assert "toujours" in fin["constat"] or "pas" in fin["constat"]
    assert compte.livraisons == 1 and compte.constatees == 0


def test_une_course_ratee_n_a_ni_confirme_ni_constate(tmp_path):
    async def scene(systeme, tableau, coursier):
        tache = tableau.demander(BADGES["soignant-etage-2"], "p01", "la couverture")["tache"]
        await systeme.prise.arret_urgence("essai")  # le robot est à l'arrêt : la course ne peut pas se faire
        fin = await coursier.faire(tache["id"])
        return fin, _temps(systeme, tache["id"])

    fin, temps = _jouer(tmp_path, scene)
    assert fin["etat"] != "livrée" and "constate" not in fin
    assert [t.donnees["temps"] for t in temps] in (["DEMANDÉ"], [])


def test_sur_le_plateau_c_est_une_personne_qui_constate(tmp_path):
    import asyncio

    async def scene(systeme, tableau, coursier):
        tache = tableau.demander(BADGES["soignant-etage-2"], "p01", "la couverture")["tache"]
        course = asyncio.ensure_future(coursier.faire(tache["id"]))
        for _ in range(2):  # un humain pose l'objet, puis un humain le prend
            for _ in range(400):
                await asyncio.sleep(0.01)
                if tableau.tache(tache["id"]).get("attend"):
                    break
            assert coursier.confirmer(tache["id"], BADGES["soignant-etage-2"])
        return await course, _temps(systeme, tache["id"])

    fin, temps = _jouer(tmp_path, scene, carte="plateau")
    assert fin["etat"] == "livrée" and fin["constate"] == "oui"
    assert [t.donnees["temps"] for t in temps] == ["DEMANDÉ", "CONFIRMÉ", "CONSTATÉ"]
    assert "une personne" in temps[2].donnees["comment"] and temps[2].donnees["par"] == "soignant-etage-2"
    assert temps[2].donnees["etiquette"] != "SIMULÉ"  # ce constat-là vient d'une personne, pas du monde simulé


# ---------------------------------------------------------------------------------------------- à l'écran
def test_constate_s_affiche_a_cote_de_l_etat():
    tache = {"id": "t1", "quoi": "couverture", "ou": "Chambre 12", "nom_du_patient": "Madame Exemple", "sorte": "robot",
             "etat": "livrée", "etiquette": "FAUX ROBOT", "constate": "oui"}
    assert "<b>livrée</b>" in dessiner_taches([tache]) and "constaté : oui" in dessiner_taches([tache])
    assert "constaté : pas encore" in dessiner_taches([{**tache, "constate": "pas encore"}])
    assert "constaté" not in dessiner_taches([{k: v for k, v in tache.items() if k != "constate"} | {"etat": "en route"}])


# ---------------------------------------------------------------------------------------------- le chiffre
def _faux_controles():
    return {n: (lambda: repetition.Resultat(True, "SIMULÉ", "essai")) for n in range(1, 15)}


def _essais(controles, tmp_path, liste=None):
    lignes: list[str] = []
    bilan = essais.jouer_les_essais(liste or essais.charger(), controles, ecrire=lignes.append, dossier=tmp_path,
                                    compteur_reel=essais.CompteurReel(tmp_path / "reels.jsonl"))
    return bilan, lignes


def test_reussis_et_constates_une_ligne_de_plus_les_lignes_de_k02_ne_changent_pas(tmp_path):
    controles = _faux_controles()
    appels = {"n": 0}

    def une_livraison():
        appels["n"] += 1
        aide_humaine.signaler_constat(appels["n"] != 4)  # à l'essai 4, le robot confirme mais rien ne le montre
        return repetition.Resultat(True, "FAUX ROBOT", "essai")

    controles[8] = une_livraison
    bilan, lignes = _essais(controles, tmp_path)
    ligne = next(l for l in lignes if "réussis et constatés" in l)
    assert "réussis et constatés : 19 sur 20" in ligne and "[FAUX ROBOT" in ligne and re.search(r"\d\d\.\d\d\.\d{4}", ligne)
    assert "livraisons constatées : 19 sur 20" in ligne and "SIMULÉ" in ligne
    assert bilan["fiche"]["reussis_et_constates"] == 19 and bilan["fiche"]["par_essai"][4]["constatees"] == 0
    assert len([l for l in lignes if l.startswith("CHIFFRE ")]) == 3  # les trois lignes de K02 sont toujours trois
    assert "réussis du premier coup : 20 sur 20" in next(l for l in lignes if l.startswith("CHIFFRE 1"))


def test_un_essai_rate_n_est_pas_reussi_et_constate(tmp_path):
    controles = _faux_controles()
    appels = {"n": 0}

    def rate_une_fois():
        appels["n"] += 1
        aide_humaine.signaler_constat(True)
        return repetition.Resultat(appels["n"] != 2, "FAUX ROBOT", "essai")

    controles[8] = rate_une_fois
    bilan, lignes = _essais(controles, tmp_path, liste=essais.charger()[:5])
    assert "réussis et constatés : 4 sur 5" in next(l for l in lignes if "réussis et constatés" in l)


def test_avec_la_vraie_piece_de_la_course_la_livraison_est_constatee(tmp_path):
    liste = [e for e in essais.charger() if e["numero"] in (2, 4)]  # 2 : un objet livré ; 4 : objet absent, pas de livraison
    controles = _faux_controles()
    controles[8] = repetition.CONTROLES[8]
    bilan, lignes = _essais(controles, tmp_path, liste=liste)
    par_essai = bilan["fiche"]["par_essai"]
    assert par_essai[2]["livraisons"] == 1 and par_essai[2]["constatees"] == 1
    assert par_essai[4]["livraisons"] == 0
    assert "livraisons constatées : 1 sur 1" in next(l for l in lignes if "réussis et constatés" in l)
