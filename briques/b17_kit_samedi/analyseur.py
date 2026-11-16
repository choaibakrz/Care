"""Brique 17 — Lire le texte du défi, hors ligne, par mots-clés (français, allemand, anglais).

Aucun modèle de langue, aucun Internet : le même texte donne toujours la même analyse.
Les mots-clés sont dans mots_cles.yaml (facile à compléter). Le kit REPÈRE ; un humain relit.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

DOSSIER = Path(__file__).resolve().parent
RACINE = DOSSIER.parents[1]
MOTS_CLES = DOSSIER / "mots_cles.yaml"
LANGUES_DU_PROJET = RACINE / "commun" / "langues.yaml"
MONDE = RACINE / "commun" / "monde.yaml"

PUCE = re.compile(r"^\s*(?:[-*•–]|\d{1,2}[.)])\s+")
SEPARATEUR_TABLEAU = re.compile(r"^\s*\|?\s*:?-{3,}")
POINTS = re.compile(r"(\d+)\s*(?:points?|pts|punkte?|%)(?!\w)")
HORAIRE_AVANT = {"a", "des", "vers", "jusqu'a", "um", "ab", "bis", "at", "from", "until", "by", "avant", "apres",
                 "nach", "vor", "before", "after"}


# ---------------------------------------------------------------- outils de texte
def normaliser(texte: str) -> str:
    """Minuscules, sans accents, ß → ss, apostrophes droites, tirets → espaces."""
    t = unicodedata.normalize("NFKD", texte.casefold())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return t.replace("’", "'").replace("‘", "'").replace("-", " ").replace("‐", " ")


@lru_cache(maxsize=4096)
def motif(mot: str) -> re.Pattern:
    """Un mot-clé → une recherche. « apport* » = tous les mots qui commencent par « apport »."""
    m = normaliser(mot).strip()
    prefixe = m.endswith("*")
    m = m.rstrip("*").strip()
    corps = r"\s+".join(re.escape(p) for p in m.split())
    if any(ord(c) >= 0x2E80 for c in m):  # chinois, japonais : pas d'espaces, on cherche n'importe où
        return re.compile(corps)
    return re.compile(r"(?<!\w)" + corps + (r"\w*" if prefixe else r"(?!\w)"))


def trouver(texte_normalise: str, mots: list[str]) -> list[str]:
    """Les mots-clés présents dans le texte (déjà normalisé), dans l'ordre de la liste, sans doublon."""
    vus: list[str] = []
    for mot in mots:
        if mot not in vus and motif(mot).search(texte_normalise):
            vus.append(mot)
    return vus


def compter(texte_normalise: str, mots: list[str]) -> int:
    return sum(len(motif(m).findall(texte_normalise)) for m in dict.fromkeys(mots))


class Texte:
    """Le texte du défi, normalisé pour chercher, avec le lien vers le texte d'origine pour montrer les vrais mots."""

    def __init__(self, original: str) -> None:
        self.original = original
        morceaux, self._index = [], []
        for i, car in enumerate(original):
            for c in normaliser(car):
                morceaux.append(c)
                self._index.append(i)
        self.normalise = "".join(morceaux)

    def occurrences(self, mots: list[str], maximum: int = 6) -> list[str]:
        """Les mots tels qu'ils sont écrits dans le défi (en minuscules), dans l'ordre du texte, sans doublon."""
        trouves: list[tuple[int, str]] = []
        for mot in dict.fromkeys(mots):
            for m in motif(mot).finditer(self.normalise):
                debut, fin = self._index[m.start()], self._index[m.end() - 1] + 1
                trouves.append((debut, " ".join(self.original[debut:fin].split()).casefold()))
        return list(dict.fromkeys(t for _, t in sorted(trouves)))[:maximum]


def nettoyer(ligne: str) -> str:
    """Enlève les marques de liste, de titre, de tableau et de gras, pour l'affichage."""
    s = PUCE.sub("", ligne.strip())
    s = s.lstrip("#").strip().strip("|").strip()
    s = re.sub(r"\s*\|\s*", " — ", s)
    return s.replace("**", "").replace("__", "").strip()


@lru_cache(maxsize=1)
def mots_cles() -> dict:
    return yaml.safe_load(MOTS_CLES.read_text(encoding="utf-8"))


def langues_du_projet() -> dict:
    return yaml.safe_load(LANGUES_DU_PROJET.read_text(encoding="utf-8"))["langues"]


# ---------------------------------------------------------------- résultat
@dataclass
class Capacite:
    cle: str
    mots: list[str]
    nombre: int  # combien de fois les mots apparaissent
    dans_criteres: int  # dans combien de critères du jury
    lignes: list[str] = field(default_factory=list)  # où on l'a vue (deux premières lignes)

    @property
    def priorite(self) -> int:
        return self.nombre + 3 * self.dans_criteres


@dataclass
class Critere:
    texte: str
    points: int | None = None
    capacites: list[str] = field(default_factory=list)


@dataclass
class Duree:
    valeur: float
    unite: str  # secondes, minutes, heures
    ligne: str
    demonstration: bool = False

    @property
    def secondes(self) -> float:
        return self.valeur * {"secondes": 1, "minutes": 60, "heures": 3600}[self.unite]

    def __str__(self) -> str:
        v = int(self.valeur) if self.valeur == int(self.valeur) else self.valeur
        return f"{v} {self.unite}"


@dataclass
class Analyse:
    titre: str
    langue_du_texte: str | None
    genres: dict[str, list[str]]  # genre → mots trouvés, le plus cité d'abord
    capacites: list[Capacite]  # dans l'ordre de mots_cles.yaml
    langues: dict[str, list[str]]  # code → mots trouvés
    durees: list[Duree]
    horaires: list[str]
    criteres: list[Critere]
    securite: list[str]
    lieux_objets: dict[str, list[str]]  # id du monde → mots trouvés
    questions: list[str]

    @property
    def genre(self) -> str | None:
        return next(iter(self.genres), None)

    @property
    def cles(self) -> list[str]:
        return [c.cle for c in self.capacites]

    def capacite(self, cle: str) -> Capacite | None:
        return next((c for c in self.capacites if c.cle == cle), None)

    @property
    def duree_demo(self) -> Duree | None:
        demo = [d for d in self.durees if d.demonstration and d.unite != "heures"]
        return demo[0] if demo else None


# ---------------------------------------------------------------- lecture par sections
def _est_titre(lignes: list[str], i: int) -> bool:
    s = lignes[i].strip()
    if s.startswith("#"):
        return True
    if s.startswith("|") and i + 1 < len(lignes) and SEPARATEUR_TABLEAU.match(lignes[i + 1]):
        return True  # en-tête d'un tableau
    if PUCE.match(s):
        return False
    gras = s.startswith("**") and s.rstrip(":").rstrip().endswith("**")
    return gras or (s.endswith(":") and len(s) <= 90)


def _collecter(lignes: list[str], titres: list[str], mots_lignes: list[str], avec_points: bool) -> list[str]:
    """Les lignes d'une catégorie : listes sous un titre qui en parle, et toute ligne qui contient un mot fort."""
    trouvees: list[str] = []
    dans_section = False
    for i, brute in enumerate(lignes):
        s = brute.strip()
        if not s or SEPARATEUR_TABLEAU.match(s):
            continue
        n = normaliser(s)
        if _est_titre(lignes, i):
            dans_section = bool(trouver(n, titres))
            # Un titre du genre « Critère 1 : accueil (30 points) » est lui-même un critère.
            if ":" in s and not s.rstrip().endswith(":") and (trouver(n, mots_lignes) or (avec_points and POINTS.search(n))):
                trouvees.append(nettoyer(s))
            continue
        liste = bool(PUCE.match(s)) or s.startswith("|")
        fort = bool(trouver(n, mots_lignes)) or (avec_points and bool(POINTS.search(n)))
        if (dans_section and liste) or fort:
            trouvees.append(nettoyer(s))
        elif dans_section and not liste:
            dans_section = False  # un paragraphe ordinaire termine la section
    return list(dict.fromkeys(t for t in trouvees if t))


def _durees(lignes: list[str], unites: dict[str, list[str]], mots_demo: list[str]) -> tuple[list[Duree], list[str]]:
    durees: list[Duree] = []
    horaires: list[str] = []
    for brute in lignes:
        s = brute.strip()
        if not s:
            continue
        n = normaliser(s)
        demo = bool(trouver(n, mots_demo))
        for unite, mots in unites.items():
            alternatives = "|".join(re.escape(normaliser(m).rstrip("*")) + (r"\w*" if m.endswith("*") else "")
                                    for m in mots)
            for m in re.finditer(r"(?<![\w.,])(\d+(?:[.,]\d+)?)\s*(?:" + alternatives + r")(?![\w])", n):
                avant = n[:m.start()].split()
                if avant and avant[-1] in HORAIRE_AVANT:
                    horaires.append(f"{m.group(0).strip()} — « {nettoyer(s)} »")
                    continue
                durees.append(Duree(float(m.group(1).replace(",", ".")), unite, nettoyer(s), demo))
    return durees, list(dict.fromkeys(horaires))


def _langue_du_texte(texte_normalise: str, petits_mots: dict[str, list[str]]) -> str | None:
    jetons = re.findall(r"[a-z]+", texte_normalise)
    scores = {}
    for code, mots in petits_mots.items():
        connus = {normaliser(m) for m in mots}
        scores[code] = sum(1 for j in jetons if j in connus)
    meilleur = max(scores, key=lambda c: scores[c]) if scores else None
    return meilleur if meilleur and scores[meilleur] >= 3 else None


def _lieux_objets(texte_normalise: str, a_ignorer: list[str]) -> dict[str, list[str]]:
    monde = yaml.safe_load(MONDE.read_text(encoding="utf-8"))
    ignores = {normaliser(m).rstrip("*") for m in a_ignorer}
    trouves: dict[str, list[str]] = {}
    for chose in monde.get("lieux", []) + monde.get("objets", []):
        noms = [n for liste in (chose.get("noms") or {}).values() for n in liste if normaliser(n) not in ignores]
        mots = trouver(texte_normalise, noms)
        if mots:
            trouves[chose["id"]] = mots
    return trouves


# ---------------------------------------------------------------- l'analyse
def analyser(texte: str) -> Analyse:
    mc = mots_cles()
    lignes = texte.splitlines()
    defi = Texte(texte)
    tout = defi.normalise

    titre = next((nettoyer(l) for l in lignes if l.strip().startswith("#")), None) \
        or next((nettoyer(l) for l in lignes if l.strip()), "Défi sans titre")

    genres_comptes = {g: compter(tout, mots) for g, mots in mc["genres"].items()}
    genres = {g: defi.occurrences(mc["genres"][g]) for g in sorted(
        (g for g, c in genres_comptes.items() if c), key=lambda g: -genres_comptes[g])}

    criteres_textes = _collecter(lignes, mc["criteres"]["titres"], mc["criteres"]["lignes"], avec_points=True)
    criteres = []
    for t in criteres_textes:
        n = normaliser(t)
        p = POINTS.search(n)
        caps = [cle for cle, mots in mc["capacites"].items() if trouver(n, mots)]
        criteres.append(Critere(texte=t, points=int(p.group(1)) if p else None, capacites=caps))

    capacites = []
    for cle, mots in mc["capacites"].items():
        if not trouver(tout, mots):
            continue
        ou = [nettoyer(l) for l in lignes if l.strip() and trouver(normaliser(l), mots)]
        capacites.append(Capacite(cle=cle, mots=defi.occurrences(mots), nombre=compter(tout, mots),
                                  dans_criteres=sum(1 for c in criteres if cle in c.capacites), lignes=ou[:2]))

    langues = {code: defi.occurrences(liste) for code, liste in mc["langues"].items() if trouver(tout, liste)}
    securite = [s for s in _collecter(lignes, mc["securite"]["titres"], mc["securite"]["lignes"], avec_points=False)
                if s not in criteres_textes]  # un critère du jury qui parle de sécurité reste un critère
    durees, horaires = _durees(lignes, mc["durees"], mc["mots_demonstration"])
    lieux_objets = _lieux_objets(tout, mc["criteres"]["titres"])

    analyse = Analyse(titre=titre, langue_du_texte=_langue_du_texte(tout, mc["langue_du_texte"]), genres=genres,
                      capacites=capacites, langues=langues, durees=durees, horaires=horaires, criteres=criteres,
                      securite=securite, lieux_objets=lieux_objets, questions=[])
    analyse.questions = _questions(analyse)
    return analyse


def _questions(a: Analyse) -> list[str]:
    """Ce que le texte ne dit pas : à demander aux organisateurs samedi matin."""
    q = []
    if not a.genre:
        q.append("Quel robot aurons-nous (genre, fabricant, modèle) ?")
    q.append("Où sont le kit de programmation du robot et sa documentation, et sous quelle licence ?")
    q.append("Vitesse maximale, arrêt d'urgence, chien de garde du robot : où est-ce écrit ? (à vérifier dans le kit du fabricant)")
    if not a.criteres:
        q.append("Quelle est la grille du jury (critères et points) ?")
    if not a.duree_demo:
        q.append("Combien de temps dure la démonstration ?")
    q.append("À quelle heure passons-nous devant le jury ?")
    if not a.langues and ("parler" in a.cles or "plusieurs_langues" in a.cles):
        q.append("Quelles langues parlent les visiteurs ?")
    connues = langues_du_projet()
    for code in a.langues:
        if code not in connues:
            nom = mots_cles()["noms_des_langues"].get(code, code)
            q.append(f"Le {nom} est-il obligatoire ? (le projet ne le parle pas encore)")
    if not a.securite:
        q.append("Quelles règles de sécurité impose l'organisation (distance au public, vitesse, zone) ?")
    return q
