"""Brique 13 — Le bouton « Internet coupé » (idée 8) : il coupe VRAIMENT les sorties de ce programme vers Internet.

Comme conftest.py pendant les tests, on remplace des fonctions de Python :
- `socket.connect`, `connect_ex`, `sendto` (ouvrir une connexion, envoyer) : refusés si l'adresse n'est pas locale ;
- `socket.getaddrinfo`, `gethostbyname`, `gethostbyname_ex` (chercher l'adresse d'un nom, « DNS ») : refusés pour
  un nom d'Internet ; `gethostbyaddr` (chercher le nom d'une adresse) : refusé pour une adresse d'Internet.
  Pas remplacé : `getnameinfo` (rarement utilisé seul ; la connexion qui suit, elle, est vérifiée).
Restent permis : cet ordinateur (localhost, 127.0.0.1, ::1) et le réseau local de l'équipe
(192.168.x.x, 10.x.x.x, 172.16 à 31.x.x, 100.64.x.x à 100.127.x.x — réseaux comme Tailscale —, fe80::…, fd00::…,
un nom sans point comme « imac », et les noms en .local, .lan, .home, .home.arpa, .fritz.box, .internal).
C'est là que sont l'autre Mac, les tablettes et l'écran du jury : ils continuent de marcher.
En plus : `reglages.yaml → ecran → internet_coupe → toujours_permis` (noms ou adresses du robot et de l'autre Mac,
ex. ["robot-g1", "192.168.8.20", "10.42.0.0/24"]) : toujours permis, même si ce n'est pas une adresse locale.
Exception : un mandataire (« proxy », variables HTTPS_PROXY, HTTP_PROXY, ALL_PROXY) mène à Internet même s'il est
sur cet ordinateur : il est refusé aussi pendant la coupure.

Le bouton éteint aussi l'étage « Apertus par Internet » de la cascade (s'il existe) : le cerveau passe tout de suite
au suivant, sans attendre son délai.

Limites honnêtes :
- seul CE programme Python est coupé ; les autres programmes du Mac (navigateur, mises à jour…) ne le sont pas ;
- une connexion ouverte AVANT le clic n'est pas coupée (sauf celle du cerveau par Internet, qu'on ferme) ;
- avec « uvloop » (pas installé aujourd'hui), les connexions asynchrones passeraient à côté : la page le signale.
Pour une démonstration totale, débrancher aussi le câble Internet de la box : le Wi-Fi local continue.
"""
from __future__ import annotations

import asyncio
import errno
import ipaddress
import math
import os
import socket
import time
from collections import deque
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlparse

SUFFIXES_LOCAUX = (".local", ".lan", ".home", ".home.arpa", ".fritz.box", ".internal", ".localhost")
# 100.64.0.0/10 : « espace partagé » (box d'opérateur, Tailscale). Python ne le compte pas comme privé.
RESEAUX_LOCAUX_EN_PLUS = (ipaddress.ip_network("100.64.0.0/10"),)
ESSAI = ("1.1.1.1", 443)  # adresse d'Internet utilisée pour vérifier la coupure (rien ne part : refusé avant)


class InternetCoupe(ConnectionRefusedError):
    """Le programme a voulu sortir vers Internet pendant la coupure."""


class NomRefuse(socket.gaierror):
    """Le programme a voulu chercher l'adresse d'un nom d'Internet pendant la coupure."""


def nom_local(nom: str) -> bool:
    """« imac.local », « imac », « localhost » : des noms du réseau local. « api.exemple.ch » : Internet."""
    nom = nom.strip().rstrip(".").lower()
    return nom == "localhost" or "." not in nom or nom.endswith(SUFFIXES_LOCAUX)


def _ip(hote: str):
    try:
        ip = ipaddress.ip_address(hote.strip().strip("[]").split("%")[0])
    except ValueError:
        return None
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip


def mandataires_declares() -> set[tuple[str, int]]:
    """Les mandataires (« proxy ») déclarés dans l'environnement : souvent sur 127.0.0.1, mais ils mènent à Internet."""
    res: set[tuple[str, int]] = set()
    for nom in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy", "all_proxy"):
        valeur = os.environ.get(nom) or ""
        if not valeur:
            continue
        u = urlparse(valeur if "//" in valeur else "//" + valeur)
        try:
            port = u.port or {"https": 443, "socks5": 1080, "socks5h": 1080}.get(u.scheme, 80)
        except ValueError:
            continue
        if u.hostname:
            res.add((u.hostname.lower(), port))
    return res


def adresse_permise(hote: Any) -> bool:
    """Vrai pour cet ordinateur et le réseau local ; faux pour Internet."""
    if isinstance(hote, bytes):
        hote = hote.decode("ascii", "ignore")
    if not isinstance(hote, str):
        return False
    if hote.strip() in ("", "localhost"):
        return True
    ip = _ip(hote)
    if ip is None:
        return nom_local(hote)
    return ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_unspecified \
        or any(ip.version == r.version and ip in r for r in RESEAUX_LOCAUX_EN_PLUS)


def _nom_simple(x: Any) -> str:
    """« http://Robot-G1.local:8000/ » -> « robot-g1.local » ; « [fd00::1] » -> « fd00::1 »."""
    texte = str(x).strip()
    if "//" in texte:
        texte = urlparse(texte).hostname or ""
    return texte.strip().strip("[]").rstrip(".").lower()


class Coupure:
    """L'interrupteur. Une seule coupure à la fois pour tout le programme (les fonctions remplacées sont communes)."""

    def __init__(self, toujours_permis: Iterable[Any] = ()) -> None:
        self.coupe = False
        self.depuis: str | None = None  # heure de la coupure
        self.refusees = 0  # connexions vers Internet refusées depuis la coupure
        self.dernieres: deque = deque(maxlen=5)  # les dernières adresses refusées
        self._avant: dict[str, Any] = {}
        self._miens: dict[str, Any] = {}
        self.mandataires: set[tuple[str, int]] = set()  # (adresse, port) des « proxy » vers Internet, refusés aussi
        # reglages.yaml → ecran → internet_coupe → toujours_permis : le robot, l'autre Mac (noms ou adresses).
        self.toujours_permis: list[str] = []
        self._toujours_noms: set[str] = set()
        self._toujours_reseaux: list = []
        self._toujours_ips: set = set()  # les adresses des noms toujours permis (trouvées en les cherchant)
        if isinstance(toujours_permis, (str, bytes)):  # « toujours_permis: robot-g1 » au lieu d'une liste
            toujours_permis = [toujours_permis]
        for x in toujours_permis or ():
            nom = _nom_simple(x)
            if not nom:
                continue
            self.toujours_permis.append(nom)
            try:
                self._toujours_reseaux.append(ipaddress.ip_network(nom.split("%")[0], strict=False))
            except ValueError:
                self._toujours_noms.add(nom)

    def toujours(self, hote: Any) -> bool:
        """Vrai pour un nom ou une adresse de la liste « toujours permis » (sans rien demander au réseau)."""
        if isinstance(hote, bytes):
            hote = hote.decode("ascii", "ignore")
        if not isinstance(hote, str) or not self.toujours_permis:
            return False
        if _nom_simple(hote) in self._toujours_noms:
            return True
        ip = _ip(hote)
        return ip is not None and (ip in self._toujours_ips
                                   or any(ip.version == r.version and ip in r for r in self._toujours_reseaux))

    def _noter_adresses_permises(self, resultats) -> None:
        for r in resultats:
            ip = _ip(str(r[4][0]))
            if ip is not None:
                self._toujours_ips.add(ip)

    # ------------------------------------------------------------ couper / rétablir
    def couper(self) -> None:
        if self.coupe:
            return
        avant = self._avant = {"connect": socket.socket.connect, "connect_ex": socket.socket.connect_ex,
                               "sendto": socket.socket.sendto, "getaddrinfo": socket.getaddrinfo,
                               "gethostbyname": socket.gethostbyname, "gethostbyname_ex": socket.gethostbyname_ex,
                               "gethostbyaddr": socket.gethostbyaddr}
        self.mandataires = set()
        for nom in self._toujours_noms:  # où mènent les noms toujours permis (avant de couper la recherche)
            try:
                self._noter_adresses_permises(avant["getaddrinfo"](nom, None))
            except OSError:
                pass
        for hote, port in mandataires_declares():
            self.mandataires.add((hote, port))
            if _ip(hote) is None and nom_local(hote):
                try:
                    self.mandataires |= {(r[4][0], port) for r in avant["getaddrinfo"](hote, port)}
                except OSError:
                    pass
        coupure = self

        def connect(sock, adresse):
            coupure._verifier(sock, adresse)
            return avant["connect"](sock, adresse)

        def connect_ex(sock, adresse):
            try:
                coupure._verifier(sock, adresse)
            except InternetCoupe:
                return errno.ECONNREFUSED
            return avant["connect_ex"](sock, adresse)

        def sendto(sock, donnees, *reste):
            if reste:
                coupure._verifier(sock, reste[-1])
            return avant["sendto"](sock, donnees, *reste)

        def getaddrinfo(hote, *args, **kwargs):
            return coupure._chercher(hote, *args, **kwargs)

        def gethostbyname(hote):
            coupure._chercher(hote, None)  # même vérification que getaddrinfo (lève NomRefuse pour Internet)
            ip = avant["gethostbyname"](hote)
            if not coupure.toujours(hote) and not coupure.toujours(ip) and not adresse_permise(ip):
                coupure._refuser(hote)
                raise NomRefuse(socket.EAI_NONAME, f"Internet coupé (bouton de l'écran) : {hote} mène vers Internet")
            return ip

        def gethostbyname_ex(hote):
            coupure._chercher(hote, None)
            nom, alias, ips = avant["gethostbyname_ex"](hote)
            if not coupure.toujours(hote):
                ips = [ip for ip in ips if adresse_permise(ip) or coupure.toujours(ip)]
                if not ips:
                    coupure._refuser(hote)
                    raise NomRefuse(socket.EAI_NONAME, f"Internet coupé (bouton de l'écran) : {hote} mène vers Internet")
            return nom, alias, ips

        def gethostbyaddr(adresse):
            texte = adresse.decode("ascii", "ignore") if isinstance(adresse, bytes) else str(adresse)
            if _ip(texte) is None:
                coupure._chercher(adresse, None)  # un nom : même vérification que getaddrinfo
            elif not coupure.toujours(texte) and not adresse_permise(texte):
                coupure._refuser(texte)
                raise NomRefuse(socket.EAI_NONAME, f"Internet coupé (bouton de l'écran) : pas de recherche pour {texte}")
            return avant["gethostbyaddr"](adresse)

        self._miens = {"connect": connect, "connect_ex": connect_ex, "sendto": sendto, "getaddrinfo": getaddrinfo,
                       "gethostbyname": gethostbyname, "gethostbyname_ex": gethostbyname_ex,
                       "gethostbyaddr": gethostbyaddr}
        socket.socket.connect = connect
        socket.socket.connect_ex = connect_ex
        socket.socket.sendto = sendto
        socket.getaddrinfo = getaddrinfo
        socket.gethostbyname = gethostbyname
        socket.gethostbyname_ex = gethostbyname_ex
        socket.gethostbyaddr = gethostbyaddr
        self.coupe = True
        self.depuis = time.strftime("%H:%M:%S")
        self.refusees = 0
        self.dernieres.clear()

    def retablir(self) -> None:
        if not self.coupe:
            return
        # On ne remet l'ancienne fonction que si la nôtre est encore en place (un test a pu tout remettre lui-même).
        m, a = self._miens, self._avant
        if socket.socket.connect is m["connect"]:
            socket.socket.connect = a["connect"]
        if socket.socket.connect_ex is m["connect_ex"]:
            socket.socket.connect_ex = a["connect_ex"]
        if socket.socket.sendto is m["sendto"]:
            socket.socket.sendto = a["sendto"]
        if socket.getaddrinfo is m["getaddrinfo"]:
            socket.getaddrinfo = a["getaddrinfo"]
        if socket.gethostbyname is m["gethostbyname"]:
            socket.gethostbyname = a["gethostbyname"]
        if socket.gethostbyname_ex is m["gethostbyname_ex"]:
            socket.gethostbyname_ex = a["gethostbyname_ex"]
        if socket.gethostbyaddr is m["gethostbyaddr"]:
            socket.gethostbyaddr = a["gethostbyaddr"]
        self.coupe = False
        self.depuis = None

    # ------------------------------------------------------------ vérifications
    def _refuser(self, hote: Any) -> None:
        self.refusees += 1
        self.dernieres.append(str(hote))

    def _permis(self, hote: Any) -> bool:
        if isinstance(hote, bytes):
            hote = hote.decode("ascii", "ignore")
        if not isinstance(hote, str) or _ip(hote) is not None or not nom_local(hote):
            return adresse_permise(hote)
        # Un nom local (« imac.local ») : on vérifie aussi où il mène.
        try:
            res = self._avant["getaddrinfo"](hote, None)
        except OSError:
            return True  # nom introuvable : la vraie connexion échouera d'elle-même
        return all(adresse_permise(r[4][0]) for r in res)

    def _verifier(self, sock, adresse) -> None:
        if sock.family not in (socket.AF_INET, socket.AF_INET6):
            return  # fichiers locaux (AF_UNIX) et autres : pas Internet
        hote = adresse[0] if isinstance(adresse, tuple) and adresse else adresse
        port = adresse[1] if isinstance(adresse, tuple) and len(adresse) > 1 else None
        if (str(hote).lower(), port) in self.mandataires:
            self._refuser(f"{hote}:{port}")
            raise InternetCoupe(f"Internet coupé (bouton de l'écran) : mandataire (proxy) {hote}:{port} refusé")
        if self.toujours(hote):  # reglages.yaml → ecran → internet_coupe → toujours_permis (robot, autre Mac)
            return
        if not self._permis(hote):
            self._refuser(hote)
            raise InternetCoupe(f"Internet coupé (bouton de l'écran) : connexion vers {hote} refusée")

    def _chercher(self, hote, *args, **kwargs):
        if hote is None:
            return self._avant["getaddrinfo"](hote, *args, **kwargs)
        texte = hote.decode("ascii", "ignore") if isinstance(hote, bytes) else str(hote)
        if self.toujours(texte):  # le robot ou l'autre Mac : permis ; on note où il mène, pour la connexion
            res = self._avant["getaddrinfo"](hote, *args, **kwargs)
            self._noter_adresses_permises(res)
            return res
        if _ip(texte) is None and not nom_local(texte):
            self._refuser(texte)
            raise NomRefuse(socket.EAI_NONAME, f"Internet coupé (bouton de l'écran) : pas de recherche pour {texte}")
        res = self._avant["getaddrinfo"](hote, *args, **kwargs)
        if _ip(texte) is not None:
            return res  # adresse en chiffres : rien n'est demandé au réseau ; la connexion sera vérifiée
        gardes = [r for r in res if adresse_permise(r[4][0])]
        if not gardes:
            self._refuser(texte)
            raise NomRefuse(socket.EAI_NONAME, f"Internet coupé (bouton de l'écran) : {texte} mène vers Internet")
        return gardes

    # ------------------------------------------------------------ preuve
    def essai(self) -> str:
        """Essayer d'ouvrir une connexion vers Internet : elle doit être refusée AVANT de partir."""
        avant = self.refusees
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.settimeout(0.5)
            s.connect(ESSAI)
        except InternetCoupe:
            return f"essai : connexion vers {ESSAI[0]}:{ESSAI[1]} refusée avant de partir"
        except OSError as e:
            return f"essai : connexion impossible ({e.__class__.__name__}), coupure à vérifier"
        finally:
            s.close()
            self.refusees = avant
            if self.dernieres and self.dernieres[-1] == ESSAI[0]:
                self.dernieres.pop()
        return "ATTENTION : la connexion d'essai vers Internet a réussi : la coupure ne marche pas"


def limites_de_la_coupure() -> list[str]:
    """Ce que la coupure ne peut pas voir, dit honnêtement (affiché sur la page)."""
    limites = []
    try:
        boucle = type(asyncio.get_running_loop()).__module__
    except RuntimeError:
        boucle = ""
    if boucle.startswith("uvloop"):
        limites.append("uvloop est utilisé : les connexions asynchrones ne passent pas par la coupure (lancer avec "
                       "loop=\"asyncio\")")
    return limites


# ---------------------------------------------------------------- l'étage « Apertus par Internet »
def etages_par_internet(cerveau: Any, toujours: Any = None) -> list:
    """Les étages de la cascade dont le cerveau est joint par Internet (adresse non locale, et pas dans la liste
    « toujours permis » : `toujours` est la fonction `Coupure.toujours`)."""
    res = []
    for etage in getattr(cerveau, "etages", None) or []:
        url = getattr(etage.cerveau, "url", "") or ""
        hote = urlparse(url if "//" in url else "//" + url).hostname or ""
        if hote and not adresse_permise(hote) and not (toujours and toujours(hote)):
            res.append(etage)
    return res


class EtagesEteints:
    """Met de côté (sans limite de temps) les étages par Internet, puis les rend tels qu'ils étaient."""

    def __init__(self) -> None:
        self._eteints: list[tuple[Any, float]] = []

    @property
    def noms(self) -> list[str]:
        return [e.cerveau.nom for e, _ in self._eteints]

    async def eteindre(self, cerveau: Any, toujours: Any = None) -> list[str]:
        for etage in etages_par_internet(cerveau, toujours):
            if any(e is etage for e, _ in self._eteints):
                continue
            self._eteints.append((etage, etage.en_pause_jusqua))
            etage.en_pause_jusqua = math.inf  # la cascade passe au suivant sans l'essayer
            try:
                await etage.cerveau.arreter()  # ferme sa connexion réseau déjà ouverte
            except Exception:  # noqa: BLE001 - éteindre ne doit jamais planter l'écran
                pass
        return self.noms

    def rallumer(self) -> list[str]:
        noms = self.noms
        for etage, pause in self._eteints:
            etage.en_pause_jusqua = pause if math.isfinite(pause) else 0.0
        self._eteints = []
        return noms
