"""Brique 8 — Les aides apprises : « quand on dit X, cela veut dire Y ».

Un humain apprend un mot au robot (écran). Le mot est gardé dans `journal/aides_apprises.yaml` et ajouté au monde
(les noms des lieux et des objets) : le cerveau le comprend tout de suite, et à chaque démarrage.
Le fichier est HORS du dépôt suivi par git (le dossier `journal/` est ignoré, voir .gitignore) : ce qu'on écrit
pendant le Carnival ne part jamais dans le dépôt par erreur. Seulement des MOTS, jamais de nom de personne.
L'ancien fichier, dans le dépôt (`briques/b08_doute/aides_apprises.yaml`), est relu une fois s'il contient des
mots : ils sont recopiés dans `journal/`, puis l'ancien fichier est laissé vide, avec un commentaire.

Le mot est refusé s'il prête à confusion ou s'il est mal écrit :
- autre chose que des lettres (accents permis), espaces, tiret, apostrophe et caractères chinois : pas de chiffre,
  pas de « < » ni « > », pas de caractère invisible, ni de caractère qui inverse le sens du texte ;
- trop court ou trop long (3 lettres à 40 caractères, 4 mots au plus ; en chinois, au moins deux caractères) ;
- il contient, ou est contenu dans : un mot d'arrêt (« stop »), un mot d'action (« va », « prends »), un « oui »,
  un « non », une négation, ou un nom d'un AUTRE lieu ou objet (« la table » ne peut pas vouloir dire la cuisine).
  « Contenir » se lit comme le cerveau à règles lit une phrase : mot entier (langues à espaces), morceau de texte
  (chinois).
Au démarrage, chaque mot du fichier est revérifié : un mot qui ne passe plus est ignoré, et c'est écrit au journal.
"""
from __future__ import annotations

import logging
import os
import re
import unicodedata
from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ValidationError

from commun.monde import Monde

log = logging.getLogger("doute")
RACINE = Path(__file__).resolve().parents[2]
CHEMIN_AIDES = RACINE / "journal" / "aides_apprises.yaml"  # hors du dépôt suivi par git (journal/ est ignoré)
ANCIEN_CHEMIN_AIDES = Path(__file__).with_name("aides_apprises.yaml")  # avant : dans le dépôt (relu une fois)
ENTETE = """# Les aides apprises (brique 8) : « quand on dit X, cela veut dire Y ».
# Écrit par le robot quand un humain lui apprend un mot (écran : « apprendre un mot »). Relu au démarrage.
# Seulement des mots, jamais de nom de personne. sens = un lieu ou un objet de commun/monde.yaml.
# Ce fichier est dans journal/ : il n'est PAS suivi par git (voir .gitignore).
"""
ENTETE_ANCIEN = """# ANCIEN emplacement des aides apprises (brique 8). Ne plus rien écrire ici.
# Les mots appris sont maintenant dans journal/aides_apprises.yaml (hors du dépôt suivi par git).
# S'il reste des mots ici, ils y sont recopiés au prochain démarrage, puis ce fichier est vidé.
"""
LONGUEUR_MAX = 40  # caractères
MOTS_MAX = 4
SEPARATEURS = " -'’"  # espace, tiret, apostrophes (droite et typographique)
_CJK = re.compile(r"[一-鿿]")


class MotAppris(BaseModel):
    mot: str
    langue: str
    sens: str  # id d'un lieu ou d'un objet du monde
    genre: Literal["lieu", "objet"]
    appris_le: str = ""


class AideRefusee(ValueError):
    """Le mot n'est pas appris ; le message dit pourquoi (en français)."""


def _caractere_permis(c: str) -> bool:
    """Lettres latines (avec accents), caractères chinois, espace, tiret, apostrophe. Rien d'autre."""
    if c in SEPARATEURS or _CJK.fullmatch(c):
        return True
    return unicodedata.category(c).startswith("L") and "LATIN" in unicodedata.name(c, "")


def _se_touchent(a: str, b: str) -> bool:
    """a contient b, ou b contient a : mots entiers (langues à espaces), morceau de texte (chinois)."""
    from briques.b06_cerveau.branchements.regles import contient, normaliser

    na, nb = normaliser(a), normaliser(b)
    if not na.strip() or not nb.strip():
        return False
    return contient(na, b) or contient(nb, a)


def _mots_reserves() -> list[tuple[str, str]]:
    """(mot, ce qu'il veut dire) : un mot appris ne doit ni en contenir un, ni être contenu dans l'un d'eux."""
    from briques.b06_cerveau.branchements.regles import _lexique
    from commun.chaine import NEGATIONS
    from commun.phrases import _oui_non

    lex = _lexique()
    on = _oui_non()
    res = [(m, "« stop » (l'arrêt)") for mots in lex["verbes"]["arreter"].values() for m in mots]
    res += [(m, "un mot d'action") for nom, table in lex["verbes"].items() if nom != "arreter"
            for mots in table.values() for m in mots]
    res += [(m, "un mot d'action (geste)") for table in lex["gestes"].values() for mots in table.values() for m in mots]
    res += [(m, "un « oui »") for mots in on["oui"].values() for m in mots] + [(m, "un « oui »") for m in on.get("partout", [])]
    res += [(m, "un « non »") for mots in on["non"].values() for m in mots]
    res += [(m, "une négation") for mots in NEGATIONS.values() for m in mots]
    res += [(m, "une négation") for m in on.get("negations", [])]
    # Relecture du lot C : les mots du cerveau qui ne sont pas des noms (petits pas, sens, côtés, ici, vitesses,
    # nombres, unités) : « un peu » = cuisine ferait d'un petit pas un trajet.
    from briques.b06_cerveau.branchements import regles

    res += [(m, "« un peu » (petit pas)") for mots in regles.PETIT_DEPLACEMENT.values() for m in mots]
    res += [(m, "un sens ou un côté") for motifs in regles._CLAIRS.values() for m in motifs if m.isalpha() or " " in m
            and all(x.isalpha() for x in m.split())]
    res += [(m, "un sens ou un côté") for m in regles._AMBIGUS]
    res += [(m, "un nombre") for m in list(regles._MOTS_NOMBRES) + list(regles._MOTS_CENT) + list(regles._MOTS_MILLE)
            if len(m) > 2]
    res += [(m, "une unité ou une vitesse") for m in ("metre", "metres", "meter", "meters", "metern", "metri", "metro",
                                                      "centimetre", "kilometre", "seconde", "second", "sekunde",
                                                      "secondo", "newton", "newtons", "vite", "lentement", "schnell",
                                                      "langsam", "fast", "slow", "slowly", "veloce", "piano", "米", "秒")]
    res += [(m, "un mot vague") for m in ("doucement", "encore", "plus loin", "en face", "centre", "milieu", "la-bas",
                                         "dort", "dahin", "dorthin", "hierhin", "noch", "weiter", "again", "further",
                                         "more", "ancora", "piu lontano", "laggiu", "那边", "再")]
    res += [(m, "« ici », « devant », « moi »") for m in ("ici", "devant", "moi", "toi", "hier", "da", "vorne",
                                                         "mir", "here", "there", "me", "you", "qui", "qua", "davanti",
                                                         "me", "这里", "那里", "我", "前面")]
    return res


class AidesApprises:
    def __init__(self, chemin: str | Path = CHEMIN_AIDES, ancien: str | Path | None = None) -> None:
        """`chemin` : où garder les mots. `ancien` : un fichier d'avant à reprendre une fois (par défaut, pour le
        chemin habituel : l'ancien fichier du dépôt). Un réglage qui montre encore l'ancien fichier du dépôt
        (reglages.yaml d'avant cette correction) est redirigé vers journal/."""
        chemin = Path(chemin)
        if _meme_fichier(chemin, ANCIEN_CHEMIN_AIDES):
            log.warning("aides apprises : %s est dans le dépôt ; elles sont maintenant gardées dans %s",
                        chemin, CHEMIN_AIDES)
            chemin = CHEMIN_AIDES
        if ancien is None and _meme_fichier(chemin, CHEMIN_AIDES):
            ancien = ANCIEN_CHEMIN_AIDES
        self.chemin = chemin
        self.mots: list[MotAppris] = self._lire(self.chemin)
        if ancien is not None and not _meme_fichier(Path(ancien), self.chemin):
            self._reprendre(Path(ancien))

    @staticmethod
    def _lire(chemin: Path) -> list[MotAppris]:
        if not chemin.exists():
            return []
        try:
            donnees = yaml.safe_load(chemin.read_text(encoding="utf-8")) or {}
        except (yaml.YAMLError, UnicodeDecodeError):
            log.warning("%s illisible : ignoré", chemin)
            return []
        mots = []
        for m in (donnees.get("mots") if isinstance(donnees, dict) else None) or []:
            try:
                mots.append(MotAppris.model_validate(m))
            except ValidationError:
                log.warning("mot appris mal écrit, ignoré : %r", m)
        return mots

    def _reprendre(self, ancien: Path) -> None:
        """Recopier les mots de l'ancien fichier (dans le dépôt) dans le nouveau, puis vider l'ancien."""
        anciens = self._lire(ancien)
        if not anciens:
            return
        deja = {(m.mot, m.langue, m.sens) for m in self.mots}
        self.mots += [m for m in anciens if (m.mot, m.langue, m.sens) not in deja]
        self._ecrire()
        _ecrire_d_un_coup(ancien, ENTETE_ANCIEN + "mots: []\n")
        log.warning("aides apprises : %d mot(s) repris de %s vers %s (l'ancien fichier est vidé)",
                    len(anciens), ancien, self.chemin)

    def _ecrire(self) -> None:
        texte = ENTETE + yaml.safe_dump({"mots": [m.model_dump() for m in self.mots]}, allow_unicode=True, sort_keys=False)
        _ecrire_d_un_coup(self.chemin, texte)

    def appliquer(self, monde: Monde) -> int:
        """Ajouter les mots appris aux noms du monde, après les avoir revérifiés. Rend le nombre de mots ajoutés.
        Un mot qui ne passe plus la vérification (fichier écrit à la main, règle plus stricte) est ignoré."""
        n = 0
        gardes = []
        for m in self.mots:
            try:
                self.verifier(m.mot, m.langue, m.sens, monde)
            except AideRefusee as e:
                log.warning("mot appris « %s » ignoré : %s", m.mot, e)
                continue
            gardes.append(m)
            chose = monde.lieu(m.sens) if m.genre == "lieu" else monde.objet(m.sens)
            noms = chose.noms.setdefault(m.langue, [])
            if m.mot not in noms:
                noms.append(m.mot)
                n += 1
        self.mots = gardes
        return n

    def verifier(self, mot: str, langue: str, sens: str, monde: Monde) -> MotAppris:
        """Le mot peut-il être appris ? Rend le MotAppris, ou lève AideRefusee avec la raison."""
        from briques.b06_cerveau.branchements.regles import normaliser
        from commun.phrases import est_ordre_arret, langues

        if not isinstance(mot, str):
            raise AideRefusee("le mot doit être un texte")
        mot = " ".join(unicodedata.normalize("NFKC", mot).split())
        if langue not in langues()["langues"]:
            raise AideRefusee(f"langue inconnue « {langue} » (connues : {', '.join(langues()['langues'])})")
        interdits = sorted({c for c in mot if not _caractere_permis(c)})
        if interdits:
            montres = ", ".join(f"U+{ord(c):04X}" if not c.isprintable() or unicodedata.category(c)[0] in "CZ"
                                else f"« {c} »" for c in interdits)
            raise AideRefusee(f"seulement des lettres, des espaces, « - », « ' » et des caractères chinois "
                              f"(refusé : {montres})")
        simple = normaliser(mot).strip()
        if not simple or len(mot) > LONGUEUR_MAX:
            raise AideRefusee(f"le mot doit avoir entre 1 et {LONGUEUR_MAX} caractères")
        if len(mot.split()) > MOTS_MAX:
            raise AideRefusee(f"{MOTS_MAX} mots au plus")
        if _CJK.search(mot) and len(_CJK.findall(mot)) < 2:
            raise AideRefusee("en chinois, il faut au moins deux caractères (un seul se cache dans trop de mots)")
        if not _CJK.search(mot) and len(simple.replace(" ", "")) < 3:
            raise AideRefusee("il faut au moins trois lettres (« a » se cacherait dans « va à la table »)")
        chose = monde.lieu(sens) or monde.objet(sens)
        if chose is None:
            raise AideRefusee(f"« {sens} » n'est ni un lieu ni un objet du monde (commun/monde.yaml)")
        genre = "lieu" if monde.lieu(sens) else "objet"
        if est_ordre_arret(mot):
            raise AideRefusee("ce mot contient un « stop » : il reste réservé à l'arrêt")
        reserves = _mots_reserves()
        for m, quoi in reserves:  # d'abord le mot tout seul : la raison la plus claire
            if normaliser(m).strip() == simple:
                raise AideRefusee(f"« {mot} » est déjà {quoi} : il prêterait à confusion")
        for m, quoi in reserves:  # puis « contient », ou « est contenu dans »
            if _se_touchent(mot, m):
                raise AideRefusee(f"« {mot} » contient {quoi} (« {m} »), ou s'y cache : il prêterait à confusion")
        for autre in monde.lieux + monde.objets:
            if autre.id == sens:
                continue
            for _, n in autre.tous_les_noms():
                if _se_touchent(mot, n):
                    if normaliser(n).strip() == simple:
                        raise AideRefusee(f"« {mot} » veut déjà dire autre chose : c'est un nom de « {autre.id} »")
                    raise AideRefusee(f"« {mot} » veut déjà dire autre chose : il touche le nom « {n} » "
                                      f"({autre.id}) : il le contient, ou s'y cache")
        return MotAppris(mot=mot, langue=langue, sens=sens, genre=genre, appris_le=date.today().isoformat())

    def apprendre(self, mot: str, langue: str, sens: str, monde: Monde) -> tuple[MotAppris, bool]:
        """Apprendre le mot (fichier + monde). Rend (le mot, nouveau ?)."""
        from briques.b06_cerveau.branchements.regles import normaliser

        appris = self.verifier(mot, langue, sens, monde)
        chose = monde.lieu(sens) if appris.genre == "lieu" else monde.objet(sens)
        simple = normaliser(appris.mot).strip()
        if any(normaliser(n).strip() == simple for n in chose.noms.get(langue, [])):
            return appris, False  # déjà connu : rien à écrire
        self.mots.append(appris)
        self._ecrire()
        chose.noms.setdefault(langue, []).append(appris.mot)
        return appris, True

    def liste(self) -> list[dict]:
        return [m.model_dump() for m in self.mots]


def _meme_fichier(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return False


def _ecrire_d_un_coup(chemin: Path, texte: str) -> None:
    """D'un seul coup : une coupure de courant ne laisse pas un fichier à moitié écrit."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    provisoire = chemin.with_suffix(".partiel")
    provisoire.write_text(texte, encoding="utf-8")
    os.replace(provisoire, chemin)
