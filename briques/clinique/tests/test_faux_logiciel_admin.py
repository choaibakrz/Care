"""La clinique en boîte — L02a, le faux logiciel administratif et ses messages (avenant 4, L02 ; première moitié).

L02 est coupée en deux. Ici, L02a : le petit programme à part, sa liste, ses neuf sortes de messages. « Fini » veut dire :
- le faux logiciel est rangé à part, avec son propre fichier ; il porte l'étiquette SIMULÉ ;
- sa liste administrative recopie les douze patients du faux dossier, et les deux fichiers disent la même chose ;
- trois personnes inventées sont « en attente » ; notre système ne les connaît pas ;
- chaque événement écrit un message de la bonne sorte, un fichier texte par message, dans « du logiciel vers nous » ;
- on relit les neuf sortes de messages et on y retrouve le numéro du patient, le numéro du séjour et la chambre ;
- aucun message ne contient la raison du séjour, ni un nom de médecin, ni un numéro d'assurance sociale ;
- un patient verrouillé (les douze du faux dossier) ne bouge pas ;
- « remettre à zéro » vide les messages et remet les trois personnes en attente.
L02b fera : la page et ses boutons, les deux liens, la boîte noire. Aucun vrai logiciel : rien n'est connecté à rien.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml

import faux_logiciel_admin
from briques.clinique import dossier
from faux_logiciel_admin import logiciel

RACINE = Path(__file__).resolve().parents[3]
NEUF = {"A05": "la pré-admission", "A01": "l'admission", "A02": "le changement de chambre", "A03": "la sortie",
        "A08": "la correction d'une information", "A11": "l'annulation d'une admission", "A13": "l'annulation d'une sortie",
        "A21": "le départ en congé", "A22": "le retour de congé"}


@pytest.fixture
def faux(tmp_path):
    heure = {"jour": 1, "heure": "09:10"}
    return logiciel.FauxLogiciel(dossier=tmp_path / "faux_logiciel", heure=lambda: dict(heure)), heure


def _segments(texte: str) -> dict[str, list[str]]:
    return {ligne.split("|")[0]: ligne.split("|") for ligne in texte.splitlines() if ligne.strip()}


# ---------------------------------------------------------------------------------------------- à part
def test_le_faux_logiciel_est_range_a_part_et_ne_connait_pas_notre_systeme():
    dossier_du_logiciel = Path(faux_logiciel_admin.__file__).parent
    assert dossier_du_logiciel == RACINE / "faux_logiciel_admin" and logiciel.LISTE.parent == dossier_du_logiciel
    for fichier in dossier_du_logiciel.glob("*.py"):
        for noeud in ast.walk(ast.parse(fichier.read_text(encoding="utf-8"))):
            modules = [a.name for a in noeud.names] if isinstance(noeud, ast.Import) else \
                [noeud.module or ""] if isinstance(noeud, ast.ImportFrom) else []
            assert not any(m.startswith(("briques", "commun")) for m in modules), (fichier.name, modules)
    assert logiciel.ETIQUETTE == "SIMULÉ"
    texte = "".join(f.read_text(encoding="utf-8") for f in dossier_du_logiciel.iterdir() if f.is_file()).lower()
    assert "compatible" not in texte


def test_les_neuf_sortes_de_messages_sont_celles_de_l_avenant():
    assert {code: s["nom"] for code, s in logiciel.SORTES.items()} == NEUF


# ---------------------------------------------------------------------------------------------- la liste
def test_la_liste_recopie_les_douze_patients_et_dit_la_meme_chose_que_le_faux_dossier(faux):
    logiciel_, _ = faux
    liste = {p["numero_patient"]: p for p in logiciel_.liste()}
    d = dossier.charger()
    assert len(d.patients) == 12
    for p in d.patients:
        ligne = liste[p["Patient"]["id"]]
        assert ligne["nom"] == p["Patient"]["nom_affiche"] and ligne["langue"] == p["Patient"]["langue"]
        assert ligne["chambre"] == str(p["Encounter"]["chambre"])
        assert ligne["jour_entree"] == p["Encounter"]["arrivee"]["jour"] and ligne["jour_sortie_prevue"] == p["Encounter"]["sortie_jour"]
        assert ligne["date_naissance"] == ""  # le faux dossier ne donne pas de date de naissance : le champ reste vide
        assert ligne["assurance"] == "Assurance Exemple" and ligne["verrouille"] is True and ligne["statut"] == "admis"
        assert ligne["numero_sejour"]
    assert len({l["numero_sejour"] for l in liste.values()}) == len(liste) == 15
    brut = logiciel.LISTE.read_text(encoding="utf-8")
    for interdit in ("raison", "habitudes", "CarePlan", "médecin", "AVS"):
        assert interdit not in brut, interdit  # seulement des lignes administratives


def test_trois_personnes_inventees_sont_en_attente_et_notre_systeme_ne_les_connait_pas(faux):
    logiciel_, _ = faux
    attente = [p for p in logiciel_.liste() if p["statut"] == "en attente"]
    assert len(attente) == 3 and all(not p["verrouille"] and p["chambre"] == "" for p in attente)
    assert all("inventé" in p["nom"] or p["nom"].endswith(".") for p in attente)
    connus = {p["Patient"]["id"] for p in dossier.charger().patients}
    assert not connus & {p["numero_patient"] for p in attente}
    assert yaml.safe_load(logiciel.LISTE.read_text(encoding="utf-8"))["marque"] == "inventé"


# ---------------------------------------------------------------------------------------------- les messages
def _tout_jouer(logiciel_, numero):
    """Les neuf événements, dans un ordre possible, sur une personne en attente."""
    return [logiciel_.evenement("A05", numero), logiciel_.evenement("A01", numero, chambre="11"),
            logiciel_.evenement("A02", numero, chambre="13"), logiciel_.evenement("A08", numero, champ="langue", valeur="de"),
            logiciel_.evenement("A21", numero), logiciel_.evenement("A22", numero), logiciel_.evenement("A03", numero),
            logiciel_.evenement("A13", numero), logiciel_.evenement("A11", numero)]


def test_chaque_evenement_ecrit_un_message_de_la_bonne_sorte_un_fichier_par_message(faux):
    logiciel_, _ = faux
    numero = next(p["numero_patient"] for p in logiciel_.liste() if p["statut"] == "en attente")
    messages = _tout_jouer(logiciel_, numero)
    assert [m["sorte"] for m in messages] == ["A05", "A01", "A02", "A08", "A21", "A22", "A03", "A13", "A11"]
    fichiers = sorted((logiciel_.dossier / "du_logiciel_vers_nous").iterdir())
    assert len(fichiers) == 9 and all(f.suffix == ".hl7" for f in fichiers)
    assert [Path(m["fichier"]).name for m in messages] == [f.name for f in fichiers]
    assert len({_segments(f.read_text(encoding="utf-8"))["MSH"][9] for f in fichiers}) == 9  # un numéro unique par message


def test_on_relit_les_neuf_sortes_et_on_y_retrouve_le_patient_le_sejour_et_la_chambre(faux):
    logiciel_, heure = faux
    personne = next(p for p in logiciel_.liste() if p["statut"] == "en attente")
    for message in _tout_jouer(logiciel_, personne["numero_patient"]):
        texte = Path(message["fichier"]).read_text(encoding="utf-8")
        s = _segments(texte)
        assert set(s) >= {"MSH", "EVN", "PID", "PV1"}, message["sorte"]
        msh, evn, pid, pv1 = s["MSH"], s["EVN"], s["PID"], s["PV1"]
        assert msh[1] == "^~\\&" and msh[2] == "FAUX_LOGICIEL_ADMIN" and msh[11] == "2.5"  # qui envoie, la version
        assert msh[8] == f"ADT^{message['sorte']}" and evn[1] == message["sorte"]
        assert msh[6].startswith("20261114") and msh[6].endswith("0910") and evn[2] == msh[6]  # l'heure de démonstration
        assert pid[3].split("^")[0] == personne["numero_patient"]
        assert pid[5].split("^")[1] in personne["nom"] and pid[7] == personne["date_naissance"].replace("-", "")
        assert pid[15] in ("it", "de", "fr", "en", "pt")
        assert pv1[19] == personne["numero_sejour"]
        if message["sorte"] == "A05":
            assert pv1[3] == ""  # pré-admission : pas encore de chambre
        elif message["sorte"] == "A01":
            assert pv1[3].split("^")[1] == "11"
        else:
            assert pv1[3].split("^")[1] == "13", message["sorte"]
        if message["sorte"] == "A02":
            assert pv1[6].split("^")[1] == "11"  # la chambre d'avant
        assert "Assurance Exemple" in texte


def test_aucun_message_ne_contient_rien_de_medical(faux):
    logiciel_, _ = faux
    for p in [p for p in logiciel_.liste() if p["statut"] == "en attente"]:
        _tout_jouer(logiciel_, p["numero_patient"])
    raisons = {p["Encounter"]["raison"] for p in dossier.charger().patients}
    for fichier in (logiciel_.dossier / "du_logiciel_vers_nous").iterdir():
        texte = fichier.read_text(encoding="utf-8")
        assert not any(r in texte for r in raisons)
        for interdit in ("raison", "Dr", "Docteur", "médecin", "756."):  # ni raison, ni médecin, ni numéro d'assurance sociale
            assert interdit not in texte, (fichier.name, interdit)
        assert {l.split("|")[0] for l in texte.splitlines()} <= {"MSH", "EVN", "PID", "PV1", "IN1"}


# ---------------------------------------------------------------------------------------------- les règles
def test_un_patient_verrouille_ne_bouge_pas(faux):
    logiciel_, _ = faux
    avant = logiciel_.liste()
    for code, plus in (("A02", {"chambre": "14"}), ("A03", {}), ("A08", {"champ": "langue", "valeur": "en"}), ("A21", {})):
        with pytest.raises(logiciel.Refus, match="verrouillé"):
            logiciel_.evenement(code, "p01", **plus)
    assert logiciel_.liste() == avant and logiciel_.messages() == []


def test_un_evenement_impossible_est_refuse_en_clair(faux):
    logiciel_, _ = faux
    numero = next(p["numero_patient"] for p in logiciel_.liste() if p["statut"] == "en attente")
    with pytest.raises(logiciel.Refus, match="pas admise"):
        logiciel_.evenement("A03", numero)  # sortir quelqu'un qui n'est pas entré
    with pytest.raises(logiciel.Refus, match="chambre"):
        logiciel_.evenement("A01", numero, chambre="99")  # pas une chambre du cahier
    with pytest.raises(logiciel.Refus, match="inconnu"):
        logiciel_.evenement("A01", "p99", chambre="11")
    with pytest.raises(logiciel.Refus, match="sorte"):
        logiciel_.evenement("A99", numero)
    assert logiciel_.messages() == []


def test_deux_personnes_peuvent_partager_une_chambre(faux):
    logiciel_, _ = faux
    un, deux = [p["numero_patient"] for p in logiciel_.liste() if p["statut"] == "en attente"][:2]
    logiciel_.evenement("A01", un, chambre="12")  # la chambre de Madame Giulia B. : le faux logiciel ne refuse pas
    logiciel_.evenement("A01", deux, chambre="12")
    assert [p["chambre"] for p in logiciel_.liste() if p["numero_patient"] in (un, deux)] == ["12", "12"]


def test_l_etat_survit_a_un_redemarrage_du_faux_logiciel(faux, tmp_path):
    logiciel_, _ = faux
    numero = next(p["numero_patient"] for p in logiciel_.liste() if p["statut"] == "en attente")
    logiciel_.evenement("A01", numero, chambre="14")
    encore = logiciel.FauxLogiciel(dossier=logiciel_.dossier, heure=lambda: {"jour": 1, "heure": "10:00"})
    personne = next(p for p in encore.liste() if p["numero_patient"] == numero)
    assert personne["statut"] == "admis" and personne["chambre"] == "14"
    assert Path(encore.evenement("A03", numero)["fichier"]).name.startswith("0002_")  # la numérotation continue


def test_remettre_a_zero_vide_les_messages_et_remet_les_trois_personnes_en_attente(faux):
    logiciel_, _ = faux
    depart = logiciel_.liste()
    numero = next(p["numero_patient"] for p in depart if p["statut"] == "en attente")
    logiciel_.evenement("A01", numero, chambre="11")
    (logiciel_.dossier / "de_nous_vers_le_logiciel").mkdir(exist_ok=True)
    (logiciel_.dossier / "de_nous_vers_le_logiciel" / "x.txt").write_text("essai", encoding="utf-8")
    logiciel_.remettre_a_zero()
    assert logiciel_.liste() == depart and logiciel_.messages() == []
    assert list((logiciel_.dossier / "de_nous_vers_le_logiciel").iterdir()) == []


def test_non_teste_le_dit():
    assert ("messages fabriqués par nous au standard HL7 version 2.5 ; jamais essayés avec un vrai logiciel de clinique"
            in (RACINE / "NON_TESTE.md").read_text(encoding="utf-8"))
