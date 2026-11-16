"""La clinique en boîte — T22a, les cartes de rôle : les fichiers, le monde simulé, la voix (cahier 5.10 et 6.6).

T22 est coupée en deux. Ici, T22a. « Fini » veut dire :
- cinq cartes lisibles, une par rôle : Accueil, Étage, Thérapie, Visite, Nuit ; chacune dit les lieux permis, la vitesse
  la plus haute, le volume de la voix, les actions permises ; une carte mal écrite est refusée, en clair ;
- dans le monde simulé, le robot à la carte Accueil refuse de quitter le hall ;
- le robot à la carte Nuit parle bas : le son est mesuré plus faible ;
- changer la carte de R1 dans `flotte.yaml` change ce qu'il a le droit de faire, sans toucher au code ;
- un changement de carte en cours de route est noté, et il s'applique tout de suite.
T22b fera le reste : le VRAI gardien applique la carte de R1 (lieux, vitesse) sur le faux robot, et l'écran le montre.
"""
from __future__ import annotations

import array
import math
import wave
from pathlib import Path

import pytest

from briques.clinique import accueil_voix, cartes
from briques.clinique.monde_robots import MondeDesRobots

FLOTTE = Path(cartes.__file__).with_name("flotte.yaml")


def _force(son) -> float:
    with wave.open(str(son)) as w:
        a = array.array("h", w.readframes(w.getnframes()))
    return math.sqrt(sum(x * x for x in a) / len(a))


def _robot(monde, ident):
    return next(r for r in monde.etat() if r["id"] == ident)


# ---------------------------------------------------------------------------------------------- les cinq cartes
def test_cinq_cartes_une_par_role_et_chacune_dit_les_quatre_choses():
    les_cartes = cartes.charger_cartes()
    assert sorted(les_cartes) == ["Accueil", "Nuit", "Thérapie", "Visite", "Étage"]
    for carte in les_cartes.values():
        assert carte.lieux_permis and 0 < carte.vitesse_max_m_s <= cartes.plafond_de_vitesse()
        assert 0 < carte.volume_voix <= 1 and {"arreter", "etat"} <= set(carte.actions_permises)
        assert carte.phrase and carte.nom in carte.phrase
    assert set(les_cartes["Accueil"].lieux_permis) == {"Hall", "Accueil"}
    assert "saisir" not in les_cartes["Accueil"].actions_permises and "saisir" in les_cartes["Étage"].actions_permises
    assert les_cartes["Nuit"].volume_voix < les_cartes["Étage"].volume_voix
    assert les_cartes["Nuit"].vitesse_max_m_s < les_cartes["Étage"].vitesse_max_m_s


def test_chaque_fichier_de_carte_porte_la_marque_invente():
    fichiers = sorted(cartes.DOSSIER.glob("*.yaml"))
    assert len(fichiers) == 5
    assert all("marque: inventé" in f.read_text(encoding="utf-8") for f in fichiers)


@pytest.mark.parametrize("ligne, mot", [
    ("lieux_permis: [Lune]", "Lune"),
    ("vitesse_max_m_s: 2.0", "vitesse"),
    ("volume_voix: 3", "volume"),
    ("actions_permises: [voler, arreter, etat]", "voler"),
    ("actions_permises: [parler]", "arreter"),
    ("vitese_max_m_s: 0.2", "vitese_max_m_s"),
])
def test_une_carte_mal_ecrite_est_refusee_en_clair(tmp_path, ligne, mot):
    bonne = {"marque": "marque: inventé", "nom": "nom: Essai", "phrase": 'phrase: "La carte Essai."',
             "lieux_permis": "lieux_permis: [Hall]", "vitesse_max_m_s": "vitesse_max_m_s: 0.2",
             "volume_voix": "volume_voix: 0.5", "actions_permises": "actions_permises: [parler, arreter, etat]"}
    bonne[ligne.split(":")[0]] = ligne
    (tmp_path / "essai.yaml").write_text("\n".join(bonne.values()) + "\n", encoding="utf-8")
    with pytest.raises(cartes.CarteInvalide, match=mot):
        cartes.charger_cartes(tmp_path)


def test_une_carte_dit_non_en_phrases_simples():
    accueil = cartes.charger_cartes()["Accueil"]
    assert accueil.refus_lieu("Hall") is None and accueil.refus_action("parler") is None
    assert accueil.refus_lieu("Chambre 12") == "la carte Accueil ne permet pas le lieu « Chambre 12 »"
    assert accueil.refus_action("saisir") == "la carte Accueil ne permet pas l'action « saisir »"
    assert accueil.refus_action("arreter") is None  # s'arrêter est toujours permis


# ---------------------------------------------------------------------------------------------- la flotte et ses cartes
def test_les_cartes_des_quatre_robots_sont_celles_du_cahier():
    flotte = cartes.CartesDeLaFlotte()
    assert [flotte.carte_de(i).nom for i in ("robot-r1", "robot-r2", "robot-r3", "robot-r4")] == ["Étage", "Étage", "Thérapie", "Nuit"]


def test_une_carte_inconnue_dans_flotte_yaml_est_refusee(tmp_path):
    fichier = tmp_path / "flotte.yaml"
    fichier.write_text(FLOTTE.read_text(encoding="utf-8").replace('carte: "Nuit"', 'carte: "Jardin"'), encoding="utf-8")
    with pytest.raises(cartes.CarteInvalide, match="Jardin"):
        cartes.CartesDeLaFlotte(fichier)


def test_changer_la_carte_de_r1_dans_le_fichier_change_ses_droits_sans_toucher_au_code(tmp_path):
    etage = cartes.CartesDeLaFlotte().carte_de("robot-r1")
    assert etage.refus_action("saisir") is None and etage.refus_lieu("Chambre 12") is None and etage.refus_lieu("Hall")
    fichier = tmp_path / "flotte.yaml"
    texte = FLOTTE.read_text(encoding="utf-8")
    assert texte.count('nom: R1, carte: "Étage"') == 1
    fichier.write_text(texte.replace('nom: R1, carte: "Étage"', 'nom: R1, carte: "Accueil"'), encoding="utf-8")
    accueil = cartes.CartesDeLaFlotte(fichier).carte_de("robot-r1")  # le même code, un autre fichier
    assert accueil.nom == "Accueil" and accueil.refus_action("saisir") and accueil.refus_lieu("Chambre 12")
    assert accueil.refus_lieu("Hall") is None


def test_un_changement_de_carte_en_route_est_note_et_s_applique_tout_de_suite():
    flotte = cartes.CartesDeLaFlotte()
    note = flotte.changer("robot-r1", "Accueil", qui="soignant-etage-2")
    assert note == {"robot": "robot-r1", "avant": "Étage", "apres": "Accueil", "qui": "soignant-etage-2"}
    assert flotte.carte_de("robot-r1").nom == "Accueil" and flotte.changements == [note]
    with pytest.raises(cartes.CarteInvalide, match="Jardin"):
        flotte.changer("robot-r1", "Jardin", qui="x")
    assert flotte.carte_de("robot-r1").nom == "Accueil"


# ---------------------------------------------------------------------------------------------- le monde simulé
def test_le_robot_a_la_carte_accueil_refuse_de_quitter_le_hall():
    flotte = cartes.CartesDeLaFlotte()
    flotte.changer("robot-r2", "Accueil", qui="essai")
    monde = MondeDesRobots(cartes=flotte)
    monde.placer("robot-r2", "Hall")
    monde.envoyer("robot-r2", "Accueil")  # dans ses lieux permis : il y va (5 mètres)
    for _ in range(3):
        monde.pas()
    assert _robot(monde, "robot-r2")["ou"] == "Accueil" and _robot(monde, "robot-r2")["carte"] == "Accueil"
    monde.placer("robot-r2", "Hall")
    monde.envoyer("robot-r2", "Salle 1")  # hors du hall : il ne part pas
    for _ in range(8):
        monde.pas()
    r2 = _robot(monde, "robot-r2")
    assert r2["ou"] == "Hall" and r2["etat"] == "bloqué"
    bloque = [e for e in monde.journal if e["quoi"] == "bloqué"]
    assert len(bloque) == 1 and bloque[0]["raison"] == "la carte Accueil ne permet pas le lieu « Salle 1 »"


def test_la_carte_changee_en_route_s_applique_au_lieu_suivant():
    flotte = cartes.CartesDeLaFlotte()
    monde = MondeDesRobots(cartes=flotte)
    monde.envoyer("robot-r2", "Chambre 12")  # Réserve → Poste de soins → Chambre 11 → Chambre 12
    monde.pas(), monde.pas()
    assert _robot(monde, "robot-r2")["ou"] == "Poste de soins"
    flotte.changer("robot-r2", "Accueil", qui="essai")  # la carte change en route
    for _ in range(6):
        monde.pas()
    # il finit le couloir où il était déjà engagé (vers la Chambre 11), puis s'arrête avant le lieu suivant
    r2 = _robot(monde, "robot-r2")
    assert r2["carte"] == "Accueil" and r2["etat"] == "bloqué" and r2["ou"] == "Chambre 11"
    assert monde.journal[-1]["raison"] == "la carte Accueil ne permet pas le lieu « Chambre 12 »"


def test_sans_cartes_le_monde_marche_comme_avant():
    monde = MondeDesRobots()
    monde.envoyer("robot-r2", "Chambre 12")
    for _ in range(7):
        monde.pas()
    assert _robot(monde, "robot-r2")["ou"] == "Chambre 12"


# ---------------------------------------------------------------------------------------------- la voix
def _un_son(chemin: Path, force: int = 8000) -> Path:
    with wave.open(str(chemin), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(16000)
        w.writeframes(array.array("h", [int(force * math.sin(i / 5)) for i in range(16000)]).tobytes())
    return chemin


def test_baisser_le_son_le_rend_vraiment_plus_faible(tmp_path):
    son = _un_son(tmp_path / "son.wav")
    avant = _force(son)
    accueil_voix.baisser(son, 0.3)
    assert _force(son) == pytest.approx(avant * 0.3, rel=0.02)
    with pytest.raises(ValueError):
        accueil_voix.baisser(son, 1.5)  # jamais plus fort que la voix normale


def test_la_carte_donne_son_volume_a_la_voix(tmp_path):
    vus = []

    def fausse_voix(texte, langue, sortie, haut_parleur=False, volume=1.0):
        vus.append(volume)
        return Path(sortie)

    les_cartes = cartes.charger_cartes()
    cartes.dire_avec_la_carte(les_cartes["Nuit"], "Bonsoir.", "fr", tmp_path / "n.wav", parler=fausse_voix)
    cartes.dire_avec_la_carte(les_cartes["Étage"], "Bonjour.", "fr", tmp_path / "e.wav", parler=fausse_voix)
    assert vus == [les_cartes["Nuit"].volume_voix, les_cartes["Étage"].volume_voix]
    with pytest.raises(cartes.RefusDeLaCarte, match="parler"):
        carte_muette = cartes.Carte(nom="Muette", phrase="La carte Muette.", lieux_permis=("Hall",), vitesse_max_m_s=0.1,
                                    volume_voix=0.5, actions_permises=("arreter", "etat"))
        cartes.dire_avec_la_carte(carte_muette, "Bonjour.", "fr", tmp_path / "m.wav", parler=fausse_voix)


@pytest.mark.skipif(not accueil_voix.voix_disponible()[0], reason="la voix du Mac n'est pas sur cet ordinateur")
def test_le_robot_a_la_carte_nuit_parle_bas_mesure_sur_le_son(tmp_path):
    les_cartes = cartes.charger_cartes()
    nuit = cartes.dire_avec_la_carte(les_cartes["Nuit"], "Buonasera, la sua camera è pronta.", "it", tmp_path / "nuit.wav")
    etage = cartes.dire_avec_la_carte(les_cartes["Étage"], "Buonasera, la sua camera è pronta.", "it", tmp_path / "etage.wav")
    attendu = les_cartes["Nuit"].volume_voix / les_cartes["Étage"].volume_voix
    assert _force(nuit) / _force(etage) == pytest.approx(attendu, rel=0.05)
    assert _force(nuit) < 0.6 * _force(etage)  # nettement plus bas


# ---------------------------------------------------------------------------------------------- la commande
def test_la_commande_montre_les_cartes_et_dit_vrai(capsys):
    assert '"cartes"' in (Path(__file__).resolve().parents[3] / "lancer.py").read_text(encoding="utf-8")
    assert cartes.main([]) == 0
    sortie = capsys.readouterr().out
    for mot in ("Accueil", "Étage", "Thérapie", "Visite", "Nuit", "données inventées", "R1", "Hall",
                "le gardien applique la carte", "essayé sur le faux robot seulement"):  # vrai depuis T22b
        assert mot in sortie, mot
