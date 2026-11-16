"""La clinique en boîte — R5, plusieurs faux robots dans le même monde (la brique 16 n'existe pas ; oui de Hiba, Q5 et Q6).

« Fini » veut dire, pour la version la plus simple, sans physique :
- quatre robots sont dans le même monde, chacun à un lieu du plan, avec son étiquette (R1 « FAUX ROBOT » ; R2 à R4
  « FAUX ROBOT — SIMULÉ ») ;
- un robot simulé se déplace sur le plan, pas à pas, par les couloirs du plan ; il ne change pas d'étage ;
- il prend une tâche (aller chercher, puis porter) et arrive ;
- il tombe en panne : panne provoquée, ou batterie basse ; il s'arrête où il est et rend sa tâche ;
- on sait quels robots libres sont les plus proches d'un lieu (pour le répartiteur, T23) ;
- une règle venue d'ailleurs (les cartes de rôle, T22) peut interdire un lieu : le robot s'arrête avant ;
- R1, le robot branché, ne bouge jamais par ce monde : il part par le coursier, sous le gardien.
Rien ne bouge pour de vrai : ce monde n'existe que dans l'ordinateur. Internet coupé.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from briques.clinique import dossier, monde_robots
from briques.clinique.monde_robots import MondeDesRobots


@pytest.fixture
def monde():
    return MondeDesRobots()


def _robot(monde, ident):
    return next(r for r in monde.etat() if r["id"] == ident)


def _avancer(monde, fois):
    for _ in range(fois):
        monde.pas()


# ---------------------------------------------------------------------------------------------- quatre robots, un monde
def test_quatre_robots_dans_le_meme_monde_avec_leur_etiquette(monde):
    etat = monde.etat()
    assert [r["nom"] for r in etat] == ["R1", "R2", "R3", "R4"]
    assert [r["etiquette"] for r in etat] == ["FAUX ROBOT"] + ["FAUX ROBOT — SIMULÉ"] * 3
    lieux = {l["nom"] for l in dossier.charger().lieux["lieux"]}
    assert all(r["ou"] in lieux and r["etat"] == "libre" and r["batterie"] == 100 for r in etat)
    assert monde.compte()["texte"] == "3 robots simulés sur 4"


def test_un_depart_hors_du_plan_est_refuse(tmp_path):
    fichier = tmp_path / "flotte.yaml"
    fichier.write_text("marque: inventé\nrobots:\n  - {id: robot-r2, nom: R2, carte: Étage, simule: true, depart: Lune}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Lune"):
        MondeDesRobots(fichier=fichier)


# ---------------------------------------------------------------------------------------------- se déplacer sur le plan
def test_un_robot_simule_se_deplace_pas_a_pas_par_les_couloirs(monde):
    assert _robot(monde, "robot-r2")["ou"] == "Réserve"
    route = monde.envoyer("robot-r2", "Chambre 12")
    assert route == {"par": ["Poste de soins", "Chambre 11", "Chambre 12"], "metres": 14.0}
    monde.pas()  # 2 mètres sur les 4 du premier couloir
    r2 = _robot(monde, "robot-r2")
    assert r2["etat"] == "en route" and r2["ou"] == "entre Réserve et Poste de soins"
    monde.pas()
    assert _robot(monde, "robot-r2")["ou"] == "Poste de soins"
    _avancer(monde, 4)
    assert _robot(monde, "robot-r2")["ou"] == "entre Chambre 11 et Chambre 12"
    evenements = monde.pas()
    r2 = _robot(monde, "robot-r2")
    assert r2["ou"] == "Chambre 12" and r2["etat"] == "libre"
    assert [e["quoi"] for e in evenements if e["robot"] == "robot-r2"] == ["arrivé"]
    assert r2["batterie"] == pytest.approx(100 - 14 * monde.conso)
    _avancer(monde, 3)
    assert _robot(monde, "robot-r2")["ou"] == "Chambre 12"  # arrivé, il ne bouge plus


def test_les_robots_ne_changent_pas_d_etage(monde):
    with pytest.raises(ValueError, match="pas de chemin"):
        monde.envoyer("robot-r2", "Hall")
    with pytest.raises(ValueError, match="lieu inconnu"):
        monde.envoyer("robot-r2", "Lune")
    assert _robot(monde, "robot-r2")["etat"] == "libre"


def test_r1_le_robot_branche_ne_bouge_pas_par_ce_monde(monde):
    with pytest.raises(ValueError, match="coursier"):
        monde.envoyer("robot-r1", "Accueil")
    with pytest.raises(ValueError, match="coursier"):
        monde.prendre("robot-r1", "t1", "Réserve", "Chambre 12")
    monde.placer("robot-r1", "Poste de soins")  # on dit où il est, c'est tout
    assert _robot(monde, "robot-r1")["ou"] == "Poste de soins"


def test_pas_de_physique_deux_robots_peuvent_etre_au_meme_lieu(monde):
    monde.envoyer("robot-r4", "Réserve")  # R4 part du Poste de soins : 4 mètres
    _avancer(monde, 2)
    assert _robot(monde, "robot-r4")["ou"] == _robot(monde, "robot-r2")["ou"] == "Réserve"


# ---------------------------------------------------------------------------------------------- prendre une tâche
def test_un_robot_prend_une_tache_va_chercher_puis_porte(monde):
    monde.placer("robot-r2", "Poste de soins")
    monde.prendre("robot-r2", "t7", "Réserve", "Chambre 11")
    r2 = _robot(monde, "robot-r2")
    assert r2["tache"] == "t7" and r2["etat"] == "en route"
    vus = []
    for _ in range(12):
        vus += monde.pas()
    assert [(e["quoi"], e.get("lieu")) for e in vus] == [("sur place", "Réserve"), ("arrivé", "Chambre 11")]
    assert vus[-1]["tache"] == "t7"
    r2 = _robot(monde, "robot-r2")
    assert r2["ou"] == "Chambre 11" and r2["etat"] == "arrivé" and r2["tache"] == "t7"
    monde.liberer("robot-r2")
    assert _robot(monde, "robot-r2")["etat"] == "libre" and _robot(monde, "robot-r2")["tache"] is None


def test_un_robot_occupe_ne_prend_pas_une_deuxieme_tache(monde):
    monde.prendre("robot-r2", "t1", "Réserve", "Chambre 12")
    with pytest.raises(ValueError, match="occupé"):
        monde.prendre("robot-r2", "t2", "Réserve", "Chambre 11")


# ---------------------------------------------------------------------------------------------- tomber en panne
def test_panne_provoquee_en_pleine_course_il_s_arrete_et_rend_sa_tache(monde):
    monde.prendre("robot-r3", "t3", "Chambre 14", "Chambre 12")  # R3 part du Salon
    _avancer(monde, 2)
    evenement = monde.panne("robot-r3", "batterie basse")
    assert evenement["quoi"] == "panne" and evenement["provoquee"] is True and evenement["tache"] == "t3"
    ou = _robot(monde, "robot-r3")["ou"]
    assert ou == "entre Salon et Chambre 14"
    _avancer(monde, 5)
    r3 = _robot(monde, "robot-r3")
    assert r3["etat"] == "en panne" and r3["ou"] == ou and r3["tache"] is None and r3["panne"] == "batterie basse (panne provoquée)"
    with pytest.raises(ValueError, match="en panne"):
        monde.envoyer("robot-r3", "Salon")
    monde.reparer("robot-r3")
    assert _robot(monde, "robot-r3")["etat"] == "libre"


def test_batterie_basse_le_robot_tombe_en_panne_tout_seul():
    monde = MondeDesRobots(conso=10.0, seuil=15)  # 10 % par mètre : la batterie ne tient pas 14 mètres
    monde.prendre("robot-r2", "t1", "Réserve", "Chambre 12")
    vus = []
    for _ in range(10):
        vus += monde.pas()
    pannes = [e for e in vus if e["quoi"] == "panne"]
    assert len(pannes) == 1 and pannes[0]["provoquee"] is False and pannes[0]["tache"] == "t1"
    r2 = _robot(monde, "robot-r2")
    assert r2["etat"] == "en panne" and r2["batterie"] <= 15 and r2["ou"] != "Chambre 12"
    assert r2["panne"] == "batterie basse"  # pas « provoquée » : elle vient du calcul


# ---------------------------------------------------------------------------------------------- le plus proche
def test_les_robots_libres_les_plus_proches_d_un_lieu(monde):
    # départs : R1 Hall (autre étage), R2 Réserve, R3 Salon, R4 Poste de soins
    assert monde.plus_proches("Réserve") == [("robot-r2", 0.0), ("robot-r4", 4.0), ("robot-r3", 28.0)]
    monde.panne("robot-r2", "roue bloquée")
    monde.envoyer("robot-r4", "Chambre 11")
    assert monde.plus_proches("Réserve") == [("robot-r3", 28.0)]  # ni le robot en panne, ni le robot occupé
    monde.placer("robot-r1", "Chambre 11")
    assert monde.plus_proches("Réserve")[0] == ("robot-r1", 10.0)  # R1 compte, là où on l'a placé


# ---------------------------------------------------------------------------------------------- une règle d'ailleurs
def test_une_regle_peut_interdire_un_lieu_le_robot_s_arrete_avant():
    def pas_la_chambre_11(robot, lieu):
        return "la carte ne permet pas ce lieu" if lieu == "Chambre 11" else None

    monde = MondeDesRobots(permis=pas_la_chambre_11)
    monde.envoyer("robot-r2", "Chambre 12")
    vus = []
    for _ in range(10):
        vus += monde.pas()
    r2 = _robot(monde, "robot-r2")
    assert r2["ou"] == "Poste de soins" and r2["etat"] == "bloqué"
    bloque = [e for e in vus if e["quoi"] == "bloqué"]
    assert len(bloque) == 1 and bloque[0]["lieu"] == "Chambre 11" and "carte" in bloque[0]["raison"]


# ---------------------------------------------------------------------------------------------- dire vrai
def test_le_journal_garde_tout_dans_l_ordre(monde):
    monde.envoyer("robot-r4", "Réserve")
    _avancer(monde, 2)
    monde.panne("robot-r4", "essai")
    assert [(e["pas"], e["quoi"]) for e in monde.journal] == [(0, "départ"), (2, "arrivé"), (2, "panne")]


def test_ce_monde_ne_touche_ni_au_robot_ni_a_l_ossature():
    source = Path(monde_robots.__file__).read_text(encoding="utf-8")
    for interdit in ("from commun", "import commun", "briques.b0", "briques.b1", "socket", "subprocess"):
        assert interdit not in source, interdit


def test_la_commande_montre_les_etiquettes_et_dit_que_rien_ne_bouge(capsys):
    assert '"monde-robots"' in (Path(__file__).resolve().parents[3] / "lancer.py").read_text(encoding="utf-8")
    assert monde_robots.main([]) == 0
    sortie = capsys.readouterr().out
    for mot in ("FAUX ROBOT — SIMULÉ", "3 robots simulés sur 4", "rien ne bouge", "sans physique", "en panne", "arrivé",
                "pas de chemin", "R1"):
        assert mot in sortie, mot
