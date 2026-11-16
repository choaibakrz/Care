"""T25 — Le tableau de flotte (cahier 5.10 ; avenant 2, K03 et K04).

    /clinique/tableau-de-flotte             la page : le plan, les robots, leur carte, leur batterie, leur tâche, leur étiquette
    /clinique/flotte/pourquoi?tache=t1      pourquoi ce robot (le choix du répartiteur ; aucun nom de patient)
    POST /api/clinique/flotte/attribuer     {tache}            le répartiteur choisit un robot pour une tâche demandée
    POST /api/clinique/flotte/pas                              le temps du monde simulé avance d'un pas
    POST /api/clinique/flotte/panne         {robot, raison}    panne provoquée d'un robot simulé
    POST /api/clinique/flotte/reprendre     {tache}            la reprise par le robot libre le plus proche (T24)

- Le plan : les lieux du faux dossier, par étage, lus par la porte ; chaque robot est écrit là où il est.
- Les étiquettes : « FAUX ROBOT — SIMULÉ » pour R2, R3, R4 (ils n'existent que dans l'ordinateur) ; pour R1, celle du
  robot branché (FAUX ROBOT aujourd'hui, RÉEL avec un vrai robot). Jamais du simulé présenté comme du réel.
- L'âge de l'information s'affiche (K03) ; « Pourquoi ? » ouvre le choix du répartiteur (K04).
- Les boutons (avancer, panne, reprise, attribuer) sont pour l'équipe : code d'équipe depuis un autre ordinateur.
- Aucun nom de patient : une tâche est montrée par son objet et son lieu.
DIRE VRAI : dans le monde simulé, RIEN NE BOUGE. Le temps n'avance que quand on appuie sur « Avancer d'un pas ».
La page simple `/clinique/flotte` (T11c) n'est pas changée.
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .monde_robots import ETIQUETTE_BRANCHE, ETIQUETTE_SIMULE, MondeDesRobots
from .panne_reprise import PanneEtReprise
from .repartiteur import Repartiteur

PAGE = "/clinique/tableau-de-flotte"
ETAGES = {0: "Rez-de-chaussée"}


class PourUneTache(BaseModel):
    tache: Annotated[str, Field(max_length=20)]


class UnePanne(BaseModel):
    robot: Annotated[str, Field(max_length=40)]
    raison: Annotated[str, Field(max_length=80)] = "panne"


class TableauDeFlotte:
    """Ce que la page partage : le monde simulé, le répartiteur, la panne et la reprise, le tableau des tâches."""

    def __init__(self, clinique, cartes) -> None:
        coursier = clinique.coursier
        if coursier is not None and getattr(coursier, "repartiteur", None) is not None:  # le même monde que la séance (K04)
            self.repartiteur = coursier.repartiteur
        else:
            self.repartiteur = Repartiteur(MondeDesRobots(cartes=cartes), cartes)
        self.monde = self.repartiteur.monde
        self.clinique, self.taches, self.cartes = clinique, clinique.taches, cartes
        self.reprise = PanneEtReprise(self.monde, self.repartiteur, clinique.taches, clinique.carnet, coursier=coursier,
                                      bus=coursier.systeme.bus if coursier is not None else getattr(clinique.horloge, "bus", None))

    def etiquette(self, robot: dict[str, Any]) -> str:
        if robot["simule"]:
            return ETIQUETTE_SIMULE
        return self.clinique.coursier.etiquette() if self.clinique.coursier is not None else ETIQUETTE_BRANCHE

    def plan(self) -> dict[int, list[str]]:
        """Les lieux, par étage, lus par la porte avec un badge de robot (un robot a le droit de lire le plan)."""
        badge = next(b for b in self.clinique.badges.values() if b.role == "robot")
        par_etage: dict[int, list[str]] = {}
        for lieu in self.clinique.porte.lieux(badge)["lieux"]:
            par_etage.setdefault(int(lieu["etage"]), []).append(lieu["nom"])
        return par_etage

    def taches_de_robot(self) -> list[dict[str, Any]]:
        return [t for t in self.taches._taches() if t.get("de")]


def dessiner(tf: TableauDeFlotte, place_de_r1: dict[str, Any] | None = None) -> str:
    from .ecrans import _e

    robots = tf.monde.etat()
    taches = {t["id"]: t for t in tf.taches_de_robot()}
    par_lieu: dict[str, list[str]] = {}
    branche = tf.clinique.coursier is not None
    for r in robots:
        if not r["simule"]:  # R1 : pas posé sur le plan (sa place lue sur le robot est écrite dans sa ligne, H18)
            continue
        lieu = tf.monde._robot(r["id"])["lieu"]
        vers = tf.monde._robot(r["id"])["vers"]
        par_lieu.setdefault(lieu, []).append(f"{r['nom']}{' → ' + vers if vers else ''}")
    plan = ""
    for etage, lieux in sorted(tf.plan().items(), reverse=True):
        cases = "".join(
            f"<span style='display:inline-block;border:1px solid #d5d9df;border-radius:.4rem;padding:.25rem .5rem;margin:.15rem;"
            f"background:{'#fff8e1' if par_lieu.get(lieu) else '#fff'}'>{_e(lieu)}"
            f"{' <b>' + _e(', '.join(par_lieu[lieu])) + '</b>' if par_lieu.get(lieu) else ''}</span>" for lieu in lieux)
        plan += f"<h4>{_e(ETAGES.get(etage, f'Étage {etage}'))}</h4><p>{cases}</p>"
    rangs = ""
    for r in robots:
        if not r["simule"]:  # R1 : rien d'inventé. Sa place est lue sur le robot branché (H18), jamais devinée.
            etat = "branché (ses courses : par le coursier, sous le gardien)" if branche else "pas branché"
            # H18 (réponse de Hiba à Q28 : A) : branché, sa place est lue sur le robot (le lieu du plan le plus proche).
            # Le chiffre de la batterie n'est pas montré : l'essai du tour 81 interdit « 100 % » ici (question Q34).
            if not branche:
                ou, batterie = "place pas suivie sur ce plan", "batterie pas lue"
            elif place_de_r1 is None:
                ou, batterie = "place pas lue", "batterie pas lue"
            else:
                ou = f"près de « {_e(place_de_r1['lieu'])} » (lu sur le robot)"
                batterie = "batterie lue sur le robot" if place_de_r1.get("batterie") is not None else "batterie pas lue"
            rangs += (f"<tr><td><b>{_e(r['nom'])}</b></td><td>{_e(r['carte'])}</td><td>{_e(tf.etiquette(r))}</td>"
                      f"<td>{ou}</td><td>{batterie}</td><td><b>{etat}</b></td><td>—</td><td></td></tr>")
            continue
        tache = taches.get(str(r["tache"])) if r["tache"] else None
        quoi = f"{_e(tache['quoi'])} → {_e(tache['ou'])}" if tache else "—"
        panne = f" : {_e(r['panne'])}" if r["panne"] else ""
        bouton = (f"<button data-panne=\"{_e(r['id'])}\" data-raison=\"batterie basse\">Panne : batterie basse</button> "
                  f"<button data-panne=\"{_e(r['id'])}\" data-raison=\"robot bloqué\">Panne : robot bloqué</button>"
                  if r["simule"] and r["etat"] != "en panne" else "")
        rangs += (f"<tr><td><b>{_e(r['nom'])}</b></td><td>{_e(r['carte'])}</td><td>{_e(tf.etiquette(r))}</td><td>{_e(r['ou'])}</td>"
                  f"<td>{r['batterie']:.0f} %</td><td><b>{_e(r['etat'])}</b>{panne}</td><td>{quoi}</td><td>{bouton}</td></tr>")
    courses = ""
    for t in taches.values():
        nom = lambda ident: tf.monde._robots[ident]["nom"] if ident in tf.monde._robots else ident  # noqa: E731
        ligne = f"<li><b>{_e(t['quoi'])} → {_e(t['ou'])}</b> (de {_e(t['de'])}) — <b>{_e(t['etat'])}</b>"
        if t.get("sorte") == "humain":
            ligne += f" — pour un humain : {_e(t.get('pourquoi_un_humain') or '')}"
            if t.get("robot"):  # l'histoire, sans faire croire qu'un robot a encore la course
                ligne += f" (avant : {_e(nom(t['robot']))})"
        elif t.get("robot"):
            ligne += f" — robot : {_e(nom(t['robot']))}{' [' + _e(t['etiquette']) + ']' if t.get('etiquette') else ''}"
        if t.get("repris_de") and t.get("sorte") != "humain":
            ligne += f" — reprise de {_e(nom(t['repris_de']))}"
        if t.get("pourquoi_ce_robot") and t.get("sorte") != "humain":
            ligne += f"<br><span class='ou'>{_e(t['pourquoi_ce_robot'])}</span> <a href=\"/clinique/flotte/pourquoi?tache={_e(t['id'])}\">Pourquoi ?</a>"
        if t.get("note_de_reprise"):
            ligne += f"<br><span class='ou'>{_e(t['note_de_reprise'])}</span>"
        if t.get("arrive_simule"):
            ligne += f"<br><span class='ou'>{_e(t['arrive_simule'])}</span>"
        if t.get("sorte") == "robot" and t["etat"] == "reprise":
            ligne += f" <button data-reprendre=\"{_e(t['id'])}\">Reprendre (le plus proche)</button>"
        elif t.get("sorte") == "robot" and t["etat"] == "demandée" and not t.get("robot"):
            ligne += (" <span class='ou'>un robot est branché : cette course se fait par le coursier, pas depuis ce tableau</span>" if branche
                      else f" <button data-attribuer=\"{_e(t['id'])}\">Attribuer (le plus proche)</button>")
        courses += ligne + "</li>"
    compte = tf.monde.compte()
    changements = "".join(  # H13 : un changement de carte laisse une trace sur le tableau
        f"<li>{_e(tf.monde._robots[c['robot']]['nom'] if c['robot'] in tf.monde._robots else c['robot'])} : carte {_e(c['avant'])} → "
        f"{_e(c['apres'])} (par {_e(c['qui'])})</li>" for c in tf.cartes.changements)
    return (
        f"<p><b>{_e(compte['texte'])}.</b> Un robot simulé n'existe que dans l'ordinateur : rien ne bouge. Le temps du monde simulé "
        f"n'avance que quand on appuie sur « Avancer d'un pas » (pas n° {tf.monde.numero_du_pas}).</p>"
        "<p class='ou'><b>Les trois étiquettes</b> : RÉEL (un vrai robot) · FAUX ROBOT (le robot branché, simulé par l'ossature) · "
        "FAUX ROBOT — SIMULÉ (un point sur le plan, dans l'ordinateur).</p>"
        f"<article><h2>Le plan</h2>{plan}<p class='ou'>Plan inventé. Les robots ne changent pas d'étage.</p></article>"
        "<table><tr><th>Robot</th><th>Carte</th><th>Étiquette</th><th>Où</th><th>Batterie</th><th>État</th><th>Tâche</th><th></th></tr>"
        f"{rangs}</table>"
        "<p><button data-pas='1'>Avancer d'un pas</button> <span class='ou' id='dit' role='status'></span></p>"
        + (f"<article><h2>Courses</h2><ul>{courses}</ul></article>" if courses else "<p class='rien'>Aucune course pour un robot.</p>")
        + (f"<article><h2>Changements de carte</h2><ul>{changements}</ul></article>" if changements else ""))


SCRIPT = """<script>
async function envoyer(chemin, corps) {
  const tete = {'Content-Type': 'application/json'}, code = document.getElementById('code').value;
  if (code) tete['X-Code-Equipe'] = code;
  const dit = document.getElementById('dit');
  try {
    const r = await fetch('/api/clinique/flotte/' + chemin, {method: 'POST', headers: tete, body: JSON.stringify(corps || {})});
    const j = await r.json();
    if (dit) dit.textContent = r.ok ? 'Fait.' : 'Refusé : ' + (j.detail || r.status);
  } catch (e) { if (dit) dit.textContent = 'Connexion perdue : rien n\\'a été fait.'; }
  if (typeof rafraichir === 'function') rafraichir();
}
document.addEventListener('click', e => {  // les boutons sont redessinés avec la page : on écoute au-dessus d'eux
  const b = e.target.closest('button');
  if (!b) return;
  if (b.dataset.pas) envoyer('pas');
  else if (b.dataset.panne) envoyer('panne', {robot: b.dataset.panne, raison: b.dataset.raison});
  else if (b.dataset.reprendre) envoyer('reprendre', {tache: b.dataset.reprendre});
  else if (b.dataset.attribuer) envoyer('attribuer', {tache: b.dataset.attribuer});
});
</script>"""


def brancher_tableau_de_flotte(app: FastAPI, clinique, protege: list, cartes) -> None:
    from .ecrans import _e, _heure_html, _page, script_de_mise_a_jour

    tf = clinique.tableau_de_flotte = TableauDeFlotte(clinique, cartes)

    def essayer(faire):
        try:
            return faire()
        except ValueError as erreur:
            raise HTTPException(400, str(erreur))

    derniere = {"quand": -10.0, "place": None}

    async def _place_de_r1():
        """H18 : lire (seulement) la place du robot branché ; None s'il n'y en a pas, ou s'il ne répond pas.
        La page se recharge toutes les 2 s, sur plusieurs écrans : une lecture sert pendant 1,5 s, pour ne pas charger un
        vrai robot lent."""
        import time

        if clinique.coursier is None:
            return None
        if time.monotonic() - derniere["quand"] >= 1.5:
            derniere.update(place=await clinique.coursier.lire_la_place(tf.monde), quand=time.monotonic())
        return derniere["place"]

    @app.get(PAGE, response_class=HTMLResponse)
    async def page_tableau():
        tete = (f"<h1>Tableau de flotte</h1><span class='heure' id='heure'>{_heure_html(clinique.horloge.etat())}</span>"
                "<label>Code d'équipe (depuis un autre ordinateur) <input id='code' size='12' type='password' autocomplete='off'></label>")
        return _page("Clinique — Tableau de flotte", tete, dessiner(tf, await _place_de_r1()),
                     script_de_mise_a_jour(f"{PAGE}/contenu") + SCRIPT)

    @app.get(f"{PAGE}/contenu", response_class=HTMLResponse)
    async def page_tableau_contenu():
        return dessiner(tf, await _place_de_r1())

    @app.get("/clinique/flotte/pourquoi", response_class=HTMLResponse)
    async def page_pourquoi_ce_robot(tache: str):
        t = next((x for x in tf.taches_de_robot() if x["id"] == tache), None)
        if t is None:
            raise HTTPException(404, "cette tâche n'est pas une course de robot")
        de = t.get("objet_ou") or t["de"]
        regardes = tf.repartiteur.choisir({**t, "de": de})["regardes"]
        rangs = "".join(
            f"<tr><td><b>{_e(r['nom'])}</b></td><td>{_e(r['carte'])}</td><td>{_e(tf.etiquette(tf.monde._robot(r['id'])))}</td><td>{'oui' if r['libre'] else 'non'}</td>"
            f"<td>{'—' if r['metres'] is None else f'{r['metres']:.0f} m'}</td><td>{r['batterie']:.0f} %</td>"
            f"<td>{'oui' if r['carte_permet'] else 'non'}</td><td>{_e(r['raison'] or 'convient')}</td></tr>" for r in regardes)
        # H13 : le feu du gardien (K04). Seul le robot branché demande au gardien ; un robot simulé ne lui demande rien.
        decisions = []
        if clinique.coursier is not None:
            decisions = [e.donnees for e in clinique.coursier.systeme.bus.historique
                         if e.type == "gardien_decision" and e.conversation == f"clinique-{tache}"]
        oui, non, humain = (sum(1 for d in decisions if d.get("verdict") == v) for v in ("oui", "non", "humain"))
        if decisions:
            couleur = "rouge" if non else ("orange" if humain else "vert")
            feu = (f"Feu <b>{couleur}</b> : {oui} oui, {non} non, {humain} « demander à un humain », pour les gestes de cette tâche. "
                   "Aucun geste ne part sans un « oui ».")
        elif t.get("robot") and tf.monde._robots.get(t["robot"], {}).get("simule"):
            feu = ("Robot simulé : aucun geste n'est demandé au gardien, parce que rien ne bouge. "
                   "Le gardien ne décide que pour le robot branché.")
        else:
            feu = "Pas encore de geste : le gardien n'a rien eu à décider pour cette tâche."
        milieu = (f"<p class='ou'>Tâche {_e(t['id'])} : {_e(t['quoi'])} → {_e(t['ou'])} — <b>{_e(t['etat'])}</b>. Données inventées.</p>"
                  f"<article><h2>Pourquoi ce robot</h2><p class='dit'>{_e(t.get('pourquoi_ce_robot') or t.get('pourquoi_un_humain') or 'Aucun robot n’est encore choisi.')}</p></article>"
                  f"<article><h2>Le feu du gardien</h2><p>{feu}</p></article>"
                  "<article><h2>Les robots, regardés maintenant</h2><table><tr><th>Robot</th><th>Carte</th><th>Étiquette</th><th>Libre</th>"
                  f"<th>Distance</th><th>Batterie</th><th>Sa carte permet</th><th>Avis</th></tr>{rangs}</table>"
                  "<p class='ou'>Ce tableau est refait maintenant : il peut différer du moment du choix, écrit dans la phrase ci-dessus.</p></article>"
                  f"<p><a class='bouton' href=\"{PAGE}\">Retour au tableau de flotte</a></p>")
        tete = f"<h1>Pourquoi ce robot ?</h1><span class='heure' id='heure'>{_heure_html(clinique.horloge.etat())}</span>"
        return _page("Clinique — Pourquoi ce robot ?", tete, milieu)

    @app.post("/api/clinique/flotte/attribuer", dependencies=protege)
    async def api_attribuer(p: PourUneTache):
        if clinique.coursier is not None:  # une vraie demande ne part pas à un robot simulé (K04)
            raise HTTPException(400, "un robot branché est là : la course se fait par le coursier, sous le gardien, pas depuis ce tableau")
        return essayer(lambda: tf.repartiteur.attribuer(clinique.taches, p.tache))

    @app.post("/api/clinique/flotte/pas", dependencies=protege)
    async def api_pas():
        traitees = tf.reprise.avancer()
        await tf.reprise.ecrire_dans_la_boite()
        return {"pas": tf.monde.numero_du_pas, "pannes": [t["id"] for t in traitees]}

    @app.post("/api/clinique/flotte/panne", dependencies=protege)
    async def api_panne(p: UnePanne):
        def provoquer():
            if not tf.monde._robot(p.robot)["simule"]:  # le robot branché n'est pas un point sur le plan : ses pannes sont celles de la prise
                raise ValueError("pas de panne provoquée d'ici pour le robot branché : seulement pour un robot simulé")
            return tf.reprise.provoquer(p.robot, p.raison)

        rendue = essayer(provoquer)
        await tf.reprise.ecrire_dans_la_boite()
        return {"tache": rendue}

    @app.post("/api/clinique/flotte/reprendre", dependencies=protege)
    async def api_reprendre(p: PourUneTache):
        try:
            return await tf.reprise.reprendre(p.tache)
        except ValueError as erreur:
            raise HTTPException(400, str(erreur))
