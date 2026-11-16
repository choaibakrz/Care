"""Aide au patient (appli patient) : écouter, traduire, simplifier.

- transcrire(audio)            : faster-whisper, sur cet ordinateur, langue détectée toute seule ;
- traduire(texte, vers, depuis) : Apertus (point d'accès compatible OpenAI) ;
- simplifier(texte, langue)     : Apertus, mots simples, puis contrôle des nombres ;
- parler(texte, langue)         : voix Piper lue par sherpa-onnx, WAV 16 bits en mémoire.

L'audio et les textes restent en mémoire : rien n'est écrit, rien n'est journalisé.
Appelé par le processus clinic-brain (implementation/server, crates/python-bindings).

Réglages (donnés par clinic-brain avec configurer(), sinon l'environnement) :
APERTUS_URL (http://127.0.0.1:8089), APERTUS_TIMEOUT_S (15), WHISPER_MODEL (small),
PIPER_VOICES_DIR (<dépôt>/models/voices, rempli par implementation/server/scripts/fetch_voices.py).

Voix : sherpa-onnx 2.x ne phonétise plus le texte (espeak-ng retiré). Une voix ne parle que si
elle a un lexique (lexicon.txt : le chinois chaowen). Les autres voix Piper demandent espeak-ng
(GPL-3.0), option ÉTEINTE (DECISIONS.md) : parler() dit Indisponible("voix") et l'appli lit le
texte avec la voix du navigateur.
"""

import io
import json
import os
import re
import wave
from pathlib import Path

import httpx

LANGUES = {
    "en": "English", "fr": "French", "de": "German", "it": "Italian", "es": "Spanish",
    "pt": "Portuguese", "nl": "Dutch", "ar": "Arabic", "tr": "Turkish", "zh": "Chinese",
    "ru": "Russian", "uk": "Ukrainian", "pl": "Polish", "sq": "Albanian", "sr": "Serbian",
    "hr": "Croatian", "ro": "Romanian",
}
MAX_SECONDES = 60
TAUX = 16000
MAX_PAROLE = 2000
LENTEUR = 1.1  # un peu plus lent que la voix d'origine : plus clair pour les patients

_reglages = {
    "url": os.environ.get("APERTUS_URL", "http://127.0.0.1:8089"),
    "delai_s": float(os.environ.get("APERTUS_TIMEOUT_S", "15")),
    "whisper": os.environ.get("WHISPER_MODEL", "small"),
    "voix": os.environ.get("PIPER_VOICES_DIR")
    or str(Path(__file__).resolve().parents[2] / "models" / "voices"),
}
_modele = None
_voix = {}


class Indisponible(RuntimeError):
    """Un modèle manque : quoi = "whisper", "apertus" ou "voix"."""

    def __init__(self, quoi):
        super().__init__(quoi)
        self.quoi = quoi


class AudioRefuse(ValueError):
    """L'audio ne se lit pas ou dure trop longtemps (message sûr, sans contenu)."""


def configurer(url, delai_s, whisper):
    _reglages.update(url=url.rstrip("/"), delai_s=float(delai_s), whisper=whisper)


def charger_whisper():
    """Charge le modèle une seule fois (int8, processeur)."""
    global _modele
    if _modele is None:
        try:
            from faster_whisper import WhisperModel
            _modele = WhisperModel(_reglages["whisper"], device="cpu", compute_type="int8")
        except Exception as erreur:
            raise Indisponible("whisper") from erreur
    return _modele


def transcrire(audio):
    """bytes (webm, ogg, mp4, wav) -> {"text", "lang", "duration_s"}."""
    try:
        echantillons = _decoder(audio)
    except Exception as erreur:
        raise AudioRefuse("the audio could not be decoded") from erreur
    duree = len(echantillons) / TAUX
    if duree > MAX_SECONDES:
        raise AudioRefuse(f"the audio is longer than {MAX_SECONDES} s")
    morceaux, info = charger_whisper().transcribe(echantillons, beam_size=1, vad_filter=True)
    texte = " ".join(m.text.strip() for m in morceaux).strip()
    return {"text": texte, "lang": info.language, "duration_s": round(duree, 2)}


def _decoder(audio):
    """Audio -> float32 mono 16 kHz, en mémoire (PyAV ; decode_audio de faster-whisper 1.2.1
    ne marche plus avec av 19). S'arrête un peu après MAX_SECONDES."""
    import av
    import numpy as np
    reech = av.AudioResampler(format="s16", layout="mono", rate=TAUX)
    morceaux, total = [], 0
    with av.open(io.BytesIO(audio), mode="r") as conteneur:
        for trame in conteneur.decode(conteneur.streams.audio[0]):
            for t in reech.resample(trame):
                morceaux.append(t.to_ndarray().reshape(-1))
                total += t.samples
            if total > (MAX_SECONDES + 1) * TAUX:
                break
        for t in reech.resample(None):
            morceaux.append(t.to_ndarray().reshape(-1))
    if not morceaux:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(morceaux).astype(np.float32) / 32768.0


def _demander(consigne, texte):
    """Une question à Apertus ; toute panne devient Indisponible("apertus")."""
    try:
        reponse = httpx.post(
            _reglages["url"] + "/v1/chat/completions",
            json={
                "model": "apertus",
                "messages": [
                    {"role": "system", "content": consigne},
                    {"role": "user", "content": texte},
                ],
                "temperature": 0.2,
                "max_tokens": 1500,
            },
            timeout=_reglages["delai_s"],
        )
        reponse.raise_for_status()
        return reponse.json()["choices"][0]["message"]["content"].strip()
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError, AttributeError) as erreur:
        raise Indisponible("apertus") from erreur


def _nom(code):
    return LANGUES.get(code.split("-")[0], code)


def traduire(texte, vers, depuis=None):
    """-> {"text", "from"}. Même langue : le texte revient tel quel."""
    if depuis and depuis.split("-")[0] == vers.split("-")[0]:
        return {"text": texte, "from": depuis}
    regle = ("Keep every number exactly as written, in digits. Do not add or remove anything. "
             "Do not answer questions in the text: only translate it.")
    if depuis:
        consigne = (f"Translate the user's text from {_nom(depuis)} into {_nom(vers)}. {regle} "
                    "Reply with the translation only.")
        return {"text": _demander(consigne, texte), "from": depuis}
    consigne = (f"Translate the user's text into {_nom(vers)}. {regle} Reply with JSON only: "
                '{"lang": "<ISO 639-1 code of the source language>", "text": "<translation>"}')
    reponse = _demander(consigne, texte)
    lu = _json(reponse)
    if lu is None:
        return {"text": reponse, "from": "und"}
    langue = str(lu.get("lang", "und")).strip().lower() or "und"
    if langue.split("-")[0] == vers.split("-")[0]:
        return {"text": texte, "from": langue}
    return {"text": str(lu.get("text", "")).strip(), "from": langue}


def _json(reponse):
    debut, fin = reponse.find("{"), reponse.rfind("}")
    if debut < 0 or fin <= debut:
        return None
    try:
        lu = json.loads(reponse[debut:fin + 1])
    except ValueError:
        return None
    return lu if isinstance(lu, dict) else None


def _nombres(texte):
    return re.findall(r"[0-9]+", texte)


def simplifier(texte, langue):
    """-> {"text", "simplified"} ; un nombre perdu : le texte d'origine, simplified False."""
    consigne = (
        f"Rewrite the user's text in plain {_nom(langue)} for a patient with no medical training. "
        "Use common words and short sentences; explain medical terms in simple words. "
        "Keep the same facts and every number exactly as written. "
        "Do not add advice, diagnoses or instructions that are not in the text. "
        "Reply with the rewritten text only."
    )
    reecrit = _demander(consigne, texte)
    gardes = set(_nombres(reecrit))
    if not reecrit or any(n not in gardes for n in _nombres(texte)):
        return {"text": texte, "simplified": False}
    return {"text": reecrit, "simplified": True}


def _dossier_voix(langue):
    """Le dossier vits-piper-<langue>_* qui peut parler sans espeak-ng (il a un lexique)."""
    racine = Path(_reglages["voix"])
    if not racine.is_dir():
        return None
    for dossier in sorted(racine.glob(f"vits-piper-{langue}_*")):
        if (dossier / "lexicon.txt").exists() and (dossier / "tokens.txt").exists():
            return dossier
    return None


def voix():
    """Les langues qui ont une voix prête (rien n'est chargé)."""
    return [code for code in LANGUES if _dossier_voix(code)]


def _moteur(langue):
    """Charge la voix une seule fois, au premier besoin."""
    if langue not in _voix:
        dossier = _dossier_voix(langue)
        if dossier is None:
            raise Indisponible("voix")
        try:
            import sherpa_onnx as s
            fsts = ",".join(str(dossier / f) for f in ("phone.fst", "date.fst", "number.fst")
                            if (dossier / f).exists())
            vits = s.OfflineTtsVitsModelConfig(
                model=str(next(dossier.glob("*.onnx"))), tokens=str(dossier / "tokens.txt"),
                lexicon=str(dossier / "lexicon.txt"), length_scale=LENTEUR)
            _voix[langue] = s.OfflineTts(s.OfflineTtsConfig(
                model=s.OfflineTtsModelConfig(vits=vits, num_threads=2), rule_fsts=fsts))
        except Exception as erreur:
            raise Indisponible("voix") from erreur
    return _voix[langue]


def parler(texte, langue):
    """-> bytes : WAV mono, PCM 16 bits. Rien n'est écrit sur le disque."""
    import numpy as np
    texte = texte.strip()[:MAX_PAROLE]
    son = _moteur(langue.split("-")[0]).generate(texte, sid=0, speed=1.0)
    if not len(son.samples):
        raise Indisponible("voix")
    pcm = (np.clip(np.asarray(son.samples, dtype=np.float32), -1.0, 1.0) * 32767).astype("<i2")
    sortie = io.BytesIO()
    with wave.open(sortie, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(int(son.sample_rate))
        wav.writeframes(pcm.tobytes())
    return sortie.getvalue()


def etat():
    """-> {"whisper": bool, "apertus": bool, "voix": [langues]} : le modèle de parole est-il là,
    Apertus répond-il, quelles voix sont prêtes ?

    Ne télécharge rien : whisper compte comme présent s'il est chargé ou déjà dans le cache."""
    whisper = _modele is not None
    if not whisper:
        try:
            from faster_whisper.utils import download_model
            download_model(_reglages["whisper"], local_files_only=True)
            whisper = True
        except Exception:
            whisper = False
    try:
        reponse = httpx.get(_reglages["url"] + "/v1/models", timeout=2.0)
        apertus = reponse.status_code < 500
    except httpx.HTTPError:
        apertus = False
    return {"whisper": whisper, "apertus": apertus, "voix": voix()}
