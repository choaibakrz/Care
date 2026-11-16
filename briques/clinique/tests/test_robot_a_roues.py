"""La clinique en boîte — T31, le robot à roues, à préparer sans toucher (cahier 5.12 ; avenant 3, M01).

« Une carte d'identité d'exemple pour « un robot à roues à deux bras » : il roule, ne monte pas d'escaliers, porte peu
(mets 5 kg par bras, marqué « à vérifier »), vitesse lente. Une ébauche d'adaptateur à partir du modèle vide (brique 3),
marquée « non testé sur vrai robot ». N'installe aucun kit de fabricant. La liste du samedi matin, dans docs/projet/SAMEDI_MATIN.md. »
« Fini quand : la carte d'identité d'exemple passe le test de conformité sur le faux robot ; l'ébauche est marquée
« non testé sur vrai robot » ; docs/projet/SAMEDI_MATIN.md contient la liste. »
Tout est sur le FAUX ROBOT. Aucun robot de ce genre n'a été vu.
"""
from __future__ import annotations

import re
from pathlib import Path

from briques.b01_prise.carte import CarteIdentite
from briques.clinique import brancher, repetition

RACINE = Path(__file__).resolve().parents[3]
CARTE = RACINE / "briques" / "b02_faux_robot" / "cartes" / "roues_deux_bras.yaml"
EBAUCHE = RACINE / "briques" / "b03_adaptateurs" / "robots" / "roues_deux_bras"
MARQUE = "non testé sur vrai robot"


def test_la_carte_d_exemple_dit_ce_que_le_cahier_demande():
    texte = CARTE.read_text(encoding="utf-8")
    carte = CarteIdentite.charger(CARTE)
    assert carte.genre == "roues" and carte.vrai_robot is False and "exemple" in carte.nom.lower()
    assert carte.sait("se_deplacer") and carte.sait("saisir") and carte.sait("poser")
    assert carte.limites.charge_max_kg == 5.0
    ligne_charge = next(l for l in texte.splitlines() if "charge_max_kg" in l)
    assert "par bras" in ligne_charge and "à vérifier" in ligne_charge
    assert 0 < carte.limites.vitesse_max_m_s <= 0.2  # « vitesse lente »
    for mot in ("deux bras", "Il roule", "Il ne monte pas les escaliers", "5 kg par bras", "à vérifier"):
        assert mot in carte.remarques, mot
    assert MARQUE in texte.splitlines()[0] and "compatible" not in texte.lower()
    for ligne in texte.split("limites:")[1].split("gestes:")[0].strip().splitlines():  # chaque chiffre : à vérifier
        assert "à vérifier" in ligne, ligne


def test_la_carte_d_exemple_passe_le_test_de_conformite_sur_le_faux_robot(tmp_path):
    lignes: list[str] = []
    code = brancher.main(["roues_deux_bras"], ecrire=lignes.append, dossier=tmp_path)
    texte = "\n".join(lignes)
    assert code == 0 and "✘" not in texte and "testé sur faux robot" in texte, texte
    assert re.search(r"contrôles réussis : (\d+) sur \1\b", texte)


def test_l_etape_du_coussin_reussit_avec_cette_carte():
    with repetition.variation({"robot": "roues_deux_bras"}):
        resultat = repetition.CONTROLES[8]()
    assert resultat.reussie is True and resultat.etiquette == "FAUX ROBOT", resultat.detail
    assert "livrée" in resultat.detail


def test_l_ebauche_vient_du_modele_vide_et_est_marquee_partout():
    fichiers = {f.name: f.read_text(encoding="utf-8") for f in EBAUCHE.iterdir() if f.suffix in (".py", ".yaml", ".md")}
    for nom in ("liaison.py", "adaptateur.py", "carte.yaml"):
        assert nom in fichiers, nom
        assert MARQUE.upper() in fichiers[nom].upper(), nom
    assert "ABrancher" in fichiers["liaison.py"]  # rien n'est inventé : ce qui n'est pas connu reste « à brancher »
    carte = CarteIdentite.charger(EBAUCHE / "carte.yaml")
    assert carte.genre == "roues" and "deux bras" in carte.nom
    # pour un VRAI robot, la règle du modèle vide : un chiffre pas lu dans la doc reste 0 (le robot refuse de bouger)
    assert carte.limites.charge_max_kg == 0.0 and carte.limites.vitesse_max_m_s == 0.0
    ligne = fichiers["carte.yaml"].split("charge_max_kg")[1].splitlines()[0]
    assert "5 kg par bras" in ligne and "à vérifier" in ligne
    for texte in fichiers.values():  # aucun kit de fabricant importé
        assert not re.search(r"^\s*(import|from)\s+(unitree|agibot|flexiv|rclpy|ros)", texte, re.M | re.I)


def test_samedi_matin_contient_la_liste_du_cahier_sans_rien_effacer():
    texte = (RACINE / "docs/projet/SAMEDI_MATIN.md").read_text(encoding="utf-8")
    assert "En plus, pour le matériel" in texte and "Trois cartes sont prêtes d'avance" in texte  # rien d'effacé (M01)
    partie = texte.split("Le robot à roues (cahier 5.12)")[1]
    for question in ("Quel robot, et pour combien d'heures ?",
                     "Peut-on le piloter depuis nos ordinateurs ?",
                     "Y a-t-il un vrai bouton d'arrêt qui coupe le courant ?",
                     "Sa navigation marche-t-elle dans la salle ?",
                     "La prise d'objet est-elle prête ?",
                     "A-t-on le droit de rouler près du public, et à quelle vitesse ?",
                     "Micro et haut-parleur : les siens ou les nôtres ?",
                     "Batterie et recharge : combien de temps, et où recharger ?"):
        assert f"- [ ] {question}" in partie, question
