"""T24 — La panne et la reprise (cahier 5.10).

    python3 lancer.py panne-reprise       un petit essai raconté : une panne, la reprise par le plus proche, puis un humain

    pr = PanneEtReprise(monde, repartiteur, tableau, carnet, coursier=None)
    pr.avancer()                          # le temps du monde simulé avance d'un pas ; une panne en route est traitée
    pr.provoquer("robot-r2", "robot bloqué")    # panne provoquée, pour la démonstration
    await pr.reprendre("t1")              # le répartiteur donne la course au robot libre le plus proche

« Batterie basse ou robot bloqué : la tâche passe « reprise » et un autre robot la prend. Si aucun ne peut : un humain
reprend la main, et c'est écrit. »
- La panne : écrite au carnet (le robot, la raison, provoquée ou non, la tâche). La tâche passe « reprise ».
- La reprise : c'est le répartiteur (T23) qui choisit — le robot libre le plus proche, avec la bonne carte et assez de
  batterie. Le robot en panne n'est jamais choisi. La phrase qui dit pourquoi est écrite sur la tâche.
- Si le robot en panne avait déjà l'objet, le robot suivant va d'abord là où la panne a eu lieu.
- Avec un robot branché (le coursier) : la reprise doit être une vraie livraison ; seul le robot branché peut la faire,
  par le coursier, sous le gardien. Sinon : un humain.
- Personne ne peut : la tâche passe à un humain ; c'est écrit, et compté comme une aide humaine (K02).

DIRE VRAI :
- R2, R3, R4 sont SIMULÉS : le programme écrit des états, RIEN NE BOUGE. Un robot simulé qui « arrive » ne livre rien :
  la tâche reste « en route », avec la note « arrivé dans le monde simulé ».
- Passer l'objet d'un robot en panne à un autre robot n'est pas joué : personne ne le fait dans ce monde sans bras.
  On note seulement où l'objet est resté. Sur scène, c'est un humain qui le ferait.
- La version simple de la flotte (flotte.py, étape 12 de la répétition) n'est pas changée.
"""
from __future__ import annotations

from typing import Any, Callable

from .carnet import Carnet
from .flotte import ETIQUETTE_SIMULE, GENRE_PANNE
from .monde_robots import ETIQUETTE_BRANCHE, MondeDesRobots
from .porte import Badge
from .repartiteur import BADGE as BADGE_DU_REPARTITEUR
from .repartiteur import Repartiteur
from .taches import TableauDesTaches

ARRIVE_SIMULE = "arrivé dans le monde simulé : rien n'a été livré, ce robot n'existe que dans l'ordinateur"


def _badge(robot: str, nom: str) -> Badge:
    return Badge(id=robot, role="robot", libelle=f"Robot {nom}")


class PanneEtReprise:
    def __init__(self, monde: MondeDesRobots, repartiteur: Repartiteur, tableau: TableauDesTaches, carnet: Carnet, coursier=None,
                 bus=None) -> None:
        self.monde, self.repartiteur, self.tableau, self.carnet, self.coursier = monde, repartiteur, tableau, carnet, coursier
        self.bus = bus  # la boîte noire (H13) : une panne et un passage à un humain y sont écrits. Sans bus : carnet seulement.
        self._a_noter: list[dict[str, Any]] = []

    async def ecrire_dans_la_boite(self) -> int:
        """Écrit dans la boîte noire les pannes et les passages à un humain qui n'y sont pas encore. Aucun nom de patient."""
        a_ecrire, self._a_noter = self._a_noter, []
        if self.bus is not None:
            for note in a_ecrire:
                await self.bus.emettre("note", "clinique", **note)
        return len(a_ecrire)

    # ------------------------------------------------------------------ la panne
    def _avait_l_objet(self, robot: str, tache: str) -> bool:
        """Le robot était-il déjà passé chercher l'objet ? (Le monde note « sur place » quand il arrive au premier lieu.)"""
        return any(e["robot"] == robot and e["quoi"] == "sur place" and str(e.get("tache")) == str(tache) for e in self.monde.journal)

    def _traiter(self, evenement: dict[str, Any]) -> dict[str, Any] | None:
        """Une panne ou un blocage vient d'arriver dans le monde : l'écrire, et rendre la tâche passée « reprise »."""
        robot, nom, tache = evenement["robot"], evenement["nom"], evenement.get("tache")
        raison = str(evenement.get("raison") or evenement["quoi"])
        provoquee = bool(evenement.get("provoquee", False))
        if evenement["quoi"] == "bloqué":  # arrêté devant un lieu que sa carte ne permet pas : il rend sa tâche
            self.monde.panne(robot, f"robot bloqué : {raison}", provoquee=False)
            raison = f"robot bloqué ({raison})"
        badge = _badge(robot, nom)
        self.carnet.ecrire(badge, GENRE_PANNE, {"robot": robot, "nom": nom, "raison": raison, "provoquee": provoquee,
                                                "etiquette": ETIQUETTE_SIMULE, "tache": tache}, valide_par_un_humain=False)
        self._a_noter.append({"quoi": "panne_de_robot", "robot": robot, "nom": nom, "raison": raison, "provoquee": provoquee,
                              "etiquette": ETIQUETTE_SIMULE, "tache": tache})
        if not tache:
            return None
        plus: dict[str, Any] = {}
        if self._avait_l_objet(robot, tache):  # l'objet est resté avec le robot en panne
            plus = {"objet_avec": robot, "objet_ou": self.monde._robot(robot)["lieu"]}
        return self.tableau.changer_etat(badge, tache, "reprise", repris_de=robot, **plus,
                                         pourquoi=f"{nom} en panne : {raison}" + (" (panne provoquée)" if provoquee else ""))

    def provoquer(self, robot: str, raison: str) -> dict[str, Any] | None:
        """Panne PROVOQUÉE d'un robot simulé (batterie basse, robot bloqué). Rend sa tâche passée « reprise », s'il en avait une."""
        avait = self._avait_l_objet(robot, self.monde._robot(robot)["tache"] or "")
        evenement = self.monde.panne(robot, raison, provoquee=True)
        rendue = self._traiter(evenement)
        if rendue is not None and avait and "objet_avec" not in rendue:
            rendue = self.tableau.changer_etat(_badge(robot, evenement["nom"]), rendue["id"], "reprise", objet_avec=robot,
                                               objet_ou=self.monde._robot(robot)["lieu"])
        return rendue

    def avancer(self) -> list[dict[str, Any]]:
        """Le temps du monde simulé avance d'un pas. Une panne en route est traitée ; un robot arrivé rend sa tâche sans livrer."""
        traitees = []
        for evenement in self.monde.pas():
            if evenement["quoi"] in ("panne", "bloqué"):
                rendue = self._traiter(evenement)
                if rendue is not None:
                    traitees.append(rendue)
            elif evenement["quoi"] == "arrivé" and evenement.get("tache"):
                robot = evenement["robot"]
                self.tableau.changer_etat(_badge(robot, evenement["nom"]), evenement["tache"], "en route",
                                          arrive_simule=f"{evenement['nom']} est {ARRIVE_SIMULE}")
                self.monde.liberer(robot)
        return traitees

    # ------------------------------------------------------------------ la reprise
    def _a_un_humain(self, tache: dict[str, Any], raison: str) -> dict[str, Any]:
        self._a_noter.append({"quoi": "course_a_un_humain", "tache": tache["id"],
                              "pourquoi": f"aucun robot ne peut reprendre la course ({raison}) : un humain reprend la main"})
        return self.tableau.changer_etat(BADGE_DU_REPARTITEUR, tache["id"], "reprise", sorte="humain",
                                         pourquoi_un_humain=f"aucun robot ne peut reprendre la course ({raison}) : un humain reprend la main")

    async def reprendre(self, ident: str) -> dict[str, Any]:
        """Le répartiteur donne la course en reprise au robot libre le plus proche. Sinon : un humain.
        Ce qui s'est passé (panne, passage à un humain) est écrit dans la boîte noire à la fin."""
        try:
            return await self._reprendre(ident)
        finally:
            await self.ecrire_dans_la_boite()

    async def _reprendre(self, ident: str) -> dict[str, Any]:
        tache = self.tableau.tache(ident)
        if tache["etat"] != "reprise" or tache["sorte"] != "robot":
            raise ValueError("on ne reprend qu'une tâche de robot à l'état « reprise »")
        pour_de_vrai = self.coursier is not None  # un robot est branché : la course doit être vraiment livrée
        note = None
        if pour_de_vrai:
            await self.coursier.placer_dans(self.monde)  # H12 : la place de R1 est lue sur le robot, pas inventée
            de = tache["de"]
            if tache.get("objet_ou"):  # dire vrai : un robot simulé n'a jamais rien pris pour de vrai
                note = (f"{self.monde._robot(tache['objet_avec'])['nom']} est simulé : il n'a jamais vraiment pris l'objet. "
                        f"L'objet est toujours à « {de} » : c'est là qu'on va le chercher.")
        else:
            de = tache.get("objet_ou") or tache["de"]
        choix = self.repartiteur.choisir({**tache, "de": de}, pour_de_vrai=pour_de_vrai)
        pourquoi = choix["pourquoi"] + (f" {note}" if note else "")
        if tache.get("objet_ou") and not pour_de_vrai:
            reste = f" L'objet est resté avec {self.monde._robot(tache['objet_avec'])['nom']}, à « {de} »"
            if choix["robot"] is None:  # personne ne reprend : ne pas dire qu'un robot va le chercher
                return self._a_un_humain(tache, pourquoi + reste + ".")
            pourquoi += reste + " : le robot va d'abord le chercher là."
        if choix["robot"] is None:
            return self._a_un_humain(tache, pourquoi)
        if choix["etiquette"] == ETIQUETTE_BRANCHE:  # le robot branché : par le coursier, chaque geste sous le gardien
            if self.coursier is None:
                ecartes = " ; ".join(f"{r['nom']} : {r['raison']}" for r in choix["regardes"] if not r["convient"])
                return self._a_un_humain(tache, (ecartes + " ; " if ecartes else "")
                                         + f"{choix['nom']} : c'est le robot branché, et aucun robot n'est branché sur la prise")
            self.tableau.changer_etat(BADGE_DU_REPARTITEUR, ident, "reprise", pourquoi_ce_robot=pourquoi,
                                      **({"note_de_reprise": note, "objet_ou": None, "objet_avec": None} if note else {}))
            fin = await self.coursier.faire(ident)
            await self.coursier.placer_dans(self.monde)  # après la course : le monde des robots sait où R1 est arrivé
            if fin["etat"] == "livrée":
                return fin
            return self._a_un_humain(fin, fin.get("pourquoi") or f"la course est « {fin['etat']} »")
        self.monde.prendre(choix["robot"], ident, de, tache["ou"])
        badge = _badge(choix["robot"], choix["nom"])
        self.tableau.changer_etat(badge, ident, "attribuée", robot=choix["robot"], etiquette=choix["etiquette"], de=de,
                                  pourquoi_ce_robot=pourquoi)
        return self.tableau.changer_etat(badge, ident, "en route")


# ---------------------------------------------------------------------- un petit essai, à lire
def essai(ecrire: Callable[[str], None] = print) -> int:
    """Une course, une panne en route, la reprise par le plus proche ; puis tous les robots en panne : un humain."""
    import asyncio

    from . import cartes
    from .horloge import HorlogeDeDemonstration
    from .listes import ListesDeSoin
    from .porte import JournalDesAcces, PorteDeLecture, charger_badges

    flotte = cartes.CartesDeLaFlotte()
    monde = MondeDesRobots(cartes=flotte)
    monde.placer("robot-r1", "Salon")
    horloge = HorlogeDeDemonstration()
    carnet = Carnet(horloge=horloge)
    listes = ListesDeSoin(PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), carnet)
    tableau = TableauDesTaches(listes.porte, carnet, listes)
    pr = PanneEtReprise(monde, Repartiteur(monde, flotte), tableau, carnet)
    soignant = charger_badges()["soignant-etage-2"]
    ecrire(f"LA PANNE ET LA REPRISE — {ETIQUETTE_SIMULE} — données inventées : le programme écrit des états, rien ne bouge.")
    tache = tableau.demander(soignant, "p01", "la couverture")["tache"]
    un = pr.repartiteur.attribuer(tableau, tache["id"])
    ecrire(f"1. Demande : {tache['quoi']} → {tache['ou']}. {un['pourquoi_ce_robot']}")
    pr.avancer()
    rendue = pr.provoquer(un["robot"], "batterie basse")
    ecrire(f"2. Panne provoquée : {rendue['pourquoi']}. La tâche passe « {rendue['etat']} ».")
    fin = asyncio.run(pr.reprendre(tache["id"]))
    ecrire(f"3. La reprise : {fin['pourquoi_ce_robot']}")
    for _ in range(40):
        pr.avancer()
    ecrire(f"4. {tableau.tache(tache['id']).get('arrive_simule', 'le robot est encore en route')}.")
    autre = tableau.demander(soignant, "p01", "la bouteille d'eau")["tache"]
    deux = pr.repartiteur.attribuer(tableau, autre["id"])
    pr.provoquer(deux["robot"], "robot bloqué")
    for robot in monde.etat():
        if robot["simule"] and robot["etat"] != "en panne":
            monde.panne(robot["id"], "robot bloqué")
    humain = asyncio.run(pr.reprendre(autre["id"]))
    ecrire(f"5. Deuxième course, puis tous les robots simulés en panne : {humain['pourquoi_un_humain']}")
    ecrire(f"Pannes écrites au carnet : {len(carnet.lignes(GENRE_PANNE))}. Aides humaines comptées : {len(tableau.aides)}.")
    return 0


def main(reste: list[str] | None = None) -> int:
    return essai()
