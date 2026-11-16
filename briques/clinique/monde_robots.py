"""Plusieurs faux robots dans le même monde (tâche R5 ; la brique 16 de l'ossature n'existe pas ; oui de Hiba, Q5 et Q6).

    python3 lancer.py monde-robots        un petit essai : un robot porte, un robot tombe en panne

    monde = MondeDesRobots()
    monde.prendre("robot-r2", "t1", "Réserve", "Chambre 12")   # R2 va chercher à la Réserve, puis porte en Chambre 12
    monde.pas()                                                # le temps avance d'un pas : chaque robot en route avance
    monde.panne("robot-r3", "batterie basse")                  # panne provoquée : il s'arrête où il est, il rend sa tâche
    monde.plus_proches("Réserve")                              # les robots libres, du plus proche au plus loin

La version la plus simple, SANS PHYSIQUE : les robots sont des points sur le plan inventé du faux dossier. Ils avancent
de quelques mètres par pas, le long des couloirs du plan. Ils ne changent pas d'étage (pas d'ascenseur). Ils ne se
gênent pas : deux robots peuvent être au même lieu. La batterie baisse avec les mètres ; trop basse : panne.

DIRE VRAI :
- Ce monde n'existe que dans l'ordinateur : RIEN NE BOUGE. R2, R3, R4 portent « FAUX ROBOT — SIMULÉ ».
- R1 est le robot branché sur la prise (« FAUX ROBOT » aujourd'hui). Ici on note seulement où il est (`placer`).
  Il ne bouge jamais par ce monde : il part par le coursier, et chaque geste a d'abord un « oui » du gardien.
- Les mètres, la vitesse et la batterie sont inventés. Ils ne disent rien d'un vrai robot.
- `permis` : une règle venue d'ailleurs peut interdire un lieu à un robot. `cartes=` branche les cartes de rôle
  (`cartes.py`, T22a) : le robot s'arrête avant un lieu que sa carte ne permet pas.
"""
from __future__ import annotations

import heapq
from pathlib import Path
from typing import Any, Callable

import yaml

from . import dossier

FICHIER = Path(__file__).resolve().parent / "flotte.yaml"
ETIQUETTE_SIMULE = "FAUX ROBOT — SIMULÉ"
ETIQUETTE_BRANCHE = "FAUX ROBOT"
BATTERIE_BASSE = "batterie basse"


class MondeDesRobots:
    def __init__(self, lieux=None, fichier: Path = FICHIER, vitesse: float = 2.0, conso: float = 0.5, seuil: float = 15.0,
                 permis: Callable[[dict[str, Any], str], str | None] | None = None, cartes=None) -> None:
        """`vitesse` : mètres par pas. `conso` : batterie perdue par mètre, en %. `seuil` : batterie basse, en %."""
        lieux = lieux if lieux is not None else dossier.charger().lieux
        self._lieux = [l["nom"] for l in lieux["lieux"]]
        self._voisins: dict[str, list[tuple[str, float]]] = {}
        for v in lieux["voisins"]:
            self._voisins.setdefault(v["de"], []).append((v["a"], float(v["metres"])))
            self._voisins.setdefault(v["a"], []).append((v["de"], float(v["metres"])))
        donnees = yaml.safe_load(Path(fichier).read_text(encoding="utf-8"))
        if donnees.get("marque") != "inventé":
            raise ValueError("flotte.yaml : la marque « inventé » manque")
        self.cartes = cartes  # les cartes de rôle (cartes.CartesDeLaFlotte), si elles sont branchées
        if cartes is not None and permis is None:
            permis = cartes.permis
        self.vitesse, self.conso, self.seuil, self.permis = float(vitesse), float(conso), float(seuil), permis
        self.numero_du_pas = 0
        self.journal: list[dict[str, Any]] = []
        self._robots: dict[str, dict[str, Any]] = {}
        for r in donnees["robots"]:
            depart = r.get("depart")
            if depart not in self._lieux:
                raise ValueError(f"flotte.yaml : le départ de {r['nom']} (« {depart} ») n'est pas un lieu du plan")
            self._robots[r["id"]] = {"id": r["id"], "nom": r["nom"], "carte": r["carte"], "simule": bool(r["simule"]),
                                     "lieu": depart, "vers": None, "reste": 0.0, "route": [], "buts": [],
                                     "batterie": 100.0, "etat": "libre", "tache": None, "panne": None}

    # ------------------------------------------------------------------ lire
    def _robot(self, ident: str) -> dict[str, Any]:
        if ident not in self._robots:
            raise ValueError(f"robot inconnu « {ident} »")
        return self._robots[ident]

    def _lieu(self, nom: str) -> str:
        if nom not in self._lieux:
            raise ValueError(f"lieu inconnu « {nom} »")
        return nom

    def chemin(self, depart: str, arrivee: str) -> tuple[list[str], float] | None:
        """Le plus court chemin par les couloirs du plan : les lieux à passer, et les mètres. None : pas de chemin."""
        file: list[tuple[float, list[str]]] = [(0.0, [self._lieu(depart)])]
        self._lieu(arrivee)
        vus: set[str] = set()
        while file:
            metres, passes = heapq.heappop(file)
            ici = passes[-1]
            if ici == arrivee:
                return passes[1:], metres
            if ici in vus:
                continue
            vus.add(ici)
            for suivant, m in self._voisins.get(ici, ()):
                if suivant not in vus:
                    heapq.heappush(file, (metres + m, passes + [suivant]))
        return None

    def _metres_entre(self, a: str, b: str) -> float:
        return next(m for voisin, m in self._voisins[a] if voisin == b)

    def distance(self, ident: str, lieu: str) -> float | None:
        """Les mètres entre un robot et un lieu, par les couloirs. None : pas de chemin (un autre étage)."""
        robot = self._robot(ident)
        depuis, deja = (robot["vers"], robot["reste"]) if robot["vers"] else (robot["lieu"], 0.0)
        trouve = self.chemin(depuis, lieu)
        return None if trouve is None else deja + trouve[1]

    def plus_proches(self, lieu: str) -> list[tuple[str, float]]:
        """Les robots LIBRES qui peuvent aller à ce lieu, du plus proche au plus loin. Ni en panne, ni occupés."""
        libres = [(self.distance(i, lieu), i) for i, r in self._robots.items() if r["etat"] == "libre"]
        return [(i, metres) for metres, i in sorted((m, i) for m, i in libres if m is not None)]

    def _dans_un_couloir(self, robot: dict[str, Any]) -> bool:
        """Vrai s'il a déjà quitté son lieu : à un lieu, prêt à repartir, il est encore « à ce lieu »."""
        return bool(robot["vers"]) and robot["reste"] < self._metres_entre(robot["lieu"], robot["vers"]) - 1e-9

    def compte(self) -> dict[str, Any]:
        simules = sum(1 for r in self._robots.values() if r["simule"])
        return {"robots": len(self._robots), "simules": simules, "texte": f"{simules} robots simulés sur {len(self._robots)}"}

    def etat(self) -> list[dict[str, Any]]:
        """Pour chaque robot : nom, carte, étiquette, où il est, batterie, état, tâche. Aucun nom de patient."""
        return [{"id": r["id"], "nom": r["nom"], "simule": r["simule"],
                 "carte": self.cartes.carte_de(r["id"]).nom if self.cartes is not None else r["carte"],
                 "etiquette": ETIQUETTE_SIMULE if r["simule"] else ETIQUETTE_BRANCHE,
                 "ou": f"entre {r['lieu']} et {r['vers']}" if self._dans_un_couloir(r) else r["lieu"],
                 "batterie": round(r["batterie"], 1), "etat": r["etat"], "tache": r["tache"], "panne": r["panne"]}
                for r in self._robots.values()]

    # ------------------------------------------------------------------ écrire
    def _noter(self, robot: dict[str, Any], quoi: str, **plus: Any) -> dict[str, Any]:
        evenement = {"pas": self.numero_du_pas, "robot": robot["id"], "nom": robot["nom"], "quoi": quoi, **plus}
        self.journal.append(evenement)
        return evenement

    def placer(self, ident: str, lieu: str) -> None:
        """Dire où est un robot (sert surtout à R1, dont la vraie place vient de la prise)."""
        robot = self._robot(ident)
        robot.update(lieu=self._lieu(lieu), vers=None, reste=0.0, route=[], buts=[])
        if robot["etat"] in ("en route", "bloqué"):
            robot["etat"] = "libre"

    def _partir(self, ident: str, buts: list[str], tache: str | None) -> dict[str, Any]:
        robot = self._robot(ident)
        if not robot["simule"]:
            raise ValueError(f"{robot['nom']} est le robot branché : il part par le coursier, sous le gardien")
        if robot["etat"] == "en panne":
            raise ValueError(f"{robot['nom']} est en panne")
        if robot["etat"] != "libre":
            raise ValueError(f"{robot['nom']} est occupé ({robot['etat']})")
        ici, par, metres = robot["lieu"], [], 0.0
        for but in buts:
            trouve = self.chemin(ici, but)
            if trouve is None:
                raise ValueError(f"pas de chemin de « {ici} » à « {but} » pour {robot['nom']} (les robots ne changent pas d'étage)")
            par, metres, ici = par + trouve[0], metres + trouve[1], but
        robot.update(buts=list(buts), tache=tache, etat="en route")
        self._noter(robot, "départ", vers=buts[-1], **({"tache": tache} if tache else {}))
        self._but_suivant(robot)
        return {"par": par, "metres": metres}

    def envoyer(self, ident: str, lieu: str) -> dict[str, Any]:
        """Un robot simulé part vers un lieu. Rend le chemin prévu. Il avancera à chaque `pas()`."""
        return self._partir(ident, [lieu], None)

    def prendre(self, ident: str, tache: str, de: str, ou: str) -> dict[str, Any]:
        """Un robot simulé prend une tâche : il va à `de` (chercher), puis à `ou` (porter)."""
        return self._partir(ident, [de, ou], str(tache))

    def liberer(self, ident: str) -> None:
        """Le robot arrivé avec sa tâche est de nouveau libre."""
        robot = self._robot(ident)
        if robot["etat"] == "arrivé":
            robot.update(etat="libre", tache=None)

    def panne(self, ident: str, raison: str, provoquee: bool = True) -> dict[str, Any]:
        """Le robot s'arrête où il est et rend sa tâche. `provoquee` : déclenchée exprès, pour la démonstration."""
        robot = self._robot(ident)
        raison = " ".join(str(raison).split())[:80] or "panne"
        tache = robot["tache"]
        robot.update(etat="en panne", tache=None, route=[], buts=[],
                     panne=f"{raison} (panne provoquée)" if provoquee else raison)
        return self._noter(robot, "panne", raison=raison, provoquee=bool(provoquee), tache=tache)

    def reparer(self, ident: str) -> None:
        """Le robot en panne repart de là où il s'est arrêté (au lieu qu'il venait de quitter). Batterie pleine."""
        robot = self._robot(ident)
        if robot["etat"] == "en panne":
            robot.update(etat="libre", panne=None, vers=None, reste=0.0, batterie=100.0)

    # ------------------------------------------------------------------ le temps avance
    def _but_suivant(self, robot: dict[str, Any], nouveaux: list[dict[str, Any]] | None = None) -> None:
        """Arrivé à un lieu : préparer le couloir suivant, ou dire qu'il est sur place ou arrivé."""
        nouveaux = nouveaux if nouveaux is not None else []
        while not robot["route"]:
            if not robot["buts"]:
                robot["etat"] = "arrivé" if robot["tache"] else "libre"
                nouveaux.append(self._noter(robot, "arrivé", lieu=robot["lieu"], **({"tache": robot["tache"]} if robot["tache"] else {})))
                return
            but = robot["buts"][0]
            if but == robot["lieu"]:
                robot["buts"].pop(0)
                if robot["buts"]:
                    nouveaux.append(self._noter(robot, "sur place", lieu=but, tache=robot["tache"]))
                continue
            robot["route"] = self.chemin(robot["lieu"], but)[0]
        suivant = robot["route"][0]
        refus = self.permis(dict(robot), suivant) if self.permis is not None else None
        if refus:
            robot.update(etat="bloqué", route=[], buts=[])
            nouveaux.append(self._noter(robot, "bloqué", lieu=suivant, raison=str(refus), tache=robot["tache"]))
            return
        robot["route"].pop(0)
        robot.update(vers=suivant, reste=self._metres_entre(robot["lieu"], suivant))

    def pas(self) -> list[dict[str, Any]]:
        """Le temps avance d'un pas : chaque robot en route avance de `vitesse` mètres. Rend ce qui vient d'arriver."""
        self.numero_du_pas += 1
        nouveaux: list[dict[str, Any]] = []
        for robot in self._robots.values():
            a_faire = self.vitesse
            while robot["etat"] == "en route" and robot["vers"] and a_faire > 1e-9:
                bout = min(a_faire, robot["reste"])
                robot["reste"] -= bout
                robot["batterie"] = max(0.0, robot["batterie"] - bout * self.conso)
                a_faire -= bout
                if robot["reste"] <= 1e-9:
                    robot.update(lieu=robot["vers"], vers=None, reste=0.0)
                if robot["batterie"] <= self.seuil:
                    nouveaux.append(self.panne(robot["id"], BATTERIE_BASSE, provoquee=False))
                    break
                if robot["vers"] is None:
                    self._but_suivant(robot, nouveaux)
        return nouveaux


# ---------------------------------------------------------------------- la commande
def _ligne(r: dict[str, Any]) -> str:
    panne = f" : {r['panne']}" if r["panne"] else ""
    tache = f", tâche {r['tache']}" if r["tache"] else ""
    return f"{r['nom']} [{r['etiquette']}] carte {r['carte']} — {r['ou']} — {r['etat']}{panne}{tache} — batterie {r['batterie']:.0f} %"


def main(reste: list[str] | None = None, ecrire: Callable[[str], None] = print) -> int:
    monde = MondeDesRobots()
    ecrire(f"LE MONDE DES ROBOTS — SIMULÉ, sans physique — {monde.compte()['texte']} — données inventées")
    ecrire("Ce monde n'existe que dans l'ordinateur : rien ne bouge. R1 est le robot branché : ici on note seulement où il est.")
    for r in monde.etat():
        ecrire("  " + _ligne(r))
    route = monde.prendre("robot-r2", "t1", "Réserve", "Chambre 12")
    ecrire(f"R2 prend la tâche t1 (Réserve → Chambre 12) : {route['metres']:.0f} m par {' → '.join(route['par'])}")
    monde.envoyer("robot-r3", "Chambre 13")
    ecrire("R3 part du Salon vers la Chambre 13.")
    try:
        monde.envoyer("robot-r4", "Hall")
    except ValueError as erreur:
        ecrire(f"R4 vers le Hall : refusé — {erreur}")
    for _ in range(8):
        if monde.numero_du_pas == 2:
            panne = monde.panne("robot-r3", "roue bloquée")
            ecrire(f"  pas {panne['pas']} : R3 en panne ({panne['raison']}, panne provoquée) : il s'arrête où il est")
        for e in monde.pas():
            suite = f" ({e['lieu']})" if e.get("lieu") else ""
            ecrire(f"  pas {e['pas']} : {e['nom']} {e['quoi']}{suite}")
    for r in monde.etat():
        ecrire("  " + _ligne(r))
    ecrire(f"Les robots libres les plus proches de la Réserve : "
           f"{', '.join(f'{monde._robot(i)['nom']} ({m:.0f} m)' for i, m in monde.plus_proches('Réserve')) or 'aucun'}")
    return 0
