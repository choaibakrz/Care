"""La clinique en boîte — H08b, docs/projet/PREMIERE_HEURE.md : les gestes de la première heure avec un vrai robot.

« Fini » veut dire : une page ; les gestes dans l'ordre, du câble au premier mouvement lent ; l'arrêt est essayé AVANT
tout mouvement ; la page dit qu'elle n'a jamais été essayée ; elle ne donne aucun chiffre de fabricant ; les commandes
qu'elle cite existent ; c'est un humain qui tape les commandes du vrai robot.
"""
from __future__ import annotations

import re
from pathlib import Path

RACINE = Path(__file__).resolve().parents[3]
PAGE = RACINE / "docs/projet/PREMIERE_HEURE.md"


def _texte() -> str:
    return PAGE.read_text(encoding="utf-8")


def test_une_page_qui_dit_qu_elle_n_a_jamais_ete_essayee():
    texte = _texte()
    assert len(texte.splitlines()) <= 70, "une page, pas plus"
    assert "jamais été essayée" in texte and "non testé sur vrai robot" in texte


def test_les_gestes_sont_numerotes_dans_l_ordre_du_cable_au_premier_mouvement_lent():
    texte = _texte()
    numeros = [int(n) for n in re.findall(r"^(\d+)\. ", texte, flags=re.M)]
    assert numeros == list(range(1, len(numeros) + 1)) and len(numeros) >= 8
    assert texte.index("câble") < texte.index("premier mouvement lent")
    assert "0,1 m/s" in texte


def test_l_arret_est_essaye_avant_tout_mouvement():
    texte = _texte().lower()
    arret_physique = texte.index("bouton d'arrêt physique")
    arret_logiciel = texte.index("arrêt logiciel")
    premier_mouvement = texte.index("premier mouvement lent :")
    assert arret_physique < arret_logiciel < premier_mouvement
    assert "robot immobile" in texte


def test_c_est_un_humain_qui_tape_les_commandes_du_vrai_robot_et_elles_existent():
    texte = _texte()
    assert "un humain" in texte and "feu orange" in texte.lower()
    lancer = (RACINE / "lancer.py").read_text(encoding="utf-8")
    commandes = re.findall(r"python3 lancer\.py ([a-z-]+)", texte)
    assert commandes and all(f'"{c}"' in lancer for c in set(commandes)), commandes
    assert "--conformite --vrai" in texte and "--complet" in texte
    for nom in ("unitree_go2", "roues_ros2"):
        assert nom in texte and (RACINE / "briques" / "b03_adaptateurs" / "robots" / nom / "liaison.py").exists()


def test_aucun_chiffre_de_fabricant_et_tout_ce_qui_manque_est_a_verifier():
    texte = _texte()
    assert "à vérifier" in texte
    assert not re.search(r"\d+ ?(kg|N\b|km/h|%)", texte)  # ni poids, ni force, ni batterie : nous ne les connaissons pas
