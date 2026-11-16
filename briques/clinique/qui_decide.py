"""La page « Qui décide » (avenant jury, tâche J05 ; seconde moitié : J05b).

« Qu'est-ce qui change pour les soignants, et qui l'a décidé ? » Pour chaque chose que fait le système : qui peut
l'allumer, qui peut la mettre en pause, qui est prévenu, et ce que le système ne fait jamais seul.

Cette page n'est pas écrite à la main. Elle se fabrique à partir des réglages réels :
- les droits des badges : on demande aux vraies pièces (le tableau des tâches, les listes, les pauses, les papiers, le
  résumé, le soir, l'accueil du hall) ce qu'elles laissent faire à un badge de chaque métier ;
- les cartes de rôle et la carte de chaque robot (`cartes_de_role/`, `flotte.yaml`) ;
- la règle du hall (`accueil_hall.yaml`).
Si un réglage change, la page change.

DIRE VRAI : la page dit ce que le système FAIT et laisse faire aujourd'hui, sur le prototype (données inventées). Elle ne
promet rien sur le travail des équipes : rien de tel n'a été mesuré.
"""
from __future__ import annotations

from typing import Any, Callable

from . import accueil as accueil_du_hall
from . import dossier
from .cartes import CartesDeLaFlotte
from .porte import ROLES, AccesRefuse, JournalDesAcces, PorteDeLecture, charger_badges

HALL = "Hall"


def droits() -> dict[str, list[str]]:
    """Pour chaque geste d'une personne : les métiers dont le badge a le droit. Demandé aux vraies pièces, sur une
    clinique d'essai en mémoire : un refus de la porte veut dire « non », tout le reste veut dire « oui »."""
    from .accueil import AccueilDuHall
    from .carnet import Carnet
    from .horloge import HorlogeDeDemonstration
    from .listes import ListesDeSoin
    from .papiers import Papiers
    from .pauses import Pauses
    from .resume import ResumeDuMedecin
    from .soir import LeSoir
    from .taches import TableauDesTaches

    badges = charger_badges()
    un_par_metier = {role: next((b for b in badges.values() if b.role == role), None) for role in ROLES}
    liste = str(dossier.charger().patient("p01")["CarePlan"][0])
    trouves: dict[str, list[str]] = {}

    def essayer(nom: str, geste: Callable[[dict[str, Any], Any], Any]) -> None:
        permis = []
        for role, badge in un_par_metier.items():
            if badge is None:
                continue
            horloge = HorlogeDeDemonstration()  # une clinique neuve à chaque question : rien ne déborde
            porte = PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour)
            carnet = Carnet(horloge=horloge)
            listes = ListesDeSoin(porte, carnet)
            taches = TableauDesTaches(porte, carnet, listes)
            pieces = {"porte": porte, "carnet": carnet, "horloge": horloge, "listes": listes, "taches": taches, "badges": badges,
                      "pauses": Pauses(porte, carnet, horloge), "papiers": Papiers(porte, carnet),
                      "resume": ResumeDuMedecin(porte, carnet, horloge), "soir": LeSoir(porte, carnet, horloge, taches, badges),
                      "accueil": AccueilDuHall(porte, carnet, un_par_metier["robot"])}
            try:
                geste(pieces, badge)
            except AccesRefuse:
                continue
            except Exception:  # une autre erreur (pas l'heure, pas le bon moment) : la porte, elle, a laissé passer
                pass
            permis.append(role)
        trouves[nom] = permis

    essayer("demander une livraison", lambda p, b: p["taches"].demander(b, "p01", "la couverture"))
    essayer("cocher un point d'une liste", lambda p, b: p["listes"].cocher(b, "p01", liste, 1))
    essayer("mettre une pause", lambda p, b: p["pauses"].mettre(b, "rouler", 1, "autre"))
    essayer("ranger un papier", lambda p, b: p["papiers"].pile(b))
    essayer("lire le résumé du matin", lambda p, b: p["resume"].tous(b))
    essayer("poser une question du soir", lambda p, b: p["soir"].poser(b, "question d'essai"))
    essayer("voir les messages du hall pour l'étage", lambda p, b: p["accueil"].messages_pour_l_etage(b))
    essayer("voir les appels du robot du hall", lambda p, b: p["accueil"].appels(b))
    return trouves


def _et(mots: list[str], rien: str = "personne") -> str:
    return ", ".join(mots) if mots else rien


def table(flotte: CartesDeLaFlotte | None = None) -> list[dict[str, str]]:
    """Les sept choses que fait le système, chacune avec ses quatre réponses, fabriquées à partir des réglages."""
    flotte = flotte or CartesDeLaFlotte()
    d = droits()
    robots = [(r["nom"], flotte.carte_de(r["id"])) for r in flotte.robots()]

    def avec(condition: Callable[[Any], bool]) -> list[str]:
        return [f"{nom} (carte {carte.nom})" for nom, carte in robots if condition(carte)]

    au_hall = avec(lambda c: HALL in c.lieux_permis and c.refus_action("parler") is None)
    cartes_du_hall = [c.nom for c in flotte.cartes.values() if HALL in c.lieux_permis]
    livreurs = avec(lambda c: all(c.refus_action(a) is None for a in ("se_deplacer", "saisir", "poser")))
    hall = (f"le robot du hall : {_et(au_hall)}" if au_hall else
            f"aucun robot n'a aujourd'hui une carte qui permet le hall (cartes : {_et(cartes_du_hall)})")
    regle_du_hall = accueil_du_hall._reglages()["regle_sante"]["phrase"]
    etage, coche = _et(d["voir les messages du hall pour l'étage"]), _et(d["cocher un point d'une liste"])
    pause = f"{_et(d['mettre une pause'])}, pour son étage (rouler, parler, livrer, entrer dans une chambre)"
    return [
        {"chose": "accueillir",
         "allume": f"la personne qui arrive, en disant son nom ; {hall}",
         "pause": pause,
         "prevenu": f"l'étage ({etage}) ; si le nom est inconnu : {_et(d['voir les appels du robot du hall'])}",
         "jamais_seul": f"{regle_du_hall} Nom inconnu ou phrase pas comprise : il appelle une personne. Aucun visage, aucun dossier affiché."},
        {"chose": "orienter",
         "allume": f"la même arrivée : le chemin s'affiche ; {hall}",
         "pause": pause,
         "prevenu": f"l'étage ({etage})",
         "jamais_seul": "Il n'accompagne pas la personne et ne prend pas l'ascenseur. Étage inconnu : il appelle une personne."},
        {"chose": "livrer",
         "allume": f"une demande de : {_et(d['demander une livraison'])} ; faite par : {_et(livreurs, 'aucun robot')}",
         "pause": pause,
         "prevenu": f"qui a demandé, sur le tableau des tâches ({_et(d['demander une livraison'])})",
         "jamais_seul": "Aucun geste sans le « oui » du gardien. Objet absent, lieu hors du plan ou hors de la carte : la demande passe à un humain."},
        {"chose": "rappeler un point",
         "allume": f"la liste de soin, cochée par : {coche}",
         "pause": "pas de pause : rien ne se fait sans la personne qui coche",
         "prevenu": f"la personne qui coche ({coche})",
         "jamais_seul": "Le système ne coche rien à la place d'une personne. Il rappelle le point oublié, c'est tout."},
        {"chose": "résumer pour le médecin",
         "allume": f"lu par : {_et(d['lire le résumé du matin'])}",
         "pause": "pas de pause : le résumé ne fait aucun geste",
         "prevenu": _et(d["lire le résumé du matin"]),
         "jamais_seul": "Aucun avis, aucun diagnostic, aucune dose. Chaque phrase montre sa source ; une phrase sans source est retirée."},
        {"chose": "poser les questions du soir",
         "allume": f"écrites par : {_et(d['poser une question du soir'])}",
         "pause": "pas de pause : la question attend le médecin",
         "prevenu": _et(d["lire le résumé du matin"]),
         "jamais_seul": "Le système ne répond jamais à une question de santé : il la transmet."},
        {"chose": "ranger un papier",
         "allume": f"proposé par le système, validé par : {_et(d['ranger un papier'])}",
         "pause": "pas de pause : rien n'est rangé sans validation",
         "prevenu": _et(d["ranger un papier"]),
         "jamais_seul": "Rien n'est rangé sans la validation d'une personne. Pas sûr, ou aucun patient ne correspond : le papier attend dans « à trier »."},
    ]


def dessiner() -> str:
    from .ecrans import _e

    rangs = "".join(f"<tr><td><b>{_e(l['chose'])}</b></td><td>{_e(l['allume'])}</td><td>{_e(l['pause'])}</td>"
                    f"<td>{_e(l['prevenu'])}</td><td>{_e(l['jamais_seul'])}</td></tr>" for l in table())
    return ("<p class='ou'>Données inventées. Cette page est fabriquée à partir des réglages du prototype : les droits des "
            "badges (demandés aux pièces elles-mêmes), les cartes de rôle, la carte de chaque robot, la règle du hall. Si un "
            "réglage change, elle change. Elle dit ce que le système fait et laisse faire ; elle ne promet rien d'autre.</p>"
            "<table><tr><th>Ce que fait le système</th><th>Qui peut l'allumer</th><th>Qui peut la mettre en pause</th>"
            f"<th>Qui est prévenu</th><th>Ce que le système ne fait jamais seul</th></tr>{rangs}</table>")


def brancher_qui_decide(app) -> None:
    from fastapi.responses import HTMLResponse

    from .ecrans import _page

    @app.get("/clinique/qui-decide", response_class=HTMLResponse)
    async def page_qui_decide():
        return _page("Clinique — Qui décide", "<h1>Qui décide</h1>", dessiner(), "")

    @app.get("/api/clinique/qui-decide")
    async def api_qui_decide():
        return {"marque": "données inventées", "droits": droits(), "table": table()}
