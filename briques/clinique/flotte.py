"""La flotte, version simple : une panne, une reprise (cahier 4.2 scène 6, 5.10, 6.6 ; tâche T11c).

    flotte = Flotte(tableau, carnet, coursier)
    flotte.partir("robot-r3", "t1")          # R3, simulé, part faire la course : « attribuée », « en route »
    flotte.panne("robot-r3", "batterie basse")   # panne provoquée : la tâche passe « reprise », et c'est écrit
    await flotte.reprendre("t1")             # R1 (le robot branché) finit la course, par le coursier, sous le gardien

DIRE VRAI :
- R2, R3, R4 n'existent que dans l'ordinateur (« FAUX ROBOT — SIMULÉ »). Pour eux, le programme écrit seulement des
  états dans le carnet : rien ne bouge, donc rien à demander au gardien. Un robot simulé ne « livre » jamais.
- Seul le robot branché sur la prise (R1) peut finir une course, et seulement par le coursier : chaque geste a
  d'abord un « oui » du gardien.
- Si aucun robot ne peut reprendre la course, un humain reprend la main, et c'est écrit dans le carnet.
- Une panne est toujours « provoquée » ici : on la déclenche exprès, pour la démonstration.

Version simple. Viendront avec R5 et T22 à T25 : les cartes de rôle appliquées par le gardien, le choix du robot
libre le plus proche, la batterie, les robots qui se déplacent sur le plan, le tableau de flotte complet.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .carnet import Carnet
from .porte import Badge
from .taches import TableauDesTaches

FICHIER = Path(__file__).resolve().parent / "flotte.yaml"
GENRE_PANNE = "panne de robot"
ETIQUETTE_SIMULE = "FAUX ROBOT — SIMULÉ"
EN_COURSE = ("attribuée", "en route")


class Flotte:
    def __init__(self, tableau: TableauDesTaches, carnet: Carnet, coursier=None, fichier: Path = FICHIER,
                 cartes=None, carte_r1=None) -> None:
        # cartes : les cartes de rôle (cartes.CartesDeLaFlotte). carte_r1 : la carte de R1 chez le gardien (cartes_gardien).
        self.cartes, self.carte_r1 = cartes, carte_r1
        donnees = yaml.safe_load(Path(fichier).read_text(encoding="utf-8"))
        if donnees.get("marque") != "inventé":
            raise ValueError("flotte.yaml : la marque « inventé » manque")
        self.tableau, self.carnet, self.coursier = tableau, carnet, coursier
        self._robots: dict[str, dict[str, Any]] = {r["id"]: dict(r) for r in donnees["robots"]}
        self._badges = {i: Badge(id=i, role="robot", libelle=f"Robot {r['nom']}") for i, r in self._robots.items()}

    # ------------------------------------------------------------------ lire
    def _robot(self, ident: str) -> dict[str, Any]:
        if ident not in self._robots:
            raise ValueError(f"robot inconnu « {ident} »")
        return self._robots[ident]

    def _etiquette(self, robot: dict[str, Any]) -> str:
        if robot["simule"]:
            return ETIQUETTE_SIMULE
        return self.coursier.etiquette() if self.coursier is not None else "FAUX ROBOT"

    def _pannes(self, ident: str) -> list[dict[str, Any]]:
        return [l for l in self.carnet.lignes(GENRE_PANNE) if l["donnees"]["robot"] == ident]

    def _course(self, ident: str) -> dict[str, Any] | None:
        """La tâche que ce robot est en train de faire, s'il y en a une."""
        for tache in self.tableau._taches():
            if tache.get("robot") == ident and tache["etat"] in EN_COURSE:
                return tache
        return None

    def robots(self) -> list[dict[str, Any]]:
        """Les quatre robots : nom, carte, étiquette, état, tâche en cours. Aucun nom de patient."""
        vus = []
        for ident, robot in self._robots.items():
            pannes, course = self._pannes(ident), self._course(ident)
            if pannes:
                etat = "en panne"
            elif course:
                etat = "en course"
            elif not robot["simule"] and self.coursier is None:
                etat = "pas branché"
            else:
                etat = "libre"
            carte = self.cartes.carte_de(ident).nom if self.cartes is not None else robot["carte"]
            vus.append({"id": ident, "nom": robot["nom"], "carte": carte, "simule": robot["simule"],
                        "etiquette": self._etiquette(robot), "etat": etat,
                        "panne": pannes[-1]["donnees"]["raison"] if pannes else None,
                        "panne_provoquee": bool(pannes[-1]["donnees"].get("provoquee")) if pannes else False,
                        "tache": {"id": course["id"], "quoi": course["quoi"], "ou": course["ou"]} if course else None})
        return vus

    def compte(self) -> dict[str, Any]:
        simules = sum(1 for r in self._robots.values() if r["simule"])
        return {"robots": len(self._robots), "simules": simules, "texte": f"{simules} robots simulés sur {len(self._robots)}"}

    def courses(self) -> list[dict[str, Any]]:
        """Les tâches de robot, pour la page de la flotte : quoi, où, état, robot. Aucun nom de patient."""
        return [{cle: t.get(cle) for cle in ("id", "quoi", "de", "ou", "etat", "robot", "etiquette", "repris_de",
                                             "sorte", "pourquoi", "pourquoi_un_humain")}
                for t in self.tableau._taches() if t.get("robot") or t.get("repris_de")]

    async def changer_carte(self, ident: str, carte: str, qui: str) -> dict[str, str]:
        """Un robot change de métier. Pour R1, le robot branché, le gardien relit ses règles tout de suite."""
        robot = self._robot(ident)
        if self.cartes is None:
            raise ValueError("les cartes de rôle ne sont pas branchées")
        if not robot["simule"] and self.carte_r1 is not None:
            return await self.carte_r1.changer(carte, qui)
        return self.cartes.changer(ident, carte, qui)

    def changements_de_carte(self) -> list[str]:
        if self.cartes is None:
            return []
        return [f"{self._robots[c['robot']]['nom']} : carte {c['avant']} → {c['apres']} (par {c['qui']})" for c in self.cartes.changements]

    def ou_en_est_la_carte(self) -> str:
        """Dire vrai sur la page : qui applique la carte, aujourd'hui."""
        if self.cartes is None:
            return "Version simple : la carte est affichée, elle n'est pas encore appliquée par le gardien."
        simules = "Les robots simulés ne bougent pas sur cette page : leur carte est affichée."
        if self.carte_r1 is None:
            return f"La carte de R1 n'est pas appliquée par le gardien : aucun robot n'est branché. {simules}"
        if not self.carte_r1.appliquee():  # relecture de la tranche 3 : ne pas dire « appliquée » avant que le gardien l'ait
            return (f"La carte de R1 ({self.carte_r1.carte.nom}) n'est pas encore chez le gardien : elle lui est donnée au démarrage "
                    f"du serveur de pages, ou au plus tard avant le premier geste du coursier. {simules}")
        return (f"La carte de R1 ({self.carte_r1.carte.nom}) est appliquée par le gardien : lieux et vitesse ; "
                f"les actions sont contrôlées avant lui. {simules}")

    # ------------------------------------------------------------------ un robot simulé part
    def partir(self, ident: str, tache: str) -> dict[str, Any]:
        """Un robot SIMULÉ prend une tâche et se met en route. Le programme écrit ses états, rien ne bouge."""
        robot = self._robot(ident)
        if not robot["simule"]:
            raise ValueError(f"{robot['nom']} est le robot branché : il part par le coursier, sous le gardien")
        if self._pannes(ident):
            raise ValueError(f"{robot['nom']} est en panne")
        actuelle = self.tableau.tache(tache)
        if actuelle["sorte"] != "robot" or actuelle["etat"] not in ("demandée", "reprise"):
            raise ValueError(f"cette tâche n'attend pas un robot (elle est « {actuelle['etat']} », pour un {actuelle['sorte']})")
        badge = self._badges[ident]
        self.tableau.changer_etat(badge, tache, "attribuée", robot=ident, etiquette=ETIQUETTE_SIMULE)
        return self.tableau.changer_etat(badge, tache, "en route")

    # ------------------------------------------------------------------ la panne
    def panne(self, ident: str, raison: str) -> dict[str, Any] | None:
        """Panne PROVOQUÉE d'un robot simulé. S'il était en course, la tâche passe « reprise ». Rend cette tâche."""
        robot = self._robot(ident)
        if not robot["simule"]:
            raise ValueError(f"{robot['nom']} est le robot branché : sa panne se provoque avec le chef de démonstration")
        raison = " ".join(str(raison).split())[:80] or "panne"
        course, badge = self._course(ident), self._badges[ident]
        self.carnet.ecrire(badge, GENRE_PANNE, {"robot": ident, "nom": robot["nom"], "raison": raison, "provoquee": True,
                                                "etiquette": ETIQUETTE_SIMULE, "tache": course["id"] if course else None},
                           valide_par_un_humain=False)
        if course is None:
            return None
        return self.tableau.changer_etat(badge, course["id"], "reprise", repris_de=ident,
                                         pourquoi=f"{robot['nom']} en panne : {raison} (panne provoquée)")

    # ------------------------------------------------------------------ la reprise
    async def reprendre(self, tache: str) -> dict[str, Any]:
        """Un autre robot finit la course : le robot branché, par le coursier, sous le gardien. Sinon : un humain."""
        actuelle = self.tableau.tache(tache)
        if actuelle["etat"] != "reprise" or actuelle["sorte"] != "robot":
            raise ValueError("on ne reprend qu'une tâche de robot à l'état « reprise »")
        branche = next((i for i, r in self._robots.items() if not r["simule"]), None)
        if self.coursier is None or branche is None:
            return self._a_un_humain(tache, actuelle, "aucun robot n'est branché")
        if self._pannes(branche):
            return self._a_un_humain(tache, actuelle, f"{self._robots[branche]['nom']} est en panne")
        fin = await self.coursier.faire(tache)
        if fin["etat"] == "livrée":
            return fin
        return self._a_un_humain(tache, fin, fin.get("pourquoi") or f"la course est « {fin['etat']} »")

    def _a_un_humain(self, tache: str, actuelle: dict[str, Any], raison: str) -> dict[str, Any]:
        badge = self._badges.get(actuelle.get("repris_de") or "") or next(iter(self._badges.values()))
        return self.tableau.changer_etat(badge, tache, "reprise", sorte="humain",
                                         pourquoi_un_humain=f"aucun robot ne peut reprendre la course ({raison})")


# ---------------------------------------------------------------------- la page
def dessiner_flotte(flotte: Flotte) -> str:
    from .ecrans import _e

    rangs = "".join(
        f"<tr><td><b>{_e(r['nom'])}</b></td><td>{_e(r['carte'])}</td><td>{_e(r['etiquette'])}</td>"
        f"<td><b>{_e(r['etat'])}</b>{' : ' + _e(r['panne']) + (' (panne provoquée)' if r['panne_provoquee'] else '') if r['panne'] else ''}</td>"
        f"<td>{_e(r['tache']['quoi']) + ' → ' + _e(r['tache']['ou']) if r['tache'] else '—'}</td></tr>"
        for r in flotte.robots())
    courses = "".join(
        f"<li><b>{_e(c['quoi'])}</b> : {_e(c.get('de') or '?')} → {_e(c['ou'])} — <b>{_e(c['etat'])}</b>"
        f"{' — pour un humain' if c['sorte'] == 'humain' else ''}"
        f"{' — robot : ' + _e(c['robot']) if c.get('robot') else ''}"
        f"{' [' + _e(c['etiquette']) + ']' if c.get('etiquette') else ''}"
        f"{' — reprise de ' + _e(c['repris_de']) if c.get('repris_de') else ''}"
        f"{' — ' + _e(c['pourquoi_un_humain'] or c['pourquoi']) if c.get('pourquoi_un_humain') or c.get('pourquoi') else ''}</li>"
        for c in flotte.courses())
    return (f"<p><b>{_e(flotte.compte()['texte'])}.</b> Un robot simulé n'existe que dans l'ordinateur : rien ne bouge.</p>"
            f"<table><tr><th>Robot</th><th>Carte</th><th>Étiquette</th><th>État</th><th>Tâche</th></tr>{rangs}</table>"
            f"<p class='ou'>{_e(flotte.ou_en_est_la_carte())} Pas de plan, pas de batterie.</p>"
            + (f"<article><h2>Changements de carte</h2><ul>{''.join(f'<li>{_e(c)}</li>' for c in flotte.changements_de_carte())}</ul></article>"
               if flotte.changements_de_carte() else "")
            + (f"<article><h2>Courses</h2><ul>{courses}</ul></article>" if courses else ""))


def brancher_flotte(app, clinique) -> None:
    from fastapi.responses import HTMLResponse

    from .ecrans import _heure_html, _page, script_de_mise_a_jour

    @app.get("/clinique/flotte", response_class=HTMLResponse)
    async def page_flotte():
        tete = f"<h1>Flotte</h1><span class='heure' id='heure'>{_heure_html(clinique.horloge.etat())}</span>"
        return _page("Clinique — Flotte", tete, dessiner_flotte(clinique.flotte), script_de_mise_a_jour("/clinique/flotte/contenu"))

    @app.get("/clinique/flotte/contenu", response_class=HTMLResponse)
    async def page_flotte_contenu():
        return dessiner_flotte(clinique.flotte)

    @app.get("/api/clinique/flotte")
    async def api_flotte():
        return {"marque": "données inventées", "compte": clinique.flotte.compte(), "robots": clinique.flotte.robots(),
                "courses": clinique.flotte.courses()}


# ---------------------------------------------------------------------- la grande répétition
def etape_12():
    """Étape 12 : un robot tombe en panne, un autre reprend. R3 simulé tombe en panne ; R1, faux robot, finit."""
    import asyncio
    import tempfile

    from commun.systeme import REGLAGES_EXEMPLE, Systeme, charger_reglages

    from .coursier import Coursier, monde_de_la_clinique
    from .horloge import HorlogeDeDemonstration
    from .listes import ListesDeSoin
    from .porte import JournalDesAcces, PorteDeLecture, charger_badges
    from .repetition import Resultat

    reglages = charger_reglages(REGLAGES_EXEMPLE)
    reglages["cerveau"] = {**reglages["cerveau"], "choix": "regles"}
    badges = charger_badges()

    async def jouer(dossier: str):
        systeme = Systeme(reglages, dossier_journal=dossier, acceleration=20.0, monde=monde_de_la_clinique())
        horloge = HorlogeDeDemonstration(bus=systeme.bus)
        carnet = Carnet(horloge=horloge)
        listes = ListesDeSoin(PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), carnet)
        tableau = TableauDesTaches(listes.porte, carnet, listes)
        coursier = Coursier(systeme, tableau, listes, badges["robot-r1"])
        flotte = Flotte(tableau, carnet, coursier)
        tache = tableau.demander(badges["soignant-etage-2"], "p01", "la feuille d'exercices")["tache"]
        flotte.partir("robot-r3", tache["id"])
        en_panne = flotte.panne("robot-r3", "batterie basse")
        await systeme.demarrer()
        try:
            fin = await flotte.reprendre(tache["id"])
        finally:
            await systeme.arreter()
        oui = [e for e in systeme.bus.historique if e.type == "gardien_decision" and e.donnees["verdict"] == "oui"]
        partis = [e for e in systeme.bus.historique if e.type == "action_demarree" and e.donnees.get("action")]
        etats = [l["donnees"]["etat"] for l in carnet.lignes("tâche") if l["donnees"]["id"] == tache["id"]]
        return en_panne, fin, (len(oui), len(partis)), etats, len(carnet.lignes(GENRE_PANNE)), coursier.etiquette(), flotte.compte()

    with tempfile.TemporaryDirectory() as dossier:
        en_panne, fin, (oui, partis), etats, pannes, etiquette_r1, compte = asyncio.run(jouer(dossier))
    reussie = (bool(en_panne) and en_panne["etat"] == "reprise" and fin["etat"] == "livrée" and fin.get("robot") == "robot-r1"
               and fin.get("repris_de") == "robot-r3" and oui == 4 and partis == 4 and pannes == 1 and "reprise" in etats)
    r1 = "faux robot" if etiquette_r1 == "FAUX ROBOT" else "vrai robot"
    if fin["etat"] == "livrée":
        suite = (f"R1 ({r1}) finit la course par le coursier : {oui} « oui » du gardien, {partis} gestes partis ; "
                 f"tâche {fin['etat']} ({fin.get('quoi')}, {fin.get('de')} → {fin.get('ou')})")
    else:
        suite = (f"aucun robot n'a repris la course : tâche « {fin['etat']} », passée à un humain "
                 f"({fin.get('pourquoi_un_humain') or fin.get('pourquoi') or '?'})")
    return Resultat(reussie, "SIMULÉ",
                    f"{compte['texte']} ; R3 est simulé : le programme écrit ses états, rien ne bouge ; panne provoquée "
                    f"(batterie basse) en route : la tâche passe « reprise » ; {suite} ; version simple : pas de cartes "
                    f"appliquées, pas de choix du plus proche")
