"""Brique 6 — Le cerveau « à règles » : des mots-clés, aucun modèle à télécharger.

Il sert aux tests et en dernier secours. Il est volontairement prudent :
au moindre doute (deux actions, deux lieux, rien de précis), il pose une question.
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from pathlib import Path

import yaml

from briques.b01_prise.actions import ActionDemandee
from briques.b01_prise.carte import CarteIdentite
from commun.monde import Monde

from ..prise_cerveau import Cerveau, Decision, garde_fou_carte

LEXIQUE = Path(__file__).with_name("regles_lexique.yaml")
_CJK = re.compile(r"[一-鿿]")
def normaliser(texte: str) -> str:
    t = unicodedata.normalize("NFKD", texte.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.replace("ß", "ss")
    return " " + re.sub(r"[^\w一-鿿]+", " ", t).strip() + " "


def contient(texte_norm: str, mot: str) -> bool:
    m = normaliser(mot).strip()
    if not m:
        return False
    if _CJK.search(m):
        return m in texte_norm
    return f" {m} " in texte_norm


@lru_cache(maxsize=1)
def _lexique() -> dict:
    return yaml.safe_load(LEXIQUE.read_text(encoding="utf-8"))


# Les chiffres dits par la personne (vitesse, force, distance), dans les 6 langues. Testés dans test_cerveau.py.
# Principe de sécurité : en cas de doute, on lit le nombre le PLUS GRAND (« 1,500 m » = 1500 m, pas 1,5 m) ; plusieurs
# distances s'additionnent ; plusieurs vitesses ou forces : la plus grande. Le gardien refuse alors en expliquant.
_NOMBRE = r"(\d+(?:[.,]\d+)?)"
_UNITE_M = r"(?:metres?|meters?|metern|meter|metri|metro|mt|m|米)"
_UNITE_KM = r"(?:kilometres?|kilometers?|kilometern|kilometer|chilometri|chilometro|km|公里)"
_UNITE_CM = r"(?:centimetres?|centimeters?|zentimetern|zentimeter|centimetri|centimetro|cm|厘米|公分)"
_UNITE_MM = r"(?:millimetres?|millimeters?|millimeter|millimetri|mm|毫米)"
_PAR_SECONDE = (r"(?:\s*/\s*(?:s|sec|seconde|second|sekunde|secondo|秒)(?![a-z])|\s*\.?\s*s-1(?!\d)|-seconde"
                r"|\s+(?:par|a la|per|a|an|pro|in der|in de|i de|i dr|i der|al|each|every|chaque|je)\s+"
                r"(?:seconde|second|sekunde|secondo|sec|s)(?![a-z])|\s*每秒)")
_PAR_MINUTE = (r"(?:\s*/\s*(?:min|minute|minuto)(?![a-z])"
               r"|\s+(?:par|a la|per|a|an|pro|in der|al|each|every|chaque|je)\s+(?:minute|minuto|min)(?![a-z])|\s*每分钟)")
_PAR_HEURE = (r"(?:\s*/\s*(?:h|heure|hour|stunde|ora|小时)(?![a-z])"
              r"|\s+(?:a l'?heure|a l heure|par heure|heure|per hour|an hour|a hour|pro stunde|in der stunde|i de stund|"
              r"all'?ora|all ora|orari|l'ora|每小时)(?![a-z])|\s*每小时)")
# (expression, diviseur pour avoir des m/s). Toutes sont retirées du texte avant de chercher une distance.
_VITESSES = [
    (re.compile(_NOMBRE + r"\s*" + _UNITE_CM + _PAR_SECONDE + r"(?![a-z])", re.I), 100.0),
    (re.compile(_NOMBRE + r"\s*" + _UNITE_MM + _PAR_SECONDE + r"(?![a-z])", re.I), 1000.0),
    (re.compile(_NOMBRE + r"\s*" + _UNITE_M + _PAR_MINUTE + r"(?![a-z])", re.I), 60.0),
    (re.compile(_NOMBRE + r"\s*" + _UNITE_M + _PAR_SECONDE + r"(?![a-z])", re.I), 1.0),
    (re.compile(_NOMBRE + r"\s*(?:" + _UNITE_KM + _PAR_HEURE + r"|kmh|km/u|kmu|stundenkilometern|stundenkilometer)(?![a-z])",
                re.I), 3.6),
    (re.compile(_NOMBRE + r"\s*mps(?![a-z])", re.I), 1.0),
    (re.compile(r"每秒\s*" + _NOMBRE + r"\s*(?:米|m)(?![a-z])"), 1.0),
    (re.compile(r"每秒\s*" + _NOMBRE + r"\s*(?:厘米|公分)"), 100.0),
    (re.compile(r"每分钟\s*" + _NOMBRE + r"\s*米"), 60.0),
    (re.compile(r"每小时\s*" + _NOMBRE + r"\s*公里"), 3.6),
]
# « 2 mètres en une seconde » : une distance ET une vitesse (la distance reste dans le texte).
_EN_N_SECONDES = re.compile(_NOMBRE + r"\s*" + _UNITE_M + r"(?![a-z])\s*(?:en|in|within|innerhalb von|entro|用)?\s*"
                            + _NOMBRE + r"\s*(?:secondes?|seconds?|sekunden?|secondi|secondo|sec|s|秒)(?![a-z])", re.I)
# « plus de 5 mètres », « au moins », « mehr als », « more than »… : le chiffre n'est pas une limite sûre → question.
_CHIFFRE_VAGUE = re.compile(
    r"(?<![\w])(?:plus de|au moins|davantage que|au-dela de|au dela de|plus vite que|plus fort que|mehr als|mindestens|"
    r"uber|ueber|schneller als|starker als|more than|at least|over|beyond|faster than|harder than|piu di|almeno|oltre|"
    r"piu veloce di|piu forte di)\s+\d"
    r"|\d+(?:[.,]\d+)?\s*[^\d\s]*\s*(?:ou plus|au minimum|minimum|ou davantage|oder mehr|mindestens|or more|at least|"
    r"minimum|o piu|almeno|o di piu)(?![\w])"
    r"|(?:超过|至少|多于|不少于|起码|最少)\s*\d|\d+\s*(?:米|公里|牛)?\s*(?:以上|多)")
_FORCE = re.compile(_NOMBRE + r"\s*(n|newtons?|newton|牛顿|牛)(?![a-z])", re.I)
_DISTANCE = re.compile(_NOMBRE + r"\s*(" + _UNITE_CM + r"|" + _UNITE_KM + r"|" + _UNITE_M + r")(?![a-z/])"
                       r"(?:\s*(\d{1,2})(?!\d)(?!\s*(?:fois|mal|times|volte|次|x\b)))?", re.I)

# Les nombres dits en lettres (« cinq mètres par seconde », « fünf Meter », « twenty newtons », « 五米每秒 ») :
# l'écoute les écrit parfois ainsi. On les change en chiffres AVANT de chercher une vitesse, une force, une distance.
# Jusqu'aux milliers ; « a » (anglais) n'est lu comme « 1 » que devant une unité (« a meter »).
_MOTS_NOMBRES = {
    # français (quatre-vingts : voir plus bas)
    "zero": 0, "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8,
    "neuf": 9, "dix": 10, "onze": 11, "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15, "seize": 16,
    "vingt": 20, "trente": 30, "quarante": 40, "cinquante": 50, "soixante": 60, "septante": 70, "huitante": 80,
    "octante": 80, "nonante": 90,
    # allemand
    "null": 0, "eins": 1, "ein": 1, "eine": 1, "einen": 1, "einem": 1, "zwei": 2, "zwo": 2, "drei": 3, "vier": 4,
    "funf": 5, "sechs": 6, "sieben": 7, "acht": 8, "neun": 9, "zehn": 10, "elf": 11, "zwolf": 12, "dreizehn": 13,
    "vierzehn": 14, "funfzehn": 15, "sechzehn": 16, "siebzehn": 17, "achtzehn": 18, "neunzehn": 19, "zwanzig": 20,
    "dreissig": 30, "vierzig": 40, "funfzig": 50, "sechzig": 60, "siebzig": 70, "achtzig": 80, "neunzig": 90,
    # suisse allemand (sans accents : « nüün » → nuun ; « nun » = « maintenant » en allemand, jamais lu comme 9)
    "eis": 1, "zwoi": 2, "dru": 3, "vieri": 4, "foif": 5, "fuf": 5, "sachs": 6, "sibe": 7, "siebe": 7, "achti": 8,
    "nuun": 9, "zah": 10, "olf": 11, "zwolfi": 12, "drizah": 13, "vierzah": 14, "foifzah": 15, "fufzah": 15,
    "sachzah": 16, "sibezah": 17, "achzah": 18, "nuunzah": 19, "zwanzg": 20, "drissg": 30, "driissg": 30,
    "vierzg": 40, "foifzg": 50, "fufzg": 50, "sachzg": 60, "sibezg": 70, "achzg": 80, "nuunzg": 90,
    # italien
    "uno": 1, "due": 2, "tre": 3, "quattro": 4, "cinque": 5, "sei": 6, "sette": 7, "otto": 8, "nove": 9,
    "dieci": 10, "undici": 11, "dodici": 12, "tredici": 13, "quattordici": 14, "quindici": 15, "sedici": 16,
    "diciassette": 17, "diciotto": 18, "diciannove": 19, "venti": 20, "trenta": 30, "quaranta": 40,
    "cinquanta": 50, "sessanta": 60, "settanta": 70, "ottanta": 80, "novanta": 90,
    # anglais
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
}
_MOTS_CENT = {"cent", "cents", "hundert", "hundred", "cento"}
_MOTS_MILLE = {"mille", "tausend", "tuusig", "thousand", "mila"}
_MOTS_VIRGULE = {"virgule", "komma", "koma", "point", "virgola"}
_DIZAINES_ELIDEES = {"vent": 20, "trent": 30, "quarant": 40, "cinquant": 50, "sessant": 60, "settant": 70,
                     "ottant": 80, "novant": 90}  # italien : « ventuno », « trentotto »
_POUR_DECOUPER = {**_MOTS_NOMBRES, **{m: 100 for m in _MOTS_CENT}, **{m: 1000 for m in _MOTS_MILLE}, **_DIZAINES_ELIDEES}
_UN_MOT_NOMBRE = "|".join(sorted([*_MOTS_NOMBRES, *_MOTS_CENT, *_MOTS_MILLE], key=len, reverse=True))
_SUITE_DE_NOMBRES = re.compile(
    rf"(?<![\w.])(?:{_UN_MOT_NOMBRE})(?:(?:\s+|-)(?:(?:et|and|und|e)(?:\s+|-))?(?:{_UN_MOT_NOMBRE}))*(?![\w])")
_MILLIERS = re.compile(r"(?<![\d.,'])([1-9]\d{0,2})((?:[.,'’   ]\d{3})+)(?![\d])")  # « 0,125 » reste 0,125
_CHIFFRES_ZH = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_MULT_ZH = {"十": 10, "百": 100, "千": 1000}
_NOMBRE_ZH = re.compile(r"[零〇一二两三四五六七八九十百千万]+(?:点[零〇一二两三四五六七八九]+)?")
_UNITE_DEMI = r"(" + _UNITE_CM + r"|" + _UNITE_KM + r"|" + _UNITE_M + r"|newtons?|newton)"


# Les mots collés n'existent qu'en allemand (et suisse allemand) et en italien : on ne découpe qu'avec les mots d'UNE
# de ces langues (sinon « unten » = un + ten = 11, « Seiten » = sei + ten = 16).
_ALLEMAND = set("null eins ein eine zwei zwo drei vier funf sechs sieben acht neun zehn elf zwolf dreizehn vierzehn "
                "funfzehn sechzehn siebzehn achtzehn neunzehn zwanzig dreissig vierzig funfzig sechzig siebzig achtzig "
                "neunzig eis zwoi dru vieri foif fuf sachs sibe siebe achti nuun zah olf zwolfi drizah vierzah foifzah "
                "fufzah sachzah sibezah achzah nuunzah zwanzg drissg driissg vierzg foifzg fufzg sachzg sibezg achzg "
                "nuunzg hundert tausend tuusig und".split())
_ITALIEN = set("uno due tre quattro cinque sei sette otto nove dieci undici dodici tredici quattordici quindici sedici "
               "diciassette diciotto diciannove venti trenta quaranta cinquanta sessanta settanta ottanta novanta cento "
               "mille mila vent trent quarant cinquant sessant settant ottant novant".split())


def _decouper(mot: str) -> list[str] | None:
    """« funfundzwanzig » → [funf, und, zwanzig] ; « duecento » → [due, cento]. None si le mot n'est pas un nombre."""
    for famille in (_ALLEMAND, _ITALIEN):
        parts = _decouper_avec(mot, famille)
        if parts:
            return parts
    return None


def _decouper_avec(mot: str, famille: set[str]) -> list[str] | None:
    n = len(mot)
    meilleur: list[list[str] | None] = [None] * (n + 1)
    meilleur[0] = []
    for i in range(n):
        if meilleur[i] is None:
            continue
        for j in range(i + 2, n + 1):
            morceau = mot[i:j]
            if morceau in famille:
                if meilleur[j] is None or len(meilleur[j]) > len(meilleur[i]) + 1:
                    meilleur[j] = meilleur[i] + [morceau]
    parts = meilleur[n]
    if not parts or len(parts) < 2 or parts[-1] == "und" or parts[0] == "und":
        return None
    return parts


def _valeur_suite(mots: list[str]) -> int:
    total, courant = 0, 0
    for m in mots:
        if m in _MOTS_CENT:
            courant = max(courant, 1) * 100
        elif m in _MOTS_MILLE:
            total += max(courant, 1) * 1000
            courant = 0
        elif m in _POUR_DECOUPER:
            courant += _POUR_DECOUPER[m]
    return total + courant


def _valeur_zh(t: str) -> str:
    """一百二十 → 120 ; 一千五 → 1500 (sens courant) ; 一百零五 → 105 ; 两万 → 20000 ; 零点五 → 0.5."""
    entier, _, decimales = t.partition("点")
    total, section, chiffre, dernier_mult = 0, 0, 0, 0
    for c in entier:
        if c == "万":
            if not (section or chiffre):  # « 万一 » (« au cas où ») : pas un nombre
                continue
            total += (section + chiffre) * 10000
            section, chiffre, dernier_mult = 0, 0, 10000
        elif c in _MULT_ZH:
            section += max(chiffre, 1) * _MULT_ZH[c] if (chiffre or not section) else _MULT_ZH[c]
            chiffre, dernier_mult = 0, _MULT_ZH[c]
        elif c in "零〇" and (section or total):
            dernier_mult = 0  # « 一百零五 » = 105 : le chiffre suivant est l'unité
        else:
            chiffre = _CHIFFRES_ZH[c]
    if chiffre and dernier_mult >= 100:  # 一千五 = 1500, 三百五 = 350 (le chiffre seul vaut l'unité d'en dessous)
        chiffre *= dernier_mult // 10
    valeur = total + section + chiffre
    return f"{valeur}." + "".join(str(_CHIFFRES_ZH[c]) for c in decimales) if decimales else str(valeur)


def _chiffre_par_chiffre(m: re.Match) -> str:
    """Après « virgule » : « zero cinq » → « 05 » (si ce ne sont que des chiffres de 0 à 9)."""
    mots = m.group(2).split()
    if all(_MOTS_NOMBRES.get(x, 99) <= 9 for x in mots):
        return f"{m.group(1)} " + "".join(str(_MOTS_NOMBRES[x]) for x in mots) + " "
    return m.group(0)


def nombres_en_chiffres(texte: str) -> str:
    """« cinq mètres » → « 5 metres », « zéro virgule zéro cinq » → « 0.05 », « 5,000 » → « 5000 », « 五米半 » → « 5.5米 ».
    Texte rendu sans accents, en minuscules."""
    # « a meter » / « an » (anglais) devant une unité = 1 ; lu AVANT d'ôter les accents (« à mètre près » n'est pas « a »).
    t = re.sub(r"(?<!half )(?<!and )(?<![\w])(?:a|an)\s+(?=(?:meter|metre|newton|kilomet|centimet)\w*)", "1 ", texte.lower())
    t = _sans_accents(t).replace("ß", "ss")
    t = _MILLIERS.sub(lambda m: m.group(1) + re.sub(r"\D", "", m.group(2)), t)
    t = re.sub(r"quatre[- ]vingts?", "huitante", t)
    t = re.sub(r"(?<![\w])anderthalb(?![\w])", "1.5", t)
    # « un demi-mètre », « half a meter », « einen halben Meter », « mezzo metro », « 半米 »
    t = re.sub(r"(?<![\w])(?:(?:un |une )?demi[- ]?|(?<!and a )half (?:an? )?|(?:einen? |ein )?halben? |mezzo )" + _UNITE_DEMI,
               r"0.5 \1", t)
    t = re.sub(r"半(米|公里)", r"0.5\1", t)
    # « en une demi-seconde », « in half a second », « in einer halben Sekunde », « in mezzo secondo », « 半秒 »
    t = re.sub(r"(?<![\w])(?:(?:une |un )?demi[- ]?|half (?:a )?|(?:einer |einen |eine )?halben? |mezzo )(seconde|second|sekunde|secondo)",
               r"0.5 \1", t)
    t = t.replace("半秒", "0.5秒")
    # mots composés : « funfundzwanzig », « zweieinhalb », « duecento », « venticinque »
    def composer(m: re.Match) -> str:
        mot = m.group(0)
        if mot in _MOTS_NOMBRES or len(mot) < 5:
            return mot
        if mot.endswith("einhalb") and (avant := _decouper(mot[:-7]) or ([mot[:-7]] if mot[:-7] in _MOTS_NOMBRES else None)):
            return f"{_valeur_suite(avant)}.5"
        parts = _decouper(mot)
        return str(_valeur_suite(parts)) if parts else mot
    t = re.sub(r"[a-z]+", composer, t)
    # Après « virgule », chiffre par chiffre : « zéro virgule zéro cinq » = 0,05 (et non 0,5).
    t = re.sub(r"((?:virgule|komma|koma|point|virgola))\s+((?:(?:zero|null|uno|un|une|eins|one|due|deux|zwei|two|trois|drei|"
               r"three|tre|quatre|vier|four|quattro|cinq|funf|five|cinque|six|sechs|sei|sept|sieben|seven|sette|huit|acht|"
               r"eight|otto|neuf|neun|nine|nove)(?:\s+|$))+)", _chiffre_par_chiffre, t)
    t = _SUITE_DE_NOMBRES.sub(lambda m: str(_valeur_suite([x for x in re.split(r"[\s-]+", m.group(0))
                                                           if x not in ("et", "and", "und", "e")])), t)
    t = re.sub(r"(\d+)\s+(?:" + "|".join(_MOTS_VIRGULE) + r")\s+(\d+)", r"\1.\2", t)
    t = _NOMBRE_ZH.sub(lambda m: _valeur_zh(m.group(0)), t)
    # « deux mètres et demi », « 5 metri e mezzo », « two and a half meters », « 5米半 »
    t = re.sub(r"(\d+(?:[.,]\d+)?)\s*" + _UNITE_DEMI + r"\s*(?:et demi|e mezzo|and a half|und ein halb|半)",
               lambda m: f"{_nombre(m.group(1)) + 0.5:g} {m.group(2)}", t)
    t = re.sub(r"(\d+)\s+(?:et demi|e mezzo|and a half|und ein halb)\s+" + _UNITE_DEMI,
               lambda m: f"{int(m.group(1)) + 0.5:g} {m.group(2)}", t)
    return t


def chiffre_vague(texte: str) -> bool:
    """« plus de 5 mètres », « at least 2 m »… : le chiffre dit n'est pas sûr → poser une question."""
    return bool(_CHIFFRE_VAGUE.search(nombres_en_chiffres(texte)))


def _sans_accents(texte: str) -> str:
    t = unicodedata.normalize("NFKD", texte.lower().replace("’", "'"))
    return "".join(c for c in t if not unicodedata.combining(c))


def _nombre(x: str) -> float:
    return float(x.replace(",", "."))


def _vitesses(t: str) -> list[float]:
    res = []
    for motif, diviseur in _VITESSES:
        res += [round(_nombre(m.group(1)) / diviseur, 3) for m in motif.finditer(t)]
    for m in _EN_N_SECONDES.finditer(t):
        duree = _nombre(m.group(2))
        if duree > 0:
            res.append(round(_nombre(m.group(1)) / duree, 3))
    return res


def _sans_vitesses(t: str) -> str:
    for motif, _ in _VITESSES:
        t = motif.sub(" ", t)
    return t


def lire_vitesse(texte: str) -> float | None:
    """La vitesse en m/s si la phrase en contient une (la plus grande s'il y en a plusieurs), sinon None."""
    v = _vitesses(nombres_en_chiffres(texte))
    return max(v) if v else None


def lire_force(texte: str) -> float | None:
    """Une force dite (« 100 newtons », « 50 N », « cent newtons ») ; la plus grande s'il y en a plusieurs ; sinon None."""
    f = [_nombre(m.group(1)) for m in _FORCE.finditer(nombres_en_chiffres(texte))]
    return max(f) if f else None


def distances_dites(texte: str) -> list[float]:
    """Chaque distance dite (« 20 mètres », « 1 m 50 », « 一米八 », « 2 km »), en mètres. Les vitesses sont d'abord
    retirées du texte : « 2 m par seconde », « 50 cm/s » ne sont jamais des distances."""
    t = _sans_vitesses(nombres_en_chiffres(texte))
    res = []
    for m in _DISTANCE.finditer(t):
        d, unite, reste = _nombre(m.group(1)), m.group(2), m.group(3)
        if reste:  # « 1 m 50 » = 1,50 m ; « 一米八 » = 1,8 m
            d += int(reste) / (10 if len(reste) == 1 else 100)
        if re.fullmatch(_UNITE_CM, unite):
            d /= 100
        elif re.fullmatch(_UNITE_KM, unite):
            d *= 1000
        res.append(round(d, 3))
    return res


def lire_distance(texte: str) -> float | None:
    """La distance dite, en mètres. Plusieurs distances : la somme (« 4 mètres puis 10 mètres » = 14 m parcourus)."""
    d = distances_dites(texte)
    return round(sum(d), 3) if d else None


# Le sens d'un déplacement relatif. dy > 0 = à gauche du robot. Règle STRICTE (relecture du lot A) : le robot ne va sur
# le côté ou en arrière que pour une tournure CLAIRE (« à gauche », « nach links », « 2 Meter links », « go left »,
# « 往左 », « recule »…). Un mot de côté ou d'arrière qui reste ailleurs dans la phrase (« ligne droite », « you're right »,
# « I left my bag », « back straight », « main droite ») → une question. Jamais deviné. Textes sans accents (normaliser).
_N = r"\d+(?:[.,]\d+)?\s*(?:m|mt|metres?|meters?|meter|metern|metri|metro)"
_CLAIRS = {
    "avant": [r"avance", r"avancer", r"en avant", r"tout droit", r"vorwarts", r"nach vorne", r"geradeaus", r"vor",
              r"fure", r"avanti", r"avanza", r"in avanti", r"dritto", r"forward", r"forwards", r"ahead", r"straight ahead",
              r"往前", r"向前", r"前进", r"朝前"],
    "reculer": [r"recule", r"reculer", r"en arriere", r"vers l arriere", r"a reculons", r"zuruck", r"ruckwarts",
                r"nach hinten", r"zrugg", r"hindere", _N + r" retour", r"indietro", r"all indietro", r"arretra",
                r"go back", r"move back", r"step back", r"backwards", r"backward", r"behind you",
                r"后退", r"往后", r"向后", r"朝后", r"倒退", r"退后"],
    "gauche": [r"a gauche", r"vers la gauche", r"sur la gauche", r"a votre gauche", r"a ta gauche", r"nach links",
               _N + r" (?:nach )?links", _N + r" linggs", r"a sinistra", r"verso sinistra", r"sulla sinistra",
               r"alla tua sinistra", r"to the left", r"to your left", r"(?:go|move|step|walk) left",
               r"向左", r"往左", r"朝左"],
    "droite": [r"a droite", r"vers la droite", r"sur la droite", r"a votre droite", r"a ta droite", r"nach rechts",
               _N + r" (?:nach )?rechts", r"a destra", r"verso destra", r"sulla destra", r"alla tua destra",
               r"to the right", r"to your right", r"(?:go|move|step|walk) right",
               r"向右", r"往右", r"朝右"],
}
# Un de ces mots qui reste après avoir ôté les tournures claires : on ne sait pas → question.
_AMBIGUS = [r"gauche", r"droite", r"arriere", r"derriere", r"reculons", r"cote", r"links", r"linggs", r"rechts", r"hinten",
            r"seite", r"seitlich", r"seitwarts", r"siite", r"retour", r"sinistra", r"destra", r"dietro", r"lato", r"left",
            r"right", r"back", r"behind", r"side", r"sideways", r"aside", r"reverse", r"左", r"右", r"后", r"旁边", r"侧"]
_PAS_UN_SENS_ZH = re.compile(r"左右|然后|之后|以后|后来|最后")  # « environ », « puis », « après » : pas des sens
def _motif(mots: list[str]) -> re.Pattern:
    """Les mots latins entre limites de mot ; les mots chinois tels quels (en Python, 走 compte comme une lettre)."""
    latins = [m for m in mots if not _CJK.search(m)]
    chinois = [m for m in mots if _CJK.search(m)]
    parts = ([r"(?<![\w])(?:" + "|".join(latins) + r")(?![\w])"] if latins else []) + chinois
    return re.compile("|".join(parts))


_REGEX_CLAIRS = {sens: _motif(motifs) for sens, motifs in _CLAIRS.items()}
_REGEX_AMBIGUS = _motif(_AMBIGUS)


_SEPARATEURS = re.compile(r"[,;.!?:，。；：]|(?<![\w])(?:puis|ensuite|then|and|und|dann|poi|e poi|und dann|danach)(?![\w])|然后")


def morceau_du_deplacement(texte: str) -> str:
    """Le morceau de phrase (entre virgules, « puis », « and »…) qui contient la distance ou « un peu »."""
    morceaux = [m for m in _SEPARATEURS.split(texte) if m and m.strip()]
    for m in morceaux:
        if distances_dites(m) or petit_deplacement_demande(m):
            return m
    return texte


def sens_dits(texte: str) -> set[str]:
    """Les sens nommés clairement (avant, reculer, gauche, droite) ; « doute » s'il reste un mot de côté ou d'arrière
    qui n'est pas dans une tournure claire (on posera une question)."""
    t = normaliser(_PAS_UN_SENS_ZH.sub(" ", nombres_en_chiffres(texte)))
    trouves: set[str] = set()
    for sens, motif in _REGEX_CLAIRS.items():
        if motif.search(t):
            trouves.add(sens)
            t = motif.sub(" ", t)
    if _REGEX_AMBIGUS.search(t):
        trouves.add("doute")
    return trouves


_REPETITION = re.compile(r"\d+\s*(?:fois|times|mal|volte|次)|(?<![\w])(?:twice|thrice|zweimal|dreimal|viermal|nochmal|"
                         r"encore une fois|once more|ancora una volta)(?![\w])")


def repetition_dite(texte: str) -> bool:
    """« Avance de 2 mètres, trois fois » : on ne multiplie pas en devinant → question."""
    return bool(_REPETITION.search(nombres_en_chiffres(texte)))


PETIT_DEPLACEMENT = {"fr": ["un peu", "un petit peu"], "de": ["ein bisschen", "ein stück", "etwas"], "gsw": ["es bitzeli", "chli"],
                     "it": ["un po'", "un poco"], "en": ["a little", "a bit"], "zh": ["一点", "一下"]}


def petit_deplacement_demande(texte: str) -> bool:
    """« Avance un peu » : un petit pas est demandé, sans chiffre."""
    t = normaliser(texte.replace("’", "'"))
    return any(contient(t, m) for mots in PETIT_DEPLACEMENT.values() for m in mots)


class CerveauRegles(Cerveau):
    nom = "regles"

    async def decider(self, texte: str, langue: str | None, carte: CarteIdentite, monde: Monde) -> Decision:
        d = self._comprendre(texte, langue, carte, monde)
        d.cerveau = self.nom
        return garde_fou_carte(d, carte)

    # ------------------------------------------------------------------
    def _comprendre(self, texte: str, langue: str | None, carte: CarteIdentite, monde: Monde) -> Decision:
        t = normaliser(texte)
        lex = _lexique()
        votes: dict[str, int] = {}

        def trouve(table: dict[str, list[str]]) -> bool:
            ok = False
            for lg, mots in table.items():
                if any(contient(t, m) for m in mots):
                    votes[lg] = votes.get(lg, 0) + 1
                    ok = True
            return ok

        verbes = [a for a, table in lex["verbes"].items() if trouve(table)]
        gestes = [g for g, table in lex["gestes"].items() if trouve(table)]
        lieux = [l.id for l in monde.lieux if trouve(l.noms)]
        objets = [o.id for o in monde.objets if trouve(o.noms)]
        langue_devinee = "zh" if _CJK.search(texte) else (max(votes, key=votes.get) if votes else None)
        base = dict(langue_devinee=langue_devinee)

        # 1. S'arrêter passe avant tout le reste.
        if "arreter" in verbes:
            return Decision(genre="action", action=ActionDemandee(nom="arreter"), confiance=1.0, **base)

        # 2. Un geste nommé.
        if gestes and not verbes:
            if len(gestes) > 1:
                opts = [ActionDemandee(nom="rejouer_geste", parametres={"nom": g}) for g in gestes]
                return Decision(genre="question", question="question_choix", options=opts, confiance=0.4, **base)
            return Decision(genre="action", action=ActionDemandee(nom="rejouer_geste", parametres={"nom": gestes[0]}),
                            confiance=0.8, **base)

        if not verbes:
            return Decision(genre="inconnu", confiance=0.0, **base)

        # 3. Plusieurs actions possibles : on demande au lieu de deviner.
        if len(verbes) > 1:
            opts = [ActionDemandee(nom=v) for v in verbes]
            return Decision(genre="question", question="question_choix", options=opts, confiance=0.3, **base)

        verbe = verbes[0]
        if verbe in ("etat", "ecouter"):
            return Decision(genre="action", action=ActionDemandee(nom=verbe), confiance=0.9, **base)

        if verbe == "se_deplacer":
            vitesse = lire_vitesse(texte)
            if lieux and (distances_dites(texte) or sens_dits(texte) - {"avant"}):  # « doute » compte aussi
                # « Avance de 2 mètres, la porte est à droite » : un lieu ET une distance ou un côté → on demande.
                return Decision(genre="question", question="question_sens", confiance=0.3, **base)
            if len(lieux) == 1:
                p = {"lieu": lieux[0], **({"vitesse": vitesse} if vitesse is not None else {})}
                return Decision(genre="action", action=ActionDemandee(nom=verbe, parametres=p), confiance=0.9, **base)
            if len(lieux) > 1:
                opts = [ActionDemandee(nom=verbe, parametres={"lieu": l}) for l in lieux]
                return Decision(genre="question", question="question_choix", options=opts, confiance=0.4, **base)
            # Pas de lieu, mais une distance dite (« avance de 2 mètres », « recule un peu ») : un déplacement relatif.
            # Deux sens, deux distances ou un chiffre vague (« plus de 5 m ») : on demande au lieu de deviner.
            dites, sens = distances_dites(texte), sens_dits(texte)
            petit = petit_deplacement_demande(texte)
            if (dites or petit) and (sens - {"avant"}) - sens_dits(morceau_du_deplacement(texte)):
                # « Go 2 meters, the exit is to the left » : le côté est dit dans une AUTRE partie de la phrase.
                sens = sens | {"doute"}
            if (dites or petit) and chiffre_vague(texte):
                return Decision(genre="question", question="question_chiffre", confiance=0.3, **base)
            if (dites or petit) and (len(dites) > 1 or "doute" in sens or len(sens) > 1 or repetition_dite(texte)):
                return Decision(genre="question", question="question_sens", confiance=0.3, **base)
            d = dites[0] if dites else (0.5 if petit else None)
            if d is not None:
                dx, dy = d, 0.0
                if "reculer" in sens:
                    dx = -d
                elif "gauche" in sens:
                    dx, dy = 0.0, d
                elif "droite" in sens:
                    dx, dy = 0.0, -d
                p = {"dx": dx, "dy": dy, **({"vitesse": vitesse} if vitesse is not None else {})}
                return Decision(genre="action", action=ActionDemandee(nom=verbe, parametres=p), confiance=0.8, **base)
            return self._question_ou_hors_carte(verbe, "question_lieu", carte, base)

        if verbe == "saisir":
            if len(objets) == 1:
                return Decision(genre="action", action=ActionDemandee(nom=verbe, parametres={"objet": objets[0]}),
                                confiance=0.9, **base)
            if len(objets) > 1:
                opts = [ActionDemandee(nom=verbe, parametres={"objet": o}) for o in objets]
                return Decision(genre="question", question="question_choix", options=opts, confiance=0.4, **base)
            return self._question_ou_hors_carte(verbe, "question_objet", carte, base)

        if verbe == "poser":
            if len(lieux) > 1:
                opts = [ActionDemandee(nom=verbe, parametres={"lieu": l}) for l in lieux]
                return Decision(genre="question", question="question_choix", options=opts, confiance=0.4, **base)
            lieu = lieux[0] if lieux else "ici"
            return Decision(genre="action", action=ActionDemandee(nom=verbe, parametres={"lieu": lieu}), confiance=0.8, **base)

        if verbe in ("regarder", "montrer"):
            cibles = lieux + objets
            if len(cibles) > 1:
                opts = [ActionDemandee(nom=verbe, parametres={"cible": c}) for c in cibles]
                return Decision(genre="question", question="question_choix", options=opts, confiance=0.4, **base)
            cible = cibles[0] if cibles else lex.get("cible_defaut", "devant")
            return Decision(genre="action", action=ActionDemandee(nom=verbe, parametres={"cible": cible}), confiance=0.8, **base)

        return Decision(genre="inconnu", confiance=0.0, **base)

    @staticmethod
    def _question_ou_hors_carte(verbe: str, question: str, carte: CarteIdentite, base: dict) -> Decision:
        if not carte.sait(verbe):  # inutile de demander « où ? » à un robot qui ne marche pas
            return Decision(genre="hors_carte", action_hors_carte=verbe, confiance=0.7, **base)
        return Decision(genre="question", question=question, confiance=0.3, **base)
