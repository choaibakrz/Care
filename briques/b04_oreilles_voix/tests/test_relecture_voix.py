"""Un test par constat de la relecture de l'étape 2 (voix). Testé sur faux robot.

Les tests de conversation utilisent une écoute FACTICE (on choisit ce qu'elle « entend » et en combien de temps) :
on teste la logique (ordre, stop, écho, modes), pas la qualité de Whisper.
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

import numpy as np
import pytest

from briques.b01_prise.actions import ActionDemandee
from conftest import lancer

RACINE = Path(__file__).resolve().parents[3]


class EcouteFactice:
    """Rend les textes prévus, dans l'ordre des appels, après un délai choisi."""

    nom = "écoute factice"

    def __init__(self, reponses: list[tuple[str, str, float]]):
        self.reponses = list(reponses)  # (texte, langue, délai en s)

    def transcrire(self, son, langue=None, langue_probable=None):
        from briques.b04_oreilles_voix.ecoute import Transcription

        texte, lg, delai = self.reponses.pop(0)
        time.sleep(delai)
        return Transcription(texte=texte, langue=lg, langue_proba=1.0, confiance=0.9, duree_son_s=1.0,
                             duree_calcul_ms=delai * 1000, moteur=self.nom)


class VoixMuette:
    nom = "muette"

    def langues(self):
        return {"fr", "de", "zh", "en", "it"}

    def synthetiser(self, texte, langue, lent=False):
        return None


def _conv(fabrique_systeme, ecoute, **reglages):
    from briques.b04_oreilles_voix.conversation import Conversation
    from briques.b04_oreilles_voix.peripheriques import HautParleurFactice

    s = fabrique_systeme(acceleration=1.0)
    return s, Conversation(s, ecoute, VoixMuette(), HautParleurFactice(vitesse=10), {**s.reglages.get("voix", {}), **reglages})


def _enonce():
    from briques.b04_oreilles_voix.fin_de_parole import Enonce

    return Enonce(son=np.zeros(16000, dtype="float32"), debut_s=0, fin_parole_s=1, detection_s=1.6)


async def _en_mouvement(s) -> bool:
    return (await s.prise.etat()).en_mouvement


# ---------------------------------------------------------------- chaîne (texte)
def _chaine(fabrique_systeme, phrases, carte="humanoide", **kw):
    async def go():
        s = fabrique_systeme(carte, acceleration=1.0)
        await s.demarrer()
        res = []
        for p in phrases:
            if p == "ATTENDRE":
                await asyncio.sleep(0.4)
                continue
            if p == "ARRET_URGENCE":
                await s.prise.arret_urgence()
                await s.prise.rearmer()
                continue
            texte, langue, extra = (p + ({},))[:3] if len(p) == 2 else p
            res.append(await s.chaine.traiter(texte, langue, attendre_fin=False, **extra))
        await asyncio.sleep(0.3)
        mouvement = await _en_mouvement(s)
        await s.arreter()
        return s, res, mouvement

    return lancer(go())


def test_1_non_stop_pendant_une_confirmation_arrete_le_robot(fabrique_systeme):
    for stop in [("Non, stop !", "fr"), ("Nein, stopp!", "de")]:
        s, res, mouvement = _chaine(fabrique_systeme, [("Va à la cuisine", "fr"), ("Prends la bouteille", "fr"), stop])
        assert not mouvement and res[-1].action.nom == "arreter"


def test_2_stop_peu_sur_arrete_quand_meme_et_oui_peu_sur_ne_confirme_pas(fabrique_systeme):
    s, res, mouvement = _chaine(fabrique_systeme, [("Va à la cuisine", "fr"), ("Stop !", "fr", {"confiance_ecoute": 0.3})])
    assert not mouvement
    s, res, _ = _chaine(fabrique_systeme, [("Prends la bouteille", "fr", {"source": "micro"}),
                                           ("oui", "fr", {"source": "micro", "confiance_ecoute": 0.1}),
                                           ("oui", "fr", {"source": "micro", "confiance_ecoute": 0.9})], carte="bras")
    assert res[1].statut_action is None and res[1].decision.genre == "inconnu"
    assert res[2].verdict == "oui"  # la question avait été gardée ; le « oui » bien entendu confirme


@pytest.mark.parametrize("entre_deux,oui", [
    ([("ok", "fr", {"source": "clavier"})], None),  # autre source
    (["ARRET_URGENCE"], ("ok", "fr", {"source": "micro"})),  # effacée par l'arrêt d'urgence
    ([], ("pas d'accord", "fr", {"source": "micro"})),  # faux « oui »
    ([], ("I'm not sure", "en", {"source": "micro"})),
])
def test_7_8_la_confirmation_n_est_pas_volee(fabrique_systeme, entre_deux, oui):
    phrases = [("Prends la bouteille", "fr", {"source": "micro"})] + entre_deux + ([oui] if oui else [])
    s, res, _ = _chaine(fabrique_systeme, phrases, carte="bras")
    assert not any(e.type == "action_demarree" and e.donnees["action"]["nom"] == "saisir" for e in s.bus.historique)


def test_confirmation_perimee(fabrique_systeme):
    async def go():
        s = fabrique_systeme("bras")
        s.chaine.delai_confirmation_s = 0.2
        await s.demarrer()
        await s.chaine.traiter("Prends la bouteille", "fr")
        await asyncio.sleep(0.3)
        r = await s.chaine.traiter("oui", "fr")
        await s.arreter()
        return r

    assert lancer(go()).statut_action is None


def test_5_les_questions_du_robot_ne_contiennent_aucun_oui():
    from commun.phrases import dire, oui_ou_non

    for lg in ["fr", "de", "it", "en", "zh"]:
        for annonce in ["", dire("annonce.saisir", lg, objet="x"), dire("annonce.se_deplacer", lg, lieu="x")]:
            assert oui_ou_non(dire("confirmer", lg, annonce=annonce), lg) is not True, lg


# ---------------------------------------------------------------- conversation (écoute factice)
def test_3_9_stop_passe_dans_tous_les_modes(fabrique_systeme):
    for mode in ["mot_d_appel", "bouton"]:
        async def go():
            s, c = _conv(fabrique_systeme, EcouteFactice([("Va à la cuisine", "fr", 0.0), ("Stop !", "fr", 0.0)]),
                         declenchement=mode, fenetre_apres_appel_s=0)
            await s.demarrer()
            _, ticket = await s.gardien.verifier(ActionDemandee(nom="se_deplacer", parametres={"lieu": "cuisine"}),
                                                 s.prise.carte())
            await s.prise.executer(ticket)
            c._lancer(c._traiter(_enonce(), time.monotonic()))  # « Va à la cuisine » sans mot d'appel / sans bouton
            await asyncio.sleep(0.2)
            c._lancer(c._traiter(_enonce(), time.monotonic()))  # « Stop ! »
            await asyncio.sleep(0.5)
            m = await _en_mouvement(s)
            entendues = [e.donnees["texte"] for e in s.bus.historique if e.type == "parole_entendue"]
            c.fermer()
            await s.arreter()
            return m, entendues

        mouvement, entendues = lancer(go())
        assert not mouvement, mode
        assert entendues == ["Stop !"], (mode, entendues)  # « Va à la cuisine » (non adressé) est ignoré


def test_6_un_stop_annule_une_phrase_plus_ancienne_encore_en_cours(fabrique_systeme):
    async def go():
        s, c = _conv(fabrique_systeme, EcouteFactice([("Va à la cuisine", "fr", 1.0), ("Stop !", "fr", 0.1)]))
        await s.demarrer()
        c._lancer(c._traiter(_enonce(), time.monotonic()))
        await asyncio.sleep(0.05)
        c._lancer(c._traiter(_enonce(), time.monotonic()))
        await asyncio.sleep(1.6)
        m = await _en_mouvement(s)
        c.fermer()
        await s.arreter()
        return s, m

    s, mouvement = lancer(go())
    assert not mouvement
    assert not any(e.type == "action_demarree" and e.donnees["action"]["nom"] == "se_deplacer" for e in s.bus.historique)


def test_4_bouton_jamais_relache_se_relache_tout_seul(fabrique_systeme):
    async def go():
        s, c = _conv(fabrique_systeme, EcouteFactice([("Regarde la table", "fr", 0.0)]), duree_max_bouton_s=0.2)
        await s.demarrer()
        c.appuyer()
        for _ in range(20):
            await c.recevoir(np.zeros(512, dtype="float32"))
            await asyncio.sleep(0.02)
        await asyncio.sleep(0.5)
        r = (c._bouton, [e.donnees["texte"] for e in s.bus.historique if e.type == "parole_entendue"])
        c.fermer()
        await s.arreter()
        return r

    appuye, entendues = lancer(go())
    assert appuye is False and entendues == ["Regarde la table"]


def test_5_le_robot_ignore_l_echo_de_sa_propre_voix(fabrique_systeme):
    async def go():
        s, c = _conv(fabrique_systeme, EcouteFactice([("Je prends : bouteille. Vous confirmez ?", "fr", 0.0)]))
        await s.demarrer()
        c._dits.append(("jeprendsbouteillevousconfirmez", time.monotonic()))
        c._lancer(c._traiter(_enonce(), time.monotonic()))
        await asyncio.sleep(0.3)
        r = [e for e in s.bus.historique if e.type == "parole_entendue"]
        c.fermer()
        await s.arreter()
        return r

    assert lancer(go()) == []


def test_10_langue_gardee_ne_force_pas_une_autre_langue():
    if not (RACINE / "modeles/whisper-base-fw").exists():
        pytest.skip("whisper base absent")
    from briques.b04_oreilles_voix.audio import lire
    from briques.b04_oreilles_voix.branchements.ecoute_faster_whisper import EcouteFasterWhisper

    son = lire(RACINE / "donnees_voix/synthetique_zh/aller_cuisine.wav")
    t = EcouteFasterWhisper("base").transcrire(son, langue_probable="de")
    assert t.langue == "zh" and "厨房" in t.texte


def test_bouton_je_parle_par_l_ecran(fabrique_systeme):
    from fastapi.testclient import TestClient

    from briques.b13_ecran.serveur import creer_app

    class Conv:
        appuis = []

        def appuyer(self):
            self.appuis.append(True)

        def relacher(self):
            self.appuis.append(False)

    s = fabrique_systeme()
    s.reglages["ecran"]["code_equipe"] = "code-de-test"
    c = Conv()
    with TestClient(creer_app(s, conversation=c)) as client:
        assert client.post("/api/je_parle", json={"appui": True}).status_code == 403
        h = {"X-Code-Equipe": "code-de-test"}
        client.post("/api/je_parle", json={"appui": True}, headers=h)
        client.post("/api/je_parle", json={"appui": False}, headers=h)
        assert client.get("/api/micro").json()["micro"] is True
    assert c.appuis == [True, False]
