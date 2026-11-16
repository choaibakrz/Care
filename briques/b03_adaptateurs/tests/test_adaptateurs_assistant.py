"""Brique 3 — l'assistant « brancher un robot », le registre, et le système complet. Testé sur faux robot."""
from __future__ import annotations

import importlib.util
import inspect
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from briques.b01_prise.carte import CarteIdentite
from briques.b03_adaptateurs import registre
from briques.b03_adaptateurs.assistant import (DOSSIER_ROBOTS, charger_robot, creer, main, nom_de_classe, nom_valide,
                                               reste_a_brancher)
from conftest import lancer

RACINE = Path(__file__).resolve().parents[3]


def _lancer_les_tests_du_robot(ici: Path) -> int:
    """Le test généré, lancé comme pytest le ferait (fonctions test_*), sans sous-programme."""
    fichier = next((ici / "tests").glob("test_conformite_*.py"))
    spec = importlib.util.spec_from_file_location(f"genere_{ici.name}_{abs(hash(str(ici)))}", fichier)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    tests = [f for n, f in inspect.getmembers(module, inspect.isfunction) if n.startswith("test_")]
    for t in tests:
        t()
    return len(tests)


@pytest.mark.parametrize("genre,chemin", [("chien", "ros2"), ("bras", "sdk"), ("humanoide", "sdk"), ("roues", "ros2")])
def test_l_assistant_cree_un_robot_pret_a_tester(tmp_path, genre, chemin):
    ici = creer(f"robot_{genre}", genre, chemin, tmp_path)
    assert {p.name for p in ici.iterdir()} >= {"__init__.py", "carte.yaml", "liaison.py", "adaptateur.py", "tests",
                                                 "branchement.yaml"}
    carte = CarteIdentite.charger(ici / "carte.yaml")
    assert carte.genre == genre and carte.capacites == ["arreter", "etat"] and carte.id == f"robot-{genre}"
    liaison = (ici / "liaison.py").read_text(encoding="utf-8")
    assert f"class {nom_de_classe(f'robot_{genre}')}(LiaisonVide):" in liaison
    assert "gabarit:" not in liaison and "branchees: frozenset[str] = frozenset()" in liaison
    assert liaison.count("À BRANCHER") >= 12 and "NON TESTÉ SUR VRAI ROBOT" in liaison
    assert _lancer_les_tests_du_robot(ici) == 4  # le test prêt à lancer passe tout de suite (faux kit)
    module = charger_robot(f"robot_{genre}", tmp_path)
    vrai = getattr(module, nom_de_classe(f"robot_{genre}"))
    assert vrai.branchees == frozenset(), "rien n'est promis pour le vrai robot au départ"
    assert not module.fabriquer(vrai=False).carte().vrai_robot


def test_l_assistant_ne_touche_a_aucun_robot_et_n_ecrase_rien(tmp_path):
    creer("mon_robot", "chien", "sdk", tmp_path)
    with pytest.raises(ValueError, match="existe déjà"):
        creer("mon_robot", "bras", "ros2", tmp_path)
    for faux_nom in ("", "A", "é_robot", "class", "tests", "robot-g1", "x" * 40):
        assert nom_valide(faux_nom), faux_nom
        with pytest.raises(ValueError):
            creer(faux_nom, "chien", "sdk", tmp_path)
    with pytest.raises(ValueError):
        creer("autre", "dragon", "sdk", tmp_path)
    with pytest.raises(ValueError):
        creer("autre", "chien", "bluetooth", tmp_path)


def test_le_reste_a_brancher_est_liste(tmp_path):
    ici = creer("mon_robot", "humanoide", "sdk", tmp_path)
    lignes = reste_a_brancher(ici)
    assert lignes[0].startswith("Reste à brancher :") and "liaison.py:" in lignes[1]
    assert "Proposition pour un robot « humanoide »" in (ici / "carte.yaml").read_text(encoding="utf-8")
    assert yaml.safe_load((ici / "branchement.yaml").read_text(encoding="utf-8"))["chemin"] == "sdk"


def test_la_ligne_de_commande(tmp_path):
    lignes = []
    assert main(["robot_x", "--dossier", str(tmp_path)], ecrire=lignes.append) == 2  # ni genre ni chemin
    assert main(["robot_x", "--vrai", "--dossier", str(tmp_path)], ecrire=lignes.append) == 2
    assert main(["robot_x", "--genre", "chien", "--chemin", "sdk", "--dossier", str(tmp_path)], ecrire=lignes.append) == 0
    assert any("rien n'a été envoyé à un robot" in l for l in lignes)
    assert main(["robot_x", "--conformite", "--dossier", str(tmp_path)], ecrire=lignes.append) == 0
    assert any("testé sur faux robot" in l for l in lignes) and any("Chronomètre" in l for l in lignes)
    assert main(["inconnu", "--conformite", "--dossier", str(tmp_path)], ecrire=lignes.append) == 2


def test_la_vraie_commande_dans_un_autre_programme_sans_internet(tmp_path):
    """lancer.py brancher, dans un autre programme, Internet coupé ; --vrai sans clavier est refusé."""
    garde = tmp_path / "garde"
    garde.mkdir()
    (garde / "sitecustomize.py").write_text(
        "import socket\n"
        "_c = socket.socket.connect\n"
        "def _connect(self, a):\n"
        "    if isinstance(a, tuple) and a[0] not in ('127.0.0.1', '::1', 'localhost'):\n"
        "        raise ConnectionRefusedError('Internet coupé pour ce test')\n"
        "    return _c(self, a)\n"
        "socket.socket.connect = _connect\n", encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(garde), os.environ.get("PYTHONPATH", "")]).rstrip(os.pathsep)}
    robots = tmp_path / "robots"
    reglages, existait = RACINE / "reglages.yaml", (RACINE / "reglages.yaml").exists()

    def commande(*args):
        return subprocess.run([sys.executable, str(RACINE / "lancer.py"), "brancher", *args, "--dossier", str(robots)],
                              cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)

    try:
        cree = commande("robot_y", "--genre", "roues", "--chemin", "ros2")
        essai = commande("robot_y", "--conformite")
        vrai = commande("robot_y", "--conformite", "--vrai")
    finally:  # lancer.py crée reglages.yaml depuis l'exemple au premier lancement : on ne laisse pas de trace
        exemple = (RACINE / "reglages.exemple.yaml").read_text(encoding="utf-8")
        if not existait and reglages.exists() and reglages.read_text(encoding="utf-8") == exemple:
            reglages.unlink()
    assert cree.returncode == 0, cree.stderr
    assert essai.returncode == 0 and "RÉUSSI" in essai.stdout and "testé sur faux robot" in essai.stdout, essai.stdout
    assert vrai.returncode == 2 and "pas de clavier" in vrai.stdout, vrai.stdout + vrai.stderr
    assert not (robots / "robot_y" / "conformite.yaml").exists()


def test_le_dossier_des_robots_du_projet_est_un_paquet():
    assert (DOSSIER_ROBOTS / "__init__.py").exists()


# ---------------------------------------------------------------- le registre et le système complet
def _reglages(reglages, nom, vrai=False):
    return {**reglages, "robot": {**reglages["robot"], "adaptateur": nom, "vrai_robot": vrai},
            "cerveau": {**reglages["cerveau"], "choix": "regles"}}


def test_le_registre_refuse_un_inconnu_et_un_vrai_robot_sans_conformite(tmp_path, reglages):
    with pytest.raises(ValueError, match="Adaptateur inconnu"):
        registre.fabriquer("personne", _reglages(reglages, "personne"), tmp_path)
    creer("robot_z", "chien", "sdk", tmp_path)
    with pytest.raises(ValueError, match="conformité complet"):
        registre.fabriquer("robot_z", _reglages(reglages, "robot_z", vrai=True), tmp_path)
    (tmp_path / "robot_z" / "conformite.yaml").write_text("complet: {reussi: false}\n", encoding="utf-8")
    assert not registre.conformite_reussie(tmp_path / "robot_z")
    assert not registre.fabriquer("robot_z", _reglages(reglages, "robot_z"), tmp_path).carte().vrai_robot


def test_le_systeme_complet_avec_un_robot_cree_par_l_assistant(tmp_path, reglages):
    """cerveau → gardien (ticket) → prise → adaptateur → faux kit, avec la chaîne du projet. Testé sur faux robot."""
    from commun.systeme import Systeme

    ici = creer("robot_demo", "humanoide", "sdk", tmp_path)
    carte = (ici / "carte.yaml").read_text(encoding="utf-8")
    (ici / "carte.yaml").write_text(carte.replace("capacites: [arreter, etat]",
                                                  "capacites: [se_deplacer, parler, rejouer_geste, arreter, etat]"),
                                    encoding="utf-8")
    r = _reglages(reglages, "robot_demo")

    async def go():
        s = Systeme(r, dossier_journal=tmp_path / "journal", adaptateur=registre.fabriquer("robot_demo", r, tmp_path))
        await s.demarrer()
        try:
            salue = await s.chaine.traiter("Salue", "fr")
            assert salue.statut_action == "reussie", salue
            cuisine = await s.chaine.traiter("Va à la cuisine", "fr")
            assert cuisine.statut_action != "reussie"  # ce robot ne sait pas aller à un lieu nommé : refus expliqué
            assert any(e.type == "action_refusee" for e in s.bus.historique)
            debut = next(e for e in s.bus.historique if e.type == "session_debut")
            assert debut.donnees["mention"] == "testé sur faux robot" and debut.donnees["vrai_robot"] is False
        finally:
            await s.arreter()

    lancer(go())
