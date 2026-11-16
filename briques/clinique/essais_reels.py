"""Le compteur d'essais réels : l'équipe compte ce qu'un VRAI robot réussit ou rate (avenant jury, J01).

    /clinique/essais-reels                  la page de l'équipe : le robot, le geste, « réussi » ou « raté », une note
    POST /api/clinique/essais_reels         {robot, geste, reussi, note}   (code d'équipe demandé)

- Chaque appui est une ligne dans un fichier (journal/clinique/essais_reels.jsonl), avec l'heure. Ce dossier ne
  part pas vers GitHub.
- On ajoute, c'est tout : un essai compté ne s'efface pas et ne se corrige pas. Un échec se montre.
- La fiche de vérité affiche ces essais à part, avec l'étiquette RÉEL. Tant que rien n'est compté :
  « RÉEL : aucun essai compté ».
- SEULE L'ÉQUIPE COMPTE. Un agent d'IA n'écrit jamais un essai réel : il n'a pas vu le robot. Les boutons demandent
  le code d'équipe, comme les boutons protégés de l'écran de l'ossature (brique 13).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

FICHIER = Path(__file__).resolve().parents[2] / "journal" / "clinique" / "essais_reels.jsonl"
PROTOCOLE = Path(__file__).resolve().parents[2] / "docs/projet/PROTOCOLE_ESSAIS_REELS.md"  # avenant 2, K02 : la page à imprimer
ETIQUETTE = "RÉEL"
AUCUN = "RÉEL : aucun essai compté"


def _court(texte: Any, longueur: int) -> str:
    return " ".join(str(texte).split())[:longueur]


class CompteurReel:
    def __init__(self, fichier: str | Path | None = None) -> None:
        self.fichier = Path(fichier) if fichier else FICHIER

    def compter(self, robot: str, geste: str, reussi: bool, note: str = "", avec_aide: bool = False,
                plus: dict[str, Any] | None = None) -> dict[str, Any]:
        """Un appui de l'équipe : une ligne de plus, avec l'heure. Rien n'est jamais retiré.
        `avec_aide` (avenant 2, K02) : quelqu'un a touché le robot, l'objet ou le clavier. Raté reste raté."""
        robot, geste = _court(robot, 60), _court(geste, 80)
        if not robot or not geste:
            raise ValueError("il faut le nom du robot et le nom du geste")
        ligne = {"quand": datetime.now().astimezone().isoformat(timespec="seconds"), "robot": robot, "geste": geste,
                 "resultat": ("réussi avec aide" if avec_aide else "réussi") if reussi else "raté", "note": _court(note, 120), "etiquette": ETIQUETTE,
                 **(plus or {})}  # `plus` : l'épreuve des étagères ajoute son numéro, et « RÉEL · TÉLÉCOMMANDÉ » (avenant 3, M02)
        return self._ajouter(ligne)

    def noter(self, evenement: str, **donnees: Any) -> dict[str, Any]:
        """Une ligne qui n'est pas un essai (départ, aide, arrêt, annulation d'une épreuve) : écrite avec l'heure, jamais comptée."""
        return self._ajouter({"quand": datetime.now().astimezone().isoformat(timespec="seconds"), "evenement": evenement, **donnees})

    def _ajouter(self, ligne: dict[str, Any]) -> dict[str, Any]:
        self.fichier.parent.mkdir(parents=True, exist_ok=True)
        with open(self.fichier, "a", encoding="utf-8") as f:
            f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
        return ligne

    def _lire(self) -> tuple[list[dict[str, Any]], int]:
        if not self.fichier.exists():
            return [], 0
        lignes, illisibles, annules = [], 0, set()
        for brute in self.fichier.read_text(encoding="utf-8").splitlines():
            if not brute.strip():
                continue
            try:
                ligne = json.loads(brute)
                if isinstance(ligne, dict) and "evenement" in ligne:  # pas un essai : un départ, une aide, une annulation…
                    if ligne["evenement"] == "annulation" and ligne.get("annule"):
                        annules.add(ligne["annule"])
                    continue
                if not isinstance(ligne, dict) or ligne.get("resultat") not in ("réussi", "réussi avec aide", "raté"):
                    raise ValueError
                lignes.append(ligne)
            except ValueError:
                illisibles += 1  # une ligne abîmée se compte et se dit ; elle ne bloque pas la lecture
        # un appui annulé (erreur de doigt) ne compte plus ; il reste écrit dans le fichier, avec son annulation
        return [l for l in lignes if l.get("id") not in annules], illisibles

    def lignes(self) -> list[dict[str, Any]]:
        return self._lire()[0]

    def resume(self) -> dict[str, Any]:
        """Ce que la fiche de vérité affiche : calculé depuis le fichier, jamais tapé."""
        lignes, illisibles = self._lire()
        reussis = sum(1 for l in lignes if l["resultat"] == "réussi")
        groupes: dict[tuple[str, str], list[int]] = {}
        for l in lignes:
            compte = groupes.setdefault((str(l.get("robot", "?")), str(l.get("geste", "?"))), [0, 0])
            compte[0] += l["resultat"] == "réussi"
            compte[1] += 1
        avec_aide = sum(1 for l in lignes if l["resultat"] == "réussi avec aide")
        texte = f"RÉEL : {reussis} sur {len(lignes)}" if lignes else AUCUN
        if avec_aide:  # à part : un essai réussi avec aide n'est pas un essai réussi tout court
            texte += f" ; réussis avec aide : {avec_aide} sur {len(lignes)}"
        if illisibles:
            texte += f" ({illisibles} ligne{'s' if illisibles > 1 else ''} illisible{'s' if illisibles > 1 else ''} dans le fichier)"
        return {"etiquette": ETIQUETTE, "essais": len(lignes), "reussis": reussis, "avec_aide": avec_aide, "illisibles": illisibles, "texte": texte,
                "par_geste": [{"robot": r, "geste": g, "reussis": c[0], "essais": c[1]} for (r, g), c in groupes.items()],
                "premier": lignes[0]["quand"] if lignes else None, "dernier": lignes[-1]["quand"] if lignes else None}


# ---------------------------------------------------------------------- la page de l'équipe
class Essai(BaseModel):
    robot: Annotated[str, Field(max_length=120)]
    geste: Annotated[str, Field(max_length=160)]
    reussi: bool
    note: Annotated[str, Field(max_length=400)] = ""
    avec_aide: bool = False


SCRIPT = """<script>
async function compter(reussi, avec_aide = false) {
  const v = id => document.getElementById(id).value;
  const dit = document.getElementById('dit');
  const entetes = {'Content-Type': 'application/json'};
  if (v('code')) entetes['X-Code-Equipe'] = v('code');
  try {
    const r = await fetch('/api/clinique/essais_reels', {method: 'POST', headers: entetes,
      body: JSON.stringify({robot: v('robot'), geste: v('geste'), reussi, avec_aide, note: v('note')})});
    const j = await r.json();
    if (!r.ok) { dit.textContent = 'Refusé : ' + (j.detail || ''); return; }
    dit.textContent = 'Compté : ' + j.ligne.resultat + ' — ' + j.resume.texte;
    document.getElementById('note').value = '';
    const c = await fetch('/clinique/essais-reels/contenu', {cache: 'no-store'});
    document.getElementById('compte').innerHTML = await c.text();
  } catch (erreur) { dit.textContent = 'Connexion perdue : rien n\\'a été compté.'; }
}
document.getElementById('reussi').onclick = () => compter(true);
document.getElementById('rate').onclick = () => compter(false);
document.getElementById('aide').onclick = () => compter(true, true);
</script>"""


def dessiner_compte(compteur: CompteurReel) -> str:
    from .ecrans import _e

    resume, lignes = compteur.resume(), compteur.lignes()
    par_geste = "".join(f"<li><b>{_e(g['robot'])}</b> — {_e(g['geste'])} : {g['reussis']} sur {g['essais']}</li>"
                        for g in resume["par_geste"])
    dernieres = "".join(f"<li>{_e(l.get('quand', '?'))} — {_e(l.get('robot', '?'))} — {_e(l.get('geste', '?'))} — "
                        f"<b>{_e(l['resultat'])}</b>{' — ' + _e(l['note']) if l.get('note') else ''}</li>"
                        for l in reversed(lignes[-30:]))
    return (f"<p class='dit'>{_e(resume['texte'])}</p>"
            + (f"<article><h2>Par geste</h2><ul>{par_geste}</ul></article>" if par_geste else "")
            + (f"<article><h2>Les derniers essais (le plus récent en haut)</h2><ul>{dernieres}</ul></article>" if dernieres else ""))


def brancher_essais_reels(app: FastAPI, clinique, protege: list) -> None:
    from .ecrans import _heure_html, _page

    @app.get("/clinique/essais-reels", response_class=HTMLResponse)
    async def page_essais_reels():
        tete = f"<h1>Essais réels</h1><span class='heure' id='heure'>{_heure_html(clinique.horloge.etat())}</span>"
        milieu = ("<p class='ou'>Pour l'équipe, avec un <b>vrai robot</b>, pendant le hackathon. Un appui = un essai, écrit "
                  "avec l'heure. On ne peut ni effacer ni corriger : un essai raté reste. Ces essais sont affichés à part, "
                  "avec l'étiquette <b>RÉEL</b>. Ne comptez jamais ici un essai fait sur le faux robot.</p>"
                  "<p><label>Robot <input id='robot' size='18' maxlength='60'></label> "
                  "<label>Geste <input id='geste' size='24' maxlength='80'></label></p>"
                  "<p><label>Note courte <input id='note' size='34' maxlength='120'></label></p>"
                  "<p><label>Code d'équipe (depuis un autre ordinateur) <input id='code' size='12' type='password' "
                  "autocomplete='off'></label></p>"
                  "<p><button id='reussi'>Réussi</button> <button id='aide'>Réussi avec aide</button> "
                  "<button id='rate'>Raté</button></p>"
                  "<p class='ou'>« Réussi avec aide » : quelqu'un a touché le robot, l'objet ou le clavier pendant l'essai. "
                  "<a href='/clinique/protocole-essais-reels'>Le protocole des essais réels (à imprimer)</a> · "
                  "<a href='/clinique/etageres'>L'épreuve des étagères (dix minutes)</a></p>"
                  "<div class='dit' id='dit' role='status'></div>"
                  f"<div id='compte'>{dessiner_compte(clinique.essais_reels)}</div>")
        return _page("Clinique — Essais réels", tete, milieu, SCRIPT)

    @app.get("/clinique/protocole-essais-reels", response_class=HTMLResponse)
    async def page_protocole():
        from .ecrans import _e

        texte = PROTOCOLE.read_text(encoding="utf-8") if PROTOCOLE.exists() else "Le fichier docs/projet/PROTOCOLE_ESSAIS_REELS.md manque."
        lignes = "".join(f"<p>{_e(l)}</p>" for l in texte.splitlines() if l.strip() and not l.startswith("#"))
        return _page("Clinique — Protocole des essais réels", "<h1>Le protocole des essais réels</h1>", lignes, "")

    @app.get("/clinique/essais-reels/contenu", response_class=HTMLResponse)
    async def page_essais_reels_contenu():
        return dessiner_compte(clinique.essais_reels)

    @app.get("/api/clinique/essais_reels")
    async def api_lire():
        return {"marque": "données inventées", "resume": clinique.essais_reels.resume()}

    @app.post("/api/clinique/essais_reels", dependencies=protege)
    async def api_compter(e: Essai):
        try:
            ligne = clinique.essais_reels.compter(e.robot, e.geste, e.reussi, e.note, avec_aide=e.avec_aide)
        except ValueError as erreur:
            raise HTTPException(400, str(erreur))
        return {"ligne": ligne, "resume": clinique.essais_reels.resume()}
