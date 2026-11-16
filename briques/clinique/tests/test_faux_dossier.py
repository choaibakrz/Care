"""La clinique en boîte — T02, le faux dossier (cahier 5.1 et 6). Internet coupé, aucun modèle.

On vérifie : tout se charge ; chaque fiche porte « inventé » ; aucun nom d'établissement, de médecin ou d'assurance
sans le mot « Exemple » ; les trois cas voulus sont là ; les règles de 6.2 sont tenues ; le dossier ne peut pas changer.
"""
from __future__ import annotations

import re
import shutil
from collections import Counter
from pathlib import Path

import pytest

from briques.clinique import dossier

RACINE = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def d():
    return dossier.charger()


def _textes(objet):
    """Toutes les chaînes d'un objet chargé (clés comprises)."""
    if isinstance(objet, str):
        yield objet
    elif hasattr(objet, "items"):
        for cle, valeur in objet.items():
            yield str(cle)
            yield from _textes(valeur)
    elif isinstance(objet, (list, tuple)):
        for valeur in objet:
            yield from _textes(valeur)


def _autres(d):
    return [p for p in d.patients if p["Patient"]["id"] != "p01"]


def test_tout_se_charge(d):
    assert len(d.patients) == 12
    assert len({p["Patient"]["id"] for p in d.patients}) == 12
    assert [len(l["points"]) for l in d.listes] == [6, 5, 7]
    assert len(d.reserve) == 5
    assert len(d.lieux["lieux"]) == 14  # cahier 6.5 : six lieux au rez-de-chaussée, huit au deuxième étage
    assert len(d.feuilles_sans_patient) == 1


def test_la_patiente_du_scenario(d):
    g = d.patient("p01")
    assert g["Patient"]["nom_affiche"] == "Madame Giulia B." and g["Patient"]["age"] == 71
    assert g["Patient"]["langue"] == "it" and "fr" in g["Patient"]["comprend_un_peu"]
    assert g["Encounter"]["chambre"] == 12 and g["Encounter"]["etage"] == 2
    assert g["Encounter"]["arrivee"] == {"jour": 1, "heure": "09:00"} and g["Encounter"]["duree_jours"] == 18
    assert len(g["habitudes"]) == 5
    assert [(r["jour"], r["heure"]) for r in g["Appointment"]] == [
        (1, "10:00"), (1, "11:00"), (1, "14:00"), (2, "08:00"), (2, "10:00")]
    assert [doc["genre"] for doc in g["DocumentReference"]] == [
        "lettre du médecin traitant", "liste de médicaments", "carte d'assurance"]
    assert "Assurance Exemple" in g["DocumentReference"][2]["texte"]
    assert g["CarePlan"][0] == "installation"


def test_les_onze_autres_suivent_les_regles(d):
    autres = _autres(d)
    assert Counter(p["Patient"]["langue"] for p in autres) == {"fr": 4, "de": 4, "it": 1, "en": 1, "pt": 1}
    chambres = [p["Encounter"]["chambre"] for p in d.patients]
    assert len(set(chambres)) == 12 and all(11 <= c <= 24 for c in chambres)
    for p in autres:
        assert 2 <= len(p["habitudes"]) <= 4, p["Patient"]["id"]
        assert len(p["Appointment"]) >= 1, p["Patient"]["id"]
        assert len(p["DocumentReference"]) <= 3, p["Patient"]["id"]
        assert len(p["Encounter"]["raison"].splitlines()) == 1 and len(p["Encounter"]["raison"]) <= 90


def test_les_trois_cas_voulus(d):
    autres = _autres(d)
    sans_document = [p for p in autres if not p["DocumentReference"]]
    assert len(sans_document) == 1
    assert all(len(p["DocumentReference"]) >= 1 for p in autres if p not in sans_document)

    def dates_en_conflit(p):
        dates = {}
        for doc in p["DocumentReference"]:
            for fait in doc.get("faits", ()):
                dates.setdefault(fait["evenement"], set()).add(fait["date"])
        return [e for e, valeurs in dates.items() if len(valeurs) > 1]

    en_conflit = [p for p in d.patients if dates_en_conflit(p)]
    assert len(en_conflit) == 1 and len(en_conflit[0]["DocumentReference"]) >= 2
    demain = [p for p in d.patients if p["Encounter"]["sortie_jour"] == 2]
    assert len(demain) == 1
    assert "sortie" in demain[0]["CarePlan"]
    assert len({sans_document[0]["Patient"]["id"], en_conflit[0]["Patient"]["id"], demain[0]["Patient"]["id"]}) == 3


def test_chaque_fiche_porte_invente(d):
    for p in d.patients:
        assert p["marque"] == "inventé", p["Patient"]["id"]
        assert "inventé" in p["Patient"]["nom_complet_affiche"]
        for doc in p["DocumentReference"]:
            assert doc["marque"] == "INVENTÉ" and "INVENTÉ" in doc["texte"], doc["id"]
    for feuille in d.feuilles_sans_patient:
        assert feuille["marque"] == "INVENTÉ" and "INVENTÉ" in feuille["texte"]
    for liste in d.listes:
        assert liste["marque"] == "exemple inventé, non médical, à remplacer par les listes de la clinique"
    assert d.lieux["marque"] == "inventé" and d.reserve_marque == "inventé"
    for fichier in dossier.fichiers():
        assert "invent" in fichier.read_text(encoding="utf-8").lower(), fichier.name


MOTS_D_ETABLISSEMENT = re.compile(
    r"\b(clinique|hôpital|hopital|klinik|spital|krankenhaus|ospedale|clinica|clínica|hospital|assurance|versicherung|"
    r"krankenkasse|assicurazione|insurance|seguro|dr|docteur|dott|dottore|dottoressa|doktor|doctor|doutor|cabinet|"
    r"praxis|studio medico|pharmacie|apotheke|farmacia)\b", re.IGNORECASE)


def test_aucun_nom_d_etablissement_sans_le_mot_exemple(d):
    # Le genre d'un document (« carte d'assurance ») est un mot du classement, pas le nom d'une assurance : on le saute.
    genres = {doc["genre"] for p in d.patients for doc in p["DocumentReference"]}
    # La marque des listes est une phrase du cahier (2.6), mot pour mot : « la clinique » n'y est pas un nom d'établissement.
    genres.add(dossier.MARQUE_LISTE)
    vus = 0
    for objet in (d.patients, d.listes, d.lieux, d.reserve, d.feuilles_sans_patient):
        for texte in _textes(objet):
            for ligne in texte.splitlines():
                if ligne not in genres and MOTS_D_ETABLISSEMENT.search(ligne):
                    vus += 1
                    assert "Exemple" in ligne, ligne
    assert vus >= 5, "le contrôle n'a presque rien trouvé à contrôler : il est sans doute cassé"


def test_prenom_et_initiale_seulement(d):
    for p in d.patients:
        assert re.fullmatch(r"(Madame|Monsieur) [A-ZÀ-Ý][a-zà-ÿ]+ [A-Z]\.", p["Patient"]["nom_affiche"]), p["Patient"]["nom_affiche"]


def test_pas_de_medecine_dans_les_donnees(d):
    for texte in _textes((d.patients, d.listes, d.feuilles_sans_patient)):
        assert not re.search(r"\d+\s?(mg|ml|µg|g/j|cp)\b", texte, re.IGNORECASE), texte
        assert not re.search(r"\b(diagnos\w+|posolog\w+|dosage|dosis|dose)\b", texte, re.IGNORECASE), texte


def test_les_listes_de_soin(d):
    installation, physio, sortie = d.listes
    assert (installation["id"], physio["id"], sortie["id"]) == ("installation", "avant_physio", "sortie")
    assert installation["points"][2]["texte"] == "Montrer la sonnette et la laisser à portée de main."
    assert all(point["pour"] in ("médecin", "soignant", "accueil") for point in sortie["points"])
    assert "à faire par un humain" in sortie["points"][6]["texte"]
    assert d.liste("installation") is installation


def test_les_documents_de_6_4(d):
    genres = Counter(doc["genre"] for p in d.patients for doc in p["DocumentReference"])
    for genre in ("lettre du médecin traitant", "liste de médicaments", "carte d'assurance", "rapport de radiologie",
                  "ordonnance de physiothérapie", "formulaire d'admission"):
        assert genres[genre] >= 1, genre
    formulaire = [doc for p in d.patients for doc in p["DocumentReference"] if doc["genre"] == "formulaire d'admission"]
    assert formulaire[0]["ecriture"] == "à la main, difficile"
    proprietaires = {p["Patient"]["id"] for p in d.patients for doc in p["DocumentReference"]
                     if doc["genre"] in ("rapport de radiologie", "ordonnance de physiothérapie", "formulaire d'admission")}
    assert "p01" not in proprietaires
    assert "patient" not in d.feuilles_sans_patient[0]


def test_les_lieux_et_les_distances(d):
    noms = {l["nom"] for l in d.lieux["lieux"]}
    for nom in ("Hall", "Accueil", "Salle 1", "Salle 2", "Bassin", "Poste de soins", "Réserve", "Chambre 11",
                "Chambre 12", "Chambre 13", "Chambre 14", "Salon"):
        assert nom in noms, nom
    assert all(v["metres"] > 0 and v["de"] in noms and v["a"] in noms for v in d.lieux["voisins"])
    distance = d.distance("Réserve", "Chambre 12")
    assert distance is not None and distance > 0
    assert d.distance("Chambre 12", "Réserve") == distance
    assert d.distance("Hall", "Chambre 12") is None, "les robots ne prennent pas l'ascenseur"
    assert d.distance("Hall", "Salle 2") > 0


def test_la_reserve(d):
    assert [o["nom"] for o in d.reserve] == ["grand coussin", "coussin de nuque", "couverture", "bouteille d'eau",
                                              "feuille d'exercices"]


def test_le_dossier_ne_peut_pas_changer(d):
    with pytest.raises(TypeError):
        d.patients[0]["Patient"]["age"] = 30
    with pytest.raises((TypeError, AttributeError)):
        d.patients[0]["habitudes"].append("triche")
    with pytest.raises(Exception):
        d.patients = ()
    assert dossier.empreinte() == dossier.empreinte() and len(dossier.empreinte()) == 64
    assert not [nom for nom in dir(dossier) if re.match(r"(ecrire|enregistrer|modifier|sauver)", nom)]


def test_une_fiche_sans_la_marque_est_refusee(tmp_path):
    copie = tmp_path / "faux_dossier"
    shutil.copytree(dossier.DOSSIER, copie)
    fiche = sorted((copie / "patients").glob("*.yaml"))[3]
    fiche.write_text(fiche.read_text(encoding="utf-8").replace("marque: inventé", "marque: vrai", 1), encoding="utf-8")
    with pytest.raises(dossier.DossierInvalide, match="inventé"):
        dossier.charger(copie)


def test_un_patient_en_moins_est_refuse(tmp_path):
    copie = tmp_path / "faux_dossier"
    shutil.copytree(dossier.DOSSIER, copie)
    sorted((copie / "patients").glob("*.yaml"))[-1].unlink()
    with pytest.raises(dossier.DossierInvalide, match="12"):
        dossier.charger(copie)


def test_non_teste_le_dit():
    texte = (RACINE / "NON_TESTE.md").read_text(encoding="utf-8")
    assert "inspiré de FHIR, non validé ; aucun lien avec un vrai logiciel de clinique n'a été essayé" in texte
