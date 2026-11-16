"""La clinique en boîte — L04a, l'assistant prépare, une personne valide : la pré-admission (avenant 4, L04 ; première moitié).

« Votre assistant écrit-il dans le logiciel de la clinique ? » Jamais seul. L04 est coupée en deux. Ici, L04a. « Fini » veut dire :
- deux papiers inventés (une lettre de médecin, une carte d'assurance « Exemple ») n'arrivent que sur demande ; ils attendent
  dans « à trier » ; la remise à zéro les retire ;
- à partir de ces deux papiers, la pré-admission est proposée avec ses sources et un niveau de confiance ;
- un champ que les papiers ne donnent pas reste vide, avec « je ne suis pas sûr » ; rien de médical n'est repris ;
- la proposition vit dans le carnet ; une personne avec le badge « accueil » corrige, puis valide ;
- sans validation, le dossier « de nous vers le logiciel » reste vide ; après validation, le message part ;
- le message ne contient rien de médical ; le badge et l'heure de la validation sont dans la boîte noire.
L04b fera : le faux logiciel affiche la demande, « admettre » fait revenir une admission, les boutons à l'écran.
"""
from __future__ import annotations

import pytest

from briques.clinique import pre_admission
from briques.clinique.carnet import Carnet
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.papiers import Papiers
from briques.clinique.porte import AccesRefuse, JournalDesAcces, PorteDeLecture, charger_badges
from commun.bus import Bus
from conftest import lancer

BADGES = charger_badges()
ACCUEIL, SOIGNANT, ROBOT = BADGES["accueil"], BADGES["soignant-etage-2"], BADGES["robot-r1"]


@pytest.fixture
def banc(tmp_path):
    bus = Bus()
    horloge = HorlogeDeDemonstration(bus=bus)
    porte = PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour)
    carnet = Carnet(horloge=horloge)
    papiers = Papiers(porte, carnet)
    pre = pre_admission.PreAdmissions(papiers, carnet, tmp_path / "de_nous_vers_le_logiciel", horloge, bus=bus)
    return pre, papiers, carnet, bus, tmp_path / "de_nous_vers_le_logiciel"


def _ids(pile, tas):
    return [p["id"] for p in pile[tas]]


def _segments(texte):
    return {l.split("|")[0]: l.split("|") for l in texte.splitlines() if l.strip()}


# ---------------------------------------------------------------------------------------------- les deux papiers
def test_sans_demande_rien_ne_change(banc):
    pre, papiers, _, _, dossier = banc
    avant = papiers.pile(ACCUEIL)
    assert not set(pre_admission.IDS_DES_PAPIERS) & set(_ids(avant, "a_trier") + _ids(avant, "a_valider"))
    assert pre.propositions(ACCUEIL) == [] and not dossier.exists()


def test_les_deux_papiers_arrivent_sur_demande_et_attendent_dans_a_trier(banc):
    pre, papiers, _, _, _ = banc
    assert pre.faire_arriver() == list(pre_admission.IDS_DES_PAPIERS) and len(pre_admission.IDS_DES_PAPIERS) == 2
    pile = papiers.pile(ACCUEIL)
    assert set(pre_admission.IDS_DES_PAPIERS) <= set(_ids(pile, "a_trier"))  # aucun patient ne correspond : on ne range pas
    textes = pre_admission.papiers_inventes()
    assert all("INVENTÉ" in p["texte"] for p in textes)
    assert any("EXEMPLE-0001" in p["texte"] and "Assurance Exemple" in p["texte"] for p in textes)
    pre.remettre_a_zero()
    assert not set(pre_admission.IDS_DES_PAPIERS) & set(_ids(papiers.pile(ACCUEIL), "a_trier"))  # la remise à zéro les retire


# ---------------------------------------------------------------------------------------------- la proposition
def test_la_pre_admission_est_proposee_avec_ses_sources_et_sa_confiance(banc):
    pre, _, carnet, _, _ = banc
    pre.faire_arriver()
    p = pre.preparer(ACCUEIL)
    assert p["numero"] == "PA-0001" and p["etat"] == "proposée" and p["phrase"] == "L'assistant prépare. Une personne décide."
    champs = p["champs"]
    assert list(champs) == ["nom", "prenom", "date_naissance", "langue", "assurance", "date_arrivee_prevue"]
    lettre, carte = pre_admission.IDS_DES_PAPIERS
    assert champs["nom"]["valeur"] == "C." and champs["prenom"]["valeur"] == "Elena"
    assert champs["nom"]["sources"] == [lettre, carte] and champs["nom"]["confiance"] == "haute"  # les deux papiers le disent
    assert champs["date_naissance"] == {"valeur": "1950-02-02", "sources": [carte], "confiance": "moyenne", "dit": ""}
    assert champs["assurance"]["valeur"] == "Assurance Exemple — EXEMPLE-0001" and champs["assurance"]["sources"] == [carte]
    assert champs["date_arrivee_prevue"]["valeur"] == "2026-11-15" and champs["date_arrivee_prevue"]["sources"] == [lettre]
    # un champ que les papiers ne donnent pas reste vide
    assert champs["langue"] == {"valeur": "", "sources": [], "confiance": "", "dit": "je ne suis pas sûr"}
    lignes = carnet.lignes(pre_admission.GENRE)
    assert len(lignes) == 1 and lignes[0]["donnees"]["numero"] == "PA-0001" and lignes[0]["valide_par_un_humain"] is False


def test_rien_de_medical_n_est_repris(banc):
    pre, _, carnet, _, _ = banc
    pre.faire_arriver()
    p = pre.preparer(ACCUEIL)
    lettre = next(x for x in pre_admission.papiers_inventes() if "médecin" in x["genre"])
    medical = [l for l in lettre["texte"].splitlines() if l.startswith("Motif")]
    assert medical, "la lettre inventée doit avoir une ligne médicale, pour vérifier qu'elle n'est pas reprise"
    assert medical[0] not in str(p) and medical[0].split(":", 1)[1].strip() not in str(carnet.lignes(pre_admission.GENRE))
    assert "Dr" not in str(p["champs"])  # ni le nom du médecin


def test_deux_papiers_qui_ne_disent_pas_la_meme_chose_le_champ_reste_vide():
    lettre, carte = pre_admission.papiers_inventes()
    carte = {**carte, "texte": carte["texte"].replace("Prénom : Elena", "Prénom : Elisa")}
    champs = pre_admission.proposer([lettre, carte])
    assert champs["prenom"]["valeur"] == "" and champs["prenom"]["dit"] == "je ne suis pas sûr"
    assert champs["prenom"]["sources"] == [lettre["id"], carte["id"]]  # on montre les deux papiers qui se contredisent
    assert champs["nom"]["valeur"] == "C."


def test_sans_les_papiers_on_ne_prepare_rien_et_seul_l_accueil_prepare(banc):
    pre, _, _, _, _ = banc
    with pytest.raises(pre_admission.Refus, match="papiers"):
        pre.preparer(ACCUEIL)
    pre.faire_arriver()
    with pytest.raises(AccesRefuse):
        pre.preparer(SOIGNANT)
    with pytest.raises(AccesRefuse):
        pre.preparer(ROBOT)


# ---------------------------------------------------------------------------------------------- corriger, puis valider
def test_sans_validation_rien_ne_part(banc):
    pre, _, _, _, dossier = banc
    pre.faire_arriver()
    pre.preparer(ACCUEIL)
    pre.corriger(ACCUEIL, "PA-0001", "langue", "it")
    assert not dossier.exists() or list(dossier.iterdir()) == []


def test_une_personne_de_l_accueil_corrige_puis_valide_et_le_message_part(banc):
    pre, _, carnet, bus, dossier = banc
    pre.faire_arriver()
    pre.preparer(ACCUEIL)
    corrigee = pre.corriger(ACCUEIL, "PA-0001", "langue", "it")
    assert corrigee["champs"]["langue"] == {"valeur": "it", "sources": ["corrigé par accueil"], "confiance": "humain", "dit": ""}
    validee = lancer(pre.valider(ACCUEIL, "PA-0001"))
    assert validee["etat"] == "validée" and validee["valide"]["par"] == "accueil" and validee["valide"]["quand"]
    fichiers = list(dossier.iterdir())
    assert len(fichiers) == 1 and fichiers[0].name == "0001_A05_PA-0001.hl7"
    s = _segments(fichiers[0].read_text(encoding="utf-8"))
    assert s["MSH"][2] == "CLINIQUE_EN_BOITE" and s["MSH"][8] == "ADT^A05" and s["MSH"][11] == "2.5" and s["EVN"][1] == "A05"
    assert s["PID"][3] == "" and s["PID"][5] == "C.^Elena" and s["PID"][7] == "19500202" and s["PID"][15] == "it"
    assert s["PV1"][2] == "P" and s["PV1"][5] == "PA-0001"  # le numéro de la pré-admission relie la demande et la réponse
    assert s["PV2"][8] == "20261115" and s["IN1"][4] == "Assurance Exemple" and s["IN1"][36] == "EXEMPLE-0001"
    # le carnet : proposée, corrigée, validée par un humain
    lignes = carnet.lignes(pre_admission.GENRE)
    assert [l["donnees"]["etat"] for l in lignes] == ["proposée", "proposée", "validée"]
    assert lignes[-1]["valide_par_un_humain"] is True and lignes[-1]["qui"] == "accueil"
    # la boîte noire : le badge de la personne qui a validé, et l'heure
    notes = [e.donnees for e in bus.historique if e.type == "note" and e.donnees.get("quoi") == "pre_admission_validee"]
    assert len(notes) == 1 and notes[0]["badge"] == "accueil" and notes[0]["numero"] == "PA-0001" and notes[0]["heure"]
    assert notes[0]["fichier"] == "0001_A05_PA-0001.hl7" and "Elena" not in str(notes[0])


def test_le_message_ne_contient_rien_de_medical(banc):
    pre, _, _, _, dossier = banc
    pre.faire_arriver()
    pre.preparer(ACCUEIL)
    lancer(pre.valider(ACCUEIL, "PA-0001"))
    texte = next(dossier.iterdir()).read_text(encoding="utf-8")
    assert {l.split("|")[0] for l in texte.splitlines()} <= {"MSH", "EVN", "PID", "PV1", "PV2", "IN1"}
    for interdit in ("Motif", "Dr", "médecin", "réadaptation", "756."):
        assert interdit not in texte, interdit


def test_seul_l_accueil_valide_une_fois_et_plus_rien_ne_change_apres(banc):
    pre, _, _, _, dossier = banc
    pre.faire_arriver()
    pre.preparer(ACCUEIL)
    for badge in (SOIGNANT, ROBOT, BADGES["assistant"]):
        with pytest.raises(AccesRefuse):
            lancer(pre.valider(badge, "PA-0001"))
    assert not dossier.exists() or list(dossier.iterdir()) == []
    lancer(pre.valider(ACCUEIL, "PA-0001"))
    with pytest.raises(pre_admission.Refus, match="déjà"):
        lancer(pre.valider(ACCUEIL, "PA-0001"))
    with pytest.raises(pre_admission.Refus, match="déjà"):
        pre.corriger(ACCUEIL, "PA-0001", "langue", "de")
    assert len(list(dossier.iterdir())) == 1


def test_sans_nom_ou_sans_prenom_on_ne_valide_pas(banc):
    pre, _, _, _, dossier = banc
    pre.faire_arriver()
    pre.preparer(ACCUEIL)
    pre.corriger(ACCUEIL, "PA-0001", "prenom", "")
    with pytest.raises(pre_admission.Refus, match="prénom"):
        lancer(pre.valider(ACCUEIL, "PA-0001"))
    with pytest.raises(pre_admission.Refus, match="champ"):
        pre.corriger(ACCUEIL, "PA-0001", "raison", "x")
    with pytest.raises(pre_admission.Refus, match="langue"):
        pre.corriger(ACCUEIL, "PA-0001", "langue", "klingon")
    assert not dossier.exists() or list(dossier.iterdir()) == []
