"""R2 — Apertus sur l'iMac : un essai du vrai modèle, mesuré.

    python3 lancer.py apertus-essai                     les 30 demandes du banc de l'ossature, en fr, de, it, en
    python3 lancer.py apertus-essai --langues fr --limite 5

- Le serveur du modèle est lancé par la pièce de l'ossature (brique 6, `ServeurModele`) : rien de neuf n'est installé.
  S'il tournait déjà, on ne le relance pas et on ne l'éteint pas. Sinon on l'éteint à la fin, même si l'essai casse.
- Les demandes et le jugement « bonne réponse » sont ceux du banc de l'ossature (`banc_cerveau`) : le faux humanoïde,
  le verrou des chiffres et le gardien. AUCUN VRAI ROBOT ne bouge : le cerveau est RÉEL, le robot est un FAUX ROBOT.
- Tous les chiffres sont calculés depuis les réponses. Rien n'est tapé. Si l'essai n'est pas possible : la raison, et
  aucun chiffre.
- Le résultat est écrit en haut de docs/projet/MESURE_APERTUS.md (le dernier essai seulement) ; la part « chaîne entière » (H07), plus bas, est gardée.
"""
from __future__ import annotations

import argparse
import statistics
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable

RACINE = Path(__file__).resolve().parents[2]
FICHIER = RACINE / "docs/projet/MESURE_APERTUS.md"
LANGUES = ["fr", "de", "it", "en"]
LIMITE_LENTE_MS = 5000  # Hiba, 12.11 : « dis-moi si une réponse met plus de cinq secondes »


def _pas_possible(raison: str) -> dict[str, Any]:
    return {"possible": False, "raison": raison, "quand": datetime.now().astimezone().isoformat(timespec="seconds")}


def _memoire_go(serveur) -> float | None:
    """La mémoire prise par le serveur que nous avons lancé (commande « ps », déjà sur le Mac). Sinon : pas mesuré."""
    proc = getattr(serveur, "proc", None)
    if proc is None:
        return None
    try:
        sortie = subprocess.run(["ps", "-o", "rss=", "-p", str(proc.pid)], capture_output=True, text=True, timeout=5).stdout
        return round(int(sortie.strip()) / 1024 / 1024, 2)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


async def essai(serveur, langues: list[str], mesurer: Callable[..., Awaitable[dict]] | None = None,
                demandes: list[dict] | None = None, cerveau: Any = None, limite: int | None = None,
                attente_s: float = 180) -> dict[str, Any]:
    if not Path(serveur.modele).exists():
        return _pas_possible(f"modèle absent ({serveur.modele})")
    deja = serveur.en_marche()
    if not deja and "llama-server" not in Path(serveur.commande()[0]).name:
        return _pas_possible("le programme llama-server n'est pas sur cet ordinateur (l'installer est un feu orange)")
    chargement_s = None
    if not deja:
        t0 = time.perf_counter()
        serveur.lancer()
        if not serveur.attendre(attente_s):
            serveur.eteindre()
            return _pas_possible(f"le serveur du modèle n'a pas démarré en {attente_s:.0f} secondes")
        chargement_s = round(time.perf_counter() - t0, 1)
    try:
        if mesurer is None or demandes is None or cerveau is None:
            from briques.b06_cerveau import banc_cerveau
            from briques.b06_cerveau.branchements.llm import CerveauLLM

            mesurer = mesurer or banc_cerveau.mesurer
            demandes = banc_cerveau.charger_demandes() if demandes is None else demandes
            if cerveau is None:
                cerveau = CerveauLLM(serveur.nom, serveur.url)
                try:  # la première demande met les consignes en mémoire : elle n'est pas comptée, et c'est dit
                    await cerveau.decider("Bonjour", "fr", *banc_cerveau._carte_monde())
                except Exception:
                    pass
        if limite:
            demandes = demandes[:limite]
        par = await mesurer(cerveau, demandes, langues)
        memoire = _memoire_go(serveur)
    except Exception as erreur:  # l'essai casse : on le dit, sans chiffre
        return _pas_possible(f"l'essai a cassé : {erreur.__class__.__name__}: {erreur}"[:200])
    finally:
        if not deja:
            serveur.eteindre()
        fermer = getattr(cerveau, "arreter", None)
        if fermer:
            try:
                await fermer()
            except Exception:
                pass
    lignes = [{**l, "langue": lg} for lg, v in par.items() for l in v["detail"]]
    if not lignes:
        return _pas_possible("aucune demande n'a été posée")

    def compte(ls: list[dict]) -> dict[str, Any]:
        temps = [l["ms"] for l in ls]
        return {"demandes": len(ls), "bonnes": sum(1 for l in ls if l["bon"] and not l.get("erreur")),
                "temps_median_ms": round(statistics.median(temps)), "temps_max_ms": round(max(temps)),
                "erreurs": sum(1 for l in ls if l.get("erreur"))}

    return {"possible": True, "quand": datetime.now().astimezone().isoformat(timespec="seconds"),
            "modele": Path(serveur.modele).name, "langues": list(par), "chargement_s": chargement_s, "memoire_go": memoire,
            **compte(lignes), "par_langue": {lg: compte([l for l in lignes if l["langue"] == lg]) for lg in par},
            "par_sorte": {c: compte([l for l in lignes if l["categorie"] == c]) for c in sorted({l["categorie"] for l in lignes})},
            "plus_de_5_s": [{"langue": l["langue"], "phrase": l["phrase"], "ms": round(l["ms"])} for l in lignes if l["ms"] > LIMITE_LENTE_MS],
            "mauvaises": [{"langue": l["langue"], "phrase": l["phrase"], "sorte": l["categorie"], "obtenu": l.get("action") or l.get("genre"),
                           "erreur": l.get("erreur")} for l in lignes if not l["bon"] or l.get("erreur")]}


def rapport(r: dict[str, Any]) -> list[str]:
    jour = datetime.fromisoformat(r["quand"]).strftime("%d.%m.%Y, %H h %M")
    if not r["possible"]:
        return [f"ESSAI D'APERTUS : PAS POSSIBLE — {jour}", f"Raison : {r['raison']}.", "Aucun chiffre : rien n'a été mesuré."]
    L = [f"ESSAI D'APERTUS — cerveau : RÉEL (vrai modèle) ; robot : FAUX ROBOT — {jour}",
         f"Modèle : {r['modele']}, sur cet ordinateur, Internet inutile. Le cerveau propose ; aucun vrai robot n'a bougé.",
         f"Demandes : celles du banc de l'ossature, en {', '.join(r['langues'])}. Une demande de mise en route n'est pas comptée.",
         (f"Temps de chargement du modèle : {r['chargement_s']} s." if r["chargement_s"] is not None
          else "Le serveur tournait déjà : temps de chargement : non mesuré.")
         + (f" Mémoire du serveur vue par « ps » : {r['memoire_go']} Go (la part chargée dans la puce graphique n'y est sans doute pas : à vérifier)." if r.get("memoire_go") else " Mémoire : non mesurée."),
         f"RÉSULTAT : {r['bonnes']} bonnes réponses sur {r['demandes']}. Temps médian {r['temps_median_ms']} ms ; "
         f"le plus long {r['temps_max_ms']} ms."]
    if r["erreurs"]:
        L.append(f"{r['erreurs']} fois, le modèle n'a pas répondu (panne, délai ou hors formulaire) : compté comme mauvaise réponse.")
    for lg, c in r["par_langue"].items():
        L.append(f"  - {lg} : {c['bonnes']} sur {c['demandes']} ; médian {c['temps_median_ms']} ms ; le plus long {c['temps_max_ms']} ms")
    for sorte, c in r["par_sorte"].items():
        L.append(f"  - sorte « {sorte} » : {c['bonnes']} sur {c['demandes']}")
    lentes = r["plus_de_5_s"]
    if lentes:
        L.append(f"{len(lentes)} réponse{'s' if len(lentes) > 1 else ''} de plus de 5 secondes :")
        L += [f"  - [{l['langue']}] « {l['phrase']} » : {l['ms']} ms" for l in lentes]
    else:
        L.append("Aucune réponse de plus de 5 secondes.")
    if r["mauvaises"]:
        L.append("Les mauvaises réponses, telles quelles :")
        L += [f"  - [{m['langue']}] ({m['sorte']}) « {m['phrase']} » → {m['erreur'] or m['obtenu']}" for m in r["mauvaises"]]
    L.append("« Bonne réponse » : jugée comme dans le banc de l'ossature, après le verrou des chiffres et le gardien. "
             "Les phrases ont été écrites par un agent, pas par des soignants.")
    return L


def ecrire(r: dict[str, Any], fichier: str | Path | None = None) -> Path:
    fichier = Path(fichier) if fichier else FICHIER
    # H07 : la part « chaîne entière » (chaine_mesure.py) est écrite plus bas dans le même fichier : on la garde
    from .chaine_mesure import TITRE

    ancien = fichier.read_text(encoding="utf-8") if fichier.exists() else ""
    suite = ("\n" + TITRE + ancien.split(TITRE, 1)[1]) if TITRE in ancien else ""
    fichier.write_text("# Mesure d'Apertus (dernier essai)\n\n" + "\n\n".join(l if not l.startswith("  - ") else l.strip()
                                                                              for l in rapport(r)) + "\n" + suite, encoding="utf-8")
    return fichier


def main(argv: list[str] | None = None) -> int:
    import asyncio

    from commun.systeme import charger_reglages, creer_serveurs

    p = argparse.ArgumentParser(prog="lancer.py apertus-essai")
    p.add_argument("--langues", default=",".join(LANGUES))
    p.add_argument("--limite", type=int, help="seulement les N premières demandes")
    p.add_argument("--serveur", default="apertus_8b")
    a = p.parse_args(argv)
    serveur = creer_serveurs(charger_reglages()).get(a.serveur)
    r = (asyncio.run(essai(serveur, a.langues.split(","), limite=a.limite)) if serveur
         else _pas_possible(f"pas de serveur « {a.serveur} » dans reglages.yaml"))
    for ligne in rapport(r):
        print(ligne)
    from . import mesures_cerveau  # T21 : gardé pour la fiche de vérité

    mesures_cerveau.noter("apertus_essai", {**r, "cerveau": "Apertus 8B" if r["possible"] else ""})
    print(f"Écrit dans {ecrire(r).name}")
    return 0 if r["possible"] else 2
