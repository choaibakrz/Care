"""L'ébauche de branchement d'une main Leadtron DH116, main gauche, 6 moteurs (demande de Hiba, 15.11.2026).

NON TESTÉ SUR VRAI ROBOT. Ces essais tournent avec une DOUBLURE à la place de la main (doublure.py) : une fausse main,
qui offre les mêmes méthodes que notre classe `KitDeLaMain`. La classe `KitDeLaMain`, elle, est essayée contre un FAUX
kit du fabricant, écrit par ces essais dans un dossier provisoire : le VRAI kit du fabricant n'est JAMAIS chargé ici, et
rien n'est envoyé à la vraie main (un garde-fou, plus bas, pointe le dossier du kit vers un dossier vide).
Rien de tout cela ne dit ce que fait la vraie main.
« Fini » veut dire :
- la liaison n'importe jamais le kit du fabricant en haut du fichier ; seule la classe `KitDeLaMain` le touche ;
- le kit se connecte SANS allumer les moteurs et SANS mise en position de départ ; se connecter, donner un signe de vie
  et lire l'état ne font que des LECTURES ;
- une main injoignable ou illisible est dite ; dans le doute, la main est dite EN MOUVEMENT ; une alarme est dite ;
- nos limites (celles des exemples du fabricant : vitesse 20000, courant 1000, position 10000) ne sont JAMAIS dépassées : une valeur hors limites, pas finie,
  booléenne ou illisible est REFUSÉE, jamais ramenée en silence ; la vitesse demandée ne fait que ralentir ;
- une main pas préparée refuse tout, sauf « preparer_la_main », qui allume, attend, puis lance la mise en position de départ ;
- un geste n'est « fini » que si chaque doigt est arrivé, ou arrêté sur l'objet (pour « tenir_doucement » seulement) ;
  une alarme, un doigt bloqué, une lecture ratée, des moteurs coupés, une main trop rapide : le geste est dit RATÉ,
  aussi par l'adaptateur entier, avec un autre lecteur de l'état à côté ;
- un arrêt passe toujours devant (pendant les vérifications, pendant les réglages, pendant l'envoi, pendant l'allumage) ;
  l'arrêt normal arrête puis VÉRIFIE ; l'arrêt d'urgence arrête puis coupe ; ensuite rien ne part avant le réarmement ;
  réarmer n'envoie rien ; ces essais se font presque tous dans UN seul fil : l'arrêt « venu d'un autre fil » y est imité ;
- la carte promet les deux actions obligatoires et rejouer_geste (trois gestes), PAS saisir ni poser, et garde 0 partout ;
- le test de conformité réussit avec la doublure et la VRAIE liaison de ce dossier, et dit « testé sur faux robot ».
Après la relecture du 15.11.2026 (un relecteur neuf, un défaut grave), un essai par défaut :
- une main qui dit « couple atteint » sans qu'un doigt ait avancé n'a rien pris : « tenir_doucement » est dit RATÉ ;
- le kit attend 0,3 s entre fermer et rouvrir le boîtier USB ; un lancement REFUSÉ est quand même suivi d'un arrêt ;
- fermer() coupe les moteurs si c'est nous qui les avons allumés ; une clé écrite deux fois dans le fichier des gestes est refusée ;
- le dossier de la bibliothèque libusb du kit est montré à pyusb (variable DYLD_FALLBACK_LIBRARY_PATH).
"""
import ast
import asyncio
import inspect
import math
import os
import re
import sys
import random
import threading
import time
from pathlib import Path

import pytest
import yaml

from briques.b01_prise.adaptateur import ActionImpossible
from briques.b01_prise.carte import CarteIdentite
from briques.b03_adaptateurs import conformite_deux_temps as conformite
from briques.b03_adaptateurs.chemins.sdk.faux_sdk import FauxKit
from briques.b03_adaptateurs.modele_vide.liaison import ABrancher
from briques.b03_adaptateurs.registre import charger_robot, sur_faux_kit
from briques.b03_adaptateurs.robots.leadtron_dh116 import liaison as module_liaison
from briques.b03_adaptateurs.robots.leadtron_dh116.doublure import ORDRES, DoublureLeadtronDh116
from briques.b03_adaptateurs.robots.leadtron_dh116.liaison import (BOUGER, COURANT_MAX, DOIGTS, GESTES, OUVRIR, POSITION_MAX,
                                                                  PREPARER, TENIR, VITESSE_MAX, KitDeLaMain,
                                                                  LiaisonLeadtronDh116, ordre_permis)

ICI = Path(__file__).resolve().parents[1]
ROBOT = charger_robot(ICI.name, ICI.parent)
MARQUE = "NON TESTÉ SUR VRAI ROBOT"
LECTURES = {"nombre_de_moteurs", "positions", "etats", "alarmes", "moteurs_allumes", "cibles_atteintes", "couples_atteints"}
METHODES_DU_KIT = LECTURES | set(ORDRES) | {"relier", "fermer"}
# LES GESTES POUR LES ESSAIS. Le vrai fichier gestes.yaml est réglé par l'équipe sur la vraie main : les essais n'en
# dépendent pas. Ils jouent une COPIE FIGÉE du fichier d'origine (tests/gestes_d_essai.yaml), dans laquelle trois gestes
# gardent les petites valeurs des premiers essais (tenir_doucement, ouvrir_la_main, bouger_les_doigts : vitesse 5000,
# courant 150 pour fermer et 500 pour ouvrir), sur lesquelles la plupart des essais ont été écrits.
VRAI_FICHIER_DES_GESTES = module_liaison.FICHIER_DES_GESTES
COPIE_FIGEE = Path(__file__).with_name("gestes_d_essai.yaml")  # les quatorze gestes, tels que livrés le 15.11.2026
TENIR_DU_FICHIER = [3000, 2500, 3500, 3500, 3500, 3500]
V_ESSAI = 5000  # la vitesse de ces trois gestes dans les essais


def _positions(valeurs) -> dict:
    return dict(zip(DOIGTS, valeurs))


def _gestes_des_essais() -> str:
    lu = yaml.safe_load(COPIE_FIGEE.read_text(encoding="utf-8"))
    fermer = {"positions": _positions(TENIR_DU_FICHIER), "vitesse": V_ESSAI, "courant": 150}
    ouvrir = {"positions": _positions([0] * 6), "vitesse": V_ESSAI, "courant": 500}
    lu["gestes"].update({TENIR: {"etapes": [fermer]}, OUVRIR: {"etapes": [ouvrir]}, BOUGER: {"etapes": [fermer, ouvrir] * 3}})
    return yaml.safe_dump(lu, allow_unicode=True, sort_keys=False)


GESTES_DES_ESSAIS = _gestes_des_essais()
ALLUMER, COUPER, DEPART = "allumer_les_moteurs", "couper_les_moteurs", "mise_en_position_de_depart"
CIBLE, LANCER, ARRETER = "donner_une_cible", "lancer_le_mouvement", "arreter_les_moteurs"
REGLER, ENVOYER = "regler_vitesse_et_courant", "envoyer_les_reglages"
# Depuis le 15.11.2026 : avant la mise en position de départ, la liaison écrit sa vitesse et son courant les plus grands.
LE_DEPART = [REGLER, ENVOYER, DEPART]


@pytest.fixture(autouse=True)
def jamais_le_vrai_kit(tmp_path, monkeypatch):
    """GARDE-FOU : pendant ces essais, le dossier du kit du fabricant pointe vers un dossier VIDE. Même par erreur,
    aucun essai ne peut charger le vrai kit ni parler à la vraie main (pyusb est installé sur cet ordinateur)."""
    vide = tmp_path / "pas_de_kit_ici"
    monkeypatch.setenv(module_liaison.KIT_DANS_L_ENVIRONNEMENT, str(vide))
    monkeypatch.setattr(module_liaison, "KIT_PAR_DEFAUT", vide)
    # Les essais ont leur propre fichier de gestes : régler le vrai fichier sur la vraie main ne casse aucun essai.
    gestes = tmp_path / "gestes_des_essais.yaml"
    gestes.write_text(GESTES_DES_ESSAIS, encoding="utf-8")
    monkeypatch.setattr(module_liaison, "FICHIER_DES_GESTES", gestes)
    # (Le fichier par défaut de la liaison est fixé à la définition de son constructeur : on change ce défaut-là.)
    assert LiaisonLeadtronDh116.__init__.__defaults__ == (VRAI_FICHIER_DES_GESTES,)
    monkeypatch.setattr(LiaisonLeadtronDh116.__init__, "__defaults__", (gestes,))


def test_le_vrai_fichier_des_gestes_regle_par_l_equipe_est_lisible_dans_nos_limites_et_complet():
    """Le fichier réglé sur la vraie main n'est pas celui des essais. On vérifie SEULEMENT qu'il reste lisible par la
    liaison (donc dans nos limites), qu'il a tous les gestes de la carte, et qu'aucun ne dure plus de 25 s."""
    assert VRAI_FICHIER_DES_GESTES == ICI / "gestes.yaml" and MARQUE in VRAI_FICHIER_DES_GESTES.read_text(encoding="utf-8")
    carte = CarteIdentite.charger(ICI / "carte.yaml")
    liaison = LiaisonLeadtronDh116(DoublureLeadtronDh116(), VRAI_FICHIER_DES_GESTES)
    for nom in carte.gestes:
        if nom == PREPARER:
            continue  # écrit dans liaison.py, pas dans le fichier
        for tirage, etapes in liaison._variantes(nom).items():  # lève une erreur si le fichier est illisible ou hors limites
            assert 1 <= len(etapes) <= module_liaison.ETAPES_MAX, nom
            assert liaison._duree_estimee(etapes, [0] * 6) <= module_liaison.DUREE_MAX_GESTE_S, (nom, tirage)
    dans_le_fichier = set(yaml.safe_load(VRAI_FICHIER_DES_GESTES.read_text(encoding="utf-8"))["gestes"])
    assert dans_le_fichier == set(carte.gestes) - {PREPARER}  # ni un geste en moins, ni un geste que la carte ne connaît pas


def _liaison(prete: bool = False, gestes: Path | None = None):
    doublure = DoublureLeadtronDh116()
    liaison = LiaisonLeadtronDh116(doublure) if gestes is None else LiaisonLeadtronDh116(doublure, gestes)
    liaison.ouvrir()
    if prete:  # la main déjà préparée, sans passer par le geste (plus court)
        doublure.preparer_sans_bouger()
        liaison._depart_fait = True
    doublure.appels_du_kit.clear()
    return liaison, doublure


def _envoyes(doublure) -> list[str]:
    """Les ORDRES arrivés à la fausse main (pas les lectures), dans l'ordre."""
    return [nom for nom, _ in doublure.appels_du_kit if nom in ORDRES]


def _cibles(doublure) -> list[tuple]:
    return [valeurs for nom, valeurs in doublure.appels_du_kit if nom == CIBLE]


def _jouer(liaison, max_s: float = 15.0) -> dict:
    """Fait le travail de l'adaptateur : un tic, une lecture d'état, jusqu'à ce que la main ne soit plus occupée."""
    fin = time.monotonic() + max_s
    while time.monotonic() < fin:
        liaison.tic()
        etat = liaison.lire_etat()
        if not etat["occupe"]:
            return etat
        time.sleep(0.02)
    raise AssertionError("le geste ne finit pas")


def _tics(liaison, duree_s: float) -> None:
    fin = time.monotonic() + duree_s
    while time.monotonic() < fin:
        liaison.tic()
        time.sleep(0.02)


def _refus(appel) -> str:
    with pytest.raises(ActionImpossible) as refus:
        appel()
    return refus.value.code


def _dans_nos_limites(doublure) -> None:
    """Tout ordre « donner_une_cible » arrivé à la fausse main est dans nos limites."""
    for moteur, position, vitesse, courant in _cibles(doublure):
        assert 1 <= moteur <= 6 and 0 <= position <= POSITION_MAX and 0 < vitesse <= VITESSE_MAX and 0 < courant <= COURANT_MAX


# ================================================================ les fichiers, et qui touche au kit du fabricant
def test_la_marque_est_sur_chaque_fichier_de_l_ebauche():
    for nom in ("liaison.py", "carte.yaml", "doublure.py", "adaptateur.py", "__init__.py", "postures.yaml", "gestes.yaml", "tests/gestes_d_essai.yaml",
                "tests/test_ebauche_leadtron_dh116.py", "tests/test_conformite_leadtron_dh116.py"):
        assert MARQUE in (ICI / nom).read_text(encoding="utf-8"), nom
    fiche = (ICI.parents[1] / "fiches" / "leadtron_dh116.md").read_text(encoding="utf-8")
    assert "Non testé sur vrai robot" in fiche and "testé sur vrai robot" not in fiche.replace("Non testé sur vrai robot", "")


def _code(texte: str) -> str:
    """Le code sans ses commentaires ni ses textes entre trois guillemets."""
    sans = "\n".join(ligne.split("#")[0] for ligne in texte.splitlines())
    return re.sub(r'""".*?"""', "", sans, flags=re.S)


def _classe(nom: str) -> str:
    texte = (ICI / "liaison.py").read_text(encoding="utf-8")
    noeud = next(n for n in ast.parse(texte).body if isinstance(n, ast.ClassDef) and n.name == nom)
    return _code("\n".join(texte.splitlines()[noeud.lineno - 1:noeud.end_lineno]))


def test_la_liaison_n_importe_jamais_le_kit_du_fabricant_en_haut_du_fichier():
    texte = (ICI / "liaison.py").read_text(encoding="utf-8")
    importes = set()
    for noeud in ast.parse(texte).body:  # seulement le HAUT du fichier
        if isinstance(noeud, ast.Import):
            importes |= {alias.name for alias in noeud.names}
        elif isinstance(noeud, ast.ImportFrom):
            importes.add(noeud.module)
    assert importes == {"__future__", "importlib", "importlib.util", "math", "os", "random", "sys", "threading", "time", "dataclasses",
                        "pathlib", "typing", "yaml", "briques.b01_prise.adaptateur",
                        "briques.b03_adaptateurs.chemins.sdk.faux_sdk", "briques.b03_adaptateurs.modele_vide.liaison"}
    # Charger notre liaison (c'est fait en haut de ce fichier d'essais) n'a chargé ni le kit du fabricant ni pyusb.
    assert not [m for m in sys.modules if m.startswith(("lhandprolib", "canfd_lib", "gsusb", "usb."))] and "usb" not in sys.modules
    code = _code(texte)
    assert code.count("import_module(") == 1 and "import_module(" in _classe("KitDeLaMain")  # une seule porte, dans le kit
    assert "import usb" not in code and "ctypes" not in code and "__import__" not in code
    for fichier in ("doublure.py", "adaptateur.py"):
        assert "import_module" not in (ICI / fichier).read_text(encoding="utf-8")


def test_seule_la_classe_du_kit_touche_au_fabricant_et_seulement_par_les_fonctions_lues():
    kit, liaison = _classe("KitDeLaMain"), _classe("LiaisonLeadtronDh116")
    tout = _code((ICI / "liaison.py").read_text(encoding="utf-8"))
    du_fabricant = {"get_dof", "get_now_position", "get_now_status", "get_now_alarm", "get_enable", "get_position_reached",
                    "get_torque_reached", "set_enable", "home_motors", "set_target_position", "set_position_velocity",
                    "set_max_current", "move_motors", "stop_motors", "apply_motion_params"}
    assert set(re.findall(r"\bmain\.(\w+)\(", kit)) == du_fabricant  # exactement ces 15 fonctions, lues le 15.11.2026
    assert set(re.findall(r"\bcontroleur\.(\w+)\(", kit)) == {"connect", "disconnect"}
    for nom in du_fabricant | {"sdk_handle", "is_connected", "LHandProController", "disconnect("}:
        assert nom in kit and nom not in tout.replace(kit, ""), nom  # nulle part ailleurs que dans la classe du kit
    # La liaison ne parle au kit que par nos quinze méthodes en français.
    assert set(re.findall(r"\bkit\.(\w+)\(", liaison)) == METHODES_DU_KIT
    # Se connecter : SANS allumer et SANS mise en position de départ. Une seule connexion, un seul allumage.
    assert kit.count("connect(enable_motors=False, home_motors=False") == 1 and kit.count(".connect(") == 1
    assert "enable_motors=True" not in tout and "home_motors=True" not in tout
    assert kit.count("set_enable(0, True)") == 1 and kit.count("home_motors(0)") == 1 and kit.count("move_motors(0)") == 1
    # Un seul endroit de la liaison allume, un seul lance la mise en position de départ, un seul lance un mouvement.
    for ordre in ("kit.allumer_les_moteurs(", "kit.mise_en_position_de_depart(", "kit.lancer_le_mouvement(", "kit.donner_une_cible("):
        assert liaison.count(ordre) == 1, ordre
    # Jamais : bouger sans mise en position de départ, effacer une alarme, un geste du fabricant, un réglage de la main.
    for interdit in ("set_move_no_home", "set_clear_alarm", "clear_alarm", "play_gesture", "set_home_current",
                     "set_control_mode", "set_target_angle", "set_angular_velocity", "set_velocity", "set_sdo_drive_param",
                     "save_sdo_drive_param", "set_ota_send_data", "get_ota_recv_data", "set_hand_type", "set_hand_direction", "set_safe_current_enable",
                     "set_dry_run_mode", "move_to_positions", "move_to_zero", "enable_home_check", "sync_position_to_target"):
        assert interdit not in tout, interdit


def test_la_doublure_offre_exactement_les_memes_methodes_que_le_kit():
    du_kit = {nom for nom, objet in vars(KitDeLaMain).items() if callable(objet) and not nom.startswith("_")}
    assert du_kit == METHODES_DU_KIT and len(du_kit) == 17
    de_la_doublure = vars(DoublureLeadtronDh116)
    for nom in sorted(du_kit):
        assert nom in de_la_doublure, nom  # écrite dans la doublure elle-même, pas héritée du faux kit
        assert list(inspect.signature(de_la_doublure[nom]).parameters) == list(inspect.signature(vars(KitDeLaMain)[nom]).parameters), nom


# ================================================================ la classe du kit, contre un FAUX kit du fabricant
FAUX_FABRICANT = '''
"""Un FAUX kit du fabricant, écrit par les essais. Il note chaque appel et ne parle à rien."""
JOURNAL = []
REGLAGES = {"connect": True, "erreurs": {}, "retours": {"get_dof": (6, 6)}}


class ErreurDuFaux(Exception):
    def __init__(self, error_code):
        self.error_code = error_code
        super().__init__(f"Error {error_code}")


class _Poignee:
    def __getattr__(self, nom):
        def appel(*valeurs):
            JOURNAL.append((nom, valeurs))
            if nom in REGLAGES["erreurs"]:
                raise REGLAGES["erreurs"][nom]
            return REGLAGES["retours"].get(nom, 100 * valeurs[0] if valeurs else None)
        return appel


class LHandProController:
    def __init__(self, **options):
        JOURNAL.append(("LHandProController", options))
        self.sdk_handle, self.is_connected = None, False

    def connect(self, **options):
        JOURNAL.append(("connect", options))
        if not REGLAGES["connect"]:
            return False
        self.sdk_handle, self.is_connected = _Poignee(), True
        return True

    def disconnect(self):
        JOURNAL.append(("disconnect", ()))
        self.sdk_handle, self.is_connected = None, False
'''
SANS_ALLUMER = {"enable_motors": False, "home_motors": False, "canfd_nom_baudrate": 1000000, "canfd_dat_baudrate": 5000000}


@pytest.fixture
def faux_fabricant(tmp_path, monkeypatch):
    """Un dossier provisoire rangé comme le kit du fabricant, avec un faux paquet du même nom. Nettoyé à la fin."""
    dossier = tmp_path / "faux_kit"
    paquet = dossier / module_liaison.EXEMPLES_PYTHON / module_liaison.PAQUET_DU_FABRICANT
    paquet.mkdir(parents=True)
    (paquet / "__init__.py").write_text("", encoding="utf-8")
    (paquet / "controller.py").write_text(FAUX_FABRICANT, encoding="utf-8")
    (dossier / "lib").mkdir()
    (dossier / module_liaison.BIBLIOTHEQUE).write_bytes(b"")  # un fichier vide : jamais chargé par le faux kit
    monkeypatch.delenv(module_liaison.OU_EST_LA_BIBLIOTHEQUE, raising=False)
    monkeypatch.setattr(module_liaison, "_pyusb_est_la", lambda: True)
    chemins = list(sys.path)
    yield dossier
    sys.path[:] = chemins
    for nom in [m for m in sys.modules if m.startswith(module_liaison.PAQUET_DU_FABRICANT)]:
        del sys.modules[nom]


def _faux(nom: str = "controller"):
    return sys.modules[f"{module_liaison.PAQUET_DU_FABRICANT}.{nom}"]


def test_le_kit_se_connecte_sans_allumer_les_moteurs_et_sans_mise_en_position_de_depart(faux_fabricant, monkeypatch):
    avant = list(sys.path)
    kit = KitDeLaMain(faux_fabricant)
    assert _faux().JOURNAL == [("LHandProController", {"communication_mode": "CANFD", "canfd_node_id": 1}),
                               ("connect", SANS_ALLUMER)]  # et RIEN d'autre : aucun ordre, aucune lecture
    assert sys.path[:len(avant)] == avant and sys.path[-1] == str(faux_fabricant / module_liaison.EXEMPLES_PYTHON)  # à la FIN
    assert os.environ[module_liaison.OU_EST_LA_BIBLIOTHEQUE] == str(faux_fabricant / module_liaison.BIBLIOTHEQUE)
    assert LiaisonLeadtronDh116(kit).vrai_robot is True  # la classe du kit est toujours prise pour la VRAIE main
    # Par la variable d'environnement, comme le fera un humain :
    monkeypatch.setenv(module_liaison.KIT_DANS_L_ENVIRONNEMENT, str(faux_fabricant))
    _faux().JOURNAL.clear()
    assert type(LiaisonLeadtronDh116.creer_kit()) is KitDeLaMain
    assert [nom for nom, _ in _faux().JOURNAL] == ["LHandProController", "connect"] and _faux().JOURNAL[1][1] == SANS_ALLUMER


def test_chaque_methode_du_kit_appelle_la_fonction_du_fabricant_lue_et_elle_seule(faux_fabricant):
    kit = KitDeLaMain(faux_fabricant)
    journal = _faux().JOURNAL
    lectures = {"positions": "get_now_position", "etats": "get_now_status", "alarmes": "get_now_alarm",
                "moteurs_allumes": "get_enable", "cibles_atteintes": "get_position_reached",
                "couples_atteints": "get_torque_reached"}
    for methode, fonction in lectures.items():
        journal.clear()
        rendu = vars(KitDeLaMain)[methode](kit)
        assert journal == [(fonction, (numero,)) for numero in range(1, 7)], methode  # les moteurs 1 à 6, jamais 0
        assert len(rendu) == 6
    assert kit.positions() == [100, 200, 300, 400, 500, 600] and kit.moteurs_allumes() == [True] * 6
    journal.clear()
    assert kit.nombre_de_moteurs() == 6 and journal == [("get_dof", ())]
    ordres = [(kit.allumer_les_moteurs, [("set_enable", (0, True))]), (kit.couper_les_moteurs, [("set_enable", (0, False))]),
              (kit.mise_en_position_de_depart, [("home_motors", (0,))]), (kit.lancer_le_mouvement, [("move_motors", (0,))]),
              (kit.arreter_les_moteurs, [("stop_motors", (0,))]), (kit.fermer, [("disconnect", ())]),
              (kit.relier, [("connect", SANS_ALLUMER)])]
    for methode, attendu in ordres:
        journal.clear()
        methode()
        assert journal == attendu, methode
    journal.clear()
    kit.relier()  # déjà reliée : rien n'est fait
    kit.donner_une_cible(3, 3500, 2500, 150)
    assert journal == [("set_target_position", (3, 3500)), ("set_position_velocity", (3, 2500)), ("set_max_current", (3, 150))]
    # (15.11.2026) Régler la vitesse et le courant de CHAQUE moteur, sans cible ni mouvement ; puis les envoyer.
    journal.clear()
    kit.regler_vitesse_et_courant(5000, 600)
    assert journal == [paire for n in range(1, 7) for paire in (("set_position_velocity", (n, 5000)), ("set_max_current", (n, 600)))]
    journal.clear()
    kit.envoyer_les_reglages()
    assert journal == [("apply_motion_params", ())]  # lu : envoie vitesse et courant tout de suite ; pas un mouvement
    for hors_limites in ((20001, 600), (5000, 1001), (0, 600), (5000, 0), (math.nan, 600), (5000, True)):
        journal.clear()
        assert _refus(lambda: kit.regler_vitesse_et_courant(*hors_limites)) == "hors_limites" and journal == []


@pytest.mark.parametrize("ordre", [(1, 10001, 2500, 200), (1, 3000, 20001, 200), (1, 3000, 2500, 1001), (0, 3000, 2500, 200),
                                   (7, 3000, 2500, 200), (1, math.nan, 2500, 200), (1, 3000, math.inf, 200),
                                   (1, 3000, 2500, True), (1, 3000, 0, 200), (1, 3000, -100, 200), (1, 3000, 40000, 2000)])
def test_la_classe_du_kit_refuse_elle_aussi_un_ordre_hors_de_nos_limites(faux_fabricant, ordre):
    kit = KitDeLaMain(faux_fabricant)
    _faux().JOURNAL.clear()
    assert _refus(lambda: kit.donner_une_cible(*ordre)) == "hors_limites"
    assert _faux().JOURNAL == []  # rien n'est parti vers le fabricant


def test_les_erreurs_du_fabricant_sont_redites_simplement(faux_fabricant):
    kit = KitDeLaMain(faux_fabricant)
    faux = _faux()
    faux.REGLAGES["erreurs"] = {"move_motors": faux.ErreurDuFaux(11)}  # lu : LER_NOT_HOME
    assert _refus(kit.lancer_le_mouvement) == "main_pas_preparee"
    faux.REGLAGES["erreurs"] = {"move_motors": faux.ErreurDuFaux(1), "stop_motors": faux.ErreurDuFaux(7),
                                "set_enable": OSError("câble arraché"), "get_now_position": faux.ErreurDuFaux(1)}
    assert _refus(kit.lancer_le_mouvement) == "robot_refuse"  # un ordre refusé est dit refusé
    for appel in (kit.arreter_les_moteurs, kit.couper_les_moteurs, kit.positions):  # communication, erreur sans code, LECTURE
        with pytest.raises(ConnectionError):
            appel()
    faux.REGLAGES["erreurs"] = {}
    kit._controleur.is_connected = False  # lu : le programme du fabricant baisse ce drapeau quand la liaison tombe
    faux.JOURNAL.clear()
    for appel in (kit.positions, kit.lancer_le_mouvement, kit.arreter_les_moteurs, kit.nombre_de_moteurs):
        with pytest.raises(ConnectionError, match="pas ouverte"):
            appel()
    assert faux.JOURNAL == []


def test_une_connexion_ratee_un_kit_absent_ou_pyusb_absent_sont_dits(faux_fabricant, tmp_path, monkeypatch):
    with pytest.raises(RuntimeError, match="LEADTRON_KIT"):
        KitDeLaMain(tmp_path / "nulle_part")
    with pytest.raises(RuntimeError, match="LEADTRON_KIT"):
        LiaisonLeadtronDh116.creer_kit()  # le garde-fou de ces essais : le dossier par défaut est vide
    monkeypatch.setattr(module_liaison, "_pyusb_est_la", lambda: False)
    with pytest.raises(RuntimeError, match="pyusb"):
        KitDeLaMain(faux_fabricant)
    assert not [m for m in sys.modules if m.startswith(module_liaison.PAQUET_DU_FABRICANT)]  # rien n'a été chargé
    monkeypatch.setattr(module_liaison, "_pyusb_est_la", lambda: True)
    (faux_fabricant / module_liaison.EXEMPLES_PYTHON / module_liaison.PAQUET_DU_FABRICANT / "controller.py").write_text(
        FAUX_FABRICANT.replace('"connect": True', '"connect": False'), encoding="utf-8")
    with pytest.raises(ConnectionError, match="ne répond pas.*libusb n'est pas trouvée"):
        KitDeLaMain(faux_fabricant)
    assert [nom for nom, _ in _faux().JOURNAL] == ["LHandProController", "connect"]


def test_le_kit_attend_avant_de_rouvrir_le_boitier_usb_apres_une_fermeture(faux_fabricant):
    """Relecture, défaut 2. Lu : le fabricant attend 0,2 s entre fermer et rouvrir. Nous : 0,3 s. Le test de conformité
    ferme et rouvre plusieurs fois de suite."""
    assert module_liaison.PAUSE_AVANT_DE_ROUVRIR_S == 0.3
    debut = time.monotonic()
    kit = KitDeLaMain(faux_fabricant)
    assert time.monotonic() - debut < 0.25  # la PREMIÈRE connexion n'attend pas
    journal = _faux().JOURNAL
    for _ in range(2):  # fermer puis rouvrir, deux fois de suite
        kit.fermer()
        debut = time.monotonic()
        kit.relier()
        assert 0.3 <= time.monotonic() - debut < 0.6
    assert [nom for nom, _ in journal] == ["LHandProController", "connect", "disconnect", "connect", "disconnect", "connect"]
    assert all(options == SANS_ALLUMER for nom, options in journal if nom == "connect")  # jamais d'allumage en se reconnectant
    kit.fermer()
    time.sleep(0.35)  # la pause est déjà passée : rouvrir n'attend pas une seconde fois
    debut = time.monotonic()
    kit.relier()
    assert time.monotonic() - debut < 0.25
    # Le drapeau du fabricant tombé sans fermeture propre (liaison perdue) : relier() ferme d'abord, puis attend aussi.
    kit._controleur.is_connected = False
    debut = time.monotonic()
    kit.relier()
    assert 0.3 <= time.monotonic() - debut < 0.6 and [nom for nom, _ in journal][-2:] == ["disconnect", "connect"]


def test_le_dossier_de_la_bibliotheque_libusb_du_kit_est_montre_a_pyusb(faux_fabricant, monkeypatch):
    """Vérifié le 15.11.2026 sur ce Mac par le coordinateur : pyusb trouve la bibliothèque libusb livrée avec le kit quand
    DYLD_FALLBACK_LIBRARY_PATH contient le dossier lib/ du kit. Ici : contre le FAUX kit des essais, jamais le vrai."""
    variable, dossier_lib = module_liaison.OU_CHERCHER_LES_BIBLIOTHEQUES, str(faux_fabricant / "lib")
    assert variable == "DYLD_FALLBACK_LIBRARY_PATH" and module_liaison.LIBUSB == "libusb-1.0.dylib"
    # Sans le fichier libusb dans le dossier du kit : la variable n'est pas touchée (ni créée, ni changée).
    monkeypatch.delenv(variable, raising=False)
    KitDeLaMain(faux_fabricant)
    assert variable not in os.environ
    monkeypatch.setenv(variable, "/quelque/part")
    KitDeLaMain(faux_fabricant)
    assert os.environ[variable] == "/quelque/part"
    # Avec le fichier : le dossier est ajouté DEVANT, ce qui y était est gardé, et il n'est jamais ajouté deux fois.
    (faux_fabricant / "lib" / "libusb-1.0.dylib").write_bytes(b"")
    KitDeLaMain(faux_fabricant)
    assert os.environ[variable] == dossier_lib + os.pathsep + "/quelque/part"
    KitDeLaMain(faux_fabricant)
    assert os.environ[variable] == dossier_lib + os.pathsep + "/quelque/part"
    # Variable vide ou absente : on garde aussi les dossiers par défaut du système.
    for depart in (None, ""):
        monkeypatch.delenv(variable, raising=False) if depart is None else monkeypatch.setenv(variable, depart)
        KitDeLaMain(faux_fabricant)
        assert os.environ[variable].split(os.pathsep) == [dossier_lib, str(Path.home() / "lib"), "/usr/local/lib", "/usr/lib"]
    assert not [m for m in sys.modules if m == "usb" or m.startswith("usb.")]  # et pyusb lui-même n'a pas été chargé


# ================================================================ la liaison, avec la doublure : se connecter, lire
def test_se_connecter_et_lire_l_etat_ne_font_que_des_lectures():
    doublure = DoublureLeadtronDh116()
    liaison = LiaisonLeadtronDh116(doublure)
    liaison.ouvrir()
    liaison.signe_de_vie()
    etat = liaison.lire_etat()
    liaison.tic()
    liaison.fermer()
    assert _envoyes(doublure) == []  # aucun ordre : rien n'est allumé, rien ne bouge
    assert {nom for nom, _ in doublure.appels_du_kit} <= LECTURES | {"relier", "fermer"}
    assert doublure.allume == [False] * 6 and doublure.position == [0.0] * 6
    assert {"batterie_pct", "x", "y", "cap", "en_mouvement", "occupe", "objet_tenu", "erreurs", "arret_urgence"} <= set(etat)
    assert etat["batterie_pct"] is None and etat["x"] is None and etat["objet_tenu"] is None  # rien d'inventé
    assert etat["en_mouvement"] is False and etat["occupe"] is False and etat["erreurs"] == [] and etat["echec_action"] is None


def test_la_doublure_est_reconnue_comme_un_faux_robot_par_sa_classe_jamais_par_ce_qu_elle_dit():
    liaison, doublure = _liaison()
    assert isinstance(doublure, FauxKit) and liaison.vrai_robot is False and liaison.repere_du_monde is False
    assert liaison.infos_simulation() == {"limites": {}, "gestes": []}

    class SeDitFaux:
        vrai_robot = False
        faux = True

    menteuse = LiaisonLeadtronDh116(SeDitFaux())
    assert menteuse.vrai_robot is True and menteuse.infos_simulation() is None


def test_une_main_injoignable_ou_qui_n_est_pas_la_bonne_est_dite():
    liaison, doublure = _liaison()
    doublure.provoquer_panne("coupure")
    for appel in (liaison.ouvrir, liaison.signe_de_vie, liaison.lire_etat):
        with pytest.raises(ConnectionError):
            appel()
    doublure.reparer()
    doublure.moteurs = 16  # lu : le fabricant vend aussi une main à 16 moteurs
    with pytest.raises(ConnectionError, match="pas la main attendue"):
        liaison.ouvrir()
    doublure.moteurs = 6
    liaison.fermer()
    with pytest.raises(ConnectionError):  # liaison fermée : plus de lecture
        liaison.lire_etat()
    liaison.ouvrir()  # et on peut la rouvrir (le test de conformité ouvre et ferme plusieurs fois)
    assert liaison.lire_etat()["erreurs"] == [] and _envoyes(doublure) == []


@pytest.mark.parametrize("methode, reponse", [
    ("positions", [0] * 5), ("positions", None), ("positions", "000000"), ("positions", [0, 0, 0, 0, 0, "x"]),
    ("positions", [0, 0, 0, 0, 0, math.nan]), ("positions", [0, 0, 0, 0, 0, True]), ("etats", [0] * 7),
    ("etats", [None] * 6), ("alarmes", {}), ("moteurs_allumes", [True] * 5), ("moteurs_allumes", ["oui"] * 6),
    ("moteurs_allumes", [2] * 6)])
def test_une_lecture_illisible_est_une_liaison_perdue_jamais_une_autre_erreur(methode, reponse):
    liaison, doublure = _liaison()
    doublure.__dict__[methode] = lambda: reponse
    with pytest.raises(ConnectionError, match="illisible"):
        liaison.lire_etat()
    if methode == "positions":
        with pytest.raises(ConnectionError, match="illisible"):
            liaison.signe_de_vie()
    assert _envoyes(doublure) == []


def test_dans_le_doute_la_main_est_dite_en_mouvement():
    liaison, doublure = _liaison()
    assert liaison.lire_etat()["en_mouvement"] is False
    for etats, erreur in (([0, 0, 1, 0, 0, 0], None), ([7] * 6, None), ([0, 0, 0, 0, 0, 42], "état inconnu")):
        doublure.__dict__["etats"] = lambda e=etats: list(e)
        etat = liaison.lire_etat()
        assert etat["en_mouvement"] is True, etats
        assert (erreur is None and etat["erreurs"] == []) or erreur in etat["erreurs"][0]
    del doublure.__dict__["etats"]
    assert liaison.lire_etat()["en_mouvement"] is False
    doublure.position[2] += 200  # quelqu'un pousse un doigt à la main, entre deux lectures
    assert liaison.lire_etat()["en_mouvement"] is True
    assert liaison.lire_etat()["en_mouvement"] is False and _envoyes(doublure) == []


def test_une_alarme_et_un_arret_d_urgence_de_la_main_sont_dits_en_mots_simples():
    liaison, doublure = _liaison()
    doublure.provoquer_alarme(3, 3)
    doublure.provoquer_alarme(6, 77)
    etat = liaison.lire_etat()
    assert etat["erreurs"] == ["la main dit : index : trop de courant (alarme 3)",
                               "la main dit : auriculaire : alarme inconnue (à vérifier dans la doc du fabricant) (alarme 77)"]
    assert etat["arret_urgence"] is False
    doublure.alarme = [0] * 6
    doublure.__dict__["etats"] = lambda: [6, 0, 0, 0, 0, 0]  # lu : 6 = « Emergency Stop State »
    etat = liaison.lire_etat()
    assert etat["arret_urgence"] is True and "pouce_ecartement : en arrêt d'urgence" in etat["erreurs"][0]
    assert _envoyes(doublure) == []  # notre système n'efface JAMAIS une alarme


# ================================================================ nos limites : jamais dépassées
def test_nos_limites_sont_celles_des_exemples_du_fabricant_et_c_est_ecrit():
    # Décision de Hiba du 15.11.2026 (avant : 2500/200/6000, puis 5000/600/6000). Lu : main.py du fabricant, 20000 et 1000.
    assert (POSITION_MAX, VITESSE_MAX, COURANT_MAX, module_liaison.COURSE) == (10000, 20000, 1000, 10000)
    assert module_liaison.COURSE / VITESSE_MAX == 0.5  # toute la course en une demi-seconde, comme les exemples du fabricant
    code = (ICI / "liaison.py").read_text(encoding="utf-8")
    for phrase in ("personne ne s'approche de la main, seuls des objets", "ne pas être trop prudent", "effet waouh de suite",
                   "EXEMPLES DU FABRICANT", "ELLES NE SONT PAS ESSAYÉES SUR LA VRAIE MAIN PAR NOTRE SYSTÈME"):
        assert phrase in code, phrase
    assert (module_liaison.ETAPES_MAX, module_liaison.PAUSE_MAX_S, module_liaison.DUREE_MAX_GESTE_S) == (30, 3.0, 25.0)
    liaison, _ = _liaison()
    (etape,), = liaison._variantes(TENIR).values()  # le fichier DES ESSAIS : les petites valeurs des premiers essais
    assert (list(etape.cibles), etape.vitesse, etape.courant, etape.pause_s, etape.attendre) == (TENIR_DU_FICHIER, 5000, 150, 0.0, True)
    (etape,), = liaison._variantes(OUVRIR).values()
    assert (list(etape.cibles), etape.vitesse, etape.courant) == ([0] * 6, 5000, 500)


@pytest.mark.parametrize("champ, valeur", [
    ("position", 10001), ("position", 20000), ("position", -1), ("position", math.nan), ("position", math.inf),
    ("position", True), ("position", "3000"), ("position", 3000.5), ("position", None),
    ("vitesse", 0), ("vitesse", -5), ("vitesse", 20001), ("vitesse", 40000), ("vitesse", math.nan), ("vitesse", math.inf),
    ("vitesse", True), ("vitesse", 0.5), ("courant", 0), ("courant", -1), ("courant", 1001), ("courant", 2000),
    ("courant", math.nan), ("courant", False), ("moteur", 0), ("moteur", 7), ("moteur", True), ("moteur", 1.5)])
def test_un_ordre_hors_limites_pas_fini_ou_booleen_est_refuse_jamais_ramene(champ, valeur):
    ordre = {"moteur": 1, "position": 3000, "vitesse": 2500, "courant": 150, champ: valeur}
    assert _refus(lambda: ordre_permis(**ordre)) == "hors_limites"
    assert ordre_permis(6, 10000, 20000, 1000) == (6, 10000, 20000, 1000) and ordre_permis(1, 0, 1, 1) == (1, 0, 1, 1)
    assert ordre_permis(1, 3000.0, 2500.0, 150.0) == (1, 3000, 2500, 150)  # un nombre entier écrit avec une virgule : accepté


@pytest.mark.parametrize("demandee, envoyee", [(1.0, 5000), (0.5, 2500), (0.25, 1250), (0.37, 1850), (3.0, 5000), (1e9, 5000)])
def test_la_vitesse_demandee_ne_fait_que_ralentir(demandee, envoyee):
    liaison, doublure = _liaison(prete=True)
    liaison.geste(TENIR, demandee)
    assert [(position, vitesse, courant) for _, position, vitesse, courant in _cibles(doublure)] == \
        [(position, envoyee, 150) for position in TENIR_DU_FICHIER]
    assert envoyee <= demandee * VITESSE_MAX and envoyee <= VITESSE_MAX  # jamais plus vite que demandé, ni que notre limite
    _dans_nos_limites(doublure)
    liaison.arreter_mouvement()


@pytest.mark.parametrize("vitesse", [0, 0.0, -1, -0.5, math.nan, math.inf, -math.inf, True, False, "1", None, 0.1, 0.24])
@pytest.mark.parametrize("nom", GESTES)
def test_une_vitesse_nulle_negative_pas_finie_ou_trop_petite_est_refusee_et_rien_ne_part(nom, vitesse):
    liaison, doublure = _liaison(prete=True)
    assert _refus(lambda: liaison.geste(nom, vitesse)) == "hors_limites"
    _tics(liaison, 0.1)
    assert _envoyes(doublure) == [] and liaison.lire_etat()["occupe"] is False


BON_FICHIER = """defauts: {vitesse: 5000, courant: 150, pause_s: 0}
gestes:
  tenir_doucement:
    etapes:
      - {positions: {pouce_ecartement: 3000, pouce_flexion: 2500, index: 3500, majeur: 3500, annulaire: 3500, auriculaire: 3500}}
  ouvrir_la_main:
    etapes:
      - {positions: {pouce_ecartement: 0, pouce_flexion: 0, index: 0, majeur: 0, annulaire: 0, auriculaire: 0}, courant: 500}
"""
UNE_ETAPE = "      - {positions: {pouce_ecartement: 3000, pouce_flexion: 2500, index: 3500, majeur: 3500, annulaire: 3500, auriculaire: 3500}}\n"
ZERO = "      - {positions: {pouce_ecartement: 0, pouce_flexion: 0, index: 0, majeur: 0, annulaire: 0, auriculaire: 0}, pause_s: 3}\n"


@pytest.mark.parametrize("change, code", [
    # ---- une valeur hors limites, pas entière, booléenne, pas un nombre
    (("index: 3500", "index: 10001"), "hors_limites"), (("index: 3500", "index: 20000"), "hors_limites"),
    (("index: 3500", "index: -1"), "hors_limites"), (("index: 3500", "index: .nan"), "hors_limites"),
    (("index: 3500", "index: .inf"), "hors_limites"), (("index: 3500", "index: true"), "hors_limites"),
    (("index: 3500", "index: beaucoup"), "hors_limites"), (("index: 3500", "index: 3500.5"), "hors_limites"),
    (("index: 3500", "index: null"), "hors_limites"), (("index: 3500", "index: [3500]"), "hors_limites"),
    (("courant: 150", "courant: 1001"), "hors_limites"), (("courant: 150", "courant: 0"), "hors_limites"),
    (("courant: 150", "courant: yes"), "hors_limites"), (("courant: 150", "courant: 150.5"), "hors_limites"),
    (("vitesse: 5000", "vitesse: 20001"), "hors_limites"), (("vitesse: 5000", "vitesse: 0"), "hors_limites"),
    (("vitesse: 5000", "vitesse: -3"), "hors_limites"), (("vitesse: 5000", "vitesse: .inf"), "hors_limites"),
    (("vitesse: 5000, ", ""), "hors_limites"),  # ni dans l'étape ni dans « defauts » : pas de vitesse du tout
    (("pause_s: 0", "pause_s: 3.5"), "hors_limites"), (("pause_s: 0", "pause_s: -1"), "hors_limites"),
    (("pause_s: 0", "pause_s: true"), "hors_limites"), (("pause_s: 0", "pause_s: longtemps"), "hors_limites"),
    (("auriculaire: 3500}}", "auriculaire: 3500}, vitesse: 99999}"), "hors_limites"),  # dans l'étape elle-même
    (("auriculaire: 3500}}", "auriculaire: 3500}, courant: 1500}"), "hors_limites"),
    (("auriculaire: 3500}}", "auriculaire: 3500}, pause_s: 10}"), "hors_limites"),
    ((UNE_ETAPE, UNE_ETAPE * 31), "hors_limites"),  # plus de 30 étapes
    ((UNE_ETAPE, UNE_ETAPE + ZERO * 9), "hors_limites"),  # 9 pauses de 3 s : plus de 25 s en tout
    # ---- un doigt en trop, en moins, écrit deux fois ; une clé en double ; une clé inconnue
    ((", auriculaire: 3500}}", "}}"), "geste_illisible"),  # un doigt en moins
    ((", auriculaire: 3500}}", ", auriculaire: 3500, sixieme_doigt: 100}}"), "geste_illisible"),  # un doigt en trop
    (("index: 3500", "indexe: 3500"), "geste_illisible"),  # une faute de frappe
    ((", auriculaire: 3500}}", ", auriculaire: 3500, index: 3000}}"), "geste_illisible"),  # un doigt écrit DEUX FOIS
    ((", auriculaire: 3500}}", ", auriculaire: 3500, auriculaire: 3500}}"), "geste_illisible"),  # deux fois, même valeur
    (("auriculaire: 3500}}", "auriculaire: 3500}, vitesse: 100, vitesse: 200}"), "geste_illisible"),
    (("auriculaire: 3500}}", "auriculaire: 3500}, force: 3}"), "geste_illisible"),  # une clé inconnue dans l'étape
    (("auriculaire: 3500}}", "auriculaire: 3500}, attendre: 3}"), "geste_illisible"),
    (("auriculaire: 3500}}", "auriculaire: 3500}, attendre: false}"), "geste_illisible"),  # la dernière étape doit attendre
    (("pause_s: 0}", "pause_s: 0, force: 3}"), "geste_illisible"),  # une clé inconnue dans « defauts »
    (("  tenir_doucement:", "  tenir_doucement: {etapes: []}\n  tenir_doucement:"), "geste_illisible"),  # le geste écrit deux fois
    (("    etapes:\n      - {positions: {pouce_ecartement: 3000", "    etapes: []\n    etapes:\n      - {positions: {pouce_ecartement: 3000"), "geste_illisible"),
    (("gestes:", "gestes: {}\ngestes:"), "geste_illisible"),
    (("defauts:", "defauts: {}\ndefauts:"), "geste_illisible"),
    # ---- un geste absent, vide, mal écrit ; un fichier abîmé, vide, absent
    (("tenir_doucement:", "tenir_fort:"), "geste_illisible"),  # le geste de la carte n'est pas dans le fichier
    ((UNE_ETAPE, ""), "geste_illisible"),  # « etapes: » sans étape
    ((UNE_ETAPE, "      - 3500\n"), "geste_illisible"),  # une étape qui n'en est pas une
    ((UNE_ETAPE, "      - {vitesse: 5000}\n"), "geste_illisible"),  # une étape sans positions
    (("    etapes:\n" + UNE_ETAPE, "    positions: {index: 3500}\n"), "geste_illisible"),  # l'ancienne écriture (postures.yaml)
    (("positions: {pouce_ecartement: 3000", "positions: [{pouce_ecartement: 3000"), "geste_illisible"),  # fichier abîmé
    (("gestes:", "- gestes"), "geste_illisible"),
    (("gestes:", "postures:"), "geste_illisible"),
    ((BON_FICHIER, ""), "geste_illisible"),  # fichier vide
    ((BON_FICHIER, "3"), "geste_illisible"),
    ((BON_FICHIER, None), "geste_illisible"),  # pas de fichier
])
def test_un_fichier_de_gestes_hors_limites_ou_abime_est_refuse_et_rien_ne_part(tmp_path, change, code):
    fichier = tmp_path / "gestes.yaml"
    if change[1] is not None:
        assert change[0] in BON_FICHIER, change[0]
        fichier.write_text(BON_FICHIER.replace(*change), encoding="utf-8")
    liaison, doublure = _liaison(prete=True, gestes=fichier)
    assert _refus(lambda: liaison.geste(TENIR, 1.0)) == code
    assert _envoyes(doublure) == []  # RIEN n'est parti : ni un réglage, ni un mouvement
    # (La main n'est même pas lue, sauf pour estimer la durée du geste : il faut savoir où sont les doigts.)
    assert doublure.appels_du_kit == [] or (change[1] == UNE_ETAPE + ZERO * 9 and {nom for nom, _ in doublure.appels_du_kit} <= LECTURES)
    # Un fichier abîmé ne casse ni l'état, ni l'arrêt, ni « preparer_la_main » (qui n'est pas dans le fichier).
    assert liaison.lire_etat()["erreurs"] == []
    liaison.arreter_mouvement()
    liaison.geste(PREPARER, 1.0)
    assert _envoyes(doublure) == [ARRETER, *LE_DEPART]


def test_le_bon_fichier_des_essais_est_bien_lu_et_il_est_relu_a_chaque_geste(tmp_path):
    fichier = tmp_path / "gestes.yaml"
    fichier.write_text(BON_FICHIER, encoding="utf-8")
    liaison, doublure = _liaison(prete=True, gestes=fichier)
    liaison.geste(TENIR, 1.0)
    assert _cibles(doublure) == [(moteur, position, 5000, 150) for moteur, position in enumerate(TENIR_DU_FICHIER, 1)]
    assert _jouer(liaison)["echec_action"] is None
    # L'équipe règle le fichier pendant que le programme tourne : le geste suivant prend les nouvelles valeurs.
    fichier.write_text(BON_FICHIER.replace("index: 0", "index: 400").replace("courant: 500", "courant: 700"), encoding="utf-8")
    doublure.appels_du_kit.clear()
    liaison.geste(OUVRIR, 1.0)
    assert _cibles(doublure) == [(1, 0, 5000, 700), (2, 0, 5000, 700), (3, 400, 5000, 700), (4, 0, 5000, 700), (5, 0, 5000, 700), (6, 0, 5000, 700)]
    assert _jouer(liaison)["echec_action"] is None and doublure.position[2] == 400.0


def test_au_bord_de_nos_limites_c_est_accepte_et_rien_ne_depasse(tmp_path):
    fichier = tmp_path / "gestes.yaml"
    fichier.write_text(BON_FICHIER.replace("3500", "10000").replace("courant: 150", "courant: 1000").replace("vitesse: 5000", "vitesse: 20000")
                       .replace("pause_s: 0", "pause_s: 3"), encoding="utf-8")
    liaison, doublure = _liaison(prete=True, gestes=fichier)
    liaison.geste(TENIR, 1.0)
    assert [(position, vitesse, courant) for _, position, vitesse, courant in _cibles(doublure)][2:] == [(10000, 20000, 1000)] * 4
    _dans_nos_limites(doublure)
    liaison.arreter_mouvement()
    assert max(doublure.position) < 10000  # arrêtée en route


@pytest.mark.parametrize("etape_au_hasard", [
    "{au_hasard: [poing, nulle_part]}",  # un geste qui n'est pas dans le fichier
    "{au_hasard: []}", "{au_hasard: poing}", "{au_hasard: [poing, poing]}", "{au_hasard: [3]}",
    "{au_hasard: [poing], vitesse: 100}",  # « au_hasard » s'écrit seul
    "{au_hasard: [pierre_feuille_ciseaux]}",  # lui-même
    "{au_hasard: [preparer_la_main]}",
    "{au_hasard: [poing]}\n      - {au_hasard: [victoire]}",  # deux tirages dans un geste
    "{au_hasard: [vague_au_hasard]}",  # un geste qui a lui-même un tirage
])
def test_une_etape_au_hasard_mal_ecrite_est_refusee_et_rien_ne_part(tmp_path, etape_au_hasard):
    texte = COPIE_FIGEE.read_text(encoding="utf-8")
    bonne = "{au_hasard: [poing, ouvrir_la_main, victoire]}"
    assert texte.count(bonne) == 1
    texte = texte.replace(bonne, etape_au_hasard) + "\n  vague_au_hasard:\n    etapes:\n      - {au_hasard: [poing]}\n"
    fichier = tmp_path / "gestes.yaml"
    fichier.write_text(texte, encoding="utf-8")
    liaison, doublure = _liaison(prete=True, gestes=fichier)
    assert _refus(lambda: liaison.geste("pierre_feuille_ciseaux", 1.0)) == "geste_illisible"
    assert doublure.appels_du_kit == [] and liaison.lire_etat()["dernier_tirage"] is None
    liaison.geste("poing", 1.0)  # les autres gestes du fichier marchent toujours
    assert _jouer(liaison)["echec_action"] is None


# ================================================================ une main pas préparée ; « preparer_la_main »
@pytest.fixture
def allumage_court(monkeypatch):
    """Pour aller plus vite : 0,1 s d'attente après l'allumage au lieu de 1 s (un autre essai vérifie la vraie attente)."""
    monkeypatch.setattr(module_liaison, "ATTENTE_APRES_ALLUMAGE_S", 0.1)


@pytest.mark.parametrize("nom", [TENIR, OUVRIR, BOUGER])
def test_main_pas_preparee_tout_est_refuse_sauf_preparer(nom):
    liaison, doublure = _liaison()  # moteurs coupés, aucune mise en position de départ
    assert _refus(lambda: liaison.geste(nom, 1.0)) == "main_pas_preparee"
    doublure.allume = [True] * 6  # moteurs allumés par un autre programme, mais PAS de mise en position de départ par nous
    assert _refus(lambda: liaison.geste(nom, 1.0)) == "main_pas_preparee"
    doublure.depart_fait = True  # même si la main, elle, est prête (préparée par le logiciel du fabricant) : dans le doute, non
    assert _refus(lambda: liaison.geste(nom, 1.0)) == "main_pas_preparee"
    liaison._depart_fait, doublure.allume = True, [False] * 6  # préparée par nous, puis moteurs coupés par ailleurs
    assert _refus(lambda: liaison.geste(nom, 1.0)) == "main_pas_preparee" and liaison._depart_fait is False
    _tics(liaison, 0.1)
    assert _envoyes(doublure) == []


def test_preparer_allume_attend_une_seconde_puis_lance_la_mise_en_position_de_depart_et_verifie():
    liaison, doublure = _liaison()
    doublure.position = [800.0, 0.0, 1500.0, 0.0, 0.0, 0.0]  # des doigts un peu fermés au départ
    debut = time.monotonic()
    liaison.geste(PREPARER, 1.0)
    assert time.monotonic() - debut < 1.0  # le geste se LANCE : la méthode rend la main tout de suite
    assert _envoyes(doublure) == [ALLUMER] and liaison._depart_fait is False and liaison.lire_etat()["occupe"] is True
    etat = _jouer(liaison)
    assert _envoyes(doublure) == [ALLUMER, *LE_DEPART]  # et rien d'autre : jamais un « lancer », jamais une cible
    heures = {nom: heure for heure, nom in doublure.journal if nom in (ALLUMER, DEPART)}
    assert heures[DEPART] - heures[ALLUMER] >= 1.0  # lu : le fabricant attend 1 s après avoir allumé
    assert etat["echec_action"] is None and etat["erreurs"] == [] and etat["occupe"] is False
    assert liaison._depart_fait is True and doublure.position == [0.0] * 6 and doublure.allume == [True] * 6
    liaison.tic()
    assert liaison.lire_etat()["en_mouvement"] is False and _envoyes(doublure) == [ALLUMER, *LE_DEPART]


def test_moteurs_deja_allumes_preparer_lance_tout_de_suite_la_mise_en_position_de_depart():
    liaison, doublure = _liaison(prete=True)
    doublure.position = [2000.0] * 6
    liaison.geste(PREPARER, 0.5)
    assert _envoyes(doublure) == LE_DEPART and liaison._depart_fait is False  # pas préparée tant que ce n'est pas VÉRIFIÉ
    assert _refus(lambda: liaison.geste(TENIR, 1.0)) == "robot_occupe"
    assert _jouer(liaison)["echec_action"] is None
    assert liaison._depart_fait is True and doublure.position == [0.0] * 6 and _envoyes(doublure) == LE_DEPART


def test_des_doigts_qui_sautent_a_l_allumage_font_recouper_les_moteurs(allumage_court):
    liaison, doublure = _liaison()
    doublure.saut_a_l_allumage = 500
    liaison.geste(PREPARER, 1.0)
    etat = _jouer(liaison)
    assert "a bougé tout seul" in etat["echec_action"] and _envoyes(doublure) == [ALLUMER, COUPER]
    assert doublure.allume == [False] * 6 and liaison._depart_fait is False and doublure.departs_lances == 0


def test_des_moteurs_qui_ne_s_allument_pas_et_la_mise_en_position_de_depart_ne_part_pas(allumage_court):
    liaison, doublure = _liaison()
    doublure.refuser_d_allumer = True
    liaison.geste(PREPARER, 1.0)
    etat = _jouer(liaison)
    assert "ne se sont pas tous allumés" in etat["echec_action"] and doublure.departs_lances == 0
    assert _envoyes(doublure) == [ALLUMER, COUPER] and liaison._depart_fait is False


def test_une_main_qui_refuse_d_allumer_ou_de_se_mettre_en_position_de_depart_est_dite(allumage_court):
    liaison, doublure = _liaison()
    doublure.provoquer_panne("refus")
    assert _refus(lambda: liaison.geste(PREPARER, 1.0)) == "robot_refuse" and doublure.allume == [False] * 6
    doublure.reparer()
    liaison.geste(PREPARER, 1.0)
    doublure.provoquer_panne("refus")  # elle a allumé, puis elle refuse la mise en position de départ
    etat = _jouer(liaison)
    assert "refuse" in etat["echec_action"] and doublure.allume == [False] * 6 and liaison._depart_fait is False


def test_un_ordre_d_allumer_sans_reponse_fait_recouper(allumage_court):
    liaison, doublure = _liaison()
    doublure.reponse_perdue = {ALLUMER}
    with pytest.raises(ConnectionError, match="recoupés"):
        liaison.geste(PREPARER, 1.0)
    assert _envoyes(doublure) == [ALLUMER, COUPER] and doublure.allume == [False] * 6 and liaison.lire_etat()["occupe"] is False


def test_une_main_qui_ne_dit_jamais_en_depart_on_attend_comme_le_fabricant(allumage_court, monkeypatch):
    """À vérifier sur la vraie main : dit-elle « mise en position de départ en cours » ? Si elle ne le dit jamais, la
    liaison attend le temps que le fabricant attend (5 s, raccourci à 1,2 s pour cet essai), puis vérifie."""
    assert module_liaison.ATTENTE_DEPART_S == 5.0 and module_liaison.DELAI_DEPART_S == 20.0
    monkeypatch.setattr(module_liaison, "ATTENTE_DEPART_S", 1.2)
    liaison, doublure = _liaison(prete=True)
    doublure.dit_en_depart, doublure.duree_depart_s = False, 0.3
    liaison.geste(PREPARER, 1.0)
    debut = time.monotonic()
    etat = _jouer(liaison)
    assert time.monotonic() - debut >= 1.2 and etat["echec_action"] is None and liaison._depart_fait is True


def test_une_mise_en_position_de_depart_qui_ne_finit_pas_ou_qui_finit_loin_de_zero_est_dite_ratee(monkeypatch):
    monkeypatch.setattr(module_liaison, "DELAI_DEPART_S", 0.6)
    liaison, doublure = _liaison(prete=True)
    doublure.duree_depart_s = 100.0
    liaison.geste(PREPARER, 1.0)
    etat = _jouer(liaison)
    assert "n'est pas finie" in etat["echec_action"] and liaison._depart_fait is False
    assert _envoyes(doublure) == [*LE_DEPART, ARRETER]  # et les moteurs sont arrêtés
    # Finie d'après la main, mais un doigt n'est pas revenu à 0 :
    liaison, doublure = _liaison(prete=True)
    doublure.duree_depart_s = 0.2
    vraies = doublure.positions
    doublure.__dict__["positions"] = lambda: [p + (900 if i == 3 else 0) for i, p in enumerate(vraies())]
    liaison.geste(PREPARER, 1.0)
    etat = _jouer(liaison)
    assert "majeur" in etat["echec_action"] and "ne sont pas à 0" in etat["echec_action"] and liaison._depart_fait is False


def test_une_alarme_empeche_de_preparer_et_notre_systeme_ne_l_efface_jamais():
    liaison, doublure = _liaison()
    doublure.provoquer_alarme(2, 8)
    for nom in GESTES:
        assert _refus(lambda: liaison.geste(nom, 1.0)) in ("alarme", "main_pas_preparee")
    assert _refus(lambda: liaison.geste(PREPARER, 1.0)) == "alarme"
    assert _envoyes(doublure) == [] and doublure.alarme[1] == 8


# ================================================================ les gestes qui réussissent
def test_tenir_doucement_ferme_en_partie_lentement_avec_peu_de_courant():
    liaison, doublure = _liaison(prete=True)
    debut = time.monotonic()
    liaison.geste(TENIR, 1.0)
    assert time.monotonic() - debut < 1.0
    assert _envoyes(doublure) == [CIBLE] * 6 + [LANCER]  # six réglages, puis UN lancement
    assert _cibles(doublure) == [(moteur, position, 5000, 150) for moteur, position in enumerate(TENIR_DU_FICHIER, 1)]
    etat = _jouer(liaison)
    assert time.monotonic() - debut >= 3500 / V_ESSAI - 0.1  # 3500 positions à 5000 par seconde : 0,7 s au moins
    assert etat["echec_action"] is None and etat["erreurs"] == [] and etat["objet_tenu"] is None
    assert [round(p) for p in doublure.position] == TENIR_DU_FICHIER and max(doublure.position) <= POSITION_MAX
    assert doublure.mouvements_lances == 1 and _envoyes(doublure) == [CIBLE] * 6 + [LANCER]
    assert liaison.lire_etat()["en_mouvement"] is False


def test_ouvrir_la_main_ramene_tous_les_doigts_a_zero():
    liaison, doublure = _liaison(prete=True)
    doublure.position = [float(p) for p in TENIR_DU_FICHIER]
    liaison.geste(OUVRIR, 1.0)
    assert _cibles(doublure) == [(moteur, 0, 5000, 500) for moteur in range(1, 7)]  # ouvrir : courant 500
    etat = _jouer(liaison)
    assert etat["echec_action"] is None and doublure.position == [0.0] * 6
    liaison.geste(OUVRIR, 1.0)  # déjà ouverte : fini tout de suite, et vérifié
    assert _jouer(liaison)["echec_action"] is None


@pytest.mark.parametrize("en_marche", [False, True])
def test_un_doigt_arrete_sur_l_objet_compte_comme_fini_pour_tenir_doucement(en_marche):
    liaison, doublure = _liaison(prete=True)
    doublure.objet = {3: 2000, 4: 2100, 5: 2200}  # le petit ours : trois doigts le touchent avant leur cible
    doublure.en_marche_sur_l_objet = en_marche  # à vérifier sur la vraie main : un moteur qui pousse est-il dit « en marche » ?
    liaison.geste(TENIR, 1.0)
    etat = _jouer(liaison)
    assert etat["echec_action"] is None and etat["occupe"] is False
    assert [round(p) for p in doublure.position] == [3000, 2500, 2000, 2100, 2200, 3500]
    assert doublure.couple == [False, False, True, True, True, False] and _envoyes(doublure) == [CIBLE] * 6 + [LANCER]
    assert liaison.lire_etat()["en_mouvement"] is en_marche  # dans le doute (« en marche »), la main est dite en mouvement


@pytest.mark.parametrize("coinces, attendu", [({1, 2, 3, 4, 5, 6}, [0] * 6), ({3}, [3000, 2500, 0, 3500, 3500, 3500])])
def test_un_couple_atteint_sans_que_le_doigt_ait_avance_n_est_jamais_un_geste_fini(coinces, attendu, monkeypatch):
    """Relecture du 15.11.2026, défaut GRAVE : une main qui dit « couple atteint » partout et dont les doigts ne bougent
    pas faisait dire « tenir_doucement » RÉUSSI, positions à 0 : la main n'avait rien pris."""
    monkeypatch.setattr(module_liaison, "ATTENTE_EN_PLUS_S", 0.3)
    assert module_liaison.AVANCE_MIN == 300
    liaison, doublure = _liaison(prete=True)
    doublure.couple_colle, doublure.coinces = True, coinces
    debut = time.monotonic()
    liaison.geste(TENIR, 1.0)
    etat = _jouer(liaison)
    assert etat["occupe"] is False and "dit « couple atteint » sans avoir avancé" in etat["echec_action"]
    assert "index" in etat["echec_action"] and time.monotonic() - debut >= 3500 / V_ESSAI * 1.5  # dit raté à la fin du délai, pas avant
    assert [round(p) for p in doublure.position] == attendu and _envoyes(doublure)[-1] == ARRETER


@pytest.mark.parametrize("touche_a, reussi", [(100, False), (300, False), (301, True), (1000, True)])
def test_un_objet_touche_tout_de_suite_ne_compte_pas_il_faut_avoir_avance_de_plus_de_300(touche_a, reussi, monkeypatch):
    """La limite de cette règle, dite honnêtement : un doigt qui touche l'objet avant d'avoir avancé de 300 positions est
    dit « pas arrivé » (geste raté), même s'il tient vraiment l'objet. Le sens sûr ; à régler sur la vraie main."""
    monkeypatch.setattr(module_liaison, "ATTENTE_EN_PLUS_S", 0.3)
    liaison, doublure = _liaison(prete=True)
    doublure.objet = {3: touche_a}
    liaison.geste(TENIR, 1.0)
    etat = _jouer(liaison)
    assert (etat["echec_action"] is None) is reussi and round(doublure.position[2]) == touche_a
    if not reussi:
        assert "index (dit « couple atteint » sans avoir avancé" in etat["echec_action"]
    # Et depuis une main déjà fermée sur l'objet : redemander « tenir_doucement » ne fait rien avancer → raté aussi.


def test_un_couple_atteint_dit_pendant_que_les_doigts_bougent_encore_ne_finit_pas_le_geste():
    """À vérifier sur la vraie main : quand dit-elle « couple atteint » ? Si elle le dit trop tôt (ou si la lecture est
    vieille), le geste ne doit pas être dit fini tant que les doigts bougent."""
    liaison, doublure = _liaison(prete=True)
    doublure.__dict__["couples_atteints"] = lambda: [True] * 6
    debut = time.monotonic()
    liaison.geste(TENIR, 1.0)
    etat = _jouer(liaison)
    assert etat["echec_action"] is None and time.monotonic() - debut >= 3500 / V_ESSAI - 0.1
    assert [round(p) for p in doublure.position] == TENIR_DU_FICHIER  # dit fini seulement quand les doigts sont arrivés


def test_pour_ouvrir_un_couple_atteint_ne_compte_pas(monkeypatch):
    monkeypatch.setattr(module_liaison, "ATTENTE_EN_PLUS_S", 0.3)
    liaison, doublure = _liaison(prete=True)
    doublure.position = [float(p) for p in TENIR_DU_FICHIER]
    doublure.coinces = {4}  # le majeur ne s'ouvre pas
    doublure.__dict__["couples_atteints"] = lambda: [True] * 6  # et la main dit « couple atteint » partout
    liaison.geste(OUVRIR, 1.0)
    etat = _jouer(liaison)
    assert "majeur" in etat["echec_action"] and "pas arrivé" in etat["echec_action"] and doublure.position[3] == 3500.0
    # Un doigt qui n'a pas quitté sa place, mais qui devait AVANCER loin : un « couple atteint » ne suffit toujours pas.
    liaison, doublure = _liaison(prete=True)
    doublure.position = [3000.0, 2500.0, 3500.0, 1000.0, 3500.0, 3500.0]
    doublure.coinces = {4}  # le majeur reste à 1000 ; sa cible est 3500
    doublure.__dict__["couples_atteints"] = lambda: [True] * 6
    liaison.geste(TENIR, 1.0)
    etat = _jouer(liaison)
    assert "majeur (dit « couple atteint » sans avoir avancé" in etat["echec_action"] and doublure.position[3] == 1000.0


def test_un_doigt_deja_a_sa_cible_n_a_pas_a_bouger_et_ce_n_est_pas_un_echec():
    """Demande du 15.11.2026. Même si la main ne dit pas « arrivé » pour un doigt qui n'a pas bougé : s'il était déjà à
    sa cible au départ de l'étape (à 300 positions près) et qu'il y est encore, il compte comme arrivé."""
    liaison, doublure = _liaison(prete=True)
    doublure.position = [3000.0, 2500.0, 3500.0, 3500.0, 200.0, 0.0]  # quatre doigts déjà à leur place
    vraie = doublure.cibles_atteintes
    doublure.__dict__["cibles_atteintes"] = lambda: [False] * 4 + vraie()[4:]  # la main ne dit « arrivé » que pour ceux qui ont bougé
    doublure.__dict__["couples_atteints"] = lambda: [False] * 6
    liaison.geste(TENIR, 1.0)
    etat = _jouer(liaison)
    assert etat["echec_action"] is None and [round(p) for p in doublure.position] == TENIR_DU_FICHIER
    # Tous déjà en place : le geste est fini tout de suite, sans échec, même si la main ne dit « arrivé » pour aucun.
    doublure.__dict__["cibles_atteintes"] = lambda: [False] * 6
    liaison.geste(TENIR, 1.0)
    assert _jouer(liaison, max_s=1.5)["echec_action"] is None
    # Mais un doigt « déjà là » au départ et qui n'y est PLUS (poussé ailleurs) n'est pas dit arrivé.
    liaison.geste(TENIR, 1.0)
    doublure.position[2] = 1000.0
    liaison.tic()
    assert liaison.lire_etat()["occupe"] is True
    liaison.arreter_mouvement()


def test_jamais_deux_gestes_a_la_fois_et_un_geste_inconnu_est_refuse():
    liaison, doublure = _liaison(prete=True)
    assert _refus(lambda: liaison.geste("serrer_fort", 1.0)) == "geste_inconnu" and _envoyes(doublure) == []
    liaison.geste(TENIR, 1.0)
    for nom in GESTES:
        assert _refus(lambda: liaison.geste(nom, 1.0)) == "robot_occupe"
    assert doublure.mouvements_lances == 1 and doublure.departs_lances == 0 and len(_cibles(doublure)) == 6
    assert _jouer(liaison)["echec_action"] is None


def test_une_main_qui_bouge_deja_ne_recoit_aucun_ordre():
    """Le logiciel du fabricant ouvert en même temps, par exemple."""
    liaison, doublure = _liaison(prete=True)
    doublure.__dict__["etats"] = lambda: [0, 0, 1, 0, 0, 0]
    for nom in (TENIR, OUVRIR, BOUGER):  # « preparer_la_main » a sa propre règle depuis le 15.11.2026 : voir plus bas
        assert _refus(lambda: liaison.geste(nom, 1.0)) == "robot_occupe"
    assert _envoyes(doublure) == []


# ================================================================ un geste raté est dit RATÉ
def test_une_alarme_pendant_un_geste_le_geste_est_dit_rate_a_tous_les_lecteurs_et_les_moteurs_sont_arretes(monkeypatch):
    liaison, doublure = _liaison(prete=True)
    liaison.geste(TENIR, 1.0)
    _tics(liaison, 0.3)
    doublure.provoquer_alarme(3, 3)
    liaison.tic()
    for _ in range(3):  # trois lecteurs à la suite : aucun n'avale l'échec
        etat = liaison.lire_etat()
        assert etat["occupe"] is False and "trop de courant" in etat["echec_action"] and "tenir_doucement" in etat["echec_action"]
    assert _envoyes(doublure)[-1] == ARRETER and doublure.alarme[2] == 3  # arrêtés ; l'alarme n'est pas effacée
    assert _refus(lambda: liaison.geste(OUVRIR, 1.0)) == "robot_occupe"  # et rien ne part pendant que l'échec est dit
    fige = list(doublure.position)
    _tics(liaison, 0.3)
    assert doublure.position == fige and max(fige) < 3500 and _envoyes(doublure).count(LANCER) == 1
    monkeypatch.setattr(module_liaison, "ECHEC_VISIBLE_S", 0.0)  # plus tard : le texte de l'échec ne reste pas pour toujours
    etat = liaison.lire_etat()
    assert etat["echec_action"] is None and etat["erreurs"] == ["la main dit : index : trop de courant (alarme 3)"]


def test_un_doigt_bloque_loin_de_sa_cible_le_geste_est_dit_rate(monkeypatch):
    monkeypatch.setattr(module_liaison, "ATTENTE_EN_PLUS_S", 0.3)
    liaison, doublure = _liaison(prete=True)
    doublure.coinces = {3}  # l'index ne bouge pas, sans alarme et sans « couple atteint »
    debut = time.monotonic()
    liaison.geste(TENIR, 1.0)
    etat = _jouer(liaison)
    assert time.monotonic() - debut >= 3500 / V_ESSAI * 1.5  # on lui a laissé une fois et demie la durée prévue, pas moins
    assert "pas arrivé à temps : index (à 3500 positions de sa cible)" in etat["echec_action"]
    assert _envoyes(doublure)[-1] == ARRETER and doublure.position[2] == 0.0


def test_une_lecture_ratee_pendant_un_geste_le_geste_est_dit_rate_et_les_moteurs_sont_arretes():
    for par in ("lire_etat", "tic"):
        liaison, doublure = _liaison(prete=True)
        liaison.geste(TENIR, 1.0)
        _tics(liaison, 0.2)
        doublure.__dict__["alarmes"] = lambda: (_ for _ in ()).throw(ConnectionError("une lecture perdue"))
        if par == "lire_etat":
            with pytest.raises(ConnectionError):
                liaison.lire_etat()  # CE lecteur reçoit l'erreur…
        else:
            liaison.tic()
        del doublure.__dict__["alarmes"]
        etat = liaison.lire_etat()  # …et le suivant lit que le geste est raté (jamais « fini »)
        assert etat["occupe"] is False and "une lecture perdue" in etat["echec_action"], par
        assert _envoyes(doublure)[-1] == ARRETER
        fige = list(doublure.position)
        _tics(liaison, 0.3)
        assert doublure.position == fige and max(fige) < 3500


def test_des_moteurs_coupes_pendant_un_geste_le_geste_est_dit_rate_et_la_main_n_est_plus_preparee():
    liaison, doublure = _liaison(prete=True)
    liaison.geste(TENIR, 1.0)
    _tics(liaison, 0.2)
    doublure.allume = [True, True, True, False, True, True]  # un moteur coupé par ailleurs
    etat = _jouer(liaison)
    assert "ont été coupés pendant le geste" in etat["echec_action"] and liaison._depart_fait is False
    time.sleep(module_liaison.ECHEC_VISIBLE_S)
    assert _refus(lambda: liaison.geste(OUVRIR, 1.0)) == "main_pas_preparee"


def test_une_main_qui_ne_tient_pas_notre_vitesse_est_arretee_et_le_geste_est_dit_rate():
    """Le filet : si la main part à sa vitesse d'origine (20000) au lieu de la nôtre, la liaison le mesure et arrête."""
    liaison, doublure = _liaison(prete=True)
    doublure.vitesse_ignoree = True
    liaison.geste(TENIR, 1.0)
    etat = _jouer(liaison)
    assert "ne tient pas notre vitesse" in etat["echec_action"] and _envoyes(doublure)[-1] == ARRETER
    # HONNÊTEMENT : à cette vitesse, la fausse main est arrivée avant qu'on l'arrête. Le filet dit « raté », il n'empêche pas.
    assert etat["occupe"] is False


def test_si_l_arret_d_un_geste_rate_rate_aussi_c_est_dit_jusqu_au_prochain_arret_reussi():
    liaison, doublure = _liaison(prete=True)
    liaison.geste(TENIR, 1.0)
    doublure.provoquer_alarme(1, 4)
    doublure.__dict__[ARRETER] = lambda: (_ for _ in ()).throw(ConnectionError("câble arraché"))
    liaison.tic()
    etat = liaison.lire_etat()
    assert etat["en_mouvement"] is True and any("n'a pas pu être arrêté" in e for e in etat["erreurs"])
    time.sleep(module_liaison.ECHEC_VISIBLE_S)
    doublure.alarme = [0] * 6
    assert _refus(lambda: liaison.geste(OUVRIR, 1.0)) == "robot_occupe"  # tant que l'alerte est là, rien ne part
    with pytest.raises(ConnectionError):
        liaison.arreter_mouvement()
    assert any("n'a pas pu être arrêté" in e for e in liaison.lire_etat()["erreurs"])  # un arrêt raté n'efface rien
    del doublure.__dict__[ARRETER]
    liaison.arreter_mouvement()
    assert liaison.lire_etat()["erreurs"] == [] and liaison.lire_etat()["en_mouvement"] is False


def test_un_ordre_de_bouger_sans_reponse_fait_arreter_les_moteurs():
    liaison, doublure = _liaison(prete=True)
    doublure.reponse_perdue = {LANCER}  # l'ordre ARRIVE à la main, mais sa réponse se perd
    with pytest.raises(ConnectionError, match="ont été arrêtés"):
        liaison.geste(TENIR, 1.0)
    assert _envoyes(doublure) == [CIBLE] * 6 + [LANCER, ARRETER] and liaison.lire_etat()["occupe"] is False
    fige = list(doublure.position)
    _tics(liaison, 0.3)
    assert doublure.position == fige and max(fige) < 200
    # Et si même l'arrêt de secours rate : c'est dit, et ça reste dit.
    liaison, doublure = _liaison(prete=True)
    doublure.reponse_perdue = {LANCER, ARRETER}
    assert _refus(lambda: liaison.geste(TENIR, 1.0)) == "arret_non_confirme"
    etat = liaison.lire_etat()
    assert etat["en_mouvement"] is True and any("n'a pas pu être arrêté" in e for e in etat["erreurs"])


def test_un_lancement_refuse_par_la_main_est_quand_meme_suivi_d_un_arret_et_le_refus_reste_dit():
    """Relecture, défaut 3. Lu (manuel, lignes 1317 à 1327) : un lancement envoie plusieurs messages. Refusé en route,
    une partie a pu partir : on envoie l'arrêt quand même, sans masquer le refus."""
    liaison, doublure = _liaison(prete=True)
    doublure.refus_a_moitie = True  # refusé, mais trois doigts sont partis quand même
    assert _refus(lambda: liaison.geste(TENIR, 1.0)) == "robot_refuse"  # le refus d'origine, pas autre chose
    assert _envoyes(doublure) == [CIBLE] * 6 + [LANCER, ARRETER]
    fige = list(doublure.position)
    _tics(liaison, 0.3)
    etat = liaison.lire_etat()
    assert doublure.position == fige and max(fige) < 200 and etat["occupe"] is False and etat["erreurs"] == []
    # Si même cet arrêt rate : le refus d'origine reste celui qu'on dit, et l'arrêt raté reste dit dans l'état.
    liaison, doublure = _liaison(prete=True)
    doublure.refus_a_moitie = True
    doublure.__dict__[ARRETER] = lambda: (_ for _ in ()).throw(ConnectionError("câble arraché"))
    assert _refus(lambda: liaison.geste(TENIR, 1.0)) == "robot_refuse"
    etat = liaison.lire_etat()
    assert etat["en_mouvement"] is True and any("l'arrêt envoyé ensuite a raté" in e for e in etat["erreurs"])
    assert _refus(lambda: liaison.geste(OUVRIR, 1.0)) == "robot_occupe"  # rien ne part tant que ce n'est pas arrêté
    # La panne « refus » simple (rien n'est parti) : l'arrêt part quand même.
    liaison, doublure = _liaison(prete=True)
    doublure.provoquer_panne("refus")
    assert _refus(lambda: liaison.geste(TENIR, 1.0)) == "robot_refuse" and _envoyes(doublure)[-2:] == [LANCER, ARRETER]


def test_la_main_qui_dit_elle_meme_pas_preparee_au_lancement_on_la_croit_et_rien_d_autre_ne_part():
    liaison, doublure = _liaison(prete=True)
    doublure.depart_fait = False  # la main a perdu sa mise en position de départ (coupure de courant ?) sans que nous le sachions
    assert _refus(lambda: liaison.geste(TENIR, 1.0)) == "main_pas_preparee"
    assert _envoyes(doublure) == [CIBLE] * 6 + [LANCER] and liaison._depart_fait is False  # lu : refus AVANT tout envoi (à vérifier)
    doublure.appels_du_kit.clear()
    assert _refus(lambda: liaison.geste(OUVRIR, 1.0)) == "main_pas_preparee" and _envoyes(doublure) == []


def test_une_mise_en_position_de_depart_ou_un_allumage_refuses_sont_quand_meme_suivis_d_un_arret(allumage_court):
    liaison, doublure = _liaison(prete=True)  # moteurs déjà allumés : l'ordre part de geste()
    doublure.provoquer_panne("refus")
    assert _refus(lambda: liaison.geste(PREPARER, 1.0)) == "robot_refuse"
    assert _envoyes(doublure) == [*LE_DEPART, ARRETER] and liaison._depart_fait is False
    liaison, doublure = _liaison()  # moteurs coupés : l'allumage est refusé → on recoupe quand même
    doublure.provoquer_panne("refus")
    assert _refus(lambda: liaison.geste(PREPARER, 1.0)) == "robot_refuse"
    assert _envoyes(doublure) == [ALLUMER, COUPER] and liaison._allumes_par_nous is False
    doublure.reparer()
    liaison.geste(PREPARER, 1.0)  # allumés par nous ; puis la mise en position de départ est refusée (elle part de tic())
    doublure.provoquer_panne("refus")
    etat = _jouer(liaison)
    assert "refuse" in etat["echec_action"] and _envoyes(doublure)[-6:] == [ALLUMER, *LE_DEPART, ARRETER, COUPER]
    assert doublure.allume == [False] * 6 and liaison._allumes_par_nous is False


# ================================================================ après le premier essai sur la vraie main (15.11.2026)
def test_avant_la_mise_en_position_de_depart_la_liaison_ecrit_sa_vitesse_et_son_courant_les_plus_grands(allumage_court):
    """Vu sur la vraie main : après un « tenir_doucement » à 150 pour mille, la mise en position de départ n'a plus
    fini. Hypothèse (pas prouvée) : la petite limite de courant était restée dans la main. La fausse main l'imite."""
    liaison, doublure = _liaison(prete=True)
    doublure.courant_min_pour_le_depart = 300  # l'hypothèse : sous 300 pour mille dans la main, le départ ne finit pas
    liaison.geste(TENIR, 1.0)
    assert _jouer(liaison)["echec_action"] is None and doublure.courant_dans_la_main == [150] * 6  # la petite limite est restée
    doublure.appels_du_kit.clear()
    liaison.geste(PREPARER, 1.0)
    assert _envoyes(doublure) == LE_DEPART  # régler, envoyer les réglages, PUIS la mise en position de départ
    assert [valeurs for nom, valeurs in doublure.appels_du_kit if nom == REGLER] == [(VITESSE_MAX, COURANT_MAX)] == [(20000, 1000)]
    etat = _jouer(liaison)
    assert etat["echec_action"] is None and etat["erreurs"] == [] and liaison._depart_fait is True
    assert CIBLE not in _envoyes(doublure) and LANCER not in _envoyes(doublure)  # aucun mouvement lancé pour cela
    # Depuis des moteurs coupés (allumés par nous) : même ordre, après l'attente d'allumage.
    liaison, doublure = _liaison()
    doublure.courant_dans_la_main, doublure.courant_min_pour_le_depart = [150] * 6, 300
    liaison.geste(PREPARER, 1.0)
    assert _jouer(liaison)["echec_action"] is None and _envoyes(doublure) == [ALLUMER, *LE_DEPART]


def test_si_la_main_refuse_nos_reglages_la_mise_en_position_de_depart_part_quand_meme_et_c_est_dit():
    """On ne sait pas si la main accepte ces réglages AVANT sa mise en position de départ. Sur la vraie main, elle a
    réussi sans eux : un refus ne doit donc pas l'empêcher. Il est dit dans l'état, pas caché."""
    liaison, doublure = _liaison(prete=True)
    doublure.refuser_les_reglages = True
    liaison.geste(PREPARER, 1.0)
    assert _envoyes(doublure) == [REGLER, DEPART]  # « envoyer » n'est pas tenté après le refus ; le départ part
    etat = _jouer(liaison)
    assert etat["echec_action"] is None and liaison._depart_fait is True
    assert len(etat["erreurs"]) == 1 and "a refusé nos réglages de vitesse et de courant" in etat["erreurs"][0]
    doublure.refuser_les_reglages = False
    liaison.geste(PREPARER, 1.0)
    assert _jouer(liaison)["erreurs"] == []  # acceptés cette fois : la remarque s'en va
    # Une liaison perdue pendant ces réglages : rien d'autre ne part, et c'est une liaison perdue.
    liaison, doublure = _liaison(prete=True)
    doublure.__dict__[REGLER] = lambda *valeurs: (_ for _ in ()).throw(ConnectionError("câble arraché"))
    with pytest.raises(ConnectionError):
        liaison.geste(PREPARER, 1.0)
    assert _envoyes(doublure) == [] and liaison.lire_etat()["occupe"] is False


@pytest.mark.parametrize("cas", ["etat_colle", "mouvement_qui_s_arrete"])
def test_preparer_envoie_un_arret_avant_de_refuser_une_main_dite_en_mouvement(cas):
    """Vu sur la vraie main le 15.11.2026 : après un geste raté, « prépare la main » était refusé (« la main bouge
    déjà ») jusqu'au redémarrage. Maintenant : un arrêt d'abord, au plus 0,5 s, et on relit."""
    liaison, doublure = _liaison(prete=True)
    if cas == "etat_colle":  # la main se dit encore « en mise en position de départ », mais ses doigts ne bougent pas
        doublure._colle_en_depart = True
        assert liaison.lire_etat()["en_mouvement"] is True and doublure.position == [0.0] * 6
    else:  # un vieux mouvement lent encore en cours : l'arrêt le fige
        doublure.cible, doublure.vitesse_dans_la_main, doublure._en_route = [3000] * 6, [400] * 6, [True] * 6
    for nom in (TENIR, OUVRIR, BOUGER):  # les autres gestes restent refusés, sans rien envoyer
        assert _refus(lambda: liaison.geste(nom, 1.0)) == "robot_occupe"
    assert _envoyes(doublure) == []
    debut = time.monotonic()
    liaison.geste(PREPARER, 1.0)
    duree = time.monotonic() - debut
    assert duree < 1.0  # la méthode rend la main en moins d'une seconde, attente comprise
    assert _envoyes(doublure) == [ARRETER, *LE_DEPART]  # l'arrêt D'ABORD, puis les réglages et le départ
    if cas == "etat_colle":
        assert duree >= 0.5  # l'état est resté collé : on a attendu la demi-seconde entière, doigts MESURÉS immobiles
    etat = _jouer(liaison)
    assert etat["echec_action"] is None and liaison._depart_fait is True and doublure.position == [0.0] * 6
    assert liaison.lire_etat()["en_mouvement"] is False  # la main n'est plus inutilisable
    liaison.geste(TENIR, 1.0)
    assert _jouer(liaison)["echec_action"] is None


def test_preparer_reste_refuse_si_les_doigts_bougent_encore_apres_l_arret():
    """Un autre programme commande la main (le logiciel du fabricant ?) : l'arrêt n'y change rien → refus, rien ne part."""
    liaison, doublure = _liaison(prete=True)
    doublure.cible, doublure.vitesse_dans_la_main, doublure._en_route = [5000] * 6, [400] * 6, [True] * 6
    doublure.provoquer_panne("arret_ignore")  # la main ignore notre arrêt : les doigts continuent
    debut = time.monotonic()
    assert _refus(lambda: liaison.geste(PREPARER, 1.0)) == "robot_occupe"
    assert 0.5 <= time.monotonic() - debut < 1.0
    assert _envoyes(doublure) == [ARRETER] and liaison.lire_etat()["occupe"] is False  # ni réglage, ni départ, ni allumage
    # Et un arrêt d'urgence garde son comportement : refus tout de suite, sans même envoyer cet arrêt-là.
    liaison, doublure = _liaison(prete=True)
    doublure._colle_en_depart = True
    liaison.arret_urgence()
    doublure.appels_du_kit.clear()
    assert _refus(lambda: liaison.geste(PREPARER, 1.0)) == "arret_urgence_actif" and doublure.appels_du_kit == []


@pytest.mark.parametrize("arret", ["arreter_mouvement", "arret_urgence"])
def test_un_arret_qui_passe_pendant_l_attente_avant_de_preparer_et_rien_ne_part(arret):
    liaison, doublure = _liaison(prete=True)
    doublure._colle_en_depart = True
    vraie, deja = doublure.etats, []

    def etats_avec_un_arret_au_milieu():
        rendu = vraie()
        if len(deja) == 1:  # pendant l'attente qui suit NOTRE arrêt (la deuxième lecture des états)
            vars(LiaisonLeadtronDh116)[arret](liaison)  # « l'autre fil »
        deja.append(True)
        return rendu

    doublure.__dict__["etats"] = etats_avec_un_arret_au_milieu
    assert _refus(lambda: liaison.geste(PREPARER, 1.0)) == "arrete"
    _tics(liaison, 0.3)
    for ordre in (ALLUMER, REGLER, DEPART, CIBLE, LANCER):
        assert ordre not in _envoyes(doublure), ordre


def test_un_geste_rate_puis_une_mise_en_position_de_depart_ratee_ne_laissent_pas_la_main_inutilisable(monkeypatch):
    """Le fil du 15.11.2026, rejoué sur la fausse main : un geste raté, une mise en position de départ qui ne finit
    pas, la main reste dite « en mise en position de départ » ; puis « prépare la main » doit de nouveau marcher."""
    monkeypatch.setattr(module_liaison, "DELAI_DEPART_S", 0.6)
    monkeypatch.setattr(module_liaison, "ATTENTE_EN_PLUS_S", 0.3)
    monkeypatch.setattr(module_liaison, "ECHEC_VISIBLE_S", 0.2)
    liaison, doublure = _liaison(prete=True)
    doublure.duree_depart_s = 0.2  # (une mise en position de départ qui marche dure 0,2 s dans cet essai)
    doublure.coinces = {2, 6}  # le pouce (flexion) et l'auriculaire n'avancent pas, comme sur la vraie main
    liaison.geste(TENIR, 1.0)
    assert "pas arrivé à temps" in _jouer(liaison)["echec_action"]
    time.sleep(0.25)
    doublure.coinces = set()
    # La mise en position de départ bloquée (on force l'hypothèse : le courant resté dans la main est trop petit, et
    # la main refuse nos réglages) : elle ne finit pas, et l'état reste collé après l'arrêt.
    doublure.courant_min_pour_le_depart, doublure.depart_colle, doublure.refuser_les_reglages = 300, True, True
    liaison.geste(PREPARER, 1.0)
    assert "n'est pas finie" in _jouer(liaison)["echec_action"]
    time.sleep(0.25)
    assert liaison.lire_etat()["en_mouvement"] is True  # l'état collé : « en mise en position de départ »
    assert _refus(lambda: liaison.geste(TENIR, 1.0)) == "main_pas_preparee"
    doublure.refuser_les_reglages = False  # cette fois nos réglages passent : le courant remonte dans la main
    liaison.geste(PREPARER, 1.0)  # AVANT : refusé « la main bouge déjà », jusqu'au redémarrage
    etat = _jouer(liaison)
    assert etat["echec_action"] is None and liaison._depart_fait is True and liaison.lire_etat()["en_mouvement"] is False
    liaison.geste(TENIR, 1.0)
    assert _jouer(liaison)["echec_action"] is None


# ================================================================ « bouger_les_doigts » (demande de Hiba, 15.11.2026)
def _lancements(doublure) -> int:
    return _envoyes(doublure).count(LANCER)


@pytest.fixture
def bouger_court():
    """(Ne fait plus rien : dans le fichier des essais, « bouger_les_doigts » dure déjà 5 s environ, à la vitesse 5000.)"""


def test_bouger_les_doigts_ferme_et_rouvre_trois_fois_une_etape_a_la_fois():
    liaison, doublure = _liaison(prete=True)
    vraie, ou_etaient_les_doigts = doublure.lancer_le_mouvement, []

    def lancement_note():
        ou_etaient_les_doigts.append([round(p) for p in doublure.position])
        vraie()

    doublure.__dict__[LANCER] = lancement_note
    debut = time.monotonic()
    liaison.geste(BOUGER, 1.0)
    assert time.monotonic() - debut < 1.0 and _lancements(doublure) == 1  # le geste se LANCE : UNE seule étape est partie
    assert liaison.lire_etat()["occupe"] is True
    etat = _jouer(liaison, max_s=20.0)
    duree = time.monotonic() - debut
    assert etat["echec_action"] is None and etat["erreurs"] == [] and etat["occupe"] is False
    assert 6 * 3500 / V_ESSAI <= duree <= 6 * 3500 / V_ESSAI + 2.5, duree  # six fois 0,7 s, plus le temps de voir chaque arrivée
    assert _envoyes(doublure) == ([CIBLE] * 6 + [LANCER]) * 6  # six étapes : six réglages puis UN lancement, six fois
    cibles = _cibles(doublure)
    for morceau in range(6):
        attendu = TENIR_DU_FICHIER if morceau % 2 == 0 else [0] * 6
        courant = 150 if morceau % 2 == 0 else 500  # (les valeurs du fichier des essais)
        assert cibles[6 * morceau:6 * morceau + 6] == [(m, p, V_ESSAI, courant) for m, p in enumerate(attendu, 1)], morceau
    # Jamais deux étapes à la fois : chaque étape est partie quand la précédente était ARRIVÉE.
    assert ou_etaient_les_doigts == [[0] * 6, TENIR_DU_FICHIER] * 3
    assert doublure.position == [0.0] * 6 and doublure.mouvements_lances == 6
    _dans_nos_limites(doublure)


@pytest.mark.parametrize("demandee, vitesse", [(1.0, 5000), (0.5, 2500), (0.25, 1250), (3.0, 5000)])
def test_la_vitesse_demandee_ne_fait_que_ralentir_bouger_les_doigts(demandee, vitesse):
    liaison, doublure = _liaison(prete=True)
    liaison.geste(BOUGER, demandee)
    assert [v for _, _, v, _ in _cibles(doublure)] == [vitesse] * 6 and vitesse <= VITESSE_MAX
    liaison.arreter_mouvement()
    assert _lancements(doublure) == 1


def test_un_geste_trop_ralenti_durerait_plus_de_vingt_cinq_secondes_et_il_est_refuse(tmp_path):
    """La durée est ESTIMÉE avant que rien ne parte : plus de 25 s = refus (l'adaptateur arrête toute action après 30 s)."""
    fichier = tmp_path / "gestes.yaml"
    fichier.write_text(GESTES_DES_ESSAIS.replace("vitesse: 5000", "vitesse: 900"), encoding="utf-8")  # 6 fois 3500 à 900 : 23,3 s + 0,9 s
    liaison, doublure = _liaison(prete=True, gestes=fichier)
    assert 24.0 < liaison._duree_estimee(liaison._variantes(BOUGER)[None], [0] * 6) <= 25.0
    assert _refus(lambda: liaison.geste(BOUGER, 0.9)) == "hors_limites" and _envoyes(doublure) == []  # ralenti : plus de 25 s
    assert _refus(lambda: liaison.geste(BOUGER, 0.5)) == "hors_limites" and _envoyes(doublure) == []
    liaison.geste(BOUGER, 1.0)  # à la vitesse du fichier : accepté
    assert _lancements(doublure) == 1
    liaison.arreter_mouvement()


def test_bouger_les_doigts_avec_un_objet_dans_la_main_un_doigt_arrete_sur_l_objet_compte_comme_arrive(bouger_court):
    liaison, doublure = _liaison(prete=True)
    doublure.objet = {3: 2000, 4: 2100}
    liaison.geste(BOUGER, 1.0)
    etat = _jouer(liaison, max_s=12.0)
    assert etat["echec_action"] is None and _lancements(doublure) == 6 and doublure.position == [0.0] * 6
    # Mais une main qui dit « couple atteint » sans qu'un doigt avance : le morceau est raté, et la suite ne part pas.
    liaison, doublure = _liaison(prete=True)
    doublure.couple_colle, doublure.coinces = True, {1, 2, 3, 4, 5, 6}
    liaison.geste(BOUGER, 1.0)
    etat = _jouer(liaison, max_s=12.0)
    assert "sans avoir avancé" in etat["echec_action"] and _lancements(doublure) == 1


@pytest.mark.parametrize("arret", ["arreter_mouvement", "arret_urgence"])
@pytest.mark.parametrize("apres", [1, 2, 4])
def test_un_arret_au_milieu_de_bouger_les_doigts_et_plus_aucun_morceau_ne_part(arret, apres, bouger_court):
    liaison, doublure = _liaison(prete=True)
    liaison.geste(BOUGER, 1.0)
    fin = time.monotonic() + 10.0
    while _lancements(doublure) < apres and time.monotonic() < fin:
        liaison.tic()
        time.sleep(0.02)
    _tics(liaison, 0.2)  # au milieu du morceau
    assert _lancements(doublure) == apres and len(liaison._geste.file) == 6 - apres
    vars(LiaisonLeadtronDh116)[arret](liaison)
    assert liaison._geste is None  # la file est oubliée avec le geste
    fige = list(doublure.position)
    _tics(liaison, 1.0)
    etat = liaison.lire_etat()
    assert _lancements(doublure) == apres and doublure.position == fige  # plus AUCUN morceau, et les doigts ne bougent plus
    assert etat["occupe"] is False and etat["echec_action"] is None  # un arrêt n'est pas un échec
    if arret == "arret_urgence":
        assert doublure.allume == [False] * 6 and _refus(lambda: liaison.geste(BOUGER, 1.0)) == "arret_urgence_actif"


@pytest.mark.parametrize("arret", ["arreter_mouvement", "arret_urgence"])
def test_un_arret_qui_passe_juste_quand_un_morceau_part_et_les_moteurs_sont_arretes_de_nouveau(arret, bouger_court):
    liaison, doublure = _liaison(prete=True)
    vraie, compte = doublure.lancer_le_mouvement, []

    def lancement_avec_un_arret_juste_avant():
        compte.append(True)
        if len(compte) == 3:  # au troisième morceau, lancé depuis tic()
            vars(LiaisonLeadtronDh116)[arret](liaison)  # l'arrêt de « l'autre fil » arrive AVANT notre ordre
        vraie()

    doublure.__dict__[LANCER] = lancement_avec_un_arret_juste_avant
    liaison.geste(BOUGER, 1.0)
    _tics(liaison, 3.0)
    envoyes = _envoyes(doublure)
    assert envoyes.count(LANCER) == 3 and ARRETER in envoyes[len(envoyes) - envoyes[::-1].index(LANCER):]  # arrêté APRÈS
    fige = list(doublure.position)
    _tics(liaison, 0.5)
    etat = liaison.lire_etat()
    assert doublure.position == fige and max(fige) < 300 and _lancements(doublure) == 3
    assert etat["occupe"] is False and etat["echec_action"] is None


@pytest.mark.parametrize("arret", ["arreter_mouvement", "arret_urgence"])
def test_un_arret_fini_juste_avant_qu_un_morceau_parte_et_ce_morceau_ne_part_pas(arret, bouger_court):
    """L'arrêt passe ET FINIT pendant que tic() vérifie l'arrivée du morceau d'avant (entre la lecture et l'envoi) :
    le morceau suivant ne doit pas partir. C'est la génération lue au DÉBUT du geste qui le dit."""
    liaison, doublure = _liaison(prete=True)
    vraie, deja = doublure.couples_atteints, []

    def lecture_avec_un_arret_au_milieu():
        rendu = vraie()
        if not deja and _lancements(doublure) == 2 and all(doublure.cibles_atteintes()):  # le 2e morceau vient d'arriver
            deja.append(True)
            vars(LiaisonLeadtronDh116)[arret](liaison)  # « l'autre fil » : l'arrêt passe, et il est fini
        return rendu

    doublure.__dict__["couples_atteints"] = lecture_avec_un_arret_au_milieu
    liaison.geste(BOUGER, 1.0)
    _tics(liaison, 3.0)
    assert deja and _lancements(doublure) == 2 and liaison._arrets_en_cours == 0  # le troisième morceau n'est jamais parti
    etat = liaison.lire_etat()
    assert etat["occupe"] is False and etat["echec_action"] is None and doublure.position == [0.0] * 6


@pytest.mark.parametrize("panne", ["alarme", "doigt_bloque", "refus", "moteurs_coupes", "lecture_ratee"])
def test_un_morceau_rate_de_bouger_les_doigts_le_geste_est_dit_rate_et_la_suite_ne_part_pas(panne, bouger_court, monkeypatch):
    monkeypatch.setattr(module_liaison, "ATTENTE_EN_PLUS_S", 0.3)
    liaison, doublure = _liaison(prete=True)
    liaison.geste(BOUGER, 1.0)
    fin = time.monotonic() + 10.0
    while _lancements(doublure) < 2 and time.monotonic() < fin:  # le premier morceau réussit ; on casse pendant le deuxième
        liaison.tic()
        time.sleep(0.02)
    _tics(liaison, 0.2)
    if panne == "alarme":
        doublure.provoquer_alarme(3, 8)
    elif panne == "doigt_bloque":
        doublure.coinces = {5}
    elif panne == "refus":
        doublure.provoquer_panne("refus")  # la main refusera le lancement du troisième morceau
    elif panne == "moteurs_coupes":
        doublure.allume = [False] * 6
    else:
        doublure.__dict__["etats"] = lambda: (_ for _ in ()).throw(ConnectionError("une lecture perdue"))
        liaison.tic()
        del doublure.__dict__["etats"]
    etat = _jouer(liaison, max_s=10.0)
    assert etat["occupe"] is False and etat["echec_action"] is not None and "bouger_les_doigts" in etat["echec_action"], panne
    lances = _lancements(doublure)
    assert lances == (3 if panne == "refus" else 2)  # (le lancement refusé est arrivé à la main, qui a dit non)
    assert _envoyes(doublure)[-1] in (ARRETER, COUPER)
    fige = list(doublure.position)
    _tics(liaison, 0.8)
    assert _lancements(doublure) == lances and doublure.position == fige  # plus rien ne part, plus rien ne bouge
    assert _refus(lambda: liaison.geste(BOUGER, 1.0)) in ("robot_occupe", "main_pas_preparee", "alarme")


# ================================================================ fermer (relecture, défaut 4)
def test_fermer_coupe_les_moteurs_si_c_est_nous_qui_les_avons_allumes(allumage_court):
    """Un Ctrl+C ou une erreur après « preparer_la_main » laissait les moteurs ALLUMÉS. Décision : fermer() les coupe."""
    liaison, doublure = _liaison()
    liaison.geste(PREPARER, 1.0)
    assert liaison._allumes_par_nous is True
    assert _jouer(liaison)["echec_action"] is None and doublure.allume == [True] * 6 and liaison._depart_fait is True
    liaison.arreter_mouvement()  # ce que fait l'adaptateur juste avant de fermer
    liaison.fermer()
    assert _envoyes(doublure) == [ALLUMER, *LE_DEPART, ARRETER, COUPER] and doublure.appels_du_kit[-1][0] == "fermer"
    assert doublure.allume == [False] * 6 and doublure.reliee is False
    assert liaison._depart_fait is False and liaison._allumes_par_nous is False
    liaison.ouvrir()  # rouverte : la main n'est plus dite préparée
    assert _refus(lambda: liaison.geste(TENIR, 1.0)) == "main_pas_preparee"
    # Fermer AU MILIEU de l'attente d'allumage (Ctrl+C tout de suite après l'ordre) : coupés aussi.
    liaison, doublure = _liaison()
    liaison.geste(PREPARER, 1.0)
    liaison.fermer()
    assert _envoyes(doublure) == [ALLUMER, COUPER] and doublure.allume == [False] * 6


def test_fermer_ne_coupe_pas_des_moteurs_allumes_par_un_autre_et_une_coupure_ratee_n_empeche_pas_de_fermer(allumage_court):
    liaison, doublure = _liaison(prete=True)  # moteurs allumés par un AUTRE programme (le logiciel du fabricant)
    liaison.geste(OUVRIR, 1.0)
    _jouer(liaison)
    liaison.fermer()
    assert COUPER not in _envoyes(doublure) and doublure.allume == [True] * 6 and liaison._depart_fait is False
    # Déjà coupés par l'arrêt d'urgence : fermer() ne coupe pas une seconde fois.
    liaison, doublure = _liaison()
    liaison.geste(PREPARER, 1.0)
    liaison.arret_urgence()
    liaison.fermer()
    assert _envoyes(doublure).count(COUPER) == 1 and doublure.allume == [False] * 6
    # La coupure rate (liaison tombée) : fermer() ne lève pas d'erreur, et ferme quand même.
    liaison, doublure = _liaison()
    liaison.geste(PREPARER, 1.0)
    doublure.__dict__[COUPER] = lambda: (_ for _ in ()).throw(ConnectionError("câble arraché"))
    liaison.fermer()
    assert doublure.reliee is False and liaison._depart_fait is False


# ================================================================ s'arrêter
def test_l_arret_normal_arrete_les_moteurs_puis_verifie_et_ne_les_coupe_pas():
    liaison, doublure = _liaison(prete=True)
    liaison.geste(TENIR, 1.0)
    _tics(liaison, 0.3)
    debut = time.monotonic()
    liaison.arreter_mouvement()
    assert time.monotonic() - debut < 1.0
    assert _envoyes(doublure) == [CIBLE] * 6 + [LANCER, ARRETER] and doublure.allume == [True] * 6
    fige = list(doublure.position)
    assert 0 < max(fige) < 3500
    _tics(liaison, 0.3)
    etat = liaison.lire_etat()
    assert doublure.position == fige and _envoyes(doublure)[-1] == ARRETER
    assert etat["occupe"] is False and etat["echec_action"] is None and etat["en_mouvement"] is False  # un arrêt n'est pas un échec
    assert liaison._depart_fait is True  # après un arrêt NORMAL, la main reste préparée
    liaison.geste(OUVRIR, 1.0)
    assert _jouer(liaison)["echec_action"] is None and doublure.position == [0.0] * 6


def test_l_arret_normal_sans_rien_en_cours_envoie_quand_meme_l_arret():
    liaison, doublure = _liaison()
    liaison.arreter_mouvement()
    assert _envoyes(doublure) == [ARRETER] and doublure.allume == [False] * 6


@pytest.mark.parametrize("glisse_s, panne, confirme", [(0.0, None, True), (0.3, None, True), (20.0, None, False),
                                                       (0.0, "arret_ignore", False)])
def test_l_arret_normal_dit_quand_il_n_est_pas_confirme_et_rend_la_main_en_moins_d_une_seconde(glisse_s, panne, confirme):
    liaison, doublure = _liaison(prete=True)
    doublure.glisse_s = glisse_s  # après l'arrêt, les doigts glissent encore (inventé : à vérifier sur la vraie main)
    liaison.geste(TENIR, 0.25)  # au quart de la vitesse : les doigts sont encore loin de leur cible une seconde plus tard
    _tics(liaison, 0.2)
    if panne:
        doublure.provoquer_panne(panne)  # la main ignore l'arrêt logiciel : les doigts continuent
    debut = time.monotonic()
    if confirme:
        liaison.arreter_mouvement()
    else:
        assert _refus(liaison.arreter_mouvement) == "arret_non_confirme"
    assert time.monotonic() - debut < 1.0 and liaison._arrets_en_cours == 0
    assert module_liaison.BUDGET_ARRET_S + module_liaison.ENTRE_DEUX_LECTURES_S < 1.0
    assert liaison.lire_etat()["occupe"] is False


def test_un_arret_impossible_a_envoyer_est_dit():
    liaison, doublure = _liaison(prete=True)
    doublure.provoquer_panne("coupure")
    with pytest.raises(ConnectionError):
        liaison.arreter_mouvement()
    with pytest.raises(ConnectionError):
        liaison.arret_urgence()
    assert liaison._arrets_en_cours == 0 and liaison._urgence is True


def test_l_arret_d_urgence_propose_arrete_puis_coupe_les_moteurs():
    liaison, doublure = _liaison(prete=True)
    liaison.geste(TENIR, 1.0)
    _tics(liaison, 0.3)
    debut = time.monotonic()
    liaison.arret_urgence()
    assert time.monotonic() - debut < 0.3  # l'adaptateur ne l'attend pas plus de 0,3 s
    assert _envoyes(doublure) == [CIBLE] * 6 + [LANCER, ARRETER, COUPER]  # arrêter D'ABORD, couper ENSUITE
    assert doublure.allume == [False] * 6 and liaison._urgence is True and liaison._depart_fait is False
    fige = list(doublure.position)
    _tics(liaison, 0.3)
    etat = liaison.lire_etat()
    assert doublure.position == fige and 0 < max(fige) < 3500 and _envoyes(doublure)[-1] == COUPER
    assert etat["occupe"] is False and etat["en_mouvement"] is False and etat["echec_action"] is None


def test_la_coupure_part_meme_si_l_arret_rate_et_un_echec_est_dit():
    liaison, doublure = _liaison(prete=True)
    doublure.__dict__[ARRETER] = lambda: (_ for _ in ()).throw(ConnectionError("arrêt perdu"))
    with pytest.raises(ConnectionError, match="arrêt perdu"):
        liaison.arret_urgence()
    assert _envoyes(doublure) == [COUPER] and doublure.allume == [False] * 6  # la coupure est partie quand même
    liaison, doublure = _liaison(prete=True)
    doublure.__dict__[COUPER] = lambda: (_ for _ in ()).throw(ConnectionError("coupure perdue"))
    with pytest.raises(ConnectionError, match="coupure perdue"):
        liaison.arret_urgence()
    assert _envoyes(doublure) == [ARRETER] and liaison._urgence is True and liaison._arrets_en_cours == 0


def test_apres_un_arret_d_urgence_rien_ne_part_avant_qu_un_humain_rearme_et_rearmer_n_envoie_rien():
    liaison, doublure = _liaison(prete=True)
    liaison.arret_urgence()
    doublure.appels_du_kit.clear()
    for nom in GESTES:
        assert _refus(lambda: liaison.geste(nom, 1.0)) == "arret_urgence_actif"
    _tics(liaison, 0.2)
    assert doublure.appels_du_kit == []  # pas même une lecture : le refus vient avant tout
    liaison.rearmer()
    assert doublure.appels_du_kit == [] and doublure.allume == [False] * 6  # réarmer n'envoie RIEN : moteurs toujours coupés
    for nom in (TENIR, OUVRIR):  # réarmée, mais plus préparée : seul « preparer_la_main » est permis
        assert _refus(lambda: liaison.geste(nom, 1.0)) == "main_pas_preparee"
    assert _envoyes(doublure) == []
    liaison.geste(PREPARER, 1.0)
    assert _envoyes(doublure) == [ALLUMER]
    liaison.arreter_mouvement()


@pytest.mark.parametrize("arret", ["arreter_mouvement", "arret_urgence"])
@pytest.mark.parametrize("nom", GESTES)
def test_un_arret_qui_passe_pendant_les_verifications_empeche_l_ordre_de_partir(arret, nom):
    """L'arrêt d'urgence part dans un fil à part ; il peut passer pendant que geste() lit l'état de la main.
    L'ordre ne doit PAS partir après lui."""
    liaison, doublure = _liaison(prete=True)
    doublure.allume = [nom != PREPARER] * 6  # pour « preparer_la_main » : moteurs coupés, il voudra les allumer
    vraie, deja = doublure.moteurs_allumes, []

    def lecture_avec_un_arret_au_milieu():
        rendu = vraie()
        if not deja:  # la dernière des quatre lectures avant l'envoi
            deja.append(True)
            vars(LiaisonLeadtronDh116)[arret](liaison)  # « l'autre fil »
        return rendu

    doublure.__dict__["moteurs_allumes"] = lecture_avec_un_arret_au_milieu
    assert _refus(lambda: liaison.geste(nom, 1.0)) in ("arrete", "main_pas_preparee")
    _tics(liaison, 0.3)
    for ordre in (ALLUMER, REGLER, DEPART, CIBLE, LANCER):
        assert ordre not in _envoyes(doublure), ordre
    assert liaison.lire_etat()["occupe"] is False and doublure.position == [0.0] * 6


@pytest.mark.parametrize("arret", ["arreter_mouvement", "arret_urgence"])
def test_un_arret_qui_passe_pendant_les_reglages_empeche_le_lancement(arret):
    liaison, doublure = _liaison(prete=True)
    vraie = doublure.donner_une_cible

    def reglage_avec_un_arret_au_milieu(*valeurs):
        vraie(*valeurs)
        if valeurs[0] == 3:  # après le troisième des six réglages
            vars(LiaisonLeadtronDh116)[arret](liaison)

    doublure.__dict__[CIBLE] = reglage_avec_un_arret_au_milieu
    assert _refus(lambda: liaison.geste(TENIR, 1.0)) == "arrete"
    _tics(liaison, 0.3)
    assert len(_cibles(doublure)) == 3 and LANCER not in _envoyes(doublure) and doublure.position == [0.0] * 6


@pytest.mark.parametrize("arret", ["arreter_mouvement", "arret_urgence"])
def test_un_arret_qui_passe_pendant_le_lancement_fait_arreter_de_nouveau_apres_l_ordre(arret):
    liaison, doublure = _liaison(prete=True)
    vraie = doublure.lancer_le_mouvement

    def lancement_avec_un_arret_juste_avant():
        vars(LiaisonLeadtronDh116)[arret](liaison)  # l'arrêt de « l'autre fil » arrive à la main AVANT notre ordre…
        vraie()  # …et notre ordre arrive après lui : la main repart

    doublure.__dict__[LANCER] = lancement_avec_un_arret_juste_avant
    assert _refus(lambda: liaison.geste(TENIR, 1.0)) == "arrete"
    envoyes = _envoyes(doublure)
    assert envoyes.index(LANCER) < len(envoyes) - 1 and ARRETER in envoyes[envoyes.index(LANCER) + 1:]  # arrêté APRÈS notre ordre
    if arret == "arret_urgence":
        assert COUPER in envoyes[envoyes.index(LANCER) + 1:] and doublure.allume == [False] * 6
    fige = list(doublure.position)
    _tics(liaison, 0.3)
    assert doublure.position == fige and max(fige) < 200 and liaison.lire_etat()["occupe"] is False


@pytest.mark.parametrize("arret", ["arreter_mouvement", "arret_urgence"])
def test_un_arret_qui_passe_pendant_l_allumage_fait_recouper_les_moteurs(arret, allumage_court):
    liaison, doublure = _liaison()
    vraie = doublure.allumer_les_moteurs

    def allumage_avec_un_arret_juste_avant():
        vars(LiaisonLeadtronDh116)[arret](liaison)  # l'arrêt (et sa coupure) arrivent AVANT notre ordre d'allumer…
        vraie()  # …et notre ordre rallume

    doublure.__dict__[ALLUMER] = allumage_avec_un_arret_juste_avant
    assert _refus(lambda: liaison.geste(PREPARER, 1.0)) == "arrete"
    assert _envoyes(doublure)[-2:] == [ALLUMER, COUPER] and doublure.allume == [False] * 6
    _tics(liaison, 0.4)
    assert doublure.departs_lances == 0 and liaison.lire_etat()["occupe"] is False


@pytest.mark.parametrize("arret", ["arreter_mouvement", "arret_urgence"])
@pytest.mark.parametrize("moteurs_allumes", [True, False])
def test_un_arret_qui_passe_pendant_l_envoi_de_la_mise_en_position_de_depart_la_fait_arreter(arret, moteurs_allumes, allumage_court):
    """Les deux chemins : moteurs déjà allumés (l'ordre part de geste()), ou allumés par nous (l'ordre part de tic())."""
    liaison, doublure = _liaison(prete=moteurs_allumes)
    doublure.position, doublure.duree_depart_s = [3000.0] * 6, 3.0
    vraie = doublure.mise_en_position_de_depart

    def depart_avec_un_arret_juste_avant():
        vars(LiaisonLeadtronDh116)[arret](liaison)  # l'arrêt de « l'autre fil » arrive à la main AVANT notre ordre…
        if arret == "arret_urgence":
            doublure.allume = [True] * 6  # (pour l'essai : sinon la fausse main, moteurs coupés, refuserait notre ordre)
        vraie()  # …et notre ordre arrive après lui : la main repart

    doublure.__dict__[DEPART] = depart_avec_un_arret_juste_avant
    if moteurs_allumes:
        assert _refus(lambda: liaison.geste(PREPARER, 1.0)) == "arrete"
    else:
        liaison.geste(PREPARER, 1.0)
        _tics(liaison, 0.4)
    envoyes = _envoyes(doublure)
    assert ARRETER in envoyes[envoyes.index(DEPART) + 1:]  # arrêtée APRÈS notre ordre
    if arret == "arret_urgence":
        assert COUPER in envoyes[envoyes.index(DEPART) + 1:] and doublure.allume == [False] * 6
    fige = list(doublure.position)
    _tics(liaison, 0.4)
    etat = liaison.lire_etat()
    assert doublure.position == fige and min(fige) > 2000 and liaison._depart_fait is False
    assert etat["occupe"] is False and etat["echec_action"] is None  # un arrêt n'est pas un échec


@pytest.mark.parametrize("arret", ["arreter_mouvement", "arret_urgence"])
def test_un_arret_pendant_l_attente_d_allumage_et_la_mise_en_position_de_depart_ne_part_jamais(arret, allumage_court):
    liaison, doublure = _liaison()
    liaison.geste(PREPARER, 1.0)
    vars(LiaisonLeadtronDh116)[arret](liaison)
    _tics(liaison, 0.5)
    assert doublure.departs_lances == 0 and DEPART not in _envoyes(doublure) and liaison._depart_fait is False
    etat = liaison.lire_etat()
    assert etat["occupe"] is False and etat["echec_action"] is None


@pytest.mark.parametrize("arret", ["arreter_mouvement", "arret_urgence"])
def test_un_arret_pendant_la_mise_en_position_de_depart_et_la_main_n_est_pas_dite_preparee(arret):
    liaison, doublure = _liaison(prete=True)
    doublure.position, doublure.duree_depart_s = [3000.0] * 6, 3.0
    liaison.geste(PREPARER, 1.0)
    _tics(liaison, 0.2)
    vars(LiaisonLeadtronDh116)[arret](liaison)
    fige = list(doublure.position)
    _tics(liaison, 0.4)
    assert doublure.position == fige and 0 < max(fige) < 3000 and liaison._depart_fait is False
    if arret == "arret_urgence":
        liaison.rearmer()
    assert _refus(lambda: liaison.geste(TENIR, 1.0)) == "main_pas_preparee"


@pytest.mark.parametrize("arret, code", [("arreter_mouvement", "arrete"), ("arret_urgence", "arret_urgence_actif")])
def test_un_ordre_appele_pendant_qu_un_arret_travaille_ne_part_pas(arret, code):
    liaison, doublure = _liaison(prete=True)
    vraie, refus = doublure.arreter_les_moteurs, []

    def arret_avec_un_ordre_au_milieu():
        for nom in GESTES:
            refus.append(_refus(lambda: liaison.geste(nom, 1.0)))  # « l'autre fil » : un ordre PENDANT l'arrêt
        vraie()

    doublure.__dict__[ARRETER] = arret_avec_un_ordre_au_milieu
    vars(LiaisonLeadtronDh116)[arret](liaison)
    assert refus == [code] * len(GESTES) and liaison._arrets_en_cours == 0
    for ordre in (ALLUMER, REGLER, DEPART, CIBLE, LANCER):
        assert ordre not in _envoyes(doublure)


def test_un_vrai_arret_d_urgence_venu_d_un_autre_fil_pendant_un_geste():
    """Un seul essai avec deux VRAIS fils : il ne prouve pas l'absence de course, il montre le cas simple."""
    for _ in range(5):
        liaison, doublure = _liaison(prete=True)
        liaison.geste(TENIR, 1.0)
        fil = threading.Timer(0.15, liaison.arret_urgence)
        fil.start()
        _tics(liaison, 0.5)
        fil.join()
        fige = list(doublure.position)
        _tics(liaison, 0.2)
        assert doublure.position == fige and doublure.allume == [False] * 6 and _envoyes(doublure)[-1] == COUPER
        assert _refus(lambda: liaison.geste(OUVRIR, 1.0)) == "arret_urgence_actif" and liaison.lire_etat()["occupe"] is False


def test_une_main_trop_lente_a_repondre_et_l_ordre_ne_part_pas():
    assert module_liaison.BUDGET_AVANT_ENVOI_S < 0.5
    liaison, doublure = _liaison(prete=True)
    doublure.latence_s = 0.12  # quatre lectures prennent déjà plus de 0,4 s
    assert _refus(lambda: liaison.geste(TENIR, 1.0)) == "trop_lent"
    doublure.allume = [False] * 6
    assert _refus(lambda: liaison.geste(PREPARER, 1.0)) == "trop_lent"
    assert _envoyes(doublure) == []


def test_saisir_poser_et_le_reste_sont_a_brancher_et_rien_ne_part():
    liaison, doublure = _liaison(prete=True)
    for appel in (lambda: liaison.saisir("ours", 5.0), lambda: liaison.poser("ici"), lambda: liaison.montrer("ours"),
                  lambda: liaison.regarder("devant"), lambda: liaison.vitesse(0.1, 0.0, 0.0),
                  lambda: liaison.aller_au_lieu("table", 0.1), lambda: liaison.parler("bonjour", "fr"),
                  lambda: liaison.ecouter(1.0)):
        with pytest.raises(ABrancher):
            appel()
    assert doublure.appels_du_kit == [] and LiaisonLeadtronDh116.branchees == {"arreter", "etat", "rejouer_geste"}


# ================================================================ la carte
def test_la_carte_ne_promet_que_ce_qui_est_branche_pas_saisir_ni_poser_et_garde_zero_partout():
    texte = (ICI / "carte.yaml").read_text(encoding="utf-8")
    carte = CarteIdentite.charger(ICI / "carte.yaml")
    assert carte.capacites == ["arreter", "etat", "rejouer_geste"]
    assert sorted(carte.capacites) == sorted(LiaisonLeadtronDh116.branchees)
    assert not carte.sait("saisir") and not carte.sait("poser")
    assert carte.gestes == list(GESTES) and carte.gestes[0] == PREPARER  # le test de conformité essaie le PREMIER
    assert carte.genre == "autre" and carte.position_fixe == "table"
    limites = carte.limites
    assert (limites.vitesse_max_m_s, limites.portee_max_m, limites.charge_max_kg, limites.force_max_n) == (0, 0, 0, 0)
    assert texte.count("à vérifier") >= 6 and "12 à 24 V" in texte and "48" not in texte


# ================================================================ par l'adaptateur entier
async def _par_l_adaptateur(actions, pendant=None, lecteur_a_cote=False, prete=True):
    """Le chemin de l'ADAPTATEUR (pas la liaison seule, pas la prise) : demarrer, suivre, battement."""
    from briques.b01_prise.actions import ActionDemandee

    adaptateur = ROBOT.fabriquer(vrai=False, acceleration=5)
    await adaptateur.connecter()
    liaison, doublure, resultats = adaptateur._liaison, adaptateur._liaison.kit, []
    if prete:
        doublure.preparer_sans_bouger()
        liaison._depart_fait = True
    try:
        for nom, parametres in actions:
            ident = await adaptateur.demarrer(ActionDemandee(nom=nom, parametres=parametres))
            for tour in range(1500):
                if pendant is not None:
                    pendant(tour, doublure)
                if lecteur_a_cote:
                    try:
                        await adaptateur.etat_robot()  # comme l'écran, qui lit l'état plusieurs fois par seconde
                    except Exception:
                        pass  # l'écran reçoit l'erreur : ce n'est pas l'action qui la reçoit
                suivi = await adaptateur.suivre(ident)
                if suivi.finie:
                    break
                try:
                    await adaptateur.battement()
                except Exception:
                    pass  # un signe de vie raté : la prise le note à part ; ici on regarde seulement ce que devient l'action
                await asyncio.sleep(0.02)
            resultats.append((suivi.statut, suivi.code_erreur))
        await asyncio.sleep(0.3)
        return resultats, doublure
    finally:
        await adaptateur.deconnecter()


def test_par_l_adaptateur_les_trois_gestes_reussissent_sur_la_doublure_dans_nos_limites():
    geste = lambda nom, **plus: ("rejouer_geste", {"nom": nom, **plus})
    resultats, doublure = asyncio.run(_par_l_adaptateur(
        [geste(TENIR), geste(PREPARER), geste(TENIR), geste(OUVRIR, vitesse_relative=0.5), geste("serrer_fort")], prete=False))
    assert resultats == [("echouee", "main_pas_preparee"), ("reussie", None), ("reussie", None), ("reussie", None),
                         ("echouee", "geste_inconnu")]
    assert _envoyes(doublure)[:4] == [ALLUMER, *LE_DEPART] and doublure.mouvements_lances == 2 and doublure.departs_lances == 1
    assert [vitesse for _, _, vitesse, _ in _cibles(doublure)] == [5000] * 6 + [2500] * 6
    _dans_nos_limites(doublure)
    assert doublure.position == [0.0] * 6


def test_par_l_adaptateur_se_deconnecter_apres_preparer_la_main_coupe_les_moteurs():
    """Relecture, défaut 4, par l'adaptateur entier : préparer (nous allumons), puis se déconnecter."""
    resultats, doublure = asyncio.run(_par_l_adaptateur([("rejouer_geste", {"nom": PREPARER})], prete=False))
    assert resultats == [("reussie", None)]
    assert _envoyes(doublure) == [ALLUMER, *LE_DEPART, ARRETER, COUPER] and doublure.allume == [False] * 6 and doublure.reliee is False


def test_par_l_adaptateur_bouger_les_doigts_reussit_et_un_morceau_rate_n_est_jamais_compte_reussi(bouger_court):
    geste = ("rejouer_geste", {"nom": BOUGER})
    resultats, doublure = asyncio.run(_par_l_adaptateur([geste], lecteur_a_cote=True))
    assert resultats == [("reussie", None)] and _lancements(doublure) == 6 and doublure.position == [0.0] * 6
    _dans_nos_limites(doublure)

    def une_alarme_au_troisieme_morceau(tour, doublure):
        if _lancements(doublure) == 3 and not any(doublure.alarme):
            doublure.provoquer_alarme(2, 3)

    for lecteur_a_cote in (False, True):
        resultats, doublure = asyncio.run(_par_l_adaptateur([geste], pendant=une_alarme_au_troisieme_morceau,
                                                            lecteur_a_cote=lecteur_a_cote))
        assert resultats == [("echouee", "action_interrompue")] and _lancements(doublure) == 3


def test_par_l_adaptateur_un_arret_d_urgence_au_milieu_de_bouger_les_doigts_et_plus_aucun_morceau_ne_part(bouger_court):
    async def scenario():
        from briques.b01_prise.actions import ActionDemandee

        adaptateur = ROBOT.fabriquer(vrai=False)
        await adaptateur.connecter()
        liaison, doublure = adaptateur._liaison, adaptateur._liaison.kit
        doublure.preparer_sans_bouger()
        liaison._depart_fait = True
        try:
            ident = await adaptateur.demarrer(ActionDemandee(nom="rejouer_geste", parametres={"nom": BOUGER}))
            for _ in range(200):
                if _lancements(doublure) == 2:
                    break
                await adaptateur.battement()
                await asyncio.sleep(0.02)
            await asyncio.sleep(0.2)
            await adaptateur.arret_urgence()
            await asyncio.sleep(0.3)
            fige, lances = list(doublure.position), _lancements(doublure)
            for _ in range(60):  # 1,2 s de plus : le temps qu'aurait pris le morceau suivant
                await asyncio.sleep(0.02)
            return fige, lances, (await adaptateur.suivre(ident)).statut, doublure
        finally:
            await adaptateur.deconnecter()

    fige, lances, statut, doublure = asyncio.run(scenario())
    assert lances == 2 and _lancements(doublure) == 2 and statut == "annulee"
    assert doublure.position == fige and doublure.allume == [False] * 6 and COUPER in _envoyes(doublure)


def test_par_l_adaptateur_en_mode_lent_les_gestes_vont_a_mi_vitesse():
    async def scenario():
        from briques.b01_prise.actions import ActionDemandee

        adaptateur = ROBOT.fabriquer(vrai=False, lent=True)
        await adaptateur.connecter()
        try:
            adaptateur._liaison.kit.preparer_sans_bouger()
            adaptateur._liaison._depart_fait = True
            await adaptateur.demarrer(ActionDemandee(nom="rejouer_geste", parametres={"nom": TENIR}))
            await asyncio.sleep(0.3)
            return adaptateur._liaison.kit
        finally:
            await adaptateur.deconnecter()

    doublure = asyncio.run(scenario())
    assert [vitesse for _, _, vitesse, _ in _cibles(doublure)] == [2500] * 6 and ARRETER in _envoyes(doublure)


@pytest.mark.parametrize("panne", ["alarme", "doigt_bloque", "moteurs_coupes", "trop_vite", "couple_sans_avancer"])
def test_par_l_adaptateur_un_geste_rate_n_est_jamais_compte_reussi_meme_avec_un_autre_lecteur(panne, monkeypatch):
    monkeypatch.setattr(module_liaison, "ATTENTE_EN_PLUS_S", 0.3)

    def provoquer(tour, doublure):
        if panne == "alarme" and tour == 10:
            doublure.provoquer_alarme(4, 8)
        elif panne == "doigt_bloque" and tour == 0:
            doublure.coinces = {5}
        elif panne == "moteurs_coupes" and tour == 10:
            doublure.allume = [False] * 6
        elif panne == "trop_vite" and tour == 0:
            doublure.vitesse_ignoree = True
        elif panne == "couple_sans_avancer" and tour == 0:  # relecture, défaut GRAVE : « couple atteint » partout, doigts immobiles
            doublure.couple_colle, doublure.coinces = True, {1, 2, 3, 4, 5, 6}

    for lecteur_a_cote in (False, True):
        resultats, doublure = asyncio.run(_par_l_adaptateur([("rejouer_geste", {"nom": TENIR})], pendant=provoquer,
                                                            lecteur_a_cote=lecteur_a_cote))
        assert resultats == [("echouee", "action_interrompue")], (panne, lecteur_a_cote)
        assert ARRETER in _envoyes(doublure)[7:]  # et les moteurs ont été arrêtés après le lancement
        if panne == "couple_sans_avancer":
            assert doublure.position == [0.0] * 6  # aucun doigt n'a bougé : ce n'est PAS « réussie »


def test_par_l_adaptateur_une_lecture_ratee_par_un_autre_lecteur_ne_donne_jamais_reussie():
    """Une seule lecture ratée, à des instants différents, avec l'écran à côté : jamais « réussie » à tort."""
    for instant in (2, 6, 12, 20, 30):
        etat = {"fait": False}

        def une_lecture_ratee(tour, doublure, instant=instant, etat=etat):
            if tour == instant and not etat["fait"]:
                etat["fait"] = True
                vraie, compte = doublure.positions, []

                def positions():
                    if not compte:
                        compte.append(True)
                        raise ConnectionError("une lecture perdue")
                    return vraie()

                doublure.__dict__["positions"] = positions

        resultats, doublure = asyncio.run(_par_l_adaptateur([("rejouer_geste", {"nom": TENIR})],
                                                            pendant=une_lecture_ratee, lecteur_a_cote=True))
        (statut, code), = resultats
        arrivee = [round(p) for p in doublure.position] == TENIR_DU_FICHIER
        # Ou bien l'action est dite ratée, ou bien la main est VRAIMENT arrivée (la lecture ratée était un simple signe
        # de vie, que la prise note à part). Jamais « réussie » avec une main qui n'est pas arrivée.
        assert statut == "echouee" or arrivee, (instant, statut, code, doublure.position)


def test_par_l_adaptateur_un_arret_d_urgence_pendant_un_geste_fige_la_main_et_bloque_tout_jusqu_au_rearmement():
    async def scenario():
        from briques.b01_prise.actions import ActionDemandee

        adaptateur = ROBOT.fabriquer(vrai=False)
        await adaptateur.connecter()
        liaison, doublure = adaptateur._liaison, adaptateur._liaison.kit
        doublure.preparer_sans_bouger()
        liaison._depart_fait = True
        try:
            ident = await adaptateur.demarrer(ActionDemandee(nom="rejouer_geste", parametres={"nom": TENIR}))
            await asyncio.sleep(0.4)
            await adaptateur.arret_urgence()
            await asyncio.sleep(0.3)
            fige, statut = list(doublure.position), (await adaptateur.suivre(ident)).statut
            await asyncio.sleep(0.4)
            with pytest.raises(ActionImpossible) as refus:
                await adaptateur.demarrer(ActionDemandee(nom="rejouer_geste", parametres={"nom": OUVRIR}))
            await adaptateur.rearmer()
            ident = await adaptateur.demarrer(ActionDemandee(nom="rejouer_geste", parametres={"nom": OUVRIR}))
            await asyncio.sleep(0.3)
            apres = await adaptateur.suivre(ident)
            return fige, statut, refus.value.code, (apres.statut, apres.code_erreur), doublure, liaison._urgence
        finally:
            await adaptateur.deconnecter()

    fige, statut, refus, apres, doublure, urgence = asyncio.run(scenario())
    assert statut == "annulee" and refus == "arret_urgence_actif" and urgence is False
    assert doublure.position == fige and 0 < max(fige) < 3500 and doublure.allume == [False] * 6
    assert apres == ("echouee", "main_pas_preparee")  # réarmée, mais plus préparée : il faut « preparer_la_main »
    assert _envoyes(doublure).count(LANCER) == 1 and COUPER in _envoyes(doublure) and ALLUMER not in _envoyes(doublure)


def test_la_conformite_reussit_avec_la_doublure_et_la_vraie_liaison_et_dit_faux_robot():
    adaptateur = ROBOT.fabriquer(vrai=False, acceleration=5)
    assert type(adaptateur._liaison) is LiaisonLeadtronDh116
    assert type(adaptateur._liaison.kit) is DoublureLeadtronDh116 and adaptateur._liaison.vrai_robot is False
    assert sur_faux_kit(adaptateur) and adaptateur.carte().vrai_robot is False
    assert adaptateur.carte().mention_test() == "testé sur faux robot"
    for temps in (conformite.sans_mouvement, conformite.complet):
        rapport = asyncio.run(temps(lambda: ROBOT.fabriquer(vrai=False, acceleration=5), vrai_attendu=False))
        assert rapport.reussi, rapport.texte()
        assert rapport.mention == "testé sur faux robot"
    assert "action « rejouer_geste »" in rapport.texte()  # le premier geste, « preparer_la_main », a bien été essayé


# ================================================================ les gestes du fichier (décision de Hiba, 15.11.2026)
# Ces essais jouent la COPIE FIGÉE du fichier d'origine (tests/gestes_d_essai.yaml), sur la fausse main. Aucun de ces
# gestes n'est essayé sur la vraie main.
POING, VICTOIRE, PFC = "poing", "victoire", "pierre_feuille_ciseaux"
# La forme finale attendue de chaque geste : pouce (écartement), pouce (flexion), index, majeur, annulaire, auriculaire ;
# et le nombre d'étapes. Valeurs de départ, pas mesurées sur la vraie main.
FORMES = {
    OUVRIR: ([0, 0, 0, 0, 0, 0], 1),
    TENIR: ([5000, 5000, 6000, 6000, 6000, 6000], 1),
    "attraper": ([7000, 7000, 8500, 8500, 8500, 8500], 2),
    BOUGER: ([0, 0, 0, 0, 0, 0], 6),
    POING: ([8000, 8000, 10000, 10000, 10000, 10000], 2),
    VICTOIRE: ([8000, 8000, 0, 0, 10000, 10000], 2),
    "pouce_leve": ([0, 0, 10000, 10000, 10000, 10000], 1),
    "pointer": ([8000, 8000, 0, 10000, 10000, 10000], 2),
    "rock": ([8000, 8000, 0, 10000, 10000, 0], 2),
    "je_t_aime": ([0, 0, 0, 10000, 10000, 0], 1),
    "compter": ([0, 0, 0, 0, 0, 0], 7),
    "vague": ([0, 0, 0, 0, 0, 0], 16),
}


def _figee(prete: bool = True):
    return _liaison(prete=prete, gestes=COPIE_FIGEE)


def test_la_carte_la_liaison_et_la_copie_figee_ont_les_memes_quatorze_gestes_dans_le_meme_ordre():
    carte = CarteIdentite.charger(ICI / "carte.yaml")
    attendus = ["preparer_la_main", "ouvrir_la_main", "tenir_doucement", "attraper", "bouger_les_doigts", "poing", "victoire",
                "pouce_leve", "pointer", "rock", "je_t_aime", "compter", "vague", "pierre_feuille_ciseaux"]
    assert carte.gestes == attendus == list(GESTES) and carte.gestes[0] == PREPARER  # le test de conformité essaie le PREMIER
    assert set(FORMES) | {PFC, PREPARER} == set(GESTES)
    assert list(yaml.safe_load(COPIE_FIGEE.read_text(encoding="utf-8"))["gestes"]) == attendus[1:]


@pytest.mark.parametrize("nom", list(FORMES))
def test_chaque_geste_de_la_carte_se_joue_en_entier_sur_la_fausse_main_et_finit_dans_la_forme_attendue(nom):
    forme, etapes = FORMES[nom]
    liaison, doublure = _figee()
    if nom == OUVRIR:
        doublure.position = [8000.0, 8000.0, 10000.0, 10000.0, 10000.0, 10000.0]  # on part du poing
    prevue = liaison._duree_estimee(liaison._variantes(nom)[None], [round(p) for p in doublure.position])
    debut = time.monotonic()
    liaison.geste(nom, 1.0)
    assert time.monotonic() - debut < 1.0  # le geste se LANCE : la méthode rend la main tout de suite
    etat = _jouer(liaison, max_s=30.0)
    duree = time.monotonic() - debut
    assert etat["echec_action"] is None and etat["erreurs"] == [] and etat["occupe"] is False, nom
    assert [round(p) for p in doublure.position] == forme, nom
    assert _lancements(doublure) == etapes and _envoyes(doublure) == ([CIBLE] * 6 + [LANCER]) * etapes
    assert duree <= prevue + 0.5 + 0.2 * etapes and prevue <= module_liaison.DUREE_MAX_GESTE_S, (nom, duree, prevue)
    _dans_nos_limites(doublure)
    assert etat["dernier_tirage"] is None and liaison.lire_etat()["en_mouvement"] is False


def test_attraper_le_doudou_les_doigts_s_arretent_dessus_a_pleine_force_et_c_est_reussi():
    liaison, doublure = _figee()
    doublure.objet = {1: 4000, 2: 4500, 3: 5000, 4: 5200, 5: 5400, 6: 6000}  # le doudou : chaque doigt le touche avant sa cible
    liaison.geste("attraper", 1.0)
    etat = _jouer(liaison)
    assert etat["echec_action"] is None and [round(p) for p in doublure.position] == [4000, 4500, 5000, 5200, 5400, 6000]
    assert {courant for _, _, _, courant in _cibles(doublure)} == {1000}  # toute la force (valeur des exemples du fabricant)
    assert [position for _, position, _, _ in _cibles(doublure)[:6]] == [0, 0, 8500, 8500, 8500, 8500]  # les doigts d'abord, le pouce ensuite


@pytest.mark.parametrize("tirage, forme", [("poing", [8000, 8000, 10000, 10000, 10000, 10000]), ("ouvrir_la_main", [0] * 6),
                                           ("victoire", [8000, 8000, 0, 0, 10000, 10000])])
def test_pierre_feuille_ciseaux_trois_battements_puis_la_forme_tiree_et_le_tirage_se_lit_dans_l_etat(tirage, forme):
    liaison, doublure = _figee()
    proposes = []

    def tirer(choix):
        proposes.append(list(choix))
        return tirage

    liaison.tirer_au_hasard = tirer  # le hasard est fixé pour l'essai
    assert liaison.lire_etat()["dernier_tirage"] is None
    liaison.geste(PFC, 1.0)
    assert liaison.lire_etat()["dernier_tirage"] == tirage  # lisible dès que le geste est parti
    etat = _jouer(liaison)
    assert etat["echec_action"] is None and [round(p) for p in doublure.position] == forme
    assert proposes == [["poing", "ouvrir_la_main", "victoire"]]  # UN seul tirage, parmi pierre, feuille, ciseaux
    battements = [position for moteur, position, _, _ in _cibles(doublure) if moteur == 3][:6]
    assert battements == [4000, 0, 4000, 0, 4000, 0]  # trois petits battements d'abord
    assert etat["dernier_tirage"] == tirage and liaison.lire_etat()["dernier_tirage"] == tirage  # et il reste lisible après coup
    liaison.geste(POING, 1.0)  # un geste sans hasard ne l'efface pas
    assert _jouer(liaison)["dernier_tirage"] == tirage


def test_le_hasard_de_pierre_feuille_ciseaux_est_un_vrai_hasard_qu_on_peut_fixer_par_une_graine():
    tirages = []
    for graine in (1, 1, 2, 3, 4, 5, 6, 7):
        liaison, doublure = _figee()
        liaison.tirer_au_hasard = random.Random(graine).choice
        liaison.geste(PFC, 1.0)
        tirages.append(liaison.lire_etat()["dernier_tirage"])
        liaison.arreter_mouvement()
    assert tirages[0] == tirages[1]  # même graine, même tirage
    assert set(tirages) <= {"poing", "ouvrir_la_main", "victoire"} and len(set(tirages)) >= 2
    liaison, doublure = _figee()  # sans rien fixer : le hasard par défaut tire dans la liste
    liaison.geste(PFC, 1.0)
    assert liaison.lire_etat()["dernier_tirage"] in ("poing", "ouvrir_la_main", "victoire")
    liaison.arreter_mouvement()
    # Un tirage qui rend autre chose que la liste : refus, rien ne part, et l'état ne dit pas un faux tirage.
    liaison, doublure = _figee()
    liaison.tirer_au_hasard = lambda choix: "serrer_tres_fort"
    assert _refus(lambda: liaison.geste(PFC, 1.0)) == "geste_illisible"
    assert _envoyes(doublure) == [] and liaison.lire_etat()["dernier_tirage"] is None
    # Un geste refusé (main pas préparée) ne tire rien et ne dit pas de tirage.
    liaison, doublure = _figee(prete=False)
    liaison.tirer_au_hasard = lambda choix: (_ for _ in ()).throw(AssertionError("aucun tirage ne devait être fait"))
    assert _refus(lambda: liaison.geste(PFC, 1.0)) == "main_pas_preparee" and liaison.lire_etat()["dernier_tirage"] is None


def test_la_pause_apres_une_etape_est_tenue_et_la_main_reste_occupee_pendant_la_pause(tmp_path):
    fichier = tmp_path / "gestes.yaml"
    fichier.write_text(BON_FICHIER.replace("auriculaire: 3500}}", "auriculaire: 3500}, pause_s: 0.6}\n" + UNE_ETAPE.rstrip("\n")
                                           .replace("index: 3500", "index: 1000")[:-1] + ", pause_s: 0.5}"), encoding="utf-8")
    liaison, doublure = _liaison(prete=True, gestes=fichier)
    debut = time.monotonic()
    liaison.geste(TENIR, 1.0)
    etat = _jouer(liaison)
    duree = time.monotonic() - debut
    heures = [heure for heure, nom in doublure.journal if nom == LANCER]
    assert etat["echec_action"] is None and len(heures) == 2
    assert heures[1] - heures[0] >= 3500 / V_ESSAI + 0.6  # l'étape suivante part APRÈS l'arrivée, puis après la pause de 0,6 s
    assert duree >= 3500 / V_ESSAI + 0.6 + 2500 / V_ESSAI + 0.5  # la pause de la dernière étape est tenue aussi
    assert round(doublure.position[2]) == 1000
    # Un arrêt PENDANT une pause : l'étape suivante ne part jamais.
    liaison, doublure = _liaison(prete=True, gestes=fichier)
    liaison.geste(TENIR, 1.0)
    _tics(liaison, 3500 / V_ESSAI + 0.3)
    assert liaison._geste.phase == "pause" and liaison.lire_etat()["occupe"] is True
    liaison.arreter_mouvement()
    _tics(liaison, 1.0)
    assert _lancements(doublure) == 1 and liaison.lire_etat()["occupe"] is False


# ESSAI SENSIBLE AU TEMPS, CONNU : sur une machine chargée, il échoue environ une fois sur trois (vu le 16.11.2026 : 2 échecs sur 5).
# La cause est écrite dans NON_TESTE.md (relecture de la main, point 4) : le filet « trop vite » compte le chemin fait pendant
# l'envoi de l'ordre, et la « vague » peut alors être dite ratée à tort. La liaison n'est PAS corrigée ici : c'est la version
# essayée sur la vraie main, et la changer oblige à refaire le test sur la vraie main.
@pytest.mark.xfail(strict=False, reason="essai sensible au temps : la vague peut être dite ratée à tort sur une machine chargée (NON_TESTE.md)")
def test_la_vague_les_doigts_partent_l_un_apres_l_autre_sans_attendre_et_tout_est_verifie_a_la_fin():
    liaison, doublure = _figee()
    vraie, ou_etaient_les_doigts = doublure.lancer_le_mouvement, []

    def lancement_note():
        ou_etaient_les_doigts.append([round(p) for p in doublure.position])
        vraie()

    doublure.__dict__[LANCER] = lancement_note
    liaison.geste("vague", 1.0)
    _jouer_sans_fin = _jouer(liaison, max_s=30.0)
    assert _jouer_sans_fin["echec_action"] is None and len(ou_etaient_les_doigts) == 16
    heures = [heure for heure, nom in doublure.journal if nom == LANCER]
    for etape in (1, 2, 3):  # les trois doigts suivants partent 0,15 s environ après le précédent, sans attendre son arrivée
        assert 0.15 <= heures[etape] - heures[etape - 1] < 0.45, etape
        assert 0 < ou_etaient_les_doigts[etape][5] < 10000  # l'auriculaire est encore EN ROUTE quand le doigt suivant part
    assert ou_etaient_les_doigts[4] == [0, 0, 10000, 10000, 10000, 10000]  # la moitié suivante part quand TOUS sont arrivés
    assert ou_etaient_les_doigts[8] == [0] * 6 and doublure.position == [0.0] * 6


@pytest.mark.parametrize("arret", ["arreter_mouvement", "arret_urgence"])
@pytest.mark.parametrize("nom, apres", [("compter", 3), ("compter", 5), ("vague", 2), ("vague", 6), (PFC, 4)])
def test_un_arret_au_milieu_d_un_geste_long_et_plus_aucune_etape_ne_part(arret, nom, apres):
    liaison, doublure = _figee()
    liaison.tirer_au_hasard = lambda choix: "victoire"
    liaison.geste(nom, 1.0)
    fin = time.monotonic() + 15.0
    while _lancements(doublure) < apres and time.monotonic() < fin:
        liaison.tic()
        time.sleep(0.02)
    _tics(liaison, 0.1)  # au milieu de l'étape (ou de sa pause)
    assert _lancements(doublure) == apres and liaison._geste is not None and liaison._geste.file
    vars(LiaisonLeadtronDh116)[arret](liaison)
    assert liaison._geste is None
    fige = list(doublure.position)
    _tics(liaison, 1.2)
    etat = liaison.lire_etat()
    assert _lancements(doublure) == apres and doublure.position == fige  # plus AUCUNE étape, et les doigts ne bougent plus
    assert etat["occupe"] is False and etat["echec_action"] is None and etat["en_mouvement"] is False  # un arrêt n'est pas un échec
    if arret == "arret_urgence":
        assert doublure.allume == [False] * 6
        for autre in GESTES:
            assert _refus(lambda: liaison.geste(autre, 1.0)) == "arret_urgence_actif"
        liaison.rearmer()
        assert _refus(lambda: liaison.geste(nom, 1.0)) == "main_pas_preparee" and _lancements(doublure) == apres
    else:
        liaison.geste(OUVRIR, 1.0)  # après un arrêt NORMAL, la main reste préparée : on peut la rouvrir
        assert _jouer(liaison)["echec_action"] is None and doublure.position == [0.0] * 6


@pytest.mark.parametrize("nom, panne", [("compter", "alarme"), ("compter", "doigt_bloque"), ("vague", "alarme"),
                                        ("vague", "doigt_bloque"), ("compter", "moteurs_coupes"), (POING, "refus")])
def test_une_etape_ratee_le_geste_est_dit_rate_et_la_suite_ne_part_pas(nom, panne, monkeypatch):
    monkeypatch.setattr(module_liaison, "ATTENTE_EN_PLUS_S", 0.3)
    liaison, doublure = _figee()
    liaison.geste(nom, 1.0)
    _tics(liaison, 0.25)
    if panne == "alarme":
        doublure.provoquer_alarme(4, 8)
    elif panne == "doigt_bloque":
        doublure.coinces = {3}  # l'index ne bouge plus : il n'arrivera pas
    elif panne == "moteurs_coupes":
        doublure.allume = [False] * 6
    else:
        doublure.provoquer_panne("refus")  # la main refusera l'étape suivante
    etat = _jouer(liaison, max_s=15.0)
    assert etat["occupe"] is False and etat["echec_action"] is not None and f"« {nom} »" in etat["echec_action"], (nom, panne)
    lances = _lancements(doublure)
    assert lances < FORMES[nom][1] or panne == "refus"  # la suite n'est pas partie
    assert _envoyes(doublure)[-1] in (ARRETER, COUPER)
    fige = list(doublure.position)
    _tics(liaison, 0.8)
    assert _lancements(doublure) == lances and doublure.position == fige


def test_un_geste_de_la_carte_absent_du_fichier_est_refuse_proprement(tmp_path):
    lu = yaml.safe_load(COPIE_FIGEE.read_text(encoding="utf-8"))
    del lu["gestes"]["rock"]
    fichier = tmp_path / "gestes.yaml"
    fichier.write_text(yaml.safe_dump(lu, allow_unicode=True, sort_keys=False), encoding="utf-8")
    liaison, doublure = _liaison(prete=True, gestes=fichier)
    with pytest.raises(ActionImpossible, match="« rock » n'est pas dans le fichier") as refus:
        liaison.geste("rock", 1.0)
    assert refus.value.code == "geste_illisible" and doublure.appels_du_kit == [] and liaison.lire_etat()["occupe"] is False
    liaison.geste("je_t_aime", 1.0)  # les autres gestes marchent
    assert _jouer(liaison)["echec_action"] is None
    # Un geste écrit dans le fichier mais ABSENT de la carte : la liaison ne le connaît pas (c'est la carte qui liste les noms).
    lu["gestes"]["doigt_d_honneur"] = lu["gestes"]["pointer"]
    fichier.write_text(yaml.safe_dump(lu, allow_unicode=True, sort_keys=False), encoding="utf-8")
    assert _refus(lambda: liaison.geste("doigt_d_honneur", 1.0)) == "geste_inconnu"
    # Et « preparer_la_main » écrit par erreur dans le fichier n'y est jamais lu : il reste celui de liaison.py.
    lu["gestes"][PREPARER] = lu["gestes"]["poing"]
    fichier.write_text(yaml.safe_dump(lu, allow_unicode=True, sort_keys=False), encoding="utf-8")
    doublure.appels_du_kit.clear()
    liaison.geste(PREPARER, 1.0)
    assert _envoyes(doublure) == LE_DEPART


def test_le_filet_trop_vite_ne_se_declenche_pas_a_tort_aux_grandes_vitesses_et_reste_la_pour_une_etape_lente(tmp_path):
    """Aux vitesses des exemples du fabricant (20000), la fausse main va exactement à la vitesse demandée : le filet ne
    doit pas dire « trop vite ». Pour une étape lente (5000), une main qui part à 20000 est toujours arrêtée."""
    fichier = tmp_path / "gestes.yaml"
    fichier.write_text(BON_FICHIER.replace("3500", "10000").replace("vitesse: 5000", "vitesse: 20000"), encoding="utf-8")
    for _ in range(3):
        liaison, doublure = _liaison(prete=True, gestes=fichier)
        liaison.geste(TENIR, 1.0)
        assert _jouer(liaison)["echec_action"] is None and max(doublure.position) == 10000.0
        liaison.geste(OUVRIR, 1.0)
        assert _jouer(liaison)["echec_action"] is None
    assert module_liaison.SURVITESSE == 2.0
    liaison, doublure = _liaison(prete=True)  # le fichier des essais : vitesse 5000
    doublure.vitesse_ignoree = True  # la main part à 20000 quoi qu'on demande
    liaison.geste(TENIR, 1.0)
    assert "ne tient pas notre vitesse" in _jouer(liaison)["echec_action"]


def test_par_l_adaptateur_les_gestes_d_expression_reussissent_et_le_tirage_se_lit_ensuite():
    async def scenario():
        from briques.b01_prise.actions import ActionDemandee

        adaptateur = ROBOT.fabriquer(vrai=False)
        adaptateur._liaison._gestes = COPIE_FIGEE
        adaptateur._liaison.tirer_au_hasard = lambda choix: "victoire"
        await adaptateur.connecter()
        liaison, doublure, resultats = adaptateur._liaison, adaptateur._liaison.kit, []
        try:
            for nom in (PREPARER, "attraper", OUVRIR, "rock", PFC, "geste_absent"):
                ident = await adaptateur.demarrer(ActionDemandee(nom="rejouer_geste", parametres={"nom": nom}))
                for _ in range(1500):
                    suivi = await adaptateur.suivre(ident)
                    if suivi.finie:
                        break
                    await adaptateur.battement()
                    await asyncio.sleep(0.02)
                resultats.append((suivi.statut, suivi.code_erreur, [round(p) for p in doublure.position]))
            return resultats, liaison.lire_etat()["dernier_tirage"], doublure
        finally:
            await adaptateur.deconnecter()

    resultats, tirage, doublure = asyncio.run(scenario())
    assert resultats == [("reussie", None, [0] * 6), ("reussie", None, [7000, 7000, 8500, 8500, 8500, 8500]),
                         ("reussie", None, [0] * 6), ("reussie", None, [8000, 8000, 0, 10000, 10000, 0]),
                         ("reussie", None, [8000, 8000, 0, 0, 10000, 10000]),
                         ("echouee", "geste_inconnu", [8000, 8000, 0, 0, 10000, 10000])]
    assert tirage == "victoire"
    _dans_nos_limites(doublure)
