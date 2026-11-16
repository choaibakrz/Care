"""Brique 5 — La caméra SIMULÉE du faux robot : une petite image dessinée du faux monde, vue par le robot.

- Elle dessine (en numpy) le sol de la halle, la table, les personnes et les objets aux positions de commun/monde.yaml
  (les objets suivent l'état du faux robot : un objet posé ailleurs est dessiné ailleurs), les marqueurs ArUco posés
  au sol aux lieux (marqueurs.yaml) et un panneau écrit à chaque lieu (si OpenCV est installé).
- Elle garde la « vérité du dessin » (ce qu'elle a dessiné, et où dans l'image) : le branchement `simule` la lit à
  la place d'un vrai détecteur de personnes. C'est de la SIMULATION : tout ce qui en sort est « testé sur caméra simulée ».
- Jamais avec un vrai robot : elle refuse un état qui dit « simulation: false ».

La caméra est un modèle « sténopé » (un trou d'épingle) : un point du monde est projeté sur l'image selon la
hauteur, l'inclinaison et le champ de la caméra (MONTAGES, ou un montage donné).
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import numpy as np

from commun.monde import Monde

from .geometrie import PlacementMarqueur, homographie
from .marqueurs import ListeMarqueurs
from .prise_yeux import ImageCamera

PRES = 0.05  # m : un point plus près que ça (ou derrière la caméra) n'est pas dessiné


class CameraEnPanne(RuntimeError):
    """La caméra ne donne pas d'image (panne provoquée, câble, position du robot inconnue…)."""


class CameraRefusee(RuntimeError):
    """Cette caméra ne doit pas servir ici (ex. la caméra simulée avec un vrai robot)."""


@dataclass
class Montage:
    """Où la caméra est posée sur le robot."""

    hauteur_m: float  # au-dessus du sol
    inclinaison_deg: float  # négatif : regarde vers le bas
    lacet_deg: float = 0.0  # tournée par rapport à l'avant du robot (+ : vers la gauche)
    champ_deg: float = 70.0  # champ horizontal
    avance_m: float = 0.0  # devant le centre du robot


# Montages d'exemple pour les faux robots (chiffres inventés pour la simulation).
MONTAGES = {
    "humanoide": Montage(1.30, -25, 0, 70, 0.10),
    "chien": Montage(0.35, -8, 0, 80, 0.30),
    "bras": Montage(1.10, -35, 90, 70, 0.0),  # le bras regarde la table, à sa gauche
    "roues": Montage(0.80, -20, 0, 70, 0.10),
    "autre": Montage(1.00, -20, 0, 70, 0.0),
}
# Caméra FIXE simulée, au-dessus du bord sud de la halle, qui voit tout le sol de la halle (x, y, hauteur, cap,
# inclinaison) : pour montrer qu'avec une vue de tout le sol, le gardien peut dire « oui » sans humain.
FIXE_HALLE = (5.0, -4.0, 6.0, 90.0, -40.0)
MONTAGE_FIXE = Montage(6.0, -40, 0, 84, 0.0)

# Tailles des choses dessinées (largeur, profondeur, hauteur en m ; couleur rouge, vert, bleu). Inventées.
TAILLES = {
    "bouteille": (0.08, 0.08, 0.25, (40, 140, 60)),
    "tasse": (0.09, 0.09, 0.10, (235, 235, 245)),
    "valise": (0.45, 0.22, 0.65, (120, 70, 40)),
    "objet_test": (0.10, 0.10, 0.10, (220, 40, 40)),
    "caisse": (0.50, 0.40, 0.40, (200, 130, 50)),
}
TAILLE_DEFAUT = (0.20, 0.20, 0.20, (150, 150, 150))
TABLE = (1.2, 0.8, 0.75, (150, 105, 60))
CORPS = (0.45, 0.25, 1.45, (50, 80, 170))
TETE = (0.22, 0.22, 0.25, (225, 185, 150))
MUR, SOL, SOL_CALIBRATION = (225, 215, 195), (175, 175, 170), (185, 185, 180)


@dataclass
class _Cam:
    """Position et orientation de la caméra, et ses réglages d'image."""

    centre: np.ndarray
    droite: np.ndarray
    bas: np.ndarray
    avant: np.ndarray
    fx: float
    cx: float
    cy: float

    def projeter(self, points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Points du monde (N×3) → pixels (N×2) et profondeur (N)."""
        d = np.asarray(points, dtype=float) - self.centre
        x, y, z = d @ self.droite, d @ self.bas, d @ self.avant
        with np.errstate(divide="ignore", invalid="ignore"):
            u = self.cx + self.fx * x / z
            v = self.cy + self.fx * y / z
        return np.c_[u, v], z


@dataclass
class _Dessin:
    profondeur: float
    faire: object  # fonction (image) -> None
    verite: dict | None = None


@dataclass
class CameraSimulee:
    monde: Monde
    genre: str = "humanoide"
    largeur: int = 320
    hauteur: int = 240
    montage: Montage | None = None
    fixe: tuple[float, float, float, float, float] | None = None  # caméra fixe : x, y, hauteur, cap, inclinaison
    marqueurs: ListeMarqueurs | None = None
    panneaux: bool = True  # un panneau écrit (nom du lieu) à chaque lieu, si OpenCV est là
    personnes: dict[str, tuple[float, float]] = field(default_factory=dict)
    caches: set[str] = field(default_factory=set)  # objets retirés du dessin (tests : « la bouteille n'est pas là »)
    en_panne: bool = False
    source: str = "camera_simulee"

    def __post_init__(self) -> None:
        self.montage = self.montage or MONTAGES.get(self.genre, MONTAGES["autre"])
        if self.marqueurs is None:
            self.marqueurs = ListeMarqueurs.charger()
        if not self.personnes:
            self.personnes = {p.id: (p.position.x, p.position.y) for p in self.monde.personnes}
        self._textures: dict[str, np.ndarray | None] = {}

    # ---------- faux monde (tests, répétitions) ----------
    def placer_personne(self, ident: str, x: float, y: float) -> None:
        self.personnes[ident] = (float(x), float(y))

    def retirer_personne(self, ident: str) -> None:
        self.personnes.pop(ident, None)

    def provoquer_panne(self) -> None:
        self.en_panne = True

    def reparer(self) -> None:
        self.en_panne = False

    # ---------- la caméra ----------
    def ouvrir(self) -> None:
        """Rien à ouvrir : la caméra simulée est toujours là (sauf panne provoquée)."""

    def fermer(self) -> None:
        """Rien à fermer."""

    def lire(self, etat=None) -> ImageCamera:
        """Une image vue depuis la position du robot (lue dans son état). Lève CameraEnPanne si pas d'image."""
        if self.en_panne:
            raise CameraEnPanne("caméra simulée : panne provoquée")
        extra = (getattr(etat, "extra", None) or {}) if etat is not None else {}
        if extra.get("simulation") is False:
            raise CameraRefusee("caméra SIMULÉE avec un robot qui n'est pas simulé : refusé")
        pose = self._pose(etat)
        if pose is None:
            raise CameraEnPanne("caméra simulée : position du robot inconnue")
        objets = {k: tuple(v) for k, v in (extra.get("objets") or {}).items()} or \
            {o.id: (o.position.x, o.position.y) for o in self.monde.objets}
        tenu = getattr(etat, "objet_tenu", None) if etat is not None else None
        heure = time.monotonic()
        pixels, verite = self._rendre(pose, objets, tenu)
        return ImageCamera(pixels=pixels, heure=heure, source=self.source, verite=verite, pose=pose)

    def _pose(self, etat) -> tuple[float, float, float] | None:
        if self.fixe is not None:
            return (self.fixe[0], self.fixe[1], self.fixe[3])
        if etat is None:
            d = self.monde.depart
            return (d.x, d.y, d.cap)
        p = getattr(etat, "position", None) or {}
        x, y, cap = p.get("x"), p.get("y"), p.get("cap", 0.0)
        if all(isinstance(v, (int, float)) and math.isfinite(v) for v in (x, y, cap)):
            return (float(x), float(y), float(cap))
        return None

    def _cam(self, pose: tuple[float, float, float]) -> _Cam:
        m = self.montage
        if self.fixe is not None:
            cx_, cy_, z, cap, incl = self.fixe
            centre = np.array([cx_, cy_, z])
        else:
            x, y, cap_robot = pose
            r = math.radians(cap_robot)
            centre = np.array([x + m.avance_m * math.cos(r), y + m.avance_m * math.sin(r), m.hauteur_m])
            cap, incl = cap_robot + m.lacet_deg, m.inclinaison_deg
        psi, theta = math.radians(cap), math.radians(incl)
        avant = np.array([math.cos(theta) * math.cos(psi), math.cos(theta) * math.sin(psi), math.sin(theta)])
        droite = np.array([math.sin(psi), -math.cos(psi), 0.0])
        haut = np.cross(droite, avant)
        fx = (self.largeur / 2) / math.tan(math.radians(m.champ_deg) / 2)
        return _Cam(centre, droite, -haut, avant, fx, self.largeur / 2, self.hauteur / 2)

    # ---------- dessin ----------
    def _rendre(self, pose, objets: dict[str, tuple], tenu: str | None) -> tuple[np.ndarray, list[dict]]:
        cam = self._cam(pose)
        img = np.empty((self.hauteur, self.largeur, 3), np.uint8)
        img[:] = MUR
        L, H = self.monde.taille.get("largeur", 10), self.monde.taille.get("hauteur", 6)
        _polygone_sol(img, cam, [(0, 0), (L, 0), (L, H), (0, H)], SOL)
        dessins: list[_Dessin] = []
        for m in self.marqueurs.lieux:  # marqueurs ArUco posés au sol aux lieux
            lieu = self.monde.lieu(m.lieu)
            if lieu is None:
                continue
            x, y = (m.position.x, m.position.y) if m.position else (lieu.position.x, lieu.position.y)
            self._ajouter_marqueur(dessins, cam, PlacementMarqueur(numero=m.numero, x=x, y=y, taille_m=m.taille_m))
        table = self.monde.lieu("table")
        if table is not None:
            self._ajouter_boite(dessins, cam, table.position.x, table.position.y, 0.0, TABLE, None)
        if self.panneaux:
            for lieu in self.monde.lieux:
                self._ajouter_panneau(dessins, cam, lieu)
        for ident, (x, y) in self.personnes.items():
            corps = _sommets(x, y, 0.0, CORPS)
            tete = _sommets(x, y, CORPS[2], TETE)
            verite = {"sorte": "personne", "id": ident, "monde": (round(x, 3), round(y, 3))}
            self._ajouter_boite(dessins, cam, x, y, 0.0, CORPS, verite, extra=tete, couleur_extra=TETE[3],
                                sommets_verite=np.vstack([corps, tete]))
        for ident, (x, y) in objets.items():
            if ident == tenu or ident in self.caches:
                continue
            taille = TAILLES.get(ident, TAILLE_DEFAUT)
            sur_table = table is not None and abs(x - table.position.x) <= TABLE[0] / 2 and \
                abs(y - table.position.y) <= TABLE[1] / 2
            obj = self.monde.objet(ident)
            etiquette = ((obj.noms.get("en") or [ident])[0]) if obj else ident
            verite = {"sorte": "objet", "id": ident, "etiquette": etiquette, "monde": (round(x, 3), round(y, 3)),
                      "sur_table": sur_table}
            self._ajouter_boite(dessins, cam, x, y, TABLE[2] if sur_table else 0.0, taille, verite)
        dessins.sort(key=lambda d: -d.profondeur)  # du plus loin au plus près
        verites = []
        for d in dessins:
            d.faire(img)
            if d.verite is not None:
                verites.append(d.verite)
        return img, verites

    def _ajouter_boite(self, dessins, cam, x, y, z0, taille, verite, extra=None, couleur_extra=None,
                       sommets_verite=None) -> None:
        s = _sommets(x, y, z0, taille)
        tous = s if extra is None else np.vstack([s, extra])
        pix, z = cam.projeter(tous)
        if (z < PRES).any():
            return  # (en partie) derrière la caméra : pas dessiné, pas vu
        v = None
        if verite is not None:
            boite = _boite_dans_image(cam.projeter(sommets_verite if sommets_verite is not None else s)[0],
                                      self.largeur, self.hauteur)
            if boite is None:
                return  # hors de l'image : pas vu
            v = {**verite, "boite": boite}

        def faire(img, s=s, extra=extra):
            _dessiner_boite(img, cam, s, taille[3])
            if extra is not None:
                _dessiner_boite(img, cam, extra, couleur_extra)

        dessins.append(_Dessin(float(np.linalg.norm(np.array([x, y, z0]) - cam.centre)), faire, v))

    def _ajouter_marqueur(self, dessins, cam, p: PlacementMarqueur) -> None:
        texture = self._texture_marqueur(p.numero)
        if texture is None:
            return
        cases = 6  # 4×4 cases + le bord noir
        avec_marge = PlacementMarqueur(numero=p.numero, x=p.x, y=p.y, taille_m=p.taille_m * (cases + 2) / cases,
                                       cap_deg=p.cap_deg)
        coins = np.array([[cx, cy, 0.0] for cx, cy in avec_marge.coins()])
        pix, z = cam.projeter(coins)
        if (z < PRES).any():
            return
        dessins.append(_Dessin(float(np.linalg.norm(np.array([p.x, p.y, 0.0]) - cam.centre)) + 50,  # au sol : dessous
                               lambda img, pix=pix, t=texture: _plaquer(img, pix, t)))

    def _ajouter_panneau(self, dessins, cam, lieu) -> None:
        texture = self._texture_panneau(lieu.id, (lieu.noms.get("fr") or [lieu.id])[0])
        if texture is None:
            return
        x, y = lieu.position.x, lieu.position.y
        L, H = self.monde.taille.get("largeur", 10), self.monde.taille.get("hauteur", 6)
        a = math.atan2(H / 2 - y, L / 2 - x)  # le panneau regarde le milieu de la halle
        d = (-math.sin(a), math.cos(a))  # la droite de celui qui le lit, debout en face
        lg, bas, haut = 0.8, 1.0, 1.0 + 0.8 * texture.shape[0] / texture.shape[1]
        coins = np.array([[x - d[0] * lg / 2, y - d[1] * lg / 2, haut], [x + d[0] * lg / 2, y + d[1] * lg / 2, haut],
                          [x + d[0] * lg / 2, y + d[1] * lg / 2, bas], [x - d[0] * lg / 2, y - d[1] * lg / 2, bas]])
        pix, z = cam.projeter(coins)
        if (z < PRES).any():
            return
        face = np.array([math.cos(a), math.sin(a), 0.0])
        if face @ (cam.centre - np.array([x, y, bas])) <= 0:
            return  # vu de dos : on ne voit pas l'écriture
        dessins.append(_Dessin(float(np.linalg.norm(np.array([x, y, bas]) - cam.centre)),
                               lambda img, pix=pix, t=texture: _plaquer(img, pix, t)))

    def _texture_marqueur(self, numero: int) -> np.ndarray | None:
        cle = f"m{numero}"
        if cle not in self._textures:
            try:
                from .marqueurs import image_marqueur

                self._textures[cle] = image_marqueur(numero, self.marqueurs.dictionnaire, cote_px=96)
            except ImportError:  # sans OpenCV : pas de marqueurs dessinés
                self._textures[cle] = None
        return self._textures[cle]

    def _texture_panneau(self, ident: str, texte: str) -> np.ndarray | None:
        cle = f"p{ident}"
        if cle not in self._textures:
            try:
                import cv2
            except ImportError:
                self._textures[cle] = None
                return None
            import unicodedata

            ecrit = "".join(c for c in unicodedata.normalize("NFKD", texte.upper()) if ord(c) < 128)
            t = np.full((60, 240), 255, np.uint8)
            echelle = min(1.4, 210 / max(1, cv2.getTextSize(ecrit, cv2.FONT_HERSHEY_SIMPLEX, 1.0, 2)[0][0]))
            (lt, ht), _ = cv2.getTextSize(ecrit, cv2.FONT_HERSHEY_SIMPLEX, echelle, 2)
            cv2.putText(t, ecrit, ((240 - lt) // 2, (60 + ht) // 2), cv2.FONT_HERSHEY_SIMPLEX, echelle, 0, 2, cv2.LINE_AA)
            self._textures[cle] = t
        return self._textures[cle]

    # ---------- calibration et contrôle (tests, essai du samedi) ----------
    def image_de_calibration(self, placements: list[PlacementMarqueur]) -> ImageCamera:
        """Le robot au centre d'un grand sol vide, avec les marqueurs de calibration posés dans SON repère
        (x devant, y à gauche) : comme samedi, avec le mètre ruban."""
        if self.fixe is not None:
            raise CameraRefusee("caméra fixe : calibrer avec des marqueurs posés dans le repère du monde")
        cam = self._cam((0.0, 0.0, 0.0))
        img = np.empty((self.hauteur, self.largeur, 3), np.uint8)
        img[:] = MUR
        _polygone_sol(img, cam, [(-20, -20), (20, -20), (20, 20), (-20, 20)], SOL_CALIBRATION)
        dessins: list[_Dessin] = []
        for p in placements:
            self._ajouter_marqueur(dessins, cam, p)
        for d in sorted(dessins, key=lambda d: -d.profondeur):
            d.faire(img)
        return ImageCamera(pixels=img, heure=time.monotonic(), source=self.source + ":calibration", verite=[],
                           pose=(0.0, 0.0, 0.0))

    def placements_de_calibration(self, numeros=(0, 1, 2), taille_m: float = 0.28) -> list[PlacementMarqueur]:
        """Où poser les 3 marqueurs pour que CETTE caméra les voie en entier : un près, deux plus loin à gauche et
        à droite (pas trop loin : vu de biais, un marqueur au sol devient trop fin pour être reconnu)."""
        m = self.montage
        fx = (self.largeur / 2) / math.tan(math.radians(m.champ_deg) / 2)
        bas = math.radians(m.inclinaison_deg) - math.atan((self.hauteur / 2) / fx)  # le rayon du bas de l'image
        d_min = m.hauteur_m / math.tan(-bas) if bas < 0 else 1.0
        d_max = math.sqrt(fx * taille_m * m.hauteur_m / 20)  # au-delà, le marqueur fait moins de ~20 pixels de haut
        d1 = d_min + 0.15 + taille_m / 2
        d2 = max(d1 + 0.3, min(d_max, d1 + 1.0))
        lat = max(0.3, min(0.8, d2 * math.tan(math.radians(m.champ_deg) / 2) * 0.45))
        l = math.radians(m.lacet_deg)
        sortie = []
        for numero, (d, cote) in zip(numeros, [(d1, 0.0), (d2, lat), (d2, -lat)]):
            d += m.avance_m
            sortie.append(PlacementMarqueur(numero=numero, x=round(d * math.cos(l) - cote * math.sin(l), 3),
                                            y=round(d * math.sin(l) + cote * math.cos(l), 3), taille_m=taille_m,
                                            cap_deg=m.lacet_deg))
        return sortie

    def homographie_exacte(self) -> np.ndarray:
        """La vraie transformation pixel → sol (repère du robot ; caméra fixe : repère du monde), connue parce que la
        caméra est simulée. Sert aux tests (comparer avec la calibration par marqueurs) et quand OpenCV manque."""
        cam = self._cam((0.0, 0.0, 0.0))
        sol = [(1.5, -0.8), (1.5, 0.8), (4.0, 1.5), (4.0, -1.5), (2.5, 0.0)]
        if self.fixe is not None:
            sol = [(2.0, 1.0), (8.0, 1.0), (8.0, 5.0), (2.0, 5.0), (5.0, 3.0)]
        elif self.genre == "bras":
            sol = [(0.8, 0.5), (-0.8, 0.5), (0.8, 1.6), (-0.8, 1.6), (0.0, 1.0)]
        pix, _ = cam.projeter(np.array([[x, y, 0.0] for x, y in sol]))
        return homographie(pix, sol)


# ---------------------------------------------------------------- petites fonctions de dessin (numpy seul)
def _sommets(x: float, y: float, z0: float, taille) -> np.ndarray:
    lx, ly, lz = taille[0] / 2, taille[1] / 2, taille[2]
    return np.array([[x + sx * lx, y + sy * ly, z0 + sz * lz] for sz in (0, 1) for sy in (-1, 1) for sx in (-1, 1)])


# Faces d'une boîte (indices des sommets de _sommets), avec leur normale ; pas le dessous.
_FACES = [((4, 5, 7, 6), (0, 0, 1)), ((0, 1, 5, 4), (0, -1, 0)), ((2, 3, 7, 6), (0, 1, 0)),
          ((0, 2, 6, 4), (-1, 0, 0)), ((1, 3, 7, 5), (1, 0, 0))]


def _dessiner_boite(img: np.ndarray, cam: _Cam, sommets: np.ndarray, couleur) -> None:
    pix, _ = cam.projeter(sommets)
    for indices, normale in _FACES:
        centre = sommets[list(indices)].mean(axis=0)
        if np.dot(normale, cam.centre - centre) <= 0:
            continue  # face vue de dos
        ombre = 1.0 if normale[2] else (0.85 if normale[0] else 0.72)
        _remplir(img, pix[list(indices)], tuple(int(c * ombre) for c in couleur))


def _remplir(img: np.ndarray, pts: np.ndarray, couleur) -> None:
    """Remplir un polygone convexe (pixels)."""
    pts = np.asarray(pts, dtype=float)
    if len(pts) < 3 or not np.isfinite(pts).all():
        return
    h, w = img.shape[:2]
    x0, y0 = max(0, int(np.floor(pts[:, 0].min()))), max(0, int(np.floor(pts[:, 1].min())))
    x1, y1 = min(w, int(np.ceil(pts[:, 0].max())) + 1), min(h, int(np.ceil(pts[:, 1].max())) + 1)
    if x0 >= x1 or y0 >= y1:
        return
    ys, xs = np.mgrid[y0:y1, x0:x1] + 0.5
    signe = np.sign(_aire(pts)) or 1.0
    dedans = np.ones(xs.shape, bool)
    for i in range(len(pts)):
        (ax, ay), (bx, by) = pts[i], pts[(i + 1) % len(pts)]
        dedans &= ((bx - ax) * (ys - ay) - (by - ay) * (xs - ax)) * signe >= 0
    img[y0:y1, x0:x1][dedans] = couleur


def _aire(pts: np.ndarray) -> float:
    x, y = pts[:, 0], pts[:, 1]
    return float(0.5 * (np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def _plaquer(img: np.ndarray, coins_px: np.ndarray, texture: np.ndarray) -> None:
    """Dessiner une image (marqueur, panneau) sur un quadrilatère de l'image (coins : haut-g, haut-d, bas-d, bas-g).
    Chaque pixel est la moyenne de 4 points (dessin moins « en escalier » : les coins des marqueurs sont plus justes)."""
    th, tw = texture.shape[:2]
    try:
        h_inv = homographie(coins_px, [(0, 0), (tw, 0), (tw, th), (0, th)])
    except ValueError:
        return
    h, w = img.shape[:2]
    x0, y0 = max(0, int(np.floor(coins_px[:, 0].min()))), max(0, int(np.floor(coins_px[:, 1].min())))
    x1, y1 = min(w, int(np.ceil(coins_px[:, 0].max())) + 1), min(h, int(np.ceil(coins_px[:, 1].max())) + 1)
    if x0 >= x1 or y0 >= y1:
        return
    ys, xs = np.mgrid[y0:y1, x0:x1]
    somme = np.zeros(xs.shape, float)
    compte = np.zeros(xs.shape, float)
    for dx, dy in ((0.25, 0.25), (0.75, 0.25), (0.25, 0.75), (0.75, 0.75)):
        p = np.c_[xs.ravel() + dx, ys.ravel() + dy, np.ones(xs.size)] @ h_inv.T
        with np.errstate(divide="ignore", invalid="ignore"):
            tx, ty = p[:, 0] / p[:, 2], p[:, 1] / p[:, 2]
        ok = (p[:, 2] > 0) & (tx >= 0) & (tx < tw) & (ty >= 0) & (ty < th)
        val = np.zeros(xs.size)
        val[ok] = texture[ty[ok].astype(int), tx[ok].astype(int)] if texture.ndim == 2 else \
            texture[ty[ok].astype(int), tx[ok].astype(int)].mean(axis=1)
        somme += val.reshape(xs.shape)
        compte += ok.reshape(xs.shape)
    dedans = compte > 0
    if not dedans.any():
        return
    zone = img[y0:y1, x0:x1]
    melange = (somme[dedans] + zone[dedans].mean(axis=1) * (4 - compte[dedans])) / 4  # bords : mélangé au fond
    zone[dedans] = np.repeat(np.clip(melange, 0, 255).astype(np.uint8)[:, None], 3, axis=1)


def _polygone_sol(img: np.ndarray, cam: _Cam, coins_xy, couleur) -> None:
    """Un polygone posé au sol, coupé devant la caméra (la partie derrière n'existe pas à l'image)."""
    pts = np.array([[x, y, 0.0] for x, y in coins_xy])
    d = pts - cam.centre
    z = d @ cam.avant
    coupe = []
    for i in range(len(pts)):  # découpage de Sutherland-Hodgman contre le plan « juste devant la caméra »
        a, b, za, zb = pts[i], pts[(i + 1) % len(pts)], z[i], z[(i + 1) % len(pts)]
        if za >= PRES:
            coupe.append(a)
        if (za >= PRES) != (zb >= PRES):
            t = (PRES - za) / (zb - za)
            coupe.append(a + t * (b - a))
    if len(coupe) >= 3:
        pix, _ = cam.projeter(np.array(coupe))
        _remplir(img, pix, couleur)


def _boite_dans_image(pix: np.ndarray, largeur: int, hauteur: int) -> tuple[float, float, float, float] | None:
    x0, y0 = max(0.0, float(pix[:, 0].min())), max(0.0, float(pix[:, 1].min()))
    x1, y1 = min(float(largeur), float(pix[:, 0].max())), min(float(hauteur), float(pix[:, 1].max()))
    if x1 - x0 < 1 or y1 - y0 < 1:
        return None
    return (round(x0, 2), round(y0, 2), round(x1 - x0, 2), round(y1 - y0, 2))
