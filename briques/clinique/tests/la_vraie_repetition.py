"""La commande « python3 lancer.py repetition », lancée UNE fois pour tous les essais qui en ont besoin.

Elle dure quelques secondes ; la vérification rapide doit rester sous deux minutes. Elle tourne dans son propre
programme : le garde-fou « Internet coupé » des tests n'y est pas, c'est sa propre surveillance qui compte.
(Pas de fichier conftest.py ici : il cacherait celui de la racine, dont d'autres essais se servent.)
"""
from __future__ import annotations

import functools
import subprocess
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[3]


@functools.lru_cache(maxsize=1)
def _lancer() -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(RACINE / "lancer.py"), "repetition"], cwd=RACINE,
                          capture_output=True, text=True, timeout=120)


@pytest.fixture
def la_vraie_repetition() -> subprocess.CompletedProcess:
    return _lancer()
