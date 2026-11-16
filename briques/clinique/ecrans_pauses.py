"""La pause, sur la tablette du soignant (avenant jury, J05a).

    GET  /clinique/soignant/pauses?badge=…     les pauses en cours de mon étage ; mettre une pause ; lever une pause
    POST /api/clinique/pause                   mettre une pause (badge de soignant)
    POST /api/clinique/pause/lever             lever une pause (badge de soignant du même étage)

Le gardien applique la pause au prochain geste que le robot demande. Si aucun robot n'est branché, la page le dit.
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .pauses import CHOSES, MINUTES_MAX, RAISONS, Refus
from .porte import AccesRefuse

Court = Annotated[str, Field(max_length=60)]


class Pause(BaseModel):
    badge: Court
    chose: Court
    minutes: int
    raison: Court


class Levee(BaseModel):
    badge: Court
    numero: Court


SCRIPT = """<script>
const badge = new URLSearchParams(location.search).get('badge') || '';
const dit = document.getElementById('dit');
async function envoyer(chemin, corps) {
  const r = await fetch(chemin, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(corps)});
  const j = await r.json();
  if (!r.ok) { dit.textContent = 'Refusé : ' + (j.detail || r.status); return; }
  location.reload();
}
document.getElementById('mettre').onclick = () => envoyer('/api/clinique/pause', {badge,
  chose: document.getElementById('chose').value, minutes: parseInt(document.getElementById('minutes').value, 10),
  raison: document.getElementById('raison').value});
document.querySelectorAll('button[data-lever]').forEach(b => b.onclick = () =>
  envoyer('/api/clinique/pause/lever', {badge, numero: b.dataset.lever}));
</script>"""


def dessiner(clinique, badge) -> str:
    from .ecrans import _e

    pauses = clinique.pauses_des_soignants
    en_cours = [p for p in pauses.actives() if p["etage"] == badge.etage]
    liste = "".join(f"<li>{_e(p['dit'])} <button data-lever=\"{_e(p['numero'])}\">Lever la pause</button></li>" for p in en_cours)
    choses = "".join(f"<option value='{c}'>{_e(t)}</option>" for c, t in CHOSES.items())
    raisons = "".join(f"<option>{_e(r)}</option>" for r in RAISONS)
    robot = ("" if clinique.coursier is not None else
             "<p class='rien'>Aucun robot n'est branché : la pause est notée, mais aucun robot n'agit en ce moment.</p>")
    return ("<p class='ou'>Mettez en pause une chose que font les robots à votre étage. Le gardien l'applique au prochain geste du "
            "robot ; le robot dit pourquoi il attend. La pause finit seule à l'heure dite, ou quand vous la levez. Tout est noté.</p>"
            f"<p><label>Quoi <select id='chose'>{choses}</select></label> "
            f"<label>Combien de minutes <input id='minutes' type='number' min='1' max='{MINUTES_MAX}' value='15' size='4'></label> "
            f"<label>Raison <select id='raison'>{raisons}</select></label> <button class='bouton' id='mettre'>Mettre en pause</button></p>"
            "<div class='dit' id='dit' role='status'></div>" + robot
            + f"<h2>Pauses en cours à l'étage {_e(badge.etage)} ({len(en_cours)})</h2>"
            + (f"<ul>{liste}</ul>" if liste else "<p class='rien'>Aucune pause en cours.</p>"))


def brancher_pauses(app, clinique) -> None:
    from .ecrans import _page

    def badge_de(identifiant: str):
        if identifiant not in clinique.badges:
            raise HTTPException(404, "Ce badge n'existe pas")
        return clinique.badges[identifiant]

    async def essayer(geste) -> Any:
        try:
            resultat = geste()
        except AccesRefuse as refus:
            raise HTTPException(403, str(refus))
        except Refus as refus:
            raise HTTPException(400, str(refus))
        await clinique.pauses_des_soignants.ecrire_dans_la_boite()
        return resultat

    @app.get("/clinique/soignant/pauses", response_class=HTMLResponse)
    async def page_pauses(badge: str):
        b = badge_de(badge)
        if b.role != "soignant":
            raise HTTPException(403, "les pauses sont pour les soignants")
        return _page("Clinique — Pauses", f"<h1>Pauses</h1><a href=\"/clinique/soignant?badge={b.id}\">← Mon écran</a>",
                     dessiner(clinique, b), SCRIPT)

    @app.get("/api/clinique/pauses")
    async def api_lire():
        return {"marque": "données inventées", "pauses": clinique.pauses_des_soignants.actives()}

    @app.post("/api/clinique/pause")
    async def api_mettre(p: Pause):
        return {"pause": await essayer(lambda: clinique.pauses_des_soignants.mettre(badge_de(p.badge), p.chose, p.minutes, p.raison))}

    @app.post("/api/clinique/pause/lever")
    async def api_lever(levee: Levee):
        return {"pause": await essayer(lambda: clinique.pauses_des_soignants.lever(badge_de(levee.badge), levee.numero))}
