"""H07 — La chaîne entière mesurée sur l'iMac : l'écoute, le vrai Apertus et la voix, ensemble (Hiba, 12.11.2026).

    python3 lancer.py chaine-mesure                douze phrases (fr, de, it, en), du son entendu au son de la réponse

Pour chaque phrase :
    un son (la phrase dite)  →  l'écoute (whisper.cpp, modèle « small »)  →  le texte entendu
    →  le cerveau (le vrai Apertus 8B, par le cerveau de l'ossature)  →  une décision
    →  la voix du Mac (« say ») fabrique le son de la réponse.
Le temps compté va de la fin de la phrase (le son est fini, l'écoute commence) au début de la réponse (le son de la
réponse est prêt à être joué). Le serveur d'Apertus reste chargé pendant toute la mesure : les trois pièces se
partagent la mémoire. La mémoire libre de l'ordinateur est relevée cinq fois par seconde.

DIRE VRAI :
- Les phrases sont dites par la VOIX DE SYNTHÈSE du Mac (pas par des personnes), sans bruit autour. Ce sont des ordres
  simples du banc de l'ossature. Les sons du dépôt (FLEURS) sont de longues phrases lues, pas des ordres : pas pris ici.
- AUCUN ROBOT : la décision du cerveau n'est envoyée à aucun robot, même faux. On mesure le temps et la mémoire.
- Pas de micro, pas de haut-parleur : des fichiers. Le temps d'attente du micro (savoir que la phrase est finie) n'est
  pas dans la mesure.
- « La mémoire manque » : règle écrite ici — moins de 1 Go libre vu pendant la mesure, ou la mémoire d'échange du
  disque qui grossit de plus de 0,5 Go.
"""
from __future__ import annotations

import argparse
import asyncio
import statistics
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable

RACINE = Path(__file__).resolve().parents[2]
FICHIER = RACINE / "docs/projet/MESURE_APERTUS.md"
TITRE = "## La chaîne entière : l'écoute, Apertus et la voix ensemble (dernière mesure)"
URL = "http://127.0.0.1:8089"
LIMITE_LENTE_MS = 5000
LIBRE_MINIMUM_GO, ECHANGE_EN_PLUS_GO = 1.0, 0.5
# Douze ordres simples, trois par langue. Écrits par l'agent ; allemand, italien, anglais : pas relus.
PHRASES = [("fr", "Va à la cuisine."), ("fr", "Regarde la table."), ("fr", "Arrête-toi."),
           ("de", "Geh zur Küche."), ("de", "Schau auf den Tisch."), ("de", "Bleib stehen."),
           ("it", "Vai in cucina."), ("it", "Guarda il tavolo."), ("it", "Fermati."),
           ("en", "Go to the kitchen."), ("en", "Look at the table."), ("en", "Stop.")]
D_ACCORD = {"fr": "D'accord.", "de": "In Ordnung.", "it": "Va bene.", "en": "All right."}
PARDON = {"fr": "Pardon, je n'ai pas compris.", "de": "Entschuldigung, ich habe nicht verstanden.",
          "it": "Scusi, non ho capito.", "en": "Sorry, I did not understand."}


def memoire_de_l_ordinateur() -> dict[str, float]:
    import psutil

    v, s = psutil.virtual_memory(), psutil.swap_memory()
    return {"disponible_go": round(v.available / 1e9, 2), "echange_go": round(s.used / 1e9, 2), "total_go": round(v.total / 1e9, 2)}


class _Releve:
    """Relève la mémoire pendant la mesure, cinq fois par seconde, dans un fil à part."""

    def __init__(self, memoire: Callable[[], dict[str, float]], pas_s: float = 0.2) -> None:
        self.memoire, self.pas_s, self.releves, self._fin = memoire, pas_s, [], threading.Event()
        self._fil = threading.Thread(target=self._tourner, daemon=True)

    def _tourner(self) -> None:
        while not self._fin.wait(self.pas_s):
            self.releves.append(self.memoire())

    def __enter__(self) -> "_Releve":
        self.avant = self.memoire()
        self.releves.append(self.avant)
        self._fil.start()
        return self

    def __exit__(self, *_: Any) -> None:
        self._fin.set()
        self._fil.join(timeout=2)
        self.releves.append(self.memoire())


async def mesurer(phrases: list[dict[str, Any]], ecouter: Callable[[Any, str], dict[str, Any]],
                  decider: Callable[[str, str], Awaitable[dict[str, Any]]], dire: Callable[[str, str, Any], Any],
                  dossier: str | Path, montre: Callable[[], float] = time.perf_counter,
                  memoire: Callable[[], dict[str, float]] = memoire_de_l_ordinateur, origine: str = "", plus: dict | None = None) -> dict[str, Any]:
    dossier, lignes = Path(dossier), []
    with _Releve(memoire) as releve:
        for p in phrases:
            ligne = {"id": p["id"], "langue": p["langue"], "dit": p["texte"], "entendu": None, "decision": None, "a_dire": None,
                     "ecoute_ms": None, "cerveau_ms": None, "voix_ms": None, "total_ms": None, "panne": None}
            t0 = montre()  # la phrase est finie : l'écoute commence
            try:
                etape = "écoute"
                ligne["entendu"] = (await asyncio.to_thread(ecouter, p["son"], p["langue"]))["texte"]
                t1 = montre()
                releve.releves.append(memoire())  # un relevé sûr après chaque étape, en plus du fil
                etape = "cerveau"
                decision = await decider(ligne["entendu"], p["langue"])
                t2 = montre()
                releve.releves.append(memoire())
                ligne["decision"], ligne["a_dire"] = decision["resume"], decision["a_dire"]
                etape = "voix"
                await asyncio.to_thread(dire, decision["a_dire"], p["langue"], dossier / f"reponse_{p['id']}.wav")
                t3 = montre()  # le son de la réponse est prêt : elle peut commencer
                ligne.update(ecoute_ms=round((t1 - t0) * 1000), cerveau_ms=round((t2 - t1) * 1000), voix_ms=round((t3 - t2) * 1000),
                             total_ms=round((t3 - t0) * 1000))
            except Exception as erreur:  # une pièce en panne : la phrase reste sans réponse, et c'est dit
                ligne["panne"] = f"{etape} : {type(erreur).__name__}: {erreur}"[:160]
            lignes.append(ligne)
    faites = [l for l in lignes if l["total_ms"] is not None]
    libres = [r["disponible_go"] for r in releve.releves]
    echange = max(r["echange_go"] for r in releve.releves) - releve.avant["echange_go"]
    mediane = lambda cle: round(statistics.median(l[cle] for l in faites)) if faites else None  # noqa: E731
    return {"possible": True, "quand": datetime.now().astimezone().isoformat(timespec="seconds"), "origine": origine, **(plus or {}),
            "phrases": lignes, "sans_reponse": len(lignes) - len(faites),
            "total_median_ms": mediane("total_ms"), "total_max_ms": max((l["total_ms"] for l in faites), default=None),
            "ecoute_median_ms": mediane("ecoute_ms"), "cerveau_median_ms": mediane("cerveau_ms"), "voix_median_ms": mediane("voix_ms"),
            "plus_de_5_s": [l for l in faites if l["total_ms"] > LIMITE_LENTE_MS],
            "memoire": {"total_go": releve.avant["total_go"], "avant_go": releve.avant["disponible_go"], "moins_de_libre_go": min(libres),
                        "echange_en_plus_go": round(echange, 2), "releves": len(libres),
                        "manque": min(libres) < LIBRE_MINIMUM_GO or echange > ECHANGE_EN_PLUS_GO}}


def rapport(r: dict[str, Any]) -> list[str]:
    jour = datetime.fromisoformat(r["quand"]).strftime("%d.%m.%Y, %H h %M")
    if not r["possible"]:
        return [f"LA CHAÎNE ENTIÈRE : PAS POSSIBLE — {jour}", f"Raison : {r['raison']}.", "Aucun chiffre : rien n'a été mesuré."]
    n, m = len(r["phrases"]), r["memoire"]
    L = [f"LA CHAÎNE ENTIÈRE — écoute, cerveau et voix ensemble, sur cet ordinateur — AUCUN ROBOT — {jour}",
         f"Les phrases : {r['origine']}. {n} phrases. La décision du cerveau n'est envoyée à aucun robot.",
         "Temps compté : de la fin de la phrase (l'écoute commence) au début de la réponse (le son de la réponse est prêt)."]
    if r.get("pieces"):
        L.append(f"Les pièces : {r['pieces']}.")
    if r["total_median_ms"] is not None:
        L.append(f"RÉSULTAT : de la fin de la phrase au début de la réponse, médian {r['total_median_ms']} ms ; le plus long {r['total_max_ms']} ms. "
                 f"Au milieu : écoute {r['ecoute_median_ms']} ms, cerveau {r['cerveau_median_ms']} ms, voix {r['voix_median_ms']} ms.")
    if r["sans_reponse"]:
        L.append(f"{r['sans_reponse']} phrase{'s' if r['sans_reponse'] > 1 else ''} sans réponse (une pièce en panne) : "
                 + " ; ".join(dict.fromkeys(l["panne"] for l in r["phrases"] if l["panne"])) + ".")
    lentes = r["plus_de_5_s"]
    if lentes:
        L.append(f"{len(lentes)} réponse{'s' if len(lentes) > 1 else ''} de plus de 5 secondes : "
                 + ", ".join(f"{l['id']} ({l['total_ms']} ms)" for l in lentes) + ".")
    elif r["total_median_ms"] is not None:
        L.append("Aucune réponse de plus de 5 secondes.")
    L.append(f"MÉMOIRE (ordinateur de {m['total_go']} Go) : libre au début de la mesure (Apertus déjà chargé), {m['avant_go']} Go ; le moins de libre vu pendant la mesure, "
             f"{m['moins_de_libre_go']} Go ; mémoire d'échange du disque en plus : {m['echange_en_plus_go']} Go ({m['releves']} relevés).")
    L.append("LA MÉMOIRE MANQUE (moins de 1 Go libre, ou plus de 0,5 Go d'échange en plus) : à décider, partager le travail avec le deuxième Mac."
             if m["manque"] else "La mémoire n'a pas manqué (règle : moins de 1 Go libre, ou plus de 0,5 Go d'échange en plus).")
    L.append("Phrase par phrase, tel quel :")
    for l in r["phrases"]:
        if l["panne"]:
            L.append(f"- {l['id']} [{l['langue']}] « {l['dit']} » → SANS RÉPONSE ({l['panne']})")
        else:
            L.append(f"- {l['id']} [{l['langue']}] dit « {l['dit']} » → entendu « {l['entendu']} » → {l['decision']} → réponse « {l['a_dire']} » — "
                     f"écoute {l['ecoute_ms']} ms, cerveau {l['cerveau_ms']} ms, voix {l['voix_ms']} ms, total {l['total_ms']} ms")
    L.append("Limites : la langue de chaque phrase est donnée à l'écoute (dans le hall, elle doit la deviner : plus lent, à mesurer) ; "
             "voix de synthèse sans bruit, pas de micro ni de haut-parleur, phrases courtes, un seul passage, aucun robot, "
             "les écrans de la clinique n'étaient pas ouverts.")
    return L


def ecrire(r: dict[str, Any], fichier: str | Path | None = None) -> Path:
    """Ajoute (ou remplace) la part « chaîne entière » de docs/projet/MESURE_APERTUS.md, sans toucher à ce qui est au-dessus."""
    fichier = Path(fichier) if fichier else FICHIER
    haut = fichier.read_text(encoding="utf-8").split(TITRE)[0].rstrip("\n") if fichier.exists() else "# Mesure d'Apertus"
    fichier.write_text(haut + "\n\n" + TITRE + "\n\n" + "\n\n".join(rapport(r)) + "\n", encoding="utf-8")
    return fichier


# ---------------------------------------------------------------------- avec les vraies pièces
def mesurer_pour_de_vrai(dossier: str | Path, limite: int | None = None, url: str = URL) -> dict[str, Any]:
    """Le serveur d'Apertus doit déjà tourner. Fabrique les phrases avec la voix du Mac, puis mesure."""
    from briques.b06_cerveau import banc_cerveau
    from briques.b06_cerveau.branchements.llm import CerveauLLM

    from . import accueil_voix, ecoute

    quand = datetime.now().astimezone().isoformat(timespec="seconds")
    for oui, raison in (ecoute.disponible(), accueil_voix.voix_disponible()):
        if not oui:
            return {"possible": False, "raison": raison, "quand": quand}
    dossier = Path(dossier)
    phrases = [{"id": f"{lg}{i}", "langue": lg, "texte": texte, "son": accueil_voix.dire(texte, lg, dossier / f"phrase_{lg}{i}.wav")}
               for i, (lg, texte) in enumerate(PHRASES[:limite] if limite else PHRASES, 1)]
    carte, monde = banc_cerveau._carte_monde()

    async def tout() -> dict[str, Any]:
        cerveau = CerveauLLM("apertus_8b", url)

        async def decider(texte: str, langue: str) -> dict[str, Any]:
            d = await cerveau.decider(texte, langue, carte, monde)
            if d.genre == "action" and d.action:
                return {"genre": "action", "resume": d.action.resume(), "a_dire": D_ACCORD[langue]}
            return {"genre": d.genre, "resume": f"{d.genre} : {d.question or d.texte or ''}"[:120], "a_dire": d.texte or PARDON[langue]}

        try:
            try:  # une première demande met les consignes en mémoire : elle n'est pas comptée
                await cerveau.decider("Bonjour", "fr", carte, monde)
            except Exception:
                pass
            return await mesurer(phrases, ecoute.ecouter, decider, accueil_voix.dire, dossier,
                                 origine="dites par la voix de synthèse du Mac (« say »), sans bruit, lues dans des fichiers",
                                 plus={"pieces": f"écoute : {ecoute.OUTIL} ; cerveau : RÉEL, Apertus 8B ; voix : « say » du Mac"})
        finally:
            await cerveau.arreter()

    return asyncio.run(tout())


def main(argv: list[str] | None = None) -> int:
    import tempfile

    from commun.systeme import charger_reglages, creer_serveurs

    p = argparse.ArgumentParser(prog="lancer.py chaine-mesure")
    p.add_argument("--limite", type=int, help="seulement les N premières phrases")
    a = p.parse_args(argv)
    serveur = creer_serveurs(charger_reglages()).get("apertus_8b")
    quand = datetime.now().astimezone().isoformat(timespec="seconds")
    if serveur is None or not Path(serveur.modele).exists():
        r = {"possible": False, "raison": "le modèle Apertus 8B n'est pas sur cet ordinateur", "quand": quand}
    else:
        deja = serveur.en_marche()
        if not deja:
            serveur.lancer()
        try:
            if deja or serveur.attendre(180):
                with tempfile.TemporaryDirectory() as dossier:
                    r = mesurer_pour_de_vrai(dossier, a.limite, serveur.url)
            else:
                r = {"possible": False, "raison": "le serveur du modèle n'a pas démarré", "quand": quand}
        finally:
            if not deja:
                serveur.eteindre()
    for ligne in rapport(r):
        print(ligne)
    from . import mesures_cerveau  # T21 : gardé pour la fiche de vérité

    mesures_cerveau.noter("chaine", r)
    print(f"Ajouté à {ecrire(r).name}")
    return 0 if r["possible"] else 2
