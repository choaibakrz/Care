"""L'accueil du hall en espagnol (ajouté le 14.11.2026 ; décision de Hiba notée dans docs/projet/QUESTIONS_POUR_HIBA.md, Q8).

Les phrases espagnoles sont écrites par l'agent : PAS RELUES tant que les deux personnes de l'équipe qui parlent
espagnol n'ont pas rendu docs/projet/RELECTURE_ESPAGNOL.md. Ces essais disent seulement que la mécanique marche, sur des phrases
TAPÉES. SIMULÉ. L'écoute de l'espagnol à la voix n'a jamais été mesurée.
« Fini » veut dire :
- « Soy Giulia B. », avec un salut et un merci autour, reçoit la chambre, le programme et le chemin, en espagnol ;
- l'étage est prévenu, et le message dit « espagnol » ;
- tout le reste appelle un humain et ne donne aucune chambre : négation, question (avec ou sans « ? »), un proche,
  « je cherche », la santé — et aussi « me llamo » et « mi nombre es », écartés pour l'instant par prudence ;
- seuls huit mots espagnols ont été ajoutés aux mots d'une simple arrivée ;
- la règle du hall sur la santé n'a PAS été changée (seule Hiba la change) ;
- les quatre autres langues sont reconnues exactement comme avant ;
- la voix du Mac a une voix espagnole.
La limite « un mot qui commence par l'initiale compte comme le nom » (« Hola Giulia, buenos días ») a été corrigée le
même jour : voir test_accueil_nom_de_famille.py.
"""
import hashlib
import json
import re

import pytest
import yaml

from briques.clinique import accueil_voix
from briques.clinique.accueil import FICHIER, AccueilDuHall, deviner_langue
from briques.clinique.carnet import Carnet
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.porte import JournalDesAcces, PorteDeLecture, charger_badges

REGLAGES = yaml.safe_load(FICHIER.read_text(encoding="utf-8"))
# Les mots de mots_d_arrivee qui n'y étaient pas avant l'espagnol (comparé à l'enregistrement 002f152).
MOTS_ESPAGNOLS_AJOUTES = {'buenas', 'buenos', 'dias', 'gracias', 'hola', 'noches', 'soy', 'tardes'}
# L'empreinte de la règle du hall sur la santé, telle qu'elle était AVANT l'espagnol (enregistrement 002f152).
EMPREINTE_DE_LA_REGLE_SANTE = "8a50e2556daada1877b08a8e07e1c17aa6c7ba3d3595a92f9a82f630f9737d99"
# (phrase, langue, sûre ?) : ce que le programme devinait AVANT l'espagnol, calculé avec l'ancienne liste de mots.
COMME_AVANT = [
    ('Est-ce que Giulia B. est là', 'fr', True),
    ("Qu'est-ce que c'est", 'fr', True),
    ('Il faut que je monte', 'fr', True),
    ('Que voulez-vous', 'fr', False),
    ('Oui, que faire', 'fr', False),
    ('Bonjour, je suis Giulia B.', 'fr', True),
    ('Je ne suis pas Giulia B.', 'fr', True),
    ('Es ist Giulia B.', 'de', True),
    ('Guten Tag, ich bin Giulia B.', 'de', True),
    ('No, sono Giulia B.', 'it', True),
    ('Non sono Giulia B.', 'it', True),
    ('No, I am Giulia B.', 'en', True),
    ('Buongiorno, sono Giulia B.', 'it', True),
    ('Salve, mi chiamo Giulia B., grazie', 'it', True),
    ('Hello, my name is Giulia B.', 'en', True),
    ("Hi, it's Giulia B.", 'en', True),
    ('Où est la salle 2 ?', 'fr', True),
    ('Je cherche une personne', 'fr', True),
    ('Ich habe eine Frage', 'de', True),
    ('Dove sta la signora', 'it', True),
    ('Where is the lift', 'en', True),
    ('Merci, bonsoir', 'fr', True),
    ('Danke, bitte', 'de', True),
    ('Scusi, ho una domanda', 'it', True),
    ('Wo ist der Aufzug', 'de', True),
    ('Warum ist Frau B. hier?', 'de', True),
    ('Perché la signora B. è qui?', 'it', True),
    ('Why is Mrs B. here?', 'en', True),
    ('Pourquoi Madame B. est-elle ici ?', 'fr', True),
    ('Giulia B.', 'fr', False),
]


def _pieces():
    horloge = HorlogeDeDemonstration()
    porte = PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour)
    carnet = Carnet(horloge=horloge)
    badges = charger_badges()
    return AccueilDuHall(porte, carnet, badges["robot-r1"]), badges, carnet


@pytest.mark.parametrize("phrase", ["Buenos días, soy Giulia B.", "Hola, soy Giulia B., gracias",
                                    "Buenas tardes, soy Giulia B.", "buenos dias soy giulia b",
                                    "Buenas noches, soy Giulia B."])
def test_soy_avec_un_salut_recoit_la_chambre_en_espagnol(phrase):
    accueil, badges, carnet = _pieces()
    reponse = accueil.entendre(phrase)
    assert reponse["cas"] == "arrivée" and reponse["langue"] == "es" and reponse["langue_sure"] is True, phrase
    assert reponse["chambre"] == 12 and reponse["etage"] == 2 and reponse["premiere_heure"] == "10:00"
    for morceau in ("Buenos días, Giulia", "habitación", "12", "planta 2", "a las 10:00", "No voy con usted", "pantalla"):
        assert morceau in reponse["dit"], morceau
    assert reponse["etiquette"] == "SIMULÉ" and reponse["marque"] == "données inventées"
    messages = carnet.lignes("message pour l'étage")
    assert len(messages) == 1 and "Langue parlée dans le hall : espagnol" in str(messages[0])


@pytest.mark.parametrize("phrase", [
    # négation, recherche, proche, question
    "No soy Giulia B.", "Busco a Giulia B.", "Soy el marido de Giulia B.", "Soy la hija de Giulia B.",
    "¿Dónde está Giulia?", "¿Es Giulia B.?", "¿Giulia B. es paciente aquí?", "Hola, soy Marco, vengo a ver a Giulia B.",
    "soy giulia rossi", "Giulia", "Tampoco soy Giulia B.", "Soy Giulia B., no",
    # trouvées par le relecteur le 14.11.2026 : elles recevaient la chambre avec les mots retirés depuis
    "Mi señora es Giulia B.", "Es mi señora Giulia B.", "Señora Giulia B., por favor", "Hola, me llamó Giulia B.",
    "Es por Giulia B.", "Hola, llamo por Giulia B.", "Hola, por Giulia B.", "Gracias por Giulia B.",
    "Es Giulia B.", "es giulia b", "¿Es Giulia B.", "Es ist Giulia B.", "Ist es Frau Giulia B.",
    # écartées pour l'instant par prudence (sûr, mais gênant : à décider avec les relecteurs et Hiba)
    "Hola, me llamo Giulia B.", "Mi nombre es Giulia B.", "Soy la señora Giulia B.", "Yo soy Giulia B.",
    # la santé
    "¿Por qué la señora B. está aquí?", "¿Giulia está enferma?", "¿Qué tiene Giulia?", "¿Giulia B. tiene cáncer?",
    "¿Por qué ingresaron a Giulia B.?",
])
def test_tout_le_reste_appelle_un_humain_et_ne_donne_aucune_chambre(phrase):
    accueil, badges, carnet = _pieces()
    reponse = accueil.entendre(phrase)
    assert reponse["cas"] in ("santé", "inconnu"), phrase
    assert "12" not in str(reponse) and reponse["chemin"] == [] and reponse["etage_prevenu"] is False, phrase
    for fuite in ("hanche", "10:00", "habitación"):
        assert fuite not in reponse["dit"], phrase
    assert carnet.lignes("message pour l'étage") == [] and len(accueil.appels(badges["accueil"])) == 1


def test_un_nom_inconnu_en_espagnol_appelle_un_humain_en_espagnol():
    accueil, badges, carnet = _pieces()
    reponse = accueil.entendre("Buenos días, soy Marco T.")
    assert reponse["cas"] == "inconnu" and reponse["langue"] == "es"
    assert reponse["dit"].startswith("No encuentro ese nombre") and "Un momento, por favor." in reponse["dit"]
    appels = accueil.appels(badges["accueil"])
    assert len(appels) == 1 and appels[0]["langue"] == "es"


def test_seuls_huit_mots_espagnols_sont_permis_et_aucun_n_ouvre_la_porte_a_un_proche():
    permis = set(REGLAGES["mots_d_arrivee"])
    assert MOTS_ESPAGNOLS_AJOUTES == {"hola", "buenos", "dias", "buenas", "tardes", "noches", "soy", "gracias"}
    assert MOTS_ESPAGNOLS_AJOUTES <= permis
    for interdit in ("no", "el", "la", "de", "busco", "donde", "marido", "hija", "ver", "que", "porque", "esta",
                     "senora", "senor", "es", "por", "favor", "me", "llamo", "nombre", "yo", "su", "a"):
        assert interdit not in permis, interdit
    assert all(isinstance(mot, str) for mot in permis)  # un « no » sans guillemets serait lu « faux » par le fichier


def test_la_regle_du_hall_sur_la_sante_est_exactement_celle_d_avant():
    """Seule Hiba change cette règle. Les mots espagnols proposés sont dans docs/projet/RELECTURE_ESPAGNOL.md, pas dans la règle."""
    texte = json.dumps(REGLAGES["regle_sante"], sort_keys=True, ensure_ascii=False)
    assert hashlib.sha256(texte.encode()).hexdigest() == EMPREINTE_DE_LA_REGLE_SANTE
    # Conséquence, dite honnêtement : la question de santé en espagnol n'a pas le refus poli sur la santé.
    accueil, badges, _ = _pieces()
    reponse = accueil.entendre("¿Por qué la señora B. está aquí?")
    assert reponse["cas"] == "inconnu" and reponse["langue"] == "es"
    assert reponse["dit"].startswith(("No estoy seguro de haber entendido", "No encuentro ese nombre"))
    assert "12" not in str(reponse) and len(accueil.appels(badges["accueil"])) == 1


def test_les_phrases_espagnoles_ont_les_memes_cles_et_les_memes_trous_que_le_francais():
    fr, es = REGLAGES["phrases"]["fr"], REGLAGES["phrases"]["es"]
    assert set(es) == set(fr)
    for cle in fr:
        assert sorted(re.findall(r"\{(\w+)\}", es[cle])) == sorted(re.findall(r"\{(\w+)\}", fr[cle])), cle
        assert es[cle].strip() and es[cle] != fr[cle], cle
    assert REGLAGES["noms_des_langues"]["es"] == "espagnol"
    assert all(isinstance(mot, str) for mot in REGLAGES["mots_des_langues"]["es"])


@pytest.mark.parametrize("phrase,langue,sure", COMME_AVANT)
def test_les_quatre_autres_langues_sont_devinees_exactement_comme_avant(phrase, langue, sure):
    assert deviner_langue(phrase) == (langue, sure), phrase


def test_la_voix_du_mac_a_une_voix_espagnole_et_dit_la_reponse(tmp_path):
    assert accueil_voix.VOIX["es"]
    la, raison = accueil_voix.voix_disponible()
    if not la:
        pytest.skip(f"voix du Mac indisponible : {raison}")
    try:
        son = accueil_voix.dire(REGLAGES["phrases"]["es"]["chemin"], "es", tmp_path / "es.wav")
    except accueil_voix.VoixImpossible as erreur:
        pytest.skip(f"aucune voix espagnole installée sur ce Mac : {erreur}")
    assert son.exists() and son.stat().st_size > 1000  # voix de synthèse du Mac, pas une personne
