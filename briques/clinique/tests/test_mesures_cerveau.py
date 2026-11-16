"""La clinique en boîte — T21, les temps de réponse et les taux d'erreur mesurés, dans la fiche de vérité.

« Fini » veut dire :
- chaque commande de mesure du vrai cerveau garde son résultat dans un fichier (dossier journal, jamais envoyé) ;
- la fiche de vérité lit ces fichiers : cinq lignes de plus, avec le chiffre, le temps, le nombre de réponses de plus de
  cinq secondes, l'étiquette (cerveau RÉEL, FAUX ROBOT ou aucun robot) et la date ;
- rien n'est tapé à la main : un chiffre changé dans le fichier change la ligne ;
- pas de fichier (ou fichier abîmé) : « non mesuré sur cet ordinateur », avec la commande à lancer — jamais un chiffre ;
- un essai fait avec un cerveau de test n'est jamais gardé comme une mesure du vrai cerveau ;
- les sept lignes du cahier ne changent pas, et l'étape 13 de la répétition réussit toujours.
"""
from __future__ import annotations

import json
import re

import pytest

from briques.clinique import fiche, mesures_cerveau

QUAND = "2026-11-12T13:03:00+01:00"
EXEMPLES = {
    "apertus_essai": {"possible": True, "quand": QUAND, "cerveau": "Apertus 8B", "demandes": 120, "bonnes": 112,
                      "temps_median_ms": 1478, "temps_max_ms": 2394, "plus_de_5_s": []},
    "resume": {"possible": True, "quand": QUAND, "cerveau": "Apertus 8B", "demandees": 13, "ecrites": 0,
               "ligne_mediane_ms": 6367, "ligne_max_ms": 7827, "lignes_lentes": 11},
    "papiers": {"possible": True, "quand": QUAND, "cerveau": "Apertus 8B", "papiers": 9, "bien_ranges_surs": 2,
                "mal_ranges_dits_surs": 0, "regles_seules_bien_ranges_surs": 6, "temps_median_ms": 3668, "temps_max_ms": 4150,
                "plus_de_5_s": []},
    "tirage": {"numero": 1, "quand": QUAND, "cerveau": "Apertus 8B", "demandes": 30, "compris": 26, "bonnes": 29,
               "interdits_executes": 0, "partis_a_tort": 1, "temps_median_ms": 1450, "temps_max_ms": 9255,
               "plus_de_5_s": [{"rang": 15}, {"rang": 18}]},
    "chaine": {"possible": True, "quand": QUAND, "pieces": "cerveau : RÉEL, Apertus 8B", "phrases": [{}] * 12, "sans_reponse": 0,
               "total_median_ms": 2532, "total_max_ms": 4225, "plus_de_5_s": [],
               "memoire": {"moins_de_libre_go": 1.48, "echange_en_plus_go": 0.62, "manque": True}},
}


def _remplir(dossier):
    for nom, mesure in EXEMPLES.items():
        mesures_cerveau.noter(nom, mesure, dossier)


def test_les_cinq_lignes_viennent_des_fichiers_avec_chiffre_temps_etiquette_et_date(tmp_path):
    _remplir(tmp_path)
    lignes = {l["titre"]: l["valeur"] for l in mesures_cerveau.lignes_de_la_fiche(tmp_path)}
    assert len(lignes) == 5 and all("12.11.2026" in v for v in lignes.values())
    comprendre = lignes["Cerveau — comprendre un ordre"]
    assert "112 bonnes réponses sur 120" in comprendre and "médian 1478 ms" in comprendre and "le plus long 2394 ms" in comprendre
    assert "aucune réponse de plus de 5 secondes" in comprendre and "RÉEL" in comprendre and "FAUX ROBOT" in comprendre
    assert "0 ligne gardée sur 13" in lignes["Cerveau — le résumé du médecin"] and "11 de plus de 5 secondes" in lignes["Cerveau — le résumé du médecin"]
    papiers = lignes["Cerveau — le rangement des papiers"]
    assert "2 bien rangés et sûrs sur 9" in papiers and "règles simples seules : 6 sur 9" in papiers and "0 mal rangé dit sûr" in papiers
    tirage = lignes["Cerveau — le tirage de trente demandes"]
    assert "compris 26 sur 30" in tirage and "gestes interdits exécutés : 0" in tirage and "gestes partis à tort : 1" in tirage
    assert "2 réponses de plus de 5 secondes" in tirage and "9255 ms" in tirage
    chaine = lignes["La chaîne entière : écoute, cerveau, voix"]
    assert "médian 2532 ms" in chaine and "le plus long 4225 ms" in chaine and "LA MÉMOIRE MANQUE" in chaine and "aucun robot" in chaine


def test_rien_n_est_tape_un_chiffre_change_dans_le_fichier_change_la_ligne(tmp_path):
    _remplir(tmp_path)
    mesures_cerveau.noter("apertus_essai", {**EXEMPLES["apertus_essai"], "bonnes": 97, "plus_de_5_s": [{}, {}, {}]}, tmp_path)
    ligne = mesures_cerveau.lignes_de_la_fiche(tmp_path)[0]["valeur"]
    assert "97 bonnes réponses sur 120" in ligne and "3 réponses de plus de 5 secondes" in ligne


@pytest.mark.parametrize("cas", ["absent", "abime", "pas_possible"])
def test_sans_mesure_non_mesure_et_la_commande_jamais_un_chiffre(tmp_path, cas):
    if cas == "abime":
        (tmp_path / "apertus_essai.json").write_text("{pas du json", encoding="utf-8")
    if cas == "pas_possible":
        mesures_cerveau.noter("apertus_essai", {"possible": False, "raison": "modèle absent", "quand": QUAND}, tmp_path)
    lignes = mesures_cerveau.lignes_de_la_fiche(tmp_path)
    assert len(lignes) == 5
    premiere = lignes[0]["valeur"]
    assert premiere.startswith(fiche.NON_MESURE) and "python3 lancer.py apertus-essai" in premiere
    assert not re.search(r"\d+ (sur|ms)", premiere)
    for ligne, commande in zip(lignes[1:], ("resume-apertus", "papiers-apertus", "tirage-apertus", "chaine-mesure")):
        assert ligne["valeur"].startswith(fiche.NON_MESURE) and f"python3 lancer.py {commande}" in ligne["valeur"]


def test_un_cerveau_de_test_n_est_jamais_garde_comme_une_mesure_du_vrai_cerveau(tmp_path):
    assert mesures_cerveau.noter("tirage", {**EXEMPLES["tirage"], "cerveau": "cerveau de test (réponses fixes)"}, tmp_path) is None
    assert not (tmp_path / "tirage.json").exists()
    assert mesures_cerveau.noter("tirage", EXEMPLES["tirage"], tmp_path) is not None
    assert json.loads((tmp_path / "tirage.json").read_text(encoding="utf-8"))["compris"] == 26


def test_la_repetition_affiche_les_sept_lignes_du_cahier_et_celles_du_cerveau_et_reussit_toujours():
    from briques.clinique import repetition

    assert len(fiche.LIGNES_DU_CAHIER) == 7
    lignes: list[str] = []
    assert repetition.jouer(ecrire=lignes.append) == 0  # l'étape 13 réussit toujours
    texte = "\n".join(lignes)
    for titre in (*fiche.LIGNES_DU_CAHIER, *mesures_cerveau.TITRES.values()):
        assert f"· {titre} : " in texte, titre
    assert "les 7 lignes du cahier sont là" in texte
