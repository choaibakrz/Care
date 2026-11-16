"""La clinique en boîte — K07b : les quatre boutons de l'invité dans six ordres, et la taille du texte (avenant 2, K07).

« Fini quand : une commande essaie les quatre boutons dans six ordres différents, avec une remise à zéro entre chaque,
et le scénario se rejoue ensuite sans erreur ; la remise à zéro prend moins de dix secondes ; les actions de l'invité
portent la marque INVITÉ ; la vérification de la taille du texte passe. »
« Une vérification mesure la plus petite taille de texte de ces deux écrans (Invité, Patient), et la compare à un seuil
écrit dans les réglages. » La mesure se fait dans Chrome sans fenêtre (la taille que le navigateur calcule vraiment).
Faux robot et robots simulés. Aucun vrai robot.
"""
from __future__ import annotations

import itertools

import pytest

from briques.clinique import invite_essai, lisibilite
from briques.clinique.tests.test_clic_dans_le_navigateur import CHROME, chrome, serveur  # noqa: F401


# ------------------------------------------------------------------------------------------------ les six ordres
def test_les_six_ordres_sont_differents_et_contiennent_chacun_les_quatre_boutons():
    ordres = invite_essai.ORDRES
    assert len(ordres) == 6 and len(set(ordres)) == 6
    for ordre in ordres:
        assert sorted(ordre) == sorted(invite_essai.BOUTONS) and len(ordre) == 4
    assert set(ordres) <= set(itertools.permutations(invite_essai.BOUTONS))


def test_la_commande_joue_les_six_ordres_remet_a_zero_et_rejoue_le_scenario():
    lignes: list[str] = []
    bilan = invite_essai.essayer(ecrire=lignes.append, avec_lisibilite=False)
    texte = "\n".join(lignes)
    assert bilan["ordres_reussis"] == 6, texte
    assert len(bilan["remises"]) == 6 and max(bilan["remises"]) < 10, bilan["remises"]
    assert bilan["actions_invite"] == 6 * 5 and bilan["sans_marque"] == 0  # 4 boutons + la remise à zéro, six fois
    assert bilan["scenario"] == "RÉUSSIE" and "RÉPÉTITION : RÉUSSIE" in texte
    assert bilan["etat_propre"] is True  # après la dernière remise : aucune panne, faux logiciel vide
    assert "INVITÉ — SIX ORDRES : RÉUSSI" in texte and "FAUX ROBOT" in texte


def test_si_la_remise_a_zero_ne_finit_plus_les_pannes_la_commande_dit_rate(monkeypatch):
    """Une pièce cassée exprès : « finir une panne » ne fait plus rien. La commande doit dire RATÉ, jamais RÉUSSI."""
    from briques.clinique import pannes

    async def ne_finit_rien(self, ident, attendre=False):
        return {"reparties": [], "en_attente": [], "dit": ""}

    monkeypatch.setattr(pannes.Pannes, "finir", ne_finit_rien)
    lignes: list[str] = []
    bilan = invite_essai.essayer(ecrire=lignes.append, avec_lisibilite=False)
    texte = "\n".join(lignes)
    assert bilan["ordres_reussis"] < 6 and "INVITÉ — SIX ORDRES : RATÉ" in texte and "RÉUSSI" not in texte.splitlines()[-1]


# ------------------------------------------------------------------------------------------------ la taille du texte
def test_le_seuil_est_ecrit_dans_les_reglages():
    seuil = lisibilite.seuil_px()
    assert isinstance(seuil, (int, float)) and seuil >= 16
    from commun.systeme import REGLAGES_EXEMPLE, charger_reglages

    assert charger_reglages(REGLAGES_EXEMPLE)["ecran"]["taille_texte_min_px"] == seuil or "taille_texte_min_px" in (
        charger_reglages().get("ecran") or {})


@pytest.mark.skipif(not CHROME.exists(), reason="Chrome n'est pas sur cet ordinateur : la taille du texte n'est pas mesurée")
@pytest.mark.parametrize("chemin", lisibilite.ECRANS.values())
def test_la_plus_petite_taille_de_texte_des_ecrans_invite_et_patient_atteint_le_seuil(serveur, chrome, chemin):  # noqa: F811
    import asyncio

    mesure = asyncio.run(lisibilite.mesurer(chrome, serveur + chemin))
    assert mesure["textes"] > 10, mesure  # la page a bien été lue
    assert mesure["plus_petite_px"] >= lisibilite.seuil_px(), mesure


@pytest.mark.skipif(not CHROME.exists(), reason="Chrome n'est pas sur cet ordinateur")
def test_la_mesure_voit_vraiment_un_petit_texte(serveur, chrome):  # noqa: F811
    """Contrôle de la mesure elle-même : une page ordinaire (le journal des accès) a des textes plus petits que le seuil."""
    import asyncio

    mesure = asyncio.run(lisibilite.mesurer(chrome, serveur + "/clinique"))
    assert mesure["plus_petite_px"] < lisibilite.seuil_px(), mesure


def test_les_autres_ecrans_ne_changent_pas_de_style():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from briques.clinique.ecrans import brancher_ecrans

    app = FastAPI()
    brancher_ecrans(app)
    client = TestClient(app)
    assert "class='lisible'" in client.get("/clinique/patient?badge=patient-p01").text
    assert "class='lisible'" in client.get("/clinique/invite").text
    for chemin in ("/clinique/soignant?badge=soignant-etage-2", "/clinique/medecin?badge=medecin-exemple", "/clinique"):
        assert "class='lisible'" not in client.get(chemin).text, chemin
