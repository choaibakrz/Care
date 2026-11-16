"""Le répartiteur et le relais (cahier 5.10 et 6.6 ; tâche T23).

    rep = Repartiteur(monde, cartes)          # monde : le monde des robots (R5) ; cartes : les cartes de rôle (T22)
    choix = rep.choisir(tache)                # le robot choisi, tous les robots regardés, et pourquoi
    rep.attribuer(tableau, "t1")              # écrit le choix sur la tâche ; un robot simulé part dans le monde simulé

Le répartiteur : pour une tâche de robot, il choisit le robot LIBRE le plus PROCHE, qui a la BONNE CARTE (ses lieux et ses
gestes le permettent) et ASSEZ DE BATTERIE pour le trajet. Il garde la liste des robots regardés, avec la raison de chacun.
Le relais : un robot ne sort pas de ses lieux permis. Si aucun robot ne peut faire tout le trajet, deux robots peuvent se
passer la main à un lieu que leurs deux cartes permettent. Sinon, la tâche passe à un humain, et c'est écrit.
(Le robot du hall, lui, passe la main par un message pour l'étage : c'est l'accueil, tâche T10.)

DIRE VRAI : R2, R3, R4 sont SIMULÉS (des points sur un plan inventé ; rien ne bouge). R1 est le robot branché : s'il est
choisi, le répartiteur ne le fait pas bouger ; la course se fait par le coursier, sous le gardien. Les mètres et la
batterie sont inventés. Un relais est proposé, pas encore joué.
"""
from __future__ import annotations

from typing import Any

from .cartes import CartesDeLaFlotte
from .monde_robots import ETIQUETTE_BRANCHE, MondeDesRobots
from .porte import Badge

GESTES = ("se_deplacer", "saisir", "poser")
BADGE = Badge(id="repartiteur", role="robot", libelle="Répartiteur")


class Repartiteur:
    def __init__(self, monde: MondeDesRobots, cartes: CartesDeLaFlotte) -> None:
        self.monde, self.cartes = monde, cartes

    # ------------------------------------------------------------------ regarder chaque robot
    def _regarder(self, robot: dict[str, Any], de: str, ou: str, pour_de_vrai: bool = False) -> dict[str, Any]:
        carte = self.cartes.carte_de(robot["id"])
        refus = [r for r in [carte.refus_lieu(de), carte.refus_lieu(ou)] + [carte.refus_action(g) for g in GESTES] if r]
        metres = self.monde.distance(robot["id"], de)
        trajet = self.monde.chemin(de, ou)
        # relecture de la tranche 3 : les lieux TRAVERSÉS comptent aussi, pas seulement le départ et l'arrivée
        aller = self.monde.chemin(self.monde._robot(robot["id"])["lieu"], de)
        traverses = (aller[0] if aller else []) + (trajet[0] if trajet else [])
        en_chemin = [f"{r}, qui est sur le trajet" for r in dict.fromkeys(carte.refus_lieu(lieu) for lieu in traverses) if r]
        besoin = None if metres is None or trajet is None else (metres + trajet[1]) * self.monde.conso
        libre = robot["etat"] == "libre"
        if pour_de_vrai and robot["simule"]:  # une vraie livraison : un robot simulé n'existe que dans l'ordinateur
            raison = "simulé : il n'existe que dans l'ordinateur, il ne peut pas livrer pour de vrai"
        elif robot["etat"] == "en panne":
            raison = f"en panne ({robot['panne']})"
        elif not libre:
            raison = f"occupé ({robot['etat']})"
        elif refus:
            raison = refus[0]
        elif besoin is None:
            raison = "pas de chemin (les robots ne changent pas d'étage)"
        elif robot["batterie"] - besoin <= self.monde.seuil:  # « <= » comme le monde : à la limite, il tomberait en panne à l'arrivée
            raison = f"pas assez de batterie ({robot['batterie']:.0f} %, il en faut {besoin + self.monde.seuil:.0f})"
        elif en_chemin:
            raison = en_chemin[0]
        else:
            raison = ""
        return {"id": robot["id"], "nom": robot["nom"], "carte": carte.nom, "etiquette": robot["etiquette"], "libre": libre,
                "metres": metres, "batterie": robot["batterie"], "carte_permet": not refus and not en_chemin, "convient": raison == "", "raison": raison}

    def _le_plus_proche(self, de: str, ou: str, pour_de_vrai: bool = False) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        regardes = [self._regarder(r, de, ou, pour_de_vrai) for r in self.monde.etat()]
        bons = sorted((r for r in regardes if r["convient"]), key=lambda r: (r["metres"], r["id"]))
        return (bons[0] if bons else None), regardes

    # ------------------------------------------------------------------ choisir
    def choisir(self, tache: dict[str, Any], pour_de_vrai: bool = False) -> dict[str, Any]:
        """Le robot choisi (ou aucun), les robots regardés, un relais possible, et la phrase qui dit pourquoi.
        `pour_de_vrai` : la livraison doit se faire vraiment (un robot est branché) ; un robot simulé est alors écarté."""
        de, ou = tache["de"], tache["ou"]
        choisi, regardes = self._le_plus_proche(de, ou, pour_de_vrai)
        ecartes = " ; ".join(f"{r['nom']} : {r['raison']}" for r in regardes if not r["convient"])
        if choisi is not None:
            pourquoi = (f"J'envoie {choisi['nom']} : il est libre, c'est le plus proche ({choisi['metres']:.0f} m de « {de} »), "
                        f"et sa carte {choisi['carte']} permet « {de} » et « {ou} ».")
            if choisi["etiquette"] == ETIQUETTE_BRANCHE:
                pourquoi += " C'est le robot branché : la course se fait par le coursier, sous le gardien."
            if ecartes:
                pourquoi += f" Écartés : {ecartes}."
            return {"robot": choisi["id"], "nom": choisi["nom"], "metres": choisi["metres"], "etiquette": choisi["etiquette"],
                    "regardes": regardes, "relais": None, "pourquoi": pourquoi}
        relais = None if pour_de_vrai else self._relais(de, ou)
        if relais is not None:
            un, deux = relais["etapes"]
            pourquoi = (f"Aucun robot ne peut faire tout le trajet sans sortir de ses lieux permis. {un['nom']} porte de « {de} » à "
                        f"« {relais['point']} », puis passe la main à {deux['nom']}, qui porte jusqu'à « {ou} ».")
        else:
            pourquoi = f"aucun robot ne convient ({ecartes or 'aucun robot'}) : la tâche passe à un humain"
        return {"robot": None, "nom": None, "metres": None, "etiquette": None, "regardes": regardes, "relais": relais,
                "pourquoi": pourquoi}

    def _relais(self, de: str, ou: str) -> dict[str, Any] | None:
        """Deux robots, un lieu de passage que leurs deux cartes permettent. Le trajet total le plus court gagne."""
        meilleur: tuple[float, dict[str, Any]] | None = None
        for point in self.monde._lieux:
            if point in (de, ou):
                continue
            aller, retour = self.monde.chemin(de, point), self.monde.chemin(point, ou)
            if aller is None or retour is None:
                continue
            premier, _ = self._le_plus_proche(de, point)
            if premier is None:
                continue
            seconds = sorted((r for r in (self._regarder(x, point, ou) for x in self.monde.etat())
                              if r["convient"] and r["id"] != premier["id"]), key=lambda r: (r["metres"], r["id"]))
            if not seconds:
                continue
            total = aller[1] + retour[1]
            if meilleur is None or total < meilleur[0]:
                meilleur = (total, {"point": point, "metres": total, "etapes": [
                    {"robot": premier["id"], "nom": premier["nom"], "de": de, "ou": point},
                    {"robot": seconds[0]["id"], "nom": seconds[0]["nom"], "de": point, "ou": ou}]})
        return meilleur[1] if meilleur else None

    # ------------------------------------------------------------------ attribuer
    def attribuer(self, tableau, ident: str) -> dict[str, Any]:
        """Écrit le choix sur la tâche. Un robot simulé part dans le monde simulé ; R1 attend le coursier ; personne : un humain."""
        tache = tableau.tache(ident)
        if tache["sorte"] != "robot" or tache["etat"] not in ("demandée", "reprise"):
            raise ValueError("on n'attribue qu'une tâche de robot « demandée » ou « reprise »")
        choix = self.choisir(tache)
        if choix["robot"] is None:  # personne ne convient (un relais est proposé, pas encore joué) : un humain
            return tableau.changer_etat(BADGE, ident, tache["etat"], sorte="humain", pourquoi_un_humain=choix["pourquoi"],
                                        relais_propose=choix["relais"])
        if choix["etiquette"] == ETIQUETTE_BRANCHE:  # le robot branché : rien ne bouge ici, le coursier fera la course
            return tableau.changer_etat(BADGE, ident, tache["etat"], robot=choix["robot"], pourquoi_ce_robot=choix["pourquoi"])
        self.monde.prendre(choix["robot"], ident, tache["de"], tache["ou"])
        return tableau.changer_etat(Badge(id=choix["robot"], role="robot", libelle=f"Robot {choix['nom']}"), ident, "attribuée",
                                    robot=choix["robot"], etiquette=choix["etiquette"], pourquoi_ce_robot=choix["pourquoi"])
