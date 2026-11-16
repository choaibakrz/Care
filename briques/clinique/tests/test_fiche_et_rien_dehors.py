"""La clinique en boîte — T11d, la fiche de vérité de la répétition et « rien n'est sorti de l'ordinateur ».
Version simple (cahier 5.11 et partie 8, étapes 13 et 14).

« Fini » veut dire :
- après les étapes 1 à 12, la fiche de vérité a les sept lignes du cahier (5.11), chacune remplie par un calcul ou
  par « non mesuré » et sa raison ; jamais un chiffre tapé à la main ;
- elle montre aussi les étapes ratées ou manquantes : un échec ne se cache pas ;
- pendant toute la répétition, chaque essai de connexion de ce programme vers l'extérieur est compté ET bloqué ;
  l'étape 14 réussit seulement si le compte est zéro, et si toute la répétition a été surveillée ;
- hors d'une répétition, les étapes 13 et 14 ratent : elles ne se jouent pas toutes seules ;
- avec tout cela, la grande répétition dit « RÉUSSIE » : T11 est finie.
"""
from __future__ import annotations

import re
import socket

import pytest

from briques.clinique import chef_clinique, fiche, repetition
from briques.clinique.tests.la_vraie_repetition import la_vraie_repetition  # noqa: F401 (une aide d'essai)

LIGNES_DU_CAHIER = ["Données inventées", "Robots simulés", "Temps accéléré", "Part de l'humain",
                    "Phrases retirées faute de source", "Taux d'erreur de lecture des papiers",
                    "Taux d'erreur de la voix, par langue"]


@pytest.fixture(autouse=True)
def _sans_mesure_de_lecture_sur_cet_ordinateur(monkeypatch, tmp_path):
    """La fiche lit la dernière mesure de lecture des papiers, si cet ordinateur en a une (journal/clinique/). Ces essais
    ne doivent pas dépendre de ce qui a été mesuré ici : ils partent d'un ordinateur sans mesure."""
    from briques.clinique import papiers_images

    monkeypatch.setattr(papiers_images, "FICHIER_MESURE", tmp_path / "pas_de_mesure.json")
    from briques.clinique import ecoute

    monkeypatch.setattr(ecoute, "FICHIER_MESURE", tmp_path / "pas_de_mesure_d_ecoute.json")


def _ok(etiquette="SIMULÉ", **mesures):
    return lambda: repetition.Resultat(True, etiquette, "essai", mesures)


def _controles(**remplace):
    """De faux contrôles pour les étapes 1 à 12 ; les VRAIS contrôles pour la fiche (13) et le réseau (14)."""
    controles = {n: _ok() for n in range(1, 13)}
    controles[8] = _ok("FAUX ROBOT")
    controles[10] = _ok(phrases_retirees=2)
    controles[13], controles[14] = repetition.CONTROLES[13], repetition.CONTROLES[14]
    controles.update({int(cle[1:]): valeur for cle, valeur in remplace.items()})
    return controles


def _jouer(controles):
    lignes: list[str] = []
    code = chef_clinique.jouer(controles, ecrire=lignes.append)
    return code, lignes


def _fiche(lignes):
    return {l.split(" : ", 1)[0].strip(" ·"): l.split(" : ", 1)[1] for l in lignes if l.startswith("    · ")}


# ---------------------------------------------------------------------------------------------- la fiche (étape 13)
def test_la_fiche_a_les_sept_lignes_du_cahier_chacune_remplie():
    code, lignes = _jouer(_controles())
    vue = _fiche(lignes)
    for titre in LIGNES_DU_CAHIER:
        assert vue.get(titre), titre
    assert vue["Données inventées"].startswith("oui")
    assert vue["Robots simulés"].startswith("3 sur 4")
    assert vue["Temps accéléré"].startswith("oui") and "5 sauts" in vue["Temps accéléré"]
    assert vue["Part de l'humain"].startswith("aucune") and "0 étape sur 12" in vue["Part de l'humain"]
    assert vue["Phrases retirées faute de source"].startswith("2")
    assert vue["Taux d'erreur de lecture des papiers"].startswith("non mesuré")
    assert vue["Taux d'erreur de la voix, par langue"].startswith("non mesuré")
    assert vue["Étiquettes des étapes"] == "FAUX ROBOT : 1 · SIMULÉ : 11"
    assert any(re.match(r"\s*13\. \[SIMULÉ\] réussie", l) for l in lignes)
    assert code == 0 and lignes[-1] == "RÉPÉTITION : RÉUSSIE"


def test_ce_qui_n_est_pas_mesure_s_ecrit_non_mesure_avec_sa_raison():
    controles = _controles()
    controles[10] = _ok()  # le résumé n'a pas donné son compte de phrases retirées
    _, lignes = _jouer(controles)
    vue = _fiche(lignes)
    assert vue["Phrases retirées faute de source"].startswith("non mesuré")
    for titre in LIGNES_DU_CAHIER:
        if vue[titre].startswith("non mesuré"):
            assert len(vue[titre]) > len("non mesuré") + 10, titre  # la raison est dite


def test_un_echec_se_montre_dans_la_fiche_et_la_repetition_reste_ratee():
    rate = lambda: repetition.Resultat(False, "FAUX ROBOT", "le robot n'est pas arrivé")
    controles = _controles(e8=rate)
    del controles[12]
    code, lignes = _jouer(controles)
    vue = _fiche(lignes)
    assert "8" in vue["Étapes ratées ou manquantes"] and "12" in vue["Étapes ratées ou manquantes"]
    assert code == 1 and lignes[-1].startswith("RÉPÉTITION : RATÉE — ")
    assert any(re.match(r"\s*13\. .*RATÉE", l) for l in lignes)  # sans les douze étapes, la fiche n'est pas complète


def test_une_etape_jouee_par_un_humain_compte_dans_la_part_de_l_humain():
    _, lignes = _jouer(_controles(e4=_ok("JOUÉ")))
    assert _fiche(lignes)["Part de l'humain"].startswith("1 étape sur 12")


def test_hors_d_une_repetition_la_fiche_et_le_reseau_ne_se_jouent_pas_tout_seuls():
    for numero in (13, 14):
        resultat = repetition.CONTROLES[numero]()
        assert resultat.reussie is False and "répétition" in resultat.detail, numero


def test_aucun_chiffre_de_la_fiche_n_est_ecrit_en_dur():
    """Le compte des robots vient de flotte.yaml, les sauts viennent de l'horloge : on change, la fiche change."""
    seance = repetition.Seance()
    for n in range(1, 13):
        seance.noter(n, "reussie", repetition.Resultat(True, "SIMULÉ", "essai"))
    seance.sauts = 0
    lignes = {l["titre"]: l["valeur"] for l in fiche.fiche_de_la_repetition(seance)["lignes"]}
    assert lignes["Temps accéléré"].startswith("non")
    seance.sauts = None
    lignes = {l["titre"]: l["valeur"] for l in fiche.fiche_de_la_repetition(seance)["lignes"]}
    assert lignes["Temps accéléré"].startswith("non mesuré")


# ---------------------------------------------------------------------------------------------- rien dehors (étape 14)
def test_sans_essai_de_sortie_l_etape_14_reussit_et_dit_ce_qu_elle_a_surveille():
    code, lignes = _jouer(_controles())
    ligne = next(l for l in lignes if re.match(r"\s*14\. ", l))
    assert "[SIMULÉ] réussie" in ligne and "0 essai de connexion vers l'extérieur" in ligne
    assert "ce programme" in ligne  # la limite est dite : on ne surveille que ce programme


def _sortir():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.2)
        try:
            s.connect(("192.0.2.1", 80))  # une adresse d'exemple, hors de l'ordinateur
        except OSError:
            pass
    return repetition.Resultat(True, "SIMULÉ", "une pièce a essayé de sortir")


def test_une_piece_qui_essaie_de_sortir_fait_rater_l_etape_14_et_rien_ne_part():
    code, lignes = _jouer(_controles(e5=_sortir))
    ligne = next(l for l in lignes if re.match(r"\s*14\. ", l))
    assert "RATÉE" in ligne and "1 essai" in ligne and "192.0.2.1" in ligne and "bloqué" in ligne
    assert code == 1 and "étape ratée : 14" in lignes[-1]


def test_un_nom_a_chercher_sur_internet_compte_aussi():
    def chercher():
        try:
            socket.getaddrinfo("exemple.invalid", 443)
        except OSError:
            pass
        return repetition.Resultat(True, "SIMULÉ", "une pièce a cherché un nom")

    code, lignes = _jouer(_controles(e2=chercher))
    ligne = next(l for l in lignes if re.match(r"\s*14\. ", l))
    assert "RATÉE" in ligne and "exemple.invalid" in ligne and code == 1


def test_une_connexion_a_l_ordinateur_lui_meme_ne_compte_pas():
    def local():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            try:
                s.connect(("127.0.0.1", 9))
            except OSError:
                pass
        return repetition.Resultat(True, "SIMULÉ", "connexion locale")

    code, lignes = _jouer(_controles(e3=local))
    assert code == 0 and lignes[-1] == "RÉPÉTITION : RÉUSSIE"


def test_la_surveillance_s_arrete_avec_la_repetition():
    avant = (socket.socket.connect, socket.socket.connect_ex, socket.socket.sendto, socket.getaddrinfo)
    _jouer(_controles())
    assert (socket.socket.connect, socket.socket.connect_ex, socket.socket.sendto, socket.getaddrinfo) == avant
    assert repetition.SEANCE is None


def test_si_une_etape_manque_avant_l_etape_14_elle_rate():
    controles = _controles()
    del controles[6]
    code, lignes = _jouer(controles)
    assert any(re.match(r"\s*14\. .*RATÉE", l) for l in lignes) and code == 1


# ---------------------------------------------------------------------------------------------- T11 est finie
def test_la_grande_repetition_reussit_avec_les_vraies_pieces(la_vraie_repetition):
    lignes = la_vraie_repetition.stdout.strip().splitlines()
    assert lignes[-1] == "RÉPÉTITION : RÉUSSIE", "\n".join(lignes[-12:])
    assert la_vraie_repetition.returncode == 0
    etapes = [l for l in lignes if re.match(r"\s*\d+\. ", l)]
    assert len(etapes) == 14 and all(re.search(r"\[(SIMULÉ|FAUX ROBOT)\] réussie", l) for l in etapes)
    assert not any("RÉEL" in l.split("]")[0] for l in etapes)  # rien n'est fait par un vrai robot : personne ne le dit
    vue = _fiche(lignes)
    for titre in LIGNES_DU_CAHIER:
        assert vue.get(titre), titre
    assert vue["Robots simulés"].startswith("3 sur 4") and vue["Temps accéléré"].startswith("oui")
    assert re.match(r"\d+", vue["Phrases retirées faute de source"])
    assert "0 essai de connexion vers l'extérieur" in next(l for l in etapes if l.lstrip().startswith("14."))
