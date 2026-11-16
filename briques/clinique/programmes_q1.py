"""Écrire un petit programme pour le robot PrimeBot Q1, à coller à la main dans son application.

NON TESTÉ SUR VRAI ROBOT par notre système : notre système n'envoie RIEN au Q1. Il écrit un texte ; un humain le colle.

Le Q1 ne nous a pas ouvert de porte pour les développeurs. Mais son application accepte un programme en blocs, collé
sous forme de texte (JSON). Ce que l'équipe a vu le 15.11.2026, et rien de plus :
- le bloc `q1_tts` (dire un texte) : collé dans l'application, il fait dire « boulangerie » au robot ;
- le bloc `q1_action` (faire un geste du robot), avec un code : l'équipe a exporté le programme du geste « fist bump »
  (poing contre poing), code 3003 ;
- le bloc `wait_last_motion_completion` (attendre la fin du dernier geste, avec un délai de garde en secondes) : l'équipe
  l'a ajouté dans l'application le 15.11.2026 au soir, avec « 5 » secondes, pour que les gestes se suivent au lieu de
  partir tous ensemble (sans lui, le robot dansait dès le début). L'ordre vu marcher : dire, geste, attendre, dire…

Ce que cette pièce fait, et rien d'autre :
- elle fabrique un programme fait de ces deux blocs, dans la forme exacte des programmes vus ;
- un geste se demande par son NOM, et seuls les gestes de `GESTES_CONNUS` existent. Leurs numéros sont LUS dans le
  kit public du fabricant (fichier `aimdk_msgs/mc/motion/McPresetMotion.msg`, partie « Q », lu le 15.11.2026). Le
  3003 (« fist bump ») est le seul que l'équipe a vu marcher dans l'application ; les autres sont À VÉRIFIER SUR LE
  ROBOT : rien ne dit encore que l'application accepte les mêmes numéros. On n'invente ni un nom de bloc, ni un code ;
- elle refuse tout le reste (un texte vide, trop long, plus de dix étapes).

À vérifier sur le robot : plusieurs blocs à la suite (l'enchaînement « next » est la forme habituelle de ces programmes
en blocs, mais nous n'avons vu marcher que des programmes d'UN bloc) ; les langues que sa voix sait dire.

Usage :  python3 -m briques.clinique.programmes_q1 --nom bonjour "Buongiorno." "Sono qui per aiutarla."
         python3 -m briques.clinique.programmes_q1 --nom salut geste:fist_bump
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

BLOC_DIRE = "q1_tts"      # vu le 15.11.2026
BLOC_GESTE = "q1_action"  # vu le 15.11.2026
BLOC_ATTENDRE = "wait_last_motion_completion"  # vu le 15.11.2026, avec TIMEOUT_SECONDS « 5 » ; autres durées : à vérifier
ATTENTE_MAX_S = 60
# Les gestes prêts du Q1, numéros lus dans le kit public du fabricant (McPresetMotion.msg, partie « Q », 15.11.2026).
# VU MARCHER dans l'application : seulement « fist_bump » (exporté par l'équipe). Les autres : à vérifier sur le robot.
GESTES_VUS_MARCHER = frozenset({"fist_bump"})
GESTES_CONNUS = {
    "faire_signe": "3001",    # Q_BECKON (« wave » dans le kit)
    "serrer_la_main": "3002", # Q_SHAKE_HANDS
    "fist_bump": "3003",      # Q_BUMP_FISTS — poing contre poing, exporté par l'équipe : vu marcher
    "saluer": "3004",         # Q_WAVE_HAND
    "content": "3005",        # Q_SHOW_HAPPINESS
    "coeur": "3007",          # Q_MAKE_HEART — un cœur avec les deux mains
    "encourager": "3008",     # Q_CHEER_ON (« come on »)
    "s_etirer": "3010",       # Q_STRETCH
    "parler_a": "3012",       # Q_SPEAK_A — geste de quelqu'un qui parle
    "parler_b": "3013",       # Q_SPEAK_B
    "parler_c": "3014",       # Q_SPEAK_C
    "embrasser": "3018",      # Q_HUG (« embrace ») : PAS près d'une personne
    "refuser": "3021",        # Q_REFUSE (« reject »)
    "danse_a": "3046",        # Q_DANCE_A
    "danse_b": "3047",        # Q_DANCE_B
    "danse_c": "3048",        # Q_DANCE_C
}
PLACE = {BLOC_DIRE: (90, 130), BLOC_GESTE: (150, 150), BLOC_ATTENDRE: (150, 150)}  # la place du premier bloc sur la page, comme dans les programmes vus
ETAPES_MAX, LONGUEUR_MAX = 60, 200  # une scène d'une à deux minutes : dire, geste, attendre, une vingtaine de fois
PREFIXE_GESTE, PREFIXE_ATTENDRE = "geste:", "attendre:"
DOSSIER = Path(__file__).resolve().parents[2] / "mesures" / "q1"


class ProgrammeRefuse(ValueError):
    """Le programme demandé sort de ce que nous savons écrire sans rien inventer."""


def _bloc_dire(numero: int, texte: str) -> dict:
    return {"type": BLOC_DIRE, "id": f"tts{numero}",
            "inputs": {"TEXT": {"shadow": {"type": "text", "id": f"txt{numero}", "fields": {"TEXT": texte}}}}}


def _bloc_geste(numero: int, code: str) -> dict:
    return {"type": BLOC_GESTE, "id": f"act{numero}", "fields": {"ACTION_CODE": code}}


def programme(etapes: list[str], nom: str = "mira", maintenant_ms: int = 1794768936292) -> dict:
    """Un programme qui joue ces étapes, dans l'ordre. Une étape : une phrase à dire, « geste:NOM » (geste connu), ou
    « attendre:N » (attendre la fin du dernier geste, N secondes au plus)."""
    if not isinstance(etapes, (list, tuple)) or not 1 <= len(etapes) <= ETAPES_MAX:
        raise ProgrammeRefuse(f"il faut de 1 à {ETAPES_MAX} étapes")
    if not isinstance(nom, str) or not re.fullmatch(r"[a-z0-9_]([a-z0-9_ ]{0,28}[a-z0-9_])?", nom):
        raise ProgrammeRefuse("le nom du programme : minuscules, chiffres, « _ », espaces au milieu, 30 caractères au plus")
    blocs, dits, gestes, attentes = [], 0, 0, 0
    for etape in etapes:
        if not isinstance(etape, str) or not etape.strip() or len(etape.strip()) > LONGUEUR_MAX:
            raise ProgrammeRefuse(f"chaque étape est un texte de 1 à {LONGUEUR_MAX} caractères")
        if any(ord(c) < 32 for c in etape):
            raise ProgrammeRefuse("pas de caractère de commande dans une étape")
        etape = etape.strip()
        if etape.startswith(PREFIXE_GESTE):
            geste = etape[len(PREFIXE_GESTE):]
            if geste not in GESTES_CONNUS:
                raise ProgrammeRefuse(f"geste inconnu « {geste} » ; gestes connus : {', '.join(sorted(GESTES_CONNUS))}. "
                                      "Un numéro qui n'est pas dans le kit du fabricant n'est pas écrit")
            gestes += 1
            blocs.append(_bloc_geste(gestes, GESTES_CONNUS[geste]))
        elif etape.startswith(PREFIXE_ATTENDRE):
            secondes = etape[len(PREFIXE_ATTENDRE):]
            if not secondes.isdigit() or not 1 <= int(secondes) <= ATTENTE_MAX_S:
                raise ProgrammeRefuse(f"« attendre: » veut un nombre entier de secondes, de 1 à {ATTENTE_MAX_S}")
            attentes += 1
            blocs.append({"type": BLOC_ATTENDRE, "id": f"wait{attentes}", "fields": {"TIMEOUT_SECONDS": str(int(secondes))}})
        else:
            dits += 1
            blocs.append(_bloc_dire(dits, etape))
    for avant, apres in zip(blocs, blocs[1:]):
        avant["next"] = {"block": apres}  # l'enchaînement habituel des programmes en blocs : à vérifier sur le robot
    # Le premier bloc porte sa place sur la page (x, y), dans le MÊME ordre d'écriture que les programmes vus sur le robot.
    x, y = PLACE[blocs[0]["type"]]
    premier = {"type": blocs[0]["type"], "id": blocs[0]["id"], "x": x, "y": y,
               **{cle: valeur for cle, valeur in blocs[0].items() if cle not in ("type", "id")}}
    return {"schemaVersion": 1, "type": "qy_blockly_canvas",
            "canvas": {"name": nom, "robotTarget": "q1", "updatedAt": int(maintenant_ms),
                       "workspace": {"blocks": {"languageVersion": 0, "blocks": [premier]}}}}


def programme_parole(phrases: list[str], nom: str = "mira", maintenant_ms: int = 1794768936292) -> dict:
    """Un programme qui ne fait que DIRE ces phrases. Une phrase qui commence par « geste: » est refusée ici."""
    if isinstance(phrases, (list, tuple)) and any(isinstance(p, str) and p.strip().startswith((PREFIXE_GESTE, PREFIXE_ATTENDRE)) for p in phrases):
        raise ProgrammeRefuse("ce programme ne fait que parler : pas de geste ici")
    return programme(phrases, nom, maintenant_ms)


def en_texte(prog: dict) -> str:
    """Le texte à coller dans l'application, sur une seule ligne."""
    return json.dumps(prog, ensure_ascii=False, separators=(",", ":"))


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    nom = "mira"
    if arguments[:1] == ["--nom"] and len(arguments) >= 2:
        nom, arguments = arguments[1], arguments[2:]
    try:
        texte = en_texte(programme(arguments, nom))
    except ProgrammeRefuse as refus:
        print(f"  Refusé : {refus}. Rien n'a été écrit.")
        return 2
    DOSSIER.mkdir(parents=True, exist_ok=True)
    fichier = DOSSIER / f"{nom.replace(' ', '_')}.json"
    fichier.write_text(texte + "\n", encoding="utf-8")
    print(texte)
    print(f"\n  Écrit dans {fichier}. À COLLER À LA MAIN dans l'application du Q1 : notre système n'envoie rien au robot.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
