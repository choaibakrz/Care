"""« Rien n'est sorti de l'ordinateur » : la surveillance des connexions pendant la répétition (cahier, partie 8, étape 14).

    with Surveillance() as s:
        ...                      # la répétition
    s.essais                     # chaque essai de connexion vers l'extérieur : où, par quoi

Pendant la surveillance, ce programme ne peut pas se connecter hors de l'ordinateur : chaque essai est COMPTÉ et
BLOQUÉ (rien ne part), puis l'étape 14 le dit. Les adresses de l'ordinateur lui-même (127.0.0.1, ::1, localhost,
fichiers locaux) restent permises.

LIMITES, à dire à voix haute : on surveille seulement CE programme, par les portes réseau de Python (connexion,
envoi direct, recherche d'un nom ou d'une adresse). On ne voit pas un autre programme lancé à côté (un serveur de modèle, un
navigateur), ni un outil qui parlerait au réseau sans passer par Python. Pendant la démonstration avec les écrans
(« python3 lancer.py »), cette surveillance ne tourne pas : elle ne tourne que pendant la répétition.
"""
from __future__ import annotations

import ipaddress
import socket
from typing import Any

NOMS_LOCAUX = (None, "", "localhost", "127.0.0.1", "::1", "0.0.0.0", "testserver")
def _poser(nom: str, porte: Any) -> None:
    """Met une porte en place. Chaque nom est écrit en clair : pas d'accès « par un nom calculé »."""
    if nom == "socket.connect":
        socket.socket.connect = porte
    elif nom == "socket.connect_ex":
        socket.socket.connect_ex = porte
    elif nom == "socket.sendto":
        socket.socket.sendto = porte
    elif nom == "socket.sendmsg":
        socket.socket.sendmsg = porte
    elif nom == "getaddrinfo":
        socket.getaddrinfo = porte
    elif nom == "gethostbyname":
        socket.gethostbyname = porte
    elif nom == "gethostbyname_ex":
        socket.gethostbyname_ex = porte
    elif nom == "gethostbyaddr":
        socket.gethostbyaddr = porte
    elif nom == "getnameinfo":
        socket.getnameinfo = porte
    else:
        raise ValueError(f"porte inconnue « {nom} »")


def _en_place() -> dict[str, Any]:
    """Les neuf portes réseau surveillées, telles qu'elles sont maintenant."""
    return {"socket.connect": socket.socket.connect, "socket.connect_ex": socket.socket.connect_ex,
            "socket.sendto": socket.socket.sendto, "socket.sendmsg": socket.socket.sendmsg,
            "getaddrinfo": socket.getaddrinfo, "gethostbyname": socket.gethostbyname,
            "gethostbyname_ex": socket.gethostbyname_ex, "gethostbyaddr": socket.gethostbyaddr,
            "getnameinfo": socket.getnameinfo}


def _est_local(adresse: Any) -> bool:
    if isinstance(adresse, (str, bytes)):  # un fichier local (AF_UNIX)
        return True
    hote = adresse[0] if isinstance(adresse, tuple) and adresse else adresse
    if hote in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(hote).is_loopback
    except (ValueError, TypeError):
        return False


def _est_une_adresse(hote: Any) -> bool:
    try:
        ipaddress.ip_address(hote.decode() if isinstance(hote, bytes) else hote)
        return True
    except (ValueError, TypeError, AttributeError):
        return False


class Surveillance:
    def __init__(self) -> None:
        self.essais: list[dict[str, str]] = []
        self.active = False
        self.complete = False  # vrai seulement si elle a tourné du début jusqu'à maintenant, sans trou
        self._avant: dict[str, Any] = {}
        self._posees: dict[str, Any] = {}

    def _noter(self, par: str, ou: Any) -> None:
        self.essais.append({"par": par, "ou": str(ou)})

    def __enter__(self) -> "Surveillance":
        veille = self
        self._avant = _en_place()
        self._avant["connect"] = self._avant["socket.connect"]  # l'ancien nom, gardé pour les essais
        avant = self._avant

        def bloquer(par: str, ou: Any, erreur=ConnectionRefusedError):
            veille._noter(par, ou)
            raise erreur(f"répétition : {par} vers {ou} : bloqué (rien ne sort de l'ordinateur)")

        def connect(sock, adresse):
            if not _est_local(adresse):
                bloquer("connexion", adresse)
            return avant["socket.connect"](sock, adresse)

        def connect_ex(sock, adresse):
            if not _est_local(adresse):
                veille._noter("connexion", adresse)
                return 111  # « connexion refusée »
            return avant["socket.connect_ex"](sock, adresse)

        def sendto(sock, *args):
            if args and not _est_local(args[-1]):
                bloquer("envoi direct", args[-1])
            return avant["socket.sendto"](sock, *args)

        def sendmsg(sock, *args):
            if len(args) >= 4 and args[3] is not None and not _est_local(args[3]):
                bloquer("envoi direct", args[3])
            return avant["socket.sendmsg"](sock, *args)

        def par_nom(fonction: str):  # chercher un nom, c'est déjà parler au réseau
            def chercher(hote, *args, **kwargs):
                if hote not in NOMS_LOCAUX and not _est_une_adresse(hote):
                    bloquer("recherche d'un nom", hote, socket.gaierror)
                return avant[fonction](hote, *args, **kwargs)
            return chercher

        def gethostbyaddr(hote, *args):  # demander le nom d'une adresse : pareil
            if hote not in NOMS_LOCAUX and not _est_local((hote,)):
                bloquer("recherche d'un nom", hote, socket.herror)
            return avant["gethostbyaddr"](hote, *args)

        def getnameinfo(adresse, *args):
            if not _est_local(adresse):
                bloquer("recherche d'un nom", adresse, socket.gaierror)
            return avant["getnameinfo"](adresse, *args)

        self._posees = {"socket.connect": connect, "socket.connect_ex": connect_ex, "socket.sendto": sendto,
                        "socket.sendmsg": sendmsg, "getaddrinfo": par_nom("getaddrinfo"),
                        "gethostbyname": par_nom("gethostbyname"), "gethostbyname_ex": par_nom("gethostbyname_ex"),
                        "gethostbyaddr": gethostbyaddr, "getnameinfo": getnameinfo}
        for nom, porte in self._posees.items():
            _poser(nom, porte)
        self.active = self.complete = True
        return self

    def intacte(self) -> bool:
        """Nos portes sont-elles toujours en place ? Si une pièce en a retiré une, la surveillance a un trou."""
        en_place = _en_place()
        for nom, porte in self._posees.items():
            if en_place[nom] is not porte:
                self.complete = False
        return self.complete

    def __exit__(self, *exc) -> None:
        for nom in self._posees:
            _poser(nom, self._avant[nom])
        self.active = False


def etape_14():
    """Étape 14 : pendant tout le scénario, le prototype n'a rien envoyé hors de l'ordinateur."""
    from . import repetition

    seance = repetition.SEANCE
    limite = ("surveillance de ce programme seulement (portes réseau de Python) ; un autre programme lancé à côté "
              "ne serait pas vu")
    if seance is None or seance.reseau is None or not seance.reseau.active:
        return repetition.Resultat(False, "SIMULÉ", "cette étape se joue pendant une répétition, avec la surveillance "
                                                    "du réseau allumée depuis le début")
    if not seance.reseau.intacte():
        return repetition.Resultat(False, "SIMULÉ", "la surveillance du réseau a été retirée en cours de répétition : "
                                                    "on ne peut pas dire que rien n'est sorti")
    if not seance.jouees(range(1, 14)):
        manquent = [n for n in range(1, 14) if seance.issues.get(n) not in ("reussie", "ratee")]
        return repetition.Resultat(False, "SIMULÉ", f"tout le scénario n'a pas été joué sous surveillance : étapes "
                                                    f"{', '.join(str(n) for n in manquent)} pas jouées ; {limite}")
    essais = seance.reseau.essais
    if essais:
        liste = " ; ".join(f"{e['par']} vers {e['ou']}" for e in essais[:5])
        return repetition.Resultat(False, "SIMULÉ", f"{len(essais)} essai{'s' if len(essais) > 1 else ''} de connexion "
                                                    f"vers l'extérieur, bloqué{'s' if len(essais) > 1 else ''} : {liste} ; {limite}")
    return repetition.Resultat(True, "SIMULÉ", f"0 essai de connexion vers l'extérieur pendant les étapes 1 à 13 "
                                               f"(un essai aurait été compté et bloqué) ; {limite}",
                               {"essais_vers_l_exterieur": 0})
