"""La clinique en boîte — H01, l'accueil ne voit plus le texte d'un document médical ni les listes de soin.

Réponse de Hiba à la question Q18 (12.11.2026) : « L'écran de l'accueil ne montre que le genre, la date, l'auteur et le
patient d'un papier. Jamais le texte d'un document médical. Jamais les listes de soin. La pièce qui range les papiers
peut lire le texte d'un papier à ranger, avec son propre badge, pour préparer sa proposition. »
« Fini » veut dire :
- par la porte, le badge de l'accueil ne reçoit plus le texte d'aucun papier, ni le programme, ni une liste de soin ;
- la pièce qui range lit le texte avec SON badge (l'assistant, au service de l'accueil) : c'est au journal des accès ;
  aucun autre badge n'ouvre cette lecture ;
- la pile et l'écran de l'accueil montrent, pour chaque papier : le genre proposé, la date, l'auteur, le patient,
  l'endroit, la confiance — et pas une ligne du papier ;
- le rangement marche comme avant : trois papiers de Madame B. proposés, la feuille sans nom « à trier », la
  validation d'un doigt écrite au carnet.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique.carnet import Carnet
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.papiers import Papiers
from briques.clinique.porte import AccesRefuse, JournalDesAcces, PorteDeLecture, charger_badges

BADGES = charger_badges()
ACCUEIL = BADGES["accueil"]
DU_PAPIER = ("soggiorno", "riabilitazione", "intervento", "anca", "Medicinale", "Numéro inventé", "chaussures fermées")


def _porte():
    return PorteDeLecture(journal=JournalDesAcces())


def test_la_porte_ne_donne_plus_a_l_accueil_le_texte_d_un_papier_ni_le_programme():
    arrivees = _porte().patients(ACCUEIL)
    assert [p["id"] for p in arrivees] == ["p01"]
    giulia = arrivees[0]
    assert giulia["nom"] == "Madame Giulia B." and giulia["chambre"] == 12  # ce qu'il faut pour accueillir
    assert "programme" not in giulia and "habitudes" not in giulia and "raison" not in giulia and "listes" not in giulia
    assert len(giulia["documents"]) == 3
    assert all(set(d) == {"id"} for d in giulia["documents"])  # un papier attend : c'est tout ce que l'accueil en sait
    assert not any(mot in str(arrivees) for mot in DU_PAPIER)


def test_les_feuilles_sans_nom_arrivent_a_l_accueil_sans_leur_texte():
    feuilles = _porte().feuilles_sans_patient(ACCUEIL)
    assert [f["id"] for f in feuilles] == ["f-01"] and all("texte" not in f for f in feuilles)


def test_l_accueil_ne_lit_plus_aucune_liste_de_soin():
    porte = _porte()
    for liste in ("installation", "avant_physio", "sortie"):
        with pytest.raises(AccesRefuse):
            porte.liste_de_soin(ACCUEIL, liste)
    assert porte.liste_de_soin(BADGES["soignant-etage-2"], "installation")["id"] == "installation"  # le soignant, oui
    refus = [l for l in porte.journal.lignes() if l["resultat"] == "refusé"]
    assert len(refus) == 3 and all(l["qui"] == "accueil" for l in refus)


def test_seule_la_piece_qui_range_lit_le_texte_avec_son_propre_badge_et_c_est_au_journal():
    porte = _porte()
    pour_l_accueil = BADGES["assistant"].travaille_pour(ACCUEIL)
    papiers = porte.papiers_a_ranger(pour_l_accueil)
    assert {p["id"] for p in papiers} == {"p01-d1", "p01-d2", "p01-d3", "f-01"}
    assert all(p["texte"].startswith("INVENTÉ") and set(p) == {"id", "texte", "langue", "ecriture"} for p in papiers)
    ligne = porte.journal.lignes()[-1]
    assert (ligne["qui"], ligne["pour"], ligne["quoi"], ligne["resultat"]) == ("assistant", "accueil", "papiers à ranger", "lu")
    for badge in (ACCUEIL, BADGES["soignant-etage-2"], BADGES["medecin-exemple"], BADGES["direction"], BADGES["robot-r1"],
                  BADGES["patient-p01"], BADGES["assistant"], BADGES["assistant"].travaille_pour(BADGES["medecin-exemple"])):
        with pytest.raises(AccesRefuse):
            porte.papiers_a_ranger(badge)


def test_la_pile_de_l_accueil_dit_le_genre_la_date_l_auteur_le_patient_et_pas_une_ligne_du_papier():
    porte = _porte()
    pile = Papiers(porte, Carnet()).pile(ACCUEIL)
    assert len(pile["a_valider"]) == 3 and [p["id"] for p in pile["a_trier"]] == ["f-01"]
    lettre = next(p for p in pile["a_valider"] if p["id"] == "p01-d1")
    assert "debut" not in lettre and "texte" not in lettre
    proposition = lettre["proposition"]
    assert proposition["type"] == "lettre du médecin traitant" and proposition["nom_du_patient"] == "Madame Giulia B."
    assert proposition["auteur"] and proposition["endroit"] == "Courrier médical" and "date" in proposition
    assert not any(mot in str(pile) for mot in DU_PAPIER)
    # le texte a été lu par la pièce qui range, sous son badge : le journal le dit
    assert any(l["qui"] == "assistant" and l["pour"] == "accueil" and l["quoi"] == "papiers à ranger" for l in porte.journal.lignes())


def test_le_rangement_marche_comme_avant_la_validation_va_au_carnet():
    carnet = Carnet()
    papiers = Papiers(_porte(), carnet)
    papiers.pile(ACCUEIL)
    valide = papiers.valider(ACCUEIL, "p01-d3")
    assert valide["etat"] == "validé" and valide["type"] == "carte d'assurance" and "validée par Accueil" in valide["valide"]
    assert "texte" not in valide and "Numéro inventé" not in str(valide)  # même la réponse à la validation : sans le texte
    assert carnet.lignes("rangement de papier")[-1]["valide_par_un_humain"] is True
    from briques.clinique.papiers import PapierRefuse

    with pytest.raises(PapierRefuse):
        papiers.valider(ACCUEIL, "f-01")  # aucun patient : elle reste « à trier »


def test_l_ecran_de_l_accueil_ne_montre_aucune_ligne_d_un_papier():
    from briques.clinique.ecrans import brancher_ecrans

    horloge = HorlogeDeDemonstration()
    app = FastAPI()
    brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge, carnet=Carnet(horloge=horloge))
    client = TestClient(app)
    pages = [client.get("/clinique/accueil?badge=accueil").text]
    for chemin in ("/clinique/accueil/papiers?badge=accueil", "/clinique/papiers?badge=accueil"):
        reponse = client.get(chemin)
        if reponse.status_code == 200:
            pages.append(reponse.text)
    assert len(pages) >= 2, "la page des papiers de l'accueil ne s'ouvre pas"
    pages.append(client.get("/api/clinique/papiers", params={"badge": "accueil"}).text)
    pages.append(client.post("/api/clinique/papiers/valider", json={"badge": "accueil", "papier": "p01-d1"}).text)
    tout = "\n".join(pages)
    assert "lettre du médecin traitant" in tout and "Madame Giulia B." in tout and "Courrier médical" in tout
    assert not any(mot in tout for mot in DU_PAPIER)
