"""La clinique en boîte — H10a, le mode interprète : le cœur et la mesure (message de Hiba, 12.11.2026).

« La personne qui présente répondra au jury en français. La boîte redira chaque phrase en anglais, à voix haute. »
Cette première moitié fait le cœur (un son en français → un texte anglais, contrôlé, dit par la voix) et la mesure
sur dix phrases. Les deux boutons de l'écran de régie sont la seconde moitié (H10b).
« Fini » veut dire :
- la phrase dite en français sort en anglais, avec l'étiquette « TRADUCTION AUTOMATIQUE EN DIRECT », et la voix la dit ;
- les mots fixés d'avance sont dans un fichier lisible ; s'ils ne sont pas respectés, c'est compté comme une erreur ;
- les chiffres s'affichent en chiffres ; un chiffre perdu ou changé est compté comme une erreur ;
- les réponses préparées sont dans un fichier, avec l'étiquette « TRADUCTION PRÉPARÉE » ;
- le délai est noté pour chaque phrase (écoute, traduction, voix, total) ; les erreurs sont comptées telles quelles ;
- rien ne sort de l'ordinateur : la pièce n'appelle que des programmes de cet ordinateur ;
- une pièce en panne : la phrase est comptée « sans traduction », jamais cachée.
Ces essais prennent de fausses pièces : ni son, ni modèle.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from briques.clinique import interprete

RACINE = Path(__file__).resolve().parents[3]


def _pieces(traductions, ecoute_s=0.5, traduction_s=1.2, voix_s=0.4, casse=None):
    montre = {"t": 0.0}

    def ecouter(son, langue):
        if casse == "ecoute":
            raise RuntimeError("micro")
        montre["t"] += ecoute_s
        return {"texte": str(son)}

    def traduire(texte, mots):
        if casse == "traduction":
            raise RuntimeError("modèle éteint")
        montre["t"] += traduction_s
        return traductions[texte]

    dites = []

    def dire(texte, langue, sortie):
        montre["t"] += voix_s
        dites.append((texte, langue))
        return Path(sortie)

    return ecouter, traduire, dire, (lambda: montre["t"]), dites


def _interpreter(fr, en, tmp_path, **kw):
    ecouter, traduire, dire, montre, dites = _pieces({fr: en}, **kw)
    return interprete.interpreter(fr, tmp_path, ecouter=ecouter, traduire=traduire, dire=dire, montre=montre), dites


# ---------------------------------------------------------------------------------------------- les fichiers
def test_les_mots_fixes_sont_dans_un_fichier_lisible_avec_les_cinq_mots_de_hiba():
    donnees = yaml.safe_load(interprete.FICHIER_MOTS.read_text(encoding="utf-8"))
    assert [m["fr"] for m in donnees["mots"]] == ["soignant", "course", "boîte", "palier", "seuil d'arrêt"]
    assert all(m["en"].strip() for m in donnees["mots"]) and "à confirmer par Hiba" in donnees["marque"]
    assert len(interprete.charger_les_mots()) == 5


def test_les_reponses_preparees_sont_dans_un_fichier_et_portent_leur_etiquette():
    reponses = interprete.reponses_preparees()
    assert len(reponses) >= 3 and all(r["etiquette"] == "TRADUCTION PRÉPARÉE" for r in reponses)
    assert all(r["fr"].strip() and r["en"].strip() and r["id"] for r in reponses)
    brut = interprete.FICHIER_REPONSES.read_text(encoding="utf-8")
    assert "pas relus" in brut and "à remplacer par" in brut
    assert not re.search(r"\d", " ".join(r["en"] + r["fr"] for r in reponses))  # des exemples sans aucun chiffre de mesure


# ---------------------------------------------------------------------------------------------- une phrase
def test_une_phrase_sort_en_anglais_avec_l_etiquette_les_delais_et_la_voix(tmp_path):
    r, dites = _interpreter("Le robot apporte une couverture.", "The robot brings a blanket.", tmp_path)
    assert r["etiquette"] == "TRADUCTION AUTOMATIQUE EN DIRECT"
    assert r["fr"] == "Le robot apporte une couverture." and r["en"] == "The robot brings a blanket." and r["erreurs"] == []
    assert (r["ecoute_ms"], r["traduction_ms"], r["voix_ms"], r["total_ms"]) == (500, 1200, 400, 2100)
    assert dites == [("The robot brings a blanket.", "en")]


def test_un_mot_fixe_non_respecte_est_compte_comme_une_erreur(tmp_path):
    bonne, _ = _interpreter("Le soignant demande une course.", "The caregiver asks for an errand.", tmp_path)
    assert bonne["erreurs"] == []
    fausse, _ = _interpreter("Le soignant demande une course.", "The nurse asks for a race.", tmp_path)
    assert sorted(fausse["erreurs"]) == ["mot fixé non respecté : « course » doit donner « errand »",
                                         "mot fixé non respecté : « soignant » doit donner « caregiver »"]
    pluriel, _ = _interpreter("Les soignantes ferment la boîte au seuil d'arrêt.", "The caregivers close the box at the stop threshold.", tmp_path)
    assert pluriel["erreurs"] == []
    assert fausse["en"] == "The nurse asks for a race."  # affichée telle quelle : l'erreur se voit, elle n'est pas maquillée


def test_un_mot_fixe_employe_a_tort_est_compte_aussi(tmp_path):
    """Mesuré avec le vrai Apertus le 12.11 : « gardien » rendu par « caregiver », « l'arrêt » par « stop threshold »."""
    gardien, _ = _interpreter("Chaque course passe par le gardien.", "Each errand passes through the caregiver.", tmp_path)
    assert gardien["erreurs"] == ["mot fixé employé à tort : « caregiver » alors que la phrase ne dit pas « soignant »"]
    arret, _ = _interpreter("Le soignant garde la main sur l'arrêt.", "The caregiver keeps a hand on the stop threshold.", tmp_path)
    assert arret["erreurs"] == ["mot fixé employé à tort : « stop threshold » alors que la phrase ne dit pas « seuil d'arrêt »"]
    juste, _ = _interpreter("Chaque course passe par le gardien.", "Each errand goes through the guardian.", tmp_path)
    assert juste["erreurs"] == []


def test_les_chiffres_s_affichent_en_chiffres(tmp_path):
    r, dites = _interpreter("Le robot a fait 20 courses en 3 jours.", "The robot did twenty errands in three days.", tmp_path)
    assert r["en"] == "The robot did 20 errands in 3 days." and r["erreurs"] == []
    assert dites[0][0] == "The robot did 20 errands in 3 days."
    lettres, _ = _interpreter("Il y a quatre robots et deux paliers.", "There are four robots and two levels.", tmp_path)
    assert lettres["en"] == "There are 4 robots and 2 levels." and lettres["erreurs"] == []


def test_un_chiffre_perdu_ou_change_est_compte_comme_une_erreur(tmp_path):
    change, _ = _interpreter("Le robot a fait 20 courses.", "The robot did 30 errands.", tmp_path)
    assert change["erreurs"] == ["chiffre perdu ou changé : 20"] and change["en"] == "The robot did 30 errands."
    perdu, _ = _interpreter("Il reste 112 demandes sur 120.", "There are requests left.", tmp_path)
    assert perdu["erreurs"] == ["chiffre perdu ou changé : 112, 120"]
    pronom, _ = _interpreter("Personne ne remplace le soignant.", "No one replaces the caregiver.", tmp_path)
    assert pronom["en"] == "No one replaces the caregiver."  # « one » n'est pas un chiffre ici : pas touché


@pytest.mark.parametrize("panne, mot", [("ecoute", "écoute"), ("traduction", "traduction")])
def test_une_piece_en_panne_la_phrase_reste_sans_traduction_et_c_est_dit(tmp_path, panne, mot):
    r, dites = _interpreter("Bonjour.", "Hello.", tmp_path, casse=panne)
    assert r["en"] is None and r["total_ms"] is None and mot in r["panne"] and dites == []
    assert r["erreurs"] == ["pas de traduction"]


def test_une_traduction_vide_ou_restee_en_francais_est_une_erreur(tmp_path):
    vide, _ = _interpreter("Le soignant arrive.", "   ", tmp_path)
    assert vide["erreurs"] == ["pas de traduction"]
    meme, dites = _interpreter("Le soignant arrive.", "Le soignant arrive.", tmp_path)
    assert "la sortie est restée en français" in meme["erreurs"] and dites == []


# ---------------------------------------------------------------------------------------------- la mesure
def test_la_mesure_compte_les_erreurs_telles_quelles_et_note_le_delai_de_chaque_phrase(tmp_path):
    phrases = ["Le soignant demande une course.", "Le robot a fait 20 courses.", "La boîte marche sans Internet."]
    sorties = {phrases[0]: "The nurse asks for a race.", phrases[1]: "The robot did 20 errands.", phrases[2]: "The box works without the Internet."}
    ecouter, traduire, dire, montre, _ = _pieces(sorties)
    bilan = interprete.mesurer(phrases, tmp_path, ecouter=ecouter, traduire=traduire, dire=dire, montre=montre,
                               sons={p: p for p in phrases}, chemin="essai", origine="phrases d'essai")
    assert bilan["phrases"] == 3 and bilan["sorties_en_anglais"] == 3 and bilan["sans_erreur"] == 2 and bilan["erreurs"] == 2
    assert [l["total_ms"] for l in bilan["detail"]] == [2100, 2100, 2100] and bilan["total_median_ms"] == 2100
    texte = "\n".join(interprete.rapport([bilan]))
    assert "2 phrases sans erreur comptée sur 3" in texte and "2 erreurs comptées" in texte
    assert "The nurse asks for a race." in texte and "mot fixé non respecté" in texte
    assert "phrases d'essai" in texte and "TRADUCTION AUTOMATIQUE EN DIRECT" in texte


def test_les_dix_phrases_de_la_mesure_servent_les_mots_fixes_et_des_chiffres():
    assert len(interprete.PHRASES) == 10
    tout = " ".join(interprete.PHRASES).lower()
    for mot in ("soignant", "course", "boîte", "palier", "seuil d'arrêt"):
        assert mot in tout, mot
    assert sum(bool(re.search(r"\d", p)) for p in interprete.PHRASES) >= 3


def test_rien_ne_sort_de_l_ordinateur_et_la_commande_existe():
    source = Path(interprete.__file__).read_text(encoding="utf-8")
    assert re.findall(r"https?://[^\s\"']+", source) == []  # la seule adresse est celle du serveur local, lue dans les réglages
    assert interprete.SERVEUR_LOCAL.startswith("127.0.0.1")
    assert '"interprete-mesure"' in (RACINE / "lancer.py").read_text(encoding="utf-8")
    vide = interprete.rapport([{"possible": False, "raison": "essai", "chemin": "x", "quand": "2026-11-12T16:00:00+01:00"}])
    assert "PAS POSSIBLE" in "\n".join(vide) and not re.search(r"\d+ ms|\d+ phrases? sans", "\n".join(vide))
