"""Brique 5 — Le lien des yeux avec le reste du robot.

Les yeux ne commandent RIEN. Ils donnent :
- au GARDIEN : les personnes vues, au sol, dans le repère du monde, avec l'heure de la photo
  (Perception.annoncer_personnes). Sans nouvelles fraîches (caméra en panne, pas calibrée, aucun outil qui voit les
  personnes), ils ne disent RIEN : le gardien, sans nouvelles depuis 2 s, demande un humain avant de bouger.
- au CERVEAU : « prends la bouteille » → la bouteille est-elle vue ? Oui : sa position est notée (boîte noire) et
  l'action continue. Non : une question (« Je ne vois pas : bouteille. Pouvez-vous me montrer où c'est ? »).
  Les yeux ne savent pas chercher (caméra en panne, aucun outil pour les objets) : rien ne change.

Deux boucles : une image toutes les `periode_s` (personnes, objets, marqueurs), et les textes de temps en temps
(`periode_textes_s`, plus lent). Les calculs tournent à côté (fil séparé) pour ne jamais retarder le chien de garde.

Avec le faux robot : caméra SIMULÉE et vérité du dessin (« testé sur caméra simulée »). Avec un vrai robot : les
personnes ne sont JAMAIS données au gardien (`yeux.gardien_vrai_robot: true` est refusé au démarrage tant que la
relecture sécurité ne l'a pas permis). Le reste (objets, marqueurs, textes) marche.

Corrections après relecture (lot D) :
- les personnes sont données AVEC la zone du sol vue (ZoneVue) : hors de cette zone (derrière, à côté, l'angle mort au
  pied de la caméra, au-delà de la portée), le gardien ne sait pas et demande un humain ;
- une photo fixe (`fichier:`) ne donne jamais de personnes ni d'objets « vus maintenant » ;
- vraie caméra : images identiques de suite = image figée = panne ; position du robot lue APRÈS l'image ; une lecture
  plus longue que `delai_camera_s` est jetée.
"""
from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from briques.b07_gardien.perception import PersonneVue

from . import verifier_reglages
from .branchements import fabriquer
from .branchements.aruco import BranchementAruco
from .camera import ouvrir_camera
from .camera_simulee import CameraEnPanne, CameraRefusee, CameraSimulee
from .geometrie import Calibration, calibrer, monde_vers_robot, robot_vers_monde
from .marqueurs import CHEMIN_MARQUEURS, ListeMarqueurs
from .prise_yeux import ImageCamera, Vue, Yeux

RACINE = Path(__file__).resolve().parents[2]
BRANCHEMENTS_DEFAUT = ["simule", "aruco", "mediapipe", "rapidocr"]
VUE_RECENTE_S = 2.0  # une vue plus vieille ne sert plus à dire « je ne vois pas »
DELAI_CAMERA_S = 2.0  # une caméra qui ne rend pas d'image dans ce délai est « en panne » (flux réseau bloqué…)
IMAGES_IDENTIQUES_MAX = 5  # vraie caméra : 5 images exactement pareilles de suite = image figée (un capteur a du bruit)
MARGE_BORD = 0.04  # part de l'image retirée de la zone vue, sur les côtés et en bas (une personne au bord peut échapper)


class ZoneVue:
    """Le sol vu par la caméra sur UNE image, dans le repère du monde : ce qui est dans l'image (moins les bords),
    devant la caméra, à portée. Pas l'angle mort au pied de la caméra, ni derrière, ni à côté.
    Limite : un objet ou une personne qui cache le sol derrière lui n'est pas retiré de la zone (à vérifier)."""

    def __init__(self, calibration: Calibration, pose: tuple[float, float, float] | None) -> None:
        self.calibration, self.pose = calibration, pose

    def voit(self, x: float, y: float) -> bool:
        if self.calibration.repere == "robot":
            if self.pose is None:
                return False
            x, y = monde_vers_robot(self.pose, x, y)
        return self.calibration.voit(x, y, MARGE_BORD)


@dataclass
class ChoseVue:
    """Un objet (ou un lieu) vu : où, quand, par quel outil."""

    nom: str
    heure: float
    source: str
    x: float | None = None  # dans le monde, si posé au sol (None : caméra non calibrée ou position du robot inconnue)
    y: float | None = None
    distance_max_m: float | None = None  # depuis le robot ; exacte si posé au sol, sinon PLUS PETITE en vrai
    direction_deg: float | None = None  # depuis l'avant du robot, + = à gauche (juste même sur une table)
    precision: str = "juste si posé au sol ; sur une table : direction juste, distance trop grande"

    def age_s(self) -> float:
        return time.monotonic() - self.heure


class LesYeux:
    def __init__(self, reglages: dict, bus, monde, perception, lire_etat, faux_robot: bool, genre: str = "humanoide",
                 robot: str | None = None) -> None:
        r = reglages or {}
        verifier_reglages(r)  # gardien_vrai_robot: true → refusé (relecture sécurité du lot D)
        self.reglages, self.bus, self.monde, self.perception = r, bus, monde, perception
        self._lire_etat = lire_etat  # lecture seule de l'état du robot (par la prise)
        self.faux_robot, self.genre, self.robot = faux_robot, genre, robot
        self.periode_s = max(0.05, float(r.get("periode_s", 0.2)))
        self.periode_textes_s = max(0.2, float(r.get("periode_textes_s", 5.0)))
        self.objet_vu_depuis_s = float(r.get("objet_vu_depuis_s", 3.0))
        self.delai_camera_s = max(0.1, float(r.get("delai_camera_s", DELAI_CAMERA_S)))
        self._lecture: asyncio.Future | None = None  # une lecture de la caméra pas encore finie
        self._debut_lecture = 0.0
        self._derniers_pixels = None  # vraie caméra : pour repérer une image figée
        self._identiques = 0
        self.donner_au_gardien = faux_robot  # vrai robot : jamais (gardien_vrai_robot: true est refusé plus haut)
        self.marqueurs = ListeMarqueurs.charger(_chemin(r.get("marqueurs"), CHEMIN_MARQUEURS))
        self.camera, self.erreur_camera = None, ""
        try:
            self.camera = ouvrir_camera(str(r.get("camera", "auto")), monde, genre, faux_robot)
        except (CameraRefusee, ValueError) as e:
            self.erreur_camera = str(e)
        if self.camera is None and not self.erreur_camera:
            self.erreur_camera = "aucune caméra (reglages.yaml → yeux.camera)"
        self.yeux = Yeux(fabriquer(list(r.get("branchements") or BRANCHEMENTS_DEFAUT), monde, self.marqueurs, r))
        self.calibration_dite = ""
        self.derniere_vue: Vue | None = None
        self.derniere_vue_textes: Vue | None = None
        self._derniere_image: ImageCamera | None = None
        self._choses: dict[str, ChoseVue] = {}  # objets vus (par nom du monde)
        self.lieux_vus: dict[str, ChoseVue] = {}  # lieux reconnus (marqueur ArUco ou panneau lu)
        self._taches: list[asyncio.Task] = []
        self._pret = asyncio.Event()
        self._etats: dict[str, Any] = {}  # dernier état dit dans la boîte noire (on ne répète pas à chaque image)
        self.images, self.images_ratees = 0, 0

    @property
    def simulee(self) -> bool:
        return isinstance(self.camera, CameraSimulee)

    @property
    def photo_fixe(self) -> bool:
        return getattr(self.camera, "photo_fixe", False) is True

    def mention(self) -> str:
        if self.simulee:
            return "testé sur caméra simulée"
        return "photo fixe (pas une caméra : rien de vu maintenant)" if self.photo_fixe else "vraie caméra"

    # ---------------------------------------------------------------- allumer, éteindre
    async def allumer(self) -> None:
        """Lancer les boucles. Ne bloque pas : les outils se chargent dans la boucle (quelques secondes)."""
        if self._taches:
            return
        self._taches.append(asyncio.create_task(self._boucle()))

    async def eteindre(self) -> None:
        for t in self._taches:
            t.cancel()
        for t in self._taches:
            try:
                await t
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 - on s'arrête de toute façon
                pass
        self._taches.clear()
        if self.camera is not None:
            try:  # une caméra bloquée ne doit jamais empêcher le programme de s'arrêter
                await asyncio.wait_for(asyncio.to_thread(self.camera.fermer), self.delai_camera_s)
            except (asyncio.TimeoutError, Exception):  # noqa: BLE001
                pass

    async def attendre_une_vue(self, delai_s: float = 10.0) -> bool:
        """Pour les tests et le démarrage : attendre la première image analysée."""
        try:
            await asyncio.wait_for(self._pret.wait(), delai_s)
            return True
        except asyncio.TimeoutError:
            return False

    def preparer(self) -> dict[str, str]:
        """Charger les outils et calibrer. Rend {branchement: raison} pour ceux qui manquent."""
        absents = self.yeux.preparer()
        if self.yeux.calibration is None:
            self.yeux.calibration, self.calibration_dite = self._calibration()
        return absents

    def _calibration(self) -> tuple[Calibration | None, str]:
        if isinstance(self.camera, CameraSimulee) and self.camera.fixe is not None:
            cal = Calibration(repere="monde", homographie=self.camera.homographie_exacte().tolist(),
                              largeur=self.camera.largeur, hauteur=self.camera.hauteur,
                              source="caméra simulée fixe : transformation exacte")
            return cal, "caméra simulée fixe (toute la halle), transformation exacte"
        if isinstance(self.camera, CameraSimulee):
            return self._calibrer_camera_simulee(self.camera)
        chemin = _chemin(self.reglages.get("calibration"), RACINE / "briques/b05_yeux/calibration.yaml")
        if not chemin.exists():
            return None, f"caméra non calibrée ({chemin.name} absent : python -m briques.b05_yeux.calibrer)"
        try:
            cal = Calibration.charger(chemin)
        except Exception as e:  # noqa: BLE001
            return None, f"calibration illisible ({chemin.name}) : {e}"
        return cal, f"{chemin.name} ({cal.source}, {cal.date})"

    def _calibrer_camera_simulee(self, camera: CameraSimulee) -> tuple[Calibration, str]:
        """Comme samedi, mais dans le faux monde : 3 marqueurs ArUco dessinés au sol devant le robot, retrouvés par
        OpenCV. Sans OpenCV : la transformation exacte, connue parce que la caméra est simulée."""
        placements = camera.placements_de_calibration(self.marqueurs.calibration.numeros, self.marqueurs.calibration.taille_m)
        aruco = BranchementAruco(self.marqueurs)
        if aruco.preparer() is None:
            image = camera.image_de_calibration(placements)
            vus = [m for m in aruco.analyser(image).marqueurs if m.sorte == "calibration"]
            if vus:
                cal = calibrer(vus, placements, image.largeur, image.hauteur, source="caméra simulée : marqueurs ArUco dessinés")
                return cal, f"caméra simulée, {len(vus)} marqueur(s) ArUco retrouvé(s) par OpenCV"
        cal = Calibration(homographie=camera.homographie_exacte().tolist(), largeur=camera.largeur, hauteur=camera.hauteur,
                          source="caméra simulée : transformation exacte (sans ArUco)")
        return cal, "caméra simulée, transformation exacte (OpenCV absent)"

    # ---------------------------------------------------------------- les boucles
    async def _boucle(self) -> None:
        try:
            absents = await asyncio.to_thread(self.preparer)
        except Exception as e:  # noqa: BLE001 - sans outils ni calibration, les yeux continuent (et le disent)
            absents = {"preparation": f"{type(e).__name__}: {e}"}
        await self._dire("demarrage", True, camera=getattr(self.camera, "source", None) or "aucune",
                         erreur_camera=self.erreur_camera, absents=absents, calibration=self.calibration_dite,
                         personnes_au_gardien=self.donner_au_gardien, simulation=self.simulee,
                         mention=self.mention())
        if self.yeux.prets(seulement_rapides=False) and self.camera is not None:
            self._taches.append(asyncio.create_task(self._boucle_textes()))
        while True:
            t0 = time.monotonic()
            try:
                await self.une_image()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 - les yeux ne tombent jamais : on le dit et on continue
                await self._dire("erreur", f"{type(e).__name__}: {e}")
            self._pret.set()
            await asyncio.sleep(max(0.0, self.periode_s - (time.monotonic() - t0)))

    async def _boucle_textes(self) -> None:
        while True:
            await asyncio.sleep(self.periode_textes_s)
            image = self._derniere_image
            if image is None or time.monotonic() - image.heure > VUE_RECENTE_S:
                continue
            vue = await asyncio.to_thread(self.yeux.voir, image, False)
            self.derniere_vue_textes = vue
            for t in vue.textes:
                if t.lieu:
                    self.lieux_vus[t.lieu] = ChoseVue(nom=t.lieu, heure=vue.heure, source=f"texte « {t.texte} »")

    async def une_image(self) -> Vue | None:
        """Une image : lire la caméra, regarder, noter les objets, donner les personnes au gardien."""
        # La caméra simulée dessine depuis la position du robot : elle la lit AVANT. Une vraie caméra : APRÈS l'image.
        etat = await self._etat() if self.simulee else None
        if self.camera is None:
            await self._dire("camera", False, raison=self.erreur_camera)
            await self._dire_gardien("pas de caméra")
            return None
        try:
            image = await self._lire_camera(etat)
        except (CameraEnPanne, CameraRefusee, OSError, RuntimeError) as e:
            self.images_ratees += 1
            await self._dire("camera", False, raison=str(e))
            await self._dire_gardien("caméra en panne")
            return None
        if not self.simulee:
            image.pose = _pose(await self._etat())
        await self._dire("camera", True)
        vue = await asyncio.to_thread(self.yeux.voir, image, True)
        self.images += 1
        self.derniere_vue, self._derniere_image = vue, image
        for b in vue.branchements:
            await self._dire(f"branchement:{b.nom}", b.etat, raison=b.raison)
        self._noter_choses(vue, image.pose)
        await self._donner_au_gardien(vue, image)
        return vue

    async def _lire_camera(self, etat) -> ImageCamera:
        """Lire une image à côté (fil séparé), sans jamais attendre plus de `delai_camera_s`. Une lecture bloquée
        n'est pas relancée tant qu'elle n'est pas finie (pas de fils qui s'empilent)."""
        if self._lecture is None:
            self._debut_lecture = time.monotonic()
            self._lecture = asyncio.ensure_future(asyncio.to_thread(self.camera.lire, etat))
        fini, _ = await asyncio.wait({self._lecture}, timeout=self.delai_camera_s)
        if not fini:
            raise CameraEnPanne(f"pas d'image depuis {self.delai_camera_s:.1f} s (caméra bloquée ?)")
        lecture, self._lecture = self._lecture, None
        image = lecture.result()
        if time.monotonic() - self._debut_lecture > self.delai_camera_s:
            raise CameraEnPanne("lecture plus longue que le délai : image jetée (elle n'est plus neuve)")
        if not self.simulee and not image.photo_fixe:
            self._verifier_pas_figee(image)
        return image

    def _verifier_pas_figee(self, image: ImageCamera) -> None:
        """Vraie caméra : un capteur a toujours un peu de bruit. Des images exactement pareilles de suite = un flux
        figé qui répète la dernière image (pilote, réseau) : panne, jusqu'à une image différente."""
        import numpy as np

        precedente, self._derniers_pixels = self._derniers_pixels, image.pixels
        pareille = precedente is not None and precedente.shape == image.pixels.shape and np.array_equal(precedente, image.pixels)
        self._identiques = self._identiques + 1 if pareille else 0
        if self._identiques + 1 >= IMAGES_IDENTIQUES_MAX:
            raise CameraEnPanne(f"image figée : {self._identiques + 1} images identiques de suite")

    async def _etat(self):
        try:
            return await self._lire_etat() if self._lire_etat is not None else None
        except Exception:  # noqa: BLE001
            return None

    # ---------------------------------------------------------------- le gardien
    async def _donner_au_gardien(self, vue: Vue, image: ImageCamera) -> None:
        if not self.donner_au_gardien:
            await self._dire_gardien("vrai robot : personnes jamais données au gardien (relecture sécurité à faire)")
            return
        if image.photo_fixe or self.photo_fixe:
            await self._dire_gardien("photo fixe : jamais de personnes pour le gardien")
            return
        if not vue.personnes_fiables:
            await self._dire_gardien("aucun outil ne voit les personnes sur cette image")
            return
        if not vue.calibree:
            await self._dire_gardien(self.calibration_dite or "caméra non calibrée")
            return
        if vue.repere == "robot" and image.pose is None:
            await self._dire_gardien("position du robot inconnue")
            return
        personnes = []
        for i, p in enumerate(vue.personnes, start=1):
            if p.pieds_coupes and vue.repere == "robot":
                x, y = image.pose[0], image.pose[1]  # pieds hors de l'image : la personne est tout près du robot
            elif p.pieds_coupes:
                await self._dire_gardien("une personne au bord de l'image, pieds cachés : place inconnue")
                return
            elif p.sol is None:
                await self._dire_gardien("une personne vue, mais sa place au sol est inconnue")
                return
            elif vue.repere == "robot":
                x, y = robot_vers_monde(image.pose, p.sol.x, p.sol.y)
            else:
                x, y = p.sol.x, p.sol.y
            personnes.append(PersonneVue(id=f"vue{i}", x=round(x, 3), y=round(y, 3), source=p.source))
        source = "yeux (caméra simulée)" if image.simulee else "yeux"
        zone = ZoneVue(self.yeux.calibration, image.pose)  # hors de cette zone, le gardien ne sait pas
        self.perception.annoncer_personnes(personnes, source=source, heure=image.heure, zone=zone)
        await self._dire_gardien(None)

    async def _dire_gardien(self, raison: str | None) -> None:
        await self._dire("gardien", raison is None, raison=raison or "")

    # ---------------------------------------------------------------- les objets, pour le cerveau
    def _noter_choses(self, vue: Vue, pose) -> None:
        """Les objets vus, avec leur place si la caméra est calibrée. La place vient du bas de la boîte, supposé AU SOL :
        pour un objet sur une table, la DIRECTION est juste mais la distance est trop grande (« precision »)."""
        cal = self.yeux.calibration
        trouves = [(o.nom, o.boite.bas_milieu(), o.source) for o in vue.objets if o.nom]
        trouves += [(m.nom, m.centre(), "aruco") for m in vue.marqueurs if m.sorte == "objet" and m.nom]
        for nom, pixel, source in trouves:
            x = y = d = direction = None
            sol = cal.vers_sol(*pixel, vue.largeur, vue.hauteur, limiter=False) if cal is not None else None
            if sol is not None and vue.repere == "robot" and pose is not None:
                x, y = robot_vers_monde(pose, sol.x, sol.y)
                d, direction = math.hypot(sol.x, sol.y), math.degrees(math.atan2(sol.y, sol.x))
            elif sol is not None and vue.repere == "monde":
                x, y = sol.x, sol.y
                if pose is not None:
                    d = math.hypot(x - pose[0], y - pose[1])
            self._choses[nom] = ChoseVue(nom=nom, heure=vue.heure, source=source, x=_r(x), y=_r(y), distance_max_m=_r(d),
                                         direction_deg=_r(direction))
        for m in vue.marqueurs:
            if m.sorte == "lieu" and m.nom:
                self.lieux_vus[m.nom] = ChoseVue(nom=m.nom, heure=vue.heure, source=f"marqueur ArUco n° {m.numero}")

    def ou_est(self, objet: str, depuis_s: float | None = None) -> ChoseVue | None:
        """L'objet a-t-il été vu il y a moins de `depuis_s` secondes ? Où ?"""
        c = self._choses.get(objet)
        limite = self.objet_vu_depuis_s if depuis_s is None else depuis_s
        return c if c is not None and c.age_s() <= limite else None

    def peut_chercher(self, objet: str) -> tuple[bool, str]:
        """Les yeux savent-ils dire « je ne vois pas cet objet » en ce moment ?"""
        v = self.derniere_vue
        if self.photo_fixe:
            return False, "photo fixe : ne dit pas ce qui est là maintenant"
        if self._etats.get("camera") != (True, "") or v is None or time.monotonic() - v.heure > VUE_RECENTE_S:
            return False, "pas d'image récente (caméra en panne ou éteinte)"
        outils = {b.nom for b in v.branchements if b.etat == "ok"}
        if outils & {"simule", "mediapipe"}:
            return True, ""
        if "aruco" in outils and any(m.objet == objet for m in self.marqueurs.objets):
            return True, ""
        return False, "aucun outil ne sait trouver cet objet (MediaPipe absent, pas de marqueur ArUco)"

    async def filet_objet(self, decision):
        """Après le cerveau : « prends la bouteille » sans bouteille vue → une question. Rien d'autre ne change."""
        action = getattr(decision, "action", None)
        if decision.genre != "action" or action is None or action.nom != "saisir":
            return decision
        objet = action.parametres.get("objet")
        if not objet:
            return decision
        peut, raison = self.peut_chercher(objet)
        if not peut:
            await self.bus.emettre("yeux", "yeux", robot=self.robot, quoi="objet_non_cherche", objet=objet, raison=raison)
            return decision
        vu = self.ou_est(objet)
        if vu is not None:
            await self.bus.emettre("yeux", "yeux", robot=self.robot, quoi="objet_vu", objet=objet, x=vu.x, y=vu.y,
                                   distance_max_m=vu.distance_max_m, direction_deg=vu.direction_deg, precision=vu.precision,
                                   depuis_s=round(vu.age_s(), 2), outil=vu.source,
                                   mention=self.mention())
            return decision
        await self.bus.emettre("yeux", "yeux", robot=self.robot, quoi="objet_pas_vu", objet=objet,
                               depuis_s=self.objet_vu_depuis_s)
        return decision.model_copy(update={"genre": "question", "question": "question_pas_vu", "options": [action],
                                           "action": None})

    def relier_au_cerveau(self, cerveau) -> None:
        """Le cerveau passe ses décisions par `filet_objet`. Le cerveau ne sait rien des yeux (ni l'inverse), et
        l'objet cerveau reste le même (la cascade reste une cascade pour le chef de démonstration)."""
        decider = cerveau.decider

        async def decider_avec_les_yeux(texte, langue, carte, monde):
            return await self.filet_objet(await decider(texte, langue, carte, monde))

        cerveau.decider = decider_avec_les_yeux

    # ---------------------------------------------------------------- pour l'écran et la boîte noire
    def resume(self) -> dict[str, Any]:
        v = self.derniere_vue
        return {
            "camera": getattr(self.camera, "source", None) or "aucune", "erreur_camera": self.erreur_camera,
            "simulation": self.simulee, "calibration": self.calibration_dite,
            "personnes_au_gardien": self.donner_au_gardien, "images": self.images, "images_ratees": self.images_ratees,
            "derniere_vue_age_s": round(time.monotonic() - v.heure, 2) if v else None,
            "personnes": len(v.personnes) if v else None,
            "objets": sorted({c.nom for c in self._choses.values() if c.age_s() <= self.objet_vu_depuis_s}),
            "lieux": sorted(n for n, c in self.lieux_vus.items() if c.age_s() <= 10),
            "branchements": [b.model_dump() for b in v.branchements] if v else [],
        }

    async def _dire(self, quoi: str, valeur, **details) -> None:
        """Un événement « yeux » dans la boîte noire, seulement quand quelque chose change."""
        cle = (valeur, details.get("raison", ""))
        if self._etats.get(quoi) == cle:
            return
        self._etats[quoi] = cle
        await self.bus.emettre("yeux", "yeux", robot=self.robot, quoi=quoi, valeur=valeur, **details)


def _chemin(valeur, defaut: Path) -> Path:
    if not valeur:
        return Path(defaut)
    p = Path(valeur)
    return p if p.is_absolute() else RACINE / p


def _pose(etat) -> tuple[float, float, float] | None:
    p = (getattr(etat, "position", None) or {}) if etat is not None else {}
    x, y, cap = p.get("x"), p.get("y"), p.get("cap", 0.0)
    if all(isinstance(v, (int, float)) and math.isfinite(v) for v in (x, y, cap)):
        return (float(x), float(y), float(cap))
    return None


def _r(v):
    return None if v is None else round(float(v), 3)
