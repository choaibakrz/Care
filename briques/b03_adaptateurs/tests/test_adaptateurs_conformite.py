"""Brique 3 — le test de conformité en deux temps, et la confirmation tapée (feu orange). Testé sur faux robot."""
from __future__ import annotations

import re
import socket

import pytest

from aides_adaptateurs import CARTE_COMPLETE, FAUX, KitSansEtiquette, faux_sdk
from briques.b03_adaptateurs import conformite_deux_temps as conformite
from briques.b03_adaptateurs.assistant import creer, lancer_conformite
from briques.b03_adaptateurs.chemins.sdk.liaison_sdk import LiaisonSDK
from briques.b03_adaptateurs.modele_vide.adaptateur import AdaptateurModele
from briques.b03_adaptateurs.modele_vide.liaison import LiaisonVide
from conftest import lancer

EN_PLUS = ["mention honnête (vrai ou faux robot)", "la carte ne promet que ce qui est branché", "connexion sans mouvement",
           "refuse ce qui dépasse les limites (gardien)", "refuse le ticket d'un autre robot",
           "arrêt d'urgence : tout est bloqué", "aucune tentative d'arrêt sautée",
           "arrêt d'urgence : robot immobile et joignable", "réarmé par un humain : l'état se lit de nouveau",
           "aucun ordre de mouvement envoyé"]


@pytest.mark.parametrize("chemin", ["sdk", "ros2"])
def test_temps_1_sans_mouvement_sur_le_faux(chemin):
    rapport = lancer(conformite.sans_mouvement(lambda: FAUX[chemin]()[0], vrai_attendu=False))
    assert rapport.reussi, rapport.texte()
    noms = [c.nom for c in rapport.controles]
    assert all(n in noms for n in EN_PLUS), noms
    assert "arrêt d'urgence immédiat" in noms  # celui de briques/b01_prise/conformite.py, réutilisé
    assert not any(n.startswith("action") for n in noms), "aucune action jouée au temps 1"


@pytest.mark.parametrize("chemin", ["sdk", "ros2"])
def test_temps_2_complet_sur_le_faux(chemin):
    rapport = lancer(conformite.complet(lambda: FAUX[chemin]()[0], vrai_attendu=False))
    assert rapport.reussi, rapport.texte()
    assert any(c.nom == "[complet] arrêt d'urgence pendant un mouvement" for c in rapport.controles)


def test_les_refus_n_envoient_rien_au_robot():
    kits = []

    def fabrique():
        a, kit = faux_sdk()
        kits.append(kit)
        return a

    controles = lancer(conformite.controles_sans_mouvement(fabrique))
    assert all(c.ok for c in controles), controles
    kit = kits[-1]
    assert kit.appels["vitesse"] == 0 and kit.appels["jouer_geste"] == 0 and kit.appels["prendre"] == 0
    assert kit.appels["arreter_en_urgence"] == 1  # l'arrêt d'urgence logiciel, lui, est bien envoyé


def test_un_adaptateur_qui_bouge_en_se_connectant_echoue():
    class LiaisonQuiBouge(LiaisonSDK):
        def ouvrir(self) -> None:
            super().ouvrir()
            self.kit.vitesse(0.3, 0.0, 0.0)  # FAUTE exprès : ouvrir ne doit jamais faire bouger

    def fabrique():
        a, kit = faux_sdk()
        a._liaison = LiaisonQuiBouge(kit)
        return a

    rapport = lancer(conformite.sans_mouvement(fabrique, vrai_attendu=False))
    assert not rapport.reussi
    assert [c.nom for c in rapport.controles if not c.ok] == ["connexion sans mouvement"]


def test_une_carte_qui_promet_plus_que_la_liaison_echoue_et_bloque_le_temps_2():
    class LiaisonPresqueVide(LiaisonSDK):
        branchees = frozenset({"arreter", "etat"})

    fabrique = lambda: AdaptateurModele(CARTE_COMPLETE, LiaisonPresqueVide(KitSansEtiquette()))
    rapport = lancer(conformite.complet(fabrique, vrai_attendu=True))
    rate = {c.nom: c.detail for c in rapport.controles if not c.ok}
    assert "la carte ne promet que ce qui est branché" in rate and "se_deplacer" in rate["la carte ne promet que ce qui est branché"]
    assert "temps 2 (complet) non lancé" in rate
    assert not any(c.nom.startswith("[complet]") for c in rapport.controles)


def test_un_adaptateur_pas_branche_donne_un_rapport_clair_sans_planter():
    rapport = lancer(conformite.sans_mouvement(lambda: AdaptateurModele(CARTE_COMPLETE, LiaisonVide())))
    assert not rapport.reussi
    assert "À BRANCHER" in rapport.texte() and "ouvrir" in rapport.texte()


def test_la_confirmation_demande_la_phrase_exacte():
    lignes = []
    assert not conformite.confirmer("sans mouvement", "avertissement", lire=lambda _: "oui", ecrire=lignes.append)
    assert "Annulé : rien n'a été envoyé au robot." in lignes
    assert not conformite.confirmer("sans mouvement", "avertissement", lire=lambda _: "sans mouvement",
                                    ecrire=lignes.append, nombre=4821)  # sans le nombre : refusé
    assert conformite.confirmer("sans mouvement", "avertissement", lire=lambda _: " sans mouvement 4821 ",
                                ecrire=lignes.append, nombre=4821)
    texte = "\n".join(lignes)
    for mot in ("FEU ORANGE", "Hiba", "responsable sécurité", "PHYSIQUE", "portique", "une seule liaison"):
        assert mot in texte, mot


def test_sans_clavier_la_confirmation_est_refusee():
    """Un agent ou un script (pas de clavier) ne peut pas confirmer à la place d'un humain."""
    lignes = []
    assert not conformite.confirmer("sans mouvement", "avertissement", ecrire=lignes.append)  # pytest : pas de clavier
    assert any("pas de clavier" in l for l in lignes)


def _recopier(invite: str) -> str:
    """Pour les tests : taper exactement la phrase demandée (avec son nombre tiré au hasard)."""
    return re.search(r"« (.+?) »", invite).group(1)


def _port_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_vrai_robot_sans_la_phrase_rien_n_est_fabrique(tmp_path):
    creer("robot_essai", "chien", "sdk", tmp_path)
    lignes = []
    code = lancer_conformite("robot_essai", tmp_path, vrai=True, lire=lambda _: "non", ecrire=lignes.append,
                             port_ecran=_port_libre())
    assert code == 2 and "Annulé : rien n'a été envoyé au robot." in lignes
    assert not (tmp_path / "robot_essai" / "conformite.yaml").exists()


def test_vrai_robot_confirme_mais_pas_encore_branche(tmp_path):
    creer("robot_essai", "chien", "sdk", tmp_path)
    lignes = []
    code = lancer_conformite("robot_essai", tmp_path, vrai=True, lire=_recopier, ecrire=lignes.append,
                             port_ecran=_port_libre())
    texte = "\n".join(lignes)
    assert code == 1 and "À BRANCHER : creer_kit" in texte and "Reste à brancher" in texte
    assert "reussi: false" in (tmp_path / "robot_essai" / "conformite.yaml").read_text(encoding="utf-8")


def test_vrai_robot_refuse_si_l_ecran_tourne_deja(tmp_path):
    creer("robot_essai", "chien", "sdk", tmp_path)
    with socket.socket() as serveur:
        serveur.bind(("127.0.0.1", 0))
        serveur.listen()
        lignes = []
        code = lancer_conformite("robot_essai", tmp_path, vrai=True, lire=_recopier,
                                 ecrire=lignes.append, port_ecran=serveur.getsockname()[1])
    assert code == 2 and any("l'écran tourne déjà" in l for l in lignes)


def test_la_phrase_du_temps_2_contient_le_robot():
    assert conformite.phrase_complet("unitree-g1") == "mouvement lent unitree-g1"
    assert "FAIT BOUGER" in conformite.AVERTISSEMENT_COMPLET and "0,1 m/s" in conformite.AVERTISSEMENT_COMPLET
    assert "TOMBE" in conformite.AVERTISSEMENT_SANS_MOUVEMENT.upper()
