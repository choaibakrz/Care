"""La clinique en boîte — M01, trois cartes de robots prêtes d'avance (avenant 3).

« Fini » veut dire :
- les trois cartes (Unitree G1, Go2, G1-D) passent le test de conformité sur le faux robot, par la commande « brancher » ;
- l'étape du coussin réussit avec chacune ;
- avec la carte du robot à quatre pattes, aucune tâche qui demande un bras n'est donnée, et un humain est appelé pour
  prendre l'objet ;
- les fichiers du cerveau sont les mêmes avant et après ;
- chaque carte porte la marque « PRÉPARÉE SANS LE ROBOT — non testé sur vrai robot », et « à vérifier samedi » (ou « à
  remplir samedi ») sur chaque chiffre qui décrit le robot ; on n'écrit nulle part « compatible » ;
- `docs/projet/CARTE_A_REMPLIR.md` tient sur une page ; `docs/projet/SAMEDI_MATIN.md` contient les neuf lignes.
Tout est sur le FAUX ROBOT : aucun de ces robots n'a été vu.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest
import yaml

from briques.b01_prise.carte import CarteIdentite
from briques.clinique import brancher, repetition

RACINE = Path(__file__).resolve().parents[3]
CARTES = RACINE / "briques" / "b02_faux_robot" / "cartes"
NOMS = ["unitree_g1", "unitree_go2", "unitree_g1d"]
MARQUE = "PRÉPARÉE SANS LE ROBOT — non testé sur vrai robot"
CERVEAU = sorted((RACINE / "briques" / "b06_cerveau").rglob("*.py")) + [RACINE / "briques/clinique/coursier.py",
                                                                        RACINE / "briques/clinique/taches.py"]


def _empreinte() -> str:
    h = hashlib.sha256()
    for f in CERVEAU:
        h.update(f.relative_to(RACINE).as_posix().encode() + f.read_bytes())
    return h.hexdigest()


def _texte(nom: str) -> str:
    return (CARTES / f"{nom}.yaml").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------------------------- les cartes
@pytest.mark.parametrize("nom", NOMS)
def test_chaque_carte_porte_la_marque_et_a_verifier_samedi_sur_chaque_chiffre(nom):
    texte = _texte(nom)
    carte = CarteIdentite.charger(CARTES / f"{nom}.yaml")  # le format n'a pas changé : la carte se charge telle quelle
    assert MARQUE in carte.remarques and MARQUE in texte.splitlines()[0]
    assert carte.vrai_robot is False and "compatible" not in texte.lower()
    assert "il faut peut-être la version faite pour les développeurs : à vérifier samedi" in carte.remarques
    assert "jamais sans une personne à l'arrêt" in carte.remarques
    # chaque chiffre de la partie « limites » : « à vérifier samedi » ou « à remplir samedi » sur la même ligne
    limites = texte.split("limites:")[1].split("gestes:")[0].strip().splitlines()
    assert len(limites) == 4
    for ligne in limites:
        assert re.search(r"à (vérifier|remplir) samedi", ligne), ligne
    # chaque chiffre de la note (hors le nom du modèle) : « environ », « au moins », « au plus » ou « samedi » dans la même phrase
    for phrase in re.split(r"[.;] ", carte.remarques):
        sans_le_nom = re.sub(r"\b(G1-D|G1|Go2)\b", "", phrase)
        if re.search(r"\d", sans_le_nom):
            assert re.search(r"environ|au moins|au plus|samedi", sans_le_nom), phrase


def test_ce_que_l_avenant_dit_de_chaque_robot_est_sur_sa_carte():
    g1, go2, g1d = (CarteIdentite.charger(CARTES / f"{n}.yaml") for n in NOMS)
    for mot in ("deux jambes, deux bras", "environ 1,3 m", "environ 35 kg", "environ 2 heures", "Mains : à remplir samedi",
                "Charge par bras : à remplir samedi", "Il peut tomber", "au moins 2 m", "ni escalier ni ascenseur",
                "il ne le donne pas de la main à la main"):
        assert mot in g1.remarques, mot
    for mot in ("quatre pattes, pas de bras", "Il ne saisit rien", "panier", "à vérifier samedi", "ni course ni saut",
                "au moins 1 m", "1 kg au plus sur le dos", "pas d'escalier"):
        assert mot in go2.remarques, mot
    for mot in ("deux bras sur une base à roues", "environ 80 kg", "environ 1,3 m à environ 1,7 m", "environ 3 kg",
                "environ 2 m de haut", "Sa base peut rouler vite", "il roule très lentement", "au moins 1 m"):
        assert mot in g1d.remarques, mot
    assert g1.sait("saisir") and g1d.sait("saisir") and not go2.sait("saisir") and not go2.sait("poser")
    for carte in (g1, g1d):
        assert "Pour le faux robot seulement : on fait comme s'il pouvait saisir un objet léger" in carte.remarques
    assert "Pour le faux robot seulement : on fait comme si le panier était là" in go2.remarques
    assert go2.limites.charge_max_kg == 1.0 and go2.limites.portee_max_m == 0.0


# ---------------------------------------------------------------------------------------------- la conformité, par « brancher »
@pytest.mark.parametrize("nom", NOMS)
def test_la_carte_passe_le_test_de_conformite_sur_le_faux_robot(nom, tmp_path):
    lignes: list[str] = []
    code = brancher.main([nom], ecrire=lignes.append, dossier=tmp_path)
    texte = "\n".join(lignes)
    assert code == 0, texte
    assert "✘" not in texte and "testé sur faux robot" in texte and "FAUX ROBOT" in lignes[0]
    assert re.search(r"contrôles réussis : (\d+) sur \1\b", texte)


# ---------------------------------------------------------------------------------------------- le coussin
@pytest.mark.parametrize("nom, avec_bras", [("unitree_g1", True), ("unitree_go2", False), ("unitree_g1d", True)])
def test_l_etape_du_coussin_reussit_et_le_cerveau_ne_change_pas(nom, avec_bras):
    avant = _empreinte()
    with repetition.variation({"robot": nom}):
        resultat = repetition.CONTROLES[8]()
    assert resultat.reussie is True, resultat.detail
    assert resultat.etiquette == "FAUX ROBOT"
    if avec_bras:
        assert "livrée" in resultat.detail and "un humain pose" not in resultat.detail
    else:  # quatre pattes : jamais un geste de bras ; un humain pose, un humain prend
        for mot in ("un humain pose", "un humain prend", "0 geste de bras"):
            assert mot in resultat.detail, mot
    assert _empreinte() == avant  # aucun fichier du cerveau n'a changé


def test_rien_n_est_ecrit_en_dur_pour_ces_robots_dans_le_cerveau():
    for fichier in CERVEAU:
        texte = fichier.read_text(encoding="utf-8").lower()
        for mot in ("unitree", "go2", "g1-d", "g1d"):
            assert mot not in texte, (fichier.name, mot)


# ---------------------------------------------------------------------------------------------- les papiers
def test_la_carte_a_remplir_tient_sur_une_page_et_suit_le_format():
    texte = (RACINE / "docs/projet/CARTE_A_REMPLIR.md").read_text(encoding="utf-8")
    assert len(texte.splitlines()) <= 45 and len(texte) <= 3600
    for champ in ("id", "nom", "genre", "fabricant", "modele", "capacites", "vitesse_max_m_s", "portee_max_m", "charge_max_kg",
                  "force_max_n", "gestes", "remarques"):
        assert champ in texte, champ
    assert "arrêt" in texte and MARQUE in texte and "compatible" not in texte.lower()
    assert "docs/projet/CARTE_A_REMPLIR.md" in (RACINE / "BRANCHER_UN_ROBOT.md").read_text(encoding="utf-8")


def test_samedi_matin_contient_les_neuf_lignes_du_materiel():
    texte = (RACINE / "docs/projet/SAMEDI_MATIN.md").read_text(encoding="utf-8")
    partie = texte.split("En plus, pour le matériel")[1]
    for ligne in ("Quels modèles sont là, et dans quelle version : celle qu'on peut programmer ?",
                  "Combien de robots pour notre équipe, et pour combien de temps ?",
                  "Qui, chez le fabricant, peut nous aider sur place ?",
                  "Que fait le robot quand on appuie sur l'arrêt : il se fige, il s'assoit, il tombe ?",
                  "Un robot à jambes a-t-il besoin d'un support ou d'une sangle au début ?",
                  "A-t-il des mains ou des pinces ? Que peut-il saisir, et jusqu'à quel poids ?",
                  "Peut-on le télécommander ? Avec quoi, et qui en a le droit ?",
                  "Pour un robot sans bras : y a-t-il un panier ou un plateau ?",
                  "Y a-t-il trois niveaux d'étagère et une table pour l'épreuve (M02) ?"):
        assert ligne in partie, ligne
    assert "## 1. Arrivée (9 h)" in texte  # rien n'a été effacé


def test_non_teste_le_dit():
    assert "les trois cartes n'ont été essayées que sur le faux robot" in (RACINE / "NON_TESTE.md").read_text(encoding="utf-8")
