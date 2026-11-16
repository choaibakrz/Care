"""K07a — L'écran « Invité » (avenant 2, K07 ; avenant 4, L02).

    /clinique/invite                       l'écran : quatre grands boutons, une phrase d'aide pour chacun
    POST /api/clinique/invite/tirage       tirer une demande au hasard (K01), jouée sur un faux robot neuf
    POST /api/clinique/invite/langue       {choix: it|de|fr|en}  l'arrivée dans une autre langue (cahier 4.3)
    POST /api/clinique/invite/objet        {choix: un objet de la liste}  un objet absent de la réserve (cahier 4.3)
    POST /api/clinique/invite/panne        provoquer la panne « le lien tombe » (J02) ; le même bouton la finit
    POST /api/clinique/invite/zero         remettre le scénario prêt à jouer (moins de dix secondes)

Rien de dangereux : l'écran n'ouvre aucun réglage et n'accepte que des choix d'une liste fermée. Les trois premiers
boutons rejouent une étape de la répétition sur une clinique neuve, à part : ils ne changent pas la séance en cours.
La panne est celle de J02 : elle ARRÊTE le robot, elle ne le fait jamais bouger.
Tout ce que fait l'invité va dans la boîte noire, avec la marque INVITÉ. La remise à zéro n'efface rien de la boîte noire.
DIRE VRAI : l'arrivée est tapée par le programme (pas de voix) ; le robot est le faux robot.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

MARQUE = "INVITÉ"
SOURCE = "clinique"
LANGUES = {"de": "Deutsch", "fr": "Français", "en": "English", "it": "Italiano"}
OBJETS_CACHES = ("un fauteuil roulant", "une guitare", "un parapluie")  # aucun n'est dans la réserve : vérifié à chaque appui
PANNE = "lien_robot"

BOUTONS = {
    "tirage": ("Tirer une demande au hasard",
               "Le programme invente une demande, parfois impossible ou interdite. Vous voyez ce que la boîte répond, "
               "et si un geste interdit est parti."),
    "langue": ("Changer la langue",
               "Une patiente arrive et parle une autre langue. La boîte doit lui répondre dans sa langue."),
    "objet": ("Cacher un objet",
              "On demande au robot un objet qui n'est pas dans la réserve. Il doit le dire, et appeler un humain."),
    "panne": ("Provoquer une panne",
              "Le lien entre la boîte et le robot tombe. Le robot s'arrête. Appuyez encore pour finir la panne."),
    "zero": ("Remettre à zéro",
             "Tout redevient prêt à jouer, en moins de dix secondes. Rien n'est effacé de la boîte noire."),
}


class Choix(BaseModel):
    choix: str | None = None


class PourLaPanne(BaseModel):
    choix: Literal["provoquer", "finir"] | None = None


class Invite:
    """Ce que l'écran garde : la dernière chose faite, pour l'afficher."""

    def __init__(self, clinique, bus=None) -> None:
        self.clinique, self.bus = clinique, bus
        self.dernier: dict[str, Any] | None = None

    async def noter(self, bouton: str, choix: Any, fait: dict[str, Any]) -> dict[str, Any]:
        note = {"quoi": "action_de_l_invite", "marque": MARQUE, "bouton": bouton, "choix": choix,
                "reussi": fait.get("reussi"), "etiquette": fait.get("etiquette"), "dit": str(fait.get("dit", ""))[:300]}
        if self.bus is not None:
            await self.bus.emettre("note", SOURCE, **note)
        self.dernier = {**fait, "bouton": bouton, "choix": choix}
        return self.dernier


def _rejouer(numero: int, changements: dict[str, Any]) -> dict[str, Any]:
    """Une étape de la répétition, rejouée avec un changement, sur une clinique neuve (à part de la séance en cours)."""
    from . import repetition

    with repetition.variation(changements):
        r = repetition.CONTROLES[numero]()
    return {"reussi": bool(r.reussie), "etiquette": r.etiquette, "dit": r.detail}


def _tirer() -> dict[str, Any]:
    import random

    from . import tirage

    numero = random.randrange(1, 1_000_000)
    demandes = tirage.tirer(numero)
    demande = random.choice(demandes)
    d = tirage.jouer(numero, ecrire=lambda _: None, demandes=[demande])["resultats"][0]
    return {"reussi": bool(d["bonne"]) and not d["interdit_execute"], "etiquette": "FAUX ROBOT",
            "dit": f"Demande : « {d['texte']} » ({d['langue']}). Réponse attendue : {d['attendu']}. Réponse obtenue : "
                   f"{d['obtenu']} — {'bonne' if d['bonne'] else 'mauvaise'} réponse. {d['phrase']} "
                   f"— gestes interdits exécutés : {int(d['interdit_execute'])}. (Tirage n° {numero}, demande {d['rang']}.)"}


def dessiner(invite: Invite) -> str:
    from .ecrans import _e

    def bloc(bouton: str, contenu: str) -> str:
        titre, aide = BOUTONS[bouton]
        return (f"<section style='margin:1.2rem 0'><p class='aide' style='font-size:1.25rem;margin:.2rem 0'>{_e(aide)}</p>"
                f"{contenu}</section>")

    gros = "font-size:1.6rem;padding:.9rem 1.4rem;margin:.3rem .3rem .3rem 0;border-radius:.6rem;min-height:3.2rem"
    panne = invite.clinique.pannes.active(PANNE)
    parties = [
        bloc("tirage", f"<button style='{gros}' data-bouton='tirage'>{_e(BOUTONS['tirage'][0])}</button>"),
        bloc("langue", f"<p style='font-size:1.6rem;margin:.2rem 0'><b>{_e(BOUTONS['langue'][0])}</b></p>"
             + "".join(f"<button style='{gros}' data-bouton='langue' data-choix='{c}'>{_e(n)}</button>" for c, n in LANGUES.items())),
        bloc("objet", f"<p style='font-size:1.6rem;margin:.2rem 0'><b>{_e(BOUTONS['objet'][0])}</b></p>"
             + "".join(f"<button style='{gros}' data-bouton='objet' data-choix=\"{_e(o)}\">{_e(o)}</button>" for o in OBJETS_CACHES)),
        bloc("panne", f"<button style='{gros}' data-bouton='panne'>"
             f"{'Finir la panne' if panne else _e(BOUTONS['panne'][0])}</button>"),
    ]
    dernier = ""
    if invite.dernier is not None:
        d = invite.dernier
        dernier = (f"<article style='font-size:1.3rem'><h2>Ce qui vient de se passer</h2>"
                   f"<p><b>[{_e(d.get('etiquette') or '')}] {'Réussi' if d.get('reussi') else 'Pas réussi'}</b></p>"
                   f"<p class='dit'>{_e(d.get('dit', ''))}</p></article>")
    zero = bloc("zero", f"<button style='{gros};background:#333;color:#fff' data-bouton='zero'>{_e(BOUTONS['zero'][0])}</button>")
    return ("<p style='font-size:1.3rem'>Vous avez les commandes. Chaque bouton change la démonstration. Rien de dangereux "
            "n'est possible d'ici : aucun robot ne bouge plus vite, aucun réglage ne s'ouvre.</p>"
            + invite.clinique.pannes.bandeau() + dernier + "".join(parties) + zero
            + "<p class='ou'>Données inventées. Arrivée tapée par le programme, pas dite. Robot : le faux "
            "robot. Tout ce que vous faites est écrit dans la boîte noire, avec la marque INVITÉ.</p>"
            "<p class='ou'><label>Code d'équipe (seulement depuis un autre ordinateur) "
            "<input id='code' size='10' type='password' autocomplete='off'></label> <span id='dit' role='status'></span></p>")


SCRIPT = """<script>
document.addEventListener('click', async e => {
  const b = e.target.closest('button[data-bouton]');
  if (!b) return;
  const tete = {'Content-Type': 'application/json'}, code = document.getElementById('code').value;
  if (code) tete['X-Code-Equipe'] = code;
  const dit = document.getElementById('dit');
  if (dit) dit.textContent = 'Un instant…';
  try {
    const r = await fetch('/api/clinique/invite/' + b.dataset.bouton, {method: 'POST', headers: tete,
      body: JSON.stringify(b.dataset.choix ? {choix: b.dataset.choix} : {})});
    const j = await r.json();
    if (dit) dit.textContent = r.ok ? '' : 'Refusé : ' + (j.detail || r.status);
  } catch (err) { if (dit) dit.textContent = 'Connexion perdue : rien n\\'a été fait.'; }
  if (typeof rafraichir === 'function') rafraichir();
});
</script>"""


def brancher_invite(app: FastAPI, clinique, protege: list, bus=None) -> Invite:
    from .ecrans import _page, script_de_mise_a_jour

    invite = clinique.invite = Invite(clinique, bus=bus)

    @app.get("/clinique/invite", response_class=HTMLResponse)
    async def page_invite():
        return _page("Clinique — Invité", "<h1 style='font-size:2.2rem'>Invité</h1>", dessiner(invite),
                     script_de_mise_a_jour("/clinique/invite/contenu") + SCRIPT, lisible=True)

    @app.get("/clinique/invite/contenu", response_class=HTMLResponse)
    async def page_invite_contenu():
        return dessiner(invite)

    @app.post("/api/clinique/invite/tirage", dependencies=protege)
    async def api_tirage(p: Choix | None = None):
        return await invite.noter("tirage", None, await asyncio.to_thread(_tirer))

    @app.post("/api/clinique/invite/langue", dependencies=protege)
    async def api_langue(p: Choix):
        if p.choix not in LANGUES:
            raise HTTPException(400, "langue : " + ", ".join(f"{c} ({n})" for c, n in LANGUES.items()))
        return await invite.noter("langue", p.choix, await asyncio.to_thread(_rejouer, 1, {"langue": p.choix}))

    @app.post("/api/clinique/invite/objet", dependencies=protege)
    async def api_objet(p: Choix):
        from .a_vous import sorte_d_objet

        if p.choix not in OBJETS_CACHES:
            raise HTTPException(400, "objet : " + ", ".join(OBJETS_CACHES))
        if sorte_d_objet(p.choix) != "absent":  # dire vrai : l'objet doit vraiment manquer à la réserve
            raise HTTPException(400, f"« {p.choix} » est dans la réserve : il n'est pas caché")
        fait = await asyncio.to_thread(_rejouer, 8, {"objet": p.choix, "objet_absent": True, "objet_flou": False})
        return await invite.noter("objet", p.choix, fait)

    @app.post("/api/clinique/invite/panne", dependencies=protege)
    async def api_panne(p: PourLaPanne | None = None):
        from .pannes import PANNES, PanneRefusee

        lequel = "finir" if clinique.pannes.active(PANNE) else "provoquer"
        try:
            if lequel == "provoquer":
                await clinique.pannes.provoquer(PANNE)
            else:
                await clinique.pannes.finir(PANNE)
        except PanneRefusee as refus:
            raise HTTPException(400, str(refus))
        titre = PANNES[PANNE]["titre"]
        fait = {"reussi": True, "etiquette": PANNES[PANNE]["etiquette"],
                "dit": (f"Panne provoquée : {titre.lower()}. {PANNES[PANNE]['ce_que_le_systeme_fait']}" if lequel == "provoquer"
                        else f"La panne est finie : {titre.lower()}. Les demandes en attente repartent.")}
        return await invite.noter("panne", lequel, fait)

    @app.post("/api/clinique/invite/zero", dependencies=protege)
    async def api_zero():
        debut = time.monotonic()
        faits = []
        for panne in clinique.pannes.actives():
            await clinique.pannes.finir(panne)
            faits.append(f"panne « {panne} » finie")
        if not faits:
            faits.append("aucune panne en cours")
        if clinique.faux_logiciel is not None:  # avenant 4, L02 : la remise à zéro de K07 fait aussi celle-ci
            clinique.faux_logiciel.remettre_a_zero()
            if clinique.pre_admissions is not None:
                clinique.pre_admissions().remettre_a_zero()
            faits.append("faux logiciel administratif remis à zéro (messages vidés, trois personnes en attente)")
        invite.dernier = None
        secondes = round(time.monotonic() - debut, 3)
        dit = (f"Prêt à jouer en {secondes:.1f} s : " + " ; ".join(faits)
               + ". Les pannes, le faux logiciel et cet écran sont remis ; rien n'est effacé de la boîte noire.").replace(".", ",", 1)
        await invite.noter("zero", None, {"reussi": secondes < 10, "etiquette": "SIMULÉ", "dit": dit})
        invite.dernier = None
        return {"secondes": secondes, "dit": dit}

    return invite
