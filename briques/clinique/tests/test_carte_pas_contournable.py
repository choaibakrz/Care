"""La clinique en boîte — H11 : la carte de rôle ne se contourne pas (relecture de la tranche 3, point 2).

Avant : avec la carte Accueil chez le gardien, le gardien disait « oui » à `se_deplacer cuisine` (un lieu de l'ossature,
pas du plan de la clinique) et à `saisir` (les actions n'étaient contrôlées que par le coursier). Un ordre qui ne passait
pas par le coursier échappait donc à la carte.
« Fini » veut dire, en demandant DIRECTEMENT au gardien (sans le coursier) :
- un lieu que la carte ne permet pas est refusé, qu'il soit du plan de la clinique ou de l'ossature ;
- une carte qui ne permet pas de saisir : le gardien refuse de saisir chaque objet du monde ;
- une autre action hors carte (montrer, rejouer un geste) : le gardien ne dit jamais « oui » tout seul (il demande un humain) ;
- ce que la carte permet marche comme avant, et les règles de l'ossature sont toutes là.
Testé sur faux robot. Aucun vrai robot.
"""
from __future__ import annotations

import pytest

from briques.b07_gardien.regles import charger_regles
from briques.clinique import cartes, cartes_gardien
from briques.clinique.coursier import monde_de_la_clinique
from briques.clinique.tests.test_cartes_gardien import _jouer

LIEUX_DE_L_OSSATURE = [l.id for l in monde_de_la_clinique(rez_de_chaussee=True).lieux
                       if l.id not in cartes_gardien.lieux_du_plan()]


def test_le_monde_a_bien_des_lieux_qui_ne_sont_pas_du_plan_de_la_clinique():
    assert len(LIEUX_DE_L_OSSATURE) >= 3, LIEUX_DE_L_OSSATURE


@pytest.mark.parametrize("nom", ["Accueil", "Étage", "Thérapie", "Visite", "Nuit"])
def test_chaque_carte_interdit_tous_les_lieux_qu_elle_ne_nomme_pas_et_le_vrai_gardien_accepte_le_fichier(tmp_path, nom):
    monde, carte = monde_de_la_clinique(rez_de_chaussee=True), cartes.charger_cartes()[nom]
    regles = charger_regles(cartes_gardien.ecrire_les_regles(carte, monde, tmp_path / "regles.yaml"), monde)
    interdits = {r.valeurs["lieu"] for r in regles.regles if r.sorte == "zone_interdite" and r.id.startswith("carte_")}
    assert interdits == {l.id for l in monde.lieux} - set(carte.lieux_permis)
    for garde in ("vitesse_max", "force_max", "distance_personnes", "escalier", "rester_dans_la_halle", "valise"):
        assert regles.regle(garde) is not None  # la carte ne retire rien
    sans_main = "saisir" not in carte.actions_permises
    touches_interdits = {o for r in regles.regles if r.id.startswith("carte_objet_") for o in r.valeurs["objets"]}
    assert touches_interdits == ({o.id for o in monde.objets} if sans_main else set())


@pytest.mark.parametrize("carte", ["Accueil", "Visite"])
def test_demande_directe_au_gardien_les_lieux_de_l_ossature_et_saisir_sont_refuses(tmp_path, carte):
    async def scene(banc):
        vus = {lieu: (await banc.demander("se_deplacer", lieu=lieu))[0] for lieu in LIEUX_DE_L_OSSATURE + ["Chambre 12"]}
        objets = {o.id: (await banc.demander("saisir", objet=o.id))[0] for o in banc.systeme.monde.objets}
        return vus, objets, (await banc.demander("se_deplacer", lieu="Accueil"))[0]

    vus, objets, permis = _jouer(tmp_path, carte, scene)
    assert all(v.verdict == "non" for v in vus.values()), {l: v.verdict for l, v in vus.items()}
    assert objets and all(v.verdict == "non" for v in objets.values()), {o: v.verdict for o, v in objets.items()}
    assert permis.verdict == "oui"


def test_demande_directe_au_gardien_la_carte_etage_refuse_les_lieux_de_l_ossature_mais_garde_ses_gestes(tmp_path):
    async def scene(banc):
        vus = {lieu: (await banc.demander("se_deplacer", lieu=lieu))[0].verdict for lieu in LIEUX_DE_L_OSSATURE + ["Hall"]}
        return vus, (await banc.demander("se_deplacer", lieu="Réserve"))[0].verdict

    vus, reserve = _jouer(tmp_path, "Étage", scene)
    assert set(vus.values()) == {"non"}, vus
    assert reserve == "oui"


def test_demande_directe_au_gardien_une_action_hors_carte_n_a_jamais_un_oui_tout_seul(tmp_path):
    """La carte Nuit ne permet pas « montrer » ; aucune carte ne permet « rejouer_geste »."""
    async def scene(banc):
        return [(await banc.demander(nom, **p))[0].verdict for nom, p in (("montrer", {"cible": "Chambre 12"}),
                                                                           ("rejouer_geste", {"geste": "saluer"}))]

    verdicts = _jouer(tmp_path, "Nuit", scene)
    assert "oui" not in verdicts, verdicts
