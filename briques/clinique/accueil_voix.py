"""L'accueil à la voix (cahier 5.9, tâche T20) : l'arrivée dite, la réponse dite, le chemin affiché, le plan B à l'écran.

    python3 lancer.py accueil-voix --essai                  l'arrivée en italien, dite par la voix du Mac, puis toute la boucle
    python3 lancer.py accueil-voix arrivee.wav              un enregistrement à vous
    python3 lancer.py accueil-voix --essai --haut-parleur   la réponse sort aussi du haut-parleur

La boucle : un son → l'écoute (whisper.cpp, R4) → la phrase → l'accueil du hall (T10, les mêmes règles que la phrase
tapée) → la réponse → la voix du Mac (`say`) la dit, dans la langue de la personne. Le chemin est rendu avec la réponse
(écrit dans le terminal : aucun écran n'est ouvert par cette commande). Tout tourne sur l'ordinateur.

Le plan B « voix en panne » : si le micro est en panne (J02), si l'écoute ne marche pas, ou si rien n'est compris, on
passe à l'écran : la phrase se tape sur /clinique/hall. Si c'est la voix du Mac qui ne marche pas, la réponse s'affiche.

DIRE VRAI : dans l'essai, l'arrivée est dite par une VOIX DE SYNTHÈSE du Mac, pas par une personne. Il n'y a pas encore
de micro en direct : la boucle part d'un enregistrement. Aucun robot ne bouge, aucun visage.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from . import ecoute

DOSSIER_SONS = Path(__file__).resolve().parents[2] / "journal" / "clinique" / "sons"
# Les voix du Mac, par langue, dans l'ordre où on les essaie (relevées sur l'iMac le 11.11.2026).
# Espagnol : voix relevées sur le MacBook le 14.11.2026 ; sur l'iMac : à vérifier (`say -v '?'`).
VOIX = {"it": ("Alice",), "de": ("Anna",), "en": ("Daniel",), "fr": ("Eddy (Français (France))", "Amélie"),
        "es": ("Mónica", "Paulina")}
ARRIVEE_D_ESSAI = ("Buongiorno, sono Giulia B.", "it")
ECRAN_DU_HALL = "/clinique/hall"


class VoixImpossible(RuntimeError):
    """La voix du Mac n'a pas pu dire la phrase. Le message dit pourquoi."""


def voix_disponible() -> tuple[bool, str]:
    if sys.platform != "darwin" or shutil.which("say") is None:
        return False, "la voix du Mac (« say ») n'est pas sur cet ordinateur"
    return True, ""


def baisser(son: str | Path, volume: float) -> Path:
    """Rendre un son (.wav, 16 bits) plus faible : chaque point du son est multiplié par `volume` (de 0 à 1)."""
    import array
    import wave

    if not 0 < volume <= 1:
        raise ValueError("le volume va de 0 à 1 (1 = la voix normale) : on ne parle jamais plus fort")
    if volume == 1:
        return Path(son)
    with wave.open(str(son), "rb") as lu:
        forme, points = lu.getparams(), array.array("h", lu.readframes(lu.getnframes()))
    if forme.sampwidth != 2:
        raise ValueError("ce son n'est pas en 16 bits")
    with wave.open(str(son), "wb") as ecrit:
        ecrit.setparams(forme)
        ecrit.writeframes(array.array("h", (int(p * volume) for p in points)).tobytes())
    return Path(son)


def dire(texte: str, langue: str, sortie: str | Path, haut_parleur: bool = False, volume: float = 1.0) -> Path:
    """La voix du Mac dit la phrase dans un fichier son (16 kHz). `haut_parleur` : le fichier est aussi joué tout haut.
    `volume` : de 0 à 1 (la carte de rôle du robot ; 1 = la voix normale). Le son du fichier est vraiment plus faible."""
    oui, raison = voix_disponible()
    if not oui:
        raise VoixImpossible(raison)
    sortie = Path(sortie)
    sortie.parent.mkdir(parents=True, exist_ok=True)
    for voix in VOIX.get(langue, ()):
        fait = subprocess.run(["say", "-v", voix, "-o", str(sortie), "--data-format=LEI16@16000", texte],
                              capture_output=True, text=True, timeout=60)
        if fait.returncode == 0 and sortie.exists() and sortie.stat().st_size > 1000:
            baisser(sortie, volume)
            if haut_parleur and shutil.which("afplay"):
                subprocess.run(["afplay", str(sortie)], capture_output=True, timeout=60)
            return sortie
    raise VoixImpossible(f"aucune voix du Mac pour la langue « {langue} »")


def _plan_b(raison: str) -> dict[str, Any]:
    return {"moyen": "écran", "raison": raison, "ou": ECRAN_DU_HALL,
            "dit": "Voix en panne : on passe à l'écran. La personne tape sa phrase sur l'écran du hall."}


def accueillir(accueil, son: str | Path, dossier: str | Path = DOSSIER_SONS, pannes=None, haut_parleur: bool = False,
               ecouter: Callable[..., dict[str, Any]] = ecoute.ecouter, parler: Callable[..., Path] = dire) -> dict[str, Any]:
    """Un son d'arrivée → ce que l'accueil a entendu, répondu et dit. Jamais une réponse sur une phrase pas comprise."""
    rien = {"entendu": None, "reponse": None, "son_de_la_reponse": None, "voix": None}
    if pannes is not None and pannes.active("micro_bruit"):
        return {**rien, "plan_b": _plan_b("le micro n'entend que du bruit (panne)")}
    try:
        entendu = ecouter(son, None)
    except Exception as erreur:  # modèle absent, outil absent, son illisible : la voix est en panne
        return {**rien, "plan_b": _plan_b(f"l'écoute ne marche pas ({erreur})")}
    if not entendu.get("texte", "").strip() or not any(c.isalpha() for c in entendu["texte"]):
        return {**rien, "entendu": entendu, "plan_b": _plan_b("rien n'a été compris dans ce son")}
    reponse = accueil.entendre(entendu["texte"])  # les mêmes règles que la phrase tapée : chambre, refus, appel d'un humain
    resultat = {"entendu": entendu, "reponse": reponse, "son_de_la_reponse": None, "voix": None, "plan_b": None}
    try:
        resultat["son_de_la_reponse"] = str(parler(reponse["dit"], reponse["langue"],
                                                   Path(dossier) / f"reponse_{reponse['langue']}.wav", haut_parleur))
        resultat["voix"] = "voix du Mac (synthèse)"
    except Exception as erreur:  # la voix du Mac ne marche pas : la réponse s'affiche, c'est tout
        resultat["plan_b"] = {"moyen": "écran", "raison": f"la voix ne marche pas ({erreur})", "ou": ECRAN_DU_HALL,
                              "dit": "Voix en panne : la réponse s'affiche à l'écran."}
    return resultat


def _accueil_neuf():
    """Un accueil du hall neuf, comme dans la répétition (faux dossier, carnet en mémoire, aucun robot)."""
    from fastapi import FastAPI

    from .carnet import Carnet
    from .ecrans import brancher_ecrans
    from .horloge import HorlogeDeDemonstration
    from .porte import JournalDesAcces, PorteDeLecture

    horloge = HorlogeDeDemonstration()
    clinique = brancher_ecrans(FastAPI(), porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour),
                               horloge=horloge, carnet=Carnet(horloge=horloge), code_equipe="")
    return clinique


def essai(dossier: str | Path = DOSSIER_SONS, haut_parleur: bool = False) -> dict[str, Any]:
    """L'arrivée du scénario, dite par la voix du Mac dans un fichier, puis toute la boucle."""
    texte, langue = ARRIVEE_D_ESSAI
    arrivee = dire(texte, langue, Path(dossier) / "arrivee_d_essai.wav")
    clinique = _accueil_neuf()
    resultat = accueillir(clinique.accueil, arrivee, dossier, haut_parleur=haut_parleur)
    return {**resultat, "arrivee_dite": texte, "son_de_l_arrivee": str(arrivee), "clinique": clinique}


def main(reste: list[str] | None = None, ecrire: Callable[[str], None] = print) -> int:
    p = argparse.ArgumentParser(prog="lancer.py accueil-voix", description="La clinique en boîte : l'accueil du hall, à la voix")
    p.add_argument("son", nargs="?", help="un enregistrement (.wav) d'une arrivée")
    p.add_argument("--essai", action="store_true", help="l'arrivée en italien, dite par la voix du Mac")
    p.add_argument("--haut-parleur", action="store_true", help="dire la réponse tout haut, en plus du fichier")
    a = p.parse_args(reste or [])
    if not a.essai and not a.son:
        ecrire("Donner un enregistrement (.wav), ou --essai.")
        return 2
    try:
        if a.essai:
            r = essai(haut_parleur=a.haut_parleur)
            ecrire(f"L'ACCUEIL À LA VOIX — essai — l'arrivée est dite par la VOIX DE SYNTHÈSE du Mac, pas par une personne : « {r['arrivee_dite']} »")
        else:
            r = accueillir(_accueil_neuf().accueil, a.son, haut_parleur=a.haut_parleur)
            ecrire("L'ACCUEIL À LA VOIX — un enregistrement")
    except VoixImpossible as erreur:
        ecrire(f"Voix indisponible : {erreur}. Plan B : la phrase se tape sur l'écran du hall ({ECRAN_DU_HALL}).")
        return 2
    if r["entendu"]:
        ecrire(f"entendu ({r['entendu']['outil']}, {r['entendu']['duree_s']} s) : « {r['entendu']['texte']} »")
    if r["reponse"]:
        rep = r["reponse"]
        ecrire(f"cas : {rep.get('cas')} ; langue reconnue : {rep.get('langue')}")
        ecrire(f"réponse : « {rep.get('dit')} »")
        chemin = " → ".join(pas["lieu"] for pas in rep.get("chemin") or [])
        ecrire(f"le chemin (écrit ici ; aucun écran n'est ouvert par cette commande) : {chemin or 'aucun'}")
        if r["son_de_la_reponse"]:
            ecrire(f"réponse dite par la {r['voix']} : {r['son_de_la_reponse']}")
    if r["plan_b"]:
        ecrire(f"PLAN B — {r['plan_b']['dit']} ({r['plan_b']['raison']}) → {r['plan_b']['ou']}")
    ecrire("Étiquettes : l'écoute et la voix sont de vrais outils (RÉEL) ; il n'y a ni micro en direct ni robot (SIMULÉ).")
    return 0 if r["reponse"] and not r["plan_b"] else 1
