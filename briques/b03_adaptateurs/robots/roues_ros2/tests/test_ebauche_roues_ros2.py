"""H08b — L'ébauche de branchement d'un robot à roues qui parle ROS 2 (demande de Hiba, 12.11.2026).

PRÉPARÉE SANS LE ROBOT — non testé sur vrai robot. Ces essais tournent avec une DOUBLURE à la place du robot : le faux
ROS 2 du projet (briques/b03_adaptateurs/chemins/ros2/faux_ros2.py). ROS 2 n'est pas installé sur nos ordinateurs.
« Fini » veut dire :
- l'ébauche sait : recevoir une vitesse, s'arrêter, dire sa position — et rien d'autre ;
- elle ne publie que sur le canal de vitesse, un message de vitesse standard ; elle n'écrit sur aucun canal inventé ;
- se connecter, lire l'état et réarmer ne publient rien : le robot ne bouge pas ;
- la carte garde des limites de prudence, et aucun chiffre de fabricant n'est inventé ;
- la marque « PRÉPARÉE SANS LE ROBOT — non testé sur vrai robot » est sur chaque fichier ;
- le test de conformité réussit avec la doublure, et dit « testé sur faux robot » ;
- sans ROS 2 (jamais installé ici), le vrai branchement dit pourquoi il ne peut pas se faire.
"""
import asyncio
import math
import re
import time
from pathlib import Path

import pytest

from briques.b01_prise.carte import CarteIdentite
from briques.b03_adaptateurs import conformite_deux_temps as conformite
from briques.b03_adaptateurs.chemins.ros2.faux_ros2 import MESSAGES, FauxRclpy
from briques.b03_adaptateurs.registre import charger_robot

ICI = Path(__file__).resolve().parents[1]
ROBOT = charger_robot(ICI.name, ICI.parent)
MARQUE = "PRÉPARÉE SANS LE ROBOT — non testé sur vrai robot"


def _liaison():
    from briques.b03_adaptateurs.robots.roues_ros2.liaison import LiaisonRouesRos2

    doublure = FauxRclpy(acceleration=5)
    return LiaisonRouesRos2(doublure, MESSAGES), doublure


def test_la_marque_est_sur_chaque_fichier_de_l_ebauche():
    for nom in ("liaison.py", "carte.yaml", "adaptateur.py"):
        assert MARQUE in (ICI / nom).read_text(encoding="utf-8"), nom


def test_recevoir_une_vitesse_s_arreter_dire_sa_position():
    liaison, doublure = _liaison()
    liaison.ouvrir()
    liaison.tic()
    depart = liaison.lire_etat()
    liaison.vitesse(0.1, 0.0, 0.0)
    assert doublure.robot.recus == {"/cmd_vel": 1} and doublure.robot.vitesse_max_vue == pytest.approx(0.1)
    time.sleep(0.15)
    en_route = liaison.lire_etat()
    liaison.arreter_mouvement()
    assert doublure.robot.recus == {"/cmd_vel": 2}
    arrete = liaison.lire_etat()
    assert en_route["en_mouvement"] is True and arrete["en_mouvement"] is False
    assert arrete["x"] > depart["x"] and arrete["y"] == pytest.approx(depart["y"], abs=0.01)
    assert {"x", "y", "cap", "en_mouvement", "batterie_pct"} <= set(arrete)
    assert arrete["batterie_pct"] is None  # aucun canal de batterie n'est garanti : à vérifier samedi, pas inventé


def test_se_connecter_lire_l_etat_et_rearmer_ne_publient_rien():
    liaison, doublure = _liaison()
    liaison.ouvrir()
    liaison.signe_de_vie()
    liaison.lire_etat()
    liaison.rearmer()
    liaison.fermer()
    assert sum(doublure.robot.recus.values()) == 0


def test_l_arret_d_urgence_logiciel_publie_une_vitesse_nulle_et_rien_sur_un_canal_invente():
    liaison, doublure = _liaison()
    liaison.ouvrir()
    liaison.vitesse(0.1, 0.0, 0.0)
    liaison.arret_urgence()
    assert set(doublure.robot.recus) == {"/cmd_vel"}
    assert liaison.lire_etat()["en_mouvement"] is False


def test_la_liaison_n_ecrit_sur_aucun_canal_invente_et_ne_branche_que_trois_actions():
    from briques.b03_adaptateurs.robots.roues_ros2.liaison import SUJETS, LiaisonRouesRos2

    assert SUJETS == {"vitesse": "/cmd_vel", "odometrie": "/odom"}
    assert LiaisonRouesRos2.branchees == frozenset({"arreter", "etat", "se_deplacer"})
    code = "\n".join(l.split("#")[0] for l in (ICI / "liaison.py").read_text(encoding="utf-8").splitlines())
    code = re.sub(r'""".*?"""', "", code, flags=re.S)
    assert "/leukerbad" not in code and "getattr" not in code


def test_un_robot_muet_la_liaison_le_dit():
    liaison, doublure = _liaison()
    liaison.ouvrir()
    liaison.signe_de_vie()
    doublure.robot.pannes.add("muet")
    time.sleep(1.1)
    with pytest.raises(ConnectionError):
        liaison.signe_de_vie()


def test_le_cap_vient_de_l_orientation_du_message_de_position():
    liaison, doublure = _liaison()
    doublure.robot.cap = 90.0
    liaison.ouvrir()
    assert liaison.lire_etat()["cap"] == pytest.approx(90.0, abs=0.5) and math.isfinite(liaison.lire_etat()["x"])


def test_la_carte_garde_des_limites_de_prudence_et_n_invente_aucun_chiffre_de_fabricant():
    texte = (ICI / "carte.yaml").read_text(encoding="utf-8")
    carte = CarteIdentite.charger(ICI / "carte.yaml")
    assert sorted(carte.capacites) == ["arreter", "etat", "se_deplacer"]
    assert carte.limites.vitesse_max_m_s == 0.3 and carte.limites.portee_max_m == 0 and carte.limites.force_max_n == 0
    assert list(carte.gestes) == []
    assert texte.count("à vérifier samedi") >= 8 and "choix de prudence" in texte


def test_sans_ros_2_le_vrai_branchement_dit_pourquoi():
    import importlib.util

    if importlib.util.find_spec("rclpy") is not None:
        pytest.skip("ROS 2 est installé sur cet ordinateur : cet essai est pour un ordinateur sans ROS 2")
    from briques.b03_adaptateurs.robots.roues_ros2.liaison import creer_ros2

    with pytest.raises(Exception, match="ROS 2"):
        creer_ros2()


def test_la_conformite_reussit_avec_la_doublure_et_dit_faux_robot():
    from briques.b03_adaptateurs.robots.roues_ros2.liaison import LiaisonRouesRos2

    adaptateur = ROBOT.fabriquer(vrai=False, acceleration=5)
    assert type(adaptateur._liaison) is LiaisonRouesRos2 and adaptateur._liaison.vrai_robot is False
    for temps in (conformite.sans_mouvement, conformite.complet):
        rapport = asyncio.run(temps(lambda: ROBOT.fabriquer(vrai=False, acceleration=5), vrai_attendu=False))
        assert rapport.reussi, rapport.texte()
        assert rapport.mention == "testé sur faux robot"
