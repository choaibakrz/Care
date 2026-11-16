"""Brique 17 — le kit du samedi matin. Internet coupé (conftest.py), aucun modèle. Testé sur faux robot.

On vérifie : l'analyseur repère robot, capacités, langues, durées, critères et sécurité (fr, de, en) ;
le plan a toutes ses parties ; 48 heures sans trou ; 35 personnes sans doublon ; jamais « testé sur vrai robot » ;
la commande marche hors ligne ; les phrases du scénario font ce qui est annoncé sur le faux robot.
"""
from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from briques.b17_kit_samedi.analyseur import analyser, mots_cles, motif, normaliser
from briques.b17_kit_samedi.kit import main
from briques.b17_kit_samedi.plan import (LANGUES_DES_PHRASES, chantiers, config_equipes, connaissances,
                                         etat_des_briques, programme, rendre_plan, rendre_scenario, repartir,
                                         scenario, scenario_chef)
from conftest import lancer

DOSSIER = Path(__file__).resolve().parents[1]
RACINE = DOSSIER.parents[1]
EXEMPLE = DOSSIER / "exemples" / "defi_exemple.md"
EXEMPLE_DE = DOSSIER / "exemples" / "defi_exemple_de.md"
DEFI_EN = """# Challenge 5 — The careful arm

FAKE CHALLENGE written by the team to test the kit.

A robotic arm is fixed on a table in a care home. It must help an elderly person (a mannequin is used for
the demonstration): recognise the cup on the table, pick it up gently and hand it over. The arm also waves to
greet the person. The robot must answer in English or Italian.

Safety rules:
- The robot must not touch the face of the mannequin.
- An emergency stop must be reachable at all times.

Judging criteria:
1. Gentle and safe grasping (40 points)
2. Clear explanation to the person (30 points)
3. Robustness when something fails (30 points)

The demo lasts 4 minutes.
"""
SECTIONS = ["## 1. Résumé du défi", "## 2. Briques prêtes", "## 3. Ce qui manque",
            "## 4. Plan heure par heure", "## 5. Répartition des 35 personnes", "## 6. Risques",
            "## 7. Brouillon de scénario de démonstration", "## 8. Critères du jury → ce que l'on montre → preuve",
            "## Annexe A", "## Annexe B"]
DEFIS = {"fr": EXEMPLE.read_text(encoding="utf-8"), "de": EXEMPLE_DE.read_text(encoding="utf-8"), "en": DEFI_EN}
FAUSSE_MENTION = re.compile(r"teste\w*\s+sur\s+(un\s+)?vrai\s+robot")


# ---------------------------------------------------------------- l'analyseur
def test_l_analyseur_lit_le_faux_defi_en_francais():
    a = analyser(DEFIS["fr"])
    assert a.langue_du_texte == "fr"
    assert a.genre == "humanoide"
    assert {"parler", "plusieurs_langues", "saisir", "se_deplacer", "voir", "demander_aide"} <= set(a.cles)
    assert {"fr", "de", "gsw", "it", "en"} <= set(a.langues)
    assert a.duree_demo is not None and a.duree_demo.secondes == 6 * 60
    assert len(a.criteres) == 6 and sum(c.points for c in a.criteres) == 100
    assert "saisir" in next(c for c in a.criteres if c.texte.startswith("Livraison")).capacites
    assert any("arrêt d'urgence" in s for s in a.securite) and any("enfants" in s for s in a.securite)
    assert not any(s.startswith("Sécurité :") for s in a.securite), "un critère du jury n'est pas une règle"
    assert {"entree", "table", "bouteille"} <= set(a.lieux_objets)


def test_l_analyseur_lit_un_defi_en_allemand():
    a = analyser(DEFIS["de"])
    assert a.langue_du_texte == "de"
    assert a.genre == "chien"
    assert {"se_deplacer", "voir", "gestes", "plusieurs_robots"} <= set(a.cles)
    assert {"de", "gsw", "en"} <= set(a.langues)
    assert a.duree_demo is not None and a.duree_demo.secondes == 8 * 60
    assert [c.points for c in a.criteres] == [30, 30, 20, 20]
    assert "plusieurs_robots" in a.criteres[0].capacites
    assert any("Not-Aus" in s for s in a.securite) and len(a.securite) == 3


def test_l_analyseur_lit_un_defi_en_anglais():
    a = analyser(DEFIS["en"])
    assert a.langue_du_texte == "en"
    assert a.genre == "bras"
    assert {"soin_assistance", "saisir", "voir", "gestes", "parler"} <= set(a.cles)
    assert set(a.langues) == {"en", "it"}
    assert [c.points for c in a.criteres] == [40, 30, 30]
    assert any("must not touch" in s for s in a.securite)
    assert a.duree_demo is not None and a.duree_demo.secondes == 4 * 60


def test_un_texte_vide_ou_sans_rien_pose_les_bonnes_questions():
    a = analyser("Bonjour. Construisez quelque chose de beau.")
    assert a.genre is None and not a.criteres and not a.capacites
    assert any("Quel robot" in q for q in a.questions)
    assert any("grille du jury" in q for q in a.questions)
    plan = rendre_plan(a)
    assert all(s in plan for s in SECTIONS)


def test_les_mots_cles_suivent_les_regles_du_fichier():
    assert normaliser("Begrüßung Élève e-stop") == "begrussung eleve e stop"
    assert motif("apport*").search(normaliser("Apportez la serviette"))
    assert motif("e stop").search(normaliser("Press the E-Stop"))
    assert not motif("parle").search(normaliser("parlement"))  # mot entier
    assert motif("中文").search("说中文")  # chinois : n'importe où
    # Les petits mots courants ne doivent pas tromper le kit.
    a = analyser("Prendre en compte le jury. Montrer au jury la solution. Il va falloir être prêt.")
    assert "saisir" not in a.cles and "gestes" not in a.cles and "se_deplacer" not in a.cles


def test_la_meme_entree_donne_toujours_le_meme_plan():
    assert rendre_plan(analyser(DEFIS["fr"])) == rendre_plan(analyser(DEFIS["fr"]))
    assert rendre_scenario(analyser(DEFIS["de"])) == rendre_scenario(analyser(DEFIS["de"]))


# ---------------------------------------------------------------- le plan
@pytest.mark.parametrize("langue", ["fr", "de", "en"])
def test_le_plan_contient_toutes_les_parties(langue):
    plan = rendre_plan(analyser(DEFIS[langue]))
    positions = [plan.index(s) for s in SECTIONS]
    assert positions == sorted(positions), "les parties sont dans l'ordre"
    for mot in ("Repas", "dort", "GEL DES FONCTIONS", "GEL DU CODE", "Répétition", "DÉMONSTRATION",
                "Responsable", "Sécurité", "Relecteurs sécurité", "brique 3", "tablette", "main humaine",
                "mode local", "fiche de vérité", "boîte noire", "NON_TESTE.md", "à vérifier"):
        assert mot.lower() in plan.lower(), mot


def test_le_programme_couvre_48_heures_sans_trou():
    debut = {"Samedi": 0, "Dimanche": 24, "Lundi": 48}
    heure = 9
    types = set()
    for jour in programme()["jours"]:
        decalage = debut[jour["jour"].split()[0]]
        for b in jour["blocs"]:
            assert decalage + b["h"] == heure, f"trou ou chevauchement à {jour['jour']} {b['h']} h"
            heure += b.get("duree", 1)
            types.add(b["type"])
    assert heure == 48 + 9, "du samedi 9 h au lundi 9 h"
    assert {"repas", "sommeil", "gel", "repetition", "demonstration", "securite"} <= types


@pytest.mark.parametrize("langue", ["fr", "de", "en"])
def test_35_personnes_reparties_sans_doublon(langue):
    a = analyser(DEFIS[langue])
    etats, conn = etat_des_briques(), connaissances()
    equipes = repartir(chantiers(a, etats, conn), etats)
    personnes = [p for e in equipes for p in e.personnes]
    assert len(personnes) == 35 == config_equipes()["total"]
    assert sorted(personnes) == [f"P{i:02d}" for i in range(1, 36)], "chacun une fois, personne oublié"
    noms = {e.nom for e in equipes}
    assert {"Responsable", "Sécurité", "Relecteurs sécurité", "Adaptateurs", "Gardien", "Tests"} <= noms
    assert next(e for e in equipes if e.nom == "Responsable").prenoms == ["Hiba"]
    # La même chose, lue dans le plan (annexe A) : 35 lignes, 35 personnes différentes.
    plan = rendre_plan(a)
    annexe = plan.split("## Annexe A")[1].split("## Annexe B")[0]
    lignes = re.findall(r"^\| (P\d\d) \|", annexe, flags=re.M)
    assert len(lignes) == 35 and len(set(lignes)) == 35


def test_les_renforts_vont_aux_briques_qui_manquent():
    a = analyser(DEFIS["de"])  # deux robots : brique 16, à faire
    etats, conn = etat_des_briques(), connaissances()
    liste = chantiers(a, etats, conn)
    assert liste[0].numero == 3, "l'adaptateur du vrai robot passe toujours en premier"
    assert 16 in [c.numero for c in liste]
    equipes = repartir(liste, etats)
    assert any(16 in e.briques and e.renforts for e in equipes)


@pytest.mark.parametrize("langue", ["fr", "de", "en"])
def test_le_plan_ne_dit_jamais_teste_sur_vrai_robot(langue):
    a = analyser(DEFIS[langue])
    for texte in (rendre_plan(a), rendre_scenario(a)):
        assert not FAUSSE_MENTION.search(normaliser(texte))


def test_meme_si_le_defi_le_dit_le_plan_ne_le_recopie_pas():
    texte = DEFIS["fr"] + "\n## Règles\n- Le robot doit être testé sur vrai robot avant la démonstration.\n"
    a = analyser(texte)
    assert any("vrai robot" in s for s in a.securite)
    assert not FAUSSE_MENTION.search(normaliser(rendre_plan(a)))


def test_le_plan_d_exemple_est_la_et_honnete():
    plan = (DOSSIER / "exemples" / "plan_exemple.md").read_text(encoding="utf-8")
    assert all(s in plan for s in SECTIONS)
    assert not FAUSSE_MENTION.search(normaliser(plan))
    s = yaml.safe_load((DOSSIER / "exemples" / "plan_exemple_scenario.yaml").read_text(encoding="utf-8"))
    assert s["etapes"]


# ---------------------------------------------------------------- le scénario
@pytest.mark.parametrize("langue", ["fr", "de", "en"])
def test_le_scenario_yaml_suit_le_format_de_la_brique_15(langue):
    from briques.b15_chef_demo.scenario import lire

    texte = rendre_scenario(analyser(DEFIS[langue]))
    sc = lire(yaml.safe_load(texte), "brouillon du kit")  # toute clé inconnue serait refusée
    genres = [e.attendu.genre for e in sc.etapes if e.attendu]
    assert "refus" in genres and "question" in genres, "toujours : un refus expliqué et une question"
    assert any(e.genre == "fiche" for e in sc.etapes), "toujours : la fiche de vérité"
    for e in sc.etapes:
        if e.genre == "dire":
            assert e.dire.langue in LANGUES_DES_PHRASES and e.duree_max_s and e.plan_b
        if e.attendu and e.attendu.genre == "confirmation":
            suivante = sc.etapes[sc.etapes.index(e) + 1]
            assert suivante.genre == "dire" and suivante.attendu.action == e.attendu.action, "après l'ordre : « oui »"
    assert "verifier" in texte and "lancer.py scenario" in texte


@pytest.mark.parametrize("langue,carte", [("fr", "humanoide"), ("de", "chien"), ("en", "bras")])
def test_le_chef_de_demonstration_joue_le_brouillon_sur_le_faux_robot(fabrique_systeme, langue, carte):
    """Testé sur faux robot, cerveau à règles : chaque étape « dire » du brouillon réussit du premier coup."""
    from briques.b15_chef_demo.chef import ChefDemo
    from briques.b15_chef_demo.scenario import lire

    a = analyser(DEFIS[langue])
    sc = lire(scenario_chef(a))
    s = fabrique_systeme(carte)

    async def jouer():
        await s.demarrer()
        try:
            return await ChefDemo(s, sc, acceleration=200.0).jouer()
        finally:
            await s.arreter()

    res = lancer(jouer())
    dires = [e for e in res.etapes if e.genre == "dire"]
    assert dires and all(e.resultat == "reussie" for e in dires), [(e.nom, e.resultat, e.detail) for e in dires]


@pytest.mark.parametrize("langue,carte", [("fr", "humanoide"), ("de", "chien"), ("en", "bras")])
def test_les_phrases_du_scenario_font_ce_qui_est_annonce_sur_le_faux_robot(fabrique_systeme, langue, carte):
    """Le brouillon ne promet rien que le faux robot ne fasse : testé sur faux robot (cerveau à règles)."""
    a = analyser(DEFIS[langue])
    assert a.genre == carte
    etapes = [e for e in scenario(a)["etapes"] if e["type"] == "parole"]
    s = fabrique_systeme(carte)

    async def jouer():
        await s.demarrer()
        try:
            for e in etapes:
                r = await s.chaine.traiter(e["dire"], e["langue"])
                if e["attendu"] == "confirmation":
                    assert r.verdict == "oui" and r.statut_action is None, e["nom"]
                    r = await s.chaine.traiter(e["puis_dire"], e["langue"])
                    assert r.statut_action == "reussie", (e["nom"], r.reponses)
                elif e["attendu"] == "action":
                    assert r.verdict == "oui" and r.statut_action == "reussie", (e["nom"], r.reponses)
                elif e["attendu"] == "question":
                    assert r.decision.genre == "question", (e["nom"], r.reponses)
                elif e["attendu"] == "aide":
                    assert r.verdict == "humain" and r.statut_action is None, (e["nom"], r.reponses)
                elif e["attendu"] == "refus":
                    assert r.verdict == "non" and r.statut_action is None, (e["nom"], r.reponses)
        finally:
            await s.arreter()

    lancer(jouer())


# ---------------------------------------------------------------- la commande, hors ligne
def test_la_commande_marche_hors_ligne(tmp_path, capsys):
    """Dans ce processus, Internet est coupé (conftest.py) : toute connexion ferait échouer le test."""
    sortie = tmp_path / "plan.md"
    assert main([str(EXEMPLE), "--sortie", str(sortie)]) == 0
    assert all(s in sortie.read_text(encoding="utf-8") for s in SECTIONS)
    assert yaml.safe_load((tmp_path / "plan_scenario.yaml").read_text(encoding="utf-8"))["etapes"]
    assert main([str(tmp_path / "absent.md")]) == 2


def test_lancer_py_kit_samedi_dans_un_autre_processus_sans_internet(tmp_path):
    """La vraie commande, dans un autre programme Python, avec Internet coupé dès le démarrage (sitecustomize)."""
    garde = tmp_path / "garde"
    garde.mkdir()
    (garde / "sitecustomize.py").write_text(
        "import pathlib, socket\n"
        "pathlib.Path(__file__).with_name('garde_active').write_text('oui')\n"
        "_c = socket.socket.connect\n"
        "def _connect(self, a):\n"
        "    if isinstance(a, tuple) and a[0] not in ('127.0.0.1', '::1', 'localhost'):\n"
        "        raise ConnectionRefusedError('Internet coupé pour ce test')\n"
        "    return _c(self, a)\n"
        "socket.socket.connect = _connect\n"
        "_g = socket.getaddrinfo\n"
        "def _getaddrinfo(h, *a, **k):\n"
        "    if h not in (None, 'localhost', '127.0.0.1', '::1'):\n"
        "        raise socket.gaierror('Internet coupé pour ce test')\n"
        "    return _g(h, *a, **k)\n"
        "socket.getaddrinfo = _getaddrinfo\n", encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(garde), os.environ.get("PYTHONPATH", "")]).rstrip(os.pathsep)}
    reglages, existait = RACINE / "reglages.yaml", (RACINE / "reglages.yaml").exists()
    try:
        r = subprocess.run([sys.executable, str(RACINE / "lancer.py"), "kit-samedi", str(EXEMPLE_DE),
                            "--sortie", str(tmp_path / "plan.md")], cwd=tmp_path, env=env,
                           capture_output=True, text=True, timeout=120)
    finally:
        # lancer.py crée reglages.yaml depuis l'exemple au premier lancement : on ne laisse pas de trace.
        exemple = (RACINE / "reglages.exemple.yaml").read_text(encoding="utf-8")
        if not existait and reglages.exists() and reglages.read_text(encoding="utf-8") == exemple:
            reglages.unlink()
    assert r.returncode == 0, r.stderr
    assert (garde / "garde_active").exists(), "la coupure d'Internet était bien active"
    assert all(s in (tmp_path / "plan.md").read_text(encoding="utf-8") for s in SECTIONS)
    assert (tmp_path / "plan_scenario.yaml").exists()


def test_le_code_du_kit_n_utilise_pas_le_reseau():
    interdits = {"socket", "urllib", "http", "httpx", "requests", "aiohttp", "websockets", "ssl"}
    for f in DOSSIER.glob("*.py"):
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Import):
                modules = [a.name for a in n.names]
            elif isinstance(n, ast.ImportFrom):
                modules = [n.module or ""]
            else:
                continue
            assert not {m.split(".")[0] for m in modules} & interdits, f"{f.name} importe {modules}"


# ---------------------------------------------------------------- les fichiers de données
def _feuilles(x, chemin=""):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from _feuilles(v, f"{chemin}/{k}")
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from _feuilles(v, f"{chemin}[{i}]")
    else:
        yield chemin, x


def test_l_etat_des_briques_est_honnete_et_bien_forme():
    etats = etat_des_briques()
    assert sorted(etats) == list(range(1, 18))
    for n, b in etats.items():
        if b["etat"] == "prete":  # « prête » se prouve : des tests, des tâches, un essai sur le faux robot
            assert (RACINE / b["dossier"] / "tests").is_dir() and b.get("taches"), f"brique {n} : prête sans tests ?"
            assert b["faux_robot"] in ("oui", "sans_objet"), f"brique {n} : prête sans essai sur le faux robot ?"
    for n, b in etats.items():
        assert b["etat"] in ("prete", "socle", "a_faire")
        assert b["vrai_robot"] in ("jamais", "sans_objet"), f"brique {n} : rien n'est essayé sur un vrai robot"
        dossier_existe = bool(b.get("dossier")) and (RACINE / b["dossier"]).is_dir()
        assert dossier_existe == (b["etat"] != "a_faire"), f"brique {n} : état et dossier ne vont pas ensemble"
        if b.get("taches"):
            assert (RACINE / b["taches"]).is_file(), f"brique {n} : {b['taches']} introuvable"
        if b["etat"] == "a_faire":
            assert b.get("premieres_taches"), f"brique {n} : écrire au moins une première tâche"
        for cle, v in b.items():  # un « : » dans une phrase de liste en fait un dictionnaire : mettre la phrase entre « " »
            if isinstance(v, list):
                assert all(isinstance(x, str) for x in v), f"brique {n} : {cle} contient autre chose qu'une phrase"
    # Un « : » oublié dans le YAML transforme une phrase en dictionnaire : on le repère ici.
    for chemin, v in _feuilles(_brut(RACINE / "briques" / "etat_des_briques.yaml")):
        assert v is None or isinstance(v, (str, bool, int)), chemin


def _brut(chemin: Path):
    return yaml.safe_load(chemin.read_text(encoding="utf-8"))


def test_les_fichiers_du_kit_vont_ensemble():
    mc, conn = mots_cles(), connaissances()
    assert set(mc["capacites"]) == set(conn["capacites"]), "mêmes capacités dans mots_cles.yaml et connaissances.yaml"
    for cle, info in conn["capacites"].items():
        assert set(info["briques"]) <= set(range(1, 18)), cle
        for champ in ("nom", "risque", "parade", "montrer", "preuve"):
            assert isinstance(info[champ], str) and info[champ], (cle, champ)
    for e in conn["etapes"]:
        assert set(e["plan_b"]) <= set(conn["plans_b"]), e["id"]
        assert set(e.get("si", []) + e.get("si_un_de", [])) <= set(conn["capacites"]), e["id"]
        assert set(e.get("liens", [])) <= set(conn["capacites"]) | set(conn["themes_jury"]), e["id"]
        if e["type"] == "parole":
            assert set(LANGUES_DES_PHRASES) <= set(e["dire"]), e["id"]
    for fichier in ("mots_cles.yaml", "connaissances.yaml", "programme_48h.yaml", "equipes.yaml"):
        for chemin, v in _feuilles(_brut(DOSSIER / fichier)):
            assert v is None or isinstance(v, (str, bool, int)), f"{fichier} {chemin}"


def test_la_skill_et_la_liste_du_samedi_existent():
    skill = (RACINE / "savoir-faire" / "lire-le-defi" / "SKILL.md").read_text(encoding="utf-8")
    entete = yaml.safe_load(skill.split("---")[1])
    assert entete["name"] == "lire-le-defi" and entete["description"]
    assert "kit-samedi" in skill and "NON_TESTE.md" in skill
    liste = (RACINE / "docs/projet/SAMEDI_MATIN.md").read_text(encoding="utf-8")
    assert liste.count("- [ ]") >= 20
    for mot in ("conformité", "arrêt d'urgence", "PHYSIQUE", "code_equipe", "feu orange", "kit-samedi",
                "python3 lancer.py tests"):
        assert mot in liste, mot
