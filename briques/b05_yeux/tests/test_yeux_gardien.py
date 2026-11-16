"""Brique 5 → gardien : les personnes vues par la caméra (simulée) arrivent au gardien, avec l'heure de la photo et
la ZONE du sol vue. « Pas vue » n'est pas « pas là » : hors de la zone vue, le gardien demande un humain.

Testé sur faux robot, caméra simulée, Internet coupé. Sans OpenCV, la caméra simulée se calibre avec sa
transformation exacte : ces tests passent aussi (numpy seulement). Corrections après la relecture du lot D :
points 1 (angles morts), 4 (photo fixe), 5 (heure dans le futur), 6 (vraie caméra) — un test chacun ci-dessous.
"""
from __future__ import annotations

import asyncio
import time

import numpy as np
import pytest

from briques.b01_prise.actions import ActionDemandee
from briques.b05_yeux import ReglageRefuse
from briques.b05_yeux.geometrie import Calibration
from briques.b05_yeux.lien import LesYeux
from briques.b05_yeux.prise_yeux import Boite, Branchement, ImageCamera, Personne, Trouvailles
from briques.b07_gardien.perception import PARTOUT, Perception, PersonneVue, zone_couvre
from commun.bus import Bus
from commun.monde import Monde
from conftest import lancer

from aides_yeux import attendre, evenements_yeux, images_neuves, systeme_avec_yeux

AVANCE_3M = ActionDemandee(nom="se_deplacer", parametres={"dx": 3.0, "dy": 0.0})
RECULE_1M = ActionDemandee(nom="se_deplacer", parametres={"dx": -1.0, "dy": 0.0})
PAS_DE_COTE = ActionDemandee(nom="se_deplacer", parametres={"dx": 0.0, "dy": 1.5})
SALUER = ActionDemandee(nom="rejouer_geste", parametres={"nom": "saluer"})


def _codes(decision) -> set[str]:
    return {r.code for r in decision.raisons}


def _hors_du_champ(decision) -> bool:
    return any(r.code == "personnes_inconnues" and r.details.get("hors_du_champ") for r in decision.raisons)


# ---------------------------------------------------------------- comme avant
def test_yeux_eteints_par_defaut_rien_ne_change(fabrique_systeme):
    s = fabrique_systeme()
    assert s.reglages["yeux"]["actif"] is False and s.yeux is None
    assert s.gardien.perception.simulation is True  # personnes simulées de monde.yaml, comme avant la brique 5

    async def go():
        await s.demarrer()
        await s.arreter()
        assert not [e for e in s.bus.historique if e.type == "yeux"]

    lancer(go())


def test_les_personnes_vues_arrivent_au_gardien_avec_leur_place_et_la_zone_vue(tmp_path, reglages):
    s = systeme_avec_yeux(tmp_path, reglages)
    assert s.gardien.perception.simulation is False  # elles ne viennent plus de monde.yaml, mais de la caméra

    async def go():
        await s.demarrer()
        try:
            assert await s.yeux.attendre_une_vue()
            assert await attendre(lambda: s.gardien.perception._heure_annonce is not None)
            vue = await s.gardien.perception.vue()
            assert vue.source_personnes == "yeux (caméra simulée)"
            assert len(vue.personnes) == 1  # le visiteur de monde.yaml (8,6 ; 2,2), vu par la caméra simulée
            p = vue.personnes[0]
            assert abs(p.x - 8.6) < 0.4 and abs(p.y - 2.2) < 0.4 and p.source == "camera_simulee"
            zone = vue.zone_vue  # le robot est en (1 ; 1), cap 0 : il voit devant lui, pas derrière ni à ses pieds
            assert zone.voit(3.0, 1.0) and not zone.voit(0.5, 1.0) and not zone.voit(1.3, 1.0) and not zone.voit(1.0, 2.5)
            demarrage = evenements_yeux(s, "demarrage")[0]
            assert demarrage["mention"] == "testé sur caméra simulée" and demarrage["personnes_au_gardien"] is True
        finally:
            await s.arreter()

    lancer(go())


# ---------------------------------------------------------------- point 1 : les angles morts
def test_angles_morts_une_personne_derriere_ou_a_cote_n_est_pas_absente(tmp_path, reglages):
    """Relecture, point 1 (GRAVE) : une personne 0,5 m DERRIÈRE (recul) ou 0,6 m à CÔTÉ (geste, pas de côté) n'est
    pas vue par la caméra du robot. Avant : « oui ». Maintenant : « humain » (hors du champ). Yeux éteints, avec la
    même personne simulée : « non » (le gardien la connaît)."""
    s = systeme_avec_yeux(tmp_path, reglages)

    async def go():
        await s.demarrer()
        try:
            assert await s.yeux.attendre_une_vue()
            carte = s.prise.carte()
            s.yeux.camera.placer_personne("derriere", 0.5, 1.0)
            await images_neuves(s)
            assert all(abs(p.x - 0.5) > 0.5 for p in (await s.gardien.perception.vue()).personnes)  # pas vue
            d, t = await s.gardien.verifier(RECULE_1M, carte)
            assert d.verdict == "humain" and _hors_du_champ(d) and t is None
            s.yeux.camera.retirer_personne("derriere")
            s.yeux.camera.placer_personne("cote", 1.0, 1.6)
            await images_neuves(s)
            for action in (SALUER, PAS_DE_COTE):
                d, t = await s.gardien.verifier(action, carte)
                assert d.verdict == "humain" and _hors_du_champ(d) and t is None, (action, d)
            res = await s.chaine.traiter("recule d'un mètre", "fr")
            assert res.verdict == "humain" and "Je ne sais pas où sont les personnes" in res.reponses[-1]
        finally:
            await s.arreter()

    lancer(go())

    async def sans_yeux(fabrique):  # même personnes, simulées, yeux éteints : le gardien sait, il dit « non »
        s = fabrique()
        for nom, x, y, action in (("derriere", 0.5, 1.0, RECULE_1M), ("cote", 1.0, 1.6, SALUER)):
            s.gardien.perception.placer_personne(nom, x, y)
            d, _ = await s.gardien.verifier(action, s.prise.carte())
            assert d.verdict == "non" and "trop_pres_personne" in _codes(d)
            s.gardien.perception.retirer_personne(nom)

    from commun.systeme import Systeme

    r = {**reglages, "cerveau": {**reglages["cerveau"], "choix": "regles"}}
    lancer(sans_yeux(lambda: Systeme(r, dossier_journal=tmp_path / "j2", acceleration=20)))


def test_camera_du_robot_aucun_mouvement_sans_humain_mais_le_refus_passe_avant(tmp_path, reglages):
    """Le pied de la caméra du robot n'est jamais vu (angle mort) : tout déplacement ou geste → « humain ».
    Une personne VUE trop près du chemin → « non » (le refus passe avant la demande à un humain), en français et en
    allemand."""
    s = systeme_avec_yeux(tmp_path, reglages)

    async def go():
        await s.demarrer()
        try:
            assert await s.yeux.attendre_une_vue()
            d, ticket = await s.gardien.verifier(AVANCE_3M, s.prise.carte())
            assert d.verdict == "humain" and _hors_du_champ(d) and ticket is None
            d, _ = await s.gardien.verifier(ActionDemandee(nom="regarder", parametres={"cible": "table"}), s.prise.carte())
            assert d.verdict == "oui"  # regarder ne bouge rien
            s.yeux.camera.placer_personne("proche", 3.0, 1.3)  # vue, à 0,3 m du chemin (1,1) → (4,1)
            await images_neuves(s)
            res = await s.chaine.traiter("avance de 3 mètres", "fr")
            assert res.verdict == "non" and "trop près d'une personne" in res.reponses[-1], res.reponses
            res = await s.chaine.traiter("geh 3 Meter vorwärts", "de")
            assert res.verdict == "non" and "zu nahe" in res.reponses[-1], res.reponses
        finally:
            await s.arreter()

    lancer(go())


def test_camera_fixe_qui_voit_toute_la_halle_le_gardien_peut_dire_oui(tmp_path, reglages):
    """Avec une caméra (simulée) fixe qui voit tout le sol de la halle, la zone vue couvre le chemin : « oui ».
    Une personne près du chemin : « non ». Elle part : de nouveau « oui »."""
    s = systeme_avec_yeux(tmp_path, reglages, camera="simulee_fixe")

    async def go():
        await s.demarrer()
        try:
            assert await s.yeux.attendre_une_vue()
            assert "fixe" in s.yeux.calibration_dite and s.yeux.yeux.calibration.repere == "monde"
            d, ticket = await s.gardien.verifier(AVANCE_3M, s.prise.carte())
            assert d.verdict == "oui" and ticket is not None, d
            s.yeux.camera.placer_personne("proche", 3.0, 1.3)
            await images_neuves(s)
            d, _ = await s.gardien.verifier(AVANCE_3M, s.prise.carte())
            assert d.verdict == "non" and "trop_pres_personne" in _codes(d)
            s.yeux.camera.retirer_personne("proche")
            await images_neuves(s)
            d, ticket = await s.gardien.verifier(AVANCE_3M, s.prise.carte())
            assert d.verdict == "oui" and ticket is not None
        finally:
            await s.arreter()

    lancer(go())


def test_zone_couvre_regarde_toute_la_bande_autour_du_chemin():
    class DemiPlan:  # « je vois tout ce qui a x > 0 »
        def voit(self, x, y):
            return x > 0

    assert zone_couvre(PARTOUT, (0, 0), (5, 0), 1.0)
    assert not zone_couvre(DemiPlan(), (1.0, 0.0), (3.0, 0.0), 1.0)  # la bande autour du départ passe sous x = 0
    assert zone_couvre(DemiPlan(), (2.0, 0.0), (4.0, 0.0), 1.0)
    assert not zone_couvre(DemiPlan(), (2.0, 0.0), (-1.0, 0.0), 1.0)  # reculer vers ce qu'on ne voit pas
    assert not zone_couvre(DemiPlan(), (0.5, 0.0), (0.5, 0.0), 1.0)  # un geste sur place, près du bord
    assert zone_couvre(None, (0, 0), (1, 0), 1.0)  # personnes simulées : connues partout


def test_annoncer_des_personnes_demande_la_zone_vue():
    p = Perception(simulation=False)
    with pytest.raises(TypeError):
        p.annoncer_personnes([])  # oubli de la zone : refusé (sinon « pas vue » redeviendrait « pas là »)
    with pytest.raises(ValueError, match="zone"):
        p.annoncer_personnes([], zone=None)


def test_une_personne_tout_pres_pieds_hors_de_l_image_compte_comme_collee_au_robot(tmp_path, reglages):
    """Une personne si proche que ses pieds sortent de l'image est mise À LA PLACE du robot (le pire cas) : « non »."""
    s = systeme_avec_yeux(tmp_path, reglages)

    async def go():
        await s.demarrer()
        try:
            assert await s.yeux.attendre_une_vue()
            s.yeux.camera.placer_personne("collee", 1.75, 1.0)
            await images_neuves(s)
            assert any(p.pieds_coupes for p in s.yeux.derniere_vue.personnes)
            d, _ = await s.gardien.verifier(RECULE_1M, s.prise.carte())
            assert d.verdict == "non" and "trop_pres_personne" in _codes(d)  # même en reculant
        finally:
            await s.arreter()

    lancer(go())


def test_camera_en_panne_le_gardien_demande_un_humain_puis_tout_revient(tmp_path, reglages):
    s = systeme_avec_yeux(tmp_path, reglages, camera="simulee_fixe")
    s.gardien.perception.fraicheur_max_s = 0.4  # 2 s en vrai ; plus court pour le test

    async def go():
        await s.demarrer()
        try:
            assert await s.yeux.attendre_une_vue()
            d, _ = await s.gardien.verifier(AVANCE_3M, s.prise.carte())
            assert d.verdict == "oui"
            s.yeux.camera.provoquer_panne()
            await asyncio.sleep(0.6)
            d, ticket = await s.gardien.verifier(AVANCE_3M, s.prise.carte())
            assert d.verdict == "humain" and "personnes_inconnues" in _codes(d) and ticket is None
            res = await s.chaine.traiter("avance de 1 mètre", "fr")
            assert res.verdict == "humain" and "Je ne sais pas où sont les personnes" in res.reponses[-1]
            pannes = evenements_yeux(s, "camera")
            assert pannes[-1]["valeur"] is False and "panne" in pannes[-1]["raison"]
            assert evenements_yeux(s, "gardien")[-1]["valeur"] is False
            s.yeux.camera.reparer()
            await images_neuves(s)
            d, _ = await s.gardien.verifier(AVANCE_3M, s.prise.carte())
            assert d.verdict == "oui"
        finally:
            await s.arreter()

    lancer(go())


def test_sans_outil_pour_les_personnes_rien_n_est_dit_au_gardien(tmp_path, reglages):
    """Caméra qui marche, mais seulement ArUco (qui ne voit pas les personnes) : « personne » serait un mensonge."""
    s = systeme_avec_yeux(tmp_path, reglages, branchements=["aruco"])
    s.gardien.perception.fraicheur_max_s = 0.4

    async def go():
        await s.demarrer()
        try:
            assert await s.yeux.attendre_une_vue()
            await images_neuves(s)
            assert (await s.gardien.perception.vue()).personnes is None
            d, _ = await s.gardien.verifier(AVANCE_3M, s.prise.carte())
            assert d.verdict == "humain" and "personnes_inconnues" in _codes(d)
            assert "aucun outil" in evenements_yeux(s, "gardien")[-1]["raison"]
        finally:
            await s.arreter()

    lancer(go())


# ---------------------------------------------------------------- vrai robot : refusé au démarrage
def test_gardien_vrai_robot_true_le_programme_refuse_de_demarrer(tmp_path, reglages):
    """Relecture, point 1 : tant que ce n'est pas relu, `yeux.gardien_vrai_robot: true` empêche de démarrer,
    avec un message clair (même yeux éteints : on ne garde pas un réglage dangereux en attente)."""
    from commun.systeme import Systeme

    for actif in (True, False):
        r = {**reglages, "cerveau": {**reglages["cerveau"], "choix": "regles"},
             "yeux": {**reglages["yeux"], "actif": actif, "gardien_vrai_robot": True}}
        with pytest.raises(ReglageRefuse, match="gardien_vrai_robot.*REFUSÉ"):
            Systeme(r, dossier_journal=tmp_path / "journal")
    with pytest.raises(ReglageRefuse):
        LesYeux({"camera": "aucune", "gardien_vrai_robot": "oui"}, Bus(), Monde.charger(), Perception(), None,
                faux_robot=False)


def test_vrai_robot_les_personnes_ne_vont_jamais_au_gardien(tmp_path):
    cv2 = pytest.importorskip("cv2", reason="OpenCV absent : la caméra « fichier » en a besoin")
    photo = tmp_path / "photo.png"
    cv2.imwrite(str(photo), np.full((240, 320, 3), 128, np.uint8))

    async def go():
        perception, bus = Perception(simulation=False), Bus()
        yeux = LesYeux({"camera": f"fichier:{photo}", "branchements": ["aruco"], "periode_s": 0.05}, bus,
                       Monde.charger(), perception, None, faux_robot=False)
        await yeux.allumer()
        try:
            assert await yeux.attendre_une_vue()
            await asyncio.sleep(0.2)
            assert perception._heure_annonce is None
            raison = [e.donnees for e in bus.historique if e.type == "yeux" and e.donnees.get("quoi") == "gardien"][-1]
            assert raison["valeur"] is False and "vrai robot" in raison["raison"]
        finally:
            await yeux.eteindre()

    lancer(go())


# ---------------------------------------------------------------- point 4 : la photo fixe
class _VoitUnePersonne(Branchement):
    """Un détecteur imité qui « voit » une personne loin devant : pour vérifier ce qui part (ou non) au gardien."""

    nom, voit_les_personnes, voit_les_objets = "detecteur_imite", True, True

    def analyser(self, image):
        return Trouvailles(personnes=[Personne(boite=Boite(x=150, y=100, largeur=20, hauteur=60), confiance=0.9,
                                               source="detecteur_imite")])


def test_une_photo_fixe_ne_donne_jamais_de_personnes_au_gardien(tmp_path):
    """Relecture, point 4 : une image lue dans un fichier passait pour neuve à chaque lecture. Maintenant : jamais de
    personnes au gardien (même avec le faux robot), jamais « je ne vois pas » au cerveau, mention « photo fixe »."""
    cv2 = pytest.importorskip("cv2", reason="OpenCV absent : la caméra « fichier » en a besoin")
    from briques.b05_yeux.camera_simulee import CameraSimulee

    photo = tmp_path / "vieille_photo.png"
    cv2.imwrite(str(photo), np.full((240, 320, 3), 128, np.uint8))

    async def etat():
        from types import SimpleNamespace

        return SimpleNamespace(position={"x": 1.0, "y": 1.0, "cap": 0.0})

    async def go():
        perception, bus, monde = Perception(simulation=False), Bus(), Monde.charger()
        yeux = LesYeux({"camera": f"fichier:{photo}", "branchements": ["simule"], "periode_s": 0.05}, bus, monde,
                       perception, etat, faux_robot=True)
        yeux.yeux.branchements = [_VoitUnePersonne()]
        yeux.yeux.calibration = Calibration(homographie=CameraSimulee(monde).homographie_exacte().tolist(),
                                            largeur=320, hauteur=240, source="essai")
        await yeux.allumer()
        try:
            assert await yeux.attendre_une_vue()
            await asyncio.sleep(0.2)
            assert yeux.derniere_vue.photo_fixe and len(yeux.derniere_vue.personnes) == 1
            assert perception._heure_annonce is None and (await perception.vue()).personnes is None
            evs = [e.donnees for e in bus.historique if e.type == "yeux"]
            assert evs[0]["mention"].startswith("photo fixe")
            assert "photo fixe" in [e for e in evs if e.get("quoi") == "gardien"][-1]["raison"]
            assert yeux.peut_chercher("bouteille") == (False, "photo fixe : ne dit pas ce qui est là maintenant")
        finally:
            await yeux.eteindre()

    lancer(go())


# ---------------------------------------------------------------- point 5 : l'heure de la photo
def test_la_fraicheur_se_compte_depuis_la_photo_et_une_heure_fausse_est_refusee():
    """Relecture, point 5 : une heure dans le futur (ex. l'horloge murale time.time() au lieu de time.monotonic())
    était ramenée à « maintenant » et jugée fraîche. Maintenant : rien d'annoncé, et l'annonce d'avant est oubliée."""
    async def go():
        p = Perception(simulation=False, fraicheur_max_s=2.0)
        p.annoncer_personnes([PersonneVue(id="a", x=1, y=1)], heure=time.monotonic() - 3.0, zone=PARTOUT)
        assert (await p.vue()).personnes is None  # photo vieille de 3 s
        p.annoncer_personnes([PersonneVue(id="a", x=1, y=1)], heure=time.monotonic() - 0.5, zone=PARTOUT)
        assert len((await p.vue()).personnes) == 1
        for fausse in (time.time() - 3600, time.monotonic() + 1.0, float("nan"), float("inf"), True, "maintenant"):
            p.annoncer_personnes([PersonneVue(id="a", x=1, y=1)], heure=time.monotonic() - 0.1, zone=PARTOUT)
            p.annoncer_personnes([], heure=fausse, zone=PARTOUT)
            assert (await p.vue()).personnes is None, fausse  # « personnes inconnues », pas « personne »
        p.annoncer_personnes([], heure=time.monotonic() + 0.05, zone=PARTOUT)  # petit écart d'horloge : toléré
        assert (await p.vue()).personnes == []
        p.annoncer_personnes([PersonneVue(id="b", x=2, y=2)], zone=PARTOUT)  # sans heure : maintenant
        assert (await p.vue()).personnes[0].id == "b"

    lancer(go())


# ---------------------------------------------------------------- point 6 : la vraie caméra
class _CameraImitee:
    """Une « vraie » caméra imitée (ni simulée, ni photo fixe)."""

    source = "imitee"

    def __init__(self, bruit: bool = True, attente_s: float = 0.0, journal: list | None = None) -> None:
        self.bruit, self.attente_s, self.journal = bruit, attente_s, journal if journal is not None else []
        self._fixe = np.full((240, 320, 3), 100, np.uint8)

    def lire(self, etat=None):
        self.journal.append("image")
        time.sleep(self.attente_s)
        pixels = np.random.randint(0, 255, (240, 320, 3), np.uint8) if self.bruit else self._fixe.copy()
        return ImageCamera(pixels=pixels, heure=time.monotonic(), source=self.source)

    def fermer(self):
        pass


def _yeux_avec(camera, lire_etat=None, **reglage) -> tuple[LesYeux, Bus]:
    bus = Bus()
    yeux = LesYeux({"camera": "aucune", "branchements": ["simule"], "periode_s": 0.05, **reglage}, bus,
                   Monde.charger(), Perception(simulation=False), lire_etat, faux_robot=True)
    yeux.camera = camera
    return yeux, bus


def _raisons_camera(bus) -> list[str]:
    return [e.donnees.get("raison", "") for e in bus.historique if e.type == "yeux" and e.donnees.get("quoi") == "camera"]


def test_une_image_figee_est_une_panne():
    """Relecture, point 6 : un flux qui répète la même image (pilote ou réseau figé) passait pour neuf."""
    async def go():
        yeux, bus = _yeux_avec(_CameraImitee(bruit=False))
        await yeux.allumer()
        try:
            assert await attendre(lambda: any("figée" in r for r in _raisons_camera(bus)), 3)
            n = yeux.images
            await asyncio.sleep(0.3)
            assert yeux.images == n  # plus aucune image regardée tant qu'elle est figée
        finally:
            await yeux.eteindre()
        yeux, bus = _yeux_avec(_CameraImitee(bruit=True))  # une vraie image bouge toujours un peu (bruit du capteur)
        await yeux.allumer()
        try:
            assert await attendre(lambda: yeux.images >= 8, 3)
            assert not any("figée" in r for r in _raisons_camera(bus))
        finally:
            await yeux.eteindre()

    lancer(go())


def test_vraie_camera_la_position_du_robot_est_lue_apres_l_image():
    journal: list[str] = []

    async def lire_etat():
        from types import SimpleNamespace

        journal.append("position")
        return SimpleNamespace(position={"x": 2.0, "y": 1.0, "cap": 0.0})

    async def go():
        yeux, _ = _yeux_avec(_CameraImitee(journal=journal), lire_etat)
        await yeux.une_image()
        assert journal == ["image", "position"]
        assert yeux._derniere_image.pose == (2.0, 1.0, 0.0)

    lancer(go())


def test_une_lecture_plus_longue_que_le_delai_est_jetee():
    """Une image arrivée après le délai n'est pas neuve (son heure dit « maintenant », mais elle a traîné) : jetée."""
    async def go():
        yeux, bus = _yeux_avec(_CameraImitee(attente_s=0.5), delai_camera_s=0.3)
        await yeux.allumer()
        try:
            assert await attendre(lambda: any("jetée" in r for r in _raisons_camera(bus)), 4)
            assert yeux.images == 0  # aucune de ces images n'a été regardée
        finally:
            await yeux.eteindre()

    lancer(go())


def test_une_camera_bloquee_est_une_panne_et_n_empeche_pas_d_arreter():
    """Un flux réseau qui ne rend plus d'image (lire() bloqué) : panne dite après le délai, rien au gardien, et
    l'arrêt du programme n'attend pas la caméra."""
    import threading

    debloquer = threading.Event()

    class CameraBloquee:
        source = "bloquee"

        def lire(self, etat=None):
            debloquer.wait(5)
            raise RuntimeError("débloquée")

        def fermer(self):
            debloquer.wait(5)  # comme une vraie caméra dont la lecture tient le verrou

    async def go():
        yeux, bus = _yeux_avec(CameraBloquee(), delai_camera_s=0.3)
        await yeux.allumer()
        try:
            assert await yeux.attendre_une_vue(3)
            assert any("bloquée" in r for r in _raisons_camera(bus)) and yeux.perception._heure_annonce is None
        finally:
            t0 = time.monotonic()
            await yeux.eteindre()
            assert time.monotonic() - t0 < 2.0
            debloquer.set()

    lancer(go())


def test_la_camera_simulee_est_refusee_avec_un_vrai_robot():
    async def go():
        yeux = LesYeux({"camera": "simulee", "branchements": ["simule"]}, Bus(), Monde.charger(),
                       Perception(simulation=False), None, faux_robot=False)
        assert yeux.camera is None and "refusé" in yeux.erreur_camera
        assert await yeux.une_image() is None

    lancer(go())
