"""H10a — Le mode interprète, le cœur et la mesure (message de Hiba, 12.11.2026).

    python3 lancer.py interprete-mesure        dix phrases françaises → l'anglais à l'écran et à la voix, sur deux chemins

« La personne qui présente répondra au jury en français. La boîte redira chaque phrase en anglais, à voix haute. »
    un son en français → l'écoute → la traduction en anglais → les contrôles → la voix du Mac dit l'anglais
Deux chemins possibles, tous deux sur cet ordinateur, sans Internet, sans rien télécharger :
- « direct » : l'outil d'écoute (whisper.cpp, modèle « small » par défaut ; « medium » avec --modele medium, H20) traduit
  lui-même vers l'anglais. Un seul pas, rapide.
  Il ne connaît pas nos mots fixés : on peut seulement compter quand il ne les respecte pas.
- « deux temps » : l'écoute écrit le français, puis le vrai Apertus 8B le traduit, avec la liste des mots fixés.
Les contrôles, les mêmes pour les deux chemins :
- LES MOTS FIXÉS (`interprete_mots.yaml`, que Hiba peut lire et changer) : si la phrase française contient un de ces
  mots, l'anglais doit contenir sa traduction fixée. Et l'inverse : la traduction fixée ne doit pas apparaître si la
  phrase ne dit pas ce mot. Sinon : une erreur comptée. La phrase n'est pas maquillée.
- LES CHIFFRES EN CHIFFRES : un nombre de la phrase française s'affiche en chiffres en anglais (« twenty » → « 20 »).
  Un nombre perdu ou changé : une erreur comptée.
- Une sortie vide, ou restée en français : « pas de traduction », et la voix ne dit rien.
Les réponses préparées (`interprete_reponses.yaml`) portent l'étiquette « TRADUCTION PRÉPARÉE ».

DIRE VRAI : les erreurs comptées sont celles que le programme sait voir (mots fixés, chiffres, pas de traduction).
Il ne juge pas le sens : chaque phrase anglaise est écrite telle quelle dans le compte rendu, pour qu'une personne la lise.
Les deux boutons de l'écran de régie (tenir pour écouter ; afficher une réponse préparée) : seconde moitié, H10b.
"""
from __future__ import annotations

import argparse
import re
import statistics
import subprocess
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import yaml

ICI = Path(__file__).resolve().parent
RACINE = ICI.parents[1]
FICHIER_MOTS = ICI / "interprete_mots.yaml"
FICHIER_REPONSES = ICI / "interprete_reponses.yaml"
FICHIER_MESURE = RACINE / "docs/projet/MESURE_INTERPRETE.md"
# H20 (Q27 : B ; Q30 : « medium complet ») : le modèle d'écoute se choisit par son nom ; « small » reste le choix par défaut.
MODELES = {"small": RACINE / "modeles" / "ggml-small.bin", "medium": RACINE / "modeles" / "ggml-medium.bin"}
SERVEUR_LOCAL = "127.0.0.1:8089"  # le serveur d'Apertus des réglages, sur cet ordinateur : rien ne sort
DIRECT, PREPAREE = "TRADUCTION AUTOMATIQUE EN DIRECT", "TRADUCTION PRÉPARÉE"
LIMITE_LENTE_MS = 5000

# Dix phrases de présentation, écrites par l'agent : elles servent les cinq mots fixés et des chiffres.
PHRASES = [
    "Le soignant demande une course au robot.",
    "La boîte marche sans Internet.",
    "Le robot a fait 20 courses pendant la répétition.",
    "Au premier palier, le robot roule lentement.",
    "Le seuil d'arrêt est réglé par l'équipe.",
    "Quatre robots sont à l'écran, dont 3 simulés.",
    "Le soignant garde toujours la main sur l'arrêt.",
    "Chaque course passe par le gardien.",
    "La boîte ne répond à aucune question de santé.",
    "Nous avons mesuré 112 bonnes réponses sur 120.",
]
NOMBRES_FR = {"deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10, "onze": 11,
              "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15, "seize": 16, "vingt": 20, "trente": 30, "quarante": 40,
              "cinquante": 50, "soixante": 60}
NOMBRES_EN = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven",
              12: "twelve", 13: "thirteen", 14: "fourteen", 15: "fifteen", 16: "sixteen", 20: "twenty", 30: "thirty", 40: "forty",
              50: "fifty", 60: "sixty"}
PETITS_MOTS_FRANCAIS = {"le", "la", "les", "une", "des", "est", "et", "du", "au", "nous", "sans", "par"}


def charger_les_mots(fichier: Path = FICHIER_MOTS) -> list[dict[str, Any]]:
    return list(yaml.safe_load(Path(fichier).read_text(encoding="utf-8"))["mots"])


def reponses_preparees(fichier: Path = FICHIER_REPONSES) -> list[dict[str, Any]]:
    """Les réponses dont l'anglais est écrit d'avance. Chacune porte l'étiquette « TRADUCTION PRÉPARÉE »."""
    return [{**r, "etiquette": PREPAREE} for r in yaml.safe_load(Path(fichier).read_text(encoding="utf-8"))["reponses"]]


def _simple(texte: str) -> str:
    sans = unicodedata.normalize("NFD", str(texte).lower().replace("’", "'"))
    return "".join(c for c in sans if unicodedata.category(c) != "Mn")


def _nombres_dits(francais: str) -> list[str]:
    """Les nombres de la phrase française, en chiffres : ceux écrits en chiffres, et « deux » à « soixante » en lettres."""
    trouves = re.findall(r"\d+", francais)
    trouves += [str(NOMBRES_FR[m]) for m in re.findall(r"[a-z]+", _simple(francais)) if m in NOMBRES_FR]
    return list(dict.fromkeys(trouves))


def chiffres_en_chiffres(anglais: str, nombres: list[str]) -> str:
    """Un nombre de la phrase française écrit en lettres en anglais devient des chiffres (« twenty » → « 20 »).
    Seulement pour les nombres de la phrase : « no one » n'est pas touché."""
    for nombre in nombres:
        mot = NOMBRES_EN.get(int(nombre))
        if mot and not re.search(rf"(?<!\d){nombre}(?!\d)", anglais):
            anglais = re.sub(rf"\b{mot}\b", nombre, anglais, flags=re.IGNORECASE)
    return anglais


def controler(francais: str, anglais: str, mots: list[dict[str, Any]]) -> list[str]:
    """Les erreurs que le programme sait voir. Il ne juge pas le sens."""
    if not anglais.strip():
        return ["pas de traduction"]
    erreurs = []
    fr, en = _simple(francais), _simple(anglais)
    jetons = re.findall(r"[a-z']+", en)
    if en.strip(" .!?") == fr.strip(" .!?") or sum(j in PETITS_MOTS_FRANCAIS for j in jetons) >= 2:
        erreurs.append("la sortie est restée en français")
    for mot in mots:
        formes = [_simple(f) for f in (mot["fr"], *mot.get("aussi", ()))]
        present = any(re.search(rf"(?<![a-z]){re.escape(f)}(?![a-z])", fr) for f in formes)
        if present and _simple(mot["en"]) not in en:
            erreurs.append(f"mot fixé non respecté : « {mot['fr']} » doit donner « {mot['en']} »")
        elif not present and re.search(rf"(?<![a-z]){re.escape(_simple(mot['en']))}", en):
            # mesuré le 12.11 : « gardien » rendu par « caregiver », « l'arrêt » par « stop threshold » — le mot fixé d'un AUTRE mot
            erreurs.append(f"mot fixé employé à tort : « {mot['en']} » alors que la phrase ne dit pas « {mot['fr']} »")
    manquants = [n for n in _nombres_dits(francais) if not re.search(rf"(?<!\d){n}(?!\d)", anglais)]
    if manquants:
        erreurs.append("chiffre perdu ou changé : " + ", ".join(manquants))
    return erreurs


def interpreter(son: Any, dossier: str | Path, ecouter: Callable[[Any, str], dict[str, Any]],
                traduire: Callable[[str, list[dict[str, Any]]], str], dire: Callable[[str, str, Any], Any],
                montre: Callable[[], float] = time.perf_counter, mots: list[dict[str, Any]] | None = None,
                dit: str | None = None, nom: str = "reponse") -> dict[str, Any]:
    """Un son en français → l'anglais affiché et dit. `dit` : la phrase vraiment dite, si on la connaît (la mesure) ;
    les contrôles se font alors contre elle, pas contre ce que l'écoute a cru entendre."""
    mots = charger_les_mots() if mots is None else mots
    r: dict[str, Any] = {"etiquette": DIRECT, "dit": dit, "fr": None, "en": None, "erreurs": [], "panne": None,
                         "ecoute_ms": None, "traduction_ms": None, "voix_ms": None, "total_ms": None}
    t0 = montre()
    try:
        etape = "écoute"
        entendu = ecouter(son, "fr")
        r["fr"] = entendu.get("texte")
        t1 = montre()
        etape = "traduction"
        brut = entendu["anglais"] if "anglais" in entendu else traduire(r["fr"], mots)  # chemin direct : l'écoute a déjà traduit
        t2 = montre()
        source = dit or r["fr"] or ""
        anglais = chiffres_en_chiffres(" ".join(str(brut or "").split()), _nombres_dits(source))
        r["erreurs"] = controler(source, anglais, mots)
        r.update(ecoute_ms=round((t1 - t0) * 1000), traduction_ms=round((t2 - t1) * 1000))
        if "pas de traduction" in r["erreurs"]:
            r["erreurs"], r["total_ms"] = ["pas de traduction"], None
            return r
        r["en"] = anglais
        if "la sortie est restée en français" in r["erreurs"]:
            return r  # affichée telle quelle, avec l'erreur ; la voix ne dit pas du français comme de l'anglais
        etape = "voix"
        dire(anglais, "en", Path(dossier) / f"{nom}.wav")
        t3 = montre()
        r.update(voix_ms=round((t3 - t2) * 1000), total_ms=round((t3 - t0) * 1000))
    except Exception as erreur:  # une pièce en panne : pas de traduction, et c'est dit
        r.update(en=None, total_ms=None, erreurs=["pas de traduction"], panne=f"{etape} : {type(erreur).__name__}: {erreur}"[:160])
    return r


def mesurer(phrases: list[str], dossier: str | Path, ecouter, traduire, dire, montre: Callable[[], float] = time.perf_counter,
            sons: dict[str, Any] | None = None, chemin: str = "", origine: str = "", mots: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    detail = [interpreter((sons or {}).get(p, p), dossier, ecouter, traduire, dire, montre, mots, dit=p, nom=f"reponse_{i:02d}")
              for i, p in enumerate(phrases, 1)]
    faites = [l for l in detail if l["total_ms"] is not None]
    totaux = [l["total_ms"] for l in faites]
    return {"possible": True, "quand": datetime.now().astimezone().isoformat(timespec="seconds"), "chemin": chemin, "origine": origine,
            "phrases": len(detail), "sorties_en_anglais": sum(1 for l in detail if l["en"] and "la sortie est restée en français" not in l["erreurs"]),
            "sans_erreur": sum(1 for l in detail if not l["erreurs"]), "erreurs": sum(len(l["erreurs"]) for l in detail),
            "total_median_ms": round(statistics.median(totaux)) if totaux else None, "total_max_ms": max(totaux, default=None),
            "plus_de_5_s": [l for l in faites if l["total_ms"] > LIMITE_LENTE_MS], "detail": detail}


def rapport(bilans: list[dict[str, Any]]) -> list[str]:
    L = []
    for b in bilans:
        jour = datetime.fromisoformat(b["quand"]).strftime("%d.%m.%Y, %H h %M")
        if not b.get("possible", True):
            L += [f"LE MODE INTERPRÈTE — chemin « {b['chemin']} » : PAS POSSIBLE — {jour}", f"Raison : {b['raison']}.",
                  "Aucun chiffre : rien n'a été mesuré."]
            continue
        n = b["phrases"]
        L += [f"LE MODE INTERPRÈTE — chemin « {b['chemin']} » — {DIRECT} — aucun robot — {jour}",
              f"Les phrases : {b['origine']}. Sur cet ordinateur, sans Internet.",
              f"RÉSULTAT : {b['sorties_en_anglais']} phrases sur {n} sorties en anglais, à l'écran et à la voix ; "
              f"{b['sans_erreur']} phrase{'s' if b['sans_erreur'] > 1 else ''} sans erreur comptée sur {n} ; "
              f"{b['erreurs']} erreur{'s' if b['erreurs'] > 1 else ''} comptée{'s' if b['erreurs'] > 1 else ''} "
              f"(mots fixés, chiffres, pas de traduction : le sens n'est pas jugé)."]
        if b["total_median_ms"] is not None:
            lentes = b["plus_de_5_s"]
            L.append(f"Délai, de la fin de la phrase à l'anglais prêt à être dit : médian {b['total_median_ms']} ms ; le plus long "
                     f"{b['total_max_ms']} ms ; " + (f"{len(lentes)} de plus de 5 secondes." if lentes else "aucun de plus de 5 secondes."))
        L.append("Phrase par phrase, tel quel :")
        for i, l in enumerate(b["detail"], 1):
            delai = (f"écoute {l['ecoute_ms']} ms, traduction {l['traduction_ms']} ms, voix {l['voix_ms']} ms, total {l['total_ms']} ms"
                     if l["total_ms"] is not None else "pas de délai : rien n'a été dit")
            entendu = f" (entendu : « {l['fr']} »)" if l["fr"] and l["fr"] != l["dit"] else ""
            L.append(f"- {i}. dit « {l['dit']} »{entendu} → « {l['en'] or '—'} » — {delai} — "
                     + ("erreurs : " + " ; ".join(l["erreurs"]) if l["erreurs"] else "aucune erreur comptée")
                     + (f" — panne : {l['panne']}" if l["panne"] else ""))
    return L


# ---------------------------------------------------------------------- le modèle d'écoute et la mémoire (H20)
def fichier_de_mesure(nom: str) -> Path:
    return FICHIER_MESURE if nom == "small" else FICHIER_MESURE.with_name(f"MESURE_INTERPRETE_{nom.upper()}.md")


def choisir_modele(nom: str) -> Path:
    from . import ecoute

    if nom not in MODELES:
        raise ValueError(f"modèle d'écoute inconnu « {nom} » : {', '.join(MODELES)}")
    if not MODELES[nom].exists():
        raise ecoute.EcouteImpossible(f"modèle d'écoute « {nom} » absent de cet ordinateur : {MODELES[nom].name}")
    return MODELES[nom]


class avec_le_modele:
    """Le temps d'une mesure, l'écoute utilise ce modèle ; ensuite, on remet celui d'avant."""

    def __init__(self, nom: str) -> None:
        self.nom, self.chemin = nom, choisir_modele(nom)

    def __enter__(self):
        from . import ecoute

        self.avant = (ecoute.MODELE, ecoute.OUTIL)
        ecoute.MODELE, ecoute.OUTIL = self.chemin, f"whisper.cpp (whisper-cli), modèle « {self.nom} »"
        return self

    def __exit__(self, *_):
        from . import ecoute

        ecoute.MODELE, ecoute.OUTIL = self.avant


class SuiviMemoire:
    """La mémoire libre de l'ordinateur au plus bas pendant une mesure (Q22), lue toutes les `pas_s` secondes."""

    def __init__(self, pas_s: float = 0.25) -> None:
        self.pas_s, self.plus_bas_go = pas_s, None

    def _lire(self) -> None:
        import psutil

        libre = psutil.virtual_memory().available / 1e9
        self.plus_bas_go = libre if self.plus_bas_go is None else min(self.plus_bas_go, libre)

    def __enter__(self):
        import threading

        self._fin = threading.Event()
        self._lire()

        def tourner():
            while not self._fin.wait(self.pas_s):
                self._lire()

        self._fil = threading.Thread(target=tourner, daemon=True)
        self._fil.start()
        return self

    def __exit__(self, *_):
        self._fin.set()
        self._fil.join(timeout=2)
        self._lire()


# ---------------------------------------------------------------------- les vraies pièces (cet ordinateur seulement)
def ecouter_et_traduire_directement(son: Any, langue: str) -> dict[str, Any]:
    """Le chemin direct : whisper.cpp écoute le français et écrit l'anglais lui-même. Il ne rend pas le français."""
    from . import ecoute

    oui, raison = ecoute.disponible()
    if not oui:
        raise ecoute.EcouteImpossible(raison)
    fait = subprocess.run(["whisper-cli", "-m", str(ecoute.MODELE), "-f", str(son), "-l", langue, "-tr", "-nt", "-np"],
                          capture_output=True, text=True, timeout=120)
    if fait.returncode != 0:
        raise ecoute.EcouteImpossible(fait.stderr.strip()[-200:] or f"whisper-cli a rendu le code {fait.returncode}")
    return {"texte": None, "anglais": " ".join(fait.stdout.split())}


def traduire_avec_apertus(adresse: str, delai_s: float = 15.0) -> Callable[[str, list[dict[str, Any]]], str]:
    """Le chemin en deux temps : le vrai Apertus, sur cet ordinateur, traduit le français écrit par l'écoute."""
    def traduire(francais: str, mots: list[dict[str, Any]]) -> str:
        import httpx

        fixes = "; ".join(f"« {m['fr']} » = \"{m['en']}\"" for m in mots)
        consigne = ("You are an interpreter. Translate the French sentence into English. Output only the English translation, "
                    "one sentence, nothing else. Write every number with digits. Always use these fixed translations: " + fixes + ".")
        reponse = httpx.post(adresse.rstrip("/") + "/v1/chat/completions", timeout=delai_s, json={
            "messages": [{"role": "system", "content": consigne}, {"role": "user", "content": francais}],
            "temperature": 0, "max_tokens": 120, "stream": False})
        reponse.raise_for_status()
        return reponse.json()["choices"][0]["message"]["content"].strip().strip('"')

    return traduire


def main(argv: list[str] | None = None) -> int:
    import tempfile

    from commun.systeme import charger_reglages, creer_serveurs

    from . import accueil_voix, ecoute

    lecteur = argparse.ArgumentParser(prog="lancer.py interprete-mesure")
    lecteur.add_argument("--modele", default="small", choices=list(MODELES), help="le modèle d'écoute (H20) ; small par défaut")
    nom = lecteur.parse_args(argv).modele
    try:
        with avec_le_modele(nom), SuiviMemoire() as memoire:
            code, lignes = _mesurer_tout(nom, accueil_voix, ecoute, creer_serveurs, charger_reglages, tempfile)
    except ecoute.EcouteImpossible as erreur:
        print(f"INTERPRÈTE : pas de mesure — {erreur}")
        return 2
    lignes.append(f"Mémoire libre de tout l'ordinateur au plus bas pendant la mesure : {memoire.plus_bas_go:.2f} Go".replace(".", ",")
                  + " (lue toutes les 0,25 s ; Apertus, la voix et les autres programmes ouverts compris : ce n'est pas la mémoire "
                    "du modèle d'écoute seul ; une seule mesure).")
    for ligne in lignes:
        print(ligne)
    fichier = fichier_de_mesure(nom)
    fichier.write_text(f"# Le mode interprète (dernière mesure, modèle d'écoute « {nom} »)\n\n" + "\n\n".join(lignes) + "\n\n"
                       "Limites : voix de synthèse, pas une personne ; pas de micro, pas de bruit de salle ; phrases écrites par un "
                       "agent ; les mots fixés anglais sont proposés par un agent, à confirmer par Hiba ; le sens des phrases "
                       "anglaises n'est jugé par personne : à relire.\n", encoding="utf-8")
    print(f"Écrit dans {fichier.name}")
    return code


def _mesurer_tout(nom: str, accueil_voix, ecoute, creer_serveurs, charger_reglages, tempfile) -> tuple[int, list[str]]:
    quand = datetime.now().astimezone().isoformat(timespec="seconds")
    origine = "dix phrases écrites par un agent, dites par la VOIX DE SYNTHÈSE française du Mac, sans bruit, lues dans des fichiers"
    bilans: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as provisoire:
        dossier = Path(provisoire)
        sons = {p: accueil_voix.dire(p, "fr", dossier / f"phrase_{i:02d}.wav") for i, p in enumerate(PHRASES, 1)}
        bilans.append(mesurer(PHRASES, dossier, ecouter_et_traduire_directement, lambda fr, mots: "", accueil_voix.dire, sons=sons,
                              chemin=f"direct : l'écoute (whisper.cpp « {nom} ») traduit elle-même", origine=origine))
        serveur = creer_serveurs(charger_reglages()).get("apertus_8b")
        chemin = f"deux temps : l'écoute (« {nom} ») écrit le français, le vrai Apertus 8B traduit avec les mots fixés"
        if serveur is None or not Path(serveur.modele).exists():
            bilans.append({"possible": False, "raison": "le modèle Apertus 8B n'est pas sur cet ordinateur", "chemin": chemin, "quand": quand})
        else:
            deja = serveur.en_marche()
            if not deja:
                serveur.lancer()
            try:
                if deja or serveur.attendre(180):
                    traduire = traduire_avec_apertus(serveur.url)
                    try:  # une première demande met le modèle en route : elle n'est pas comptée
                        traduire("Bonjour.", [])
                    except Exception:
                        pass
                    bilans.append(mesurer(PHRASES, dossier, ecoute.ecouter, traduire, accueil_voix.dire, sons=sons, chemin=chemin, origine=origine))
                else:
                    bilans.append({"possible": False, "raison": "le serveur du modèle n'a pas démarré", "chemin": chemin, "quand": quand})
            finally:
                if not deja:
                    serveur.eteindre()
    return (0 if all(b.get("possible", True) for b in bilans) else 2), rapport(bilans)
