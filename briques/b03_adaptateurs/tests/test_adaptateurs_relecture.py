"""Brique 3 — un test par constat de la relecture sécurité indépendante (commit 9c0ef26). Testé sur faux robot.

Chaque test reproduit l'essai du relecteur (scripts e1 à e8) et vérifie que le défaut ne revient pas.
"""
from __future__ import annotations

import asyncio
import math
import re
import threading
import time
from pathlib import Path

import pytest
import yaml

from aides_adaptateurs import CARTE_COMPLETE, KitSansEtiquette, agir, chaine, faux_sdk
from briques.b01_prise.actions import ActionDemandee
from briques.b01_prise.adaptateur import ActionImpossible
from briques.b01_prise.carte import CarteIdentite, Limites
from briques.b01_prise.conformite import Rapport, verifier_conformite
from briques.b01_prise.prise import Prise
from briques.b03_adaptateurs import conformite_deux_temps as conformite
from briques.b03_adaptateurs import registre
from briques.b03_adaptateurs.assistant import _noter, creer
from briques.b03_adaptateurs.chemins.sdk.faux_sdk import FauxKit
from briques.b03_adaptateurs.chemins.sdk.liaison_sdk import LiaisonSDK
from briques.b03_adaptateurs.modele_vide.adaptateur import MAX_FILS_ARRET, AdaptateurModele
from briques.b07_gardien.gardien import Gardien
from commun.bus import Bus
from conftest import lancer

ICI = Path(__file__).resolve().parents[1]
RACINE = ICI.parents[1]


def _distance(kit, x0, y0):
    with kit._verrou:
        kit._avancer()
    return math.hypot(kit.x - x0, kit.y - y0)


# ---------------------------------------------------------------- 1. le robot ne repart pas après l'arrêt
class KitEtatEnRetard(FauxKit):
    """Un robot dont l'état dit toujours « immobile » (état en retard) : la prise croit l'arrêt confirmé et ne
    renvoie rien. Seul l'adaptateur peut rattraper l'ordre qui était en route."""

    def lire(self):
        etat = super().lire()
        etat["en_mouvement"] = False
        return etat


def test_1_un_ordre_en_route_ne_fait_pas_repartir_le_robot_apres_l_arret():
    async def go():
        # arrêt qui NE BLOQUE PAS (comme StopMove), ordres qui durent 1 s (comme Move du G1), l'ordre de vitesse
        # arrive 80 ms après son départ : l'arrêt, parti après lui, arrive AVANT lui
        kit = KitEtatEnRetard(acceleration=1.0, duree_ordre_s=1.0, arret_bloquant=False, latence_vitesse_s=0.08)
        adaptateur, _ = faux_sdk(kit=kit)
        bus, gardien, prise = chaine(adaptateur)
        await prise.connecter()
        await agir(gardien, prise, "se_deplacer", dx=3.0)
        await asyncio.sleep(0.5)
        kit.ordre_en_route.clear()
        while not kit.ordre_en_route.is_set():  # attendre qu'un ordre de vitesse soit EN ROUTE vers le robot
            await asyncio.sleep(0.001)
        t_arret = time.monotonic()
        await prise.arret_urgence(raison="essai")
        x0, y0 = kit.x, kit.y
        await asyncio.sleep(0.6)
        assert _distance(kit, x0, y0) < 0.06, "le robot ne doit pas repartir (sans correction : ~0,18 m)"
        assert not any(kit._v)
        apres = [nom for h, nom in kit.journal if h > t_arret]
        assert "vitesse" in apres and "stop" in apres[apres.index("vitesse"):], "un arrêt suit l'ordre en route"
        await prise.deconnecter()

    lancer(go())


def test_1_un_ordre_prepare_avant_l_arret_ne_part_jamais():
    async def go():
        adaptateur, kit = faux_sdk()
        bus, gardien, prise = chaine(adaptateur)
        await prise.connecter()
        adaptateur._arret_actif = True  # (test) comme juste après un arrêt d'urgence
        with pytest.raises(ActionImpossible) as e:
            await adaptateur._appel(adaptateur._liaison.vitesse, 0.1, 0.0, 0.0)
        assert e.value.code == "ordre_perime" and kit.appels["vitesse"] == 0
        adaptateur._arret_actif = False
        await prise.deconnecter()

    lancer(go())


# ---------------------------------------------------------------- 2. un arrêt coincé ne fait pas sauter les autres
class KitArretCoince(FauxKit):
    def __init__(self, **options):
        super().__init__(**options)
        self.tentatives: list[float] = []
        self.premier = True

    def arreter_en_urgence(self):
        self.tentatives.append(time.monotonic())
        if self.premier:
            self.premier = False
            time.sleep(3.0)  # la requête est perdue : le kit attend sa réponse
            return 0
        return super().arreter_en_urgence()


def test_2_un_arret_coince_dans_le_kit_n_empeche_pas_les_suivants():
    async def go():
        kit = KitArretCoince(acceleration=1.0, duree_ordre_s=10.0)  # robot SANS chien de garde du fabricant
        adaptateur, _ = faux_sdk(kit=kit)
        bus, gardien, prise = chaine(adaptateur)
        await prise.connecter()
        await agir(gardien, prise, "se_deplacer", dx=3.0)
        await asyncio.sleep(0.4)
        t0 = time.monotonic()
        await prise.arret_urgence(raison="essai")
        await asyncio.sleep(1.0)
        assert len(kit.tentatives) >= 2 and kit.tentatives[1] - t0 < 0.8, "les nouvelles tentatives partent"
        assert not any(kit._v), "le robot est arrêté (arrêt de secours ou 2e tentative)"
        assert any("arrêt non confirmé" in ligne for ligne in adaptateur.journal)
        await prise.deconnecter()

    lancer(go())


def test_2_trop_d_arrets_coinces_chaque_saut_est_note_et_l_ecran_demande_le_bouton_physique():
    class KitToujoursCoince(FauxKit):
        def arreter_en_urgence(self):
            time.sleep(2.0)
            return 0

        def stop(self):
            time.sleep(2.0)
            return 0

    async def go():
        bus = Bus()
        kit = KitToujoursCoince(acceleration=1.0, duree_ordre_s=10.0)
        adaptateur = AdaptateurModele(CARTE_COMPLETE, LiaisonSDK(kit), bus=bus)
        gardien = Gardien(bus)
        prise = Prise(adaptateur, gardien.verificateur, bus)
        await prise.connecter()
        for _ in range(MAX_FILS_ARRET + 2):
            await adaptateur.arret_urgence()
        assert adaptateur.arrets_sautes >= 1
        assert any("SAUTÉE" in ligne for ligne in adaptateur.journal)
        # Attentes « jusqu'à ce que ce soit vrai, 5 s au plus » (pas des pauses fixes : la machine peut être chargée).
        async def bientot(condition) -> bool:
            for _ in range(250):
                if condition():
                    return True
                await asyncio.sleep(0.02)
            return condition()

        assert await bientot(lambda: any("SAUTÉE" in e.donnees.get("texte", "") for e in bus.historique
                                         if e.type == "note" and e.source == "adaptateur")), "noté dans la boîte noire (bus)"
        etat = await prise.etat()
        assert not etat.liaison_ok  # arrêt coincé : on ne sait pas si le robot l'a reçu
        await prise.arret_urgence(raison="essai")
        assert await bientot(lambda: any(e.type == "panne" and e.donnees.get("quoi") == "arret_urgence_non_confirme"
                                         for e in bus.historique))
        await prise.deconnecter()

    lancer(go())


# ---------------------------------------------------------------- 3. mauvais sens, hors du trajet
class KitAEnvers(FauxKit):
    def vitesse(self, vx, vy, vyaw):
        return super().vitesse(-vx, vy, vyaw)  # erreur de signe dans le branchement


class KitDeCote(FauxKit):
    def vitesse(self, vx, vy, vyaw):
        return super().vitesse(vy, vx, vyaw)  # avant et côté échangés


@pytest.mark.parametrize("kit,code", [(KitAEnvers, "mauvais_sens"), (KitDeCote, "hors_trajet")])
def test_3_le_robot_qui_part_dans_le_mauvais_sens_est_arrete_tout_de_suite(kit, code):
    async def go():
        k = kit(acceleration=1.0)
        adaptateur, _ = faux_sdk(kit=k)
        bus, gardien, prise = chaine(adaptateur)
        await prise.connecter()
        x0, y0 = k.x, k.y
        suivi = await agir(gardien, prise, "se_deplacer", dx=0.5)
        fin = await prise.attendre(suivi.id, 10)
        assert fin.statut == "echouee" and fin.code_erreur == code, fin
        await asyncio.sleep(0.4)
        assert _distance(k, x0, y0) < 0.25, "arrêté bien avant le plafond (sans correction : 1,6 m)"
        await prise.deconnecter()

    lancer(go())


# ---------------------------------------------------------------- 4. la conformité ne dit plus RÉUSSI à l'envers
def test_4_un_robot_qui_recule_echoue_au_test_de_conformite():
    class VraiAEnvers(KitSansEtiquette):
        def vitesse(self, vx, vy, vyaw):
            return super().vitesse(-vx, vy, vyaw)

    class LiaisonDeplacement(LiaisonSDK):
        branchees = frozenset({"se_deplacer", "arreter", "etat"})

    carte = CarteIdentite(id="chien-essai", nom="chien essai", genre="chien", capacites=["se_deplacer", "arreter", "etat"],
                          limites=Limites(vitesse_max_m_s=0.5), vrai_robot=True)
    rapport = lancer(conformite.complet(lambda: AdaptateurModele(carte, LiaisonDeplacement(VraiAEnvers()), lent=True),
                                        vrai_attendu=True))
    assert not rapport.reussi
    rate = [c for c in rapport.controles if not c.ok]
    assert any(c.nom == "[complet] action « se_deplacer »" and "mauvais_sens" in c.detail for c in rate), rapport.texte()


def test_4_un_refus_explique_au_depart_reste_bon():
    class LiaisonPresqueVide(LiaisonSDK):
        branchees = frozenset({"arreter", "etat"})

    carte = CARTE_COMPLETE.model_copy(update={"capacites": ["regarder", "arreter", "etat"]})
    rapport = lancer(verifier_conformite(lambda: AdaptateurModele(carte, LiaisonPresqueVide(KitSansEtiquette())), True))
    regarder = next(c for c in rapport.controles if c.nom == "action « regarder »")
    assert regarder.ok and "pas encore branché" in regarder.detail


# ---------------------------------------------------------------- 5. le verrou suit les fichiers
def _rapport_reussi() -> Rapport:
    return Rapport(robot="robot_essai", mention="testé sur vrai robot")


def test_5_changer_la_carte_apres_le_test_rouvre_le_verrou(tmp_path, reglages):
    ici = creer("robot_essai", "chien", "sdk", tmp_path)
    _noter(ici, "complet", _rapport_reussi())
    assert registre.conformite_reussie(ici)
    notes = yaml.safe_load((ici / "conformite.yaml").read_text(encoding="utf-8"))
    assert set(notes["complet"]["empreintes"]) == {"carte.yaml", "liaison.py", "adaptateur.py"}
    carte = (ici / "carte.yaml").read_text(encoding="utf-8")
    (ici / "carte.yaml").write_text(carte.replace("vitesse_max_m_s: 0.0", "vitesse_max_m_s: 1.5"), encoding="utf-8")
    assert not registre.conformite_reussie(ici) and "changé" in registre.raison_refus_vrai(ici)
    r = {**reglages, "robot": {**reglages["robot"], "vrai_robot": True}}
    with pytest.raises(ValueError, match="changé"):
        registre.fabriquer("robot_essai", r, tmp_path)


def test_5_apres_fabrication_le_registre_verifie_vrai_ou_faux():
    with pytest.raises(ValueError, match="faux kit"):
        registre._verifier(faux_sdk()[0], True, "essai")  # un « vrai » robot sur le faux kit
    with pytest.raises(ValueError, match="vrai robot"):
        registre._verifier(AdaptateurModele(CARTE_COMPLETE, LiaisonSDK(object())), False, "essai")
    with pytest.raises(ValueError):  # une copie du faux kit : le système la voit fausse, la liaison vraie → refus
        registre._verifier(AdaptateurModele(CARTE_COMPLETE, LiaisonSDK(KitSansEtiquette())), False, "essai")
    assert registre._verifier(faux_sdk()[0], False, "essai")


# ---------------------------------------------------------------- 6. la phrase tapée : un nombre au hasard, et l'honnêteté
def test_6_la_phrase_contient_un_nombre_tire_au_hasard_et_dit_ses_limites():
    lignes, invites = [], []

    def lire(invite):
        invites.append(invite)
        return "sans mouvement"  # sans le nombre : refusé

    assert not conformite.confirmer("sans mouvement", "avertissement", lire=lire, ecrire=lignes.append)
    attendu = re.search(r"« (.+?) »", invites[0]).group(1)
    assert re.fullmatch(r"sans mouvement \d{4}", attendu)
    assert conformite.confirmer("sans mouvement", "avertissement", lire=lambda i: re.search(r"« (.+?) »", i).group(1),
                                ecrire=lignes.append)
    assert any("protège contre l'OUBLI, pas contre un agent" in l for l in lignes)
    for fichier in (ICI / "conformite_deux_temps.py", ICI / "assistant.py", ICI / "registre.py", ICI / "GUIDE.md",
                    RACINE / "BRANCHER_UN_ROBOT.md", RACINE / "savoir-faire/brancher-un-robot/SKILL.md"):
        texte = fichier.read_text(encoding="utf-8").replace("\n", " ")
        assert re.search(r"contre l'(OUBLI|oubli)", texte) and re.search(r"pas contre (un agent|quelqu'un)", texte), fichier.name


# ---------------------------------------------------------------- 8. un état bizarre ne fait plus taire l'arrêt
@pytest.mark.parametrize("valeur", ["n/a", [80], float("nan"), True])
def test_8_un_etat_bizarre_ne_casse_pas_la_verification_de_l_arret(valeur):
    class KitEtatBizarre(FauxKit):
        bizarre = False

        def lire(self):
            e = super().lire()
            if self.bizarre:
                e.update({"batterie_pct": valeur, "x": "abc", "erreurs": "moteur chaud", "objet_tenu": 3})
            return e

        def arreter_en_urgence(self):  # l'arrêt du kit est IGNORÉ : la prise doit réessayer et alerter
            self.appels["arret_vu"] += 1
            return 0

        def stop(self):  # l'arrêt normal aussi (sinon il rattrape tout, et la prise n'a rien à réessayer)
            return 0

    async def go():
        kit = KitEtatBizarre(acceleration=1.0, duree_ordre_s=10.0)
        adaptateur, _ = faux_sdk(kit=kit)
        bus, gardien, prise = chaine(adaptateur)
        await prise.connecter()
        await agir(gardien, prise, "se_deplacer", dx=3.0)
        await asyncio.sleep(0.4)
        kit.bizarre = True
        etat = await prise.etat()
        assert etat.batterie_pct is None and etat.erreurs[0] == "moteur chaud" and etat.objet_tenu is None
        assert "x" not in etat.extra["odometrie"]
        await prise.arret_urgence(raison="essai")
        await asyncio.sleep(1.0)
        assert kit.appels["arret_vu"] >= 3, "la prise réessaie"
        assert any(e.type == "panne" and e.donnees.get("quoi") == "arret_urgence_non_confirme" for e in bus.historique)
        await prise.deconnecter()

    lancer(go())


def test_8_un_etat_qui_n_est_pas_un_dictionnaire_devient_liaison_perdue():
    class KitListe(FauxKit):
        def lire(self):
            super().lire()
            return [1, 2, 3]

    async def go():
        adaptateur, _ = faux_sdk(kit=KitListe())
        bus, gardien, prise = chaine(adaptateur)
        await prise.connecter()
        etat = await prise.etat()
        assert not etat.liaison_ok and etat.erreurs == ["liaison perdue"]
        await prise.deconnecter()

    lancer(go())


# ---------------------------------------------------------------- 9. un arrêt sans code = non confirmé
def test_9_un_arret_qui_ne_rend_rien_n_est_pas_confirme():
    class KitSansCode(FauxKit):
        def stop(self):
            super().stop()
            return None  # comme StopMove() du G1 (lu : il ne rend rien)

    async def go():
        adaptateur, kit = faux_sdk(kit=KitSansCode())
        bus, gardien, prise = chaine(adaptateur)
        await prise.connecter()
        # 2e relecture du lot C : un « stop » non confirmé par le kit ne lève plus d'erreur inexpliquée ; la prise passe à
        # l'arrêt d'urgence (l'arrêt du fabricant, avec ses secours) et refuse en expliquant.
        from briques.b01_prise.raisons import ActionRefusee

        with pytest.raises(ActionRefusee) as refus:
            await agir(gardien, prise, "arreter")
        assert prise.arret_urgence_actif
        assert any(r.details.get("code") == "arret_non_confirme" for r in refus.value.raisons)
        await prise.deconnecter()

    lancer(go())
    with pytest.raises(ActionImpossible):
        LiaisonSDK._ok(None, "arrêt", arret=True)
    LiaisonSDK._ok(None, "geste")  # hors arrêt, None reste accepté (à vérifier par kit)


# ---------------------------------------------------------------- 15. un arrêt pendant le réarmement est renvoyé
def test_15_un_arret_pendant_le_rearmement_est_renvoye_au_robot():
    class KitRearmementLent(FauxKit):
        commence = threading.Event()

        def lever_arret(self):
            self.commence.set()
            time.sleep(0.2)  # le réarmement est en route…
            return super().lever_arret()  # … et efface l'arrêt arrivé entre-temps

    async def go():
        kit = KitRearmementLent()
        adaptateur, _ = faux_sdk(kit=kit)
        bus, gardien, prise = chaine(adaptateur)
        await prise.connecter()
        await prise.arret_urgence(raison="premier")
        rearmement = asyncio.create_task(prise.rearmer())
        while not kit.commence.is_set():
            await asyncio.sleep(0.005)
        await prise.arret_urgence(raison="pendant le réarmement")
        assert await rearmement is False
        await asyncio.sleep(0.1)
        assert kit.arret_actif, "l'arrêt a été renvoyé après le réarmement du kit"
        assert prise.arret_urgence_actif
        await prise.deconnecter()

    lancer(go())


# ---------------------------------------------------------------- 10, 11, 13, 14, 16, 17, 18 : les documents
def test_documents_mis_a_jour_apres_la_relecture():
    fiches = ICI / "fiches"
    g1 = (fiches / "unitree_g1.md").read_text(encoding="utf-8")
    assert "SetVelocity(0, 0, 0)" in g1 and "None" in g1 and "non confirmé" in g1  # 9
    assert "vitesse du geste : à vérifier par kit" in g1  # 10
    assert "ClearFault()" in (fiches / "flexiv_rizon.md").read_text(encoding="utf-8").split("rearmer")[1][:200]  # 11
    go2 = (fiches / "unitree_go2.md").read_text(encoding="utf-8")
    assert "Dance1" in go2 and "mise en garde" in go2.lower()  # 18
    texte = (ICI / "conformite_deux_temps.py").read_text(encoding="utf-8")
    assert "DU GARDIEN" in texte  # 13
    assert "2 m" in conformite.AVERTISSEMENT_COMPLET and "0,2 s" in conformite.AVERTISSEMENT_COMPLET  # 16
    assert "à vérifier par kit" in conformite.AVERTISSEMENT_COMPLET  # 10
    assert "PAS le liaison.py" in (ICI / "assistant.py").read_text(encoding="utf-8")  # 14
    guide = (RACINE / "BRANCHER_UN_ROBOT.md").read_text(encoding="utf-8")
    assert "3 lignes proposées" not in guide and "n'essaie PAS" in guide  # 14, 17
    samedi = (RACINE / "docs/projet/SAMEDI_MATIN.md").read_text(encoding="utf-8")
    assert "à partir de `briques/b01_prise/adaptateur.py`" not in samedi and "lancer.py brancher" in samedi  # 17
    notes = (ICI / "NOTES_POUR_COORDINATEUR.md").read_text(encoding="utf-8")
    assert "ne bloque pas" in notes  # décision à dire à Hiba



def test_9b_un_stop_pendant_un_trajet_refuse_par_le_kit_declenche_l_arret_d_urgence():
    """2e relecture du lot C : stop refusé par le kit (code d'erreur) pendant un déplacement → arrêt d'urgence, le robot
    ne bouge plus. Avant : erreur non attrapée, ni arrêt d'urgence ni alerte, robot encore en mouvement 2 s après."""
    from briques.b01_prise.raisons import ActionRefusee

    class KitStopRefuse(FauxKit):
        def stop(self):
            return 3  # le kit refuse l'arrêt normal (code d'erreur)

    async def go():
        adaptateur, kit = faux_sdk(kit=KitStopRefuse())
        bus, gardien, prise = chaine(adaptateur)
        await prise.connecter()
        await agir(gardien, prise, "se_deplacer", dx=1.0)
        await asyncio.sleep(0.3)
        try:
            await agir(gardien, prise, "arreter")
        except ActionRefusee:
            pass
        assert prise.arret_urgence_actif
        await asyncio.sleep(0.3)
        etat = await prise.etat()
        await prise.deconnecter()
        return etat

    etat = lancer(go())
    assert not etat.en_mouvement
