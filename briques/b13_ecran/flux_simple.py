"""Brique 13 — Le flux simplifié : une petite ligne par événement (pour le motion design et l'écran du jury).

    {"numero": 42, "heure": "2026-11-14T10:02:03.120+00:00", "heure_locale": "11:02:03", "type": "reponse_dite",
     "langue": "fr", "texte": "Je vais à : cuisine.", "picto": "aller", "conversation": "3f9c0a1b2c", "robot": "humanoide"}

`picto` est un nom de la liste PICTOS (les mêmes dessins que la page /jury, `<symbol id="p-NOM">`), ou "" si aucun.
Fonctionne sur l'événement en JSON (comme dans /ws, /api/flux et les journaux de la boîte noire).
Voir FLUX_POUR_MOTION_DESIGN.md.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

# Les pictogrammes : nom → ce qu'il veut dire. Les sept grandes situations d'abord.
PICTOS: dict[str, str] = {
    "aller": "le robot se déplace",
    "prendre": "le robot prend un objet",
    "regarder": "le robot regarde",
    "refus": "le robot refuse (et dit pourquoi)",
    "question": "le robot pose une question",
    "arret": "arrêt (stop ou arrêt d'urgence)",
    "aide": "le robot a besoin d'un humain",
    "poser": "le robot pose un objet",
    "montrer": "le robot montre quelque chose",
    "geste": "le robot fait un geste",
    "etat": "le robot dit son état (batterie)",
    "entendu": "le robot a entendu une personne",
    "compris": "le robot a compris",
    "parle": "le robot parle",
    "fait": "c'est fait, réussi",
    "rate": "raté",
    "panne": "panne",
    "internet": "Internet coupé (tout continue)",
    "silence": "mode silence (sous-titres seulement)",
}

PICTO_ACTION = {"se_deplacer": "aller", "saisir": "prendre", "poser": "poser", "regarder": "regarder",
                "montrer": "montrer", "rejouer_geste": "geste", "arreter": "arret", "etat": "etat",
                "ecouter": "entendu", "parler": "parle"}

TEXTE_MAX = 160


def _action(d: dict) -> dict:
    a = d.get("action")
    return a if isinstance(a, dict) else {}


def _picto_action(d: dict) -> str:
    return PICTO_ACTION.get(_action(d).get("nom", ""), "")


def _codes(d: dict) -> str:
    return ", ".join(str(r.get("code", "?")) for r in d.get("raisons") or [] if isinstance(r, dict))


def _resume_action(a: dict) -> str:
    if not a:
        return ""
    p = a.get("parametres") or {}
    morceaux = [f"{k}={v}" for k, v in p.items() if v not in (None, "")]
    return a.get("nom", "?") + (f" ({', '.join(morceaux)})" if morceaux else "")


def picto(e: dict) -> str:
    t, d = e.get("type"), e.get("donnees") or {}
    if t in ("parole_entendue", "transcription", "mot_d_appel", "interruption", "parole_finie"):
        return "entendu"
    if t == "demande_comprise":
        genre = d.get("genre")
        if genre == "action":
            return _picto_action(d) or "compris"
        if genre == "confirmation":
            return (_picto_action(d) or "compris") if d.get("confirme") else "parle"
        return {"question": "question", "inconnu": "question", "hors_carte": "refus", "discussion": "parle"}.get(genre, "")
    if t == "gardien_decision":
        return {"non": "refus", "humain": "aide"}.get(d.get("verdict"), _picto_action(d) or "compris")
    if t in ("question_posee", "confirmation_demandee"):
        return "question"
    if t in ("aide_demandee", "pilotage_humain"):
        return "aide"
    if t == "action_demarree":
        return _picto_action(d)
    if t == "action_terminee":
        return {"reussie": "fait", "annulee": "arret"}.get(d.get("statut"), "rate")
    if t == "action_refusee":
        return "refus"
    if t == "reponse_dite":
        genre = d.get("genre")
        if genre == "refus":
            return "refus"
        if genre == "question":
            return "question"
        if genre == "fin":
            return "fait" if d.get("statut") == "reussie" else "rate"
        cle = str(d.get("cle") or "")
        if genre == "annonce" and cle.startswith("annonce."):
            nom = cle.split(".", 1)[1].replace("se_deplacer_relatif", "se_deplacer")
            return PICTO_ACTION.get(nom, "parle")
        return "parle"
    if t in ("voix_debut",):
        return "parle"
    if t == "arret_urgence":
        return "arret"
    if t == "panne":
        return "panne"
    if t == "reparation":
        return "fait"
    if t == "internet_coupe":
        return "internet"
    if t == "mode_silence":
        return "silence"
    return ""


def texte_court(e: dict) -> str:
    t, d = e.get("type"), e.get("donnees") or {}
    if t in ("parole_entendue", "transcription", "mot_d_appel", "reponse_dite", "note"):
        texte = d.get("texte") or ""
    elif t in ("question_posee", "confirmation_demandee"):
        texte = d.get("question") or ""
    elif t == "demande_comprise":
        genre = d.get("genre", "?")
        if genre == "confirmation":
            texte = f"réponse à la question : {'oui' if d.get('confirme') else 'non'}"
        else:
            texte = f"compris : {genre}" + (f" — {_resume_action(_action(d))}" if _action(d) else "")
    elif t == "gardien_decision":
        texte = f"gardien : {d.get('verdict')}" + (f" ({_codes(d)})" if _codes(d) else "")
    elif t == "action_demarree":
        texte = f"démarre : {_resume_action(_action(d))}"
    elif t == "action_progression":
        p = d.get("progression")
        texte = f"{round(float(p) * 100)} %" if isinstance(p, (int, float)) else ""
    elif t == "action_terminee":
        texte = f"{d.get('statut')}" + (f" : {d['message']}" if d.get("message") else "")
    elif t == "action_refusee":
        texte = f"la prise refuse ({_codes(d)})"
    elif t == "aide_demandee":
        texte = str(d.get("texte") or d.get("raison") or d.get("question") or "aide demandée")
    elif t == "arret_urgence":
        texte = f"ARRÊT D'URGENCE ({d.get('raison')})"
    elif t == "panne":
        texte = f"panne : {d.get('quoi')}" + (" (entraînement)" if d.get("provoquee") else "")
    elif t == "reparation":
        texte = f"réparé : {d.get('quoi')}"
    elif t == "internet_coupe":
        texte = "Internet coupé — tout continue" if d.get("coupe") else "Internet rétabli"
    elif t == "mode_silence":
        texte = "mode silence : sous-titres seulement" if d.get("actif") else "mode silence arrêté : la voix revient"
    elif t == "voix_debut":
        texte = "voix" + (f" : {d['latence_ms']} ms après la fin de la phrase" if d.get("latence_ms") is not None else "")
        if d.get("sous_titres_seulement"):
            texte += " (sous-titres seulement)"
    elif t == "interruption":
        texte = "interruption : le robot se tait"
    elif t == "parole_finie":
        texte = f"fin de phrase ({d.get('duree_s')} s)"
    elif t == "cerveau_secours":
        texte = f"cerveau : {d.get('de')} → {d.get('vers')} ({d.get('raison')})"
    elif t == "cerveau_serveur":
        texte = f"cerveau de secours {'lancé' if d.get('quoi') == 'lance' else 'arrêté'} ({d.get('raison') or ''})".replace(" ()", "")
    elif t == "session_debut":
        texte = f"début : {e.get('robot') or ''} — {d.get('mention') or ''}".strip(" —")
    elif t == "session_fin":
        texte = "fin de la session"
    elif t == "pilotage_humain":  # brique 11
        qui = d.get("qui") or d.get("operateur") or ""
        texte = {"reprise": f"un humain prend la main : {qui}", "rendu": f"l'humain rend la main : {qui}",
                 "ordre": f"ordre de l'humain ({qui}) : {_resume_action(_action(d))}",
                 "demande": "le chef de démonstration demande qu'un humain prenne la main",
                 "demande_retiree": f"demande retirée : {d.get('raison') or ''}"}.get(d.get("quoi"),
                                                                                    f"pilotage humain : {d.get('quoi', '')}")
    elif t == "regle_changee":
        texte = f"règle changée : {d.get('regle') or d.get('texte') or ''}"
    elif t == "etat_robot":
        texte = f"batterie {d.get('batterie_pct', '?')} %"
    else:
        texte = ""
    texte = " ".join(str(texte).split())
    return texte if len(texte) <= TEXTE_MAX else texte[: TEXTE_MAX - 1] + "…"


def langue(e: dict) -> str | None:
    d = e.get("donnees") or {}
    return d.get("langue") or d.get("langue_entendue") or None


def heure_locale(iso: str | None) -> str:
    try:
        return datetime.fromisoformat(str(iso)).astimezone().strftime("%H:%M:%S")
    except ValueError:
        return ""


def ligne_simple(e: dict) -> dict:
    """L'événement (en JSON) → une ligne courte : heure, type, langue, texte court, pictogramme."""
    return {"numero": e.get("numero"), "heure": e.get("heure"), "heure_locale": heure_locale(e.get("heure")),
            "type": e.get("type"), "langue": langue(e), "texte": texte_court(e), "picto": picto(e),
            "conversation": e.get("conversation"), "robot": e.get("robot"), "id": e.get("id")}


def filtre(types: str = "", sans: str = ""):
    """types="reponse_dite,parole_entendue" : seulement ceux-là ; sans="action_progression" : tous sauf ceux-là."""
    garder = {t.strip() for t in types.split(",") if t.strip()}
    enlever = {t.strip() for t in sans.split(",") if t.strip()}

    def accepte(e: dict) -> bool:
        t = e.get("type")
        return (not garder or t in garder) and t not in enlever

    return accepte
