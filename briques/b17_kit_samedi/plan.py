"""Brique 17 — Du texte du défi à un plan lisible (Markdown) et à un brouillon de scénario (YAML).

Tout vient de fichiers du dépôt : briques/etat_des_briques.yaml, les TACHES.md, NON_TESTE.md, et les fichiers YAML
de ce dossier (connaissances, programme_48h, equipes). Aucun Internet, aucun modèle : même défi → même plan.
Le plan ne dit jamais qu'une chose est essayée sur un vrai robot : rien ne l'est encore (NON_TESTE.md).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .analyseur import DOSSIER, RACINE, Analyse, langues_du_projet, mots_cles, normaliser, trouver

ETAT_DES_BRIQUES = RACINE / "briques" / "etat_des_briques.yaml"
NON_TESTE = RACINE / "NON_TESTE.md"
CARTES_FAUX_ROBOT = RACINE / "briques" / "b02_faux_robot" / "cartes"
ETATS = {"prete": "prête", "socle": "version minimale", "a_faire": "à faire"}
NOMS_GENRES = {"humanoide": "humanoïde", "chien": "chien (quatre pattes)", "bras": "bras",
               "roues": "robot à roues", "autre": "autre (drone…)"}
ATTENDUS = {"action": "le robot agit et le dit",
            "confirmation": "le robot répète l'ordre et attend « oui » ; après le « oui », il agit",
            "question": "le robot pose une question au lieu de deviner",
            "refus": "le robot refuse et explique pourquoi, dans la même langue",
            "aide": "le robot lève la main : un humain doit d'abord accepter (le gardien revérifie)"}
LANGUES_DES_PHRASES = ("fr", "de", "en", "it")  # langues des phrases toutes prêtes du scénario
ROTATIONS = ("R1", "R2", "R3")
# Garde-fou : le plan ne doit jamais prétendre un essai sur vrai robot, même en recopiant le texte du défi.
FAUSSE_MENTION = re.compile(r"test[ée]e?s?\s+sur\s+(?:un\s+)?vrai\s+robot", re.IGNORECASE)


def _yaml(chemin: Path) -> dict:
    return yaml.safe_load(Path(chemin).read_text(encoding="utf-8"))


def connaissances() -> dict:
    return _yaml(DOSSIER / "connaissances.yaml")


def programme() -> dict:
    return _yaml(DOSSIER / "programme_48h.yaml")


def config_equipes() -> dict:
    return _yaml(DOSSIER / "equipes.yaml")


def etat_des_briques() -> dict[int, dict]:
    return {int(n): b for n, b in _yaml(ETAT_DES_BRIQUES)["briques"].items()}


def genres_du_faux_robot() -> set[str]:
    return {_yaml(p).get("genre") for p in sorted(CARTES_FAUX_ROBOT.glob("*.yaml"))}


def sans_fausse_mention(texte: str) -> str:
    return FAUSSE_MENTION.sub("essai sur un vrai robot (pas encore fait)", texte)


# ---------------------------------------------------------------- briques, tâches, chantiers
def taches_du_fichier(chemin: str | None) -> list[str]:
    """Les tâches non cochées (« - [ ] … ») d'un TACHES.md."""
    if not chemin or not (RACINE / chemin).exists():
        return []
    lignes = (RACINE / chemin).read_text(encoding="utf-8").splitlines()
    return [re.sub(r"^\s*-\s*\[ \]\s*", "", l).strip() for l in lignes if re.match(r"^\s*-\s*\[ \]", l)]


def taches(brique: dict, morceaux: list[str] | None = None, maximum: int = 3) -> list[str]:
    liste = taches_du_fichier(brique.get("taches"))
    if not liste:
        return list(brique.get("premieres_taches") or [])[:maximum]
    if morceaux:
        choisies = [t for t in liste if any(normaliser(m) in normaliser(t) for m in morceaux)]
        if choisies:
            return choisies[:maximum]
    return liste[:2]


def etat_capacite(cle: str, etats: dict[int, dict], conn: dict) -> str:
    e = [etats[n]["etat"] for n in conn["capacites"][cle]["briques"]]
    if all(x == "prete" for x in e):
        return "prête"
    if any(x in ("prete", "socle") for x in e):
        return "en partie"
    return "à construire"


def langues_manquantes(a: Analyse) -> list[str]:
    connues = langues_du_projet()
    return [code for code in a.langues if code not in connues]


@dataclass
class Chantier:
    numero: int
    nom: str
    pourquoi: list[str] = field(default_factory=list)
    taches: list[str] = field(default_factory=list)

    def titre(self) -> str:
        return f"{self.nom} (brique {self.numero})"


def chantiers(a: Analyse, etats: dict[int, dict], conn: dict) -> list[Chantier]:
    """Les briques à construire pour CE défi, la plus importante d'abord. L'adaptateur (brique 3) est toujours là."""
    liste: dict[int, Chantier] = {}

    def ajouter(n: int, pourquoi: str, morceaux: list[str] | None = None) -> None:
        if n not in liste:
            liste[n] = Chantier(n, etats[n]["nom"], [], taches(etats[n], morceaux))
        if pourquoi not in liste[n].pourquoi:
            liste[n].pourquoi.append(pourquoi)

    ajouter(3, "brancher le vrai robot (toujours nécessaire)")
    for c in sorted(a.capacites, key=lambda c: -c.priorite):  # tri stable : à égalité, l'ordre de mots_cles.yaml
        info = conn["capacites"][c.cle]
        for n in info["briques"]:
            if etats[n]["etat"] != "prete":
                ajouter(n, info["nom"], (info.get("taches") or {}).get(n))
    manquantes = langues_manquantes(a)
    if manquantes:
        noms = ", ".join(mots_cles()["noms_des_langues"].get(c, c) for c in manquantes)
        ajouter(4, f"langues à ajouter : {noms}", ["commun/langues.yaml", "Une voix", "12 phrases", "oui_non"])
    if a.genre and a.genre not in genres_du_faux_robot():
        ajouter(2, f"faux robot « {NOMS_GENRES.get(a.genre, a.genre)} » pour s'entraîner", [a.genre])
    return list(liste.values())


# ---------------------------------------------------------------- les 35 personnes
@dataclass
class Equipe:
    nom: str
    mission: str
    briques: list[int]
    verifie: str
    membres: list[str] = field(default_factory=list)
    renforts: list[str] = field(default_factory=list)
    prenoms: list[str] = field(default_factory=list)
    de_base: bool = False

    @property
    def personnes(self) -> list[str]:
        return self.membres + self.renforts


def repartir(liste_chantiers: list[Chantier], etats: dict[int, dict]) -> list[Equipe]:
    """Chaque personne (P01…P35) dans UNE seule équipe. Les renforts vont aux chantiers, le premier d'abord."""
    cfg = config_equipes()
    numeros = iter(range(1, cfg["total"] + 1))

    def personnes(k: int) -> list[str]:
        return [f"P{next(numeros):02d}" for _ in range(k)]

    equipes = [Equipe(r["nom"], r["mission"], list(r["briques"]), r["verifie"], personnes(r["nombre"]),
                      prenoms=list(r.get("prenoms") or [])) for r in cfg["roles_fixes"]]
    equipes += [Equipe(r["nom"], r["mission"], list(r["briques"]), r["verifie"], personnes(r["nombre"]), de_base=True)
                for r in cfg["equipes_de_base"]]
    reste = cfg["total"] - sum(len(e.membres) for e in equipes)
    if reste < 0:
        raise ValueError("equipes.yaml demande plus de personnes que « total »")

    compte = {c.numero: 0 for c in liste_chantiers}
    while reste > 0 and any(v < cfg["max_renforts_par_brique"] for v in compte.values()):
        for n in compte:
            if reste and compte[n] < cfg["max_renforts_par_brique"]:
                compte[n] += 1
                reste -= 1

    for c in liste_chantiers:
        if not compte[c.numero]:
            continue
        equipe = next((e for e in equipes if e.de_base and c.numero in e.briques), None)
        if equipe is None:
            relecture = " + relecteurs sécurité" if c.numero in (1, 3, 7) else ""
            equipe = Equipe(f"Brique {c.numero} — {c.nom}", "Construire la brique.", [c.numero], "Tests" + relecture)
            equipes.append(equipe)
        equipe.mission += " Pour ce défi : " + " ; ".join(c.pourquoi) + "."
        equipe.renforts += personnes(compte[c.numero])
    if reste:  # tous les chantiers sont pleins : le reste aide les tests et les répétitions
        tests = next(e for e in equipes if e.nom == "Tests")
        tests.renforts += personnes(reste)
    return equipes


def rotation(index_equipe: int, index_personne: int) -> str:
    return ROTATIONS[(index_equipe + index_personne) % len(ROTATIONS)]


# ---------------------------------------------------------------- le scénario
def _etape_choisie(e: dict, a: Analyse) -> bool:
    genre = a.genre or "humanoide"
    if genre in (e.get("pas_pour") or []):
        return False
    if e.get("seulement_pour") and genre not in e["seulement_pour"]:
        return False
    if e.get("toujours"):
        return True
    if e.get("si_un_de") and any(c in a.cles for c in e["si_un_de"]):
        return True
    return bool(e.get("si")) and all(c in a.cles for c in e["si"])


def _critere_lie(liens: list[str], a: Analyse, conn: dict):
    """Le premier lien (dans l'ordre de « liens ») qui correspond à un critère du jury."""
    for lien in liens:
        for c in a.criteres:
            if lien in c.capacites:
                return c
            theme = conn["themes_jury"].get(lien)
            if theme and trouver(normaliser(c.texte), theme["mots"]):
                return c
    return None


def langues_de_la_demo(a: Analyse) -> list[str]:
    """Les langues demandées qui ont des phrases toutes prêtes ; la langue du texte du défi d'abord."""
    demandees = [code for code in mots_cles()["langues"] if code in a.langues and code in LANGUES_DES_PHRASES]
    demandees.sort(key=lambda code: code != a.langue_du_texte)  # tri stable : le reste garde son ordre
    if demandees:
        return demandees
    return [a.langue_du_texte if a.langue_du_texte in LANGUES_DES_PHRASES else "fr"]


def faux_robot_du_scenario(a: Analyse) -> str:
    """Le faux robot sur lequel les phrases du scénario sont essayées (par un test de la brique 17)."""
    return a.genre if a.genre in ("humanoide", "chien", "bras") else "humanoide"


def scenario(a: Analyse, conn: dict | None = None) -> dict:
    """Le brouillon de scénario, en format simple (pour le plan écrit). Pour le chef : scenario_chef()."""
    conn = conn or connaissances()
    langues = langues_de_la_demo(a)
    etapes, ids, i_parole = [], [], 0
    for e in conn["etapes"]:
        if not _etape_choisie(e, a):
            continue
        ids.append(e["id"])
        etape: dict = {"nom": e["nom"], "type": e["type"]}
        if e["type"] == "parole":
            langue = langues[i_parole % len(langues)]
            i_parole += 1
            etape |= {"dire": e["dire"][langue], "langue": langue}
            if e.get("puis_dire"):
                etape["puis_dire"] = e["puis_dire"][langue]
            etape["attendu"] = e["attendu"]
        else:
            etape["action"] = e["action"]
        etape["duree_max_s"] = e["duree_max_s"]
        etape["plan_b"] = [conn["plans_b"][p]["court"] for p in e["plan_b"]]
        critere = _critere_lie(e.get("liens") or e.get("si") or e.get("si_un_de") or [], a, conn)
        if critere:
            etape["critere"] = critere.texte
        etapes.append(etape)
    demo = a.duree_demo
    return {"defi": a.titre, "robot": a.genre or "à vérifier", "langues": langues,
            "duree_totale_s": sum(e["duree_max_s"] for e in etapes),
            "duree_demonstration_s": int(demo.secondes) if demo else None,
            "plans_b": {k: conn["plans_b"][k]["long"] for k in ("tablette", "main_humaine", "mode_local")},
            "etapes": etapes, "_ids": ids}


# Les plans B que le chef de démonstration (brique 15) sait jouer ; les autres restent écrits pour les humains.
MOYENS_DU_CHEF = ("tablette", "mode_local", "main_humaine")


def scenario_chef(a: Analyse, conn: dict | None = None) -> dict:
    """Le même brouillon, au format de la brique 15 : `python3 lancer.py scenario FICHIER` peut le jouer.

    parole → une étape « dire » (passée à la chaîne : cerveau → gardien → prise) ; confirmation → deux étapes
    (l'ordre, puis « oui ») ; écran et à construire → « attendre_s » avec la consigne pour l'équipe dans « remarque » ;
    la fiche de vérité → une étape « fiche ».
    """
    conn = conn or connaissances()
    brut = {e["id"]: e for e in conn["etapes"]}
    simple = scenario(a, conn)
    langue_chef = simple["langues"][0]
    etapes = []
    for e, ident in zip(simple["etapes"], simple["_ids"]):
        source = brut[ident]
        humains = [conn["plans_b"][p]["court"] for p in source["plan_b"] if p not in MOYENS_DU_CHEF]
        remarque = e["nom"] + (f" — critère : {e['critere']}" if e.get("critere") else "")
        if humains:
            remarque += " — plan B à la main : " + " ; ".join(humains)
        if e["type"] == "parole":
            etape: dict = {"nom": ident, "dire": {"texte": e["dire"], "langue": e["langue"]}}
            if e["attendu"] == "confirmation":
                etape["attendu"] = {"genre": "confirmation", "action": source["attendu_action"]}
            elif e["attendu"] == "action":
                etape["attendu"] = {"action": source["attendu_action"]}
            else:
                etape["attendu"] = e["attendu"]  # question, refus, aide
            etape["duree_max_s"] = e["duree_max_s"]
            etape["plan_b"] = [p for p in source["plan_b"] if p in MOYENS_DU_CHEF] + ["sauter"]
            etape["remarque"] = remarque
            etapes.append(etape)
            if e.get("puis_dire"):
                etapes.append({"nom": f"{ident}_oui", "dire": {"texte": e["puis_dire"], "langue": e["langue"]},
                               "attendu": {"action": source["attendu_action"]}, "duree_max_s": e["duree_max_s"],
                               "plan_b": ["tablette", "main_humaine", "sauter"],
                               "remarque": "la personne confirme : le robot agit seulement maintenant"})
        elif ident == "fiche":
            etapes.append({"nom": ident, "fiche": langue_chef, "remarque": remarque})
        else:
            quoi = "GESTE DE L'ÉQUIPE" if e["type"] == "ecran" else "À CONSTRUIRE (le chef attend seulement)"
            etapes.append({"nom": ident, "attendre_s": e["duree_max_s"],
                           "remarque": f"{quoi} : {e['action']} — {remarque}"})
    sc: dict = {"titre": f"Brouillon du kit — {a.titre or 'défi'}",
                "description": "Fait par le kit du samedi matin (brique 17), hors ligne. À relire et régler en répétition.",
                "robot": faux_robot_du_scenario(a)}
    if simple["duree_demonstration_s"]:
        sc["duree_visee_s"] = simple["duree_demonstration_s"]
    sc |= {"langue": langue_chef, "duree_max_s": 20, "plan_b": ["tablette", "mode_local", "main_humaine", "sauter"],
           "etapes": etapes}
    return sc


def rendre_scenario(a: Analyse) -> str:
    faux = faux_robot_du_scenario(a)
    s = scenario(a)
    entete = (
        "# Brouillon de scénario de démonstration — fait par le kit du samedi matin (brique 17), hors ligne.\n"
        "# Format de la brique 15 (chef de démonstration). Vérifier sans robot :\n"
        "#   python3 -m briques.b15_chef_demo.verifier CE_FICHIER.yaml\n"
        f"# Répéter sur le faux robot :  python3 lancer.py scenario CE_FICHIER.yaml --robot {faux} --repetition\n"
        "# Chaque « dire » passe par cerveau → gardien → prise, comme toute phrase. Rien ne contourne le gardien.\n"
        "# « attendre_s » + « GESTE DE L'ÉQUIPE » : le chef attend pendant que l'équipe fait le geste à l'écran.\n"
        f"# Phrases essayées sur le faux robot « {NOMS_GENRES[faux]} », cerveau à règles : testé sur faux robot seulement.\n"
        f"# Durées : propositions du kit (total {_duree_lisible(s['duree_totale_s'])}), à régler pendant les répétitions.\n"
        "# Plans B, en clair :\n"
        + "".join(f"#   - {t}\n" for t in s["plans_b"].values())
    )
    corps = yaml.safe_dump(scenario_chef(a), allow_unicode=True, sort_keys=False, width=110)
    return sans_fausse_mention(entete + corps)


# ---------------------------------------------------------------- les morceaux du plan
def _cellule(texte: str) -> str:
    return str(texte).replace("|", "/").replace("\n", " ")


def _duree_lisible(secondes: float) -> str:
    m, s = divmod(int(secondes), 60)
    if not m:
        return f"{s} s"
    return f"{m} min {s:02d} s" if s else f"{m} min"


def _section_resume(a: Analyse, etats, conn, liste_chantiers) -> list[str]:
    noms_langues = mots_cles()["noms_des_langues"]
    connues = langues_du_projet()
    out = ["## 1. Résumé du défi", ""]
    if a.langue_du_texte:
        out.append(f"- **Texte écrit en** : {noms_langues.get(a.langue_du_texte, a.langue_du_texte)} (deviné par le kit).")
    if a.genre:
        mots = ", ".join(f"« {m} »" for m in a.genres[a.genre][:3])
        ligne = f"- **Robot** : {NOMS_GENRES.get(a.genre, a.genre)} (mots trouvés : {mots})."
        if a.genre in genres_du_faux_robot():
            ligne += f" S'entraîner sur le faux robot : `python3 lancer.py --robot {a.genre}`."
        else:
            ligne += " Pas de faux robot de ce genre : prendre le plus proche (`--robot humanoide`) et ajouter une carte (brique 2)."
        out.append(ligne)
        autres = [NOMS_GENRES.get(g, g) for g in list(a.genres)[1:]]
        if autres:
            out.append(f"  Aussi cités : {', '.join(autres)}.")
    else:
        out.append("- **Robot** : le texte ne le dit pas → à demander aux organisateurs.")
    out.append("- **Capacités demandées** (la plus importante d'abord ; « prête » = testé sur faux robot) :")
    if not a.capacites:
        out.append("  - aucune repérée : relire le texte à la main.")
    for c in sorted(a.capacites, key=lambda c: -c.priorite):
        info = conn["capacites"][c.cle]
        crit = f", dans {c.dans_criteres} critère(s) du jury" if c.dans_criteres else ""
        mots = ", ".join(c.mots[:4])
        out.append(f"  - **{info['nom']}** — {etat_capacite(c.cle, etats, conn)} (mots : {mots} ; {c.nombre} fois{crit})")
    if a.langues:
        pretes = [noms_langues.get(c, c) for c in a.langues if c in connues]
        manquent = [noms_langues.get(c, c) for c in a.langues if c not in connues]
        ligne = "- **Langues** : " + (", ".join(pretes) + " (prêtes)" if pretes else "")
        if manquent:
            ligne += ("; " if pretes else "") + ", ".join(manquent) + " (manquent)"
        out.append(ligne + ".")
    else:
        out.append("- **Langues** : aucune citée.")
    if a.durees:
        d = "; ".join(f"{x}{' (démonstration)' if x.demonstration else ''}" for x in a.durees[:5])
        out.append(f"- **Durées repérées** : {d}.")
    if a.horaires:
        out.append(f"- **Horaires repérés** : {'; '.join(a.horaires[:4])}.")
    out.append(f"- **Critères du jury** : {len(a.criteres)} repéré(s) → partie 8.")
    out.append(f"- **Règles de sécurité du défi** : {len(a.securite)} repérée(s) → partie 6.")
    if a.lieux_objets:
        lo = ", ".join(f"{i} (« {m[0]} »)" for i, m in a.lieux_objets.items())
        out.append(f"- **Lieux et objets déjà dans le faux monde** : {lo}. Les autres : à ajouter dans `commun/monde.yaml`.")
    else:
        out.append("- **Lieux et objets** : aucun du faux monde ; les écrire dans `commun/monde.yaml` samedi.")
    out += ["", "**Les chantiers du samedi, dans l'ordre :**", ""]
    out += [f"{i}. {c.titre()} — {' ; '.join(c.pourquoi)}" for i, c in enumerate(liste_chantiers, 1)]
    out += ["", "### Questions à poser aux organisateurs", ""]
    out += [f"- [ ] {q}" for q in a.questions]
    return out + [""]


def _section_pretes(a: Analyse, etats, conn) -> list[str]:
    out = ["## 2. Briques prêtes", "",
           "Testées sur faux robot, sur un ordinateur Linux. **Aucune n'a encore été essayée sur un vrai robot, "
           "ni sur les Mac** (NON_TESTE.md).", ""]
    utiles: dict[int, list[str]] = {}
    for c in a.capacites:
        for n in conn["capacites"][c.cle]["briques"]:
            utiles.setdefault(n, []).append(conn["capacites"][c.cle]["nom"])
    for n, b in etats.items():
        if b["etat"] not in ("prete", "socle") or n == 17:
            continue
        out.append(f"### Brique {n} — {b['nom']} · {ETATS[b['etat']]}")
        out.append("- Sait faire : " + " ; ".join(b.get("sait_faire", [])[:4]) + ".")
        if b.get("manque"):
            out.append("- Il manque : " + " ; ".join(b["manque"]) + ".")
        if b.get("limites_connues"):
            out.append("- Attention : " + " ; ".join(b["limites_connues"]) + ".")
        if b.get("commandes"):
            out.append("- Commandes : " + " · ".join(f"`{c}`" for c in b["commandes"]))
        if utiles.get(n):
            out.append("- Utile pour ce défi : " + ", ".join(dict.fromkeys(utiles[n])) + ".")
        out.append("")
    return out


def _section_manque(a: Analyse, etats, conn, liste_chantiers) -> list[str]:
    out = ["## 3. Ce qui manque", "",
           "Par capacité demandée : quelle brique, quelle tâche (prise dans son TACHES.md). "
           "Une tâche = une personne, moins d'une heure, avec son test.", ""]
    b3 = etats[3]
    out += [f"### Toujours : brancher le vrai robot (brique 3, {ETATS.get(b3['etat'], b3['etat'])})",
            "Un **adaptateur** est le petit programme qui traduit les 10 actions de la prise universelle "
            "en ordres pour CE robot. Le modèle et l'assistant existent (`python3 lancer.py brancher`, "
            "BRANCHER_UN_ROBOT.md) ; la liaison de CE robot reste à écrire samedi.", ""]
    out += [f"- [ ] {t}" for t in b3.get("premieres_taches", [])]
    out.append("")
    pretes: list[str] = []
    deja: dict[tuple[int, tuple[str, ...]], str] = {}  # mêmes tâches d'une brique : on ne les répète pas
    for c in sorted(a.capacites, key=lambda c: -c.priorite):
        info = conn["capacites"][c.cle]
        etat = etat_capacite(c.cle, etats, conn)
        if etat == "prête":
            pretes.append(info["nom"])
            continue
        out.append(f"### {info['nom'].capitalize()} — {etat}")
        briques = ", ".join(f"{n} ({ETATS[etats[n]['etat']]})" for n in info["briques"])
        out.append(f"- Briques : {briques}.")
        out.append(f"- Mots du défi : {', '.join(c.mots[:5])}.")
        if c.lignes:
            out.append(f"- Dans le texte : « {c.lignes[0][:160]} »")
        for n in info["briques"]:
            if etats[n]["etat"] == "prete":
                continue
            liste = taches(etats[n], (info.get("taches") or {}).get(n))
            cle = (n, tuple(liste))
            if cle in deja:
                out.append(f"- Brique {n} : mêmes tâches que pour « {deja[cle]} », plus haut.")
                continue
            deja[cle] = info["nom"]
            if etats[n].get("taches"):
                out.append(f"- Brique {n} — tâches ({etats[n]['taches']}) :")
            else:
                out.append(f"- Brique {n} — premières tâches (dossier à créer) :")
            out += [f"  - [ ] {t}" for t in liste] or ["  - [ ] Écrire les premières tâches."]
        out.append("")
    manquantes = langues_manquantes(a)
    if manquantes:
        noms = ", ".join(mots_cles()["noms_des_langues"].get(c, c) for c in manquantes)
        out += [f"### Langues à ajouter : {noms}", "- Brique 4 — tâches (briques/b04_oreilles_voix/TACHES.md) :"]
        out += [f"  - [ ] {t}" for t in taches(etats[4], ["commun/langues.yaml", "Une voix", "12 phrases", "oui_non"])]
        out.append("")
    if a.genre and a.genre not in genres_du_faux_robot():
        out += [f"### Faux robot « {NOMS_GENRES.get(a.genre, a.genre)} »",
                "- Brique 2 — tâches (briques/b02_faux_robot/TACHES.md) :"]
        out += [f"  - [ ] {t}" for t in taches(etats[2], [a.genre])]
        out.append("")
    orphelins = [c for c in a.criteres if not c.capacites and not any(
        trouver(normaliser(c.texte), t["mots"]) for t in conn["themes_jury"].values())]
    if orphelins:
        out += ["### Critères du jury sans brique (à discuter en équipe)"]
        out += [f"- « {c.texte} »" for c in orphelins]
        out.append("")
    if pretes:
        out += [f"**Déjà prêt pour ce défi** (testé sur faux robot) : {', '.join(pretes)}.", ""]
    return out


def _section_horaire(a: Analyse, liste_chantiers) -> list[str]:
    prog = programme()
    titres = [c.titre()[:1].lower() + c.titre()[1:] for c in liste_chantiers] + ["les tâches des TACHES.md"] * 3

    class _Defaut(dict):
        def __missing__(self, cle):
            return "—"

    valeurs = _Defaut(chantier_1=titres[0], chantier_2=titres[1], chantier_3=titres[2],
                      robot=NOMS_GENRES.get(a.genre, "genre à vérifier") if a.genre else "genre à vérifier")
    out = ["## 4. Plan heure par heure (samedi 9 h → lundi 9 h)", "",
           "Heures officielles du Carnival (repas, passage devant le jury) : **à vérifier**. Si la démonstration est "
           "plus tôt, avancer d'autant les gels et les répétitions.",
           "Un **gel du code** est un moment après lequel on n'ajoute plus rien : on corrige seulement. "
           "**Feu orange** = tout ce qui touche le vrai robot attend le « oui » de Hiba.",
           "Sommeil par rotation, nuit 1 : " + " ; ".join(f"{r} {t}" for r, t in prog["rotations"].items())
           + ". Nuit 2 : tout le monde dort 23 h – 5 h.", ""]
    for jour in prog["jours"]:
        out += [f"### {jour['jour']}", "", "| Heure | Ce qu'on fait | Qui |", "|---|---|---|"]
        for b in jour["blocs"]:
            d = b.get("duree", 1)
            heure = f"{b['h']:02d} h" if d == 1 else f"{b['h']:02d} h – {(b['h'] + d) % 24:02d} h"
            quoi = b["quoi"].format_map(valeurs)
            if b.get("type") in ("gel", "demonstration"):
                quoi = f"**{quoi}**"
            out.append(f"| {heure} | {_cellule(quoi)} | {_cellule(b['qui'])} |")
        out.append("")
    return out


def _section_equipes(equipes: list[Equipe]) -> list[str]:
    total = sum(len(e.personnes) for e in equipes)
    out = ["## 5. Répartition des 35 personnes", "",
           f"{total} personnes, chacune dans **une seule** équipe. La première personne de la liste est le chef. "
           "« Vérifié par » : celui qui écrit n'est pas celui qui vérifie. Les prénoms : annexe A.",
           "Le **responsable sécurité** (équipe Sécurité) peut tout arrêter, à tout moment, sans discussion.", "",
           "| Équipe | Personnes | Mission | Briques | Vérifié par |", "|---|---|---|---|---|"]
    for e in equipes:
        membres = [f"{p} ({e.prenoms[i]})" if i < len(e.prenoms) else p for i, p in enumerate(e.membres)]
        texte = ", ".join(membres)
        if e.renforts:
            texte += (" + renforts " if e.membres else "") + ", ".join(e.renforts)
        briques = ", ".join(str(n) for n in e.briques) or "—"
        out.append(f"| {_cellule(e.nom)} | {texte} | {_cellule(e.mission)} | {briques} | {_cellule(e.verifie)} |")
    return out + [""]


def _non_teste(a: Analyse, conn: dict) -> list[tuple[str, list[str]]]:
    sections: list[tuple[str, list[str]]] = []
    for ligne in NON_TESTE.read_text(encoding="utf-8").splitlines():
        if ligne.startswith("## "):
            sections.append((ligne[3:].strip(), []))
        elif sections and ligne.strip():
            if re.match(r"^\s*-\s+", ligne) or not sections[-1][1]:
                sections[-1][1].append(re.sub(r"^\s*-\s+", "", ligne.strip()))
            else:
                sections[-1][1][-1] += " " + ligne.strip()
    gardees = []
    for titre, points in sections:
        regle = next((r for r in conn["non_teste"] if normaliser(r["titre"]) in normaliser(titre)), None)
        if regle is None or regle["montrer"] == "toujours" or set(regle["montrer"]) & set(a.cles):
            gardees.append((titre, points))
    return gardees


def _section_risques(a: Analyse, conn: dict) -> list[str]:
    out = ["## 6. Risques", "", "### Les risques de ce défi", ""]
    for c in sorted(a.capacites, key=lambda c: -c.priorite):
        info = conn["capacites"][c.cle]
        out.append(f"- **{info['nom'].capitalize()}** : {info['risque']} → {info['parade']}")
    if not a.capacites:
        out.append("- Aucune capacité repérée : relire le défi à la main.")
    out += ["", "### Les règles de sécurité du défi (à respecter, à mettre dans le gardien)", ""]
    out += [f"- {s}" for s in a.securite] or ["- Aucune trouvée dans le texte → demander aux organisateurs."]
    out += ["", "### Nos règles, toujours", "",
            "- L'arrêt d'urgence passe avant tout. Le bouton d'arrêt **physique** du robot reste à portée de main.",
            "- Vitesse 0,3 m/s et force 15 N par défaut (`reglages.yaml` → `securite`), même si le robot peut plus.",
            "- Tout ordre au robot passe par le cerveau, le **gardien** (qui vérifie et délivre un ticket), "
            "la prise, puis l'adaptateur. Rien d'autre.",
            "- Démonstration de soin : sur un mannequin seulement, jamais de diagnostic.",
            "", "### Les risques de tout défi", ""]
    out += [f"- **{r['risque']}** → {r['parade']}" for r in conn["risques_generaux"]]
    out += ["", "### Jamais essayé (extrait de NON_TESTE.md)", "",
            "Ne jamais promettre au jury ce qui suit : ce n'est pas encore essayé.", ""]
    for titre, points in _non_teste(a, conn):
        out.append(f"**{titre}**")
        out += [f"- {p}" for p in points]
        out.append("")
    return out


def _section_scenario(a: Analyse, nom_fichier: str | None) -> list[str]:
    s = scenario(a)
    faux = NOMS_GENRES[faux_robot_du_scenario(a)]
    out = ["## 7. Brouillon de scénario de démonstration", "",
           "À répéter, chronométrer et couper. Chaque phrase passe par le cerveau, le gardien puis la prise : "
           f"rien ne contourne le gardien. Phrases essayées sur le faux robot « {faux} » : testé sur faux robot "
           "seulement. Lieux et objets : la table, la bouteille, l'entrée et la cuisine du faux monde "
           "(`commun/monde.yaml`), à remplacer par ceux du défi."]
    autres = {i: m for i, m in a.lieux_objets.items() if i not in ("table", "bouteille", "entree", "cuisine")}
    if autres:
        out[-1] += " Le défi parle aussi de : " + ", ".join(f"{i} (« {m[0]} »)" for i, m in autres.items()) + "."
    out.append("")
    noms_langues = mots_cles()["noms_des_langues"]
    for i, e in enumerate(s["etapes"], 1):
        out.append(f"{i}. **{e['nom']}** — {e['duree_max_s']} s au plus")
        if e["type"] == "parole":
            ligne = f"   - Dire ({noms_langues.get(e['langue'], e['langue'])}) : « {e['dire']} »"
            if e.get("puis_dire"):
                ligne += f", puis « {e['puis_dire']} »"
            out.append(ligne + f" → {ATTENDUS[e['attendu']]}.")
        else:
            prefixe = "À construire" if e["type"] == "a_construire" else "À l'écran"
            out.append(f"   - {prefixe} : {e['action']}")
        out.append("   - Plan B : " + " ; ".join(e["plan_b"]) + ".")
        if e.get("critere"):
            out.append(f"   - Montre au jury : « {e['critere']} »")
    out += ["", f"**Durée totale proposée : {_duree_lisible(s['duree_totale_s'])}.**"]
    if s["duree_demonstration_s"]:
        out[-1] += f" Le défi donne {_duree_lisible(s['duree_demonstration_s'])} pour la démonstration."
        if s["duree_totale_s"] > 0.8 * s["duree_demonstration_s"]:
            out.append("Trop long : garder 20 % de marge pour les imprévus. Raccourcir d'abord les étapes "
                       "« à construire », puis celles qui ne montrent aucun critère du jury.")
            sans = [str(i) for i, e in enumerate(s["etapes"], 1) if not e.get("critere")]
            if sans:
                out.append(f"Étapes sans critère du jury : {', '.join(sans)} (à raccourcir ou à regrouper).")
    out += ["", "### Les plans B de toute la démonstration", ""]
    out += [f"- {t}" for t in s["plans_b"].values()]
    out.append("")
    if nom_fichier:
        out.append(f"Le même brouillon en YAML : `{nom_fichier}`, au format du chef de démonstration (brique 15) : "
                   f"`python3 lancer.py scenario {nom_fichier} --repetition`.")
    else:
        out.append("Le même brouillon en YAML : relancer avec `--sortie` ou `--scenario` pour l'écrire.")
    return out + [""]


def _section_jury(a: Analyse, conn: dict) -> list[str]:
    out = ["## 8. Critères du jury → ce que l'on montre → preuve", "",
           "La **fiche de vérité** compte tout depuis la boîte noire (réussites, refus, part de l'humain, temps) et "
           "dit d'elle-même « faux robot » ou « vrai robot ». La **boîte noire** garde chaque événement "
           "(`journal/`) et se rejoue : `python3 lancer.py rejouer`.", "",
           "| Critère du jury | Ce que l'on montre | Preuve |", "|---|---|---|"]
    lignes = a.criteres
    if not lignes:
        out.append("| Aucun critère trouvé dans le texte → demander la grille | — | — |")
        defauts = ["securite", "fiabilite", "interaction"]
        for t in defauts:
            th = conn["themes_jury"][t]
            out.append(f"| (proposition) {t} | {_cellule(th['montrer'])} | {_cellule(th['preuve'])} |")
        return out + [""]
    for c in lignes:
        montres, preuves = [], []
        for cle in c.capacites[:2]:
            montres.append(conn["capacites"][cle]["montrer"])
            preuves.append(conn["capacites"][cle]["preuve"])
        n = normaliser(c.texte)
        for theme in conn["themes_jury"].values():
            if len(montres) >= 2:
                break
            if trouver(n, theme["mots"]):
                montres.append(theme["montrer"])
                preuves.append(theme["preuve"])
        if not montres:
            montres, preuves = ["À décider en équipe (le kit n'a pas trouvé de lien)."], ["À choisir."]
        texte = c.texte + (f" ({c.points} points)" if c.points is not None and str(c.points) not in c.texte else "")
        out.append(f"| {_cellule(texte)} | {_cellule(' '.join(dict.fromkeys(montres)))} | "
                   f"{_cellule(' '.join(dict.fromkeys(preuves)))} |")
    total = sum(c.points for c in lignes if c.points is not None)
    if total:
        out += ["", f"Total des points repérés : {total}."]
    return out + [""]


def _annexe_personnes(equipes: list[Equipe]) -> list[str]:
    out = ["## Annexe A — La liste des 35 personnes (à remplir samedi)", "",
           "| Personne | Prénom | Équipe | Sommeil, nuit 1 |", "|---|---|---|---|"]
    lignes = []
    for t, e in enumerate(equipes):
        for i, p in enumerate(e.personnes):
            prenom = e.prenoms[i] if i < len(e.prenoms) else ""
            lignes.append((p, prenom, e.nom, rotation(t, i)))
    for p, prenom, nom, r in sorted(lignes):
        out.append(f"| {p} | {prenom} | {_cellule(nom)} | {r} |")
    return out + [""]


GLOSSAIRE = [
    ("Adaptateur", "le petit programme qui traduit nos 10 actions en ordres pour un robot précis."),
    ("Prise universelle", "la courte liste de 10 actions, dite pareil pour tous les robots (briques/b01_prise/PRISE.md)."),
    ("Carte d'identité", "le fichier qui dit ce qu'un robot sait faire et ses limites (vitesse, force, portée)."),
    ("Gardien", "le programme qui vérifie chaque action avant qu'elle parte ; seul lui délivre le ticket."),
    ("Ticket", "l'autorisation signée du gardien, pour une seule action, valable 5 secondes."),
    ("Test de conformité", "l'essai qu'un adaptateur doit réussir avant de servir (briques/b01_prise/conformite.py)."),
    ("Faux robot", "le robot imaginaire de l'ordinateur, pour s'entraîner sans matériel."),
    ("Boîte noire", "le journal où chaque événement est écrit, avec l'heure (dossier journal/)."),
    ("Fiche de vérité", "les chiffres calculés depuis la boîte noire : réussites, refus, temps, part de l'humain."),
    ("Gel du code", "le moment après lequel on n'ajoute plus rien : on corrige seulement."),
    ("Rotation", "un groupe qui dort pendant que les autres travaillent (R1, R2, R3)."),
    ("Feu orange", "une action qui attend le « oui » de Hiba (vrai robot, installation, gros téléchargement)."),
    ("Plan B", "ce qu'on fait si une partie tombe en panne pendant la démonstration."),
    ("Mode local", "tout tourne sur un seul Mac, sans Internet."),
    ("Tablette", "le champ texte de l'écran : on tape la phrase au lieu de la dire."),
]


def rendre_plan(a: Analyse, nom_fichier_scenario: str | None = None) -> str:
    etats = etat_des_briques()
    conn = connaissances()
    liste = chantiers(a, etats, conn)
    equipes = repartir(liste, etats)
    lignes = [f"# Plan du défi — {a.titre}", "",
              "> Fait par le kit du samedi matin (brique 17), hors ligne, en cherchant des mots-clés. "
              "**À relire et ajuster par un humain** : le kit repère, il ne comprend pas.",
              "> Tout le projet est testé sur faux robot seulement : rien n'a encore été essayé sur un vrai robot "
              "(NON_TESTE.md). Les chiffres sans source sont **à vérifier**.", "",
              "Sommaire : 1. Résumé · 2. Briques prêtes · 3. Ce qui manque · 4. Plan heure par heure · "
              "5. Équipes · 6. Risques · 7. Scénario · 8. Jury · Annexes", ""]
    lignes += _section_resume(a, etats, conn, liste)
    lignes += _section_pretes(a, etats, conn)
    lignes += _section_manque(a, etats, conn, liste)
    lignes += _section_horaire(a, liste)
    lignes += _section_equipes(equipes)
    lignes += _section_risques(a, conn)
    lignes += _section_scenario(a, nom_fichier_scenario)
    lignes += _section_jury(a, conn)
    lignes += _annexe_personnes(equipes)
    lignes += ["## Annexe B — Les mots du plan", ""] + [f"- **{m}** : {d}" for m, d in GLOSSAIRE] + [""]
    return sans_fausse_mention("\n".join(lignes))
