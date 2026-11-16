"""Réglages communs à tous les tests.

Internet est coupé pour TOUS les tests : toute connexion vers l'extérieur fait échouer le test.
Seules les adresses locales (127.0.0.1, ::1, fichiers locaux) restent permises.
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

_connect_original = socket.socket.connect


def pytest_configure(config):
    """GARDE-FOU (15.11.2026) : les essais ne touchent JAMAIS un vrai robot.

    reglages.yaml est propre à chaque ordinateur. Le jour où il désigne un vrai robot (robot.vrai_robot: true, ou un
    adaptateur de la brique 3), un essai qui fabrique le système « avec les réglages de l'ordinateur » se connecterait
    au vrai robot, et pourrait le faire bouger. Donc, pendant TOUS les essais, les réglages chargés ont toujours le
    faux robot, quoi que dise le fichier ; et le dossier du kit de la main pointe vers un dossier vide."""
    import os

    from commun import systeme

    os.environ["LEADTRON_KIT"] = "/var/empty"
    charger_pour_de_vrai = systeme.charger_reglages

    def charger_reglages_sans_vrai_robot(chemin=None):
        reglages = charger_pour_de_vrai(chemin)
        robot = reglages.get("robot") if isinstance(reglages, dict) else None
        if isinstance(robot, dict) and (robot.get("vrai_robot") or robot.get("adaptateur") != "faux_robot"):
            robot["adaptateur"], robot["vrai_robot"] = "faux_robot", False
            robot["carte"] = robot.get("carte") or "humanoide"
        return reglages

    systeme.charger_reglages = charger_reglages_sans_vrai_robot


def _est_local(adresse) -> bool:
    if isinstance(adresse, (str, bytes)):  # socket fichier (AF_UNIX)
        return True
    hote = adresse[0]
    if hote in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(hote).is_loopback
    except ValueError:
        return False


def _connect_sans_internet(self, adresse):
    if not _est_local(adresse):
        raise ConnectionRefusedError(f"Internet coupé pendant les tests : connexion vers {adresse} interdite")
    return _connect_original(self, adresse)


@pytest.fixture(autouse=True)
def sans_internet(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect", _connect_sans_internet)
    monkeypatch.setattr(socket, "getaddrinfo", _getaddrinfo_local)
    yield


_getaddrinfo_original = socket.getaddrinfo


def _getaddrinfo_local(hote, *args, **kwargs):
    if hote not in (None, "localhost", "127.0.0.1", "::1", "0.0.0.0", "testserver"):
        raise socket.gaierror(f"Internet coupé pendant les tests : pas de résolution pour {hote}")
    return _getaddrinfo_original(hote, *args, **kwargs)


def robot(systeme):
    """Pour les TESTS seulement : regarder l'intérieur du faux robot (interdit dans le code du projet)."""
    return systeme.prise._Prise__adaptateur


def lancer(coro):
    """Faire tourner une fonction asynchrone dans un test."""
    return asyncio.run(coro)


@pytest.fixture
def reglages():
    """Les réglages d'EXEMPLE du dépôt (jamais le reglages.yaml de cet ordinateur : les tests doivent donner le même
    résultat partout, quel que soit ce qu'une personne a réglé à la main)."""
    from commun.systeme import REGLAGES_EXEMPLE, charger_reglages

    return charger_reglages(REGLAGES_EXEMPLE)


@pytest.fixture
def fabrique_systeme(tmp_path, reglages):
    """fabrique_systeme("bras") -> un Système complet avec ce faux robot, journal dans un dossier temporaire."""
    from commun.systeme import Systeme

    def fabrique(carte: str = "humanoide", acceleration: float = 20.0):
        r = {**reglages, "robot": {**reglages["robot"], "carte": carte}, "ecran": dict(reglages["ecran"]),
             "cerveau": {**reglages["cerveau"], "choix": "regles"}}  # tests : cerveau à règles (déterministe)
        return Systeme(r, dossier_journal=tmp_path / "journal", acceleration=acceleration)

    return fabrique
