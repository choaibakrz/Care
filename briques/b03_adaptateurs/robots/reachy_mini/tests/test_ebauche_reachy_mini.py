"""L'ébauche de branchement d'un Reachy Mini (demande de Hiba, 14.11.2026).

NON TESTÉ SUR VRAI ROBOT. Ces essais tournent avec une DOUBLURE à la place du robot (doublure.py) : un faux programme
de fond, qui répond aux mêmes adresses web que celui du fabricant, lues en ligne le 14.11.2026. Le petit client web,
lui, est essayé contre un petit serveur d'essai lancé sur cet ordinateur. Rien de tout cela ne dit ce que fait le vrai robot.
« Fini » veut dire :
- se connecter, donner un signe de vie et lire l'état ne font que des LECTURES (GET) : rien n'est envoyé au robot ;
- un programme de fond arrêté, en erreur, pas prêt ou injoignable est dit, avec sa raison, jamais caché ;
- dans le doute, le robot est dit EN MOUVEMENT (un mouvement en cours, une tête qui bouge, un mode inconnu) ;
- l'arrêt normal arrête chaque mouvement de la liste, même si l'un d'eux rate, puis VÉRIFIE que la tête ne bouge plus ;
- l'arrêt d'urgence proposé coupe les moteurs D'ABORD, puis annule les mouvements ; la coupure part même si tout le reste rate ;
- réarmer n'envoie rien au robot ; montrer, la voix, l'écoute, saisir et poser disent « À BRANCHER » ;
- (15.11.2026) regarder tourne la tête LENTEMENT vers une direction du fichier directions.yaml, et rien d'autre ;
  « oui » et « non » sont de petits mouvements envoyés UN PAR UN, le suivant seulement quand la tête est ARRIVÉE ;
  une cible inconnue ou hors limites, des moteurs coupés, une tête pas en place, un robot occupé : refus, rien ne part ;
  un ordre perdu par le programme de fond est dit perdu ; un mouvement qui n'arrive pas à sa cible est dit raté ;
  un arrêt passe toujours devant (même pendant les vérifications ou pendant l'envoi) et vide ce qui restait ;
  un geste interrompu en route est dit raté à tous ceux qui lisent l'état, et l'adaptateur le compte « échouée » ;
  ces essais se font sur la doublure, dans UN seul fil : l'arrêt « venu d'un autre fil » y est imité, pas réel ;
- (15.11.2026, demande de Hiba : tout par notre cerveau) « lever_la_tete » est NOTRE réveil : il allume les moteurs puis
  monte la tête en 6 secondes au moins, et c'est le seul ordre permis quand la tête est couchée ; « coucher_la_tete »
  la repose aussi lentement ; un arrêt qui passe pendant qu'on rallume fait recouper les moteurs ; le réveil et le
  coucher du fabricant (rapides) ne sont jamais envoyés ;
- le client web n'envoie que sept demandes permises, sur cet ordinateur seulement, sans relais ni redirection ;
- la carte promet les deux actions obligatoires, regarder et rejouer_geste (quatre gestes), et garde 0 partout ;
- le test de conformité réussit avec la doublure et la VRAIE liaison de ce dossier, et dit « testé sur faux robot ».
"""
import asyncio
import http.server
import json
import math
import re
import threading
import time
from pathlib import Path

import pytest

from briques.b01_prise.adaptateur import ActionImpossible
from briques.b01_prise.carte import CarteIdentite
from briques.b03_adaptateurs import conformite_deux_temps as conformite
from briques.b03_adaptateurs.modele_vide.liaison import ABrancher
from briques.b03_adaptateurs.registre import charger_robot
from briques.b03_adaptateurs.robots.reachy_mini import liaison as module_liaison
from briques.b03_adaptateurs.robots.reachy_mini.doublure import DoublureReachyMini
from briques.b03_adaptateurs.robots.reachy_mini.liaison import PERMIS, ClientDuProgrammeDeFond, LiaisonReachyMini

ICI = Path(__file__).resolve().parents[1]
ROBOT = charger_robot(ICI.name, ICI.parent)
MARQUE = "NON TESTÉ SUR VRAI ROBOT"
LECTURES = {"/api/daemon/status", "/api/move/running", "/api/state/full"}
ARRET, COUPURE, TETE = "/api/move/stop", "/api/motors/set_mode/disabled", "/api/move/goto"
ALLUMER = "/api/motors/set_mode/enabled"


def _liaison():
    doublure = DoublureReachyMini(acceleration=5)
    return LiaisonReachyMini(doublure), doublure


def _envoyes(doublure) -> list[str]:
    return [adresse for verbe, adresse, _ in doublure.appels_du_kit if verbe == "POST"]


# ================================================================ la liaison, avec la doublure
def test_la_marque_est_sur_les_fichiers_de_l_ebauche():
    for nom in ("liaison.py", "carte.yaml", "doublure.py", "adaptateur.py", "__init__.py", "tests/test_ebauche_reachy_mini.py"):
        assert MARQUE in (ICI / nom).read_text(encoding="utf-8"), nom
    assert "Non testé sur vrai robot" in (ICI.parents[1] / "fiches" / "reachy_mini.md").read_text(encoding="utf-8")


def test_se_connecter_et_lire_l_etat_ne_font_que_des_lectures():
    liaison, doublure = _liaison()
    liaison.ouvrir()
    liaison.signe_de_vie()
    etat = liaison.lire_etat()
    liaison.fermer()
    assert _envoyes(doublure) == []  # aucun POST : rien n'est envoyé au robot
    assert {adresse for _, adresse, _ in doublure.appels_du_kit} == LECTURES
    assert {"batterie_pct", "x", "y", "cap", "en_mouvement", "occupe", "objet_tenu", "erreurs", "arret_urgence"} <= set(etat)
    assert etat["batterie_pct"] is None and etat["x"] is None and etat["cap"] is None  # rien d'inventé
    assert etat["en_mouvement"] is False and etat["occupe"] is False and etat["erreurs"] == []


def test_lire_l_etat_fait_au_plus_quatre_lectures_puis_trois():
    """La règle du projet : rendre la main vite. Le client coupe chaque lecture à 0,2 s : 4 lectures restent sous 1 s."""
    liaison, doublure = _liaison()
    liaison.lire_etat()
    assert len(doublure.appels_du_kit) == 4  # état, liste, et deux lectures de position (la première fois)
    doublure.appels_du_kit.clear()
    liaison.lire_etat()
    assert len(doublure.appels_du_kit) == 3  # ensuite, la lecture gardée en mémoire sert de point de comparaison
    assert 4 * module_liaison.DELAI_LECTURE_S + module_liaison.ENTRE_DEUX_LECTURES_S < 1.0


def test_la_doublure_est_reconnue_comme_un_faux_robot_par_sa_classe():
    liaison, _ = _liaison()
    assert liaison.vrai_robot is False and liaison.repere_du_monde is False
    assert LiaisonReachyMini(ClientDuProgrammeDeFond()).vrai_robot is True  # le client web est toujours pris pour le vrai


@pytest.mark.parametrize("etat_du_fond", ["not_initialized", "starting", "stopping", "stopped", "error", None, 12])
def test_un_programme_de_fond_qui_n_est_pas_en_marche_est_dit(etat_du_fond):
    liaison, doublure = _liaison()
    doublure.etat_du_fond = etat_du_fond
    for appel in (liaison.ouvrir, liaison.signe_de_vie, liaison.lire_etat):
        with pytest.raises(TimeoutError, match="n'est pas en marche"):
            appel()


def test_la_raison_de_la_panne_est_dite():
    """Lu : quand le programme de fond a une erreur, son état vaut « error » et il donne la raison."""
    liaison, doublure = _liaison()
    doublure.etat_du_fond, doublure.erreur_du_fond = "error", "no motors found on the serial port"
    with pytest.raises(TimeoutError, match="no motors found on the serial port"):
        liaison.signe_de_vie()
    doublure.etat_du_fond, doublure.erreur_du_fond = "running", None
    doublure.erreur_du_materiel = "motor 3 overload"
    assert liaison.lire_etat()["erreurs"] == ["le Reachy Mini dit : motor 3 overload"]


def test_un_robot_pas_pret_ou_injoignable_est_dit():
    liaison, doublure = _liaison()
    doublure.pret = False
    with pytest.raises(TimeoutError, match="n'est pas prêt"):
        liaison.signe_de_vie()
    doublure.pret = True
    doublure.provoquer_panne("coupure")
    for appel in (liaison.ouvrir, liaison.signe_de_vie, liaison.lire_etat):
        with pytest.raises(ConnectionError):
            appel()


def test_des_positions_illisibles_sont_une_liaison_perdue_jamais_une_autre_erreur():
    liaison, doublure = _liaison()
    origine = doublure.get
    for reponse in ({"head_joints": None, "body_yaw": 0.0, "antennas_position": [0, 0]},  # la tête pas demandée
                    {"head_joints": [0.0] * 6, "body_yaw": 0.0, "antennas_position": [0, 0]},  # 6 au lieu de 7
                    {"head_joints": [0.0] * 7, "antennas_position": [0, 0]}, "pas un dictionnaire", None):
        doublure.get = lambda chemin, r=reponse: r if chemin.startswith("/api/state/full") else origine(chemin)
        with pytest.raises(ConnectionError, match="illisible"):
            liaison.lire_etat()
    doublure.get = lambda chemin: {"pas": "une liste"} if chemin == "/api/move/running" else origine(chemin)
    with pytest.raises(ConnectionError, match="illisible"):
        liaison.lire_etat()


def test_dans_le_doute_le_robot_est_dit_en_mouvement():
    """La logique et le seuil sont un choix de l'équipe, à vérifier sur le robot : ici, seule la doublure répond."""
    liaison, doublure = _liaison()
    assert liaison.lire_etat()["en_mouvement"] is False  # en marche, moteurs tenus, rien en cours, tête immobile
    doublure.mode = "disabled"
    assert liaison.lire_etat()["en_mouvement"] is False  # moteurs coupés, tête immobile
    doublure.mode = "enabled"
    doublure.mouvements = ["m-1"]
    etat = liaison.lire_etat()
    assert etat["en_mouvement"] is True and etat["occupe"] is True  # un mouvement de la liste
    doublure.mouvements = []
    doublure.mouvement_invisible = True  # un mouvement que la liste ne montre pas : la mesure des positions le voit
    etat = liaison.lire_etat()
    assert etat["en_mouvement"] is True and etat["occupe"] is False
    doublure.mouvement_invisible = False
    assert liaison.lire_etat()["en_mouvement"] is False
    doublure.pousse = 0.01  # quelqu'un pousse la tête à la main
    assert liaison.lire_etat()["en_mouvement"] is True
    doublure.pousse = 0.0005  # sous le seuil de 0,003 radian
    assert liaison.lire_etat()["en_mouvement"] is False
    doublure.pousse = 0.0
    for mode in ("gravity_compensation", "autre_chose", None):  # on peut bouger la tête à la main, ou mode inconnu
        doublure.mode = mode
        assert liaison.lire_etat()["en_mouvement"] is True, mode


def test_l_arret_normal_arrete_chaque_mouvement_de_la_liste_et_ne_coupe_pas_les_moteurs():
    liaison, doublure = _liaison()
    doublure.mouvements = ["m-1", "m-2"]
    liaison.arreter_mouvement()
    assert [(a, c) for v, a, c in doublure.appels_du_kit if v == "POST"] == [(ARRET, {"uuid": "m-1"}), (ARRET, {"uuid": "m-2"})]
    assert doublure.mouvements == [] and doublure.mode == "enabled"
    doublure.appels_du_kit.clear()
    liaison.arreter_mouvement()  # rien en cours : rien n'est envoyé
    assert _envoyes(doublure) == []


def test_un_arret_qui_rate_n_empeche_pas_les_suivants():
    """Lu : arrêter un mouvement déjà fini rend une erreur. Trouvé par le relecteur : la boucle s'arrêtait là."""
    liaison, doublure = _liaison()
    doublure.mouvements = ["m-1", "m-2"]
    origine = doublure.post

    def post(chemin, corps=None):
        if chemin == ARRET and corps == {"uuid": "m-1"}:  # m-1 vient de finir tout seul
            doublure.mouvements.remove("m-1")
            doublure.appels_du_kit.append(("POST", chemin, corps))
            raise ActionImpossible("robot_refuse", "code 500")
        return origine(chemin, corps)

    doublure.post = post
    liaison.arreter_mouvement()
    assert doublure.mouvements == [] and _envoyes(doublure) == [ARRET, ARRET]


def test_l_arret_normal_dit_quand_il_n_est_pas_confirme():
    liaison, doublure = _liaison()
    doublure.mouvements = ["m-1"]
    origine = doublure.post
    doublure.post = lambda chemin, corps=None: (_ for _ in ()).throw(ActionImpossible("robot_refuse", "code 500")) \
        if chemin == ARRET else origine(chemin, corps)
    with pytest.raises(ActionImpossible, match="encore en cours"):  # le mouvement est toujours dans la liste
        liaison.arreter_mouvement()

    liaison, doublure = _liaison()
    doublure.mouvement_invisible = True  # un réveil, un geste lancé par un autre programme : la liste est vide
    with pytest.raises(ActionImpossible, match="bouge encore") as erreur:
        liaison.arreter_mouvement()
    assert erreur.value.code == "arret_non_confirme"


def test_l_arret_d_urgence_propose_coupe_les_moteurs_d_abord():
    liaison, doublure = _liaison()
    doublure.mouvements = ["m-1", "m-2"]
    liaison.arret_urgence()
    assert _envoyes(doublure) == [COUPURE, ARRET, ARRET]  # la coupure part EN PREMIER
    assert doublure.mode == "disabled" and doublure.mouvements == []


def test_la_coupure_part_meme_si_tout_le_reste_rate_et_un_echec_de_coupure_est_dit():
    liaison, doublure = _liaison()
    doublure.mouvements = ["m-1"]
    origine = doublure.get
    doublure.get = lambda chemin: (_ for _ in ()).throw(ConnectionError("essai : plus aucune lecture"))
    liaison.arret_urgence()  # la liste est illisible : la coupure est partie quand même, et aucune erreur ne la masque
    assert doublure.mode == "disabled" and _envoyes(doublure) == [COUPURE]
    doublure.get = origine

    liaison, doublure = _liaison()
    doublure.mouvements = ["m-1"]
    doublure.pret = False  # la coupure est refusée (code 503)
    with pytest.raises(ActionImpossible, match="503"):
        liaison.arret_urgence()
    assert _envoyes(doublure)[0] == COUPURE


def test_rearmer_n_envoie_rien_au_robot():
    liaison, doublure = _liaison()
    liaison.arret_urgence()
    doublure.appels_du_kit.clear()
    liaison.rearmer()
    assert doublure.appels_du_kit == [] and doublure.mode == "disabled"  # les moteurs restent coupés : étape humaine


def test_montrer_la_voix_et_le_reste_sont_a_brancher_et_rien_ne_part():
    liaison, doublure = _liaison()
    appels = [lambda: liaison.montrer("bras"),
              lambda: liaison.parler("bonjour", "fr"), lambda: liaison.ecouter(1.0),
              lambda: liaison.vitesse(0.1, 0.0, 0.0), lambda: liaison.saisir("coussin", 5.0), lambda: liaison.poser("ici")]
    for appel in appels:
        with pytest.raises(ABrancher, match="À BRANCHER"):
            appel()
    assert doublure.appels_du_kit == []
    assert LiaisonReachyMini.branchees == frozenset({"arreter", "etat", "regarder", "rejouer_geste"})


def test_la_liaison_ne_connait_que_sept_demandes_et_ne_parle_au_robot_que_par_le_client():
    assert PERMIS == {("GET", "/api/daemon/status"), ("GET", "/api/move/running"), ("GET", "/api/state/full"),
                      ("POST", ARRET), ("POST", COUPURE), ("POST", TETE), ("POST", ALLUMER)}
    code = "\n".join(ligne.split("#")[0] for ligne in (ICI / "liaison.py").read_text(encoding="utf-8").splitlines())
    code = re.sub(r'""".*?"""', "", code, flags=re.S)
    assert set(re.findall(r"\bkit\.(\w+)\(", code)) == {"get", "post"}
    assert code.count("urlopen") == 0 and code.count("self._ouvreur.open(") == 1  # une seule porte de sortie
    assert code.count("goto") == 1  # une seule adresse pour bouger la tête : celle qui prend une DURÉE
    # Allumer les moteurs : une seule adresse, envoyée à un seul endroit (le geste « lever_la_tete »).
    assert code.count("set_mode/enabled") == 1 and code.count("kit.post(ALLUMER_LES_MOTEURS") == 1
    # Jamais le réveil ni le coucher du FABRICANT (rapides, avec un son), jamais un ordre sans durée, jamais le corps.
    for interdit in ("/play", "set_target", "gravity_compensation\")", "body_yaw\":"):
        assert interdit not in code, interdit


def test_la_carte_ne_promet_que_ce_qui_est_branche_et_garde_zero_partout():
    texte = (ICI / "carte.yaml").read_text(encoding="utf-8")
    carte = CarteIdentite.charger(ICI / "carte.yaml")
    assert sorted(carte.capacites) == ["arreter", "etat", "regarder", "rejouer_geste"]
    assert sorted(carte.capacites) == sorted(LiaisonReachyMini.branchees)
    assert sorted(carte.gestes) == sorted([*module_liaison.GESTES, *module_liaison.POSTURES])
    # Le test de conformité essaie les actions dans l'ordre de la carte, et le PREMIER geste : notre réveil lent d'abord.
    assert carte.gestes[0] == "lever_la_tete" and carte.capacites.index("rejouer_geste") < carte.capacites.index("regarder")
    assert carte.genre == "autre" and carte.position_fixe == "table"
    limites = carte.limites
    assert (limites.vitesse_max_m_s, limites.portee_max_m, limites.charge_max_kg, limites.force_max_n) == (0, 0, 0, 0)
    assert texte.count("à vérifier") >= 4 and "--no-wake-up-on-start" in texte


def test_la_conformite_reussit_avec_la_doublure_et_la_vraie_liaison_et_dit_faux_robot():
    adaptateur = ROBOT.fabriquer(vrai=False, acceleration=5)
    assert type(adaptateur._liaison) is LiaisonReachyMini
    assert type(adaptateur._liaison.kit) is DoublureReachyMini and adaptateur._liaison.vrai_robot is False
    for temps in (conformite.sans_mouvement, conformite.complet):
        rapport = asyncio.run(temps(lambda: ROBOT.fabriquer(vrai=False, acceleration=5), vrai_attendu=False))
        assert rapport.reussi, rapport.texte()
        assert rapport.mention == "testé sur faux robot"


# ================================================================ bouger la tête (15.11.2026), avec la doublure
# Réécrit après la relecture du 15.11.2026 (16 défauts, dont 5 graves) : chaque défaut grave a son essai ci-dessous.
def _jouer(liaison, doublure, max_s: float = 10.0) -> list[tuple[float, float]]:
    """Fait le travail de l'adaptateur : un tic, une lecture d'état, jusqu'à ce que le robot ne soit plus occupé."""
    poses, fin = [], time.monotonic() + max_s
    while time.monotonic() < fin:
        liaison.tic()
        etat = liaison.lire_etat()
        poses.append((doublure.lacet, doublure.tangage))
        if not etat["occupe"]:
            return poses
        time.sleep(0.01)
    raise AssertionError("le mouvement ne finit pas")


def _tetes(doublure) -> list[dict]:
    return [corps for verbe, adresse, corps in doublure.appels_du_kit if (verbe, adresse) == ("POST", TETE)]


def _refus(appel) -> str:
    with pytest.raises(ActionImpossible) as refus:
        appel()
    return refus.value.code


def test_regarder_envoie_un_seul_ordre_lent_vers_une_direction_du_fichier():
    liaison, doublure = _liaison()
    assert {"devant", "patient", "collegue"} <= set(liaison.directions)
    lacet, tangage = liaison.directions["patient"]
    liaison.regarder("patient")
    assert liaison.lire_etat()["occupe"] is True and liaison.lire_etat()["en_mouvement"] is True
    _jouer(liaison, doublure)
    (ordre,) = _tetes(doublure)
    assert set(ordre) == {"head_pose", "duration"}  # ni le corps ni les antennes : la tête seulement
    assert ordre["head_pose"] == {"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": tangage, "yaw": lacet}
    assert ordre["duration"] == pytest.approx(abs(lacet) / module_liaison.VITESSE_TETE_RAD_S)  # 20° par seconde en moyenne
    assert ordre["duration"] >= module_liaison.DUREE_MIN_S
    assert (doublure.lacet, doublure.tangage) == pytest.approx((lacet, tangage))
    assert set(_envoyes(doublure)) == {TETE}  # rien d'autre n'est parti
    assert liaison.lire_etat()["echec_action"] is None and liaison.lire_etat()["erreurs"] == []


def test_les_directions_du_fichier_sont_dans_nos_limites_et_les_limites_sont_petites():
    liaison, _ = _liaison()
    assert math.degrees(module_liaison.LACET_MAX_RAD) <= 40.0 + 1e-9 and math.degrees(module_liaison.TANGAGE_MAX_RAD) <= 20.0 + 1e-9
    assert math.degrees(module_liaison.VITESSE_TETE_RAD_S) <= 20.0 + 1e-9 and math.degrees(module_liaison.VITESSE_GESTE_RAD_S) <= 25.0 + 1e-9
    assert module_liaison.DUREE_MIN_S >= 1.0
    for nom, (lacet, tangage) in liaison.directions.items():
        assert abs(lacet) <= module_liaison.LACET_MAX_RAD and abs(tangage) <= module_liaison.TANGAGE_MAX_RAD, nom
    texte = (ICI / "directions.yaml").read_text(encoding="utf-8")
    assert MARQUE in texte and "à vérifier" in texte
    # la vitesse de POINTE est dite (elle est plus haute que la moyenne), dans la liaison et dans la carte
    assert "1,875" in (ICI / "liaison.py").read_text(encoding="utf-8") and "pointe" in (ICI / "carte.yaml").read_text(encoding="utf-8")


def test_une_cible_inconnue_ou_hors_limites_est_refusee_et_rien_ne_part():
    liaison, doublure = _liaison()
    liaison.directions["trop_loin"] = (math.radians(41.0), 0.0)
    liaison.directions["trop_haut"] = (0.0, math.radians(-21.0))
    liaison.directions["pas_un_nombre"] = (math.nan, 0.0)
    for cible, code in (("plafond", "cible_inconnue"), ("trop_loin", "hors_limites"), ("trop_haut", "hors_limites"),
                        ("pas_un_nombre", "hors_limites")):
        assert _refus(lambda: liaison.regarder(cible)) == code
    assert _refus(lambda: liaison.geste("danser", 1.0)) == "geste_inconnu"
    assert _refus(lambda: liaison.geste("non", math.nan)) == "hors_limites"
    assert doublure.appels_du_kit == []  # pas même une lecture


def test_un_fichier_de_directions_abime_ne_casse_ni_l_etat_ni_l_arret(tmp_path, monkeypatch):
    fichier = tmp_path / "directions.yaml"
    fichier.write_text("directions:\n  devant: {lacet_deg: 0, tangage_deg: 0}\n  casse: {lacet_deg: beaucoup}\n  vide:\n"
                       "  nan: {lacet_deg: .nan, tangage_deg: 0}\n  nan2: {lacet_deg: 0, tangage_deg: 'nan'}\n"
                       "  infini: {lacet_deg: .inf, tangage_deg: 0}\n  vrai: {lacet_deg: true, tangage_deg: 0}\n", encoding="utf-8")
    monkeypatch.setattr(module_liaison, "DIRECTIONS", fichier)
    liaison, doublure = _liaison()
    assert set(liaison.directions) == {"devant"}  # ni texte, ni vide, ni « pas un nombre », ni infini, ni « true »
    fichier.write_text("ceci n'est pas : [du yaml", encoding="utf-8")
    liaison, doublure = _liaison()
    assert liaison.directions == {}
    liaison.lire_etat()
    liaison.arreter_mouvement()
    assert _refus(lambda: liaison.regarder("devant")) == "cible_inconnue"


@pytest.mark.parametrize("mode", ["disabled", "gravity_compensation", None, "autre"])
def test_moteurs_pas_allumes_la_tete_ne_recoit_aucun_ordre(mode):
    liaison, doublure = _liaison()
    doublure.mode = mode
    for appel in (lambda: liaison.regarder("patient"), lambda: liaison.geste("non", 1.0)):
        assert _refus(appel) == "moteurs_coupes"
    assert _envoyes(doublure) == []  # ni ordre de tête, ni moteurs rallumés : seul « lever_la_tete » peut les rallumer


@pytest.mark.parametrize("champ, valeur", [("hauteur", -0.05), ("roulis", math.radians(10.0)), ("corps", 0.2),
                                           ("lacet", math.radians(60.0)), ("tangage", math.radians(31.0))])
def test_une_tete_couchee_penchee_ou_trop_tournee_ne_recoit_aucun_ordre(champ, valeur):
    """La liaison ne fait jamais le « réveil » du fabricant : une tête pas en place est refusée (relecture, défaut 8c)."""
    liaison, doublure = _liaison()
    assert champ in vars(doublure)
    vars(doublure)[champ] = valeur
    for appel in (lambda: liaison.regarder("devant"), lambda: liaison.geste("non", 1.0)):
        assert _refus(appel) == "tete_pas_en_place"
    assert _envoyes(doublure) == []


def test_jamais_deux_ordres_de_tete_a_la_fois():
    """Vu sur le simulateur du fabricant : un ordre envoyé pendant qu'un autre joue est perdu sans le dire."""
    liaison, doublure = _liaison()
    liaison.regarder("patient")
    for appel in (lambda: liaison.regarder("collegue"), lambda: liaison.geste("oui", 1.0)):
        assert _refus(appel) == "robot_occupe"
    assert len(_tetes(doublure)) == 1 and doublure.ordres_perdus == 0
    _jouer(liaison, doublure)
    doublure.mouvements.append("un-mouvement-lance-par-un-autre-programme")
    assert _refus(lambda: liaison.regarder("devant")) == "robot_occupe" and len(_tetes(doublure)) == 1


def test_un_ordre_perdu_par_le_programme_de_fond_est_dit_perdu_jamais_reussi():
    """Relecture, défaut 2 : la réponse « 200 » ne prouve rien. Après l'envoi, notre ordre doit être dans la liste."""
    # (a) un mouvement que la liste ne montre pas (lancé par un autre chemin) bloque notre ordre
    liaison, doublure = _liaison()
    doublure.mouvement_invisible = True
    assert _refus(lambda: liaison.regarder("patient")) == "ordre_perdu"
    assert doublure.ordres_perdus == 1 and liaison.lire_etat()["occupe"] is False and doublure.lacet == 0.0
    # (b) un autre programme envoie son ordre ENTRE notre vérification et notre envoi
    liaison, doublure = _liaison()
    vrai_get = doublure.get

    def get_avec_un_intrus(chemin):
        rendu = vrai_get(chemin)
        if chemin.startswith("/api/state/full?with_head_pose=true") and not doublure.ordres_de_tete:
            doublure.post(TETE, {"head_pose": {"yaw": -0.3}, "duration": 2.0})  # l'autre programme passe juste avant nous
        return rendu

    doublure.get = get_avec_un_intrus
    assert _refus(lambda: liaison.regarder("patient")) == "ordre_perdu"
    assert doublure.ordres_perdus == 1 and len(doublure.ordres_de_tete) == 1  # seul l'ordre de l'intrus joue


@pytest.mark.parametrize("nom, axe, ecart_deg", [("non", 0, 15.0), ("oui", 1, 10.0)])
def test_un_geste_est_une_suite_de_petits_ordres_envoyes_un_par_un_et_revient_au_depart(nom, axe, ecart_deg):
    liaison, doublure = _liaison()
    liaison.geste(nom, 1.0)
    assert len(_tetes(doublure)) == 1 and len(liaison._file[1]) == 3  # le premier morceau seulement ; trois attendent
    assert liaison.lire_etat()["occupe"] is True
    poses = _jouer(liaison, doublure)
    ordres = _tetes(doublure)
    assert len(ordres) == 4 and doublure.ordres_perdus == 0  # aucun ordre envoyé pendant qu'un autre jouait
    cibles = [(o["head_pose"]["yaw"], o["head_pose"]["pitch"]) for o in ordres]
    assert max(abs(c[axe]) for c in cibles) == pytest.approx(math.radians(ecart_deg))
    assert all(c[1 - axe] == pytest.approx(0.0) for c in cibles) and cibles[-1] == pytest.approx((0.0, 0.0))
    assert all(o["duration"] >= module_liaison.DUREE_MIN_S for o in ordres)
    assert max(abs(p[axe]) for p in poses) <= math.radians(ecart_deg) + 1e-6
    assert (doublure.lacet, doublure.tangage) == pytest.approx((0.0, 0.0), abs=1e-6)
    assert liaison._file is None and liaison._dernier is None and liaison.lire_etat()["echec_action"] is None


def test_la_vitesse_demandee_ne_fait_que_ralentir_un_geste():
    durees = {}
    for vitesse in (0.0, 0.25, 0.5, 1.0, 3.0):
        doublure = DoublureReachyMini(acceleration=40)
        liaison = LiaisonReachyMini(doublure)
        liaison.geste("non", vitesse)
        _jouer(liaison, doublure)
        durees[vitesse] = [ordre["duration"] for ordre in _tetes(doublure)]
        assert len(durees[vitesse]) == 4
    assert durees[3.0] == pytest.approx(durees[1.0], rel=0.05)  # demander plus vite que 1 ne change rien
    assert sum(durees[0.5]) > 1.5 * sum(durees[1.0]) > 0 and sum(durees[0.25]) > 1.8 * sum(durees[0.5])
    assert durees[0.0] == pytest.approx(durees[0.25], rel=0.05)  # 0 = le plus lent permis, jamais « pleine vitesse »
    assert sum(durees[0.25]) < 25.0  # le plus lent finit bien avant la limite de 30 s de l'adaptateur


def test_la_duree_de_chaque_morceau_vient_de_la_position_lue_juste_avant():
    """Relecture, défaut 8b : si la tête n'est plus où on croyait entre deux morceaux, on ne va pas plus vite pour autant."""
    liaison, doublure = _liaison()
    liaison.geste("non", 1.0)
    while doublure.mouvements:
        liaison.lire_etat()
        time.sleep(0.01)
    doublure.lacet = math.radians(18.0)  # poussée de 3° : sous la tolérance d'arrivée, donc le geste continue
    liaison.tic()
    (_, deuxieme) = _tetes(doublure)
    angle = abs(deuxieme["head_pose"]["yaw"] - math.radians(18.0))
    assert deuxieme["duration"] == pytest.approx(angle / module_liaison.VITESSE_GESTE_RAD_S)  # 33° → 1,32 s, pas 1,2 s


def test_un_trajet_trop_long_est_refuse_jamais_raccourci(monkeypatch):
    """Relecture, défaut 8a : couper une durée, c'est aller plus vite. On refuse."""
    monkeypatch.setattr(module_liaison, "DUREE_MAX_S", 1.2)
    liaison, doublure = _liaison()
    assert _refus(lambda: liaison.regarder("patient")) == "trop_loin" and _envoyes(doublure) == []  # 30° = 1,5 s > 1,2 s


def test_en_mode_lent_regarder_va_deux_fois_moins_vite():
    durees = []
    for lent in (False, True):
        adaptateur = ROBOT.fabriquer(vrai=False, acceleration=5, lent=lent)
        liaison = adaptateur._liaison
        assert liaison.lent is lent
        liaison.regarder("patient")
        durees.append(_tetes(liaison.kit)[0]["duration"])
    assert durees[1] == pytest.approx(2 * durees[0])


def test_un_geste_pres_du_bord_reste_dans_les_limites():
    liaison, doublure = _liaison()
    doublure.lacet = module_liaison.LACET_MAX_RAD - math.radians(5.0)
    liaison.geste("non", 1.0)
    _jouer(liaison, doublure)
    assert len(_tetes(doublure)) == 4
    for morceau in _tetes(doublure):
        assert abs(morceau["head_pose"]["yaw"]) <= module_liaison.LACET_MAX_RAD + 1e-9


@pytest.mark.parametrize("arret", ["arreter_mouvement", "arret_urgence"])
def test_un_arret_vide_ce_qui_restait_a_envoyer_et_plus_rien_ne_part(arret):
    liaison, doublure = _liaison()
    liaison.geste("non", 1.0)
    assert len(liaison._file[1]) == 3
    if arret == "arreter_mouvement":
        liaison.arreter_mouvement()
        assert doublure.mode == "enabled"
    else:
        liaison.arret_urgence()
        assert doublure.mode == "disabled" and _envoyes(doublure)[1] == COUPURE  # la coupure part tout de suite après l'ordre de tête
    assert liaison._file is None and liaison._dernier is None and doublure.mouvements == []
    fige = (doublure.lacet, doublure.tangage)
    for _ in range(30):
        liaison.tic()
        time.sleep(0.01)
    assert len(_tetes(doublure)) == 1 and (doublure.lacet, doublure.tangage) == fige
    etat = liaison.lire_etat()
    assert etat["occupe"] is False and etat["echec_action"] is None  # un arrêt n'est pas un échec


@pytest.mark.parametrize("arret", ["arreter_mouvement", "arret_urgence"])
@pytest.mark.parametrize("ordre", ["regarder", "geste"])
def test_un_arret_qui_passe_pendant_les_verifications_empeche_l_ordre_de_partir(arret, ordre):
    """Relecture, défaut 3 : l'arrêt d'urgence part dans un fil à part ; il peut passer pendant que regarder() ou
    geste() lisent l'état du robot. L'ordre ne doit PAS partir après lui, et aucun morceau ne doit suivre."""
    liaison, doublure = _liaison()
    vrai_get, deja = doublure.get, []

    def get_avec_un_arret_au_milieu(chemin):
        rendu = vrai_get(chemin)
        if chemin == "/api/move/running" and not deja:  # la dernière lecture avant l'envoi
            deja.append(True)
            liaison.arret_urgence() if arret == "arret_urgence" else liaison.arreter_mouvement()  # « l'autre fil »
        return rendu

    doublure.get = get_avec_un_arret_au_milieu
    appel = (lambda: liaison.regarder("patient")) if ordre == "regarder" else (lambda: liaison.geste("non", 1.0))
    assert _refus(appel) == "arrete"
    for _ in range(20):
        liaison.tic()
        time.sleep(0.01)
    assert _tetes(doublure) == [] and liaison._file is None and liaison._dernier is None
    assert liaison.lire_etat()["occupe"] is False


def test_un_arret_qui_passe_pendant_l_envoi_d_un_morceau_annule_ce_morceau():
    """L'arrêt peut aussi arriver PENDANT que l'ordre voyage vers le robot : le mouvement à peine né est annulé."""
    for depuis in ("tic", "geste"):
        liaison, doublure = _liaison()
        if depuis == "tic":
            liaison.geste("non", 1.0)
            while doublure.mouvements:  # attendre la fin du premier morceau
                liaison.lire_etat()
                time.sleep(0.01)
        vrai_post = doublure.post

        def post_avec_un_arret_au_milieu(chemin, corps=None, delai_s=None):
            rendu = vrai_post(chemin, corps, delai_s)
            if chemin == TETE:
                liaison._plus_rien_a_suivre()  # l'arrêt passe juste après le départ de l'ordre
            return rendu

        doublure.post = post_avec_un_arret_au_milieu
        if depuis == "tic":
            liaison.tic()
        else:
            assert _refus(lambda: liaison.geste("non", 1.0)) == "arrete"
        assert _envoyes(doublure)[-2:] == [TETE, ARRET] and doublure.mouvements == []
        assert liaison._file is None and liaison._dernier is None


def test_si_l_annulation_de_secours_rate_c_est_dit_jamais_passe_sous_silence():
    """Relecture, défaut 6 : un ordre parti pendant un arrêt et qu'on n'arrive pas à annuler = « arrêt non confirmé »."""
    liaison, doublure = _liaison()
    vrai_post = doublure.post

    def post(chemin, corps=None, delai_s=None):
        if chemin == ARRET:
            raise ConnectionError("le programme de fond ne répond plus")
        rendu = vrai_post(chemin, corps, delai_s)
        if chemin == TETE:
            liaison._plus_rien_a_suivre()
        return rendu

    doublure.post = post
    assert _refus(lambda: liaison.regarder("patient")) == "arret_non_confirme"
    assert len(doublure.mouvements) == 1  # le mouvement joue encore : c'est pour cela qu'on le dit


def test_un_ordre_sans_reponse_fait_tout_annuler():
    """Relecture, défaut 6 : pas de réponse à l'ordre de tête ne veut pas dire qu'il n'est pas parti."""
    liaison, doublure = _liaison()
    vrai_post = doublure.post

    def post(chemin, corps=None, delai_s=None):
        rendu = vrai_post(chemin, corps, delai_s)
        if chemin == TETE:
            assert delai_s == module_liaison.DELAI_ORDRE_TETE_S
            raise ConnectionError("délai dépassé")  # l'ordre est arrivé, mais sa réponse s'est perdue
        return rendu

    doublure.post = post
    with pytest.raises(ConnectionError, match="guette encore"):
        liaison.regarder("patient")
    assert doublure.mouvements == [] and _envoyes(doublure) == [TETE, ARRET]
    # Relecture 2, défaut 3 : l'ordre peut aussi ARRIVER EN RETARD. Pendant 1,5 s, tic annule ce qui apparaît.
    doublure.post = vrai_post
    doublure.mouvements.append("l-ordre-arrive-en-retard")
    liaison.tic()
    assert doublure.mouvements == [] and liaison.lire_etat()["occupe"] is False


def test_un_geste_interrompu_en_route_est_dit_rate_tant_qu_on_peut_le_lire():
    """Relecture, défaut 1 : l'échec n'est plus une exception « dite une fois » qu'un autre lecteur peut avaler."""
    liaison, doublure = _liaison()
    liaison.geste("non", 1.0)
    while doublure.mouvements:
        liaison.lire_etat()
        time.sleep(0.01)
    doublure.refuser_la_tete = True  # le deuxième morceau est refusé par le programme de fond
    liaison.tic()
    assert liaison._file is None
    lectures = [liaison.lire_etat() for _ in range(5)]  # cinq lecteurs : tous voient l'échec, aucun ne reçoit d'exception
    assert all(etat["echec_action"] and "arrêté en route" in etat["echec_action"] for etat in lectures)
    assert all(etat["occupe"] is False and etat["erreurs"] for etat in lectures)
    doublure.refuser_la_tete = False
    assert _refus(lambda: liaison.regarder("devant")) == "robot_occupe"  # un nouvel ordre n'efface pas l'échec tout de suite
    assert liaison.lire_etat()["echec_action"]
    for _ in range(10):
        liaison.tic()
    assert len(doublure.ordres_de_tete) == 1 and len(_tetes(doublure)) == 2  # joué : le premier ; tenté et refusé : le deuxième ; rien de plus


def test_moteurs_coupes_au_milieu_d_un_geste_le_geste_est_dit_rate_et_plus_rien_ne_part():
    """Relecture, défaut 5."""
    liaison, doublure = _liaison()
    liaison.geste("non", 1.0)
    doublure.mode = "disabled"  # quelqu'un d'autre coupe les moteurs pendant le premier morceau
    for _ in range(100):
        liaison.tic()
        if not liaison._en_route():
            break
        time.sleep(0.01)
    etat = liaison.lire_etat()
    assert len(_tetes(doublure)) == 1 and etat["echec_action"] and etat["occupe"] is False


def test_une_tete_qui_n_arrive_pas_a_sa_cible_est_dite_ratee():
    """Relecture, défaut 2 : à la fin d'un « regarder », la pose lue est comparée à la cible."""
    liaison, doublure = _liaison()
    liaison.regarder("patient")
    doublure.post(ARRET, {"uuid": doublure.mouvements[0]})  # un autre programme arrête notre mouvement en route
    liaison.tic()
    etat = liaison.lire_etat()
    assert etat["occupe"] is False and "de sa cible" in etat["echec_action"]


def test_une_lecture_qui_rate_pendant_un_geste_vide_la_file_et_le_geste_est_dit_rate():
    """Relecture 1, défaut 4 : une action déjà dite « échouée » ne doit plus envoyer d'ordre de tête.
    Relecture 2, défaut 1 : la lecture qui rate peut être celle d'un AUTRE lecteur (l'écran) ; le geste doit alors être
    dit RATÉ à celui qui attend sa fin, jamais effacé — et le morceau qui joue est annulé."""
    liaison, doublure = _liaison()
    liaison.geste("non", 1.0)
    doublure.provoquer_panne("coupure")
    with pytest.raises(ConnectionError):
        liaison.lire_etat()  # la lecture de l'écran, par exemple
    doublure.reparer()
    etat = liaison.lire_etat()  # la lecture de celui qui attend la fin du geste
    assert "abandonné" in etat["echec_action"]  # (le morceau n'a pas pu être annulé pendant la coupure : il joue encore,
    assert etat["occupe"] is True               #  l'état le dit, et l'adaptateur, lui, enverra un arrêt)
    for _ in range(40):
        liaison.tic()
        time.sleep(0.01)
    assert len(_tetes(doublure)) == 1 and liaison._file is None and liaison._dernier is None
    # un échec posé par tic n'est pas effacé non plus par une lecture ratée qui suit
    liaison, doublure = _liaison()
    liaison.geste("non", 1.0)
    while doublure.mouvements:
        liaison.lire_etat()
        time.sleep(0.01)
    doublure.refuser_la_tete = True
    liaison.tic()
    doublure.provoquer_panne("coupure")
    with pytest.raises(ConnectionError):
        liaison.lire_etat()
    doublure.reparer()
    assert liaison.lire_etat()["echec_action"]


def test_une_lecture_ratee_annule_le_morceau_qui_joue():
    liaison, doublure = _liaison()
    liaison.regarder("patient")
    vrai_get, compte = doublure.get, []

    def get_qui_rate_une_fois(chemin):
        if not compte:
            compte.append(True)
            raise ConnectionError("une lecture perdue")
        return vrai_get(chemin)

    doublure.get = get_qui_rate_une_fois
    with pytest.raises(ConnectionError):
        liaison.lire_etat()
    assert doublure.mouvements == [] and _envoyes(doublure) == [TETE, ARRET]  # le mouvement ne joue pas « dans le dos »


def test_par_l_adaptateur_une_lecture_ratee_par_un_autre_lecteur_ne_donne_jamais_reussie():
    """Relecture 2, défaut 1, par l'adaptateur : une seule lecture ratée, à des instants différents, écran à côté."""
    for instant in (3, 8, 15, 25, 40):
        etat = {"fait": False}

        def une_lecture_ratee(tour, doublure, instant=instant, etat=etat):
            if tour == instant and not etat["fait"]:
                etat["fait"] = True
                vrai_get, compte = doublure.get, []

                def get(chemin):
                    if not compte:
                        compte.append(True)
                        raise ConnectionError("une lecture perdue")
                    return vrai_get(chemin)

                doublure.get = get

        resultats, doublure = asyncio.run(_par_l_adaptateur([("rejouer_geste", {"nom": "non"})],
                                                            pendant=une_lecture_ratee, lecteur_a_cote=True))
        (statut, code), = resultats
        assert statut == "echouee" or len(doublure.ordres_de_tete) == 4, (instant, statut, code, len(doublure.ordres_de_tete))
        assert doublure.mouvements == []  # et rien ne joue encore quand l'action est finie


def test_un_ordre_appele_pendant_qu_un_arret_travaille_ne_part_pas():
    """Relecture 2, défaut 5 : vu sur le simulateur du fabricant, un ordre appelé PENDANT un arrêt normal passait."""
    for arret in ("arreter_mouvement", "arret_urgence"):
        liaison, doublure = _liaison()
        vrai_get, refus = doublure.get, []

        def get_avec_un_ordre_au_milieu(chemin):
            if chemin == "/api/move/running" and not refus:
                refus.append(_refus(lambda: liaison.regarder("patient")))  # « l'autre fil » : un ordre pendant l'arrêt
            return vrai_get(chemin)

        doublure.get = get_avec_un_ordre_au_milieu
        liaison.arret_urgence() if arret == "arret_urgence" else liaison.arreter_mouvement()
        assert refus == ["arret_urgence_actif" if arret == "arret_urgence" else "arrete"]
        assert _tetes(doublure) == [] and liaison._arrets_en_cours == 0


def test_un_mouvement_qu_on_n_a_pas_pu_annuler_reste_dit_jusqu_au_prochain_arret_reussi():
    """Relecture 2, défaut 4 : dans tic, une annulation « après coup » qui rate n'était dite à personne."""
    liaison, doublure = _liaison()
    liaison.geste("non", 1.0)
    while doublure.mouvements:
        liaison.lire_etat()
        time.sleep(0.01)
    vrai_post = doublure.post

    def post(chemin, corps=None, delai_s=None):
        if chemin == ARRET:
            raise ConnectionError("pas de réponse")
        rendu = vrai_post(chemin, corps, delai_s)
        if chemin == TETE:
            liaison._plus_rien_a_suivre()  # un arrêt passe pendant que le morceau voyage
        return rendu

    doublure.post = post
    liaison.tic()
    etat = liaison.lire_etat()
    assert etat["en_mouvement"] is True and any("encore en cours" in e or "pas pu être annulé" in e for e in etat["erreurs"])
    assert _refus(lambda: liaison.regarder("devant")) == "robot_occupe"
    doublure.post = vrai_post
    liaison.arreter_mouvement()  # un arrêt entièrement vérifié lève l'alerte
    assert liaison.lire_etat()["erreurs"] == [] and doublure.mouvements == []


def test_moteurs_coupes_tout_a_la_fin_ce_n_est_pas_fini():
    """Relecture 2, défaut 7 : coupés dans les derniers degrés, le mouvement était compté « réussi »."""
    liaison, doublure = _liaison()
    liaison.regarder("patient")
    while doublure.mouvements:
        doublure.get("/api/move/running")
        time.sleep(0.01)
    doublure.mode = "disabled"  # la tête est arrivée, mais elle ne tient plus sa place
    liaison.tic()
    etat = liaison.lire_etat()
    assert etat["occupe"] is False and "moteurs" in etat["echec_action"]


def test_un_geste_au_bord_qui_ne_bougerait_pas_est_refuse():
    """Relecture 2, défaut 12."""
    liaison, doublure = _liaison()
    doublure.tangage = module_liaison.TANGAGE_MAX_RAD  # « oui » demande de baisser encore : impossible ici
    assert _refus(lambda: liaison.geste("oui", 1.0)) == "trop_pres_du_bord" and _envoyes(doublure) == []


def test_le_texte_d_un_echec_ne_reste_pas_dans_les_erreurs_pour_toujours(monkeypatch):
    """Relecture 2, défaut 14."""
    monkeypatch.setattr(module_liaison, "ECHEC_VISIBLE_S", 0.2)
    liaison, doublure = _liaison()
    doublure.mouvement_invisible = True
    liaison._echec = (time.monotonic(), "un mouvement raté")
    assert liaison.lire_etat()["erreurs"] == ["un mouvement raté"]
    time.sleep(0.25)
    etat = liaison.lire_etat()
    assert etat["erreurs"] == [] and etat["echec_action"] is None


def test_les_pires_temps_tiennent_sous_la_seconde_de_l_adaptateur():
    """Relecture 2, défauts 2 et 11 : vérifications 0,4 s au plus, ordre 0,3 s, relire la liste 0,2 s."""
    pire = module_liaison.BUDGET_AVANT_ENVOI_S + module_liaison.DELAI_ORDRE_TETE_S + module_liaison.DELAI_LECTURE_S
    assert pire < 1.0
    liaison, doublure = _liaison()
    doublure.latence_s = 0.15  # un programme de fond lent : trois lectures dépassent déjà 0,4 s
    assert _refus(lambda: liaison.regarder("patient")) == "trop_lent" and _tetes(doublure) == []


@pytest.mark.parametrize("glisse_s, confirme", [(1.0, True), (20.0, False)])
def test_apres_un_arret_la_tete_peut_glisser_un_instant_pas_longtemps(glisse_s, confirme):
    """Vu sur le simulateur du fabricant : la tête glisse encore un instant après l'arrêt. Tout l'arrêt tient sous 1 s."""
    liaison, doublure = _liaison()  # la doublure va 5 fois plus vite : 1 s = 0,2 s ; 20 s = 4 s
    doublure.glisse_s = glisse_s
    liaison.regarder("patient")
    debut = time.monotonic()
    if confirme:
        liaison.arreter_mouvement()
    else:
        assert _refus(liaison.arreter_mouvement) == "arret_non_confirme"
    assert time.monotonic() - debut < 1.0 and doublure.mouvements == []


async def _par_l_adaptateur(actions, pendant=None, lecteur_a_cote=False, avant=None):
    """Le chemin de l'ADAPTATEUR (pas la liaison seule, pas la prise) : demarrer, suivre, battement."""
    from briques.b01_prise.actions import ActionDemandee

    adaptateur = ROBOT.fabriquer(vrai=False, acceleration=5)
    if avant is not None:
        avant(adaptateur._liaison.kit)
    await adaptateur.connecter()
    doublure, resultats = adaptateur._liaison.kit, []
    try:
        for nom, parametres in actions:
            ident = await adaptateur.demarrer(ActionDemandee(nom=nom, parametres=parametres))
            for tour in range(900):
                if pendant is not None:
                    pendant(tour, doublure)
                if lecteur_a_cote:
                    try:
                        await adaptateur.etat_robot()  # comme l'écran, qui lit l'état cinq fois par seconde
                    except Exception:
                        pass  # l'écran reçoit l'erreur : ce n'est pas l'action qui la reçoit
                suivi = await adaptateur.suivre(ident)
                if suivi.finie:
                    break
                await adaptateur.battement()
                await asyncio.sleep(0.02)
            resultats.append((suivi.statut, suivi.code_erreur))
        await asyncio.sleep(0.5)
        return resultats, doublure
    finally:
        await adaptateur.deconnecter()


def test_par_l_adaptateur_regarder_et_les_gestes_reussissent_sur_la_doublure_et_une_cible_inconnue_est_refusee():
    resultats, doublure = asyncio.run(_par_l_adaptateur([
        ("regarder", {"cible": "patient"}), ("rejouer_geste", {"nom": "non"}),
        ("rejouer_geste", {"nom": "oui", "vitesse_relative": 0.5}), ("regarder", {"cible": "plafond"})]))
    assert resultats == [("reussie", None), ("reussie", None), ("reussie", None), ("echouee", "cible_inconnue")]
    assert len(doublure.ordres_de_tete) == 9 and doublure.ordres_perdus == 0  # 1 + 4 + 4, jamais deux à la fois


def test_par_l_adaptateur_un_geste_rate_n_est_jamais_compte_reussi_meme_avec_un_autre_lecteur():
    """Relecture, défaut 1, par l'adaptateur entier, avec un deuxième lecteur de l'état (comme l'écran)."""
    def refuser_le_deuxieme_morceau(tour, doublure):
        if len(doublure.ordres_de_tete) >= 1:
            doublure.refuser_la_tete = True

    for _ in range(3):
        resultats, doublure = asyncio.run(_par_l_adaptateur([("rejouer_geste", {"nom": "non"})],
                                                            pendant=refuser_le_deuxieme_morceau, lecteur_a_cote=True))
        assert resultats == [("echouee", "action_interrompue")] and len(doublure.ordres_de_tete) == 1


def test_par_l_adaptateur_un_ordre_perdu_n_est_jamais_compte_reussi():
    def un_mouvement_que_la_liste_ne_montre_pas(tour, doublure):
        doublure.mouvement_invisible = True

    async def scenario():
        from briques.b01_prise.actions import ActionDemandee

        adaptateur = ROBOT.fabriquer(vrai=False, acceleration=5)
        await adaptateur.connecter()
        try:
            adaptateur._liaison.kit.mouvement_invisible = True
            ident = await adaptateur.demarrer(ActionDemandee(nom="regarder", parametres={"cible": "patient"}))
            for _ in range(300):
                suivi = await adaptateur.suivre(ident)
                if suivi.finie:
                    return suivi.statut, suivi.code_erreur, adaptateur._liaison.kit.lacet
                await adaptateur.battement()
                await asyncio.sleep(0.02)
        finally:
            await adaptateur.deconnecter()

    assert asyncio.run(scenario()) == ("echouee", "ordre_perdu", 0.0)


# ================================================================ se lever, se coucher (15.11.2026) : notre réveil lent
def _endormie():
    liaison, doublure = _liaison()
    doublure.endormir()  # comme au démarrage du programme du fabricant SANS réveil : tête couchée, moteurs coupés
    return liaison, doublure


def test_tete_couchee_seul_lever_la_tete_est_permis_et_il_allume_les_moteurs_puis_monte_lentement():
    liaison, doublure = _endormie()
    for appel in (lambda: liaison.regarder("devant"), lambda: liaison.geste("non", 1.0), lambda: liaison.geste("coucher_la_tete", 1.0)):
        assert _refus(appel) == "moteurs_coupes"
    assert _envoyes(doublure) == []
    liaison.geste("lever_la_tete", 1.0)
    assert _envoyes(doublure) == [ALLUMER, TETE] and doublure.mode == "enabled"
    (ordre,) = _tetes(doublure)
    assert ordre == {"head_pose": {"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
                     "antennas": [-0.1745, 0.1745], "duration": module_liaison.DUREE_POSTURE_S}
    assert module_liaison.DUREE_POSTURE_S >= 6.0  # 31° et 5 cm en 6 s au moins : lent
    assert liaison.lire_etat()["occupe"] is True
    _jouer(liaison, doublure)
    assert (doublure.lacet, doublure.tangage, doublure.hauteur) == pytest.approx((0.0, 0.0, 0.0), abs=1e-6)
    assert doublure.antennes == [-0.1745, 0.1745] and liaison.lire_etat()["echec_action"] is None
    liaison.regarder("patient")  # maintenant la tête est en place : elle peut tourner
    _jouer(liaison, doublure)
    assert doublure.lacet == pytest.approx(liaison.directions["patient"][0])


@pytest.mark.parametrize("vitesse, duree", [(1.0, 6.0), (3.0, 6.0), (0.5, 12.0), (0.1, 12.0), (0.0, 12.0)])
def test_se_lever_ne_va_jamais_plus_vite_que_six_secondes_ni_plus_lentement_que_douze(vitesse, duree):
    liaison, doublure = _endormie()
    liaison.geste("lever_la_tete", vitesse)
    assert _tetes(doublure)[0]["duration"] == pytest.approx(duree)


def test_coucher_la_tete_la_repose_lentement_puis_coupe_les_moteurs():
    """Comme le fabricant : on vise SA pose couchée (pas plus bas), puis on coupe les moteurs (relecture du 15.11.2026 :
    tenir la tête contre son socle, moteurs allumés, risquait de les faire forcer)."""
    liaison, doublure = _liaison()
    liaison.geste("coucher_la_tete", 1.0)
    (ordre,) = _tetes(doublure)
    assert ordre["duration"] == module_liaison.DUREE_POSTURE_S and ordre["antennas"] == [-3.05, 3.05]
    assert ordre["head_pose"] == {"x": -0.021, "y": 0.001, "z": -0.044, "roll": 0.0, "pitch": 0.426, "yaw": 0.0}
    assert _envoyes(doublure) == [TETE] and doublure.mode == "enabled"  # pendant la descente, les moteurs tiennent
    _jouer(liaison, doublure)
    assert doublure.hauteur == pytest.approx(-0.044) and doublure.tangage == pytest.approx(0.426)
    assert _envoyes(doublure) == [TETE, COUPURE] and doublure.mode == "disabled"  # arrivée : moteurs coupés
    assert liaison.lire_etat()["echec_action"] is None
    assert _refus(lambda: liaison.regarder("devant")) == "moteurs_coupes"
    liaison.geste("lever_la_tete", 1.0)  # et on peut la relever : les moteurs sont rallumés par ce geste
    _jouer(liaison, doublure)
    assert doublure.hauteur == pytest.approx(0.0, abs=1e-6) and doublure.mode == "enabled"


def test_une_tete_qui_saute_a_l_allumage_fait_recouper_les_moteurs():
    """Relecture du 15.11.2026 : lu dans le code du fabricant, la tête pourrait repartir vers une ancienne cible au
    moment où les moteurs se rallument. Si elle bouge toute seule, on recoupe, et aucun ordre de tête ne part."""
    liaison, doublure = _endormie()
    doublure.saut_a_l_allumage = math.radians(10.0)
    assert _refus(lambda: liaison.geste("lever_la_tete", 1.0)) == "tete_a_saute"
    assert _envoyes(doublure) == [ALLUMER, COUPURE] and doublure.mode == "disabled" and _tetes(doublure) == []
    liaison, doublure = _endormie()
    doublure.saut_a_l_allumage = math.radians(1.0)  # un petit jeu de 1° n'est pas un saut
    liaison.geste("lever_la_tete", 1.0)
    assert _envoyes(doublure) == [ALLUMER, TETE]


def test_si_le_lever_ne_part_pas_apres_l_allumage_les_moteurs_sont_recoupes():
    """Relecture du 15.11.2026 : un « lever » raté après le rallumage laissait les moteurs allumés, sans le dire."""
    for panne in ("refuse", "perdu", "sans_reponse_a_l_allumage"):
        liaison, doublure = _endormie()
        vrai_post = doublure.post
        if panne == "refuse":
            doublure.refuser_la_tete = True
        elif panne == "perdu":
            doublure.mouvement_invisible = True

        def post(chemin, corps=None, delai_s=None, panne=panne, vrai_post=vrai_post):
            rendu = vrai_post(chemin, corps, delai_s)
            if panne == "sans_reponse_a_l_allumage" and chemin == ALLUMER:
                raise ConnectionError("délai dépassé")  # l'ordre est arrivé, sa réponse s'est perdue
            return rendu

        doublure.post = post
        with pytest.raises((ActionImpossible, ConnectionError)):
            liaison.geste("lever_la_tete", 1.0)
        assert doublure.mode == "disabled" and _envoyes(doublure)[-1] == COUPURE, panne
        assert doublure.mouvements == [] and liaison.lire_etat()["occupe"] is False


def test_apres_un_arret_d_urgence_rien_ne_part_avant_qu_un_humain_rearme():
    """Le verrou d'urgence de la liaison (relecture du 15.11.2026) : ni ordre de tête, ni moteurs rallumés."""
    liaison, doublure = _liaison()
    liaison.arret_urgence()
    doublure.appels_du_kit.clear()
    for appel in (lambda: liaison.geste("lever_la_tete", 1.0), lambda: liaison.regarder("devant"),
                  lambda: liaison.geste("non", 1.0), lambda: liaison.geste("coucher_la_tete", 1.0)):
        assert _refus(appel) == "arret_urgence_actif"
    assert doublure.appels_du_kit == [] and doublure.mode == "disabled"
    liaison.rearmer()  # la décision d'un humain : rien n'est envoyé, les moteurs restent coupés
    assert doublure.appels_du_kit == [] and doublure.mode == "disabled"
    liaison.geste("lever_la_tete", 1.0)  # c'est ce geste (accordé par le gardien) qui rallume
    assert _envoyes(doublure) == [ALLUMER, TETE]


def test_une_antenne_tournee_trop_loin_personne_ne_bouge():
    liaison, doublure = _endormie()
    doublure.antennes = [3.05, 3.05]  # l'antenne droite a été tournée à la main de l'autre côté : 185° de trajet
    assert _refus(lambda: liaison.geste("lever_la_tete", 1.0)) == "tete_pas_en_place" and _envoyes(doublure) == []


def test_une_annulation_de_secours_ratee_reste_dite_dans_l_etat():
    """Relecture du 15.11.2026 : l'alerte n'était posée que par tic(), pas par regarder() ni geste()."""
    liaison, doublure = _liaison()
    vrai_post = doublure.post

    def post(chemin, corps=None, delai_s=None):
        if chemin == ARRET:
            raise ConnectionError("le programme de fond ne répond plus")
        rendu = vrai_post(chemin, corps, delai_s)
        if chemin == TETE:
            liaison._plus_rien_a_suivre()
        return rendu

    doublure.post = post
    assert _refus(lambda: liaison.regarder("patient")) == "arret_non_confirme"
    etat = liaison.lire_etat()
    assert etat["en_mouvement"] is True and any("arrêter le robot" in e for e in etat["erreurs"])


@pytest.mark.parametrize("mode", ["gravity_compensation", None, "autre"])
def test_un_mode_de_moteurs_inconnu_n_est_jamais_rallume(mode):
    liaison, doublure = _endormie()
    doublure.mode = mode
    assert _refus(lambda: liaison.geste("lever_la_tete", 1.0)) == "moteurs_coupes" and _envoyes(doublure) == []


def test_si_le_robot_refuse_d_allumer_ses_moteurs_rien_d_autre_ne_part():
    liaison, doublure = _endormie()
    doublure.refuser_d_allumer = True
    assert _refus(lambda: liaison.geste("lever_la_tete", 1.0)) == "robot_refuse"
    assert _envoyes(doublure) == [ALLUMER] and doublure.mode == "disabled"


@pytest.mark.parametrize("arret", ["arreter_mouvement", "arret_urgence"])
def test_un_arret_qui_passe_pendant_qu_on_rallume_les_moteurs_les_fait_recouper(arret):
    """L'arrêt d'urgence part dans un autre fil : s'il passe PENDANT qu'on rallume, les moteurs ne restent pas allumés."""
    liaison, doublure = _endormie()
    vrai_post = doublure.post

    def post(chemin, corps=None, delai_s=None):
        rendu = vrai_post(chemin, corps, delai_s)
        if chemin == ALLUMER:
            liaison.arret_urgence() if arret == "arret_urgence" else liaison.arreter_mouvement()  # « l'autre fil »
        return rendu

    doublure.post = post
    assert _refus(lambda: liaison.geste("lever_la_tete", 1.0)) == "arrete"
    assert doublure.mode == "disabled" and _tetes(doublure) == [] and _envoyes(doublure)[-1] == COUPURE
    for _ in range(20):
        liaison.tic()
    assert _tetes(doublure) == []


def test_un_arret_avant_de_rallumer_et_rien_ne_part():
    liaison, doublure = _endormie()
    vrai_get, deja = doublure.get, []

    def get(chemin):
        rendu = vrai_get(chemin)
        if chemin.startswith("/api/state/full") and not deja:  # la dernière lecture avant de rallumer
            deja.append(True)
            liaison.arret_urgence()
        return rendu

    doublure.get = get
    assert _refus(lambda: liaison.geste("lever_la_tete", 1.0)) == "arrete"
    assert ALLUMER not in _envoyes(doublure) and _tetes(doublure) == [] and doublure.mode == "disabled"


def test_une_tete_qui_ne_monte_pas_est_dite_ratee():
    liaison, doublure = _endormie()
    liaison.geste("lever_la_tete", 1.0)
    doublure.mode = "disabled"  # les moteurs lâchent en route : la tête ne monte pas
    for _ in range(300):
        liaison.tic()
        if not liaison._en_route():
            break
        time.sleep(0.01)
    etat = liaison.lire_etat()
    assert etat["occupe"] is False and etat["echec_action"] and doublure.hauteur < -0.03


def test_le_corps_tourne_personne_ne_leve_la_tete():
    liaison, doublure = _endormie()
    doublure.corps = 0.3
    assert _refus(lambda: liaison.geste("lever_la_tete", 1.0)) == "tete_pas_en_place" and _envoyes(doublure) == []


def test_par_l_adaptateur_depuis_la_tete_couchee_se_lever_regarder_se_coucher():
    resultats, doublure = asyncio.run(_par_l_adaptateur([
        ("regarder", {"cible": "patient"}), ("rejouer_geste", {"nom": "lever_la_tete"}), ("regarder", {"cible": "patient"}),
        ("regarder", {"cible": "devant"}), ("rejouer_geste", {"nom": "coucher_la_tete"})], avant=lambda d: d.endormir()))
    assert resultats == [("echouee", "moteurs_coupes"), ("reussie", None), ("reussie", None), ("reussie", None), ("reussie", None)]
    assert [round(o["hauteur"], 3) for o in doublure.ordres_de_tete] == [0.0, 0.0, 0.0, -0.044]
    assert doublure.mode == "disabled" and doublure.hauteur == pytest.approx(-0.044)  # couchée, moteurs coupés


def test_la_conformite_reussit_aussi_en_partant_de_la_tete_couchee():
    """Comme sur le vrai robot lancé sans réveil : le test complet lève d'abord la tête (premier geste de la carte)."""
    def fabrique():
        adaptateur = ROBOT.fabriquer(vrai=False, acceleration=5)
        adaptateur._liaison.kit.endormir()
        return adaptateur

    for temps in (conformite.sans_mouvement, conformite.complet):
        rapport = asyncio.run(temps(fabrique, vrai_attendu=False))
        assert rapport.reussi, rapport.texte()
        assert rapport.mention == "testé sur faux robot"


# ================================================================ le petit client web, contre un serveur d'essai sur cet ordinateur
class _ServeurDEssai(http.server.BaseHTTPRequestHandler):
    recu: list = []
    comportement = "normal"

    def log_message(self, *args):  # pas de bruit dans les essais
        return

    def _repondre(self, code: int, corps: bytes, genre: str = "application/json", en_tetes: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", genre)
        self.send_header("Content-Length", str(len(corps)))
        for nom, valeur in (en_tetes or {}).items():
            self.send_header(nom, valeur)
        self.end_headers()
        self.wfile.write(corps)

    def _traiter(self, verbe: str):
        longueur = int(self.headers.get("Content-Length") or 0)
        corps = self.rfile.read(longueur) if longueur else b""
        type(self).recu.append((verbe, self.path, corps.decode("utf-8")))
        quoi = type(self).comportement
        if quoi == "503":
            return self._repondre(503, b'{"detail": "Backend not running"}')
        if quoi == "500":
            return self._repondre(500, b'{"detail": "boom"}')
        if quoi == "html":
            return self._repondre(200, b"<html>une page, pas des donnees</html>", "text/html")
        if quoi == "redirection":
            return self._repondre(307, b"", en_tetes={"Location": "http://127.0.0.1:9/ailleurs"})
        if quoi == "lent":
            time.sleep(0.8)
        return self._repondre(200, json.dumps({"state": "running", "error": None}).encode("utf-8"))

    def do_GET(self):  # noqa: N802 — nom imposé par la bibliothèque
        self._traiter("GET")

    def do_POST(self):  # noqa: N802
        self._traiter("POST")


@pytest.fixture
def serveur():
    _ServeurDEssai.recu, _ServeurDEssai.comportement = [], "normal"
    essai = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _ServeurDEssai)
    fil = threading.Thread(target=essai.serve_forever, daemon=True)
    fil.start()
    yield f"http://127.0.0.1:{essai.server_address[1]}"
    essai.shutdown()
    essai.server_close()


def test_le_client_envoie_exactement_la_demande_voulue(serveur):
    client = ClientDuProgrammeDeFond(serveur)
    assert client.get("/api/daemon/status") == {"state": "running", "error": None}
    client.post(ARRET, {"uuid": "abc"})
    client.post(COUPURE)
    assert _ServeurDEssai.recu == [("GET", "/api/daemon/status", ""), ("POST", ARRET, '{"uuid": "abc"}'), ("POST", COUPURE, "")]


def test_le_client_refuse_toute_demande_qui_n_est_pas_dans_la_liste(serveur):
    client = ClientDuProgrammeDeFond(serveur)
    for verbe, chemin in (("GET", "/api/move/goto"), ("POST", "/api/move/goto_joint_positions"), ("POST", "/api/move/play/wake_up"), ("POST", "/api/move/set_target"),
                          ("POST", "/api/motors/set_mode/gravity_compensation"), ("GET", "/api/move/stop"), ("POST", "/api/daemon/status"),
                          ("GET", "/api/camera"), ("POST", "/api/daemon/stop")):
        with pytest.raises(ValueError, match="non permise"):
            client._demander(verbe, chemin, None, 0.5)
    assert _ServeurDEssai.recu == []  # rien n'est parti


def test_une_lecture_refusee_est_une_liaison_perdue_un_ordre_refuse_est_dit_refuse(serveur):
    client = ClientDuProgrammeDeFond(serveur)
    _ServeurDEssai.comportement = "503"
    with pytest.raises(ConnectionError, match="503.*Backend not running"):
        client.get("/api/state/full?with_head_joints=true")
    _ServeurDEssai.comportement = "500"
    with pytest.raises(ActionImpossible, match="500"):
        client.post(ARRET, {"uuid": "fini"})


def test_une_page_au_lieu_de_donnees_une_reponse_trop_lente_et_une_redirection_sont_des_liaisons_perdues(serveur):
    client = ClientDuProgrammeDeFond(serveur)
    _ServeurDEssai.comportement = "html"
    with pytest.raises(ConnectionError, match="illisible"):
        client.get("/api/daemon/status")
    _ServeurDEssai.comportement = "lent"
    debut = time.monotonic()
    with pytest.raises(ConnectionError, match="ne répond pas"):
        client.get("/api/daemon/status")
    assert time.monotonic() - debut < 0.6  # coupé à 0,2 s, pas attendu 0,8 s
    _ServeurDEssai.comportement = "redirection"
    with pytest.raises(ConnectionError, match="307"):  # la redirection n'est PAS suivie
        client.get("/api/daemon/status")
    with pytest.raises(ActionImpossible, match="307"):
        client.post(COUPURE)


def test_le_client_ne_passe_par_aucun_relais_du_systeme(serveur, monkeypatch):
    for nom in ("http_proxy", "HTTP_PROXY", "all_proxy", "ALL_PROXY"):
        monkeypatch.setenv(nom, "http://127.0.0.1:9")  # un relais qui n'existe pas : s'il était utilisé, la demande raterait
    monkeypatch.delenv("no_proxy", raising=False)
    monkeypatch.delenv("NO_PROXY", raising=False)
    assert ClientDuProgrammeDeFond(serveur).get("/api/daemon/status")["state"] == "running"


def test_le_client_ne_parle_qu_a_cet_ordinateur_sauf_demande_expres():
    for adresse in ("fichier:///etc/passwd", "ftp://127.0.0.1", "http://"):
        with pytest.raises(ValueError, match="invalide"):
            ClientDuProgrammeDeFond(adresse)
    for adresse in ("http://192.168.1.20:8000", "http://reachy-mini.local:8000", "http://exemple.org"):
        with pytest.raises(ValueError, match="n'est pas sur cet ordinateur"):
            ClientDuProgrammeDeFond(adresse)
    assert ClientDuProgrammeDeFond("http://192.168.1.20:8000", hors_de_cet_ordinateur=True).adresse.endswith(":8000")
    client = ClientDuProgrammeDeFond("http://127.0.0.1:9")  # port 9 : personne n'y répond
    with pytest.raises(ConnectionError, match="ne répond pas"):
        client.get("/api/daemon/status")


def test_l_adresse_d_un_robot_wireless_demande_deux_lignes_ecrites_par_un_humain(monkeypatch):
    monkeypatch.delenv("REACHY_MINI_ADRESSE", raising=False)
    monkeypatch.delenv("REACHY_MINI_RESEAU_PRIVE", raising=False)
    assert LiaisonReachyMini.creer_kit().adresse == "http://127.0.0.1:8002"  # rien à régler pour un Lite
    monkeypatch.setenv("REACHY_MINI_ADRESSE", "http://192.168.43.20:8000")
    with pytest.raises(ValueError, match="pas sur cet ordinateur"):  # l'adresse seule ne suffit pas
        LiaisonReachyMini.creer_kit()
    monkeypatch.setenv("REACHY_MINI_RESEAU_PRIVE", "peut-être")
    with pytest.raises(ValueError, match="pas sur cet ordinateur"):
        LiaisonReachyMini.creer_kit()
    monkeypatch.setenv("REACHY_MINI_RESEAU_PRIVE", "oui")
    assert LiaisonReachyMini.creer_kit().adresse == "http://192.168.43.20:8000"
    # « réseau privé » est vérifié, pas seulement déclaré (relecture 2, défaut 17)
    for adresse in ("http://example.com:8000", "http://8.8.8.8:8000", "http://reachy.example.org:8000"):
        monkeypatch.setenv("REACHY_MINI_ADRESSE", adresse)
        with pytest.raises(ValueError, match="réseau privé"):
            LiaisonReachyMini.creer_kit()
    for adresse in ("http://10.0.0.7:8000", "http://172.20.10.3:8000", "http://reachy-mini.local:8000"):
        monkeypatch.setenv("REACHY_MINI_ADRESSE", adresse)
        assert LiaisonReachyMini.creer_kit().adresse == adresse


class _ClientQuiRepondCommeLeSimulateurDuFabricant:
    """Pas un faux kit du projet : pour la liaison, c'est donc un « vrai » client. Il répond comme le programme du
    fabricant lancé avec « --mockup-sim » (réponse copiée le 15.11.2026, version 1.14.0)."""

    def __init__(self, **champs):
        self.etat = {"state": "running", "simulation_enabled": False, "mockup_sim_enabled": True, "error": None,
                     "backend_status": {"motor_control_mode": "enabled", "error": None}, **champs}
        self.demandes = []

    def get(self, chemin):
        self.demandes.append(("GET", chemin))
        return self.etat

    def post(self, chemin, corps=None):
        self.demandes.append(("POST", chemin))
        return {"uuid": "x"}


@pytest.mark.parametrize("champs", [{"mockup_sim_enabled": True}, {"mockup_sim_enabled": False, "simulation_enabled": True}])
def test_le_simulateur_du_fabricant_ne_passe_jamais_pour_un_vrai_robot(champs):
    client = _ClientQuiRepondCommeLeSimulateurDuFabricant(**champs)
    liaison = LiaisonReachyMini(client)
    assert liaison.vrai_robot is True  # la liaison croirait parler à un vrai robot…
    assert LiaisonReachyMini(client, simulateur_du_fabricant=True).vrai_robot is False  # l'option d'essai : jamais « vrai »
    for appel in (liaison.ouvrir, liaison.signe_de_vie, liaison.lire_etat, lambda: liaison.regarder("devant"), lambda: liaison.geste("non", 1.0)):
        with pytest.raises(ConnectionError, match="MODE SIMULÉ"):  # …donc elle refuse, et le dit
            appel()
    assert [verbe for verbe, _ in client.demandes].count("POST") == 0
    # un essai à la main peut le demander exprès ; le système et le test de conformité ne le font jamais
    LiaisonReachyMini(client, simulateur_du_fabricant=True).ouvrir()
    # et dans l'autre sens : l'option d'essai ne vaut que pour un simulateur. Si un VRAI robot répond : refus.
    vrai = _ClientQuiRepondCommeLeSimulateurDuFabricant(mockup_sim_enabled=False, simulation_enabled=False)
    essai = LiaisonReachyMini(vrai, simulateur_du_fabricant=True)
    for appel in (essai.ouvrir, essai.lire_etat, lambda: essai.regarder("devant"), lambda: essai.geste("lever_la_tete", 1.0)):
        with pytest.raises(ConnectionError, match="VRAI robot"):
            appel()
    assert [verbe for verbe, _ in vrai.demandes].count("POST") == 0
    for fichier in ("adaptateur.py",):
        assert "simulateur_du_fabricant" not in (ICI / fichier).read_text(encoding="utf-8")

