"""Brique 3 — le modèle vide (adaptateur, liaison, carte). Testé sur faux robot."""
from __future__ import annotations

import asyncio
import inspect
from pathlib import Path

import pytest

from aides_adaptateurs import CARTE_COMPLETE, KitSansEtiquette, agir, chaine, faux_sdk
from briques.b01_prise.actions import ActionDemandee
from briques.b01_prise.adaptateur import ActionImpossible, Adaptateur
from briques.b01_prise.carte import CarteIdentite
from briques.b01_prise.raisons import ActionRefusee
from briques.b03_adaptateurs.chemins.sdk.liaison_sdk import LiaisonSDK
from briques.b03_adaptateurs.modele_vide.adaptateur import AdaptateurModele
from briques.b03_adaptateurs.modele_vide.liaison import ABrancher, LiaisonVide
from conftest import lancer

MODELE = Path(__file__).resolve().parents[1] / "modele_vide"


def test_chaque_methode_du_modele_commun_est_ecrite_et_expliquee():
    communes = [n for n, f in vars(Adaptateur).items() if inspect.isfunction(f) and not n.startswith("_")]
    assert set(communes) >= {"carte", "connecter", "deconnecter", "demarrer", "suivre", "annuler", "arret_urgence",
                             "rearmer", "etat_robot", "battement"}
    for nom in communes:
        methode = vars(AdaptateurModele).get(nom)
        assert methode is not None, f"{nom} manque dans le modèle"
        doc = inspect.getdoc(methode) or ""
        assert "DOIT" in doc or "PASSE AVANT TOUT" in doc, f"{nom} : dire ce qu'elle doit faire"
    assert "REFUSE" in inspect.getdoc(AdaptateurModele.demarrer)
    assert "JAMAIS" in inspect.getdoc(AdaptateurModele.arret_urgence) and "PHYSIQUE" in inspect.getdoc(AdaptateurModele.arret_urgence)


def test_la_liaison_vide_est_a_brancher_partout():
    vide = LiaisonVide()
    for nom, f in vars(LiaisonVide).items():
        if not inspect.isfunction(f) or nom.startswith("_") or nom in ("tic", "infos_simulation"):
            continue
        nb = len(inspect.signature(f).parameters) - 1
        with pytest.raises(ABrancher) as e:
            f(vide, *(["x"] * nb))
        assert "À BRANCHER" in str(e.value) and "à vérifier dans la doc du fabricant" in str(e.value)
    assert vide.vrai_robot and vide.branchees == frozenset() and not vide.repere_du_monde


def test_la_carte_vide_est_valide_et_ne_promet_rien():
    texte = (MODELE / "carte.yaml").read_text(encoding="utf-8")
    carte = CarteIdentite.charger(MODELE / "carte.yaml")
    assert carte.capacites == ["arreter", "etat"] and carte.gestes == []
    assert all(v == 0 for v in carte.limites.model_dump().values()), "chiffres inconnus = 0 (le robot refuse de bouger)"
    assert texte.count("à vérifier") >= 5 and "lien" in texte


def test_un_adaptateur_vide_refuse_de_se_connecter_et_dit_quoi_brancher():
    async def go():
        a = AdaptateurModele(MODELE / "carte.yaml", LiaisonVide())
        with pytest.raises(ActionImpossible) as e:
            await a.connecter()
        assert e.value.code == "a_brancher" and "ouvrir" in str(e.value)
        await a.arret_urgence()  # jamais d'erreur, même jamais connecté
        assert a.carte().vrai_robot

    lancer(go())


def test_l_arret_d_urgence_ne_leve_jamais_d_erreur():
    class LiaisonQuiPlante(LiaisonSDK):
        def arret_urgence(self) -> None:
            raise RuntimeError("le kit plante")

    async def go():
        a, kit = faux_sdk()
        a._liaison = LiaisonQuiPlante(kit)
        await a.connecter()
        await a.arret_urgence()
        assert any("plante" in ligne for ligne in a.journal)
        with pytest.raises(ActionImpossible) as e:  # et le drapeau est quand même levé
            await a.demarrer(ActionDemandee(nom="regarder", parametres={"cible": "devant"}))
        assert e.value.code == "arret_urgence_actif"
        await a.deconnecter()

    lancer(go())


def test_vrai_ou_faux_vient_de_la_liaison_jamais_du_fichier():
    faux, _ = faux_sdk()  # la carte dit vrai_robot: true
    assert not faux.carte().vrai_robot and faux.carte().mention_test() == "testé sur faux robot"
    assert "(simulation)" in faux.carte().nom
    vrai = AdaptateurModele(CARTE_COMPLETE.model_copy(update={"vrai_robot": False}), LiaisonSDK(KitSansEtiquette()))
    assert vrai.carte().vrai_robot, "un kit qui ne se dit pas faux = un vrai robot"


def test_faux_robot_les_chiffres_a_verifier_prennent_ceux_de_la_simulation():
    carte = CarteIdentite.charger(MODELE / "carte.yaml").model_copy(update={"capacites": ["se_deplacer", "arreter", "etat"]})
    a, _ = faux_sdk(carte)
    assert a.carte().limites.vitesse_max_m_s > 0
    vrai = AdaptateurModele(carte, LiaisonSDK(KitSansEtiquette()))
    assert vrai.carte().limites.vitesse_max_m_s == 0, "vrai robot : jamais de chiffre inventé"


def test_vrai_robot_la_position_de_l_odometre_n_est_pas_donnee_au_gardien():
    async def go():
        a = AdaptateurModele(CARTE_COMPLETE, LiaisonSDK(KitSansEtiquette()))
        await a.connecter()
        etat = await a.etat_robot()
        assert etat.position == {} and etat.extra["odometrie"]["x"] == 1.0
        await a.deconnecter()
        f, _ = faux_sdk()
        await f.connecter()
        assert (await f.etat_robot()).position["x"] == 1.0
        await f.deconnecter()

    lancer(go())


def test_une_capacite_pas_branchee_est_refusee_avec_une_explication():
    class LiaisonPresqueVide(LiaisonSDK):
        branchees = frozenset({"arreter", "etat"})

    async def go():
        bus, gardien, prise = chaine(AdaptateurModele(CARTE_COMPLETE, LiaisonPresqueVide(KitSansEtiquette())))
        await prise.connecter()
        with pytest.raises(ActionRefusee) as e:
            await agir(gardien, prise, "regarder", cible="devant")
        assert e.value.raisons[0].code == "robot_refuse" and "pas encore branché" in e.value.raisons[0].details["message"]
        await prise.deconnecter()

    lancer(go())


def test_le_modele_ne_s_appelle_que_par_la_prise():
    texte = (MODELE / "adaptateur.py").read_text(encoding="utf-8")
    assert "Seule la prise" in texte and "défense en profondeur" in texte
    assert asyncio.iscoroutinefunction(AdaptateurModele.arret_urgence)
