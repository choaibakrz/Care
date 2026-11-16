"""La clinique en boîte — H03, l'allemand des écrans du soignant et du médecin, et la table du programme du patient.

Réponse de Hiba à la question Q19 (12.11.2026) : « Traduis les textes fixes des écrans du soignant et du médecin en
allemand, et ajoute la petite table de traduction pour le programme du patient. Mets toutes les phrases traduites dans
un seul fichier, pour qu'un équipier qui parle la langue les relise. »
« Fini » veut dire :
- toutes les phrases traduites sont dans UN fichier, qui dit qu'elles ne sont pas relues ;
- en allemand, les textes fixes de l'écran du soignant et de l'écran du médecin sont en allemand ;
- sur l'écran du patient, en allemand, italien et anglais : les lignes du programme et le genre des documents sont
  traduits par la table ; le titre d'un document reste tel qu'il est écrit ;
- ce qui vient des données et n'est pas dans la table reste en français : rien n'est inventé ;
- en français, rien ne change ; aucune adresse, aucun bouton, aucun nom de patient n'est touché par la traduction ;
- la page qui se rafraîchit toute seule reçoit la même traduction.
"""
from __future__ import annotations

import asyncio
import html
import re
from pathlib import Path

import pytest
import yaml

from briques.clinique import traductions
from briques.clinique.tests.test_soir_et_dictee import MEDECIN, PATIENTE, Q1, SOIGNANT, _clinique

RACINE = Path(__file__).resolve().parents[3]


def _texte(page: str) -> str:
    sans = re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S)
    return " | ".join(html.unescape(x).strip() for x in re.findall(r">([^<]+)<", sans) if x.strip())


def _page(client, ecran, badge, langue=None, contenu=False):
    params = {"badge": badge, **({"langue": langue} if langue else {})}
    return client.get(f"/clinique/{ecran}" + ("/contenu" if contenu else ""), params=params).text


# ---------------------------------------------------------------------------------------------- un seul fichier, pas relu
def test_toutes_les_phrases_traduites_sont_dans_un_seul_fichier_qui_dit_pas_relu():
    fichier = traductions.FICHIER
    assert fichier.exists() and fichier.name == "traductions_ecrans.yaml"
    brut = fichier.read_text(encoding="utf-8")
    assert "PAS RELU" in brut.splitlines()[0] or "PAS RELU" in brut[:400]
    donnees = yaml.safe_load(brut)
    assert donnees["relu_par"] in (None, "") and "pas relu" in donnees["marque"].lower()
    assert len(donnees["ecrans_de"]["entiers"]) >= 15 and len(donnees["ecrans_de"]["morceaux"]) >= 8
    for section in ("programme", "genres_de_documents", "lieux"):
        for francais, par_langue in donnees["donnees"][section].items():
            assert set(par_langue) == {"de", "it", "en"} and all(str(v).strip() for v in par_langue.values()), francais
    assert all(str(v).strip() for v in donnees["donnees"]["listes_de_soin"].values())
    # les valeurs du faux dossier sont toutes dans la table
    quoi = set(re.findall(r"quoi: (.+)", "\n".join(f.read_text(encoding="utf-8") for f in (RACINE / "briques/clinique/faux_dossier/patients").glob("*.yaml"))))
    assert quoi <= set(donnees["donnees"]["programme"]), quoi - set(donnees["donnees"]["programme"])


def test_les_ecrans_ne_gardent_plus_de_phrases_allemandes_ailleurs_que_dans_ce_fichier_pour_ces_textes():
    assert "Schichtbeginn" not in (RACINE / "briques/clinique/ecrans_listes.py").read_text(encoding="utf-8")
    assert "Zusammenfassung" not in (RACINE / "briques/clinique/ecrans_resume.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------------------------- le soignant
def test_l_ecran_du_soignant_en_allemand_a_ses_textes_fixes_en_allemand():
    client, _, _ = _clinique()
    de, fr = _texte(_page(client, "soignant", SOIGNANT, "de")), _texte(_page(client, "soignant", SOIGNANT, "fr"))
    for francais in ("Point de prise de poste", "Mes patients :", "Points qui restent :", "Fin de poste", "Ce qui a changé",
                     "Ce que le poste d'avant n'a pas fini", "arrive aujourd'hui"):
        assert francais in fr and francais not in de, francais
    for allemand in ("Übersicht bei Schichtbeginn", "Offene Punkte:", "Schichtende", "Was sich geändert hat", "kommt heute an"):
        assert allemand in de and allemand not in fr, allemand
    assert "Physiotherapie — Raum 2" in de and "Einrichten im Zimmer — Zimmer 12" in de  # le programme, par la table
    assert "Brief der Hausärztin oder des Hausarztes : Lettera del medico curante" in de  # le genre traduit, le titre tel quel
    assert "Einrichten bei der Ankunft" in de  # le titre d'une liste de soin
    assert "entend mal de l'oreille gauche" in de  # une habitude : une donnée, pas dans la table → en français, pas inventée
    assert "Madame Giulia B." in de


def test_en_francais_rien_ne_change():
    client, _, _ = _clinique()
    sans, avec = _page(client, "soignant", SOIGNANT), _page(client, "soignant", SOIGNANT, "fr")
    assert _texte(sans) == _texte(avec).replace("", "")
    assert not any(mot in sans for mot in ("Schicht", "Offene Punkte", "Raum 2", "Physiotherapie —"))
    assert "physiothérapie — Salle 2" in _texte(sans)


def test_la_page_qui_se_rafraichit_recoit_la_meme_traduction():
    client, _, _ = _clinique()
    entiere, milieu = _page(client, "soignant", SOIGNANT, "de"), _page(client, "soignant", SOIGNANT, "de", contenu=True)
    assert "Übersicht bei Schichtbeginn" in milieu and milieu in entiere


def test_la_traduction_ne_touche_ni_aux_adresses_ni_aux_boutons_ni_aux_balises():
    client, _, _ = _clinique()
    fr, de = _page(client, "soignant", SOIGNANT, "fr", contenu=True), _page(client, "soignant", SOIGNANT, "de", contenu=True)
    balises = lambda page: re.sub(r"langue=(fr|de)", "langue=X", "".join(re.findall(r"<[^>]+>", page)))  # noqa: E731
    assert balises(fr) == balises(de)


# ---------------------------------------------------------------------------------------------- le médecin
def test_l_ecran_du_medecin_en_allemand_le_cadre_est_en_allemand_et_dit_que_les_phrases_restent_en_francais():
    client, clinique, _ = _clinique("le soir")
    client.post("/api/clinique/soir/question", json={"badge": PATIENTE, "texte": Q1})
    asyncio.run(clinique.horloge.sauter("le lendemain matin"))
    de = _texte(_page(client, "medecin", MEDECIN, "de"))
    for allemand in ("Dokument suchen:", "Öffnen", "Zusammenfassung — Madame Giulia B.", "Warum er oder sie hier ist",
                     "Was sich seit gestern geändert hat", "Was auf eine Entscheidung wartet", "Seine oder ihre Fragen",
                     "Heute geplant", "Quelle:", "Das Team um etwas bitten", "Aufgaben für mich (1)"):
        assert allemand in de, allemand
    for francais in ("Chercher un document", "Pourquoi il est là", "Ses questions", "Prévu aujourd'hui", "Tâches pour moi"):
        assert francais not in de, francais
    assert "nicht übersetzt" in de  # les phrases du résumé viennent des données : elles restent en français, et c'est dit
    assert "Raison du séjour : réadaptation après une opération de la hanche." in de
    assert Q1 in de  # la question de la patiente : jamais touchée
    assert "Arrivée le jour 1 à 09:00, chambre 12." in de and "Zimmer 12." not in de.split("Zusammenfassung — Madame Giulia B.")[1].split("Quelle:")[1]  # une phrase du résumé n'est jamais traduite à moitié


# ---------------------------------------------------------------------------------------------- le patient
LIGNES_DU_PATIENT = ("<ul><li><b>11:00</b> physiothérapie — Salle 2</li></ul><ul><li>carte d'assurance : Carte de l'Assurance Exemple</li></ul>")


@pytest.mark.parametrize("langue, programme, genre", [
    ("de", "Physiotherapie — Raum 2", "Versicherungskarte : Carte de l'Assurance Exemple"),
    ("it", "fisioterapia — Sala 2", "tessera dell'assicurazione : Carte de l'Assurance Exemple"),
    ("en", "physiotherapy — Room 2", "insurance card : Carte de l'Assurance Exemple")])
def test_la_table_du_patient_est_prete_programme_et_genre_des_documents_dans_trois_langues(langue, programme, genre):
    page = _texte("<x>" + traductions.traduire(LIGNES_DU_PATIENT, langue, "patient", patient=True) + "</x>")
    assert programme in page and genre in page
    assert "physiothérapie — Salle 2" not in page and "carte d'assurance :" not in page


def test_sur_l_ecran_du_patient_la_table_est_allumee_depuis_la_reponse_a_q25():
    """Réponse de Hiba à Q25 : A (12.11.2026). Cet essai disait « éteinte en attendant Q25 » ; adapté avec son accord (H03b).
    Le programme du patient est traduit dans sa langue ; en français, il reste en français."""
    assert traductions.PATIENT_TRADUIT is True
    client, _, _ = _clinique()
    attendus = {"it": "fisioterapia", "de": "Physiotherapie", "en": "physiotherapy", "fr": "physiothérapie — Salle 2"}
    for langue, mot in attendus.items():
        assert mot in _texte(_page(client, "patient", PATIENTE, langue)), langue
    assert "Q25" in (RACINE / "docs/projet/QUESTIONS_POUR_HIBA.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------------------------- rien n'est inventé
def test_une_valeur_qui_n_est_pas_dans_la_table_reste_en_francais():
    rendu = traductions.traduire("<ul><li><b>10:00</b> atelier de poterie — Salle 3</li><li>physiothérapie — Jardin</li></ul>", "de", "patient", patient=True)
    assert "atelier de poterie — Salle 3" in rendu  # ni l'activité ni son lieu : on ne traduit pas une ligne à moitié comprise
    assert "Physiotherapie — Jardin" in rendu  # le lieu inconnu reste tel quel
    assert traductions.traduire("<p>physiothérapie — Salle 2</p>", "fr", "patient", patient=True) == "<p>physiothérapie — Salle 2</p>"
    assert traductions.traduire("<p>physiothérapie — Salle 2</p>", "pt", "patient", patient=True) == "<p>physiothérapie — Salle 2</p>"


def test_l_accueil_et_le_therapeute_restent_en_francais():
    assert traductions.traduire("<h2>Point de prise de poste</h2>", "de", "accueil") == "<h2>Point de prise de poste</h2>"
