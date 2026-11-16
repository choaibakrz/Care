"""Le coursier : il fait faire au robot une tâche « apporter un objet » (cahier 5.6). Testé sur faux robot.

    systeme = Systeme(reglages, monde=monde_de_la_clinique())
    coursier = Coursier(systeme, tableau, listes, badges["robot-r1"])
    await coursier.faire("t1")       # aller à la réserve, prendre, aller à la chambre, poser

RIEN NE CONTOURNE LE GARDIEN. Chaque geste suit le seul chemin permis :
    coursier → gardien.verifier() → ticket → prise.executer(ticket) → adaptateur
Si le gardien dit non, ou demande un humain, ou si la prise refuse (arrêt d'urgence) : rien ne part, la tâche passe
« échouée », avec la raison. Le coursier ne connaît ni l'adaptateur ni le faux robot.

- États de la tâche, dans le carnet : demandée → attribuée → en route → livrée (ou échouée).
- Quand c'est livré, le point de liste qui attendait l'objet se coche, et le carnet note que c'est la livraison.
- Chaque tâche porte l'étiquette de ce qui l'a faite : « FAUX ROBOT » ici ; « RÉEL » seulement avec un vrai robot.
- Un seul robot, une course à la fois : les autres attendent leur tour.
Le plan (monde_clinique.yaml) : positions inventées, posées dans la halle de démonstration de l'ossature.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import yaml

from briques.b01_prise.actions import ActionDemandee
from briques.b01_prise.prise import ActionRefusee
from commun.monde import Chose, Monde, Position

from .listes import ListesDeSoin
from .porte import Badge
from .taches import TableauDesTaches

FICHIER_PLAN = Path(__file__).resolve().parent / "monde_clinique.yaml"


def monde_de_la_clinique(rez_de_chaussee: bool = False) -> Monde:
    """Le monde de l'ossature, plus les lieux du deuxième étage et les objets de la réserve.
    Sans nom dans les langues : le cerveau de l'ossature ne les entend pas et ne les confond avec rien.
    `rez_de_chaussee` : ajouter aussi le Hall et l'Accueil (la même salle joue alors le hall et l'étage)."""
    plan = yaml.safe_load(FICHIER_PLAN.read_text(encoding="utf-8"))
    if plan.get("marque") != "inventé":
        raise ValueError("monde_clinique.yaml : la marque « inventé » manque")
    monde = Monde.charger()
    lieux = {**plan["lieux"], **(plan["lieux_du_rez_de_chaussee"] if rez_de_chaussee else {})}
    for nom, p in lieux.items():
        monde.lieux.append(Chose(id=nom, position=Position(x=p["x"], y=p["y"])))
    for nom, p in plan["objets"].items():
        monde.objets.append(Chose(id=nom, position=Position(x=p["x"], y=p["y"]), poids_kg=p["poids_kg"]))
    return monde


class Coursier:
    def __init__(self, systeme, tableau: TableauDesTaches, listes: ListesDeSoin | None, badge: Badge,
                 attente_humain_s: float = 120.0) -> None:
        if badge.role != "robot":
            raise ValueError("le coursier travaille avec un badge de robot")
        self.systeme, self.tableau, self.listes, self.badge = systeme, tableau, listes, badge
        self._une_a_la_fois = asyncio.Lock()
        self.pannes = None  # les pannes provoquées (pannes.py), si elles sont branchées
        self.attente_humain_s = attente_humain_s  # robot à plateau : combien de temps il attend qu'un humain pose ou prenne l'objet
        self._attentes: dict[str, asyncio.Event] = {}
        self._en_cours: set[asyncio.Task] = set()
        self.carte_de_role = None  # la carte de rôle de ce robot (cartes_gardien.CarteDuRobotBranche), si elle est branchée
        self.repartiteur = None  # le répartiteur (repartiteur.py), s'il est branché : il dit pourquoi ce robot (avenant 2, K04)
        self.annonces: dict[str, str] = {}  # tâche → la dernière chose que le robot a annoncée avant de partir (K04)

    def etiquette(self) -> str:
        """Dire vrai : « RÉEL » seulement si la carte d'identité du robot dit que c'est un vrai robot."""
        prise = self.systeme.prise
        return "RÉEL" if prise.carte().vrai_robot else "FAUX ROBOT"

    def _a_l_abri(self) -> str | None:
        """La panne qui met le robot à l'abri, s'il y en a une : il ne commence rien de nouveau."""
        return self.pannes.a_l_abri() if self.pannes is not None else None

    async def _geste(self, action: ActionDemandee, conversation: str) -> str:
        """Un geste, par le seul chemin permis. Rend "" si c'est fait, sinon la raison de l'échec."""
        gardien, prise = self.systeme.gardien, self.systeme.prise
        if self.carte_de_role is not None:  # la carte ne fait que refuser : le « oui » reste celui du gardien
            refus = await self.carte_de_role.avant_le_gardien(action, conversation)
            if refus:
                return f"la carte de rôle a dit non ({refus})" if refus.startswith("la carte ") and "gardien" not in refus else refus
        verdict, ticket = await gardien.verifier(action, prise.carte(), conversation=conversation, demandeur="cerveau")
        codes = ", ".join(r.code for r in verdict.raisons)
        en_pause = None  # une pause mise par un soignant (J05) : le refus dit qui l'a mise, et jusqu'à quand
        if verdict.verdict != "oui" and self.carte_de_role is not None and self.carte_de_role.pauses is not None:
            en_pause = self.carte_de_role.pauses.dire_pour([r.details.get("regle") for r in verdict.raisons])
        if verdict.verdict == "humain":
            if verdict.numero_demande:  # personne n'attend la réponse : la demande est retirée, rien ne partira plus tard
                gardien.oublier_demandes(lambda d: d.numero == verdict.numero_demande)
            return en_pause or f"le gardien demande l'accord d'un humain ({codes})"
        if en_pause:
            return en_pause
        if verdict.verdict != "oui" or ticket is None:
            return f"le gardien a dit non ({codes})"
        try:
            suivi = await prise.executer(ticket, conversation=conversation)
        except ActionRefusee as refus:
            return "la prise a refusé (" + ", ".join(r.code for r in refus.raisons) + ")"
        fin = await prise.attendre(suivi.id)
        if fin.statut != "reussie":
            return f"le robot n'a pas réussi « {action.nom} » ({fin.code_erreur or fin.message or fin.statut})"
        return ""

    async def faire(self, ident: str) -> dict[str, Any]:
        """Fait la course d'une tâche « pour un robot » à l'état « demandée » ou « reprise ». Rend la tâche à la fin.
        Les aides humaines notées pendant la course sont écrites dans la boîte noire (avenant 2, K02)."""
        from . import aide_humaine

        try:
            return await self._faire(ident)
        finally:
            await aide_humaine.ecrire_dans_la_boite(self.systeme.bus, self.tableau)
            if self.repartiteur is not None:  # H12 : après la course, le monde des robots sait où le robot est arrivé
                await self._placer_dans_le_monde()

    async def _faire(self, ident: str) -> dict[str, Any]:
        tache = self.tableau.tache(ident)
        if tache["sorte"] != "robot":
            raise ValueError("cette tâche est pour un humain, pas pour un robot")
        if tache["etat"] not in ("demandée", "reprise"):  # « reprise » : un autre robot est tombé en panne en route
            raise ValueError(f"cette tâche est déjà « {tache['etat']} »")
        abri = self._a_l_abri()
        if abri:  # panne provoquée : rien ne part, le gardien n'est même pas sollicité ; la tâche attend la fin de la panne
            from .pannes import ATTENTES
            return self.tableau.changer_etat(self.badge, ident, tache["etat"], en_attente=ATTENTES[abri])
        choix: dict[str, Any] = {}
        if self.repartiteur is not None:  # le choix expliqué (K04) : les robots regardés, et pourquoi celui-ci
            await self._placer_dans_le_monde()
            vu = self.repartiteur.choisir(tache, pour_de_vrai=True)
            await self.systeme.bus.emettre("note", "clinique", quoi="choix_du_repartiteur", tache=ident, robot_choisi=vu["robot"],
                                           pourquoi=vu["pourquoi"], regardes=vu["regardes"])
            if vu["robot"] != self.badge.id:  # ce robot ne convient pas, et aucun autre ne peut livrer pour de vrai : un humain
                return self.tableau.changer_etat(self.badge, ident, tache["etat"], sorte="humain", regardes=vu["regardes"],
                                                 pourquoi_un_humain=vu["pourquoi"])
            choix = {"pourquoi_ce_robot": vu["pourquoi"], "regardes": vu["regardes"]}
        self.tableau.changer_etat(self.badge, ident, "attribuée", robot=self.badge.id, etiquette=self.etiquette(),
                                  en_attente=None, **choix)
        # Le cerveau lit la carte d'identité du robot branché et s'adapte : avec un bras, il prend et pose ; sans bras,
        # il porte sur son plateau et demande à un humain de poser puis de prendre l'objet. Jamais un geste absent de la carte.
        carte = self.systeme.prise.carte()
        a_un_bras = carte.sait("saisir") and carte.sait("poser")
        pour_un_humain = None
        if not carte.sait("se_deplacer"):
            pour_un_humain = "ce robot ne se déplace pas"
        elif not a_un_bras:
            objet = self.systeme.monde.objet(tache["quoi"])
            if objet is not None and objet.poids_kg > carte.limites.charge_max_kg:
                pour_un_humain = (f"objet trop lourd pour le plateau de ce robot ({objet.poids_kg} kg, "
                                  f"le robot porte {carte.limites.charge_max_kg} kg)")
        if pour_un_humain is None and self.carte_de_role is not None:  # le métier du robot ne permet pas cette course
            pour_un_humain = self.carte_de_role.refus_de_la_course(tache, a_un_bras)
        if pour_un_humain:
            return self.tableau.changer_etat(self.badge, ident, tache["etat"], sorte="humain", pourquoi_un_humain=pour_un_humain)
        await self._temps("DEMANDÉ", ident, par=tache.get("qui_demande"), pour=tache.get("pour_qui"), quoi_demande=tache.get("quoi"))
        async with self._une_a_la_fois:
            if not a_un_bras:
                return await self._course_sur_le_plateau(ident, tache, carte)
            self.tableau.changer_etat(self.badge, ident, "en route")
            gestes = [ActionDemandee(nom="se_deplacer", parametres={"lieu": tache["de"]}),
                      ActionDemandee(nom="saisir", parametres={"objet": tache["quoi"]}),
                      ActionDemandee(nom="se_deplacer", parametres={"lieu": tache["ou"]}),
                      ActionDemandee(nom="poser", parametres={"lieu": tache["ou"]})]
            for rang, geste in enumerate(gestes):
                if geste.nom == "se_deplacer":  # dire avant de faire : l'annonce, juste avant d'envoyer l'ordre au gardien
                    await self._annoncer(ident, tache, vers_la_reserve=rang == 0)
                raison = await self._geste(geste, conversation=f"clinique-{ident}")
                if raison.startswith("en pause"):  # un soignant a mis une pause : la tâche attend, et dit pourquoi
                    if rang == 0:
                        return self.tableau.changer_etat(self.badge, ident, "demandée", en_attente=raison)
                    return self.tableau.changer_etat(self.badge, ident, "reprise", pourquoi=raison)
                abri = self._a_l_abri()
                if raison and abri:  # une panne est tombée en pleine course : la tâche n'est pas perdue
                    pourquoi = ("le lien avec le robot est tombé pendant la course" if abri == "lien_robot"
                                else "le robot s'est mis à l'abri pendant la course (panne provoquée)")
                    return self.tableau.changer_etat(self.badge, ident, "reprise", panne=abri, pourquoi=f"{pourquoi} ({raison})")
                if raison:
                    return self.tableau.changer_etat(self.badge, ident, "échouée", pourquoi=raison)
            await self._temps("CONFIRMÉ", ident, par=self.badge.id, comment="le robot dit qu'il a fini : ses quatre gestes sont réussis")
            oui, comment = await self._constater(tache)
            if oui:
                await self._temps("CONSTATÉ", ident, par="monde simulé", etiquette="SIMULÉ", comment=comment)
            fin = self.tableau.changer_etat(self.badge, ident, "livrée", constate="oui" if oui else "pas encore", constat=comment,
                                            **({"annonce": self.annonces[ident]} if ident in self.annonces else {}))
        if fin.get("point") and self.listes is not None:
            self.listes.livraison(self.badge, fin)
        return fin

    # ------------------------------------------------------------------ le choix expliqué, dire avant de faire (avenant 2, K04)
    async def _placer_dans_le_monde(self) -> None:
        """Dire au répartiteur où est le robot branché : le lieu du plan le plus proche de sa vraie position."""
        await self.placer_dans(self.repartiteur.monde)

    async def lire_la_place(self, monde_des_robots) -> dict[str, Any] | None:
        """Lire SEULEMENT (H18) : le lieu du plan le plus proche de la position du robot branché, et sa batterie.
        Rien n'est écrit. Rend {"lieu", "batterie"} ; None si rien n'a pu être lu."""
        try:
            etat = await self._lire_le_monde()
        except Exception:
            return None
        position = etat.position or {}
        connus = [l for l in self.systeme.monde.lieux if l.id in monde_des_robots._lieux]
        if "x" not in position or not connus:
            return None
        proche = min(connus, key=lambda l: (l.position.x - position["x"]) ** 2 + (l.position.y - position["y"]) ** 2)
        return {"lieu": proche.id, "batterie": etat.batterie_pct}

    async def placer_dans(self, monde_des_robots) -> dict[str, Any] | None:
        """Lire la place du robot branché sur la prise et l'écrire dans un monde des robots (H12) : le lieu du plan le
        plus proche de sa position. Rend {"lieu", "batterie"} ; None si rien n'a pu être lu (alors rien n'est changé)."""
        lue = await self.lire_la_place(monde_des_robots)
        if lue is not None and monde_des_robots._robot(self.badge.id)["etat"] != "en panne":
            monde_des_robots.placer(self.badge.id, lue["lieu"])
        return lue

    def _article(self, quoi: str) -> str:
        try:
            return next((f"{o['article']} " for o in self.tableau.porte.reserve(self.badge) if o["nom"] == quoi), "")
        except Exception:
            return ""

    async def _annoncer(self, ident: str, tache: dict[str, Any], vers_la_reserve: bool) -> str:
        """Le robot annonce ce qu'il va faire et où il va : un texte court, pour l'écran, écrit dans la boîte noire.
        C'est la clinique qui annonce ; le gardien n'est pas changé. (Par la voix : pas encore.)"""
        objet = f"{self._article(tache['quoi'])}{tache['quoi']}"
        if vers_la_reserve:
            ou = "à la réserve" if tache["de"] == "Réserve" else f"à « {tache['de']} »"
            texte = f"Je vais chercher {objet} {ou}."
        else:
            ou = f"en chambre {tache['ou'][8:]}" if tache["ou"].startswith("Chambre ") else f"à « {tache['ou']} »"
            texte = f"J'apporte {objet} {ou}."
        self.annonces[ident] = texte
        await self.systeme.bus.emettre("note", "clinique", quoi="annonce", tache=ident, annonce_par=self.badge.id, texte=texte,
                                       par="texte à l'écran")
        return texte

    # ------------------------------------------------------------------ demandé, confirmé, constaté (avenant 2, K03)
    async def _temps(self, temps: str, ident: str, **donnees: Any) -> None:
        """Un des trois temps d'un geste, écrit dans la boîte noire avec son heure. Des numéros, jamais un nom."""
        await self.systeme.bus.emettre("note", "clinique", quoi="temps_d_un_geste", temps=temps, tache=ident, **donnees)

    async def _lire_le_monde(self):
        return await self.systeme.prise.etat()

    async def _constater(self, tache: dict[str, Any]) -> tuple[bool, str]:
        """CONSTATÉ : autre chose que la parole du robot le montre. Sur le faux robot : l'état du monde simulé (où est
        l'objet), étiqueté SIMULÉ. Sur un vrai robot : rien ici ; une personne ou un capteur devra le dire."""
        from . import aide_humaine

        oui, comment = False, "vrai robot : pas encore constaté (il faut une personne qui l'a vu, ou un capteur)"
        try:
            etat = await self._lire_le_monde()
        except Exception as erreur:  # on ne sait pas : ce n'est pas constaté
            etat, comment = None, f"le monde n'a pas pu être lu ({type(erreur).__name__})"
        if etat is not None and etat.extra.get("simulation"):
            objet, lieu = tache["quoi"], self.systeme.monde.lieu(tache["ou"])
            position = (etat.extra.get("objets") or {}).get(objet)
            if etat.objet_tenu == objet:
                comment = f"monde simulé : le robot tient toujours « {objet} »"
            elif position is None or lieu is None:
                comment = f"monde simulé : on ne sait pas où est « {objet} »"
            else:
                metres = ((position[0] - lieu.position.x) ** 2 + (position[1] - lieu.position.y) ** 2) ** 0.5
                oui = metres <= 0.5
                comment = (f"monde simulé : « {objet} » est à {metres:.1f} m de {tache['ou']}" if oui
                           else f"monde simulé : « {objet} » n'est pas arrivé : toujours à {metres:.1f} m de {tache['ou']}")
        aide_humaine.signaler_constat(oui)
        return oui, comment

    # ------------------------------------------------------------------ le robot sans bras : il porte sur son plateau
    async def _course_sur_le_plateau(self, ident: str, tache: dict[str, Any], carte) -> dict[str, Any]:
        """Aller à la réserve, demander à un humain de poser l'objet, l'apporter, demander à un humain de le prendre."""
        conversation = f"clinique-{ident}"
        etapes = [(tache["de"], f"un humain pose « {tache['quoi']} » sur le plateau du robot",
                   f"Posez {tache['quoi']} sur mon plateau, s'il vous plaît."),
                  (tache["ou"], f"un humain prend « {tache['quoi']} » sur le plateau du robot",
                   f"Voici {tache['quoi']}. Prenez-le sur mon plateau, s'il vous plaît.")]
        self.tableau.changer_etat(self.badge, ident, "en route", attend=None)
        for lieu, attend, phrase in etapes:
            await self._annoncer(ident, tache, vers_la_reserve=lieu == tache["de"])  # dire avant de faire (K04)
            gestes = [ActionDemandee(nom="se_deplacer", parametres={"lieu": lieu})]
            if carte.sait("parler"):  # il le demande à voix haute, s'il a une voix ; la demande est aussi sur la tablette
                gestes.append(ActionDemandee(nom="parler", parametres={"texte": phrase, "langue": "fr"}))
            for geste in gestes:
                raison = await self._geste(geste, conversation=conversation)
                if raison:
                    return self._course_interrompue(ident, raison)
            self._attentes[ident] = asyncio.Event()
            self.tableau.changer_etat(self.badge, ident, "en route", attend=attend, dit=phrase)
            try:
                await asyncio.wait_for(self._attentes[ident].wait(), self.attente_humain_s)
            except asyncio.TimeoutError:
                return self.tableau.changer_etat(
                    self.badge, ident, "échouée", attend=None,
                    pourquoi=f"personne n'a répondu : {attend} (attendu {self.attente_humain_s:g} s)")
            finally:
                self._attentes.pop(ident, None)
        from . import aide_humaine

        qui = self.tableau.tache(ident).get("confirme_par") or "une personne"
        await self._temps("CONFIRMÉ", ident, par=self.badge.id, comment="le robot dit qu'il a fini : il est arrivé avec l'objet sur son plateau")
        comment = f"une personne ({qui}) a pris l'objet sur le plateau et l'a dit"
        await self._temps("CONSTATÉ", ident, par=qui, etiquette=self.etiquette(), comment=comment)
        aide_humaine.signaler_constat(True)
        fin = self.tableau.changer_etat(self.badge, ident, "livrée", attend=None, remise="prise par un humain sur le plateau",
                                        constate="oui", constat=comment)
        if fin.get("point") and self.listes is not None:
            self.listes.livraison(self.badge, fin)
        return fin

    def _course_interrompue(self, ident: str, raison: str) -> dict[str, Any]:
        abri = self._a_l_abri()
        if abri:
            return self.tableau.changer_etat(self.badge, ident, "reprise", panne=abri, attend=None,
                                             pourquoi=f"le robot s'est mis à l'abri pendant la course ({raison})")
        return self.tableau.changer_etat(self.badge, ident, "échouée", attend=None, pourquoi=raison)

    def confirmer(self, ident: str, badge: Badge) -> bool:
        """Un humain de l'équipe dit « c'est fait » (l'objet est posé sur le plateau, ou repris). Rend False si le robot n'attendait rien."""
        from .listes import HUMAINS

        if badge.role not in HUMAINS:
            self.tableau.porte.refuser(badge, "confirmer un geste", "seul un humain de l'équipe confirme un geste fait à la main")
        attente = self._attentes.get(ident)
        if attente is None or attente.is_set():
            return False
        self.tableau.changer_etat(badge, ident, "en route", attend=None, confirme_par=badge.id)
        self.tableau.noter_aide("geste", qui=badge.id, tache=ident, detail="un humain pose ou prend l'objet sur le plateau du robot")
        attente.set()
        return True

    def lancer(self, ident: str) -> None:
        """Pour le serveur : la course part en arrière-plan, l'écran suit les états dans le tableau des tâches."""
        course = asyncio.get_running_loop().create_task(self.faire(ident))
        self._en_cours.add(course)
        course.add_done_callback(self._en_cours.discard)


# ---------------------------------------------------------------------- la grande répétition
def etape_8():
    """Étape 8 : « Il manque un coussin » : question, livraison, point coché. Par les vraies pièces, sur le faux robot.
    Dans un essai compté, l'objet change. Un objet précis : livré sans question. Un objet absent de la réserve :
    le prototype le dit, la tâche passe à un humain, aucun robot ne bouge (cahier 4.3)."""
    import tempfile

    from commun.systeme import REGLAGES_EXEMPLE, Systeme, charger_reglages

    from .carnet import Carnet
    from .horloge import HorlogeDeDemonstration
    from .porte import JournalDesAcces, PorteDeLecture, charger_badges
    from .repetition import Resultat, changement

    objet, absent = changement("objet", "un coussin"), bool(changement("objet_absent", False))
    autre_robot = changement("robot")  # un essai avec une autre carte de faux robot (« plateau » : sans bras)
    demande_dite = f"il manque {objet} en chambre 12"
    reglages = charger_reglages(REGLAGES_EXEMPLE)
    reglages["cerveau"] = {**reglages["cerveau"], "choix": "regles"}
    if autre_robot:
        reglages["robot"] = {**reglages["robot"], "carte": autre_robot}
    badges = charger_badges()
    soignant = badges["soignant-etage-2"]

    async def jouer(dossier: str):
        systeme = Systeme(reglages, dossier_journal=dossier, acceleration=20.0, monde=monde_de_la_clinique())
        horloge = HorlogeDeDemonstration(bus=systeme.bus)
        carnet = Carnet(horloge=horloge)
        listes = ListesDeSoin(PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), carnet)
        tableau = TableauDesTaches(listes.porte, carnet, listes)
        coursier = Coursier(systeme, tableau, listes, badges["robot-r1"])
        question, demande = None, tableau.demander(soignant, "p01", demande_dite, liste="installation", numero=4)
        if demande["genre"] == "question":  # demande floue : le prototype demande lequel, on prend le premier choix
            question = demande
            demande = tableau.demander(soignant, "p01", demande_dite, choix=question["choix"][0],
                                       liste="installation", numero=4)
        fin, gestes, mains = demande.get("tache"), 0, []
        if fin and fin["sorte"] == "robot":
            await systeme.demarrer()
            try:
                course = asyncio.create_task(coursier.faire(fin["id"]))
                while not course.done():  # robot sans bras : le programme joue l'humain qui pose, puis prend, l'objet
                    actuelle = tableau.tache(fin["id"])
                    if actuelle.get("attend") and coursier.confirmer(fin["id"], soignant):
                        mains.append(actuelle["attend"])
                    await asyncio.sleep(0.01)
                fin = await course
            finally:
                await systeme.arreter()
            gestes = len([e for e in systeme.bus.historique if e.type == "action_demarree" and e.donnees.get("action")])
        bras = len([e for e in systeme.bus.historique if e.type == "gardien_decision" and e.donnees.get("action")
                    and e.donnees["action"]["nom"] in ("saisir", "poser", "montrer", "rejouer_geste")])
        point = next(p for p in listes.liste(soignant, "p01", "installation")["points"] if p["numero"] == 4)
        return question, demande, fin, point, gestes, coursier.etiquette(), mains, bras, systeme.prise.carte()

    with tempfile.TemporaryDirectory() as dossier:
        question, demande, fin, point, gestes, etiquette, mains, bras, carte = asyncio.run(jouer(dossier))
    dit_question = f"question : « {question['phrase']} »" if question else "pas de question (objet précis)"
    if absent:  # l'objet n'est pas dans la réserve : le dire, passer à un humain, ne rien faire bouger
        reussie = (bool(fin) and fin["sorte"] == "humain" and "Je ne trouve pas cet objet" in demande.get("phrase", "")
                   and gestes == 0 and point["etat"] != "fait")
        return Resultat(reussie, "SIMULÉ",
                        f"demande : « {demande_dite} » ; objet absent de la réserve ; le prototype dit : "
                        f"« {demande.get('phrase', '')} » ; tâche pour un {fin['sorte'] if fin else '?'} ; {gestes} geste du "
                        f"robot ; aucun robot n'a servi")
    floue = bool(changement("objet_flou", objet == "un coussin"))  # « À vous » (T28) : c'est le tableau qui dit si l'objet est flou
    reussie = (bool(fin) and fin.get("etat") == "livrée" and point["etat"] == "fait"
               and point.get("comment") == "livraison du robot" and bool(question) == floue)
    detail = (f"demande : « {demande_dite} » ; {dit_question} ; tâche {fin['etat'] if fin else 'absente'} "
              f"({fin.get('quoi') if fin else ''}, {fin.get('de') if fin else ''} → {fin.get('ou') if fin else ''}) ; "
              f"point d'exemple « {point['nom'] if point else '?'} » : {point['etat'] if point else '?'} "
              "(quel point le coussin coche : à décider avec Hiba)")
    if not (carte.sait("saisir") and carte.sait("poser")):  # robot sans bras : il porte sur son plateau
        reussie = reussie and len(mains) == 2 and bras == 0 and fin.get("remise") == "prise par un humain sur le plateau"
        detail += (f" ; robot « {carte.nom} » (sans bras, lu sur sa carte) : il porte sur son plateau ; {' ; puis '.join(mains)} "
                   f"(ces {len(mains)} gestes d'humain sont faits par le programme) ; {bras} geste de bras demandé au gardien")
    if fin and fin.get("pourquoi"):
        detail += f" ; raison : {fin['pourquoi']}"
    if fin and fin.get("pourquoi_un_humain"):
        detail += f" ; passée à un humain : {fin['pourquoi_un_humain']}"
    return Resultat(reussie, etiquette, detail)
