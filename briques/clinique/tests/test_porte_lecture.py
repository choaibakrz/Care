"""La clinique en boîte — T03, la porte de lecture (cahier 5.2). Internet coupé, aucun modèle.

On vérifie : le soignant voit ses patients ; la direction ne voit aucun nom ; le robot ne voit rien sur la santé ;
chaque lecture est au journal ; une demande d'écriture est refusée et notée ; le cerveau lit par la même porte,
avec son propre badge (branchement sur la porte des agents, brique 14).
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from briques.clinique import dossier
from briques.clinique.porte import (AccesRefuse, EcritureRefusee, JournalDesAcces, PorteDeLecture, ROLES,
                                    brancher_sur_la_porte_des_agents, charger_badges)

RACINE = Path(__file__).resolve().parents[3]


@pytest.fixture
def badges():
    return charger_badges()


@pytest.fixture
def porte():
    return PorteDeLecture(journal=JournalDesAcces())


def _mots_de_sante(d):
    """Tout ce qui, dans le faux dossier, touche à la santé ou à la vie privée : habitudes, raison, textes des documents."""
    mots = set()
    for p in d.patients:
        mots.update(p["habitudes"])
        mots.add(p["Encounter"]["raison"])
        for doc in p["DocumentReference"]:
            mots.update(ligne for ligne in doc["texte"].splitlines() if len(ligne) > 12)
    return mots


def test_les_huit_badges_du_cahier(badges):
    assert {b.role for b in badges.values()} == set(ROLES)
    assert set(ROLES) == {"patient", "soignant", "thérapeute", "médecin", "accueil", "direction", "assistant", "robot"}
    assert "Exemple" in badges["medecin-exemple"].libelle


def test_le_soignant_voit_les_patients_de_son_etage(porte, badges):
    vus = porte.patients(badges["soignant-etage-2"])
    assert {p["id"] for p in vus} == {"p01", "p02", "p03", "p04"}
    giulia = next(p for p in vus if p["id"] == "p01")
    assert giulia["nom"] == "Madame Giulia B." and len(giulia["habitudes"]) == 5
    assert len(giulia["programme"]) == 5 and giulia["listes"] == ["installation", "avant_physio"]
    assert len(giulia["documents"]) == 3
    assert "raison" not in giulia
    with pytest.raises(AccesRefuse):
        porte.patient(badges["soignant-etage-2"], "p07")  # une patiente d'un autre étage


def test_la_direction_ne_voit_aucun_nom(porte, badges):
    with pytest.raises(AccesRefuse):
        porte.patients(badges["direction"])
    with pytest.raises(AccesRefuse):
        porte.patient(badges["direction"], "p01")
    comptes = porte.comptes(badges["direction"])
    assert sum(e["patients"] for e in comptes["etages"]) == 12
    etage_2 = next(e for e in comptes["etages"] if e["etage"] == 2)
    assert etage_2["patients"] == 4 and etage_2["arrivees_du_jour"] == 1
    texte = json.dumps(comptes, ensure_ascii=False)
    for p in dossier.charger().patients:
        prenom = p["Patient"]["nom_affiche"].split()[1]
        assert prenom not in texte and p["Patient"]["id"] not in texte
    assert "soignant" not in texte.lower()


def test_le_robot_ne_voit_rien_sur_la_sante(porte, badges):
    vus = porte.patients(badges["robot-r1"])
    assert len(vus) == 12
    for p in vus:
        assert set(p) == {"id", "prenom", "langue", "chambre", "etage"}
    assert next(p for p in vus if p["id"] == "p01") == {"id": "p01", "prenom": "Giulia", "langue": "it",
                                                        "chambre": 12, "etage": 2}
    texte = json.dumps([vus, porte.patient(badges["robot-r1"], "p01")], ensure_ascii=False)
    for mot in _mots_de_sante(dossier.charger()):
        assert mot not in texte, mot
    assert porte.lieux(badges["robot-r1"])["lieux"] and porte.reserve(badges["robot-r1"])
    with pytest.raises(AccesRefuse):
        porte.liste_de_soin(badges["robot-r1"], "installation")


def test_le_patient_ne_voit_que_lui(porte, badges):
    moi = porte.patients(badges["patient-p01"])
    assert [p["id"] for p in moi] == ["p01"] and len(moi[0]["programme"]) == 5
    with pytest.raises(AccesRefuse):
        porte.patient(badges["patient-p01"], "p02")
    with pytest.raises(AccesRefuse):
        porte.reserve(badges["patient-p01"])


def test_le_medecin_voit_tout_de_ses_patients_et_le_therapeute_le_programme(porte, badges):
    fiche = porte.patient(badges["medecin-exemple"], "p01")
    assert fiche["raison"] == "réadaptation après une opération de la hanche" and fiche["age"] == 71
    assert fiche["habitudes"] and fiche["documents"][0]["texte"]
    with pytest.raises(AccesRefuse):
        porte.patient(badges["medecin-exemple"], "p02")
    vue = porte.patient(badges["therapeute-exemple"], "p01")
    assert set(vue) == {"id", "nom", "langue", "chambre", "etage", "programme"}


def test_l_accueil_voit_les_arrivees_du_jour_sans_habitudes_ni_raison(porte, badges):
    arrivees = porte.patients(badges["accueil"])
    assert [p["id"] for p in arrivees] == ["p01"]
    assert "habitudes" not in arrivees[0] and "raison" not in arrivees[0]
    assert arrivees[0]["chambre"] == 12 and len(arrivees[0]["documents"]) == 3
    assert [p["id"] for p in PorteDeLecture(journal=JournalDesAcces(), jour=lambda: 0).patients(badges["accueil"])] == ["p04"]


def test_l_assistant_voit_ce_que_voit_la_personne_pour_qui_il_travaille(porte, badges):
    with pytest.raises(AccesRefuse):
        porte.patients(badges["assistant"])  # il ne travaille pour personne : il ne voit rien
    pour_soignant = badges["assistant"].travaille_pour(badges["soignant-etage-2"])
    assert porte.patients(pour_soignant) == porte.patients(badges["soignant-etage-2"])
    pour_direction = badges["assistant"].travaille_pour(badges["direction"])
    with pytest.raises(AccesRefuse):
        porte.patients(pour_direction)
    with pytest.raises(ValueError):
        badges["soignant-etage-2"].travaille_pour(badges["medecin-exemple"])  # seul l'assistant emprunte une vue
    with pytest.raises(ValueError):
        badges["assistant"].travaille_pour(pour_soignant)  # pas d'assistant d'assistant
    derniere = [l for l in porte.journal.lignes() if l["resultat"] == "lu"][0]
    assert derniere["qui"] == "assistant" and derniere["pour"] == "soignant-etage-2"


def test_chaque_lecture_est_au_journal(porte, badges):
    porte.patients(badges["soignant-etage-2"])
    porte.patient(badges["medecin-exemple"], "p01")
    porte.comptes(badges["direction"])
    porte.lieux(badges["robot-r1"])
    porte.reserve(badges["soignant-etage-2"])
    porte.liste_de_soin(badges["soignant-etage-2"], "installation")
    with pytest.raises(AccesRefuse):
        porte.patients(badges["direction"])
    with pytest.raises(AccesRefuse):
        porte.patient(badges["medecin-exemple"], "p99")
    lignes = porte.journal.lignes()
    assert len(lignes) == 8
    assert [l["resultat"] for l in lignes] == ["lu"] * 6 + ["refusé"] * 2
    for l in lignes:
        assert l["qui"] and l["quoi"] and l["quand"] and l["role"]
    assert lignes[0]["patients"] == ["p01", "p02", "p03", "p04"]
    assert lignes[1]["patients"] == ["p01"] and lignes[6]["raison"]


def test_une_demande_d_ecriture_est_refusee_et_notee(porte, badges):
    avant = dossier.empreinte()
    for badge in badges.values():
        with pytest.raises(EcritureRefusee):
            porte.ecrire(badge, "patient", identifiant="p01", habitudes=["triche"])
    lignes = porte.journal.lignes()
    assert len(lignes) == len(badges) and all(l["resultat"] == "écriture refusée" for l in lignes)
    assert lignes[0]["quoi"] == "écrire : patient" and lignes[0]["patients"] == ["p01"]
    assert dossier.empreinte() == avant
    fiche = porte.patient(badges["medecin-exemple"], "p01")
    fiche["habitudes"].append("triche")  # ce qu'on reçoit est une copie : la modifier ne change rien
    assert len(porte.patient(badges["medecin-exemple"], "p01")["habitudes"]) == 5


def test_le_journal_s_ecrit_dans_un_fichier(tmp_path, badges):
    fichier = tmp_path / "acces.jsonl"
    porte = PorteDeLecture(journal=JournalDesAcces(fichier))
    porte.patients(badges["soignant-etage-2"])
    with pytest.raises(EcritureRefusee):
        porte.ecrire(badges["robot-r1"], "lieux")
    lignes = [json.loads(l) for l in fichier.read_text(encoding="utf-8").splitlines()]
    assert [l["resultat"] for l in lignes] == ["lu", "écriture refusée"]


def test_un_badge_inconnu_est_refuse(porte, badges):
    import dataclasses

    faux = dataclasses.replace(badges["accueil"], role="chef")
    with pytest.raises(AccesRefuse):
        porte.patients(faux)
    assert porte.journal.lignes()[-1]["resultat"] == "refusé"


def test_le_cerveau_lit_par_la_meme_porte_avec_son_badge(porte, badges):
    from mcp import Client
    from mcp.server.mcpserver import MCPServer

    serveur = MCPServer(name="essai-clinique")
    brancher_sur_la_porte_des_agents(serveur, porte, badges["assistant"].travaille_pour(badges["soignant-etage-2"]))

    async def jouer():
        async with Client(serveur, mode="legacy") as client:
            outils = [t.name for t in (await client.list_tools()).tools]
            patients = (await client.call_tool("lire_dossier", {"quoi": "patients"})).structured_content
            refus = await client.call_tool("lire_dossier", {"quoi": "patient", "identifiant": "p07"})
            return outils, patients, refus

    outils, patients, refus = asyncio.run(jouer())
    assert outils == ["lire_dossier"], "un seul outil, qui lit : aucun outil pour écrire"
    assert {p["id"] for p in patients["resultat"]} == {"p01", "p02", "p03", "p04"}
    assert refus.structured_content["refuse"] is True
    lignes = porte.journal.lignes()
    assert [(l["qui"], l["pour"], l["resultat"]) for l in lignes] == [
        ("assistant", "soignant-etage-2", "lu"), ("assistant", "soignant-etage-2", "refusé")]


def test_non_teste_dit_que_le_badge_n_est_pas_un_controle_d_identite():
    assert "pas un vrai contrôle d'identité" in (RACINE / "NON_TESTE.md").read_text(encoding="utf-8")
