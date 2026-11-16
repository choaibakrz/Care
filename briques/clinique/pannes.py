"""Les pannes provoquées (avenant jury, J02) : « Si le Wi-Fi tombe, que fait le robot ? »

    /clinique/pannes                                   la page : une ligne par panne, un bouton pour la provoquer
    POST /api/clinique/pannes/{panne}/provoquer        (code d'équipe demandé)
    POST /api/clinique/pannes/{panne}/finir
    python3 lancer.py pannes                           la liste des pannes
    python3 lancer.py pannes lien_robot                joue la panne sur le faux robot et montre les quatre choses
                                                       (aussi : cerveau_muet, micro_bruit ; la tablette : sur la page)

Pour chaque panne, quatre choses obligatoires :
  1. le robot s'arrête là où il est, et il ne commence rien de nouveau ;
  2. l'écran le dit en mots simples : ce qui se passe, ce que le système fait, qui est prévenu ;
  3. la boîte noire l'écrit (et le carnet aussi) ;
  4. quand la panne finit, rien n'est perdu : les coches sont là, les tâches en attente repartent.
Pendant une panne, le système continue ce qu'il sait faire sans la pièce absente, et il le dit. Jamais « tout va bien ».
Chaque panne provoquée porte l'étiquette SIMULÉ.

Les quatre pannes de l'avenant sont construites. Trois mettent le robot à l'abri (ABRI) : il s'arrête et ne commence
rien de nouveau, les demandes attendent, et repartent à la fin. La quatrième est celle de la tablette.

DIRE VRAI : dans la version simple, le « cerveau » est fait de règles, sans modèle, et aucune pièce n'écoute encore
un micro. « Le cerveau ne répond plus » fige donc les pièces que le cerveau fera vivre (le résumé, la proposition
de rangement, les demandes au robot). « Le micro n'entend que du bruit » rend du bruit à qui demande ce que les
oreilles ont entendu (`entendre`) ; la seule chaîne qui écoute aujourd'hui est celle de l'ossature.

La panne de la tablette : la page de liste marque chacun de ses échanges (« X-Tablette »). Pendant la panne, le
programme répond « lien coupé » à ces échanges-là. C'est une panne SIMULÉE : le vrai Wi-Fi n'est pas coupé, et une
page rechargée repartirait. Sur la tablette, les coches vont dans une file gardée par le navigateur, et repartent
au retour du lien (ecrans_listes.py).

Comment le robot s'arrête : par les pièces de l'ossature, pas par un chemin à part. Le faux robot perd sa liaison
(panne « perte_liaison » de la brique 2) : son chien de garde l'arrête sur place. Tant que la panne dure, le coursier
ne demande rien au gardien : les demandes au robot attendent. Si la prise a déclenché l'arrêt d'urgence, seul un
humain réarme : au retour du lien, les tâches attendent encore, et l'écran le dit.
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from .carnet import Carnet
from .porte import Badge

SOURCE = "pannes_clinique"
GENRE = "panne"
ETIQUETTE = "SIMULÉ"
ATTENTE_LIEN = "le lien avec le robot est coupé (panne provoquée) : la course partira au retour du lien"
# Les pannes qui mettent le robot à l'abri : il s'arrête et ne commence rien de nouveau. Ce que dit la tâche qui attend.
ATTENTES = {"lien_robot": ATTENTE_LIEN,
            "cerveau_muet": "le cerveau ne répond plus (panne provoquée) : la course partira quand il répondra",
            "micro_bruit": "le micro n'entend que du bruit (panne provoquée) : le robot attend la fin de la panne"}
ABRI = tuple(ATTENTES)

# Les quatre pannes de l'avenant. Les phrases s'affichent telles quelles sur les écrans.
PANNES: dict[str, dict[str, Any]] = {
    "lien_robot": {
        "titre": "Le lien tombe entre le cerveau et un robot", "etiquette": ETIQUETTE, "construite": True,
        "ce_qui_se_passe": "Le cerveau ne peut plus parler au robot.",
        "ce_que_le_systeme_fait": "Le robot s’arrête là où il est et ne commence rien de nouveau. Les demandes au robot "
                                  "attendent le retour du lien. Les listes de soin et les écrans continuent.",
        "qui_est_prevenu": "Prévenus : tous les écrans de l’équipe, par ce bandeau."},
    "lien_tablette": {
        "titre": "Le lien tombe entre le cerveau et une tablette", "etiquette": ETIQUETTE, "construite": True,
        "ce_qui_se_passe": "Une tablette ne reçoit plus rien du cerveau.",
        "ce_que_le_systeme_fait": "La tablette garde la liste déjà ouverte : on continue à cocher, elle affiche « hors ligne », "
                                  "et les coches partent au retour du lien. Aucune demande au robot ne part de cette tablette.",
        "qui_est_prevenu": "Prévenus : la personne qui tient la tablette, sur sa tablette, et les autres écrans, par ce bandeau."},
    "cerveau_muet": {
        "titre": "Le cerveau ne répond plus", "etiquette": ETIQUETTE, "construite": True,
        "ce_qui_se_passe": "Le cerveau, qui prépare les résumés, propose le rangement des papiers et comprend les demandes, ne répond plus.",
        "ce_que_le_systeme_fait": "Le robot s’arrête et ne commence rien de nouveau : les demandes au robot attendent. Le médecin "
                                  "garde le résumé préparé avant la panne, marqué « peut être vieux ». Les nouveaux papiers "
                                  "attendent sans proposition. Les listes de soin se cochent toujours au doigt.",
        "qui_est_prevenu": "Prévenus : tous les écrans de l’équipe, par ce bandeau."},
    "micro_bruit": {
        "titre": "Le micro n’entend que du bruit", "etiquette": ETIQUETTE, "construite": True,
        "ce_qui_se_passe": "La voix n’est plus comprise : le micro n’entend que du bruit.",
        "ce_que_le_systeme_fait": "Le robot s’arrête et ne commence rien de nouveau. Une phrase mal entendue ne coche rien et "
                                  "ne fait rien partir. On passe au doigt et au clavier : les listes se cochent toujours.",
        "qui_est_prevenu": "Prévenus : tous les écrans de l’équipe, par ce bandeau."},
}


class PanneRefusee(ValueError):
    """La panne demandée ne peut pas être provoquée ou finie. Le message dit pourquoi."""


class Pannes:
    def __init__(self, carnet: Carnet, taches=None, coursier=None, systeme=None, bus=None) -> None:
        self.carnet, self.taches, self.coursier, self.systeme = carnet, taches, coursier, systeme
        self.bus = bus if bus is not None else (systeme.bus if systeme is not None else None)
        self._actives: list[str] = []
        self._dit = ""  # ce que l'écran doit dire après le retour (un humain doit réarmer…)
        self._badge = Badge(id="pannes", role="assistant", libelle="Pannes provoquées")
        self.resume = self.papiers = None  # branchés par les écrans : le cerveau muet les fige
        if coursier is not None:
            coursier.pannes = self

    # ------------------------------------------------------------------ lire
    def actives(self) -> list[str]:
        return list(self._actives)

    def active(self, ident: str) -> bool:
        return ident in self._actives

    def a_l_abri(self) -> str | None:
        """La première panne en cours qui met le robot à l'abri, ou None."""
        return next((i for i in self._actives if i in ABRI), None)

    def entendre(self, texte: str) -> tuple[str, float]:
        """Ce que les oreilles rendent : la phrase et la confiance. Micro en panne : du bruit, confiance très basse.
        Les pièces à la voix (tâches T16, T17, T20) passeront par ici."""
        return ("…", 0.1) if self.active("micro_bruit") else (texte, 1.0)

    def etat(self) -> list[dict[str, Any]]:
        return [{"id": i, **p, "active": i in self._actives} for i, p in PANNES.items()]

    def bandeau(self) -> str:
        """Le morceau d'écran que toutes les pages redemandent : ce qui se passe, ce que le système fait, qui est prévenu."""
        from .ecrans import _e

        style = "display:block;background:#b00020;color:#fff;padding:.4rem .6rem;border-radius:.4rem;margin:.3rem 0;font-weight:400"
        morceaux = []
        for ident in self._actives:
            p = PANNES[ident]
            morceaux.append(f"<span class='panne' style='{style}'><b>PANNE PROVOQUÉE [{_e(p['etiquette'])}] — {_e(p['titre'])}.</b> "
                            f"{_e(p['ce_qui_se_passe'])} {_e(p['ce_que_le_systeme_fait'])} {_e(p['qui_est_prevenu'])}</span>")
        if self._dit and not self._actives:
            morceaux.append(f"<span class='panne' style='{style.replace('#b00020', '#8a5a00')}'>{_e(self._dit)}</span>")
        return "".join(morceaux)

    # ------------------------------------------------------------------ écrire
    async def _noter(self, ident: str, etat: str, **plus: Any) -> None:
        p = PANNES[ident]
        self.carnet.ecrire(self._badge, GENRE, {"panne": ident, "titre": p["titre"], "etat": etat, "provoquee": True,
                                                "etiquette": p["etiquette"], **plus}, valide_par_un_humain=False)
        if self.bus is not None:  # la boîte noire écoute ce bus
            await self.bus.emettre("panne", SOURCE, quoi=ident, etat=etat, provoquee=True, etiquette=p["etiquette"],
                                   titre=p["titre"], **plus)

    def _connue(self, ident: str) -> dict[str, Any]:
        if ident not in PANNES:
            raise KeyError(ident)
        return PANNES[ident]

    async def provoquer(self, ident: str) -> dict[str, Any]:
        panne = self._connue(ident)
        if not panne["construite"]:
            raise PanneRefusee(f"« {panne['titre']} » : pas encore construite")
        if ident in self._actives:
            raise PanneRefusee(f"« {panne['titre']} » est déjà en cours")
        self._actives.append(ident)
        self._dit = ""
        if ident == "lien_robot" and self.systeme is not None and self.systeme.simulation is not None:
            self.systeme.simulation.provoquer_panne("perte_liaison")  # le faux robot s'arrête par son chien de garde
        elif ident in ABRI and self.systeme is not None:
            await self.systeme.prise.arreter_tout()  # arrêt normal : le robot s'arrête là où il est
        if ident == "cerveau_muet":
            self._muet(True)
        await self._noter(ident, "début")
        return {"panne": ident, "active": True, "etiquette": panne["etiquette"]}

    async def finir(self, ident: str, attendre: bool = False) -> dict[str, Any]:
        """La panne finit. Rien n'est perdu : les tâches en attente repartent (sauf si un humain doit d'abord réarmer)."""
        panne = self._connue(ident)
        if ident not in self._actives:
            raise PanneRefusee(f"« {panne['titre']} » n'est pas en cours")
        self._actives.remove(ident)
        if ident == "lien_robot" and self.systeme is not None and self.systeme.simulation is not None:
            self.systeme.simulation.reparer()
        if ident == "cerveau_muet":
            self._muet(False)
        rien = {"reparties": [], "en_attente": [], "dit": ""}
        retour = await self._repartir(attendre) if ident in ABRI and self.a_l_abri() is None else rien
        self._dit = retour["dit"]
        await self._noter(ident, "fin", reparties=retour["reparties"], en_attente=retour["en_attente"])
        return {"panne": ident, "active": False, **retour}

    async def relancer(self, attendre: bool = False) -> dict[str, Any]:
        """Après qu'un humain a réarmé le robot : les demandes qui attendaient repartent. Refusé pendant une panne."""
        if self.a_l_abri():
            raise PanneRefusee("le lien avec le robot est encore coupé, ou une autre panne est en cours : rien ne peut repartir")
        retour = await self._repartir(attendre)
        self._dit = retour["dit"]
        if self.taches is not None and retour["reparties"]:  # une relance à la main : c'est une aide humaine (avenant 2, K02)
            from . import aide_humaine

            for ident in retour["reparties"]:
                self.taches.noter_aide("relance", qui="équipe", tache=ident, detail="relancée après qu'un humain a réarmé le robot")
            await aide_humaine.ecrire_dans_la_boite(self.bus, self.taches)
        return retour

    def _muet(self, oui: bool) -> None:
        for piece in (self.resume, self.papiers):  # les pièces que le cerveau fait vivre
            if piece is not None:
                piece.muet = oui

    def _en_attente_du_lien(self) -> list[str]:
        if self.taches is None:
            return []
        return [t["id"] for t in self.taches._taches()
                if t.get("sorte") == "robot" and ((t["etat"] == "demandée" and t.get("en_attente"))
                                                  or (t["etat"] == "reprise" and t.get("panne") in ABRI))]

    async def _repartir(self, attendre: bool) -> dict[str, Any]:
        attendent = self._en_attente_du_lien()
        if not attendent:
            return {"reparties": [], "en_attente": [], "dit": ""}
        if self.coursier is None:
            return {"reparties": [], "en_attente": attendent,
                    "dit": "La panne est finie. Aucun robot n'est branché : les demandes au robot attendent toujours."}
        if self.systeme is not None and self.systeme.prise.arret_urgence_actif:
            return {"reparties": [], "en_attente": attendent,
                    "dit": "La panne est finie, mais le robot est à l'arrêt d'urgence : un humain doit le vérifier puis le "
                           f"réarmer. {len(attendent)} demande(s) au robot attendent. Rien n'est perdu."}
        for ident in attendent:
            if attendre:
                await self.coursier.faire(ident)
            else:
                self.coursier.lancer(ident)
        return {"reparties": attendent, "en_attente": [], "dit": ""}


# ---------------------------------------------------------------------- la page
SCRIPT = """<script>
document.querySelectorAll('button[data-panne]').forEach(b => b.onclick = async () => {
  const dit = document.getElementById('dit');
  const entetes = {};
  const code = document.getElementById('code').value;
  if (code) entetes['X-Code-Equipe'] = code;
  try {
    const r = await fetch('/api/clinique/pannes/' + b.dataset.panne + '/' + b.dataset.geste, {method: 'POST', headers: entetes});
    const j = await r.json();
    dit.textContent = r.ok ? (j.active ? 'Panne provoquée.' : 'Panne finie. ' + (j.dit || '')) : 'Refusé : ' + (j.detail || '');
    if (r.ok) setTimeout(() => location.reload(), 1500);
  } catch (erreur) { dit.textContent = 'Connexion perdue.'; }
});
document.getElementById('relancer').onclick = async () => {
  const dit = document.getElementById('dit');
  const entetes = {};
  const code = document.getElementById('code').value;
  if (code) entetes['X-Code-Equipe'] = code;
  try {
    const r = await fetch('/api/clinique/pannes/relancer', {method: 'POST', headers: entetes});
    const j = await r.json();
    dit.textContent = r.ok ? (j.dit || (j.reparties.length + ' demande(s) reparties.')) : 'Refusé : ' + (j.detail || '');
  } catch (erreur) { dit.textContent = 'Connexion perdue.'; }
};
</script>"""


def dessiner_pannes(pannes: Pannes) -> str:
    from .ecrans import _e

    lignes = []
    for p in pannes.etat():
        if not p["construite"]:
            bouton = "<i>pas encore construite</i>"
        elif p["active"]:
            bouton = f"<b>EN COURS</b> <button data-panne=\"{_e(p['id'])}\" data-geste='finir'>Finir la panne</button>"
        else:
            bouton = f"<button data-panne=\"{_e(p['id'])}\" data-geste='provoquer'>Provoquer</button>"
        lignes.append(f"<article><h3>{_e(p['titre'])} <small>[{_e(p['etiquette'])}]</small></h3>"
                      f"<p>{_e(p['ce_qui_se_passe'])} {_e(p['ce_que_le_systeme_fait'])} {_e(p['qui_est_prevenu'])}</p>"
                      f"<p>{bouton}</p></article>")
    return ("<p class='ou'>Pour l'équipe. Une panne provoquée est une panne d'entraînement : elle porte l'étiquette "
            "<b>SIMULÉ</b>. Pendant une panne, les écrans le disent. L'arrêt d'urgence passe toujours avant tout.</p>"
            "<p><label>Code d'équipe (depuis un autre ordinateur) <input id='code' size='12' type='password' "
            "autocomplete='off'></label></p><div class='dit' id='dit' role='status'></div>" + "".join(lignes)
            + "<article><h3>Après un arrêt d'urgence</h3><p>Si le robot s'est mis à l'arrêt d'urgence pendant une panne, "
              "un humain le vérifie et le réarme (écran de l'équipe). Ensuite, ce bouton fait repartir les demandes "
              "qui attendaient.</p><p><button id='relancer'>Relancer les demandes en attente</button></p></article>")


def brancher_pannes(app: FastAPI, clinique, protege: list) -> None:
    from .ecrans import _heure_html, _page

    from fastapi.responses import JSONResponse

    @app.middleware("http")
    async def lien_de_la_tablette(request, suite):
        """Panne « lien_tablette » : les échanges d'une page de liste déjà ouverte reçoivent « lien coupé »."""
        if (clinique.pannes.active("lien_tablette") and request.headers.get("x-tablette")
                and not request.url.path.startswith("/api/clinique/pannes/")):  # on peut toujours finir la panne
            return JSONResponse({"detail": "le lien avec cette tablette est coupé (panne provoquée, SIMULÉ)"}, status_code=503)
        return await suite(request)

    @app.get("/clinique/pannes", response_class=HTMLResponse)
    async def page_pannes():
        tete = f"<h1>Pannes</h1><span class='heure' id='heure'>{_heure_html(clinique.horloge.etat())}{clinique.pannes.bandeau()}</span>"
        return _page("Clinique — Pannes", tete, dessiner_pannes(clinique.pannes), SCRIPT)

    @app.get("/api/clinique/pannes")
    async def api_pannes():
        return {"marque": "données inventées", "pannes": clinique.pannes.etat()}

    async def geste(panne: str, lequel: str):
        try:
            if lequel == "provoquer":
                return await clinique.pannes.provoquer(panne)
            return await clinique.pannes.finir(panne)
        except KeyError:
            raise HTTPException(404, "Cette panne n'existe pas. La liste : /clinique/pannes")
        except PanneRefusee as refus:
            raise HTTPException(400, str(refus))

    @app.post("/api/clinique/pannes/relancer", dependencies=protege)
    async def api_relancer():
        try:
            return await clinique.pannes.relancer()
        except PanneRefusee as refus:
            raise HTTPException(400, str(refus))

    @app.post("/api/clinique/pannes/{panne}/provoquer", dependencies=protege)
    async def api_provoquer(panne: str):
        return await geste(panne, "provoquer")

    @app.post("/api/clinique/pannes/{panne}/finir", dependencies=protege)
    async def api_finir(panne: str):
        return await geste(panne, "finir")


# ---------------------------------------------------------------------- la commande : la panne jouée sur le faux robot
def demonstration(ident: str, dossier=None) -> dict[str, Any]:
    """Joue une panne sur le faux robot, avec les vraies pièces, et contrôle les quatre choses obligatoires."""
    import asyncio
    import tempfile
    from pathlib import Path

    from fastapi.testclient import TestClient

    from briques.b12_boite_noire.journal import lire
    from commun.systeme import REGLAGES_EXEMPLE, Systeme, charger_reglages

    from .coursier import monde_de_la_clinique
    from .ecrans import brancher_ecrans
    from .horloge import HorlogeDeDemonstration
    from .porte import JournalDesAcces, PorteDeLecture

    if not PANNES[ident]["construite"]:
        raise PanneRefusee(f"« {PANNES[ident]['titre']} » : pas encore construite")
    if ident not in ABRI:
        raise PanneRefusee(f"« {PANNES[ident]['titre']} » : cette panne se provoque sur la page /clinique/pannes, avec une "
                           "tablette ouverte sur une liste ; la commande joue : " + ", ".join(ABRI))
    reglages = charger_reglages(REGLAGES_EXEMPLE)
    reglages["cerveau"] = {**reglages["cerveau"], "choix": "regles"}
    temporaire = tempfile.TemporaryDirectory() if dossier is None else None
    dossier = Path(dossier if dossier is not None else temporaire.name)
    systeme = Systeme(reglages, dossier_journal=dossier / "journal", acceleration=20.0, monde=monde_de_la_clinique())
    horloge = HorlogeDeDemonstration(bus=systeme.bus)
    app = FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge), systeme=systeme, code_equipe="")
    client, soignant = TestClient(app), clinique.badges["soignant-etage-2"]
    clinique.listes.cocher(soignant, "p01", "installation", 1)  # une coche AVANT la panne

    def gestes() -> list[str]:
        return [e.donnees["action"]["nom"] for e in systeme.bus.historique if e.type == "action_demarree" and e.donnees.get("action")]

    async def scene():
        await systeme.demarrer()
        arrets = []
        arreter = systeme.prise.arreter_tout

        async def arreter_et_compter(*a, **k):  # on compte les arrêts normaux demandés à la prise
            arrets.append(1)
            return await arreter(*a, **k)

        systeme.prise.arreter_tout = arreter_et_compter
        try:
            await clinique.pannes.provoquer(ident)
            bandeau = client.get("/clinique/heure").text
            demande = clinique.taches.demander(soignant, "p01", "une couverture")["tache"]  # une demande PENDANT la panne
            pendant = await clinique.coursier.faire(demande["id"])
            gestes_pendant = gestes()
            decisions = len([e for e in systeme.bus.historique if e.type == "gardien_decision"])
            clinique.listes.cocher(soignant, "p01", "installation", 2)  # ce qui marche sans le robot continue
            mal_entendu = None
            if ident == "micro_bruit":  # une phrase dite pendant la panne arrive à la chaîne de l'ossature comme du bruit
                coches = len(clinique.carnet.lignes("point de liste"))
                texte, confiance = clinique.pannes.entendre("va à la Réserve")
                await systeme.chaine.traiter(texte, "fr", confiance_ecoute=confiance, source="micro")
                mal_entendu = {"texte": texte, "confiance": confiance, "gestes": len(gestes()),
                               "coches_en_plus": len(clinique.carnet.lignes("point de liste")) - coches}
            retour = await clinique.pannes.finir(ident, attendre=True)
            return bandeau, demande, pendant, gestes_pendant, decisions, retour, len(arrets), mal_entendu
        finally:
            await systeme.arreter()

    bandeau, demande, pendant, gestes_pendant, decisions, retour, arrets_demandes, mal_entendu = asyncio.run(scene())
    p = PANNES[ident]
    notes = [e for e in lire(systeme.boite_noire.fichier) if e.type == "panne" and e.source == SOURCE]
    points = {x["numero"]: x["etat"] for x in clinique.listes.liste(soignant, "p01", "installation")["points"]}
    finale = clinique.taches.tache(demande["id"])
    choses = {
        1: pendant["etat"] == "demandée" and bool(pendant.get("en_attente")) and gestes_pendant == [] and decisions == 0
           and (ident == "lien_robot" or arrets_demandes == 1)
           and (mal_entendu is None or (mal_entendu["gestes"] == 0 and mal_entendu["coches_en_plus"] == 0)),
        2: all(m in bandeau for m in (p["ce_qui_se_passe"], p["ce_que_le_systeme_fait"], p["qui_est_prevenu"], p["etiquette"])),
        3: [(e.donnees["quoi"], e.donnees["etat"]) for e in notes] == [(ident, "début"), (ident, "fin")]
           and [l["donnees"]["etat"] for l in clinique.carnet.lignes(GENRE)] == ["début", "fin"],
        4: points.get(1) == "fait" and points.get(2) == "fait" and finale["etat"] == "livrée"
           and retour["reparties"] == [demande["id"]],
    }
    lignes = [
        f"PANNE PROVOQUÉE [{p['etiquette']}] — {p['titre']} — testé sur FAUX ROBOT — DONNÉES INVENTÉES",
        f"1. {'oui' if choses[1] else 'NON'} — le robot ne commence rien de nouveau : une demande arrivée pendant la panne "
        f"reste « {pendant['etat']} » ({pendant.get('en_attente', '?')}) ; {len(gestes_pendant)} geste parti, {decisions} "
        f"demande au gardien",
        f"2. {'oui' if choses[2] else 'NON'} — l'écran le dit : « {p['ce_qui_se_passe']} {p['ce_que_le_systeme_fait']} {p['qui_est_prevenu']} »",
        f"3. {'oui' if choses[3] else 'NON'} — la boîte noire l'écrit : {len(notes)} événements « panne » (début, fin) ; le carnet : "
        f"{len(clinique.carnet.lignes(GENRE))} lignes",
        f"4. {'oui' if choses[4] else 'NON'} — rien n'est perdu : la coche d'avant et la coche faite pendant la panne sont là ; la "
        f"demande en attente est repartie à la fin de la panne : « {finale['etat']} » ({', '.join(gestes())})",
        *([f"   une phrase mal entendue pendant la panne (« {mal_entendu['texte']} », confiance {mal_entendu['confiance']}) : "
           f"{mal_entendu['gestes']} geste parti, {mal_entendu['coches_en_plus']} coche"] if mal_entendu else []),
        *([f"   arrêt normal demandé à la prise au début de la panne : {arrets_demandes} fois"] if ident != "lien_robot" else []),
        "Limite : la panne tombe ici avant le départ du robot. Le cas « en pleine course » est essayé pour le lien seulement.",
        "PANNE : TENUE" if all(choses.values()) else "PANNE : PAS TENUE — " + ", ".join(str(n) for n, ok in choses.items() if not ok),
    ]
    resultat = {"ok": all(choses.values()), "choses": choses, "lignes": lignes, "clinique": clinique, "systeme": systeme,
                "bandeau": bandeau, "demande": demande, "pendant": pendant, "gestes_pendant": gestes_pendant,
                "decisions_pendant": decisions, "retour": retour, "notes": notes, "points": points, "gestes": gestes(),
                "arrets_demandes": arrets_demandes, "mal_entendu": mal_entendu,
                "client": client}
    if temporaire is not None:
        temporaire.cleanup()
    return resultat


def main(reste: list[str] | None = None) -> int:
    reste = reste or []
    if not reste:
        print("LES PANNES PROVOQUÉES — la clinique en boîte — chaque panne porte l'étiquette SIMULÉ")
        for ident, p in PANNES.items():
            print(f"- {ident} [{p['etiquette']}] {p['titre']}" + ("" if p["construite"] else " — pas encore construite"))
        print("Pour en jouer une sur le faux robot : python3 lancer.py pannes lien_robot")
        return 0
    if reste[0] not in PANNES:
        print(f"Panne inconnue « {reste[0]} ». Connues : {', '.join(PANNES)}")
        return 2
    try:
        resultat = demonstration(reste[0])
    except PanneRefusee as refus:
        print(str(refus))
        return 2
    for ligne in resultat["lignes"]:
        print(ligne)
    return 0 if resultat["ok"] else 1
