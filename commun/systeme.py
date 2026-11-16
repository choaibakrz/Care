"""Assembler toutes les briques à partir de reglages.yaml.

Changer de robot = changer une ligne dans reglages.yaml (ou --robot en ligne de commande).
Rien d'autre ne change : c'est la promesse de la multiprise.
"""
from __future__ import annotations

import asyncio

import platform
from pathlib import Path
from typing import Any

import yaml

from briques.b01_prise.adaptateur import Adaptateur
from briques.b01_prise.prise import Prise
from briques.b06_cerveau.prise_cerveau import Cerveau
from briques.b07_gardien.gardien import ATTENTE_HUMAIN_S, Gardien, LimitesParDefaut
from briques.b07_gardien.perception import Perception
from briques.b07_gardien.regles import CHEMIN_REGLES
from briques.b08_doute.aides_apprises import CHEMIN_AIDES, AidesApprises
from briques.b08_doute.doute import Doute
from briques.b12_boite_noire.fiche import Compteur
from briques.b12_boite_noire.journal import DOSSIER_DEFAUT, BoiteNoire
from commun.bus import Bus
from commun.chaine import Chaine
from commun.monde import Monde

RACINE = Path(__file__).resolve().parents[1]


REGLAGES = RACINE / "reglages.yaml"  # propre à chaque Mac, JAMAIS dans le dépôt (contient le code d'équipe)
REGLAGES_EXEMPLE = RACINE / "reglages.exemple.yaml"  # dans le dépôt, sans aucun code


def preparer_reglages() -> bool:
    """Crée reglages.yaml à partir de l'exemple s'il n'existe pas. Rend True s'il vient d'être créé."""
    if REGLAGES.exists():
        return False
    REGLAGES.write_text(REGLAGES_EXEMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    return True


def charger_reglages(chemin: str | Path | None = None) -> dict[str, Any]:
    chemin = Path(chemin) if chemin else (REGLAGES if REGLAGES.exists() else REGLAGES_EXEMPLE)
    with open(chemin, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _chemin(valeur: str | Path | None, defaut: Path) -> Path:
    """Un chemin de reglages.yaml : relatif au dossier du projet ; vide = le chemin par défaut."""
    if not valeur:
        return defaut
    p = Path(valeur)
    return p if p.is_absolute() else RACINE / p


def _creer_adaptateur(reglages: dict, monde: Monde, acceleration: float = 1.0, bus: Bus | None = None) -> Adaptateur:
    nom = reglages["robot"]["adaptateur"]
    if nom == "faux_robot":
        from briques.b02_faux_robot.faux_robot import FauxRobot

        return FauxRobot(reglages["robot"]["carte"], monde=monde, acceleration=acceleration,
                         delai_chien_de_garde_s=reglages["securite"]["delai_chien_de_garde_s"])
    # Brique 3 : un robot de briques/b03_adaptateurs/robots/<nom>/ (créé par « lancer.py brancher »). Le registre
    # refuse un vrai robot tant que son test de conformité complet n'a pas réussi.
    from briques.b03_adaptateurs.registre import fabriquer

    return fabriquer(nom, reglages, bus=bus)  # le bus : les remarques de l'adaptateur vont dans la boîte noire


def fabrique_du_faux_robot(carte: str, acceleration: float = 1.0):
    """De quoi fabriquer un FAUX robot neuf avec une carte donnée, pour le test de conformité de la prise (brique 1), qui
    l'entoure lui-même d'une prise et d'un gardien. Jamais un vrai robot. C'est ici, et nulle part ailleurs, qu'un
    adaptateur se fabrique (clinique en boîte, commande « brancher-carte » ; voir DECISIONS.md)."""
    from briques.b02_faux_robot.faux_robot import FauxRobot

    return lambda: FauxRobot(carte, acceleration=acceleration)


def creer_cerveau(reglages: dict, bus: Bus | None = None, serveurs: dict | None = None) -> Cerveau:
    """regles : sans modèle. cascade : Apertus 8B → Apertus 4B → règles (voir reglages.yaml → cerveau)."""
    from briques.b06_cerveau.branchements.regles import CerveauRegles

    r = reglages["cerveau"]
    if r["choix"] == "regles":
        return CerveauRegles()
    if r["choix"] != "cascade":
        raise ValueError(f"Cerveau inconnu : {r['choix']} (regles ou cascade)")
    from briques.b06_cerveau.branchements.cascade import CerveauCascade, Etage
    from briques.b06_cerveau.branchements.llm import CerveauLLM

    serveurs = serveurs or {}
    etages = []
    internet = r.get("internet") or {}
    liste = list(r.get("cascade", []))
    if internet.get("actif") and internet.get("url"):
        liste.insert(0, {"nom": "apertus_internet", **internet})
    for e in liste:
        if e["nom"] == "regles":
            etages.append(Etage(CerveauRegles()))
            continue
        serveur = serveurs.get(e["nom"]) if _url_locale(e["url"]) else None  # sur l'autre Mac : pas notre serveur
        etages.append(Etage(CerveauLLM(e["nom"], e["url"], e.get("modele", ""), e.get("formulaire", "force"),
                                       e.get("cle_env"), trousseau=e.get("trousseau")), delai_s=float(e.get("delai_s", 6)),
                            pause_apres_echec_s=float(e.get("pause_apres_echec_s", 30)), serveur=serveur,
                            demarrage=getattr(serveur, "demarrage", "jamais")))
    if not etages or not isinstance(etages[-1].cerveau, CerveauRegles):
        etages.append(Etage(CerveauRegles()))  # toujours un dernier recours qui ne dépend de rien
    return CerveauCascade(etages, bus)


def _url_locale(url: str) -> bool:
    from urllib.parse import urlparse

    return (urlparse(url).hostname or "") in ("127.0.0.1", "localhost", "::1")


def creer_serveurs(reglages: dict) -> dict:
    """Les serveurs de modèles à lancer sur CET ordinateur (reglages.yaml → cerveau.serveurs)."""
    from briques.b06_cerveau.serveurs import ServeurModele

    res = {}
    for nom, s in (reglages["cerveau"].get("serveurs") or {}).items():
        srv = ServeurModele(nom, s["modele"], int(s["port"]), s.get("hote", "127.0.0.1"), int(s.get("contexte", 4096)))
        srv.demarrage = s.get("demarrage", "jamais")
        res[nom] = srv
    return res


class Simulation:
    """Le pupitre du faux robot : pannes d'entraînement et dessin. Aucune commande de mouvement ici."""

    def __init__(self, faux_robot) -> None:
        self.__robot = faux_robot

    def provoquer_panne(self, nom: str) -> None:
        self.__robot.provoquer_panne(nom)

    def reparer(self) -> None:
        self.__robot.reparer()

    def trace(self) -> list:
        return list(self.__robot.trace[-200:])


class CarteIncoherente(RuntimeError):
    """La carte d'identité et l'adaptateur ne disent pas la même chose (faux ou vrai robot)."""


class Systeme:
    def __init__(self, reglages: dict | None = None, dossier_journal: str | Path = DOSSIER_DEFAUT,
                 acceleration: float = 1.0, adaptateur: Adaptateur | None = None, monde: Monde | None = None) -> None:
        self.reglages = reglages or charger_reglages()
        self.bus = Bus()
        self.boite_noire = BoiteNoire(self.bus, dossier_journal)
        self.monde = monde or Monde.charger()  # un monde donné : la clinique en boîte y ajoute son plan (DECISIONS.md)
        # Brique 8 : les mots appris d'un humain (« frigo » = cuisine) sont ajoutés au monde avant tout le reste.
        d = self.reglages.get("doute") or {}
        self.aides = AidesApprises(_chemin(d.get("aides_apprises"), CHEMIN_AIDES))
        self.aides.appliquer(self.monde)
        self.compteur = Compteur()  # la fiche de vérité en direct (ne se remet jamais à zéro)
        self.bus.abonner(self.compteur.ajouter)
        s = self.reglages["securite"]
        limites = LimitesParDefaut(vitesse_m_s=s["vitesse_m_s"], force_n=s["force_n"], distance_m=s.get("distance_m", 5.0))
        g = self.reglages.get("gardien") or {}
        # Brique 7 : le gardien lit regles.yaml au démarrage (un fichier faux = pas de démarrage, avec l'explication).
        self.gardien = Gardien(self.bus, limites, monde=self.monde, regles=_chemin(g.get("regles"), CHEMIN_REGLES),
                               attente_humain_s=float(g.get("attente_humain_s", ATTENTE_HUMAIN_S)),
                               # Brique 14 : allumé si la ligne manque (réglages copiés avant la brique 14).
                               accord_humain_agents=(self.reglages.get("porte_agents") or {}).get("accord_humain") is not False)
        # L'adaptateur est donné directement à la prise : le système n'en garde AUCUNE référence.
        robot = adaptateur or _creer_adaptateur(self.reglages, self.monde, acceleration, self.bus)
        from briques.b02_faux_robot.faux_robot import FauxRobot

        # Le pupitre de pannes n'existe que pour LE faux robot du projet (sa classe, pas une méthode qui lui ressemble).
        self.simulation = Simulation(robot) if isinstance(robot, FauxRobot) else None
        self.prise = Prise(robot, self.gardien.verificateur, self.bus,
                           delai_reponse_s=s["delai_reponse_robot_s"], plafonds=limites.plafonds())
        from briques.b03_adaptateurs.registre import sur_faux_kit

        sur_kit = sur_faux_kit(robot)
        del robot
        # Brique 7 : le gardien voit la position du robot (lecture de l'état, par la prise) et les personnes :
        # simulées (monde.yaml) pour un faux robot ; pour un vrai robot, seulement celles données par les yeux (brique 5).
        # Faux ou vrai : décidé par l'ADAPTATEUR (le faux robot a un pupitre de pannes), jamais par la seule carte :
        # une carte copiée d'un faux robot (« vrai_robot: false ») sur un vrai robot ferait croire à des personnes
        # simulées et afficherait « testé sur faux robot ». Si la carte dit autre chose : pas de démarrage.
        faux = self.simulation is not None or sur_kit  # faux robot du projet, ou adaptateur de la brique 3 sur le faux kit
        if self.prise.carte().vrai_robot == faux:
            raise CarteIncoherente(
                f"La carte « {self.prise.carte().id} » dit vrai_robot: {str(self.prise.carte().vrai_robot).lower()}, "
                f"mais l'adaptateur est {'le faux robot' if faux else 'un vrai robot'}. Corriger la carte "
                f"(vrai_robot: {'false' if faux else 'true'}) avant de démarrer.")
        # Brique 5 : yeux allumés (reglages.yaml → yeux.actif, éteints par défaut) = les personnes viennent de la caméra
        # (simulée avec le faux robot), plus directement de monde.yaml. Éteints : rien ne change.
        from briques.b05_yeux import verifier_reglages

        verifier_reglages(self.reglages.get("yeux"))  # yeux.gardien_vrai_robot: true → pas de démarrage (relecture)
        yeux_actifs = (self.reglages.get("yeux") or {}).get("actif") is True
        simulees = faux and not yeux_actifs
        self.gardien.perception = Perception(lire_etat=self.prise.etat, simulation=simulees,
                                             personnes=self.monde.personnes if simulees else ())
        self.serveurs = creer_serveurs(self.reglages) if self.reglages["cerveau"]["choix"] == "cascade" else {}
        self.cerveau = creer_cerveau(self.reglages, self.bus, self.serveurs)
        self.yeux = None  # brique 5 : ils ne commandent rien ; personnes vues → gardien, objets vus → cerveau
        if yeux_actifs:
            from briques.b05_yeux.lien import LesYeux

            self.yeux = LesYeux(self.reglages["yeux"], self.bus, self.monde, self.gardien.perception, self.prise.etat,
                                faux_robot=faux, genre=self.prise.carte().genre, robot=self.prise.robot)
            self.yeux.relier_au_cerveau(self.cerveau)
        main_levee = (self.reglages.get("interrupteurs") or {}).get("main_levee") or {}
        self.doute = Doute(self.bus, self.monde, self.aides, actif=bool(main_levee.get("actif", True)),
                           incompris_avant_main=int(d.get("incompris_avant_main_levee", 2)),
                           echecs_avant_main=int(d.get("echecs_avant_main_levee", 2)))
        self.chaine = Chaine(self.bus, self.cerveau, self.gardien, self.prise, self.monde,
                             seuil_confiance=self.reglages["cerveau"]["seuil_confiance"],
                             actions_a_confirmer=self.reglages.get("confirmation", {}).get("actions", []),
                             doute=self.doute)
        # Clinique (15.11.2026) : quand la chaîne dit un refus, la tête peut faire « non » — par le gardien et la prise,
        # comme tout le monde. ÉTEINT par défaut (le gardien demande un humain pour un geste près d'une personne) ; sans
        # effet si la carte du robot n'a pas le geste « non » (voir briques/clinique/reactions_tete.py).
        from briques.clinique.reactions_tete import ReactionsDeLaTete

        non_de_la_tete = (self.reglages.get("interrupteurs") or {}).get("non_de_la_tete") or {}
        self.reactions = ReactionsDeLaTete(self.bus, self.gardien, self.prise, actif=non_de_la_tete.get("actif") is True,
                                           humain_a_la_main=lambda: self.chaine.pilote_humain is not None)
        # Clinique (15.11.2026) : un accord humain donné D'AVANCE pour quelques gestes d'un robot précis (décision de
        # Hiba pour la main). ÉTEINT par défaut ; il ne change aucune règle du gardien (briques/clinique/accord_d_avance.py).
        from briques.clinique.accord_d_avance import AccordDAvance

        self.accord_d_avance = AccordDAvance(self.bus, self.chaine, self.prise,
                                             (self.reglages.get("interrupteurs") or {}).get("accord_d_avance"))

    async def demarrer(self) -> None:
        carte = self.prise.carte()
        await self.bus.emettre("session_debut", "systeme", robot=carte.id, carte=carte.model_dump(),
                               vrai_robot=carte.vrai_robot, cerveau=self.cerveau.nom,
                               machine=platform.platform(), mention=carte.mention_test(),
                               regles=self.gardien.regles_lisibles())
        urls = {e["nom"]: e.get("url", "") for e in self.reglages["cerveau"].get("cascade", [])}
        for nom, srv in self.serveurs.items():
            # Seulement si la cascade attend CE serveur sur cet ordinateur (deux Mac : le 8B est sur l'iMac).
            if getattr(srv, "demarrage", "jamais") == "toujours" and srv.modele.exists() and _url_locale(urls.get(nom, "")):
                srv.lancer()  # ne bloque pas : le cerveau à règles répond tant que le modèle se charge
        await self.cerveau.demarrer()
        await self.prise.connecter()
        if self.yeux is not None:
            await self.yeux.allumer()  # brique 5 : ne bloque pas (les outils se chargent à côté)

    async def arreter(self) -> None:
        if self.yeux is not None:
            await self.yeux.eteindre()
        await self.prise.deconnecter()
        await self.cerveau.arreter()
        for srv in self.serveurs.values():
            await asyncio.to_thread(srv.eteindre)  # jusqu'à 15 s : le reste du programme ne se fige pas
        await self.bus.emettre("session_fin", "systeme", robot=self.prise.robot)
        self.boite_noire.fermer()
