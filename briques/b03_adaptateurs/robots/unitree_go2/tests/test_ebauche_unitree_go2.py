"""H08a — L'ébauche de branchement d'un Unitree Go2 programmable (demande de Hiba, 12.11.2026).

PRÉPARÉE SANS LE ROBOT — non testé sur vrai robot. Ces essais tournent avec une DOUBLURE à la place du robot
(doublure.py) : un faux client qui porte les mêmes noms de fonctions que le kit public d'Unitree, lus en ligne.
« Fini » veut dire :
- l'ébauche sait : se lever, avancer à une vitesse donnée, s'arrêter, dire son état — et rien d'autre ;
- la liaison n'appelle que des fonctions lues dans la documentation publique ; jamais un saut, un salto, une danse ;
- se connecter et réarmer ne font jamais bouger le robot ; le robot ne se lève que sur un ordre passé par la prise ;
- la carte garde les limites de prudence déjà acceptées, et aucun chiffre du fabricant n'est inventé ;
- la marque « PRÉPARÉE SANS LE ROBOT — non testé sur vrai robot » est sur chaque fichier ;
- le test de conformité réussit avec la doublure, et dit « testé sur faux robot » ;
- sans le kit du fabricant (jamais installé ici), le vrai branchement dit pourquoi il ne peut pas se faire.
"""
import asyncio
import re
from pathlib import Path

import pytest
import yaml

from briques.b01_prise.adaptateur import ActionImpossible
from briques.b01_prise.carte import CarteIdentite
from briques.b03_adaptateurs import conformite_deux_temps as conformite
from briques.b03_adaptateurs.registre import charger_robot

ICI = Path(__file__).resolve().parents[1]
ROBOT = charger_robot(ICI.name, ICI.parent)
MARQUE = "PRÉPARÉE SANS LE ROBOT — non testé sur vrai robot"
LUS_DANS_LA_DOC = {"StandUp", "Move", "StopMove", "SetTimeout", "Init"}  # sport_client.py du kit public, lu le 12.11.2026
MOUVEMENTS = {"StandUp", "Move", "StandDown", "Damp", "BalanceStand", "RecoveryStand", "Sit", "RiseSit", "Hello"}


def _liaison():
    from briques.b03_adaptateurs.robots.unitree_go2.doublure import DoublureUnitree
    from briques.b03_adaptateurs.robots.unitree_go2.liaison import LiaisonUnitreeGo2

    doublure = DoublureUnitree(acceleration=5)
    return LiaisonUnitreeGo2(doublure), doublure


def test_la_marque_est_sur_chaque_fichier_de_l_ebauche():
    for nom in ("liaison.py", "carte.yaml", "doublure.py", "adaptateur.py"):
        assert MARQUE in (ICI / nom).read_text(encoding="utf-8"), nom


def test_se_lever_avancer_s_arreter_dire_son_etat_par_les_fonctions_lues_dans_la_doc():
    liaison, doublure = _liaison()
    liaison.ouvrir()
    liaison.geste("se_lever", 1.0)
    liaison.vitesse(0.1, 0.0, 0.0)
    liaison.arreter_mouvement()
    etat = liaison.lire_etat()
    appels = [nom for nom, _ in doublure.appels_du_kit]
    assert appels == ["StandUp", "Move", "StopMove"]
    assert doublure.appels_du_kit[1] == ("Move", (0.1, 0.0, 0.0))
    assert set(appels) <= LUS_DANS_LA_DOC
    assert {"x", "y", "en_mouvement", "occupe", "erreurs", "batterie_pct", "cap"} <= set(etat)
    assert etat["batterie_pct"] is None and etat["cap"] is None  # pas lus dans la doc : à vérifier samedi, pas inventés


def test_se_connecter_lire_l_etat_et_rearmer_ne_font_jamais_bouger_le_robot():
    liaison, doublure = _liaison()
    liaison.ouvrir()
    liaison.signe_de_vie()
    liaison.lire_etat()
    liaison.rearmer()
    liaison.fermer()
    assert not {nom for nom, _ in doublure.appels_du_kit} & MOUVEMENTS
    assert doublure.debout is False  # il ne s'est pas levé tout seul


def test_l_arret_d_urgence_logiciel_appelle_l_arret_de_marche_et_un_arret_sans_code_n_est_pas_confirme():
    liaison, doublure = _liaison()
    liaison.ouvrir()
    liaison.arret_urgence()
    assert [nom for nom, _ in doublure.appels_du_kit] == ["StopMove"]
    doublure.code_de_l_arret = None
    with pytest.raises(ActionImpossible, match="non confirmé"):
        liaison.arret_urgence()


def test_un_geste_qui_n_est_pas_se_lever_est_refuse_et_rien_ne_part():
    liaison, doublure = _liaison()
    liaison.ouvrir()
    for nom in ("FrontFlip", "Dance1", "saluer", "se_coucher"):
        with pytest.raises(ActionImpossible):
            liaison.geste(nom, 1.0)
    assert doublure.appels_du_kit == []


def test_la_liaison_ne_nomme_aucun_saut_salto_ni_danse_hors_des_commentaires():
    code = "\n".join(l.split("#")[0] for l in (ICI / "liaison.py").read_text(encoding="utf-8").splitlines())
    code = re.sub(r'""".*?"""', "", code, flags=re.S)
    for interdit in ("Flip", "Jump", "Pounce", "HandStand", "Dance", "FreeBound", "TrotRun", "Damp(", "ZeroTorque"):
        assert interdit not in code, interdit


def test_le_robot_refuse_un_ordre_le_code_est_dit():
    liaison, doublure = _liaison()
    liaison.ouvrir()
    doublure.code_suivant = 3104
    with pytest.raises(ActionImpossible, match="3104"):
        liaison.vitesse(0.1, 0.0, 0.0)


def test_un_robot_muet_la_liaison_le_dit():
    liaison, doublure = _liaison()
    liaison.ouvrir()
    doublure.muet = True
    with pytest.raises((ConnectionError, TimeoutError)):
        liaison.signe_de_vie()


def test_la_carte_garde_les_limites_de_prudence_et_n_invente_aucun_chiffre_du_fabricant():
    texte = (ICI / "carte.yaml").read_text(encoding="utf-8")
    carte = CarteIdentite.charger(ICI / "carte.yaml")
    prudence = yaml.safe_load((ICI.parents[2] / "b02_faux_robot" / "cartes" / "unitree_go2.yaml").read_text(encoding="utf-8"))
    assert sorted(carte.capacites) == ["arreter", "etat", "rejouer_geste", "se_deplacer"]
    assert carte.limites.vitesse_max_m_s == prudence["limites"]["vitesse_max_m_s"] == 0.3
    assert carte.limites.portee_max_m == 0 and carte.limites.force_max_n == 0  # pas de bras : il ne saisit rien
    assert list(carte.gestes) == ["se_lever"]
    assert texte.count("à vérifier samedi") >= 8 and "choix de prudence" in texte


def test_sans_le_kit_du_fabricant_le_vrai_branchement_dit_pourquoi():
    import importlib.util

    if importlib.util.find_spec("unitree_sdk2py") is not None:
        pytest.skip("le kit du fabricant est installé sur cet ordinateur : cet essai est pour un ordinateur sans le kit")
    from briques.b03_adaptateurs.robots.unitree_go2.liaison import LiaisonUnitreeGo2

    with pytest.raises(Exception, match="unitree_sdk2py"):
        LiaisonUnitreeGo2.creer_kit()


def test_la_conformite_reussit_avec_la_doublure_et_dit_faux_robot():
    from briques.b03_adaptateurs.robots.unitree_go2.doublure import DoublureUnitree

    adaptateur = ROBOT.fabriquer(vrai=False, acceleration=5)
    assert type(adaptateur._liaison.kit) is DoublureUnitree and adaptateur._liaison.vrai_robot is False
    for temps in (conformite.sans_mouvement, conformite.complet):
        rapport = asyncio.run(temps(lambda: ROBOT.fabriquer(vrai=False, acceleration=5), vrai_attendu=False))
        assert rapport.reussi, rapport.texte()
        assert rapport.mention == "testé sur faux robot"
