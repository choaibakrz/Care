"""T29 — Le rejeu autonome (cahier 5.11 ; avenant J03).

    python3 lancer.py rejeu-autonome [DOSSIER]

La commande joue la grande répétition, l'enregistre, puis écrit un dossier de pages simples qui la rejouent, sans
serveur, sans cerveau, sans robot : on ouvre `index.html` par un double-clic.
- En haut : « Rejeu d'une séance enregistrée le (date) — données inventées ».
- Dedans : les quatorze étapes (réussie ou ratée, l'étiquette, ce qui a été vu), la fiche de vérité, et la liste des
  moments de J03, chacun sur sa page avec ses quatre choses.
- Rien n'est chargé depuis l'extérieur : pas de programme, pas d'image, pas de police, pas de lien vers dehors.
- Le dossier ne contient que la séance : aucun chemin de nos ordinateurs (retiré avant d'écrire, puis vérifié), aucun
  code d'équipe, aucun autre fichier. `verifier(dossier)` le contrôle, et la commande refuse de finir si ça rate.
L'enregistrement : le temps de la répétition, on garde une copie de chaque événement publié sur un bus et de chaque
ligne écrite dans un carnet, sans rien changer à ce qu'ils font. Après, tout redevient comme avant.
Par défaut, le dossier va dans `journal/clinique/rejeu/` : ce dossier ne part jamais vers GitHub.
TU NE LE METS JAMAIS EN LIGNE : c'est Hiba qui décide.
"""
from __future__ import annotations

import html
import re
import shutil
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator

RACINE = Path(__file__).resolve().parents[2]
DOSSIER_DEFAUT = RACINE / "journal" / "clinique" / "rejeu"
RETIRE = "[chemin retiré]"
MODE_D_EMPLOI = ("Ouvrez index.html par un double-clic : il s’ouvre dans le navigateur, sans Internet et sans programme.\n"
                 "Les pages rejouent une répétition enregistrée : les étapes, la fiche de vérité, les moments marquants.\n"
                 "Données inventées. Gardez ce dossier à part : ne le mettez pas en ligne sans l’accord de Hiba.\n")

STYLE = ("body{font-family:system-ui,sans-serif;margin:0;background:#f6f7f9;color:#16181d;line-height:1.45}"
         ".bandeau{background:#16181d;color:#fff;padding:.6rem 1rem;font-weight:700}main{padding:1rem;max-width:72rem}"
         "table{border-collapse:collapse;width:100%;background:#fff}td,th{border:1px solid #d5d9df;padding:.3rem .5rem;"
         "text-align:left;vertical-align:top}article{background:#fff;border:1px solid #d5d9df;border-radius:.5rem;"
         "padding:.6rem .9rem;margin:.8rem 0}.ou{color:#44505c}.rate{color:#b00020;font-weight:700}a{color:#0b57d0}")


# ---------------------------------------------------------------------- l'enregistrement de la séance
@contextmanager
def enregistrer() -> Iterator[list[dict[str, Any]]]:
    """Le temps d'un bloc : une copie de chaque événement de bus et de chaque ligne de carnet, au format des moments."""
    from commun.bus import Bus

    from . import repetition
    from .carnet import Carnet

    entrees: list[dict[str, Any]] = []
    publier, ecrire = Bus.publier, Carnet.ecrire

    def etape() -> int | None:
        seance = repetition.SEANCE
        return None if seance is None else len(seance.issues) + 1

    async def publier_et_garder(self, ev):
        entrees.append({"heure": str(ev.heure), "origine": "boîte noire", "type": ev.type, "source": ev.source,
                        "donnees": dict(ev.donnees), "id": f"b{ev.numero}", "conversation": ev.conversation, "etape": etape()})
        return await publier(self, ev)

    def ecrire_et_garder(self, badge, genre, donnees, valide_par_un_humain):
        ligne = ecrire(self, badge, genre, donnees, valide_par_un_humain)
        entrees.append({"heure": str(ligne["quand"].get("reel", "")), "origine": "carnet", "type": ligne["genre"],
                        "source": ligne["qui"], "donnees": ligne["donnees"], "id": f"c{len(entrees) + 1}",
                        "conversation": None, "etape": etape()})
        return ligne

    Bus.publier, Carnet.ecrire = publier_et_garder, ecrire_et_garder
    try:
        yield entrees
    finally:
        Bus.publier, Carnet.ecrire = publier, ecrire


# ---------------------------------------------------------------------- « rien que la séance »
def _chemins_de_l_ordinateur() -> list[str]:
    import sys
    import tempfile

    vus = {str(RACINE), str(Path.home()), tempfile.gettempdir(), str(Path(tempfile.gettempdir()).resolve()), sys.prefix,
           str(Path(sys.executable).parent)}
    return sorted((c for c in vus if c and len(c) > 4), key=len, reverse=True)


CHEMIN_SEUL = re.compile(r"(?:/(?:Users|private|var/folders|tmp|home|Volumes|opt)/[^\s\"'<>«»)]*)|(?:[A-Za-z]:\\[^\s\"'<>]*)")


def _codes_secrets() -> list[str]:
    try:
        from commun.systeme import charger_reglages

        code = str((charger_reglages().get("ecran") or {}).get("code_equipe") or "")
    except Exception:  # noqa: BLE001 — sans réglages, rien à cacher
        code = ""
    return [code] if len(code) >= 3 else []


def nettoyer(texte: str) -> str:
    """Retire de ce texte les chemins de cet ordinateur et le code d'équipe."""
    for chemin in _chemins_de_l_ordinateur():
        texte = texte.replace(chemin, RETIRE)
    texte = CHEMIN_SEUL.sub(RETIRE, texte)
    for code in _codes_secrets():
        texte = texte.replace(code, "[code retiré]")
    return texte


def verifier(dossier: str | Path) -> list[str]:
    """Ce qui ne va pas dans un dossier de rejeu. Une liste vide : il ne contient que la séance, et rien ne vient de dehors."""
    dossier, problemes = Path(dossier), []
    for f in sorted(dossier.iterdir()):
        if f.is_dir() or not re.fullmatch(r"index\.html|moment_\d+\.html|LISEZ_MOI\.txt", f.name):
            problemes.append(f"un fichier qui n'est pas la séance : {f.name}")
            continue
        texte = f.read_text(encoding="utf-8")
        if any(c in texte for c in _chemins_de_l_ordinateur()) or CHEMIN_SEUL.search(texte):
            problemes.append(f"{f.name} : un chemin de cet ordinateur")
        if any(code in texte for code in _codes_secrets()):
            problemes.append(f"{f.name} : le code d'équipe")
        if re.search(r"https?:|<script|<link|<img|<iframe|@import|url\(|src=|fetch\(", texte, re.I):
            problemes.append(f"{f.name} : quelque chose est chargé depuis l'extérieur")
        for lien in re.findall(r'href="([^"]+)"', texte):
            if "/" in lien or not (dossier / lien).exists():
                problemes.append(f"{f.name} : un lien qui sort du dossier ({lien[:40]})")
    if not (dossier / "index.html").exists():
        problemes.append("pas de index.html")
    return problemes


# ---------------------------------------------------------------------- les pages
def _e(texte: Any) -> str:
    return html.escape(nettoyer(str(texte)), quote=True)


def _page(titre: str, quand: str, milieu: str) -> str:
    return ("<!doctype html><html lang='fr'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            f"<title>{_e(titre)}</title><style>{STYLE}</style></head><body>"
            f"<div class='bandeau'>Rejeu d’une séance enregistrée le {_e(quand)} — données inventées</div>"
            f"<main>{milieu}</main></body></html>")


def _dessiner_moment(m: dict[str, Any]) -> str:
    def liste(lignes: list[dict[str, str]]) -> str:
        if not lignes:
            return "<p class='ou'>Rien d’écrit dans ces dix secondes.</p>"
        return "<ul>" + "".join(f"<li>{_e(l['heure'])} — {_e(l['quoi'])} ({_e(l['origine'])})</li>" for l in lignes) + "</ul>"

    q = m["quatre"]
    return (f"<p><a href=\"index.html\">← Retour à la séance</a></p>"
            f"<article><h2>{_e(m['genre'])} — {_e(m['titre'])}</h2><p class='ou'>{_e(m['heure'])} (UTC) · {_e(m['origine'])}"
            f"{' · étape ' + _e(m['etape']) if m.get('etape') else ''}</p></article>"
            f"<article><h3>1. Ce que le système a vu ou entendu</h3><p>{_e(q['vu'])}</p></article>"
            f"<article><h3>2. Ce qu’il a décidé, et pourquoi</h3><p>{_e(q['decide'])}</p></article>"
            f"<article><h3>3. Ce qu’il a fait</h3><p>{_e(q['fait'])}</p></article>"
            f"<article><h3>4. Les dix secondes d’avant et d’après</h3><h4>Avant</h4>{liste(q['autour']['avant'])}"
            f"<h4>Après</h4>{liste(q['autour']['apres'])}</article>")


def _dessiner_index(seance, sortie: list[str], la_fiche: dict[str, Any], trouves: list[dict[str, Any]],
                    attrapees: dict[str, Any]) -> str:
    from .repetition import ETAPES

    rangs = ""
    for etape in ETAPES:
        issue = seance.issues.get(etape.numero, "manquante")
        r = seance.resultats.get(etape.numero)
        rangs += (f"<tr><td>{etape.numero}</td><td>{_e(etape.titre)}</td><td{' class=rate' if issue != 'reussie' else ''}>"
                  f"{'réussie' if issue == 'reussie' else _e(issue)}</td><td>{_e(r.etiquette if r else '—')}</td>"
                  f"<td>{_e(r.detail if r else 'pas de résultat')}</td></tr>")
    lignes = "".join(f"<tr><td><b>{_e(l['titre'])}</b></td><td>{_e(l['valeur'])}</td></tr>" for l in la_fiche["lignes"])
    moments = "".join(f"<li><a href=\"moment_{i}.html\">{_e(m['genre'])} — {_e(m['titre'])}</a> "
                      f"<span class='ou'>({_e(m['heure'][11:19])}{', étape ' + _e(m['etape']) if m.get('etape') else ''})</span></li>"
                      for i, m in enumerate(trouves, 1))
    fin = next((l for l in reversed(sortie) if l.startswith("RÉPÉTITION")), "RÉPÉTITION : pas de conclusion")
    return (f"<h1>La clinique en boîte — rejeu</h1><p><b>{_e(fin)}</b></p>"
            "<p class='ou'>Ces pages sont écrites une fois, après la répétition. Elles ne demandent rien à personne : pas de serveur, "
            "pas de cerveau, pas de robot. Gardez ce dossier à part : il n’est jamais mis en ligne sans l’accord de Hiba.</p>"
            "<p class='ou'>Les étiquettes : RÉEL (un vrai robot, une vraie personne) · FAUX ROBOT (le robot simulé de l’ossature) · "
            "SIMULÉ (dans l’ordinateur) · JOUÉ (une personne qui joue un rôle).</p>"
            f"<article><h2>Les étapes</h2><table><tr><th>N°</th><th>Ce qui est essayé</th><th>Issue</th><th>Étiquette</th>"
            f"<th>Ce qui a été vu</th></tr>{rangs}</table></article>"
            f"<article><h2>La fiche de vérité</h2><table>{lignes}</table></article>"
            f"<article><h2>Les moments</h2><p>{_e(attrapees['texte'])} (les erreurs attrapées).</p>"
            + (f"<ol>{moments}</ol>" if moments else "<p class='ou'>Aucun moment marquant dans cette séance.</p>")
            + "<p class='ou'>Un moment ne dit que ce qui a été écrit pendant la séance ; ce qui manque est écrit « pas noté "
              "dans la séance ».</p></article>")


# ---------------------------------------------------------------------- la commande
def fabriquer(dossier: str | Path | None = None, ecrire: Callable[[str], None] = print) -> dict[str, Any]:
    from . import chef_clinique, fiche, moments, repetition

    quand = datetime.now()
    dossier = Path(dossier) if dossier else DOSSIER_DEFAUT / quand.strftime("%Y%m%d_%H%M%S")
    sortie: list[str] = []
    seances: list[repetition.Seance] = []
    with enregistrer() as entrees:
        code = chef_clinique.jouer(ecrire=sortie.append, garder=seances)
    seance = seances[0]
    la_fiche = fiche.fiche_de_la_repetition(seance)
    entrees.sort(key=lambda e: e["heure"])
    trouves = moments.moments(entrees)
    for m in trouves:
        m["etape"] = next((e.get("etape") for e in entrees if e["id"] == m["id"]), None)
    attrapees = moments.erreurs_attrapees(trouves)
    texte_quand = quand.strftime("%d.%m.%Y à %-H h %M")
    if dossier.exists():
        shutil.rmtree(dossier)
    dossier.mkdir(parents=True)
    (dossier / "index.html").write_text(_page("Rejeu de la séance", texte_quand,
                                              _dessiner_index(seance, sortie, la_fiche, trouves, attrapees)), encoding="utf-8")
    for i, m in enumerate(trouves, 1):
        (dossier / f"moment_{i}.html").write_text(_page(f"Moment {i}", texte_quand, _dessiner_moment(m)), encoding="utf-8")
    (dossier / "LISEZ_MOI.txt").write_text(MODE_D_EMPLOI, encoding="utf-8")
    problemes = verifier(dossier)
    bilan = {"dossier": dossier, "repetition": "RÉUSSIE" if code == 0 else "RATÉE", "moments": len(trouves),
             "entrees": len(entrees), "problemes": problemes, "reussi": not problemes}
    ecrire("LE REJEU AUTONOME — DONNÉES INVENTÉES")
    ecrire(f"  la répétition : {bilan['repetition']} ; enregistré : {len(entrees)} lignes (boîte noire et carnets) ; "
           f"{len(trouves)} moments ; {attrapees['texte']}")
    ecrire(f"  le dossier : {dossier}  ({len(list(dossier.iterdir()))} fichiers)")
    ecrire("  ouvrir : index.html, par un double-clic. Ne pas le mettre en ligne : c'est Hiba qui décide.")
    if problemes:
        ecrire("REJEU : RATÉ — " + " ; ".join(problemes))
    else:
        ecrire("  vérifié : rien n'est chargé de l'extérieur ; aucun chemin de cet ordinateur ; rien d'autre que la séance")
        ecrire("REJEU : PRÊT")
    return bilan


def main(reste: list[str] | None = None) -> int:
    reste = reste or []
    return 0 if fabriquer(reste[0] if reste else None)["reussi"] else 1
