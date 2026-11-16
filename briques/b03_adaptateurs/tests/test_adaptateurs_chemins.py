"""Brique 3 — les deux chemins (kit du fabricant, pont ROS 2) avec leur faux. Testé sur faux robot."""
from __future__ import annotations

import asyncio
import importlib.util
import inspect
import sys
import time
from pathlib import Path

import pytest

from aides_adaptateurs import CARTE_COMPLETE, FAUX, KitSansEtiquette, agir, chaine, faux_ros2, faux_sdk
from briques.b01_prise.actions import ActionDemandee
from briques.b01_prise.adaptateur import ActionImpossible
from briques.b01_prise.conformite import verifier_conformite
from briques.b03_adaptateurs.chemins.ros2 import liaison_ros2
from briques.b03_adaptateurs.chemins.ros2.faux_ros2 import FauxRclpy
from briques.b03_adaptateurs.chemins.ros2.liaison_ros2 import SUJETS
from briques.b03_adaptateurs.chemins.sdk import liaison_sdk
from briques.b03_adaptateurs.chemins.sdk.faux_sdk import FauxKit
from briques.b03_adaptateurs.modele_vide.liaison import ABrancher
from conftest import lancer

CHEMINS = Path(__file__).resolve().parents[1] / "chemins"
MARQUE = "# À BRANCHER (à vérifier dans la doc du fabricant)"


def _etat_du_faux(chemin, faux):
    """(bouge, arrêt d'urgence vu par le robot) — lu directement dans le faux robot (permis dans un test)."""
    if chemin == "sdk":
        e = faux.lire()
        return e["en_mouvement"], e["arret_urgence"]
    faux.avancer()
    return any(faux._v), faux.arret_actif


@pytest.mark.parametrize("chemin", ["sdk", "ros2"])
def test_le_test_de_conformite_complet_passe_sur_le_faux(chemin):
    rapport = lancer(verifier_conformite(lambda: FAUX[chemin]()[0], complet=True))
    assert rapport.reussi, rapport.texte()
    assert rapport.mention == "testé sur faux robot"
    attendues = 10 if chemin == "sdk" else 8  # le pont ne branche pas saisir et poser
    assert len([c for c in rapport.controles if c.nom.startswith("action")]) == attendues - 1  # « arreter » à part


@pytest.mark.parametrize("chemin", ["sdk", "ros2"])
def test_arret_d_urgence_pendant_un_deplacement(chemin):
    async def go():
        adaptateur, faux = FAUX[chemin](acceleration=1.0)
        bus, gardien, prise = chaine(adaptateur)
        await prise.connecter()
        suivi = await agir(gardien, prise, "se_deplacer", dx=2.0)
        await asyncio.sleep(0.4)
        assert _etat_du_faux(chemin, faux)[0], "le faux robot doit bouger"
        await prise.arret_urgence(raison="test")
        bouge, arret = _etat_du_faux(chemin, faux)
        assert not bouge and arret, "arrêté tout de suite, et le robot a reçu l'arrêt"
        assert (await prise.suivre(suivi.id)).finie or (await prise.attendre(suivi.id, 2)).finie
        with pytest.raises(ActionImpossible) as e:  # défense en profondeur : l'adaptateur refuse aussi, seul
            await adaptateur.demarrer(ActionDemandee(nom="se_deplacer", parametres={"dx": 0.2}))
        assert e.value.code == "arret_urgence_actif"
        assert await prise.rearmer()
        assert not _etat_du_faux(chemin, faux)[1]
        await prise.deconnecter()

    lancer(go())


@pytest.mark.parametrize("chemin", ["sdk", "ros2"])
def test_le_chien_de_garde_de_l_adaptateur_arrete_le_robot(chemin):
    """La prise ne donne plus signe de vie (programme en panne) : l'adaptateur arrête le robot seul."""
    async def go():
        adaptateur, faux = FAUX[chemin](acceleration=1.0)
        bus, gardien, prise = chaine(adaptateur)
        await prise.connecter()
        suivi = await agir(gardien, prise, "se_deplacer", dx=3.0)
        await asyncio.sleep(0.3)
        prise._battement.cancel()  # plus de signes de vie (test seulement)
        await asyncio.sleep(1.2)
        assert not _etat_du_faux(chemin, faux)[0]
        assert any("chien de garde" in ligne for ligne in adaptateur.journal)
        fin = await adaptateur.suivre(suivi.id)
        assert fin.statut == "echouee" and fin.code_erreur == "chien_de_garde"
        await prise.deconnecter()

    lancer(go())


@pytest.mark.parametrize("chemin", ["sdk", "ros2"])
def test_le_programme_fige_le_robot_s_arrete_seul(chemin):
    """Tout le programme se fige (plus aucun ordre ne part) : le chien de garde du FABRICANT (simulé) arrête le robot.
    Sur un vrai robot, ce chien de garde est à vérifier (fiches/)."""
    async def go():
        adaptateur, faux = FAUX[chemin](acceleration=1.0)
        bus, gardien, prise = chaine(adaptateur)
        await prise.connecter()
        await agir(gardien, prise, "se_deplacer", dx=3.0)
        await asyncio.sleep(0.4)
        x0 = faux.x
        time.sleep(1.0)  # le programme est figé une seconde : aucune tâche ne tourne
        _etat_du_faux(chemin, faux)
        assert faux.x - x0 < 0.3 * 0.5, "le robot n'a avancé que pendant la durée de vie du dernier ordre"
        await prise.arret_urgence(raison="fin du test")
        await prise.deconnecter()

    lancer(go())


def test_le_robot_ignore_l_arret_logiciel_il_s_arrete_quand_nos_ordres_cessent():
    async def go():
        adaptateur, kit = faux_sdk(acceleration=1.0)
        bus, gardien, prise = chaine(adaptateur)
        await prise.connecter()
        await agir(gardien, prise, "se_deplacer", dx=3.0)
        await asyncio.sleep(0.3)
        kit.provoquer_panne("arret_ignore")
        await prise.arret_urgence(raison="test")
        await asyncio.sleep(0.6)
        assert not kit.lire()["en_mouvement"] and not kit.arret_actif
        await prise.deconnecter()

    lancer(go())


@pytest.mark.parametrize("chemin", ["sdk", "ros2"])
def test_liaison_coupee_pendant_un_deplacement(chemin):
    async def go():
        adaptateur, faux = FAUX[chemin](acceleration=1.0)
        bus, gardien, prise = chaine(adaptateur)
        await prise.connecter()
        suivi = await agir(gardien, prise, "se_deplacer", dx=3.0)
        await asyncio.sleep(0.3)
        faux.provoquer_panne("coupure") if chemin == "sdk" else faux.pannes.add("muet")
        fin = await prise.attendre(suivi.id, 5)
        assert fin.statut == "echouee" and fin.code_erreur == "liaison_perdue"
        await asyncio.sleep(0.5)
        assert not prise.liaison_ok
        assert any(e.type == "panne" and e.donnees.get("quoi") == "liaison_perdue" for e in bus.historique)
        await prise.deconnecter()

    lancer(go())


@pytest.mark.parametrize("chemin", ["sdk", "ros2"])
def test_annuler_immobilise_le_robot(chemin):
    async def go():
        adaptateur, faux = FAUX[chemin](acceleration=1.0)
        bus, gardien, prise = chaine(adaptateur)
        await prise.connecter()
        suivi = await agir(gardien, prise, "se_deplacer", dx=3.0)
        await asyncio.sleep(0.3)
        await prise.annuler(suivi.id)
        assert (await prise.attendre(suivi.id, 2)).statut == "annulee"
        assert not _etat_du_faux(chemin, faux)[0]
        await prise.deconnecter()

    lancer(go())


@pytest.mark.parametrize("chemin", ["sdk", "ros2"])
def test_le_mode_lent_bride_la_vitesse(chemin):
    async def go():
        adaptateur, faux = FAUX[chemin](lent=True)
        bus, gardien, prise = chaine(adaptateur)
        await prise.connecter()
        suivi = await agir(gardien, prise, "se_deplacer", dx=0.1, vitesse=0.3)
        assert (await prise.attendre(suivi.id, 10)).statut == "reussie"
        assert 0 < faux.vitesse_max_vue <= 0.1
        await prise.deconnecter()

    lancer(go())


@pytest.mark.parametrize("chemin", ["sdk", "ros2"])
def test_deconnecter_fait_un_arret_normal_jamais_l_arret_d_urgence(chemin):
    """Robot à jambes : l'arrêt d'urgence du fabricant peut le faire tomber. Fermer le programme ne doit pas le déclencher."""
    async def go():
        adaptateur, faux = FAUX[chemin]()
        bus, gardien, prise = chaine(adaptateur)
        await prise.connecter()
        await prise.deconnecter()
        if chemin == "sdk":
            assert faux.appels["stop"] >= 1 and faux.appels["arreter_en_urgence"] == 0
        else:
            assert faux.recus[SUJETS["vitesse"]] >= 1 and faux.recus[SUJETS["arret_urgence"]] == 0

    lancer(go())


def test_un_geste_et_une_phrase_suivent_le_robot_jusqu_au_bout():
    async def go():
        adaptateur, kit = faux_sdk(acceleration=1.0)
        bus, gardien, prise = chaine(adaptateur)
        await prise.connecter()
        t0 = time.monotonic()
        suivi = await agir(gardien, prise, "rejouer_geste", nom="saluer")
        fin = await prise.attendre(suivi.id, 5)
        assert fin.statut == "reussie" and time.monotonic() - t0 >= 0.55  # le geste du faux kit dure 0,6 s
        assert kit.appels["jouer_geste"] == 1
        suivi = await agir(gardien, prise, "saisir", objet="objet_test")
        assert (await prise.attendre(suivi.id, 5)).statut == "reussie" and kit.objet_tenu == "objet_test"
        await prise.deconnecter()

    lancer(go())


def test_le_robot_refuse_un_ordre_l_action_est_refusee_et_expliquee():
    async def go():
        adaptateur, kit = faux_sdk()
        bus, gardien, prise = chaine(adaptateur)
        await prise.connecter()
        kit.provoquer_panne("refus")
        suivi = await agir(gardien, prise, "rejouer_geste", nom="saluer")
        fin = await prise.attendre(suivi.id, 5)
        assert fin.statut == "echouee" and fin.code_erreur == "robot_refuse" and "code 3" in fin.message
        await prise.deconnecter()

    lancer(go())


def test_une_erreur_imprevue_pendant_un_deplacement_arrete_le_robot_et_le_dit():
    class LiaisonQuiPerdLOdometre(liaison_sdk.LiaisonSDK):
        appels = 0

        def lire_etat(self):
            self.appels += 1
            etat = super().lire_etat()
            return etat if self.appels < 4 else {k: v for k, v in etat.items() if k != "x"}  # FAUTE exprès

    async def go():
        adaptateur, kit = faux_sdk(acceleration=1.0)
        adaptateur._liaison = LiaisonQuiPerdLOdometre(kit)
        bus, gardien, prise = chaine(adaptateur)
        await prise.connecter()
        suivi = await agir(gardien, prise, "se_deplacer", dx=2.0)
        fin = await prise.attendre(suivi.id, 5)
        assert fin.statut == "echouee" and fin.code_erreur == "erreur_adaptateur"
        await asyncio.sleep(0.4)
        assert not kit.lire()["en_mouvement"] and kit.appels["stop"] >= 1
        await prise.deconnecter()

    lancer(go())


def test_les_ebauches_marquent_chaque_appel_a_brancher():
    for fichier, classe in ((CHEMINS / "sdk" / "liaison_sdk.py", liaison_sdk.LiaisonSDK),
                            (CHEMINS / "ros2" / "liaison_ros2.py", liaison_ros2.LiaisonPontROS2)):
        texte = fichier.read_text(encoding="utf-8")
        assert "NON TESTÉ SUR VRAI ROBOT" in texte and "Testé sur faux robot" in texte
        assert texte.count(MARQUE) >= 12, fichier.name
        assert "# gabarit:classe" in texte and "# gabarit:branchees" in texte
    source = inspect.getsource(liaison_sdk.LiaisonSDK)
    for nom in ("ouvrir", "fermer", "signe_de_vie", "lire_etat", "arreter_mouvement", "arret_urgence", "rearmer",
                "vitesse", "geste", "regarder", "montrer", "saisir", "poser", "parler", "ecouter"):
        corps = source.split(f"    def {nom}(", 1)[1].split("\n    def ", 1)[0]
        assert MARQUE in corps, f"LiaisonSDK.{nom} : l'appel au kit doit être marqué"


def test_faux_ou_vrai_se_decide_par_la_classe_jamais_par_un_attribut():
    """Point 12 de la relecture : un objet qui DIT être une simulation n'est pas pour autant le faux kit du projet."""
    class SeDitSimulation:
        simulation = True

    from briques.b03_adaptateurs.chemins.ros2.faux_ros2 import MESSAGES

    assert not liaison_sdk.LiaisonSDK(FauxKit()).vrai_robot
    assert liaison_sdk.LiaisonSDK(SeDitSimulation()).vrai_robot and liaison_sdk.LiaisonSDK(KitSansEtiquette()).vrai_robot
    assert not liaison_ros2.LiaisonPontROS2(FauxRclpy(), MESSAGES).vrai_robot
    assert liaison_ros2.LiaisonPontROS2(SeDitSimulation(), MESSAGES).vrai_robot
    for fichier in (CHEMINS / "sdk" / "faux_sdk.py", CHEMINS / "ros2" / "faux_ros2.py"):
        texte = fichier.read_text(encoding="utf-8")
        assert "Testé sur faux robot" in texte and ("INVENTÉS" in texte or "inventés" in texte) and "CLASSE" in texte


def test_aucun_kit_de_robot_ni_ros2_n_est_importe():
    interdits = ("rclpy", "unitree_sdk2py", "flexivrdk", "geometry_msgs")
    assert not [m for m in sys.modules if m.split(".")[0] in interdits]
    with pytest.raises(ABrancher):
        liaison_sdk.LiaisonSDK.creer_kit()
    if importlib.util.find_spec("rclpy") is None:  # ROS 2 absent ici : l'erreur le dit clairement
        with pytest.raises(ABrancher) as e:
            liaison_ros2.creer_ros2()
        assert "feu orange" in str(e.value)


def test_vrai_robot_ros2_le_pont_sait_qu_il_est_vrai():
    class RclpySansEtiquette(FauxRclpy):
        simulation = False

    from briques.b03_adaptateurs.chemins.ros2.faux_ros2 import MESSAGES

    pont = liaison_ros2.LiaisonPontROS2(RclpySansEtiquette(), MESSAGES)
    assert pont.vrai_robot and not pont.repere_du_monde and pont.infos_simulation() is None
    assert CARTE_COMPLETE.vrai_robot  # la carte de test dit « vrai » ; c'est la liaison qui décide (voir modèle)
    a, _ = faux_ros2()
    assert not a.carte().vrai_robot and "saisir" not in a.carte().capacites
