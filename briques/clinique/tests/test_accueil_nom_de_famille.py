"""L'accueil du hall : ce qui compte comme « le nom » après le prénom (resserré le 14.11.2026, décision de Hiba).

Avant, n'importe quel mot qui commençait par l'initiale du nom comptait comme le nom : « Is Giulia better » ou
« Hallo Giulia, bitte » recevaient le numéro de la chambre. Trouvé par un relecteur le 14.11.2026.
Ces essais tournent sur des phrases TAPÉES. SIMULÉ. À la voix, les majuscules dépendent de l'écoute : pas mesuré.
« Fini » veut dire :
- l'initiale seule compte toujours (« Giulia B. », « giulia b », « GIULIA B. ») ;
- un nom entier compte s'il commence par l'initiale, est écrit avec une majuscule au milieu d'une phrase, et n'est ni
  un mot courant ni un mot de la règle sur la santé ;
- un mot courant, un mot sans majuscule, un mot juste après un point : jamais pris pour le nom ; un humain est appelé ;
- dans une phrase tout en majuscules, seule l'initiale seule compte ;
- si deux personnes sont possibles avec l'ancienne règle, le robot n'en choisit aucune (comme avant) ;
- le prix est écrit : de vrais noms tapés sans majuscule appellent maintenant un humain.

CE QUI REÇOIT ENCORE LA CHAMBRE sans être la personne (pas corrigé ; aucun essai ne l'affirme, pour ne pas le figer) :
« Frau Giulia B., bitte », « Madame Giulia B. », « C'est Giulia B. », « Is Giulia B. there » (la demande d'un visiteur
faite de mots permis) ; « Ist Giulia B. » (une question dite sans « ? ») ; « Is Giulia Better », « Giulia Blumen »,
« Giulia Brustkrebs » (un mot inconnu avec une majuscule). Le hall ne prouve pas qui parle : voir NON_TESTE.md.
"""
import pytest

import yaml

from briques.clinique.accueil import FICHIER, AccueilDuHall, _est_le_nom, _mots_ordinaires, simple_arrivee
from briques.clinique.carnet import Carnet
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.porte import JournalDesAcces, PorteDeLecture, charger_badges


def _pieces():
    horloge = HorlogeDeDemonstration()
    porte = PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour)
    carnet = Carnet(horloge=horloge)
    badges = charger_badges()
    return AccueilDuHall(porte, carnet, badges["robot-r1"]), badges, carnet


@pytest.mark.parametrize("phrase", [
    # un mot courant qui commence par « b », dans chaque langue
    "Is Giulia better", "Hallo Giulia, bitte", "Buongiorno Giulia, buonasera", "Hola Giulia, buenos días",
    "Bonjour Giulia, bonsoir", "Hallo Giulia, Bitte", "Bonjour Giulia, Bonsoir", "Hola Giulia, Buenas tardes",
    # un mot inconnu, sans majuscule
    "Hola, Giulia baja", "Ist Giulia besuchbar", "Giulia busca", "is giulia back", "Giulia bleibt", "giulia bianchi",
    # tout en majuscules : on ne peut pas reconnaître un nom entier
    "IS GIULIA BETTER", "GIULIA BIANCHI", "HALLO GIULIA BITTE",
    # une majuscule normale en début de phrase, juste après le prénom (trouvé par le relecteur)
    "Hallo Giulia. Bis morgen", "Hello Giulia. Bye", "Ciao Giulia. Bene, grazie", "Hola Giulia. Bien, gracias",
    "Bonjour Giulia. Bisous", "Hallo Giulia! Bis bald",
    # un mot de la règle sur la santé n'est jamais le nom
    "Giulia Blessure", "Hallo Giulia. Behandlung", "Giulia Behandlung",
])
def test_un_mot_qui_commence_par_l_initiale_n_est_plus_pris_pour_le_nom(phrase):
    accueil, badges, carnet = _pieces()
    reponse = accueil.entendre(phrase)
    assert reponse["cas"] in ("santé", "inconnu"), phrase
    assert "12" not in str(reponse) and reponse["chemin"] == [] and reponse["etage_prevenu"] is False, phrase
    assert carnet.lignes("message pour l'étage") == [] and len(accueil.appels(badges["accueil"])) == 1


@pytest.mark.parametrize("phrase", [
    "Giulia B.", "giulia b", "GIULIA B.", "Buongiorno, sono Giulia B.", "Bonjour, je suis Giulia B.",
    "Guten Tag, ich bin Giulia B.", "Hello, my name is Giulia B.", "Buenos días, soy Giulia B.",
    "Hi, it's Giulia B.", "Buon giorno, Giulia B.", "Salve, mi chiamo Giulia B., grazie",
    "Guten Tag, mein Name ist Giulia Bianchi", "Buongiorno, sono Giulia Bianchi", "Bonjour, je suis Giulia Bernard",
])
def test_ces_vraies_arrivees_recoivent_la_chambre(phrase):
    accueil, *_ = _pieces()
    reponse = accueil.entendre(phrase)
    assert reponse["cas"] == "arrivée" and reponse["chambre"] == 12, phrase


@pytest.mark.parametrize("phrase", ["giulia bianchi", "Giulia bianchi", "GIULIA BIANCHI", "ich heisse giulia bianchi",
                                    "Giulia bi", "giulia bee"])
def test_le_prix_un_vrai_nom_sans_majuscule_appelle_maintenant_un_humain(phrase):
    """Ces phrases recevaient la chambre avant le 14.11.2026. Sans majuscule, on ne devine pas : c'est le sens sûr.
    À la voix, les majuscules viennent de l'écoute : pas mesuré avec de vraies voix."""
    accueil, badges, _ = _pieces()
    reponse = accueil.entendre(phrase)
    assert reponse["cas"] == "inconnu" and "12" not in str(reponse), phrase
    assert len(accueil.appels(badges["accueil"])) == 1


def test_la_regle_du_nom_cas_par_cas():
    assert _est_le_nom("b", "b", False, "b", False) and _est_le_nom("b", "B", True, "b", True)  # l'initiale seule, toujours
    assert _est_le_nom("bianchi", "Bianchi", False, "b", False)
    assert not _est_le_nom("bianchi", "bianchi", False, "b", False)  # sans majuscule
    assert not _est_le_nom("bianchi", "Bianchi", True, "b", False)  # en début de phrase : la majuscule ne dit rien
    assert not _est_le_nom("bianchi", "BIANCHI", False, "b", True)  # phrase tout en majuscules
    assert not _est_le_nom("bitte", "Bitte", False, "b", False)  # mot courant, même avec une majuscule
    assert not _est_le_nom("behandlung", "Behandlung", False, "b", False)  # mot de la règle sur la santé
    assert not _est_le_nom("rossi", "Rossi", False, "b", False)  # pas la bonne initiale
    for mot in ("bitte", "buenos", "bonsoir", "buonasera", "bonjour", "buenas", "bin", "buon", "busco"):
        assert mot in _mots_ordinaires(), mot


def test_deux_personnes_possibles_le_robot_n_en_choisit_aucune():
    """Avec l'ancienne règle large, deux fiches pouvaient convenir : le robot refusait. La règle serrée ne doit pas
    en faire gagner une des deux (trouvé par le relecteur : « anna maria m. » avec Anna M. et Anna-Maria M.)."""
    arrivees = [{"prenom": "Anna", "initiale": "M."}, {"prenom": "Anna-Maria", "initiale": "M."}]
    _, simples = simple_arrivee("anna maria m.", arrivees)
    assert len(simples) != 1
    arrivees = [{"prenom": "My", "initiale": "G."}, {"prenom": "Giulia", "initiale": "B."}]
    _, simples = simple_arrivee("my GIULIA buonasera", arrivees)
    assert len(simples) != 1
    _, simples = simple_arrivee("Buongiorno, sono Giulia B.", arrivees)  # une seule convient : elle est rendue
    assert [a["prenom"] for a in simples] == ["Giulia"]


def test_le_grand_eszett_ne_decale_pas_les_mots():
    accueil, *_ = _pieces()
    assert accueil.entendre("ICH HEIẞE GIULIA B.")["cas"] == "arrivée"  # l'initiale seule compte, même tout en majuscules
    assert accueil.entendre("ICH HEIẞE GIULIA BIANCHI")["cas"] == "inconnu"


def test_chaque_mot_du_fichier_est_un_texte():
    """Sans guillemets, « no », « on », « yes », « off » seraient lus « vrai » ou « faux » par le fichier."""
    reglages = yaml.safe_load(FICHIER.read_text(encoding="utf-8"))
    listes = [reglages["mots_d_arrivee"], *reglages["mots_des_langues"].values(), *(
        reglages["regle_sante"][cle] for cle in ("debuts", "entiers", "pourquoi", "personne"))]
    for liste in listes:
        assert all(isinstance(mot, str) for mot in liste), [mot for mot in liste if not isinstance(mot, str)]
