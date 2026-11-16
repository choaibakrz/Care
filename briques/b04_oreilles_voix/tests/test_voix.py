"""Brique 4 — oreilles et voix. Internet coupé (conftest.py). Testé sur faux robot, sur Linux, processeur seul.

Sons utilisés : vraies voix FLEURS (donnees_voix/fleurs) et phrases chinoises SYNTHÉTIQUES (voix chaowen).
La voix synthétique prononce mal certains mots (« 机器人 » en début de phrase, « 去 » seul) : les phrases d'essai
ont été choisies pour être bien prononcées. Les vraies voix de l'équipe seront mesurées au banc d'essai.
Les tests sautent proprement si un modèle n'est pas téléchargé (outils/telecharger.py).
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import numpy as np
import pytest

from conftest import lancer

RACINE = Path(__file__).resolve().parents[3]
FLEURS = RACINE / "donnees_voix" / "fleurs"
besoin_whisper = pytest.mark.skipif(not (RACINE / "modeles/whisper-base-fw").exists(), reason="whisper base absent")
besoin_voix_zh = pytest.mark.skipif(not (RACINE / "modeles/voix-zh-sherpa").exists(), reason="voix chinoise absente")


@pytest.fixture(scope="module")
def ecoute():
    if not (RACINE / "modeles/whisper-base-fw").exists():
        pytest.skip("whisper base absent")
    from briques.b04_oreilles_voix.branchements.ecoute_faster_whisper import EcouteFasterWhisper

    return EcouteFasterWhisper("base")


@pytest.fixture(scope="module")
def voix_zh():
    if not (RACINE / "modeles/voix-zh-sherpa").exists():
        pytest.skip("voix chinoise absente")
    from briques.b04_oreilles_voix.branchements.voix_sherpa_piper import VoixSherpaPiper

    return VoixSherpaPiper()


def _fleurs(langue: str, i: int = 0):
    from briques.b04_oreilles_voix.audio import lire

    meta = json.loads((FLEURS / langue / "textes.json").read_text(encoding="utf-8"))[i]
    return lire(FLEURS / langue / meta["fichier"]), meta["texte"]


FIGEES = {"请去厨房。": "aller_cuisine", "请看桌子。": "regarder_table", "停下。": "stop", "你好机器人，请去门口。": "appel_porte"}


def _dire_zh(voix_zh, texte: str) -> np.ndarray:
    """Phrase chinoise SYNTHÉTIQUE : prise dans donnees_voix/synthetique_zh si elle y est (même son à chaque fois)."""
    from briques.b04_oreilles_voix.audio import lire, reechantillonner

    if texte in FIGEES:
        return lire(RACINE / "donnees_voix" / "synthetique_zh" / f"{FIGEES[texte]}.wav")
    son = voix_zh.synthetiser(texte, "zh")
    return reechantillonner(son.echantillons, son.taux, 16000)


# ------------------------------------------------------------------ fin de parole
def test_fin_de_parole_une_phrase_un_enonce():
    from briques.b04_oreilles_voix.audio import silence
    from briques.b04_oreilles_voix.fin_de_parole import DetecteurParole

    son, _ = _fleurs("fr")
    d = DetecteurParole(silence_fin_ms=600)
    enonces = d.ajouter(np.concatenate([silence(1000), son, silence(1500)]))
    assert len(enonces) >= 1
    e = enonces[-1]
    assert abs((e.detection_s - e.fin_parole_s) - 0.6) < 0.1  # on attend 600 ms de silence, pas plus
    assert sum(len(x.son) for x in enonces) / 16000 > 0.7 * len(son) / 16000  # presque toute la voix est gardée


def test_le_silence_ne_declenche_rien():
    from briques.b04_oreilles_voix.audio import silence
    from briques.b04_oreilles_voix.fin_de_parole import DetecteurParole

    assert DetecteurParole().ajouter(silence(3000) + 0.001 * np.random.default_rng(0).standard_normal(48000).astype("float32")) == []


# ------------------------------------------------------------------ écoute
@pytest.mark.parametrize("langue", ["fr", "de", "it", "en", "zh"])
def test_la_langue_est_reconnue_sur_de_vraies_voix(ecoute, langue):
    son, _ = _fleurs(langue, 1)
    t = ecoute.transcrire(son)
    assert t.langue == langue and t.langue_proba > 0.5 and t.texte


def test_suisse_allemand_repere_par_ses_mots():
    from briques.b04_oreilles_voix.ecoute import suisse_allemand_probable

    assert suisse_allemand_probable("Gang i d'Chuchi und nimm d'Fläsche")
    assert not suisse_allemand_probable("Geh in die Küche und nimm die Flasche")


# ------------------------------------------------------------------ voix
@besoin_voix_zh
def test_voix_chinoise_et_cascade_vers_les_sous_titres(voix_zh):
    from briques.b04_oreilles_voix.voix import VoixEnCascade

    son = voix_zh.synthetiser("我去厨房。", "zh")
    assert son.duree_s > 0.5 and son.duree_calcul_ms < 2000
    cascade = VoixEnCascade([voix_zh])
    assert cascade.synthetiser("Je vais à la cuisine.", "fr") is None  # pas de voix française : sous-titres


# ------------------------------------------------------------------ conversation complète (son → robot → réponse)
async def _attendre(s, type_: str, delai_s: float = 20.0, condition=lambda e: True):
    for _ in range(int(delai_s / 0.05)):
        if any(e.type == type_ and condition(e) for e in s.bus.historique):
            return True
        await asyncio.sleep(0.05)
    return False


def _conversation(fabrique_systeme, ecoute, voix, **reglages):
    from briques.b04_oreilles_voix.conversation import Conversation
    from briques.b04_oreilles_voix.peripheriques import HautParleurFactice

    s = fabrique_systeme()
    hp = HautParleurFactice(vitesse=reglages.pop("vitesse_hp", 4.0))
    c = Conversation(s, ecoute, voix, hp, {**s.reglages.get("voix", {}), **reglages}, vitesse_micro=reglages.pop("vitesse", 4.0))
    return s, c, hp


@besoin_voix_zh
def test_parler_au_robot_avec_la_voix_il_agit_et_repond(fabrique_systeme, ecoute, voix_zh):
    from briques.b04_oreilles_voix.audio import silence
    from briques.b04_oreilles_voix.peripheriques import MicroFichier

    async def go():
        s, c, hp = _conversation(fabrique_systeme, ecoute, voix_zh)
        await s.demarrer()
        await c.ecouter(MicroFichier(np.concatenate([silence(500), _dire_zh(voix_zh, "请去厨房。")]), vitesse=4.0))
        await _attendre(s, "action_terminee")
        await c.attendre_calme()
        c.fermer()
        await s.arreter()
        return s, hp

    s, hp = lancer(go())
    types = [e.type for e in s.bus.historique]
    for t in ("parole_finie", "transcription", "demande_comprise", "action_terminee", "voix_debut"):
        assert t in types, t
    fin = [e for e in s.bus.historique if e.type == "action_terminee"][-1]
    assert fin.donnees["action"]["nom"] == "se_deplacer" and fin.donnees["action"]["parametres"]["lieu"] == "cuisine"
    voix = [e for e in s.bus.historique if e.type == "voix_debut"]
    assert voix[0].donnees["langue"] == "zh" and voix[0].donnees["latence_ms"] is not None
    assert hp.joues, "le robot a parlé"


@besoin_voix_zh
def test_interruption_le_robot_se_tait_quand_on_lui_parle(fabrique_systeme, ecoute, voix_zh):
    from briques.b04_oreilles_voix.audio import silence

    async def go():
        s, c, hp = _conversation(fabrique_systeme, ecoute, voix_zh, vitesse_hp=1.0, vitesse=1.0)
        await s.demarrer()
        longue = _dire_zh(voix_zh, "这是一个很长的回答，我会说很久很久，一直说下去，直到有人打断我为止。")
        tache = asyncio.create_task(hp.jouer(longue, 16000))
        await asyncio.sleep(0.2)
        assert hp.parle
        parole = _dire_zh(voix_zh, "停下")
        for i in range(0, len(parole) - 511, 512):
            await c.recevoir(parole[i:i + 512])
            await asyncio.sleep(0.032)
        complet = await tache
        for i in range(0, 16000, 512):
            await c.recevoir(silence(32))
        await c.attendre_calme()
        c.fermer()
        await s.arreter()
        return s, complet

    s, complet = lancer(go())
    assert complet is False, "la réponse en cours a été coupée"
    assert any(e.type == "interruption" for e in s.bus.historique)


@besoin_voix_zh
def test_mot_d_appel_on_ignore_ce_qui_n_est_pas_pour_le_robot(fabrique_systeme, ecoute, voix_zh):
    from briques.b04_oreilles_voix.audio import silence
    from briques.b04_oreilles_voix.peripheriques import MicroFichier

    async def go():
        s, c, hp = _conversation(fabrique_systeme, ecoute, voix_zh, declenchement="mot_d_appel", mots_d_appel=["机器人"])
        await s.demarrer()
        son = np.concatenate([_dire_zh(voix_zh, "去厨房"), silence(1500), _dire_zh(voix_zh, "你好机器人，请去门口。")])
        await c.ecouter(MicroFichier(son, vitesse=4.0))
        await asyncio.sleep(0.5)
        await c.attendre_calme()
        c.fermer()
        await s.arreter()
        return s

    s = lancer(go())
    entendues = [e.donnees["texte"] for e in s.bus.historique if e.type == "parole_entendue"]
    assert len(entendues) == 1 and "门口" in entendues[0]  # la première phrase (sans « robot ») est ignorée
    assert any(e.type == "mot_d_appel" for e in s.bus.historique)


@besoin_voix_zh
def test_bouton_je_parle(fabrique_systeme, ecoute, voix_zh):
    async def go():
        s, c, hp = _conversation(fabrique_systeme, ecoute, voix_zh, declenchement="bouton")
        await s.demarrer()
        c.appuyer()
        son = _dire_zh(voix_zh, "请看桌子。")
        for i in range(0, len(son) - 511, 512):
            await c.recevoir(son[i:i + 512])
        c.relacher()
        await _attendre(s, "action_terminee")
        await c.attendre_calme()
        c.fermer()
        await s.arreter()
        return s

    s = lancer(go())
    assert any(e.type == "action_terminee" and e.donnees["action"]["nom"] == "regarder" for e in s.bus.historique)
