"""L'ébauche de branchement d'un bras AgileX PiPER (demande de Hiba, 14.11.2026).

NON TESTÉ SUR VRAI ROBOT. Ces essais tournent avec une DOUBLURE à la place du bras (doublure.py) : un faux client qui
porte les mêmes noms de fonctions que le kit public d'AgileX, lus en ligne le 14.11.2026. Ils ne disent rien du vrai bras.
« Fini » veut dire :
- l'ébauche sait : se connecter en écoute seule, dire son état, se déconnecter — et rien d'autre ;
- elle n'appelle QUE six fonctions du kit, toutes lues dans la documentation publique ; rien n'est écrit sur le câble ;
- un état jamais reçu (les valeurs par défaut du kit, qui ressemblent à « tout va bien ») est refusé, jamais cru ;
- dans le doute, le bras est dit EN MOUVEMENT ; un code inconnu est dit ; les pannes d'articulation sont dites ;
- les trois arrêts et tous les mouvements disent « À BRANCHER » ; aucune action n'est déclarée branchée ;
- la carte ne promet que les deux actions obligatoires et garde 0 partout (rien n'a été lu dans la doc du fabricant) ;
- la marque « NON TESTÉ SUR VRAI ROBOT » est sur les fichiers de l'ébauche ;
- sans le kit du fabricant (jamais installé ici), le vrai branchement dit pourquoi il ne peut pas se faire.
"""
import re
import sys
import types
from pathlib import Path

import pytest

from briques.b01_prise.carte import CarteIdentite
from briques.b03_adaptateurs.modele_vide.liaison import ABrancher
from briques.b03_adaptateurs.robots.agilex_piper import liaison as module_liaison
from briques.b03_adaptateurs.robots.agilex_piper.doublure import ORDRES, DoublurePiper
from briques.b03_adaptateurs.robots.agilex_piper.liaison import LiaisonAgilexPiper

ICI = Path(__file__).resolve().parents[1]
MARQUE = "NON TESTÉ SUR VRAI ROBOT"
# Les seules fonctions du kit que la liaison a le droit d'appeler (lues le 14.11.2026).
PERMISES = {"ConnectPort", "DisconnectPort", "get_connect_status", "isOk", "GetArmStatus", "GetArmHighSpdInfoMsgs"}


def _liaison(ouverte: bool = True):
    doublure = DoublurePiper(acceleration=5)
    liaison = LiaisonAgilexPiper(doublure)
    if ouverte:
        liaison.ouvrir()
    return liaison, doublure


@pytest.fixture(autouse=True)
def _attente_courte(monkeypatch):
    monkeypatch.setattr(module_liaison, "ATTENTE_OUVERTURE_S", 0.1)  # pour que les essais d'un bras muet restent courts


def test_la_marque_est_sur_les_fichiers_de_l_ebauche():
    for nom in ("liaison.py", "carte.yaml", "doublure.py", "adaptateur.py", "__init__.py",
                "tests/test_ebauche_agilex_piper.py", "tests/test_conformite_agilex_piper.py"):
        texte = (ICI / nom).read_text(encoding="utf-8")
        # le test de conformité, écrit par l'assistant du projet, le dit avec ses propres mots
        attendu = "ne parle JAMAIS au vrai robot" if nom.endswith("test_conformite_agilex_piper.py") else MARQUE
        assert attendu in texte, nom
    assert "Non testé sur vrai robot" in (ICI.parents[1] / "fiches" / "agilex_piper.md").read_text(encoding="utf-8")


def test_reconnecter_lire_l_etat_et_se_deconnecter_n_ecrivent_rien_sur_le_cable():
    liaison, doublure = _liaison(ouverte=False)  # le kit existe mais la lecture du câble n'est pas lancée
    liaison.ouvrir()
    liaison.signe_de_vie()
    etat = liaison.lire_etat()
    liaison.fermer()
    appels = [nom for nom, _ in doublure.appels_du_kit]
    assert set(appels) <= PERMISES and not set(appels) & set(ORDRES)
    assert appels[0] == "ConnectPort" and appels[-1] == "DisconnectPort"
    assert doublure.appels_du_kit[0] == ("ConnectPort", (True, False))  # lu : can_init=True ; piper_init=False = écoute seule
    assert sum(doublure.appels.values()) == 0  # aucune fonction du faux kit du projet (vitesse, stop, prendre…) non plus
    assert {"batterie_pct", "x", "y", "cap", "en_mouvement", "occupe", "objet_tenu", "erreurs", "arret_urgence"} <= set(etat)
    assert etat["batterie_pct"] is None and etat["x"] is None and etat["cap"] is None  # rien d'inventé
    assert etat["en_mouvement"] is False and etat["erreurs"] == [] and etat["arret_urgence"] is False


def test_un_bras_deja_connecte_n_est_pas_reconnecte():
    liaison, doublure = _liaison(ouverte=False)
    doublure.branche = True
    liaison.ouvrir()
    assert "ConnectPort" not in [nom for nom, _ in doublure.appels_du_kit]


def test_creer_le_vrai_kit_se_fait_en_ecoute_seule_avec_un_faux_module_du_fabricant(monkeypatch):
    """Le premier chemin (creer_kit) essayé avec un FAUX module « piper_sdk » : toujours pas le vrai kit."""
    crees = []

    class FauxClient(DoublurePiper):
        def __init__(self, can_name="can0"):
            super().__init__()
            self.can_name = can_name
            crees.append(self)

    monkeypatch.setitem(sys.modules, "piper_sdk", types.SimpleNamespace(C_PiperInterface_V2=FauxClient))
    kit = LiaisonAgilexPiper.creer_kit(can_name="can_bras")
    assert crees == [kit] and kit.can_name == "can_bras"
    assert kit.appels_du_kit == [("ConnectPort", (False, False))]  # piper_init=False : aucune question écrite au bras

    def casse(can_name="can0"):
        raise ValueError("CAN socket can0 does not exist")

    monkeypatch.setitem(sys.modules, "piper_sdk", types.SimpleNamespace(C_PiperInterface_V2=casse))
    with pytest.raises(ConnectionError, match="ne s'ouvre pas"):
        LiaisonAgilexPiper.creer_kit()


def test_la_doublure_est_reconnue_comme_un_faux_robot_par_sa_classe():
    liaison, _ = _liaison(ouverte=False)
    assert liaison.vrai_robot is False and liaison.repere_du_monde is False
    assert LiaisonAgilexPiper(object()).vrai_robot is True  # tout autre kit est pris pour le vrai : jamais l'inverse


def test_un_etat_jamais_recu_n_est_pas_pris_pour_tout_va_bien():
    """Lu : avant le premier message, le kit rend time_stamp 0, Hz 0 et des codes à 0 (« normal », « arrivé »)."""
    liaison, doublure = _liaison(ouverte=False)
    doublure.allume = False  # bras éteint, débranché ou en mode « bras maître » : aucun message
    assert doublure.isOk() is True  # comme le vrai kit : isOk() est vrai dès le départ, il ne prouve rien
    with pytest.raises(TimeoutError, match="ne donne pas son état"):
        liaison.ouvrir()
    for appel in (liaison.signe_de_vie, liaison.lire_etat):
        with pytest.raises(TimeoutError, match="ne donne pas son état"):
            appel()


def test_un_bras_qui_a_parle_puis_se_tait_n_est_plus_cru():
    """Lu : quand les messages cessent, time_stamp garde sa dernière valeur ; seul Hz retombe à 0."""
    liaison, doublure = _liaison()
    doublure.etat_vieux = True
    for appel in (liaison.signe_de_vie, liaison.lire_etat, liaison.ouvrir):
        with pytest.raises(TimeoutError, match="ne donne pas son état"):
            appel()
    doublure.etat_vieux, doublure.vitesses_vieilles = False, True  # l'état arrive, mais plus les mesures de vitesse
    assert liaison.lire_etat()["en_mouvement"] is True  # de vieilles vitesses nulles ne prouvent pas « immobile »


def test_un_bras_qui_se_tait_ou_une_liaison_fermee_sont_dits():
    liaison, doublure = _liaison()
    doublure.sain = False  # le kit ne voit plus aucun message sur le câble
    with pytest.raises(TimeoutError, match="ne répond plus"):
        liaison.signe_de_vie()
    doublure.sain, doublure.branche = True, False  # le drapeau du programme : la lecture n'est pas lancée
    for appel in (liaison.signe_de_vie, liaison.lire_etat):
        with pytest.raises(ConnectionError, match="n'est pas ouverte"):
            appel()


def test_l_arret_d_urgence_les_pannes_et_les_codes_inconnus_sont_dits():
    liaison, doublure = _liaison()
    doublure.code = 0x01
    etat = liaison.lire_etat()
    assert etat["arret_urgence"] is True and "arrêt d'urgence" in etat["erreurs"][0]
    doublure.code = 0x07
    etat = liaison.lire_etat()
    assert etat["arret_urgence"] is False and "collision" in etat["erreurs"][0] and "code 7" in etat["erreurs"][0]
    doublure.code = 0xFF  # lu : UNKNOWN
    assert "code inconnu : 255" in liaison.lire_etat()["erreurs"][0]
    doublure.code = 0x0B  # apprentissage à la main : un état, pas une panne
    assert liaison.lire_etat()["erreurs"] == []
    doublure.code = 0x00
    doublure.pannes_articulations = {"joint_3_angle_limit": True, "communication_status_joint_5": True}
    assert liaison.lire_etat()["erreurs"] == ["articulation 3 : angle hors limite", "articulation 5 : communication anormale"]


def test_dans_le_doute_le_bras_est_dit_en_mouvement():
    """La logique et le seuil sont un choix de l'équipe, à vérifier sur le bras : ici, seule la doublure répond."""
    liaison, doublure = _liaison()

    def bouge() -> bool:
        etat = liaison.lire_etat()
        assert etat["occupe"] is etat["en_mouvement"]
        return etat["en_mouvement"]

    assert bouge() is False  # en attente, arrivé, vitesses nulles, mesures reçues : le seul cas « immobile »
    doublure.mode = 0x01
    assert bouge() is False  # commandé par CAN et arrivé
    for mouvement in (0x01, 0xFF):  # pas arrivé, ou inconnu
        doublure.mouvement = mouvement
        assert bouge() is True, mouvement
    doublure.mouvement = 0x00
    for mode in (0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0xFF):  # apprentissage, Ethernet, Wi-Fi, télécommande… : doute
        doublure.mode = mode
        assert bouge() is True, mode
    doublure.mode = 0x00
    for code in (0x01, 0x0B, 0x0C, 0x0D, 0xFF):  # descente après l'arrêt « rapide », trajet guidé ou rejoué, inconnu
        doublure.code = code
        assert bouge() is True, code
    doublure.code = 0x00
    doublure.vitesses_moteurs = [0, 0, 0, -45, 0, 0]  # un moteur tourne à 0,045 rad/s (bras poussé à la main, chute…)
    assert bouge() is True
    doublure.vitesses_moteurs = [0, 0, 0, 5, 0, 0]  # sous le seuil de 0,02 rad/s
    assert bouge() is False
    doublure.vitesses_recues = False  # aucune mesure de vitesse : on ne peut pas dire « immobile »
    assert bouge() is True


def test_les_trois_arrets_et_tous_les_mouvements_sont_a_brancher_et_rien_ne_part():
    liaison, doublure = _liaison()
    doublure.appels_du_kit.clear()
    appels = [liaison.arreter_mouvement, liaison.arret_urgence, liaison.rearmer,
              lambda: liaison.vitesse(0.1, 0.0, 0.0), lambda: liaison.geste("saluer", 0.5),
              lambda: liaison.regarder("patient"), lambda: liaison.montrer("verre"),
              lambda: liaison.saisir("verre", 5.0), lambda: liaison.poser("ici"),
              lambda: liaison.parler("bonjour", "fr"), lambda: liaison.ecouter(1.0)]
    for appel in appels:
        with pytest.raises(ABrancher, match="À BRANCHER"):
            appel()
    assert doublure.appels_du_kit == [] and sum(doublure.appels.values()) == 0
    assert LiaisonAgilexPiper.branchees == frozenset()  # rien n'est déclaré branché tant que les arrêts ne sont pas choisis


def test_la_liaison_n_appelle_que_les_fonctions_permises_du_kit():
    """Liste BLANCHE : hors des commentaires, tout ce qui suit « kit. » doit être une des lectures permises."""
    code = "\n".join(l.split("#")[0] for l in (ICI / "liaison.py").read_text(encoding="utf-8").splitlines())
    code = re.sub(r'""".*?"""', "", code, flags=re.S)
    appelees = set(re.findall(r"\bkit\.(\w+)\(", code))
    assert appelees == PERMISES, appelees ^ PERMISES
    # Pas de détour : « self.kit » n'apparaît que rangé (= kit), suivi d'une fonction permise, ou donné à isinstance.
    restes = re.sub(r"self\.kit\.(?:%s)\(" % "|".join(sorted(PERMISES)), "", code)
    restes = restes.replace("self.kit = kit", "")
    assert "self.kit" not in restes and "getattr(kit" not in restes and "getattr(self.kit" not in restes, restes
    for ordre in ORDRES:
        assert ordre not in code, ordre


def test_la_carte_ne_promet_rien_et_garde_zero_partout():
    texte = (ICI / "carte.yaml").read_text(encoding="utf-8")
    carte = CarteIdentite.charger(ICI / "carte.yaml")
    assert sorted(carte.capacites) == ["arreter", "etat"] and list(carte.gestes) == []
    assert carte.genre == "bras" and carte.position_fixe == "table"
    limites = carte.limites
    # Rien n'a été lu dans la doc du fabricant elle-même : tout reste à 0, et le bras refuse de bouger.
    assert (limites.vitesse_max_m_s, limites.portee_max_m, limites.charge_max_kg, limites.force_max_n) == (0, 0, 0, 0)
    assert texte.count("à vérifier") >= 6


def test_sans_le_kit_du_fabricant_le_vrai_branchement_dit_pourquoi():
    import importlib.util

    if importlib.util.find_spec("piper_sdk") is not None:
        pytest.skip("le kit du fabricant est installé sur cet ordinateur : cet essai est pour un ordinateur sans le kit")
    with pytest.raises(RuntimeError, match="piper_sdk"):
        LiaisonAgilexPiper.creer_kit()
