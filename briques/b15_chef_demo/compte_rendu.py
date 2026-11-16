"""Brique 15 — Le compte rendu d'une répétition (Markdown) : chronomètre, ce qui a marché, ce qui a raté,
quel plan B a servi, combien de temps. Écrit dans mesures/ (hors du dépôt) ou dans le dossier choisi.
Tous les chiffres viennent de la répétition elle-même : rien n'est estimé.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from pathlib import Path

from .chef import CAUSES, ResultatScenario

RACINE = Path(__file__).resolve().parents[2]
DOSSIER_DEFAUT = RACINE / "mesures"
MOTS = {"reussie": "✔ réussie", "rattrapee": "✔ rattrapée (plan B)", "ratee": "✘ ratée", "sautee": "↷ sautée",
        "interrompue": "🛑 interrompue", "ignoree": "· ignorée"}
MOTS_PLAN_B = {"reussi": "✔", "rate": "✘", "saute": "↷", "inutile": "inutile"}


def _s(secondes: float | None, chiffres: int = 2) -> str:
    return "—" if secondes is None else f"{secondes:.{chiffres}f}".replace(".", ",")


def _cellule(texte: str) -> str:
    return texte.replace("|", "/").replace("\n", " ")


def _en_retard(e) -> bool:
    return e.resultat == "reussie" and e.limite_s is not None and e.duree_s > e.limite_s


def _plans(e) -> str:
    morceaux = []
    for p in e.plans_b:
        if p.resultat == "inutile":
            continue
        morceaux.append(f"{p.moyen}{' (préventif)' if p.preventif else ''} {MOTS_PLAN_B.get(p.resultat, p.resultat)}")
    return " → ".join(morceaux) or "—"


def texte(res: ResultatScenario) -> str:
    acc = res.acceleration
    lignes = [f"# Répétition — {res.titre}", ""]
    lignes += [
        f"- **{res.mention}** · robot : {res.robot} · cerveau : {res.cerveau} · le {res.debut}",
        f"- Scénario : `{res.fichier or '(en mémoire)'}` · {res.nb_etapes} étapes · opérateur : {res.operateur}",
    ]
    if acc != 1:
        lignes.append(f"- **Accéléré ×{acc:g}** : le faux robot et les pauses vont {acc:g} fois plus vite. "
                      "Les temps ci-dessous ne sont PAS ceux d'une vraie démonstration : répéter à ×1 pour les connaître.")
    if res.pannes:
        pannes = ", ".join(f"{nom}@{num}" for num, nom in sorted(res.pannes.items()))
        lignes.append(f"- Pannes provoquées : {pannes}" + (f" (mode pagaille, graine {res.graine})" if res.graine is not None else ""))
    else:
        lignes.append("- Pannes provoquées : aucune (hors étapes « provoquer_panne » du scénario)")
    visee = f" (visée : {res.duree_visee_s:g} s à vitesse normale)" if res.duree_visee_s else ""
    lignes.append(f"- **Durée totale mesurée : {_s(res.duree_s)} s**{visee}")
    lignes.append(f"- Résultat : {res.compter('reussie')} réussies du premier coup, {res.compter('rattrapee')} rattrapées "
                  f"par un plan B, {res.compter('ratee')} ratées, {res.compter('sautee')} sautées, "
                  f"{len(res.etapes)} jouées sur {res.nb_etapes}.")
    if res.interrompu:
        lignes.append(f"- **Interrompu : {res.interrompu}.** Les étapes suivantes n'ont pas été jouées.")
    lignes += ["", "## Chronomètre", "",
               "| # | Étape | Quoi | Résultat | Plan B | Temps (s) | Limite (s) | Détail |",
               "|---|---|---|---|---|---|---|---|"]
    for e in res.etapes:
        detail = e.detail if e.resultat != "reussie" else ""
        if _en_retard(e):
            detail = "fini, mais après la limite"
        if e.panne:
            detail = f"panne {e.panne} : {e.panne_detail}" + (f" · {detail}" if detail else "")
        lignes.append(f"| {e.numero} | {_cellule(e.nom)} | {e.genre} | {MOTS.get(e.resultat, e.resultat)} | {_plans(e)} | "
                      f"{_s(e.duree_s, 3)} | {_s(e.limite_s)} | {_cellule(detail)} |")
    total_etapes = sum(e.duree_s for e in res.etapes)
    lignes += ["", f"Somme des temps d'étape : {_s(total_etapes)} s ; le reste du total, ce sont les pauses du scénario "
               "(`pause_apres_s`, divisées par l'accélération)."]

    rates = [e for e in res.etapes if e.resultat in ("ratee", "rattrapee", "sautee", "interrompue")]
    lignes += ["", "## Ce qui a raté", ""]
    if not rates:
        lignes.append("Rien : toutes les étapes jouées ont réussi du premier coup.")
    lentes = [e for e in res.etapes if _en_retard(e)]
    if lentes:
        lignes.append("- Réussies, mais après leur limite : " + ", ".join(
            f"{e.numero} « {e.nom} » ({_s(e.duree_s)} s > {_s(e.limite_s)} s)" for e in lentes))
    for e in rates:
        cause = CAUSES.get(e.cause or "", e.cause or "?")
        lignes.append(f"- Étape {e.numero} « {e.nom} » ({cause}) : {e.detail or '—'}")
        if e.attendu:
            lignes.append(f"  - attendu : {e.attendu}")
        for p in e.plans_b:
            lignes.append(f"  - plan B {p.moyen} : {MOTS_PLAN_B.get(p.resultat, p.resultat)} — {p.detail}"
                          + (f" ({_s(p.duree_s)} s)" if p.resultat != "inutile" else ""))
        lignes.append(f"  - résultat : {MOTS.get(e.resultat, e.resultat)}")

    lignes += ["", "## Plans B utilisés", ""]
    compte: dict[str, list[int]] = {}
    for e in res.etapes:
        for p in e.plans_b:
            if p.resultat != "inutile":
                c = compte.setdefault(p.moyen, [0, 0])
                c[0] += 1
                c[1] += p.resultat == "reussi"
    if not compte:
        lignes.append("Aucun.")
    for moyen, (n, ok) in sorted(compte.items()):
        lignes.append(f"- {moyen} : {n} fois, dont {ok} réussi(s)")
    preventifs = [p for e in res.etapes for p in e.plans_b if p.preventif]
    if preventifs:
        lignes.append("- « préventif » : le cerveau est passé au secours pendant une étape réussie ; le chef est passé "
                      "en mode local pour la suite.")

    if res.fiche is not None:
        f = res.fiche
        lignes += ["", "## Fiche de vérité de cette répétition", "",
                   "| Mention | Demandes | Réussites | Ratés | Annulées | Refus du gardien | Questions | Plans B (réussis) "
                   "| Part de l'humain | Arrêts d'urgence | Pannes provoquées |",
                   "|---|---|---|---|---|---|---|---|---|---|---|",
                   f"| {f.mention} | {f.demandes} | {f.reussites} | {f.rates} | {f.annulees} | {f.refus_gardien} | "
                   f"{f.questions_posees} | {f.plans_b} ({f.plans_b_reussis}) | {f.part_humain_pct:g} %"
                   + (f" (+ {f.part_humain_simulee_pct:g} % simulée)" if f.part_humain_simulee_pct else "") + " | "
                   f"{f.arrets_urgence} | {f.pannes_provoquees} |"]
    lignes += ["", f"_Compte rendu écrit par le chef de démonstration (brique 15). {res.mention.capitalize()}._", ""]
    return "\n".join(lignes)


def _nom_fichier(titre: str) -> str:
    t = unicodedata.normalize("NFKD", titre.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_")[:40] or "scenario"


def ecrire(res: ResultatScenario, dossier: str | Path | None = None) -> Path:
    dossier = Path(dossier) if dossier else DOSSIER_DEFAUT
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / f"repetition_{_nom_fichier(res.titre)}_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.md"
    n = 2
    while chemin.exists():
        chemin = chemin.with_name(f"{chemin.stem.rsplit('__', 1)[0]}__{n}.md")
        n += 1
    chemin.write_text(texte(res), encoding="utf-8")
    return chemin
