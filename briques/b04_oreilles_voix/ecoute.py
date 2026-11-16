"""Brique 4 — L'écoute : transformer la parole en texte, et reconnaître la langue.

Une seule forme (`Ecoute.transcrire`), plusieurs moteurs (voir branchements/) :
- faster_whisper : sur le processeur (Linux, Mac). Testé ici.
- mlx_whisper : sur la puce Apple (Mac seulement). Non testé.
- whisper_cpp : whisper.cpp avec la puce graphique Apple (Mac). Non testé.
On garde le plus rapide mesuré sur le Mac (`preparer_mac.sh`), l'autre reste branché.
"""
from __future__ import annotations

import math
import time
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path

import numpy as np
import yaml
from pydantic import BaseModel, Field

from commun.phrases import langues

ICI = Path(__file__).parent


class Transcription(BaseModel):
    texte: str
    langue: str  # notre code de langue (fr, de, gsw, it, en, zh)
    langue_proba: float  # 0 à 1 : sûreté sur la langue
    confiance: float  # 0 à 1 : sûreté sur les mots
    duree_son_s: float
    duree_calcul_ms: float
    langue_moteur: str = ""  # ce que le moteur a vraiment dit (ex. « de » pour du suisse allemand)
    probas_langues: dict[str, float] = Field(default_factory=dict)
    langue_verifiee: bool = True  # False : langue supposée (celle de la personne précédente), non mesurée
    moteur: str = ""


def langues_ecoute() -> dict[str, str]:
    """{code_moteur: notre_code} pour les langues qu'on accepte (gsw est écouté comme « de »)."""
    table = {}
    for code, info in langues()["langues"].items():
        table.setdefault(info.get("code_ecoute", code), code)
    return table


@lru_cache(maxsize=1)
def mots_du_pays() -> list[str]:
    return yaml.safe_load((ICI / "mots_du_pays.yaml").read_text(encoding="utf-8"))["mots"]


@lru_cache(maxsize=1)
def marqueurs_suisse_allemand() -> set[str]:
    return set(yaml.safe_load((ICI / "mots_du_pays.yaml").read_text(encoding="utf-8"))["suisse_allemand"])


SEUIL_LANGUE_GARDEE = 0.75  # langue de la personne précédente : acceptée seulement si l'écoute est très sûre
DUREE_ORDRE_COURT_S = 4.0  # en dessous : sans doute un ordre au robot → on aide l'écoute avec le vocabulaire du robot


@lru_cache(maxsize=16)
def vocabulaire_commandes(langue_moteur: str) -> str:
    """Quelques ordres d'exemple dans la langue (verbes du robot × lieux et objets du monde), plus les mots du pays.
    Donnés à l'écoute comme « contexte » : les ordres courts sont bien mieux compris (mesuré dans le banc d'essai)."""
    from briques.b06_cerveau.branchements.regles import _lexique
    from commun.monde import Monde

    nos_codes = [c for c, i in langues()["langues"].items() if i.get("code_ecoute", c) == langue_moteur]
    if not nos_codes:
        return ", ".join(mots_du_pays())
    monde, lex = Monde.charger(), _lexique()

    def premier(table: dict, lg: str) -> str | None:
        mots = table.get(lg) or []
        return mots[0] if mots else None

    phrases, mots = [], []
    for lg in nos_codes[:1] if langue_moteur == "de" else nos_codes:  # allemand : exemples en allemand standard seulement
        sep = "" if lg == "zh" else " "
        fin = "。" if lg == "zh" else "."
        verbes = {a: (lex["verbes"][a].get(lg) or [])[:2] for a in lex["verbes"]}
        v_aller, v_prendre = (verbes["se_deplacer"] or [None])[0], (verbes["saisir"] or [None])[0]
        v_voir, v_montrer = (verbes["regarder"] or [None])[0], (verbes["montrer"] or [None])[0]
        v_poser = (verbes["poser"] or [None])[0]
        lieux = [l.noms[lg][0] for l in monde.lieux if l.noms.get(lg)]
        objets = [o.noms[lg][0] for o in monde.objets if o.noms.get(lg) and o.id != "objet_test"]
        for lieu in lieux:
            if v_aller:
                phrases.append(f"{v_aller}{sep}{lieu}{fin}")
        for objet in objets:
            if v_prendre:
                phrases.append(f"{v_prendre}{sep}{objet}{fin}")
        for v, cible in ((v_voir, lieux[:2]), (v_montrer, lieux[2:3]), (v_poser, lieux[2:3])):
            if v and cible:
                phrases.append(f"{v}{sep}{cible[0]}{fin}")
        # Tous les mots attendus : verbes de chaque action, gestes.
        mots += [m for liste in verbes.values() for m in liste]
        mots += [m for g in lex["gestes"].values() for m in (g.get(lg) or [])[:1]]
    # Whisper ne garde que la FIN d'un long contexte (environ 220 morceaux de mots) : la liste des mots d'abord,
    # les phrases d'exemple à la fin ; et pas plus de 900 caractères.
    texte = ", ".join(dict.fromkeys(mots_du_pays() + mots)) + ". " + " ".join(dict.fromkeys(phrases))
    return texte[-900:]


def choisir_langue(probas: dict[str, float], forcee: str | None = None) -> tuple[str, float, str]:
    """Garde la langue la plus probable PARMI celles qu'on sait traiter. Rend (code moteur, proba, notre code)."""
    autorisees = langues_ecoute()
    if forcee:
        code_moteur = langues()["langues"].get(forcee, {}).get("code_ecoute", forcee)
        return code_moteur, 1.0, forcee
    candidates = {l: p for l, p in probas.items() if l in autorisees}
    if not candidates:
        defaut = langues()["defaut"]
        return defaut, 0.0, defaut
    total = sum(candidates.values()) or 1.0
    meilleure = max(candidates, key=candidates.get)
    return meilleure, candidates[meilleure] / total, autorisees[meilleure]


def suisse_allemand_probable(texte: str) -> bool:
    """Whisper écoute le suisse allemand comme de l'allemand. Certains mots le trahissent (« Chuchi », « isch »…).
    Limite : Whisper « traduit » souvent en allemand standard, et ces mots disparaissent. À mesurer avec de vraies voix."""
    import re

    mots = set(re.findall(r"\w+", texte.lower()))
    return len(mots & marqueurs_suisse_allemand()) >= 1


TRADITIONNELS = set("這個們來說時會對過還為與開點廚門東機器讓嗎麼給從經應進動關見長間後種國學現頭電話實體發問題書車馬魚鳥樂聽寫號買賣錢飯館場處帶邊戰歲隻張條")


def caracteres_traditionnels(texte: str) -> bool:
    return any(c in TRADITIONNELS for c in texte)


def confiance_depuis(logprobs_moyens: list[float], sans_parole: list[float]) -> float:
    """Sûreté sur les mots, de 0 à 1, à partir de ce que dit Whisper pour chaque morceau de phrase."""
    if not logprobs_moyens:
        return 0.0
    c = math.exp(float(np.mean(logprobs_moyens)))
    return round(max(0.0, min(1.0, c * (1 - max(sans_parole or [0.0])))), 3)


class Ecoute(ABC):
    nom = "ecoute"

    @abstractmethod
    def _transcrire(self, son: np.ndarray, langue_moteur: str | None, mots: list[str],
                    contexte: str | None = None) -> tuple[str, str, dict[str, float], float]:
        """Rend (texte, langue moteur, probas des langues, confiance). `contexte` : phrases d'exemple pour aider."""

    def prechauffer(self) -> None:
        """Un premier passage à vide : le premier vrai passage est ensuite à pleine vitesse."""
        self.transcrire(np.zeros(16000, dtype="float32"))

    def _detecter(self, son: np.ndarray) -> dict[str, float]:
        """Probabilités des langues, sans écrire le texte (plus rapide). Par défaut : un passage complet."""
        return self._transcrire(son, None, [])[2]

    def transcrire(self, son: np.ndarray, langue: str | None = None, langue_probable: str | None = None) -> Transcription:
        """`langue` : imposée. `langue_probable` : celle de la personne qui vient de parler (on essaie d'abord celle-là)."""
        t0 = time.perf_counter()
        court = len(son) / 16000 < DUREE_ORDRE_COURT_S
        verifiee = True
        if langue:
            code_moteur, proba, notre = choisir_langue({}, langue)
            texte, lm, probas, confiance = self._passage(son, code_moteur, court)
        elif court:
            texte = ""
            confiance, probas = 0.0, {}
            verifiee = True
            if langue_probable:
                # Même personne, même langue (le plus souvent) : un seul passage. Accepté seulement si très sûr.
                code_moteur, _, notre = choisir_langue({}, langue_probable)
                texte, lm, _, confiance = self._passage(son, code_moteur, True)
                proba, verifiee = confiance, False
            if not texte or confiance < SEUIL_LANGUE_GARDEE:
                verifiee = True
                # Ordre court : on reconnaît d'abord la langue (rapide), puis on écoute avec le vocabulaire du robot.
                probas = self._detecter(son)
                code_moteur, proba, notre = choisir_langue(probas)
                texte, lm, _, confiance = self._passage(son, code_moteur, True)
        else:
            texte, lm, probas, confiance = self._transcrire(son, None, mots_du_pays())
            code_moteur, proba, notre = choisir_langue(probas or {lm: 1.0})
            if lm not in langues_ecoute():  # langue hors de notre liste : on refait dans la meilleure langue permise
                texte, lm, _, confiance = self._passage(son, code_moteur, False)
        if notre == "zh" and caracteres_traditionnels(texte):
            # Whisper écrit parfois le chinois en caractères traditionnels : on redemande en caractères simplifiés.
            texte, lm, _, confiance = self._transcrire(son, "zh", [], contexte="以下是普通话的句子。" + vocabulaire_commandes("zh"))
        if notre == "de" and langue != "de" and suisse_allemand_probable(texte):
            notre = "gsw"
        return Transcription(texte=texte.strip(), langue=notre, langue_proba=round(proba, 3), confiance=confiance,
                             duree_son_s=round(len(son) / 16000, 2), duree_calcul_ms=round((time.perf_counter() - t0) * 1000, 1),
                             langue_moteur=lm, probas_langues={k: round(v, 3) for k, v in sorted(
                                 (probas or {}).items(), key=lambda kv: -kv[1])[:5]}, moteur=self.nom,
                             langue_verifiee=verifiee)

    def _passage(self, son: np.ndarray, code_moteur: str, court: bool):
        if court:
            return self._transcrire(son, code_moteur, [], contexte=vocabulaire_commandes(code_moteur))
        return self._transcrire(son, code_moteur, mots_du_pays())

    def detecter_langue(self, son: np.ndarray) -> tuple[str, float]:
        """« Deux mots suffisent » : la langue à partir d'un court début de phrase."""
        _, _, probas, _ = self._transcrire(son, None, [])
        _, proba, notre = choisir_langue(probas)
        return notre, proba


def moteur_auto() -> str:
    """Sur Mac à puce Apple : mlx-whisper s'il est installé, sinon whisper.cpp. Ailleurs : faster-whisper."""
    import importlib.util
    import platform
    import sys

    if sys.platform == "darwin" and platform.machine() == "arm64":
        for moteur, paquet in (("mlx_whisper", "mlx_whisper"), ("whisper_cpp", "pywhispercpp")):
            if importlib.util.find_spec(paquet):
                return moteur
    return "faster_whisper"


def creer_ecoute(reglages: dict) -> Ecoute:
    r = reglages.get("voix", {}).get("ecoute", {})
    moteur = r.get("moteur", "auto")
    if moteur == "auto":
        moteur = moteur_auto()
    modele = r.get("modele", "small")
    if moteur == "faster_whisper":
        from .branchements.ecoute_faster_whisper import EcouteFasterWhisper

        return EcouteFasterWhisper(modele)
    if moteur == "mlx_whisper":
        from .branchements.ecoute_mlx_whisper import EcouteMlxWhisper

        return EcouteMlxWhisper(modele)
    if moteur == "whisper_cpp":
        from .branchements.ecoute_whisper_cpp import EcouteWhisperCpp

        return EcouteWhisperCpp(modele)
    raise ValueError(f"Moteur d'écoute inconnu : {moteur}")
