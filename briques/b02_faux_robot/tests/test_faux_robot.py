"""Brique 2 — le faux robot. Testé sur faux robot (évidemment)."""
from __future__ import annotations

import asyncio

import pytest

from briques.b01_prise.actions import ActionDemandee
from briques.b01_prise.conformite import verifier_conformite
from briques.b01_prise.raisons import ActionRefusee
from briques.b02_faux_robot.faux_robot import FauxRobot, cartes_disponibles
from conftest import lancer, robot


def test_trois_cartes_d_exemple():
    assert set(cartes_disponibles()) >= {"humanoide", "chien", "bras"}


@pytest.mark.parametrize("genre", ["humanoide", "chien", "bras"])
def test_le_faux_robot_passe_le_test_de_conformite(genre):
    rapport = lancer(verifier_conformite(lambda: FauxRobot(genre, acceleration=20)))
    assert rapport.reussi, rapport.texte()
    assert rapport.mention == "testé sur faux robot"


def _agir(s, nom, **p):
    async def go():
        _, ticket = await s.gardien.verifier(ActionDemandee(nom=nom, parametres=p), s.prise.carte())
        suivi = await s.prise.executer(ticket)
        return await s.prise.attendre(suivi.id, 10)

    return go()


def test_panne_lenteur_ralentit(fabrique_systeme):
    async def scenario():
        s = fabrique_systeme(acceleration=5)
        await s.demarrer()
        t0 = asyncio.get_running_loop().time()
        await _agir(s, "se_deplacer", dx=0.5)
        normal = asyncio.get_running_loop().time() - t0
        s.simulation.provoquer_panne("lenteur")
        t0 = asyncio.get_running_loop().time()
        await _agir(s, "se_deplacer", dx=0.5)
        lent = asyncio.get_running_loop().time() - t0
        assert lent > 2.5 * normal
        await s.arreter()

    lancer(scenario())


def test_panne_refus(fabrique_systeme):
    async def scenario():
        s = fabrique_systeme()
        await s.demarrer()
        s.simulation.provoquer_panne("refus")
        with pytest.raises(ActionRefusee) as e:
            await _agir(s, "regarder", cible="devant")
        assert e.value.raisons[0].code == "robot_refuse"
        s.simulation.reparer()
        fin = await _agir(s, "regarder", cible="devant")
        assert fin.statut == "reussie"
        await s.arreter()

    lancer(scenario())


def test_perte_de_liaison_le_chien_de_garde_arrete_le_robot(fabrique_systeme):
    async def scenario():
        s = fabrique_systeme(acceleration=1.0)
        await s.demarrer()
        _, ticket = await s.gardien.verifier(ActionDemandee(nom="se_deplacer", parametres={"lieu": "cuisine"}), s.prise.carte())
        await s.prise.executer(ticket)
        await asyncio.sleep(0.3)
        s.simulation.provoquer_panne("perte_liaison")
        await asyncio.sleep(1.5)
        assert not any(not t.done() for t in robot(s)._taches.values()), "le robot doit s'être arrêté seul"
        assert any("chien de garde" in e for e in robot(s).erreurs)
        assert any(e.type == "panne" and e.donnees.get("quoi") == "liaison_perdue" for e in s.bus.historique)
        etat = await s.prise.etat()
        assert etat.liaison_ok is False
        # Liaison coupée : l'ordre d'arrêt d'urgence n'arrive pas (comme sur un vrai robot). La prise le note,
        # et signale que l'arrêt n'est pas confirmé. Le robot est déjà arrêté par son propre chien de garde.
        await s.prise.arret_urgence()
        arret = [e for e in s.bus.historique if e.type == "arret_urgence"][-1]
        assert arret.donnees["erreur"] and "LiaisonPerdue" in arret.donnees["erreur"]
        await asyncio.sleep(0.7)
        assert any(e.type == "panne" and e.donnees.get("quoi") == "arret_urgence_non_confirme" for e in s.bus.historique)
        await s.arreter()

    lancer(scenario())


def test_trop_lourd_et_hors_de_portee(fabrique_systeme):
    async def scenario():
        s = fabrique_systeme("bras")
        await s.demarrer()
        assert (await _agir(s, "saisir", objet="bouteille")).statut == "reussie"
        assert (await _agir(s, "poser", lieu="ici")).statut == "reussie"
        # Étape 4 : la valise (12 kg, interdite) est refusée AVANT, par le gardien ; le faux robot ne la voit plus.
        d, ticket = await s.gardien.verifier(ActionDemandee(nom="saisir", parametres={"objet": "valise"}), s.prise.carte())
        assert ticket is None and {"trop_lourd", "objet_interdit"} <= {r.code for r in d.raisons}
        loin = await _agir(s, "saisir", objet="objet_test")  # léger, mais loin du bras : le faux robot refuse lui-même
        assert loin.statut == "echouee" and loin.code_erreur == "trop_loin"
        await s.arreter()

    lancer(scenario())
