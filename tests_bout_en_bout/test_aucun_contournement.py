"""Aucun chemin du code ne permet d'agir sans passer par le gardien et la prise.

Ce test lit tout le code Python du projet (sans l'exécuter). Il refuse :
1. tout appel aux commandes du robot sur autre chose que la prise (même via un autre nom de variable) ;
2. tout accès aux parties cachées de la prise, du gardien ou du pupitre de simulation ;
3. tout getattr/setattr/vars avec un nom calculé (moyen classique de cacher un accès) ;
4. toute fabrication de ticket ailleurs que dans le gardien ;
5. que le système garde une référence vers l'adaptateur.
Les fichiers de test sont exclus : ils essaient justement de tricher, pour vérifier que la prise refuse.
Limite honnête : Python ne peut pas tout interdire. Ce test attrape les erreurs et les raccourcis, pas un saboteur.
"""
from __future__ import annotations

import ast
import importlib
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
COMMANDES_ROBOT = {"demarrer", "suivre", "annuler", "arret_urgence", "rearmer", "etat_robot", "battement",
                   "connecter", "deconnecter"}
FICHIER_PRISE = "briques/b01_prise/prise.py"
# L'intérieur des adaptateurs (ils parlent au robot, par définition) : exclu des deux premières règles.
# PAS exclus (relecture de la brique 3) : briques/b03_adaptateurs/robots/, assistant.py, registre.py.
INTERIEUR_ADAPTATEURS = ("briques/b02_faux_robot/", "briques/b03_adaptateurs/modele_vide/",
                         "briques/b03_adaptateurs/chemins/")
# Le témoin du test de conformité enveloppe un adaptateur et relaie ses commandes (seule la prise l'appelle).
RELAIS = {"briques/b03_adaptateurs/conformite_deux_temps.py"}
# Le registre de la brique 3 : le seul à appeler la fabrique d'un robot de robots/ (pour le système, la conformité).
REGISTRE = "briques/b03_adaptateurs/registre.py"
# Seul le test de conformité en ligne de commande demande au registre une fabrique « pour la conformité ».
CONFORMITE_CLI = "briques/b03_adaptateurs/assistant.py"
AUTORISES_TICKET = {"briques/b07_gardien/gardien.py", "briques/b01_prise/ticket.py"}
CACHES = {"_Prise__": FICHIER_PRISE, "_Gardien__": "briques/b07_gardien/gardien.py",
          "_Simulation__": "commun/systeme.py", "_Guichet__": "briques/b01_prise/ticket.py"}


def _fichiers():
    for p in RACINE.rglob("*.py"):
        rel = p.relative_to(RACINE).as_posix()
        if rel.startswith((".venv/", "modeles/", "savoir-faire/")) or "/tests/" in rel or rel.startswith("tests_bout_en_bout/") \
                or rel == "conftest.py":
            continue
        yield rel, ast.parse(p.read_text(encoding="utf-8"))


def _dernier_nom(noeud) -> str:
    texte = ast.unparse(noeud)
    return texte.split(".")[-1]


def test_les_commandes_du_robot_ne_passent_que_par_la_prise():
    """Appel OU simple lecture (f = x.demarrer) d'une commande du robot : seulement sur la prise."""
    fautes = []
    for rel, arbre in _fichiers():
        if rel == FICHIER_PRISE or rel.startswith(INTERIEUR_ADAPTATEURS) or rel in RELAIS:
            continue
        for n in ast.walk(arbre):
            if isinstance(n, ast.Attribute) and n.attr in COMMANDES_ROBOT:
                recepteur = _dernier_nom(n.value)
                permis = recepteur == "prise" or (n.attr == "demarrer" and recepteur in {"systeme", "s", "cerveau"})
                if not permis:
                    fautes.append(f"{rel}:{n.lineno} {ast.unparse(n)}")
    assert not fautes, "Commandes du robot hors de la prise :\n" + "\n".join(fautes)


def _module(rel: str, n: ast.ImportFrom) -> str:
    """Le nom complet du module importé (aussi pour « from .liaison import … »)."""
    if not n.level:
        return n.module or ""
    paquet = rel[:-3].split("/")[:-n.level]
    return ".".join(paquet + ([n.module] if n.module else []))


def _fabrique_un_robot(module: str, nom: str) -> bool:
    """Ce nom est-il un adaptateur, une liaison ou un faux robot ? (le construire = ouvrir une liaison avec un robot)"""
    from briques.b01_prise.adaptateur import Adaptateur
    from briques.b02_faux_robot.faux_robot import FauxRobot
    from briques.b03_adaptateurs.chemins.ros2.faux_ros2 import FauxRclpy, FauxRobotROS2
    from briques.b03_adaptateurs.chemins.sdk.faux_sdk import FauxKit
    from briques.b03_adaptateurs.modele_vide.liaison import LiaisonVide

    try:
        objet = getattr(importlib.import_module(module), nom)
    except Exception:
        return nom[:1].isupper()  # introuvable : prudence
    return isinstance(objet, type) and issubclass(objet, (Adaptateur, LiaisonVide, FauxKit, FauxRclpy, FauxRobotROS2,
                                                           FauxRobot))


def test_un_adaptateur_ne_se_fabrique_que_dans_le_systeme():
    """Sinon on pourrait ouvrir une deuxième liaison avec le robot, sans prise ni gardien.
    Permis : commun/systeme.py ; l'intérieur des adaptateurs ; la fonction `fabriquer` de robots/NOM/adaptateur.py
    (c'est la fabrique elle-même) ; `….fabriquer(…)` d'un robot seulement dans le registre ; la fabrique « pour la
    conformité » seulement dans la ligne de commande de la conformité."""
    fautes = []
    for rel, arbre in _fichiers():
        if rel.startswith(INTERIEUR_ADAPTATEURS) or rel == "commun/systeme.py":
            continue
        importes = {}
        for n in ast.walk(arbre):
            if isinstance(n, ast.ImportFrom):
                module = _module(rel, n)
                if module.startswith(("briques.b02_faux_robot", "briques.b03_adaptateurs")):
                    importes.update({a.asname or a.name: (module, a.name) for a in n.names})
        usine = rel.startswith("briques/b03_adaptateurs/robots/") and rel.endswith("/adaptateur.py")
        zones_usine = [(f.lineno, f.end_lineno) for f in arbre.body
                       if usine and isinstance(f, ast.FunctionDef) and f.name == "fabriquer"]
        for n in ast.walk(arbre):
            if not isinstance(n, ast.Call):
                continue
            nom = ast.unparse(n.func).split(".")[-1]
            faute = nom == "_creer_adaptateur"
            faute |= nom in importes and (nom == "fabriquer" or _fabrique_un_robot(*importes[nom]))
            faute |= isinstance(n.func, ast.Attribute) and n.func.attr == "fabriquer" and rel != REGISTRE
            faute |= (isinstance(n.func, ast.Name) and n.func.id == "getattr" and len(n.args) >= 2
                      and isinstance(n.args[1], ast.Constant) and n.args[1].value == "fabriquer" and rel != REGISTRE)
            faute |= nom == "fabrique_pour_conformite" and rel not in (REGISTRE, CONFORMITE_CLI)
            if faute and not any(a <= n.lineno <= b for a, b in zones_usine):
                fautes.append(f"{rel}:{n.lineno} {ast.unparse(n.func)}")
    assert not fautes, "Adaptateur fabriqué hors du système :\n" + "\n".join(fautes)


def test_la_regle_attrape_une_fabrique_cachee():
    """La règle ci-dessus attrape bien les raccourcis connus (sur un faux fichier, jamais lancé)."""
    exemple = (
        "from briques.b03_adaptateurs.registre import charger_robot\n"
        "from briques.b03_adaptateurs.modele_vide.adaptateur import AdaptateurModele\n"
        "from briques.b03_adaptateurs.chemins.sdk.faux_sdk import FauxKit\n"
        "a = charger_robot('x').fabriquer(vrai=True)\n"
        "b = getattr(charger_robot('x'), 'fabriquer')()\n"
        "c = AdaptateurModele('carte.yaml', None)\n"
        "d = FauxKit()\n")
    arbre = ast.parse(exemple)
    importes = {}
    for n in ast.walk(arbre):
        if isinstance(n, ast.ImportFrom):
            importes.update({a.name: (n.module, a.name) for a in n.names})
    trouves = []
    for n in ast.walk(arbre):
        if isinstance(n, ast.Call):
            nom = ast.unparse(n.func).split(".")[-1]
            if (nom in importes and _fabrique_un_robot(*importes[nom])) or \
                    (isinstance(n.func, ast.Attribute) and n.func.attr == "fabriquer") or \
                    (isinstance(n.func, ast.Name) and n.func.id == "getattr" and n.args[1].value == "fabriquer"):
                trouves.append(n.lineno)
    assert sorted(set(trouves)) == [4, 5, 6, 7]
    assert not _fabrique_un_robot("briques.b03_adaptateurs.modele_vide.liaison", "ABrancher")  # une erreur, pas un robot


def test_personne_ne_touche_aux_parties_cachees():
    fautes = []
    for rel, arbre in _fichiers():
        for n in ast.walk(arbre):
            noms = []
            if isinstance(n, ast.Attribute):
                noms.append(n.attr)
            if isinstance(n, ast.Constant) and isinstance(n.value, str):
                noms.append(n.value)
            for nom in noms:
                for prefixe, proprietaire in CACHES.items():
                    if prefixe in nom and rel != proprietaire:
                        fautes.append(f"{rel}:{n.lineno} {nom}")
                if "__adaptateur" in nom and rel != FICHIER_PRISE:
                    fautes.append(f"{rel}:{n.lineno} {nom}")
    assert not fautes, "Accès aux parties cachées :\n" + "\n".join(fautes)


def test_pas_de_getattr_avec_un_nom_calcule():
    fautes = []
    for rel, arbre in _fichiers():
        for n in ast.walk(arbre):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("getattr", "setattr", "delattr", "vars"):
                if n.func.id == "vars" or len(n.args) < 2 or not isinstance(n.args[1], ast.Constant):
                    fautes.append(f"{rel}:{n.lineno} {ast.unparse(n)}")
            if isinstance(n, ast.Attribute) and n.attr == "__dict__":
                fautes.append(f"{rel}:{n.lineno} __dict__")
    assert not fautes, "Accès par nom calculé :\n" + "\n".join(fautes)


def test_seul_le_gardien_fabrique_des_tickets():
    fautes = []
    for rel, arbre in _fichiers():
        if rel in AUTORISES_TICKET:
            continue
        for n in ast.walk(arbre):
            if isinstance(n, ast.Call):
                f = ast.unparse(n.func)
                if f.split(".")[-1] in ("Guichet", "Ticket") or (f.endswith(".emettre") and "bus" not in f):
                    fautes.append(f"{rel}:{n.lineno} {f}")
    assert not fautes, "Fabrication de ticket hors du gardien :\n" + "\n".join(fautes)


def test_le_systeme_ne_garde_pas_l_adaptateur():
    arbre = ast.parse((RACINE / "commun/systeme.py").read_text(encoding="utf-8"))
    for n in ast.walk(arbre):
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Name) and n.value.id == "robot":
            cibles = [ast.unparse(t) for t in n.targets]
            assert not any(c.startswith("self.") for c in cibles), f"systeme.py:{n.lineno} garde l'adaptateur"


def test_le_cerveau_ne_connait_ni_la_prise_ni_le_gardien():
    for rel, arbre in _fichiers():
        if not rel.startswith("briques/b06_cerveau/") or rel == "briques/b06_cerveau/banc_cerveau.py":
            continue  # le banc d'essai n'est pas le cerveau : il utilise le gardien pour JUGER les réponses
        for n in ast.walk(arbre):
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                module = getattr(n, "module", "") or ""
                noms = [a.name for a in n.names]
                assert module.split(".")[-1] not in ("prise", "ticket", "adaptateur") and "b07_gardien" not in module, \
                    f"{rel} importe {module}"
                assert not {"Prise", "Guichet", "Ticket", "Adaptateur"} & set(noms), f"{rel} importe {noms}"
