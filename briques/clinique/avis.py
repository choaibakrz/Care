"""K06 — L'avis des personnes (avenant 2, K06). Réponse de Hiba à Q9, le 12.11.2026 : « oui, aux conditions que tu écris ».

Les conditions : cinq notes de 1 à 5 et un rôle ; sans nom ; sans texte libre ; dans un fichier qui reste sur l'ordinateur.

    /clinique/avis/donner                  le formulaire, pour un téléphone du Wi-Fi (la phrase d'abord, puis les questions)
    POST /api/clinique/avis                {role, notes[5], essai?}  un avis ; tout autre champ est refusé
    /clinique/avis                         la page « Avis » : le nombre, par rôle, la moyenne de chaque question (à partir de 5)
    POST /api/clinique/avis/effacer-les-essais   pour l'équipe (code d'équipe) : retire les avis marqués ESSAI

Le fichier : `journal/clinique/avis.jsonl`, une ligne par avis (l'heure, le rôle, les cinq notes, la marque RÉEL ou ESSAI).
Il ne part jamais vers GitHub (une ligne dans .gitignore ; une vérification le prouve).
Les avis d'essai servent aux vérifications : ils sont marqués ESSAI, montrés à part, et effacés. Ce programme n'écrit
JAMAIS un avis réel lui-même : un avis réel vient seulement d'une personne qui remplit le formulaire.
Les mauvaises notes sont montrées comme les bonnes. En dessous de cinq avis : « trop peu d'avis », pas de moyenne.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field, conint

FICHIER = Path(__file__).resolve().parents[2] / "journal" / "clinique" / "avis.jsonl"
PHRASE = "Vos réponses sont anonymes. Elles servent à un prototype de concours. Vous pouvez arrêter quand vous voulez."
QUESTIONS = ("Le robot a-t-il dit ce qu'il allait faire avant de bouger ?",
             "Est-il resté à une distance qui vous convenait ?",
             "Vous a-t-il surpris ? (1 : souvent ; 5 : jamais)",
             "Avez-vous compris ses refus, et ses « je ne suis pas sûr » ?",
             "Seriez-vous d'accord pour qu'il aide dans un service de soins ?")
ROLES = ("soignant", "patient ou proche", "visiteur", "ingénieur", "autre")
MINIMUM = 5
REEL, ESSAI = "RÉEL", "ESSAI"
AUCUN = "Aucun avis réel recueilli pour l'instant."


class UnAvis(BaseModel):
    """Rien d'autre que le rôle et cinq notes : un nom ou un texte libre envoyé en plus est refusé."""

    model_config = ConfigDict(extra="forbid")
    role: Literal["soignant", "patient ou proche", "visiteur", "ingénieur", "autre"]
    notes: list[conint(ge=1, le=5)] = Field(min_length=5, max_length=5)
    essai: bool = False


class Avis:
    def __init__(self, fichier: str | Path | None = None) -> None:
        self.fichier = Path(fichier) if fichier else FICHIER

    def ajouter(self, role: str, notes: list[int], essai: bool) -> dict[str, Any]:
        avis = UnAvis(role=role, notes=notes, essai=essai)  # les mêmes conditions, même hors de la page
        ligne = {"quand": datetime.now().astimezone().isoformat(timespec="seconds"), "role": avis.role, "notes": list(avis.notes),
                 "marque": ESSAI if avis.essai else REEL}
        self.fichier.parent.mkdir(parents=True, exist_ok=True)
        with open(self.fichier, "a", encoding="utf-8") as f:
            f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
        return ligne

    def lignes(self) -> list[dict[str, Any]]:
        if not self.fichier.exists():
            return []
        lues = []
        for brute in self.fichier.read_text(encoding="utf-8").splitlines():
            try:
                l = json.loads(brute)
            except ValueError:
                continue  # une ligne abîmée ne bloque rien
            if isinstance(l, dict) and l.get("role") in ROLES and isinstance(l.get("notes"), list) and len(l["notes"]) == 5:
                lues.append(l)
        return lues

    def effacer_les_essais(self) -> int:
        if not self.fichier.exists():
            return 0
        gardees, effacees = [], 0
        for brute in self.fichier.read_text(encoding="utf-8").splitlines():
            try:
                essai = json.loads(brute).get("marque") == ESSAI
            except (ValueError, AttributeError):
                essai = False
            if essai:
                effacees += 1
            else:
                gardees.append(brute)
        self.fichier.write_text("".join(l + "\n" for l in gardees), encoding="utf-8")
        return effacees


def resume(lignes: list[dict[str, Any]]) -> dict[str, Any]:
    par_role = {r: sum(1 for l in lignes if l["role"] == r) for r in ROLES}
    moyennes = None
    if len(lignes) >= MINIMUM:
        moyennes = [sum(l["notes"][i] for l in lignes) / len(lignes) for i in range(len(QUESTIONS))]
    return {"nombre": len(lignes), "par_role": par_role, "moyennes": moyennes}


def _virgule(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


def _dessiner_bloc(titre: str, r: dict[str, Any]) -> str:
    from .ecrans import _e

    roles = " · ".join(f"{_e(role)} : {n}" for role, n in r["par_role"].items())
    if r["moyennes"] is None:
        moyennes = f"<p><b>trop peu d'avis</b> : il en faut au moins {MINIMUM} pour calculer quelque chose.</p>"
    else:
        moyennes = "<ul>" + "".join(f"<li>{_e(q)} — moyenne {_virgule(m)} sur 5</li>" for q, m in zip(QUESTIONS, r["moyennes"])) + "</ul>"
    return f"<article><h2>{_e(titre)}</h2><p><b>{r['nombre']} avis</b> — {roles}</p>{moyennes}</article>"


def dessiner_resultats(lignes: list[dict[str, Any]], adresse: str | None) -> str:
    from .ecrans import _e

    reels = [l for l in lignes if l.get("marque") == REEL]
    essais = [l for l in lignes if l.get("marque") == ESSAI]
    corps = (_dessiner_bloc("Avis réels", resume(reels)) if reels else f"<article><h2>Avis réels</h2><p class='rien'>{AUCUN}</p></article>")
    if essais:
        corps += ("<p class='ou'>Les avis d'essai ci-dessous servent aux vérifications : marqués ESSAI, jamais mêlés aux avis "
                  "réels, effacés ensuite.</p>" + _dessiner_bloc("Avis d'essai (ESSAI)", resume(essais)))
    lien = (f"http://{_e(adresse)}/clinique/avis/donner" if adresse else "/clinique/avis/donner")
    return (f"<p>Pour donner son avis, sur un téléphone du même Wi-Fi : <b style='font-size:1.4rem;overflow-wrap:anywhere'>{lien}</b></p>"
            "<p class='ou'>Codes QR : pas encore (question Q29). Anonyme : un rôle et cinq notes, sans nom, sans texte. "
            "Le fichier reste sur cet ordinateur. Les mauvaises notes sont montrées comme les bonnes.</p>" + corps)


def dessiner_formulaire() -> str:
    from .ecrans import _e

    questions = ""
    for i, q in enumerate(QUESTIONS):
        choix = "".join(f"<label style='margin-right:.8rem'><input type='radio' name='q{i}' value='{n}' required> {n}</label>"
                        for n in range(1, 6))
        questions += f"<fieldset style='margin:.8rem 0'><legend><b>{_e(q)}</b></legend>{choix}</fieldset>"
    roles = "".join(f"<option value=\"{_e(r)}\">{_e(r)}</option>" for r in ROLES)
    return (f"<p><b>{_e(PHRASE)}</b></p>"
            "<form id='avis'>"
            f"<p><label>Vous êtes : <select name='role' required><option value=''>— choisir —</option>{roles}</select></label></p>"
            f"{questions}<p style='margin:.4rem 0'>1 : pas du tout · 5 : tout à fait.</p>"
            "<p><button class='bouton' type='submit'>Envoyer</button> <span id='dit' role='status'></span></p></form>")


SCRIPT = """<script>
document.getElementById('avis').addEventListener('submit', async e => {
  e.preventDefault();
  const f = new FormData(e.target), notes = [];
  for (let i = 0; i < 5; i++) notes.push(parseInt(f.get('q' + i), 10));
  const dit = document.getElementById('dit');
  try {
    const r = await fetch('/api/clinique/avis', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({role: f.get('role'), notes: notes})});
    dit.textContent = r.ok ? 'Merci. Votre avis est enregistré.' : 'Pas enregistré : une réponse manque ?';
    if (r.ok) e.target.reset();
  } catch (err) { dit.textContent = 'Connexion perdue : pas enregistré.'; }
});
</script>"""


def brancher_avis(app: FastAPI, clinique, protege: list) -> None:
    from .ecrans import _page
    from .ecrans_listes import _du_meme_site
    from .reseau_local import adresse_du_wifi

    clinique.avis = Avis()

    @app.get("/clinique/avis/donner", response_class=HTMLResponse)
    async def page_donner():
        return _page("Clinique — Votre avis", "<h1>Votre avis sur le robot</h1>", dessiner_formulaire(), SCRIPT, lisible=True)

    @app.post("/api/clinique/avis", dependencies=[Depends(_du_meme_site)])
    async def api_avis(a: UnAvis):
        ligne = clinique.avis.ajouter(a.role, list(a.notes), a.essai)
        return {"enregistre": True, "marque": ligne["marque"]}

    @app.get("/clinique/avis", response_class=HTMLResponse)
    async def page_avis(request: Request):
        ip = adresse_du_wifi()
        adresse = f"{ip}:{request.url.port}" if ip and request.url.port else ip
        return _page("Clinique — Avis", "<h1>Avis</h1>", dessiner_resultats(clinique.avis.lignes(), adresse))

    @app.post("/api/clinique/avis/effacer-les-essais", dependencies=protege)
    async def api_effacer():
        return {"effaces": clinique.avis.effacer_les_essais()}
