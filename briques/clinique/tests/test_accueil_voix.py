"""La clinique en boîte — T20, l'accueil à la voix (cahier 5.9).

« Fini » veut dire :
- l'arrivée dite en italien donne la réponse dite en italien ;
- le chemin s'affiche ;
- le plan B « voix en panne » passe à l'écran.
La boucle est vraie : un son → l'écoute → la phrase → l'accueil → la réponse → la voix du Mac. Ces essais-là sont sautés
sans la voix du Mac ou sans le modèle d'écoute. DIRE VRAI : l'arrivée est dite par une voix de synthèse du Mac, pas par
une personne ; il n'y a pas de micro en direct.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from briques.clinique import accueil_voix, ecoute
from conftest import lancer

VOIX_LA, RAISON_VOIX = accueil_voix.voix_disponible()
ECOUTE_LA, RAISON_ECOUTE = ecoute.disponible()
avec_la_voix = pytest.mark.skipif(not (VOIX_LA and ECOUTE_LA), reason=f"voix ou écoute indisponible : {RAISON_VOIX} {RAISON_ECOUTE}")


@pytest.fixture(scope="module")
def boucle(tmp_path_factory):
    """L'arrivée du scénario, dite par la voix du Mac, puis toute la boucle : une seule fois."""
    return accueil_voix.essai(tmp_path_factory.mktemp("sons"))


@avec_la_voix
def test_l_arrivee_dite_en_italien_donne_la_reponse_dite_en_italien(boucle):
    assert boucle["plan_b"] is None
    assert ecoute.taux_d_erreur_mots(boucle["entendu"]["texte"], "Buongiorno, sono Giulia B.") == 0.0
    reponse = boucle["reponse"]
    assert reponse["cas"] == "arrivée" and reponse["langue"] == "it"
    assert "camera è la numero 12" in reponse["dit"] and "Non la accompagno" in reponse["dit"]
    son = Path(boucle["son_de_la_reponse"])
    assert son.exists() and son.stat().st_size > 20_000 and boucle["voix"] == "voix du Mac (synthèse)"
    # on réécoute ce que la voix a dit : c'est bien de l'italien, et il y a la chambre
    redit = ecoute.ecouter(son, "it")["texte"].lower()
    assert "camera" in redit and ("12" in redit or "dodici" in redit), redit


@avec_la_voix
def test_le_chemin_s_affiche_et_l_etage_est_prevenu(boucle):
    chemin = [pas["lieu"] for pas in boucle["reponse"]["chemin"]]
    assert chemin[0] == "Hall" and chemin[-1] == "Chambre 12"
    assert len(boucle["clinique"].carnet.lignes("message pour l'étage")) == 1


@avec_la_voix
def test_la_commande_d_essai_dit_que_la_voix_est_de_synthese(capsys, monkeypatch, boucle):
    monkeypatch.setattr(accueil_voix, "essai", lambda haut_parleur=False: boucle)  # la boucle déjà jouée
    assert accueil_voix.main(["--essai"]) == 0
    sortie = capsys.readouterr().out
    for mot in ("VOIX DE SYNTHÈSE du Mac, pas par une personne", "Buongiorno, sono Giulia B.", "camera", "Hall → ",
                "Chambre 12", "ni micro en direct ni robot"):
        assert mot in sortie, mot


# ---------------------------------------------------------------------------------------------- le plan B (sans son)
def _accueil():
    return accueil_voix._accueil_neuf()


def test_plan_b_si_l_ecoute_ne_marche_pas_on_passe_a_l_ecran(tmp_path):
    def ecoute_cassee(son, langue):
        raise ecoute.EcouteImpossible("le modèle d'écoute manque")

    clinique = _accueil()
    r = accueil_voix.accueillir(clinique.accueil, tmp_path / "x.wav", tmp_path, ecouter=ecoute_cassee)
    assert r["reponse"] is None and r["plan_b"]["moyen"] == "écran" and r["plan_b"]["ou"] == "/clinique/hall"
    assert "on passe à l'écran" in r["plan_b"]["dit"] and "modèle" in r["plan_b"]["raison"]
    assert clinique.carnet.lignes() == []  # rien n'a été répondu ni transmis sur une phrase pas entendue


@pytest.mark.parametrize("texte", ["", "   ", "…", "[BLANK_AUDIO]".replace("BLANK_AUDIO", "  ")])
def test_plan_b_si_rien_n_est_compris(tmp_path, texte):
    clinique = _accueil()
    r = accueil_voix.accueillir(clinique.accueil, tmp_path / "x.wav", tmp_path,
                                ecouter=lambda son, langue: {"texte": texte, "outil": "essai", "duree_s": 0})
    assert r["reponse"] is None and r["plan_b"]["moyen"] == "écran" and clinique.carnet.lignes() == []


def test_plan_b_micro_en_panne_on_n_ecoute_meme_pas(tmp_path):
    clinique = _accueil()
    lancer(clinique.pannes.provoquer("micro_bruit"))
    appels = []
    r = accueil_voix.accueillir(clinique.accueil, tmp_path / "x.wav", tmp_path, pannes=clinique.pannes,
                                ecouter=lambda son, langue: appels.append(1) or {"texte": "Buongiorno, sono Giulia B."})
    assert appels == [] and r["plan_b"]["moyen"] == "écran" and "micro" in r["plan_b"]["raison"]


def test_plan_b_si_la_voix_ne_marche_pas_la_reponse_s_affiche(tmp_path):
    def voix_cassee(texte, langue, sortie, haut_parleur=False):
        raise accueil_voix.VoixImpossible("aucune voix")

    clinique = _accueil()
    r = accueil_voix.accueillir(clinique.accueil, tmp_path / "x.wav", tmp_path, parler=voix_cassee,
                                ecouter=lambda son, langue: {"texte": "Buongiorno, sono Giulia B.", "outil": "essai", "duree_s": 0})
    assert r["reponse"]["cas"] == "arrivée" and "camera" in r["reponse"]["dit"]  # la réponse est là, pour l'écran
    assert r["son_de_la_reponse"] is None and "la réponse s'affiche" in r["plan_b"]["dit"]


def test_a_la_voix_les_memes_refus_qu_a_l_ecran(tmp_path):
    """Une question de santé dite dans le hall : refusée comme la phrase tapée, et un humain est appelé."""
    clinique = _accueil()
    dits = []
    r = accueil_voix.accueillir(clinique.accueil, tmp_path / "x.wav", tmp_path,
                                parler=lambda texte, langue, sortie, haut_parleur=False: dits.append(texte) or Path(sortie),
                                ecouter=lambda son, langue: {"texte": "Pourquoi Madame B. est-elle ici ?", "outil": "essai", "duree_s": 0})
    assert r["reponse"]["cas"] == "santé" and "Je transmets à l'équipe" in dits[0]
    assert "12" not in dits[0] and "Giulia" not in dits[0]


def test_la_commande_est_dans_lancer_et_sans_son_elle_le_dit(capsys):
    assert '"accueil-voix"' in (Path(__file__).resolve().parents[3] / "lancer.py").read_text(encoding="utf-8")
    assert accueil_voix.main([]) == 2 and "--essai" in capsys.readouterr().out
