"""La clinique en boîte — J06, la parole des soignants, VERSION SIMPLE (avenant jury, J06).

Hiba n'a pas répondu à la question Q7 : pas de fichier de paroles. « Fini » veut dire :
- le guide d'entretien tient sur une page à imprimer, avec les dix questions de l'avenant, mot pour mot ;
- deux étiquettes existent pour ce qu'un écran dit du travail des gens : DIT PAR UN SOIGNANT, ou HYPOTHÈSE ;
- la page « Ce qu'on nous a dit » affiche : « Aucune parole recueillie pour l'instant. Ce que nous disons du travail des
  soignants est une hypothèse. » ;
- rien n'est inventé : aucune parole de soignant n'est écrite nulle part, et aucun fichier de paroles n'existe.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique import paroles, paroles_fichier
from briques.clinique.carnet import Carnet
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.porte import JournalDesAcces, PorteDeLecture

RACINE = Path(__file__).resolve().parents[3]
QUESTIONS = [
    "Racontez-moi votre dernière matinée de travail, du début à la fin.",
    "Qu'est-ce qui vous prend du temps et qui n'est pas du soin ?",
    "Qu'est-ce qui s'oublie le plus facilement quand la journée est chargée ?",
    "Quand il vous manque un objet dans la chambre, que faites-vous ?",
    "Comment apprenez-vous les habitudes d'un nouveau patient ?",
    "Que se passe-t-il quand un patient ne parle pas votre langue ?",
    "Avez-vous connu un robot ou un nouvel outil qui a été abandonné ? Pourquoi ?",
    "Voici notre prototype. Qu'est-ce qui vous gênerait ? Qu'est-ce qui vous servirait ?",
    "Qui devrait décider de ce que le robot a le droit de faire dans votre service ?",
    "Qu'est-ce qu'un robot ne devrait jamais faire ici ?",
]
PHRASE = "Aucune parole recueillie pour l'instant. Ce que nous disons du travail des soignants est une hypothèse."


def _client():
    from briques.clinique.ecrans import brancher_ecrans

    horloge = HorlogeDeDemonstration()
    app = FastAPI()
    brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                    carnet=Carnet(horloge=horloge), code_equipe="x")
    return TestClient(app)


def test_le_guide_d_entretien_tient_sur_une_page_avec_les_dix_questions_mot_pour_mot():
    guide = (RACINE / "docs/projet/GUIDE_ENTRETIEN.md").read_text(encoding="utf-8")
    places = [guide.index(f"{i}. {q}") for i, q in enumerate(QUESTIONS, 1)]
    assert places == sorted(places)
    assert "qui l'on est" in guide and "prototype pour un concours" in guide and "rien n'est noté sans accord" in guide
    assert "Pouvons-nous citer une de vos phrases, sans votre nom ?" in guide
    lignes = guide.splitlines()
    assert len(lignes) <= 45 and max(len(l) for l in lignes) <= 110  # une page à imprimer
    assert "Pas de nom" in guide and "patient" in guide  # ce qu'on ne note jamais


def test_les_deux_etiquettes_existent_et_tant_qu_il_n_y_a_pas_de_parole_tout_est_hypothese():
    assert paroles.ETIQUETTES == ("DIT PAR UN SOIGNANT", "HYPOTHÈSE")
    assert paroles.etiquette_du_travail() == "HYPOTHÈSE"
    if not paroles_fichier.FICHIER.exists():  # Q26 A : zéro parole tant que le fichier de l'équipe n'existe pas
        assert paroles.paroles_recueillies() == 0


def test_la_page_ce_qu_on_nous_a_dit_affiche_la_phrase_et_les_deux_etiquettes():
    client = _client()
    page = client.get("/clinique/ce-qu-on-nous-a-dit")
    assert page.status_code == 200 and "DONNÉES INVENTÉES" in page.text
    assert PHRASE.replace("'", "&#x27;") in page.text
    assert "DIT PAR UN SOIGNANT" in page.text and "HYPOTHÈSE" in page.text
    assert "Pas de nom. Pas un mot sur un patient." in page.text
    assert "docs/projet/GUIDE_ENTRETIEN.md" in page.text
    assert "/clinique/ce-qu-on-nous-a-dit" in client.get("/clinique").text


def test_ce_qu_un_ecran_dit_du_travail_des_soignants_porte_l_etiquette_hypothese():
    client = _client()
    liste = client.get("/clinique/soignant/liste", params={"badge": "soignant-etage-2", "patient": "p01", "liste": "installation"}).text
    assert "HYPOTHÈSE" in liste and "aucun soignant ne nous l" in liste
    assert "DIT PAR UN SOIGNANT" not in liste  # personne ne nous a rien dit : on ne le prétend pas


def test_rien_n_est_invente_aucune_parole_aucun_fichier():
    assert not (RACINE / "PAROLES_DES_SOIGNANTS.md").exists()
    page = _client().get("/clinique/ce-qu-on-nous-a-dit").text
    for interdit in ("dirait", "nous a dit que", "une soignante nous", "un soignant nous", "fait gagner du temps",
                     "soulage", "ne remplace personne"):
        assert interdit not in page, interdit
    source = (RACINE / "briques/clinique/paroles.py").read_text(encoding="utf-8")
    assert "open(" not in source and "read_text" not in source and "paroles_fichier" in source  # Q26 A : la page ne lit que ce fichier-là, par la pièce de lecture
