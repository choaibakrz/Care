"""Brique 1 — la prise universelle. Testé sur faux robot."""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from briques.b01_prise.actions import ACTIONS, ActionDemandee
from briques.b01_prise.carte import CarteIdentite
from briques.b01_prise.raisons import ActionRefusee
from briques.b01_prise.ticket import Guichet, Ticket
from briques.b01_prise.validation import valider
from briques.b02_faux_robot.faux_robot import DOSSIER_CARTES
from conftest import lancer

BRAS = CarteIdentite.charger(DOSSIER_CARTES / "bras.yaml")
HUMANOIDE = CarteIdentite.charger(DOSSIER_CARTES / "humanoide.yaml")


def test_la_liste_des_actions_est_ecrite_dans_prise_md():
    texte = (Path(__file__).parents[1] / "PRISE.md").read_text(encoding="utf-8")
    dans_le_fichier = set(re.findall(r"^\|\s*`(\w+)`", texte, flags=re.M))
    assert dans_le_fichier == set(ACTIONS), "PRISE.md et actions.py doivent lister les mêmes actions"


@pytest.mark.parametrize("action", [a for a in ACTIONS if a not in BRAS.capacites])
def test_refuse_toute_action_absente_de_la_carte(action):
    raisons = valider(ActionDemandee(nom=action, parametres=ACTIONS[action].exemple), BRAS)
    assert [r.code for r in raisons] == ["absente_de_la_carte"]


def test_refuse_une_action_inconnue():
    assert valider(ActionDemandee(nom="voler"), HUMANOIDE)[0].code == "action_inconnue"


def test_refuse_au_dessus_des_limites_de_la_carte():
    r = valider(ActionDemandee(nom="se_deplacer", parametres={"lieu": "cuisine", "vitesse": 9.0}), HUMANOIDE,
                plafonds={"vitesse": 100})
    assert r[0].code == "au_dessus_de_la_limite" and r[0].details["limite"] == HUMANOIDE.limites.vitesse_max_m_s


def test_parametres_manquants_inconnus_et_mauvais_type():
    assert valider(ActionDemandee(nom="saisir"), HUMANOIDE)[0].code == "parametre_manquant"
    assert valider(ActionDemandee(nom="se_deplacer"), HUMANOIDE)[0].code == "parametre_manquant"
    assert valider(ActionDemandee(nom="regarder", parametres={"cible": "x", "laser": 1}), HUMANOIDE)[0].code == "parametre_inconnu"
    assert valider(ActionDemandee(nom="se_deplacer", parametres={"dx": "loin"}), HUMANOIDE)[0].code == "parametre_mauvais_type"


def test_geste_non_enregistre_refuse():
    assert valider(ActionDemandee(nom="rejouer_geste", parametres={"nom": "salto"}), HUMANOIDE)[0].code == "geste_inconnu"


def test_carte_sans_arret_est_invalide():
    with pytest.raises(ValueError):
        CarteIdentite(id="x", nom="x", genre="autre", capacites=["regarder"])


def test_ticket_unique_signe_lie_au_robot_et_non_falsifiable():
    g = Guichet()
    regarder = ActionDemandee(nom="regarder", parametres={"cible": "devant"})
    t = g.emettre(regarder, "r1")
    assert g.verifier(t, "r1") is None
    assert g.verifier(t, "r1") == "ticket_invalide"  # déjà utilisé
    faux = Ticket(action=ActionDemandee(nom="se_deplacer", parametres={"dx": 5}), robot="r1", numero="x",
                  emis_a=t.emis_a, signature=t.signature)
    assert g.verifier(faux, "r1") == "ticket_invalide"
    assert g.verifier(Guichet().emettre(regarder, "r1"), "r1") == "ticket_invalide"  # autre guichet
    assert g.verifier(g.emettre(regarder, "r1"), "r2") == "ticket_invalide"  # autre robot
    assert g.verifier("pas un ticket", "r1") == "sans_ticket"

    class Deguise(Ticket):
        pass

    t2 = g.emettre(regarder, "r1")
    assert g.verifier(Deguise(t2.action, t2.robot, t2.numero, t2.emis_a, t2.signature), "r1") == "sans_ticket"


def test_prise_refuse_sans_ticket_et_note_le_refus(fabrique_systeme):
    async def scenario():
        s = fabrique_systeme()
        await s.demarrer()
        with pytest.raises(ActionRefusee) as e:
            await s.prise.executer(ActionDemandee(nom="se_deplacer", parametres={"dx": 1}))  # type: ignore[arg-type]
        assert e.value.raisons[0].code == "sans_ticket"
        assert any(ev.type == "action_refusee" for ev in s.bus.historique)
        await s.arreter()

    lancer(scenario())


def test_prise_revalide_meme_avec_un_ticket(fabrique_systeme):
    """Même si un ticket était émis par erreur pour une action hors carte, la prise refuse."""

    async def scenario():
        s = fabrique_systeme("bras")
        await s.demarrer()
        ticket = s.gardien._Gardien__guichet.emettre(ActionDemandee(nom="se_deplacer", parametres={"dx": 1}), s.prise.robot)
        with pytest.raises(ActionRefusee) as e:
            await s.prise.executer(ticket)
        assert e.value.raisons[0].code == "absente_de_la_carte"
        await s.arreter()

    lancer(scenario())


def test_action_longue_suivie_et_annulee(fabrique_systeme):
    async def scenario():
        s = fabrique_systeme(acceleration=1.0)
        await s.demarrer()
        _, ticket = await s.gardien.verifier(ActionDemandee(nom="se_deplacer", parametres={"lieu": "cuisine"}), s.prise.carte())
        suivi = await s.prise.executer(ticket)
        await asyncio.sleep(0.5)
        en_cours = await s.prise.suivre(suivi.id)
        assert en_cours.statut == "en_cours" and 0 < en_cours.progression < 1
        await s.prise.annuler(suivi.id)
        fin = await s.prise.attendre(suivi.id, 3)
        assert fin.statut == "annulee"
        assert any(e.type == "action_progression" for e in s.bus.historique)
        await s.arreter()

    lancer(scenario())


def test_arret_urgence_toujours_permis_et_bloque_la_suite(fabrique_systeme):
    async def scenario():
        s = fabrique_systeme(acceleration=1.0)
        await s.demarrer()
        _, ticket = await s.gardien.verifier(ActionDemandee(nom="se_deplacer", parametres={"lieu": "cuisine"}), s.prise.carte())
        suivi = await s.prise.executer(ticket)
        await asyncio.sleep(0.3)
        await s.prise.arret_urgence()
        fin = await s.prise.attendre(suivi.id, 3)
        assert fin.statut == "annulee" and not (await s.prise.etat()).en_mouvement
        _, ticket = await s.gardien.verifier(ActionDemandee(nom="regarder", parametres={"cible": "devant"}), s.prise.carte())
        with pytest.raises(ActionRefusee) as e:
            await s.prise.executer(ticket)
        assert e.value.raisons[0].code == "arret_urgence_actif"
        await s.prise.rearmer()
        _, ticket = await s.gardien.verifier(ActionDemandee(nom="regarder", parametres={"cible": "devant"}), s.prise.carte())
        await s.prise.executer(ticket)
        await s.arreter()

    lancer(scenario())
