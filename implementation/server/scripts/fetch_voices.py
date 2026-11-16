"""Download the Piper voices the patient app speaks with (sherpa-onnx VITS, offline).

One medium-quality voice per language, from the official sherpa-onnx release
(github.com/k2-fsa/sherpa-onnx/releases/tag/tts-models), unpacked into
PIPER_VOICES_DIR (default: <repo>/models/voices, git-ignored). Run it while online,
before the pitch:

    .venv\\Scripts\\python.exe implementation\\server\\scripts\\fetch_voices.py [lang ...]

A voice already unpacked is skipped. No Croatian (hr) Piper voice exists: the app falls
back to the browser's voice for it.

sherpa-onnx 2.x no longer turns text into phonemes itself: a voice speaks only when it has a
lexicon (lexicon.txt, here zh chaowen). The other Piper voices need espeak-ng (GPL-3.0), an
option the team turned OFF (DECISIONS.md, "Voix"): they are downloaded so the pitch can run
offline once that is decided, and until then the app uses the browser's voice for them.
"""

import os
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

BASE = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/"
VOICES = {
    "en": "vits-piper-en_US-lessac-medium",
    "fr": "vits-piper-fr_FR-siwis-medium",
    "de": "vits-piper-de_DE-thorsten-medium",
    "it": "vits-piper-it_IT-paola-medium",
    "es": "vits-piper-es_ES-davefx-medium",
    "pt": "vits-piper-pt_PT-tugao-medium",
    "nl": "vits-piper-nl_BE-nathalie-medium",
    "ar": "vits-piper-ar_JO-kareem-medium",
    "tr": "vits-piper-tr_TR-dfki-medium",
    "zh": "vits-piper-zh_CN-chaowen-medium",
    "ru": "vits-piper-ru_RU-irina-medium",
    "uk": "vits-piper-uk_UA-ukrainian_tts-medium",
    "pl": "vits-piper-pl_PL-gosia-medium",
    "ro": "vits-piper-ro_RO-mihai-medium",
    "sr": "vits-piper-sr_RS-serbski_institut-medium",
    "sq": "vits-piper-sq_AL-edon-medium",
}
REPO = Path(__file__).resolve().parents[3]


def main(langs):
    target = Path(os.environ.get("PIPER_VOICES_DIR", REPO / "models" / "voices"))
    target.mkdir(parents=True, exist_ok=True)
    (target / ".gitignore").write_text("*\n", encoding="utf-8")
    for lang in langs or VOICES:
        name = VOICES[lang]
        if (target / name / "tokens.txt").exists():
            print(f"{lang}: {name} already here")
            continue
        print(f"{lang}: downloading {name} ...", flush=True)
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / f"{name}.tar.bz2"
            urllib.request.urlretrieve(BASE + archive.name, archive)
            with tarfile.open(archive, "r:bz2") as tar:
                tar.extractall(target, filter="data")
        print(f"{lang}: ok")


if __name__ == "__main__":
    main(sys.argv[1:])
